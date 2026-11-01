"""Salida de consola en UTF-8 para los scripts.

En Windows, cuando la salida va a un pipe (p. ej. `! comando` en Claude Code o
`| Out-File`), Python usa la página de códigos cp1252, que no tiene caracteres
como ●, ⚠, → o los títulos en japonés, y el script falla con UnicodeEncodeError.
"""

from __future__ import annotations

import sys


def setup() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")
