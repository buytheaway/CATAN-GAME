from __future__ import annotations

import json
import math
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.engine.board_geom import axial_to_pixel, build_graph_from_tiles
from app.engine.state import RESOURCES, TERRAIN_TO_RES, Tile, BoardState
from app.engine.topology import coastal_edges
from app.engine.scenario import parse_scenario_rules
from app.engine.exploration import initially_visible_coasts
from app.resource_path import resource_path


MAP_VERSION = 1
FOG_MAP_VERSION = 2
DEFAULT_PRESET_ID = "base_standard"

PRESET_REGISTRY = [
    {
        "id": "base_standard",
        "name": "Base Standard",
        "description": "Classic 19-hex base map with standard decks.",
        "file": "base_standard.json",
    },
    {
        "id": "base_rich_ore",
        "name": "Base: Ore Rich",
        "description": "Extra mountains, fewer fields (resource skew).",
        "file": "base_rich_ore.json",
    },
    {
        "id": "base_high_prob",
        "name": "Base: High Probability",
        "description": "More 6/8 tiles, fewer low rolls (faster economy).",
        "file": "base_high_prob.json",
    },
    {
        "id": "base_12vp",
        "name": "Base: 12 VP",
        "description": "Standard base map with victory target 12.",
        "file": "base_12vp.json",
    },
    {
        "id": "base_20vp_multi_robbers",
        "name": "Base: 20 VP (Multi-Robber)",
        "description": "Higher VP target with two robbers blocking tiles.",
        "file": "base_20vp_multi_robbers.json",
    },
    {
        "id": "community_balanced_a",
        "name": "Community Balanced A",
        "description": "Community-style layout (no adjacent 6/8).",
        "file": "community_balanced_a.json",
    },
    {
        "id": "community_balanced_b",
        "name": "Community Balanced B",
        "description": "Community-style layout (no adjacent 6/8).",
        "file": "community_balanced_b.json",
    },
    {
        "id": "community_balanced_c",
        "name": "Community Balanced C",
        "description": "Community-style layout (no adjacent 6/8).",
        "file": "community_balanced_c.json",
    },
    {
        "id": "seafarers_simple_1",
        "name": "Seafarers: Coastal Lanes",
        "description": "Sea lanes on the sides with larger land core.",
        "file": "seafarers_simple_1.json",
    },
    {
        "id": "seafarers_simple_2",
        "name": "Seafarers: Simple Sea Ring",
        "description": "A standard-size land island surrounded by a complete sea ring.",
        "file": "seafarers_simple_2.json",
    },
    {
        "id": "seafarers_gold_haven",
        "name": "Seafarers: Gold Haven",
        "description": "Two islands separated by sea, with gold, pirate and ship movement.",
        "file": "seafarers_gold_haven.json",
    },
    {
        "id": "seafarers_pirate_lanes",
        "name": "Seafarers: Pirate Lanes",
        "description": "Two islands and a navigable pirate channel, with gold and ship movement.",
        "file": "seafarers_pirate_lanes.json",
    },
]

DEFAULT_TERRAIN_DECK = (
    ["forest"] * 4
    + ["hills"] * 3
    + ["pasture"] * 4
    + ["fields"] * 4
    + ["mountains"] * 3
    + ["desert"] * 1
)

DEFAULT_NUMBER_DECK = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]

DEFAULT_PORT_DECK = ["3:1"] * 4 + [f"2:1:{r}" for r in RESOURCES]

ALLOWED_TERRAIN = set(TERRAIN_TO_RES.keys()) | {"sea"}


class MapValidationError(Exception):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


def maps_dir() -> Path:
    return resource_path("app/assets/maps")


def load_map_file(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MapValidationError("map file not found", {"path": str(path)}) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MapValidationError("map json invalid", {"path": str(path), "error": str(exc)}) from exc
    return data


def get_preset_map(name: str) -> Dict[str, Any]:
    preset = next((p for p in PRESET_REGISTRY if p["id"] == name), None)
    filename = preset["file"] if preset else f"{name}.json"
    path = maps_dir() / filename
    return load_map_file(path)


def list_presets() -> List[Dict[str, str]]:
    return [{"id": p["id"], "name": p["name"], "description": p["description"]} for p in PRESET_REGISTRY]


def get_preset_meta(name: str) -> Optional[Dict[str, str]]:
    preset = next((p for p in PRESET_REGISTRY if p["id"] == name), None)
    if not preset:
        return None
    return {"id": preset["id"], "name": preset["name"], "description": preset["description"]}


def validate_map_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise MapValidationError("map must be object")
    raw_version = data.get("version", MAP_VERSION)
    if type(raw_version) is int and raw_version == FOG_MAP_VERSION:
        return _validate_fog_recipe(data)
    version = int(raw_version)  # Preserve the existing v1 input contract.
    if version != MAP_VERSION:
        raise MapValidationError("unsupported map version", {"version": version})
    name = data.get("name")
    if name is not None and not isinstance(name, str):
        raise MapValidationError("map name must be string")
    tiles = data.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise MapValidationError("tiles must be non-empty list")

    has_random_terrain = False
    has_random_number = False
    coordinates = set()
    for idx, t in enumerate(tiles):
        if not isinstance(t, dict):
            raise MapValidationError("tile must be object", {"index": idx})
        if "q" not in t or "r" not in t:
            raise MapValidationError("tile missing q/r", {"index": idx})
        if type(t["q"]) is not int or type(t["r"]) is not int:
            raise MapValidationError("tile q/r must be int", {"index": idx})
        coordinate = (t["q"], t["r"])
        if coordinate in coordinates:
            raise MapValidationError("duplicate tile coordinates", {"index": idx})
        coordinates.add(coordinate)
        terrain = t.get("terrain")
        if terrain == "random":
            has_random_terrain = True
        elif not isinstance(terrain, str):
            raise MapValidationError("tile terrain must be string", {"index": idx})
        elif terrain not in ALLOWED_TERRAIN:
            raise MapValidationError("unknown terrain", {"index": idx, "terrain": terrain})
        num = t.get("number", None)
        if num == "random":
            has_random_number = True
        elif num is not None:
            if type(num) is not int:
                raise MapValidationError("tile number must be int/None", {"index": idx})
            if num < 2 or num > 12 or num == 7:
                raise MapValidationError("tile number out of range", {"index": idx, "number": num})
            if terrain in ("sea", "desert"):
                raise MapValidationError("sea/desert cannot have a number", {"index": idx})

    if has_random_terrain:
        deck = data.get("terrain_deck", DEFAULT_TERRAIN_DECK)
        if not isinstance(deck, list) or not deck:
            raise MapValidationError("terrain_deck must be list for random terrain")
        if any(not isinstance(t, str) or t not in ALLOWED_TERRAIN for t in deck):
            raise MapValidationError("terrain_deck contains unknown terrain")
        if len(deck) < sum(t.get("terrain") == "random" for t in tiles):
            raise MapValidationError("terrain_deck exhausted")
    if has_random_number:
        deck = data.get("number_deck", DEFAULT_NUMBER_DECK)
        if not isinstance(deck, list) or not deck:
            raise MapValidationError("number_deck must be list for random number")
        if any(type(n) is not int or n < 2 or n > 12 or n == 7 for n in deck):
            raise MapValidationError("number_deck contains invalid number")

    ports = data.get("ports")
    if ports is not None:
        if not isinstance(ports, list):
            raise MapValidationError("ports must be list")
        for idx, p in enumerate(ports):
            if not isinstance(p, dict):
                raise MapValidationError("port must be object", {"index": idx})
            edge = p.get("edge")
            kind = p.get("type")
            if not isinstance(edge, list) or len(edge) != 2:
                raise MapValidationError("port edge must be list[2]", {"index": idx})
            if not all(type(v) is int for v in edge):
                raise MapValidationError("port edge must be int pair", {"index": idx})
            if not isinstance(kind, str):
                raise MapValidationError("port type must be string", {"index": idx})
            if kind not in DEFAULT_PORT_DECK:
                raise MapValidationError("unknown port type", {"index": idx})

    ports_auto = data.get("ports_auto")
    if ports_auto is not None:
        if not isinstance(ports_auto, dict):
            raise MapValidationError("ports_auto must be object")
        if "count" in ports_auto and (type(ports_auto["count"]) is not int or ports_auto["count"] < 0):
            raise MapValidationError("ports_auto.count must be nonnegative int")
        if "deck" in ports_auto:
            deck = ports_auto.get("deck")
            if not isinstance(deck, list):
                raise MapValidationError("ports_auto.deck must be list")
            if not all(isinstance(x, str) for x in deck):
                raise MapValidationError("ports_auto.deck must be list[str]")
            if any(kind not in DEFAULT_PORT_DECK for kind in deck):
                raise MapValidationError("ports_auto.deck contains unknown port type")

    rules = data.get("rules")
    if rules is not None and not isinstance(rules, dict):
        raise MapValidationError("rules must be object")
    if isinstance(rules, dict):
        try:
            config = parse_scenario_rules(rules)
            if config.fog is not None:
                raise ValueError("Fog requires a version 2 recipe")
        except ValueError as exc:
            raise MapValidationError(str(exc)) from exc
        if "target_vp" in rules and not isinstance(rules.get("target_vp"), int):
            raise MapValidationError("rules.target_vp must be int")
        if "victory_points" in rules and not isinstance(rules.get("victory_points"), int):
            raise MapValidationError("rules.victory_points must be int")
        if "robber_count" in rules and not isinstance(rules.get("robber_count"), int):
            raise MapValidationError("rules.robber_count must be int")
        if "enable_seafarers" in rules and not isinstance(rules.get("enable_seafarers"), bool):
            raise MapValidationError("rules.enable_seafarers must be bool")
        if "max_ships" in rules and not isinstance(rules.get("max_ships"), int):
            raise MapValidationError("rules.max_ships must be int")
        if "enable_pirate" in rules and not isinstance(rules.get("enable_pirate"), bool):
            raise MapValidationError("rules.enable_pirate must be bool")
        if "enable_gold" in rules and not isinstance(rules.get("enable_gold"), bool):
            raise MapValidationError("rules.enable_gold must be bool")
        if "enable_move_ship" in rules and not isinstance(rules.get("enable_move_ship"), bool):
            raise MapValidationError("rules.enable_move_ship must be bool")
        limits = rules.get("limits")
        if limits is not None:
            if not isinstance(limits, dict):
                raise MapValidationError("rules.limits must be object")
            for key in ("roads", "settlements", "cities", "ships"):
                if key in limits and not isinstance(limits.get(key), int):
                    raise MapValidationError("rules.limits values must be int", {"key": key})

    robber_tile = data.get("robber_tile")
    if robber_tile is not None and type(robber_tile) is not int:
        raise MapValidationError("robber_tile must be int")
    pirate_tile = data.get("pirate_tile")
    if pirate_tile is not None and type(pirate_tile) is not int:
        raise MapValidationError("pirate_tile must be int")
    offboard = robber_tile == -1 and isinstance(rules, dict) and rules.get("enable_seafarers") is True
    if robber_tile is not None and not offboard and (robber_tile < 0 or robber_tile >= len(tiles)):
        raise MapValidationError("robber_tile out of range", {"robber_tile": robber_tile})
    if pirate_tile is not None and (pirate_tile < 0 or pirate_tile >= len(tiles)):
        raise MapValidationError("pirate_tile out of range", {"pirate_tile": pirate_tile})

    return data


def fog_slots(data: Dict[str, Any]) -> Tuple[int, ...]:
    return tuple(i for i, t in enumerate(data["tiles"]) if t.get("terrain") == "fog")


def _validate_fog_recipe(data: Dict[str, Any]) -> Dict[str, Any]:
    """Only a public recipe, never a client-supplied hidden assignment/seed."""
    allowed = {"version", "name", "description", "tiles", "rules", "fog_pool",
               "ports", "ports_auto", "robber_tile", "pirate_tile"}
    if set(data) - allowed:
        raise MapValidationError("Unknown fog recipe fields")
    tiles, rules, pool = data.get("tiles"), data.get("rules"), data.get("fog_pool")
    if type(tiles) is not list or not tiles or type(rules) is not dict:
        raise MapValidationError("Fog recipe requires tiles and explicit rules")
    if type(pool) is not dict or set(pool) != {"terrain", "numbers"}:
        raise MapValidationError("Fog recipe requires exact terrain and number pools")
    for tile in tiles:
        if type(tile) is not dict or set(tile) - {"q", "r", "terrain", "number"}:
            raise MapValidationError("Unknown fog tile fields")
        if type(tile.get("terrain")) is not str or tile.get("terrain") not in ALLOWED_TERRAIN | {"fog"}:
            raise MapValidationError("Invalid fog recipe terrain")
        if tile.get("terrain") == "fog" and tile.get("number") is not None:
            raise MapValidationError("Fog slots cannot specify number assignments")
        if tile.get("terrain") not in ("sea", "desert", "fog") and tile.get("number") is None:
            raise MapValidationError("Visible producing tiles require numbers")
    hidden = fog_slots(data)
    terrain, numbers = pool["terrain"], pool["numbers"]
    if (not hidden or type(terrain) is not list or len(terrain) != len(hidden)
            or any(type(t) is not str or t not in ALLOWED_TERRAIN for t in terrain)):
        raise MapValidationError("Fog terrain pool must exactly fill the hidden slots")
    if (type(numbers) is not list or len(numbers) != sum(t not in ("sea", "desert") for t in terrain)
            or any(type(n) is not int or n not in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12) for n in numbers)):
        raise MapValidationError("Fog number pool must exactly fill the producing slots")
    try:
        config = parse_scenario_rules(rules, fog_slots=hidden)
    except ValueError as exc:
        raise MapValidationError(str(exc)) from exc
    if config.fog is None:
        raise MapValidationError("Fog recipe requires an explicit fog profile")
    if ("gold" in terrain or any(t.get("terrain") == "gold" for t in tiles)) and rules.get("enable_gold") is not True:
        raise MapValidationError("Fog gold requires Gold support")
    for key in ("robber_tile", "pirate_tile"):
        index = data.get(key)
        if index is not None and (type(index) is not int or index in hidden):
            raise MapValidationError("Initial robber/pirate must use visible territory")
    # Reuse v1's structural/rule/port validation with neutral, visible-only sea
    # placeholders. This does not consume randomness or inspect hidden terrain.
    visible = deepcopy(data)
    visible["version"] = MAP_VERSION
    visible.pop("fog_pool")
    visible["rules"]["scenario"].pop("fog")
    for i in hidden:
        visible["tiles"][i]["terrain"] = "sea"
    validate_map_data(visible)
    return data


def _materialize_tiles(
    data: Dict[str, Any],
    rng,
    size: float,
    fog_rng=None,
) -> Tuple[List[Tile], Optional[int]]:
    tiles_spec = data["tiles"]
    hidden = fog_slots(data)
    fog_terrain, fog_numbers = [], []
    if hidden:
        fog_terrain, fog_numbers = list(data["fog_pool"]["terrain"]), list(data["fog_pool"]["numbers"])
        private_rng = fog_rng if fog_rng is not None else random.SystemRandom()
        private_rng.shuffle(fog_terrain)
        private_rng.shuffle(fog_numbers)
    fog_terrain_idx = fog_number_idx = 0
    terrain_deck = list(data.get("terrain_deck", DEFAULT_TERRAIN_DECK))
    number_deck = list(data.get("number_deck", DEFAULT_NUMBER_DECK))

    has_random_terrain = any(t.get("terrain") == "random" for t in tiles_spec)
    has_random_number = any(t.get("number") == "random" for t in tiles_spec)
    if has_random_terrain:
        rng.shuffle(terrain_deck)
    if has_random_number:
        rng.shuffle(number_deck)

    terrain_idx = 0
    number_idx = 0
    tiles: List[Tile] = []
    desert_idx = None

    for idx, spec in enumerate(tiles_spec):
        terrain = spec.get("terrain")
        if terrain == "random":
            if terrain_idx >= len(terrain_deck):
                raise MapValidationError("terrain_deck exhausted", {"index": idx})
            terrain = terrain_deck[terrain_idx]
            terrain_idx += 1

        number = spec.get("number", None)
        if terrain == "fog":
            terrain = fog_terrain[fog_terrain_idx]
            fog_terrain_idx += 1
            if terrain not in ("sea", "desert"):
                number = fog_numbers[fog_number_idx]
                fog_number_idx += 1
        elif number == "random":
            if terrain in ("desert", "sea"):
                number = None
            else:
                if number_idx >= len(number_deck):
                    raise MapValidationError("number_deck exhausted", {"index": idx})
                number = number_deck[number_idx]
                number_idx += 1
        elif number is not None:
            number = int(number)

        q = int(spec["q"])
        r = int(spec["r"])
        center = axial_to_pixel(q, r, size)
        if terrain == "desert" and idx not in hidden:
            desert_idx = len(tiles)
        tiles.append(Tile(q=q, r=r, terrain=str(terrain), number=number, center=center))

    return tiles, desert_idx


def _auto_ports(
    board: BoardState,
    deck: List[str],
    count: int,
    rng,
    coast=None,
) -> List[Tuple[Tuple[int, int], str]]:
    coast = sorted(coastal_edges(board) if coast is None else coast)
    count = min(count, len(deck))
    if not coast or count == 0:
        return []
    vertices = board.vertices
    center = (0.0, 0.0)

    def angle_of_edge(e: Tuple[int, int]) -> float:
        a, b = e
        p = ((vertices[a][0] + vertices[b][0]) * 0.5, (vertices[a][1] + vertices[b][1]) * 0.5)
        return math.atan2(p[1] - center[1], p[0] - center[0])

    coast.sort(key=angle_of_edge)
    pick_idx = [int(i * len(coast) / count) for i in range(count)]
    coast_pick, used_vertices = [], set()
    # Try evenly spaced positions first, then fill from the same deterministic
    # ordering. Small custom coasts may support fewer than the requested ports.
    for edge in [coast[i] for i in pick_idx] + coast:
        if used_vertices.isdisjoint(edge):
            coast_pick.append(edge)
            used_vertices.update(edge)
        if len(coast_pick) == count:
            break

    port_types = list(deck)
    rng.shuffle(port_types)
    port_types = port_types[: len(coast_pick)]
    return list(zip(coast_pick, port_types))


def build_board_from_map(
    data: Dict[str, Any],
    rng,
    size: float,
    *, fog_rng=None,
) -> Tuple[BoardState, int, Dict[str, Any]]:
    validate_map_data(data)
    tiles, desert_idx = _materialize_tiles(data, rng, size, fog_rng)
    vertices, v_hexes, edges, edge_hexes = build_graph_from_tiles(tiles, size)

    board = BoardState(tiles=tiles, vertices=vertices, vertex_adj_hexes=v_hexes,
                       edges=edges, edge_adj_hexes=edge_hexes)
    ports: List[Tuple[Tuple[int, int], str]] = []
    hidden = fog_slots(data)
    coast = initially_visible_coasts(board, hidden) if hidden else coastal_edges(board)
    if data.get("ports") is not None:
        used_vertices = set()
        for p in data["ports"]:
            edge = p["edge"]
            a, b = int(edge[0]), int(edge[1])
            e = (a, b) if a < b else (b, a)
            if e not in edges:
                raise MapValidationError("port edge not in graph", {"edge": [a, b]})
            if e not in coast:
                raise MapValidationError("port must be on a land coastline", {"edge": [a, b]})
            if not used_vertices.isdisjoint(e):
                raise MapValidationError("ports cannot share an endpoint", {"edge": [a, b]})
            used_vertices.update(e)
            ports.append((e, str(p["type"])))
    else:
        ports_auto = data.get("ports_auto", {})
        count = int(ports_auto.get("count", 9))
        deck = list(ports_auto.get("deck", DEFAULT_PORT_DECK))
        ports = _auto_ports(board, deck, count, rng, coast)

    board.ports = ports
    rules = dict(data.get("rules", {}))
    robber_tile = data.get("robber_tile")
    if robber_tile is None:
        robber_tile = desert_idx if desert_idx is not None else (-1 if rules.get("enable_seafarers") else 0)
    if robber_tile != -1 and tiles[robber_tile].terrain == "sea":
        raise MapValidationError("robber must start on land or offboard")
    pirate_tile = data.get("pirate_tile")
    if pirate_tile is not None and tiles[pirate_tile].terrain != "sea":
        raise MapValidationError("pirate must start on sea")
    return board, robber_tile, rules
