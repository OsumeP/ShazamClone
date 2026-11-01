"""Mapa de constelación: extracción de picos espectrales (RF3).

Un punto (m, k) del espectrograma es un pico si
  1. es el máximo de su vecindario rectangular (frecuencia × tiempo), y
  2. supera en al menos PEAK_MIN_PROMINENCE_DB la mediana de su propia ventana
     (columna m del espectrograma, dentro de la banda).

La condición 2 es relativa a la propia señal, por lo que no depende de la
ganancia de grabación: sumar una constante en dB a todo el espectrograma
(subir o bajar el volumen) no cambia los picos detectados. Y es local en el
tiempo, así que una canción completa y un fragmento suyo obtienen los mismos
picos en las ventanas que comparten. El piso de ruido
plano (alta entropía) queda por debajo del umbral y se descarta; sobreviven
los pocos puntos de máxima energía (baja entropía).
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter

from . import config
from .spectrogram import frequency_axis


def find_peaks(
    S_db: np.ndarray,
    fmin_hz: float = config.PEAK_FMIN_HZ,
    fmax_hz: float = config.PEAK_FMAX_HZ,
    neighborhood: tuple[int, int] = (config.PEAK_NEIGHBORHOOD_FREQ, config.PEAK_NEIGHBORHOOD_TIME),
    min_prominence_db: float = config.PEAK_MIN_PROMINENCE_DB,
    n_fft: int = config.N_FFT,
) -> np.ndarray:
    """Extrae el mapa de constelación de un espectrograma en dB.

    Args:
        S_db: espectrograma (n_bins, n_frames).

    Returns:
        Arreglo int32 (n_picos, 2) con columnas (ventana m, bin k), ordenado por
        tiempo y luego por frecuencia. k es el índice absoluto del bin.
    """
    f = frequency_axis(n_fft)
    k_lo = int(np.searchsorted(f, fmin_hz))
    k_hi = int(np.searchsorted(f, fmax_hz, side="right"))
    if k_hi <= k_lo or S_db.shape[1] == 0:
        return np.empty((0, 2), dtype=np.int32)

    # El vecindario se evalúa sobre la banda extendida medio vecindario a cada
    # lado: así un punto en el borde de la banda solo es pico si también
    # domina a sus vecinos de fuera (evita filas falsas de picos en fmin/fmax).
    half = neighborhood[0] // 2
    e_lo, e_hi = max(0, k_lo - half), min(S_db.shape[0], k_hi + half)
    local_max = maximum_filter(
        S_db[e_lo:e_hi], size=neighborhood, mode="constant", cval=-np.inf
    )[k_lo - e_lo : k_hi - e_lo]

    # Umbral por ventana: depende solo del contenido de esa ventana, que es el
    # mismo en la canción completa y en cualquier fragmento que la contenga.
    # (Una mediana global de la señal cambia según qué porción se analiza.)
    band = S_db[k_lo:k_hi]
    threshold = np.median(band, axis=0, keepdims=True) + min_prominence_db
    is_peak = (band == local_max) & (band >= threshold)

    k_idx, m_idx = np.nonzero(is_peak)
    peaks = np.column_stack([m_idx, k_idx + k_lo]).astype(np.int32)
    order = np.lexsort((peaks[:, 1], peaks[:, 0]))
    return peaks[order]
