"""Grant-free Fog matches; guarded test process, never a production import.

The ONLY admission exception is a privately bound test room's start/rematch.
Original dispatcher/host/ownership/start/transition/transaction/receipt/publisher
still execute. No engine state is edited after construction. Agents see wire
snapshots only; trusted SQL observations are assertions, never policy inputs.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
import heapq
import os
from pathlib import Path
import random
import uuid

from tests.full_match_support import (
    Backend, Match, NaturalAgent, SETTINGS, COST, RESOURCES, TERRAIN,
    install_test_rng, validate_database_url, public_checksum, edge_key,
)
from tests.fog_live_support import connect

MAP_ID = "seafarers_fog_natural"


def recipe():
    from tests.test_fog_foundation import fog_recipe
    data = fog_recipe()
    data.update(name="Natural shared-preassigned Fog", description="Internal test profile; not official Fog Islands")
    return data


class FogBackend(Backend):
    def __init__(self, database_url, manifest, port=None):
        self.manifest = Path(manifest)
        super().__init__(database_url, port, module="tests.fog_natural_support",
                         serve_args=("--manifest", str(self.manifest)))

    def close(self):
        self.stop()
        self.log.seek(0)
        self.manifest.with_name("private-server.log").write_bytes(self.log.read())
        super().close()


class FixtureAdmission:
    """Test-only lifecycle admission; no public input can register a room.

    A ContextVar confines feature-gate exceptions to the ORIGINAL lifecycle
    invocation, including the two existing transition validations. Other rooms,
    commands, historical markers, timers and Test Tools keep their normal gates.
    """
    def __init__(self, server, manifest):
        self.server, self.path = server, Path(manifest)
        self.source = recipe()
        self.binding = None
        self.intent = ContextVar("fog_natural_lifecycle", default=None)
        self.transition = ContextVar("fog_natural_transition", default=None)

    def owns_room(self, room):
        from app.match_rulesets import CURRENT_RULESET
        return bool(self.binding and room and str(room.id) == self.binding["room_id"]
                    and not room.test_mode and room.selected_map_id == MAP_ID
                    and room.selected_map_data == self.source
                    and (room.game is None and room.status == "lobby" and room.match_id == 0
                         or room.ruleset_id == CURRENT_RULESET
                         and str(room.match_uuid) == self.binding.get("match_uuid")))

    def allowed(self, room):
        return self.intent.get() in ("start_match", "rematch") and self.owns_room(room)

    def save_binding(self, room):
        from app.fog_transport import FogMatchAccess
        if room.game is not None:
            self.binding["match_uuid"] = str(room.match_uuid)
            self.server.app.state._fog_fixture_access = (FogMatchAccess(room.id, room.match_uuid),)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.binding), encoding="utf-8")

    async def initialize(self):
        from app.persistence.recovery import clone_room
        from tests.test_auth import connection
        if self.path.is_file():
            self.binding = json.loads(self.path.read_text(encoding="utf-8"))
            room = self.server.manager.rooms.get(self.binding["room_code"])
            if not self.owns_room(room):
                raise RuntimeError("Natural Fog binding does not match recovered state")
            self.save_binding(room)  # Explicit test rebind, never recovery activation.
            return
        clients = [await connection(), await connection()]
        await self.server._dispatch(clients[0], {"type": "create_room", "name": "Fog Natural 1", "max_players": 2})
        room = self.server.manager.rooms[clients[0].room_code]
        await self.server._dispatch(clients[1], {"type": "join_room", "name": "Fog Natural 2", "room_code": room.room_code})
        candidate = clone_room(room)
        # Trusted INITIAL CONFIGURATION ONLY. No GameState, grants or VP edits.
        candidate.selected_map_id, candidate.selected_map_data = MAP_ID, recipe()
        candidate.selected_map_meta = {"id": MAP_ID, "name": recipe()["name"], "description": recipe()["description"]}
        from app.engine.rules import parse_rules_config
        candidate.selected_rules_config = vars(parse_rules_config(recipe()["rules"]))
        self.server._set_room_settings(candidate, 0, SETTINGS)
        candidate.map_revision += 1
        await self.server._commit(room, candidate)
        self.binding = {"room_code": room.room_code, "room_id": str(room.id),
                        "proofs": [c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]}
        for c in clients:
            self.server.manager.leave_room(c)
            self.server.manager.connections.pop(c.ws)
        self.save_binding(room)

    def install(self):
        from app import match_rulesets
        from app.persistence import repositories
        from app.engine.exploration import has_fog, validate_fog_state
        server = self.server
        dispatch, compatible, start, commit = server._dispatch_impl, server._require_compatible, server._start_match, server._commit
        data_gate, game_gate = server.require_non_fog_data, server.require_no_fog
        restricted = match_rulesets.restricted

        async def dispatch_scoped(conn, data):
            room = server.manager.rooms.get(conn.room_code or "")
            kind = data.get("type") if self.owns_room(room) else None
            token = self.intent.set(kind if kind in ("start_match", "rematch") else None)
            try: return await dispatch(conn, data)
            finally: self.intent.reset(token)

        def compatible_scoped(room, **kwargs):
            if not self.allowed(room): return compatible(room, **kwargs)

        def data_scoped(data):
            if self.intent.get() not in ("start_match", "rematch") or data != self.source:
                return data_gate(data)

        def game_scoped(game):
            if self.intent.get() not in ("start_match", "rematch") or game.map_id != MAP_ID:
                return game_gate(game)
            validate_fog_state(game)

        def start_scoped(room, **kwargs):
            if not self.allowed(room): return start(room, **kwargs)
            if room.game is not None and not room.game.game_over:
                raise server.RuleError("invalid", "Internal Fog rematch requires a finished match")
            # The real builder assigns once, then performs all ordinary opening
            # initialization. The private draw is test-only and differs by epoch.
            build = server.build_game
            def seeded(*args, **options):
                return build(*args, **options, fog_rng=random.Random(501 + room.match_id))
            server.build_game = seeded
            try: return start(room, **kwargs)
            finally: server.build_game = build

        async def commit_scoped(before, candidate, **kwargs):
            operation = kwargs.get("operation") or {}
            lifecycle = self.allowed(before) and operation.get("kind") == self.intent.get()
            if not lifecycle: return await commit(before, candidate, **kwargs)
            game = candidate.game
            assert candidate.id == before.id and candidate.match_id == before.match_id + 1
            assert candidate.match_uuid != before.match_uuid and candidate.ruleset_id == match_rulesets.CURRENT_RULESET
            assert has_fog(game) and game.phase == "setup" and not game.game_over
            assert not game.occupied_v and not game.occupied_e and not game.occupied_ships
            assert not game.scenario.fog.revealed and not game.scenario.fog.discoveries and game.scenario.fog.continuation is None
            assert all(p.vp == 0 and not any(p.res.values()) and not p.dev_cards for p in game.players)
            validate_fog_state(game)
            token = self.transition.set(before)
            try: await commit(before, candidate, **kwargs)
            finally: self.transition.reset(token)
            self.save_binding(before)

        # The original validators still check marker/assignment/epoch invariants.
        # Only their legacy-Fog restriction is admitted for this verified new
        # lifecycle transaction; no imported runtime gate is globally disabled.
        def restricted_scoped(room):
            return False if room is self.transition.get() and room is not None else restricted(room)
        match_rulesets.restricted = repositories.restricted = restricted_scoped
        server._dispatch_impl, server._require_compatible = dispatch_scoped, compatible_scoped
        server.require_non_fog_data, server.require_no_fog = data_scoped, game_scoped
        server._start_match, server._commit = start_scoped, commit_scoped


class FogAgent(NaturalAgent):
    """Cooperative player; plans using known wire terrain and authoritative legal lists."""
    def __init__(self, pid):
        super().__init__(pid, True)
        self.land_policy = NaturalAgent(pid, False)
        self.paid = Counter()

    @staticmethod
    def frontier(s, edge):
        adjacent = set(s["edge_adj_hexes"][edge_key(edge)])
        for vertex in edge: adjacent.update(s["vertex_adj_hexes"][str(vertex)])
        return sum(s["tiles"][i].get("visibility") == "hidden" for i in adjacent)

    def setup(self, s):
        if s["setup_need"] == "settlement":
            owned = [v for v, (p, _) in s["occupied_v"].items() if p == self.pid]
            existing = {TERRAIN.get(s["tiles"][i]["terrain"]) for v in owned for i in s["vertex_adj_hexes"][v]}
            def score(vid):
                resources = {TERRAIN.get(s["tiles"][i]["terrain"]) for i in s["vertex_adj_hexes"][str(vid)]} - {None}
                coast = any(self.has_sea(s, e) for e in s["edges"] if vid in e)
                frontier = sum(s["tiles"][i].get("visibility") == "hidden" for i in s["vertex_adj_hexes"][str(vid)])
                # Open at one frontier; keep the other openings productive and
                # leave a genuine main-phase voyage rather than reveal all Fog
                # during the snake setup. Only public visibility is consulted.
                weight = 60 if self.pid == 0 else -60
                economy = 14 * ("ore" in resources - existing) + 10 * ("wheat" in resources - existing)
                return weight * frontier + 20 * coast + self.productivity(s, vid) + 8 * len(resources - existing) + economy
            options = s["legal"]["settlements"]
            if owned:
                # Reserve an actual shipping opening on KNOWN unblocked water.
                # Unknown adjacency alone is not sea access under Fog rules.
                coast = [v for v in options if any(v in e and self.has_sea(s, e)
                    and s["pirate_tile"] not in s["edge_adj_hexes"][edge_key(e)] for e in s["edges"])]
                if coast: options = coast
            return {"type": "place_settlement", "vid": max(options, key=lambda v: (score(v), -v))}
        own_buildings = sum(p == self.pid for p, _ in s["occupied_v"].values())
        ships = s["legal"]["ships"]
        kind = "build_ship" if own_buildings == 2 and ships else "place_road"
        options = ships if kind == "build_ship" else s["legal"]["roads"]
        if not options:
            kind, options = "build_ship", ships
        return {"type": kind, "eid": max(options, key=lambda e: (self.frontier(s, e), [-v for v in e]))}

    def exploration_goal(self, s, *, ship=True):
        owned = {int(v) for v, (pid, _) in s["occupied_v"].items() if pid == self.pid}
        occupancy = "occupied_ships" if ship else "occupied_e"
        other_occupancy = "occupied_e" if ship else "occupied_ships"
        own_routes = {tuple(map(int, e.split(","))) for e, pid in s[occupancy].items() if pid == self.pid}
        roots = owned | {v for e in own_routes for v in e}
        occupied = {int(v): pid for v, (pid, _) in s["occupied_v"].items()}
        graph = {int(v): [] for v in s["vertices"]}
        for edge in s["edges"]:
            key = edge_key(edge)
            known = self.has_sea(s, edge) if ship else any(s["tiles"][i].get("visibility") != "hidden"
                    and s["tiles"][i]["terrain"] != "sea" for i in s["edge_adj_hexes"][key])
            if not known or key in s[other_occupancy]: continue
            if key in s[occupancy] and s[occupancy][key] != self.pid: continue
            if ship and s["pirate_tile"] in s["edge_adj_hexes"][key]: continue
            a, b = edge
            graph[a].append((b, tuple(edge)))
            graph[b].append((a, tuple(edge)))
        queue = [(0, v, []) for v in sorted(roots)]
        heapq.heapify(queue)
        seen = set()
        while queue:
            cost, vertex, path = heapq.heappop(queue)
            if vertex in seen: continue
            seen.add(vertex)
            if path and any(s["tiles"][i].get("visibility") == "hidden" for i in s["vertex_adj_hexes"][str(vertex)]):
                missing = next((edge for edge in path if edge not in own_routes), None)
                if missing:
                    cmd = {"type": "build_ship" if ship else "place_road", "eid": list(missing)}
                    return "ship" if ship else "road", cmd, list(missing) in s["legal"]["ships" if ship else "roads"]
            for other, edge in sorted(graph[vertex]):
                if occupied.get(other, self.pid) == self.pid:
                    heapq.heappush(queue, (cost + (edge not in own_routes), other, path + [edge]))
        return None

    def goal(self, s):
        for kind, command, key in (("road", "place_road", "roads"), ("ship", "build_ship", "ships")):
            if not self.paid[command]:
                options = s["legal"][key]
                if not options and all(self.hand(s)[r] >= n for r, n in COST[kind].items()):
                    continue  # Develop economy/cards rather than wait on a blocked route.
                edge = max(options, key=lambda e: (self.frontier(s, e), [-v for v in e])) if options else None
                return kind, None if edge is None else {"type": command, "eid": edge}, bool(edge)
        # Explore an available visible frontier, never classify an unknown tile.
        for kind, command, key in (("ship", "build_ship", "ships"), ("road", "place_road", "roads")):
            options = [e for e in s["legal"][key] if self.frontier(s, e)]
            if options:
                return kind, {"type": command, "eid": max(options, key=lambda e: (self.frontier(s, e), [-v for v in e]))}, True
        exploration = self.exploration_goal(s)
        if exploration is None: exploration = self.exploration_goal(s, ship=False)
        if exploration: return exploration
        # The existing land policy must treat unknowns as unavailable, rather
        # than its historical non-Sea == land assumption. This local copy is a
        # planning view, never a mutation of engine state or the received frame.
        planning = deepcopy(s)
        for tile in planning["tiles"]:
            if tile.get("visibility") == "hidden": tile["terrain"] = "sea"
        return self.land_policy.goal(planning)


class FogMatch(Match):
    def __init__(self, backend):
        super().__init__(backend, 2, MAP_ID)
        self.names = ["Fog Natural 1", "Fog Natural 2"]
        self.previous_entries = ()
        self.discovery_triggers = Counter()
        self.observation = None
        self.reward_summary = {}

    async def connect(self):
        return await connect(f"ws://127.0.0.1:{self.backend.port}/ws", origin=f"http://127.0.0.1:{self.backend.port}")

    async def create(self):
        binding = json.loads(self.backend.manifest.read_text(encoding="utf-8"))
        self.room_code = binding["room_code"]
        for proof in binding["proofs"]:
            peer = await self.connect()
            self.peers.append(peer)
            await peer.send({"type": "reconnect", "room_code": self.room_code, "reconnect_token": proof})
            await peer.wait(lambda: peer.room is not None and peer.token is not None)
            assert peer.state is None  # No prepared midgame snapshot exists.
        await self.peers[0].send({"type": "start_match", "request_id": uuid.uuid4().hex, "expected_match_id": 0})
        await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in self.peers))
        assert self.state["phase"] == "setup" and not self.state["occupied_v"]
        self.assert_views()
        await self.assert_conservation()

    def assert_views(self):
        super().assert_views()
        for pid, peer in enumerate(self.peers):
            s = peer.state["state"]
            assert not s["scenario"]["rules"]["new_island_vp"]
            assert not s["scenario"]["home_islands"] and not s["scenario"]["awarded_islands"]
            assert set(s.get("pending_gold_queue", [])) <= {pid}
            assert not ({"assignment_digest", "discoveries", "continuation", "initially_hidden", "fog_pool"} & s["scenario"]["fog"].keys())
            for tile in s["tiles"]:
                if tile["visibility"] == "hidden":
                    assert tile["terrain"] == "fog" and tile["number"] is None

    async def committed_game(self):
        from sqlalchemy import select
        from app.persistence import models as m
        from app.persistence.snapshots import decode_snapshot
        async with self.database.sessions() as session:
            payload = (await session.execute(select(m.game_snapshots.c.payload)
                .join(m.matches, m.matches.c.latest_snapshot_id == m.game_snapshots.c.id)
                .join(m.rooms, m.rooms.c.current_match_id == m.matches.c.id)
                .where(m.rooms.c.room_code == self.room_code))).scalar_one()
        return payload, decode_snapshot(payload["engine"])

    async def assert_conservation(self):
        await super().assert_conservation()
        payload, game = await self.committed_game()
        from app.engine.exploration import validate_fog_state
        validate_fog_state(game)
        for player in game.players:
            buildings = sum(level for owner, level in game.occupied_v.values() if owner == player.pid)
            hidden_vp = sum(c["type"] == "victory_point" for c in player.dev_cards)
            achievements = 2 * (game.longest_road_owner == player.pid) + 2 * (game.largest_army_owner == player.pid)
            assert player.vp == buildings + hidden_vp + achievements
            assert not game.scenario.awarded_islands.get(player.pid)
        if game.game_over: assert game.winner_pid == game.turn
        for peer in self.peers:
            tiles = peer.state["state"]["tiles"]
            for i in game.scenario.rules.fog.initially_hidden:
                if i in game.scenario.fog.revealed:
                    assert (tiles[i]["terrain"], tiles[i]["number"]) == (game.tiles[i].terrain, game.tiles[i].number)
                else: assert tiles[i]["visibility"] == "hidden"
        if self.peers[0].state["match_id"] != 1: return
        entries = game.scenario.fog.discoveries
        if len(entries) > len(self.previous_entries):
            assert self.observation and self.observation[1] in ("place_road", "build_ship", "move_ship")
            self.discovery_triggers["/".join(self.observation[1:])] += len(entries) - len(self.previous_entries)
        for old, new in zip(self.previous_entries, entries):
            assert old == new or (old.reward_status == "pending" and new.reward_status in ("awarded", "unavailable"))
        self.previous_entries = entries
        self.reward_summary = {
            "revealed": len(entries),
            "terrain": dict(Counter(game.tiles[e.tile_index].terrain for e in entries)),
            "ordinary_awarded": dict(Counter(e.resource for e in entries if e.reward_status == "awarded" and game.tiles[e.tile_index].terrain != "gold")),
            "gold_awarded": sum(game.tiles[e.tile_index].terrain == "gold" and e.reward_status == "awarded" for e in entries),
            "statuses": dict(Counter(e.reward_status for e in entries)),
            "triggers": dict(self.discovery_triggers), "island_bonus": 0,
        }

    async def command(self, pid, cmd, **kwargs):
        before, _ = await self.committed_game()
        self.observation = (pid, cmd["type"], self.state["phase"])
        try:
            result = await super().command(pid, cmd, **kwargs)
            if not kwargs.get("expect_applied", True):
                after, _ = await self.committed_game()
                assert before["engine"] == after["engine"]
                self.recovery_evidence.append({"kind": "atomic_rejected_command", "command": cmd["type"], "tick": self.peers[0].state["tick"]})
            return result
        finally: self.observation = None

    async def duplicate(self):
        before, _ = await self.committed_game()
        states = [deepcopy(p.state) for p in self.peers]
        await super().duplicate()
        after, _ = await self.committed_game()
        assert before["engine"] == after["engine"]
        assert [p.state for p in self.peers] == states

    async def takeover(self, pid=0):
        old = self.peers[pid]
        saved = deepcopy(old.state)
        replacement = await self.connect()
        await replacement.send({"type": "reconnect", "room_code": self.room_code, "reconnect_token": old.token})
        await replacement.wait(lambda: replacement.state is not None and replacement.token is not None)
        self.peers[pid] = replacement
        assert replacement.state == saved
        await old.send({"type": "cmd", "cmd_id": uuid.uuid4().hex, "seq": self.seq[pid] + 1,
                        "match_id": saved["match_id"], "cmd": {"type": "noop"}})
        await old.wait(lambda: old.closed or bool(old.errors))
        assert old.state == saved
        await old.close()
        self.recovery_evidence.append({"kind": "controlling_socket_takeover", "tick": saved["tick"]})
        self.assert_views()

    async def rematch(self, result):
        _, previous = await self.committed_game()
        await super().rematch(result)
        self.seq = [0, 0]
        _, fresh = await self.committed_game()
        assert fresh.scenario.fog.assignment_digest != previous.scenario.fog.assignment_digest
        assert not fresh.scenario.fog.revealed and not fresh.scenario.fog.discoveries
        assert fresh.scenario.fog.continuation is None and not fresh.pending_gold
        assert not fresh.ships_built_this_turn and not fresh.ship_moved_this_turn
        assert all(p.last_seq == 0 for p in self.peers)
        await self.assert_conservation()
        self.recovery_evidence.append({"kind": "fresh_fog_assignment_no_rewards_or_history", "epoch": 2})


async def play_fog(backend, *, max_rolls=450):
    match = FogMatch(backend)
    agents = [FogAgent(pid) for pid in range(2)]
    await match.create()
    pending_restart = reconnected = takeover = lost_ack = invalid_gold = invalid_road = False
    discovery_lost_ack = ship_restart = False
    try:
        while not match.state["game_over"]:
            assert match.counters["roll"] < max_rolls, ("Fog policy did not finish", dict(match.counters),
                                                       [p["vp"] for p in match.state["players"]])
            s = match.state
            if s["pending_action"] == "choose_gold":
                if not pending_restart:
                    await match.restart()
                    match.recovery_evidence.append({"kind": "restart_during_pending_gold", "tick": match.peers[0].state["tick"]})
                    pending_restart = True
                if not invalid_gold:
                    await match.command(s["pending_pid"], {"type": "choose_gold", "res": "gold"}, expect_applied=False)
                    invalid_gold = True
            if match.counters["roll"] >= 3 and not reconnected:
                await match.reconnect()
                reconnected = True
            if match.counters["roll"] >= 4 and not takeover:
                await match.takeover()
                takeover = True
            if s["phase"] == "main" and s["rolled"] and not s["pending_action"] and not invalid_road:
                await match.command(s["turn"], {"type": "place_road", "eid": [-900, 900]}, expect_applied=False)
                await match.duplicate()
                invalid_road = True
            selected = None
            if not s["pending_action"]:
                for pid, agent in enumerate(agents):
                    cmd = agent.accept(match.peers[pid].state["state"])
                    if cmd: selected = pid, cmd; break
            if selected is None:
                for pid, agent in enumerate(agents):
                    cmd = agent.next(match.peers[pid].state["state"])
                    if cmd: selected = pid, cmd; break
            assert selected, "No entitled action in natural Fog policy"
            pid, cmd = selected
            phase = s["phase"]
            discovery_loss = (cmd["type"] in ("place_road", "build_ship") and not discovery_lost_ack
                              and FogAgent.frontier(s, cmd["eid"]) > 0)
            gold_loss = cmd["type"] == "choose_gold" and not lost_ack
            lose = discovery_loss or gold_loss
            await match.command(pid, cmd, lose_ack=lose)
            lost_ack |= gold_loss
            discovery_lost_ack |= discovery_loss
            if discovery_loss: match.recovery_evidence.append({"kind": "discovery_route_lost_ack", "tick": match.peers[0].state["tick"]})
            if gold_loss: match.recovery_evidence.append({"kind": "gold_choice_lost_ack", "tick": match.peers[0].state["tick"]})
            if phase == "main" and not cmd.get("free") and cmd["type"] in ("place_road", "build_ship"):
                agents[pid].paid[cmd["type"]] += 1
                if cmd["type"] == "build_ship" and not ship_restart:
                    await match.restart()
                    await match.duplicate()
                    match.recovery_evidence.append({"kind": "restart_after_paid_ship", "tick": match.peers[0].state["tick"]})
                    ship_restart = True
            if os.environ.get("CATAN_NATURAL_PROGRESS") and cmd["type"] == "roll" and match.counters["roll"] % 20 == 0:
                print(json.dumps({"rolls": match.counters["roll"], "actions": len(match.commands),
                                  "public_vp": [p["vp"] for p in match.state["players"]], "discoveries": match.reward_summary}), flush=True)
        assert all((pending_restart, reconnected, takeover, lost_ack, discovery_lost_ack, ship_restart, invalid_gold, invalid_road))
        result = await match.durable_result()
        rewards = deepcopy(match.reward_summary)
        await match.duplicate()
        await match.restart()
        assert await match.durable_result() == result
        await match.command(match.state["winner_pid"], {"type": "roll"}, expect_applied=False)
        await match.duplicate()
        assert await match.durable_result() == result
        await match.rematch(result)
        exported = match.export(result)
        exported.update(format="catan-natural-fog-match-v1", discovery=rewards,
                        paid_routes=[dict(a.paid) for a in agents])
        exported["rng_profile"] = {"id": "fog-natural-v1", "assignment": "server-only, distinct draw per epoch",
                                   "dice_cursor": "durable roll_count"}
        return exported
    finally: await match.close()


def serve(manifest):
    validate_database_url(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0" or os.environ.get("CATAN_HOST", "127.0.0.1") != "127.0.0.1":
        raise ValueError("Isolated loopback with Test Tools disabled is required")
    origin = "http://127.0.0.1:" + os.environ.get("CATAN_PORT", "18770")
    os.environ.update(CATAN_ENABLE_TEST_TOOLS="0", CATAN_PERSISTENCE_MODE="durable",
                      CATAN_AUTH_MODE="development", CATAN_AUTH_ORIGINS=origin)
    install_test_rng()
    from app import server_mp as server
    admission = FixtureAdmission(server, manifest)
    admission.install()
    original = server.app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            await admission.initialize()
            try: yield
            finally:
                if hasattr(app.state, "_fog_fixture_access"): del app.state._fog_fixture_access
    server.app.router.lifespan_context = lifespan
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if (dist / "index.html").is_file():
        class ProductionFiles(StaticFiles):
            async def get_response(self, path, scope):
                try: return await super().get_response(path, scope)
                except HTTPException as error:
                    if error.status_code != 404 or path.startswith(("assets/", "api/")): raise
                    return await super().get_response("index.html", scope)
        server.app.mount("/", ProductionFiles(directory=dist, html=True))
    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ.get("CATAN_PORT", "18770")),
                loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto",
                proxy_headers=False, log_level="error", access_log=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve",))
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    serve(args.manifest)


if __name__ == "__main__": main()
