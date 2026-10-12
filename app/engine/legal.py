"""Personal board-action hints, checked by the existing command executor."""
from copy import deepcopy
import random

from .rules import (
    RuleError, apply_cmd, can_place_road, can_place_settlement, can_place_ship,
    can_upgrade_city, _victims_for_tile, _victims_for_pirate_tile,
)
from .state import GameState
from .exploration import has_fog, require_no_fog, tile_is_known


def board_legal_moves(g: GameState, pid: int, *, trusted_fog: bool = False) -> dict:
    if trusted_fog is not True:
        require_no_fog(g)
    legal = {
        "pid": pid, "settlements": [], "roads": [], "cities": [], "ships": [],
        "road_free": False, "robber_tiles": [], "pirate_tiles": [],
        "robber_victims": {}, "pirate_victims": {},
        "move_ship": {"sources": [], "targets": {}},
    }
    if g.game_over or not 0 <= pid < len(g.players) or pid != g.turn:
        return legal

    # Never reuse live data. Non-fog probes may share an isolated base geometry;
    # fog probes get a complete copy, including terrain and discovery history.
    base = deepcopy(g)
    # Hints execute only on copies and must not draw from gameplay entropy.
    probe_rng = random.Random(0)
    geometry = (base.tiles, base.vertices, base.edges, base.vertex_adj_hexes,
                base.edge_adj_hexes, base.board.ports) if not has_fog(g) else ()

    def accepts(cmd):
        probe = deepcopy(base, {id(value): value for value in geometry})
        try:
            apply_cmd(probe, pid, cmd, trusted_fog=trusted_fog, theft_rng=probe_rng)
        except RuleError:
            return False
        return True

    if g.pending_action == "robber_move":
        for tile, terrain in enumerate(g.tiles):
            if not tile_is_known(g, tile):
                continue
            pirate = terrain.terrain == "sea"
            kind = "pirate" if pirate else "robber"
            if accepts({"type": "move_" + kind, "tile": tile}):
                legal[kind + "_tiles"].append(tile)
                victims = _victims_for_pirate_tile if pirate else _victims_for_tile
                legal[kind + "_victims"][str(tile)] = victims(g, tile, pid)
        return legal
    if g.pending_action is not None:
        return legal

    setup = g.phase == "setup"
    legal["road_free"] = not setup and int(g.free_roads.get(pid, 0)) > 0
    for vid in sorted(g.vertices):
        if can_place_settlement(g, pid, vid, require_road=not setup):
            if accepts({"type": "place_settlement", "vid": vid, "setup": setup}):
                legal["settlements"].append(vid)
        if can_upgrade_city(g, pid, vid) and accepts({"type": "upgrade_city", "vid": vid}):
            legal["cities"].append(vid)
    for edge in sorted(g.edges):
        road = {"type": "place_road", "eid": list(edge), "setup": setup}
        if legal["road_free"]:
            road["free"] = True
        if can_place_road(g, pid, edge) and accepts(road):
            legal["roads"].append(list(edge))
        ship = {"type": "build_ship", "eid": list(edge), "setup": setup}
        if legal["road_free"]:
            ship["free"] = True
        if can_place_ship(g, pid, edge) and accepts(ship):
            legal["ships"].append(list(edge))
    if not setup:
        for source, owner in sorted(g.occupied_ships.items()):
            if owner != pid:
                continue
            destinations = [list(edge) for edge in sorted(g.edges)
                            if accepts({"type": "move_ship", "from_eid": list(source), "to_eid": list(edge)})]
            if destinations:
                key = ",".join(map(str, source))
                legal["move_ship"]["sources"].append(list(source))
                legal["move_ship"]["targets"][key] = destinations
    return legal
