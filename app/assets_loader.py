from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

from PySide6 import QtCore, QtGui, QtSvg
from app.resource_path import resource_path


def _base_dir() -> Path:
    return resource_path("app")


def asset_path(rel: str) -> Path:
    return _base_dir() / "assets" / rel


def load_svg(rel: str) -> QtSvg.QSvgRenderer:
    path = asset_path(rel)
    if not path.exists():
        return QtSvg.QSvgRenderer()
    return QtSvg.QSvgRenderer(str(path))


def load_pixmap(rel: str, size: Optional[Union[int, Tuple[int, int]]] = None) -> QtGui.QPixmap:
    path = asset_path(rel)
    pm = QtGui.QPixmap(str(path)) if path.exists() else QtGui.QPixmap()
    if size:
        if isinstance(size, (tuple, list)):
            w, h = size
        else:
            w = h = int(size)
        pm = pm.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    return pm
