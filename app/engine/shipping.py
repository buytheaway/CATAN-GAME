"""Shipping topology, independent of turn entitlements and pirate blocking."""

from .state import GameState


def is_open_ship(g: GameState, pid: int, edge: tuple[int, int]) -> bool:
    """Apply the Seafarers open-end rule and official ship-circle exceptions.

    Only this player's ships and buildings determine maritime topology. Foreign
    buildings interrupt placement/trade-route scoring, but do not reopen a
    previously closed shipping line. With the normal fifteen-ship supply, small
    vertex-simple DFS searches also distinguish side branches from closed lines.
    """
    if g.occupied_ships.get(edge) != pid or edge[0] == edge[1]:
        return False

    ships = {ship for ship, owner in g.occupied_ships.items() if owner == pid}
    anchors = {vertex for vertex, (owner, _level) in g.occupied_v.items()
               if owner == pid}
    adjacency: dict[int, list[tuple[int, tuple[int, int]]]] = {}
    for ship in ships:
        a, b = ship
        adjacency.setdefault(a, []).append((b, ship))
        adjacency.setdefault(b, []).append((a, ship))

    def reaches_other_anchor(vertex, home, visited, contains_source):
        if vertex != home and vertex in anchors:
            return contains_source
        for neighbor, ship in adjacency.get(vertex, []):
            if neighbor not in visited and reaches_other_anchor(
                neighbor, home, visited | {neighbor}, contains_source or ship == edge
            ):
                return True
        return False

    # Membership in a simple line between distinct own buildings closes a ship.
    # Counting all anchors in a component would incorrectly freeze side loops.
    if len(anchors) > 1 and any(
        reaches_other_anchor(home, home, {home}, False) for home in anchors
    ):
        return False

    if any(vertex not in anchors and len(adjacency.get(vertex, [])) == 1
           for vertex in edge):
        return True

    a, b = edge
    if a in anchors and b in anchors:
        return False

    def completes_circle(vertex, visited):
        if vertex == b:
            return True
        if vertex != a and vertex in anchors:
            return False
        for neighbor, ship in adjacency.get(vertex, []):
            if ship != edge and neighbor not in visited and completes_circle(
                neighbor, visited | {neighbor}
            ):
                return True
        return False

    # A circle with no own building allows any ship to move. A circle returning
    # to one own building allows only its two bordering ships: an alternate path
    # must have no own building in its interior, though one endpoint may have one.
    return completes_circle(a, {a})
