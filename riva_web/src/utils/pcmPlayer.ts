/**
 * PCMPlayer — gapless PCM audio playback via Web Audio API.
 *
 * Improvements:
 *  - interrupt(): stops all scheduled audio immediately (barge-in support)
 *  - isPlaying: true while buffers are scheduled ahead of currentTime
 *  - onPlaybackEnd callback: fires when the play queue drains
 */
export class PCMPlayer {
  private audioContext: AudioContext;
  private sampleRate: number;
  private startTime: number = 0;
  private activeSources: AudioBufferSourceNode[] = [];

  /** Called when the last scheduled chunk finishes playing. */
  onPlaybackEnd?: () => void;

  constructor(sampleRate: number = 24000) {
    this.sampleRate = sampleRate;
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: this.sampleRate,
    });
  }

  /** Returns true if there is still audio scheduled to play. */
  get isPlaying(): boolean {
    return this.startTime > this.audioContext.currentTime;
  }

  /** Append a PCM chunk to the play queue. */
  feed(data: Int16Array) {
    const buffer = this.audioContext.createBuffer(1, data.length, this.sampleRate);
    const channelData = buffer.getChannelData(0);

    for (let i = 0; i < data.length; i++) {
      channelData[i] = data[i] / 32768.0;
    }

    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);

    const currentTime = this.audioContext.currentTime;
    if (this.startTime < currentTime) {
      this.startTime = currentTime;
    }

    source.start(this.startTime);
    this.startTime += buffer.duration;
    this.activeSources.push(source);

    // Clean up reference and fire callback when this chunk ends
    source.onended = () => {
      this.activeSources = this.activeSources.filter(s => s !== source);
      if (this.activeSources.length === 0) {
        this.onPlaybackEnd?.();
      }
    };
  }

  /**
   * Interrupt playback immediately — used for barge-in.
   * Stops all scheduled sources and resets the play clock.
   */
  interrupt() {
    for (const src of this.activeSources) {
      try { src.stop(); } catch { /* already ended */ }
    }
    this.activeSources = [];
    this.startTime = 0;
  }

  close() {
    this.interrupt();
    this.audioContext.close();
  }
}
