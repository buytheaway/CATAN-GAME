from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtWidgets

from app.config import GameConfig
from app.theme import apply_theme, apply_ui_scale


def start_game(config: GameConfig, on_back_to_menu: Optional[Callable[[], None]] = None):
    if config.expansion != "base":
        QtWidgets.QMessageBox.information(None, "Not implemented", "Selected expansion is not implemented yet.")
        return None

    app = QtWidgets.QApplication.instance()
    if app:
        apply_theme(app, config.theme)
        apply_ui_scale(app, config.ui_scale)

    from app import ui_v6

    w = ui_v6.MainWindow(config=config, on_back_to_menu=on_back_to_menu)
    if config.fullscreen:
        w.showFullScreen()
    else:
        w.show()
    return w
