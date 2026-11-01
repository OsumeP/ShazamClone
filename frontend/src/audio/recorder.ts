// Captura de micrófono con Web Audio API (RF4, acuerdo A2).
//
// - Se piden las restricciones echoCancellation / noiseSuppression /
//   autoGainControl en false: el procesamiento del navegador altera los picos
//   espectrales (se reporta qué aplicó realmente el navegador).
// - Se usa un AudioWorklet para obtener PCM crudo, no MediaRecorder (Opus/AAC
//   con pérdidas).
// - Se graba a la frecuencia nativa del AudioContext (normalmente 48 kHz) y el
//   backend la remuestrea a 44.1 kHz con el mismo filtro polifásico que usa
//   para todo el audio, así la consulta y la BD pasan por la misma normalización.

import { rmsDbfs } from "./wav";

// Servido desde public/ como archivo propio: algunos navegadores no aceptan
// módulos de AudioWorklet incrustados como URL data:.
const WORKLET_URL = `${import.meta.env.BASE_URL}recorder-worklet.js`;

export interface Recording {
  samples: Float32Array;
  sampleRate: number;
  endedAt: number; // performance.now() al terminar la grabación (inicio de la latencia, A3)
  levelDbfs: number;
  peak: number;
  trackSettings: MediaTrackSettings;
}

export interface RecordOptions {
  seconds: number;
  onLevel?: (dbfs: number) => void;
  onProgress?: (fraction: number) => void;
  onAnalyser?: (analyser: AnalyserNode | null) => void;
  signal?: AbortSignal;
}

export const AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
  channelCount: 1,
};

export async function recordClip(opts: RecordOptions): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Este navegador no permite acceder al micrófono (se requiere HTTPS o localhost).");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS });
  const ctx = new AudioContext();
  const cleanup = () => {
    stream.getTracks().forEach((t) => t.stop());
    opts.onAnalyser?.(null);
    void ctx.close();
  };

  try {
    await ctx.audioWorklet.addModule(WORKLET_URL);
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0;
    source.connect(analyser);
    opts.onAnalyser?.(analyser);

    const recorder = new AudioWorkletNode(ctx, "recorder");
    const mute = ctx.createGain();
    mute.gain.value = 0; // el nodo debe estar conectado al destino para procesarse, pero sin sonar
    source.connect(recorder).connect(mute).connect(ctx.destination);

    const target = Math.round(opts.seconds * ctx.sampleRate);
    const samples = new Float32Array(target);
    let filled = 0;

    const endedAt = await new Promise<number>((resolve, reject) => {
      opts.signal?.addEventListener("abort", () => reject(new DOMException("Grabación cancelada", "AbortError")));
      recorder.port.onmessage = (e: MessageEvent<Float32Array>) => {
        if (filled >= target) return;
        const block = e.data.subarray(0, target - filled);
        samples.set(block, filled);
        filled += block.length;
        opts.onLevel?.(rmsDbfs(block));
        opts.onProgress?.(filled / target);
        if (filled >= target) resolve(performance.now());
      };
    });

    let peak = 0;
    for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
    return {
      samples,
      sampleRate: ctx.sampleRate,
      endedAt,
      levelDbfs: rmsDbfs(samples),
      peak,
      trackSettings: stream.getAudioTracks()[0]?.getSettings() ?? {},
    };
  } finally {
    cleanup();
  }
}
