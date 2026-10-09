"""Read-only topology derived from the materialized board's shared-edge graph."""
from app.engine.state import BoardState


def land_components(board: BoardState) -> dict[int, tuple[int, ...]]:
    """Island IDs are the smallest original tile index, stable for saved boards."""
    land = {i for i, tile in enumerate(board.tiles) if tile.terrain != "sea"}
    neighbors = {i: set() for i in land}
    for adjacent in board.edge_adj_hexes.values():
        touching = land.intersection(adjacent)
        for tile in touching:
            neighbors[tile].update(touching - {tile})
    remaining = set(land)
    result = {}
    while remaining:
        root = min(remaining)
        pending, component = [root], set()
        while pending:
            tile = pending.pop()
            if tile in component:
                continue
            component.add(tile)
            pending.extend(neighbors[tile] - component)
        remaining.difference_update(component)
        result[root] = tuple(sorted(component))
    return result


def island_ids(board: BoardState) -> dict[int, int]:
    return {tile: island for island, tiles in land_components(board).items() for tile in tiles}


def coastal_edges(board: BoardState) -> set[tuple[int, int]]:
    """One land side and sea or the outer frame on the other side."""
    return {edge for edge, adjacent in board.edge_adj_hexes.items()
            if sum(board.tiles[i].terrain != "sea" for i in adjacent) == 1
            and (len(adjacent) == 1 or any(board.tiles[i].terrain == "sea" for i in adjacent))}
