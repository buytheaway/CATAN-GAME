"""Production policy for one custom Fog beta, independent of test capabilities.

Admission controls NEW selections/starts/rematches. Emergency stop separately
fences existing gameplay. Neither switch changes saved provenance or executes
rules during recovery; a codec version alone never grants beta access.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path

from app.engine.exploration import FOG_PROFILE, validate_fog_state
from app.engine.state import GameState, RulesConfig

BETA_MAP_ID = "seafarers_fog_beta_2"
BETA_RULESET = "catan-fog-beta-1"
BETA_PAUSED_MESSAGE = (
    "Fog beta gameplay is temporarily paused. Your match and seat are preserved. "
    "Return Home or reconnect after the server resumes this beta."
)


def _flag(name):
    value = os.environ.get(name, "0")
    if value not in ("0", "1"):
        raise ValueError(f"{name} must be 0 or 1")
    return value == "1"


def validate_configuration():
    """Fail startup on an ambiguous deployment flag, without printing values."""
    _flag("CATAN_FOG_BETA_ADMISSION")
    _flag("CATAN_FOG_BETA_EMERGENCY_STOP")


def emergency_stopped():
    return _flag("CATAN_FOG_BETA_EMERGENCY_STOP")


def admission_enabled():
    return _flag("CATAN_FOG_BETA_ADMISSION") and not emergency_stopped()


@lru_cache(maxsize=1)
def _recipe():
    # A shipped public recipe, NOT a materialized hidden assignment. Returning
    # only copies keeps a selected room from changing later admissions.
    path = Path(__file__).parent / "assets" / "maps" / f"{BETA_MAP_ID}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def beta_recipe():
    return deepcopy(_recipe())


def beta_descriptor():
    source = _recipe()
    return {"id": BETA_MAP_ID, "name": source["name"], "description": source["description"],
            "required_players": 2, "target_vp": 12,
            "custom_scenario": "shared_preassigned_fog_beta"}


def is_beta_source(source, map_id):
    """Exact recipe identity; callers separately reject all client uploads."""
    return (type(map_id) is str and map_id == BETA_MAP_ID and type(source) is dict
            and _same_json(source, _recipe()))


def _same_json(actual, expected):
    # JSON spelling distinguishes booleans from integers, unlike dict equality.
    try:
        return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True)
    except (TypeError, ValueError):
        return False


def is_beta_game(game):
    """Validate recorded canonical provenance, without rebuilds/RNG/rule execution.

    All eight private assignments may differ between matches, but must be the
    approved unordered pools. Coordinates, initially visible tiles, profile,
    limits and public metadata stay canonical. Discovery/history validation is
    pure and never repairs old VP, rewards or achievements.
    """
    if not isinstance(game, GameState):
        return False
    source = _recipe()
    config = RulesConfig(target_vp=12, enable_seafarers=True, enable_pirate=True,
                         enable_gold=True, enable_move_ship=True)
    if (game.map_id != BETA_MAP_ID or game.map_name != source["name"]
            or type(game.max_players) is not int or game.max_players != 2 or len(game.players) != 2
            or not _same_json(vars(game.rules_config), vars(config))
            or not (_same_json(game.rules, {**source["rules"], "discard_threshold": 7})
                    or _same_json(game.rules, source["rules"]))
            or game.rules.get("sea_frame") or game.board.ports
            or game.map_meta.get("id") != BETA_MAP_ID
            or any(game.map_meta.get(key) != source[key] for key in ("name", "description"))):
        return False
    descriptor = beta_descriptor()
    if (set(game.map_meta) - set(descriptor)
            or any(not _same_json(game.map_meta[key], descriptor[key]) for key in game.map_meta)):
        return False
    fog = game.scenario.rules.fog
    hidden = tuple(i for i, tile in enumerate(source["tiles"]) if tile["terrain"] == "fog")
    if (fog is None or fog.profile != FOG_PROFILE or fog.initially_hidden != hidden
            or game.scenario.rules.starting_islands is not None or game.scenario.rules.new_island_vp != 0
            or game.scenario.home_islands or game.scenario.awarded_islands
            or len(game.tiles) != len(source["tiles"])):
        return False
    for actual, expected in zip(game.tiles, source["tiles"]):
        if (type(actual.q) is not int or type(actual.r) is not int
                or (actual.q, actual.r) != (expected["q"], expected["r"])
                or expected["terrain"] != "fog"
                and (actual.terrain, actual.number) != (expected["terrain"], expected.get("number"))):
            return False
    if (Counter(game.tiles[i].terrain for i in hidden) != Counter(source["fog_pool"]["terrain"])
            or Counter(game.tiles[i].number for i in hidden if game.tiles[i].number is not None)
            != Counter(source["fog_pool"]["numbers"])):
        return False
    try:
        validate_fog_state(game)
    except ValueError:
        return False
    return True
