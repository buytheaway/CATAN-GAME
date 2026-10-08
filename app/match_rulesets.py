"""Match provenance, independent of the engine snapshot format.

Only creation assigns a ruleset. Decoding a snapshot is never evidence that
its derived scores were produced by the current gameplay rules.
"""
CURRENT_RULESET = "catan-seafarers-s1"
COMPATIBILITY_MESSAGE = (
    "This match uses an older or unverified ruleset. Gameplay is restricted; "
    "the saved match is preserved. Return Home to create a new game."
)


def compatibility(ruleset_id):
    return {"status": "compatible" if ruleset_id == CURRENT_RULESET else "compatibility_required",
            "ruleset_id": ruleset_id, "current_ruleset_id": CURRENT_RULESET}


def restricted(room):
    return room is not None and room.game is not None and room.ruleset_id != CURRENT_RULESET


class RulesetCompatibilityError(RuntimeError):
    pass


def validate_transition(before, candidate, *, snapshot=False, receipt=None, operation=None):
    """Fence all commit paths, including metadata-only reconnect and RAM tests."""
    if before and before.match_uuid == candidate.match_uuid and before.ruleset_id != candidate.ruleset_id:
        raise RulesetCompatibilityError("An existing match's ruleset is immutable")
    if not restricted(before):
        return
    if (snapshot or receipt or operation and operation["kind"] in ("start_match", "rematch")
            or any(getattr(before, key) != getattr(candidate, key) for key in
                   ("game", "match_uuid", "match_id", "ruleset_id", "tick", "timer", "timer_paused", "status"))):
        raise RulesetCompatibilityError(COMPATIBILITY_MESSAGE)
