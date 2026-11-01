"""Parámetros globales del sistema de huellas acústicas."""

from pathlib import Path

# --- Rutas ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
NORMALIZED_DIR = DATA_DIR / "normalized"
FIGURES_DIR = REPO_ROOT / "docs" / "figures"

# --- Normalización (RNF1, acuerdo A1) ------------------------------------
SAMPLE_RATE = 44_100        # Hz; frecuencia de Nyquist = 22 050 Hz
WAV_SUBTYPE = "PCM_16"      # WAV normalizado: mono, 16 bits -> 88 200 B/s

# --- STFT (RF2) -----------------------------------------------------------
N_FFT = 4096                # muestras por ventana (~93 ms, Δf ≈ 10.8 Hz)
HOP = 2048                  # salto R entre ventanas (~46 ms)
WINDOW = "hann"
DB_EPS = 1e-10              # ε en S_dB = 10·log10(|X|² + ε)

# --- Mapa de constelación (RF3) ------------------------------------------
# La búsqueda de picos se limita a la banda donde la música concentra su
# energía; fs sigue siendo 44.1 kHz (RNF1), solo se ignoran bins altos.
PEAK_FMIN_HZ = 60.0
PEAK_FMAX_HZ = 5_000.0
PEAK_NEIGHBORHOOD_FREQ = 21     # bins (~226 Hz): tamaño del vecindario del máximo local
PEAK_NEIGHBORHOOD_TIME = 21     # ventanas (~0.98 s)
PEAK_MIN_PROMINENCE_DB = 10.0   # el pico debe superar la mediana del espectrograma en ≥ X dB

# --- Hashing combinatorio (RF3, RNF2) ------------------------------------
FAN_OUT = 10                    # pares por punto ancla
TARGET_DT_MIN = 1               # zona objetivo: Δt en ventanas
TARGET_DT_MAX = 63
HASH_FREQ_BITS = 10             # f1, f2 < 1024 bins (≈ 11 kHz con N = 4096)
HASH_DT_BITS = 12
# Registro almacenado por hash: hash uint32 + offset uint32 + song_id uint16
FINGERPRINT_RECORD_BYTES = 10

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
