"""Grafica el espectrograma (dB) de un archivo de audio.

Uso (desde backend/):
    python -m scripts.plot_spectrogram RUTA [--start 30] [--duration 10] [--fmax 5000] [--out fig.png]

Sin --out, la figura se guarda en docs/figures/espectrograma_<nombre>.png.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts import plot_style

plot_style.setup()
import matplotlib.pyplot as plt  # noqa: E402

from fingerprint import config  # noqa: E402
from fingerprint.audio_io import load_audio  # noqa: E402
from fingerprint.spectrogram import frequency_axis, spectrogram_db, time_axis  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--start", type=float, default=0.0, help="inicio del fragmento (s)")
    parser.add_argument("--duration", type=float, default=None, help="duración del fragmento (s)")
    parser.add_argument("--fmax", type=float, default=config.SAMPLE_RATE / 2, help="frecuencia máxima a mostrar (Hz)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    x = load_audio(args.path)
    i0 = int(args.start * config.SAMPLE_RATE)
    i1 = None if args.duration is None else i0 + int(args.duration * config.SAMPLE_RATE)
    x = x[i0:i1]

    S_db = spectrogram_db(x)
    f = frequency_axis()
    t = time_axis(S_db.shape[1]) + args.start
    keep = f <= args.fmax

    fig, ax = plt.subplots(figsize=(12, 5))
    vmax = S_db.max()
    mesh = ax.pcolormesh(t, f[keep], S_db[keep], shading="auto", cmap="magma", vmin=vmax - 80, vmax=vmax)
    fig.colorbar(mesh, ax=ax, label="Potencia (dB)")
    ax.set_xlabel("Tiempo (s)")
    ax.set_ylabel("Frecuencia (Hz)")
    ax.set_title(
        f"{args.path.stem}\nSTFT: ventana {config.WINDOW}, N={config.N_FFT}, R={config.HOP}, fs={config.SAMPLE_RATE} Hz"
    )
    fig.tight_layout()

    out = args.out or config.FIGURES_DIR / f"espectrograma_{args.path.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Figura guardada en {out}")


if __name__ == "__main__":
    main()
