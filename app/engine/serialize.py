from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Tuple
from app.engine.scenario import scenario_from_dict, scenario_to_dict, validate_scenario_state
from app.engine.exploration import require_no_fog, require_non_fog_data

from app.engine.state import (
    AchievementState,
    BoardState,
    GameState,
    PlayerState,
    RESOURCES,
    RulesConfig,
    Tile,
    TradeOffer,
)


def _edge_key(e: Tuple[int, int]) -> str:
    a, b = e
    return f"{a},{b}"


def _legacy_ship_movement_lock(phase: str, rolled: bool, cfg) -> bool:
    # Road Building may have built ships before rolling, so an unrolled legacy
    # turn also has unknown history. Only normal End Turn can establish a reset.
    return (phase == "main"
            and bool(getattr(cfg, "enable_seafarers", False))
            and bool(getattr(cfg, "enable_move_ship", False)))


def to_dict(g: GameState) -> Dict:
    require_no_fog(g)
    cfg = getattr(g, "rules_config", RulesConfig())
    return {
        "state_version": g.state_version,
        "max_players": g.max_players,
        "size": g.size,
        "map_name": g.map_name,
        "map_id": getattr(g, "map_id", g.map_name),
        "map_meta": dict(getattr(g, "map_meta", {}) or {}),
        "rules": dict(getattr(g, "rules", {}) or {}),
        "scenario": scenario_to_dict(g.scenario),
        "rules_config": {
            "target_vp": int(getattr(cfg, "target_vp", 10)),
            "discard_threshold": cfg.discard_threshold,
            "max_roads": int(getattr(cfg, "max_roads", 15)),
            "max_settlements": int(getattr(cfg, "max_settlements", 5)),
            "max_cities": int(getattr(cfg, "max_cities", 4)),
            "robber_count": int(getattr(cfg, "robber_count", 1)),
            "enable_seafarers": bool(getattr(cfg, "enable_seafarers", False)),
            "max_ships": int(getattr(cfg, "max_ships", 15)),
            "enable_pirate": bool(getattr(cfg, "enable_pirate", False)),
            "enable_gold": bool(getattr(cfg, "enable_gold", False)),
            "enable_move_ship": bool(getattr(cfg, "enable_move_ship", False)),
        },
        "phase": g.phase,
        "turn": g.turn,
        "rolled": g.rolled,
        "setup_order": list(g.setup_order),
        "setup_idx": g.setup_idx,
        "setup_need": g.setup_need,
        "setup_anchor_vid": g.setup_anchor_vid,
        "last_roll": g.last_roll,
        "robber_tile": g.robber_tile,
        "robbers": list(getattr(g, "robbers", []) or [g.robber_tile]),
        "pirate_tile": g.pirate_tile,
        "pending_action": g.pending_action,
        "pending_pid": g.pending_pid,
        "pending_victims": list(g.pending_victims),
        "discard_required": {str(k): int(v) for k, v in g.discard_required.items()},
        "discard_submitted": [int(x) for x in g.discard_submitted],
        "pending_gold": {str(k): int(v) for k, v in getattr(g, "pending_gold", {}).items()},
        "pending_gold_queue": [int(x) for x in getattr(g, "pending_gold_queue", [])],
        "trade_offers": [
            {
                "offer_id": o.offer_id,
                "from_pid": o.from_pid,
                "to_pid": o.to_pid,
                "give": dict(o.give),
                "get": dict(o.get),
                "status": o.status,
                "created_turn": o.created_turn,
                "created_tick": o.created_tick,
            }
            for o in g.trade_offers
        ],
        "trade_offer_next_id": g.trade_offer_next_id,
        "longest_road_owner": g.longest_road_owner,
        "longest_road_len": g.longest_road_len,
        "largest_army_owner": g.largest_army_owner,
        "largest_army_size": g.largest_army_size,
        "game_over": g.game_over,
        "winner_pid": g.winner_pid,
        "players": [
            {
                "pid": p.pid,
                "name": p.name,
                "vp": p.vp,
                **({"special_vp": len(g.scenario.awarded_islands.get(p.pid, ())) * g.scenario.rules.new_island_vp}
                   if g.scenario.rules.new_island_vp else {}),
                "res": dict(p.res),
                "knights_played": p.knights_played,
            }
            for p in g.players
        ],
        "bank": dict(g.bank),
        "occupied_v": {str(k): [v[0], v[1]] for k, v in g.occupied_v.items()},
        "occupied_e": {_edge_key((a, b)): owner for (a, b), owner in g.occupied_e.items()},
        "occupied_ships": {_edge_key((a, b)): owner for (a, b), owner in g.occupied_ships.items()},
        "ships_built_this_turn": [list(edge) for edge in sorted(getattr(g, "ships_built_this_turn", set()))],
        "ship_moved_this_turn": bool(getattr(g, "ship_moved_this_turn",
            _legacy_ship_movement_lock(g.phase, g.rolled, cfg))),
        "tiles": [
            {
                "q": t.q,
                "r": t.r,
                "terrain": t.terrain,
                "number": t.number,
                "center": [t.center[0], t.center[1]],
            }
            for t in g.tiles
        ],
        "vertices": {str(k): [v[0], v[1]] for k, v in g.vertices.items()},
        "edges": [[a, b] for a, b in sorted(g.edges)],
        "vertex_adj_hexes": {str(k): v for k, v in g.vertex_adj_hexes.items()},
        "edge_adj_hexes": {_edge_key((a, b)): v for (a, b), v in g.edge_adj_hexes.items()},
        "ports": [[[a, b], kind] for (a, b), kind in g.ports],
    }


def to_player_dict(g: GameState, pid: int) -> Dict:
    """Network view, distinct from the trusted/offline serialization format."""
    if type(pid) is not int or not 0 <= pid < len(g.players):
        raise ValueError("A valid player is required for a private snapshot")
    state = to_dict(g)
    # Lifecycle history is private executor/persistence data, not a wire addition.
    state.pop("ships_built_this_turn")
    state.pop("ship_moved_this_turn")
    # Exact bank counts + own hand reveal the other hand in a two-player game.
    state.pop("bank")
    state["bank_available"] = {r: n > 0 for r, n in g.bank.items()}
    for view, player in zip(state["players"], g.players):
        view["resource_count"] = sum(player.res.values())
        view["dev_count"] = len(player.dev_cards)
        if player.pid == pid:
            view["dev_cards"] = deepcopy(player.dev_cards)
        else:
            view.pop("res")
            if not g.game_over:
                hidden_vp = sum(c.get("type") == "victory_point" for c in player.dev_cards)
                view["vp"] -= hidden_vp
    state["pending_gold"] = {
        str(pid): g.pending_gold[pid]
    } if pid in g.pending_gold else {}
    state["discard_required"] = {
        str(pid): g.discard_required[pid]
    } if pid in g.discard_required and pid not in g.discard_submitted else {}
    if g.pending_pid != pid:
        state["pending_victims"] = []
    state["free_roads"] = {str(pid): g.free_roads.get(pid, 0)}
    state["dev_played_turn"] = {str(pid): g.dev_played_turn.get(pid, False)}
    return state


def from_dict(data: Dict) -> GameState:
    require_non_fog_data(data)
    seed = int(data.get("seed", 0))
    size = float(data.get("size", 58.0))
    max_players = int(data.get("max_players", 4))

    tiles = []
    for t in data.get("tiles", []):
        center = (float(t["center"][0]), float(t["center"][1]))
        tiles.append(Tile(q=int(t["q"]), r=int(t["r"]), terrain=t["terrain"], number=t.get("number"), center=center))

    vertices = {int(k): (float(v[0]), float(v[1])) for k, v in data.get("vertices", {}).items()}
    vertex_adj_hexes = {int(k): list(v) for k, v in data.get("vertex_adj_hexes", {}).items()}
    edges = set((int(a), int(b)) for a, b in data.get("edges", []))
    edge_adj_hexes = {}
    for k, v in data.get("edge_adj_hexes", {}).items():
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            edge_adj_hexes[(int(a), int(b))] = list(v)
    ports = [((int(p[0][0]), int(p[0][1])), p[1]) for p in data.get("ports", [])]
    occupied_v = {int(k): (int(v[0]), int(v[1])) for k, v in data.get("occupied_v", {}).items()}
    occupied_e = {}
    for k, owner in data.get("occupied_e", {}).items():
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            e = (int(a), int(b))
            occupied_e[e] = int(owner)
    occupied_ships = {}
    for k, owner in data.get("occupied_ships", {}).items():
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            e = (int(a), int(b))
            occupied_ships[e] = int(owner)

    board = BoardState(
        tiles=tiles,
        vertices=vertices,
        vertex_adj_hexes=vertex_adj_hexes,
        edges=edges,
        edge_adj_hexes=edge_adj_hexes,
        ports=ports,
        occupied_v=occupied_v,
        occupied_e=occupied_e,
        occupied_ships=occupied_ships,
    )

    players = []
    for p in data.get("players", []):
        pid = int(p["pid"])
        pl = PlayerState(pid=pid, name=p.get("name", f"P{pid+1}"))
        pl.vp = int(p.get("vp", 0))
        pl.res = {r: int(p.get("res", {}).get(r, 0)) for r in RESOURCES}
        pl.knights_played = int(p.get("knights_played", 0))
        players.append(pl)

    g = GameState(seed=seed, size=size, max_players=max_players, board=board, players=players)
    g.map_name = str(data.get("map_name", "base_standard"))
    g.map_id = str(data.get("map_id", g.map_name))
    g.map_meta = dict(data.get("map_meta", {}) or {})
    g.rules = dict(data.get("rules", {}) or {})
    rc = data.get("rules_config", {}) or {}
    g.rules_config = RulesConfig(
        discard_threshold=int(rc.get("discard_threshold", g.rules.get("discard_threshold", 7))),
        target_vp=int(rc.get("target_vp", g.rules.get("target_vp", g.rules.get("victory_points", 10)))),
        max_roads=int(rc.get("max_roads", g.rules.get("max_roads", 15))),
        max_settlements=int(rc.get("max_settlements", g.rules.get("max_settlements", 5))),
        max_cities=int(rc.get("max_cities", g.rules.get("max_cities", 4))),
        robber_count=int(rc.get("robber_count", g.rules.get("robber_count", 1))),
        enable_seafarers=bool(rc.get("enable_seafarers", g.rules.get("enable_seafarers", False))),
        max_ships=int(rc.get("max_ships", g.rules.get("max_ships", 15))),
        enable_pirate=bool(rc.get("enable_pirate", g.rules.get("enable_pirate", False))),
        enable_gold=bool(rc.get("enable_gold", g.rules.get("enable_gold", False))),
        enable_move_ship=bool(rc.get("enable_move_ship", g.rules.get("enable_move_ship", False))),
    )
    g.phase = data.get("phase", "setup")
    # Old saves' unrecognized map metadata is not permission to enable new rules.
    if "scenario" in data:
        g.scenario = scenario_from_dict(data["scenario"], board, g.rules_config.enable_seafarers)
        validate_scenario_state(g)
    g.turn = int(data.get("turn", 0))
    g.rolled = bool(data.get("rolled", False))
    g.ships_built_this_turn = {(int(a), int(b)) for a, b in data.get("ships_built_this_turn", [])}
    g.ship_moved_this_turn = bool(data["ship_moved_this_turn"]) if "ship_moved_this_turn" in data else (
        _legacy_ship_movement_lock(g.phase, g.rolled, g.rules_config))
    g.setup_order = [int(x) for x in data.get("setup_order", [])]
    g.setup_idx = int(data.get("setup_idx", 0))
    g.setup_need = data.get("setup_need", "settlement")
    g.setup_anchor_vid = data.get("setup_anchor_vid", None)
    g.last_roll = data.get("last_roll", None)
    g.robber_tile = int(data.get("robber_tile", 0))
    g.robbers = [int(x) for x in data.get("robbers", [])] if data.get("robbers") is not None else [g.robber_tile]
    g.pirate_tile = data.get("pirate_tile", None)
    while len(g.robbers) < int(getattr(g.rules_config, "robber_count", 1)):
        g.robbers.append(g.robber_tile)
    g.pending_action = data.get("pending_action", None)
    g.pending_pid = data.get("pending_pid", None)
    g.pending_victims = list(data.get("pending_victims", []))
    g.discard_required = {int(k): int(v) for k, v in data.get("discard_required", {}).items()}
    g.discard_submitted = set(int(x) for x in data.get("discard_submitted", []))
    g.pending_gold = {int(k): int(v) for k, v in data.get("pending_gold", {}).items()}
    g.pending_gold_queue = [int(x) for x in data.get("pending_gold_queue", [])]
    g.trade_offers = []
    for o in data.get("trade_offers", []):
        g.trade_offers.append(TradeOffer(
            offer_id=int(o.get("offer_id", 0)),
            from_pid=int(o.get("from_pid", 0)),
            to_pid=o.get("to_pid", None),
            give={r: int(q) for r, q in o.get("give", {}).items()},
            get={r: int(q) for r, q in o.get("get", {}).items()},
            status=str(o.get("status", "active")),
            created_turn=int(o.get("created_turn", 0)),
            created_tick=int(o.get("created_tick", 0)),
        ))
    g.trade_offer_next_id = int(data.get("trade_offer_next_id", 1))
    g.longest_road_owner = data.get("longest_road_owner", None)
    g.longest_road_len = int(data.get("longest_road_len", 0))
    g.largest_army_owner = data.get("largest_army_owner", None)
    g.largest_army_size = int(data.get("largest_army_size", 0))
    g.game_over = bool(data.get("game_over", False))
    g.winner_pid = data.get("winner_pid", None)
    g.bank = {r: int(data.get("bank", {}).get(r, 0)) for r in RESOURCES}
    return g
