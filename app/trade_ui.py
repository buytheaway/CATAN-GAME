from __future__ import annotations

import types
from PySide6 import QtCore, QtGui, QtWidgets

from app.economy_runtime import ensure_economy_api
RES_LIST = ["wood", "brick", "sheep", "wheat", "ore"]


def ensure_trade_api(game):
    """
    Make sure `game` has:
      - bank dict
      - best_trade_rate(pid, res) -> 4/3/2
      - trade_with_bank(pid, give, get, qty)
    Works even if your core class isn't named Game.
    """
    if hasattr(game, "trade_with_bank") and callable(getattr(game, "trade_with_bank")):
        return

    def _get_player_res_dict(self, pid: int) -> dict:
        p = self.players[pid]
        if hasattr(p, "res") and isinstance(p.res, dict):
            return p.res
        if isinstance(p, dict) and isinstance(p.get("res"), dict):
            return p["res"]
        # fallback: try direct fields
        out = {}
        for r in RES_LIST:
            out[r] = int(getattr(p, r, 0)) if hasattr(p, r) else 0
        # if it's all zeros, it is probably wrong structure
        if sum(out.values()) == 0:
            raise RuntimeError("Cannot locate player resources dict (expected player.res or player['res']).")
        return out

    def _ensure_bank(self) -> None:
        if not hasattr(self, "bank") or self.bank is None:
            self.bank = {r: 19 for r in RES_LIST}
            return
        for r in RES_LIST:
            self.bank.setdefault(r, 19)

    def _player_ports(self, pid: int) -> set[str]:
        ports = set()
        if not hasattr(self, "ports") or not self.ports:
            return ports

        owned_vertices = set()
        # common variants
        if hasattr(self, "buildings") and isinstance(self.buildings, dict):
            for vid, data in self.buildings.items():
                try:
                    owner, bkind = data
                except Exception:
                    continue
                if owner == pid and bkind in ("settlement", "city"):
                    owned_vertices.add(vid)
        if hasattr(self, "vertex_owner") and isinstance(self.vertex_owner, dict):
            for vid, owner in self.vertex_owner.items():
                if owner == pid:
                    owned_vertices.add(vid)

        for port in self.ports:
            if isinstance(port, dict):
                kind = port.get("kind")
                a = port.get("a", port.get("v1"))
                b = port.get("b", port.get("v2"))
            else:
                kind = getattr(port, "kind", None)
                a = getattr(port, "a", getattr(port, "v1", None))
                b = getattr(port, "b", getattr(port, "v2", None))

            if a in owned_vertices or b in owned_vertices:
                if kind:
                    ports.add(kind)
        return ports

    def _best_trade_rate(self, pid: int, give_res: str) -> int:
        # default 4:1, 3:1 if generic port, 2:1 if specific port for resource
        rate = 4
        ports = _player_ports(self, pid)
        if "3:1" in ports:
            rate = 3
        if give_res in ports:
            rate = 2
        return rate

    def _trade_with_bank(self, pid: int, give_res: str, get_res: str, get_qty: int = 1) -> int:
        _ensure_bank(self)

        if give_res == get_res:
            raise ValueError("give_res and get_res must be different")
        if give_res not in RES_LIST or get_res not in RES_LIST:
            raise ValueError("Unknown resource")
        if get_qty < 1:
            raise ValueError("get_qty must be >= 1")

        rate = _best_trade_rate(self, pid, give_res)
        give_qty = rate * get_qty

        pres = _get_player_res_dict(self, pid)

        if pres.get(give_res, 0) < give_qty:
            raise ValueError("Not enough resources to trade")
        if self.bank.get(get_res, 0) < get_qty:
            raise ValueError("Bank does not have enough of requested resource")

        pres[give_res] -= give_qty
        pres[get_res] = pres.get(get_res, 0) + get_qty

        self.bank[give_res] = self.bank.get(give_res, 0) + give_qty
        self.bank[get_res] -= get_qty
        return rate

    # attach to instance (works regardless of class name)
    game._get_player_res_dict = types.MethodType(_get_player_res_dict, game)
    game._ensure_bank = types.MethodType(_ensure_bank, game)
    game.player_ports = types.MethodType(_player_ports, game)
    game.best_trade_rate = types.MethodType(_best_trade_rate, game)
    game.trade_with_bank = types.MethodType(_trade_with_bank, game)


class TradeDialog(QtWidgets.QDialog):
    def __init__(self, parent, game, pid: int):
        super().__init__(parent)
        self.setWindowTitle("Trade with Bank")
        self.setModal(True)
        self.game = game
        self.pid = pid
        ensure_economy_api(self.game)
        self._applied = None

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.cb_give = QtWidgets.QComboBox()
        self.cb_give.addItems(RES_LIST)
        self.cb_get = QtWidgets.QComboBox()
        self.cb_get.addItems(RES_LIST)

        self.sp_get_qty = QtWidgets.QSpinBox()
        self.sp_get_qty.setRange(1, 5)
        self.lbl_rate = QtWidgets.QLabel("Rate: 4:1")

        form.addRow("Give:", self.cb_give)
        form.addRow("Get:", self.cb_get)
        form.addRow("Get qty:", self.sp_get_qty)
        form.addRow("", self.lbl_rate)
        layout.addLayout(form)

        self.lbl_info = QtWidgets.QLabel("")
        self.lbl_info.setWordWrap(True)
        layout.addWidget(self.lbl_info)

        btns = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("Trade")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        btns.addStretch(1)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        self.cb_give.currentIndexChanged.connect(self._recalc)
        self.cb_get.currentIndexChanged.connect(self._recalc)
        self.sp_get_qty.valueChanged.connect(self._recalc)

        self._recalc()

    def _recalc(self):
        give = self.cb_give.currentText()
        get = self.cb_get.currentText()
        qty = int(self.sp_get_qty.value())

        if give == get:
            self.lbl_rate.setText("Rate: —")
            self.lbl_info.setText("Give and Get must be different.")
            self.btn_ok.setEnabled(False)
            return

        rate = int(self.game.best_trade_rate(self.pid, give)) if hasattr(self.game, "best_trade_rate") else 4
        give_qty = rate * qty

        pres = self.game._get_player_res_dict(self.pid)
        self.game._ensure_bank()
        bank = self.game.bank

        ok = True
        msg = f"Rate: {rate}:1  |  You give {give_qty} {give} -> get {qty} {get}"

        if pres.get(give, 0) < give_qty:
            ok = False
            msg += f"\nNot enough {give} in hand."
        if bank.get(get, 0) < qty:
            ok = False
            msg += f"\nBank has not enough {get}."

        self.lbl_rate.setText(f"Rate: {rate}:1")
        self.lbl_info.setText(msg)
        self.btn_ok.setEnabled(ok)

    def _on_ok(self):
        give = self.cb_give.currentText()
        get = self.cb_get.currentText()
        qty = int(self.sp_get_qty.value())
        try:
            rate = self.game.trade_with_bank(self.pid, give, get, qty)
            self._applied = (give, get, qty, rate)
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Trade failed", str(e))


def _log(win, msg: str):
    if hasattr(win, "_log") and callable(getattr(win, "_log")):
        win._log(msg)
    elif hasattr(win, "log") and callable(getattr(win, "log")):
        win.log(msg)
    else:
        print(msg)


def _render(win):
    for name in ("_render_all", "render_all", "render", "_render"):
        fn = getattr(win, name, None)
        if callable(fn):
            try:
                fn()
                return
            except Exception:
                pass


def _get_game(win):
    for name in ("game", "_game", "g", "state"):
        obj = getattr(win, name, None)
        if obj is not None and hasattr(obj, "players"):
            return obj
    return None


def _get_pid(win) -> int:
    for name in ("you_pid", "my_pid", "player_id", "pid"):
        v = getattr(win, name, None)
        if isinstance(v, int):
            return v
    return 0


def attach_trade_button(win: QtWidgets.QWidget):
    if getattr(win, "_trade_attached", False):
        return

    game = _get_game(win)
    if game is None:
        _log(win, "[!] Trade attach: cannot find game object on window.")
        return

    ensure_trade_api(game)

    dev_btn = None
    for b in win.findChildren(QtWidgets.QPushButton):
        t = (b.text() or "").strip().lower()
        if t == "dev":
            dev_btn = b
            break
    if dev_btn is None:
        _log(win, "[!] Trade attach: cannot find Dev button (text=='Dev').")
        return

    parent = dev_btn.parentWidget()
    lay = parent.layout() if parent else None
    if lay is None:
        _log(win, "[!] Trade attach: Dev parent has no layout.")
        return

    trade_btn = QtWidgets.QPushButton("Trade")
    trade_btn.setObjectName("btn_trade_bank")

    try:
        idx = lay.indexOf(dev_btn)
        if idx >= 0:
            lay.insertWidget(idx + 1, trade_btn)
        else:
            lay.addWidget(trade_btn)
    except Exception:
        lay.addWidget(trade_btn)

    def _open():
        phase = getattr(game, "phase", "")
        if str(phase).startswith("setup"):
            _log(win, "[!] Trade disabled during setup.")
            return

        pid = _get_pid(win)
        dlg = TradeDialog(win, game, pid)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg._applied:
            give, get, qty, rate = dlg._applied
            _log(win, f"[TRADE] {rate}:1 gave {give} -> got {get} x{qty}")
            _render(win)

    trade_btn.clicked.connect(_open)

    win._trade_attached = True
    _log(win, "[SYS] Trade button attached.")
