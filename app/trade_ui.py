from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from app.runtime_patch import ensure_game_api

RES_LIST = ["wood", "brick", "sheep", "wheat", "ore"]


class TradeDialog(QtWidgets.QDialog):
    def __init__(self, parent, game, pid: int):
        super().__init__(parent)
        self.setWindowTitle("Trade with Bank")
        self.setModal(True)
        self.game = game
        self.pid = pid
        self._applied = None

        # ensure methods exist + override ports/trade logic
        ensure_game_api(self.game, override_ports=True, override_trade=True)

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.cb_give = QtWidgets.QComboBox(); self.cb_give.addItems(RES_LIST)
        self.cb_get  = QtWidgets.QComboBox(); self.cb_get.addItems(RES_LIST)
        self.sp_get_qty = QtWidgets.QSpinBox(); self.sp_get_qty.setRange(1, 5)

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
        btns.addStretch(1); btns.addWidget(self.btn_ok); btns.addWidget(self.btn_cancel)
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

        ports = []
        try:
            ports = sorted(list(self.game.player_ports(self.pid)))
        except Exception:
            ports = []

        rate = 4
        try:
            rate = int(self.game.best_trade_rate(self.pid, give))
        except Exception:
            rate = 4

        give_qty = rate * qty

        # player resources
        pres = self.game._get_player_res_dict(self.pid) if hasattr(self.game, "_get_player_res_dict") else getattr(self.game.players[self.pid], "res", {})
        if not isinstance(pres, dict):
            pres = {}

        bank = getattr(self.game, "bank", None) or {r: 19 for r in RES_LIST}

        ok = True
        msg = f"Ports detected: {ports if ports else 'none'}\nRate: {rate}:1  |  You give {give_qty} {give} -> get {qty} {get}"

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
        win._log(msg); return
    if hasattr(win, "log") and callable(getattr(win, "log")):
        win.log(msg); return
    print(msg)


def _render(win):
    for name in ("_render_all", "render_all", "render", "_render"):
        fn = getattr(win, name, None)
        if callable(fn):
            try:
                fn(); return
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

    dev_btn = win.findChild(QtWidgets.QAbstractButton, "btn_dev_action")
    if dev_btn is None:
        for b in win.findChildren(QtWidgets.QAbstractButton):
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

    trade_btn = win.findChild(QtWidgets.QAbstractButton, "btn_trade_bank")
    if trade_btn is None:
        trade_btn = QtWidgets.QPushButton("Trade")
        trade_btn.setObjectName("btn_trade_bank")

    if trade_btn.parent() is None:
        try:
            idx = lay.indexOf(dev_btn)
            if idx >= 0:
                lay.insertWidget(idx + 1, trade_btn)
            else:
                lay.addWidget(trade_btn)
        except Exception:
            lay.addWidget(trade_btn)

    def _open():
        # always ensure api right before dialog
        ensure_game_api(game, override_ports=True, override_trade=True)

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
