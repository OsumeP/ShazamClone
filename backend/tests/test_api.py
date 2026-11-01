import io
import shutil

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from api import main as api_main
from db.database import FingerprintDB
from fingerprint import config
from fingerprint.audio_io import load_audio_bytes
from fingerprint.hashing import fingerprint_signal

from tests.test_fingerprint import synthetic_music

FS = config.SAMPLE_RATE


@pytest.fixture(scope="module")
def songs():
    return {i: synthetic_music(seconds=30, seed=i) for i in range(3)}


@pytest.fixture
def client(tmp_path, songs, monkeypatch):
    db_path = tmp_path / "api.db"
    with FingerprintDB(db_path) as db:
        for i, x in songs.items():
            _, h, o = fingerprint_signal(x)
            db.add_song(title=f"Canción {i}", artist="Sintética", album=None, duration_s=30.0,
                        file_name=f"{i}.wav", file_sha1=str(i), wav_bytes=len(x) * 2, hashes=h, offsets=o)

    def get_test_db():
        db = FingerprintDB(db_path)
        try:
            yield db
        finally:
            db.close()

    # La ingesta escribe en data/raw y data/normalized: se redirigen a tmp
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "NORMALIZED_DIR", tmp_path / "normalized")
    api_main.app.dependency_overrides[api_main.get_db] = get_test_db
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


def wav_bytes(x, fs=FS, channels=1):
    buf = io.BytesIO()
    data = np.stack([x] * channels, axis=1) if channels > 1 else x
    sf.write(buf, data, fs, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_health_y_songs(client):
    health = client.get("/api/health").json()
    assert (health["status"], health["songs"]) == ("ok", 3) and health["hashes"] > 0
    songs = client.get("/api/songs").json()
    assert sorted(s["title"] for s in songs) == ["Canción 0", "Canción 1", "Canción 2"]


def test_reconoce_wav_estereo_48k(client, songs):
    """Simula una grabación del navegador: estéreo a 48 kHz, inicio no alineado."""
    from fingerprint.audio_io import resample

    clip = songs[1][int(7.31 * FS) : int(7.31 * FS) + 6 * FS]
    clip_48k = resample(clip, FS, 48_000)
    res = client.post("/api/recognize", files={"file": ("grabacion.wav", wav_bytes(clip_48k, 48_000, 2), "audio/wav")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recognized"] and body["song"]["title"] == "Canción 1"
    assert abs(body["offset_s"] - 7.31) <= config.HOP / FS
    assert abs(body["query_duration_s"] - 6.0) < 0.01
    assert {"decode", "fingerprint", "lookup", "scoring", "server_total"} <= body["timings_ms"].keys()
    assert body["timings_ms"]["server_total"] < 3000          # RNF3


def test_no_reconocida(client):
    res = client.post("/api/recognize", files={"file": ("x.wav", wav_bytes(synthetic_music(6, seed=42)), "audio/wav")})
    assert res.status_code == 200
    assert res.json()["recognized"] is False and res.json()["song"] is None


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="FFmpeg no disponible (sin él la respuesta es 500)")
def test_archivo_basura_es_400(client):
    # soundfile falla, FFmpeg también → audio inválido, no error del servidor
    assert client.post("/api/recognize", files={"file": ("x.wav", b"no es audio", "audio/wav")}).status_code == 400


def test_errores_de_entrada(client):
    assert client.post("/api/recognize", files={"file": ("x.wav", b"", "audio/wav")}).status_code == 400
    corto = wav_bytes(np.zeros(FS // 2, dtype=np.float32))
    assert client.post("/api/recognize", files={"file": ("x.wav", corto, "audio/wav")}).status_code == 422


def test_sin_ffmpeg_responde_500_con_mensaje(client, monkeypatch):
    from fingerprint import audio_io

    def missing(name):
        raise RuntimeError(f"No se encontró '{name}'.")

    monkeypatch.setattr(audio_io, "find_binary", missing)
    res = client.post("/api/recognize", files={"file": ("x.mp3", b"no es audio", "audio/mpeg")})
    assert res.status_code == 500 and "ffprobe" in res.json()["detail"]


def test_ingesta_y_luego_reconocimiento(client, tmp_path):
    nueva = synthetic_music(seconds=20, seed=7)
    files = {"file": ("Banda X - Tema Y.wav", wav_bytes(nueva), "audio/wav")}
    res = client.post("/api/ingest", files=files)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["song"]["artist"], body["song"]["title"], body["already_existed"]) == ("Banda X", "Tema Y", False)
    assert (tmp_path / "raw" / "Banda X - Tema Y.wav").exists()

    again = client.post("/api/ingest", files={"file": ("Banda X - Tema Y.wav", wav_bytes(nueva), "audio/wav")})
    assert again.json()["already_existed"] is True

    clip = nueva[3 * FS : 9 * FS]
    rec = client.post("/api/recognize", files={"file": ("q.wav", wav_bytes(clip), "audio/wav")}).json()
    assert rec["recognized"] and rec["song"]["title"] == "Tema Y"


def test_ingesta_con_metadatos_del_formulario(client):
    files = {"file": ("archivo_raro.wav", wav_bytes(synthetic_music(10, seed=8)), "audio/wav")}
    body = client.post("/api/ingest", files=files, data={"title": "Título real", "artist": "Artista real"}).json()
    assert (body["song"]["title"], body["song"]["artist"], body["metadata_source"]) == ("Título real", "Artista real", "metadata.json")


def test_ingesta_rechaza_extension_y_conflicto(client):
    assert client.post("/api/ingest", files={"file": ("x.txt", b"abc", "text/plain")}).status_code == 400
    client.post("/api/ingest", files={"file": ("A - B.wav", wav_bytes(synthetic_music(10, seed=9)), "audio/wav")})
    otro = client.post("/api/ingest", files={"file": ("A - B.wav", wav_bytes(synthetic_music(10, seed=10)), "audio/wav")})
    assert otro.status_code == 409


def test_load_audio_bytes_formato_engañoso():
    """Un WAV enviado con extensión .webm se decodifica igual (vía FFmpeg)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg no disponible")
    x = synthetic_music(2, seed=1)
    y = load_audio_bytes(wav_bytes(x), ".webm")
    assert len(y) == len(x)
