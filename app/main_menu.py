from __future__ import annotations

import sys
from dataclasses import replace

from PySide6 import QtCore, QtGui, QtWidgets

from app.config import GameConfig
from app.game_launcher import start_game
from app.lobby_ui import LobbyWindow
from app.theme import apply_theme, apply_ui_scale


class ModeSelectDialog(QtWidgets.QDialog):
    def __init__(self, parent, config: GameConfig, mode: str):
        super().__init__(parent)
        self.setWindowTitle("Game Setup")
        self.setModal(True)
        self._config = config
        self._mode = mode

        root = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()

        self.cb_expansion = QtWidgets.QComboBox()
        model = QtGui.QStandardItemModel()
        base_item = QtGui.QStandardItem("Base")
        seaf_item = QtGui.QStandardItem("Seafarers (coming soon)")
        seaf_item.setEnabled(False)
        model.appendRow(base_item)
        model.appendRow(seaf_item)
        self.cb_expansion.setModel(model)

        self.cb_map = QtWidgets.QComboBox()
        self.cb_map.addItem("Classic 19")

        self.chk_bot = QtWidgets.QCheckBox("Enable Bot")
        self.chk_bot.setChecked(config.bot_enabled)

        self.sp_difficulty = QtWidgets.QSpinBox()
        self.sp_difficulty.setRange(0, 2)
        self.sp_difficulty.setValue(config.bot_difficulty)

        if mode == "multiplayer":
            self.chk_bot.setEnabled(False)
            self.sp_difficulty.setEnabled(False)

        form.addRow("Expansion:", self.cb_expansion)
        form.addRow("Map:", self.cb_map)
        form.addRow("", self.chk_bot)
        form.addRow("Bot difficulty:", self.sp_difficulty)

        root.addLayout(form)

        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_start)
        root.addLayout(btns)

        self.btn_start.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def config(self) -> GameConfig:
        expansion = "base"
        if self.cb_expansion.currentIndex() == 1:
            expansion = "seafarers"
        return replace(
            self._config,
            mode=self._mode,
            expansion=expansion,
            map_preset="classic_19",
            bot_enabled=self.chk_bot.isChecked(),
            bot_difficulty=int(self.sp_difficulty.value()),
        )


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent, config: GameConfig):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self._config = config

        root = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.cb_theme = QtWidgets.QComboBox()
        self.cb_theme.addItems(["dark", "light", "midnight"])
        self.cb_theme.setCurrentText(config.theme)

        self.sl_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_scale.setRange(90, 120)
        self.sl_scale.setValue(int(config.ui_scale * 100))
        self.lbl_scale = QtWidgets.QLabel(f"{config.ui_scale:.2f}x")
        self.sl_scale.valueChanged.connect(self._on_scale)

        self.chk_fullscreen = QtWidgets.QCheckBox("Fullscreen")
        self.chk_fullscreen.setChecked(config.fullscreen)

        form.addRow("Theme:", self.cb_theme)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.sl_scale, 1)
        row.addWidget(self.lbl_scale)
        form.addRow("UI scale:", row)
        form.addRow("", self.chk_fullscreen)

        root.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        self.btn_apply = QtWidgets.QPushButton("Apply")
        self.btn_close = QtWidgets.QPushButton("Close")
        btns.addStretch(1)
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.btn_apply.clicked.connect(self.accept)
        self.btn_close.clicked.connect(self.reject)

    def _on_scale(self, v: int):
        self.lbl_scale.setText(f"{v/100:.2f}x")

    def config(self) -> GameConfig:
        return replace(
            self._config,
            theme=self.cb_theme.currentText(),
            ui_scale=float(self.sl_scale.value()) / 100.0,
            fullscreen=self.chk_fullscreen.isChecked(),
        )


class LobbyWindow(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Multiplayer Lobby")
        self.setModal(True)
        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(QtWidgets.QLabel("Multiplayer is coming soon."))
        root.addWidget(QtWidgets.QLabel("Host / Join UI will live here."))
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(self.accept)
        root.addWidget(btn)


class MainMenuWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CATAN-GAME")
        self.setMinimumSize(720, 520)
        self.config = GameConfig()
        self._game_window = None

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addStretch(1)

        title = QtWidgets.QLabel("CATAN-GAME")
        f = title.font()
        f.setPointSize(f.pointSize() + 12)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        btns = QtWidgets.QVBoxLayout()
        self.btn_single = QtWidgets.QPushButton("Singleplayer")
        self.btn_multi = QtWidgets.QPushButton("Multiplayer")
        self.btn_settings = QtWidgets.QPushButton("Settings")
        self.btn_exit = QtWidgets.QPushButton("Exit")
        for b in (self.btn_single, self.btn_multi, self.btn_settings, self.btn_exit):
            b.setFixedHeight(44)
            btns.addWidget(b)
        layout.addLayout(btns)
        layout.addStretch(1)

        self.btn_single.clicked.connect(self._on_single)
        self.btn_multi.clicked.connect(self._on_multi)
        self.btn_settings.clicked.connect(self._on_settings)
        self.btn_exit.clicked.connect(self.close)

    def _on_single(self):
        dlg = ModeSelectDialog(self, self.config, "singleplayer")
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        self.config = dlg.config()
        self._launch_game(self.config)

    def _on_multi(self):
        LobbyWindow(self).exec()

    def _on_settings(self):
        dlg = SettingsDialog(self, self.config)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        self.config = dlg.config()
        app = QtWidgets.QApplication.instance()
        if app:
            apply_theme(app, self.config.theme)
            apply_ui_scale(app, self.config.ui_scale)

    def _launch_game(self, config: GameConfig):
        self.hide()
        def back_to_menu():
            if self._game_window:
                self._game_window.close()
            self._game_window = None
            self.show()

        self._game_window = start_game(config, on_back_to_menu=back_to_menu)
        if self._game_window is None:
            self.show()
            return
        self._game_window.destroyed.connect(self._on_game_closed)

    def _on_game_closed(self):
        self._game_window = None
        if not self.isVisible():
            self.show()


def main():
    app = QtWidgets.QApplication(sys.argv)
    cfg = GameConfig()
    apply_theme(app, cfg.theme)
    apply_ui_scale(app, cfg.ui_scale)
    w = MainMenuWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
