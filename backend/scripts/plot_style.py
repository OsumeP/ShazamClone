"""Configuración común de matplotlib para las figuras de los scripts."""

from __future__ import annotations

import matplotlib
from matplotlib import font_manager

# Fuentes de respaldo para títulos con caracteres japoneses/chinos/coreanos
# (p. ej. "東方 - Bad Apple"); se usan solo las que existan en el sistema.
_CJK_FALLBACKS = ["Yu Gothic", "Meiryo", "MS Gothic", "Microsoft YaHei", "Noto Sans CJK JP", "Noto Sans JP"]


def setup() -> None:
    """Backend sin ventana y fuentes con respaldo Unicode."""
    matplotlib.use("Agg")
    available = {f.name for f in font_manager.fontManager.ttflist}
    matplotlib.rcParams["font.family"] = ["DejaVu Sans"] + [f for f in _CJK_FALLBACKS if f in available]
