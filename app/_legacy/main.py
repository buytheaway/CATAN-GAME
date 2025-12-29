from __future__ import annotations
import sys
import math
from typing import Dict, Optional, Set, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from app.catan_core import new_game, Game, TERRAIN_TO_RESOURCE
from app.bot import SimpleBot

# ===== simple SVG icons we own (minimal, not copied) =====
ICON_SVGS: Dict[str, str] = {
    "wood":  '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect rx="14" ry="14" x="4" y="4" width="56" height="56" fill="#1f7a3a"/><path d="M32 14c8 10 14 14 14 22 0 8-6 14-14 14S18 44 18 36c0-8 6-12 14-22z" fill="#dff5e6"/></svg>''',
    "brick": '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect rx="14" ry="14" x="4" y="4" width="56" height="56" fill="#b44b2a"/><path d="M14 24h36v6H14zM14 34h20v6H14zM36 34h14v6H36z" fill="#f3ded6"/></svg>''',
    "sheep": '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect rx="14" ry="14" x="4" y="4" width="56" height="56" fill="#4f8a3a"/><circle cx="26" cy="34" r="12" fill="#f6f6f6"/><circle cx="38" cy="34" r="10" fill="#f6f6f6"/><circle cx="40" cy="30" r="6" fill="#2b2b2b"/></svg>''',
    "wheat": '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect rx="14" ry="14" x="4" y="4" width="56" height="56" fill="#d4b21a"/><path d="M32 14v36" stroke="#fff7cf" stroke-width="4"/><path d="M32 18c-6 2-8 6-8 10 6-2 8-6 8-10zm0 10c-6 2-8 6-8 10 6-2 8-6 8-10zm0 10c-6 2-8 6-8 10 6-2 8-6 8-10z" fill="#fff7cf"/></svg>''',
    "ore":   '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect rx="14" ry="14" x="4" y="4" width="56" height="56" fill="#7f8fa3"/><path d="M18 42l8-20 10 6 10-10 2 24H18z" fill="#e8eef7"/></svg>''',
}

def svg_icon(svg: str, size: int = 18) -> QtGui.QIcon:
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    renderer = QtSvgRenderer(svg)
    p = QtGui.QPainter(img)
    renderer.render(p)
    p.end()
    return QtGui.QIcon(QtGui.QPixmap.fromImage(img))

class QtSvgRenderer(QtCore.QObject):
    def __init__(self, svg: str):
        super().__init__()
        from PySide6.QtSvg import QSvgRenderer
        self.r = QSvgRenderer(QtCore.QByteArray(svg.encode('utf-8')))
    def render(self, painter: QtGui.QPainter):
        self.r.render(painter)

# ===== Graphics items =====
class HexItem(QtWidgets.QGraphicsPolygonItem):
    def __init__(self, poly: QtGui.QPolygonF, terrain: str, number: Optional[int]):
        super().__init__(poly)
        self.terrain = terrain
        self.number = number
        self.setZValue(0)
        self.setPen(QtGui.QPen(QtGui.QColor("#d9d2b0"), 2))
        self.setBrush(QtGui.QBrush(QtGui.QColor(terrain_color(terrain))))

def terrain_color(t: str) -> str:
    return {
        "forest":   "#2f8f4e",
        "hill":     "#cc5a2d",
        "pasture":  "#7dbb4b",
        "field":    "#e4c44f",
        "mountain": "#9aa1a8",
        "desert":   "#d8c38f",
    }.get(t, "#888")

class VertexItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, vid: int, x: float, y: float):
        super().__init__(x-7, y-7, 14, 14)
        self.vid = vid
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self._state = "idle"  # idle/hover/legal/selected
        self.update_style(legal=False, hover=False)

    def update_style(self, legal: bool, hover: bool):
        if legal:
            self.setPen(QtGui.QPen(QtGui.QColor("#9be15d"), 2))
            self.setBrush(QtGui.QBrush(QtGui.QColor(155, 225, 93, 60)))
        else:
            self.setPen(QtGui.QPen(QtGui.QColor("#2a2a2a"), 1))
            self.setBrush(QtGui.QBrush(QtGui.QColor(0,0,0,0)))
        if hover and legal:
            self.setBrush(QtGui.QBrush(QtGui.QColor(155, 225, 93, 120)))

class EdgeItem(QtWidgets.QGraphicsLineItem):
    def __init__(self, eid: int, ax: float, ay: float, bx: float, by: float):
        super().__init__(ax, ay, bx, by)
        self.eid = eid
        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        self.update_style(legal=False, hover=False)

    def update_style(self, legal: bool, hover: bool):
        if legal:
            pen = QtGui.QPen(QtGui.QColor("#9be15d"), 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        else:
            pen = QtGui.QPen(QtGui.QColor("#3a3a3a"), 4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        if hover and legal:
            pen.setWidth(8)
        self.setPen(pen)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CATAN — Desktop (singleplayer prototype)")
        self.setMinimumSize(1200, 760)

        self.g: Game = new_game()
        self.bot = SimpleBot()

        self.build_mode: Optional[str] = None  # road/settlement/city

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("background:#0f5f87;")  # ocean vibe

        layout = QtWidgets.QGridLayout(root)
        layout.setContentsMargins(12,12,12,12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        # ===== top bar =====
        top = QtWidgets.QFrame()
        top.setStyleSheet("background:rgba(20,20,20,0.55); border-radius:14px;")
        topLay = QtWidgets.QHBoxLayout(top)
        topLay.setContentsMargins(12,8,12,8)

        self.lblTitle = QtWidgets.QLabel("CATAN")
        self.lblTitle.setStyleSheet("color:#fff; font-size:16px; font-weight:700;")
        topLay.addWidget(self.lblTitle)

        topLay.addSpacing(12)

        self.lblTurn = QtWidgets.QLabel("")
        self.lblTurn.setStyleSheet("color:#eaeaea; font-size:13px;")
        topLay.addWidget(self.lblTurn, 1)

        self.btnRoll = self.mk_btn("Roll", self.on_roll)
        self.btnBuild = self.mk_btn("Build", self.on_build_menu)
        self.btnEnd  = self.mk_btn("End", self.on_end)

        topLay.addWidget(self.btnRoll)
        topLay.addWidget(self.btnBuild)
        topLay.addWidget(self.btnEnd)

        layout.addWidget(top, 0, 0, 1, 2)

        # ===== board view =====
        self.scene = QtWidgets.QGraphicsScene()
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.view.setStyleSheet("background: transparent; border:0;")
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

        boardCard = QtWidgets.QFrame()
        boardCard.setStyleSheet("background:rgba(10,10,10,0.45); border-radius:18px;")
        boardLay = QtWidgets.QVBoxLayout(boardCard)
        boardLay.setContentsMargins(10,10,10,10)
        boardLay.addWidget(self.view)

        layout.addWidget(boardCard, 1, 0)

        # ===== right panel =====
        right = QtWidgets.QFrame()
        right.setStyleSheet("background:rgba(20,20,20,0.55); border-radius:18px;")
        rightLay = QtWidgets.QVBoxLayout(right)
        rightLay.setContentsMargins(12,12,12,12)
        rightLay.setSpacing(10)

        self.playersBox = QtWidgets.QLabel("")
        self.playersBox.setStyleSheet("color:#fff; font-size:13px;")
        rightLay.addWidget(self.playersBox)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:0; }
            QTabBar::tab { background:#2a2a2a; color:#ddd; padding:8px 10px; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:6px; }
            QTabBar::tab:selected { background:#3a3a3a; color:#fff; }
        """)
        self.logView = QtWidgets.QPlainTextEdit()
        self.logView.setReadOnly(True)
        self.logView.setStyleSheet("background:#141414; color:#eaeaea; border-radius:12px; padding:10px;")
        self.chatView = QtWidgets.QPlainTextEdit()
        self.chatView.setReadOnly(True)
        self.chatView.setStyleSheet("background:#141414; color:#eaeaea; border-radius:12px; padding:10px;")

        self.tabs.addTab(self.logView, "Log")
        self.tabs.addTab(self.chatView, "Chat")
        rightLay.addWidget(self.tabs, 1)

        chatRow = QtWidgets.QHBoxLayout()
        self.chatIn = QtWidgets.QLineEdit()
        self.chatIn.setPlaceholderText("Say something to Bot…")
        self.chatIn.setStyleSheet("background:#101010; color:#fff; border-radius:10px; padding:8px 10px; border:1px solid #333;")
        self.chatSend = self.mk_btn("Send", self.on_chat_send)
        chatRow.addWidget(self.chatIn, 1)
        chatRow.addWidget(self.chatSend)
        rightLay.addLayout(chatRow)

        layout.addWidget(right, 1, 1)

        # ===== bottom resource bar =====
        bottom = QtWidgets.QFrame()
        bottom.setStyleSheet("background:rgba(20,20,20,0.55); border-radius:16px;")
        bLay = QtWidgets.QHBoxLayout(bottom)
        bLay.setContentsMargins(12,10,12,10)
        bLay.setSpacing(10)

        self.resLabels: Dict[str, QtWidgets.QLabel] = {}
        for r in ["wood","brick","sheep","wheat","ore"]:
            w = QtWidgets.QFrame()
            w.setStyleSheet("background:#111; border-radius:12px;")
            wl = QtWidgets.QHBoxLayout(w)
            wl.setContentsMargins(10,6,10,6)
            icon = QtWidgets.QLabel()
            icon.setPixmap(self.svg_pix(ICON_SVGS[r], 22))
            icon.setFixedSize(24,24)
            lbl = QtWidgets.QLabel("0")
            lbl.setStyleSheet("color:#fff; font-weight:700;")
            wl.addWidget(icon)
            wl.addSpacing(6)
            wl.addWidget(lbl)
            self.resLabels[r] = lbl
            bLay.addWidget(w)

        bLay.addStretch(1)
        self.hintLbl = QtWidgets.QLabel("")
        self.hintLbl.setStyleSheet("color:#fff;")
        bLay.addWidget(self.hintLbl)

        layout.addWidget(bottom, 2, 0, 1, 2)

        # draw once
        self.hex_items = []
        self.vertex_items: Dict[int, VertexItem] = {}
        self.edge_items: Dict[int, EdgeItem] = {}
        self._draw_board()
        self._sync_all()

        # bot auto-setup
        QtCore.QTimer.singleShot(250, self._bot_tick)

    def mk_btn(self, text: str, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(slot)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setStyleSheet("""
            QPushButton { background:#28c281; color:#0c0c0c; border:0; border-radius:10px; padding:8px 14px; font-weight:700; }
            QPushButton:hover { background:#33d18f; }
            QPushButton:disabled { background:#3a3a3a; color:#bbb; }
        """)
        return b

    def svg_pix(self, svg: str, size: int) -> QtGui.QPixmap:
        img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
        img.fill(QtCore.Qt.transparent)
        renderer = QtSvgRenderer(svg)
        p = QtGui.QPainter(img)
        renderer.render(p)
        p.end()
        return QtGui.QPixmap.fromImage(img)

    def _draw_board(self):
        self.scene.clear()
        self.vertex_items.clear()
        self.edge_items.clear()

        # draw hexes
        for t in self.g.board.tiles:
            cx, cy = t.center
            poly = QtGui.QPolygonF()
            for vid in t.corners:
                v = self.g.board.vertices[vid]
                poly.append(QtCore.QPointF(v.x, v.y))
            hi = HexItem(poly, t.terrain, t.number)
            self.scene.addItem(hi)

            # number token
            if t.number is not None:
                token = QtWidgets.QGraphicsEllipseItem(cx-18, cy-18, 36, 36)
                token.setZValue(20)
                token.setPen(QtGui.QPen(QtGui.QColor("#f2ead6"), 2))
                token.setBrush(QtGui.QBrush(QtGui.QColor("#f7f3ea")))
                self.scene.addItem(token)

                txt = QtWidgets.QGraphicsTextItem(str(t.number))
                txt.setDefaultTextColor(QtGui.QColor("#c62828" if t.number in (6,8) else "#222"))
                f = QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)
                txt.setFont(f)
                txt.setPos(cx-6, cy-12)
                txt.setZValue(21)
                self.scene.addItem(txt)

            # terrain tiny icon
            res = TERRAIN_TO_RESOURCE.get(t.terrain)
            if res:
                ic = QtWidgets.QGraphicsPixmapItem(self.svg_pix(ICON_SVGS[res], 18))
                ic.setPos(cx-9, cy+10)
                ic.setZValue(21)
                self.scene.addItem(ic)

        # edges
        for eid, e in self.g.board.edges.items():
            a = self.g.board.vertices[e.a]
            b = self.g.board.vertices[e.b]
            li = EdgeItem(eid, a.x, a.y, b.x, b.y)
            self.scene.addItem(li)
            self.edge_items[eid] = li

        # vertices
        for vid, v in self.g.board.vertices.items():
            vi = VertexItem(vid, v.x, v.y)
            self.scene.addItem(vi)
            self.vertex_items[vid] = vi

        # click handlers (install via event filter-style)
        for vi in self.vertex_items.values():
            vi.mousePressEvent = lambda ev, _vi=vi: self._on_vertex_click(_vi.vid)
            vi.hoverEnterEvent = lambda ev, _vi=vi: self._on_hover_vertex(_vi.vid, True)
            vi.hoverLeaveEvent = lambda ev, _vi=vi: self._on_hover_vertex(_vi.vid, False)

        for ei in self.edge_items.values():
            ei.mousePressEvent = lambda ev, _ei=ei: self._on_edge_click(_ei.eid)
            ei.hoverEnterEvent = lambda ev, _ei=ei: self._on_hover_edge(_ei.eid, True)
            ei.hoverLeaveEvent = lambda ev, _ei=ei: self._on_hover_edge(_ei.eid, False)

        # fit
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def _on_hover_vertex(self, vid: int, on: bool):
        self._sync_highlights(hover_vid=vid if on else None)

    def _on_hover_edge(self, eid: int, on: bool):
        self._sync_highlights(hover_eid=eid if on else None)

    def _on_vertex_click(self, vid: int):
        pid = self.g.current
        if self.g.cur_player().is_bot:
            return

        try:
            if self.g.phase().startswith("setup"):
                need_pid, need_act = self.g.setup_action()
                if need_pid != pid:
                    return
                if need_act == "settlement":
                    self.g.place_settlement(pid, vid)
                else:
                    return
            else:
                if self.build_mode == "settlement":
                    self.g.place_settlement(pid, vid)
                elif self.build_mode == "city":
                    self.g.place_city(pid, vid)
                else:
                    return
        except Exception as e:
            self._toast(str(e))
            return

        self.build_mode = None
        self._sync_all()
        QtCore.QTimer.singleShot(250, self._bot_tick)

    def _on_edge_click(self, eid: int):
        pid = self.g.current
        if self.g.cur_player().is_bot:
            return

        try:
            if self.g.phase().startswith("setup"):
                need_pid, need_act = self.g.setup_action()
                if need_pid != pid:
                    return
                if need_act == "road":
                    self.g.place_road(pid, eid)
                else:
                    return
            else:
                if self.build_mode == "road":
                    self.g.place_road(pid, eid)
                else:
                    return
        except Exception as e:
            self._toast(str(e))
            return

        self.build_mode = None
        self._sync_all()
        QtCore.QTimer.singleShot(250, self._bot_tick)

    def _toast(self, msg: str):
        self.hintLbl.setText(msg)
        QtCore.QTimer.singleShot(2200, lambda: self.hintLbl.setText(""))

    def on_roll(self):
        try:
            self.g.roll_dice()
        except Exception as e:
            self._toast(str(e))
            return
        self._sync_all()
        QtCore.QTimer.singleShot(300, self._bot_tick)

    def on_end(self):
        if self.g.phase() != "main":
            self._toast("Finish setup placements")
            return
        self.g.end_turn()
        self.build_mode = None
        self._sync_all()
        QtCore.QTimer.singleShot(300, self._bot_tick)

    def on_build_menu(self):
        if self.g.phase() != "main":
            self._toast("Build is in main phase")
            return

        menu = QtWidgets.QMenu(self)
        a1 = menu.addAction("Road")
        a2 = menu.addAction("Settlement")
        a3 = menu.addAction("City")
        act = menu.exec(QtGui.QCursor.pos())
        if act == a1:
            self.build_mode = "road"
        elif act == a2:
            self.build_mode = "settlement"
        elif act == a3:
            self.build_mode = "city"
        else:
            return
        self._sync_all()

    def on_chat_send(self):
        txt = self.chatIn.text().strip()
        if not txt:
            return
        self.chatIn.setText("")
        self.chatView.appendPlainText(f"You: {txt}")
        # simple canned reply
        reply = "Ok." if len(txt) < 12 else "Noted. Focus on high pips and keep road options open."
        self.chatView.appendPlainText(f"Bot: {reply}")

    def _sync_all(self):
        # players line
        p0, p1 = self.g.players[0], self.g.players[1]
        ph = self.g.phase()
        turn = self.g.cur_player().name

        self.playersBox.setText(
            f"Players:  You (VP {p0.vp})   |   Bot (VP {p1.vp})\\n"
            f"Phase: {ph}   |   Turn: {turn}"
        )

        # buttons state
        self.btnRoll.setEnabled(self.g.can_roll() and self.g.is_human_turn())
        self.btnBuild.setEnabled(self.g.phase() == "main" and self.g.is_human_turn())
        self.btnEnd.setEnabled(self.g.phase() == "main" and self.g.is_human_turn())

        # resources (human only)
        you = self.g.players[0]
        for r,lbl in self.resLabels.items():
            lbl.setText(str(you.resources.get(r,0)))

        # log
        self.logView.setPlainText("\\n".join(self.g.log[-200:]))
        self.logView.verticalScrollBar().setValue(self.logView.verticalScrollBar().maximum())

        # draw buildings/roads
        self._redraw_ownership()
        self._sync_highlights()

        # status line
        if self.g.phase().startswith("setup"):
            pid, act = self.g.setup_action()
            who = "You" if pid == 0 else "Bot"
            self.lblTurn.setText(f"Setup: {who} place {act}. Click highlighted spots.")
        else:
            need = "Roll dice" if (self.g.is_human_turn() and not self.g.rolled) else "Build / End"
            bm = f" | Build: {self.build_mode}" if self.build_mode else ""
            self.lblTurn.setText(f"{turn}'s turn. {need}{bm}")

    def _redraw_ownership(self):
        # clear old ownership drawings: easiest add on top with fresh (lightweight)
        # remove all items with z>=30 except vertices/edges
        for it in list(self.scene.items()):
            if isinstance(it, (VertexItem, EdgeItem, HexItem, QtWidgets.QGraphicsEllipseItem, QtWidgets.QGraphicsTextItem, QtWidgets.QGraphicsPixmapItem)):
                # keep base; ownership will be separate high-z markers
                continue

        # add roads and buildings as overlays by scanning
        # roads
        for p in self.g.players:
            col = QtGui.QColor("#00d4ff" if p.pid == 0 else "#ff5a5a")
            for eid in p.roads:
                e = self.g.board.edges[eid]
                a = self.g.board.vertices[e.a]
                b = self.g.board.vertices[e.b]
                li = QtWidgets.QGraphicsLineItem(a.x, a.y, b.x, b.y)
                li.setZValue(40)
                pen = QtGui.QPen(col, 10, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
                li.setPen(pen)
                self.scene.addItem(li)

            # settlements/cities
            for vid in p.settlements:
                v = self.g.board.vertices[vid]
                item = QtWidgets.QGraphicsEllipseItem(v.x-10, v.y-10, 20, 20)
                item.setZValue(50)
                item.setPen(QtGui.QPen(QtGui.QColor("#111"), 2))
                item.setBrush(QtGui.QBrush(col))
                self.scene.addItem(item)

            for vid in p.cities:
                v = self.g.board.vertices[vid]
                item = QtWidgets.QGraphicsRectItem(v.x-12, v.y-12, 24, 24)
                item.setZValue(50)
                item.setPen(QtGui.QPen(QtGui.QColor("#111"), 2))
                item.setBrush(QtGui.QBrush(col))
                self.scene.addItem(item)

    def _sync_highlights(self, hover_vid: Optional[int]=None, hover_eid: Optional[int]=None):
        pid = self.g.current
        legalV: Set[int] = set()
        legalE: Set[int] = set()

        if not self.g.cur_player().is_bot:
            if self.g.phase().startswith("setup"):
                sp = self.g.setup_action()
                if sp and sp[0] == pid:
                    if sp[1] == "settlement":
                        legalV = self.g.legal_settlement_vertices(pid)
                    elif sp[1] == "road":
                        legalE = self.g.legal_road_edges(pid)
            else:
                if self.build_mode == "settlement":
                    legalV = self.g.legal_settlement_vertices(pid)
                elif self.build_mode == "city":
                    legalV = self.g.legal_city_vertices(pid)
                elif self.build_mode == "road":
                    legalE = self.g.legal_road_edges(pid)

        for vid, vi in self.vertex_items.items():
            vi.update_style(legal=(vid in legalV), hover=(hover_vid == vid))

        for eid, ei in self.edge_items.items():
            ei.update_style(legal=(eid in legalE), hover=(hover_eid == eid))

    def _bot_tick(self):
        # let bot play until it becomes human's turn or no action
        guard = 0
        did = True
        while did and guard < 30:
            did = self.bot.play_step(self.g)
            guard += 1
        self._sync_all()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()