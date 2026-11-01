"""Generadores de ruido y mezcla a una SNR dada (Fase 5, canal ruidoso §3.5).

Tipos de ruido (todos a 44.1 kHz):
- white:  ruido blanco, densidad espectral plana (máxima entropía espectral).
- pink:   ruido rosa, potencia ∝ 1/f (energía igual por octava; típico de ambientes).
- brown:  ruido marrón, potencia ∝ 1/f² (retumbe grave: tráfico, aire acondicionado).
- babble: murmullo de varias voces simuladas (café, multitud). Cada "voz" tiene
          una serie armónica con f0 variable y ruido de banda vocal, modulados
          por una envolvente silábica (~4 Hz). Sus armónicos generan picos
          espectrales que compiten con los de la música: es el caso más difícil.

SNR = 10·log10(P_señal / P_ruido) con potencias medias sobre todo el fragmento
y toda la banda (0 – 22.05 kHz).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

FS = 44_100
NOISE_TYPES = ("white", "pink", "brown", "babble")


def _normalize(x: np.ndarray) -> np.ndarray:
    return (x / np.sqrt(np.mean(x**2))).astype(np.float32)


def white(n: int, rng) -> np.ndarray:
    return _normalize(rng.standard_normal(n))


def colored(n: int, rng, exponent: float, f_floor: float = 20.0) -> np.ndarray:
    """Ruido con densidad de potencia ∝ 1/f^exponent (moldeado en frecuencia)."""
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1 / FS), f_floor)
    X *= f ** (-exponent / 2)
    X[0] = 0
    return _normalize(np.fft.irfft(X, n))


def pink(n: int, rng) -> np.ndarray:
    return colored(n, rng, 1.0)


def brown(n: int, rng) -> np.ndarray:
    return colored(n, rng, 2.0)


def _smooth_random(n: int, rng, rate_hz: float) -> np.ndarray:
    """Curva aleatoria suave en [0, 1) con ~rate_hz variaciones por segundo."""
    k = max(2, int(n / FS * rate_hz) + 2)
    return np.interp(np.arange(n), np.linspace(0, n, k), rng.random(k))


def babble(n: int, rng, talkers: int = 6) -> np.ndarray:
    voice_band = butter(4, [300, 3400], btype="bandpass", fs=FS, output="sos")
    out = np.zeros(n)
    for _ in range(talkers):
        f0 = rng.uniform(100, 250) * (1 + 0.15 * (_smooth_random(n, rng, 3) - 0.5))
        phase = 2 * np.pi * np.cumsum(f0) / FS
        harmonics = sum(np.sin(k * phase) / k for k in range(1, int(3400 / f0.max()) + 1))
        breath = sosfiltfilt(voice_band, rng.standard_normal(n))
        voice = _normalize(harmonics) + 0.5 * _normalize(breath)
        syllables = _smooth_random(n, rng, 8) ** 3                # ráfagas ~4 Hz
        out += voice * syllables
    return _normalize(out)


GENERATORS = {"white": white, "pink": pink, "brown": brown, "babble": babble}


def make_noise(kind: str, n: int, rng) -> np.ndarray:
    return GENERATORS[kind](n, rng)


def mix_at_snr(clean: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """clean + noise escalado para lograr la SNR pedida. Si la mezcla satura, se
    reduce la ganancia total (no altera la SNR ni los picos, que son invariantes
    a la ganancia)."""
    p_clean = np.mean(clean.astype(np.float64) ** 2)
    p_noise = np.mean(noise.astype(np.float64) ** 2)
    scale = np.sqrt(p_clean / (p_noise * 10 ** (snr_db / 10)))
    y = clean + scale * noise
    peak = np.abs(y).max()
    return (y / peak if peak > 1 else y).astype(np.float32)
