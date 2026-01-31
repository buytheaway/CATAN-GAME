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
    "ui_bg": "#0b2a3a",
    "ui_panel": "#0b2230",
    "ui_panel_border": "#164055",
    "ui_panel_tab": "#0b2433",
    "ui_panel_tab_active": "#133247",
    "ui_panel_outline": "#0f2a3b",
    "ui_panel_input": "#061a25",
    "ui_panel_deep": "#071b28",
    "ui_panel_soft": "#0a3145",
    "ui_panel_action": "#0a2230",
    "ui_panel_action_hover": "#0f2a3b",
    "ui_panel_action_checked": "#0a3145",
    "ui_panel_end": "#113a2c",
    "ui_accent": "#22c55e",
    "ui_text_soft": "#c7d7e6",
    "ui_text_muted": "#93a4b6",
    "ui_text_bright": "#d7eefc",
    "ui_text_dark": "#08131a",
    "ui_shadow": "#03131c",
    "ui_piece_shadow": "#021018",
    "ui_outline_dark": "#0b1220",
    "ui_outline_light": "#22d3ee",
    "ui_outline_hover": "#67e8f9",
    "ui_token_bg": "#f8fafc",
    "ui_token_outline": "#0b1220",
    "ui_token_hot": "#ef4444",
    "ui_action_icon": "#e5f2ff",
    "ui_progress_bg": "#0f2a3b",
    "ui_progress_chunk": "#22c55e",
    "ui_robber_text": "#e5e7eb",
    "dev_overlay_bg_rgba": "rgba(6, 18, 26, 215)",
    "dev_overlay_border_rgba": "rgba(120, 180, 220, 90)",
    "dev_chip_bg_rgba": "rgba(255,255,255,16)",
    "dev_chip_border_rgba": "rgba(255,255,255,18)",
    "dev_count_bg_rgba": "rgba(10, 18, 26, 0.6)",
    "dev_count_border_rgba": "rgba(255,255,255,0.18)",
    "dev_label_text": "#d7eefc",
    "dev_hint_rgba": "rgba(215,238,252,150)",
    "victory_overlay_bg_rgba": "rgba(5, 12, 18, 180)",
    "status_panel_stop1_rgba": "rgba(8,30,42,0.85)",
    "status_panel_stop2_rgba": "rgba(6,24,34,0.85)",
    "status_panel_border_rgba": "rgba(25, 70, 90, 180)",
    "res_chip_border_rgba": "rgba(20, 60, 80, 200)",
    "resources_panel_stop1_rgba": "rgba(8,30,42,0.7)",
    "resources_panel_stop2_rgba": "rgba(6,24,34,0.7)",
    "resources_panel_border_rgba": "rgba(25, 70, 90, 160)",
    "overlay_hex_rgba": "rgba(6, 26, 37, 40)",
    "robber_fill_rgba": "rgba(10, 10, 10, 220)",
    "token_shadow_rgba": "rgba(0, 0, 0, 80)",

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
