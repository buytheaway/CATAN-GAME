"""Match provenance, independent of the engine snapshot format.

Only creation assigns a ruleset. Decoding a snapshot is never evidence that
its derived scores were produced by the current gameplay rules.
"""
from app.engine.exploration import has_fog, validate_fog_transition

LEGACY_S1_RULESET = "catan-seafarers-s1"
LEGACY_S2B1_RULESET = "catan-seafarers-s2b-1"
CURRENT_RULESET = "catan-seafarers-s2b-2"
COMPATIBILITY_MESSAGE = (
    "This match uses an older or unverified ruleset. Gameplay is restricted; "
    "the saved match is preserved. Return Home to create a new game."
)


def compatibility(ruleset_id, game=None):
    compatible = (not has_fog(game) and (ruleset_id in (CURRENT_RULESET, LEGACY_S2B1_RULESET) or (ruleset_id == LEGACY_S1_RULESET
        and (game is None or (game.scenario.rules.starting_islands is None
                             and game.scenario.rules.new_island_vp == 0)))))
    return {"status": "compatible" if compatible else "compatibility_required",
            "ruleset_id": ruleset_id, "current_ruleset_id": CURRENT_RULESET}


def restricted(room):
    return (room is not None and room.game is not None
            and compatibility(room.ruleset_id, room.game)["status"] != "compatible")


class RulesetCompatibilityError(RuntimeError):
    pass


def validate_transition(before, candidate, *, snapshot=False, receipt=None, operation=None):
    """Fence all commit paths, including metadata-only reconnect and RAM tests."""
    if before and before.match_uuid == candidate.match_uuid and before.ruleset_id != candidate.ruleset_id:
        raise RulesetCompatibilityError("An existing match's ruleset is immutable")
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
    if (snapshot or receipt or operation and operation["kind"] in ("start_match", "rematch")
            or any(getattr(before, key) != getattr(candidate, key) for key in
                   ("game", "match_uuid", "match_id", "ruleset_id", "tick", "timer", "timer_paused", "status"))):
        raise RulesetCompatibilityError(COMPATIBILITY_MESSAGE)
