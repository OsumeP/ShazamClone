"""Hashing combinatorio de pares de picos (RF3), según Wang (2003) §2.2.

Cada pico actúa como ancla (t1, f1) y se empareja con los siguientes
FAN_OUT picos de su zona objetivo, es decir, con Δt = t2 − t1 en
[TARGET_DT_MIN, TARGET_DT_MAX]. Cada par produce

    hash   = f1 · 2^(F+D) + f2 · 2^D + Δt      (F = HASH_FREQ_BITS, D = HASH_DT_BITS)
    offset = t1                                 (ventana del ancla)

El hash solo depende de diferencias de tiempo, así que es invariante a
desplazamientos: un fragmento que empieza en la ventana s de la canción
produce los mismos hashes con offset − s (la base del matching).
"""

from __future__ import annotations

import numpy as np

from . import config
from .audio_io import load_audio
from .peaks import find_peaks
from .spectrogram import spectrogram_db

_F_BITS = config.HASH_FREQ_BITS
_D_BITS = config.HASH_DT_BITS
assert 2 * _F_BITS + _D_BITS <= 32, "el hash debe caber en uint32"


def pack_hash(f1: np.ndarray, f2: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """Empaqueta (f1, f2, Δt) en un uint32."""
    f1 = np.asarray(f1, dtype=np.uint32)
    f2 = np.asarray(f2, dtype=np.uint32)
    dt = np.asarray(dt, dtype=np.uint32)
    return (f1 << (_F_BITS + _D_BITS)) | (f2 << _D_BITS) | dt


def unpack_hash(h: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Inversa de pack_hash."""
    h = np.asarray(h, dtype=np.uint32)
    f_mask = (1 << _F_BITS) - 1
    d_mask = (1 << _D_BITS) - 1
    return (h >> (_F_BITS + _D_BITS)) & f_mask, (h >> _D_BITS) & f_mask, h & d_mask


def generate_hashes(
    peaks: np.ndarray,
    fan_out: int = config.FAN_OUT,
    dt_min: int = config.TARGET_DT_MIN,
    dt_max: int = config.TARGET_DT_MAX,
) -> tuple[np.ndarray, np.ndarray]:
    """Genera los hashes de un mapa de constelación.

    Args:
        peaks: (n, 2) con columnas (ventana, bin), ordenado por tiempo.

    Returns:
        (hashes uint32, offsets uint32), sin pares (hash, offset) repetidos.
    """
    if not (0 <= dt_min <= dt_max < (1 << _D_BITS)):
        raise ValueError("zona objetivo fuera del rango representable")
    t = peaks[:, 0].astype(np.int64)
    f = peaks[:, 1].astype(np.int64)
    if len(f) and f.max() >= (1 << _F_BITS):
        raise ValueError("bin de frecuencia fuera del rango representable")

    hashes, offsets = [], []
    # Vectorizado: el k-ésimo vecino siguiente de todos los anclas a la vez.
    # Los picos están ordenados por tiempo, así que si el vecino k ya se sale
    # de la zona, los siguientes también; basta con filtrar por Δt.
    for k in range(1, fan_out + 1):
        if k >= len(t):
            break
        dt = t[k:] - t[:-k]
        ok = (dt >= dt_min) & (dt <= dt_max)
        hashes.append(pack_hash(f[:-k][ok], f[k:][ok], dt[ok]))
        offsets.append(t[:-k][ok].astype(np.uint32))

    if not hashes:
        return np.empty(0, np.uint32), np.empty(0, np.uint32)
    pairs = np.unique(
        np.column_stack([np.concatenate(hashes), np.concatenate(offsets)]), axis=0
    )
    return pairs[:, 0].astype(np.uint32), pairs[:, 1].astype(np.uint32)


def fingerprint_signal(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Señal normalizada -> (picos, hashes, offsets)."""
    peaks = find_peaks(spectrogram_db(x))
    hashes, offsets = generate_hashes(peaks)
    return peaks, hashes, offsets


def fingerprint_file(path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Archivo de audio -> (picos, hashes, offsets)."""
    return fingerprint_signal(load_audio(path))


def fingerprint_size_bytes(n_hashes: int) -> int:
    """Tamaño lógico de la huella almacenada (sin índices de la BD)."""
    return n_hashes * config.FINGERPRINT_RECORD_BYTES
