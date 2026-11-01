"""Grafica el mapa de constelación sobre el espectrograma y los pares de hashing.

Uso (desde backend/):
    python -m scripts.plot_constellation RUTA [--start 60] [--duration 10] [--out fig.png]

Sin --out, la figura se guarda en docs/figures/constelacion_<nombre>.png.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from fingerprint import config  # noqa: E402
from fingerprint.audio_io import load_audio  # noqa: E402
from fingerprint.hashing import generate_hashes, unpack_hash  # noqa: E402
from fingerprint.peaks import find_peaks  # noqa: E402
from fingerprint.spectrogram import frequency_axis, spectrogram_db, time_axis  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--start", type=float, default=0.0, help="inicio del fragmento (s)")
    parser.add_argument("--duration", type=float, default=10.0, help="duración del fragmento (s)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    x = load_audio(args.path)
    i0 = int(args.start * config.SAMPLE_RATE)
    x = x[i0 : i0 + int(args.duration * config.SAMPLE_RATE)]

    S_db = spectrogram_db(x)
    peaks = find_peaks(S_db)
    hashes, offsets = generate_hashes(peaks)

    f = frequency_axis()
    t = time_axis(S_db.shape[1]) + args.start
    keep = f <= config.PEAK_FMAX_HZ
    pt, pf = t[peaks[:, 0]], f[peaks[:, 1]]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    vmax = S_db.max()
    ax1.pcolormesh(t, f[keep], S_db[keep], shading="auto", cmap="magma", vmin=vmax - 80, vmax=vmax)
    ax1.scatter(pt, pf, s=12, facecolors="none", edgecolors="cyan", linewidths=0.8)
    ax1.set_ylabel("Frecuencia (Hz)")
    ax1.set_title(f"{args.path.stem} — espectrograma y mapa de constelación ({len(peaks)} picos)")

    # Pares ancla -> objetivo de unos pocos anclas, como en Wang (2003) fig. 1c
    f1, f2, dt = unpack_hash(hashes)
    anchors = np.unique(offsets)[:: max(1, len(np.unique(offsets)) // 6)][:6]
    for a in anchors:
        sel = offsets == a
        for b1, b2, d in zip(f1[sel], f2[sel], dt[sel]):
            ax2.plot([t[a], t[a + d]], [f[b1], f[b2]], color="tab:orange", lw=0.7, alpha=0.8)
        ax2.scatter(t[a].repeat(sel.sum()), f[f1[sel]], s=40, color="tab:red", zorder=3)
    ax2.scatter(pt, pf, s=8, color="black")
    ax2.set_ylim(0, config.PEAK_FMAX_HZ)
    ax2.set_xlabel("Tiempo (s)")
    ax2.set_ylabel("Frecuencia (Hz)")
    ax2.set_title(
        f"Pares de hashing (fan-out {config.FAN_OUT}, Δt ≤ {config.TARGET_DT_MAX} ventanas) — "
        f"{len(hashes)} hashes en {args.duration:.0f} s"
    )
    fig.tight_layout()

    out = args.out or config.FIGURES_DIR / f"constelacion_{args.path.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Figura guardada en {out}")


if __name__ == "__main__":
    main()
