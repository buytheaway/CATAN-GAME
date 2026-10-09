"""Explicit scenario policy; no preset-name dispatch or recovery rule execution."""
from app.engine.state import BoardState, GameState, ScenarioRules, ScenarioState
from app.engine.topology import island_ids, land_components


def parse_scenario_rules(rules: dict, board: BoardState | None = None) -> ScenarioRules:
    raw = rules.get("scenario", {})
    if type(raw) is not dict or set(raw) - {"starting_islands", "new_island_vp"}:
        raise ValueError("rules.scenario must contain only starting_islands and new_island_vp")
    starts, bonus = raw.get("starting_islands"), raw.get("new_island_vp", 0)
    if starts is not None and (type(starts) is not list or not starts
            or any(type(i) is not int or i < 0 for i in starts) or len(set(starts)) != len(starts)):
        raise ValueError("scenario.starting_islands must be a nonempty list of unique island IDs")
    if type(bonus) is not int or not 0 <= bonus <= 10:
        raise ValueError("scenario.new_island_vp must be an integer from 0 to 10")
    config = ScenarioRules(None if starts is None else tuple(sorted(starts)), bonus)
    validate_scenario_rules(config, board, rules.get("enable_seafarers") is True)
    return config


def validate_scenario_rules(config: ScenarioRules, board: BoardState | None, seafarers: bool) -> None:
    if type(config.new_island_vp) is not int or not 0 <= config.new_island_vp <= 10:
        raise ValueError("Invalid scenario bonus")
    starts = config.starting_islands
    if starts is not None and (type(starts) is not tuple or not starts
            or any(type(i) is not int or i < 0 for i in starts)
            or tuple(sorted(set(starts))) != starts):
        raise ValueError("Invalid scenario starting islands")
    if (starts is not None or config.new_island_vp) and not seafarers:
        raise ValueError("Scenario island rules require Seafarers")
    if board is not None and starts is not None and not set(starts) <= land_components(board).keys():
        raise ValueError("Starting island ID does not exist in the materialized board")


def vertex_islands(board: BoardState, vid: int) -> set[int]:
    islands = island_ids(board)
    return {islands[i] for i in board.vertex_adj_hexes.get(vid, ()) if i in islands}


def valid_starting_vertex(g: GameState, vid: int) -> bool:
    starts = g.scenario.rules.starting_islands
    return starts is None or bool(vertex_islands(g.board, vid).intersection(starts))


def setup_has_capacity(g: GameState, chosen: int | None = None) -> bool:
    """Restricted setup must leave room for the rest of the snake order.

    The hex-intersection graph is bipartite. Maximum independent set size is
    vertex count minus maximum matching, so no exponential opening search.
    This is a setup guard, never a recovery side effect or a Base rule.
    """
    if g.scenario.rules.starting_islands is None:
        return True
    allowed = set(g.scenario.rules.starting_islands)
    islands = island_ids(g.board)
    candidates = {v for v, adjacent in g.vertex_adj_hexes.items()
                  if any(islands.get(i) in allowed for i in adjacent)}
    neighbors = {v: set() for v in g.vertices}
    for a, b in g.edges:
        neighbors[a].add(b)
        neighbors[b].add(a)
    for v in (*g.occupied_v, *((chosen,) if chosen is not None else ())):
        candidates.difference_update({v, *neighbors[v]})
    remaining = len(g.setup_order) - g.setup_idx - (chosen is not None)
    if remaining <= 0:
        return True
    if len(candidates) < remaining:
        return False
    colors = {}
    for root in sorted(candidates):
        if root in colors:
            continue
        colors[root], todo = 0, [root]
        while todo:
            v = todo.pop()
            for neighbor in neighbors[v] & candidates:
                if neighbor not in colors:
                    colors[neighbor] = 1 - colors[v]
                    todo.append(neighbor)
                elif colors[neighbor] == colors[v]:
                    raise ValueError("Scenario setup requires a hex-intersection graph")
    matching = {}

    def augment(v: int, seen: set[int]) -> bool:
        for neighbor in sorted(neighbors[v] & candidates - seen):
            seen.add(neighbor)
            if neighbor not in matching or augment(matching[neighbor], seen):
                matching[neighbor] = v
                return True
        return False

    for v in sorted(candidates):
        if colors[v] == 0:
            augment(v, set())
    return len(candidates) - len(matching) >= remaining


def record_settlement(g: GameState, pid: int, vid: int, *, setup: bool) -> int:
    """Called only AFTER settlement validation. Return public extra VP awarded."""
    bonus = g.scenario.rules.new_island_vp
    if not bonus:
        return 0
    islands = vertex_islands(g.board, vid)
    if setup:
        g.scenario.home_islands.setdefault(pid, set()).update(islands)
        return 0
    awarded = g.scenario.awarded_islands.setdefault(pid, set())
    new = islands - g.scenario.home_islands[pid] - awarded
    awarded.update(new)
    points = len(new) * bonus
    g.players[pid].vp += points
    return points


def scenario_to_dict(state: ScenarioState) -> dict:
    return {"rules": {"starting_islands": None if state.rules.starting_islands is None
                     else list(state.rules.starting_islands), "new_island_vp": state.rules.new_island_vp},
            "home_islands": {str(pid): sorted(ids) for pid, ids in state.home_islands.items()},
            "awarded_islands": {str(pid): sorted(ids) for pid, ids in state.awarded_islands.items()}}


def validate_scenario_state(g: GameState) -> None:
    """Validate recorded references/history; never recalculate VP or awards."""
    validate_scenario_rules(g.scenario.rules, g.board, g.rules_config.enable_seafarers)
    homes, awards = g.scenario.home_islands, g.scenario.awarded_islands
    if not g.scenario.rules.new_island_vp:
        if homes or awards:
            raise ValueError("Disabled bonus cannot retain island history")
        return
    pids, roots = {p.pid for p in g.players}, set(land_components(g.board))
    if set(homes) != pids or not set(awards) <= pids:
        raise ValueError("Missing or unknown scenario player history")
    for history in (homes, awards):
        if any(not ids <= roots for ids in history.values()):
            raise ValueError("Unknown scenario island reference")
    starts = g.scenario.rules.starting_islands
    for pid in pids:
        owned = set().union(*(vertex_islands(g.board, vid) for vid, (owner, _) in g.occupied_v.items()
                             if owner == pid))
        if not homes[pid] <= owned or starts is not None and not homes[pid] <= set(starts):
            raise ValueError("Invalid home island history")
        awarded = awards.get(pid, set())
        if g.phase == "setup":
            if homes[pid] != owned or awarded:
                raise ValueError("Setup history cannot contain island awards")
        elif not homes[pid] or awarded != owned - homes[pid]:
            raise ValueError("Missing or inconsistent island award history")


def scenario_from_dict(data: dict, board: BoardState, seafarers: bool) -> ScenarioState:
    # Offline/UI conversion preserves the ledger, rather than deriving it from VP.
    if type(data) is not dict or set(data) != {"rules", "home_islands", "awarded_islands"}:
        raise ValueError("Scenario state requires rules and complete island history")
    config = parse_scenario_rules({"enable_seafarers": seafarers, "scenario": data["rules"]}, board)
    history = {}
    for key in ("home_islands", "awarded_islands"):
        raw = data[key]
        if type(raw) is not dict:
            raise ValueError("Invalid scenario history")
        history[key] = {}
        for pid, ids in raw.items():
            if (type(pid) is not str or not pid.isdecimal() or str(int(pid)) != pid
                    or type(ids) is not list or any(type(i) is not int for i in ids)
                    or len(set(ids)) != len(ids) or not set(ids) <= land_components(board).keys()):
                raise ValueError("Invalid scenario island references")
            history[key][int(pid)] = set(ids)
    return ScenarioState(config, **history)
