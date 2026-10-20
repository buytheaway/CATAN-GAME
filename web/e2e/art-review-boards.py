"""Offline PUBLIC board geometry for the 5C visual audit; no DB or Fog recipe.

Actual shipped Base/official maps, with synthetic display occupancy. This is not
a legal gameplay replay, map editor, rules evaluator or persistent game state.
Only an explicit board-field allowlist leaves this process.
"""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.engine import rules, serialize


def display_board(map_id, count):
    game = rules.build_game(17, count, map_id=map_id)
    public = serialize.to_player_dict(game, 0)
    result = {key: public[key] for key in (
        "size", "tiles", "vertices", "edges", "edge_adj_hexes", "ports",
        "robber_tile", "robbers", "pirate_tile", "rules_config",
    )}
    result["map_id"] = map_id
    result["map_meta"] = {"name": game.map_name}
    result["display_players"] = count
    result["occupied_v"], result["occupied_e"], result["occupied_ships"] = {}, {}, {}
    land = {i for i, tile in enumerate(game.tiles) if tile.terrain != "sea"}
    land_vertices = sorted({v for edge in game.edges if land.intersection(game.edge_adj_hexes[edge]) for v in edge})
    center = tuple(sum(game.vertices[v][axis] for v in land_vertices) / len(land_vertices) for axis in (0, 1))
    angular = lambda point: math.atan2(point[1] - center[1], point[0] - center[0])
    selected = []
    for index in range(count * 2):
        angle = -math.pi + 2 * math.pi * index / (count * 2)
        candidates = sorted(land_vertices, key=lambda v: (
            abs(math.atan2(math.sin(angular(game.vertices[v]) - angle), math.cos(angular(game.vertices[v]) - angle))), v))
        vertex = next(v for v in candidates if all(math.dist(game.vertices[v], game.vertices[old]) > game.size * 1.5 for old in selected))
        selected.append(vertex)
        result["occupied_v"][str(vertex)] = [index % count, 1 if index < count else 2]
        incident = sorted(edge for edge in game.edges if vertex in edge and land.intersection(game.edge_adj_hexes[edge]))
        for edge in incident[:2]:
            result["occupied_e"][",".join(map(str, edge))] = index % count
    port_edges = {tuple(edge) for edge, _ in game.ports}
    water = sorted(edge for edge in game.edges if edge not in port_edges and
                   game.pirate_tile not in game.edge_adj_hexes[edge] and
                   any(game.tiles[i].terrain == "sea" for i in game.edge_adj_hexes[edge]) and
                   ",".join(map(str, edge)) not in result["occupied_e"])
    water.sort(key=lambda edge: (angular(tuple(sum(game.vertices[v][a] for v in edge) / 2 for a in (0, 1))), edge))
    if water:
        for index in range(count * 2):
            edge = water[index * len(water) // (count * 2)]
            result["occupied_ships"][",".join(map(str, edge))] = index % count
    return result


if __name__ == "__main__":
    boards = {"base": display_board("base_standard", 4)}
    for key, map_id in [("new-shores", "seafarers_official_new_shores"), ("four-islands", "seafarers_official_four_islands")]:
        for count in (3, 4):
            boards[f"{key}-{count}"] = display_board(f"{map_id}_{count}", count)
    print(json.dumps(boards, separators=(",", ":")))
