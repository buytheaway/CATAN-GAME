"""Natural-match TCP/PG acceptance support; never imported by the runtime.

Run a disposable backend with ``python -m tests.full_match_support serve``.
Run synthetic transcript generation with ``python -m tests.full_match_support run``.
The agents read only their authorized wire snapshot, never a live GameState.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
from copy import deepcopy
from contextvars import ContextVar
import hashlib
import heapq
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import websockets
from websockets.exceptions import ConnectionClosed

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
RESOURCES = ("wood", "brick", "sheep", "wheat", "ore")
COST = {"road": {"wood": 1, "brick": 1}, "ship": {"wood": 1, "sheep": 1},
        "settlement": {"wood": 1, "brick": 1, "sheep": 1, "wheat": 1},
        "city": {"wheat": 2, "ore": 3}, "dev": {"sheep": 1, "wheat": 1, "ore": 1}}
TERRAIN = dict(forest="wood", hills="brick", pasture="sheep", fields="wheat", mountains="ore")
SETTINGS = {"starting_player": "host", "dice_mode": "random", "bank_visibility": "hidden"}
RNG_PROFILE = {"id": "natural-match-v1", "map_seed": 1701, "deck_shuffle_seed": 811,
               "theft_draw_seed": 901, "base_totals": [6, 8, 5, 9, 4, 10, 3, 11, 2, 12, 7],
               "seafarers_totals": [6, 8, 5, 9, 4, 10, 3, 11, 2, 12] * 3 + [7],
               "dice_cursor": "candidate durable roll_count", "theft_draw": "fresh seeded draw per theft"}
PUBLIC_FIELDS = ("phase", "turn", "rolled", "setup_order", "setup_idx", "setup_need",
                 "setup_anchor_vid", "last_roll", "robber_tile", "robbers", "pirate_tile",
                 "pending_action", "pending_pid", "trade_offers", "longest_road_owner",
                 "longest_road_len", "largest_army_owner", "largest_army_size", "game_over",
                 "winner_pid", "occupied_v", "occupied_e", "occupied_ships", "tiles", "vertices",
                 "edges", "vertex_adj_hexes", "edge_adj_hexes", "ports", "scenario", "map_id",
                 "rules_config", "roll_count", "dice", "test_mode", "test_tools")


def install_test_rng():
    """Server-only deterministic draws, with no command privilege or resource grant.

    Dice depend on the already persisted public roll counter, so a crash/restart
    cannot rewind the test sequence. Credential RNG is deliberately untouched.
    """
    validate_database_url(os.environ.get("DATABASE_URL", ""))
    from app import server_mp as server
    from app.engine import rules

    server.secrets.randbits = lambda bits: 1701
    server.random.SystemRandom = lambda: random.Random(811)

    class TheftDraw:
        def randrange(self, stop):
            return random.Random(901).randrange(stop)
    rules._THEFT_RNG = TheftDraw()
    totals = (6, 8, 5, 9, 4, 10, 3, 11, 2, 12, 7)
    roll_context = ContextVar("natural_match_roll_context", default=(0, "base_standard"))
    original_apply = server._apply_cmd

    def apply_with_roll_context(room, pid, command, **kwargs):
        marker = roll_context.set((room.roll_count, room.game.map_id))
        try:
            return original_apply(room, pid, command, **kwargs)
        finally:
            roll_context.reset(marker)
    server._apply_cmd = apply_with_roll_context

    def roll():
        count, map_id = roll_context.get()
        sequence = totals if "seafarers" not in map_id else totals[:-1] * 3 + (7,)
        total = sequence[count % len(sequence)]
        first = min(6, total - 1)
        return first, total - first
    server._roll_dice = roll


def install_natural_rng(server=None):
    """Compatibility entry point for the isolated browser launcher."""
    install_test_rng()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def validate_database_url(value):
    from sqlalchemy.engine import make_url
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg" or url.host not in ("127.0.0.1", "localhost", "::1")
            or not url.database or not url.database.endswith("_test")):
        raise ValueError("Natural-match harness requires an isolated localhost PostgreSQL database ending in _test")
    return value


class Backend:
    def __init__(self, database_url, port=None, *, module="tests.full_match_support", serve_args=()):
        self.database_url, self.port = validate_database_url(database_url), port or free_port()
        self.module, self.serve_args = module, tuple(serve_args)
        self.process = None
        self.log = tempfile.TemporaryFile(mode="w+b")

    def start(self):
        env = {**os.environ, "DATABASE_URL": self.database_url, "CATAN_PERSISTENCE_MODE": "durable",
               "CATAN_ENABLE_TEST_TOOLS": "0", "CATAN_HOST": "127.0.0.1", "CATAN_PORT": str(self.port),
               "CATAN_AUTH_ORIGINS": f"http://127.0.0.1:{self.port}"}
        self.process = subprocess.Popen([sys.executable, "-B", "-m", self.module, "serve", *self.serve_args],
            cwd=ROOT, env=env, stdout=self.log, stderr=self.log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.log.seek(0)
                raise AssertionError("Natural-match backend exited: " + self.log.read().decode(errors="replace")[-3000:])
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1) as response:
                    if json.load(response)["ready"]:
                        return
            except OSError:
                pass
            time.sleep(.05)
        self.log.seek(0)
        raise AssertionError("Natural-match backend readiness timeout: " + self.log.read().decode(errors="replace")[-3000:])

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)

    def close(self):
        self.stop()
        self.log.close()


class Peer:
    def __init__(self, socket_):
        self.socket = socket_
        self.state = self.room = None
        self.token = None
        self.acks, self.errors = {}, []
        self.drop_ack_ids = set()
        self.changed = asyncio.Event()
        self.closed = False
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        try:
            async for raw in self.socket:
                msg = json.loads(raw)
                if msg["type"] == "match_state": self.state = msg
                elif msg["type"] == "room_state": self.room = msg
                elif msg["type"] == "reconnect_token": self.token = msg["reconnect_token"]
                elif msg["type"] == "cmd_ack" and msg["cmd_id"] not in self.drop_ack_ids:
                    self.acks[msg["cmd_id"]] = msg
                elif msg["type"] == "error": self.errors.append(msg)
                self.changed.set()
        except ConnectionClosed:
            pass
        finally:
            self.closed = True
            self.changed.set()

    async def wait(self, predicate, timeout=15):
        async def until():
            while not predicate():
                self.changed.clear()
                if predicate(): break
                if self.closed: raise AssertionError("Owning WebSocket closed")
                await self.changed.wait()
        await asyncio.wait_for(until(), timeout)

    async def send(self, message):
        await self.socket.send(json.dumps(message))

    async def close(self):
        await self.socket.close()
        await self.reader


def public_state(state):
    out = {key: deepcopy(state[key]) for key in PUBLIC_FIELDS if key in state}
    out["players"] = [{key: p[key] for key in ("pid", "name", "color", "resource_count", "dev_count",
                     "knights_played", "special_vp") if key in p} for p in state["players"]]
    if state["game_over"]:
        for view, player in zip(out["players"], state["players"]): view["vp"] = player["vp"]
    return out


def public_checksum(state):
    return hashlib.sha256(json.dumps(public_state(state), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Match:
    def __init__(self, backend, count, map_id):
        self.backend, self.count, self.map_id = backend, count, map_id
        self.peers, self.seq = [], [0] * count
        self.names = [f"Natural {i+1}" for i in range(count)]
        self.room_code = None
        self.commands, self.counters = [], Counter()
        self.last_wire = None
        self.recovery_evidence = []
        self.conservation_checkpoints = 0
        from app.persistence.db import Database
        self.database = Database(backend.database_url)

    @property
    def state(self): return self.peers[0].state["state"]

    async def connect(self):
        return Peer(await websockets.connect(f"ws://127.0.0.1:{self.backend.port}/ws", max_size=2**22))

    async def create(self):
        for i in range(self.count):
            peer = await self.connect()
            self.peers.append(peer)
            await peer.send({"type": "create_room", "name": self.names[i], "max_players": self.count} if i == 0 else
                {"type": "join_room", "name": self.names[i], "room_code": self.room_code})
            await peer.wait(lambda: peer.room is not None and peer.token is not None)
            self.room_code = peer.room["room_code"]
        host = self.peers[0]
        before = host.room["config_revision"]
        await host.send({"type": "set_settings", "settings": SETTINGS})
        await host.wait(lambda: host.room["config_revision"] > before)
        before = host.room["map_revision"]
        await host.send({"type": "set_map", "map_id": self.map_id})
        await host.wait(lambda: host.room["map_revision"] > before)
        await host.send({"type": "start_match", "request_id": str(uuid.uuid4()), "expected_match_id": 0})
        await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in self.peers))
        self.assert_views()
        await self.assert_conservation()

    def assert_views(self):
        expected = public_state(self.state)
        tick = self.peers[0].state["tick"]
        for pid, peer in enumerate(self.peers):
            s = peer.state["state"]
            assert peer.state["tick"] == tick
            assert public_state(s) == expected
            assert s["you_pid"] == pid and not s["test_mode"] and not s["test_tools"]
            assert not ({"seed", "dev_deck", "ships_built_this_turn", "ship_moved_this_turn", "bank"} & s.keys())
            assert set(s["pending_gold"]) <= {str(pid)} and set(s["discard_required"]) <= {str(pid)}
            for p in s["players"]:
                if p["pid"] == pid:
                    assert sum(p["res"].values()) == p["resource_count"]
                    assert len(p["dev_cards"]) == p["dev_count"]
                else:
                    assert "res" not in p and "dev_cards" not in p
                    own = self.peers[p["pid"]].state["state"]["players"][p["pid"]]
                    hidden = sum(c["type"] == "victory_point" for c in own["dev_cards"])
                    assert p["vp"] == own["vp"] - (0 if s["game_over"] else hidden)

    async def command(self, pid, cmd, *, expect_applied=True, lose_ack=False):
        self.seq[pid] += 1
        wire = {"type": "cmd", "match_id": self.peers[pid].state["match_id"], "seq": self.seq[pid],
                "cmd_id": str(uuid.uuid4()), "cmd": cmd}
        before = public_checksum(self.state)
        previous_tick = self.peers[0].state["tick"]
        peer = self.peers[pid]
        if lose_ack:
            assert expect_applied
            peer.drop_ack_ids.add(wire["cmd_id"])
        await peer.send(wire)
        if lose_ack:
            # Simulate an ACK discarded by the client's transport. Independent
            # recipients establish that COMMIT already happened before takeover.
            await asyncio.gather(*(p.wait(lambda p=p: p.state["tick"] > previous_tick) for p in self.peers))
            assert wire["cmd_id"] not in peer.acks
            ack = {"applied": True, "last_seq_applied": self.seq[pid]}
        else:
            await peer.wait(lambda: wire["cmd_id"] in peer.acks)
            ack = peer.acks[wire["cmd_id"]]
            assert ack["applied"] is expect_applied, (pid, cmd, ack, peer.errors[-1:] )
        if expect_applied:
            tick = previous_tick + 1
            await asyncio.gather(*(p.wait(lambda p=p: p.state["tick"] >= tick) for p in self.peers))
            self.assert_views()
            self.commands.append({"actor_pid": pid, "cmd": deepcopy(cmd), "tick": tick,
                                  "public_checksum": public_checksum(self.state)})
            self.counters[cmd["type"]] += 1
            await self.assert_conservation()
        else:
            assert public_checksum(self.state) == before
        self.last_wire = (pid, wire)
        if lose_ack:
            await self.reconnect(pid)
            await self.duplicate()
            self.recovery_evidence.append({"kind": "client_transport_lost_ack_reconnect_retry", "tick": previous_tick + 1})
        return ack

    async def duplicate(self):
        pid, wire = self.last_wire
        peer = self.peers[pid]
        before = deepcopy(peer.state)
        peer.acks.pop(wire["cmd_id"], None)
        await peer.send(wire)
        await peer.wait(lambda: wire["cmd_id"] in peer.acks)
        assert peer.acks[wire["cmd_id"]]["duplicate"]
        assert peer.state == before
        self.recovery_evidence.append({"kind": "duplicate_receipt", "tick": before["tick"]})

    async def reconnect(self, pid=0):
        old = self.peers[pid]
        before = deepcopy(old.state)
        token = old.token
        await old.close()
        peer = await self.connect()
        self.peers[pid] = peer
        await peer.send({"type": "reconnect", "room_code": self.room_code, "reconnect_token": token})
        await peer.wait(lambda: peer.state is not None and peer.token is not None)
        assert peer.token == token and peer.state == before
        self.assert_views()
        self.recovery_evidence.append({"kind": "guest_reconnect", "tick": before["tick"]})

    async def restart(self):
        before = [deepcopy(p.state) for p in self.peers]
        tokens = [p.token for p in self.peers]
        await asyncio.to_thread(self.backend.stop)
        await asyncio.gather(*(p.close() for p in self.peers))
        await asyncio.to_thread(self.backend.start)
        self.peers = []
        for pid, token in enumerate(tokens):
            peer = await self.connect()
            self.peers.append(peer)
            await peer.send({"type": "reconnect", "room_code": self.room_code, "reconnect_token": token})
            await peer.wait(lambda: peer.state is not None and peer.token is not None)
            assert peer.state == before[pid]
        self.assert_views()
        self.recovery_evidence.append({"kind": "backend_restart", "tick": self.peers[0].state["tick"],
                                       "game_over": self.state["game_over"]})

    async def durable_result(self, match_no=None):
        from sqlalchemy import select
        from app.persistence.db import Database
        from app.persistence import models as m
        from app.persistence.snapshots import decode_snapshot
        db = Database(self.backend.database_url)
        try:
            async with db.sessions() as session:
                query = select(m.matches).join(m.rooms, m.rooms.c.id == m.matches.c.room_id).where(m.rooms.c.room_code == self.room_code)
                query = query.where(m.matches.c.match_no == match_no) if match_no else query.where(m.rooms.c.current_match_id == m.matches.c.id)
                match = (await session.execute(query)).mappings().one()
                players = (await session.execute(select(m.match_players).where(m.match_players.c.match_id == match["id"])
                           .order_by(m.match_players.c.pid))).mappings().all()
                assert match["status"] == "finished" and match["finished_at"] is not None
                payload = (await session.execute(select(m.game_snapshots.c.payload).where(m.game_snapshots.c.id == match["latest_snapshot_id"]))).scalar_one()
                game = decode_snapshot(payload["engine"])
                assert game.game_over and game.winner_pid is not None
                assert match["winner_match_player_id"] == players[game.winner_pid]["id"]
                assert [p["final_vp"] for p in players] == [p.vp for p in game.players]
                assert [p["consumed_seq"] for p in players] == self.seq
                assert not match["is_test"]
                assert all(game.bank[r] + sum(p.res[r] for p in game.players) == 19 for r in RESOURCES)
                assert len(game.dev_deck) + sum(len(p.dev_cards) for p in game.players) + self.counters["play_dev"] == 25
                return {"status": match["status"], "winner_pid": game.winner_pid,
                        "final_vp": [p["final_vp"] for p in players], "tick": match["tick"],
                        "resource_conservation": True, "development_card_conservation": True,
                        "longest_road_owner": game.longest_road_owner, "longest_road_len": game.longest_road_len,
                        "largest_army_owner": game.largest_army_owner,
                        "ruleset_id": match["ruleset_id"], "snapshot_version": payload["engine"]["snapshot_version"],
                        "engine_compatibility": payload["engine"]["engine_compatibility"],
                        "awarded_islands": {str(p): sorted(islands) for p, islands in game.scenario.awarded_islands.items()}}
        finally:
            await db.close()

    async def assert_conservation(self):
        """Read-only durable evidence, never an input to a player's policy."""
        from sqlalchemy import select
        from app.persistence import models as m
        from app.persistence.snapshots import decode_snapshot
        async with self.database.sessions() as session:
            payload = (await session.execute(select(m.game_snapshots.c.payload)
                .join(m.matches, m.matches.c.latest_snapshot_id == m.game_snapshots.c.id)
                .join(m.rooms, m.rooms.c.current_match_id == m.matches.c.id)
                .where(m.rooms.c.room_code == self.room_code))).scalar_one()
            game = decode_snapshot(payload["engine"])
            assert all(game.bank[r] + sum(p.res[r] for p in game.players) == 19 for r in RESOURCES)
            assert payload["tick"] == self.peers[0].state["tick"]
            self.conservation_checkpoints += 1

    async def close(self):
        await asyncio.gather(*(p.close() for p in self.peers), return_exceptions=True)
        await self.database.close()

    async def rematch(self, finished_result):
        old_epoch = self.peers[0].state["match_id"]
        wire = {"type": "rematch", "request_id": str(uuid.uuid4()), "expected_match_id": old_epoch}
        await self.peers[0].send(wire)
        await asyncio.gather(*(p.wait(lambda p=p: p.state["match_id"] > old_epoch) for p in self.peers))
        self.assert_views()
        assert self.state["phase"] == "setup" and not self.state["game_over"]
        assert not self.state["occupied_v"] and not self.state["occupied_e"] and not self.state["occupied_ships"]
        assert all(p["vp"] == 0 and p["resource_count"] == 0 for p in self.state["players"])
        assert not self.state["scenario"]["awarded_islands"]
        assert await self.durable_result(old_epoch) == finished_result
        await self.peers[0].send(wire)
        await self.peers[0].wait(lambda: self.peers[0].room.get("request_id") == wire["request_id"])
        assert self.peers[0].state["match_id"] == old_epoch + 1
        self.recovery_evidence.append({"kind": "fresh_rematch_preserves_finished_result", "old_epoch": old_epoch,
                                       "new_epoch": old_epoch + 1})

    def export(self, result):
        return {"format": "catan-natural-match-v1", "map_id": self.map_id, "player_count": self.count,
                "rng_profile": RNG_PROFILE,
                "names": self.names, "settings": SETTINGS, "commands": self.commands,
                "counters": dict(self.counters), "actual_turns": self.counters["roll"],
                "player_actions": len(self.commands), "recovery": self.recovery_evidence,
                "conservation_checkpoints": self.conservation_checkpoints,
                "result": result}


def edge_key(edge): return f"{min(edge)},{max(edge)}"
def edges_owned(state, kind, pid):
    return {tuple(map(int, key.split(","))) for key, owner in state[kind].items() if owner == pid}


class NaturalAgent:
    """A cooperative legal player, using only one participant's snapshot at a time."""
    def __init__(self, pid, seafarers=False):
        self.pid, self.seafarers = pid, seafarers
        self.offer_turns = set()
        self.dev_bought = 0
        self.active_card_played = False

    def hand(self, s): return s["players"][self.pid]["res"]

    def productivity(self, s, vid):
        return sum(6 - abs(7 - s["tiles"][i]["number"]) for i in s["vertex_adj_hexes"].get(str(vid), [])
                   if s["tiles"][i].get("number"))

    def setup(self, s):
        legal = s["legal"]
        if s["setup_need"] == "settlement":
            def score(vid):
                terrains = {TERRAIN.get(s["tiles"][i]["terrain"]) for i in s["vertex_adj_hexes"][str(vid)]}
                coast = any(self.has_sea(s, e) for e in s["edges"] if vid in e)
                existing = {TERRAIN.get(s["tiles"][i]["terrain"]) for v, (p, _) in s["occupied_v"].items()
                            if p == self.pid for i in s["vertex_adj_hexes"][v]}
                # Winner gets high production, ore/wheat and two sea access points.
                economy = (8 * ("ore" in terrains - existing) + 6 * ("wheat" in terrains - existing)) if self.seafarers else 0
                return (40 * coast if self.seafarers else 0) + self.productivity(s, vid) + 4 * len(terrains - existing) + economy
            return {"type": "place_settlement", "vid": max(legal["settlements"], key=lambda v: (score(v), -v))}
        if self.seafarers and legal["ships"]:
            return {"type": "build_ship", "eid": legal["ships"][0]}
        return {"type": "place_road", "eid": legal["roads"][0]}

    def has_sea(self, s, e):
        adjacent = s["edge_adj_hexes"][edge_key(e)]
        return any(s["tiles"][i]["terrain"] == "sea" for i in adjacent) or (len(adjacent) == 1 and s["rules"].get("sea_frame"))

    def islands(self, s):
        land = {i for i, t in enumerate(s["tiles"]) if t["terrain"] != "sea"}
        neighbors = {i: set() for i in land}
        for adjacent in s["edge_adj_hexes"].values():
            touching = land.intersection(adjacent)
            for i in touching: neighbors[i].update(touching - {i})
        result = {}
        while land:
            root, stack = min(land), [min(land)]
            component = set()
            while stack:
                tile = stack.pop()
                if tile in component: continue
                component.add(tile)
                stack.extend(neighbors[tile] - component)
            land.difference_update(component)
            for tile in component: result[tile] = root
        return result

    def destination_path(self, s):
        owned = {int(v) for v, (p, _) in s["occupied_v"].items() if p == self.pid}
        occupied = {int(v): owner for v, (owner, _) in s["occupied_v"].items()}
        roads = edges_owned(s, "occupied_e", self.pid)
        ships = edges_owned(s, "occupied_ships", self.pid)
        all_roads = {tuple(map(int, k.split(","))) for k in s["occupied_e"]}
        all_ships = {tuple(map(int, k.split(","))) for k in s["occupied_ships"]}
        graph = {int(v): [] for v in s["vertices"]}
        for edge in s["edges"]:
            a, b = edge
            graph[a].append((b, tuple(edge)))
            graph[b].append((a, tuple(edge)))
        eligible = None
        islands = self.islands(s) if self.seafarers else {}
        if self.seafarers:
            scenario = s["scenario"]
            eligible = set(islands.values()) - set(scenario["home_islands"].get(str(self.pid), [])) - set(scenario["awarded_islands"].get(str(self.pid), []))
            if not eligible: return None
        queue = [(0, v, []) for v in owned]
        heapq.heapify(queue)
        seen = {}
        while queue:
            cost, v, path = heapq.heappop(queue)
            if cost >= seen.get(v, 999): continue
            seen[v] = cost
            touching = {islands[i] for i in s["vertex_adj_hexes"].get(str(v), []) if i in islands}
            distance_ok = v not in occupied and all(other not in occupied for other, _ in graph[v])
            on_land = any(s["tiles"][i]["terrain"] != "sea" for i in s["vertex_adj_hexes"].get(str(v), []))
            if path and distance_ok and on_land and (eligible is None or touching & eligible):
                return v, path
            for other, edge in sorted(graph[v]):
                if occupied.get(other, self.pid) != self.pid: continue
                if self.seafarers:
                    if not self.has_sea(s, edge) or edge in all_roads or (edge in all_ships and edge not in ships): continue
                    if s["pirate_tile"] in s["edge_adj_hexes"][edge_key(edge)]: continue
                    built = edge in ships
                else:
                    if edge in all_ships or (edge in all_roads and edge not in roads): continue
                    if not any(s["tiles"][i]["terrain"] != "sea" for i in s["edge_adj_hexes"][edge_key(edge)]): continue
                    built = edge in roads
                heapq.heappush(queue, (cost + (not built), other, path + [edge]))
        return None

    def goal(self, s):
        owned = [(int(v), level) for v, (pid, level) in s["occupied_v"].items() if pid == self.pid]
        cities = sum(level == 2 for _, level in owned)
        if cities < 4:
            settlements = [v for v, level in owned if level == 1]
            if settlements:
                v = max(settlements, key=lambda v: self.productivity(s, v))
                return "city", {"type": "upgrade_city", "vid": v}, v in s["legal"]["cities"]
        route = self.destination_path(s)
        if route and len(owned) < 4:
            target, path = route
            kind = "ship" if self.seafarers else "road"
            occupancy = "occupied_ships" if self.seafarers else "occupied_e"
            missing = next((e for e in path if edge_key(e) not in s[occupancy]), None)
            if missing:
                cmd = {"type": "build_ship" if self.seafarers else "place_road", "eid": list(missing)}
                return kind, cmd, list(missing) in s["legal"]["ships" if self.seafarers else "roads"]
            return "settlement", {"type": "place_settlement", "vid": target}, target in s["legal"]["settlements"]
        kind = "ship" if self.seafarers else "road"
        options = s["legal"]["ships" if self.seafarers else "roads"]
        if s["longest_road_owner"] != self.pid:
            if options:
                own_edges = edges_owned(s, "occupied_ships" if self.seafarers else "occupied_e", self.pid)
                degree = Counter(v for edge in own_edges for v in edge)
                edge = min(options, key=lambda e: (min(degree[e[0]], degree[e[1]]), sum(degree[v] for v in e), e))
                return kind, {"type": "build_ship" if self.seafarers else "place_road", "eid": edge}, True
            return kind, None, False
        return "dev", {"type": "buy_dev"}, all(self.hand(s)[r] >= n for r, n in COST["dev"].items())

    def rate(self, s, resource):
        owned = {int(v) for v, (p, _) in s["occupied_v"].items() if p == self.pid}
        kinds = {kind for edge, kind in s["ports"] if any(v in owned for v in edge)}
        return 2 if "2:1:" + resource in kinds else 3 if "3:1" in kinds else 4

    def pending(self, s):
        hand = self.hand(s)
        action = s["pending_action"]
        if action == "discard" and str(self.pid) in s["discard_required"]:
            need = s["discard_required"][str(self.pid)]
            counts, discards = dict(hand), {}
            while need:
                resource = max(RESOURCES, key=lambda r: counts[r])
                counts[resource] -= 1
                discards[resource] = discards.get(resource, 0) + 1
                need -= 1
            return {"type": "discard", "discards": discards}
        if action == "choose_gold" and s["pending_pid"] == self.pid:
            resource = min((r for r in RESOURCES if s["bank_available"][r]), key=lambda r: hand[r])
            return {"type": "choose_gold", "res": resource, "qty": 1}
        if action == "robber_move" and s["pending_pid"] == self.pid:
            pirate = self.seafarers and s["roll_count"] % 2 == 0
            key = "pirate" if pirate else "robber"
            options = s["legal"][key + "_tiles"]
            victims = s["legal"][key + "_victims"]
            def score(tile):
                # Protect own production/routes while exercising actual theft.
                own = sum(owner == self.pid for edge, owner in s["occupied_ships"].items()
                          if tile in s["edge_adj_hexes"][edge]) if pirate else sum(
                          owner == self.pid for vid, (owner, _) in s["occupied_v"].items() if tile in s["vertex_adj_hexes"][vid])
                return 100 * own - 10 * bool(victims.get(str(tile), [])), tile
            tile = min(options, key=score)
            return {"type": "move_pirate" if pirate else "move_robber", "tile": tile}
        return None

    def play_card(self, s):
        if s["dev_played_turn"].get(str(self.pid)): return None
        for card in s["players"][self.pid]["dev_cards"]:
            kind = card["type"]
            if card.get("new") or kind == "victory_point": continue
            cmd = {"type": "play_dev", "card": kind}
            if kind == "year_of_plenty":
                available = [r for r in RESOURCES if s["bank_available"][r]]
                if len(available) < 2: continue
                available.sort(key=lambda r: self.hand(s)[r])
                cmd.update(a=available[0], b=available[1], qa=1, qb=1)
            elif kind == "monopoly": cmd["r"] = min(RESOURCES, key=lambda r: self.hand(s)[r])
            return cmd
        return None

    def next(self, s):
        if s["pending_action"]: return self.pending(s)
        if s["phase"] == "setup": return self.setup(s) if s["turn"] == self.pid else None
        if s["turn"] != self.pid or s["game_over"]: return None
        if not s["rolled"]: return {"type": "roll"}
        card = self.play_card(s)
        if card:
            self.active_card_played = True
            return card
        # Other participants develop their own hand and army without blocking the
        # designated winning builder's shared route destinations.
        if self.pid != 0:
            if self.dev_bought < 3 and all(self.hand(s)[r] >= n for r, n in COST["dev"].items()):
                self.dev_bought += 1
                return {"type": "buy_dev"}
            return {"type": "end_turn"}
        kind, command, legal = self.goal(s)
        if s["free_roads"].get(str(self.pid), 0):
            options = s["legal"]["ships" if self.seafarers else "roads"]
            if options:
                return {"type": "build_ship" if self.seafarers else "place_road", "eid": options[0], "free": True}
        # Exercise a real development purchase before the structural winning plan.
        cards = s["players"][self.pid]["dev_cards"]
        cities = sum(p == self.pid and level == 2 for p, level in s["occupied_v"].values())
        need_active_card = (self.seafarers and cities >= 2 and self.dev_bought < 6 and not self.active_card_played
                            and not any(c["type"] != "victory_point" for c in cards))
        if (self.dev_bought < 1 or need_active_card) and all(self.hand(s)[r] >= n for r, n in COST["dev"].items()):
            self.dev_bought += 1
            return {"type": "buy_dev"}
        if legal and command: return command
        cost, hand = COST[kind], self.hand(s)
        missing = [r for r, n in cost.items() if hand[r] < n]
        surplus = sorted(RESOURCES, key=lambda r: (hand[r] - cost.get(r, 0), r), reverse=True)
        if missing:
            turn = s["roll_count"]
            if turn not in self.offer_turns and hand[surplus[0]] > cost.get(surplus[0], 0):
                self.offer_turns.add(turn)
                return {"type": "trade_offer_create", "give": {surplus[0]: 1}, "get": {missing[0]: 1}}
            for get in missing:
                if not s["bank_available"][get]: continue
                for give in surplus:
                    if give != get and hand[give] - cost.get(give, 0) >= self.rate(s, give):
                        return {"type": "trade_bank", "give": give, "get": get, "get_qty": 1}
        return {"type": "end_turn"}

    def accept(self, s):
        for offer in reversed(s["trade_offers"]):
            if offer["status"] != "active" or offer["from_pid"] == self.pid: continue
            if offer["to_pid"] not in (None, self.pid): continue
            if all(self.hand(s)[r] >= n for r, n in offer["get"].items()):
                return {"type": "trade_offer_accept", "offer_id": offer["offer_id"]}
        return None


async def play_natural(backend, count, map_id, *, smoke_turns=None, max_turns=650):
    match = Match(backend, count, map_id)
    agents = [NaturalAgent(pid, "seafarers" in map_id) for pid in range(count)]
    await match.create()
    restarted = reconnected = duplicated = lost_ack = False
    try:
        while not match.state["game_over"]:
            turns = match.counters["roll"]
            assert turns < max_turns, ("Natural match did not finish", map_id, dict(match.counters),
                                      match.state["players"], match.state["occupied_v"])
            if smoke_turns and turns >= smoke_turns and not match.state["pending_action"]:
                return match.export({"status": "smoke", "tick": match.peers[0].state["tick"]})
            if turns >= 8 and not restarted:
                await match.restart()
                await match.duplicate()
                restarted = True
            if turns >= 4 and not reconnected:
                await match.reconnect(0)
                reconnected = True
            if match.commands and not duplicated:
                await match.duplicate()
                duplicated = True
            selected = None
            if not match.state["pending_action"]:
                for pid, agent in enumerate(agents):
                    cmd = agent.accept(match.peers[pid].state["state"])
                    if cmd:
                        selected = pid, cmd
                        break
            if selected is None:
                # Pending recipients may act outside the current player's turn.
                for pid, agent in enumerate(agents):
                    cmd = agent.next(match.peers[pid].state["state"])
                    if cmd:
                        selected = pid, cmd
                        break
            assert selected, ("No entitled legal action", match.state["pending_action"])
            lose_ack = turns >= 5 and not lost_ack
            await match.command(*selected, lose_ack=lose_ack)
            lost_ack |= lose_ack
            if os.environ.get("CATAN_NATURAL_PROGRESS") and selected[1]["type"] == "roll" and match.counters["roll"] % 20 == 0:
                print(json.dumps({"rolls": match.counters["roll"], "actions": len(match.commands),
                                  "public_vp": [p["vp"] for p in match.state["players"]]}), flush=True)
        result = await match.durable_result()
        await match.duplicate()
        await match.restart()
        assert await match.durable_result() == result
        # Normal post-game intentions are consumed rejections and remain inert.
        await match.command(match.state["winner_pid"], {"type": "roll"}, expect_applied=False)
        await match.duplicate()
        result_after_rejection = await match.durable_result()
        assert result_after_rejection == result
        await match.rematch(result)
        return match.export(result)
    finally:
        await match.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--web", action="store_true", help="Mount the existing web/dist for isolated browser replay")
    run = sub.add_parser("run")
    run.add_argument("--map", default="base_standard")
    run.add_argument("--players", type=int, default=2)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--smoke-turns", type=int)
    args = parser.parse_args()
    if args.action == "serve":
        validate_database_url(os.environ.get("DATABASE_URL", ""))
        if os.environ.get("CATAN_HOST", "127.0.0.1") not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Natural-match harness only binds loopback")
        if os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0":
            raise ValueError("Natural-match harness requires disabled Test Tools")
        os.environ["CATAN_ENABLE_TEST_TOOLS"] = "0"
        os.environ["CATAN_PERSISTENCE_MODE"] = "durable"
        os.environ["CATAN_AUTH_ORIGINS"] = f"http://127.0.0.1:{os.environ.get('CATAN_PORT', '18768')}"
        if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        install_test_rng()
        from app import server_mp as server
        if args.web:
            from fastapi.staticfiles import StaticFiles
            server.app.mount("/", StaticFiles(directory=ROOT / "web" / "dist", html=True), name="natural-web")
        import uvicorn
        uvicorn.run(server.app, host=os.environ.get("CATAN_HOST", "127.0.0.1"),
                    port=int(os.environ.get("CATAN_PORT", "18768")),
                    loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto",
                    proxy_headers=False, log_level="warning")
    else:
        database_url = os.environ["CATAN_TEST_DATABASE_URL"]
        backend = Backend(database_url)
        try:
            backend.start()
            evidence = asyncio.run(play_natural(backend, args.players, args.map, smoke_turns=args.smoke_turns))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({key: evidence[key] for key in ("map_id", "actual_turns", "player_actions", "counters", "result")}, ensure_ascii=False))
        finally:
            backend.close()


if __name__ == "__main__": main()
