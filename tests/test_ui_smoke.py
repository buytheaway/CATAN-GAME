import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from app.config import GameConfig
from app.main_menu import MainMenuWindow


def test_ui_smoke_boot_and_start():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainMenuWindow()
    w.show()

    cfg = GameConfig()
    w._launch_game(cfg)
    assert w._game_window is not None

    w._game_window.close()
    w.close()
    app.processEvents()
