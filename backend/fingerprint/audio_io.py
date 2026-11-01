"""Carga y normalización de audio (RF1, RNF1).

Toda señal que entra al sistema se lleva a la forma canónica:
float32 en [-1, 1], mono, 44.1 kHz.

- WAV/FLAC/OGG se leen directamente con soundfile (libsndfile).
- MP3 y otros formatos se decodifican con FFmpeg a PCM float32 en su
  frecuencia y canales nativos; la mezcla a mono y el remuestreo se hacen
  siempre aquí con numpy/scipy, para que el procesamiento sea idéntico sin
  importar el formato de origen.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import config

_SOUNDFILE_EXTENSIONS = {".wav", ".flac", ".ogg"}


def find_binary(name: str) -> str:
    """Ubica ffmpeg/ffprobe (variable de entorno FFMPEG_DIR o PATH)."""
    custom_dir = os.environ.get("FFMPEG_DIR")
    if custom_dir:
        candidate = Path(custom_dir) / (name + (".exe" if os.name == "nt" else ""))
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(
            f"No se encontró '{name}'. Instala FFmpeg o define FFMPEG_DIR."
        )
    return found


def _probe_stream(path: Path) -> tuple[int, int]:
    """Devuelve (frecuencia de muestreo, canales) del primer stream de audio."""
    result = subprocess.run(
        [
            find_binary("ffprobe"), "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "json", str(path),
        ],
        capture_output=True, check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["sample_rate"]), int(stream["channels"])


def _decode_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    """Decodifica con FFmpeg a float32 (frames, canales) sin remuestrear."""
    fs, channels = _probe_stream(path)
    result = subprocess.run(
        [
            find_binary("ffmpeg"), "-v", "error", "-nostdin",
            "-i", str(path),
            "-map", "0:a:0",
            "-f", "f32le", "-acodec", "pcm_f32le",
            "pipe:1",
        ],
        capture_output=True, check=True,
    )
    data = np.frombuffer(result.stdout, dtype="<f4").reshape(-1, channels)
    return data, fs


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Lee un archivo de audio sin modificarlo.

    Returns:
        (datos float32 de forma (frames, canales), frecuencia de muestreo)
    """
    path = Path(path)
    if path.suffix.lower() in _SOUNDFILE_EXTENSIONS:
        data, fs = sf.read(str(path), dtype="float32", always_2d=True)
        return data, fs
    return _decode_ffmpeg(path)


def to_mono(data: np.ndarray) -> np.ndarray:
    """Promedia los canales: (frames, canales) -> (frames,)."""
    if data.ndim == 1:
        return data.astype(np.float32, copy=False)
    return data.mean(axis=1, dtype=np.float32)


def resample(x: np.ndarray, fs_in: int, fs_out: int = config.SAMPLE_RATE) -> np.ndarray:
    """Remuestreo polifásico racional (filtro anti-aliasing incluido).

    Ej. 48 000 -> 44 100 Hz equivale a up=147, down=160.
    """
    if fs_in == fs_out:
        return x.astype(np.float32, copy=False)
    ratio = Fraction(fs_out, fs_in)
    y = resample_poly(x, ratio.numerator, ratio.denominator)
    return y.astype(np.float32)


def normalize(data: np.ndarray, fs: int) -> np.ndarray:
    """Lleva una señal a la forma canónica: mono, 44.1 kHz, float32 en [-1, 1]."""
    x = resample(to_mono(data), fs, config.SAMPLE_RATE)
    return np.clip(x, -1.0, 1.0)


def load_audio(path: str | Path) -> np.ndarray:
    """Carga cualquier archivo soportado ya normalizado (mono, 44.1 kHz)."""
    data, fs = read_audio(path)
    return normalize(data, fs)


def load_audio_bytes(data: bytes, suffix: str = ".wav") -> np.ndarray:
    """Como load_audio, pero desde el contenido de un archivo en memoria
    (p. ej. un archivo subido a la API). `suffix` indica el formato."""
    suffix = suffix.lower() if suffix else ".wav"
    if suffix in _SOUNDFILE_EXTENSIONS:
        try:
            audio, fs = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
            return normalize(audio, fs)
        except sf.LibsndfileError:
            pass                      # extensión engañosa: se intenta con FFmpeg
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("upload" + suffix)
        path.write_bytes(data)
        return normalize(*_decode_ffmpeg(path))


def save_wav(path: str | Path, x: np.ndarray, fs: int = config.SAMPLE_RATE) -> None:
    """Guarda el WAV normalizado (PCM 16 bits): referencia de tamaño para RNF2."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(x, -1.0, 1.0), fs, subtype=config.WAV_SUBTYPE)
