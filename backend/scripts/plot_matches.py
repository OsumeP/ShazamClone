"""Grafica la coherencia temporal del matching para un fragmento (Wang 2003, fig. 2–3).

Izquierda: diagrama de dispersión offset_fragmento vs. offset_canción de las
coincidencias de hash con la canción reconocida y con otra canción.
Derecha: histogramas de Δ = offset_canción − offset_fragmento.

Uso (desde backend/):
    python -m scripts.plot_matches RUTA [--start 60] [--duration 10] [--out fig.png]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts import plot_style

plot_style.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from db.database import FingerprintDB  # noqa: E402
from fingerprint import config  # noqa: E402
from fingerprint.audio_io import load_audio  # noqa: E402
from fingerprint.hashing import fingerprint_signal  # noqa: E402
from fingerprint.matcher import find_matches, score_candidates  # noqa: E402

FRAME_S = config.HOP / config.SAMPLE_RATE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--start", type=float, default=60.0)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    x = load_audio(args.path)
    i0 = int(args.start * config.SAMPLE_RATE)
    clip = x[i0 : i0 + int(args.duration * config.SAMPLE_RATE)]
    _, hashes, offsets = fingerprint_signal(clip)

    with FingerprintDB(args.db) as db:
        song_ids, song_off, query_off = find_matches(db, hashes, offsets)
        cands = score_candidates(song_ids, song_off, query_off)
        best, other = cands[0], cands[1]
        names = {c.song_id: f"{db.get_song(c.song_id)['artist']} — {db.get_song(c.song_id)['title']}" for c in (best, other)}

    fig, axes = plt.subplots(2, 3, figsize=(16, 8.5))
    for row, (cand, color) in enumerate([(best, "tab:green"), (other, "tab:red")]):
        sel = song_ids == cand.song_id
        q_t, s_t = query_off[sel] * FRAME_S, song_off[sel] * FRAME_S
        ax_full, ax_zoom, ax_h = axes[row]

        ax_full.scatter(q_t, s_t, s=6, color=color, alpha=0.6)
        ax_full.set_title(f"{names[cand.song_id][:45]}\n{sel.sum()} coincidencias de hash", fontsize=10)

        # Vista ampliada alrededor del mejor Δ con la misma escala en ambos ejes:
        # las coincidencias alineadas forman la recta t_canción = t_fragmento + Δ.
        ax_zoom.scatter(q_t, s_t, s=10, color=color, alpha=0.7)
        ax_zoom.plot([0, args.duration], [cand.offset_s, cand.offset_s + args.duration], "k--", lw=0.8)
        ax_zoom.set_xlim(0, args.duration)
        ax_zoom.set_ylim(cand.offset_s - 1, cand.offset_s + args.duration + 1)
        ax_zoom.set_aspect("equal")
        ax_zoom.set_title(f"Ampliación alrededor de Δ = {cand.offset_s:.1f} s", fontsize=10)
        for ax in (ax_full, ax_zoom):
            ax.set_xlabel("Tiempo en el fragmento (s)")
            ax.set_ylabel("Tiempo en la canción (s)")

        delta = song_off[sel] - query_off[sel]
        values, counts = np.unique(delta, return_counts=True)
        ax_h.vlines(values * FRAME_S, 0, counts, color=color, lw=1.5)
        ax_h.set_ylim(0, counts.max() * 1.1)
        ax_h.set_xlabel("Δ = t_canción − t_fragmento (s)")
        ax_h.set_ylabel("Coincidencias")
        ax_h.set_title(f"Histograma de Δ — pico = {cand.score} (inicio estimado {cand.offset_s:.1f} s)", fontsize=10)

    fig.suptitle(
        f"Fragmento de {args.duration:.0f} s de «{args.path.stem}» desde {args.start:.1f} s — "
        f"arriba: canción reconocida, abajo: segunda candidata",
        fontsize=11,
    )
    fig.tight_layout()
    out = args.out or config.FIGURES_DIR / f"matching_{args.path.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Figura guardada en {out}")


if __name__ == "__main__":
    main()
