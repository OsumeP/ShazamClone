"""Transformada de Fourier de Tiempo Reducido y espectrograma (RF2).

Implementación propia con numpy de

    X(m, k) = Σ_n x[n] · w[n − mR] · e^{−j 2π k n / N}

donde la ventana m cubre las muestras [mR, mR + N). No se rellena la señal
en los bordes: el número de ventanas es 1 + ⌊(len(x) − N) / R⌋.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import get_window

from . import config


def frame_signal(x: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    """Divide x en ventanas solapadas: (n_frames, n_fft). Vista sin copia."""
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    return sliding_window_view(x, n_fft)[::hop]


def stft(
    x: np.ndarray,
    n_fft: int = config.N_FFT,
    hop: int = config.HOP,
    window: str = config.WINDOW,
) -> np.ndarray:
    """STFT de una señal real.

    Returns:
        Matriz compleja X de forma (n_fft // 2 + 1, n_frames):
        filas = bins de frecuencia (0 … fs/2), columnas = ventanas en el tiempo.
    """
    w = get_window(window, n_fft).astype(np.float32)   # Hann periódica
    frames = frame_signal(np.asarray(x, dtype=np.float32), n_fft, hop)
    # rfft: solo frecuencias no negativas (la señal es real -> espectro simétrico)
    return np.fft.rfft(frames * w, axis=1).T


def power_spectrogram(X: np.ndarray) -> np.ndarray:
    """S(m, ω) = |X(m, ω)|²."""
    return (X.real ** 2 + X.imag ** 2).astype(np.float32)


def to_db(S: np.ndarray, eps: float = config.DB_EPS) -> np.ndarray:
    """S_dB = 10 · log10(S + ε)."""
    return (10.0 * np.log10(S + eps)).astype(np.float32)


def spectrogram_db(
    x: np.ndarray,
    n_fft: int = config.N_FFT,
    hop: int = config.HOP,
    window: str = config.WINDOW,
) -> np.ndarray:
    """Espectrograma en dB: (n_fft // 2 + 1, n_frames)."""
    return to_db(power_spectrogram(stft(x, n_fft, hop, window)))


def frequency_axis(n_fft: int = config.N_FFT, fs: int = config.SAMPLE_RATE) -> np.ndarray:
    """Frecuencia (Hz) de cada bin k: f_k = k · fs / N."""
    return np.fft.rfftfreq(n_fft, d=1.0 / fs)


def time_axis(
    n_frames: int,
    n_fft: int = config.N_FFT,
    hop: int = config.HOP,
    fs: int = config.SAMPLE_RATE,
) -> np.ndarray:
    """Instante (s) del centro de cada ventana: t_m = (mR + N/2) / fs."""
    return (np.arange(n_frames) * hop + n_fft / 2) / fs
