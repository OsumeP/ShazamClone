"""API REST del sistema de reconocimiento (Fase 6).

Endpoints:
    GET  /api/health      estado y tamaño de la BD
    GET  /api/songs       canciones indexadas
    POST /api/recognize   reconoce una grabación (multipart: file)
    POST /api/ingest      agrega una canción (multipart: file [+ title, artist, album])

Ejecutar (desde backend/, con el venv activo):
    uvicorn api.main:app --reload
Documentación interactiva: http://127.0.0.1:8000/docs

Variables de entorno:
    SHAZAM_DB_PATH       ruta de la BD (por defecto data/fingerprints.db)
    SHAZAM_CORS_ORIGINS  orígenes permitidos, separados por coma (por defecto el servidor de Vite)
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path

import soundfile as sf
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db.database import FingerprintDB, file_sha1
from db.ingest import ingest_file
from fingerprint import config
from fingerprint.audio_io import find_binary, load_audio_bytes
from fingerprint.matcher import recognize

MAX_RECOGNIZE_BYTES = 20 * 1024 * 1024      # una ráfaga de 10 s en WAV pesa < 4 MB
MAX_INGEST_BYTES = 200 * 1024 * 1024
MIN_QUERY_S, MAX_QUERY_S = 1.0, 30.0         # RF4 pide 5–10 s; se tolera un margen

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _check_ffmpeg()             # avisa al iniciar si FFmpeg no está en el PATH
    yield


app = FastAPI(
    title="ShazamClone — Reconocimiento por huellas acústicas",
    description="STFT → mapa de constelación → hashing combinatorio → coherencia temporal.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "SHAZAM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_db():
    """Una conexión SQLite por petición.

    FastAPI ejecuta esta dependencia (síncrona, con yield) y el endpoint en hilos
    del threadpool que pueden ser distintos, así que se desactiva la verificación
    de hilo de sqlite3. Es seguro: la conexión es exclusiva de la petición y se
    usa de forma secuencial (nunca desde dos hilos a la vez).
    """
    db = FingerprintDB(os.environ.get("SHAZAM_DB_PATH", config.DB_PATH), check_same_thread=False)
    try:
        yield db
    finally:
        db.close()


# --- Modelos de respuesta ----------------------------------------------------

class Song(BaseModel):
    id: int
    title: str
    artist: str | None
    album: str | None
    duration_s: float
    n_hashes: int


class CandidateOut(BaseModel):
    song_id: int
    title: str
    artist: str | None
    score: int
    n_matches: int
    offset_s: float


class RecognizeOut(BaseModel):
    recognized: bool
    song: Song | None
    score: int
    confidence: float           # score del mejor / score del segundo candidato
    offset_s: float | None      # dónde empieza el fragmento dentro de la canción
    query_duration_s: float
    n_query_hashes: int
    candidates: list[CandidateOut]
    timings_ms: dict[str, float]


class IngestOut(BaseModel):
    song: Song
    already_existed: bool
    metadata_source: str


class HealthOut(BaseModel):
    status: str
    songs: int
    hashes: int


def _song(row) -> Song:
    return Song(**{k: row[k] for k in Song.model_fields})


_DECODE_ERRORS = (sf.LibsndfileError, subprocess.CalledProcessError, ValueError, IndexError, KeyError)


def _decode_or_http_error(fn, *args):
    """Traduce los errores de decodificación a respuestas HTTP con mensaje claro."""
    try:
        return fn(*args)
    except _DECODE_ERRORS as exc:
        raise HTTPException(400, f"No se pudo decodificar el audio: {type(exc).__name__}") from exc
    except RuntimeError as exc:                 # FFmpeg no instalado en el servidor
        raise HTTPException(500, str(exc)) from exc


def _check_ffmpeg() -> None:
    try:
        find_binary("ffmpeg")
        find_binary("ffprobe")
    except RuntimeError as exc:
        logging.getLogger("uvicorn.error").warning("%s Solo se podrán procesar WAV/FLAC/OGG.", exc)


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Archivo demasiado grande (máx. {limit // (1024 * 1024)} MB)")
    if not data:
        raise HTTPException(400, "Archivo vacío")
    return data


# --- Endpoints ---------------------------------------------------------------

@app.get("/api/health", response_model=HealthOut)
def health(db: FingerprintDB = Depends(get_db)):
    s = db.stats()
    return HealthOut(status="ok", songs=s["n_songs"], hashes=s["n_hashes"])


@app.get("/api/songs", response_model=list[Song])
def list_songs(db: FingerprintDB = Depends(get_db)):
    return [_song(r) for r in db.list_songs()]


@app.post("/api/recognize", response_model=RecognizeOut)
def recognize_upload(file: UploadFile = File(...), db: FingerprintDB = Depends(get_db)):
    """Reconoce una grabación corta. Se recomienda WAV PCM (sin compresión con
    pérdidas); otros formatos se decodifican con FFmpeg."""
    t0 = time.perf_counter()
    data = _read_limited(file, MAX_RECOGNIZE_BYTES)
    x = _decode_or_http_error(load_audio_bytes, data, Path(file.filename or "").suffix or ".wav")
    t_decoded = time.perf_counter()

    duration = len(x) / config.SAMPLE_RATE
    if not MIN_QUERY_S <= duration <= MAX_QUERY_S:
        raise HTTPException(422, f"La grabación dura {duration:.1f} s; se esperan {MIN_QUERY_S:g}–{MAX_QUERY_S:g} s")

    r = recognize(x, db)
    best = r.best
    second = r.candidates[1].score if len(r.candidates) > 1 else 0
    candidates = []
    for c in r.candidates[:5]:
        row = db.get_song(c.song_id)
        candidates.append(CandidateOut(
            song_id=c.song_id, title=row["title"], artist=row["artist"],
            score=c.score, n_matches=c.n_matches, offset_s=round(c.offset_s, 2),
        ))

    timings = {k.removesuffix("_s"): round(v * 1000, 1) for k, v in r.timings.items()}
    timings["decode"] = round((t_decoded - t0) * 1000, 1)
    timings["server_total"] = round((time.perf_counter() - t0) * 1000, 1)
    return RecognizeOut(
        recognized=r.recognized,
        song=_song(r.song) if r.recognized else None,
        score=best.score if best else 0,
        confidence=round(best.score / max(second, 1), 2) if best else 0.0,
        offset_s=round(best.offset_s, 2) if r.recognized else None,
        query_duration_s=round(duration, 2),
        n_query_hashes=r.n_query_hashes,
        candidates=candidates,
        timings_ms=timings,
    )


@app.post("/api/ingest", response_model=IngestOut)
def ingest_upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    artist: str | None = Form(None),
    album: str | None = Form(None),
    db: FingerprintDB = Depends(get_db),
):
    """Guarda el archivo en data/raw/ y lo indexa. Si se envía `title`, los
    metadatos del formulario tienen prioridad sobre el nombre de archivo."""
    name = Path(file.filename or "").name
    if not name or Path(name).suffix.lower() not in config.AUDIO_EXTENSIONS:
        raise HTTPException(400, f"Formato no soportado; extensiones válidas: {sorted(config.AUDIO_EXTENSIONS)}")
    data = _read_limited(file, MAX_INGEST_BYTES)

    dest = config.RAW_DIR / name
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".upload")
        tmp.write_bytes(data)
        same = file_sha1(tmp) == file_sha1(dest)
        tmp.unlink()
        if not same:
            raise HTTPException(409, f"Ya existe otro archivo llamado '{name}' en data/raw/")
    else:
        dest.write_bytes(data)

    overrides = {name: {"title": title, "artist": artist, "album": album}} if title else None
    try:
        r = _decode_or_http_error(ingest_file, dest, db, overrides)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    return IngestOut(song=_song(db.get_song(r.song_id)), already_existed=r.already_existed,
                     metadata_source=r.metadata_source)
