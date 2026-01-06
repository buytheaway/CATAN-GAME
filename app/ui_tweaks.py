from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

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

def apply_ui_tweaks(
    view: QtWidgets.QGraphicsView | None = None,
    tabs: QtWidgets.QTabWidget | None = None,
    action_buttons: list[QtWidgets.QPushButton] | None = None,
    splitter: QtWidgets.QSplitter | None = None,
    zoom: float = 1.12,
):
    if tabs is not None:
        tabs.setMaximumHeight(320)
        tabs.setMinimumHeight(220)
    if action_buttons:
        for b in action_buttons:
            b.setMinimumHeight(44)
            b.setMinimumWidth(110)
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    if splitter is not None and splitter.count() >= 2:
        w = max(1, splitter.size().width())
        splitter.setSizes([int(w * 0.78), int(w * 0.22)])
    if view is not None:
        _fit_and_zoom(view, zoom)
