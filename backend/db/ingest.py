"""Ingesta de un archivo de audio a la BD (Proceso 5.1), compartida por la CLI
`scripts/ingest_folder.py` y el endpoint `POST /api/ingest`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fingerprint import config
from fingerprint.audio_io import load_audio, save_wav
from fingerprint.hashing import fingerprint_signal
from fingerprint.metadata import resolve_metadata

from .database import FingerprintDB, file_sha1


@dataclass
class IngestResult:
    song_id: int
    title: str
    artist: str | None
    album: str | None
    metadata_source: str
    n_hashes: int
    duration_s: float
    already_existed: bool


def ingest_file(path: str | Path, db: FingerprintDB, overrides: dict | None = None) -> IngestResult:
    """SHA-1 (omite si ya existe) → metadatos → normalización (guarda el WAV de
    referencia) → huella → inserción."""
    path = Path(path)
    sha1 = file_sha1(path)
    existing = db.song_by_sha1(sha1)
    if existing:
        return IngestResult(
            existing["id"], existing["title"], existing["artist"], existing["album"], "bd",
            existing["n_hashes"], existing["duration_s"], already_existed=True,
        )

    meta = resolve_metadata(path, overrides)
    x = load_audio(path)
    wav_path = config.NORMALIZED_DIR / (path.stem + ".wav")
    save_wav(wav_path, x)
    _, hashes, offsets = fingerprint_signal(x)
    duration_s = len(x) / config.SAMPLE_RATE
    song_id = db.add_song(
        title=meta["title"],
        artist=meta["artist"],
        album=meta["album"],
        duration_s=duration_s,
        file_name=path.name,
        file_sha1=sha1,
        wav_bytes=wav_path.stat().st_size,
        hashes=hashes,
        offsets=offsets,
    )
    return IngestResult(
        song_id, meta["title"], meta["artist"], meta["album"], meta["source"],
        len(hashes), duration_s, already_existed=False,
    )
