from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtWebSockets


class NetClient(QtCore.QObject):
    connected = QtCore.Signal()
    disconnected = QtCore.Signal()
    error = QtCore.Signal(str)
    room_state_received = QtCore.Signal(dict)
    match_state_received = QtCore.Signal(dict)
    server_error_received = QtCore.Signal(dict)
    seq_state_received = QtCore.Signal(int)
    cmd_ack_received = QtCore.Signal(dict)
    out_of_order_received = QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        self._ws = QtWebSockets.QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

        self._url = None
        self._name = None
        self._room_code = None
        self._reconnect_token = None
        self._last_seq_applied = 0
        self._pending_cmds: Dict[str, Dict[str, Any]] = {}
        self._reconnect_ms = 1000
        self._reconnect_timer = QtCore.QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._reconnect)

    def connect(self, url: str, name: str):
        self._url = url
        self._name = name
        self._ws.open(QtCore.QUrl(url))

    def _reconnect(self):
        if not self._url or not self._name:
            return
        self._ws.open(QtCore.QUrl(self._url))

    def _on_connected(self):
        self._reconnect_ms = 1000
        self.connected.emit()
        if self._name:
            self.send({"type": "hello", "version": 1, "name": self._name})
        if self._room_code:
            if self._reconnect_token:
                self.send({
                    "type": "reconnect",
                    "room_code": self._room_code,
                    "reconnect_token": self._reconnect_token,
                })
            else:
                self.send({"type": "join_room", "room_code": self._room_code, "name": self._name})

    def _on_disconnected(self):
        self.disconnected.emit()
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start(self._reconnect_ms)
            self._reconnect_ms = min(self._reconnect_ms * 2, 30000)

    def _on_error(self, err):
        self.error.emit(str(err))

    def _on_message(self, msg: str):
        try:
            data = json.loads(msg)
        except Exception:
            self.error.emit("Invalid JSON from server")
            return
        mtype = data.get("type")
        if mtype == "room_state":
            self._room_code = data.get("room_code")
            self.room_state_received.emit(data)
        elif mtype == "reconnect_token":
            self._room_code = data.get("room_code")
            self._reconnect_token = data.get("reconnect_token")
            self._last_seq_applied = int(data.get("last_seq_applied", self._last_seq_applied))
            self.seq_state_received.emit(self._last_seq_applied)
            self._resend_pending()
        elif mtype == "cmd_ack":
            cmd_id = data.get("cmd_id")
            if isinstance(cmd_id, str):
                self._pending_cmds.pop(cmd_id, None)
            self._last_seq_applied = int(data.get("last_seq_applied", self._last_seq_applied))
            self.seq_state_received.emit(self._last_seq_applied)
            self.cmd_ack_received.emit(data)
        elif mtype == "match_state":
            self.match_state_received.emit(data)
        elif mtype == "error":
            if data.get("code") == "out_of_order":
                expected = data.get("detail", {}).get("expected_seq")
                if isinstance(expected, int):
                    self.out_of_order_received.emit(expected)
            self.server_error_received.emit(data)
        else:
            # ignore unknown
            pass

    def send(self, obj: Dict[str, Any]):
        try:
            self._ws.sendTextMessage(json.dumps(obj))
        except Exception as exc:
            self.error.emit(str(exc))

    def create_room(self, name: str, max_players: int = 4):
        self._reconnect_token = None
        self.send({
            "type": "create_room",
            "name": name,
            "max_players": int(max_players),
            "ruleset": {"base": True, "max_players": int(max_players)},
        })

    def join_room(self, room_code: str, name: str):
        self._room_code = room_code
        self._reconnect_token = None
        self.send({
            "type": "join_room",
            "room_code": room_code,
            "name": name,
        })

    def leave_room(self):
        self.send({"type": "leave_room"})

    def start_match(self):
        self.send({"type": "start_match"})

    def rematch(self):
        self.send({"type": "rematch"})

    def set_map(self, map_id: Optional[str] = None, map_data: Optional[Dict[str, Any]] = None):
        payload: Dict[str, Any] = {"type": "set_map"}
        if map_id:
            payload["map_id"] = str(map_id)
        if map_data is not None:
            payload["map_data"] = map_data
        self.send(payload)

    def send_cmd(self, match_id: int, seq: int, cmd_obj: Dict[str, Any], cmd_id: Optional[str] = None):
        if not cmd_id:
            cmd_id = uuid.uuid4().hex
        msg = {
            "type": "cmd",
            "match_id": int(match_id),
            "seq": int(seq),
            "cmd_id": str(cmd_id),
            "cmd": cmd_obj,
        }
        if self._room_code:
            msg["room_code"] = self._room_code
        self._pending_cmds[str(cmd_id)] = {
            "match_id": int(match_id),
            "seq": int(seq),
            "cmd_id": str(cmd_id),
            "cmd": cmd_obj,
            "room_code": self._room_code,
        }
        self.send(msg)
        return str(cmd_id)

    def _resend_pending(self):
        if not self._pending_cmds:
            return
        entries = sorted(self._pending_cmds.values(), key=lambda x: int(x.get("seq", 0)))
        for item in entries:
            seq = int(item.get("seq", 0))
            cmd_id = str(item.get("cmd_id"))
            if seq <= self._last_seq_applied:
                self._pending_cmds.pop(cmd_id, None)
                continue
            msg = {
                "type": "cmd",
                "match_id": int(item.get("match_id", 0)),
                "seq": seq,
                "cmd_id": cmd_id,
                "cmd": item.get("cmd", {}),
            }
            room_code = item.get("room_code")
            if room_code:
                msg["room_code"] = room_code
            self.send(msg)
