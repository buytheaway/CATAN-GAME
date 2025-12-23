from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
import random
import math

RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"]
TERRAINS  = ["forest", "hill", "pasture", "field", "mountain", "desert"]

TERRAIN_TO_RESOURCE = {
    "forest": "wood",
    "hill": "brick",
    "pasture": "sheep",
    "field": "wheat",
    "mountain": "ore",
    "desert": None,
}

# Standard-ish number tokens (without 7), desert gets None.
STD_NUMBERS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]

def pip_count(n: Optional[int]) -> int:
    # heuristic pips: 6/8=5, 5/9=4, 4/10=3, 3/11=2, 2/12=1
    if n is None:
        return 0
    return {6:5, 8:5, 5:4, 9:4, 4:3, 10:3, 3:2, 11:2, 2:1, 12:1}.get(n, 0)

@dataclass(frozen=True)
class Vertex:
    vid: int
    x: float
    y: float

@dataclass(frozen=True)
class Edge:
    eid: int
    a: int  # vertex id
    b: int  # vertex id

@dataclass
class Tile:
    tid: int
    q: int
    r: int
    terrain: str
    number: Optional[int]
    center: Tuple[float, float]
    corners: List[int]  # vertex ids

@dataclass
class Player:
    pid: int
    name: str
    is_bot: bool = False
    resources: Dict[str, int] = field(default_factory=lambda: {k:0 for k in RESOURCES})
    settlements: Set[int] = field(default_factory=set)  # vertex ids
    cities: Set[int] = field(default_factory=set)       # vertex ids
    roads: Set[int] = field(default_factory=set)        # edge ids

    @property
    def vp(self) -> int:
        return len(self.settlements) + 2 * len(self.cities)

@dataclass
class Board:
    tiles: List[Tile]
    vertices: Dict[int, Vertex]
    edges: Dict[int, Edge]
    vertex_tiles: Dict[int, List[int]]          # vid -> [tid...]
    vertex_neighbors: Dict[int, Set[int]]       # vid -> set(vid)
    edge_by_verts: Dict[Tuple[int,int], int]    # (min,max) -> eid

@dataclass
class Game:
    board: Board
    players: List[Player]
    current: int = 0
    rolled: bool = False
    last_roll: Optional[int] = None
    log: List[str] = field(default_factory=list)

    # setup script: snake draft for 2 players
    setup_seq: List[Tuple[int, str]] = field(default_factory=list)  # (pid, "settlement"/"road")
    setup_i: int = 0
    setup_last_settlement_vid: Optional[int] = None
    settlements_placed: Dict[int, int] = field(default_factory=dict)

    def phase(self) -> str:
        if self.setup_i < len(self.setup_seq):
            pid, act = self.setup_seq[self.setup_i]
            return f"setup:{pid}:{act}"
        return "main"

    def cur_player(self) -> Player:
        return self.players[self.current]

    def is_human_turn(self) -> bool:
        return not self.cur_player().is_bot

    def setup_action(self) -> Optional[Tuple[int, str]]:
        if self.setup_i < len(self.setup_seq):
            return self.setup_seq[self.setup_i]
        return None

    def can_roll(self) -> bool:
        return self.phase() == "main" and (not self.rolled)

    def roll_dice(self) -> int:
        if not self.can_roll():
            raise RuntimeError("Cannot roll now")
        a = random.randint(1,6)
        b = random.randint(1,6)
        self.last_roll = a+b
        self.rolled = True
        self.log.append(f"[DICE] {self.cur_player().name} rolled {self.last_roll}")
        self._distribute(self.last_roll)
        return self.last_roll

    def end_turn(self) -> None:
        if self.phase() != "main":
            return
        self.rolled = False
        self.last_roll = None
        self.current = (self.current + 1) % len(self.players)
        self.log.append(f"[TURN] Now: {self.cur_player().name}")

    # ===== build rules =====
    def cost_road(self) -> Dict[str,int]:
        return {"wood":1, "brick":1}
    def cost_settlement(self) -> Dict[str,int]:
        return {"wood":1, "brick":1, "sheep":1, "wheat":1}
    def cost_city(self) -> Dict[str,int]:
        return {"wheat":2, "ore":3}

    def has_cost(self, pid: int, cost: Dict[str,int]) -> bool:
        p = self.players[pid]
        return all(p.resources.get(k,0) >= v for k,v in cost.items())

    def pay_cost(self, pid: int, cost: Dict[str,int]) -> None:
        p = self.players[pid]
        for k,v in cost.items():
            p.resources[k] -= v

    def is_vertex_occupied(self, vid: int) -> bool:
        for p in self.players:
            if vid in p.settlements or vid in p.cities:
                return True
        return False

    def owner_of_vertex(self, vid: int) -> Optional[int]:
        for p in self.players:
            if vid in p.settlements or vid in p.cities:
                return p.pid
        return None

    def is_edge_occupied(self, eid: int) -> bool:
        for p in self.players:
            if eid in p.roads:
                return True
        return False

    def legal_settlement_vertices(self, pid: int) -> Set[int]:
        # distance rule: no adjacent settlement/city
        legal: Set[int] = set()
        for vid in self.board.vertices.keys():
            if self.is_vertex_occupied(vid):
                continue
            # adjacency ban
            ok = True
            for nb in self.board.vertex_neighbors[vid]:
                if self.is_vertex_occupied(nb):
                    ok = False
                    break
            if not ok:
                continue

            ph = self.phase()
            if ph.startswith("setup"):
                # setup: anywhere (distance rule already applied)
                legal.add(vid)
            else:
                # main: must connect to your road
                if self._is_connected_to_player_road(pid, vid):
                    legal.add(vid)
        return legal

    def legal_city_vertices(self, pid: int) -> Set[int]:
        p = self.players[pid]
        return set(p.settlements)

    def legal_road_edges(self, pid: int) -> Set[int]:
        legal: Set[int] = set()
        for eid, e in self.board.edges.items():
            if self.is_edge_occupied(eid):
                continue
            ph = self.phase()
            if ph.startswith("setup"):
                # in setup, must be adjacent to the just placed settlement
                if self.setup_last_settlement_vid is None:
                    continue
                if e.a == self.setup_last_settlement_vid or e.b == self.setup_last_settlement_vid:
                    legal.add(eid)
            else:
                # in main: must connect to player's network
                if self._edge_connects_to_player(pid, eid):
                    legal.add(eid)
        return legal

    def _is_connected_to_player_road(self, pid: int, vid: int) -> bool:
        p = self.players[pid]
        for eid in p.roads:
            e = self.board.edges[eid]
            if e.a == vid or e.b == vid:
                return True
        return False

    def _edge_connects_to_player(self, pid: int, eid: int) -> bool:
        p = self.players[pid]
        e = self.board.edges[eid]
        # adjacent to player's settlement/city
        if e.a in p.settlements or e.a in p.cities or e.b in p.settlements or e.b in p.cities:
            return True
        # adjacent to player's road (share a vertex)
        for reid in p.roads:
            r = self.board.edges[reid]
            if r.a in (e.a, e.b) or r.b in (e.a, e.b):
                return True
        return False

    # ===== apply actions =====
    def place_settlement(self, pid: int, vid: int) -> None:
        act = self.setup_action()
        if act:
            need_pid, need_act = act
            if pid != need_pid or need_act != "settlement":
                raise RuntimeError("Not your setup settlement step")

        if vid not in self.legal_settlement_vertices(pid):
            raise RuntimeError("Illegal settlement")

        if self.phase() == "main":
            if not self.rolled:
                raise RuntimeError("Roll first")
            if not self.has_cost(pid, self.cost_settlement()):
                raise RuntimeError("Not enough resources")
            self.pay_cost(pid, self.cost_settlement())

        p = self.players[pid]
        p.settlements.add(vid)
        self.setup_last_settlement_vid = vid
        self.log.append(f"[BUILD] {p.name} built Settlement")

        # setup: grant initial resources only for the SECOND settlement (standard)
        if self.phase().startswith("setup"):
            self.settlements_placed[pid] = self.settlements_placed.get(pid, 0) + 1
            if self.settlements_placed[pid] == 2:
                self._grant_initial_resources_for_vertex(pid, vid)

            self.setup_i += 1
            # next current player is driven by setup sequence
            if self.setup_i < len(self.setup_seq):
                self.current = self.setup_seq[self.setup_i][0]

    def place_city(self, pid: int, vid: int) -> None:
        if self.phase() != "main":
            raise RuntimeError("Cities only in main")
        if not self.rolled:
            raise RuntimeError("Roll first")
        p = self.players[pid]
        if vid not in p.settlements:
            raise RuntimeError("Need your settlement to upgrade")
        if not self.has_cost(pid, self.cost_city()):
            raise RuntimeError("Not enough resources")
        self.pay_cost(pid, self.cost_city())
        p.settlements.remove(vid)
        p.cities.add(vid)
        self.log.append(f"[BUILD] {p.name} upgraded to City")

    def place_road(self, pid: int, eid: int) -> None:
        act = self.setup_action()
        if act:
            need_pid, need_act = act
            if pid != need_pid or need_act != "road":
                raise RuntimeError("Not your setup road step")

        if eid not in self.legal_road_edges(pid):
            raise RuntimeError("Illegal road")

        if self.phase() == "main":
            if not self.rolled:
                raise RuntimeError("Roll first")
            if not self.has_cost(pid, self.cost_road()):
                raise RuntimeError("Not enough resources")
            self.pay_cost(pid, self.cost_road())

        p = self.players[pid]
        p.roads.add(eid)
        self.log.append(f"[BUILD] {p.name} built Road")

        if self.phase().startswith("setup"):
            self.setup_last_settlement_vid = None
            self.setup_i += 1
            if self.setup_i < len(self.setup_seq):
                self.current = self.setup_seq[self.setup_i][0]

    # ===== resources =====
    def _distribute(self, roll: int) -> None:
        if roll == 7:
            self.log.append("[INFO] 7 rolled (robber not implemented in this prototype)")
            return
        for t in self.board.tiles:
            if t.number != roll:
                continue
            res = TERRAIN_TO_RESOURCE.get(t.terrain)
            if res is None:
                continue
            for vid in t.corners:
                owner = self.owner_of_vertex(vid)
                if owner is None:
                    continue
                p = self.players[owner]
                amount = 2 if vid in p.cities else 1
                p.resources[res] += amount
        self.log.append("[INFO] Resources distributed")

    def _grant_initial_resources_for_vertex(self, pid: int, vid: int) -> None:
        # take 1 resource from each adjacent non-desert tile
        tids = self.board.vertex_tiles.get(vid, [])
        p = self.players[pid]
        for tid in tids:
            t = self.board.tiles[tid]
            res = TERRAIN_TO_RESOURCE.get(t.terrain)
            if res is None:
                continue
            p.resources[res] += 1
        self.log.append(f"[SETUP] {p.name} gained initial resources")

def generate_board(seed: Optional[int] = None, hex_size: float = 62.0) -> Board:
    rnd = random.Random(seed)

    # axial coords radius=2 => 19 tiles
    coords = []
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if abs(s) <= 2:
                coords.append((q, r))
    rnd.shuffle(coords)

    terrains = (
        ["forest"] * 4 +
        ["hill"] * 3 +
        ["pasture"] * 4 +
        ["field"] * 4 +
        ["mountain"] * 3 +
        ["desert"] * 1
    )
    rnd.shuffle(terrains)

    numbers = STD_NUMBERS[:]
    rnd.shuffle(numbers)

    def axial_to_pixel(q: int, r: int) -> Tuple[float,float]:
        x = hex_size * math.sqrt(3) * (q + r/2.0)
        y = hex_size * 1.5 * r
        return (x, y)

    def hex_corners(cx: float, cy: float) -> List[Tuple[float,float]]:
        pts = []
        for i in range(6):
            ang = math.radians(60*i - 30)  # pointy
            pts.append((cx + hex_size * math.cos(ang), cy + hex_size * math.sin(ang)))
        return pts

    # vertex pool with stable keys
    vmap: Dict[Tuple[int,int], int] = {}
    vertices: Dict[int, Vertex] = {}
    def vid_for_xy(x: float, y: float) -> int:
        key = (int(round(x*1000)), int(round(y*1000)))
        if key in vmap:
            return vmap[key]
        vid = len(vmap)
        vmap[key] = vid
        vertices[vid] = Vertex(vid, x, y)
        return vid

    tiles: List[Tile] = []
    vertex_tiles: Dict[int, List[int]] = {}

    num_i = 0
    for tid, (q, r) in enumerate(coords):
        terrain = terrains[tid]
        number = None
        if terrain != "desert":
            number = numbers[num_i]
            num_i += 1

        cx, cy = axial_to_pixel(q, r)
        corners_xy = hex_corners(cx, cy)
        corner_vids = [vid_for_xy(x, y) for (x, y) in corners_xy]

        tiles.append(Tile(
            tid=tid, q=q, r=r, terrain=terrain, number=number,
            center=(cx, cy), corners=corner_vids
        ))

        for vid in corner_vids:
            vertex_tiles.setdefault(vid, []).append(tid)

    # edges
    edge_by_verts: Dict[Tuple[int,int], int] = {}
    edges: Dict[int, Edge] = {}
    def add_edge(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key in edge_by_verts:
            return edge_by_verts[key]
        eid = len(edge_by_verts)
        edge_by_verts[key] = eid
        edges[eid] = Edge(eid, key[0], key[1])
        return eid

    for t in tiles:
        vs = t.corners
        for i in range(6):
            add_edge(vs[i], vs[(i+1)%6])

    # neighbors
    vertex_neighbors: Dict[int, Set[int]] = {vid:set() for vid in vertices.keys()}
    for e in edges.values():
        vertex_neighbors[e.a].add(e.b)
        vertex_neighbors[e.b].add(e.a)

    return Board(
        tiles=tiles,
        vertices=vertices,
        edges=edges,
        vertex_tiles=vertex_tiles,
        vertex_neighbors=vertex_neighbors,
        edge_by_verts=edge_by_verts,
    )

def new_game(seed: Optional[int] = None) -> Game:
    b = generate_board(seed=seed)
    players = [
        Player(pid=0, name="You", is_bot=False),
        Player(pid=1, name="Bot", is_bot=True),
    ]
    g = Game(board=b, players=players)
    g.setup_seq = [
        (0, "settlement"), (0, "road"),
        (1, "settlement"), (1, "road"),
        (1, "settlement"), (1, "road"),
        (0, "settlement"), (0, "road"),
    ]
    g.settlements_placed = {0:0, 1:0}
    g.current = g.setup_seq[0][0]
    g.log.append("[SYS] New game started (Base game prototype)")
    return g