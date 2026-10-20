"""Versioned Base random placement; historical boards are never regenerated."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random

import pytest

from app.engine import maps, rules
from app.persistence import snapshots


FIXTURES = Path(__file__).with_name("fixtures")


def red_edges(game):
    return [(edge, ids) for edge, ids in game.edge_adj_hexes.items()
            if len(ids) == 2 and all(game.tiles[i].number in (6, 8) for i in ids)]


@pytest.mark.parametrize("players", [3, 4])
def test_seed17_fixed_but_historical_snapshot_is_unchanged(players, monkeypatch):
    old = snapshots.loads_snapshot((FIXTURES / "base_standard_seed17_legacy_v4.json").read_text())
    assert (old.tiles[9].number, old.tiles[10].number) == (8, 6)
    assert ((21, 31), [9, 10]) in red_edges(old)
    game = rules.build_game(17, players, map_id="base_standard")
    assert not red_edges(game)
    assert [(t.q, t.r, t.terrain, t.center) for t in game.tiles] == [
        (t.q, t.r, t.terrain, t.center) for t in old.tiles]
    assert game.ports == old.ports and game.dev_deck == old.dev_deck
    assert game.vertices == old.vertices and game.edges == old.edges

    def forbidden(*args, **kwargs):
        raise AssertionError("loading materialized history must not generate maps")

    monkeypatch.setattr(maps, "build_board_from_map", forbidden)
    monkeypatch.setattr(rules, "build_game", forbidden)
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(old)) == old
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(game)) == game


def test_thousand_seeds_inventory_edges_determinism_diversity_and_rng():
    recipe = maps.get_preset_map("base_standard")
    original = deepcopy(recipe)
    legacy_recipe = deepcopy(recipe)
    legacy_recipe.pop("number_placement", None)
    legacy_recipe["name"] = "unconstrained_reference"
    signatures = set()
    original_violations = set()
    for seed in range(1000):
        for players in (3, 4):
            game = rules.build_game(seed, players, map_id="base_standard")
            assert not red_edges(game), (seed, players, red_edges(game))
            assert Counter(t.terrain for t in game.tiles) == Counter(recipe["terrain_deck"])
            assert Counter(t.number for t in game.tiles if t.number is not None) == Counter(recipe["number_deck"])
            assert [i for i, t in enumerate(game.tiles) if t.number is None] == [game.robber_tile]
            assert game.tiles[game.robber_tile].terrain == "desert"
            assert game == rules.build_game(seed, players, map_id="base_standard")
        signatures.add(tuple((t.terrain, t.number) for t in game.tiles))
        new_rng, old_rng = random.Random(seed), random.Random(seed)
        board, _, _ = maps.build_board_from_map(recipe, new_rng, 58.0)
        old_board, _, _ = maps.build_board_from_map(legacy_recipe, old_rng, 58.0)
        collisions = [ids for ids in old_board.edge_adj_hexes.values() if len(ids) == 2
                      and all(old_board.tiles[i].number in (6, 8) for i in ids)]
        original_violations.update(tuple(sorted(old_board.tiles[i].number for i in ids)) for ids in collisions)
        if not collisions:
            assert board.tiles == old_board.tiles
        assert new_rng.getstate() == old_rng.getstate()
        assert board.ports == old_board.ports
        assert [(t.q, t.r, t.terrain) for t in board.tiles] == [
            (t.q, t.r, t.terrain) for t in old_board.tiles]
    assert len(signatures) == 1000
    assert original_violations == {(6, 6), (6, 8), (8, 8)}
    assert recipe == original


def test_other_presets_remain_byte_identical_to_pre_fix():
    manifest = json.loads((FIXTURES / "number_placement_unaffected_sha256.json").read_text())
    for key, expected in manifest.items():
        map_id, seed, players = key.split(":")
        game = rules.build_game(int(seed), int(players), map_id=map_id)
        assert hashlib.sha256(snapshots.dumps_snapshot(game).encode()).hexdigest() == expected, key


def test_gallery_uses_corrected_production_board():
    path = Path(__file__).parents[1] / "web/e2e/art-review-boards.py"
    spec = importlib.util.spec_from_file_location("art_review_boards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    public = module.display_board("base_standard", 4)
    from app.engine.serialize import to_player_dict
    game = rules.build_game(17, 4, map_id="base_standard")
    assert public["tiles"] == to_player_dict(game, 0)["tiles"]
    assert not red_edges(game)


@pytest.mark.parametrize("marker", [None, "unknown_v2", [], True])
def test_invalid_placement_policy_rejected(marker):
    recipe = maps.get_preset_map("base_standard")
    recipe["number_placement"] = marker
    with pytest.raises(maps.MapValidationError, match="unsupported number_placement"):
        maps.validate_map_data(recipe)


def test_policy_is_explicit_and_rejects_fixed_or_nonstandard_recipes():
    recipe = maps.get_preset_map("base_standard")
    recipe["tiles"][0]["number"] = 2
    with pytest.raises(maps.MapValidationError, match="19 random tiles"):
        maps.validate_map_data(recipe)
    recipe = maps.get_preset_map("base_standard")
    recipe["number_deck"][0] = 6
    with pytest.raises(maps.MapValidationError, match="standard number deck"):
        maps.validate_map_data(recipe)


def test_old_canonical_lobby_recipe_uses_current_generation_only_on_new_build():
    legacy = maps.get_preset_map("base_standard")
    legacy.pop("number_placement")
    source = deepcopy(legacy)
    game = rules.build_game(17, 4, map_data=legacy)
    assert game == rules.build_game(17, 4, map_id="base_standard")
    assert legacy == source
    # A custom derivative without opt-in is not silently repaired.
    legacy["name"] = "custom_unconstrained"
    custom = rules.build_game(17, 4, map_data=legacy)
    old = snapshots.loads_snapshot((FIXTURES / "base_standard_seed17_legacy_v4.json").read_text())
    assert custom.tiles == old.tiles
