"""Utilidades compartidas por los scripts de evaluación."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from db.database import FingerprintDB  # noqa: E402
from fingerprint import config  # noqa: E402
from fingerprint.audio_io import load_audio  # noqa: E402
from fingerprint.hashing import fingerprint_signal  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FS = config.SAMPLE_RATE


def load_library(db: FingerprintDB) -> tuple[list[dict], dict[str, np.ndarray]]:
    """Canciones de la BD y su audio normalizado (por file_name)."""
    songs = [dict(r) for r in db.list_songs()]
    audio = {
        s["file_name"]: load_audio(config.NORMALIZED_DIR / (Path(s["file_name"]).stem + ".wav"))
        for s in songs
    }
    return songs, audio


def random_clips(x: np.ndarray, duration: float, n: int, rng) -> list[tuple[int, np.ndarray]]:
    """n fragmentos de `duration` s en posiciones aleatorias (resolución de una muestra)."""
    length = int(duration * FS)
    starts = rng.integers(0, len(x) - length, size=n)
    return [(int(s), x[s : s + length]) for s in starts]


def split_holdout(songs: list[dict], every: int) -> tuple[list[dict], list[dict]]:
    """(canciones que quedan en la BD, canciones fuera) — 1 de cada `every` queda fuera."""
    held_out = songs[::every]
    return [s for s in songs if s not in held_out], held_out


def build_db(path: Path, songs: list[dict], audio: dict, fingerprint=fingerprint_signal) -> FingerprintDB:
    """BD nueva con las canciones dadas. `fingerprint(x) -> (picos, hashes, offsets)`."""
    db = FingerprintDB(path)
    for s in songs:
        _, h, o = fingerprint(audio[s["file_name"]])
        db.add_song(
            title=s["title"], artist=s["artist"], album=s["album"], duration_s=s["duration_s"],
            file_name=s["file_name"], file_sha1=s["file_sha1"], wav_bytes=s["wav_bytes"], hashes=h, offsets=o,
        )
    return db
