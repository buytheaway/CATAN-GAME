from __future__ import annotations
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio, json, math, random, secrets
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

app = FastAPI(title="CATAN-GAME Server (v3)")

PLAYER_COLORS = ["#ef4444", "#22c55e", "#3b82f6", "#f59e0b"]  # red/green/blue/yellow

RESOURCES_BASE = (
    ["wood"]*4 + ["brick"]*3 + ["sheep"]*4 + ["wheat"]*4 + ["ore"]*3 + ["desert"]*1
)
TOKENS_BASE = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]  # 18 (no token for desert)

def _axial_hexes(radius: int = 2) -> List[Tuple[int,int]]:
    coords = []
    for q in range(-radius, radius+1):
        for r in range(-radius, radius+1):
            if abs(q + r) <= radius:
                coords.append((q, r))
    # stable order for deterministic-ish layouts
    coords.sort(key=lambda x: (x[1], x[0]))
    return coords

def _hex_to_pixel(q: int, r: int, size: float) -> Tuple[float,float]:
    # pointy-top axial -> pixel
    x = size * math.sqrt(3) * (q + r/2)
    y = size * 1.5 * r
    return x, y

def _hex_corners(cx: float, cy: float, size: float) -> List[Tuple[float,float]]:
    pts = []
    for k in range(6):
        ang = math.radians(60*k - 30)
        pts.append((cx + size*math.cos(ang), cy + size*math.sin(ang)))
    return pts

def _round_pt(x: float, y: float, nd: int = 2) -> Tuple[float,float]:
    return (round(x, nd), round(y, nd))

@dataclass
class Board:
    hex_size: int = 70
    hexes: List[dict] = field(default_factory=list)          # render
    nodes: List[dict] = field(default_factory=list)          # render
    edges: List[dict] = field(default_factory=list)          # render

    # internal mappings
    node_hexes: Dict[str, List[str]] = field(default_factory=dict)   # node -> [hex_id...]
    edge_nodes: Dict[str, Tuple[str,str]] = field(default_factory=dict) # edge -> (n1,n2)

def generate_board(seed: Optional[int] = None) -> Board:
    rnd = random.Random(seed)
    size = 70

    axial = _axial_hexes(2)  # 19 hexes
    resources = RESOURCES_BASE[:]
    rnd.shuffle(resources)

    tokens = TOKENS_BASE[:]
    rnd.shuffle(tokens)
    tok_i = 0

    b = Board(hex_size=size)

    # place hexes
    for i, (q,r) in enumerate(axial):
        cx, cy = _hex_to_pixel(q, r, size)
        res = resources[i]
        num = None
        if res != "desert":
            num = tokens[tok_i]
            tok_i += 1

        b.hexes.append({
            "id": f"H{i}",
            "cx": cx, "cy": cy,
            "res": res,
            "num": num
        })

    # build shared nodes / edges
    node_by_pt: Dict[Tuple[float,float], str] = {}
    nodes_xy: Dict[str, Tuple[float,float]] = {}
    edge_by_pair: Dict[Tuple[str,str], str] = {}

    def get_node_id(x: float, y: float) -> str:
        pt = _round_pt(x,y,2)
        if pt in node_by_pt:
            return node_by_pt[pt]
        nid = f"N{len(node_by_pt)}"
        node_by_pt[pt] = nid
        nodes_xy[nid] = pt
        b.node_hexes[nid] = []
        return nid

    for hx in b.hexes:
        hid = hx["id"]
        corners = _hex_corners(hx["cx"], hx["cy"], size)
        corner_ids = [get_node_id(x,y) for (x,y) in corners]

        # node adjacency to hex
        for nid in corner_ids:
            b.node_hexes[nid].append(hid)

        # edges around hex (dedup)
        for k in range(6):
            a = corner_ids[k]
            c = corner_ids[(k+1)%6]
            n1, n2 = (a, c) if a < c else (c, a)
            pair = (n1, n2)
            if pair not in edge_by_pair:
                eid = f"E{len(edge_by_pair)}"
                edge_by_pair[pair] = eid
                b.edge_nodes[eid] = (n1, n2)

    # export nodes list
    for nid, (x,y) in nodes_xy.items():
        b.nodes.append({"id": nid, "x": x, "y": y})

    # export edges list with endpoints coords (for rendering + click picking)
    for (n1,n2), eid in edge_by_pair.items():
        x1,y1 = nodes_xy[n1]
        x2,y2 = nodes_xy[n2]
        b.edges.append({"id": eid, "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    return b

@dataclass
class Player:
    id: str
    name: str
    color: str
    vp: int = 0
    res: Dict[str,int] = field(default_factory=lambda: {"wood":0,"brick":0,"sheep":0,"wheat":0,"ore":0})

@dataclass
class Room:
    id: str
    board: Board = field(default_factory=generate_board)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    conns: Dict[str, WebSocket] = field(default_factory=dict)     # pid -> ws
    players: Dict[str, Player] = field(default_factory=dict)

    phase: str = "lobby"   # lobby|setup|main|finished
    current: Optional[str] = None
    rolled: bool = False
    last_roll: Optional[int] = None

    setup_step: str = "settlement"  # settlement|road
    setup_order: List[str] = field(default_factory=list)
    setup_index: int = 0
    setup_last_settlement_node: Dict[str, str] = field(default_factory=dict)

    pieces: Dict[str, Dict[str, dict]] = field(default_factory=lambda: {"settlements": {}, "roads": {}})
    offers: List[dict] = field(default_factory=list)

    def to_public_state(self) -> dict:
        return {
            "phase": self.phase,
            "current": self.current,
            "rolled": self.rolled,
            "last_roll": self.last_roll,
            "players": {
                pid: {"name": p.name, "vp": p.vp, "res": p.res}
                for pid, p in self.players.items()
            },
            "pieces": self.pieces,
            "offers": self.offers,
        }

    def board_payload(self) -> dict:
        return {
            "hex_size": self.board.hex_size,
            "hexes": self.board.hexes,
            "nodes": self.board.nodes,
            "edges": self.board.edges,
        }

    async def send(self, pid: str, payload: dict):
        ws = self.conns.get(pid)
        if not ws:
            return
        await ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def broadcast(self, payload: dict):
        dead = []
        for pid, ws in self.conns.items():
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(pid)
        for pid in dead:
            self.conns.pop(pid, None)

    async def broadcast_state(self):
        await self.broadcast({"t": "state", "board": self.board_payload(), "state": self.to_public_state()})

    def _next_player(self, pid: str) -> Optional[str]:
        ids = list(self.players.keys())
        if not ids:
            return None
        if pid not in ids:
            return ids[0]
        i = ids.index(pid)
        return ids[(i+1) % len(ids)]

rooms: Dict[str, Room] = {}

def get_room(room_id: str) -> Room:
    if room_id not in rooms:
        # fixed seed per room -> same board for everyone inside room
        seed = int.from_bytes(room_id.encode("utf-8"), "little", signed=False) % (2**31-1)
        rooms[room_id] = Room(id=room_id, board=generate_board(seed))
    return rooms[room_id]

def roll_2d6() -> int:
    return random.randint(1,6) + random.randint(1,6)

def hex_res_by_id(room: Room) -> Dict[str,str]:
    return {h["id"]: h["res"] for h in room.board.hexes}

def hex_num_by_id(room: Room) -> Dict[str,Optional[int]]:
    return {h["id"]: h.get("num") for h in room.board.hexes}

def grant_resources(room: Room, rolled: int):
    res_of = hex_res_by_id(room)
    num_of = hex_num_by_id(room)
    # for each settlement node -> adjacent hexes
    for node_id, s in room.pieces["settlements"].items():
        pid = s["player"]
        p = room.players.get(pid)
        if not p:
            continue
        for hid in room.board.node_hexes.get(node_id, []):
            if num_of.get(hid) == rolled:
                res = res_of.get(hid)
                if res and res != "desert":
                    p.res[res] += 1

def edge_adjacent_to_node(room: Room, edge_id: str, node_id: str) -> bool:
    a,b = room.board.edge_nodes.get(edge_id, ("",""))
    return node_id in (a,b)

@app.get("/")
def root():
    return {"ok": True, "ws": "/ws/{room}", "protocol": "v3"}

@app.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str):
    await websocket.accept()
    room = get_room(room_id)

    pid = None
    try:
        # expect join
        raw = await websocket.receive_text()
        try:
            msg = json.loads(raw)
        except Exception:
            msg = {"t": "join", "name": "Player"}

        if (msg.get("t") or msg.get("type")) != "join":
            # allow clients that didn't send join first
            name = msg.get("name") or "Player"
        else:
            name = msg.get("name") or "Player"

        async with room.lock:
            pid = secrets.token_hex(4)
            color = PLAYER_COLORS[len(room.players) % len(PLAYER_COLORS)]
            room.players[pid] = Player(id=pid, name=name, color=color)
            room.conns[pid] = websocket

            if room.current is None and room.phase == "lobby":
                room.current = pid

            # hello to this client
            await room.send(pid, {"t": "hello", "you": pid, "color": color})

            # broadcast state to everyone
            await room.broadcast_state()

        # main loop
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"t": "cmd", "cmd": raw.strip()}

            t = msg.get("t") or msg.get("type") or "cmd"

            async with room.lock:
                if t == "chat":
                    text = (msg.get("text") or "").strip()
                    if text:
                        await room.broadcast({"t": "chat", "from": room.players[pid].name, "text": text})
                    continue

                if t == "trade_offer":
                    give = (msg.get("give") or "").strip()
                    get = (msg.get("get") or "").strip()
                    to_name = (msg.get("to") or "").strip()
                    offer = {
                        "id": secrets.token_hex(3),
                        "from": pid,
                        "from_name": room.players[pid].name,
                        "to_name": to_name or "*",
                        "give": give,
                        "get": get,
                        "status": "open",
                    }
                    room.offers.append(offer)
                    await room.broadcast_state()
                    continue

                if t == "cmd":
                    cmd = (msg.get("cmd") or "").strip().lower()

                    # --- lobby/start ---
                    if cmd == "start" and room.phase == "lobby":
                        room.phase = "setup"
                        room.setup_order = list(room.players.keys())
                        room.setup_index = 0
                        room.setup_step = "settlement"
                        room.current = room.setup_order[0] if room.setup_order else None
                        room.rolled = False
                        room.last_roll = None
                        await room.broadcast_state()
                        continue

                    # --- setup placement ---
                    if room.phase == "setup":
                        if pid != room.current:
                            continue

                        if cmd == "place_settlement":
                            node = msg.get("node")
                            if room.setup_step != "settlement" or not node:
                                continue
                            if node in room.pieces["settlements"]:
                                continue
                            # place
                            room.pieces["settlements"][node] = {"player": pid, "color": room.players[pid].color}
                            room.players[pid].vp += 1
                            room.setup_last_settlement_node[pid] = node
                            room.setup_step = "road"
                            await room.broadcast_state()
                            continue

                        if cmd == "place_road":
                            edge = msg.get("edge")
                            if room.setup_step != "road" or not edge:
                                continue
                            if edge in room.pieces["roads"]:
                                continue
                            last_node = room.setup_last_settlement_node.get(pid)
                            if not last_node or not edge_adjacent_to_node(room, edge, last_node):
                                continue
                            room.pieces["roads"][edge] = {"player": pid, "color": room.players[pid].color}

                            # next player
                            room.setup_step = "settlement"
                            room.setup_index += 1
                            if room.setup_index >= len(room.setup_order):
                                room.phase = "main"
                                room.current = room.setup_order[0] if room.setup_order else None
                                room.rolled = False
                                room.last_roll = None
                            else:
                                room.current = room.setup_order[room.setup_index]
                            await room.broadcast_state()
                            continue

                        continue  # ignore other commands in setup

                    # --- main phase ---
                    if room.phase == "main":
                        if cmd == "roll":
                            if pid != room.current or room.rolled:
                                continue
                            r = roll_2d6()
                            room.last_roll = r
                            room.rolled = True
                            grant_resources(room, r)
                            await room.broadcast_state()
                            continue

                        if cmd == "end":
                            if pid != room.current:
                                continue
                            room.current = room._next_player(room.current)
                            room.rolled = False
                            room.last_roll = None
                            await room.broadcast_state()
                            continue

                        if cmd == "build_settlement":
                            node = msg.get("node")
                            if pid != room.current or not node:
                                continue
                            if node in room.pieces["settlements"]:
                                continue
                            # cost: wood+brick+sheep+wheat
                            p = room.players[pid]
                            if p.res["wood"]<1 or p.res["brick"]<1 or p.res["sheep"]<1 or p.res["wheat"]<1:
                                continue
                            p.res["wood"]-=1; p.res["brick"]-=1; p.res["sheep"]-=1; p.res["wheat"]-=1
                            room.pieces["settlements"][node] = {"player": pid, "color": p.color}
                            p.vp += 1
                            await room.broadcast_state()
                            continue

                        if cmd == "build_road":
                            edge = msg.get("edge")
                            if pid != room.current or not edge:
                                continue
                            if edge in room.pieces["roads"]:
                                continue
                            # cost: wood+brick
                            p = room.players[pid]
                            if p.res["wood"]<1 or p.res["brick"]<1:
                                continue
                            p.res["wood"]-=1; p.res["brick"]-=1
                            room.pieces["roads"][edge] = {"player": pid, "color": p.color}
                            await room.broadcast_state()
                            continue

    except WebSocketDisconnect:
        pass
    except Exception:
        # keep server alive on unexpected errors
        pass
    finally:
        if pid:
            async with room.lock:
                room.conns.pop(pid, None)
                room.players.pop(pid, None)
                if room.current == pid:
                    room.current = next(iter(room.players.keys()), None)
                # if empty room -> keep or cleanup (keep for simplicity)
                await room.broadcast_state()
