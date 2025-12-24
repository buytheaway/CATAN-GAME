from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets

from app.economy_runtime import ensure_economy_api, RES_LIST

def _log(win, msg: str):
    fn = getattr(win, "_log", None)
    if callable(fn):
        fn(msg); return
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

class DevDialog(QtWidgets.QDialog):
    def __init__(self, parent, game, pid: int):
        super().__init__(parent)
        self.setWindowTitle("Development Cards")
        self.setModal(True)
        self.game = game
        self.pid = pid

        ensure_economy_api(self.game)
        self.game.ensure_bank()
        self.game.ensure_dev_deck()

        root = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.lbl_deck = QtWidgets.QLabel("")
        top.addWidget(self.lbl_deck)
        top.addStretch(1)
        self.btn_buy = QtWidgets.QPushButton("Buy Dev Card (sheep+wheat+ore)")
        top.addWidget(self.btn_buy)
        root.addLayout(top)

        self.list = QtWidgets.QListWidget()
        root.addWidget(self.list, 1)

        playRow = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("Play selected")
        self.btn_close = QtWidgets.QPushButton("Close")
        playRow.addStretch(1)
        playRow.addWidget(self.btn_play)
        playRow.addWidget(self.btn_close)
        root.addLayout(playRow)

        self.btn_close.clicked.connect(self.reject)
        self.btn_buy.clicked.connect(self._buy)
        self.btn_play.clicked.connect(self._play)

        self._refresh()

    def _hand(self) -> list:
        # economy_runtime stores hand as player.dev (list) if possible
        p = self.game.players[self.pid]
        if hasattr(p, "dev") and isinstance(p.dev, list): return p.dev
        if isinstance(p, dict) and isinstance(p.get("dev"), list): return p["dev"]
        # fallback
        if not hasattr(p, "dev"):
            try: p.dev = []
            except Exception: return []
        return p.dev

    def _refresh(self):
        self.lbl_deck.setText(f"Deck remaining: {len(getattr(self.game,'dev_deck',[]))}")
        self.list.clear()
        for c in self._hand():
            self.list.addItem(c)

    def _buy(self):
        try:
            c = self.game.buy_dev_card(self.pid)
            QtWidgets.QMessageBox.information(self, "Bought", f"You got: {c}")
            self._refresh()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Buy failed", str(e))

    def _play(self):
        it = self.list.currentItem()
        if not it:
            return
        card = it.text()

        kw = {}
        if card == "year_of_plenty":
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Year of Plenty")
            lay = QtWidgets.QFormLayout(dlg)
            a = QtWidgets.QComboBox(); a.addItems(RES_LIST)
            b = QtWidgets.QComboBox(); b.addItems(RES_LIST)
            lay.addRow("Resource 1:", a)
            lay.addRow("Resource 2:", b)
            btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            lay.addRow(btns)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            if dlg.exec() != QtWidgets.QDialog.Accepted:
                return
            kw["choose"] = [a.currentText(), b.currentText()]

        try:
            res = self.game.play_dev_card(self.pid, card, **kw)
            QtWidgets.QMessageBox.information(self, "Played", res)
            self._refresh()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Play failed", str(e))

def attach_dev_button(win: QtWidgets.QWidget):
    if getattr(win, "_dev_attached", False):
        return
    game = _get_game(win)
    if game is None:
        _log(win, "[!] Dev attach: cannot find game on window.")
        return

    ensure_economy_api(game)

    dev_btn = None
    for b in win.findChildren(QtWidgets.QPushButton):
        t = (b.text() or "").strip().lower()
        if t == "dev":
            dev_btn = b
            break
    if dev_btn is None:
        _log(win, "[!] Dev attach: cannot find Dev button (text=='Dev').")
        return

    try:
        dev_btn.clicked.disconnect()
    except Exception:
        pass

    def _open():
        phase = getattr(game, "phase", "")
        if str(phase).startswith("setup"):
            _log(win, "[!] Dev disabled during setup.")
            return
        pid = _get_pid(win)
        dlg = DevDialog(win, game, pid)
        dlg.exec()
        _render(win)

    dev_btn.clicked.connect(_open)
    win._dev_attached = True
    _log(win, "[SYS] Dev dialog attached.")