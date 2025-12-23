from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

Resource = str  # "wood" "brick" "wheat" "sheep" "ore"

COSTS = {
    "road": {"brick": 1, "wood": 1},
    "settlement": {"brick": 1, "wood": 1, "wheat": 1, "sheep": 1},
    "city": {"ore": 3, "wheat": 2},
    "dev": {"ore": 1, "wheat": 1, "sheep": 1},
}

# Classic 19-hex layout in axial coords
STANDARD_AXIAL = [
    (0, -2), (1, -2), (2, -2),
    (-1, -1), (0, -1), (1, -1), (2, -1),
    (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0),
    (-2, 1), (-1, 1), (0, 1), (1, 1),
    (-2, 2), (-1, 2), (0, 2),
]

AXIAL_DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

DEV_DECK = (
    ["knight"] * 14 +
    ["road_building"] * 2 +
    ["year_of_plenty"] * 2 +
    ["monopoly"] * 2 +
    ["victory_point"] * 5
)

MAX_ROADS = 15
MAX_SETTLEMENTS = 5
MAX_CITIES = 4

WIN_VP = 10


def axial_neighbors(q: int, r: int) -> List[Tuple[int, int]]:
    return [(q + dq, r + dr) for dq, dr in AXIAL_DIRS]


def axial_to_xy(q: int, r: int, size: float) -> Tuple[float, float]:
    # pointy-top
    x = size * math.sqrt(3) * (q + r / 2.0)
    y = size * 1.5 * r
    return x, y


def hex_corners(x: float, y: float, size: float) -> List[Tuple[float, float]]:
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        corners.append((x + size * math.cos(angle), y + size * math.sin(angle)))
    return corners


@dataclass
class HexTile:
    id: int
    q: int
    r: int
    terrain: str              # "wood" "brick" "wheat" "sheep" "ore" "desert"
    number: Optional[int]     # None for desert
    nodes: List[int] = field(default_factory=list)


@dataclass
class Board:
    seed: int
    hexes: Dict[int, HexTile]
    robber_hex: int
    node_neighbors: Dict[int, Set[int]]
    edge_nodes: Dict[int, Tuple[int, int]]
    node_hexes: Dict[int, Set[int]]
    ports_by_node: Dict[int, str]  # node -> "any3" or "<res>2"

    @staticmethod
    def generate(seed: int) -> "Board":
        rng = random.Random(seed)
        size = 10.0

        terrains = (["wood"] * 4 + ["wheat"] * 4 + ["sheep"] * 4 + ["brick"] * 3 + ["ore"] * 3 + ["desert"] * 1)
        numbers = [2, 12] + [3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11]

        axial_positions = list(STANDARD_AXIAL)
        rng.shuffle(axial_positions)

        def build_attempt() -> Tuple[Dict[int, HexTile], int]:
            rng.shuffle(terrains)
            terr = terrains[:]
            robber_hex = terr.index("desert")

            nums = numbers[:]
            rng.shuffle(nums)

            tiles: Dict[int, HexTile] = {}
            num_i = 0
            for i, (q, r) in enumerate(axial_positions):
                t = terr[i]
                if t == "desert":
                    n = None
                else:
                    n = nums[num_i]
                    num_i += 1
                tiles[i] = HexTile(id=i, q=q, r=r, terrain=t, number=n)
            return tiles, robber_hex

        def violates_6_8(tiles: Dict[int, HexTile]) -> bool:
            pos_to_id = {(t.q, t.r): t.id for t in tiles.values()}
            for t in tiles.values():
                if t.number not in (6, 8):
                    continue
                for nq, nr in axial_neighbors(t.q, t.r):
                    j = pos_to_id.get((nq, nr))
                    if j is None:
                        continue
                    if tiles[j].number in (6, 8):
                        return True
            return False

        tiles, robber_hex = build_attempt()
        for _ in range(250):
            if not violates_6_8(tiles):
                break
            tiles, robber_hex = build_attempt()

        # Build nodes/edges by corner unification
        node_id_by_xy: Dict[Tuple[float, float], int] = {}
        next_node_id = 0
        edge_id_by_pair: Dict[Tuple[int, int], int] = {}
        edge_nodes: Dict[int, Tuple[int, int]] = {}
        node_neighbors: Dict[int, Set[int]] = {}
        node_hexes: Dict[int, Set[int]] = {}

        def get_node_id(xy: Tuple[float, float]) -> int:
            nonlocal next_node_id
            key = (round(xy[0], 4), round(xy[1], 4))
            if key not in node_id_by_xy:
                node_id_by_xy[key] = next_node_id
                node_neighbors[next_node_id] = set()
                node_hexes[next_node_id] = set()
                next_node_id += 1
            return node_id_by_xy[key]

        def add_edge(a: int, b: int) -> int:
            x, y = (a, b) if a < b else (b, a)
            key = (x, y)
            if key not in edge_id_by_pair:
                eid = len(edge_id_by_pair)
                edge_id_by_pair[key] = eid
                edge_nodes[eid] = key
                node_neighbors[x].add(y)
                node_neighbors[y].add(x)
            return edge_id_by_pair[key]

        for tid, tile in tiles.items():
            cx, cy = axial_to_xy(tile.q, tile.r, size)
            corners = hex_corners(cx, cy, size)
            node_ids = [get_node_id(xy) for xy in corners]
            tile.nodes = node_ids
            for nid in node_ids:
                node_hexes[nid].add(tid)
            for i in range(6):
                add_edge(node_ids[i], node_ids[(i + 1) % 6])

        # Ports (simplified but playable):
        # Choose 9 boundary nodes: 4x "any3" + 5x resource-specific "res2"
        boundary_nodes = [nid for nid, hs in node_hexes.items() if len(hs) < 3]
        rng.shuffle(boundary_nodes)
        port_nodes = boundary_nodes[:9] if len(boundary_nodes) >= 9 else boundary_nodes[:]
        port_types = ["any3", "any3", "any3", "any3", "wood2", "brick2", "wheat2", "sheep2", "ore2"]
        rng.shuffle(port_types)

        ports_by_node: Dict[int, str] = {}
        for i, nid in enumerate(port_nodes):
            ports_by_node[nid] = port_types[i % len(port_types)]

        return Board(
            seed=seed,
            hexes=tiles,
            robber_hex=robber_hex,
            node_neighbors=node_neighbors,
            edge_nodes=edge_nodes,
            node_hexes=node_hexes,
            ports_by_node=ports_by_node,
        )


@dataclass
class Player:
    id: str
    name: str
    resources: Dict[Resource, int] = field(default_factory=lambda: {"wood": 0, "brick": 0, "wheat": 0, "sheep": 0, "ore": 0})

    # dev cards
    dev_hand: List[str] = field(default_factory=list)   # playable
    dev_new: List[str] = field(default_factory=list)    # bought this turn, not playable
    vp_cards: int = 0

    # awards
    played_knights: int = 0

    def res_total(self) -> int:
        return sum(self.resources.values())


@dataclass
class Game:
    board: Optional[Board] = None
    players: List[Player] = field(default_factory=list)

    phase: str = "lobby"  # lobby | setup | main | discard | robber | game_over
    turn: int = 0
    current_player: Optional[str] = None
    rolled: bool = False
    last_roll: Optional[int] = None

    setup_order: List[str] = field(default_factory=list)
    setup_index: int = 0

    buildings: Dict[int, Dict[str, str]] = field(default_factory=dict)  # node -> {"player":pid,"type":"settlement"/"city"}
    roads: Dict[int, str] = field(default_factory=dict)                # edge -> pid

    # per-player piece counts
    roads_built: Dict[str, int] = field(default_factory=dict)
    settlements_on_board: Dict[str, int] = field(default_factory=dict)
    cities_on_board: Dict[str, int] = field(default_factory=dict)

    # dev
    dev_deck: List[str] = field(default_factory=list)
    dev_played_this_turn: bool = False

    # robber discard
    discard_required: Dict[str, int] = field(default_factory=dict)
    discard_done: Set[str] = field(default_factory=set)

    # awards holders
    longest_road_holder: Optional[str] = None
    longest_road_len: int = 0
    largest_army_holder: Optional[str] = None
    largest_army_size: int = 0

    # end game
    winner: Optional[str] = None

    # ---------------- basic ----------------
    def add_player(self, pid: str, name: str) -> None:
        if self.phase != "lobby":
            raise ValueError("game already started (join only in lobby)")
        if any(p.id == pid for p in self.players):
            return
        if len(self.players) >= 4:
            raise ValueError("room full (max 4)")
        self.players.append(Player(id=pid, name=name))
        self.roads_built[pid] = 0
        self.settlements_on_board[pid] = 0
        self.cities_on_board[pid] = 0

    def player(self, pid: str) -> Player:
        for p in self.players:
            if p.id == pid:
                return p
        raise ValueError("unknown player")

    def _ids(self) -> List[str]:
        return [p.id for p in self.players]

    def start(self, seed: Optional[int] = None) -> None:
        if self.phase != "lobby":
            raise ValueError("already started")
        if len(self.players) < 2:
            raise ValueError("need at least 2 players")
        if seed is None:
            seed = random.randint(1, 2_000_000_000)
        self.board = Board.generate(seed)

        # init dev deck
        self.dev_deck = list(DEV_DECK)
        random.Random(seed ^ 0xA5A5A5).shuffle(self.dev_deck)
        self.dev_played_this_turn = False

        ids = self._ids()
        self.setup_order = ids + list(reversed(ids))
        self.setup_index = 0

        self.phase = "setup"
        self.current_player = self.setup_order[self.setup_index]
        self.turn = 0
        self.rolled = False
        self.last_roll = None
        self.winner = None

        self.longest_road_holder = None
        self.longest_road_len = 0
        self.largest_army_holder = None
        self.largest_army_size = 0

    # ---------------- VP calc ----------------
    def _base_vp_from_board(self, pid: str) -> int:
        vp = 0
        for _, b in self.buildings.items():
            if b["player"] != pid:
                continue
            if b["type"] == "settlement":
                vp += 1
            elif b["type"] == "city":
                vp += 2
        return vp

    def _award_vp(self, pid: str) -> int:
        vp = 0
        if self.longest_road_holder == pid:
            vp += 2
        if self.largest_army_holder == pid:
            vp += 2
        return vp

    def total_vp(self, pid: str) -> int:
        p = self.player(pid)
        return self._base_vp_from_board(pid) + p.vp_cards + self._award_vp(pid)

    def _check_win(self, pid: str) -> None:
        if self.phase == "game_over":
            return
        if self.total_vp(pid) >= WIN_VP:
            self.phase = "game_over"
            self.winner = pid

    # ---------------- public/private state ----------------
    def public_state(self) -> dict:
        b = self.board
        return {
            "phase": self.phase,
            "turn": self.turn,
            "current_player": self.current_player,
            "rolled": self.rolled,
            "last_roll": self.last_roll,
            "winner": self.winner,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "vp": self.total_vp(p.id),
                    "vp_base": self._base_vp_from_board(p.id),
                    "vp_cards": p.vp_cards,
                    "vp_awards": self._award_vp(p.id),
                    "res_count": p.res_total(),
                    "knights": p.played_knights,
                    "dev_hand": len(p.dev_hand),
                    "dev_new": len(p.dev_new),
                } for p in self.players
            ],
            "board": None if b is None else {
                "seed": b.seed,
                "robber_hex": b.robber_hex,
                "hexes": [{"id": h.id, "terrain": h.terrain, "number": h.number} for h in b.hexes.values()],
                "nodes_count": len(b.node_neighbors),
                "edges_count": len(b.edge_nodes),
                "ports_count": len(b.ports_by_node),
            },
            "buildings": self.buildings,
            "roads_count": len(self.roads),
            "dev_deck_left": len(self.dev_deck),
            "awards": {
                "longest_road_holder": self.longest_road_holder,
                "longest_road_len": self.longest_road_len,
                "largest_army_holder": self.largest_army_holder,
                "largest_army_size": self.largest_army_size,
            },
            "discard_required": self.discard_required,
            "discard_done": list(self.discard_done),
        }

    def private_state(self, pid: str) -> dict:
        if self.phase == "lobby":
            return {"you": pid, "resources": {"wood": 0, "brick": 0, "wheat": 0, "sheep": 0, "ore": 0}}
        p = self.player(pid)
        return {
            "you": pid,
            "resources": p.resources,
            "dev_hand": p.dev_hand,
            "dev_new": p.dev_new,
            "vp_cards": p.vp_cards,
        }

    # ---------------- hints ----------------
    def valid_initial_nodes(self) -> List[int]:
        if self.phase != "setup" or self.board is None:
            return []
        out = []
        for nid in self.board.node_neighbors.keys():
            if nid in self.buildings:
                continue
            if any(n2 in self.buildings for n2 in self.board.node_neighbors[nid]):
                continue
            out.append(nid)
        return out

    def valid_initial_edges(self, node_id: int) -> List[int]:
        if self.phase != "setup" or self.board is None:
            return []
        out = []
        for eid, (a, b) in self.board.edge_nodes.items():
            if eid in self.roads:
                continue
            if a == node_id or b == node_id:
                out.append(eid)
        return out

    def valid_build_edges(self, pid: str) -> List[int]:
        if self.phase != "main" or self.board is None:
            return []
        out = []
        for eid in self.board.edge_nodes.keys():
            if eid in self.roads:
                continue
            if self._road_connected(pid, eid):
                out.append(eid)
        return out

    def valid_build_nodes(self, pid: str) -> List[int]:
        if self.phase != "main" or self.board is None:
            return []
        out = []
        for nid in self.board.node_neighbors.keys():
            if nid in self.buildings:
                continue
            if any(n2 in self.buildings for n2 in self.board.node_neighbors[nid]):
                continue
            if self._node_connected(pid, nid):
                out.append(nid)
        return out

    def ports_for_player(self, pid: str) -> List[str]:
        if self.board is None:
            return []
        ports = []
        for nid, pt in self.board.ports_by_node.items():
            b = self.buildings.get(nid)
            if b and b["player"] == pid:
                ports.append(pt)
        return ports

    # ---------------- setup ----------------
    def place_initial(self, pid: str, node_id: int, edge_id: int) -> None:
        if self.phase != "setup" or self.board is None:
            raise ValueError("not in setup")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if node_id not in self.board.node_neighbors:
            raise ValueError("bad node")
        if edge_id not in self.board.edge_nodes:
            raise ValueError("bad edge")
        if node_id in self.buildings:
            raise ValueError("node occupied")
        if any(n2 in self.buildings for n2 in self.board.node_neighbors[node_id]):
            raise ValueError("too close to another settlement")

        a, b = self.board.edge_nodes[edge_id]
        if edge_id in self.roads:
            raise ValueError("edge occupied")
        if not (a == node_id or b == node_id):
            raise ValueError("edge must touch chosen node")

        # place settlement + road (free)
        self.buildings[node_id] = {"player": pid, "type": "settlement"}
        self.settlements_on_board[pid] += 1

        self.roads[edge_id] = pid
        self.roads_built[pid] += 1

        # second placement resources
        n = len(self.players)
        if self.setup_index >= n:
            self._grant_setup_resources(pid, node_id)

        self.setup_index += 1
        if self.setup_index >= len(self.setup_order):
            self.phase = "main"
            self.turn = 1
            self.current_player = self.players[0].id
            self.rolled = False
            self.last_roll = None
        else:
            self.current_player = self.setup_order[self.setup_index]

        self._update_longest_road()
        self._check_win(pid)

    def _grant_setup_resources(self, pid: str, node_id: int) -> None:
        assert self.board is not None
        pl = self.player(pid)
        for hid in self.board.node_hexes[node_id]:
            h = self.board.hexes[hid]
            if h.terrain == "desert":
                continue
            pl.resources[h.terrain] += 1

    # ---------------- main flow ----------------
    def roll_dice(self, pid: str) -> int:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if self.rolled:
            raise ValueError("already rolled")

        d = random.randint(1, 6) + random.randint(1, 6)
        self.last_roll = d
        self.rolled = True

        if d == 7:
            self.phase = "discard"
            self._begin_discard_phase()
        else:
            self._distribute_resources(d)

        return d

    def _begin_discard_phase(self) -> None:
        self.discard_required = {}
        self.discard_done = set()
        for p in self.players:
            total = p.res_total()
            if total > 7:
                self.discard_required[p.id] = total // 2

        if not self.discard_required:
            # no discards -> robber immediately
            self.phase = "robber"

    def discard(self, pid: str, give: Dict[Resource, int]) -> None:
        if self.phase != "discard":
            raise ValueError("not in discard phase")
        if pid not in self.discard_required:
            raise ValueError("you do not need to discard")
        if pid in self.discard_done:
            raise ValueError("already discarded")

        need = self.discard_required[pid]
        total = sum(int(v) for v in give.values())
        if total != need:
            raise ValueError(f"must discard exactly {need}")

        pl = self.player(pid)
        for r, c in give.items():
            c = int(c)
            if c < 0:
                raise ValueError("negative discard not allowed")
            if pl.resources.get(r, 0) < c:
                raise ValueError(f"not enough {r} to discard")

        for r, c in give.items():
            pl.resources[r] -= int(c)

        self.discard_done.add(pid)

        if len(self.discard_done) == len(self.discard_required):
            self.phase = "robber"

    def move_robber(self, pid: str, hex_id: int, victim: Optional[str] = None) -> None:
        if self.phase != "robber" or self.board is None:
            raise ValueError("not in robber")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if hex_id not in self.board.hexes:
            raise ValueError("bad hex")
        if hex_id == self.board.robber_hex:
            raise ValueError("robber already there")

        self.board.robber_hex = hex_id

        if victim:
            if victim == pid:
                raise ValueError("cannot steal from yourself")
            if not self._victim_adjacent_to_hex(victim, hex_id):
                raise ValueError("victim not adjacent to robber hex")
            self._steal_random(pid, victim)

        self.phase = "main"

    def _victim_adjacent_to_hex(self, victim_pid: str, hex_id: int) -> bool:
        assert self.board is not None
        h = self.board.hexes[hex_id]
        for nid in h.nodes:
            b = self.buildings.get(nid)
            if b and b["player"] == victim_pid:
                return True
        return False

    def _steal_random(self, thief: str, victim: str) -> None:
        v = self.player(victim)
        t = self.player(thief)
        pool = []
        for r, c in v.resources.items():
            pool += [r] * c
        if not pool:
            return
        r = random.choice(pool)
        v.resources[r] -= 1
        t.resources[r] += 1

    def end_turn(self, pid: str) -> None:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("must roll before ending")

        # unlock newly bought dev cards
        p = self.player(pid)
        if p.dev_new:
            p.dev_hand.extend(p.dev_new)
            p.dev_new = []
        self.dev_played_this_turn = False

        ids = self._ids()
        idx = ids.index(self.current_player)
        idx = (idx + 1) % len(ids)
        self.current_player = ids[idx]
        self.turn += 1
        self.rolled = False
        self.last_roll = None

    # ---------------- build ----------------
    def build_road(self, pid: str, edge_id: int, free: bool = False) -> None:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if edge_id not in self.board.edge_nodes:
            raise ValueError("bad edge")
        if edge_id in self.roads:
            raise ValueError("edge occupied")
        if self.roads_built.get(pid, 0) >= MAX_ROADS:
            raise ValueError("no roads left (limit reached)")
        if not self._road_connected(pid, edge_id):
            raise ValueError("road must connect to your network")

        if not free:
            self._pay(pid, COSTS["road"])

        self.roads[edge_id] = pid
        self.roads_built[pid] += 1

        self._update_longest_road()
        self._check_win(pid)

    def build_settlement(self, pid: str, node_id: int) -> None:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if node_id not in self.board.node_neighbors:
            raise ValueError("bad node")
        if node_id in self.buildings:
            raise ValueError("node occupied")
        if any(n2 in self.buildings for n2 in self.board.node_neighbors[node_id]):
            raise ValueError("too close to another settlement")
        if self.settlements_on_board.get(pid, 0) >= MAX_SETTLEMENTS:
            raise ValueError("no settlements left (limit reached)")
        if not self._node_connected(pid, node_id):
            raise ValueError("must connect via your road")

        self._pay(pid, COSTS["settlement"])
        self.buildings[node_id] = {"player": pid, "type": "settlement"}
        self.settlements_on_board[pid] += 1

        self._update_longest_road()
        self._check_win(pid)

    def build_city(self, pid: str, node_id: int) -> None:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")

        b = self.buildings.get(node_id)
        if not b or b["player"] != pid or b["type"] != "settlement":
            raise ValueError("need your settlement to upgrade")
        if self.cities_on_board.get(pid, 0) >= MAX_CITIES:
            raise ValueError("no cities left (limit reached)")

        self._pay(pid, COSTS["city"])
        self.buildings[node_id] = {"player": pid, "type": "city"}
        self.cities_on_board[pid] += 1
        self.settlements_on_board[pid] -= 1  # returned settlement piece

        self._check_win(pid)

    # ---------------- trade bank/ports ----------------
    def trade_bank(self, pid: str, give_res: Resource, give_n: int, get_res: Resource) -> None:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if give_res not in ("wood","brick","wheat","sheep","ore") or get_res not in ("wood","brick","wheat","sheep","ore"):
            raise ValueError("bad resource")
        if give_res == get_res:
            raise ValueError("give and get must differ")

        rate = 4
        ports = self.ports_for_player(pid)
        if f"{give_res}2" in ports:
            rate = 2
        elif "any3" in ports:
            rate = 3

        if give_n != rate:
            raise ValueError(f"wrong rate for {give_res}. Your rate: {rate}:1 (send give={give_res}:{rate}).")

        pl = self.player(pid)
        if pl.resources[give_res] < give_n:
            raise ValueError("not enough resources to trade")
        pl.resources[give_res] -= give_n
        pl.resources[get_res] += 1

    # ---------------- dev cards ----------------
    def buy_dev(self, pid: str) -> str:
        if self.phase != "main" or self.board is None:
            raise ValueError("not in main")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if not self.dev_deck:
            raise ValueError("dev deck empty")
        self._pay(pid, COSTS["dev"])

        card = self.dev_deck.pop()
        p = self.player(pid)
        if card == "victory_point":
            p.vp_cards += 1
            self._check_win(pid)
        else:
            p.dev_new.append(card)
        return card

    def play_knight(self, pid: str, hex_id: int, victim: Optional[str]) -> None:
        self._ensure_can_play_dev(pid, "knight")
        # playing knight: move robber + steal (optional)
        self.phase = "robber"
        self.move_robber(pid, hex_id, victim=victim)
        p = self.player(pid)
        p.played_knights += 1
        self._update_largest_army()
        self._consume_dev(pid, "knight")
        self._check_win(pid)

    def play_road_building(self, pid: str, edge1: int, edge2: int) -> None:
        self._ensure_can_play_dev(pid, "road_building")
        # build two free roads (still must be legal)
        self.build_road(pid, edge1, free=True)
        self.build_road(pid, edge2, free=True)
        self._consume_dev(pid, "road_building")
        self._check_win(pid)

    def play_monopoly(self, pid: str, res: Resource) -> None:
        self._ensure_can_play_dev(pid, "monopoly")
        if res not in ("wood","brick","wheat","sheep","ore"):
            raise ValueError("bad resource")
        me = self.player(pid)
        got = 0
        for p in self.players:
            if p.id == pid:
                continue
            c = p.resources[res]
            if c > 0:
                p.resources[res] -= c
                got += c
        me.resources[res] += got
        self._consume_dev(pid, "monopoly")

    def play_year_of_plenty(self, pid: str, res1: Resource, res2: Resource) -> None:
        self._ensure_can_play_dev(pid, "year_of_plenty")
        if res1 not in ("wood","brick","wheat","sheep","ore") or res2 not in ("wood","brick","wheat","sheep","ore"):
            raise ValueError("bad resource")
        me = self.player(pid)
        me.resources[res1] += 1
        me.resources[res2] += 1
        self._consume_dev(pid, "year_of_plenty")

    def _ensure_can_play_dev(self, pid: str, card: str) -> None:
        if self.phase != "main":
            raise ValueError("can play dev only in main phase")
        if self.winner is not None:
            raise ValueError("game over")
        if pid != self.current_player:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if self.dev_played_this_turn:
            raise ValueError("only one dev card per turn")
        p = self.player(pid)
        if card not in p.dev_hand:
            raise ValueError("you do not have this dev card (or it is new this turn)")

    def _consume_dev(self, pid: str, card: str) -> None:
        p = self.player(pid)
        p.dev_hand.remove(card)
        self.dev_played_this_turn = True

    # ---------------- resource distribution ----------------
    def _distribute_resources(self, roll: int) -> None:
        assert self.board is not None
        for h in self.board.hexes.values():
            if h.number != roll:
                continue
            if h.id == self.board.robber_hex:
                continue
            if h.terrain == "desert":
                continue
            for nid in h.nodes:
                b = self.buildings.get(nid)
                if not b:
                    continue
                owner = self.player(b["player"])
                amount = 2 if b["type"] == "city" else 1
                owner.resources[h.terrain] += amount

    # ---------------- payments/connectivity ----------------
    def _pay(self, pid: str, cost: Dict[Resource, int]) -> None:
        pl = self.player(pid)
        for r, c in cost.items():
            if pl.resources.get(r, 0) < c:
                raise ValueError(f"not enough {r}")
        for r, c in cost.items():
            pl.resources[r] -= c

    def _node_connected(self, pid: str, node_id: int) -> bool:
        assert self.board is not None
        b = self.buildings.get(node_id)
        if b and b["player"] == pid:
            return True
        for eid, (a, bn) in self.board.edge_nodes.items():
            if eid not in self.roads:
                continue
            if self.roads[eid] != pid:
                continue
            if a == node_id or bn == node_id:
                return True
        return False

    def _road_connected(self, pid: str, edge_id: int) -> bool:
        assert self.board is not None
        a, b = self.board.edge_nodes[edge_id]

        # if endpoint has your building -> ok
        for nid in (a, b):
            bb = self.buildings.get(nid)
            if bb and bb["player"] == pid:
                return True

        # or if connects to your road through non-blocked node
        for nid in (a, b):
            bb = self.buildings.get(nid)
            if bb and bb["player"] != pid:
                continue  # blocked
            for eid2, (x, y) in self.board.edge_nodes.items():
                if eid2 not in self.roads or self.roads[eid2] != pid:
                    continue
                if x == nid or y == nid:
                    return True
        return False

    def _is_blocked_node_for_road(self, pid: str, node_id: int) -> bool:
        b = self.buildings.get(node_id)
        return bool(b and b["player"] != pid)

    # ---------------- awards: largest army ----------------
    def _update_largest_army(self) -> None:
        # must be >=3 and strictly greater than others to take
        best_pid = None
        best = 0
        for p in self.players:
            if p.played_knights > best:
                best = p.played_knights
                best_pid = p.id
        if best < 3:
            return
        # tie does not transfer
        tied = sum(1 for p in self.players if p.played_knights == best)
        if tied > 1:
            return
        if self.largest_army_holder != best_pid:
            self.largest_army_holder = best_pid
            self.largest_army_size = best

    # ---------------- awards: longest road ----------------
    def _update_longest_road(self) -> None:
        # compute current best
        best_pid = self.longest_road_holder
        best_len = self.longest_road_len

        for p in self.players:
            l = self._longest_road_length(p.id)
            if l >= 5:
                if l > best_len:
                    best_len = l
                    best_pid = p.id
                elif l == best_len:
                    # tie: holder stays (no transfer)
                    pass

        # if someone lost roads and holder no longer qualifies, recompute strictly
        # Simplified: just set to best found this pass (holder stays on ties)
        self.longest_road_holder = best_pid if best_len >= 5 else None
        self.longest_road_len = best_len if best_len >= 5 else 0

    def _longest_road_length(self, pid: str) -> int:
        if self.board is None:
            return 0

        # player edges
        player_edges = [eid for eid, owner in self.roads.items() if owner == pid]
        if not player_edges:
            return 0

        # build adjacency: node -> list of edges
        node_to_edges: Dict[int, List[int]] = {}
        for eid in player_edges:
            a, b = self.board.edge_nodes[eid]
            node_to_edges.setdefault(a, []).append(eid)
            node_to_edges.setdefault(b, []).append(eid)

        def dfs(node: int, used: Set[int]) -> int:
            # cannot continue THROUGH opponent building
            if self._is_blocked_node_for_road(pid, node):
                return 0
            best = 0
            for eid in node_to_edges.get(node, []):
                if eid in used:
                    continue
                a, b = self.board.edge_nodes[eid]
                nxt = b if node == a else a
                used.add(eid)
                best = max(best, 1 + dfs(nxt, used))
                used.remove(eid)
            return best

        best_len = 0
        for start_node in list(node_to_edges.keys()):
            best_len = max(best_len, dfs(start_node, set()))
        return best_len
