"""Closed JSON projections. No rules, assignments, or recovery side effects."""
from .exploration import tile_is_known


RULE_FIELDS = {
    "target_vp": int, "discard_threshold": int, "max_roads": int,
    "max_settlements": int, "max_cities": int, "robber_count": int,
    "enable_seafarers": bool, "max_ships": int, "enable_pirate": bool,
    "enable_gold": bool, "enable_move_ship": bool,
}


def public_map_metadata(source) -> dict:
    if type(source) is not dict:
        return {}
    result = {key: source[key] for key in ("id", "name", "description")
              if type(source.get(key)) is str}
    # Public, fixed registry facts; arbitrary map metadata remains closed.
    counts = {"seafarers_official_new_shores_3": 3, "seafarers_official_new_shores_4": 4}
    count = counts.get(result.get("id"))
    if (count is not None and source.get("official_scenario") == "heading_for_new_shores"
            and type(source.get("required_players")) is int and source["required_players"] == count):
        result.update(official_scenario="heading_for_new_shores", required_players=count)
    return result


def public_rules_config(source) -> dict:
    data = source if type(source) is dict else vars(source)
    return {key: data[key] for key, kind in RULE_FIELDS.items() if type(data.get(key)) is kind}


def fog_scenario(game) -> dict:
    # No assignment digest, ledger, continuation, pools or island derivation.
    return {"rules": {"starting_islands": None, "new_island_vp": 0,
                      "fog": {"profile": game.scenario.rules.fog.profile}},
            "home_islands": {}, "awarded_islands": {}, "fog": {"visibility": "shared"}}


def fog_tiles(game) -> list[dict]:
    return [{"index": index, "q": tile.q, "r": tile.r,
             "center": [tile.center[0], tile.center[1]],
             "visibility": "revealed" if tile_is_known(game, index) else "hidden",
             "terrain": tile.terrain if tile_is_known(game, index) else "fog",
             "number": tile.number if tile_is_known(game, index) else None}
            for index, tile in enumerate(game.tiles)]
