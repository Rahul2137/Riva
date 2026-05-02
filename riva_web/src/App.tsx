import { useState, useRef, useEffect } from 'react';
import { Mic, Loader2, LogIn, LogOut, AlertCircle, Sparkles, MessageSquare, Calendar as CalendarIcon, Wallet, CheckSquare } from 'lucide-react';
import { signInWithGoogle, signOut, auth } from './firebase';
import { onAuthStateChanged, type User } from 'firebase/auth';
import { AudioRecorder } from './audioRecorder';
import { CalendarTab } from './components/CalendarTab';
import { FinanceTab } from './components/FinanceTab';
import { TodoTab } from './components/TodoTab';
import { PCMPlayer } from './utils/pcmPlayer';
import './index.css';

interface Message {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
}

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/stream';
const GEMINI_WS_URL = import.meta.env.VITE_GEMINI_WS_URL || 'ws://127.0.0.1:8000/gemini-live';
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

type Tab = 'voice' | 'calendar' | 'tasks' | 'finance';

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('voice');
  
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false); // true while RIVA is playing audio
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLiveMode, setIsLiveMode] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<AudioRecorder | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const shouldResumeListeningRef = useRef(false);
  const ttsUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const pcmPlayerRef = useRef<PCMPlayer | null>(null);
  const isRivaPlayingRef = useRef(false); // mirror of isSpeaking without stale closure issues
  const bargeInSentRef = useRef(false);   // prevent duplicate barge_in signals per utterance
  const bargeInTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rivaStoppedAtRef = useRef<number>(0);
  const noiseFloorRef = useRef<number>(0.02); // adaptive ambient noise estimate

  // ── Barge-in config (Adaptive VAD) ──────────────────────────────────
  // Instead of a fixed threshold, we measure the ambient noise floor in real
  // time and set the trigger relative to it. This works in quiet AND noisy rooms.
  const BARGE_IN_MULTIPLIER = 3.5; // trigger at noise_floor × this
  const BARGE_IN_MIN_RMS    = 0.045; // never trigger below this (truly silent rooms)
  const BARGE_IN_MAX_RMS    = 0.20;  // cap so loud rooms don't make it impossible
  const BARGE_IN_DEBOUNCE_MS = 80;   // must stay above threshold for this long
  const BARGE_IN_COOLDOWN_MS = 250;  // ignore frames right after RIVA finishes

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeTab]);

  // Auth listener
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setUser(currentUser);
      if (currentUser) {
        const token = await currentUser.getIdToken();
        setIdToken(token);
        // Inform backend about login
        try {
          await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idToken: token })
          });
        } catch (err) {
          console.error("Backend login sync failed", err);
        }
      } else {
        setIdToken(null);
        disconnectWebSocket();
      }
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    return () => {
      window.speechSynthesis?.cancel();
    };
  }, []);

  const addMessage = (sender: Message['sender'], text: string) => {
    setMessages(prev => [...prev, { id: Date.now().toString(), sender, text }]);
  };

  const handleLogin = async () => {
    try {
      setError(null);
      await signInWithGoogle();
    } catch (err: any) {
      setError(err.message || "Failed to sign in. Mock mode active.");
      // Fallback for demo without valid Firebase config
      setUser({ displayName: "Guest User", photoURL: "", email: "guest@example.com", uid: "mock_user" } as User);
      setIdToken("mock_token");
    }
  };

  const handleLogout = async () => {
    try {
      await signOut();
    } catch (err) {
      setUser(null);
      setIdToken(null);
    }
  };

  const stopRecorder = () => {
    if (recorderRef.current) {
      recorderRef.current.stop();
      recorderRef.current = null;
    }
    setIsListening(false);
  };

  const disconnectWebSocket = () => {
    shouldResumeListeningRef.current = false;
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      ttsUtteranceRef.current = null;
    }
    if (pcmPlayerRef.current) {
      pcmPlayerRef.current.close();
      pcmPlayerRef.current = null;
    }
    stopRecorder();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsListening(false);
    setIsProcessing(false);
  };

  const resumeRecordingIfNeeded = () => {
    if (
      !shouldResumeListeningRef.current ||
      recorderRef.current ||
      wsRef.current?.readyState !== WebSocket.OPEN
    ) {
      return;
    }

    startRecording();
  };

  const connectWebSocket = () => {
    if (!idToken || wsRef.current) return;
    
    const baseUrl = isLiveMode ? GEMINI_WS_URL : WS_URL;
    const url = `${baseUrl}?token=${encodeURIComponent(idToken)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    shouldResumeListeningRef.current = true;

    if (isLiveMode) {
      const player = new PCMPlayer(24000); // Gemini Live outputs 24kHz
      // Track when RIVA stops speaking so we reset barge-in state
      player.onPlaybackEnd = () => {
        isRivaPlayingRef.current = false;
        bargeInSentRef.current = false;
        // Cancel any pending debounce timer when RIVA finishes
        if (bargeInTimerRef.current) {
          clearTimeout(bargeInTimerRef.current);
          bargeInTimerRef.current = null;
        }
        // Record when RIVA stopped so we can apply a short cooldown
        rivaStoppedAtRef.current = Date.now();
        setIsSpeaking(false);
      };
      pcmPlayerRef.current = player;
    }

    ws.onopen = () => {
      startRecording();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (isLiveMode) {
          if (data.type === 'audio') {
            const binaryString = window.atob(data.data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
              bytes[i] = binaryString.charCodeAt(i);
            }
            const pcm16 = new Int16Array(bytes.buffer);
            // Mark RIVA as playing so barge-in detector activates
            isRivaPlayingRef.current = true;
            setIsSpeaking(true);
            pcmPlayerRef.current?.feed(pcm16);
          } else if (data.type === 'turn_complete') {
            // Optional: visual feedback
          } else if (data.type === 'reconnecting') {
            setIsProcessing(true);
            setError(`Reconnecting to Gemini (attempt ${data.attempt})…`);
          } else if (data.type === 'reconnected') {
            setIsProcessing(false);
            setError(null);
          } else if (data.type === 'session_end') {
            // User said goodbye — close everything cleanly
            addMessage('system', 'Session ended. Goodbye!');
            stopListening();
          } else if (data.error) {
            setError(data.error);
            stopListening();
          }
        } else {
          if (data.type === 'assistant_response') {
            if (data.is_final) {
              setIsProcessing(false);
            }
            addMessage('assistant', data.response);
            speakText(data.response, data.is_final);
          } else if (data.type === 'transcript') {
            addMessage('user', data.text);
            setIsProcessing(true);
            stopRecorder();
          }
        }
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket Error", err);
      setError("Connection error to backend voice stream.");
      stopListening();
    };

    ws.onclose = () => {
      stopListening();
    };
  };

  const startRecording = () => {
    if (recorderRef.current || wsRef.current?.readyState !== WebSocket.OPEN) {
      return;
    }

    const recorder = new AudioRecorder((pcmData) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(pcmData.buffer as ArrayBuffer);
      }
    });

    // ── Barge-in detector ─────────────────────────────────────────────
    // If the user's mic level crosses the threshold while RIVA is speaking,
    // stop RIVA's audio immediately and tell Gemini the user is speaking.
    recorder.onRMSLevel = (rms: number) => {
      // ── Phase 1: Update noise floor while RIVA is NOT speaking ──────
      // Exponential moving average of ambient RMS — adapts to the room.
      // α=0.02 means the floor updates slowly (won't spike on a single loud frame).
      if (!isRivaPlayingRef.current) {
        noiseFloorRef.current = noiseFloorRef.current * 0.98 + rms * 0.02;
      }

      // ── Phase 2: Barge-in detection while RIVA IS speaking ──────────
      if (
        !isLiveMode ||
        !isRivaPlayingRef.current ||
        bargeInSentRef.current ||
        wsRef.current?.readyState !== WebSocket.OPEN
      ) {
        if (!isRivaPlayingRef.current && bargeInTimerRef.current) {
          clearTimeout(bargeInTimerRef.current);
          bargeInTimerRef.current = null;
        }
        return;
      }

      // Cooldown right after RIVA finishes to avoid pickup of last audio
      if (Date.now() - rivaStoppedAtRef.current < BARGE_IN_COOLDOWN_MS) return;

      // Adaptive threshold: noise_floor × multiplier, clamped to [min, max]
      const adaptiveThreshold = Math.min(
        BARGE_IN_MAX_RMS,
        Math.max(BARGE_IN_MIN_RMS, noiseFloorRef.current * BARGE_IN_MULTIPLIER)
      );

      if (rms > adaptiveThreshold) {
        if (!bargeInTimerRef.current) {
          bargeInTimerRef.current = setTimeout(() => {
            bargeInTimerRef.current = null;
            if (
              isRivaPlayingRef.current &&
              !bargeInSentRef.current &&
              wsRef.current?.readyState === WebSocket.OPEN
            ) {
              bargeInSentRef.current = true;
              pcmPlayerRef.current?.interrupt();
              isRivaPlayingRef.current = false;
              setIsSpeaking(false);
              wsRef.current.send(JSON.stringify({ type: 'barge_in' }));
              console.log(
                `[BARGE-IN] rms=${rms.toFixed(3)} threshold=${adaptiveThreshold.toFixed(3)} floor=${noiseFloorRef.current.toFixed(3)}`
              );
            }
          }, BARGE_IN_DEBOUNCE_MS);
        }
      } else {
        // Fell below threshold — cancel pending timer (transient noise spike)
        if (bargeInTimerRef.current) {
          clearTimeout(bargeInTimerRef.current);
          bargeInTimerRef.current = null;
        }
      }
    };

    recorder.start()
      .then(() => {
        recorderRef.current = recorder;
        setIsListening(true);
      })
      .catch(() => {
        setError("Microphone access denied or not available.");
        disconnectWebSocket();
      });
  };

  const stopListening = () => {
    disconnectWebSocket();
  };

  const toggleListening = () => {
    if (shouldResumeListeningRef.current) {
      stopListening();
    } else {
      setError(null);
      connectWebSocket();
    }
  };

  const speakText = (text: string, shouldResume: boolean = true) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      ttsUtteranceRef.current = utterance;
      utterance.onend = () => {
        if (ttsUtteranceRef.current === utterance) {
          ttsUtteranceRef.current = null;
        }
        if (shouldResume) {
          resumeRecordingIfNeeded();
        }
      };
      utterance.onerror = () => {
        if (ttsUtteranceRef.current === utterance) {
          ttsUtteranceRef.current = null;
        }
        if (shouldResume) {
          resumeRecordingIfNeeded();
        }
      };
      window.speechSynthesis.speak(utterance);
      return;
    }

    resumeRecordingIfNeeded();
  };

  return (
    <div className="app-container">
      <header>
        <div className="logo" style={{ display: 'flex', alignItems: 'center' }}>
          <Sparkles style={{ marginRight: '0.5rem' }} size={28} />
          RIVA Web
        </div>
        <div className="auth-section">
          {user ? (
            <div className="user-profile">
              <span className="user-name" style={{ display: 'inline-block' }}>{user.displayName || user.email}</span>
              {user.photoURL && <img src={user.photoURL} alt="Profile" className="avatar" />}
              <button className="btn" onClick={handleLogout}>
                <LogOut size={18} />
                Sign Out
              </button>
            </div>
          ) : (
            <button className="btn btn-primary" onClick={handleLogin}>
              <LogIn size={18} />
              Sign In with Google
            </button>
          )}
        </div>
      </header>

      {user && (
        <div className="nav-tabs" style={{ display: 'flex', justifyContent: 'center', gap: '1rem', margin: '2rem 0' }}>
          <button 
            className={`tab-btn ${activeTab === 'voice' ? 'active' : ''}`} 
            onClick={() => setActiveTab('voice')}
          >
            <MessageSquare size={18} /> Voice
          </button>
          <button 
            className={`tab-btn ${activeTab === 'calendar' ? 'active' : ''}`} 
            onClick={() => setActiveTab('calendar')}
          >
            <CalendarIcon size={18} /> Calendar
          </button>
          <button 
            className={`tab-btn ${activeTab === 'tasks' ? 'active' : ''}`} 
            onClick={() => setActiveTab('tasks')}
          >
            <CheckSquare size={18} /> Tasks
          </button>
          <button 
            className={`tab-btn ${activeTab === 'finance' ? 'active' : ''}`} 
            onClick={() => setActiveTab('finance')}
          >
            <Wallet size={18} /> Finance
          </button>
        </div>
      )}

      {user && activeTab === 'voice' && (
        <div className="live-mode-toggle" style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
          <label className="toggle-switch">
            <input 
              type="checkbox" 
              checked={isLiveMode} 
              onChange={(e) => {
                setIsLiveMode(e.target.checked);
                if (shouldResumeListeningRef.current) stopListening();
              }} 
            />
            <span className="slider round"></span>
            <span className="toggle-label" style={{ marginLeft: '0.5rem', color: isLiveMode ? '#3b82f6' : '#94a3b8', fontWeight: 600 }}>
              {isLiveMode ? 'Gemini Live Active' : 'Enable Live Mode (Beta)'}
            </span>
          </label>
        </div>
      )}

      <main style={{ padding: user ? '0 0 2rem 0' : '2rem 0' }}>
        {error && activeTab === 'voice' && (
          <div className="error-banner">
            <AlertCircle size={20} />
            {error}
          </div>
        )}

        {!user ? (
          <div className="glass-panel login-prompt">
            <h2>Welcome to RIVA</h2>
            <p>Your intelligent voice-first personal assistant. Sign in to access your synchronized calendar, finances, and multi-agent AI across all your devices.</p>
          </div>
        ) : (
          <>
            {activeTab === 'voice' && (
              <>
                <div className="glass-panel" style={{ flex: 1, minHeight: '400px', display: 'flex', flexDirection: 'column' }}>
                  <div className="chat-history" style={{ flex: 1 }}>
                    {messages.length === 0 ? (
                      <div style={{ textAlign: 'center', color: '#94a3b8', marginTop: '2.5rem' }}>
                        Tap the microphone and say something to RIVA...
                      </div>
                    ) : (
                      messages.map((msg) => (
                        <div key={msg.id} className={`message ${msg.sender}`}>
                          <span className="message-sender">
                            {msg.sender === 'user' ? 'You' : 'RIVA'}
                          </span>
                          <div className="message-bubble">
                            {msg.text}
                          </div>
                        </div>
                      ))
                    )}
                    <div ref={chatEndRef} />
                  </div>
                </div>

                <div className="controls-container">
                  <div className="status-text">
                    {isSpeaking
                      ? '🔊 Speaking… (talk to interrupt)'
                      : isProcessing
                      ? 'Thinking...'
                      : isListening
                      ? 'Listening...'
                      : shouldResumeListeningRef.current
                      ? 'Tap to stop'
                      : 'Ready'}
                  </div>
                  
                  <div className="mic-wrapper">
                    {isListening && <div className="mic-ripple" />}
                    <button 
                      className={`mic-btn ${isListening ? 'listening' : ''} ${isProcessing ? 'processing' : ''} ${isSpeaking ? 'speaking' : ''}`}
                      onClick={toggleListening}
                      aria-pressed={shouldResumeListeningRef.current}
                      title={shouldResumeListeningRef.current ? 'Stop voice session' : 'Start voice session'}
                    >
                      {isProcessing ? (
                        <Loader2 size={36} style={{ animation: 'spin-pulse 2s linear infinite' }} />
                      ) : (
                        <Mic size={36} />
                      )}
                    </button>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'calendar' && <CalendarTab user={user} apiUrl={API_URL} />}

            {activeTab === 'tasks' && <TodoTab user={user} apiUrl={API_URL} />}
            
            {activeTab === 'finance' && <FinanceTab user={user} apiUrl={API_URL} />}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
