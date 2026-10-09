"""Explicit aggregate transaction: room, members, head, sequence and receipt."""
import uuid
import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import select, insert, update, delete, or_, and_, func, Integer
from sqlalchemy.dialects.postgresql import insert as pg_insert
from . import models as m
from .credentials import utcnow, token_hash, valid_token
from .inspection import safe_game
from .errors import PersistenceUnavailable, CommitUncertain
from app.auth.security import AuthError, authorize_transaction
from .recovery import room_config, match_checkpoint, checksum
from app.match_rulesets import compatibility, restricted, validate_transition


class Repository:
    def __init__(self, database):
        self.db = database
        self.last_metrics = {}
        self._test_fault = None  # In-process failure injection only; no network/env control.

    def _fault(self, stage):
        if self._test_fault:
            self._test_fault(stage)

    async def inspect_credentials(self, manager, credentials):
        """One metadata SELECT, no private snapshot/config/map definition loading."""
        hashed = [(code, token_hash(raw)) for code, raw in credentials]
        winner = m.match_players.alias("inspection_winner")
        count = (select(func.count()).select_from(m.room_players)
                 .where(m.room_players.c.room_id == m.rooms.c.id, m.room_players.c.status == "active")
                 .correlate(m.rooms).scalar_subquery())
        query = select(
            m.rooms.c.room_code, m.rooms.c.status.label("room_status"), m.rooms.c.max_players,
            m.rooms.c.updated_at, m.room_players.c.name, m.room_players.c.color, m.seat_tokens.c.token_hash,
            m.rooms.c.config["map_meta"]["name"].astext.label("map_name"),
            m.rooms.c.config["rules"]["target_vp"].astext.cast(Integer).label("target_vp"),
            m.matches.c.status.label("match_status"), m.matches.c.ruleset_id, count.label("player_count"),
            winner.c.name.label("winner_name"), winner.c.color.label("winner_color"),
        ).select_from(m.rooms.join(m.room_players, m.room_players.c.room_id == m.rooms.c.id)
                      .join(m.seat_tokens, m.seat_tokens.c.room_player_id == m.room_players.c.id)
                      .outerjoin(m.matches, m.matches.c.id == m.rooms.c.current_match_id)
                      .outerjoin(winner, winner.c.id == m.matches.c.winner_match_player_id)).where(
            or_(*(and_(m.rooms.c.room_code == code, m.seat_tokens.c.token_hash == digest) for code, digest in hashed)),
            m.room_players.c.status == "active", m.room_players.c.current_pid.is_not(None),
            m.seat_tokens.c.revoked_at.is_(None), m.seat_tokens.c.expires_at > utcnow(),
            m.rooms.c.status.in_(("lobby", "in_match", "quarantined")), m.rooms.c.closed_at.is_(None),
            or_(m.rooms.c.expires_at.is_(None), m.rooms.c.expires_at > utcnow()))
        async with self.db.sessions() as session:
            rows = (await session.execute(query)).mappings().all()
        indexed = {(row["room_code"], bytes(row["token_hash"])): row for row in rows}
        results = []
        for (code, raw), key in zip(credentials, hashed):
            row = indexed.get(key)
            if row is None:
                results.append({"status": "invalid"})
                continue
            room = manager.rooms.get(code)
            if room is None or room.persistence_blocked or row["room_status"] == "quarantined":
                results.append({"status": "temporarily_unavailable"})
                continue
            async with room.lock:
                if not any(p.name and valid_token(p, raw) for p in room.players):
                    # A lifecycle commit may have raced the SELECT; reconnect will revalidate.
                    results.append({"status": "temporarily_unavailable"})
                    continue
                results.append(safe_game(
                    room_code=code, map_name=row["map_name"], name=row["name"], color=row["color"],
                    player_count=row["player_count"], max_players=row["max_players"],
                    connected_count=sum(bool(p.name and p.connected) for p in room.players),
                    status="game_over" if row["match_status"] == "finished" else
                           "active" if row["match_status"] == "active" else "lobby",
                    target_vp=row["target_vp"], updated_at=row["updated_at"],
                    ruleset=compatibility(row["ruleset_id"], room.game) if row["match_status"] else None,
                    winner={"name": row["winner_name"], "color": row["winner_color"]} if row["winner_name"] else None))
        return results

    async def save(self, before, candidate, *, snapshot=False, receipt=None, operation=None):
        validate_transition(before, candidate, snapshot=snapshot, receipt=receipt, operation=operation)
        started = perf_counter()
        head = match_checkpoint(candidate) if snapshot and candidate.game else None
        head_checksum = checksum(head) if head else None
        config = room_config(candidate)
        encoded = perf_counter()
        now = utcnow()
        new_revision = (before.durable_revision if before else 0) + 1
        values = dict(id=candidate.id, room_code=candidate.room_code, status=candidate.status,
                      max_players=candidate.max_players, host_room_player_id=candidate.players[candidate.host_pid].id,
                      current_match_id=candidate.match_uuid, match_no=candidate.match_id, tick=candidate.tick,
                      config=config, map_revision=candidate.map_revision, config_revision=candidate.config_revision,
                      durable_revision=new_revision, chat_revision=candidate.chat_revision,
                      chat_history=candidate.chat_history, is_test=candidate.test_mode,
                      created_at=candidate.created_at, updated_at=now,
                      last_activity_at=datetime.fromtimestamp(candidate.last_activity_ts, timezone.utc),
                      closed_at=candidate.closed_at, expires_at=candidate.expires_at)
        committing = False
        async with self.db.sessions() as session:
            try:
                await session.begin()
                await authorize_transaction(session)
                self._fault("before_write")
                if before is None:
                    await session.execute(insert(m.rooms).values(**values))
                else:
                    revision = (await session.execute(select(m.rooms.c.durable_revision)
                               .where(m.rooms.c.id == candidate.id).with_for_update())).scalar_one()
                    if revision != before.durable_revision:
                        raise PersistenceUnavailable("Durable revision conflict")
                    if before.match_uuid:
                        marker = (await session.execute(select(m.matches.c.ruleset_id).where(
                            m.matches.c.id == before.match_uuid).with_for_update())).scalar_one()
                        if marker != before.ruleset_id:
                            raise PersistenceUnavailable("Durable ruleset conflict")
                    await session.execute(update(m.rooms).where(m.rooms.c.id == candidate.id).values(**values))
                named = [p for p in candidate.players if p.name]
                ids = [p.id for p in named]
                # Clear PID assignments before compacting; retire/remove in this same transaction.
                await session.execute(update(m.room_players).where(m.room_players.c.room_id == candidate.id)
                                      .values(current_pid=None))
                retired = (await session.execute(select(m.room_players.c.id).where(
                    m.room_players.c.room_id == candidate.id, m.room_players.c.id.not_in(ids)))).scalars().all()
                if retired:
                    await session.execute(update(m.room_players).where(m.room_players.c.id.in_(retired))
                                          .values(status="retired", removed_at=now))
                    await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id.in_(retired))
                                          .values(revoked_at=now))
                for p in named:
                    member = dict(id=p.id, room_id=candidate.id, user_id=p.user_id, name=p.name, color=p.color, current_pid=p.pid,
                                  status="active", joined_at=now, last_seen_at=now, removed_at=None)
                    patch = {k: v for k, v in member.items() if k not in ("id", "joined_at", "last_seen_at")}
                    old_member = next((old for old in before.players if old.id == p.id), None) if before else None
                    if old_member is None or old_member.token_expires_at != p.token_expires_at:
                        patch["last_seen_at"] = now
                    await session.execute(pg_insert(m.room_players).values(**member).on_conflict_do_update(
                        index_elements=[m.room_players.c.id], set_=patch))
                    if p.token_hash:
                        token = dict(room_player_id=p.id, token_hash=p.token_hash, created_at=now,
                                     expires_at=p.token_expires_at, revoked_at=p.token_revoked_at)
                        await session.execute(pg_insert(m.seat_tokens).values(**token).on_conflict_do_update(
                            index_elements=[m.seat_tokens.c.room_player_id],
                            set_={"expires_at": p.token_expires_at, "revoked_at": p.token_revoked_at}))
                if before and before.match_uuid and before.match_uuid != candidate.match_uuid:
                    await session.execute(update(m.matches).where(m.matches.c.id == before.match_uuid,
                        m.matches.c.status == "active").values(status="superseded", updated_at=now))
                # Reconnect/claim/chat may update ownership metadata for a restricted
                # match, but must not rewrite its head, scores or historical results.
                if candidate.game and not restricted(before):
                    game = candidate.game
                    winner_id = candidate.players[game.winner_pid].match_player_id if game.game_over and game.winner_pid is not None else None
                    match = dict(id=candidate.match_uuid, room_id=candidate.id, match_no=candidate.match_id,
                                 ruleset_id=candidate.ruleset_id,
                                 status="finished" if game.game_over else "active", tick=candidate.tick,
                                 map_id=game.map_id, map_name=game.map_name, settings=config["settings"],
                                 is_test=candidate.test_mode, started_at=now, updated_at=now,
                                 finished_at=now if game.game_over else None, winner_match_player_id=winner_id)
                    await session.execute(pg_insert(m.matches).values(**match).on_conflict_do_update(
                        index_elements=[m.matches.c.id], set_={"status": match["status"], "tick": candidate.tick,
                        "updated_at": now, "finished_at": m.matches.c.finished_at if game.game_over else None,
                        "winner_match_player_id": winner_id}))
                    if game.game_over:
                        await session.execute(update(m.matches).where(m.matches.c.id == candidate.match_uuid,
                            m.matches.c.finished_at.is_(None)).values(finished_at=now))
                    for p in named:
                        mp = dict(id=p.match_player_id, room_id=candidate.id, match_id=candidate.match_uuid,
                                  room_player_id=p.id, pid=p.pid, name=p.name, color=p.color,
                                  consumed_seq=p.last_seq_applied, final_vp=game.players[p.pid].vp if game.game_over else None)
                        await session.execute(pg_insert(m.match_players).values(**mp).on_conflict_do_update(
                            index_elements=[m.match_players.c.id], set_={"consumed_seq": p.last_seq_applied, "final_vp": mp["final_vp"]}))
                    if head:
                        head_id = uuid.uuid4()
                        await session.execute(insert(m.game_snapshots).values(
                            id=head_id, match_id=candidate.match_uuid, revision=new_revision, tick=candidate.tick,
                            snapshot_version=head["engine"]["snapshot_version"], engine_compatibility=head["engine"]["engine_compatibility"],
                            payload=head, checksum=head_checksum, created_at=now))
                        await session.execute(update(m.matches).where(m.matches.c.id == candidate.match_uuid)
                                              .values(latest_snapshot_id=head_id))
                        old = select(m.game_snapshots.c.id).where(m.game_snapshots.c.match_id == candidate.match_uuid)
                        old = old.order_by(m.game_snapshots.c.revision.desc()).offset(3)
                        await session.execute(delete(m.game_snapshots).where(m.game_snapshots.c.id.in_(old)))
                if receipt:
                    await session.execute(insert(m.command_receipts).values(**receipt, result_tick=candidate.tick,
                                          result_revision=new_revision, created_at=now))
                    old = select(m.command_receipts.c.seq).where(m.command_receipts.c.match_player_id == receipt["match_player_id"])
                    old = old.order_by(m.command_receipts.c.seq.desc()).offset(256)
                    await session.execute(delete(m.command_receipts).where(
                        m.command_receipts.c.match_player_id == receipt["match_player_id"], m.command_receipts.c.seq.in_(old)))
                if operation:
                    await session.execute(insert(m.room_operations).values(**operation, room_id=candidate.id,
                                          result_epoch=candidate.match_id, created_at=now))
                    old = select(m.room_operations.c.request_id).where(m.room_operations.c.room_id == candidate.id)
                    old = old.order_by(m.room_operations.c.created_at.desc()).offset(256)
                    await session.execute(delete(m.room_operations).where(m.room_operations.c.room_id == candidate.id,
                                                                         m.room_operations.c.request_id.in_(old)))
                if candidate.status == "closed":
                    await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id.in_(ids)).values(revoked_at=now))
                    await session.execute(update(m.matches).where(m.matches.c.room_id == candidate.id,
                        m.matches.c.status == "active").values(status="abandoned", updated_at=now))
                self._fault("before_commit")
                committing = True
                await session.commit()
                self._fault("after_commit")
            except asyncio.CancelledError:
                if before:
                    before.persistence_blocked = True
                with suppress(Exception):
                    await session.rollback()
                raise
            except AuthError:
                await session.rollback()
                raise
            except Exception as exc:
                # Cancellation while COMMIT is in flight is also ambiguous. Never retry the write.
                try:
                    await session.rollback()
                except Exception:
                    pass
                error = CommitUncertain if committing else PersistenceUnavailable
                logging.getLogger(__name__).warning("Durable transaction interrupted: stage=%s error_type=%s",
                                                   "commit" if committing else "write", type(exc).__name__)
                raise error("Commit outcome unresolved" if committing else "Durable write failed") from None
        candidate.durable_revision = new_revision
        ended = perf_counter()
        self.last_metrics = {"encode_ms": (encoded-started)*1000, "transaction_ms": (ended-encoded)*1000,
                             "durable_ms": (ended-started)*1000}

    async def codes(self):
        async with self.db.sessions() as session:
            return dict((await session.execute(select(m.rooms.c.room_code, m.rooms.c.status))).all())

    async def recoverable_ids(self):
        async with self.db.sessions() as session:
            return (await session.execute(select(m.rooms.c.id).where(
                m.rooms.c.status.in_(("lobby", "in_match")), m.rooms.c.is_test.is_(False),
                or_(m.rooms.c.expires_at.is_(None), m.rooms.c.expires_at > utcnow())))).scalars().all()

    async def load(self, room_id):
        async with self.db.sessions() as session:
            # Consistent aggregate read: locks the same row as every writer until reads finish.
            async with session.begin():
                row = (await session.execute(select(m.rooms).where(m.rooms.c.id == room_id).with_for_update())).mappings().one_or_none()
                if row is None:
                    return None
                members = (await session.execute(select(m.room_players).where(m.room_players.c.room_id == room_id,
                                                                             m.room_players.c.status == "active"))).mappings().all()
                tokens = (await session.execute(select(m.seat_tokens).where(m.seat_tokens.c.room_player_id.in_([p["id"] for p in members])))).mappings().all()
                match = head = None
                participants, receipts = [], []
                if row["current_match_id"]:
                    match = (await session.execute(select(m.matches).where(m.matches.c.id == row["current_match_id"]))).mappings().one()
                    head = (await session.execute(select(m.game_snapshots).where(m.game_snapshots.c.id == match["latest_snapshot_id"]))).mappings().one_or_none()
                    participants = (await session.execute(select(m.match_players).where(m.match_players.c.match_id == match["id"]))).mappings().all()
                    receipts = (await session.execute(select(m.command_receipts).where(m.command_receipts.c.match_player_id.in_([p["id"] for p in participants])))).mappings().all()
                return dict(room=dict(row), members=[dict(p) for p in members], tokens={t["room_player_id"]: dict(t) for t in tokens},
                            match=dict(match) if match else None, head=dict(head) if head else None,
                            participants=[dict(p) for p in participants], receipts=[dict(r) for r in receipts])

    async def receipt(self, match_player_id, seq, cmd_id):
        async with self.db.sessions() as session:
            return (await session.execute(select(m.command_receipts).where(
                m.command_receipts.c.match_player_id == match_player_id,
                or_(m.command_receipts.c.seq == seq, m.command_receipts.c.cmd_id == cmd_id)))).mappings().first()

    async def operation(self, room_id, request_id):
        async with self.db.sessions() as session:
            return (await session.execute(select(m.room_operations).where(
                m.room_operations.c.room_id == room_id, m.room_operations.c.request_id == request_id))).mappings().one_or_none()

    async def quarantine(self, room_id):
        async with self.db.sessions() as session, session.begin():
            await session.execute(update(m.rooms).where(m.rooms.c.id == room_id).values(status="quarantined", updated_at=utcnow()))
            await session.execute(update(m.matches).where(m.matches.c.room_id == room_id,
                m.matches.c.status.in_(("active", "finished"))).values(status="quarantined", updated_at=utcnow()))
