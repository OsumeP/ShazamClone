import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from fingerprint import config
from fingerprint.audio_io import load_audio, normalize, resample, save_wav, to_mono

FS = config.SAMPLE_RATE


def tone(freq, seconds, fs):
    t = np.arange(int(seconds * fs)) / fs
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def dominant_freq(x, fs):
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.fft.rfftfreq(len(x), 1 / fs)[spectrum.argmax()]


def test_to_mono_promedia_canales():
    stereo = np.stack([np.ones(10), -np.ones(10) * 0.5], axis=1).astype(np.float32)
    assert np.allclose(to_mono(stereo), 0.25)


def test_resample_48k_a_44k_conserva_duracion_y_frecuencia():
    x = tone(1000, 2.0, 48_000)
    y = resample(x, 48_000, FS)
    assert len(y) == 2 * FS
    assert abs(dominant_freq(y, FS) - 1000) < 1.0


def test_normalize_estereo_48k():
    stereo = np.stack([tone(440, 1.0, 48_000)] * 2, axis=1)
    y = normalize(stereo, 48_000)
    assert y.ndim == 1 and y.dtype == np.float32
    assert len(y) == FS
    assert np.abs(y).max() <= 1.0


def test_wav_16_bits_ida_y_vuelta(tmp_path):
    x = tone(440, 1.0, FS)
    path = tmp_path / "tono.wav"
    save_wav(path, x)
    info = sf.info(str(path))
    assert (info.samplerate, info.channels, info.subtype) == (FS, 1, "PCM_16")
    assert np.allclose(load_audio(path), x, atol=1 / 2**15)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no disponible")
def test_mp3_se_decodifica_y_normaliza(tmp_path):
    src = tmp_path / "tono_48k_estereo.wav"
    sf.write(str(src), np.stack([tone(1000, 2.0, 48_000)] * 2, axis=1), 48_000)
    mp3 = tmp_path / "tono.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), str(mp3)], check=True)

    y = load_audio(mp3)
    assert y.ndim == 1
    assert abs(len(y) / FS - 2.0) < 0.1   # el encoder MP3 agrega algo de relleno
    assert abs(dominant_freq(y, FS) - 1000) < 2.0
