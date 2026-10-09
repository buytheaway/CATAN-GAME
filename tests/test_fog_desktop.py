"""Real Qt boundaries reject fog instead of stripping history or drawing truth."""
from copy import deepcopy
import json

import pytest

from app import ui_v6
from app.engine.exploration import FOG_DISABLED_MESSAGE, FogUnavailableError
from app.persistence.snapshots import encode_snapshot
from tests.test_desktop_ship_persistence import qt_application, desktop
from tests.test_fog_foundation import fog_game


def test_real_qt_conversion_rejects_trusted_fog_before_building_view(qt_application):
    game = fog_game()
    before = deepcopy(game)
    with pytest.raises(FogUnavailableError): ui_v6._convert_base_state(game)
    assert game == before


def test_real_qt_save_does_not_overwrite_existing_file_or_strip_fog(desktop):
    window, path = desktop
    path.write_text("existing save", encoding="utf-8")
    window.game.scenario = deepcopy(fog_game().scenario)
    with pytest.raises(FogUnavailableError): ui_v6._ui_game_to_engine_dict(window.game)
    window._save_game()
    assert path.read_text(encoding="utf-8") == "existing save"
    assert FOG_DISABLED_MESSAGE in window.log.toPlainText()


def test_real_qt_load_rejects_fog_before_replacing_or_redrawing_current_game(desktop, monkeypatch):
    window, path = desktop
    current = window.game
    game = fog_game()
    payload = encode_snapshot(game)["state"]
    data = {"rules": game.rules, "scenario": payload["scenario"], "tiles": payload["board"]["tiles"]}
    path.write_text(json.dumps(data), encoding="utf-8")
    def forbidden(*args, **kwargs): pytest.fail("Rejected fog load must not redraw hidden terrain")
    monkeypatch.setattr(window, "_draw_static_board", forbidden)
    window._load_game()
    assert window.game is current and FOG_DISABLED_MESSAGE in window.log.toPlainText()
    assert json.loads(path.read_text(encoding="utf-8")) == data
