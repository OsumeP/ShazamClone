"""Resolución de metadatos (título, artista, álbum) de archivos propios (acuerdo A4).

Prioridad, de mayor a menor:
  1. metadata.json en la carpeta del archivo (corrección manual explícita):
         {"Archivo.mp3": {"title": "...", "artist": "...", "album": "..."}}
  2. Nombre de archivo con el patrón "Artista - Título".
  3. Tags del archivo leídos con ffprobe.
  4. Nombre de archivo completo como título.

El nombre de archivo va antes que los tags porque, en audio descargado de
plataformas de video, los tags suelen traer el nombre de quien lo subió
("…VEVO", canales de lyrics) y títulos con ruido ("(Lyrics)", "AMV", …).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import config
from .audio_io import find_binary

# Primer guion seguido de espacio: "Shiro SAGISU - Number One - Bankai" ->
# ("Shiro SAGISU", "Number One - Bankai"); también tolera "東方- Bad Apple".
# Un guion sin espacio después ("Jay-Z", "-Kibou no uta-") no separa.
_ARTIST_TITLE = re.compile(r"\s*-\s+")


def parse_filename(stem: str) -> tuple[str | None, str]:
    """'Artista - Título' -> (artista, título). Sin patrón -> (None, stem)."""
    parts = _ARTIST_TITLE.split(stem.strip(), maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0].strip(), parts[1].strip()
    return None, stem.strip()


def read_tags(path: Path) -> dict[str, str]:
    """Tags title/artist/album con ffprobe (claves en minúscula). {} si falla."""
    try:
        result = subprocess.run(
            [find_binary("ffprobe"), "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
            capture_output=True, check=True,
        )
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})
    except (subprocess.CalledProcessError, json.JSONDecodeError, RuntimeError):
        return {}
    tags = {k.lower(): v.strip() for k, v in tags.items() if isinstance(v, str)}
    return {k: tags[k] for k in ("title", "artist", "album") if tags.get(k)}


def load_overrides(folder: Path) -> dict[str, dict[str, str]]:
    """Lee metadata.json de la carpeta (vacío si no existe)."""
    path = folder / config.METADATA_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_metadata(path: str | Path, overrides: dict | None = None) -> dict[str, str | None]:
    """Devuelve {'title', 'artist', 'album', 'source'} según la prioridad del módulo."""
    path = Path(path)
    if overrides is None:
        overrides = load_overrides(path.parent)

    manual = overrides.get(path.name)
    if manual and manual.get("title"):
        return {
            "title": manual["title"],
            "artist": manual.get("artist"),
            "album": manual.get("album"),
            "source": "metadata.json",
        }

    artist, title = parse_filename(path.stem)
    if artist:
        return {"title": title, "artist": artist, "album": None, "source": "filename"}

    tags = read_tags(path)
    if tags.get("title"):
        return {
            "title": tags["title"],
            "artist": tags.get("artist"),
            "album": tags.get("album"),
            "source": "tags",
        }

    return {"title": title, "artist": None, "album": None, "source": "filename"}
