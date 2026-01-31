from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.engine.board_geom import axial_to_pixel, build_graph_from_tiles
from app.engine.state import RESOURCES, TERRAIN_TO_RES, Tile, BoardState
from app.resource_path import resource_path


MAP_VERSION = 1
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
        "id": "seafarers_simple_1",
        "name": "Seafarers: Coastal Lanes",
        "description": "Sea lanes on the sides with larger land core.",
        "file": "seafarers_simple_1.json",
    },
    {
        "id": "seafarers_simple_2",
        "name": "Seafarers: Simple Sea Ring",
        "description": "Coastal ring of sea tiles for ships (MVP).",
        "file": "seafarers_simple_2.json",
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
    version = int(data.get("version", MAP_VERSION))
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
    for idx, t in enumerate(tiles):
        if not isinstance(t, dict):
            raise MapValidationError("tile must be object", {"index": idx})
        if "q" not in t or "r" not in t:
            raise MapValidationError("tile missing q/r", {"index": idx})
        if not isinstance(t["q"], int) or not isinstance(t["r"], int):
            raise MapValidationError("tile q/r must be int", {"index": idx})
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
            if not isinstance(num, int):
                raise MapValidationError("tile number must be int/None", {"index": idx})
            if num < 2 or num > 12 or num == 7:
                raise MapValidationError("tile number out of range", {"index": idx, "number": num})

    if has_random_terrain:
        deck = data.get("terrain_deck", DEFAULT_TERRAIN_DECK)
        if not isinstance(deck, list) or not deck:
            raise MapValidationError("terrain_deck must be list for random terrain")
    if has_random_number:
        deck = data.get("number_deck", DEFAULT_NUMBER_DECK)
        if not isinstance(deck, list) or not deck:
            raise MapValidationError("number_deck must be list for random number")

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
            if not all(isinstance(v, int) for v in edge):
                raise MapValidationError("port edge must be int pair", {"index": idx})
            if not isinstance(kind, str):
                raise MapValidationError("port type must be string", {"index": idx})

    ports_auto = data.get("ports_auto")
    if ports_auto is not None:
        if not isinstance(ports_auto, dict):
            raise MapValidationError("ports_auto must be object")
        if "count" in ports_auto and not isinstance(ports_auto.get("count"), int):
            raise MapValidationError("ports_auto.count must be int")
        if "deck" in ports_auto:
            deck = ports_auto.get("deck")
            if not isinstance(deck, list):
                raise MapValidationError("ports_auto.deck must be list")
            if not all(isinstance(x, str) for x in deck):
                raise MapValidationError("ports_auto.deck must be list[str]")

    rules = data.get("rules")
    if rules is not None and not isinstance(rules, dict):
        raise MapValidationError("rules must be object")
    if isinstance(rules, dict):
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
    if robber_tile is not None and not isinstance(robber_tile, int):
        raise MapValidationError("robber_tile must be int")
    pirate_tile = data.get("pirate_tile")
    if pirate_tile is not None and not isinstance(pirate_tile, int):
        raise MapValidationError("pirate_tile must be int")
    if robber_tile is not None and (robber_tile < 0 or robber_tile >= len(tiles)):
        raise MapValidationError("robber_tile out of range", {"robber_tile": robber_tile})
    if pirate_tile is not None and (pirate_tile < 0 or pirate_tile >= len(tiles)):
        raise MapValidationError("pirate_tile out of range", {"pirate_tile": pirate_tile})

    return data


def _materialize_tiles(
    data: Dict[str, Any],
    rng,
    size: float,
) -> Tuple[List[Tile], Optional[int]]:
    tiles_spec = data["tiles"]
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
        if number == "random":
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
        if terrain == "desert":
            desert_idx = len(tiles)
        tiles.append(Tile(q=q, r=r, terrain=str(terrain), number=number, center=center))

    return tiles, desert_idx


def _auto_ports(
    vertices: Dict[int, Tuple[float, float]],
    edge_adj_hexes: Dict[Tuple[int, int], List[int]],
    deck: List[str],
    count: int,
    rng,
) -> List[Tuple[Tuple[int, int], str]]:
    coast = [e for e, hx in edge_adj_hexes.items() if len(hx) == 1]
    if not coast:
        return []
    center = (0.0, 0.0)

    def angle_of_edge(e: Tuple[int, int]) -> float:
        a, b = e
        p = ((vertices[a][0] + vertices[b][0]) * 0.5, (vertices[a][1] + vertices[b][1]) * 0.5)
        return math.atan2(p[1] - center[1], p[0] - center[0])

    coast.sort(key=angle_of_edge)
    if len(coast) >= count:
        pick_idx = [int(i * len(coast) / count) for i in range(count)]
        coast_pick = [coast[i % len(coast)] for i in pick_idx]
    else:
        coast_pick = coast

    port_types = list(deck)
    rng.shuffle(port_types)
    port_types = port_types[: len(coast_pick)]
    return list(zip(coast_pick, port_types))


def build_board_from_map(
    data: Dict[str, Any],
    rng,
    size: float,
) -> Tuple[BoardState, int, Dict[str, Any]]:
    validate_map_data(data)
    tiles, desert_idx = _materialize_tiles(data, rng, size)
    vertices, v_hexes, edges, edge_hexes = build_graph_from_tiles(tiles, size)

    ports: List[Tuple[Tuple[int, int], str]] = []
    if data.get("ports") is not None:
        for p in data["ports"]:
            edge = p["edge"]
            a, b = int(edge[0]), int(edge[1])
            e = (a, b) if a < b else (b, a)
            if e not in edges:
                raise MapValidationError("port edge not in graph", {"edge": [a, b]})
            ports.append((e, str(p["type"])))
    else:
        ports_auto = data.get("ports_auto", {})
        count = int(ports_auto.get("count", 9))
        deck = list(ports_auto.get("deck", DEFAULT_PORT_DECK))
        ports = _auto_ports(vertices, edge_hexes, deck, count, rng)

    board = BoardState(
        tiles=tiles,
        vertices=vertices,
        vertex_adj_hexes=v_hexes,
        edges=edges,
        edge_adj_hexes=edge_hexes,
        ports=ports,
        occupied_v={},
        occupied_e={},
    )
    rules = dict(data.get("rules", {}))
    robber_tile = int(data.get("robber_tile", desert_idx if desert_idx is not None else 0))
    return board, robber_tile, rules
