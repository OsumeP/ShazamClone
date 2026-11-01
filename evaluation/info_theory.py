"""Análisis de Teoría de la Información (Fase 5, marco teórico §3.5).

A. Entropía espectral de Shannon por ventana, normalizada a [0, 1]:
       p_k = S(m, k) / Σ_k S(m, k)     H(m) = −Σ_k p_k log2 p_k / log2 K
   (K = bins de la banda 60 Hz – 5 kHz). H ≈ 1: energía repartida
   uniformemente (ruido). H bajo: energía concentrada en pocos picos (música).
B. Efecto del canal ruidoso: entropía de la mezcla, supervivencia de picos y
   de hashes en función de la SNR.
C. Capacidad de Shannon-Hartley C = B·log2(1 + SNR) para la banda completa y la
   banda de análisis, frente a la información necesaria para identificar.

Uso (desde backend/):
    python ../evaluation/info_theory.py

Salidas: docs/figures/entropia_espectral.png, docs/figures/canal_ruidoso_vs_snr.png,
         evaluation/results/fase5_teoria.md
"""

from __future__ import annotations

import numpy as np

from common import RESULTS_DIR, FS, load_library
from db.database import FingerprintDB
from fingerprint import config
from fingerprint.hashing import generate_hashes
from fingerprint.peaks import find_peaks
from fingerprint.spectrogram import frequency_axis, power_spectrogram, spectrogram_db, stft
from noise import NOISE_TYPES, make_noise, mix_at_snr

SNRS = [20, 10, 5, 0, -5]
F = frequency_axis()
BAND = (F >= config.PEAK_FMIN_HZ) & (F <= config.PEAK_FMAX_HZ)
B_FULL = FS / 2
B_BAND = config.PEAK_FMAX_HZ - config.PEAK_FMIN_HZ


def spectral_entropy(x: np.ndarray) -> np.ndarray:
    """Entropía espectral normalizada de cada ventana (banda de análisis)."""
    S = power_spectrogram(stft(x))[BAND].astype(np.float64) + 1e-20
    p = S / S.sum(axis=0, keepdims=True)
    return -(p * np.log2(p)).sum(axis=0) / np.log2(S.shape[0])


def band_fraction(x: np.ndarray) -> float:
    """Fracción de la potencia total que cae en la banda de análisis (Parseval)."""
    P = np.abs(np.fft.rfft(x.astype(np.float64))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FS)
    return P[(f >= config.PEAK_FMIN_HZ) & (f <= config.PEAK_FMAX_HZ)].sum() / P.sum()


def fingerprint_sets(x):
    peaks = find_peaks(spectrogram_db(x))
    h, o = generate_hashes(peaks)
    return {tuple(p) for p in peaks.tolist()}, set(zip(h.tolist(), o.tolist()))


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(7)
    with FingerprintDB(config.DB_PATH) as db:
        songs, audio = load_library(db)
        stats = db.stats()

    # --- A. Entropía espectral: música vs. ruido ----------------------------
    excerpt = 30 * FS
    music = [audio[s["file_name"]][len(audio[s["file_name"]]) // 2 - excerpt // 2 :][:excerpt] for s in songs]
    H = {"música": np.concatenate([spectral_entropy(m) for m in music])}
    for kind in NOISE_TYPES:
        H[kind] = spectral_entropy(make_noise(kind, excerpt, rng))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.boxplot(list(H.values()), showfliers=False)
    ax.set_xticks(range(1, len(H) + 1), list(H.keys()))
    ax.set_ylabel("Entropía espectral normalizada H / log2 K")
    ax.set_title(f"Entropía espectral por ventana (banda {config.PEAK_FMIN_HZ:g} Hz – {config.PEAK_FMAX_HZ / 1000:g} kHz)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "entropia_espectral.png", dpi=150)

    # --- B. Canal ruidoso: entropía, picos y hashes vs. SNR -----------------
    clip_len = 10 * FS
    subset = songs[::2]
    clips = []
    for s in subset:
        x = audio[s["file_name"]]
        st = rng.integers(0, len(x) - clip_len)
        clean = x[st : st + clip_len]
        clips.append((clean, *fingerprint_sets(clean)))

    curves = {k: {"H": [], "picos": [], "hashes": [], "snr_banda": []} for k in NOISE_TYPES}
    for kind in NOISE_TYPES:
        for snr in SNRS:
            h_vals, p_surv, h_surv, snr_band = [], [], [], []
            for clean, peaks_c, hashes_c in clips:
                noise = make_noise(kind, clip_len, rng)
                y = mix_at_snr(clean, noise, snr)
                peaks_y, hashes_y = fingerprint_sets(y)
                h_vals.append(np.median(spectral_entropy(y)))
                p_surv.append(len(peaks_c & peaks_y) / len(peaks_c))
                h_surv.append(len(hashes_c & hashes_y) / len(hashes_c))
                snr_band.append(snr + 10 * np.log10(band_fraction(clean) / band_fraction(noise)))
            c = curves[kind]
            c["H"].append(np.mean(h_vals))
            c["picos"].append(100 * np.mean(p_surv))
            c["hashes"].append(100 * np.mean(h_surv))
            c["snr_banda"].append(np.mean(snr_band))

    H_clean = np.mean([np.median(spectral_entropy(c[0])) for c in clips])
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for kind in NOISE_TYPES:
        axes[0].plot(SNRS, curves[kind]["H"], marker="o", label=kind)
        axes[1].plot(SNRS, curves[kind]["picos"], marker="o", label=kind)
        axes[2].plot(SNRS, curves[kind]["hashes"], marker="o", label=kind)
    axes[0].axhline(H_clean, color="k", ls="--", lw=1, label="música limpia")
    axes[0].set_ylabel("Entropía espectral mediana (normalizada)")
    axes[1].set_ylabel("Picos que sobreviven (%)")
    axes[2].set_ylabel("Hashes que sobreviven (%)")
    for ax, title in zip(axes, ["Entropía de la mezcla", "Supervivencia de picos", "Supervivencia de hashes"]):
        ax.set_xlabel("SNR (dB)")
        ax.set_title(title)
        ax.invert_xaxis()
        ax.grid(alpha=0.3)
    axes[0].legend()
    fig.suptitle("Efecto del canal ruidoso sobre la huella (10 canciones, fragmentos de 10 s)")
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "canal_ruidoso_vs_snr.png", dpi=150)

    # --- C. Shannon-Hartley y presupuesto de información ---------------------
    total_frames = stats["duration_s"] * FS / config.HOP
    bits_needed = np.log2(total_frames)                  # (canción, posición) entre todas las ventanas de la BD
    hashes_per_s = stats["n_hashes"] / stats["duration_s"]

    lines = ["# Fase 5 — Teoría de la Información (resultados generados por `info_theory.py`)", ""]
    lines += ["## A. Entropía espectral normalizada por ventana", "",
              "| Señal | Mediana | P10 | P90 |", "|---|---|---|---|"]
    for name, h in H.items():
        lines.append(f"| {name} | {np.median(h):.3f} | {np.percentile(h, 10):.3f} | {np.percentile(h, 90):.3f} |")

    lines += ["", "## B. Canal ruidoso (promedio de 10 fragmentos de 10 s)", "",
              f"Entropía mediana de la música limpia: {H_clean:.3f}", "",
              "| Ruido | SNR global (dB) | SNR en banda 60 Hz–5 kHz (dB) | Entropía mezcla | Picos que sobreviven | Hashes que sobreviven |",
              "|---|---|---|---|---|---|"]
    for kind in NOISE_TYPES:
        c = curves[kind]
        for i, snr in enumerate(SNRS):
            lines.append(f"| {kind} | {snr:g} | {c['snr_banda'][i]:.1f} | {c['H'][i]:.3f} | {c['picos'][i]:.1f} % | {c['hashes'][i]:.1f} % |")

    lines += ["", "## C. Capacidad de Shannon-Hartley  C = B·log2(1 + SNR)", "",
              f"- Banda completa B = {B_FULL:,.0f} Hz; banda de análisis B = {B_BAND:,.0f} Hz.",
              f"- Información necesaria para identificar (canción, posición) entre las {total_frames:,.0f} ventanas de la BD: "
              f"log2({total_frames:,.0f}) ≈ **{bits_needed:.1f} bits**.",
              f"- Huella de la consulta: ~{hashes_per_s:.0f} hashes/s × 32 bits ≈ {hashes_per_s * 32 / 1000:.1f} kbit/s "
              f"(vs. PCM 16 bits a 44.1 kHz = 705.6 kbit/s).", "",
              "| SNR (dB) | C banda completa (kbit/s) | C banda análisis, ruido blanco (kbit/s) | C banda análisis, ruido rosa (kbit/s) | Bits en 5 s (rosa, banda) |",
              "|---|---|---|---|---|"]
    for i, snr in enumerate(SNRS):
        c_full = B_FULL * np.log2(1 + 10 ** (snr / 10))
        c_white = B_BAND * np.log2(1 + 10 ** (curves["white"]["snr_banda"][i] / 10))
        c_pink = B_BAND * np.log2(1 + 10 ** (curves["pink"]["snr_banda"][i] / 10))
        lines.append(f"| {snr:g} | {c_full / 1000:.1f} | {c_white / 1000:.1f} | {c_pink / 1000:.1f} | {5 * c_pink:,.0f} |")

    out = RESULTS_DIR / "fase5_teoria.md"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nFiguras en {config.FIGURES_DIR}; tablas en {out}")


if __name__ == "__main__":
    main()
