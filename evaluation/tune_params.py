"""Ajuste de parámetros de la huella bajo ruido (Fase 5, tarea 5.5).

Para cada configuración (vecindario, umbral, fan-out) se arma una BD temporal
con 3 de cada 4 canciones y se mide, en condiciones de ruido difíciles:
acierto de las canciones de la BD, falsos positivos con las canciones fuera de
ella, tamaño de la huella (RNF2) y latencia.

Uso (desde backend/):
    python ../evaluation/tune_params.py [--conditions babble:0 pink:0 white:-5] [--per-song 4]
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np

from common import FS, build_db, load_library, random_clips, split_holdout
from db.database import FingerprintDB
from fingerprint import config
from fingerprint.hashing import fingerprint_size_bytes, generate_hashes
from fingerprint.matcher import find_matches, is_confident, score_candidates
from fingerprint.peaks import find_peaks
from fingerprint.spectrogram import spectrogram_db
from noise import make_noise, mix_at_snr

CONFIGS = [
    # nombre, vecindario (frec, tiempo), umbral dB, fan-out
    ("actual 21×21 +10dB fo10", (21, 21), 10.0, 10),
    ("umbral +15dB", (21, 21), 15.0, 10),
    ("umbral +6dB", (21, 21), 6.0, 10),
    ("vecindario 15×15", (15, 15), 10.0, 10),
    ("vecindario 21×11", (21, 11), 10.0, 10),
    ("fan-out 15", (21, 21), 10.0, 15),
    ("fan-out 5", (21, 21), 10.0, 5),
    ("vecindario 15×15 fo15", (15, 15), 10.0, 15),
    ("vecindario 15×15 +6dB", (15, 15), 6.0, 10),
]


def make_fingerprint(neighborhood, prominence, fan_out):
    def fingerprint(x):
        peaks = find_peaks(spectrogram_db(x), neighborhood=neighborhood, min_prominence_db=prominence)
        return (peaks, *generate_hashes(peaks, fan_out=fan_out))
    return fingerprint


def query(db, fingerprint, x):
    _, h, o = fingerprint(x)
    cands = score_candidates(*find_matches(db, h, o))
    return cands, is_confident(cands)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conditions", nargs="+", default=["babble:0", "pink:0", "white:-5", "babble:5"])
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--per-song", type=int, default=4)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--only", default=None, help="evaluar solo las configuraciones cuyo nombre contenga este texto")
    args = parser.parse_args()
    conditions = [(c.split(":")[0], float(c.split(":")[1])) for c in args.conditions]

    with FingerprintDB(config.DB_PATH) as db:
        songs, audio = load_library(db)
    kept, held_out = split_holdout(songs, 4)

    # Mismos fragmentos y mismo ruido para todas las configuraciones (diseño pareado)
    rng = np.random.default_rng(args.seed)
    def make_queries(song_list):
        qs = []
        for s in song_list:
            for _, clean in random_clips(audio[s["file_name"]], args.duration, args.per_song, rng):
                for kind, snr in conditions:
                    qs.append((s, kind, snr, mix_at_snr(clean, make_noise(kind, len(clean), rng), snr)))
        return qs
    positives, negatives = make_queries(kept), make_queries(held_out)
    wav_bytes = sum(s["wav_bytes"] for s in kept)
    print(f"{len(positives)} consultas positivas y {len(negatives)} negativas por configuración, fragmentos de {args.duration:g} s")

    header = f"{'configuración':<26}{'hash/s':>7}{'% WAV':>7}" + "".join(f"{k}:{s:g}".rjust(11) for k, s in conditions) + f"{'FP':>5}{'neg máx':>8}{'lat ms':>8}"
    print("\n" + header)
    for name, nb, prom, fan in CONFIGS:
        if args.only and args.only not in name:
            continue
        fp = make_fingerprint(nb, prom, fan)
        with tempfile.TemporaryDirectory() as tmp:
            db = build_db(Path(tmp) / "tune.db", kept, audio, fingerprint=fp)
            try:
                n_hashes = db.stats()["n_hashes"]
                duration = sum(s["duration_s"] for s in kept)
                acc = {c: [] for c in conditions}
                lat = []
                for s, kind, snr, y in positives:
                    t0 = time.perf_counter()
                    cands, ok = query(db, fp, y)
                    lat.append(time.perf_counter() - t0)
                    acc[(kind, snr)].append(ok and db.get_song(cands[0].song_id)["file_sha1"] == s["file_sha1"])
                neg_scores, n_fp = [], 0
                for s, kind, snr, y in negatives:
                    cands, ok = query(db, fp, y)
                    neg_scores.append(cands[0].score if cands else 0)
                    n_fp += ok
            finally:
                db.close()
        size_pct = 100 * fingerprint_size_bytes(n_hashes) / wav_bytes
        print(
            f"{name:<26}{n_hashes / duration:7.0f}{size_pct:7.2f}"
            + "".join(f"{100 * np.mean(acc[c]):10.1f}%" for c in conditions)
            + f"{n_fp:>5}{max(neg_scores):>8}{1000 * np.median(lat):>8.0f}"
        )


if __name__ == "__main__":
    main()
