import numpy as np
import pytest

from fingerprint import config
from fingerprint.hashing import (
    fingerprint_signal,
    fingerprint_size_bytes,
    generate_hashes,
    pack_hash,
    unpack_hash,
)
from fingerprint.peaks import find_peaks
from fingerprint.spectrogram import frequency_axis, spectrogram_db

FS = config.SAMPLE_RATE
HOP = config.HOP


def synthetic_music(seconds=20.0, seed=0):
    """Secuencia de 'acordes' aleatorios de 3 notas (0.25 s c/u) + ruido leve."""
    rng = np.random.default_rng(seed)
    note_len = FS // 4
    t = np.arange(note_len) / FS
    envelope = np.exp(-3 * t)
    chunks = []
    for _ in range(int(seconds * 4)):
        freqs = rng.uniform(100, 4000, size=3)
        chord = sum(np.sin(2 * np.pi * f * t) for f in freqs) * envelope / 3
        chunks.append(chord)
    x = np.concatenate(chunks)
    x += 0.003 * rng.standard_normal(len(x))
    return x.astype(np.float32)


@pytest.fixture(scope="module")
def music():
    return synthetic_music()


def test_pack_unpack_ida_y_vuelta():
    f1 = np.array([0, 5, 1023])
    f2 = np.array([1023, 7, 0])
    dt = np.array([1, 63, 4095])
    h = pack_hash(f1, f2, dt)
    assert h.dtype == np.uint32
    for a, b in zip(unpack_hash(h), (f1, f2, dt)):
        assert np.array_equal(a, b)


def test_tono_puro_picos_en_su_bin_y_son_los_mas_fuertes():
    k = 93                                         # ≈ 1001 Hz, bin exacto
    x = np.sin(2 * np.pi * (k * FS / config.N_FFT) * np.arange(FS * 3) / FS)
    x += 1e-4 * np.random.default_rng(0).standard_normal(len(x))
    S_db = spectrogram_db(x.astype(np.float32))
    peaks = find_peaks(S_db)
    on_tone = peaks[:, 1] == k
    # Lejos del tono solo hay ruido: el máximo de 21×21 muestras exponenciales
    # supera la mediana en ~10 dB, así que pueden colarse picos de ruido.
    # Lo que debe cumplirse es que el tono aporte picos y sean los dominantes.
    assert on_tone.sum() >= S_db.shape[1] // config.PEAK_NEIGHBORHOOD_TIME
    amp = S_db[peaks[:, 1], peaks[:, 0]]
    assert amp[on_tone].min() > amp[~on_tone].max() + 40


def test_picos_dentro_de_la_banda_y_sin_filas_en_los_bordes(music):
    peaks = find_peaks(spectrogram_db(music))
    f = frequency_axis()[peaks[:, 1]]
    assert f.min() >= config.PEAK_FMIN_HZ and f.max() <= config.PEAK_FMAX_HZ
    # el último bin de la banda no debe acumular picos artificiales
    k_hi = np.searchsorted(frequency_axis(), config.PEAK_FMAX_HZ, side="right") - 1
    assert np.mean(peaks[:, 1] == k_hi) < 0.05


def test_picos_invariantes_a_la_ganancia(music):
    p1 = find_peaks(spectrogram_db(music))
    p2 = find_peaks(spectrogram_db(music * 0.1))   # −20 dB
    assert np.array_equal(p1, p2)


def test_hashes_respetan_zona_objetivo_y_fan_out(music):
    peaks = find_peaks(spectrogram_db(music))
    hashes, offsets = generate_hashes(peaks)
    _, _, dt = unpack_hash(hashes)
    assert dt.min() >= config.TARGET_DT_MIN and dt.max() <= config.TARGET_DT_MAX
    assert len(hashes) <= len(peaks) * config.FAN_OUT
    assert set(offsets.tolist()) <= set(peaks[:, 0].tolist())


def test_huella_determinista(music):
    _, h1, o1 = fingerprint_signal(music)
    _, h2, o2 = fingerprint_signal(music.copy())
    assert np.array_equal(h1, h2) and np.array_equal(o1, o2)


def test_fragmento_comparte_hashes_alineados_con_la_cancion(music):
    """Invariancia temporal: un fragmento que empieza en la ventana s produce
    hashes de la canción con offset desplazado en −s."""
    s = 80                                         # ventanas (~3.7 s)
    clip = music[s * HOP : s * HOP + 8 * FS]
    _, hf, of = fingerprint_signal(music)
    _, hq, oq = fingerprint_signal(clip)
    song = set(zip(hf.tolist(), of.tolist()))
    aligned = sum((h, o + s) in song for h, o in zip(hq.tolist(), oq.tolist()))
    assert aligned / len(hq) > 0.5


def test_huella_menor_al_5_por_ciento_del_wav(music):
    _, hashes, _ = fingerprint_signal(music)
    wav_bytes = len(music) * 2                     # PCM 16 bits mono
    assert fingerprint_size_bytes(len(hashes)) / wav_bytes < 0.05
