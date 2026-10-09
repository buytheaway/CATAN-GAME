"""Largest Army ownership/VP through real Knight commands and frozen snapshots.

Knight counts and victory-boundary scores are explicit fixtures, not full games.
Setup, Knight effects, turn cleanup and serialization use the shared engine.
"""
from copy import deepcopy

import pytest

from app.engine import rules, serialize
from app.persistence import snapshots
from tests.test_persistence_snapshots import (
    assert_equivalent, give_card, main_game, released_v1_payload, released_v2_payload, released_v3_payload,
)
from tests.test_seafarers_scenarios import arrive, scenario_game


@pytest.fixture(params=["base_standard", "seafarers_pirate_lanes"])
def game(request):
    return main_game(request.param, players=3)


def play_knight(g):
    give_card(g, "knight", pid=g.turn)
    rules.apply_cmd(g, g.turn, {"type": "play_dev", "card": "knight"})


def end_turn(g):
    if g.pending_action == "robber_move":
        tile = next(i for i, t in enumerate(g.tiles)
                    if t.terrain != "sea" and i != g.robber_tile)
        rules.apply_cmd(g, g.turn, {"type": "move_robber", "tile": tile})
    if not g.rolled:
        total = next(n for n in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)
                     if n not in {t.number for t in g.tiles if t.terrain == "gold"})
        rules.apply_cmd(g, g.turn, {"type": "roll", "roll": total})
    rules.apply_cmd(g, g.turn, {"type": "end_turn"})


def test_three_knight_minimum_and_holder_growth_award_exactly_two_vp(game):
    original = [p.vp for p in game.players]
    for count in range(1, 5):
        play_knight(game)
        assert game.players[0].knights_played == count
        assert game.largest_army_owner == (0 if count >= 3 else None)
        assert game.largest_army_size == (count if count >= 3 else 0)
        assert [p.vp for p in game.players] == [original[0] + (2 if count >= 3 else 0), *original[1:]]
        if count < 4:
            for _ in game.players:
                end_turn(game)


def test_two_and_three_way_ties_keep_incumbent_then_stronger_knight_transfers(game):
    original = [p.vp for p in game.players]
    for p, count in zip(game.players, (2, 2, 3)):
        p.knights_played = count
    rules.update_largest_army(game)
    held = [*original[:2], original[2] + 2]
    # Holder is P2, not the first tied player. Real turns produce ties at 3/4.
    for pid, count in ((0, 3), (1, 3), (2, 4), (0, 4), (1, 4)):
        assert game.turn == pid
        play_knight(game)
        assert game.players[pid].knights_played == count
        assert game.largest_army_owner == 2
        assert game.largest_army_size == max(p.knights_played for p in game.players)
        assert [p.vp for p in game.players] == held
        before = snapshots.encode_snapshot(game)
        rules.update_largest_army(game)
        assert snapshots.encode_snapshot(game) == before
        end_turn(game)
    end_turn(game)  # P2 passes; P0 can now exceed the holder's four Knights.
    play_knight(game)
    assert (game.largest_army_owner, game.largest_army_size) == (0, 5)
    assert [p.vp for p in game.players] == [original[0] + 2, *original[1:]]
    before = snapshots.encode_snapshot(game)
    rules.update_largest_army(game)
    assert snapshots.encode_snapshot(game) == before


def test_tie_without_holder_stays_unawarded_until_unique_leader(game):
    original = [p.vp for p in game.players]
    game.players[0].knights_played = game.players[1].knights_played = 3
    rules.update_largest_army(game)
    assert (game.largest_army_owner, game.largest_army_size) == (None, 3)
    assert [p.vp for p in game.players] == original
    game.turn = 1
    play_knight(game)
    assert (game.largest_army_owner, game.largest_army_size) == (1, 4)
    assert [p.vp for p in game.players] == [original[0], original[1] + 2, original[2]]


def test_tying_opponent_cannot_remove_waiting_holders_victory_or_win_off_turn(game):
    game.players[0].vp = game.rules_config.target_vp - 3
    give_card(game, "victory_point")
    game.players[0].knights_played, game.players[1].knights_played = 3, 2
    rules.update_largest_army(game)
    game.turn = 1
    play_knight(game)
    assert game.largest_army_owner == 0
    assert game.players[0].vp == game.rules_config.target_vp
    assert not game.game_over and game.winner_pid is None
    assert serialize.to_player_dict(game, 1)["players"][0]["vp"] == game.players[0].vp - 1
    end_turn(game)
    assert not game.game_over  # P2's turn is not the holder's turn.
    end_turn(game)
    assert game.turn == 0 and not game.rolled and game.game_over and game.winner_pid == 0
    assert serialize.to_player_dict(game, 1)["players"][0]["vp"] == game.players[0].vp


def test_strict_transfer_can_win_on_active_players_turn_before_roll(game):
    game.players[0].knights_played = game.players[1].knights_played = 3
    game.largest_army_owner, game.largest_army_size = 0, 3
    game.players[0].vp += 2
    game.players[1].vp = game.rules_config.target_vp - 2
    game.turn = 1
    play_knight(game)
    assert (game.largest_army_owner, game.largest_army_size) == (1, 4)
    assert game.players[0].vp == 2
    assert game.players[1].vp == game.rules_config.target_vp
    assert not game.rolled and game.game_over and game.winner_pid == 1


@pytest.mark.parametrize("invalid", ["new", "wrong_turn"])
def test_rejected_knight_preserves_cards_counts_achievement_and_vp(game, invalid):
    game.players[2].knights_played = 3
    game.players[0].knights_played = 2
    rules.update_largest_army(game)
    pid = 1 if invalid == "wrong_turn" else 0
    give_card(game, "knight", pid=pid, new=invalid == "new")
    before = snapshots.encode_snapshot(game)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(game, pid, {"type": "play_dev", "card": "knight"})
    assert snapshots.encode_snapshot(game) == before


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_snapshot_restores_recorded_army_and_vp_without_recalculating_history(game, version, monkeypatch):
    # Both a retained holder and old unawarded/stale values remain as recorded.
    for owner, counts in ((2, (3, 3, 3)), (None, (3, 3, 0)), (None, (0, 0, 3))):
        g = deepcopy(game)
        for p, count in zip(g.players, counts):
            p.knights_played = count
        g.largest_army_owner, g.largest_army_size = owner, 3
        if owner is not None:
            g.players[owner].vp += 2
        payload = (released_v1_payload(g) if version == 1 else released_v2_payload(g)
                   if version == 2 else released_v3_payload(g) if version == 3 else snapshots.encode_snapshot(g))
        expected = deepcopy(g)
        if version == 1 and g.rules_config.enable_seafarers:
            expected.ship_moved_this_turn = True  # Existing conservative legacy policy.
        def forbidden(*args, **kwargs):
            pytest.fail("Snapshot restoration must not execute gameplay rules")
        with monkeypatch.context() as guard:
            for name in ("update_largest_army", "update_longest_road", "check_win", "apply_cmd", "build_game"):
                guard.setattr(rules, name, forbidden)
            restored = snapshots.decode_snapshot(payload)
        assert_equivalent(expected, restored)


def test_scenario_island_bonus_and_award_ledger_survive_army_tie():
    g = scenario_game()
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": arrive(g)})
    g.players[0].knights_played, g.players[1].knights_played = 3, 2
    rules.update_largest_army(g)
    ledger, vp = deepcopy(g.scenario), [p.vp for p in g.players]
    end_turn(g)
    assert g.turn == 1 and not g.rolled
    play_knight(g)
    assert g.largest_army_owner == 0 and [p.vp for p in g.players] == vp
    assert g.scenario == ledger and g.scenario.awarded_islands == {0: {13}}
    assert serialize.to_player_dict(g, 1)["players"][0]["special_vp"] == 2
    assert_equivalent(g, snapshots.loads_snapshot(snapshots.dumps_snapshot(g)))
