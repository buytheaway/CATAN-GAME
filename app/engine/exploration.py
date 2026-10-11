"""Trusted fog domain and internal exploration execution.

Public fog support remains disabled until secure player-facing projections and
renderers exist. Never serialize this domain directly to UI.
"""
from dataclasses import replace
from hashlib import sha256
import json
import re

from .state import (BoardState, FogContinuation, FogDiscovery, FogRules,
                    FogState, GameState, RESOURCES, TERRAIN_TO_RES)

FOG_PROFILE = "shared-preassigned-v1"
FOG_DISABLED_MESSAGE = "Fog exploration is not available yet. Choose a non-fog map; saved data is preserved."


class FogUnavailableError(ValueError):
    pass


def fog_requested(data) -> bool:
    """Recognize supported input boundaries before parsing any private contents."""
    if not isinstance(data, dict):
        return False
    if data.get("version") == 2 or "fog_pool" in data:
        return True
    scenario = data.get("scenario")
    if isinstance(scenario, dict):
        if scenario.get("fog") is not None:
            return True
        config = scenario.get("rules", {})
        if isinstance(config, dict) and config.get("fog") is not None:
            return True
    rules = data.get("rules", {})
    if isinstance(rules, dict):
        scenario = rules.get("scenario", {})
        if isinstance(scenario, dict) and scenario.get("fog") is not None:
            return True
    tiles = data.get("tiles", [])
    if isinstance(tiles, list) and any(isinstance(t, dict) and t.get("terrain") == "fog" for t in tiles):
        return True
    # A durable envelope is not an offline/UI save format either.
    return isinstance(data.get("state"), dict) and fog_requested(data["state"])


def has_fog(game) -> bool:
    if game is None:
        return False
    scenario = getattr(game, "scenario", None)
    return (getattr(scenario, "fog", None) is not None
            or getattr(getattr(scenario, "rules", None), "fog", None) is not None
            or fog_requested({"rules": getattr(game, "rules", {})}))


def require_no_fog(game) -> None:
    if has_fog(game):
        raise FogUnavailableError(FOG_DISABLED_MESSAGE)


def require_non_fog_data(data) -> None:
    if fog_requested(data):
        raise FogUnavailableError(FOG_DISABLED_MESSAGE)


def validate_fog_rules(config: FogRules, board: BoardState | None = None) -> None:
    if type(config) is not FogRules:
        raise ValueError("Invalid fog configuration")
    ids = config.initially_hidden
    if (config.profile != FOG_PROFILE
            or type(ids) is not tuple or any(type(i) is not int or i < 0 for i in ids)
            or tuple(sorted(set(ids))) != ids):
        raise ValueError("Invalid fog profile or initial tile indices")
    if board is not None and (not ids or not set(ids) <= set(range(len(board.tiles)))):
        raise ValueError("Fog slots require existing tile indices")


def assignment_digest(board: BoardState) -> str:
    # Original list order is the tile ID. No private values in validation errors.
    values = [[t.q, t.r, t.terrain, t.number] for t in board.tiles]
    return sha256(json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def initial_fog_state(board: BoardState, config: FogRules) -> FogState:
    validate_fog_rules(config, board)
    return FogState(assignment_digest(board))


def initially_visible_land(board: BoardState, hidden: tuple[int, ...]) -> set[int]:
    return {i for i, t in enumerate(board.tiles) if i not in hidden and t.terrain != "sea"}


def initially_visible_coasts(board: BoardState, hidden: tuple[int, ...]) -> set[tuple[int, int]]:
    # Unknown is neither land nor sea. Use the existing stored adjacency graph.
    return {e for e, adjacent in board.edge_adj_hexes.items()
            if not set(adjacent).intersection(hidden)
            and sum(board.tiles[i].terrain != "sea" for i in adjacent) == 1
            and (len(adjacent) == 1 or any(board.tiles[i].terrain == "sea" for i in adjacent))}


def tile_is_known(g: GameState, tile_index: int) -> bool:
    config = g.scenario.rules.fog
    return config is None or (tile_index not in config.initially_hidden
                              or tile_index in g.scenario.fog.revealed)


def is_known_land(g: GameState, tile_index: int) -> bool:
    return tile_is_known(g, tile_index) and g.tiles[tile_index].terrain != "sea"


def is_known_sea(g: GameState, tile_index: int) -> bool:
    return tile_is_known(g, tile_index) and g.tiles[tile_index].terrain == "sea"


def known_land_tiles(g: GameState) -> set[int]:
    return {i for i in range(len(g.tiles)) if is_known_land(g, i)}


def discover_route(g: GameState, pid: int, edge: tuple[int, int], *,
                   command: str, setup: bool) -> tuple[list[dict], int]:
    """Only called AFTER accepted route validation/payment/occupancy mutation.

    Revealing changes frozen history, never the preassigned Tile or graph.
    Vertex adjacency deliberately includes tiles touching only one endpoint.
    Gold choices use the existing executor's pending lifecycle after this step.
    """
    state = g.scenario.fog
    if state is None:
        return [], 0
    adjacent = set(g.edge_adj_hexes.get(edge, ()))
    for vertex in edge:
        adjacent.update(g.vertex_adj_hexes.get(vertex, ()))
    discovered = sorted(adjacent.intersection(g.scenario.rules.fog.initially_hidden) - state.revealed)
    entries, events = [], []
    for tile_index in discovered:
        terrain = g.tiles[tile_index].terrain
        resource = TERRAIN_TO_RES[terrain]
        status = "none"
        if terrain == "gold":
            status = "pending"
        elif resource is not None:
            status = "unavailable"
            if g.bank.get(resource, 0) > 0:
                g.bank[resource] -= 1
                g.players[pid].res[resource] += 1
                status = "awarded"
        entry = FogDiscovery(tile_index, pid, status, resource if status == "awarded" else None)
        entries.append(entry)
        # Trusted engine events only; public serialization/publication is gated.
        events.append({"type": "discover_tile", "pid": pid, "tile": tile_index})
    gold = sum(entry.reward_status == "pending" for entry in entries)
    g.scenario.fog = replace(state, revealed=state.revealed.union(discovered),
        discoveries=state.discoveries + tuple(entries),
        continuation=FogContinuation(command, pid, edge, setup) if gold else None)
    return events, gold


def record_gold_reward(g: GameState, pid: int, resource: str, qty: int) -> None:
    """Consume discovery entries in recorded order after choose_gold validation."""
    state = g.scenario.fog
    if state is None or state.continuation is None:
        return  # Ordinary production/setup Gold has no discovery ledger.
    entries = []
    for entry in state.discoveries:
        if qty and entry.pid == pid and entry.reward_status == "pending":
            entry = replace(entry, reward_status="awarded", resource=resource)
            qty -= 1
        entries.append(entry)
    g.scenario.fog = replace(state, discoveries=tuple(entries))


def exhaust_gold_rewards(g: GameState) -> None:
    """No available card means remaining discovery entitlements cannot be paid."""
    state = g.scenario.fog
    if state is not None and state.continuation is not None:
        g.scenario.fog = replace(state, discoveries=tuple(
            replace(entry, reward_status="unavailable") if entry.reward_status == "pending" else entry
            for entry in state.discoveries))


def take_completed_continuation(g: GameState) -> FogContinuation | None:
    state = g.scenario.fog
    if (state is None or state.continuation is None
            or any(entry.reward_status == "pending" for entry in state.discoveries)):
        return None
    g.scenario.fog = replace(state, continuation=None)
    return state.continuation


def validate_fog_state(g: GameState) -> None:
    config, state = g.scenario.rules.fog, g.scenario.fog
    if config is None:
        if state is not None:
            raise ValueError("Disabled fog cannot retain discovery state")
        return
    validate_fog_rules(config, g.board)
    if type(state) is not FogState:
        raise ValueError("Fog requires complete trusted state")
    if (type(state.assignment_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", state.assignment_digest) is None
            or state.assignment_digest != assignment_digest(g.board)):
        raise ValueError("Fog terrain assignments cannot change")
    if any(t.terrain not in TERRAIN_TO_RES or (t.terrain in ("sea", "desert") and t.number is not None)
           or (t.terrain not in ("sea", "desert") and (type(t.number) is not int
               or t.number not in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12))) for t in g.tiles):
        raise ValueError("Invalid materialized fog terrain or number")
    if any(t.terrain == "gold" for t in g.tiles) and not g.rules_config.enable_gold:
        raise ValueError("Fog gold requires Gold support")
    if (type(state.revealed) is not frozenset or any(type(i) is not int for i in state.revealed)
            or not state.revealed <= set(config.initially_hidden)
            or type(state.discoveries) is not tuple):
        raise ValueError("Invalid fog discovery indices")
    ids, pending = set(), []
    for entry in state.discoveries:
        if (type(entry) is not FogDiscovery or type(entry.tile_index) is not int
                or entry.tile_index not in state.revealed or entry.tile_index in ids
                or type(entry.pid) is not int or not 0 <= entry.pid < len(g.players)
                or entry.reward_status not in ("none", "pending", "awarded", "unavailable")):
            raise ValueError("Invalid or duplicate discovery reward entry")
        ids.add(entry.tile_index)
        terrain = g.tiles[entry.tile_index].terrain
        if terrain in ("sea", "desert"):
            valid = entry.reward_status == "none" and entry.resource is None
        elif entry.reward_status == "awarded":
            valid = entry.resource in RESOURCES and (terrain == "gold" or TERRAIN_TO_RES[terrain] == entry.resource)
        else:
            valid = entry.resource is None and (entry.reward_status == "unavailable"
                    or terrain == "gold" and entry.reward_status == "pending")
        if not valid:
            raise ValueError("Invalid discovery reward record")
        if entry.reward_status == "pending":
            pending.append(entry)
    if ids != state.revealed:
        raise ValueError("Every revealed tile requires one reward record")
    continuation = state.continuation
    if pending:
        if (type(continuation) is not FogContinuation or type(continuation.pid) is not int
                or continuation.pid != g.turn or any(e.pid != continuation.pid for e in pending)
                or continuation.command not in ("place_road", "build_ship", "move_ship")
                or type(continuation.setup) is not bool or continuation.setup != (g.phase == "setup")
                or type(continuation.edge) is not tuple or continuation.edge not in g.edges
                or any(type(v) is not int for v in continuation.edge)
                or (g.occupied_e if continuation.command == "place_road" else g.occupied_ships).get(continuation.edge) != continuation.pid
                or g.pending_action != "choose_gold" or g.pending_pid != continuation.pid
                or g.pending_gold != {continuation.pid: len(pending)}
                or g.pending_gold_queue != [continuation.pid]
                or continuation.setup and (continuation.command == "move_ship"
                    or g.setup_need != "road" or g.setup_anchor_vid not in continuation.edge)):
            raise ValueError("Incomplete fog reward continuation")
    elif continuation is not None:
        raise ValueError("Continuation requires pending discovery rewards")
    visible = set(range(len(g.tiles))) - set(config.initially_hidden)
    if g.robber_tile != -1 and g.robber_tile not in visible | state.revealed:
        raise ValueError("Robber cannot occupy undiscovered territory")
    if any(i != -1 and i not in visible | state.revealed for i in g.robbers) or (
            g.pirate_tile is not None and g.pirate_tile not in visible | state.revealed):
        raise ValueError("Robber or pirate cannot occupy undiscovered territory")
    if any(edge not in initially_visible_coasts(g.board, config.initially_hidden) for edge, _ in g.ports):
        raise ValueError("Fog ports require initially visible coastline")


def validate_fog_transition(before: GameState, after: GameState) -> None:
    """Fence assignment changes, hiding discoveries and repeated reward writes."""
    validate_fog_state(before)
    validate_fog_state(after)
    previous, current = before.scenario.fog, after.scenario.fog
    if previous is None and current is None:
        return
    if (previous is None or current is None or before.scenario.rules.fog != after.scenario.rules.fog
            or previous.assignment_digest != current.assignment_digest
            or not previous.revealed <= current.revealed
            or any(getattr(before.board, key) != getattr(after.board, key) for key in
                   ("vertices", "edges", "vertex_adj_hexes", "edge_adj_hexes", "ports"))):
        raise ValueError("Fog assignment, geometry and discovery history are immutable")
    old, new = previous.discoveries, current.discoveries
    if len(new) < len(old):
        raise ValueError("Discovery rewards cannot be removed")
    for a, b in zip(old, new):
        if a != b and not (a.tile_index == b.tile_index and a.pid == b.pid
                and a.reward_status == "pending" and b.reward_status in ("awarded", "unavailable")):
            raise ValueError("A discovery reward cannot be repeated or rewritten")
    if previous.continuation is not None and current.continuation is not None and previous.continuation != current.continuation:
        raise ValueError("Pending discovery continuation cannot change")
