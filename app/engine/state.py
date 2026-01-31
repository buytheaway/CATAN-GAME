from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set


RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"]

TERRAIN_TO_RES = {
    "forest": "wood",
    "hills": "brick",
    "pasture": "sheep",
    "fields": "wheat",
    "mountains": "ore",
    "desert": None,
    "gold": None,
    "sea": None,
}

COST = {
    "road": {"wood": 1, "brick": 1},
    "ship": {"wood": 1, "sheep": 1},
    "settlement": {"wood": 1, "brick": 1, "sheep": 1, "wheat": 1},
    "city": {"wheat": 2, "ore": 3},
    "dev": {"sheep": 1, "wheat": 1, "ore": 1},
}

DEV_TYPES = ["knight", "victory_point", "road_building", "year_of_plenty", "monopoly"]


@dataclass
class TradeOffer:
    offer_id: int
    from_pid: int
    to_pid: Optional[int]
    give: Dict[str, int]
    get: Dict[str, int]
    status: str = "active"
    created_turn: int = 0
    created_tick: int = 0


@dataclass
class Tile:
    q: int
    r: int
    terrain: str
    number: Optional[int]
    center: Tuple[float, float]


@dataclass
class PlayerState:
    pid: int
    name: str
    res: Dict[str, int] = field(default_factory=lambda: {r: 0 for r in RESOURCES})
    vp: int = 0
    knights_played: int = 0
    dev_cards: List[dict] = field(default_factory=list)


@dataclass
class AchievementState:
    longest_road_owner: Optional[int] = None
    longest_road_len: int = 0
    largest_army_owner: Optional[int] = None
    largest_army_size: int = 0


@dataclass
class RulesConfig:
    target_vp: int = 10
    max_roads: int = 15
    max_settlements: int = 5
    max_cities: int = 4
    robber_count: int = 1
    enable_seafarers: bool = False
    max_ships: int = 15
    enable_pirate: bool = False
    enable_gold: bool = False
    enable_move_ship: bool = False


@dataclass
class BoardState:
    tiles: List[Tile] = field(default_factory=list)
    vertices: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    vertex_adj_hexes: Dict[int, List[int]] = field(default_factory=dict)
    edges: Set[Tuple[int, int]] = field(default_factory=set)
    edge_adj_hexes: Dict[Tuple[int, int], List[int]] = field(default_factory=dict)
    ports: List[Tuple[Tuple[int, int], str]] = field(default_factory=list)
    occupied_v: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    occupied_e: Dict[Tuple[int, int], int] = field(default_factory=dict)
    occupied_ships: Dict[Tuple[int, int], int] = field(default_factory=dict)


@dataclass
class GameState:
    seed: int
    size: float = 58.0
    max_players: int = 4
    map_name: str = "base_standard"
    map_id: str = "base_standard"
    map_meta: Dict[str, Any] = field(default_factory=dict)
    rules: Dict[str, Any] = field(default_factory=dict)
    rules_config: RulesConfig = field(default_factory=RulesConfig)
    board: BoardState = field(default_factory=BoardState)
    players: List[PlayerState] = field(default_factory=list)
    bank: Dict[str, int] = field(default_factory=lambda: {r: 19 for r in RESOURCES})

    turn: int = 0
    phase: str = "setup"
    rolled: bool = False
    setup_order: List[int] = field(default_factory=list)
    setup_idx: int = 0
    setup_need: str = "settlement"
    setup_anchor_vid: Optional[int] = None
    last_roll: Optional[int] = None

    robber_tile: int = 0
    robbers: List[int] = field(default_factory=list)
    pirate_tile: Optional[int] = None
    pending_action: Optional[str] = None
    pending_pid: Optional[int] = None
    pending_victims: List[int] = field(default_factory=list)
    discard_required: Dict[int, int] = field(default_factory=dict)
    discard_submitted: Set[int] = field(default_factory=set)
    pending_gold: Dict[int, int] = field(default_factory=dict)
    pending_gold_queue: List[int] = field(default_factory=list)

    achievements: AchievementState = field(default_factory=AchievementState)
    game_over: bool = False
    winner_pid: Optional[int] = None

    dev_deck: List[str] = field(default_factory=list)
    dev_played_turn: Dict[int, bool] = field(default_factory=dict)
    free_roads: Dict[int, int] = field(default_factory=dict)
    roll_history: List[int] = field(default_factory=list)

    tick: int = 0
    state_version: int = 1
    trade_offers: List[TradeOffer] = field(default_factory=list)
    trade_offer_next_id: int = 1

    def dev_summary(self, pid: int) -> Dict[str, int]:
        counts = {k: 0 for k in DEV_TYPES}
        for c in self.players[pid].dev_cards:
            t = str(c.get("type", "")).strip().lower() if isinstance(c, dict) else str(c).strip().lower()
            if t in counts:
                counts[t] += 1
        return counts

    def _get_player_res_dict(self, pid: int) -> Dict[str, int]:
        return self.players[pid].res

    @property
    def tiles(self) -> List[Tile]:
        return self.board.tiles

    @tiles.setter
    def tiles(self, value: List[Tile]) -> None:
        self.board.tiles = value

    @property
    def vertices(self) -> Dict[int, Tuple[float, float]]:
        return self.board.vertices

    @vertices.setter
    def vertices(self, value: Dict[int, Tuple[float, float]]) -> None:
        self.board.vertices = value

    @property
    def vertex_adj_hexes(self) -> Dict[int, List[int]]:
        return self.board.vertex_adj_hexes

    @vertex_adj_hexes.setter
    def vertex_adj_hexes(self, value: Dict[int, List[int]]) -> None:
        self.board.vertex_adj_hexes = value

    @property
    def edges(self) -> Set[Tuple[int, int]]:
        return self.board.edges

    @edges.setter
    def edges(self, value: Set[Tuple[int, int]]) -> None:
        self.board.edges = value

    @property
    def edge_adj_hexes(self) -> Dict[Tuple[int, int], List[int]]:
        return self.board.edge_adj_hexes

    @edge_adj_hexes.setter
    def edge_adj_hexes(self, value: Dict[Tuple[int, int], List[int]]) -> None:
        self.board.edge_adj_hexes = value

    @property
    def ports(self) -> List[Tuple[Tuple[int, int], str]]:
        return self.board.ports

    @ports.setter
    def ports(self, value: List[Tuple[Tuple[int, int], str]]) -> None:
        self.board.ports = value

    @property
    def occupied_v(self) -> Dict[int, Tuple[int, int]]:
        return self.board.occupied_v

    @occupied_v.setter
    def occupied_v(self, value: Dict[int, Tuple[int, int]]) -> None:
        self.board.occupied_v = value

    @property
    def occupied_e(self) -> Dict[Tuple[int, int], int]:
        return self.board.occupied_e

    @occupied_e.setter
    def occupied_e(self, value: Dict[Tuple[int, int], int]) -> None:
        self.board.occupied_e = value

    @property
    def occupied_ships(self) -> Dict[Tuple[int, int], int]:
        return self.board.occupied_ships

    @occupied_ships.setter
    def occupied_ships(self, value: Dict[Tuple[int, int], int]) -> None:
        self.board.occupied_ships = value

    @property
    def longest_road_owner(self) -> Optional[int]:
        return self.achievements.longest_road_owner

    @longest_road_owner.setter
    def longest_road_owner(self, value: Optional[int]) -> None:
        self.achievements.longest_road_owner = value

    @property
    def longest_road_len(self) -> int:
        return self.achievements.longest_road_len

    @longest_road_len.setter
    def longest_road_len(self, value: int) -> None:
        self.achievements.longest_road_len = int(value)

    @property
    def largest_army_owner(self) -> Optional[int]:
        return self.achievements.largest_army_owner

    @largest_army_owner.setter
    def largest_army_owner(self, value: Optional[int]) -> None:
        self.achievements.largest_army_owner = value

    @property
    def largest_army_size(self) -> int:
        return self.achievements.largest_army_size

    @largest_army_size.setter
    def largest_army_size(self, value: int) -> None:
        self.achievements.largest_army_size = int(value)
