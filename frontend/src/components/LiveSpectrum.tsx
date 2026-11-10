import { useEffect, useRef } from "react";

// Espectro en vivo (0–5 kHz): una FFT del AnalyserNode dibujada como barras.
// Es un corte de un solo instante del espectrograma: energía por frecuencia.

const FMAX_HZ = 5000;
const BARS = 64;
const TICKS = ["0", "1 kHz", "2 kHz", "3 kHz", "4 kHz", "5 kHz"];

export function LiveSpectrum({ analyser }: { analyser: AnalyserNode | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !analyser) return;

    const bins = new Uint8Array(analyser.frequencyBinCount);
    const nyquist = analyser.context.sampleRate / 2;
    const maxBin = Math.min(bins.length, Math.round((FMAX_HZ / nyquist) * bins.length));
    const level = new Float32Array(BARS); // valor suavizado de cada barra (0–1)
    const { width, height } = canvas;
    const fill = ctx.createLinearGradient(0, height, 0, 0);
    fill.addColorStop(0, "#2bb5c0");
    fill.addColorStop(1, "#c08bff");
    let frame = 0;

    const draw = () => {
      analyser.getByteFrequencyData(bins);
      ctx.fillStyle = "#07060f";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = fill;
      const barW = width / BARS;
      for (let i = 0; i < BARS; i++) {
        const k0 = Math.floor((i / BARS) * maxBin);
        const k1 = Math.max(k0 + 1, Math.floor(((i + 1) / BARS) * maxBin));
        let sum = 0;
        for (let k = k0; k < k1; k++) sum += bins[k];
        const v = sum / (k1 - k0) / 255;
        level[i] = Math.max(v, level[i] * 0.85); // las barras caen despacio: se leen mejor
        const h = Math.round(level[i] * (height - 4));
        ctx.fillRect(i * barW + 1, height - h, barW - 2, h);
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [analyser]);

  return (
    <figure className="spectrogram">
      <canvas ref={canvasRef} width={640} height={160} aria-label="Espectro en vivo del micrófono" />
      <div className="axis" aria-hidden="true">
        {TICKS.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
      <figcaption>Espectro en vivo (FFT del micrófono): energía de cada frecuencia, 0–5 kHz</figcaption>
    </figure>
  );
}
