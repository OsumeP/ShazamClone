// AudioWorklet que entrega el PCM crudo del micrófono (canal 0) en bloques de
// 2048 muestras al hilo principal. Se ejecuta en el hilo de audio del navegador.
class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(2048);
    this.n = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        this.block[this.n++] = channel[i];
        if (this.n === this.block.length) {
          this.port.postMessage(this.block, [this.block.buffer]);
          this.block = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("recorder", RecorderProcessor);
