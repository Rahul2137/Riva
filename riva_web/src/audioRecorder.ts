/**
 * AudioRecorder — captures mic PCM at 16kHz and exposes RMS level.
 *
 * onAudioData: called every ~256ms with a chunk of Int16 PCM
 * onRMSLevel:  called every chunk with RMS [0..1] for VAD / barge-in detection
 */
export class AudioRecorder {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private isRecording = false;

  private onAudioData: (data: Int16Array) => void;
  onRMSLevel?: (rms: number) => void;

  constructor(onAudioData: (data: Int16Array) => void) {
    this.onAudioData = onAudioData;
  }

  async start() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 16000,
      });

      this.source = this.audioContext.createMediaStreamSource(this.stream);
      // ScriptProcessorNode is deprecated but is the most reliable cross-browser
      // option for raw PCM access at a fixed buffer size.
      this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.processor.onaudioprocess = (e) => {
        if (!this.isRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);

        // Convert Float32 → Int16
        const pcm16 = new Int16Array(inputData.length);
        let sumSq = 0;
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          sumSq += s * s;
        }

        // RMS in [0, 1] — used by the barge-in detector
        const rms = Math.sqrt(sumSq / inputData.length);
        this.onRMSLevel?.(rms);

        this.onAudioData(pcm16);
      };

      this.source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);
      this.isRecording = true;
    } catch (err) {
      console.error('Error accessing microphone:', err);
      throw err;
    }
  }

  stop() {
    this.isRecording = false;
    if (this.processor && this.source) {
      this.processor.disconnect();
      this.source.disconnect();
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
    }
    if (this.audioContext) {
      this.audioContext.close();
    }
    this.processor = null;
    this.source = null;
    this.stream = null;
    this.audioContext = null;
  }
}
