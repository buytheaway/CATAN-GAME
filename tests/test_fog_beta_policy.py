"""Pure beta provenance/configuration checks; no database or test capability."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.engine import rules
from app.engine.exploration import assignment_digest
from app.fog_beta import (BETA_MAP_ID, BETA_RULESET, admission_enabled, beta_descriptor,
                          beta_recipe, emergency_stopped, is_beta_game, is_beta_source,
                          validate_configuration)
from app.match_rulesets import (CURRENT_RULESET, RulesetCompatibilityError, compatibility,
                                restricted, validate_transition)
from app.persistence.recovery import resume_timer
from app.persistence.snapshots import decode_snapshot, encode_snapshot


@pytest.fixture(autouse=True)
def beta_flags(monkeypatch):
    monkeypatch.delenv("CATAN_FOG_BETA_ADMISSION", raising=False)
    monkeypatch.delenv("CATAN_FOG_BETA_EMERGENCY_STOP", raising=False)


@pytest.fixture
def game():
    return rules.build_game(17, 2, map_id=BETA_MAP_ID, map_data=beta_recipe())


def room(game):
    return SimpleNamespace(game=game, match_uuid=uuid4(), match_id=1,
                           ruleset_id=BETA_RULESET, status="in_match", tick=0,
                           timer=None, timer_paused=False)


def test_default_admission_disabled_without_freezing_existing_beta(game):
    assert not admission_enabled() and not emergency_stopped()
    assert is_beta_game(game) and not restricted(room(game))


@pytest.mark.parametrize("admission,stop,expected", [("0", "0", False), ("1", "0", True),
                                                    ("0", "1", False), ("1", "1", False)])
def test_independent_admission_and_emergency_flags(monkeypatch, game, admission, stop, expected):
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", admission)
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", stop)
    assert admission_enabled() is expected
    assert restricted(room(game)) is (stop == "1")


@pytest.mark.parametrize("name", ["CATAN_FOG_BETA_ADMISSION", "CATAN_FOG_BETA_EMERGENCY_STOP"])
@pytest.mark.parametrize("bad", ["true", "yes", "", "2"])
def test_ambiguous_deployment_flags_fail_configuration(monkeypatch, name, bad):
    monkeypatch.setenv(name, bad)
    with pytest.raises(ValueError, match=f"{name} must be 0 or 1"):
        validate_configuration()


def test_recipe_and_descriptor_are_detached_and_not_secret_assignments():
    source, descriptor = beta_recipe(), beta_descriptor()
    assert len(source["tiles"]) == 37 and sum(t["terrain"] == "fog" for t in source["tiles"]) == 8
    assert descriptor["required_players"] == 2 and descriptor["target_vp"] == 12
    assert set(descriptor) == {"id", "name", "description", "required_players", "target_vp", "custom_scenario"}
    assert is_beta_source(source, BETA_MAP_ID)
    source["rules"]["target_vp"] = 3
    descriptor["required_players"] = 4
    assert beta_recipe()["rules"]["target_vp"] == 12 and beta_descriptor()["required_players"] == 2


def test_canonical_source_does_not_accept_boolean_instead_of_integer():
    source = beta_recipe()
    source["version"] = True
    assert not is_beta_source(source, BETA_MAP_ID)
    source = beta_recipe()
    source["rules"]["enable_seafarers"] = 1
    assert not is_beta_source(source, BETA_MAP_ID)


@pytest.mark.parametrize("mutation", ["id", "players", "target", "limit", "rules", "mask", "profile",
                                      "visible", "hidden_pool", "hidden_numbers", "coordinates", "metadata"])
def test_noncanonical_materialized_games_remain_restricted(game, mutation):
    if mutation == "id": game.map_id = "seafarers_fog_natural"
    elif mutation == "players": game.max_players = 3
    elif mutation == "target": game.rules_config.target_vp = 10
    elif mutation == "limit": game.rules_config.max_ships = 16
    elif mutation == "rules": game.rules["enable_gold"] = 1
    elif mutation == "mask": game.scenario.rules = replace(game.scenario.rules, fog=replace(
        game.scenario.rules.fog, initially_hidden=game.scenario.rules.fog.initially_hidden[:-1]))
    elif mutation == "profile": game.scenario.rules = replace(game.scenario.rules, fog=replace(
        game.scenario.rules.fog, profile="future-profile"))
    elif mutation == "visible":
        i = next(i for i in range(len(game.tiles)) if i not in game.scenario.rules.fog.initially_hidden)
        game.tiles[i].terrain = "gold"
    elif mutation == "hidden_pool":
        tile = game.tiles[game.scenario.rules.fog.initially_hidden[0]]
        tile.terrain = "forest" if tile.terrain != "forest" else "desert"
    elif mutation == "hidden_numbers":
        i = next(i for i in game.scenario.rules.fog.initially_hidden if game.tiles[i].number is not None)
        game.tiles[i].number = 12
    elif mutation == "coordinates": game.tiles[0].q = True
    elif mutation == "metadata": game.map_meta["required_players"] = True
    assert not is_beta_game(game) and restricted(room(game))
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(None, room(game), snapshot=True)


def test_private_assignment_varies_without_changing_canonical_provenance(game):
    hidden = game.scenario.rules.fog.initially_hidden
    left, right = hidden[:2]
    for key in ("terrain", "number"):
        a, b = getattr(game.tiles[left], key), getattr(game.tiles[right], key)
        setattr(game.tiles[left], key, b)
        setattr(game.tiles[right], key, a)
    game.scenario.fog = replace(game.scenario.fog, assignment_digest=assignment_digest(game.board))
    assert is_beta_game(game)


def test_metadata_only_emergency_reconnect_preserves_head_but_commands_rejected(monkeypatch, game):
    before = room(game)
    candidate = deepcopy(before)
    original = encode_snapshot(game)
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "1")
    info = compatibility(BETA_RULESET, game)
    assert info["reason"] == "fog_beta_paused"
    validate_transition(before, candidate)
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(before, candidate, snapshot=True)
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(before, candidate, receipt={"seq": 1})
    assert encode_snapshot(game) == original


def test_codec_restore_preserves_recorded_achievement_and_vp_without_recalculation(game, monkeypatch):
    game.players[0].vp = 9
    game.achievements.longest_road_owner = 0
    game.achievements.longest_road_len = 8
    payload = encode_snapshot(game)
    def forbidden(*args, **kwargs):
        pytest.fail("Recovery must not run gameplay rules or RNG")
    monkeypatch.setattr(rules, "build_game", forbidden)
    monkeypatch.setattr(rules, "apply_cmd", forbidden)
    restored = decode_snapshot(payload)
    assert encode_snapshot(restored) == payload and is_beta_game(restored)
    assert restored.players[0].vp == 9 and restored.achievements.longest_road_len == 8


def test_native_internal_marker_cannot_be_silently_reclassified(game):
    before = room(game)
    before.ruleset_id = CURRENT_RULESET
    candidate = deepcopy(before)
    candidate.ruleset_id = BETA_RULESET
    assert restricted(before)
    with pytest.raises(RulesetCompatibilityError, match="immutable"):
        validate_transition(before, candidate, snapshot=True)


def test_beta_never_resumes_timer(game):
    state = room(game)
    state.timer_paused = True
    assert not resume_timer(state) and state.timer_paused
