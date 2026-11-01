import { useEffect, useRef } from "react";

// Espectrograma en vivo (0–5 kHz) a partir del AnalyserNode de la grabación:
// cada cuadro agrega una columna con |X(m, k)| en dB y desplaza la imagen,
// es decir, una STFT dibujada en tiempo real.

const FMAX_HZ = 5000;

function color(v: number): string {
  // v en [0, 1] → escala tipo "magma" (negro → morado → naranja → amarillo)
  const h = 280 - 240 * v;
  const l = 4 + 60 * v;
  return `hsl(${h}, 90%, ${l}%)`;
}

export function LiveSpectrogram({ analyser }: { analyser: AnalyserNode | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    if (!analyser) return;

    const bins = new Uint8Array(analyser.frequencyBinCount);
    const nyquist = analyser.context.sampleRate / 2;
    const maxBin = Math.min(bins.length, Math.round((FMAX_HZ / nyquist) * bins.length));
    let frame = 0;

    ctx.fillStyle = color(0);
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const draw = () => {
      analyser.getByteFrequencyData(bins);
      const { width, height } = canvas;
      ctx.drawImage(canvas, -2, 0); // desplaza 2 px a la izquierda
      for (let y = 0; y < height; y++) {
        const k = Math.floor(((height - 1 - y) / height) * maxBin);
        ctx.fillStyle = color(bins[k] / 255);
        ctx.fillRect(width - 2, y, 2, 1);
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [analyser]);

  return (
    <figure className="spectrogram">
      <canvas ref={canvasRef} width={640} height={160} aria-label="Espectrograma en vivo del micrófono" />
      <figcaption>Espectrograma en vivo (STFT del micrófono, 0–5 kHz)</figcaption>
    </figure>
  );
}
