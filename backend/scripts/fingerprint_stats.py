"""Mide densidad y tamaño de la huella de cada canción normalizada (RNF2).

El tamaño de referencia es el WAV normalizado (acuerdo A1):
44.1 kHz, mono, PCM 16 bits, en data/normalized/.

Uso (desde backend/):
    python -m scripts.fingerprint_stats
"""

from __future__ import annotations

import time

from fingerprint import config
from fingerprint.audio_io import load_audio
from fingerprint.hashing import fingerprint_signal, fingerprint_size_bytes


def main() -> None:
    files = sorted(config.NORMALIZED_DIR.glob("*.wav"))
    if not files:
        print("No hay WAV normalizados; ejecuta primero scripts.normalize_corpus")
        return

    print(f"{'canción':<45} {'dur(s)':>7} {'picos/s':>8} {'hash/s':>7} {'huella KB':>10} {'WAV MB':>7} {'%':>6} {'t(s)':>5}")
    tot_fp = tot_wav = tot_dur = tot_peaks = tot_hashes = 0
    worst = 0.0
    for path in files:
        t0 = time.perf_counter()
        x = load_audio(path)
        peaks, hashes, _ = fingerprint_signal(x)
        elapsed = time.perf_counter() - t0

        dur = len(x) / config.SAMPLE_RATE
        fp_bytes = fingerprint_size_bytes(len(hashes))
        wav_bytes = path.stat().st_size
        pct = 100 * fp_bytes / wav_bytes
        worst = max(worst, pct)
        print(
            f"{path.stem[:45]:<45} {dur:7.1f} {len(peaks) / dur:8.1f} {len(hashes) / dur:7.1f}"
            f" {fp_bytes / 1e3:10.1f} {wav_bytes / 1e6:7.1f} {pct:6.2f} {elapsed:5.2f}"
        )
        tot_fp += fp_bytes
        tot_wav += wav_bytes
        tot_dur += dur
        tot_peaks += len(peaks)
        tot_hashes += len(hashes)

    print(
        f"\nTotal: {len(files)} canciones, {tot_dur / 60:.1f} min | "
        f"{tot_peaks / tot_dur:.1f} picos/s | {tot_hashes / tot_dur:.1f} hashes/s | "
        f"huella {tot_fp / 1e6:.2f} MB vs. WAV {tot_wav / 1e6:.1f} MB = {100 * tot_fp / tot_wav:.2f} %"
        f" (peor caso {worst:.2f} %, límite RNF2: 5 %)"
    )


if __name__ == "__main__":
    main()
