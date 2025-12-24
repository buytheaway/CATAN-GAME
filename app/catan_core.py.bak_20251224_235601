from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

# --- resources / terrains ---
TERRAIN_TO_RES = {
    "forest": "wood",
    "hills": "brick",
    "pasture": "sheep",
    "fields": "wheat",
    "mountains": "ore",
    "desert": None,
}

PIP_WEIGHT = {2:1,3:2,4:3,5:4,6:5,8:5,9:4,10:3,11:2,12:1}

COSTS = {
    "road": {"wood":1, "brick":1},
    "settlement": {"wood":1, "brick":1, "sheep":1, "wheat":1},
    "city": {"wheat":2, "ore":3},
    "dev": {"sheep":1, "wheat":1, "ore":1},
}

@dataclass(frozen=True)
class HexTile:
    idx: int
    terrain: str
    number: Optional[int]
    q: int
    r: int

def gen_classic_map(seed: Optional[int] = None) -> list[HexTile]:
    rng = random.Random(seed)
    coords: list[tuple[int,int]] = []
    rows = [3,4,5,4,3]
    r0 = -(len(rows)//2)
    for row_i, n in enumerate(rows):
        rr = r0 + row_i
        q_start = -(n//2)
        for j in range(n):
            coords.append((q_start + j, rr))

    terrains = (
        ["forest"]*4 +
        ["pasture"]*4 +
        ["fields"]*4 +
        ["hills"]*3 +
        ["mountains"]*3 +
        ["desert"]*1
    )
    rng.shuffle(terrains)

    numbers = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]
    rng.shuffle(numbers)

    tiles: list[HexTile] = []
    ni = 0
    for i,(q,r) in enumerate(coords):
        t = terrains[i]
        if t == "desert":
            tiles.append(HexTile(i, t, None, q, r))
        else:
            tiles.append(HexTile(i, t, numbers[ni], q, r))
            ni += 1
    return tiles

@dataclass
class MapGraph:
    # node_id -> (x,y)
    nodes: dict[int, tuple[float,float]] = field(default_factory=dict)
    # edge_id -> (a,b) where a<b node_ids
    edges: dict[int, tuple[int,int]] = field(default_factory=dict)
    # node_id -> neighbor node_ids
    adj: dict[int, set[int]] = field(default_factory=dict)
    # node_id -> list[tile_idx]
    node_tiles: dict[int, list[int]] = field(default_factory=dict)

def build_graph(tiles: list[HexTile], hex_size: float = 62.0) -> MapGraph:
    # axial -> pixel (pointy top)
    w = math.sqrt(3) * hex_size
    v = 1.5 * hex_size

    def axial_to_xy(q: int, r: int) -> tuple[float,float]:
        x = w * (q + r/2.0)
        y = v * r
        return (x, y)

    def corners(cx: float, cy: float) -> list[tuple[float,float]]:
        pts = []
        for i in range(6):
            ang = math.radians(60*i - 30)
            pts.append((cx + hex_size*math.cos(ang), cy + hex_size*math.sin(ang)))
        return pts

    # de-dup corners by quantization
    key_to_id: dict[tuple[int,int], int] = {}
    nodes: dict[int, tuple[float,float]] = {}
    node_tiles: dict[int, list[int]] = {}
    edges_set: set[tuple[int,int]] = set()

    def nid_for(pt: tuple[float,float]) -> int:
        x,y = pt
        key = (int(round(x*10)), int(round(y*10)))  # 0.1px grid
        if key in key_to_id:
            return key_to_id[key]
        nid = len(key_to_id)
        key_to_id[key] = nid
        nodes[nid] = (x,y)
        node_tiles[nid] = []
        return nid

    for t in tiles:
        cx,cy = axial_to_xy(t.q, t.r)
        pts = corners(cx,cy)
        nids = [nid_for(p) for p in pts]
        for nid in nids:
            node_tiles[nid].append(t.idx)
        # edges of hex
        for i in range(6):
            a = nids[i]
            b = nids[(i+1) % 6]
            aa,bb = (a,b) if a<b else (b,a)
            edges_set.add((aa,bb))

    edges: dict[int, tuple[int,int]] = {}
    adj: dict[int, set[int]] = {nid:set() for nid in nodes.keys()}
    for eid,(a,b) in enumerate(sorted(edges_set)):
        edges[eid] = (a,b)
        adj[a].add(b)
        adj[b].add(a)

    return MapGraph(nodes=nodes, edges=edges, adj=adj, node_tiles=node_tiles)

@dataclass
class Player:
    name: str
    is_bot: bool = False
    resources: dict[str,int] = field(default_factory=lambda: {"wood":0,"brick":0,"sheep":0,"wheat":0,"ore":0})
    dev_cards: int = 0
    settlements: set[int] = field(default_factory=set)
    cities: set[int] = field(default_factory=set)
    roads: set[int] = field(default_factory=set)

    def vp(self) -> int:
        return len(self.settlements) + 2*len(self.cities)

    def total_cards(self) -> int:
        return sum(self.resources.values()) + self.dev_cards

@dataclass
class Bank:
    stock: dict[str,int] = field(default_factory=lambda: {"wood":19,"brick":19,"sheep":19,"wheat":19,"ore":19})

    def can_pay(self, res: str, n: int) -> bool:
        return self.stock.get(res,0) >= n

    def take(self, res: str, n: int) -> int:
        # give to player
        have = self.stock.get(res,0)
        k = min(have, n)
        self.stock[res] = have - k
        return k

    def put(self, res: str, n: int) -> None:
        self.stock[res] = self.stock.get(res,0) + n

@dataclass
class Game:
    seed: int
    tiles: list[HexTile]
    graph: MapGraph
    bank: Bank
    players: list[Player]
    current: int = 0
    phase: str = "setup"  # setup | main
    setup_step: int = 0   # 0: P0 settlement, 1: P0 road, 2: P1 settlement, 3: P1 road
    rolled: bool = False
    last_roll: Optional[int] = None
    winner: Optional[int] = None

    def cur_player(self) -> Player:
        return self.players[self.current]

    def required_action(self) -> str:
        if self.phase != "setup":
            return ""
        return "settlement" if self.setup_step % 2 == 0 else "road"

    def next_after_setup_action(self) -> None:
        self.setup_step += 1
        if self.setup_step <= 1:
            self.current = 0
        elif self.setup_step <= 3:
            self.current = 1
        else:
            self.phase = "main"
            self.current = 0
            self.rolled = False
            self.last_roll = None

    # ---- rules helpers ----
    def can_afford(self, p: Player, cost: dict[str,int]) -> bool:
        return all(p.resources.get(k,0) >= v for k,v in cost.items())

    def pay_cost(self, p: Player, cost: dict[str,int]) -> None:
        for k,v in cost.items():
            p.resources[k] -= v
            self.bank.put(k, v)

    def can_place_settlement(self, p: Player, node: int) -> bool:
        # empty
        for pl in self.players:
            if node in pl.settlements or node in pl.cities:
                return False
        # distance rule: no neighbor occupied
        for nb in self.graph.adj[node]:
            for pl in self.players:
                if nb in pl.settlements or nb in pl.cities:
                    return False
        # in main phase: must connect to own road
        if self.phase == "main":
            if not any(self._edge_incident_to_node_owned(p, node, eid) for eid in self.graph_edge_ids_incident(node)):
                return False
        return True

    def graph_edge_ids_incident(self, node: int) -> list[int]:
        out = []
        for eid,(a,b) in self.graph.edges.items():
            if a == node or b == node:
                out.append(eid)
        return out

    def _edge_incident_to_node_owned(self, p: Player, node: int, eid: int) -> bool:
        if eid not in p.roads:
            return False
        a,b = self.graph.edges[eid]
        return a == node or b == node

    def can_place_road(self, p: Player, eid: int) -> bool:
        # empty
        for pl in self.players:
            if eid in pl.roads:
                return False
        a,b = self.graph.edges[eid]
        # in setup: must touch just placed settlement of this player
        if self.phase == "setup":
            if not p.settlements and not p.cities:
                return False
            # must touch last settlement (approx: any own settlement)
            return (a in p.settlements or a in p.cities or b in p.settlements or b in p.cities)
        # main: must connect to existing road/settlement/city
        if (a in p.settlements or a in p.cities or b in p.settlements or b in p.cities):
            return True
        # connect to existing road via shared node
        for rid in p.roads:
            ra,rb = self.graph.edges[rid]
            if a in (ra,rb) or b in (ra,rb):
                return True
        return False

    # ---- actions ----
    def place_settlement(self, node: int) -> str:
        p = self.cur_player()
        if self.phase == "setup":
            if self.required_action() != "settlement":
                return "Not your setup action."
            if not self.can_place_settlement(p, node):
                return "Invalid settlement spot."
            p.settlements.add(node)
            self.next_after_setup_action()
            return f"{p.name} placed a settlement."
        else:
            if not self.can_afford(p, COSTS["settlement"]):
                return "Not enough resources."
            if not self.can_place_settlement(p, node):
                return "Invalid settlement spot."
            self.pay_cost(p, COSTS["settlement"])
            p.settlements.add(node)
            self._check_win()
            return f"{p.name} built a settlement."

    def place_road(self, eid: int) -> str:
        p = self.cur_player()
        if self.phase == "setup":
            if self.required_action() != "road":
                return "Not your setup action."
            if not self.can_place_road(p, eid):
                return "Invalid road."
            p.roads.add(eid)
            self.next_after_setup_action()
            return f"{p.name} placed a road."
        else:
            if not self.can_afford(p, COSTS["road"]):
                return "Not enough resources."
            if not self.can_place_road(p, eid):
                return "Invalid road."
            self.pay_cost(p, COSTS["road"])
            p.roads.add(eid)
            return f"{p.name} built a road."

    def upgrade_city(self, node: int) -> str:
        p = self.cur_player()
        if self.phase != "main":
            return "Cities only in main phase."
        if node not in p.settlements:
            return "You need a settlement there."
        if not self.can_afford(p, COSTS["city"]):
            return "Not enough resources."
        self.pay_cost(p, COSTS["city"])
        p.settlements.remove(node)
        p.cities.add(node)
        self._check_win()
        return f"{p.name} upgraded to a city."

    def buy_dev(self) -> str:
        p = self.cur_player()
        if self.phase != "main":
            return "Dev cards only in main phase."
        if not self.can_afford(p, COSTS["dev"]):
            return "Not enough resources."
        self.pay_cost(p, COSTS["dev"])
        p.dev_cards += 1
        return f"{p.name} bought a development card."

    def trade_bank_4to1(self, give_res: str, get_res: str) -> str:
        p = self.cur_player()
        if self.phase != "main":
            return "Trade only in main phase."
        if give_res == get_res:
            return "Pick different resources."
        if p.resources.get(give_res,0) < 4:
            return "Not enough to trade (need 4)."
        if not self.bank.can_pay(get_res, 1):
            return "Bank is out of that resource."
        p.resources[give_res] -= 4
        self.bank.put(give_res, 4)
        got = self.bank.take(get_res, 1)
        p.resources[get_res] += got
        return f"{p.name} traded 4 {give_res} -> 1 {get_res}."

    def roll_dice(self) -> int:
        if self.phase != "main":
            return 0
        if self.rolled:
            return 0
        a = random.randint(1,6)
        b = random.randint(1,6)
        s = a+b
        self.rolled = True
        self.last_roll = s
        return s

    def distribute(self, roll: int) -> list[str]:
        if roll <= 0:
            return []
        logs: list[str] = []
        if roll == 7:
            # simplified discard: auto-random if >7
            for p in self.players:
                total = sum(p.resources.values())
                if total > 7:
                    need = total // 2
                    logs.append(f"[7] {p.name} discards {need} cards (auto).")
                    self._auto_discard(p, need)
            logs.append("[7] Robber is not implemented yet (Sprint 3).")
            return logs

        for t in self.tiles:
            if t.number != roll:
                continue
            res = TERRAIN_TO_RES[t.terrain]
            if not res:
                continue
            # nodes touching this tile
            for nid, tlist in self.graph.node_tiles.items():
                if t.idx not in tlist:
                    continue
                for pi,p in enumerate(self.players):
                    if nid in p.settlements:
                        got = self.bank.take(res, 1)
                        p.resources[res] += got
                    elif nid in p.cities:
                        got = self.bank.take(res, 2)
                        p.resources[res] += got
        logs.append(f"[ROLL] distributed resources for {roll}.")
        self._check_win()
        return logs

    def end_turn(self) -> str:
        if self.phase != "main":
            return "Can't end during setup."
        self.current = (self.current + 1) % len(self.players)
        self.rolled = False
        self.last_roll = None
        return f"Turn: {self.cur_player().name}"

    def _auto_discard(self, p: Player, need: int) -> None:
        bag = []
        for r,c in p.resources.items():
            bag += [r]*c
        random.shuffle(bag)
        for _ in range(min(need, len(bag))):
            r = bag.pop()
            p.resources[r] -= 1
            self.bank.put(r, 1)

    def _check_win(self) -> None:
        for i,p in enumerate(self.players):
            if p.vp() >= 10:
                self.winner = i

def new_game(seed: Optional[int] = None) -> Game:
    if seed is None:
        seed = random.randint(1, 10_000_000)
    tiles = gen_classic_map(seed)
    graph = build_graph(tiles, hex_size=62.0)
    bank = Bank()
    players = [Player("You", is_bot=False), Player("Bot", is_bot=True)]
    return Game(seed=seed, tiles=tiles, graph=graph, bank=bank, players=players)

# --- bot ---
def bot_setup_pick(game: Game) -> tuple[int,int]:
    # pick best settlement node by pip weight sum
    p = game.cur_player()
    best = None
    best_score = -1
    for nid in game.graph.nodes.keys():
        if not game.can_place_settlement(p, nid):
            continue
        score = 0
        for tid in game.graph.node_tiles[nid]:
            t = game.tiles[tid]
            if t.number:
                score += PIP_WEIGHT.get(t.number,0)
        if score > best_score:
            best_score = score
            best = nid
    if best is None:
        best = next(iter(game.graph.nodes.keys()))
    # choose any adjacent edge
    for eid,(a,b) in game.graph.edges.items():
        if (a==best or b==best) and game.can_place_road(p, eid):
            return (best, eid)
    # fallback
    eid0 = next(iter(game.graph.edges.keys()))
    return (best, eid0)

def bot_take_turn(game: Game) -> list[str]:
    logs: list[str] = []
    p = game.cur_player()

    if game.phase == "setup":
        if game.required_action() == "settlement":
            node, _ = bot_setup_pick(game)
            logs.append(game.place_settlement(node))
        else:
            # road
            node = next(iter(p.settlements)) if p.settlements else next(iter(game.graph.nodes.keys()))
            chosen = None
            for eid,(a,b) in game.graph.edges.items():
                if (a==node or b==node) and game.can_place_road(p, eid):
                    chosen = eid
                    break
            if chosen is None:
                chosen = next(iter(game.graph.edges.keys()))
            logs.append(game.place_road(chosen))
        return logs

    # main
    if not game.rolled:
        roll = game.roll_dice()
        logs.append(f"Bot rolled {roll}.")
        logs += game.distribute(roll)

    # try build settlement
    if game.can_afford(p, COSTS["settlement"]):
        best = None
        best_score = -1
        for nid in game.graph.nodes.keys():
            if not game.can_place_settlement(p, nid):
                continue
            score = 0
            for tid in game.graph.node_tiles[nid]:
                t = game.tiles[tid]
                if t.number:
                    score += PIP_WEIGHT.get(t.number,0)
            if score > best_score:
                best_score = score
                best = nid
        if best is not None:
            logs.append(game.place_settlement(best))
            return logs

    # try city
    if game.can_afford(p, COSTS["city"]) and p.settlements:
        # upgrade best yield settlement
        best_node = None
        best_score = -1
        for nid in list(p.settlements):
            score = 0
            for tid in game.graph.node_tiles[nid]:
                t = game.tiles[tid]
                if t.number:
                    score += PIP_WEIGHT.get(t.number,0)
            if score > best_score:
                best_score = score
                best_node = nid
        if best_node is not None:
            logs.append(game.upgrade_city(best_node))
            return logs

    # try road
    if game.can_afford(p, COSTS["road"]):
        for eid in game.graph.edges.keys():
            if game.can_place_road(p, eid):
                logs.append(game.place_road(eid))
                return logs

    # try dev
    if game.can_afford(p, COSTS["dev"]):
        logs.append(game.buy_dev())
        return logs

    # try simple trade for settlement (4:1)
    need = COSTS["settlement"]
    missing = [r for r,n in need.items() if p.resources.get(r,0) < n]
    if missing:
        miss = missing[0]
        give = None
        for r,c in p.resources.items():
            if r != miss and c >= 4:
                give = r
                break
        if give and game.bank.can_pay(miss, 1):
            logs.append(game.trade_bank_4to1(give, miss))
            return logs

    logs.append(game.end_turn())
    return logs
