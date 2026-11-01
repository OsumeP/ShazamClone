import numpy as np
import pytest

from db.database import FingerprintDB
from fingerprint import config
from fingerprint.hashing import fingerprint_signal
from fingerprint.matcher import find_matches, is_confident, recognize, score_candidates, Candidate

from tests.test_fingerprint import synthetic_music

FS = config.SAMPLE_RATE
HOP = config.HOP


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    """BD con 3 'canciones' sintéticas distintas."""
    songs = {i: synthetic_music(seconds=30, seed=i) for i in range(3)}
    with FingerprintDB(tmp_path_factory.mktemp("db") / "lib.db") as db:
        ids = {}
        for i, x in songs.items():
            _, h, o = fingerprint_signal(x)
            ids[i] = db.add_song(
                title=f"Canción {i}", artist="Sintética", album=None, duration_s=len(x) / FS,
                file_name=f"{i}.wav", file_sha1=str(i), wav_bytes=len(x) * 2, hashes=h, offsets=o,
            )
        yield db, songs, ids


def test_find_matches_expande_hashes_repetidos():
    class FakeDB:
        def lookup(self, hashes):
            # el hash 7 aparece 2 veces en la BD, el 9 una vez
            return np.array([7, 7, 9]), np.array([1, 2, 1]), np.array([100, 200, 300])

    hashes = np.array([9, 7, 7], dtype=np.uint32)        # el 7 aparece 2 veces en el fragmento
    offsets = np.array([5, 10, 20], dtype=np.uint32)
    song, s_off, q_off = find_matches(FakeDB(), hashes, offsets)
    got = sorted(zip(song.tolist(), s_off.tolist(), q_off.tolist()))
    assert got == sorted([(1, 100, 10), (1, 100, 20), (2, 200, 10), (2, 200, 20), (1, 300, 5)])


def test_score_toma_el_pico_del_histograma_con_tolerancia():
    song = np.array([1, 1, 1, 1, 1, 2, 2])
    s_off = np.array([50, 51, 62, 70, 90, 10, 40])
    q_off = np.array([10, 11, 21, 30, 5, 3, 3])
    # canción 1: Δ = 40, 40, 41, 40, 85 → pico en 40 con 3 (+1 en 41 por tolerancia)
    cands = score_candidates(song, s_off, q_off, tolerance=1)
    assert (cands[0].song_id, cands[0].score, cands[0].delta, cands[0].n_matches) == (1, 4, 40, 5)
    assert score_candidates(song, s_off, q_off, tolerance=0)[0].score == 3


def test_regla_de_decision():
    c = lambda score: Candidate(1, score, 0, score)
    assert is_confident([c(50), c(10)], min_score=10, min_ratio=2)
    assert not is_confident([c(50), c(30)], min_score=10, min_ratio=2)   # ambiguo
    assert not is_confident([c(8)], min_score=10, min_ratio=2)           # muy pocos
    assert not is_confident([])


@pytest.mark.parametrize("song, start_s", [(0, 3.3), (1, 12.71), (2, 20.05)])
def test_reconoce_fragmento_y_estima_su_inicio(library, song, start_s):
    db, songs, ids = library
    i0 = int(start_s * FS)                                # inicio no alineado con HOP
    clip = songs[song][i0 : i0 + 5 * FS]
    r = recognize(clip, db)
    assert r.recognized and r.song["id"] == ids[song]
    assert abs(r.best.offset_s - start_s) <= HOP / FS     # error ≤ una ventana
    assert r.timings["total_s"] < 3.0                     # RNF3


def test_rechaza_audio_que_no_esta_en_la_bd(library):
    db, _, _ = library
    r = recognize(synthetic_music(seconds=5, seed=99), db)
    assert not r.recognized


def test_lookup_vacio(library):
    db, _, _ = library
    h, s, o = db.lookup(np.array([], dtype=np.uint32))
    assert len(h) == len(s) == len(o) == 0
