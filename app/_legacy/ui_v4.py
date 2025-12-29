from __future__ import annotations

import sys
import math
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.catan_core import new_game, Game, TERRAIN_TO_RES, bot_take_turn

BG = "#0b2a3a"
PANEL = "#0f3446"
PANEL2 = "#0c2c3b"
TEXT = "#e8f1f6"
MUTED = "#9fb7c5"
ACCENT = "#2dd4bf"
DANGER = "#ef4444"

RESOURCE_COLORS = {
    "wood": "#2ecc71",
    "brick": "#e67e22",
    "sheep": "#a3e635",
    "wheat": "#facc15",
    "ore": "#94a3b8",
    "desert": "#d6c79b",
}

# ---------- small UI widgets ----------
class DiceWidget(QtWidgets.QWidget):
    clicked = QtCore.Signal()
    def __init__(self, value: int = 1, parent=None):
        super().__init__(parent)
        self.setFixedSize(54, 54)
        self.value = value
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def setValue(self, v: int):
        self.value = max(1, min(6, int(v)))
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        rect = self.rect().adjusted(2,2,-2,-2)
        p.setPen(QtGui.QPen(QtGui.QColor("#000000"), 1))
        p.setBrush(QtGui.QColor("#f3f4f6"))
        p.drawRoundedRect(rect, 10, 10)

        p.setBrush(QtGui.QColor("#111827"))
        p.setPen(QtCore.Qt.NoPen)

        cx = rect.center().x()
        cy = rect.center().y()
        s = 14
        pts = {
            "TL": QtCore.QPointF(cx - s, cy - s),
            "TR": QtCore.QPointF(cx + s, cy - s),
            "ML": QtCore.QPointF(cx - s, cy),
            "MR": QtCore.QPointF(cx + s, cy),
            "BL": QtCore.QPointF(cx - s, cy + s),
            "BR": QtCore.QPointF(cx + s, cy + s),
            "C":  QtCore.QPointF(cx, cy),
        }
        layout = {
            1: ["C"],
            2: ["TL","BR"],
            3: ["TL","C","BR"],
            4: ["TL","TR","BL","BR"],
            5: ["TL","TR","C","BL","BR"],
            6: ["TL","TR","ML","MR","BL","BR"],
        }[self.value]
        for k in layout:
            p.drawEllipse(pts[k], 4.6, 4.6)

class ActionChip(QtWidgets.QPushButton):
    def __init__(self, key: str, title: str, parent=None):
        super().__init__(title, parent)
        self.key = key
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setStyleSheet(
            "QPushButton{background:#062231; color:#e8f1f6; border-radius:12px; padding:10px 14px; font-weight:900;}"
            "QPushButton:checked{background:#2dd4bf; color:#0b1220;}"
        )

class TradeDialog(QtWidgets.QDialog):
    def __init__(self, parent, give_opts, get_opts):
        super().__init__(parent)
        self.setWindowTitle("Trade with bank (4:1)")
        self.setModal(True)
        self.give = QtWidgets.QComboBox()
        self.give.addItems(give_opts)
        self.get = QtWidgets.QComboBox()
        self.get.addItems(get_opts)

        ok = QtWidgets.QPushButton("Trade")
        ok.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        lay = QtWidgets.QFormLayout(self)
        lay.addRow("Give (need 4):", self.give)
        lay.addRow("Get (1):", self.get)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addRow(row)

# ---------- board graphics items ----------
class NodeItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, nid: int, x: float, y: float, r: float, on_click, parent=None):
        super().__init__(-r, -r, 2*r, 2*r, parent)
        self.nid = nid
        self.setPos(x,y)
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self.setZValue(50)
        self._base_pen = QtGui.QPen(QtGui.QColor("#0b1220"), 2)
        self._base_brush = QtGui.QBrush(QtGui.QColor("#0b1220"))
        self._hl_brush = QtGui.QBrush(QtGui.QColor(ACCENT))
        self._hl_pen = QtGui.QPen(QtGui.QColor("#0b1220"), 2)
        self.setPen(self._base_pen)
        self.setBrush(self._base_brush)

    def set_highlight(self, on: bool):
        if on:
            self.setBrush(self._hl_brush)
            self.setPen(self._hl_pen)
        else:
            self.setBrush(self._base_brush)
            self.setPen(self._base_pen)

    def hoverEnterEvent(self, e):
        self.setScale(1.2)

    def hoverLeaveEvent(self, e):
        self.setScale(1.0)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._on_click(self.nid)

class EdgeItem(QtWidgets.QGraphicsLineItem):
    def __init__(self, eid: int, ax: float, ay: float, bx: float, by: float, on_click, parent=None):
        super().__init__(ax, ay, bx, by, parent)
        self.eid = eid
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._base = QtGui.QPen(QtGui.QColor("#062231"), 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._hl = QtGui.QPen(QtGui.QColor(ACCENT), 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._own = QtGui.QPen(QtGui.QColor("#e8f1f6"), 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._bot = QtGui.QPen(QtGui.QColor("#ef4444"), 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self.setPen(self._base)

    def set_highlight(self, on: bool):
        self.setPen(self._hl if on else self._base)

    def set_owner(self, who: Optional[str]):
        if who == "You":
            self.setPen(self._own)
        elif who == "Bot":
            self.setPen(self._bot)
        else:
            self.setPen(self._base)

    def hoverEnterEvent(self, e):
        self.setOpacity(0.95)

    def hoverLeaveEvent(self, e):
        self.setOpacity(1.0)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._on_click(self.eid)

class BoardView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self._zoom = 1.25
        self._panning = False
        self._pan_start = QtCore.QPoint()

        self.node_items: dict[int, NodeItem] = {}
        self.edge_items: dict[int, EdgeItem] = {}

    def clear(self):
        self._scene.clear()
        self.node_items.clear()
        self.edge_items.clear()

    def wheelEvent(self, e: QtGui.QWheelEvent) -> None:
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1/1.12
        self._zoom = max(0.4, min(3.2, self._zoom * factor))
        self.resetTransform()
        self.scale(self._zoom, self._zoom)

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MiddleButton:
            self._panning = True
            self._pan_start = e.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._panning:
            delta = e.pos() - self._pan_start
            self._pan_start = e.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

# ---------- main ----------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CATAN — Desktop (Sprint 2: rules+bot, offline)")
        self.resize(1600, 900)

        self.game: Game = new_game()
        self.selected_action: Optional[str] = None  # settlement/road/city/dev

        root = QtWidgets.QWidget()
        root.setStyleSheet(f"background: {BG}; color: {TEXT};")
        self.setCentralWidget(root)

        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # top bar
        top = QtWidgets.QFrame()
        top.setStyleSheet(f"background: {PANEL}; border-radius: 14px;")
        tl = QtWidgets.QHBoxLayout(top)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(12)

        brand = QtWidgets.QLabel("CATAN")
        brand.setStyleSheet("font-weight: 900; font-size: 16px;")
        tl.addWidget(brand)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("font-weight: 700;")
        tl.addWidget(self.status, 1)

        self.d1 = DiceWidget(1); self.d2 = DiceWidget(1)
        self.d1.clicked.connect(self.on_roll_click)
        self.d2.clicked.connect(self.on_roll_click)
        tl.addWidget(self.d1); tl.addWidget(self.d2)

        self.btn_end = QtWidgets.QPushButton("End turn")
        self.btn_end.setStyleSheet("background:#062231; color:#e8f1f6; border-radius:12px; padding:10px 14px; font-weight:900;")
        self.btn_end.clicked.connect(self.on_end_turn)
        tl.addWidget(self.btn_end)

        outer.addWidget(top, 0)

        # mid splitter
        mid = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        mid.setHandleWidth(8)

        board_card = QtWidgets.QFrame()
        board_card.setStyleSheet(f"background: {PANEL2}; border-radius: 18px;")
        bl = QtWidgets.QVBoxLayout(board_card)
        bl.setContentsMargins(14, 14, 14, 14)
        self.board = BoardView()
        bl.addWidget(self.board, 1)
        mid.addWidget(board_card)

        side = QtWidgets.QFrame()
        side.setStyleSheet(f"background: {PANEL}; border-radius: 18px;")
        side.setMaximumWidth(520)
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(14, 14, 14, 14)
        sl.setSpacing(10)

        self.header = QtWidgets.QLabel("")
        self.header.setStyleSheet(f"color: {MUTED}; font-weight: 700;")
        sl.addWidget(self.header)

        tabs = QtWidgets.QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; }
            QTabBar::tab { background: #072230; color: #b7cad6; padding: 8px 12px; border-top-left-radius: 10px; border-top-right-radius: 10px; }
            QTabBar::tab:selected { background: #061c27; color: #e8f1f6; }
        """)
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("background:#061c27; border-radius: 12px; padding: 10px;")
        self.chat = QtWidgets.QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setMaximumHeight(170)
        self.chat.setStyleSheet("background:#061c27; border-radius: 12px; padding: 10px;")

        chat_wrap = QtWidgets.QWidget()
        cwl = QtWidgets.QVBoxLayout(chat_wrap)
        cwl.setContentsMargins(0,0,0,0)
        cwl.setSpacing(8)
        cwl.addWidget(self.chat, 0)
        row = QtWidgets.QHBoxLayout()
        self.chat_in = QtWidgets.QLineEdit()
        self.chat_in.setPlaceholderText("Say something…")
        self.chat_in.setStyleSheet("background:#041520; border-radius: 12px; padding: 10px; color:#e8f1f6;")
        send = QtWidgets.QPushButton("Send")
        send.setStyleSheet(f"background:{ACCENT}; color:#0b1220; font-weight:900; padding: 10px 16px; border-radius: 12px;")
        send.clicked.connect(self.on_send_chat)
        self.chat_in.returnPressed.connect(self.on_send_chat)
        row.addWidget(self.chat_in, 1)
        row.addWidget(send, 0)
        cwl.addLayout(row)

        tabs.addTab(self.log, "Log")
        tabs.addTab(chat_wrap, "Chat")
        sl.addWidget(tabs, 1)

        mid.addWidget(side)
        mid.setStretchFactor(0, 8)
        mid.setStretchFactor(1, 2)
        mid.setSizes([1200, 420])

        outer.addWidget(mid, 1)

        # bottom bar: actions + resources + trade
        bottom = QtWidgets.QFrame()
        bottom.setStyleSheet(f"background: {PANEL}; border-radius: 18px;")
        b = QtWidgets.QHBoxLayout(bottom)
        b.setContentsMargins(14, 10, 14, 10)
        b.setSpacing(10)

        self.act_set = ActionChip("settlement", "Settlement")
        self.act_road = ActionChip("road", "Road")
        self.act_city = ActionChip("city", "City")
        self.act_dev = ActionChip("dev", "Dev")
        for w in [self.act_set, self.act_road, self.act_city, self.act_dev]:
            w.clicked.connect(self.on_action_pick)

        b.addWidget(self.act_set)
        b.addWidget(self.act_road)
        b.addWidget(self.act_city)
        b.addWidget(self.act_dev)

        b.addSpacing(12)

        self.trade_btn = QtWidgets.QPushButton("Trade 4:1")
        self.trade_btn.setStyleSheet("background:#062231; color:#e8f1f6; border-radius:12px; padding:10px 14px; font-weight:900;")
        self.trade_btn.clicked.connect(self.on_trade)
        b.addWidget(self.trade_btn)

        b.addStretch(1)

        self.res_labels: dict[str, QtWidgets.QLabel] = {}
        for r in ["wood","brick","sheep","wheat","ore"]:
            lab = QtWidgets.QLabel()
            lab.setFixedHeight(42)
            lab.setStyleSheet(f"background:#062231; border-radius:12px; padding:10px 14px; font-weight:900; color:{TEXT};")
            self.res_labels[r] = lab
            b.addWidget(lab)

        outer.addWidget(bottom, 0)

        self._render_all()
        self._log(f"[SYS] New game seed={self.game.seed}. Setup: place settlement then road.")
        self._bot_if_needed()

    # ----- logging / ui -----
    def _log(self, s: str):
        self.log.append(s)

    def _bot_say(self, s: str):
        self.chat.append(f"<b>Bot:</b> {s}")

    def _sync_top(self):
        g = self.game
        p = g.cur_player()
        self.header.setText(f"Players: You(VP {g.players[0].vp()}) | Bot(VP {g.players[1].vp()})   Phase: {g.phase}   Turn: {p.name}")
        if g.phase == "setup":
            self.status.setText(f"Setup: {p.name} must place {g.required_action()}.")
        else:
            r = "rolled" if g.rolled else "not rolled"
            self.status.setText(f"{p.name} turn — {r}. Click dice to roll. Build by selecting card then clicking board.")

        you = g.players[0]
        for r in ["wood","brick","sheep","wheat","ore"]:
            self.res_labels[r].setText(f"{r}: {you.resources[r]} | bank:{g.bank.stock[r]}")

        # end button enabled only in main + your turn
        self.btn_end.setEnabled(g.phase=="main" and g.cur_player().name=="You")
        self.trade_btn.setEnabled(g.phase=="main" and g.cur_player().name=="You")

    # ----- board render -----
    def _render_all(self):
        self.board.clear()
        g = self.game

        # draw edges first (so nodes on top)
        for eid,(a,b) in g.graph.edges.items():
            ax,ay = g.graph.nodes[a]
            bx,by = g.graph.nodes[b]
            item = EdgeItem(eid, ax,ay, bx,by, self.on_edge_click)
            self.board.scene().addItem(item)
            self.board.edge_items[eid] = item

        # draw tiles
        hex_size = 62.0
        def hex_poly(cx,cy):
            pts = []
            for i in range(6):
                ang = math.radians(60*i - 30)
                pts.append(QtCore.QPointF(cx + hex_size*math.cos(ang), cy + hex_size*math.sin(ang)))
            return QtGui.QPolygonF(pts)

        for t in g.tiles:
            # same axial->xy as core
            w = math.sqrt(3) * hex_size
            v = 1.5 * hex_size
            cx = w * (t.q + t.r/2.0)
            cy = v * t.r

            terr = TERRAIN_TO_RES[t.terrain]
            if terr is None:
                col = RESOURCE_COLORS["desert"]
            else:
                col = RESOURCE_COLORS[terr]

            poly = hex_poly(cx,cy)
            shadow = QtWidgets.QGraphicsPolygonItem(poly.translated(0, 4))
            shadow.setBrush(QtGui.QColor(0,0,0,120))
            shadow.setPen(QtCore.Qt.NoPen)
            self.board.scene().addItem(shadow)

            item = QtWidgets.QGraphicsPolygonItem(poly)
            item.setBrush(QtGui.QColor(col))
            item.setPen(QtGui.QPen(QtGui.QColor("#0b1220"), 2))
            self.board.scene().addItem(item)

            if t.number is not None:
                token = QtWidgets.QGraphicsEllipseItem(cx-20, cy-20, 40, 40)
                token.setBrush(QtGui.QColor("#f8fafc"))
                token.setPen(QtGui.QPen(QtGui.QColor("#0b1220"), 2))
                self.board.scene().addItem(token)

                txt = QtWidgets.QGraphicsTextItem(str(t.number))
                is_hot = t.number in (6,8)
                txt.setDefaultTextColor(QtGui.QColor(DANGER if is_hot else "#111827"))
                f = QtGui.QFont("Segoe UI", 14); f.setBold(True)
                txt.setFont(f)
                b = txt.boundingRect()
                txt.setPos(cx-b.width()/2, cy-b.height()/2 - 2)
                self.board.scene().addItem(txt)

        # nodes
        for nid,(x,y) in g.graph.nodes.items():
            n = NodeItem(nid, x,y, r=6.5, on_click=self.on_node_click)
            self.board.scene().addItem(n)
            self.board.node_items[nid] = n

        # settlements/cities as simple shapes (Sprint 3: models)
        for pl in g.players:
            col = "#e8f1f6" if pl.name=="You" else "#ef4444"
            for nid in pl.settlements:
                x,y = g.graph.nodes[nid]
                it = QtWidgets.QGraphicsRectItem(x-10, y-10, 20, 20)
                it.setBrush(QtGui.QColor(col))
                it.setPen(QtGui.QPen(QtGui.QColor("#0b1220"), 2))
                it.setZValue(80)
                self.board.scene().addItem(it)
            for nid in pl.cities:
                x,y = g.graph.nodes[nid]
                it = QtWidgets.QGraphicsRectItem(x-13, y-13, 26, 26)
                it.setBrush(QtGui.QColor(col))
                it.setPen(QtGui.QPen(QtGui.QColor("#0b1220"), 2))
                it.setZValue(80)
                self.board.scene().addItem(it)

        # road ownership
        for pl in g.players:
            for eid in pl.roads:
                self.board.edge_items[eid].set_owner(pl.name)

        # fit + default zoom
        rect = self.board.scene().itemsBoundingRect().adjusted(-120,-120,120,120)
        self.board.scene().setSceneRect(rect)
        self.board.fitInView(rect, QtCore.Qt.KeepAspectRatio)
        self.board.resetTransform()
        self.board.scale(self.board._zoom, self.board._zoom)

        self._update_highlights()
        self._sync_top()

    def _update_highlights(self):
        g = self.game
        # clear
        for n in self.board.node_items.values():
            n.set_highlight(False)
        for e in self.board.edge_items.values():
            # don't override owner colors; only highlight if selectable
            pass

        if g.winner is not None:
            return
        if g.cur_player().name != "You":
            return

        act = self._effective_action()
        if act == "settlement":
            for nid in g.graph.nodes.keys():
                if g.can_place_settlement(g.cur_player(), nid):
                    self.board.node_items[nid].set_highlight(True)
        elif act == "road":
            for eid in g.graph.edges.keys():
                ok = g.can_place_road(g.cur_player(), eid)
                self.board.edge_items[eid].set_highlight(ok)

    def _effective_action(self) -> Optional[str]:
        g = self.game
        if g.phase == "setup":
            return g.required_action()
        return self.selected_action

    # ----- interactions -----
    def on_action_pick(self):
        # toggle group
        sender = self.sender()
        for w in [self.act_set, self.act_road, self.act_city, self.act_dev]:
            if w is not sender:
                w.setChecked(False)
        self.selected_action = sender.key if sender.isChecked() else None
        self._update_highlights()

    def on_roll_click(self):
        g = self.game
        if g.winner is not None:
            return
        if g.phase != "main":
            self._log("[!] Roll is available after setup.")
            return
        if g.cur_player().name != "You":
            return
        if g.rolled:
            return

        roll = g.roll_dice()
        # show dice values approx (split)
        # (we don't store both dice in core; just display total)
        self.d1.setValue(max(1, min(6, roll-1)))
        self.d2.setValue(max(1, min(6, roll-(self.d1.value))))
        self._log(f"You rolled {roll}.")
        for s in g.distribute(roll):
            self._log(s)
        self._sync_top()
        self._render_all()

    def on_end_turn(self):
        g = self.game
        if g.phase != "main" or g.cur_player().name != "You":
            return
        self.selected_action = None
        for w in [self.act_set, self.act_road, self.act_city, self.act_dev]:
            w.setChecked(False)
        self._log(g.end_turn())
        self._render_all()
        self._bot_if_needed()

    def on_trade(self):
        g = self.game
        if g.phase != "main" or g.cur_player().name != "You":
            return
        dlg = TradeDialog(self, ["wood","brick","sheep","wheat","ore"], ["wood","brick","sheep","wheat","ore"])
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        give = dlg.give.currentText()
        get = dlg.get.currentText()
        msg = g.trade_bank_4to1(give, get)
        self._log(msg)
        self._render_all()

    def on_node_click(self, nid: int):
        g = self.game
        if g.winner is not None:
            return
        if g.cur_player().name != "You":
            return
        act = self._effective_action()
        if act == "settlement":
            msg = g.place_settlement(nid)
            self._log(msg)
            self._render_all()
            self._bot_if_needed()
        elif act == "city":
            msg = g.upgrade_city(nid)
            self._log(msg)
            self._render_all()

    def on_edge_click(self, eid: int):
        g = self.game
        if g.winner is not None:
            return
        if g.cur_player().name != "You":
            return
        act = self._effective_action()
        if act == "road":
            msg = g.place_road(eid)
            self._log(msg)
            self._render_all()
            self._bot_if_needed()

    def on_send_chat(self):
        txt = self.chat_in.text().strip()
        if not txt:
            return
        self.chat_in.clear()
        self.chat.append(f"<b>You:</b> {txt}")
        self._bot_say("OK. (Chat AI will be wired later.)")

    def _bot_if_needed(self):
        g = self.game
        if g.winner is not None:
            win = g.players[g.winner].name
            self._log(f"[WIN] {win} wins!")
            return
        if g.cur_player().is_bot:
            QtCore.QTimer.singleShot(350, self._run_bot)

    def _run_bot(self):
        g = self.game
        if not g.cur_player().is_bot or g.winner is not None:
            return
        logs = bot_take_turn(g)
        for s in logs:
            self._log(s)
        self._render_all()
        if g.winner is not None:
            win = g.players[g.winner].name
            self._log(f"[WIN] {win} wins!")
            return
        # bot may still be on turn if it ended; keep going automatically if needed
        if g.cur_player().is_bot:
            QtCore.QTimer.singleShot(250, self._run_bot)

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

