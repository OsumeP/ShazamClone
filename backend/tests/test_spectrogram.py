import numpy as np
from scipy.signal import ShortTimeFFT, get_window

from fingerprint import config
from fingerprint.spectrogram import frequency_axis, spectrogram_db, stft, time_axis

FS = config.SAMPLE_RATE
N = config.N_FFT
R = config.HOP


def test_dimensiones():
    x = np.zeros(FS * 3, dtype=np.float32)
    X = stft(x)
    assert X.shape == (N // 2 + 1, 1 + (len(x) - N) // R)


def test_tono_puro_pico_en_la_frecuencia_esperada():
    k = 93                                  # bin exacto: f = k·fs/N ≈ 1001.3 Hz
    f0 = k * FS / N
    x = np.sin(2 * np.pi * f0 * np.arange(FS * 2) / FS).astype(np.float32)
    S_db = spectrogram_db(x)
    assert np.all(S_db.argmax(axis=0) == k)
    assert np.isclose(frequency_axis()[k], f0)


def test_dos_tonos_dos_picos():
    t = np.arange(FS) / FS
    x = (np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
    column = spectrogram_db(x)[:, 3]
    f = frequency_axis()
    # un máximo por banda (el lóbulo principal de Hann ocupa varios bins vecinos);
    # el pico puede caer en el bin adyacente (resolución Δf ≈ 10.8 Hz)
    low, high = f < 1500, (f >= 1500) & (f < 5000)
    assert abs(f[low][column[low].argmax()] - 440) < FS / N
    assert abs(f[high][column[high].argmax()] - 3000) < FS / N
    # el tono de 3 kHz tiene la mitad de amplitud: 20·log10(0.5) ≈ −6 dB
    assert np.isclose(column[low].max() - column[high].max(), 6.0, atol=1.0)


def test_stft_propia_coincide_con_scipy():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(FS * 2).astype(np.float64)
    ours = stft(x)

    # ShortTimeFFT sin escalado ni relleno: mismas ventanas [mR, mR + N)
    sft = ShortTimeFFT(get_window("hann", N), hop=R, fs=FS, fft_mode="onesided", scale_to=None)
    p0 = sft.lower_border_end[1]            # primera ventana sin relleno a la izquierda
    ref = sft.stft(x, p0=p0, p1=p0 + ours.shape[1])

    # ShortTimeFFT mide la fase respecto al centro de la ventana (desplazamiento
    # de N/2 muestras) -> factor e^{jπk} = (−1)^k respecto a nuestra convención.
    ref = ref * (-1.0) ** np.arange(N // 2 + 1)[:, None]

    assert ref.shape == ours.shape
    rel_err = np.abs(ours - ref).max() / np.abs(ref).max()
    assert rel_err < 1e-5                   # float32 vs. float64


def test_eje_temporal_en_centro_de_ventana():
    t = time_axis(3)
    assert np.allclose(t, (np.arange(3) * R + N / 2) / FS)
