export class PCMPlayer {
  private audioContext: AudioContext;
  private sampleRate: number;
  private startTime: number = 0;

  constructor(sampleRate: number = 24000) {
    this.sampleRate = sampleRate;
    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: this.sampleRate,
    });
  }

  feed(data: Int16Array) {
    const buffer = this.audioContext.createBuffer(1, data.length, this.sampleRate);
    const channelData = buffer.getChannelData(0);

    // Convert Int16 to Float32
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
  }

  close() {
    this.audioContext.close();
  }
}
