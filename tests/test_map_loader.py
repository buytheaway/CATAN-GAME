from __future__ import annotations

import pytest

from app.engine import rules
from app.engine import maps as map_loader


def test_base_preset_loads():
    data = map_loader.get_preset_map("base_standard")
    map_loader.validate_map_data(data)
    g = rules.build_game(seed=1, max_players=2, size=58.0, map_data=data)
    assert g.tiles
    assert len(g.tiles) == len(data["tiles"])
    assert g.robber_tile >= 0


def test_invalid_map_rejected():
    bad = {
        "version": 1,
        "tiles": [
            {"q": 0, "r": 0, "terrain": "lava", "number": 2},
        ],
    }
    with pytest.raises(map_loader.MapValidationError):
        map_loader.validate_map_data(bad)
