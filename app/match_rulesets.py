"""Match provenance, independent of the engine snapshot format.

Only creation assigns a ruleset. Decoding a snapshot is never evidence that
its derived scores were produced by the current gameplay rules.
"""
from app.engine.exploration import has_fog, validate_fog_transition

LEGACY_S1_RULESET = "catan-seafarers-s1"
LEGACY_S2B1_RULESET = "catan-seafarers-s2b-1"
CURRENT_RULESET = "catan-seafarers-s2b-2"
OFFICIAL_S3A_RULESET = "catan-seafarers-s3a-new-shores"
COMPATIBILITY_MESSAGE = (
    "This match uses an older or unverified ruleset. Gameplay is restricted; "
    "the saved match is preserved. Return Home to create a new game."
)


def compatibility(ruleset_id, game=None):
    frame = game is not None and game.rules.get("sea_frame") is True
    if ruleset_id == OFFICIAL_S3A_RULESET:
        counts = {"seafarers_official_new_shores_3": 3, "seafarers_official_new_shores_4": 4}
        count = counts.get(game.map_id) if game is not None else None
        compatible = game is None or (
            frame and count is not None and len(game.players) == count
            and game.map_meta.get("id") == game.map_id
            and game.map_meta.get("official_scenario") == "heading_for_new_shores"
            and type(game.map_meta.get("required_players")) is int
            and game.map_meta.get("required_players") == count
            and game.scenario.rules.starting_islands == (0,) and game.scenario.rules.new_island_vp == 2
            and game.rules_config.target_vp == 14 and game.rules_config.discard_threshold == 7)
    elif ruleset_id == LEGACY_S1_RULESET:
        compatible = not frame and (game is None or (game.scenario.rules.starting_islands is None
                                                     and game.scenario.rules.new_island_vp == 0))
    else:
        compatible = not frame and ruleset_id in (CURRENT_RULESET, LEGACY_S2B1_RULESET)
    compatible = compatible and not has_fog(game)
    return {"status": "compatible" if compatible else "compatibility_required",
            "ruleset_id": ruleset_id,
            "current_ruleset_id": OFFICIAL_S3A_RULESET if ruleset_id == OFFICIAL_S3A_RULESET else CURRENT_RULESET}


def restricted(room):
    return (room is not None and room.game is not None
            and compatibility(room.ruleset_id, room.game)["status"] != "compatible")


class RulesetCompatibilityError(RuntimeError):
    pass


def validate_transition(before, candidate, *, snapshot=False, receipt=None, operation=None,
                        trusted_fog=False):
    """Fence all commit paths, including metadata-only reconnect and RAM tests."""
    if before and before.match_uuid == candidate.match_uuid and before.ruleset_id != candidate.ruleset_id:
        raise RulesetCompatibilityError("An existing match's ruleset is immutable")
    if (candidate.game and (candidate.game.rules.get("sea_frame") is True
                            or candidate.ruleset_id == OFFICIAL_S3A_RULESET)
            and compatibility(candidate.ruleset_id, candidate.game)["status"] != "compatible"
            and not restricted(before)):
        raise RulesetCompatibilityError("Official sea-frame rules require verified S3A provenance")
    if candidate.game and has_fog(candidate.game) and candidate.ruleset_id != CURRENT_RULESET:
        # Existing restricted legacy data may retain metadata-only ownership writes.
        if not (before and restricted(before) and before.game == candidate.game
                and before.match_uuid == candidate.match_uuid):
            raise RulesetCompatibilityError("Fog state requires the current ruleset marker")
    if before and before.game and candidate.game and before.match_uuid == candidate.match_uuid:
        try:
            validate_fog_transition(before.game, candidate.game)
        except ValueError as exc:
            raise RulesetCompatibilityError(str(exc)) from None
    if (candidate.game and candidate.ruleset_id == LEGACY_S1_RULESET and restricted(candidate)
            and not restricted(before)):
        raise RulesetCompatibilityError("S1 matches cannot acquire new scenario rules")
    if not restricted(before):
        return
    # Internal engine acceptance may persist an existing native fog fixture.
    # This keyword is never accepted from WS data; public compatibility remains
    # restricted. Unknown provenance, epoch changes and lifecycle operations
    # cannot use it. All assignment/history fences above still apply.
    if (trusted_fog is True and before.ruleset_id == candidate.ruleset_id == CURRENT_RULESET
            and has_fog(before.game) and has_fog(candidate.game)
            and before.match_uuid == candidate.match_uuid and before.match_id == candidate.match_id
            and before.status == candidate.status and before.timer == candidate.timer
            and before.timer_paused == candidate.timer_paused and operation is None
            and (not before.game.game_over or before.game == candidate.game)):
        return
    if (snapshot or receipt or operation and operation["kind"] in ("start_match", "rematch")
            or any(getattr(before, key) != getattr(candidate, key) for key in
                   ("game", "match_uuid", "match_id", "ruleset_id", "tick", "timer", "timer_paused", "status"))):
        raise RulesetCompatibilityError(COMPATIBILITY_MESSAGE)
