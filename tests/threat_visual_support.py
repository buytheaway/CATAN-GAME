"""Guarded three-seat visual fixtures; never imported by production startup.

The private manifest contains synthetic seat proofs and public command targets.
No endpoint creates fixtures, grants capability, controls RNG or reads this file.
"""
import argparse
from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import random
from unittest.mock import patch
from uuid import UUID, uuid4

import uvicorn

from tests.full_match_support import validate_database_url

CASES = [(figure, trigger, "multiple") for figure in ("robber", "pirate")
    for trigger in ("seven", "knight")] + [("robber", "seven", "none"), ("robber", "knight", "fog"),
    ("robber", "knight", "offboard")]


def threat_game(figure, trigger, mode="multiple"):
    from app.engine import rules
    from tests.test_resource_allocation import empty_hands, theft_game
    from tests.test_persistence_snapshots import give_card

    if mode == "fog":
        from tests.test_fog_foundation import fog_recipe
        game = rules.build_game(91, 3, map_data=fog_recipe(), fog_rng=random.Random(7))
        game.phase, game.setup_idx, game.turn, game.rolled = "main", len(game.setup_order), 0, False
        hidden = game.scenario.rules.fog.initially_hidden
        tiles = sorted((i for i, t in enumerate(game.tiles) if i not in hidden
            and t.terrain != "sea" and i != game.robber_tile), key=lambda i: -sum(
                bool(set(game.vertex_adj_hexes[v]) & set(hidden)) for v in game.vertices if i in game.vertex_adj_hexes[v]))
        tile = tiles[0]
        for pid in (1, 2, 0):
            vertex = next(v for v in game.vertices if (pid == 0 or tile in game.vertex_adj_hexes[v])
                and rules.can_place_settlement(game, pid, v, require_road=False))
            game.occupied_v[vertex] = (pid, 1)
            game.players[pid].vp = 1
        empty_hands(game)
        rules.apply_cmd(game, 1, {"type": "grant_resources", "res": {"wood": 3, "ore": 1}}, trusted_fog=True)
        command = {"type": "move_robber", "tile": tile, "victim": 1}
    elif mode == "offboard":
        # Gold Haven natively has no starting robber; never fabricate this in Base.
        game, _ = theft_game("pirate", "ready")
        assert game.map_id == "seafarers_gold_haven" and game.robber_tile == -1
    else:
        game, command = theft_game(figure, "ready")
    rules.apply_cmd(game, 2, {"type": "grant_resources", "res": {"brick": 2}}, trusted_fog=True)
    if mode == "offboard":
        prepared = None
        for tile, terrain in enumerate(game.tiles):
            if terrain.terrain == "sea" or 1 not in rules._victims_for_tile(game, tile, 0):
                continue
            for source, owner in game.occupied_v.items():
                if owner != (2, 1):
                    continue
                probe = deepcopy(game)
                del probe.occupied_v[source]
                vertex = next((v for v in probe.vertices if tile in probe.vertex_adj_hexes[v]
                    and rules.can_place_settlement(probe, 2, v, require_road=False)), None)
                if vertex is not None:
                    probe.occupied_v[vertex] = (2, 1)
                    prepared = probe, {"type": "move_robber", "tile": tile, "victim": 1}
                    break
            if prepared:
                break
        assert prepared, "A prepared legal known-land settlement must give a second actual victim"
        game, command = prepared
    if figure == "pirate":
        tile = command["tile"]
        edge = next(e for e in sorted(game.edges) if tile in game.edge_adj_hexes[e]
            and e not in game.occupied_e and e not in game.occupied_ships)
        # Explicit prepared shipping, matching the existing theft_game fixture.
        game.occupied_ships[edge] = 2
    for pid in range(3):
        give_card(game, "victory_point", pid=pid)
        give_card(game, "knight", pid=pid)
    victims = rules._victims_for_tile if figure == "robber" else rules._victims_for_pirate_tile
    if mode == "none":
        tile = next(i for i, t in enumerate(game.tiles) if (t.terrain == "sea") == (figure == "pirate")
            and i != getattr(game, figure + "_tile") and not victims(game, i, 0))
        command = {"type": "move_" + figure, "tile": tile}
    assert game.pending_action is None and not game.rolled and not game.game_over
    return game, {"figure": figure, "trigger": trigger, "mode": mode, "route": command,
        "start": {"type": "roll"} if trigger == "seven" else {"type": "play_dev", "card": "knight"},
        "fog": mode == "fog"}


def validate_prepared(game, spec):
    from app.engine import rules
    from app.engine.legal import board_legal_moves
    from tests.test_resource_allocation import FixedDraw
    candidate = deepcopy(game)
    start = {**spec["start"], **({"roll": 7} if spec["trigger"] == "seven" else {})}
    rules.apply_cmd(candidate, 0, start, trusted_fog=spec["fog"])
    assert candidate.pending_action == "robber_move"
    legal = board_legal_moves(candidate, 0, trusted_fog=spec["fog"])
    command, figure = spec["route"], spec["figure"]
    assert command["tile"] in legal[figure + "_tiles"]
    expected = [] if spec["mode"] == "none" else [1, 2]
    assert legal[figure + "_victims"][str(command["tile"])] == expected
    draw = FixedDraw(3)
    rules.apply_cmd(candidate, 0, command, trusted_fog=spec["fog"], theft_rng=draw)
    assert draw.stops == ([] if spec["mode"] == "none" else [4])
    return candidate


async def threat_room(coord, figure, trigger, mode="multiple"):
    from app import server_mp as server
    from tests.test_persistence_postgres import pair, prepare
    game, spec = threat_game(figure, trigger, mode)
    validate_prepared(game, spec)
    if spec["fog"]:
        from app.match_rulesets import CURRENT_RULESET
        from app.persistence.recovery import clone_room
        from tests.test_auth import connection
        from tests.test_fog_foundation import fog_recipe
        clients = [await connection() for _ in range(3)]
        await server._dispatch(clients[0], {"type": "create_room", "name": "Alice", "max_players": 3})
        for client, name in zip(clients[1:], ("Bob", "Carol")):
            await server._dispatch(client, {"type": "join_room", "name": name, "room_code": clients[0].room_code})
        room = server.manager.rooms[clients[0].room_code]
        await server._dispatch(clients[0], {"type": "set_settings", "settings": {"bank_visibility": "hidden"}})
        candidate = clone_room(room)
        candidate.game = game
        game.map_id = "internal-threat-visual"
        for player, slot in zip(game.players, candidate.players):
            player.name = slot.name
            slot.match_player_id = uuid4()
        candidate.selected_map_id, candidate.selected_map_data = game.map_id, fog_recipe()
        candidate.selected_map_meta = {"id": game.map_id, "name": game.map_name, "description": ""}
        candidate.selected_rules_config = vars(game.rules_config).copy()
        candidate.seed, candidate.match_id, candidate.match_uuid = game.seed, 1, uuid4()
        candidate.ruleset_id, candidate.status = CURRENT_RULESET, "in_match"
        await server._commit(room, candidate, snapshot=True)
    else:
        room, clients = await pair(names=("Alice", "Bob", "Carol"), map_id=game.map_id)
        await prepare(room, game)
    proofs = [c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]
    for client in clients:
        server.manager.leave_room(client)
        server.manager.connections.pop(client.ws)
    return room, proofs, spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18778)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    validate_database_url(os.environ.get("DATABASE_URL", ""))
    if not 1024 <= args.port <= 65535 or os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0":
        raise SystemExit("Unprivileged loopback port and disabled Test Tools required")
    origin = f"http://127.0.0.1:{args.port}"
    os.environ.update(CATAN_AUTH_MODE="development", CATAN_AUTH_ORIGINS=origin,
        CATAN_PERSISTENCE_MODE="durable", CATAN_ENABLE_TEST_TOOLS="0",
        CATAN_FOG_BETA_ADMISSION="0", CATAN_FOG_BETA_EMERGENCY_STOP="0")
    from app import server_mp as server
    from app.engine import rules
    from app.fog_transport import FogMatchAccess
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException

    def audit(kind):
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        with args.audit.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind}) + "\n")

    class ControlledTheft:
        def randrange(self, stop):
            audit("theft_draw")
            assert stop == 4, "Prepared theft must retain its exact weighted hand"
            return 3

    def seven():
        audit("roll_draw")
        return 3, 4

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery cannot execute game rules or draw theft again")

    original = server.app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        recovering = args.manifest.is_file()
        with ExitStack() as guard:
            if recovering:
                for name in ("apply_cmd", "build_game", "check_win", "distribute_for_roll", "_steal_one"):
                    guard.enter_context(patch.object(rules, name, forbidden))
            async with original(app):
                guard.close()
                server._roll_dice, rules._THEFT_RNG = seven, ControlledTheft()
                if recovering:
                    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
                    audit("recovery_without_gameplay")
                else:
                    manifest = []
                    for figure, trigger, mode in CASES:
                        room, proofs, spec = await threat_room(server.persistence, figure, trigger, mode)
                        manifest.append({"room_code": room.room_code, "room_id": str(room.id),
                            "match_uuid": str(room.match_uuid), "proofs": proofs, **spec})
                    args.manifest.parent.mkdir(parents=True, exist_ok=True)
                    args.manifest.write_text(json.dumps(manifest), encoding="utf-8")
                access = []
                for entry in manifest:
                    room = server.manager.rooms.get(entry["room_code"])
                    if not room or str(room.id) != entry["room_id"] or str(room.match_uuid) != entry["match_uuid"]:
                        raise RuntimeError("Threat manifest does not match recovered native state")
                    if entry["fog"]:
                        scope = FogMatchAccess(UUID(entry["room_id"]), UUID(entry["match_uuid"]))
                        if not scope.permits(room):
                            raise RuntimeError("Threat Fog capability does not match its native state")
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
        loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto", log_level="error", access_log=False)


if __name__ == "__main__":
    main()
