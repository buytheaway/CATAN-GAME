"""Sanitized persistence errors: never include DB URLs, SQL values or state."""
class PersistenceUnavailable(RuntimeError):
    pass


class CommitUncertain(PersistenceUnavailable):
    pass


class RecoveryError(ValueError):
    pass
