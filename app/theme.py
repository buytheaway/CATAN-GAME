from __future__ import annotations

from pathlib import Path
from typing import Dict

from PySide6 import QtGui, QtWidgets

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#0f172a",
        "panel": "#111827",
        "panel_alt": "#0b1220",
        "text": "#e5e7eb",
        "text_muted": "#9aa4b2",
        "accent": "#22c55e",
        "accent_hover": "#2dd66b",
        "accent_text": "#0b1220",
        "border": "#1f2937",
        "muted": "#334155",
    },
    "light": {
        "bg": "#f7f7fb",
        "panel": "#ffffff",
        "panel_alt": "#f1f5f9",
        "text": "#0f172a",
        "text_muted": "#475569",
        "accent": "#0ea5e9",
        "accent_hover": "#38bdf8",
        "accent_text": "#0b1220",
        "border": "#e2e8f0",
        "muted": "#cbd5e1",
    },
    "midnight": {
        "bg": "#06121c",
        "panel": "#0b1b28",
        "panel_alt": "#07131d",
        "text": "#e5e7eb",
        "text_muted": "#93a4b6",
        "accent": "#22d3ee",
        "accent_hover": "#67e8f9",
        "accent_text": "#06212f",
        "border": "#0f2a3b",
        "muted": "#26465b",
    },
}


def apply_theme(app: QtWidgets.QApplication, theme_name: str) -> None:
    theme = THEMES.get(theme_name, THEMES["midnight"])
    qss_path = Path(__file__).with_name("styles.qss")
    try:
        qss = qss_path.read_text(encoding="utf-8")
    except Exception:
        qss = ""
    try:
        qss = qss.format(**theme)
    except Exception:
        pass
    app.setStyleSheet(qss)

    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(theme["bg"]))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(theme["text"]))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(theme["panel_alt"]))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(theme["text"]))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(theme["panel"]))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(theme["text"]))
    app.setPalette(pal)


def apply_ui_scale(app: QtWidgets.QApplication, scale: float) -> None:
    try:
        scale = float(scale)
    except Exception:
        scale = 1.0
    if scale <= 0:
        scale = 1.0
    base = app.property("_base_font_size")
    if base is None:
        f = app.font()
        base = f.pointSizeF() if f.pointSizeF() > 0 else 10.0
        app.setProperty("_base_font_size", base)
    f = app.font()
    f.setPointSizeF(float(base) * scale)
    app.setFont(f)
