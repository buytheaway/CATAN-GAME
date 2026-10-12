"""B1/B2: card-weighted theft and simultaneous ordinary production.

Controlled draws enumerate individual card positions, rather than relying on
statistical sampling. Sea Ring exercises a real board, setup and JSON codec.
"""
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.legal import board_legal_moves
from app.engine.state import BoardState, GameState, PlayerState, RESOURCES, Tile
from app.persistence.snapshots import dumps_snapshot, loads_snapshot, encode_snapshot, decode_snapshot
from tests.test_persistence_snapshots import (
    give_card, released_v1_payload, released_v2_payload, released_v3_payload,
)
from tests.test_pirate_lifecycle import finish_setup


class FixedDraw:
    def __init__(self, ticket):
        self.ticket = ticket
        self.stops = []

    def randrange(self, stop):
        assert 0 <= self.ticket < stop
        self.stops.append(stop)
        return self.ticket


def totals(game):
    return {r: game.bank[r] + sum(p.res[r] for p in game.players) for r in RESOURCES}


def empty_hands(game):
    for p in game.players:
        for resource in RESOURCES:
            game.bank[resource] += p.res[resource]
            p.res[resource] = 0


def theft_game(figure="robber", trigger="seven"):
    game = rules.build_game(17, 3, map_id="base_standard" if figure == "robber"
                            else "seafarers_gold_haven")
    finish_setup(game)
    empty_hands(game)
    rules.apply_cmd(game, 1, {"type": "grant_resources", "res": {"wood": 3, "ore": 1}})
    if figure == "pirate":
        tile, edge = next((t, e) for e in sorted(game.edges)
                          for t in game.edge_adj_hexes[e]
                          if game.tiles[t].terrain == "sea" and t != game.pirate_tile
                          and e not in game.occupied_e)
        game.occupied_ships[edge] = 1
    else:
        tile = next(t for t in range(len(game.tiles)) if t != game.robber_tile
                    and game.tiles[t].terrain not in ("sea", "gold")
                    and 1 in rules._victims_for_tile(game, t, 0))
    if trigger == "knight":
        give_card(game, "knight")
        rules.apply_cmd(game, 0, {"type": "play_dev", "card": "knight"})
    elif trigger == "seven":
        rules.apply_cmd(game, 0, {"type": "roll", "roll": 7})
    if trigger != "ready":
        assert game.pending_action == "robber_move" and game.pending_pid == 0
    return game, {"type": "move_" + figure, "tile": tile, "victim": 1}


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("ticket,expected", [(0, "wood"), (1, "wood"), (2, "wood"), (3, "ore")])
def test_theft_draws_each_individual_card_with_quantity_weight(monkeypatch, reverse, ticket, expected):
    game, _ = theft_game()
    if reverse:
        game.players[1].res = dict(reversed(list(game.players[1].res.items())))
    rng = FixedDraw(ticket)
    monkeypatch.setattr(rules, "_THEFT_RNG", rng, raising=False)
    before = deepcopy(game)
    stolen = rules._steal_one(game, 0, 1)
    assert stolen == expected
    assert rng.stops == [4]
    assert game.players[0].res[expected] == before.players[0].res[expected] + 1
    assert game.players[1].res[expected] == before.players[1].res[expected] - 1
    assert sum(game.players[0].res.values()) == 1
    assert sum(game.players[1].res.values()) == 3
    assert game.bank == before.bank and totals(game) == totals(before)


@pytest.mark.parametrize("figure", ["robber", "pirate"])
@pytest.mark.parametrize("trigger", ["seven", "knight"])
@pytest.mark.parametrize("ticket,expected", [(0, "wood"), (3, "ore")])
def test_seven_and_knight_use_the_same_weighted_theft(monkeypatch, figure, trigger, ticket, expected):
    game, cmd = theft_game(figure, trigger)
    rng = FixedDraw(ticket)
    monkeypatch.setattr(rules, "_THEFT_RNG", rng, raising=False)
    before = totals(game)
    _, events = rules.apply_cmd(game, 0, cmd)
    assert events[-1]["stolen"] == expected
    assert game.players[0].res[expected] == 1 and rng.stops == [4]
    assert game.pending_action is None and game.pending_pid is None
    assert totals(game) == before
    after = deepcopy(game)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(game, 0, cmd)
    assert game == after and rng.stops == [4]


@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_empty_victim_never_draws_or_transfers(monkeypatch, figure):
    game, cmd = theft_game(figure)
    empty_hands(game)
    rng = FixedDraw(0)
    monkeypatch.setattr(rules, "_THEFT_RNG", rng, raising=False)
    before = deepcopy(game)
    assert rules._steal_one(game, 0, 1) is None
    assert game == before and not rng.stops
    cmd.pop("victim")
    _, events = rules.apply_cmd(game, 0, cmd)
    assert events[-1]["victim"] is None and events[-1]["stolen"] is None
    assert totals(game) == totals(before) and not rng.stops


@pytest.mark.parametrize("figure", ["robber", "pirate"])
@pytest.mark.parametrize("invalid", ["victim", "tile", "owner"])
def test_rejected_theft_preserves_state_and_never_draws(monkeypatch, figure, invalid):
    game, cmd = theft_game(figure)
    pid = 0
    if invalid == "victim":
        cmd["victim"] = 2
    elif invalid == "tile":
        cmd["tile"] = len(game.tiles)
    else:
        pid = 1
    rng = FixedDraw(3)
    monkeypatch.setattr(rules, "_THEFT_RNG", rng, raising=False)
    before = dumps_snapshot(game)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(game, pid, cmd)
    assert dumps_snapshot(game) == before and not rng.stops


@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_legal_projection_never_draws_the_gameplay_theft_rng(monkeypatch, figure):
    game, cmd = theft_game(figure)
    rng = FixedDraw(3)
    monkeypatch.setattr(rules, "_THEFT_RNG", rng)
    before = dumps_snapshot(game)
    legal = board_legal_moves(game, 0)
    assert cmd["tile"] in legal[figure + "_tiles"]
    assert 1 in legal[figure + "_victims"][str(cmd["tile"])]
    assert dumps_snapshot(game) == before and not rng.stops


def production_game(wood_buildings, bank_wood, *, blocked=False, reverse=False):
    """Minimal production-only board, with independent brick production."""
    game = GameState(seed=17, max_players=3, players=[PlayerState(i, str(i)) for i in range(3)],
                     board=BoardState(tiles=[Tile(0, 0, "forest", 6, (0, 0)),
                                            Tile(1, 0, "hills", 6, (1, 0))]),
                     robber_tile=0 if blocked else -1, robbers=[0] if blocked else [])
    entries = [(v, (pid, level)) for v, (pid, level) in enumerate(wood_buildings)]
    entries.append((len(entries), (2, 1)))
    game.occupied_v = dict(reversed(entries) if reverse else entries)
    game.vertex_adj_hexes = {v: [0] for v in range(len(wood_buildings))}
    game.vertex_adj_hexes[len(wood_buildings)] = [1]
    game.bank["wood"] = bank_wood
    game.players[2].res["wood"] = 19 - bank_wood
    return game


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("buildings,stock,expected", [
    ([(0, 1), (1, 1)], 1, (0, 0)),
    ([(0, 1), (1, 2)], 2, (0, 0)),
    ([(0, 2), (1, 2)], 3, (0, 0)),
    ([(0, 1), (1, 2)], 3, (1, 2)),
    ([(0, 1), (1, 2)], 4, (1, 2)),
    ([(0, 2)], 1, (1, 0)),
    ([(0, 1), (0, 2)], 2, (2, 0)),
    ([(0, 1), (1, 2)], 0, (0, 0)),
    ([(0, 2)], 0, (0, 0)),
])
def test_shortage_counts_all_demand_per_resource_and_player(reverse, buildings, stock, expected):
    game = production_game(buildings, stock, reverse=reverse)
    before = totals(game)
    rules.distribute_for_roll(game, 6)
    assert tuple(p.res["wood"] for p in game.players[:2]) == expected
    assert game.bank["wood"] == stock - sum(expected)
    assert game.players[2].res["brick"] == 1 and game.bank["brick"] == 18
    assert totals(game) == before


def test_robber_blocks_demand_and_other_numbers_produce_nothing():
    game = production_game([(0, 2), (1, 1)], 1, blocked=True)
    before = deepcopy(game)
    rules.distribute_for_roll(game, 5)
    assert game == before
    rules.distribute_for_roll(game, 6)
    assert game.players[0].res["wood"] == game.players[1].res["wood"] == 0
    assert game.bank["wood"] == 1 and game.players[2].res["brick"] == 1
    assert totals(game) == totals(before)


def test_blocked_recipient_does_not_cancel_the_only_unblocked_players_partial_yield():
    game = production_game([(0, 2), (1, 2)], 1, blocked=True)
    game.tiles.append(Tile(0, 1, "forest", 6, (0, 1)))
    game.vertex_adj_hexes[1] = [2]
    before = totals(game)
    rules.distribute_for_roll(game, 6)
    assert game.players[0].res["wood"] == 0 and game.players[1].res["wood"] == 1
    assert game.bank["wood"] == 0 and totals(game) == before


def test_demand_is_aggregated_across_hexes_not_only_across_buildings():
    game = production_game([(0, 2), (1, 1)], 3)
    game.tiles.append(Tile(0, 1, "forest", 6, (0, 1)))
    game.vertex_adj_hexes[0] = [0, 2]  # City produces four, the other player one.
    before = totals(game)
    rules.distribute_for_roll(game, 6)
    assert game.players[0].res["wood"] == game.players[1].res["wood"] == 0
    assert game.bank["wood"] == 3 and totals(game) == before


def sea_ring_shortage():
    game = rules.build_game(17, 2, map_id="seafarers_simple_2")
    tile = next(i for i, t in enumerate(game.tiles) if t.terrain == "forest")
    assert game.tiles[tile].number == 2
    vertices = sorted((v for v, ts in game.vertex_adj_hexes.items() if tile in ts), key=str)
    chosen = []
    while game.phase == "setup":
        if game.setup_need == "settlement":
            if not chosen:
                vid = vertices[-1]
            elif len(chosen) == 1:
                vid = next(v for v in vertices if rules.can_place_settlement(game, game.turn, v, False))
            else:
                vid = next(v for v in sorted(game.vertices)
                           if rules.can_place_settlement(game, game.turn, v, False)
                           and not any(game.tiles[t].terrain == "forest" and game.tiles[t].number == 2
                                       for t in game.vertex_adj_hexes[v]))
            rules.apply_cmd(game, game.turn, {"type": "place_settlement", "vid": vid})
            chosen.append(vid)
        else:
            edge = next(e for e in sorted(game.edges)
                        if rules.can_place_road(game, game.turn, e, game.setup_anchor_vid))
            rules.apply_cmd(game, game.turn, {"type": "place_road", "eid": list(edge)})
    empty_hands(game)
    rules.apply_cmd(game, 0, {"type": "grant_resources", "res": {"wood": 18}})
    return game


def test_sea_ring_seed_17_roll_2_is_order_and_codec_independent():
    game = sea_ring_shortage()
    restored = loads_snapshot(dumps_snapshot(game))
    assert list(game.occupied_v) != list(restored.occupied_v)
    variants = [game, restored, deepcopy(game), deepcopy(restored)]
    for variant in variants[2:]:
        variant.occupied_v = dict(reversed(list(variant.occupied_v.items())))
        variant.vertex_adj_hexes = {v: list(reversed(ts))
                                   for v, ts in reversed(list(variant.vertex_adj_hexes.items()))}
    for variant in variants:
        before = deepcopy(variant)
        rules.apply_cmd(variant, 0, {"type": "roll", "roll": 2})
        assert [p.res["wood"] for p in variant.players] == [18, 0]
        assert variant.bank["wood"] == 1 and totals(variant) == totals(before)
    assert all(([p.res for p in variant.players], variant.bank, variant.rolled,
                variant.pending_action) == ([p.res for p in variants[0].players],
                                           variants[0].bank, variants[0].rolled,
                                           variants[0].pending_action)
               for variant in variants)


@pytest.mark.parametrize("encoder", [released_v1_payload, released_v2_payload,
                                     released_v3_payload, encode_snapshot])
def test_historical_hands_and_finished_results_decode_without_correcting_rules(monkeypatch, encoder):
    game, _ = theft_game()
    # Preserve a recorded outcome even if it came from a historical binary.
    game.players[1].res["wood"] -= 1
    game.players[0].res["wood"] += 1
    game.players[0].vp = game.rules_config.target_vp
    game.game_over = True
    game.winner_pid = 0
    payload = encoder(game)
    before = deepcopy(payload)
    def forbidden(*args, **kwargs):
        pytest.fail("Snapshot reading must not execute theft, production or score repair")
    for name in ("_steal_one", "distribute_for_roll", "update_longest_road", "update_largest_army", "check_win"):
        monkeypatch.setattr(rules, name, forbidden)
    restored = decode_snapshot(payload)
    assert payload == before
    assert restored.players == game.players and restored.bank == game.bank
    assert restored.achievements == game.achievements
    assert restored.game_over and restored.winner_pid == 0
