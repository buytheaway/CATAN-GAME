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

UI_COLORS: Dict[str, str] = {
    "ui_bg": "#0b63a6",
    "ui_panel": "#f2e7d3",
    "ui_panel_border": "#d5c6a4",
    "ui_panel_tab": "#efe1c8",
    "ui_panel_tab_active": "#e3d2b1",
    "ui_panel_outline": "#c6b48c",
    "ui_panel_input": "#fff7e6",
    "ui_panel_deep": "#0a4f7f",
    "ui_panel_soft": "#ead9bc",
    "ui_panel_action": "#e9d6b8",
    "ui_panel_action_hover": "#e2cfae",
    "ui_panel_action_checked": "#dcc7a1",
    "ui_panel_end": "#c6e6c2",
    "ui_accent": "#23c36b",
    "ui_text_soft": "#5b4b3a",
    "ui_text_muted": "#7a6a57",
    "ui_text_bright": "#2b2319",
    "ui_text_dark": "#1a140f",
    "ui_shadow": "#052538",
    "ui_piece_shadow": "#1f2d38",
    "ui_outline_dark": "#3b2f21",
    "ui_outline_light": "#1aa3d6",
    "ui_outline_hover": "#3ab7e6",
    "ui_token_bg": "#f9f4ea",
    "ui_token_outline": "#3b2f21",
    "ui_token_hot": "#d12f2f",
    "ui_action_icon": "#2b2319",
    "ui_progress_bg": "#d7c8a8",
    "ui_progress_chunk": "#2cc36b",
    "ui_robber_text": "#2b2319",
    "dev_overlay_bg_rgba": "rgba(10, 25, 35, 180)",
    "dev_overlay_border_rgba": "rgba(80, 120, 150, 90)",
    "dev_chip_bg_rgba": "rgba(255,255,255,120)",
    "dev_chip_border_rgba": "rgba(60,40,20,60)",
    "dev_count_bg_rgba": "rgba(30, 20, 10, 0.5)",
    "dev_count_border_rgba": "rgba(60,40,20,0.2)",
    "dev_label_text": "#2b2319",
    "dev_hint_rgba": "rgba(40,30,20,120)",
    "victory_overlay_bg_rgba": "rgba(5, 12, 18, 160)",
    "status_panel_stop1_rgba": "rgba(244, 232, 210, 0.95)",
    "status_panel_stop2_rgba": "rgba(233, 218, 193, 0.95)",
    "status_panel_border_rgba": "rgba(140, 115, 80, 140)",
    "res_chip_border_rgba": "rgba(160, 130, 90, 160)",
    "resources_panel_stop1_rgba": "rgba(244, 232, 210, 0.9)",
    "resources_panel_stop2_rgba": "rgba(233, 218, 193, 0.9)",
    "resources_panel_border_rgba": "rgba(140, 115, 80, 140)",
    "overlay_hex_rgba": "rgba(20, 40, 50, 40)",
    "robber_fill_rgba": "rgba(20, 20, 20, 220)",
    "token_shadow_rgba": "rgba(0, 0, 0, 70)",

    "terrain_forest": "#15803d",
    "terrain_hills": "#f97316",
    "terrain_pasture": "#86efac",
    "terrain_fields": "#facc15",
    "terrain_mountains": "#94a3b8",
    "terrain_desert": "#d6c8a0",
    "terrain_sea": "#0b4a6f",
    "terrain_gold": "#eab308",

    "res_wood": "#16a34a",
    "res_brick": "#f97316",
    "res_sheep": "#22c55e",
    "res_wheat": "#facc15",
    "res_ore": "#94a3b8",
    "res_any": "#0ea5e9",
    "res_default": "#64748b",
}

DEV_CARD_COLORS: Dict[str, tuple[str, str]] = {
    "knight": ("#6d28d9", "#8b5cf6"),
    "victory_point": ("#1d4ed8", "#3b82f6"),
    "road_building": ("#475569", "#94a3b8"),
    "year_of_plenty": ("#15803d", "#22c55e"),
    "monopoly": ("#b45309", "#f59e0b"),
    "default": ("#0f172a", "#334155"),
}

PLAYER_COLORS: list[str] = [
    "#ef4444",
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#a855f7",
    "#14b8a6",
]


def get_ui_palette(theme_name: str = "midnight") -> Dict[str, str]:
    theme = THEMES.get(theme_name, THEMES["midnight"])
    palette = dict(theme)
    palette.update(UI_COLORS)
    return palette


def get_dev_card_colors() -> Dict[str, tuple[str, str]]:
    return dict(DEV_CARD_COLORS)


def get_player_colors() -> list[str]:
    return list(PLAYER_COLORS)


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
