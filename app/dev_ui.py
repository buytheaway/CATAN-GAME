from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from app.runtime_patch import ensure_game_api

RES = ["wood", "brick", "sheep", "wheat", "ore"]
DEV_TYPES = ["knight", "road_building", "year_of_plenty", "monopoly", "victory_point"]

def _log(win, msg: str):
    fn = getattr(win, "_log", None) or getattr(win, "log", None)
    if callable(fn):
        fn(msg)
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

class DevDialog(QtWidgets.QDialog):
    def __init__(self, parent, game, pid: int):
        super().__init__(parent)
        self.setWindowTitle("Development Cards")
        self.setModal(True)
        self.game = game
        ensure_game_api(self.game, override_ports=True, override_trade=True)
        self.pid = pid

        root = QtWidgets.QVBoxLayout(self)

        # Top: Buy section
        buyBox = QtWidgets.QGroupBox("Buy")
        buyLay = QtWidgets.QHBoxLayout(buyBox)
        self.btn_buy = QtWidgets.QPushButton("Buy Dev Card (sheep+wheat+ore)")
        buyLay.addWidget(self.btn_buy)
        root.addWidget(buyBox)

        # Middle: Your cards
        mid = QtWidgets.QGroupBox("Your cards")
        midLay = QtWidgets.QVBoxLayout(mid)

        self.list_cards = QtWidgets.QListWidget()
        self.list_cards.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        midLay.addWidget(self.list_cards)

        # Play controls
        playRow = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("Play selected")
        self.lbl_hint = QtWidgets.QLabel("Select a card to play. (VP cards add points automatically.)")
        self.lbl_hint.setWordWrap(True)
        playRow.addWidget(self.btn_play)
        playRow.addWidget(self.lbl_hint, 1)
        midLay.addLayout(playRow)

        # Extra inputs (for YoP / Monopoly)
        form = QtWidgets.QFormLayout()
        self.cb_res_a = QtWidgets.QComboBox(); self.cb_res_a.addItems(RES)
        self.cb_res_b = QtWidgets.QComboBox(); self.cb_res_b.addItems(RES)
        self.cb_monopoly = QtWidgets.QComboBox(); self.cb_monopoly.addItems(RES)
        self.sp_yop_a = QtWidgets.QSpinBox(); self.sp_yop_a.setRange(0, 2); self.sp_yop_a.setValue(1)
        self.sp_yop_b = QtWidgets.QSpinBox(); self.sp_yop_b.setRange(0, 2); self.sp_yop_b.setValue(1)

        form.addRow("Year of Plenty A:", self._h(self.cb_res_a, self.sp_yop_a))
        form.addRow("Year of Plenty B:", self._h(self.cb_res_b, self.sp_yop_b))
        form.addRow("Monopoly resource:", self.cb_monopoly)
        midLay.addLayout(form)

        root.addWidget(mid)

        # Bottom buttons
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QtWidgets.QPushButton("Close")
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        btn_close.clicked.connect(self.accept)
        self.btn_buy.clicked.connect(self.on_buy)
        self.btn_play.clicked.connect(self.on_play)

        self.refresh()

    def _h(self, *widgets):
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0,0,0,0)
        for x in widgets:
            l.addWidget(x)
        l.addStretch(1)
        return w

    def refresh(self):
        self.list_cards.clear()
        fn = getattr(self.game, "dev_summary", None)
        if callable(fn):
            summary = fn(self.pid)  # dict type->count
        else:
            # fallback: try to read game.dev_hand
            hand = getattr(self.game, "dev_hand", {}).get(self.pid, [])
            summary = {}
            for c in hand:
                summary[c] = summary.get(c, 0) + 1

        for k in DEV_TYPES:
            if summary.get(k, 0) > 0:
                self.list_cards.addItem(f"{k} x{summary[k]}")

        if self.list_cards.count() == 0:
            self.list_cards.addItem("(no dev cards)")

    def _selected_type(self):
        it = self.list_cards.currentItem()
        if not it:
            return None
        t = it.text().split()[0].strip()
        if t in DEV_TYPES:
            return t
        return None

    def on_buy(self):
        try:
            card = self.game.buy_dev(self.pid)
            QtWidgets.QMessageBox.information(self, "Bought", f"You bought: {card}")
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Buy failed", str(e))

    def on_play(self):
        t = self._selected_type()
        if not t:
            return

        try:
            if t == "year_of_plenty":
                a = self.cb_res_a.currentText()
                b = self.cb_res_b.currentText()
                qa = int(self.sp_yop_a.value())
                qb = int(self.sp_yop_b.value())
                self.game.play_dev(self.pid, t, a=a, qa=qa, b=b, qb=qb)
            elif t == "monopoly":
                r = self.cb_monopoly.currentText()
                self.game.play_dev(self.pid, t, r=r)
            else:
                self.game.play_dev(self.pid, t)
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Play failed", str(e))

def attach_dev_dialog(win: QtWidgets.QWidget):
    if getattr(win, "_dev_attached", False):
        return

    game = _get_game(win)
    if game is None:
        _log(win, "[!] Dev attach: cannot find game object on window (expected win.game or win._game).")
        return

    dev_btn = None
    for b in win.findChildren(QtWidgets.QPushButton):
        if (b.text() or "").strip().lower() == "dev":
            dev_btn = b
            break
    if dev_btn is None:
        _log(win, "[!] Dev attach: cannot find Dev button (text=='Dev').")
        return

    # Make Dev open dialog (disconnect any placeholder behavior)
    try:
        dev_btn.clicked.disconnect()
    except Exception:
        pass

    def _open():
        phase = getattr(game, "phase", "")
        if str(phase).startswith("setup"):
            _log(win, "[!] Dev cards disabled during setup.")
            return
        pid = _get_pid(win)
        dlg = DevDialog(win, game, pid)
        dlg.exec()
        _render(win)

    dev_btn.clicked.connect(_open)

    win._dev_attached = True
    _log(win, "[SYS] Dev dialog attached.")