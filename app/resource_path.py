from __future__ import annotations

import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / rel
