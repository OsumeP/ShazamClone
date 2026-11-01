"""Graba una ráfaga del micrófono y la reconoce (RF4, Proceso 5.2 completo).

Uso (desde backend/):
    python -m scripts.record_and_recognize [--duration 10] [--device N] [--save grabacion.wav]
    python -m scripts.record_and_recognize --list-devices

Antes de usarlo, desactivar las "mejoras de audio" del micrófono en Windows
(Configuración > Sistema > Sonido > [micrófono] > Mejoras de audio: Desactivado),
o usar --exclusive (WASAPI exclusivo), que salta el procesamiento del sistema.
La supresión de ruido y el control automático de ganancia del sistema alteran
los picos espectrales (acuerdo A2).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from db.database import FingerprintDB
from fingerprint import config
from scripts import console
from fingerprint.audio_io import resample, save_wav
from fingerprint.matcher import recognize

FS = config.SAMPLE_RATE


def wasapi_input(device: int | None) -> int:
    """Índice WASAPI del mismo micrófono. WasapiSettings solo funciona con
    dispositivos de la API WASAPI, pero el dispositivo por defecto suele ser MME
    (que además recorta el nombre a 31 caracteres): se busca por prefijo."""
    hostapis = sd.query_hostapis()
    wasapi = next((i for i, h in enumerate(hostapis) if "WASAPI" in h["name"]), None)
    if wasapi is None:
        raise RuntimeError("WASAPI no está disponible en este equipo; graba sin --exclusive")
    info = sd.query_devices(device, "input")
    if info["hostapi"] == wasapi:
        return info["index"]
    for i, d in enumerate(sd.query_devices()):
        if d["hostapi"] == wasapi and d["max_input_channels"] > 0 and d["name"].startswith(info["name"]):
            return i
    return hostapis[wasapi]["default_input_device"]


def record(duration: float, device: int | None, exclusive: bool) -> tuple[np.ndarray, int, int | None]:
    """Graba y devuelve (mono float32, frecuencia, dispositivo usado).

    Intenta 44.1 kHz mono; si el dispositivo no lo admite (en modo exclusivo
    suele exigir su formato nativo, p. ej. 48 kHz estéreo) prueba la frecuencia
    nativa y 2 canales. El remuestreo y la mezcla a mono se hacen después."""
    extra = None
    if exclusive:
        device = wasapi_input(device)
        extra = sd.WasapiSettings(exclusive=True)
    info = sd.query_devices(device, "input")
    rates = dict.fromkeys([FS, int(info["default_samplerate"])])      # sin repetir, en orden
    channel_options = dict.fromkeys([1, min(2, info["max_input_channels"])])
    last_error = None
    for channels in channel_options:
        for fs in rates:
            try:
                audio = sd.rec(int(duration * fs), samplerate=fs, channels=channels, dtype="float32",
                               device=device, extra_settings=extra)
                sd.wait()
                return audio.mean(axis=1), fs, device
            except sd.PortAudioError as exc:
                last_error = exc
    raise RuntimeError(f"No se pudo grabar del micrófono: {last_error}")


def level_report(x: np.ndarray) -> str:
    rms_db = 10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-20)
    peak = float(np.abs(x).max())
    msg = f"nivel {rms_db:.1f} dBFS, pico {peak:.2f}"
    if peak >= 0.99:
        msg += "  ⚠ saturación: aleja el micrófono o baja el volumen"
    elif rms_db < -55:
        msg += "  ⚠ señal muy débil: acerca el micrófono o sube el volumen"
    return msg


def main() -> None:
    console.setup()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=float, default=10.0, help="segundos a grabar (RF4: 5–10)")
    parser.add_argument("--device", type=int, default=None, help="índice del dispositivo de entrada")
    parser.add_argument("--exclusive", action="store_true", help="WASAPI exclusivo (salta el procesamiento de Windows)")
    parser.add_argument("--save", type=Path, default=None, help="guardar la grabación normalizada como WAV")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    name = sd.query_devices(args.device, "input")["name"]
    print(f"Micrófono: {name}")
    for i in (3, 2, 1):
        print(f"  grabando en {i}…", end="\r")
        time.sleep(1)
    print(f"● Grabando {args.duration:g} s…      ")
    raw, fs, used = record(args.duration, args.device, args.exclusive)
    t_end = time.perf_counter()                     # fin de la grabación (acuerdo A3)

    x = np.clip(resample(raw, fs, FS), -1.0, 1.0)
    api = sd.query_hostapis(sd.query_devices(used, "input")["hostapi"])["name"]
    print(f"Grabación: {len(x) / FS:.1f} s a {fs} Hz{' → 44 100 Hz' if fs != FS else ''} "
          f"({api}{', exclusivo' if args.exclusive else ''}), {level_report(x)}")

    with FingerprintDB(args.db) as db:
        r = recognize(x, db)
        latency = time.perf_counter() - t_end
        if r.recognized:
            s = r.song
            print(f"\n>> {s['artist'] or '?'} — {s['title']}")
            print(f"   puntuación {r.best.score}, en {r.best.offset_s:.1f} s de la canción")
        else:
            print("\n>> No reconocida")
            if r.best:
                row = db.get_song(r.best.song_id)
                print(f"   mejor candidato: {row['artist']} — {row['title']} (puntuación {r.best.score}, umbral {config.MATCH_MIN_SCORE})")
    print(f"   latencia desde el fin de la grabación: {latency * 1000:.0f} ms ({r.n_query_hashes} hashes)")

    if args.save:
        save_wav(args.save, x)
        print(f"Grabación guardada en {args.save}")


if __name__ == "__main__":
    main()
