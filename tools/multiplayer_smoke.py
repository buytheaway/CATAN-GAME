from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import sys
import uuid
from pathlib import Path
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn
import websockets

from app import net_protocol
from app.engine import build_game, can_place_road, can_place_settlement


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server(port: int):
    config = uvicorn.Config("app.server_mp:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    start = time.time()
    while not server.started and time.time() - start < 5:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        raise RuntimeError("Server failed to start")
    return server, thread


async def _send(ws, obj):
    await ws.send(json.dumps(obj))


async def _recv_type(ws, want: str, timeout: float = 5.0):
    end = time.time() + timeout
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
        data = json.loads(raw)
        if data.get("type") == "error":
            raise AssertionError(f"Server error: {data.get('message')}")
        if data.get("type") == want:
            return data
    raise AssertionError(f"Timed out waiting for {want}")


async def _send_cmd(ws, match_id: int, seq: int, cmd: dict, cmd_id: str | None = None) -> str:
    cid = cmd_id or uuid.uuid4().hex
    await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq, "cmd_id": cid, "cmd": cmd})
    return cid


def _state_hash(state: dict) -> str:
    blob = json.dumps(state, sort_keys=True).encode("utf-8")
    return sha256(blob).hexdigest()


def _apply_snapshot(g, state: dict):
    g.occupied_v = {int(k): (int(v[0]), int(v[1])) for k, v in state.get("occupied_v", {}).items()}
    g.occupied_e = {}
    for k, owner in state.get("occupied_e", {}).items():
        a, b = [int(x) for x in str(k).split(",", 1)]
        e = (a, b) if a < b else (b, a)
        g.occupied_e[e] = int(owner)
    g.setup_order = [int(x) for x in state.get("setup_order", [])]
    g.setup_idx = int(state.get("setup_idx", 0))
    g.setup_need = state.get("setup_need", "settlement")
    g.setup_anchor_vid = state.get("setup_anchor_vid", None)
    g.phase = state.get("phase", "setup")
    g.turn = int(state.get("turn", 0))
    g.rolled = bool(state.get("rolled", False))
    g.robber_tile = int(state.get("robber_tile", 0))


def _pick_settlement(g, pid: int) -> int:
    for vid in sorted(g.vertices.keys()):
        if can_place_settlement(g, pid, vid, require_road=False):
            return vid
    raise AssertionError("No legal settlement found")


def _pick_road(g, pid: int, anchor_vid: int) -> tuple:
    for a, b in sorted(g.edges):
        e = (a, b) if a < b else (b, a)
        if can_place_road(g, pid, e, must_touch_vid=anchor_vid):
            return e
    raise AssertionError("No legal road found")

def _plan_discard_from_state(state: dict, pid: int, need: int) -> dict:
    res = (state.get("players", [{}])[pid].get("res", {}) if state.get("players") else {})
    plan = {r: 0 for r in res.keys()}
    remaining = int(need)
    for r in sorted(res.keys()):
        if remaining <= 0:
            break
        take = min(int(res.get(r, 0)), remaining)
        if take > 0:
            plan[r] = take
            remaining -= take
    return plan


async def _run_clients(port: int, max_players: int = 2):
    url = f"ws://127.0.0.1:{port}/ws"
    conns = [await websockets.connect(url) for _ in range(max_players)]
    try:
        names = [f"P{i+1}" for i in range(max_players)]
        for ws, name in zip(conns, names):
            await _send(ws, {"type": "hello", "version": net_protocol.VERSION, "name": name})
            await _recv_type(ws, "hello")

        host = conns[0]
        await _send(host, {"type": "create_room", "name": names[0], "max_players": max_players, "ruleset": {"base": True, "max_players": max_players}})
        room_state = await _recv_type(host, "room_state")
        room_code = room_state["room_code"]

        for idx in range(1, max_players):
            await _send(conns[idx], {"type": "join_room", "room_code": room_code, "name": names[idx]})
            await _recv_type(conns[idx], "room_state")
            room_state = await _recv_type(host, "room_state")

        await _send(host, {"type": "start_match"})
        ms1 = await _recv_type(host, "match_state")
        ms2 = await _recv_type(conns[1], "match_state")
        if ms1["tick"] != ms2["tick"]:
            raise AssertionError("tick mismatch after start")
        if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
            raise AssertionError("state hash mismatch after start")

        match_id = int(ms1.get("match_id", 0))
        state = ms1.get("state", {})
        seed = int(ms1.get("seed", 0))
        g = build_game(seed=seed, max_players=max_players, size=float(state.get("size", 58.0)))
        _apply_snapshot(g, state)

        clients = {}
        for p in room_state.get("players", []):
            name = p.get("name")
            if name in names:
                pid = int(p["pid"])
                clients[pid] = conns[names.index(name)]
        seq = {pid: 0 for pid in clients.keys()}

        while state.get("phase") == "setup":
            pid = state["setup_order"][state["setup_idx"]]
            ws = clients[pid]
            if state.get("setup_need") == "settlement":
                vid = _pick_settlement(g, pid)
                seq[pid] += 1
                await _send_cmd(ws, match_id, seq[pid], {"type": "place_settlement", "vid": vid, "setup": True})
            else:
                anchor = int(state.get("setup_anchor_vid"))
                e = _pick_road(g, pid, anchor)
                seq[pid] += 1
                await _send_cmd(ws, match_id, seq[pid], {"type": "place_road", "eid": [e[0], e[1]], "setup": True})

            ms1 = await _recv_type(host, "match_state")
            ms2 = await _recv_type(conns[1], "match_state")
            if ms1["tick"] != ms2["tick"]:
                raise AssertionError("tick mismatch during setup")
            if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
                raise AssertionError("state hash mismatch during setup")
            state = ms1.get("state", {})
            _apply_snapshot(g, state)

        current_pid = int(state.get("turn", 0))
        ws = clients[current_pid]
        seq[current_pid] += 1
        await _send_cmd(ws, match_id, seq[current_pid], {"type": "roll"})
        ms1 = await _recv_type(host, "match_state")
        ms2 = await _recv_type(conns[1], "match_state")
        if ms1["tick"] != ms2["tick"]:
            raise AssertionError("tick mismatch after roll")
        if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
            raise AssertionError("state hash mismatch after roll")
        state = ms1.get("state", {})

        if state.get("pending_action") == "discard":
            required = state.get("discard_required", {})
            for pid_key, need in required.items():
                pid = int(pid_key)
                seq[pid] += 1
                plan = _plan_discard_from_state(state, pid, int(need))
                await _send_cmd(clients[pid], match_id, seq[pid], {"type": "discard", "discards": plan})
                ms1 = await _recv_type(host, "match_state")
                ms2 = await _recv_type(conns[1], "match_state")
                if ms1["tick"] != ms2["tick"]:
                    raise AssertionError("tick mismatch after discard")
                if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
                    raise AssertionError("state hash mismatch after discard")
                state = ms1.get("state", {})

        if state.get("pending_action") == "robber_move":
            tile = int(state.get("robber_tile", 0))
            new_tile = tile + 1 if tile + 1 < len(state.get("tiles", [])) else max(0, tile - 1)
            seq[current_pid] += 1
            await _send_cmd(ws, match_id, seq[current_pid], {"type": "move_robber", "tile": new_tile})
            ms1 = await _recv_type(host, "match_state")
            ms2 = await _recv_type(conns[1], "match_state")
            if ms1["tick"] != ms2["tick"]:
                raise AssertionError("tick mismatch after robber move")
            if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
                raise AssertionError("state hash mismatch after robber move")
            state = ms1.get("state", {})

        # ensure resources for trade offer
        other_pid = 1 - current_pid
        seq[current_pid] += 1
        await _send_cmd(clients[current_pid], match_id, seq[current_pid], {"type": "grant_resources", "res": {"wood": 1}})
        ms1 = await _recv_type(host, "match_state")
        ms2 = await _recv_type(conns[1], "match_state")
        if ms1["tick"] != ms2["tick"]:
            raise AssertionError("tick mismatch after grant_resources (current)")
        state = ms1.get("state", {})

        if other_pid in clients:
            seq[other_pid] += 1
            await _send_cmd(clients[other_pid], match_id, seq[other_pid], {"type": "grant_resources", "res": {"brick": 1}})
            ms1 = await _recv_type(host, "match_state")
            ms2 = await _recv_type(conns[1], "match_state")
            if ms1["tick"] != ms2["tick"]:
                raise AssertionError("tick mismatch after grant_resources (other)")
            state = ms1.get("state", {})

        # trade offer flow
        seq[current_pid] += 1
        await _send_cmd(ws, match_id, seq[current_pid], {"type": "trade_offer_create", "give": {"wood": 1}, "get": {"brick": 1}, "to_pid": other_pid})
        ms1 = await _recv_type(host, "match_state")
        ms2 = await _recv_type(conns[1], "match_state")
        if ms1["tick"] != ms2["tick"]:
            raise AssertionError("tick mismatch after trade_offer_create")
        state = ms1.get("state", {})
        offer_id = int(state.get("trade_offers", [{}])[-1].get("offer_id", 0))

        if other_pid in clients:
            seq[other_pid] += 1
            await _send_cmd(clients[other_pid], match_id, seq[other_pid], {"type": "trade_offer_accept", "offer_id": offer_id})
            ms1 = await _recv_type(host, "match_state")
            ms2 = await _recv_type(conns[1], "match_state")
            if ms1["tick"] != ms2["tick"]:
                raise AssertionError("tick mismatch after trade_offer_accept")
            if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
                raise AssertionError("state hash mismatch after trade_offer_accept")
            state = ms1.get("state", {})

        seq[current_pid] += 1
        await _send_cmd(ws, match_id, seq[current_pid], {"type": "end_turn"})
        ms1 = await _recv_type(host, "match_state")
        ms2 = await _recv_type(conns[1], "match_state")
        if ms1["tick"] != ms2["tick"]:
            raise AssertionError("tick mismatch after end_turn")
        if _state_hash(ms1["state"]) != _state_hash(ms2["state"]):
            raise AssertionError("state hash mismatch after end_turn")
    finally:
        for ws in conns:
            await ws.close()


async def _run(port: int):
    await _run_clients(port, max_players=2)
    await _run_clients(port, max_players=5)


def main() -> int:
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        asyncio.run(_run(port))
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    print("PASS: multiplayer smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
