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

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
