from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.config import GameConfig
from app.net_client import NetClient
from app.online_controller import OnlineGameController
from app import ui_v6


class LobbyWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Multiplayer Lobby")
        self.setModal(True)
        self.resize(520, 420)

        self.net = NetClient()
        self.room_state = None
        self.you_pid: Optional[int] = None
        self._game_window = None
        self._controller = None
        self._pending_action = None

        root = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.ed_url = QtWidgets.QLineEdit("ws://127.0.0.1:8000/ws")
        self.ed_name = QtWidgets.QLineEdit("Player")
        self.ed_room = QtWidgets.QLineEdit("")
        self.sp_players = QtWidgets.QSpinBox()
        self.sp_players.setRange(2, 6)
        self.sp_players.setValue(4)
        form.addRow("Server URL:", self.ed_url)
        form.addRow("Name:", self.ed_name)
        form.addRow("Room code:", self.ed_room)
        form.addRow("Max players:", self.sp_players)
        root.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        self.btn_host = QtWidgets.QPushButton("Host")
        self.btn_join = QtWidgets.QPushButton("Join")
        row.addWidget(self.btn_host)
        row.addWidget(self.btn_join)
        root.addLayout(row)

        self.list_players = QtWidgets.QListWidget()
        root.addWidget(self.list_players, 1)

        row2 = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start Match")
        self.btn_rematch = QtWidgets.QPushButton("Rematch")
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_start.setEnabled(False)
        self.btn_rematch.setEnabled(False)
        row2.addWidget(self.btn_start)
        row2.addWidget(self.btn_rematch)
        row2.addStretch(1)
        row2.addWidget(self.btn_close)
        root.addLayout(row2)

        self.lbl_status = QtWidgets.QLabel("")
        root.addWidget(self.lbl_status)

        self.btn_close.clicked.connect(self.reject)
        self.btn_host.clicked.connect(self._on_host)
        self.btn_join.clicked.connect(self._on_join)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_rematch.clicked.connect(self._on_rematch)

        self.net.connected.connect(self._on_connected)
        self.net.disconnected.connect(self._on_disconnected)
        self.net.room_state_received.connect(self._on_room_state)
        self.net.match_state_received.connect(self._on_match_state)
        self.net.server_error_received.connect(self._on_server_error)

    def _on_connected(self):
        self.lbl_status.setText("Connected")
        if self._pending_action:
            action = self._pending_action
            self._pending_action = None
            if action[0] == "host":
                _, name, max_players = action
                self.net.create_room(name, max_players)
            elif action[0] == "join":
                _, room, name = action
                self.net.join_room(room, name)

    def _on_disconnected(self):
        self.lbl_status.setText("Disconnected (reconnecting...)")

    def _on_server_error(self, err: dict):
        self.lbl_status.setText(f"Error: {err.get('message')}")

    def _on_host(self):
        name = self.ed_name.text().strip() or "Player"
        url = self.ed_url.text().strip()
        self._pending_action = ("host", name, int(self.sp_players.value()))
        self.net.connect(url, name)

    def _on_join(self):
        name = self.ed_name.text().strip() or "Player"
        url = self.ed_url.text().strip()
        room = self.ed_room.text().strip().upper()
        if not room:
            self.lbl_status.setText("Room code required")
            return
        self._pending_action = ("join", room, name)
        self.net.connect(url, name)

    def _on_start(self):
        self.net.start_match()

    def _on_rematch(self):
        self.net.rematch()

    def _on_room_state(self, data: dict):
        self.room_state = data
        self.list_players.clear()
        players = data.get("players", [])
        host_pid = data.get("host_pid")
        name = self.ed_name.text().strip()
        self.you_pid = None
        for p in players:
            label = f"P{p['pid'] + 1}: {p.get('name', '')}"
            if p.get("connected"):
                label += " (online)"
            if p["pid"] == host_pid:
                label += " [host]"
            if p.get("name") == name:
                self.you_pid = p["pid"]
            self.list_players.addItem(label)

        can_start = self.you_pid == host_pid and sum(1 for p in players if p.get("name")) >= 2
        self.btn_start.setEnabled(bool(can_start))
        self.btn_rematch.setEnabled(data.get("status") == "in_match" and self.you_pid == host_pid)
        if data.get("room_code"):
            self.ed_room.setText(data.get("room_code"))

    def _on_match_state(self, data: dict):
        if self._game_window is None:
            cfg = GameConfig(mode="multiplayer", bot_enabled=False)
            self._game_window = ui_v6.MainWindow(config=cfg, on_back_to_menu=self._back_to_lobby)
            self._controller = OnlineGameController(self.net, self._game_window, you_pid=self.you_pid or 0)
            self._game_window.show()
            self.hide()

    def _back_to_lobby(self):
        if self._game_window:
            self._game_window.close()
        self._game_window = None
        self._controller = None
        self.show()
