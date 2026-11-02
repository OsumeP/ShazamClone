"""Pruebas de campo con micrófono real (Fase 8, tarea 8.2).

Graba varios intentos de una canción conocida en una condición dada, los
reconoce, guarda cada grabación y agrega una fila por intento a un CSV. No es
interactivo, así que funciona con `! comando` desde Claude Code.

Uso (desde backend/):
    # 5 intentos de 10 s con "Sunset Lover" sonando, en un café
    python -m scripts.field_test --expected "Sunset Lover" --condition cafe --trials 5

    # Resumen por condición de todo lo registrado
    python -m scripts.field_test --summary

    # Re-evaluar las grabaciones guardadas con la BD/parámetros actuales
    python -m scripts.field_test --replay

Salidas: evaluation/results/fase8_campo.csv y data/campo/*.wav
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from db.database import FingerprintDB
from fingerprint import config
from fingerprint.audio_io import load_audio, resample, save_wav
from fingerprint.matcher import recognize
from scripts import console
from scripts.record_and_recognize import level_report, record

FS = config.SAMPLE_RATE
CSV_PATH = config.REPO_ROOT / "evaluation" / "results" / "fase8_campo.csv"
WAV_DIR = config.DATA_DIR / "campo"
FIELDS = [
    "fecha", "condicion", "esperada", "reconocida", "correcta", "esperada_top1", "score",
    "score_2", "score_esperada", "nivel_dbfs", "pico", "latencia_ms", "dispositivo_fs", "wav",
]


def find_expected(db: FingerprintDB, text: str) -> dict:
    """Canción de la BD cuyo "artista - título" contiene `text` (sin mayúsculas)."""
    songs = [dict(r) for r in db.list_songs()]
    hits = [s for s in songs if text.lower() in f"{s['artist']} - {s['title']}".lower()]
    if len(hits) != 1:
        options = "\n  ".join(f"{s['artist']} - {s['title']}" for s in (hits or songs))
        raise SystemExit(f"'{text}' coincide con {len(hits)} canciones. Opciones:\n  {options}")
    return hits[0]


def evaluate(db: FingerprintDB, x: np.ndarray, expected: dict) -> dict:
    t0 = time.perf_counter()
    r = recognize(x, db)
    latency = time.perf_counter() - t0
    by_id = {c.song_id: c for c in r.candidates}
    return {
        "reconocida": f"{r.song['artist']} - {r.song['title']}" if r.recognized else "",
        "correcta": bool(r.recognized and r.song["id"] == expected["id"]),
        "esperada_top1": bool(r.best and r.best.song_id == expected["id"]),
        "score": r.best.score if r.best else 0,
        "score_2": r.candidates[1].score if len(r.candidates) > 1 else 0,
        "score_esperada": by_id[expected["id"]].score if expected["id"] in by_id else 0,
        "latencia_ms": round(1000 * latency),
    }


def run_trials(args) -> None:
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists()
    with FingerprintDB(args.db) as db, open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        expected = find_expected(db, args.expected)
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        print(f"Esperada: {expected['artist']} - {expected['title']} | condición: {args.condition} | {args.trials} intentos de {args.duration:g} s")
        for i in range(1, args.trials + 1):
            if i > 1:
                time.sleep(args.gap)
            print(f"\n[{i}/{args.trials}] ● grabando…")
            raw, fs, _ = record(args.duration, args.device, exclusive=False)
            x = np.clip(resample(raw, fs, FS), -1.0, 1.0)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            wav = WAV_DIR / f"{stamp}_{args.condition}_{i}.wav"
            save_wav(wav, x)
            res = evaluate(db, x, expected)
            level = 10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-20)
            row = {
                "fecha": stamp, "condicion": args.condition,
                "esperada": f"{expected['artist']} - {expected['title']}", **res,
                "nivel_dbfs": round(level, 1), "pico": round(float(np.abs(x).max()), 3),
                "dispositivo_fs": fs, "wav": wav.relative_to(config.REPO_ROOT).as_posix(),
            }
            writer.writerow(row)
            f.flush()
            mark = "✔" if res["correcta"] else "✘"
            print(
                f"   {mark} {res['reconocida'] or 'no reconocida'} | score {res['score']} "
                f"(esperada {res['score_esperada']}, 2.º {res['score_2']}) | {level_report(x)} | {res['latencia_ms']} ms"
            )
    summary()


def summary() -> None:
    if not CSV_PATH.exists():
        print("Todavía no hay pruebas de campo registradas.")
        return
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"\nResumen ({CSV_PATH.relative_to(config.REPO_ROOT).as_posix()}, {len(rows)} intentos)")
    print(f"{'condición':<14} {'n':>3} {'acierto':>8} {'top-1':>7} {'score med':>10} {'nivel med':>10} {'lat. máx':>9} {'falsos +':>9}")
    for cond in sorted({r["condicion"] for r in rows}):
        sel = [r for r in rows if r["condicion"] == cond]
        ok = [r["correcta"] == "True" for r in sel]
        top1 = [r["esperada_top1"] == "True" for r in sel]
        wrong = sum(1 for r in sel if r["reconocida"] and r["correcta"] != "True")
        print(
            f"{cond:<14} {len(sel):>3} {100 * np.mean(ok):7.0f}% {100 * np.mean(top1):6.0f}% "
            f"{np.median([int(r['score_esperada']) for r in sel]):>10.0f} "
            f"{np.median([float(r['nivel_dbfs']) for r in sel]):>9.1f}  "
            f"{max(int(r['latencia_ms']) for r in sel):>7} ms {wrong:>9}"
        )


def replay(db_path: Path) -> None:
    """Vuelve a reconocer las grabaciones guardadas (banco de pruebas real)."""
    if not CSV_PATH.exists():
        print("No hay grabaciones registradas.")
        return
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    changed = 0
    with FingerprintDB(db_path) as db:
        print(f"{'grabación':<44} {'antes':>12} {'ahora':>12}")
        for r in rows:
            path = config.REPO_ROOT / r["wav"]
            if not path.exists():
                continue
            expected = find_expected(db, r["esperada"])
            now = evaluate(db, load_audio(path), expected)
            before = f"{'✔' if r['correcta'] == 'True' else '✘'} {r['score_esperada']:>4}"
            after = f"{'✔' if now['correcta'] else '✘'} {now['score_esperada']:>4}"
            changed += before != after
            print(f"{Path(r['wav']).name[:44]:<44} {before:>12} {after:>12}")
    print(f"\n{changed} de {len(rows)} grabaciones cambiaron (✔/✘ y score de la canción esperada)")


def main() -> None:
    console.setup()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expected", help="parte del 'artista - título' de la canción que suena")
    parser.add_argument("--condition", default="silencio", help="etiqueta del entorno: silencio, cafe, calle, …")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--gap", type=float, default=2.0, help="pausa entre intentos (s)")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()

    if args.summary:
        summary()
    elif args.replay:
        replay(args.db)
    elif args.expected:
        run_trials(args)
    else:
        parser.error("indica --expected, --summary o --replay")


if __name__ == "__main__":
    main()
