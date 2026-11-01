import json
import sqlite3

import numpy as np
import pytest

from db.database import FingerprintDB, file_sha1
from fingerprint.metadata import parse_filename, resolve_metadata


@pytest.fixture
def db(tmp_path):
    with FingerprintDB(tmp_path / "test.db") as database:
        yield database


def add(db, sha1="abc", n=100, seed=0):
    rng = np.random.default_rng(seed)
    hashes = rng.integers(0, 2**32, n, dtype=np.uint64).astype(np.uint32)
    offsets = rng.integers(0, 5000, n).astype(np.uint32)
    return db.add_song(
        title="T", artist="A", album=None, duration_s=10.0, file_name="a.mp3",
        file_sha1=sha1, wav_bytes=882_044, hashes=hashes, offsets=offsets,
    ), hashes, offsets


def test_insercion_y_lectura(db):
    song_id, hashes, offsets = add(db)
    assert db.get_song(song_id)["n_hashes"] == 100
    rows = db.conn.execute(
        "SELECT hash, offset_frame FROM fingerprints WHERE song_id = ?", (song_id,)
    ).fetchall()
    assert sorted(map(tuple, rows)) == sorted(zip(hashes.tolist(), offsets.tolist()))


def test_hashes_uint32_altos_se_conservan(db):
    hashes = np.array([2**32 - 1, 2**31], dtype=np.uint32)
    song_id = db.add_song(
        title="T", artist=None, album=None, duration_s=1.0, file_name="x.wav",
        file_sha1="x", wav_bytes=1, hashes=hashes, offsets=np.array([0, 1], dtype=np.uint32),
    )
    got = {r[0] for r in db.conn.execute("SELECT hash FROM fingerprints WHERE song_id = ?", (song_id,))}
    assert got == {2**32 - 1, 2**31}


def test_sha1_duplicado_es_rechazado(db):
    add(db, sha1="dup")
    assert db.song_by_sha1("dup") is not None
    with pytest.raises(sqlite3.IntegrityError):
        add(db, sha1="dup", seed=1)
    assert db.stats()["n_songs"] == 1                # la transacción fallida no dejó residuos


def test_borrado_en_cascada(db):
    song_id, _, _ = add(db)
    db.delete_song(song_id)
    assert db.conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0] == 0


def test_consulta_por_hash_usa_la_clave_primaria(db):
    add(db)
    plan = db.conn.execute(
        "EXPLAIN QUERY PLAN SELECT song_id, offset_frame FROM fingerprints WHERE hash = ?", (1,)
    ).fetchall()
    assert "PRIMARY KEY" in " ".join(row[-1] for row in plan)


def test_stats(db):
    add(db, sha1="a")
    add(db, sha1="b", seed=1)
    s = db.stats()
    assert (s["n_songs"], s["n_hashes"], s["wav_bytes"]) == (2, 200, 2 * 882_044)
    assert s["db_bytes"] > 0


def test_file_sha1(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hola")
    assert file_sha1(p) == "99800b85d3383e3a2fb45eb7d0066a4879a9dad0"


@pytest.mark.parametrize(
    "stem, expected",
    [
        ("Linkin Park - Crawling", ("Linkin Park", "Crawling")),
        ("Shiro SAGISU - Number One - Bankai", ("Shiro SAGISU", "Number One - Bankai")),
        ("FLOW - HERO -Kibou no uta-", ("FLOW", "HERO -Kibou no uta-")),
        ("東方- Bad Apple", ("東方", "Bad Apple")),
        ("Jay-Z - Encore", ("Jay-Z", "Encore")),
        ("solo_un_titulo", (None, "solo_un_titulo")),
    ],
)
def test_parse_filename(stem, expected):
    assert parse_filename(stem) == expected


def test_metadata_json_tiene_prioridad(tmp_path):
    song = tmp_path / "Artista - Titulo.mp3"
    song.write_bytes(b"")
    (tmp_path / "metadata.json").write_text(
        json.dumps({song.name: {"title": "Título real", "artist": "Artista real", "album": "Álbum"}}),
        encoding="utf-8",
    )
    meta = resolve_metadata(song)
    assert meta == {"title": "Título real", "artist": "Artista real", "album": "Álbum", "source": "metadata.json"}


def test_metadata_desde_nombre_de_archivo(tmp_path):
    song = tmp_path / "Petit Biscuit - Sunset Lover.mp3"
    song.write_bytes(b"")
    meta = resolve_metadata(song, overrides={})
    assert (meta["artist"], meta["title"], meta["source"]) == ("Petit Biscuit", "Sunset Lover", "filename")
