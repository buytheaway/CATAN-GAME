import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from app import dev_ui, trade_ui, ui_v6
from app.config import GameConfig


def test_ui_trade_dev_and_robber_flow():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = ui_v6.MainWindow(config=GameConfig(), on_back_to_menu=None)
    win.show()

    g = win.game
    g.phase = "main"
    g.turn = 0

    orig_dev_exec = dev_ui.DevDialog.exec
    orig_trade_exec = trade_ui.TradeDialog.exec
    orig_msg_warn = QtWidgets.QMessageBox.warning
    orig_msg_info = QtWidgets.QMessageBox.information
    orig_input_get = QtWidgets.QInputDialog.getItem

    def _no_modal(self):
        return QtWidgets.QDialog.Rejected

    dev_ui.DevDialog.exec = _no_modal
    trade_ui.TradeDialog.exec = _no_modal
    QtWidgets.QMessageBox.warning = lambda *args, **kwargs: None
    QtWidgets.QMessageBox.information = lambda *args, **kwargs: None
    try:
        dev_btn = win.findChild(QtWidgets.QAbstractButton, "btn_dev_action")
        trade_btn = win.findChild(QtWidgets.QAbstractButton, "btn_trade_bank")
        assert dev_btn is not None
        assert trade_btn is not None

        dev_btn.click()
        trade_btn.click()
        app.processEvents()

        # no-crash checks with empty resources
        for r in ui_v6.RESOURCES:
            g.players[0].res[r] = 0
        dlg_dev = dev_ui.DevDialog(win, g, 0)
        dlg_dev.on_buy()
        dlg_trade = trade_ui.TradeDialog(win, g, 0)
        dlg_trade._on_ok()
    finally:
        dev_ui.DevDialog.exec = orig_dev_exec
        trade_ui.TradeDialog.exec = orig_trade_exec
        QtWidgets.QMessageBox.warning = orig_msg_warn
        QtWidgets.QMessageBox.information = orig_msg_info
        QtWidgets.QInputDialog.getItem = orig_input_get

    # robber move with no victims
    g.pending_action = "robber_move"
    g.pending_pid = 0
    g.pending_victims = []
    g.occupied_v.clear()
    for r in ui_v6.RESOURCES:
        g.players[1].res[r] = 0
    new_tile = 1 if len(g.tiles) > 1 else 0
    g.robber_tile = 0
    win._on_hex_clicked(new_tile)
    app.processEvents()
    assert g.robber_tile == new_tile
    assert g.pending_action is None

    # robber move with victim + steal
    g.robber_tile = 0
    g.pending_action = "robber_move"
    g.pending_pid = 0
    g.pending_victims = []
    g.occupied_v.clear()
    victim_vid = None
    for vid, tiles in g.vertex_adj_hexes.items():
        if new_tile in tiles:
            victim_vid = vid
            break
    assert victim_vid is not None
    g.occupied_v[victim_vid] = (1, 1)
    for r in ui_v6.RESOURCES:
        g.players[1].res[r] = 0
        g.players[0].res[r] = 0
    g.players[1].res["wood"] = 1

    QtWidgets.QInputDialog.getItem = lambda *args, **kwargs: (g.players[1].name, True)
    win._on_hex_clicked(new_tile)
    app.processEvents()
    assert g.robber_tile == new_tile
    assert g.players[1].res["wood"] == 0
    assert g.players[0].res["wood"] == 1
    assert g.pending_action is None

    win.close()
    app.processEvents()
