"""Ownership/publication ordering against an isolated real PostgreSQL database."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import update

from app import server_mp as server
from app.auth.security import AuthError, authorization
from app.auth.service import AuthService
from app.persistence import models as m
from app.persistence.credentials import utcnow, valid_token
from app.persistence.recovery import clone_room, restore_room
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import account, connection, http, auth_config
from tests.test_persistence_postgres import database_url, runtime, pair, command
from tests.test_private_publication import assert_personal


def states(client):
    return [msg for msg in client.ws.messages if msg["type"] == "match_state"]


async def account_game(coord):
    raw, who = await account(coord)
    owner, guest = await connection(who), await connection()
    await server._dispatch(owner, {"type": "create_room", "name": "Account", "max_players": 2})
    room = server.manager.rooms[owner.room_code]
    await server._dispatch(owner, {"type": "set_settings", "settings": {
        "starting_player": "host", "bank_visibility": "hidden"}})
    await server._dispatch(guest, {"type": "join_room", "name": "Guest", "room_code": room.room_code})
    await server._dispatch(owner, {"type": "start_match"})
    candidate = clone_room(room)
    for pid, resource, amount, card in ((0, "wood", 3, "knight"), (1, "ore", 2, "monopoly")):
        candidate.game.bank[resource] -= amount
        candidate.game.players[pid].res[resource] += amount
        candidate.game.dev_deck.remove(card)
        candidate.game.players[pid].dev_cards.append({"type": card, "new": False})
    await server._commit(room, candidate, snapshot=True)
    for client in (owner, guest):
        client.ws.messages.clear()
    return room, (owner, guest), raw, who


@pytest.mark.parametrize("credential", ["expired", "revoked"])
def test_durable_invalid_guest_cannot_receive_or_reconnect(database_url, monkeypatch, credential):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (guest, peer) = await pair()
            proof = room.players[0].reconnect_token
            async with room.lock:
                candidate = clone_room(room)
                if credential == "expired":
                    candidate.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
                else:
                    candidate.players[0].token_revoked_at = utcnow()
                await server._commit(room, candidate)
                bundle = await coord.repository.load(room.id)
                before = encode_snapshot(room.game)
                for client in (guest, peer):
                    client.ws.messages.clear()
                await server._send_match_state(room)
            assert not states(guest) and guest.ws.closed == 4401
            assert_personal(states(peer)[0]["state"], room, 1)
            assert not room.players[0].connected and not server._owns(guest, room)
            assert await coord.repository.load(room.id) == bundle
            assert encode_snapshot(room.game) == before
            restored = restore_room(bundle)
            assert not valid_token(restored.players[0], proof)
            fresh = await connection()
            with pytest.raises(server.RuleError) as exc:
                await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                              "reconnect_token": proof})
            assert exc.value.code == "forbidden" and not states(fresh)
            await server._dispatch(peer, command(room, peer, {"type": "noop"}))
            assert room.players[1].last_seq_applied == 1 and room.players[0].last_seq_applied == 0
            assert not states(guest) and encode_snapshot(room.game) == before

    asyncio.run(run())


def test_account_seat_ignores_guest_expiry_and_preserves_personal_views(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (owner, guest), _, who = await account_game(coord)
            room.players[0].token_expires_at = utcnow() - timedelta(days=1)
            room.players[0].token_revoked_at = utcnow()
            assert room.players[0].user_id == who["user_id"]
            async with room.lock:
                await server._send_match_state(room)
                await server._send_match_state_to(owner.ws, room)
            assert len(states(owner)) == 2 and len(states(guest)) == 1
            for client, pid in ((owner, 0), (guest, 1)):
                assert_personal(states(client)[0]["state"], room, pid)
                assert getattr(client.ws, "closed", None) is None and server._owns(client, room)
            assert authorization.get() is None
            await server._dispatch(owner, command(room, owner, {"type": "noop"}))
            assert room.players[0].last_seq_applied == 1

    asyncio.run(run())


@pytest.mark.parametrize("condition", ["expired", "revoked", "disabled"])
def test_invalid_account_session_receives_no_private_broadcast(database_url, monkeypatch, condition):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (owner, guest), _, who = await account_game(coord)
            before = await coord.repository.load(room.id)
            async with coord.database.sessions() as session, session.begin():
                if condition == "disabled":
                    await session.execute(update(m.users).where(m.users.c.id == who["user_id"])
                                          .values(disabled_at=utcnow()))
                else:
                    patch = {"expires_at": utcnow() - timedelta(seconds=1)} if condition == "expired" else {"revoked_at": utcnow()}
                    await session.execute(update(m.user_sessions).where(m.user_sessions.c.id == who["session_id"])
                                          .values(**patch))
            async with room.lock:
                await server._send_match_state(room)
            assert not states(owner) and owner.ws.closed == 4401 and room.players[0].active_ws is None
            assert_personal(states(guest)[0]["state"], room, 1)
            assert await coord.repository.load(room.id) == before
            with pytest.raises(AuthError):
                await server._dispatch(owner, command(room, owner, {"type": "noop"}))

    asyncio.run(run())


@pytest.mark.parametrize("ownership", ["guest", "account"])
def test_postgres_continue_takeover_fences_old_personal_recipient(database_url, monkeypatch, ownership):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            if ownership == "account":
                room, (old, peer), _, who = await account_game(coord)
                fresh = await connection(who)
                intent = {"type": "account_continue", "room_code": room.room_code}
            else:
                room, (old, peer) = await pair()
                fresh = await connection()
                intent = {"type": "reconnect", "room_code": room.room_code,
                          "reconnect_token": room.players[0].reconnect_token}
                for client in (old, peer):
                    client.ws.messages.clear()
            before = encode_snapshot(room.game)
            await server._dispatch(fresh, intent)
            assert_personal(states(fresh)[0]["state"], room, 0)
            assert old.pid is None and server._owns(fresh, room) and not server._owns(old, room)
            async with room.lock:
                await server._send_match_state(room)
                await server._send_match_state_to(old.ws, room)
            assert not states(old) and len(states(fresh)) == 2
            assert_personal(states(peer)[0]["state"], room, 1)
            assert encode_snapshot(room.game) == before and room.players[0].last_seq_applied == 0

    asyncio.run(run())


@pytest.mark.parametrize("preserve_socket", [False, True])
def test_guest_claim_revocation_keeps_only_the_current_account_controller(database_url, monkeypatch, preserve_socket):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (guest, peer) = await pair()
            raw, who = await account(coord)
            proof = room.players[0].reconnect_token
            request = {"room_code": room.room_code, "reconnect_token": proof}
            if preserve_socket:
                request["connection_nonce"] = guest.connection_nonce
            for client in (guest, peer):
                client.ws.messages.clear()
            assert (await http("/api/games/claim", request, cookie=raw))[0] == 200
            controller = guest if preserve_socket else await connection(who)
            if not preserve_socket:
                await server._dispatch(controller, {"type": "account_continue", "room_code": room.room_code})
            async with room.lock:
                await server._send_match_state(room)
            assert_personal(states(controller)[-1]["state"], room, 0)
            assert server._owns(controller, room) and not valid_token(room.players[0], proof)
            assert_personal(states(peer)[-1]["state"], room, 1)
            if not preserve_socket:
                assert not states(guest) and guest.ws.closed == 4409

    asyncio.run(run())


@pytest.mark.parametrize("ordering", ["revocation_first", "publication_first"])
def test_concurrent_account_revocation_and_publication_have_a_durable_order(database_url, monkeypatch, ordering):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (owner, guest), _, who = await account_game(coord)
            reached, release = asyncio.Event(), asyncio.Event()
            if ordering == "revocation_first":
                resolve = AuthService.resolve_hash

                async def delayed_resolution(service, digest):
                    identity = await resolve(service, digest)
                    reached.set()
                    await release.wait()
                    return identity

                monkeypatch.setattr(AuthService, "resolve_hash", delayed_resolution)
            else:
                send = owner.ws.send_text

                async def delayed_frame(raw):
                    reached.set()
                    await release.wait()
                    await send(raw)

                monkeypatch.setattr(owner.ws, "send_text", delayed_frame)

            async def publication():
                async with room.lock:
                    await server._send_match_state_to(owner.ws, room)

            publishing = asyncio.create_task(publication())
            await asyncio.wait_for(reached.wait(), 1)
            revoking = asyncio.create_task(AuthService(coord.database).revoke(who))
            if ordering == "revocation_first":
                await asyncio.wait_for(revoking, 1)
            else:
                await asyncio.sleep(.05)
                assert not revoking.done(), "PostgreSQL session share lock must order logout after this frame"
            release.set()
            await publishing
            await revoking
            if ordering == "revocation_first":
                assert not states(owner) and owner.ws.closed == 4401
            else:
                assert len(states(owner)) == 1 and getattr(owner.ws, "closed", None) is None
                assert_personal(states(owner)[0]["state"], room, 0)
                owner.ws.messages.clear()
                async with room.lock:
                    await server._send_match_state(room)
                assert not states(owner) and owner.ws.closed == 4401
                assert_personal(states(guest)[0]["state"], room, 1)
            assert authorization.get() is None and not server._owns(owner, room)

    asyncio.run(run())


def test_account_publication_does_not_fall_back_to_cached_session_on_outage(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (owner, _), _, who = await account_game(coord)
            bundle = await coord.repository.load(room.id)
            coord.ready = False
            async with room.lock:
                await server._send_match_state_to(owner.ws, room)
            assert not states(owner) and owner.ws.closed == 1013
            assert room.players[0].active_ws is None
            coord.ready = True
            assert await AuthService(coord.database).resolve_hash(who["session_hash"])
            assert await coord.repository.load(room.id) == bundle

    asyncio.run(run())


@pytest.mark.parametrize("ordering", ["revocation_first", "publication_first"])
def test_durable_guest_revocation_and_publication_share_the_room_lock(database_url, monkeypatch, ordering):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (guest, peer) = await pair()
            for client in (guest, peer):
                client.ws.messages.clear()
            reached, release, contending = asyncio.Event(), asyncio.Event(), asyncio.Event()
            if ordering == "publication_first":
                send = guest.ws.send_text

                async def delayed_frame(raw):
                    reached.set()
                    await release.wait()
                    await send(raw)

                monkeypatch.setattr(guest.ws, "send_text", delayed_frame)

            async def revoke():
                contending.set()
                async with room.lock:
                    candidate = clone_room(room)
                    candidate.players[0].token_revoked_at = utcnow()
                    await server._commit(room, candidate)
                    if ordering == "revocation_first":
                        reached.set()
                        await release.wait()

            async def publish():
                contending.set()
                async with room.lock:
                    await server._send_match_state_to(guest.ws, room)

            first = asyncio.create_task(publish() if ordering == "publication_first" else revoke())
            await asyncio.wait_for(reached.wait(), 1)
            contending.clear()
            second = asyncio.create_task(revoke() if ordering == "publication_first" else publish())
            await asyncio.wait_for(contending.wait(), 1)
            assert not second.done(), "Guest revocation/publication must serialize on Room.lock"
            release.set()
            await first
            await second
            assert len(states(guest)) == (1 if ordering == "publication_first" else 0)
            guest.ws.messages.clear()
            async with room.lock:
                await server._send_match_state(room)
            assert not states(guest) and guest.ws.closed == 4401
            assert_personal(states(peer)[0]["state"], room, 1)
            bundle = await coord.repository.load(room.id)
            assert bundle["tokens"][room.players[0].id]["revoked_at"] is not None

    asyncio.run(run())
