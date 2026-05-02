# RIVA - Quick Agent Briefing

## What is RIVA?
**RIVA** = Voice-first AI personal assistant that replaces a human PA. Handles productivity, finance, planning through natural voice conversations.

## Tech Stack Summary
```
Flutter App (Mobile) ←WebSocket→ FastAPI Backend (Python)
     ↓                                  ↓
  Firebase Auth                    MongoDB + OpenAI GPT-4
  flutter_sound (mic)              Vosk STT (offline)
  flutter_tts (speaker)            Multi-Agent System
```

## Architecture
```
Frontend (riva_frontend/)
├── Providers: Auth, Voice, Conversation
├── Services: API, Voice (WebSocket), Storage
├── Screens: Login, Home (voice UI), Conversation, Settings
└── Widgets: VoiceVisualizer (animated mic button)

Backend (riva-ml/)
├── main.py: FastAPI app, /stream WebSocket endpoint
├── Agents: Finance, Task, Conversational managers
├── Services: Vosk STT, OpenAI GPT, Google Calendar/Gmail
└── Database: MongoDB (user context)
```

## Current Status: MVP COMPLETE ✅

### Working Features
1. ✅ Google Sign-In (Firebase)
2. ✅ Real-time voice streaming (WebSocket)
3. ✅ Vosk offline speech recognition
4. ✅ OpenAI GPT-4 responses
5. ✅ Full-duplex audio (interrupt capability)
6. ✅ Conversation history (local storage)
7. ✅ Breathing animation on voice button
8. ✅ Toggle voice connection (start/stop)

### Voice Flow
```
Click mic → WebSocket connect → Stream audio → Vosk transcription
→ AI processing → Response → TTS playback → Click mic → Disconnect
```

## Recent Fixes Applied
- ✅ Google login (JSON response, no redirect)
- ✅ Vosk integration (free offline STT)
- ✅ Voice button toggle (proper disconnect)
- ✅ Breathing animation
- ✅ WebSocket cleanup
- ✅ Windows compatibility (unicode, file locking)

## Current Task Being Debugged
**Voice button toggle & logs visibility**
- Fixed: Disconnect logic in `voice_service.dart`
- Fixed: Toggle logic in `voice_provider.dart`
- Issue: User couldn't find logs → Created terminal guide
- Solution: Terminal 5 (Flutter app), Terminal 7 (Backend), Terminal 9 (Flutter logs)

## Key Files to Know

### Frontend
- `lib/services/voice_service.dart` - WebSocket, audio streaming
- `lib/providers/voice_provider.dart` - Voice state management
- `lib/widgets/voice_visualizer.dart` - Animated mic button
- `lib/services/api_service.dart` - HTTP API calls

### Backend
- `app/main.py` - FastAPI app, `/stream` endpoint
- `app/services/vosk_service.py` - Speech recognition
- `app/services/assistant.py` - AI request classifier
- `app/services/finance_manager.py` - Finance logic

## What's Next (Roadmap)
1. **Phase 2**: Google Calendar UI, Finance UI, Task management UI
2. **Phase 3**: Proactive suggestions, long-term memory
3. **Phase 4**: Performance optimization, testing, multi-platform

## Environment Setup

### Backend
```bash
cd riva-ml
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python setup_vosk.py  # Download Vosk model
cd app
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd riva_frontend
flutter pub get
flutter run
```

### Config
- Backend `.env`: `OPENAI_API_KEY`, `MONGODB_URI`
- Frontend: Update `lib/config/app_config.dart` with backend IP
- Firebase: Add `google-services.json` (Android), `GoogleService-Info.plist` (iOS)

## Common Issues

### Connection Problems
- **Emulator**: Use `http://10.0.2.2:8000`
- **Physical device**: Use PC IP (e.g., `192.168.1.x:8000`)
- **Port 8000 in use**: `netstat -ano | findstr :8000` → kill process

### Logs
- **Flutter app logs**: Terminal 5 (or `flutter logs`)
- **Backend logs**: Terminal 7 (uvicorn output)
- **Look for**: `[VOICE DEBUG]`, `[TRANSCRIPT]`, `[ASSISTANT]`

### Hot Reload Issues
- **Animation bugs**: Use hot restart (Shift+R) instead
- **WebSocket stuck**: Restart both frontend and backend

## Key Dependencies

### Frontend (pubspec.yaml)
```yaml
flutter_sound: ^9.28.0        # Audio recording
flutter_tts: ^4.2.2           # Text-to-speech
web_socket_channel: ^3.0.3    # WebSocket
firebase_auth: ^5.5.4         # Authentication
provider: ^6.1.1              # State management
```

### Backend (requirements.txt)
```
fastapi
uvicorn
firebase-admin==6.6.0
openai
vosk==0.3.45
speech_recognition
pymongo
```

## Testing the Voice Feature

1. Start backend: `uvicorn main:app --host 0.0.0.0 --port 8000` (in `riva-ml/app/`)
2. Start frontend: `flutter run` (in `riva_frontend/`)
3. Click mic button → Should see breathing animation
4. Speak something → Watch Terminal 7 for `[TRANSCRIPT]`
5. Get response → Should hear TTS playback
6. Click mic again → Animation should stop, disconnect

## Important Notes
- **User prefers Git Bash** over PowerShell
- **Windows-specific**: Unicode issues fixed (no emojis in logs)
- **Vosk model**: `vosk-model-small-en-us-0.15` (123MB)
- **OpenAI**: Uses GPT-4 for responses
- **Privacy**: Vosk runs offline, no data sent to cloud for STT

## Project Stats
- **Total LOC**: ~5,000+
- **Platforms**: Android, iOS (+ Windows/macOS/Linux ready)
- **Development**: MVP done in ~3 weeks
- **Status**: Production-ready for beta testing

## Unique Selling Points
1. **Offline STT** (Vosk) - privacy + cost savings
2. **Multi-agent** - specialized for finance/tasks/general
3. **Full-duplex** - can interrupt RIVA mid-speech
4. **Proactive** - will eventually suggest actions (Phase 3)
5. **Context-aware** - remembers user history (MongoDB)

---

**Bottom Line**: RIVA is a working voice-first personal assistant with a clean architecture, ready for feature expansion. The core voice system is solid and the multi-agent backend is prepared for domain-specific intelligence.

**Current Focus**: Debugging voice button toggle behavior and improving log visibility for easier development.

**Ready for**: Adding Calendar UI, Finance UI, Task UI, and proactive features.
