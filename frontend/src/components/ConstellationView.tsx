import { useEffect, useRef } from "react";
import type { Analysis } from "../api";

// Constelación: el espectrograma que analizó el servidor (0–5 kHz) con los picos
// que se convierten en hashes. Son los mismos datos que usa el algoritmo.

const STOPS: [number, [number, number, number]][] = [
  [0, [7, 6, 15]],
  [0.25, [70, 20, 120]],
  [0.5, [170, 45, 110]],
  [0.75, [250, 130, 60]],
  [1, [252, 240, 170]],
];

// Mapa de color tipo "magma" precalculado para los 256 niveles.
const LUT: [number, number, number][] = Array.from({ length: 256 }, (_, i) => {
  const v = i / 255;
  let k = 1;
  while (k < STOPS.length - 1 && v > STOPS[k][0]) k++;
  const [v0, c0] = STOPS[k - 1];
  const [v1, c1] = STOPS[k];
  const u = (v - v0) / (v1 - v0);
  return [0, 1, 2].map((j) => Math.round(c0[j] + (c1[j] - c0[j]) * u)) as [number, number, number];
});

export function ConstellationView({ analysis }: { analysis: Analysis }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const { n_frames: W, n_rows: H } = analysis;
    const bytes = Uint8Array.from(atob(analysis.spectrogram), (c) => c.charCodeAt(0));
    const img = ctx.createImageData(W, H);
    for (let row = 0; row < H; row++) {
      for (let m = 0; m < W; m++) {
        const [r, g, b] = LUT[bytes[row * W + m]];
        const o = ((H - 1 - row) * W + m) * 4; // la fila 0 son los graves: va abajo
        img.data[o] = r;
        img.data[o + 1] = g;
        img.data[o + 2] = b;
        img.data[o + 3] = 255;
      }
    }
    const small = document.createElement("canvas");
    small.width = W;
    small.height = H;
    small.getContext("2d")?.putImageData(img, 0, 0);
    ctx.drawImage(small, 0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "#5fe3f0";
    ctx.lineWidth = 1.3;
    for (const [m, k] of analysis.peaks) {
      const x = ((m + 0.5) / W) * canvas.width;
      const y = canvas.height * (1 - Math.min(1, (k * analysis.bin_hz) / analysis.f_top_hz));
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, 2 * Math.PI);
      ctx.stroke();
    }
  }, [analysis]);

  const duration = analysis.n_frames * analysis.frame_s;
  return (
    <figure className="spectrogram">
      <canvas ref={canvasRef} width={640} height={160} aria-label="Mapa de constelación sobre el espectrograma" />
      <div className="axis" aria-hidden="true">
        <span>0 s</span>
        <span>{(duration / 2).toFixed(1)} s</span>
        <span>{duration.toFixed(1)} s</span>
      </div>
      <figcaption>Constelación: {analysis.peaks.length} picos sobre el espectrograma (0–5 kHz)</figcaption>
    </figure>
  );
}
