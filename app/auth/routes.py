import json
import logging
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, or_
from app.persistence import models as m
from app.persistence.credentials import utcnow, valid_token, token_hash
from app.persistence.inspection import InspectionLimiter, safe_game
from app.match_rulesets import compatibility
from app.persistence.recovery import clone_room
from .security import (AuthError, COOKIE, authorization, require_origin, set_cookie, clear_cookie)
from .service import AuthService, safe_user

class SafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def guarded(request):
            try:
                return await original(request)
            except AuthError as exc:
                return await auth_error_handler(request, exc)
            except Exception as exc:
                return await safe_failure(request, exc)
        return guarded


router = APIRouter(route_class=SafeRoute)
login_limit = InspectionLimiter(limit=15)
register_limit = InspectionLimiter(limit=5)


def service():
    from app import server_mp as server
    if not server.persistence.ready or not server.persistence.database:
        raise AuthError("persistence_unavailable", 503)
    return AuthService(server.persistence.database)


def reply(body, status=200):
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


async def body(request, keys, optional=()):
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise AuthError("invalid_request", 400)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 4096:
            raise AuthError("invalid_request", 413)
        raw.extend(chunk)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not set(keys) <= set(data) or set(data) - set(keys) - set(optional):
            raise ValueError()
        json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise AuthError("invalid_request", 400) from None
    return data


async def identity(request, required=True):
    who = await service().resolve(request.cookies.get(COOKIE))
    if required and who is None:
        raise AuthError("session_expired" if COOKIE in request.cookies else "unauthenticated")
    return who


async def fence_session(session_id):
    from app import server_mp as server
    for conn in list(server.manager.connections.values()):
        if conn.session_id == session_id:
            room = server.manager.rooms.get(conn.room_code or "")
            if room:
                async with room.lock:
                    server.manager.leave_room(conn)
            conn.user_id = None
            try:
                await server._send(conn.ws, {"type": "error", "code": "session_expired", "message": "Sign in again"})
                await conn.ws.close(code=4401)
            except (RuntimeError, OSError):
                pass  # Logout is already committed; a closed socket must not turn it into HTTP failure.


@router.post("/api/auth/register")
@router.post("/api/auth/login")
async def authenticate(request: Request):
    require_origin(request)
    register = request.url.path.endswith("register")
    if not (register_limit if register else login_limit).allow(request.client.host if request.client else "unknown"):
        raise AuthError("rate_limited", 429)
    data = await body(request, ("username", "display_name", "password") if register else ("username", "password"))
    incoming = await identity(request, required=False)
    raw, user = await service().authenticate(data, register=register, incoming=incoming)
    if incoming:
        await fence_session(incoming["session_id"])
    response = reply({"authenticated": True, "user": user}, 201 if register else 200)
    set_cookie(response, raw)
    return response


@router.get("/api/auth/me")
async def me(request: Request):
    who = await identity(request, required=False)
    response = reply({"authenticated": bool(who), **({"user": safe_user(who)} if who else {})})
    if not who and COOKIE in request.cookies:
        clear_cookie(response)
    return response


@router.post("/api/auth/logout")
async def logout(request: Request):
    require_origin(request)
    await body(request, ())
    who = await identity(request, required=False)
    if who:
        await service().revoke(who)
        await fence_session(who["session_id"])
    response = reply({"authenticated": False})
    clear_cookie(response)
    return response


@router.get("/api/games/active")
async def active_games(request: Request):
    from app import server_mp as server
    who = await identity(request)
    winner = m.match_players.alias("account_winner")
    count = select(func.count()).where(m.room_players.c.room_id == m.rooms.c.id,
                                      m.room_players.c.status == "active").correlate(m.rooms).scalar_subquery()
    query = select(m.rooms.c.room_code, m.rooms.c.updated_at, m.rooms.c.max_players,
                   m.rooms.c.config["map_meta"]["name"].astext.label("map_name"),
                   m.rooms.c.config["rules"]["target_vp"].astext.label("target_vp"),
                   m.room_players.c.name, m.room_players.c.color, count.label("count"),
                   m.matches.c.status, m.matches.c.ruleset_id, winner.c.name.label("winner_name"), winner.c.color.label("winner_color")
                   ).select_from(m.rooms.join(m.room_players, m.room_players.c.room_id == m.rooms.c.id).outerjoin(m.matches, m.rooms.c.current_match_id == m.matches.c.id)
                                 .outerjoin(winner, m.matches.c.winner_match_player_id == winner.c.id)).where(
        m.room_players.c.user_id == who["user_id"], m.room_players.c.status == "active",
        m.room_players.c.current_pid.is_not(None), m.rooms.c.status.in_(("lobby", "in_match")),
        m.rooms.c.closed_at.is_(None), m.rooms.c.is_test.is_(False),
        or_(m.rooms.c.expires_at.is_(None), m.rooms.c.expires_at > utcnow())
    ).order_by(m.rooms.c.updated_at.desc(), m.rooms.c.room_code).limit(50)
    async with service().db.sessions() as session:
        rows = (await session.execute(query)).mappings().all()
    games = []
    for row in rows:
        room = server.manager.rooms.get(row["room_code"])
        if room is None or room.persistence_blocked:
            continue
        async with room.lock:
            if not any(p.name and p.user_id == who["user_id"] for p in room.players):
                continue
            games.append(safe_game(
                room_code=row["room_code"], map_name=row["map_name"], name=row["name"], color=row["color"],
                player_count=row["count"], max_players=row["max_players"],
                connected_count=sum(bool(p.name and p.connected) for p in room.players),
                status="game_over" if row["status"] == "finished" else "active" if row["status"] == "active" else "lobby",
                target_vp=int(row["target_vp"]), updated_at=row["updated_at"],
                ruleset=compatibility(row["ruleset_id"]) if row["status"] else None,
                winner={"name": row["winner_name"], "color": row["winner_color"]} if row["winner_name"] else None)["game"])
    return reply({"games": games})


@router.post("/api/games/claim")
async def claim(request: Request):
    from app import server_mp as server
    require_origin(request)
    who = await identity(request)
    data = await body(request, ("room_code", "reconnect_token"), ("connection_nonce",))
    code, raw = data["room_code"], data["reconnect_token"]
    nonce = data.get("connection_nonce")
    if (not isinstance(code, str) or not 1 <= len(code) <= 32 or not isinstance(raw, str) or not 1 <= len(raw) <= 512
            or nonce is not None and (not isinstance(nonce, str) or len(nonce) > 128)):
        raise AuthError("invalid_request", 400)
    room = server.manager.rooms.get(code.strip().upper())
    if room is None:
        raise AuthError("guest_credential_invalid", 403)
    async with room.lock:
        if room.persistence_blocked:
            raise AuthError("persistence_unavailable", 503)
        if room.closed_at or room.status not in ("lobby", "in_match") or room.expires_at and room.expires_at <= utcnow():
            raise AuthError("guest_credential_invalid", 403)
        prior = next((p for p in room.players if p.name and p.token_hash and secrets.compare_digest(p.token_hash, token_hash(raw))), None)
        if prior and prior.user_id is not None:
            if prior.user_id == who["user_id"]:
                return reply({"claimed": True, "room_code": room.room_code})
            raise AuthError("already_claimed", 409)
        slot = next((p for p in room.players if p.name and valid_token(p, raw)), None)
        if slot is None or room.closed_at or room.status not in ("lobby", "in_match"):
            raise AuthError("guest_credential_invalid", 403)
        if any(p.name and p.user_id == who["user_id"] for p in room.players):
            raise AuthError("duplicate_room_membership", 409)
        candidate = clone_room(room)
        target = candidate.players[slot.pid]
        target.user_id, target.token_revoked_at, target.reconnect_token = who["user_id"], utcnow(), None
        active = server.manager.connections.get(slot.active_ws)
        preserve = active and nonce and secrets.compare_digest(active.connection_nonce, nonce)
        context = authorization.set(who)
        try:
            await server._commit(room, candidate)
        finally:
            authorization.reset(context)
        slot.reconnect_token = None
        if active:
            if preserve:
                server.set_account_context(active, who)
                await server._send_reconnect_token(active.ws, room, slot.pid)
            else:
                server.manager.leave_room(active)
                await active.ws.close(code=4409)
    return reply({"claimed": True, "room_code": room.room_code})


async def auth_error_handler(request, exc):
    return reply({"error": exc.code}, exc.status)


async def safe_failure(request, exc):
    # Never emit driver errors, request values, cookies or password/session material.
    logging.getLogger(__name__).warning("Account API temporarily unavailable (details omitted)")
    return reply({"error": "persistence_unavailable"}, 503)
