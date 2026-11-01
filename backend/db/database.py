"""Almacenamiento de huellas en SQLite (Proceso 5.1, paso 6).

Esquema:
    songs(id, title, artist, album, duration_s, file_name, file_sha1, n_hashes, wav_bytes, created_at)
    fingerprints(hash, song_id, offset_frame)  PRIMARY KEY (hash, song_id, offset_frame) WITHOUT ROWID

`fingerprints` es una tabla WITHOUT ROWID: las filas se guardan en un B-tree
ordenado por su clave primaria, que empieza por `hash`. Así la propia tabla
funciona como índice para buscar por hash (Fase 4) y no hace falta un índice
secundario que duplique los datos en disco.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import numpy as np

from fingerprint import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id          INTEGER PRIMARY KEY,
    title       TEXT    NOT NULL,
    artist      TEXT,
    album       TEXT,
    duration_s  REAL    NOT NULL,
    file_name   TEXT    NOT NULL,
    file_sha1   TEXT    NOT NULL UNIQUE,
    n_hashes    INTEGER NOT NULL,
    wav_bytes   INTEGER NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fingerprints (
    hash          INTEGER NOT NULL,
    song_id       INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    offset_frame  INTEGER NOT NULL,
    PRIMARY KEY (hash, song_id, offset_frame)
) WITHOUT ROWID;
"""


def file_sha1(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """SHA-1 del archivo original: identifica canciones ya ingestadas."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


class FingerprintDB:
    """Acceso a la base de datos de huellas. Usar como context manager."""

    def __init__(self, path: str | Path = config.DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "FingerprintDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Escritura ---------------------------------------------------------

    def add_song(
        self,
        *,
        title: str,
        artist: str | None,
        album: str | None,
        duration_s: float,
        file_name: str,
        file_sha1: str,
        wav_bytes: int,
        hashes: np.ndarray,
        offsets: np.ndarray,
    ) -> int:
        """Inserta la canción y todas sus huellas en una sola transacción."""
        order = np.lexsort((offsets, hashes))       # inserción en orden de la clave
        rows = zip(hashes[order].tolist(), offsets[order].tolist())
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO songs (title, artist, album, duration_s, file_name, file_sha1, n_hashes, wav_bytes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title, artist, album, duration_s, file_name, file_sha1, len(hashes), wav_bytes),
            )
            song_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO fingerprints (hash, song_id, offset_frame) VALUES (?, ?, ?)",
                ((h, song_id, o) for h, o in rows),
            )
        return song_id

    def delete_song(self, song_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))

    # --- Lectura -----------------------------------------------------------

    def song_by_sha1(self, sha1: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM songs WHERE file_sha1 = ?", (sha1,)).fetchone()

    def get_song(self, song_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()

    def list_songs(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM songs ORDER BY artist, title").fetchall()

    def stats(self) -> dict[str, int | float]:
        """Totales para el reporte de tamaños (RNF2)."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n_songs, COALESCE(SUM(n_hashes), 0) AS n_hashes,"
            " COALESCE(SUM(wav_bytes), 0) AS wav_bytes, COALESCE(SUM(duration_s), 0) AS duration_s"
            " FROM songs"
        ).fetchone()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        page_size = self.conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = self.conn.execute("PRAGMA page_count").fetchone()[0]
        return {**dict(row), "db_bytes": page_size * page_count}
