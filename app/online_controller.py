from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6 import QtCore, QtGui

from app import ui_v6
from app.net_client import NetClient


PLAYER_COLORS = [
    "#ef4444",
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#a855f7",
    "#14b8a6",
]


class OnlineGameController(QtCore.QObject):
    def __init__(self, net: NetClient, window: ui_v6.MainWindow, you_pid: int):
        super().__init__()
        self.net = net
        self.window = window
        self.you_pid = int(you_pid)
        self.seq = 0
        self.match_id = 0
        self.room_code = None
        self.current_state: Optional[Dict[str, Any]] = None

        self.net.match_state_received.connect(self._on_match_state)
        self.net.room_state_received.connect(self._on_room_state)

        self.window.set_online(self, self.you_pid)

    def _on_room_state(self, data: Dict[str, Any]):
        self.room_code = data.get("room_code")

    def _on_match_state(self, data: Dict[str, Any]):
        self.match_id = int(data.get("match_id", 0))
        self.current_state = data.get("state") or {}
        seed = int(data.get("seed", 0))
        self.apply_snapshot(self.current_state, seed=seed)

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def _send_cmd(self, cmd: Dict[str, Any]):
        self.net.send_cmd(self.match_id, self._next_seq(), cmd)

    def cmd_place_settlement(self, vid: int, setup: bool):
        self._send_cmd({"type": "place_settlement", "vid": int(vid), "setup": bool(setup)})

    def cmd_place_road(self, eid, setup: bool):
        a, b = eid
        self._send_cmd({"type": "place_road", "eid": [int(a), int(b)], "setup": bool(setup)})

    def cmd_upgrade_city(self, vid: int):
        self._send_cmd({"type": "upgrade_city", "vid": int(vid)})

    def cmd_roll(self):
        if not self.current_state:
            return
        if self.current_state.get("turn") != self.you_pid:
            return
        if self.current_state.get("phase") != "main":
            return
        if self.current_state.get("rolled"):
            return
        self._send_cmd({"type": "roll"})

    def cmd_move_robber(self, tile: int):
        self._send_cmd({"type": "move_robber", "tile": int(tile)})

    def cmd_end_turn(self):
        if not self.current_state:
            return
        if self.current_state.get("turn") != self.you_pid:
            return
        if self.current_state.get("pending_action") is not None:
            return
        self._send_cmd({"type": "end_turn"})

    def rematch(self):
        self.net.rematch()

    def apply_snapshot(self, state: Dict[str, Any], seed: int = 0):
        size = float(state.get("size", 58.0))
        g = ui_v6.Game(seed=seed, size=size)

        g.tiles = []
        for t in state.get("tiles", []):
            center = QtCore.QPointF(float(t["center"][0]), float(t["center"][1]))
            g.tiles.append(ui_v6.HexTile(q=int(t["q"]), r=int(t["r"]), terrain=t["terrain"], number=t.get("number"), center=center))

        g.vertices = {int(k): QtCore.QPointF(v[0], v[1]) for k, v in state.get("vertices", {}).items()}
        g.vertex_adj_hexes = {int(k): list(v) for k, v in state.get("vertex_adj_hexes", {}).items()}
        g.edges = set((int(a), int(b)) for a, b in state.get("edges", []))
        g.edge_adj_hexes = {self._edge_key(k): list(v) for k, v in state.get("edge_adj_hexes", {}).items()}
        g.ports = [((int(p[0][0]), int(p[0][1])), p[1]) for p in state.get("ports", [])]

        g.players = []
        for p in state.get("players", []):
            pid = int(p["pid"])
            color = QtGui.QColor(PLAYER_COLORS[pid % len(PLAYER_COLORS)])
            pl = ui_v6.Player(p.get("name", f"P{pid+1}"), color)
            pl.vp = int(p.get("vp", 0))
            pl.res = {r: int(p.get("res", {}).get(r, 0)) for r in ui_v6.RESOURCES}
            pl.knights_played = int(p.get("knights_played", 0))
            g.players.append(pl)

        g.bank = {r: int(state.get("bank", {}).get(r, 0)) for r in ui_v6.RESOURCES}
        g.occupied_v = {int(k): (int(v[0]), int(v[1])) for k, v in state.get("occupied_v", {}).items()}
        g.occupied_e = {self._edge_key(k): int(v) for k, v in state.get("occupied_e", {}).items()}

        g.turn = int(state.get("turn", 0))
        g.phase = state.get("phase", "setup")
        g.rolled = bool(state.get("rolled", False))
        g.setup_order = [int(x) for x in state.get("setup_order", [])]
        g.setup_idx = int(state.get("setup_idx", 0))
        g.setup_need = state.get("setup_need", "settlement")
        g.setup_anchor_vid = state.get("setup_anchor_vid", None)
        g.last_roll = state.get("last_roll", None)

        g.robber_tile = int(state.get("robber_tile", 0))
        g.pending_action = state.get("pending_action", None)
        g.pending_pid = state.get("pending_pid", None)
        g.pending_victims = list(state.get("pending_victims", []))

        g.longest_road_owner = state.get("longest_road_owner", None)
        g.longest_road_len = int(state.get("longest_road_len", 0))
        g.largest_army_pid = state.get("largest_army_owner", None)
        g.largest_army_size = int(state.get("largest_army_size", 0))
        g.game_over = bool(state.get("game_over", False))
        g.winner_pid = state.get("winner_pid", None)

        self.window.game = g
        self.window._draw_static_board()
        self.window._refresh_all_dynamic()
        self.window._sync_ui()

    @staticmethod
    def _edge_key(k):
        if isinstance(k, (list, tuple)):
            a, b = k
            return (int(a), int(b)) if int(a) < int(b) else (int(b), int(a))
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            a = int(a); b = int(b)
            return (a, b) if a < b else (b, a)
        return (0, 0)
