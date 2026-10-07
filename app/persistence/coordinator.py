"""Commit gate; no gameplay rules, socket publication or SQL in callers."""
import logging
import asyncio
from .errors import PersistenceUnavailable, CommitUncertain, RecoveryError
from .repositories import Repository
from .recovery import restore_room, match_checkpoint, checksum, room_config

log = logging.getLogger(__name__)


class Coordinator:
    def __init__(self, database=None):
        self.database = database
        self.repository = Repository(database) if database else None
        self.ready = database is None
        self.quarantined_codes = set()
        self.reserved_codes = set()

    async def initialize(self, manager):
        if not self.database:
            log.info("Persistence mode: explicit local in-memory runtime")
            return
        await self.database.migrate()
        statuses = await self.repository.codes()
        self.reserved_codes = set(statuses)
        self.quarantined_codes = {code for code, status in statuses.items() if status == "quarantined"}
        for room_id in await self.repository.recoverable_ids():
            bundle = await self.repository.load(room_id)
            try:
                room = restore_room(bundle)
            except (ValueError, KeyError, TypeError, OverflowError):
                await self.repository.quarantine(room_id)
                self.quarantined_codes.add(bundle["room"]["room_code"])
                log.error("Room recovery quarantined: room_id=%s (invalid checkpoint)", room_id)
                continue
            manager.rooms[room.room_code] = room
        self.ready = True

    async def commit(self, before, candidate, **kwargs):
        if not self.ready or (before and before.persistence_blocked):
            raise PersistenceUnavailable("Persistence temporarily unavailable")
        if not self.repository:
            candidate.durable_revision = (before.durable_revision if before else 0) + 1
            return
        try:
            await self.repository.save(before, candidate, **kwargs)
        except asyncio.CancelledError:
            self.ready = False
            raise
        except CommitUncertain:
            # A metadata/head lookup resolves whether this EXACT candidate committed.
            try:
                bundle = await self.repository.load(candidate.id)
                expected = (before.durable_revision if before else 0) + 1
                if bundle and bundle["room"]["durable_revision"] == expected:
                    restored = restore_room(bundle)
                    landed = (restored.match_id == candidate.match_id and restored.tick == candidate.tick
                              and bundle["room"]["config"] == room_config(candidate)
                              and [p.id for p in restored.players if p.name] == [p.id for p in candidate.players if p.name])
                    landed = landed and [(p.user_id, p.token_revoked_at) for p in restored.players if p.name] == [
                        (p.user_id, p.token_revoked_at) for p in candidate.players if p.name]
                    if kwargs.get("snapshot") and candidate.game:
                        landed = landed and checksum(bundle["head"]["payload"]) == checksum(match_checkpoint(candidate))
                    receipt = kwargs.get("receipt")
                    if receipt:
                        known = await self.repository.receipt(receipt["match_player_id"], receipt["seq"], receipt["cmd_id"])
                        landed = landed and known is not None and known["result_revision"] == expected and all(
                            known[k] == receipt[k] for k in ("cmd_id", "seq", "payload_hash", "outcome", "error_code"))
                    operation = kwargs.get("operation")
                    if operation:
                        known = await self.repository.operation(candidate.id, operation["request_id"])
                        landed = landed and known is not None and all(known[k] == operation[k] for k in operation)
                    if landed:
                        candidate.durable_revision = expected
                        return
            except Exception:
                pass
            if before:
                before.persistence_blocked = True
            self.ready = False
            raise PersistenceUnavailable("Commit unresolved; room fenced until recovery") from None
        except PersistenceUnavailable:
            if before:
                before.persistence_blocked = True
            self.ready = False
            raise
        self.reserved_codes.add(candidate.room_code)

    async def resolve(self, room):
        """Read current head, never re-execute an uncertain command."""
        bundle = await self.repository.load(room.id)
        if bundle is None:
            raise PersistenceUnavailable("Durable room missing")
        try:
            recovered = restore_room(bundle)
        except (ValueError, KeyError, TypeError, OverflowError):
            await self.repository.quarantine(room.id)
            self.quarantined_codes.add(room.room_code)
            raise RecoveryError("Room checkpoint quarantined") from None
        return recovered

    async def close(self):
        if self.database:
            await self.database.close()
