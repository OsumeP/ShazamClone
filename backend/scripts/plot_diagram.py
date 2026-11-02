"""Diagrama de bloques del sistema (Procesos 5.1 y 5.2) para el informe.

Uso (desde backend/):
    python -m scripts.plot_diagram   → docs/figures/diagrama_sistema.png
"""

from __future__ import annotations

from scripts import plot_style

plot_style.setup()
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from fingerprint import config  # noqa: E402

COMMON = ["Normalización\n44.1 kHz, mono", "STFT\nHann N=4096, R=2048", "Mapa de constelación\nmáx. locales 15×15", "Hashing\n(f1, f2, Δt) → 32 bits"]


def box(ax, x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=color, edgecolor="#333", linewidth=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)


def arrow(ax, x0, y0, x1, y1):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12, color="#333", lw=1.2))


def main() -> None:
    fig, ax = plt.subplots(figsize=(13, 5.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    w, h, gap = 1.75, 0.95, 0.35

    rows = [
        (3.9, "Proceso 5.1 — Ingesta (una vez por canción)", "Archivo propio\n.mp3 / .wav", "#dbe9f6",
         "BD SQLite\n(hash, canción, t)", "#f9e3c8"),
        (1.1, "Proceso 5.2 — Consulta en tiempo real", "Micrófono\n5–10 s (PCM)", "#e3f2df",
         "Matching\nhistograma de Δt", "#f9e3c8"),
    ]
    for y, title, src, src_color, sink, sink_color in rows:
        ax.text(0.15, y + h + 0.25, title, fontsize=10, fontweight="bold")
        x = 0.15
        box(ax, x, y, w, h, src, src_color)
        for label in COMMON:
            arrow(ax, x + w, y + h / 2, x + w + gap, y + h / 2)
            x += w + gap
            box(ax, x, y, w, h, label, "#ece6f5")
        arrow(ax, x + w, y + h / 2, x + w + gap, y + h / 2)
        x += w + gap
        box(ax, x, y, w, h, sink, sink_color)
    # la consulta busca en la BD; el matching entrega el resultado
    x_sink = 0.15 + 5 * (w + gap)
    arrow(ax, x_sink + w / 2, 3.9, x_sink + w / 2, 1.1 + h)
    ax.text(x_sink + w / 2 + 0.08, 2.95, "búsqueda\npor hash", fontsize=8, va="center")
    ax.text(x_sink + w / 2, 0.55, "Canción + posición\n(si score ≥ 10 y ≥ 2× segundo)", ha="center", fontsize=8.5)
    arrow(ax, x_sink + w / 2, 1.1, x_sink + w / 2, 0.85)

    out = config.FIGURES_DIR / "diagrama_sistema.png"
    fig.tight_layout()
    fig.savefig(out, dpi=170)
    print(f"Figura guardada en {out}")


if __name__ == "__main__":
    main()
