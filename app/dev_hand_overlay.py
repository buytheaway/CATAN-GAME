from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

CARD_ORDER = ["knight", "victory_point", "road_building", "year_of_plenty", "monopoly"]
CARD_LABEL = {
    "knight": "Knight",
    "victory_point": "VP",
    "road_building": "Road",
    "year_of_plenty": "Plenty",
    "monopoly": "Monopoly",
}

CARD_COLORS = {
    "knight": ("#6d28d9", "#8b5cf6"),
    "victory_point": ("#1d4ed8", "#3b82f6"),
    "road_building": ("#475569", "#94a3b8"),
    "year_of_plenty": ("#15803d", "#22c55e"),
    "monopoly": ("#b45309", "#f59e0b"),
}

def _star_points(cx: float, cy: float, r: float):
    pts = []
    for i in range(10):
        ang = math.radians(i * 36 - 90)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(QtCore.QPointF(cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts

def make_dev_icon(card_type: str, size: int = 22) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    fg = QtGui.QColor("#f8fafc")
    pen = QtGui.QPen(fg)
    pen.setWidthF(1.2)
    p.setPen(pen)
    p.setBrush(fg)

    cx = size * 0.5
    cy = size * 0.5

    if card_type == "knight":
        p.drawEllipse(QtCore.QRectF(cx-5, cy-7, 10, 10))
        p.drawRect(QtCore.QRectF(cx-6, cy-2, 12, 7))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawLine(QtCore.QPointF(cx-2, cy-3), QtCore.QPointF(cx+4, cy-3))
    elif card_type == "victory_point":
        poly = QtGui.QPolygonF(_star_points(cx, cy, size * 0.38))
        p.drawPolygon(poly)
    elif card_type == "road_building":
        p.drawRoundedRect(QtCore.QRectF(cx-7, cy-4, 14, 8), 2, 2)
        p.setPen(QtGui.QPen(QtGui.QColor("#0b1220"), 1))
        p.drawLine(QtCore.QPointF(cx-6, cy), QtCore.QPointF(cx+6, cy))
    elif card_type == "year_of_plenty":
        p.drawEllipse(QtCore.QRectF(cx-7, cy-3, 7, 10))
        p.drawEllipse(QtCore.QRectF(cx, cy-3, 7, 10))
        p.drawLine(QtCore.QPointF(cx, cy+7), QtCore.QPointF(cx, cy-7))
    else:  # monopoly
        p.drawEllipse(QtCore.QRectF(cx-6, cy-6, 12, 6))
        p.drawEllipse(QtCore.QRectF(cx-6, cy-2, 12, 6))
        p.drawEllipse(QtCore.QRectF(cx-6, cy+2, 12, 6))

    p.end()
    return pm

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

def _get_dev_list(game, pid: int):
    p = game.players[pid]
    if hasattr(p, "dev_cards"):
        return p.dev_cards or []
    if hasattr(p, "dev"):
        return p.dev or []
    if isinstance(p, dict):
        return p.get("dev_cards", []) or []
    return []

def _count_cards(dev_list):
    counts = {k: 0 for k in CARD_ORDER}
    new_counts = {k: 0 for k in CARD_ORDER}
    for c in dev_list:
        if isinstance(c, dict):
            t = str(c.get("type", "")).strip().lower()
            if t in counts:
                counts[t] += 1
                if bool(c.get("new", False)):
                    new_counts[t] += 1
        else:
            t = str(c).strip().lower()
            if t in counts:
                counts[t] += 1
    return counts, new_counts

class _Chip(QtWidgets.QFrame):
    def __init__(self, card_type: str):
        super().__init__()
        self.setObjectName("devChip")
        self.setFixedSize(60, 56)
        self.card_type = card_type

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(0)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        self.icon = QtWidgets.QLabel()
        self.icon.setFixedSize(24, 24)
        self.icon.setPixmap(make_dev_icon(card_type, 22))
        top.addWidget(self.icon)
        top.addStretch(1)

        self.new_dot = QtWidgets.QLabel()
        self.new_dot.setFixedSize(6, 6)
        self.new_dot.setStyleSheet("background:#f97316; border-radius:3px;")
        self.new_dot.hide()
        top.addWidget(self.new_dot)

        self.badge = QtWidgets.QLabel("0")
        self.badge.setAlignment(QtCore.Qt.AlignCenter)
        self.badge.setObjectName("devCount")
        top.addWidget(self.badge)

        lay.addLayout(top)

        self.lbl = QtWidgets.QLabel(CARD_LABEL.get(card_type, "").upper())
        self.lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl.setStyleSheet("font-size:9px; color:rgba(248,250,252,0.9);")
        lay.addWidget(self.lbl)

    def set_count(self, count: int, new_count: int):
        self.badge.setText(str(count))
        self.new_dot.setVisible(new_count > 0)
        base, edge = CARD_COLORS.get(self.card_type, ("#0f172a", "#334155"))
        if count <= 0:
            self.setStyleSheet(
                "background:rgba(10,20,28,0.25); border:1px solid rgba(255,255,255,0.08); border-radius:12px;"
            )
            self.icon.setPixmap(make_dev_icon(self.card_type, 22))
        else:
            self.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {base}, stop:1 {edge});"
                f"border:1px solid {edge}; border-radius:12px;"
            )

class DevHandOverlay(QtWidgets.QFrame):
    def __init__(self, viewport: QtWidgets.QWidget, win: QtWidgets.QWidget):
        super().__init__(viewport)
        self.setObjectName("devHandOverlay")
        self.win = win
        self.setAutoFillBackground(False)

        # compact panel: top-right of map, clean alignment
        self.setFixedSize(360, 94)
        self.setStyleSheet("""
#devHandOverlay {
  background: rgba(6, 18, 26, 215);
  border: 1px solid rgba(120, 180, 220, 90);
  border-radius: 14px;
}
#devChip {
  background: rgba(255,255,255,16);
  border: 1px solid rgba(255,255,255,18);
  border-radius: 12px;
}
#devCount {
  background: rgba(10, 18, 26, 0.6);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 7px;
  min-width: 20px;
  padding: 1px 6px;
  font-size: 10px;
}
QLabel { color: #d7eefc; }
""")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("Dev cards")
        ft = self.title.font()
        ft.setBold(True)
        self.title.setFont(ft)
        top.addWidget(self.title)
        top.addStretch(1)
        self.hint = QtWidgets.QLabel("")
        self.hint.setStyleSheet("color: rgba(215,238,252,150); font-size: 11px;")
        top.addWidget(self.hint)
        root.addLayout(top)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.chips = {}
        for k in CARD_ORDER:
            chip = _Chip(k)
            self.chips[k] = chip
            row.addWidget(chip)
        row.addStretch(1)
        root.addLayout(row)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        viewport.installEventFilter(self)
        QtCore.QTimer.singleShot(50, self._reposition)

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Resize:
            QtCore.QTimer.singleShot(0, self._reposition)
        return super().eventFilter(obj, ev)

    def _reposition(self):
        vp = self.parentWidget()
        if not vp:
            return
        margin = 14
        x = max(margin, vp.width() - self.width() - margin)
        y = max(margin, margin)
        self.move(x, y)

    def refresh(self):
        game = _get_game(self.win)
        if game is None:
            return
        pid = _get_pid(self.win)
        dev_list = _get_dev_list(game, pid)
        counts, new_counts = _count_cards(dev_list)

        total_new = sum(new_counts.values())
        self.hint.setText(f"new:{total_new}" if total_new else "")

        for k, chip in self.chips.items():
            chip.set_count(counts.get(k, 0), new_counts.get(k, 0))

def attach_dev_hand_overlay(win: QtWidgets.QWidget):
    if getattr(win, "_devhand_attached", False):
        return

    views = win.findChildren(QtWidgets.QGraphicsView)
    if not views:
        return
    view = sorted(views, key=lambda v: v.width() * v.height(), reverse=True)[0]
    vp = view.viewport()

    overlay = DevHandOverlay(vp, win)
    overlay.show()

    win._devhand_attached = True
