"""Reconoce un fragmento de un archivo de audio contra la BD (Proceso 5.2 sin micrófono).

Uso (desde backend/):
    python -m scripts.recognize_file RUTA [--start 60] [--duration 10] [--top 5]

La latencia reportada se mide desde que el fragmento está en memoria
(equivalente al fin de la grabación, acuerdo A3).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from db.database import FingerprintDB
from fingerprint import config
from fingerprint.audio_io import load_audio
from fingerprint.matcher import recognize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--start", type=float, default=0.0, help="inicio del fragmento (s)")
    parser.add_argument("--duration", type=float, default=10.0, help="duración del fragmento (s); 0 = completo")
    parser.add_argument("--top", type=int, default=5, help="candidatos a mostrar")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    args = parser.parse_args()

    x = load_audio(args.path)
    i0 = int(args.start * config.SAMPLE_RATE)
    i1 = None if args.duration <= 0 else i0 + int(args.duration * config.SAMPLE_RATE)
    x = x[i0:i1]

    with FingerprintDB(args.db) as db:
        result = recognize(x, db)
        print(f"Fragmento: {len(x) / config.SAMPLE_RATE:.1f} s, {result.n_query_hashes} hashes")
        if result.recognized:
            s = result.song
            print(
                f"\n>> {s['artist'] or '?'} — {s['title']}\n"
                f"   puntuación {result.best.score}, empieza en {result.best.offset_s:.1f} s de la canción"
            )
        else:
            print("\n>> No reconocida")

        print(f"\n{'#':>2} {'canción':<50} {'alineados':>9} {'coincid.':>9} {'inicio(s)':>9}")
        for i, c in enumerate(result.candidates[: args.top], 1):
            row = db.get_song(c.song_id)
            name = f"{row['artist'] or '?'} — {row['title']}"
            print(f"{i:>2} {name[:50]:<50} {c.score:>9} {c.n_matches:>9} {c.offset_s:>9.1f}")

    t = result.timings
    print(
        f"\nLatencia: {t['total_s'] * 1000:.0f} ms (huella {t['fingerprint_s'] * 1000:.0f}, "
        f"búsqueda {t['lookup_s'] * 1000:.0f}, puntuación {t['scoring_s'] * 1000:.0f})"
    )


if __name__ == "__main__":
    main()
