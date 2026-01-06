import asyncio
import json
import socket
import threading
import time

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


def test_multiplayer_basic():
    port = _find_free_port()
    server, thread = _start_server(port)
    try:
        asyncio.run(_run_clients(port))
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def _run_clients(port: int):
    url = f"ws://127.0.0.1:{port}/ws"
    async with websockets.connect(url) as ws1, websockets.connect(url) as ws2:
        await _send(ws1, {"type": "hello", "version": net_protocol.VERSION, "name": "Alice"})
        await _recv_type(ws1, "hello")
        await _send(ws2, {"type": "hello", "version": net_protocol.VERSION, "name": "Bob"})
        await _recv_type(ws2, "hello")

        await _send(ws1, {"type": "create_room", "name": "Alice", "max_players": 2, "ruleset": {"base": True, "max_players": 2}})
        room_state = await _recv_type(ws1, "room_state")
        room_code = room_state["room_code"]

        await _send(ws2, {"type": "join_room", "room_code": room_code, "name": "Bob"})
        await _recv_type(ws2, "room_state")
        await _recv_type(ws1, "room_state")

        await _send(ws1, {"type": "start_match"})
        ms1 = await _recv_type(ws1, "match_state")
        ms2 = await _recv_type(ws2, "match_state")
        match_id = int(ms1.get("match_id", 0))
        state = ms1.get("state", {})
        seed = int(ms1.get("seed", 0))
        g = build_game(seed=seed, max_players=2, size=float(state.get("size", 58.0)))
        _apply_snapshot(g, state)

        seq = {0: 0, 1: 0}
        clients = {0: ws1, 1: ws2}

        while state.get("phase") == "setup":
            pid = state["setup_order"][state["setup_idx"]]
            ws = clients[pid]
            if state.get("setup_need") == "settlement":
                vid = _pick_settlement(g, pid)
                seq[pid] += 1
                await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq[pid], "cmd": {"type": "place_settlement", "vid": vid, "setup": True}})
            else:
                anchor = int(state.get("setup_anchor_vid"))
                e = _pick_road(g, pid, anchor)
                seq[pid] += 1
                await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq[pid], "cmd": {"type": "place_road", "eid": [e[0], e[1]], "setup": True}})

            ms1 = await _recv_type(ws1, "match_state")
            ms2 = await _recv_type(ws2, "match_state")
            assert ms1["tick"] == ms2["tick"]
            state = ms1.get("state", {})
            _apply_snapshot(g, state)

        current_pid = int(state.get("turn", 0))
        ws = clients[current_pid]
        seq[current_pid] += 1
        await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq[current_pid], "cmd": {"type": "roll"}})
        ms1 = await _recv_type(ws1, "match_state")
        ms2 = await _recv_type(ws2, "match_state")
        assert ms1["tick"] == ms2["tick"]
        state = ms1.get("state", {})

        if state.get("pending_action") == "robber_move":
            tile = int(state.get("robber_tile", 0))
            new_tile = tile + 1 if tile + 1 < len(state.get("tiles", [])) else max(0, tile - 1)
            seq[current_pid] += 1
            await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq[current_pid], "cmd": {"type": "move_robber", "tile": new_tile}})
            ms1 = await _recv_type(ws1, "match_state")
            ms2 = await _recv_type(ws2, "match_state")
            assert ms1["tick"] == ms2["tick"]
            state = ms1.get("state", {})

        seq[current_pid] += 1
        await _send(ws, {"type": "cmd", "match_id": match_id, "seq": seq[current_pid], "cmd": {"type": "end_turn"}})
        ms1 = await _recv_type(ws1, "match_state")
        ms2 = await _recv_type(ws2, "match_state")
        assert ms1["tick"] == ms2["tick"]
