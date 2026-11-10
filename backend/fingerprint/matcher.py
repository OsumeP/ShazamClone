"""Matching y coherencia temporal (RF5), según Wang (2003) §2.3. 

1. Se buscan en la BD todos los hashes del fragmento (coincidencias exactas).
2. Por cada coincidencia se calcula Δ = offset_canción − offset_fragmento.
3. Si el fragmento proviene de una canción, sus coincidencias verdaderas
   comparten el mismo Δ (los puntos forman una diagonal en el diagrama
   offset_fragmento vs. offset_canción). Las coincidencias casuales con otras
   canciones tienen Δ dispersos.
4. La puntuación de cada canción es la altura del pico de su histograma de Δ.
   Ese Δ indica además en qué punto de la canción empieza el fragmento.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import config
from .hashing import fingerprint_signal, generate_hashes
from .peaks import find_peaks
from .spectrogram import spectrogram_db


@dataclass
class Candidate:
    song_id: int
    score: int          # hashes alineados en el mejor Δ (± tolerancia)
    delta: int          # Δ en ventanas = ventana de la canción donde empieza el fragmento
    n_matches: int      # coincidencias de hash con la canción, alineadas o no

    @property
    def offset_s(self) -> float:
        return self.delta * config.HOP / config.SAMPLE_RATE


@dataclass
class Recognition:
    song: dict | None                   # fila de `songs` si se reconoció, si no None
    candidates: list[Candidate]         # ordenados por puntuación descendente
    n_query_hashes: int
    timings: dict[str, float] = field(default_factory=dict)
    spectrogram: np.ndarray | None = None   # S en dB (n_bins, n_ventanas); solo con with_analysis
    peaks: np.ndarray | None = None         # mapa de constelación (ventana, bin); solo con with_analysis

    @property
    def recognized(self) -> bool:
        return self.song is not None

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def find_matches(db, hashes: np.ndarray, offsets: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cruza los hashes del fragmento con la BD.

    Un mismo hash puede aparecer varias veces en el fragmento y en la BD; se
    devuelven todas las combinaciones.

    Returns:
        (song_id, offset_canción, offset_fragmento) por coincidencia, int64.
    """
    db_hash, db_song, db_offset = db.lookup(hashes)
    order = np.argsort(hashes, kind="stable")
    q_hash = hashes[order].astype(np.int64)
    q_offset = offsets[order].astype(np.int64)

    lo = np.searchsorted(q_hash, db_hash, side="left")
    hi = np.searchsorted(q_hash, db_hash, side="right")
    counts = hi - lo
    total = int(counts.sum())
    # índice en el fragmento de cada combinación: lo[i], lo[i]+1, …, hi[i]−1
    within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    q_idx = np.repeat(lo, counts) + within
    return np.repeat(db_song, counts), np.repeat(db_offset, counts), q_offset[q_idx]


def score_candidates(
    song_ids: np.ndarray,
    song_offsets: np.ndarray,
    query_offsets: np.ndarray,
    tolerance: int = config.MATCH_DELTA_TOLERANCE,
) -> list[Candidate]:
    """Histograma de Δ por canción; puntuación = altura del pico (± tolerancia)."""
    if len(song_ids) == 0:
        return []
    delta = song_offsets - query_offsets
    d_min = int(delta.min())
    span = int(delta.max()) - d_min + tolerance + 1
    key = song_ids * span + (delta - d_min)          # (canción, Δ) -> un entero

    keys, counts = np.unique(key, return_counts=True)
    scores = counts.copy()
    for s in range(1, tolerance + 1):                 # suma los bins Δ+1 … Δ+tol
        idx = np.searchsorted(keys, keys + s)
        ok = idx < len(keys)
        ok[ok] = keys[idx[ok]] == keys[ok] + s
        scores[ok] += counts[idx[ok]]

    key_song = keys // span
    key_delta = keys % span + d_min
    order = np.lexsort((-scores, key_song))           # por canción, mejor Δ primero
    first = np.r_[True, key_song[order][1:] != key_song[order][:-1]]
    best = order[first]

    songs, n_matches = np.unique(song_ids, return_counts=True)
    n_by_song = dict(zip(songs.tolist(), n_matches.tolist()))
    candidates = [
        Candidate(int(key_song[i]), int(scores[i]), int(key_delta[i]), n_by_song[int(key_song[i])])
        for i in best
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def is_confident(
    candidates: list[Candidate],
    min_score: int = config.MATCH_MIN_SCORE,
    min_ratio: float = config.MATCH_MIN_RATIO,
) -> bool:
    """Regla de decisión: pico suficientemente alto y claramente sobre el segundo."""
    if not candidates:
        return False
    second = candidates[1].score if len(candidates) > 1 else 0
    return candidates[0].score >= min_score and candidates[0].score >= min_ratio * second


def recognize(
    x: np.ndarray,
    db,
    tolerance: int = config.MATCH_DELTA_TOLERANCE,
    min_score: int = config.MATCH_MIN_SCORE,
    min_ratio: float = config.MATCH_MIN_RATIO,
    with_analysis: bool = False,
) -> Recognition:
    """Reconoce un fragmento ya normalizado (mono, 44.1 kHz).

    Los tiempos medidos empiezan con el audio ya en memoria, es decir, cuando
    termina la grabación (acuerdo A3).
    """
    t0 = time.perf_counter()
    if with_analysis:
        # Mismo proceso que fingerprint_signal, pero conservando el espectrograma y los picos.
        S_db = spectrogram_db(x)
        peaks = find_peaks(S_db)
        hashes, offsets = generate_hashes(peaks)
    else:
        S_db = peaks = None
        _, hashes, offsets = fingerprint_signal(x)
    t1 = time.perf_counter()
    song_ids, song_offsets, query_offsets = find_matches(db, hashes, offsets)
    t2 = time.perf_counter()
    candidates = score_candidates(song_ids, song_offsets, query_offsets, tolerance)
    t3 = time.perf_counter()

    song = None
    if is_confident(candidates, min_score, min_ratio):
        song = dict(db.get_song(candidates[0].song_id))
    timings = {
        "fingerprint_s": t1 - t0,
        "lookup_s": t2 - t1,
        "scoring_s": t3 - t2,
        "total_s": time.perf_counter() - t0,
    }
    return Recognition(song, candidates, len(hashes), timings, S_db, peaks)
