from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

ACTION_TEXTS = {"settlement", "road", "city", "dev", "trade"}

def _find_board_view(win: QtWidgets.QWidget) -> QtWidgets.QGraphicsView | None:
    views = win.findChildren(QtWidgets.QGraphicsView)
    if not views:
        return None
    return sorted(views, key=lambda v: v.width() * v.height(), reverse=True)[0]

def _fit_and_zoom(view: QtWidgets.QGraphicsView, zoom: float = 1.12):
    try:
        view.setRenderHints(
            QtGui.QPainter.Antialiasing |
            QtGui.QPainter.TextAntialiasing |
            QtGui.QPainter.SmoothPixmapTransform
        )
    except Exception:
        pass
    scene = view.scene()
    if scene is None:
        return
    rect = scene.itemsBoundingRect()
    if rect.isNull():
        return
    view.fitInView(rect, QtCore.Qt.KeepAspectRatio)
    view.scale(zoom, zoom)

def _fix_action_buttons(win: QtWidgets.QWidget):
    for b in win.findChildren(QtWidgets.QPushButton):
        t = (b.text() or "").strip().lower()
        if t in ACTION_TEXTS:
            b.setMinimumHeight(44)
            b.setMinimumWidth(110)
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

def _shrink_chat_vertically(win: QtWidgets.QWidget):
    # find tab widget which has "Log" and "Chat"
    tabs = win.findChildren(QtWidgets.QTabWidget)
    for tw in tabs:
        names = set()
        for i in range(tw.count()):
            names.add((tw.tabText(i) or "").strip().lower())
        if "log" in names and "chat" in names:
            tw.setMaximumHeight(320)  # smaller vertically
            tw.setMinimumHeight(220)
            return

def _widen_board_splitter(win: QtWidgets.QWidget):
    # prefer horizontal splitter that contains the board view
    board = _find_board_view(win)
    if board is None:
        return
    splitters = win.findChildren(QtWidgets.QSplitter)
    cand = []
    for sp in splitters:
        if sp.orientation() != QtCore.Qt.Horizontal:
            continue
        # does this splitter "own" the board view?
        if board in sp.findChildren(QtWidgets.QGraphicsView) or board.parentWidget() in sp.findChildren(QtWidgets.QWidget):
            cand.append(sp)
    if not cand:
        # fallback: largest horizontal splitter
        cand = [sp for sp in splitters if sp.orientation() == QtCore.Qt.Horizontal]
        if not cand:
            return
        sp = sorted(cand, key=lambda s: s.size().width(), reverse=True)[0]
    else:
        sp = sorted(cand, key=lambda s: s.size().width(), reverse=True)[0]

    if sp.count() >= 2:
        w = max(1, sp.size().width())
        sp.setSizes([int(w * 0.78), int(w * 0.22)])

def apply_ui_tweaks(win: QtWidgets.QWidget):
    # run a bit later to ensure layouts exist
    def _go():
        _widen_board_splitter(win)
        _shrink_chat_vertically(win)
        _fix_action_buttons(win)
        view = _find_board_view(win)
        if view is not None:
            _fit_and_zoom(view, 1.12)
    QtCore.QTimer.singleShot(50, _go)
    QtCore.QTimer.singleShot(250, _go)