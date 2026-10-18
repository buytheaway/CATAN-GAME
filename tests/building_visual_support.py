"""Prepared building visual acceptance; no production import or fixture endpoint.

Only synthetic seat proofs and command targets enter the private local manifest.
Normal recovery/executor/receipts/publication remain authoritative.
"""
import argparse
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import UUID

import uvicorn

from tests.fog_live_support import fixture_room
from tests.full_match_support import validate_database_url


def resolve_prepared_gold(game):
    from app.engine import rules
    while game.pending_action == "choose_gold":
        rules.apply_cmd(game, 0, {"type": "choose_gold", "res": "ore",
            "qty": game.pending_gold[0]}, trusted_fog=True)


def add_prepared_ship(game, anchor):
    """A real engine-built baseline ship; its synthetic coastal anchor is explicit."""
    from app.engine import rules
    from tests.test_fog_exploration import adjacent_hidden
    origin = game.vertices[anchor]
    edges = sorted(game.edges, key=lambda e: min(
        (game.vertices[v][0] - origin[0]) ** 2 + (game.vertices[v][1] - origin[1]) ** 2 for v in e))
    for edge in edges:
        if adjacent_hidden(game, edge):
            continue
        for vertex in edge:
            if not rules.can_place_settlement(game, 0, vertex, require_road=False):
                continue
            probe = deepcopy(game)
            probe.occupied_v[vertex] = (0, 1)
            probe.players[0].vp += 1
            try:
                rules.apply_cmd(probe, 0, {"type": "build_ship", "eid": edge}, trusted_fog=True)
            except rules.RuleError:
                continue
            assert probe.pending_action is None
            return probe
    raise AssertionError("No legal known-coast baseline ship in building fixture")


async def building_room(coord, kind):
    """Funded prepared scene; final construction is validated but never pre-executed."""
    from app import server_mp as server
    from app.engine import rules
    from app.engine.legal import board_legal_moves
    from app.persistence.recovery import clone_room

    assert kind in ("place_road", "place_settlement", "upgrade_city")
    room, proofs, road = await fixture_room(coord, kind="place_road")
    candidate = clone_room(room)
    game = candidate.game
    for resource in game.players[0].res:
        quantity = 8 - game.players[0].res[resource]
        game.players[0].res[resource] += quantity
        game.bank[resource] -= quantity
    candidate.game = game = add_prepared_ship(game, road["eid"][0])
    if kind == "place_road":
        command = {"type": kind, "eid": list(road["eid"])}
    elif kind == "upgrade_city":
        command = {"type": kind, "vid": road["eid"][0]}
    else:
        for _ in range(4):
            legal = board_legal_moves(game, 0, trusted_fog=True)
            if legal["settlements"]:
                command = {"type": kind, "vid": legal["settlements"][0]}
                break
            extension = next((edge for edge in legal["roads"] if any(
                rules.can_place_settlement(game, 0, vertex, require_road=False) for vertex in edge)),
                legal["roads"][0])
            rules.apply_cmd(game, 0, {"type": "place_road", "eid": extension}, trusted_fog=True)
            resolve_prepared_gold(game)
        else:
            raise AssertionError("Prepared roads did not reach a legal settlement")
    before = deepcopy(game)
    accepted = deepcopy(game)
    rules.apply_cmd(accepted, 0, command, trusted_fog=True)
    assert game == before and accepted != game and not game.game_over
    assert game.occupied_ships and game.pending_action is None
    await server._commit(room, candidate, snapshot=True, trusted_fog=True)
    return room, proofs, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18775)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    validate_database_url(os.environ.get("DATABASE_URL", ""))
    if not 1024 <= args.port <= 65535 or os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0":
        raise SystemExit("Unprivileged loopback port and disabled Test Tools required")
    origin = f"http://127.0.0.1:{args.port}"
    os.environ.update(CATAN_AUTH_MODE="development", CATAN_AUTH_ORIGINS=origin,
        CATAN_PERSISTENCE_MODE="durable", CATAN_ENABLE_TEST_TOOLS="0",
        CATAN_FOG_BETA_ADMISSION="0", CATAN_FOG_BETA_EMERGENCY_STOP="0")
    from app import server_mp as server
    from app.fog_transport import FogMatchAccess
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException
    original = server.app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            if args.manifest.is_file():
                manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            else:
                manifest = []
                for kind in ("place_road", "place_settlement", "upgrade_city"):
                    room, proofs, command = await building_room(server.persistence, kind)
                    manifest.append({"room_code": room.room_code, "room_id": str(room.id),
                        "match_uuid": str(room.match_uuid), "proofs": proofs, "route": command})
                args.manifest.parent.mkdir(parents=True, exist_ok=True)
                args.manifest.write_text(json.dumps(manifest), encoding="utf-8")
            access = []
            for entry in manifest:
                scope = FogMatchAccess(UUID(entry["room_id"]), UUID(entry["match_uuid"]))
                if not scope.permits(server.manager.rooms.get(entry["room_code"])):
                    raise RuntimeError("Building manifest does not match recovered native state")
                access.append(scope)
            app.state._fog_fixture_access = tuple(access)
            try:
                yield
            finally:
                del app.state._fog_fixture_access

    server.app.router.lifespan_context = lifespan
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Build production web/dist first")

    class ProductionFiles(StaticFiles):
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as error:
                if error.status_code != 404 or path.startswith(("assets/", "api/")):
                    raise
                return await super().get_response("index.html", scope)

    server.app.mount("/", ProductionFiles(directory=dist, html=True))
    uvicorn.run(server.app, host="127.0.0.1", port=args.port, proxy_headers=False,
        loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto",
        log_level="error", access_log=False)


if __name__ == "__main__":
    main()
