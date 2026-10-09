"""Real PySide6 offline conversion/file save/load; only file choosers are replaced."""
import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore, QtWidgets

from app import ui_v6
from app.config import GameConfig
from app.engine import rules, serialize
from tests.test_pirate_lifecycle import finish_setup
from tests.test_seafarers_ships import graph_game, move_command


@pytest.fixture(scope="module")
def qt_application():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application
    application.processEvents()


@pytest.fixture
def desktop(qt_application, monkeypatch, tmp_path):
    window = ui_v6.MainWindow(config=GameConfig(bot_enabled=False))
    path = tmp_path / "desktop-save.json"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), ""))
    yield window, path
    window.close()
    window.deleteLater()
    qt_application.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def coast():
    return graph_game([(0, 1), (0, 2), (0, 3)], buildings={0: (0, 1)})


def test_scenario_ledger_and_vp_survive_real_qt_file_roundtrip(desktop):
    from tests.test_seafarers_scenarios import scenario_game, arrive
    from tests.test_seafarers_maps import fund
    from app.engine.state import COST
    game = scenario_game()
    destination = arrive(game)
    rules.apply_cmd(game, 0, {"type": "place_settlement", "vid": destination})
    fund(game, COST["city"])
    payload = save_engine(desktop, game)
    assert payload["scenario"]["awarded_islands"] == {"0": [13]}
    restored = load_engine(desktop)
    assert restored.scenario == game.scenario
    assert [p.vp for p in restored.players] == [p.vp for p in game.players]
    assert restored.ships_built_this_turn == game.ships_built_this_turn
    before = restored.players[0].vp
    assert desktop[0]._apply_cmd({"type": "upgrade_city", "vid": destination}, pid=0) is not None
    after = serialize.from_dict(ui_v6._ui_game_to_engine_dict(desktop[0].game))
    assert after.players[0].vp == before + 1 and after.scenario == restored.scenario


def save_engine(desktop, game):
    window, path = desktop
    window.game = ui_v6._convert_base_state(game)
    assert isinstance(window, QtWidgets.QMainWindow) and isinstance(window.game, ui_v6.Game)
    assert isinstance(window.game.tiles[0].center, QtCore.QPointF)
    window._save_game()
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def load_engine(desktop):
    window, _ = desktop
    previous = window.game
    window._load_game()
    assert window.game is not previous, window.log.toPlainText()
    assert isinstance(window.game.vertices[next(iter(window.game.vertices))], QtCore.QPointF)
    return serialize.from_dict(ui_v6._ui_game_to_engine_dict(window.game))


def assert_move_rejected(game, command, reason):
    before = deepcopy(game)
    with pytest.raises(rules.RuleError, match=reason):
        rules.apply_cmd(game, game.turn, command)
    assert game == before


def test_offboard_robber_survives_real_desktop_save_load_without_drawing_last_tile(desktop, monkeypatch):
    game = rules.build_game(17, 2, map_id="seafarers_gold_haven")
    assert game.robber_tile == -1
    save_engine(desktop, game)
    restored = load_engine(desktop)
    assert restored.robber_tile == -1 and restored.robbers == [-1]
    window, _ = desktop
    # Real drawing entry must return before resolving any robber pixmap.
    def forbidden(*args, **kwargs):
        raise AssertionError("offboard robber must not draw on the last tile")
    monkeypatch.setattr(ui_v6, "_svg_tinted_pixmap", forbidden)
    window._draw_robber()


def assert_desktop_move_rejected(desktop, command, reason):
    window, _ = desktop
    before = deepcopy(ui_v6._ui_game_to_engine_dict(window.game))
    assert window._apply_cmd(command, pid=window.game.turn) is None
    assert reason in window.log.toPlainText()
    assert ui_v6._ui_game_to_engine_dict(window.game) == before


def test_newly_built_ship_stays_ineligible_after_real_qt_reload(desktop):
    g = coast()
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [0, 1]})
    save_engine(desktop, g)
    restored = load_engine(desktop)
    assert_desktop_move_rejected(desktop, move_command((0, 1), (0, 2)), "built this turn")
    assert_move_rejected(restored, move_command((0, 1), (0, 2)), "built this turn")
    assert restored.ships_built_this_turn == {(0, 1)} and not restored.ship_moved_this_turn
    assert restored.occupied_ships == g.occupied_ships


def test_second_ship_move_stays_rejected_after_real_qt_reload(desktop):
    g = coast()
    g.occupied_ships[(0, 1)] = 0  # Established old ship, not built in this turn.
    rules.apply_cmd(g, 0, move_command((0, 1), (0, 2)))
    save_engine(desktop, g)
    restored = load_engine(desktop)
    assert_desktop_move_rejected(desktop, move_command((0, 2), (0, 3)), "already moved")
    assert_move_rejected(restored, move_command((0, 2), (0, 3)), "already moved")
    assert restored.ship_moved_this_turn and restored.ships_built_this_turn == set()
    assert restored.occupied_ships == {(0, 2): 0}


@pytest.mark.parametrize("rolled", [False, True])
def test_old_qt_save_preserves_engine_conservative_lock_and_resave(desktop, rolled):
    g = coast()
    g.occupied_ships[(0, 1)], g.rolled = 0, rolled
    data = save_engine(desktop, g)
    for field in ("ships_built_this_turn", "ship_moved_this_turn"):
        data.pop(field, None)
    desktop[1].write_text(json.dumps(data), encoding="utf-8")
    expected = serialize.from_dict(data)
    assert expected.ship_moved_this_turn
    restored = load_engine(desktop)
    assert restored.ship_moved_this_turn == expected.ship_moved_this_turn
    if not restored.rolled:
        assert desktop[0]._apply_cmd({"type": "roll", "roll": 2}, pid=0) is not None
        restored = serialize.from_dict(ui_v6._ui_game_to_engine_dict(desktop[0].game))
    assert_desktop_move_rejected(desktop, move_command((0, 1), (0, 2)), "already moved")
    assert_move_rejected(restored, move_command((0, 1), (0, 2)), "already moved")
    desktop[0]._save_game()  # A second save/reload must not silently unlock legacy history.
    assert load_engine(desktop).ship_moved_this_turn


def test_end_turn_clears_history_but_preserves_ships_through_real_qt_reload(desktop):
    g = coast()
    g.occupied_ships[(0, 1)] = 0
    rules.apply_cmd(g, 0, move_command((0, 1), (0, 2)))
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [0, 3]})
    save_engine(desktop, g)
    restored = load_engine(desktop)
    assert restored.ship_moved_this_turn and restored.ships_built_this_turn == {(0, 3)}
    ships = dict(restored.occupied_ships)
    window = desktop[0]
    assert window._apply_cmd({"type": "end_turn"}, pid=0) is not None
    assert not window.game.ships_built_this_turn and not window.game.ship_moved_this_turn
    assert window._apply_cmd({"type": "roll", "roll": 2}, pid=1) is not None
    assert window._apply_cmd({"type": "end_turn"}, pid=1) is not None
    window._save_game()
    next_turn = load_engine(desktop)
    assert next_turn.turn == 0 and next_turn.occupied_ships == ships
    assert not next_turn.ships_built_this_turn and not next_turn.ship_moved_this_turn
    assert window._apply_cmd({"type": "roll", "roll": 2}, pid=0) is not None
    assert window._apply_cmd(move_command((0, 2), (0, 1)), pid=0) is not None


def test_valid_old_ship_moves_once_after_real_qt_reload(desktop):
    g = coast()
    g.occupied_ships[(0, 1)] = 0
    save_engine(desktop, g)
    restored = load_engine(desktop)
    assert not restored.ship_moved_this_turn and not restored.ships_built_this_turn
    window = desktop[0]
    assert window._apply_cmd(move_command((0, 1), (0, 2)), pid=0) is not None
    assert window.game.ship_moved_this_turn and window.game.occupied_ships == {(0, 2): 0}
    window._save_game()
    restored = load_engine(desktop)
    assert_desktop_move_rejected(desktop, move_command((0, 2), (0, 3)), "already moved")
    assert_move_rejected(restored, move_command((0, 2), (0, 3)), "already moved")


@pytest.mark.parametrize("stage", ["setup", "main"])
def test_legacy_base_save_load_stays_playable(desktop, stage):
    g = rules.build_game(42, 2, map_id="base_standard")
    if stage == "main":
        finish_setup(g)
    data = save_engine(desktop, g)
    for field in ("ships_built_this_turn", "ship_moved_this_turn"):
        data.pop(field, None)
    desktop[1].write_text(json.dumps(data), encoding="utf-8")
    restored = load_engine(desktop)
    assert not restored.ships_built_this_turn and not restored.ship_moved_this_turn
    assert restored.phase == g.phase and restored.turn == g.turn
    assert restored.board == g.board and restored.bank == g.bank
    assert [(p.name, p.res, p.vp) for p in restored.players] == [(p.name, p.res, p.vp) for p in g.players]
    assert not restored.rules_config.enable_seafarers
    if stage == "main":
        window = desktop[0]
        assert window._apply_cmd({"type": "roll", "roll": 2}, pid=g.turn) is not None
        assert window._apply_cmd({"type": "end_turn"}, pid=g.turn) is not None
