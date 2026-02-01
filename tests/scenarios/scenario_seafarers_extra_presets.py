from app.engine import maps
from app.engine import build_game


def scenario_seafarers_extra_presets():
    ids = ["seafarers_gold_haven", "seafarers_pirate_lanes"]
    for mid in ids:
        data = maps.get_preset_map(mid)
        maps.validate_map_data(data)
        g = build_game(seed=1234, max_players=2, map_id=mid)
        assert g.rules_config.enable_seafarers is True
    return True
