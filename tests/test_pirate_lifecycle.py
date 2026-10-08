"""A robber/pirate trigger is a single-use action in the shared engine."""
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.state import RESOURCES


def finish_setup(g):
    while g.phase == "setup":
        if g.pending_action == "choose_gold":
            resource = next(r for r in RESOURCES if g.bank[r] > 0)
            rules.apply_cmd(g, g.pending_pid,
                            {"type": "choose_gold", "res": resource, "qty": 1})
            continue
        pid = g.turn
        if g.setup_need == "settlement":
            legal = [v for v in sorted(g.vertices)
                     if rules.can_place_settlement(g, pid, v, False)]
            coast = [v for v in legal
                     if any(g.tiles[t].terrain == "sea" for t in g.vertex_adj_hexes[v])]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": (coast or legal)[0]})
        else:
            edge = next(e for e in sorted(g.edges)
                        if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": edge})


def pirate_targets(g):
    return sorted({t for e, owner in g.occupied_ships.items() if owner == 1
                   for t in g.edge_adj_hexes[e]
                   if g.tiles[t].terrain == "sea" and t != g.pirate_tile})


@pytest.fixture
def pirate_game():
    g = rules.build_game(1, 2, map_id="seafarers_pirate_lanes")
    finish_setup(g)
    # Trusted funding fixture; all ships are placed through legal build commands.
    rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"wood": 8, "sheep": 6}})
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    rules.apply_cmd(g, 1, {"type": "roll", "roll": 2})
    while len(pirate_targets(g)) < 2:
        edge = next(e for e in sorted(g.edges) if rules.can_place_ship(g, 1, e) and any(
            g.occupied_v.get(v, (-1,))[0] == 1 or
            (v not in g.occupied_v and any(v in ship and owner == 1
                                         for ship, owner in g.occupied_ships.items()))
            for v in e))
        rules.apply_cmd(g, 1, {"type": "build_ship", "eid": edge})
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    assert g.phase == "main" and g.turn == 0 and not g.rolled
    assert g.pending_action is None and len(pirate_targets(g)) >= 2
    return g


def finish_discards(g):
    for pid, need in list(g.discard_required.items()):
        plan = {}
        for resource, count in g.players[pid].res.items():
            take = min(count, need)
            if take:
                plan[resource] = take
                need -= take
        assert need == 0
        rules.apply_cmd(g, pid, {"type": "discard", "discards": plan})


def begin_movement(g, trigger):
    if trigger == "seven":
        rules.apply_cmd(g, 0, {"type": "roll", "roll": 7})
        finish_discards(g)
    else:
        g.players[0].dev_cards = [{"type": "knight", "new": False}]
        rules.apply_cmd(g, 0, {"type": "play_dev", "card": "knight"})
        assert not g.rolled  # Knight may create this action before the dice roll.
    assert g.pending_action == "robber_move" and g.pending_pid == 0


def rejected_unchanged(g, cmd, message, pid=0):
    before = deepcopy(g)
    with pytest.raises(rules.RuleError, match=message):
        rules.apply_cmd(g, pid, cmd)
    assert g == before


@pytest.mark.parametrize("rolled", [False, True])
def test_pirate_without_trigger_rejects_all_three_attempts(pirate_game, rolled):
    g = pirate_game
    if rolled:
        rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    a, b = pirate_targets(g)[:2]
    for tile in (a, b, a):
        rejected_unchanged(g, {"type": "move_pirate", "tile": tile, "victim": 1},
                           "No robber/pirate move pending")


@pytest.mark.parametrize("trigger", ["seven", "knight"])
@pytest.mark.parametrize("piece", ["pirate", "robber"])
def test_event_allows_one_piece_and_one_theft(pirate_game, trigger, piece):
    g = pirate_game
    begin_movement(g, trigger)
    if piece == "pirate":
        tile = pirate_targets(g)[0]
    else:
        tile = next(t for t, h in enumerate(g.tiles) if h.terrain != "sea"
                    and t != g.robber_tile and 1 in rules._victims_for_tile(g, t, 0))
    before = deepcopy(g)
    supply = {r: g.bank[r] + sum(p.res[r] for p in g.players) for r in RESOURCES}
    _, events = rules.apply_cmd(g, 0, {"type": f"move_{piece}", "tile": tile, "victim": 1})
    assert getattr(g, f"{piece}_tile") == tile
    assert getattr(g, "robber_tile" if piece == "pirate" else "pirate_tile") == getattr(
        before, "robber_tile" if piece == "pirate" else "pirate_tile")
    assert sum(g.players[0].res.values()) == sum(before.players[0].res.values()) + 1
    assert sum(g.players[1].res.values()) == sum(before.players[1].res.values()) - 1
    assert supply == {r: g.bank[r] + sum(p.res[r] for p in g.players) for r in RESOURCES}
    assert len(events) == 1 and events[0]["stolen"] in RESOURCES
    assert g.pending_action is None and g.pending_pid is None and g.pending_victims == []
    # Same tile, another tile, and the legacy victim alias cannot repeat the theft.
    for target in (tile, next(t for t, h in enumerate(g.tiles)
                             if h.terrain == "sea" and t != g.pirate_tile)):
        rejected_unchanged(g, {"type": "move_pirate", "tile": target, "victim_pid": 1},
                           "No robber/pirate move pending")
    land = next(t for t, h in enumerate(g.tiles) if h.terrain != "sea" and t != g.robber_tile)
    rejected_unchanged(g, {"type": "move_robber", "tile": land}, "No robber move pending")


def test_pirate_cannot_skip_seven_discards(pirate_game):
    g = pirate_game
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 7})
    assert g.pending_action == "discard" and g.discard_required
    tile = pirate_targets(g)[0]
    rejected_unchanged(g, {"type": "move_pirate", "tile": tile, "victim": 1},
                       "Resolve discard first")
    finish_discards(g)
    rules.apply_cmd(g, 0, {"type": "move_pirate", "tile": tile, "victim": 1})
    assert g.pending_action is None


@pytest.mark.parametrize("invalid", ["same_tile", "land", "victim", "wrong_player", "wrong_pending_owner"])
def test_invalid_pirate_preserves_event_and_all_state(pirate_game, invalid):
    g = pirate_game
    begin_movement(g, "knight")
    tile = pirate_targets(g)[0]
    cmd, pid = {"type": "move_pirate", "tile": tile, "victim": 1}, 0
    message = ""
    if invalid == "same_tile":
        cmd["tile"], message = g.pirate_tile, "Same pirate tile"
    elif invalid == "land":
        cmd["tile"] = next(t for t, h in enumerate(g.tiles) if h.terrain != "sea")
        message = "Expected sea hex"
    elif invalid == "victim":
        cmd["victim"], message = 0, "Victim is not eligible"
    elif invalid == "wrong_player":
        pid, message = 1, "Not your turn"
    else:
        g.pending_pid, message = 1, "Not your robber/pirate move"
    rejected_unchanged(g, cmd, message, pid)
    if invalid == "wrong_pending_owner":
        g.pending_pid = 0
    rules.apply_cmd(g, 0, {"type": "move_pirate", "tile": tile, "victim": 1})
    assert g.pending_action is None


def test_pirate_has_ship_victims_not_land_building_victims(pirate_game):
    g = pirate_game
    begin_movement(g, "knight")
    tile = next(t for t, h in enumerate(g.tiles) if h.terrain == "sea" and t != g.pirate_tile
                and 1 in rules._victims_for_tile(g, t, 0)
                and not rules._victims_for_pirate_tile(g, t, 0))
    assert sum(g.players[1].res.values()) > 0
    rejected_unchanged(g, {"type": "move_pirate", "tile": tile, "victim": 1}, "Victim is not eligible")
    before = deepcopy(g)
    _, events = rules.apply_cmd(g, 0, {"type": "move_pirate", "tile": tile})
    assert [p.res for p in g.players] == [p.res for p in before.players]
    assert events[0]["stolen"] is None and g.pending_action is None


def test_new_trigger_allows_another_pirate_action(pirate_game):
    g = pirate_game
    a, b = pirate_targets(g)[:2]
    begin_movement(g, "seven")
    rules.apply_cmd(g, 0, {"type": "move_pirate", "tile": a, "victim": 1})
    g.players[0].dev_cards = [{"type": "knight", "new": False}]
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "knight"})
    before = sum(g.players[0].res.values())
    rules.apply_cmd(g, 0, {"type": "move_pirate", "tile": b})
    assert sum(g.players[0].res.values()) == before + 1 and g.pending_action is None


def test_scenario_without_pirate_keeps_robber_flow():
    g = rules.build_game(1, 2, map_id="seafarers_simple_1")
    finish_setup(g)
    assert not g.rules_config.enable_pirate
    begin_movement(g, "seven")
    sea = next(t for t, h in enumerate(g.tiles) if h.terrain == "sea")
    rejected_unchanged(g, {"type": "move_pirate", "tile": sea}, "Pirate not enabled")
    land = next(t for t, h in enumerate(g.tiles) if h.terrain != "sea" and t != g.robber_tile)
    rules.apply_cmd(g, 0, {"type": "move_robber", "tile": land})
    assert g.robber_tile == land and g.pending_action is None
