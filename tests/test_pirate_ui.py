import os
from copy import deepcopy
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtWidgets

from app import ui_v6
from app.config import GameConfig
from app.engine import rules
from tests.test_pirate_lifecycle import begin_movement, pirate_game, pirate_targets


@pytest.mark.parametrize("online", [False, True])
@pytest.mark.parametrize("piece", ["pirate", "robber"])
def test_desktop_pending_map_click_chooses_piece(pirate_game, monkeypatch, online, piece):
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    begin_movement(pirate_game, "knight")
    tile = pirate_targets(pirate_game)[0] if piece == "pirate" else next(
        t for t, h in enumerate(pirate_game.tiles)
        if h.terrain != "sea" and t != pirate_game.robber_tile)
    win = ui_v6.MainWindow(config=GameConfig(map_preset="seafarers_pirate_lanes", bot_enabled=False))
    sent = []
    try:
        win.game = ui_v6._convert_base_state(pirate_game)
        win.online_mode = online
        win.you_pid = 0
        if online:
            win.online_controller = SimpleNamespace(
                cmd_move_pirate=lambda t: sent.append(("move_pirate", t)),
                cmd_move_robber=lambda t: sent.append(("move_robber", t)),
            )
        monkeypatch.setattr(QtWidgets.QInputDialog, "getItem", lambda *a: (win.game.players[1].name, True))
        win._refresh_all_dynamic()
        win._sync_ui()
        assert win.btn_pirate.isEnabled() and tile in win.overlay_hex
        win._on_hex_clicked(tile)
        if online:
            assert sent == [(f"move_{piece}", tile)]
            # Model the server update after accepting this command.
            rules.apply_cmd(win.game, 0, {"type": f"move_{piece}", "tile": tile})
            win._refresh_all_dynamic()
            win._sync_ui()
        assert getattr(win.game, f"{piece}_tile") == tile
        assert win.game.pending_action is None and not win.btn_pirate.isEnabled()
        before = deepcopy(win.game)
        win._on_hex_clicked(tile)
        win._on_pirate_hex_clicked(tile)
        assert win.game == before
        assert len(sent) == (1 if online else 0)
    finally:
        win.close()
        application.processEvents()
