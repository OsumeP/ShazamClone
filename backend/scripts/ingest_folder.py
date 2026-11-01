"""Ingesta de archivos propios a la base de datos (Proceso 5.1).

Por cada archivo de audio: SHA-1 (omite los ya ingestados) -> metadatos ->
normalización (guarda el WAV de referencia) -> huella -> inserción en SQLite.

Uso (desde backend/):
    python -m scripts.ingest_folder [--folder ../data/raw] [--db ../data/fingerprints.db]
    python -m scripts.ingest_folder --list
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from db.database import FingerprintDB, file_sha1
from fingerprint import config
from fingerprint.audio_io import load_audio, save_wav
from fingerprint.hashing import fingerprint_signal, fingerprint_size_bytes
from fingerprint.metadata import load_overrides, resolve_metadata


def ingest(folder: Path, db: FingerprintDB) -> None:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in config.AUDIO_EXTENSIONS)
    overrides = load_overrides(folder)
    added = skipped = 0
    t_start = time.perf_counter()

    for path in files:
        sha1 = file_sha1(path)
        existing = db.song_by_sha1(sha1)
        if existing:
            print(f"[omitido] {path.name}  (ya existe como id {existing['id']})")
            skipped += 1
            continue

        t0 = time.perf_counter()
        meta = resolve_metadata(path, overrides)
        x = load_audio(path)
        wav_path = config.NORMALIZED_DIR / (path.stem + ".wav")
        save_wav(wav_path, x)
        _, hashes, offsets = fingerprint_signal(x)
        song_id = db.add_song(
            title=meta["title"],
            artist=meta["artist"],
            album=meta["album"],
            duration_s=len(x) / config.SAMPLE_RATE,
            file_name=path.name,
            file_sha1=sha1,
            wav_bytes=wav_path.stat().st_size,
            hashes=hashes,
            offsets=offsets,
        )
        added += 1
        print(
            f"[{song_id:3d}] {meta['artist'] or '?'} — {meta['title']}  "
            f"({meta['source']}, {len(hashes)} hashes, {time.perf_counter() - t0:.2f} s)"
        )

    print(f"\n{added} agregadas, {skipped} omitidas en {time.perf_counter() - t_start:.1f} s")
    report(db)


def report(db: FingerprintDB) -> None:
    s = db.stats()
    if not s["n_songs"]:
        print("La base de datos está vacía.")
        return
    logical = fingerprint_size_bytes(s["n_hashes"])
    print(
        f"\nBase de datos: {s['n_songs']} canciones, {s['duration_s'] / 60:.1f} min, {s['n_hashes']:,} hashes\n"
        f"  WAV normalizado (referencia A1): {s['wav_bytes'] / 1e6:8.1f} MB\n"
        f"  Huella lógica (10 B/hash):       {logical / 1e6:8.2f} MB = {100 * logical / s['wav_bytes']:.2f} % (RNF2 ≤ 5 %)\n"
        f"  Archivo SQLite en disco:         {s['db_bytes'] / 1e6:8.2f} MB = {100 * s['db_bytes'] / s['wav_bytes']:.2f} %"
    )


def list_songs(db: FingerprintDB) -> None:
    for row in db.list_songs():
        print(f"[{row['id']:3d}] {row['artist'] or '?'} — {row['title']}  ({row['duration_s']:.0f} s, {row['n_hashes']} hashes)")
    report(db)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", type=Path, default=config.RAW_DIR)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--list", action="store_true", help="solo listar el contenido de la BD")
    args = parser.parse_args()

    with FingerprintDB(args.db) as db:
        if args.list:
            list_songs(db)
        else:
            ingest(args.folder, db)


if __name__ == "__main__":
    main()
