"""Full trusted GameState codec; never use this payload as a client snapshot.

Only engine state is encoded here. Room ownership, transport, dice bag, timer,
chat and personalized event history belong to the separate durable Room adapter.
No map generation, rules execution, randomness or dynamic classes on restore.
"""
from __future__ import annotations

from dataclasses import fields
import json
import math
import re
from typing import Any, Callable

from app.engine.state import (
    AchievementState, BoardState, DEV_TYPES, GameState, PlayerState,
    RESOURCES, RulesConfig, ScenarioRules, ScenarioState, Tile, TradeOffer,
)
from app.engine.scenario import validate_scenario_state

SNAPSHOT_VERSION = 3
ENGINE_COMPATIBILITY = 2
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_JSON_NODES = 200_000
MAX_JSON_DEPTH = 64
_ID_KEY = re.compile(r"0|[1-9][0-9]*")
Decoder = Callable[[Any, str], Any]


class SnapshotError(ValueError):
    """A snapshot cannot be safely encoded or restored."""


class SnapshotValidationError(SnapshotError):
    """Malformed storage data or invalid internal references."""


class UnsupportedSnapshotVersion(SnapshotError):
    """An explicit decoder/migration is required for this format version."""


class UnsupportedEngineCompatibility(SnapshotError):
    """This engine does not support the snapshot's compatibility contract."""


def _fail(path: str, reason: str) -> None:
    # Never put payload values (potential game secrets) in error messages.
    raise SnapshotValidationError(f"{path}: {reason}")


def _json_copy(value: Any) -> Any:
    """Validate JSON-only values, enforce a budget and detach every collection."""
    nodes = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("snapshot", "JSON structure exceeds limits")
        if item is None or type(item) in (str, bool, int):
            if type(item) is str:
                try:
                    size = len(item.encode("utf-8"))
                except UnicodeError:
                    _fail("snapshot", "string is not valid UTF-8")
                if size > MAX_JSON_BYTES:
                    _fail("snapshot", "string exceeds limits")
            return item
        if type(item) is float:
            if not math.isfinite(item):
                _fail("snapshot", "non-finite number")
            return item
        if type(item) is list:
            return [visit(x, depth + 1) for x in item]
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                _fail("snapshot", "JSON object keys must be strings")
            return {visit(k, depth + 1): visit(item[k], depth + 1) for k in sorted(item)}
        _fail("snapshot", "expected JSON-only data")

    return visit(value, 0)


def _integer(value: Any, path: str) -> int:
    if type(value) is not int:
        _fail(path, "expected integer (not bool/float/string)")
    return value


def _nonnegative(value: Any, path: str) -> int:
    value = _integer(value, path)
    if value < 0:
        _fail(path, "expected nonnegative integer")
    return value


def _positive(value: Any, path: str) -> int:
    value = _integer(value, path)
    if value < 1:
        _fail(path, "expected positive integer")
    return value


def _number(value: Any, path: str) -> int | float:
    if type(value) not in (int, float):
        _fail(path, "expected finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        _fail(path, "number is outside finite coordinate range")
    if not finite:
        _fail(path, "expected finite number")
    return value  # Preserve int/float distinction in coordinates and size.


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _fail(path, "expected boolean")
    return value


def _string(value: Any, path: str) -> str:
    if type(value) is not str:
        _fail(path, "expected string")
    return value


def _optional(decoder: Decoder) -> Decoder:
    return lambda value, path: None if value is None else decoder(value, path)


def _choice(*choices: Any) -> Decoder:
    def decode(value: Any, path: str) -> Any:
        if not any(type(value) is type(c) and value == c for c in choices):
            _fail(path, "unsupported enum value")
        return value
    return decode


def _list(decoder: Decoder) -> Decoder:
    def decode(value: Any, path: str) -> list:
        if type(value) is not list:
            _fail(path, "expected array")
        return [decoder(x, f"{path}[{i}]") for i, x in enumerate(value)]
    return decode


def _pair(first: Decoder, second: Decoder) -> Decoder:
    def decode(value: Any, path: str) -> tuple:
        if type(value) is not list or len(value) != 2:
            _fail(path, "expected two-element array")
        return first(value[0], path + "[0]"), second(value[1], path + "[1]")
    return decode


def _id_key(key: str, path: str) -> int:
    if not _ID_KEY.fullmatch(key) or len(key) > 16:
        _fail(path, "expected canonical nonnegative ID key")
    return int(key)


def _edge(value: Any, path: str) -> tuple[int, int]:
    a, b = _pair(_nonnegative, _nonnegative)(value, path)
    if a >= b:
        _fail(path, "edge endpoints must be distinct and ordered")
    return a, b


def _edge_key(key: str, path: str) -> tuple[int, int]:
    parts = key.split(",")
    if len(parts) != 2:
        _fail(path, "expected canonical edge key")
    return _edge([_id_key(x, path) for x in parts], path)


def _map(key_decoder: Callable, value_decoder: Decoder) -> Decoder:
    def decode(value: Any, path: str) -> dict:
        if type(value) is not dict:
            _fail(path, "expected object")
        result = {}
        for key, item in value.items():
            decoded_key = key_decoder(key, path)
            if decoded_key in result:
                _fail(path, "duplicate normalized key")
            result[decoded_key] = value_decoder(item, path + ".value")
        return result
    return decode


def _unique_set(decoder: Decoder) -> Decoder:
    def decode(value: Any, path: str) -> set:
        items = _list(decoder)(value, path)
        result = set(items)
        if len(items) != len(result):
            _fail(path, "duplicate IDs")
        return result
    return decode


def _record(value: Any, schema: dict[str, Decoder], path: str) -> dict:
    if type(value) is not dict or set(value) != set(schema):
        _fail(path, "missing required fields or unknown fields")
    return {key: decoder(value[key], path + "." + key) for key, decoder in schema.items()}


def _json_object(value: Any, path: str) -> dict:
    if type(value) is not dict:
        _fail(path, "expected JSON object")
    return value  # Already recursively copied/validated at the envelope boundary.


def _resources(value: Any, path: str) -> dict:
    return _record(value, {r: _nonnegative for r in RESOURCES}, path)


def _trade_resources(value: Any, path: str) -> dict:
    if type(value) is not dict or not set(value) <= set(RESOURCES):
        _fail(path, "expected resource quantities")
    return {r: _nonnegative(q, path) for r, q in value.items()}


def _dev_card(value: Any, path: str) -> dict:
    return _record(value, {"type": _choice(*DEV_TYPES), "new": _boolean}, path)


_TILE = {"q": _integer, "r": _integer, "terrain": _string,
         "number": _optional(_choice(2, 3, 4, 5, 6, 8, 9, 10, 11, 12)),
         "center": _pair(_number, _number)}
_PLAYER = {"pid": _nonnegative, "name": _string, "res": _resources,
           "vp": _nonnegative, "knights_played": _nonnegative,
           "dev_cards": _list(_dev_card)}
_RULES = {"target_vp": _integer, "discard_threshold": _positive,
          "max_roads": _integer, "max_settlements": _integer, "max_cities": _integer,
          "robber_count": _positive, "enable_seafarers": _boolean,
          "max_ships": _nonnegative, "enable_pirate": _boolean,
          "enable_gold": _boolean, "enable_move_ship": _boolean}
_ACHIEVEMENTS = {"longest_road_owner": _optional(_nonnegative), "longest_road_len": _nonnegative,
                 "largest_army_owner": _optional(_nonnegative), "largest_army_size": _nonnegative}
_OFFER = {"offer_id": _positive, "from_pid": _nonnegative, "to_pid": _optional(_nonnegative),
          "give": _trade_resources, "get": _trade_resources,
          "status": _choice("active", "accepted", "declined", "canceled"),
          "created_turn": _nonnegative, "created_tick": _nonnegative}
_BOARD = {"tiles": _list(lambda v, p: Tile(**_record(v, _TILE, p))),
          "vertices": _map(_id_key, _pair(_number, _number)),
          "vertex_adj_hexes": _map(_id_key, _list(_nonnegative)),
          "edges": _unique_set(_edge), "edge_adj_hexes": _map(_edge_key, _list(_nonnegative)),
          "ports": _list(_pair(_edge, _string)),
          "occupied_v": _map(_id_key, _pair(_nonnegative, _choice(1, 2))),
          "occupied_e": _map(_edge_key, _nonnegative),
          "occupied_ships": _map(_edge_key, _nonnegative)}
_GAME_V1 = {
    "seed": _integer, "size": _number, "max_players": _positive,
    "map_name": _string, "map_id": _string, "map_meta": _json_object, "rules": _json_object,
    "rules_config": lambda v, p: RulesConfig(**_record(v, _RULES, p)),
    "board": lambda v, p: BoardState(**_record(v, _BOARD, p)),
    "players": _list(lambda v, p: PlayerState(**_record(v, _PLAYER, p))), "bank": _resources,
    "turn": _nonnegative, "phase": _choice("setup", "main"), "rolled": _boolean,
    "setup_order": _list(_nonnegative), "setup_idx": _nonnegative,
    "setup_need": _choice("settlement", "road"), "setup_anchor_vid": _optional(_nonnegative),
    "last_roll": _optional(_choice(*range(2, 13))), "robber_tile": _nonnegative,
    "robbers": _list(_nonnegative), "pirate_tile": _optional(_nonnegative),
    "pending_action": _optional(_choice("discard", "robber_move", "choose_gold")),
    "pending_pid": _optional(_nonnegative), "pending_victims": _list(_nonnegative),
    "discard_required": _map(_id_key, _nonnegative), "discard_submitted": _unique_set(_nonnegative),
    "pending_gold": _map(_id_key, _nonnegative), "pending_gold_queue": _list(_nonnegative),
    "achievements": lambda v, p: AchievementState(**_record(v, _ACHIEVEMENTS, p)),
    "game_over": _boolean, "winner_pid": _optional(_nonnegative),
    "dev_deck": _list(_choice(*DEV_TYPES)), "dev_played_turn": _map(_id_key, _boolean),
    "free_roads": _map(_id_key, _nonnegative), "roll_history": _list(_choice(*range(2, 13))),
    "tick": _nonnegative, "state_version": _positive,
    "trade_offers": _list(lambda v, p: TradeOffer(**_record(v, _OFFER, p))),
    "trade_offer_next_id": _positive,
}
_GAME_V2 = {**_GAME_V1, "robber_tile": _integer, "robbers": _list(_integer),
         "ships_built_this_turn": _unique_set(_edge),
         "ship_moved_this_turn": _boolean}
_SCENARIO_RULES = {"starting_islands": _optional(lambda v, p: tuple(_list(_nonnegative)(v, p))),
                   "new_island_vp": _nonnegative}
_SCENARIO = {"rules": lambda v, p: ScenarioRules(**_record(v, _SCENARIO_RULES, p)),
             "home_islands": _map(_id_key, _unique_set(_nonnegative)),
             "awarded_islands": _map(_id_key, _unique_set(_nonnegative))}
_GAME = {**_GAME_V2, "scenario": lambda v, p: ScenarioState(**_record(v, _SCENARIO, p))}
# Also used as a fail-closed field-coverage guard; never infer schema from payload.
_SCHEMAS = [(GameState, _GAME), (BoardState, _BOARD), (PlayerState, _PLAYER),
            (Tile, _TILE), (RulesConfig, _RULES), (AchievementState, _ACHIEVEMENTS), (TradeOffer, _OFFER),
            (ScenarioRules, _SCENARIO_RULES), (ScenarioState, _SCENARIO)]


def _check_schema_coverage() -> None:
    for cls, schema in _SCHEMAS:
        if {f.name for f in fields(cls)} != set(schema):
            _fail("codec", "engine fields changed; explicit codec compatibility review required")


def _validate_references(g: GameState) -> None:
    """Check structure/identity, not gameplay legality or recomputed achievements."""
    pids, tids, vids, edges = set(range(len(g.players))), set(range(len(g.tiles))), set(g.vertices), g.edges

    def ref(value: Any, ids: set, path: str) -> None:
        if value is not None and value not in ids:
            _fail(path, "reference does not exist")

    if len(g.players) != g.max_players or [p.pid for p in g.players] != list(range(g.max_players)):
        _fail("state.players", "expected unique sequential player IDs matching max_players")
    if not g.tiles or g.size <= 0:
        _fail("state.board", "empty board or nonpositive size")
    if set(g.vertex_adj_hexes) != vids or set(g.edge_adj_hexes) != edges:
        _fail("state.board", "adjacency keys must match stored topology")
    for edge in edges:
        for vid in edge:
            ref(vid, vids, "state.board.edges")
    for adjacency in (g.vertex_adj_hexes, g.edge_adj_hexes):
        for tiles in adjacency.values():
            if not tiles or len(set(tiles)) != len(tiles):
                _fail("state.board.adjacency", "empty or duplicate tile references")
            for tile in tiles:
                ref(tile, tids, "state.board.adjacency")
    for edge, _ in g.ports:
        ref(edge, edges, "state.board.ports")
    for vid, (pid, _) in g.occupied_v.items():
        ref(vid, vids, "state.board.occupied_v")
        ref(pid, pids, "state.board.occupied_v.owner")
    for occupancy in (g.occupied_e, g.occupied_ships):
        for edge, pid in occupancy.items():
            ref(edge, edges, "state.board.occupancy")
            ref(pid, pids, "state.board.occupancy.owner")
    if set(g.occupied_e) & set(g.occupied_ships):
        _fail("state.board", "road and ship occupy the same edge")
    if g.phase == "setup" and (g.ships_built_this_turn or g.ship_moved_this_turn):
        _fail("state.ship_lifecycle", "setup cannot retain main-turn ship lifecycle")
    for edge in g.ships_built_this_turn:
        ref(edge, edges, "state.ships_built_this_turn")
        if g.occupied_ships.get(edge) != g.turn:
            _fail("state.ships_built_this_turn", "built ship must belong to current player")
    for field in ("turn", "pending_pid", "winner_pid"):
        ref(getattr(g, field), pids, "state." + field)
    for owner in (g.longest_road_owner, g.largest_army_owner):
        ref(owner, pids, "state.achievements.owner")
    for ids in (g.setup_order, g.pending_victims, g.discard_required, g.discard_submitted,
                g.pending_gold, g.pending_gold_queue, g.dev_played_turn, g.free_roads):
        for pid in ids:
            ref(pid, pids, "state.player_reference")
    if g.setup_idx > len(g.setup_order) or (g.phase == "setup" and g.setup_idx == len(g.setup_order)):
        _fail("state.setup_idx", "invalid setup cursor")
    ref(g.setup_anchor_vid, vids, "state.setup_anchor_vid")
    # V2 can store the no-desert Seafarers initial position. V1 remains frozen.
    # Historical on-board positions/ports are not reconciled during recovery.
    robber_ids = tids | {-1} if g.rules_config.enable_seafarers else tids
    for tile in [g.robber_tile, *g.robbers]:
        ref(tile, robber_ids, "state.robber")
    for tile in [g.pirate_tile]:
        ref(tile, tids, "state.robber_or_pirate")
    try:
        validate_scenario_state(g)
    except ValueError:
        _fail("state.scenario.rules", "invalid scenario configuration or island references")
    offer_ids = set()
    for offer in g.trade_offers:
        if offer.offer_id in offer_ids or offer.offer_id >= g.trade_offer_next_id:
            _fail("state.trade_offers", "duplicate offer ID or invalid next ID")
        offer_ids.add(offer.offer_id)
        for pid in (offer.from_pid, offer.to_pid, offer.created_turn):
            ref(pid, pids, "state.trade_offers.player")


def _encode_record(value: Any, schema: dict) -> dict:
    expected = next(cls for cls, known in _SCHEMAS if known is schema)
    if type(value) is not expected:
        _fail("state", "expected known engine dataclass")
    return {key: getattr(value, key) for key in schema}


def _encode_map(value: dict, edge_keys: bool = False, tuple_values: bool = False) -> dict:
    if type(value) is not dict:
        _fail("state.map", "expected dictionary")
    result = {}
    for key in value:
        if edge_keys:
            if type(key) is not tuple or len(key) != 2 or any(type(x) is not int for x in key):
                _fail("state.map", "expected tuple edge keys")
            wire_key = f"{key[0]},{key[1]}"
        else:
            if type(key) is not int:
                _fail("state.map", "expected integer keys")
            wire_key = str(key)
        item = value[key]
        if tuple_values:
            if type(item) is not tuple or len(item) != 2:
                _fail("state.map", "expected tuple pair values")
            item = list(item)
        result[wire_key] = item
    return result


def encode_snapshot(game: GameState) -> dict:
    """Detached JSON-compatible, full PRIVATE envelope. Does not modify game."""
    if type(game) is not GameState:
        _fail("state", "expected shared engine GameState")
    _check_schema_coverage()
    state = _encode_record(game, _GAME)
    board = state["board"] = _encode_record(game.board, _BOARD)
    if any(type(value) is not list for value in (game.tiles, game.players, game.trade_offers)):
        _fail("state", "expected engine lists")
    if any(type(value) is not set for value in
           (game.edges, game.discard_submitted, game.ships_built_this_turn)):
        _fail("state", "expected engine sets")
    if any(type(edge) is not tuple for edge in game.edges):
        _fail("state.board.edges", "expected tuple edges")
    for edge in game.edges:
        _edge(list(edge), "state.board.edges")
    for edge in game.ships_built_this_turn:
        if type(edge) is not tuple:
            _fail("state.ships_built_this_turn", "expected tuple edges")
        _edge(list(edge), "state.ships_built_this_turn")
    if type(game.ports) is not list or any(
        type(port) is not tuple or len(port) != 2 or type(port[0]) is not tuple
        for port in game.ports
    ):
        _fail("state.board.ports", "expected list of tuple ports")
    state["rules_config"] = _encode_record(game.rules_config, _RULES)
    scenario = state["scenario"] = _encode_record(game.scenario, _SCENARIO)
    scenario["rules"] = _encode_record(game.scenario.rules, _SCENARIO_RULES)
    starts = game.scenario.rules.starting_islands
    if starts is not None and type(starts) is not tuple:
        _fail("state.scenario.rules", "expected tuple starting islands")
    scenario["rules"]["starting_islands"] = None if starts is None else list(starts)
    for field in ("home_islands", "awarded_islands"):
        history = getattr(game.scenario, field)
        if type(history) is not dict or any(type(ids) is not set for ids in history.values()):
            _fail("state.scenario", "expected island history sets")
        scenario[field] = _encode_map(history)
        scenario[field] = {pid: sorted(ids) for pid, ids in scenario[field].items()}
    state["achievements"] = _encode_record(game.achievements, _ACHIEVEMENTS)
    state["players"] = [_encode_record(p, _PLAYER) for p in game.players]
    state["trade_offers"] = [_encode_record(o, _OFFER) for o in game.trade_offers]
    board["tiles"] = []
    for tile in game.tiles:
        record = _encode_record(tile, _TILE)
        if type(tile.center) is not tuple:
            _fail("state.board.tiles.center", "expected tuple coordinates")
        record["center"] = list(tile.center)
        board["tiles"].append(record)
    board["edges"] = [list(edge) for edge in sorted(game.edges)]
    board["ports"] = [[list(edge), kind] for edge, kind in game.ports]
    for field in ("vertices", "vertex_adj_hexes", "occupied_v"):
        board[field] = _encode_map(getattr(game.board, field), tuple_values=field != "vertex_adj_hexes")
    for field in ("edge_adj_hexes", "occupied_e", "occupied_ships"):
        board[field] = _encode_map(getattr(game.board, field), edge_keys=True)
    for field in ("discard_required", "pending_gold", "dev_played_turn", "free_roads"):
        state[field] = _encode_map(getattr(game, field))
    state["discard_submitted"] = sorted(game.discard_submitted)
    state["ships_built_this_turn"] = [list(edge) for edge in sorted(game.ships_built_this_turn)]
    payload = _json_copy({"snapshot_version": SNAPSHOT_VERSION,
                          "engine_compatibility": ENGINE_COMPATIBILITY, "state": state})
    decode_snapshot(payload)  # Never persist a structurally invalid candidate.
    return payload


def decode_snapshot(payload: Any) -> GameState:
    """Restore known structures only; reject incomplete/incompatible storage."""
    _check_schema_coverage()
    payload = _json_copy(payload)
    envelope = _record(payload, {"snapshot_version": _integer,
                                "engine_compatibility": _integer, "state": _json_object}, "snapshot")
    version = envelope["snapshot_version"]
    schemas = {1: _GAME_V1, 2: _GAME_V2, 3: _GAME}
    if version not in schemas:
        raise UnsupportedSnapshotVersion("Unsupported snapshot_version; supported versions are 1, 2 and 3")
    if envelope["engine_compatibility"] != (2 if version == 3 else 1):
        raise UnsupportedEngineCompatibility("Unsupported snapshot/engine compatibility pair")
    state = _record(envelope["state"], schemas[version], "state")
    if version < 3:
        # Structural default only: old snapshots never activate ignored metadata.
        state["scenario"] = ScenarioState()
    if version == 1:
        # Released v1 has no ship history. It cannot safely grant another move
        # in a Seafarers turn (free ships can precede Roll). End Turn removes it.
        cfg = state["rules_config"]
        state["ships_built_this_turn"] = set()
        state["ship_moved_this_turn"] = (state["phase"] == "main"
                                        and cfg.enable_seafarers and cfg.enable_move_ship)
    game = GameState(**state)
    _validate_references(game)
    return game


def dumps_snapshot(game: GameState) -> str:
    """Stable compact JSON text; byte canonicalization/checksums are future work."""
    try:
        text = json.dumps(encode_snapshot(game), ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            _fail("snapshot", "JSON text exceeds limits")
        return text
    except (ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotValidationError("snapshot: cannot encode JSON text") from exc


def loads_snapshot(text: str) -> GameState:
    """Parse bounded JSON, detecting duplicate keys before they can disappear."""
    def unique_object(pairs: list) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("snapshot", "duplicate JSON object key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        _fail("snapshot", "non-finite JSON number")

    if type(text) is not str:
        _fail("snapshot", "expected JSON text")
    try:
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            _fail("snapshot", "JSON text exceeds limits")
        return decode_snapshot(json.loads(text, object_pairs_hook=unique_object,
                                           parse_constant=invalid_constant))
    except (ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotValidationError("snapshot: invalid or truncated JSON text") from exc
