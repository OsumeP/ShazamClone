"""Normaliza el corpus: data/raw/* -> data/normalized/*.wav (44.1 kHz, mono, 16 bits).

Uso (desde backend/):
    python -m scripts.normalize_corpus [--force]
"""

from __future__ import annotations

import argparse
import time

from fingerprint import config
from scripts import console
from fingerprint.audio_io import load_audio, save_wav


def main() -> None:
    console.setup()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-normalizar aunque ya exista")
    args = parser.parse_args()

    files = sorted(
        p for p in config.RAW_DIR.iterdir() if p.suffix.lower() in config.AUDIO_EXTENSIONS
    )
    if not files:
        print(f"No hay archivos de audio en {config.RAW_DIR}")
        return

    total_raw = total_wav = 0
    for src in files:
        dst = config.NORMALIZED_DIR / (src.stem + ".wav")
        if dst.exists() and not args.force:
            print(f"[omitido] {src.name}")
        else:
            t0 = time.perf_counter()
            x = load_audio(src)
            save_wav(dst, x)
            dt = time.perf_counter() - t0
            print(f"[ok] {src.name}  ({len(x) / config.SAMPLE_RATE:.1f} s, {dt:.2f} s)")
        total_raw += src.stat().st_size
        total_wav += dst.stat().st_size

    print(
        f"\n{len(files)} archivos | original: {total_raw / 1e6:.1f} MB"
        f" | WAV normalizado: {total_wav / 1e6:.1f} MB"
    )


if __name__ == "__main__":
    main()
