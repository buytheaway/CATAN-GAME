"""Replay repaired fixtures using only the recorded authoritative commands."""
from copy import deepcopy
import importlib
import json
import random

import pytest

from app.engine import maps, rules
from tests import run_all
from tests.harness.engine import GameDriver, ScenarioFailure
from tests.harness.invariants import check_invariants
from tests.scenarios.utils import run_coastal_setup, run_setup_snake


REPAIRED = (
    "scenario_dev_cards_effects", "scenario_dev_cards_restrictions",
    "scenario_largest_army_award", "scenario_ports_trade_rates",
    "scenario_rules_limits", "scenario_seafarers_move_ship",
    "scenario_seafarers_pirate_move", "scenario_seafarers_ship_build",
    "scenario_bank_trade_shortage", "scenario_robber_7_flow",
)


def observe(driver, action, result):
    assert result["ok"], (action, result)
    assert check_invariants(driver.game, driver.expected_totals) == []


def replay(driver):
    game = deepcopy(driver.initial_game)
    assert game.phase == "setup" and not game.occupied_v
    assert not game.occupied_e and not game.occupied_ships
    assert all(not sum(player.res.values()) and not player.dev_cards for player in game.players)
    assert len(driver.steps) == len(driver.outcomes)
    theft = random.Random(driver.seed ^ 0xCA7A)
    for step, outcome in zip(driver.steps, driver.outcomes):
        assert step == outcome["action"]
        assert step["type"] != "grant_resources"
        before = deepcopy(game)
        try:
            rules.apply_cmd(game, step.get("pid", game.turn), step, theft_rng=theft)
        except rules.RuleError as error:
            assert outcome.get("expected_rejection")
            assert not outcome["result"]["ok"]
            assert (error.code, error.message) == (outcome["result"]["error"], outcome["result"]["message"])
            assert game == before
        else:
            assert outcome["result"]["ok"] and not outcome.get("expected_rejection")
        assert check_invariants(game, driver.expected_totals) == []
        for player in game.players:
            buildings = sum(level for owner, level in game.occupied_v.values() if owner == player.pid)
            hidden = sum(card["type"] == "victory_point" for card in player.dev_cards)
            special = len(game.scenario.awarded_islands.get(player.pid, ())) * game.scenario.rules.new_island_vp
            achievements = 2 * ((game.longest_road_owner == player.pid) + (game.largest_army_owner == player.pid))
            assert player.vp == buildings + hidden + special + achievements
    # Detect unrecorded inventory, placement, turn, pending, deck or VP edits.
    assert game == driver.game


@pytest.mark.parametrize("scenario", REPAIRED)
@pytest.mark.parametrize("seed", [1, 17])
def test_repaired_scenarios_replay_without_state_shortcuts(scenario, seed):
    driver = GameDriver(seed)
    driver.on_step = observe
    importlib.import_module("tests.scenarios." + scenario).run(driver)
    replay(driver)


def test_turn_helpers_preserve_pre_roll_rejection_and_resolve_actual_seven():
    driver = GameDriver(17)
    driver.on_step = observe
    run_setup_snake(driver)
    driver.reject({"type": "end_turn", "pid": 0}, error="illegal", message="Must roll before actions")
    before = deepcopy(driver.game)
    with pytest.raises(ScenarioFailure, match="current live main turn"):
        driver.begin_turn(1, roll=6)
    assert driver.game == before
    driver.ensure_resources(0, {"wood": 8})
    driver.finish_turn()
    driver.advance_to(0)
    start = len(driver.steps)
    driver.begin_turn(0, roll=7)
    choices = driver.steps[start:]
    assert choices[0] == {"type": "roll", "pid": 0, "roll": 7}
    assert any(action["type"] == "discard" for action in choices)
    assert choices[-1]["type"] == "move_robber"
    assert driver.game.rolled and driver.game.pending_action is None
    replay(driver)


def test_expected_rejection_does_not_accept_the_wrong_reason():
    driver = GameDriver(1)
    run_setup_snake(driver)
    before = deepcopy(driver.game)
    with pytest.raises(ScenarioFailure, match="unexpected rejection result"):
        driver.reject({"type": "trade_bank", "pid": 0, "give": "wood", "get": "ore"},
                      error="illegal", message="Bank has not enough resources")
    assert driver.game == before
    assert driver.outcomes[-1]["result"]["message"] == "Must roll before actions"


def test_expected_rejection_cannot_turn_an_engine_crash_into_a_pass(monkeypatch):
    driver = GameDriver(1)
    before = deepcopy(driver.game)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic engine defect")

    monkeypatch.setattr(rules, "apply_cmd", broken)
    with pytest.raises(ScenarioFailure, match="unexpected rejection result"):
        driver.reject({"type": "end_turn", "pid": 0})
    assert driver.game == before
    assert "RuntimeError" in driver.outcomes[-1]["result"]["exception"]


@pytest.mark.parametrize("pid", [0, 1])
@pytest.mark.parametrize("seed", [1, 17])
def test_coastal_opening_uses_actual_setup_ship_and_unblocked_original_edges(pid, seed):
    driver = GameDriver(seed)
    data = maps.get_preset_map("seafarers_simple_1")
    data["rules"] = dict(data.get("rules", {}), enable_pirate=True)
    driver.replace_game(rules.build_game(seed=seed, max_players=2, map_data=data))
    driver.on_step = observe
    anchor = run_coastal_setup(driver, pid=pid, initial_ship=True)
    assert driver.game.phase == "main" and len(driver.game.occupied_v) == 4
    assert any(owner == pid and anchor in edge for edge, owner in driver.game.occupied_ships.items())
    assert not driver.game.ships_built_this_turn
    replay(driver)


@pytest.mark.parametrize("crash", [False, True])
def test_runner_failure_report_records_reproducible_inputs_and_returns_failure(tmp_path, monkeypatch, crash):
    original = rules.apply_cmd

    def execute(game, pid, command, **kwargs):
        if crash and command["type"] == "broken_fixture":
            raise RuntimeError("synthetic harness defect")
        return original(game, pid, command, **kwargs)

    def scenario(driver):
        run_setup_snake(driver)
        driver.do({"type": "broken_fixture" if crash else "end_turn", "pid": 0})

    monkeypatch.setattr(rules, "apply_cmd", execute)
    module = type("Fixture", (), {"SEEDS": [17]})
    monkeypatch.setattr(run_all, "_load_scenarios", lambda: [{"name": "scenario_failure_probe",
                                                           "module": module, "run": scenario}])
    assert run_all.main(tmp_path) == 1
    report = json.loads(next(tmp_path.glob("report_*.json")).read_text(encoding="utf-8"))
    assert report["summary"] == {"total": 1, "passed": 0, "failed": 1}
    failure = report["failures"][0]
    assert failure["scenario"] == "scenario_failure_probe" and failure["seed"] == 17
    assert failure["kind"] == ("crash" if crash else "rule")
    assert failure["outcomes"][-1]["result"]["ok"] is False
    assert failure["steps"][-1] == failure["details"]["action"]
    assert "seed=17" in (tmp_path / "BUG_REPORT.md").read_text(encoding="utf-8")


def test_matrix_preserves_original_scenario_ids_and_seed_count():
    scenarios = run_all._load_scenarios()
    assert len(scenarios) == 29
    pairs = [(scenario["name"], seed) for scenario in scenarios
             for seed in getattr(scenario["module"], "SEEDS", run_all.DEFAULT_SEEDS)]
    assert len(pairs) == len(set(pairs)) == 508
    assert all((name, seed) in pairs for name in REPAIRED for seed in range(1, 21))
