"""Tasa de acierto vs. SNR para varios tipos de ruido (Fase 5, RNF4).

Diseño pareado: se eligen los mismos fragmentos limpios (posiciones aleatorias)
y a cada uno se le suma cada tipo de ruido a cada SNR. Los negativos usan una BD
temporal sin 1 de cada 4 canciones, igual que en la Fase 4.

Uso (desde backend/):
    python ../evaluation/eval_noise.py [--per-song 5] [--snrs 20 10 5 0 -5] [--durations 5 10]

Salidas: evaluation/results/fase5_ruido.csv y docs/figures/ruido_acierto_vs_snr.png
"""

from __future__ import annotations

import argparse
import csv
import tempfile
import time
from pathlib import Path

import numpy as np

from common import RESULTS_DIR, build_db, load_library, random_clips, split_holdout
from db.database import FingerprintDB
from fingerprint import config
from fingerprint.matcher import recognize
from noise import NOISE_TYPES, make_noise, mix_at_snr


def run(db, songs, audio, args, rng, positive: bool) -> list[dict]:
    rows = []
    for song in songs:
        x = audio[song["file_name"]]
        for duration in args.durations:
            for start, clean in random_clips(x, duration, args.per_song, rng):
                for kind in args.noises:
                    noise = make_noise(kind, len(clean), rng)
                    for snr in args.snrs:
                        r = recognize(mix_at_snr(clean, noise, snr), db)
                        best = r.best
                        rows.append({
                            "tipo": "positivo" if positive else "negativo",
                            "cancion": f"{song['artist']} - {song['title']}",
                            "ruido": kind,
                            "snr_db": snr,
                            "duracion_s": duration,
                            "inicio_s": round(start / config.SAMPLE_RATE, 3),
                            "top1_correcto": positive and best is not None and best.song_id == song["id"],
                            "reconocida": r.recognized,
                            "correcta": positive and r.recognized and r.song["id"] == song["id"],
                            "score": best.score if best else 0,
                            "score_2": r.candidates[1].score if len(r.candidates) > 1 else 0,
                            "latencia_ms": round(1000 * r.timings["total_s"], 1),
                        })
    return rows


def decide(row, min_score, min_ratio):
    return row["score"] >= min_score and row["score"] >= min_ratio * row["score_2"]


def summarize(rows, args):
    pos = [r for r in rows if r["tipo"] == "positivo"]
    neg = [r for r in rows if r["tipo"] == "negativo"]
    for duration in args.durations:
        print(f"\nAcierto (%) — fragmentos de {duration:g} s   [regla: score ≥ {config.MATCH_MIN_SCORE}, ≥ {config.MATCH_MIN_RATIO}× segundo]")
        print(f"{'ruido':<8}" + "".join(f"{s:>8g} dB" for s in args.snrs))
        for kind in args.noises:
            cells = []
            for snr in args.snrs:
                sel = [r for r in pos if r["ruido"] == kind and r["snr_db"] == snr and r["duracion_s"] == duration]
                cells.append(f"{100 * np.mean([r['correcta'] for r in sel]):10.1f}")
            print(f"{kind:<8}" + " ".join(cells))

    fp = [r for r in neg if r["reconocida"]]
    print(f"\nNegativos: {len(neg)} consultas, falsos positivos {len(fp)} ({100 * len(fp) / max(1, len(neg)):.2f} %)")
    neg_scores = np.array([r["score"] for r in neg])
    print(f"Score de negativos: máx {neg_scores.max()}, p99 {np.percentile(neg_scores, 99):.0f}, mediana {np.median(neg_scores):.0f}")
    lat = np.array([r["latencia_ms"] for r in rows])
    print(f"Latencia: mediana {np.median(lat):.0f} ms, máx {lat.max():.0f} ms")

    # Barrido del umbral de score (decisión recalculada sin repetir consultas)
    print("\nBarrido de MATCH_MIN_SCORE (ratio fijo):")
    print(f"{'umbral':>7} {'acierto SNR≥5':>14} {'acierto total':>14} {'falsos pos.':>12}")
    for thr in (5, 6, 8, 10, 12, 15, 20):
        hard = [r for r in pos if r["snr_db"] >= 5]
        acc5 = np.mean([decide(r, thr, config.MATCH_MIN_RATIO) and r["top1_correcto"] for r in hard])
        acc = np.mean([decide(r, thr, config.MATCH_MIN_RATIO) and r["top1_correcto"] for r in pos])
        n_fp = sum(decide(r, thr, config.MATCH_MIN_RATIO) for r in neg)
        print(f"{thr:>7} {100 * acc5:13.1f}% {100 * acc:13.1f}% {n_fp:>12}")


def plot(rows, args, out: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pos = [r for r in rows if r["tipo"] == "positivo"]
    fig, axes = plt.subplots(1, len(args.durations), figsize=(6 * len(args.durations), 4.5), sharey=True)
    axes = np.atleast_1d(axes)
    snrs = sorted(args.snrs)
    for ax, duration in zip(axes, args.durations):
        for kind in args.noises:
            acc = [
                100 * np.mean([r["correcta"] for r in pos if r["ruido"] == kind and r["snr_db"] == s and r["duracion_s"] == duration])
                for s in snrs
            ]
            ax.plot(snrs, acc, marker="o", label=kind)
        ax.axhline(80, color="gray", ls="--", lw=1)
        ax.axvline(5, color="gray", ls=":", lw=1)
        ax.text(5.3, 3, "ruido moderado\n(SNR ≥ 5 dB)", fontsize=8, color="gray")
        ax.set_title(f"Fragmentos de {duration:g} s")
        ax.set_xlabel("SNR (dB)")
        ax.set_ylim(0, 102)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Acierto (%)")
    axes[-1].legend(title="Ruido", loc="lower right")
    fig.suptitle("Tasa de acierto vs. SNR (línea discontinua: requisito RNF4 = 80 %)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Figura: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--noises", nargs="+", default=list(NOISE_TYPES), choices=NOISE_TYPES)
    parser.add_argument("--snrs", type=float, nargs="+", default=[20, 10, 5, 0, -5])
    parser.add_argument("--durations", type=float, nargs="+", default=[5.0, 10.0])
    parser.add_argument("--per-song", type=int, default=5)
    parser.add_argument("--neg-per-song", type=int, default=5)
    parser.add_argument("--holdout-every", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    t0 = time.perf_counter()

    with FingerprintDB(config.DB_PATH) as db:
        songs, audio = load_library(db)
        print(f"Positivos: {len(songs)} canciones × {len(args.durations)} duraciones × {args.per_song} fragmentos × "
              f"{len(args.noises)} ruidos × {len(args.snrs)} SNR")
        rows = run(db, songs, audio, args, rng, positive=True)

    kept, held_out = split_holdout(songs, args.holdout_every)
    args_neg = argparse.Namespace(**{**vars(args), "per_song": args.neg_per_song})
    with tempfile.TemporaryDirectory() as tmp:
        neg_db = build_db(Path(tmp) / "neg.db", kept, audio)
        try:
            print(f"Negativos: {len(held_out)} canciones fuera de una BD de {len(kept)}")
            rows += run(neg_db, held_out, audio, args_neg, rng, positive=False)
        finally:
            neg_db.close()

    summarize(rows, args)
    print(f"\nTiempo total: {(time.perf_counter() - t0) / 60:.1f} min")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_csv = RESULTS_DIR / "fase5_ruido.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Detalle: {out_csv}")
    plot(rows, args, config.FIGURES_DIR / "ruido_acierto_vs_snr.png")


if __name__ == "__main__":
    main()
