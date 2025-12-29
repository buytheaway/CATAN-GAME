from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .board import Board, make_board

RES = ["wood","brick","sheep","wheat","ore"]

COST = {
    "road": {"wood":1, "brick":1},
    "settlement": {"wood":1, "brick":1, "sheep":1, "wheat":1},
    "city": {"wheat":2, "ore":3},
    "dev": {"sheep":1, "wheat":1, "ore":1},
}

DEV_DECK = (
    ["knight"]*14 + ["vp"]*5 + ["road"]*2 + ["monopoly"]*2 + ["plenty"]*2
)

@dataclass
class Building:
    owner: str
    kind: str  # settlement/city

@dataclass
class EdgeOwner:
    owner: str  # road

@dataclass
class TradeOffer:
    id: str
    from_id: str
    to_id: str  # "*" for all
    give: Dict[str,int]
    get: Dict[str,int]
    status: str = "open"  # open/accepted/canceled

@dataclass
class Player:
    id: str
    name: str
    online: bool = True
    resources: Dict[str,int] = field(default_factory=lambda: {r:0 for r in RES})
    vp_cards: int = 0
    dev_hand: List[str] = field(default_factory=list)
    dev_new: List[str] = field(default_factory=list)
    knights_played: int = 0

@dataclass
class Game:
    seed: int | None = None
    board: Board = field(default_factory=lambda: make_board(None))
    phase: str = "lobby"  # lobby/setup/main/over
    host_id: Optional[str] = None
    players: List[Player] = field(default_factory=list)
    current: Optional[str] = None
    rolled: bool = False
    last_roll: Optional[int] = None

    buildings: Dict[int, Building] = field(default_factory=dict)  # node_id -> building
    roads: Dict[int, EdgeOwner] = field(default_factory=dict)     # edge_id -> road owner
    robber_hex: int = 0

    # setup placements
    setup_order: List[str] = field(default_factory=list)
    setup_index: int = 0
    setup_round: int = 0
    setup_place_pending_node: Dict[str, Optional[int]] = field(default_factory=dict)

    # dev deck
    dev_deck: List[str] = field(default_factory=list)

    # trade offers
    offers: List[TradeOffer] = field(default_factory=list)

    winner: Optional[str] = None

    def reset(self, seed: int | None = None):
        self.seed = seed
        self.board = make_board(seed)
        self.phase = "lobby"
        self.current = None
        self.rolled = False
        self.last_roll = None
        self.buildings.clear()
        self.roads.clear()
        self.robber_hex = self.board.robber_hex
        self.setup_order.clear()
        self.setup_index = 0
        self.setup_round = 0
        self.setup_place_pending_node = {p.id: None for p in self.players}
        self.dev_deck = DEV_DECK.copy()
        random.Random(seed).shuffle(self.dev_deck)
        self.offers.clear()
        self.winner = None

    def add_player(self, pid: str, name: str) -> Player:
        p = Player(id=pid, name=name)
        self.players.append(p)
        if self.host_id is None:
            self.host_id = pid
        self.setup_place_pending_node[pid] = None
        return p

    def get_player(self, pid: str) -> Player:
        for p in self.players:
            if p.id == pid:
                return p
        raise ValueError("player not found")

    def public_players(self):
        out = []
        for p in self.players:
            out.append({
                "id": p.id,
                "name": p.name,
                "online": p.online,
                "vp": self.vp(p.id),
                "res_count": sum(p.resources.values()),
                "knights": p.knights_played,
                "dev_hand": len(p.dev_hand),
                "dev_new": len(p.dev_new),
            })
        return out

    def vp(self, pid: str) -> int:
        v = 0
        for n,b in self.buildings.items():
            if b.owner == pid:
                v += 1 if b.kind == "settlement" else 2
        v += self.get_player(pid).vp_cards
        # (largest army / longest road can be added later)
        return v

    def can_start(self, pid: str) -> bool:
        return self.phase == "lobby" and pid == self.host_id and len(self.players) >= 2

    def start(self, pid: str, seed: int | None = None):
        if not self.can_start(pid):
            raise ValueError("cannot start")
        self.reset(seed)
        self.phase = "setup"
        # snake order: p0..pn-1 then reverse
        self.setup_order = [p.id for p in self.players]
        self.current = self.setup_order[0]
        self.setup_index = 0
        self.setup_round = 0
        self.setup_place_pending_node = {p.id: None for p in self.players}

    # ---------- helpers ----------
    def _has_res(self, pid: str, cost: Dict[str,int]) -> bool:
        pr = self.get_player(pid).resources
        return all(pr[r] >= n for r,n in cost.items())

    def _take_res(self, pid: str, cost: Dict[str,int]):
        pr = self.get_player(pid).resources
        for r,n in cost.items():
            pr[r] -= n

    def _give_res(self, pid: str, give: Dict[str,int]):
        pr = self.get_player(pid).resources
        for r,n in give.items():
            if r in pr:
                pr[r] += n

    def _node_free(self, node: int) -> bool:
        return node not in self.buildings

    def _node_distance_ok(self, node: int) -> bool:
        # distance rule: no adjacent settlements/cities
        for nb in self.board.node_adj_nodes[node]:
            if nb in self.buildings:
                return False
        return True

    def _edge_free(self, edge: int) -> bool:
        return edge not in self.roads

    def _edge_touches_node(self, edge_id: int, node_id: int) -> bool:
        e = self.board.edges[edge_id]
        return e.a == node_id or e.b == node_id

    def _player_has_road_adjacent(self, pid: str, node: int) -> bool:
        for eid in self.board.node_adj_edges[node]:
            if eid in self.roads and self.roads[eid].owner == pid:
                return True
        return False

    def _player_has_building(self, pid: str, node: int) -> bool:
        b = self.buildings.get(node)
        return b is not None and b.owner == pid

    def _node_connected_for_settlement(self, pid: str, node: int) -> bool:
        # in main phase: need adjacent own road
        return self._player_has_road_adjacent(pid, node)

    def _edge_connected_for_road(self, pid: str, edge: int) -> bool:
        e = self.board.edges[edge]
        # connected if touches own road or building
        for n in (e.a, e.b):
            if self._player_has_building(pid, n):
                return True
            for adj in self.board.node_adj_edges[n]:
                if adj in self.roads and self.roads[adj].owner == pid:
                    return True
        return False

    # ---------- setup ----------
    def setup_valid_nodes(self, pid: str) -> List[int]:
        if self.phase != "setup" or pid != self.current:
            return []
        return [n.id for n in self.board.nodes if self._node_free(n.id) and self._node_distance_ok(n.id)]

    def setup_valid_edges(self, pid: str, chosen_node: int) -> List[int]:
        if self.phase != "setup" or pid != self.current:
            return []
        return [eid for eid in self.board.node_adj_edges[chosen_node] if self._edge_free(eid)]

    def place_setup(self, pid: str, node: int, edge: int):
        if self.phase != "setup" or pid != self.current:
            raise ValueError("not your setup turn")
        if node not in self.setup_valid_nodes(pid):
            raise ValueError("invalid node")
        if edge not in self.setup_valid_edges(pid, node):
            raise ValueError("invalid edge")

        self.buildings[node] = Building(owner=pid, kind="settlement")
        self.roads[edge] = EdgeOwner(owner=pid)

        # second settlement in setup => initial resources
        if self.setup_round == 1:
            self._grant_initial_resources(pid, node)

        # advance snake: forward then reverse
        n = len(self.setup_order)
        if self.setup_round == 0:
            self.setup_index += 1
            if self.setup_index >= n:
                self.setup_round = 1
                self.setup_index = n-1
        else:
            self.setup_index -= 1
            if self.setup_index < 0:
                # setup over
                self.phase = "main"
                self.current = self.setup_order[0]
                self.rolled = False
                self.last_roll = None
                self._end_turn_cleanup()
                return

        self.current = self.setup_order[self.setup_index]

    def _grant_initial_resources(self, pid: str, node: int):
        for hid in self.board.node_adj_hexes[node]:
            h = self.board.hexes[hid]
            if h.res != "desert":
                self.get_player(pid).resources[h.res] += 1

    # ---------- main phase ----------
    def roll(self, pid: str) -> int:
        if self.phase != "main" or pid != self.current:
            raise ValueError("not your turn")
        if self.rolled:
            raise ValueError("already rolled")
        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        s = d1 + d2
        self.last_roll = s
        self.rolled = True

        if s == 7:
            # discard required handled by clients via hints
            return s

        # distribute resources
        for h in self.board.hexes:
            if h.num != s:
                continue
            if h.id == self.robber_hex:
                continue
            if h.res == "desert":
                continue
            # corners => nodes adjacent
            # derive nodes by geometry: node_adj_hexes has it
            for nid, hexes in self.board.node_adj_hexes.items():
                if h.id not in hexes:
                    continue
                b = self.buildings.get(nid)
                if not b:
                    continue
                amt = 1 if b.kind == "settlement" else 2
                self.get_player(b.owner).resources[h.res] += amt

        return s

    def end_turn(self, pid: str):
        if self.phase != "main" or pid != self.current:
            raise ValueError("not your turn")
        # move dev_new to dev_hand at end of your turn
        p = self.get_player(pid)
        p.dev_hand.extend(p.dev_new)
        p.dev_new.clear()

        # next player
        idx = [p.id for p in self.players].index(self.current)
        self.current = [p.id for p in self.players][(idx+1) % len(self.players)]
        self.rolled = False
        self._end_turn_cleanup()

    def _end_turn_cleanup(self):
        # auto-cancel all open offers from previous current player when turn changes
        for o in self.offers:
            if o.status == "open":
                o.status = "canceled"

    def build(self, pid: str, kind: str, id_: int):
        if self.phase != "main" or pid != self.current:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")

        kind = kind.lower()
        if kind == "road":
            if not self._edge_free(id_):
                raise ValueError("edge occupied")
            if not self._has_res(pid, COST["road"]):
                raise ValueError("not enough resources")
            if not self._edge_connected_for_road(pid, id_):
                raise ValueError("road must connect")
            self._take_res(pid, COST["road"])
            self.roads[id_] = EdgeOwner(owner=pid)
            return

        if kind == "settlement":
            if not self._node_free(id_):
                raise ValueError("node occupied")
            if not self._node_distance_ok(id_):
                raise ValueError("too close to another settlement")
            if not self._node_connected_for_settlement(pid, id_):
                raise ValueError("settlement must connect to your road")
            if not self._has_res(pid, COST["settlement"]):
                raise ValueError("not enough resources")
            self._take_res(pid, COST["settlement"])
            self.buildings[id_] = Building(owner=pid, kind="settlement")
            self._check_winner()
            return

        if kind == "city":
            b = self.buildings.get(id_)
            if not b or b.owner != pid or b.kind != "settlement":
                raise ValueError("need your settlement to upgrade")
            if not self._has_res(pid, COST["city"]):
                raise ValueError("not enough resources")
            self._take_res(pid, COST["city"])
            self.buildings[id_] = Building(owner=pid, kind="city")
            self._check_winner()
            return

        raise ValueError("unknown build kind")

    def trade_bank(self, pid: str, give_res: str, give_n: int, get_res: str):
        if self.phase != "main" or pid != self.current:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        give_res = give_res.lower()
        get_res = get_res.lower()
        if give_res not in RES or get_res not in RES:
            raise ValueError("bad resource")
        if give_n not in (4,):
            raise ValueError("only 4:1 supported now")
        pr = self.get_player(pid).resources
        if pr[give_res] < give_n:
            raise ValueError("not enough resources")
        pr[give_res] -= give_n
        pr[get_res] += 1

    # ---------- player trade (offers) ----------
    def offer_trade(self, pid: str, to_id: str, give: Dict[str,int], get: Dict[str,int]) -> TradeOffer:
        if self.phase != "main" or pid != self.current:
            raise ValueError("not your turn")
        if not self.rolled:
            raise ValueError("roll first")
        if to_id != "*" and all(p.id != to_id for p in self.players):
            raise ValueError("bad target")

        give = {k:int(v) for k,v in give.items() if k in RES and int(v) > 0}
        get  = {k:int(v) for k,v in get.items()  if k in RES and int(v) > 0}
        if not give or not get:
            raise ValueError("give/get must be non-empty")

        # must have resources for give
        pr = self.get_player(pid).resources
        for r,n in give.items():
            if pr[r] < n:
                raise ValueError(f"not enough {r}")

        oid = f"offer-{random.randint(100000,999999)}"
        o = TradeOffer(id=oid, from_id=pid, to_id=to_id, give=give, get=get, status="open")
        self.offers.append(o)
        return o

    def accept_trade(self, pid: str, offer_id: str):
        o = next((x for x in self.offers if x.id == offer_id), None)
        if not o or o.status != "open":
            raise ValueError("offer not found/open")
        if o.to_id != "*" and o.to_id != pid:
            raise ValueError("not your offer")
        # current player is offer owner; accepting player can accept
        offerer = self.get_player(o.from_id)
        accepter = self.get_player(pid)

        # validate both have resources
        for r,n in o.give.items():
            if offerer.resources[r] < n:
                raise ValueError("offerer lacks resources now")
        for r,n in o.get.items():
            if accepter.resources[r] < n:
                raise ValueError("accepter lacks resources")

        # transfer: offerer gives 'give' to accepter; accepter gives 'get' to offerer
        for r,n in o.give.items():
            offerer.resources[r] -= n
            accepter.resources[r] += n
        for r,n in o.get.items():
            accepter.resources[r] -= n
            offerer.resources[r] += n

        o.status = "accepted"

    def cancel_trade(self, pid: str, offer_id: str):
        o = next((x for x in self.offers if x.id == offer_id), None)
        if not o or o.status != "open":
            raise ValueError("offer not found/open")
        if o.from_id != pid:
            raise ValueError("only offerer can cancel")
        o.status = "canceled"

    def _check_winner(self):
        for p in self.players:
            if self.vp(p.id) >= 10:
                self.phase = "over"
                self.winner = p.id
                break

    # ---------- state/hints ----------
    def state_for(self, pid: str) -> Tuple[dict, dict, dict]:
        pub = {
            "phase": self.phase,
            "host_id": self.host_id,
            "current_player": self.current,
            "rolled": self.rolled,
            "last_roll": self.last_roll,
            "winner": self.winner,
            "players": self.public_players(),
            "robber_hex": self.robber_hex,
            "board": {
                "nodes": [{"id": n.id, "x": n.x, "y": n.y, "b": (self.buildings.get(n.id).kind if n.id in self.buildings else None),
                           "owner": (self.buildings.get(n.id).owner if n.id in self.buildings else None)} for n in self.board.nodes],
                "edges": [{"id": e.id, "a": e.a, "b": e.b, "owner": (self.roads.get(e.id).owner if e.id in self.roads else None)} for e in self.board.edges],
                "hexes": [{"id": h.id, "cx": h.cx, "cy": h.cy, "res": h.res, "num": h.num} for h in self.board.hexes],
            },
            "offers": [{"id": o.id, "from": o.from_id, "to": o.to_id, "give": o.give, "get": o.get, "status": o.status} for o in self.offers],
        }

        p = self.get_player(pid)
        priv = {
            "resources": p.resources,
            "vp_cards": p.vp_cards,
            "dev_hand": p.dev_hand,
            "dev_new": p.dev_new,
        }

        hints = self.hints(pid)
        return pub, priv, hints

    def hints(self, pid: str) -> dict:
        if self.phase == "lobby":
            return {"can_start": self.can_start(pid), "players_needed": max(0, 2-len(self.players))}

        if self.phase == "setup":
            if pid != self.current:
                return {"expected": "wait_setup"}
            nodes = self.setup_valid_nodes(pid)
            return {"expected": "place", "valid_nodes": nodes, "note": "Select a node, then an adjacent edge, then press Place."}

        if self.phase == "main":
            if pid != self.current:
                return {"expected": "wait_turn"}

            h = {"expected": "roll_or_play", "must_roll": (not self.rolled)}
            if self.rolled:
                h["build"] = "Select node/edge then use Build buttons"
                h["trade"] = "Offer trade to player or All"
            return h

        if self.phase == "over":
            return {"expected": "game_over", "winner": self.winner}

        return {}
