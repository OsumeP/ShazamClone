"""Evaluación del matching con fragmentos limpios (Fase 4).

Positivos: fragmentos de D segundos de cada canción de la BD, en posiciones
aleatorias con resolución de una muestra, así que casi nunca coinciden con el
inicio de una ventana de la STFT.
Negativos: se arma una BD temporal sin un subconjunto de canciones y se
consultan fragmentos de esas canciones; lo correcto es "no reconocida".

Uso (desde backend/):
    python ../evaluation/eval_matching.py [--durations 5 10] [--per-song 5] [--tolerance 1]

Escribe el detalle por consulta en evaluation/results/fase4_matching.csv.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from db.database import FingerprintDB  # noqa: E402
from fingerprint import config  # noqa: E402
from fingerprint.audio_io import load_audio  # noqa: E402
from fingerprint.hashing import fingerprint_signal  # noqa: E402
from fingerprint.matcher import is_confident, recognize  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FS = config.SAMPLE_RATE


def random_clips(x: np.ndarray, duration: float, n: int, rng) -> list[tuple[int, np.ndarray]]:
    length = int(duration * FS)
    starts = rng.integers(0, len(x) - length, size=n)
    return [(int(s), x[s : s + length]) for s in starts]


def run_queries(db, songs, audio, durations, per_song, tolerance, rng, positive):
    rows = []
    for song in songs:
        x = audio[song["file_name"]]
        for duration in durations:
            for start, clip in random_clips(x, duration, per_song, rng):
                r = recognize(clip, db, tolerance=tolerance)
                best = r.best
                second = r.candidates[1].score if len(r.candidates) > 1 else 0
                rows.append({
                    "tipo": "positivo" if positive else "negativo",
                    "cancion": f"{song['artist']} - {song['title']}",
                    "duracion_s": duration,
                    "inicio_real_s": round(start / FS, 3),
                    "top1_correcto": positive and best is not None and best.song_id == song["id"],
                    "reconocida": r.recognized,
                    "correcta": positive and r.recognized and r.song["id"] == song["id"],
                    "score": best.score if best else 0,
                    "score_2": second,
                    "error_inicio_s": round(abs(best.offset_s - start / FS), 3) if positive and best else None,
                    "hashes_consulta": r.n_query_hashes,
                    "latencia_ms": round(1000 * r.timings["total_s"], 1),
                })
    return rows


def summarize(rows, durations):
    pos = [r for r in rows if r["tipo"] == "positivo"]
    neg = [r for r in rows if r["tipo"] == "negativo"]
    print(f"\n{'dur':>4} {'n':>4} {'top-1':>7} {'acierto':>8} {'score mín':>10} {'score med':>10} {'err. inicio máx':>16} {'lat. med':>9} {'lat. máx':>9}")
    for d in durations:
        p = [r for r in pos if r["duracion_s"] == d]
        lat = np.array([r["latencia_ms"] for r in p])
        sc = np.array([r["score"] for r in p])
        err = max(r["error_inicio_s"] for r in p if r["top1_correcto"])
        print(
            f"{d:>4} {len(p):>4} {100 * np.mean([r['top1_correcto'] for r in p]):6.1f}% "
            f"{100 * np.mean([r['correcta'] for r in p]):7.1f}% {sc.min():>10} {np.median(sc):>10.0f}"
            f" {err:>15.3f}s {np.median(lat):>7.0f}ms {lat.max():>7.0f}ms"
        )
    if neg:
        fa = np.mean([r["reconocida"] for r in neg])
        print(
            f"\nNegativos (canciones fuera de la BD): {len(neg)} consultas, falsos positivos {100 * fa:.1f} %, "
            f"score máx {max(r['score'] for r in neg)}, ratio máx {max(r['score'] / max(1, r['score_2']) for r in neg):.2f}"
        )
        pos_ratio = [r["score"] / max(1, r["score_2"]) for r in pos if r["top1_correcto"]]
        print(
            f"Positivos correctos: score mín {min(r['score'] for r in pos if r['top1_correcto'])}, "
            f"ratio mín {min(pos_ratio):.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--durations", type=float, nargs="+", default=[5.0, 10.0])
    parser.add_argument("--per-song", type=int, default=5)
    parser.add_argument("--tolerance", type=int, default=config.MATCH_DELTA_TOLERANCE)
    parser.add_argument("--holdout-every", type=int, default=4, help="1 de cada N canciones queda fuera en la BD de negativos")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)

    with FingerprintDB(config.DB_PATH) as db:
        songs = [dict(r) for r in db.list_songs()]
        audio = {s["file_name"]: load_audio(config.NORMALIZED_DIR / (Path(s["file_name"]).stem + ".wav")) for s in songs}
        print(f"BD principal: {len(songs)} canciones. Consultas positivas…")
        rows = run_queries(db, songs, audio, args.durations, args.per_song, args.tolerance, rng, positive=True)

    held_out = songs[:: args.holdout_every]
    kept = [s for s in songs if s not in held_out]
    with tempfile.TemporaryDirectory() as tmp, FingerprintDB(Path(tmp) / "neg.db") as neg_db:
        print(f"BD de negativos: {len(kept)} canciones; {len(held_out)} fuera. Consultas negativas…")
        for s in kept:
            _, h, o = fingerprint_signal(audio[s["file_name"]])
            new_id = neg_db.add_song(
                title=s["title"], artist=s["artist"], album=s["album"], duration_s=s["duration_s"],
                file_name=s["file_name"], file_sha1=s["file_sha1"], wav_bytes=s["wav_bytes"], hashes=h, offsets=o,
            )
            assert new_id
        rows += run_queries(neg_db, held_out, audio, args.durations, args.per_song, args.tolerance, rng, positive=False)

    summarize(rows, args.durations)
    print(f"\nRegla de decisión: score ≥ {config.MATCH_MIN_SCORE} y score ≥ {config.MATCH_MIN_RATIO} × segundo")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "fase4_matching.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Detalle: {out}")


if __name__ == "__main__":
    main()
