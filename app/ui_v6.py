import sys, math, random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set

from PySide6 import QtCore, QtGui, QtWidgets
from app.dev_hand_overlay import attach_dev_hand_overlay
from app.dev_ui import DevDialog
from app.trade_ui import TradeDialog
from app.config import GameConfig
from app.assets_loader import load_svg
from app.theme import get_ui_palette, get_player_colors

# -------------------- Geometry (pointy-top, Colonist-like) --------------------
SQRT3 = 1.7320508075688772

def axial_to_pixel(q: int, r: int, size: float) -> QtCore.QPointF:
    # pointy-top axial
    x = size * SQRT3 * (q + r / 2.0)
    y = size * 1.5 * r
    return QtCore.QPointF(x, y)

def hex_corners(center: QtCore.QPointF, size: float) -> List[QtCore.QPointF]:
    # pointy-top corners (30 deg start)
    pts = []
    for i in range(6):
        ang = math.radians(30 + 60 * i)
        pts.append(QtCore.QPointF(
            center.x() + size * math.cos(ang),
            center.y() + size * math.sin(ang),
        ))
    return pts

def quant_key(p: QtCore.QPointF, step: float = 0.5) -> Tuple[int, int]:
    # merge vertices across hexes reliably
    return (int(round(p.x() / step)), int(round(p.y() / step)))

# Base board axial coords: rows 3-4-5-4-3
BASE_AXIAL: List[Tuple[int,int]] = (
    [(0,-2),(1,-2),(2,-2)] +
    [(-1,-1),(0,-1),(1,-1),(2,-1)] +
    [(-2,0),(-1,0),(0,0),(1,0),(2,0)] +
    [(-2,1),(-1,1),(0,1),(1,1)] +
    [(-2,2),(-1,2),(0,2)]
)

RESOURCES = ["wood","brick","sheep","wheat","ore"]
TERRAIN_TO_RES = {
    "forest": "wood",
    "hills": "brick",
    "pasture": "sheep",
    "fields": "wheat",
    "mountains": "ore",
    "desert": None,
}
TERRAIN_COLOR: Dict[str, str] = {}
RESOURCE_COLORS: Dict[str, str] = {}

# Global palette (updated in MainWindow.__init__)
PALETTE = get_ui_palette()
PLAYER_COLORS = get_player_colors()
BG = PALETTE["ui_bg"]
PANEL = PALETTE["ui_panel"]
ACCENT = PALETTE["ui_accent"]
TEXT = PALETTE["text"]

def set_ui_palette(theme_name: str) -> None:
    global PALETTE, BG, PANEL, ACCENT, TEXT, TERRAIN_COLOR, RESOURCE_COLORS, PLAYER_COLORS
    PALETTE = get_ui_palette(theme_name)
    PLAYER_COLORS = get_player_colors()
    BG = PALETTE["ui_bg"]
    PANEL = PALETTE["ui_panel"]
    ACCENT = PALETTE["ui_accent"]
    TEXT = PALETTE["text"]
    TERRAIN_COLOR = {
        "forest": PALETTE["terrain_forest"],
        "hills": PALETTE["terrain_hills"],
        "pasture": PALETTE["terrain_pasture"],
        "fields": PALETTE["terrain_fields"],
        "mountains": PALETTE["terrain_mountains"],
        "desert": PALETTE["terrain_desert"],
    }
    RESOURCE_COLORS = {
        "wood": PALETTE["res_wood"],
        "brick": PALETTE["res_brick"],
        "sheep": PALETTE["res_sheep"],
        "wheat": PALETTE["res_wheat"],
        "ore": PALETTE["res_ore"],
        "any": PALETTE["res_any"],
    }

set_ui_palette("midnight")

def _normalize_port_kind(kind: Optional[str]) -> Optional[str]:
    if kind is None:
        return None
    s = str(kind).strip().lower()
    if s in RESOURCES:
        return s
    if s in ("3:1", "3", "generic", "any", "all", "none", "?"):
        return "3:1"
    if "3:1" in s or "3/1" in s or "3 to 1" in s or "3to1" in s:
        return "3:1"
    for r in RESOURCES:
        if r in s:
            return r
    return None


def _iter_ports(ports):
    for p in ports:
        a = b = kind = None
        if isinstance(p, dict):
            kind = p.get("kind")
            a = p.get("a", p.get("v1"))
            b = p.get("b", p.get("v2"))
        elif isinstance(p, (tuple, list)) and len(p) == 2:
            edge, kind = p
            if isinstance(edge, (tuple, list)) and len(edge) == 2:
                a, b = edge
        if a is None or b is None:
            continue
        try:
            a = int(a)
            b = int(b)
        except Exception:
            continue
        yield a, b, kind

# pips like Colonist (2/12=1 ... 6/8=5)
PIPS = {2:1,3:2,4:3,5:4,6:5,8:5,9:4,10:3,11:2,12:1}
BOT_LOG = False

def make_resource_icon(name: str, size: int = 36) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    bg = RESOURCE_COLORS.get(name, PALETTE["res_default"])

    # rounded rect
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(2,2,size-4,size-4), 10, 10)
    p.fillPath(path, QtGui.QColor(bg))

    # simple white glyph (not copyrighted)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(PALETTE["ui_outline_dark"]))

    if name == "wood":
        # tree
        p.drawEllipse(QtCore.QRectF(size*0.30, size*0.20, size*0.40, size*0.40))
        p.drawRect(QtCore.QRectF(size*0.47, size*0.55, size*0.06, size*0.25))
    elif name == "brick":
        # bricks
        p.drawRect(QtCore.QRectF(size*0.20, size*0.28, size*0.60, size*0.18))
        p.drawRect(QtCore.QRectF(size*0.20, size*0.52, size*0.60, size*0.18))
    elif name == "sheep":
        # sheep blob
        p.drawEllipse(QtCore.QRectF(size*0.22, size*0.32, size*0.56, size*0.40))
        p.drawEllipse(QtCore.QRectF(size*0.18, size*0.44, size*0.18, size*0.18))
    elif name == "wheat":
        # wheat stalk
        pen = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_dark"]), 3)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(int(size*0.50), int(size*0.22), int(size*0.50), int(size*0.80))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(PALETTE["ui_outline_dark"]))
        for k in range(5):
            y = size*(0.30 + k*0.10)
            p.drawEllipse(QtCore.QRectF(size*0.52, y, size*0.12, size*0.07))
            p.drawEllipse(QtCore.QRectF(size*0.36, y, size*0.12, size*0.07))
    elif name == "ore":
        # rock
        poly = QtGui.QPolygonF([
            QtCore.QPointF(size*0.28, size*0.65),
            QtCore.QPointF(size*0.40, size*0.28),
            QtCore.QPointF(size*0.62, size*0.25),
            QtCore.QPointF(size*0.76, size*0.55),
            QtCore.QPointF(size*0.56, size*0.78),
        ])
        p.drawPolygon(poly)
    else:
        p.drawEllipse(QtCore.QRectF(size*0.28, size*0.28, size*0.44, size*0.44))

    p.end()
    return pm

def resource_icon_pixmap(name: str, size: int = 28) -> QtGui.QPixmap:
    renderer = load_svg(f"icons/{name}.svg")
    if not renderer.isValid():
        return make_resource_icon(name, size)
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    renderer.render(p, QtCore.QRectF(0, 0, size, size))
    p.end()
    return pm

def dice_face(n: int, size: int = 42) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    # card
    rect = QtCore.QRectF(1,1,size-2,size-2)
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, 10, 10)
    p.fillPath(path, QtGui.QColor(PALETTE["ui_token_bg"]))
    p.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_dark"]), 2))
    p.drawPath(path)
    # pips
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(PALETTE["ui_outline_dark"]))
    def dot(x,y):
        r = size*0.07
        p.drawEllipse(QtCore.QRectF(x-r, y-r, 2*r, 2*r))
    cx, cy = size/2, size/2
    off = size*0.18
    pos = {
        1:[(cx,cy)],
        2:[(cx-off,cy-off),(cx+off,cy+off)],
        3:[(cx-off,cy-off),(cx,cy),(cx+off,cy+off)],
        4:[(cx-off,cy-off),(cx+off,cy-off),(cx-off,cy+off),(cx+off,cy+off)],
        5:[(cx-off,cy-off),(cx+off,cy-off),(cx,cy),(cx-off,cy+off),(cx+off,cy+off)],
        6:[(cx-off,cy-off),(cx+off,cy-off),(cx-off,cy),(cx+off,cy),(cx-off,cy+off),(cx+off,cy+off)],
    }[n]
    for x,y in pos: dot(x,y)
    p.end()
    return pm

def make_action_icon(name: str, size: int = 34) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    fg = QtGui.QColor(PALETTE["ui_action_icon"])
    stroke = QtGui.QPen(fg, 2)
    p.setPen(stroke)
    p.setBrush(fg)
    pad = size * 0.18

    if name == "road":
        rect = QtCore.QRectF(pad, size*0.55, size-pad*2, size*0.2)
        p.save()
        p.translate(size/2, size/2)
        p.rotate(-20)
        p.translate(-size/2, -size/2)
        p.drawRoundedRect(rect, 4, 4)
        p.restore()
    elif name == "settlement":
        base = QtGui.QPolygonF([
            QtCore.QPointF(size*0.25, size*0.65),
            QtCore.QPointF(size*0.75, size*0.65),
            QtCore.QPointF(size*0.75, size*0.85),
            QtCore.QPointF(size*0.25, size*0.85),
        ])
        roof = QtGui.QPolygonF([
            QtCore.QPointF(size*0.22, size*0.65),
            QtCore.QPointF(size*0.5, size*0.35),
            QtCore.QPointF(size*0.78, size*0.65),
        ])
        p.drawPolygon(base)
        p.drawPolygon(roof)
    elif name == "city":
        p.drawRoundedRect(QtCore.QRectF(size*0.22, size*0.48, size*0.56, size*0.32), 4, 4)
        p.drawRect(QtCore.QRectF(size*0.32, size*0.3, size*0.36, size*0.2))
    elif name == "dev":
        p.drawRoundedRect(QtCore.QRectF(size*0.28, size*0.2, size*0.42, size*0.6), 6, 6)
        p.drawRoundedRect(QtCore.QRectF(size*0.18, size*0.3, size*0.42, size*0.6), 6, 6)
    else:  # trade
        p.setPen(QtGui.QPen(fg, 2))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawArc(QtCore.QRectF(size*0.18, size*0.2, size*0.5, size*0.5), 30*16, 200*16)
        p.drawArc(QtCore.QRectF(size*0.32, size*0.35, size*0.5, size*0.5), 210*16, 200*16)
        p.setBrush(fg)
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(size*0.62, size*0.2),
            QtCore.QPointF(size*0.78, size*0.24),
            QtCore.QPointF(size*0.66, size*0.34),
        ]))
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(size*0.26, size*0.8),
            QtCore.QPointF(size*0.12, size*0.76),
            QtCore.QPointF(size*0.24, size*0.66),
        ]))

    p.end()
    return pm

# -------------------- Game (minimal, enough for UI correctness) --------------------
@dataclass
class HexTile:
    q: int
    r: int
    terrain: str
    number: Optional[int]
    center: QtCore.QPointF

@dataclass
class Player:
    name: str
    color: QtGui.QColor
    res: Dict[str,int] = field(default_factory=lambda: {k:0 for k in RESOURCES})
    vp: int = 0
    dev_cards: List[dict] = field(default_factory=list)  # [{"type": str, "new": bool}]
    knights_played: int = 0

@dataclass
class Game:
    seed: int
    size: float = 58.0  # map scale
    tiles: List[HexTile] = field(default_factory=list)
    # geometry:
    vertices: Dict[int, QtCore.QPointF] = field(default_factory=dict)          # vid -> point
    vertex_adj_hexes: Dict[int, List[int]] = field(default_factory=dict)       # vid -> tile indices
    edges: Set[Tuple[int,int]] = field(default_factory=set)                    # (a,b)
    edge_adj_hexes: Dict[Tuple[int,int], List[int]] = field(default_factory=dict)

    # state:
    players: List[Player] = field(default_factory=list)
    bank: Dict[str,int] = field(default_factory=lambda: {k:19 for k in RESOURCES})
    occupied_v: Dict[int, Tuple[int,int]] = field(default_factory=dict)        # vid -> (pid, level 1/2)
    occupied_e: Dict[Tuple[int,int], int] = field(default_factory=dict)        # (a,b)-> pid

    turn: int = 0
    phase: str = "setup"  # setup/main
    rolled: bool = False

    setup_order: List[int] = field(default_factory=lambda: [0,1,1,0])
    setup_idx: int = 0
    setup_need: str = "settlement"  # settlement/road
    setup_anchor_vid: Optional[int] = None
    last_roll: Optional[int] = None

    ports: List[Tuple[Tuple[int,int], str]] = field(default_factory=list)      # (edge, "3:1"/"2:1:wood"...)
    robber_tile: int = 0
    pending_action: Optional[str] = None   # "discard" | "robber_move" | "robber_steal" | None
    pending_pid: Optional[int] = None
    pending_victims: List[int] = field(default_factory=list)
    longest_road_owner: Optional[int] = None
    longest_road_len: int = 0
    game_over: bool = False
    winner_pid: Optional[int] = None
    roll_history: List[int] = field(default_factory=list)
    dev_deck: List[str] = field(default_factory=list)
    dev_played_turn: Dict[int, bool] = field(default_factory=dict)
    free_roads: Dict[int, int] = field(default_factory=dict)
    largest_army_pid: Optional[int] = None
    largest_army_size: int = 0

    def dev_summary(self, pid: int) -> Dict[str,int]:
        counts = {k: 0 for k in ["knight","victory_point","road_building","year_of_plenty","monopoly"]}
        for c in self.players[pid].dev_cards:
            if isinstance(c, dict):
                t = str(c.get("type", "")).strip().lower()
            else:
                t = str(c).strip().lower()
            if t in counts:
                counts[t] += 1
        return counts

    def _get_player_res_dict(self, pid: int) -> Dict[str, int]:
        return self.players[pid].res

    def player_ports(self, pid: int) -> set:
        owned = {vid for vid, (owner, _lvl) in self.occupied_v.items() if owner == pid}
        ports = set()
        for a, b, kind in _iter_ports(self.ports):
            if a in owned or b in owned:
                norm = _normalize_port_kind(kind)
                if norm:
                    ports.add(norm)
        return ports

    def best_trade_rate(self, pid: int, give_res: str) -> int:
        ports = self.player_ports(pid)
        give_res = str(give_res).strip().lower()
        if give_res in ports:
            return 2
        if "3:1" in ports:
            return 3
        return 4

    def trade_with_bank(self, pid: int, give_res: str, get_res: str, get_qty: int) -> int:
        if self.game_over:
            raise ValueError("Game over.")
        if self.phase != "main" or pid != self.turn:
            raise ValueError("Not your turn.")
        give_res = str(give_res).strip().lower()
        get_res = str(get_res).strip().lower()
        if give_res == get_res:
            raise ValueError("Give and Get must be different.")
        if give_res not in RESOURCES or get_res not in RESOURCES:
            raise ValueError("Invalid resource.")
        qty = int(get_qty)
        if qty <= 0:
            raise ValueError("Invalid quantity.")
        rate = self.best_trade_rate(pid, give_res)
        give_qty = rate * qty
        pres = self._get_player_res_dict(pid)
        if pres.get(give_res, 0) < give_qty:
            raise ValueError("Not enough resources.")
        if self.bank.get(get_res, 0) < qty:
            raise ValueError("Bank has not enough resources.")
        pres[give_res] -= give_qty
        pres[get_res] += qty
        self.bank[give_res] += give_qty
        self.bank[get_res] -= qty
        return rate

    def _find_dev_idx(self, pid: int, card_type: str, allow_new: bool = False) -> Optional[int]:
        card_type = str(card_type).strip().lower()
        cards = self.players[pid].dev_cards
        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                continue
            if str(c.get("type", "")).strip().lower() == card_type and (allow_new or not c.get("new", False)):
                return i
        if allow_new:
            for i, c in enumerate(cards):
                if isinstance(c, dict) and str(c.get("type", "")).strip().lower() == card_type:
                    return i
        return None

    def _clear_dev_new_flags(self, pid: int) -> None:
        for c in self.players[pid].dev_cards:
            if isinstance(c, dict) and c.get("new", False):
                c["new"] = False

    def end_turn_cleanup(self, pid: int) -> None:
        self._clear_dev_new_flags(pid)
        self.dev_played_turn[pid] = False

    def _update_largest_army(self) -> None:
        sizes = [p.knights_played for p in self.players]
        max_k = max(sizes) if sizes else 0
        if max_k < 3:
            if self.largest_army_pid is not None:
                self.players[self.largest_army_pid].vp -= 2
            self.largest_army_pid = None
            self.largest_army_size = 0
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_log"):
                check_win(self, ui._log)
            return

        leaders = [i for i,k in enumerate(sizes) if k == max_k]
        if len(leaders) != 1:
            if self.largest_army_pid is not None:
                self.players[self.largest_army_pid].vp -= 2
            self.largest_army_pid = None
            self.largest_army_size = max_k
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_log"):
                check_win(self, ui._log)
            return

        leader = leaders[0]
        if leader == self.largest_army_pid:
            self.largest_army_size = max_k
            return

        if self.largest_army_pid is not None:
            self.players[self.largest_army_pid].vp -= 2
        self.largest_army_pid = leader
        self.largest_army_size = max_k
        self.players[leader].vp += 2
        ui = getattr(self, "ui", None)
        if ui and hasattr(ui, "_log"):
            check_win(self, ui._log)

    def buy_dev(self, pid: int) -> str:
        if self.game_over:
            raise ValueError("Game over.")
        if self.phase != "main" or pid != self.turn:
            raise ValueError("Not your turn.")
        if not self.dev_deck:
            raise ValueError("Dev deck is empty.")
        cost = COST["dev"]
        if not can_pay(self.players[pid], cost):
            raise ValueError("Not enough resources for dev card.")
        pay_to_bank(self, pid, cost)
        card = self.dev_deck.pop()
        self.players[pid].dev_cards.append({"type": card, "new": True})
        if card == "victory_point":
            self.players[pid].vp += 1
        ui = getattr(self, "ui", None)
        if ui and hasattr(ui, "_sync_ui"):
            check_win(self, ui._log if hasattr(ui, "_log") else None)
            ui._sync_ui()
        return card

    def play_dev(self, pid: int, card_type: str, **kwargs):
        card_type = str(card_type).strip().lower()
        if self.game_over:
            raise ValueError("Game over.")
        if self.phase != "main" or pid != self.turn:
            raise ValueError("Not your turn.")
        if self.dev_played_turn.get(pid, False):
            raise ValueError("Already played a dev card this turn.")
        if card_type == "victory_point":
            raise ValueError("Victory Point cards are passive.")

        idx = self._find_dev_idx(pid, card_type, allow_new=False)
        if idx is None:
            raise ValueError("Cannot play this card now (new or missing).")
        card = self.players[pid].dev_cards.pop(idx)
        self.dev_played_turn[pid] = True

        if card_type == "knight":
            self.players[pid].knights_played += 1
            self._update_largest_army()
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_start_robber_flow"):
                ui._start_robber_flow(pid, reason="knight")
            else:
                self.pending_action = "robber_move"
                self.pending_pid = pid
                self.pending_victims = []
            return {"played": "knight"}

        if card_type == "road_building":
            self.free_roads[pid] = int(self.free_roads.get(pid, 0)) + 2
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_start_free_roads"):
                ui._start_free_roads(pid)
            return {"played": "road_building"}

        if card_type == "year_of_plenty":
            a = str(kwargs.get("a", "wood")).lower()
            b = str(kwargs.get("b", "brick")).lower()
            qa = int(kwargs.get("qa", 1))
            qb = int(kwargs.get("qb", 1))
            if a not in RESOURCES or b not in RESOURCES:
                raise ValueError("Bad resources.")
            if qa < 0 or qb < 0 or qa + qb != 2:
                raise ValueError("Year of Plenty must give exactly 2 resources total.")
            if self.bank.get(a, 0) < qa or self.bank.get(b, 0) < qb:
                raise ValueError("Bank doesn't have enough resources.")
            self.bank[a] -= qa
            self.bank[b] -= qb
            self.players[pid].res[a] += qa
            self.players[pid].res[b] += qb
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_sync_ui"):
                ui._sync_ui()
            return {"played": "year_of_plenty"}

        if card_type == "monopoly":
            r = str(kwargs.get("r", "wood")).lower()
            if r not in RESOURCES:
                raise ValueError("Bad resource.")
            taken = 0
            for opid, op in enumerate(self.players):
                if opid == pid:
                    continue
                q = int(op.res.get(r, 0))
                if q > 0:
                    op.res[r] -= q
                    taken += q
            self.players[pid].res[r] += taken
            ui = getattr(self, "ui", None)
            if ui and hasattr(ui, "_sync_ui"):
                ui._sync_ui()
            return {"played": "monopoly", "taken": taken}

        # fallback
        self.players[pid].dev_cards.append(card)
        self.dev_played_turn[pid] = False
        raise ValueError("Unknown dev card.")

def build_board(seed: int, size: float) -> Game:
    rng = random.Random(seed)
    g = Game(seed=seed, size=size)

    terrains = (
        ["forest"]*4 + ["hills"]*3 + ["pasture"]*4 + ["fields"]*4 + ["mountains"]*3 + ["desert"]*1
    )
    rng.shuffle(terrains)

    numbers = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]
    rng.shuffle(numbers)

    tiles: List[HexTile] = []
    desert_idx = None
    ni = 0
    for (q,r), terr in zip(BASE_AXIAL, terrains):
        c = axial_to_pixel(q,r,size)
        num = None
        if terr != "desert":
            num = numbers[ni]; ni += 1
        else:
            desert_idx = len(tiles)
        tiles.append(HexTile(q=q,r=r,terrain=terr,number=num,center=c))
    g.tiles = tiles
    g.robber_tile = desert_idx if desert_idx is not None else 0
    g.pending_action = None
    g.pending_pid = None
    g.pending_victims = []

    # geometry build (global vertex merge)
    v_map: Dict[Tuple[int,int], int] = {}
    v_points: List[QtCore.QPointF] = []
    v_hexes: Dict[int, List[int]] = {}
    edges: Set[Tuple[int,int]] = set()
    edge_hexes: Dict[Tuple[int,int], List[int]] = {}

    for ti, t in enumerate(tiles):
        corners = hex_corners(t.center, size)
        vids = []
        for p in corners:
            k = quant_key(p, 0.5)
            if k not in v_map:
                vid = len(v_points)
                v_map[k] = vid
                v_points.append(p)
                v_hexes[vid] = []
            vid = v_map[k]
            vids.append(vid)
            v_hexes[vid].append(ti)

        # edges (vid pairs)
        for i in range(6):
            a = vids[i]
            b = vids[(i+1) % 6]
            e = (a,b) if a < b else (b,a)
            edges.add(e)
            edge_hexes.setdefault(e, []).append(ti)

    g.vertices = {i:p for i,p in enumerate(v_points)}
    g.vertex_adj_hexes = v_hexes
    g.edges = edges
    g.edge_adj_hexes = edge_hexes

    # ports: choose 9 coast edges (edges with 1 adjacent hex) evenly by angle
    coast = [e for e,hx in edge_hexes.items() if len(hx)==1]
    center = QtCore.QPointF(0,0)
    def angle_of_edge(e):
        a,b = e
        p = (g.vertices[a] + g.vertices[b]) * 0.5
        return math.atan2(p.y()-center.y(), p.x()-center.x())
    coast.sort(key=angle_of_edge)

    if len(coast) >= 9:
        pick_idx = [int(i * len(coast)/9) for i in range(9)]
        coast9 = [coast[i % len(coast)] for i in pick_idx]
    else:
        coast9 = coast

    port_types = ["3:1"]*4 + [f"2:1:{r}" for r in RESOURCES]
    rng.shuffle(port_types)
    port_types = port_types[:len(coast9)]
    g.ports = list(zip(coast9, port_types))
    for edge, kind in g.ports:
        if not (isinstance(edge, tuple) and len(edge) == 2 and all(isinstance(v, int) for v in edge)):
            raise ValueError(f"Port edge must be (int,int), got: {edge!r}")
        if not isinstance(kind, str):
            raise ValueError(f"Port kind must be str, got: {kind!r}")

    # players
    g.players = [
        Player("You", QtGui.QColor(PLAYER_COLORS[0])),
        Player("Bot", QtGui.QColor(PLAYER_COLORS[1])),
    ]

    dev_deck = (
        ["knight"] * 14 +
        ["victory_point"] * 5 +
        ["road_building"] * 2 +
        ["year_of_plenty"] * 2 +
        ["monopoly"] * 2
    )
    rng.shuffle(dev_deck)
    g.dev_deck = dev_deck
    return g

def edge_neighbors_of_vertex(edges: Set[Tuple[int,int]], vid: int) -> Set[int]:
    out = set()
    for a,b in edges:
        if a == vid: out.add(b)
        elif b == vid: out.add(a)
    return out

def can_place_settlement(g: Game, pid: int, vid: int, require_road: bool) -> bool:
    if vid in g.occupied_v:
        return False
    # distance rule: no adjacent vertex occupied
    for nb in edge_neighbors_of_vertex(g.edges, vid):
        if nb in g.occupied_v:
            return False
    if not require_road:
        return True
    # must connect to own road
    for e in g.edges:
        if vid in e and g.occupied_e.get(e) == pid:
            return True
    return False

def can_place_road(g: Game, pid: int, e: Tuple[int,int], must_touch_vid: Optional[int]=None) -> bool:
    if e in g.occupied_e:
        return False
    a,b = e
    if must_touch_vid is not None and (a != must_touch_vid and b != must_touch_vid):
        return False
    # must connect to own settlement/city or road
    for v in (a,b):
        occ = g.occupied_v.get(v)
        if occ and occ[0] == pid:
            return True
    # connect to own road
    for ee, owner in g.occupied_e.items():
        if owner == pid and (a in ee or b in ee):
            return True
    return False

def can_upgrade_city(g: Game, pid: int, vid: int) -> bool:
    occ = g.occupied_v.get(vid)
    return bool(occ and occ[0]==pid and occ[1]==1)

def distribute_for_roll(g: Game, roll: int, log_cb):
    for vid,(pid,level) in g.occupied_v.items():
        for ti in g.vertex_adj_hexes.get(vid, []):
            t = g.tiles[ti]
            if t.number != roll:
                continue
            if ti == g.robber_tile:
                continue
            res = TERRAIN_TO_RES[t.terrain]
            if not res:
                continue
            amount = 2 if level==2 else 1
            # bank limit
            give = min(amount, g.bank[res])
            if give <= 0:
                continue
            g.bank[res] -= give
            g.players[pid].res[res] += give
    log_cb(f"[ROLL] distributed resources for {roll} (bank limits applied).")

COST = {
    "road": {"wood":1, "brick":1},
    "settlement": {"wood":1, "brick":1, "sheep":1, "wheat":1},
    "city": {"wheat":2, "ore":3},
    "dev": {"sheep":1, "wheat":1, "ore":1},
}
def can_pay(p: Player, cost: Dict[str,int]) -> bool:
    return all(p.res[k] >= v for k,v in cost.items())
def pay_to_bank(g: Game, pid: int, cost: Dict[str,int]):
    p = g.players[pid]
    for k,v in cost.items():
        p.res[k] -= v
        g.bank[k] += v

def _vertex_owner(g: Game, vid: int) -> Optional[int]:
    if vid in g.occupied_v:
        return g.occupied_v[vid][0]
    return None

def _is_blocked_vertex(g: Game, vid: int, pid: int) -> bool:
    owner = _vertex_owner(g, vid)
    return owner is not None and owner != pid

def longest_road_length(g: Game, pid: int) -> int:
    road_edges = [e for e, owner in g.occupied_e.items() if owner == pid]
    if not road_edges:
        return 0

    adj: Dict[int, List[Tuple[int,int]]] = {}
    for e in road_edges:
        a, b = e
        adj.setdefault(a, []).append(e)
        adj.setdefault(b, []).append(e)

    def dfs(v: int, used: set[Tuple[int,int]], came_from: Optional[Tuple[int,int]]) -> int:
        if _is_blocked_vertex(g, v, pid) and came_from is not None:
            return 0
        best = 0
        for e in adj.get(v, []):
            if e in used:
                continue
            a, b = e
            nxt = b if a == v else a
            used.add(e)
            best = max(best, 1 + dfs(nxt, used, e))
            used.remove(e)
        return best

    ans = 0
    for v in adj.keys():
        ans = max(ans, dfs(v, set(), None))
    return ans

def update_longest_road(g: Game, log_cb=None) -> None:
    l0 = longest_road_length(g, 0)
    l1 = longest_road_length(g, 1)
    new_owner = None
    new_len = 0
    if l0 >= 5 and l0 > l1:
        new_owner, new_len = 0, l0
    elif l1 >= 5 and l1 > l0:
        new_owner, new_len = 1, l1

    if new_owner == g.longest_road_owner and new_len == g.longest_road_len:
        return

    if g.longest_road_owner is not None and new_owner != g.longest_road_owner:
        g.players[g.longest_road_owner].vp -= 2

    if new_owner is not None and new_owner != g.longest_road_owner:
        g.players[new_owner].vp += 2

    g.longest_road_owner = new_owner
    g.longest_road_len = new_len

    if log_cb:
        if new_owner is None:
            log_cb("Longest Road: none")
        else:
            log_cb(f"Longest Road: P{new_owner} (len {new_len})")

def check_win(g: Game, log_cb=None) -> None:
    if g.game_over:
        return
    for i, p in enumerate(g.players):
        if p.vp >= 10:
            g.game_over = True
            g.winner_pid = i
            if log_cb:
                log_cb(f"Game over. Winner: P{i}")
            return

def expected_vertex_yield(g: Game, vid: int, pid: int) -> int:
    score = 0
    for ti in g.vertex_adj_hexes.get(vid, []):
        if ti == g.robber_tile:
            continue
        t = g.tiles[ti]
        if t.number is None:
            continue
        res = TERRAIN_TO_RES.get(t.terrain)
        if not res:
            continue
        score += PIPS.get(t.number, 0)
    return score

def choose_best_city(g: Game, pid: int) -> Optional[int]:
    best = None
    best_score = -1
    for vid, (owner, level) in g.occupied_v.items():
        if owner != pid or level != 1:
            continue
        if not can_upgrade_city(g, pid, vid):
            continue
        score = expected_vertex_yield(g, vid, pid)
        if score > best_score:
            best_score = score
            best = vid
    return best

def choose_best_settlement(g: Game, pid: int) -> Optional[int]:
    best = None
    best_score = -1
    for vid in g.vertices.keys():
        if not can_place_settlement(g, pid, vid, require_road=True):
            continue
        score = expected_vertex_yield(g, vid, pid)
        terrains = set()
        for ti in g.vertex_adj_hexes.get(vid, []):
            t = g.tiles[ti]
            res = TERRAIN_TO_RES.get(t.terrain)
            if res:
                terrains.add(res)
        score += 0.1 * len(terrains)
        if score > best_score:
            best_score = score
            best = vid
    return best

def choose_best_road(g: Game, pid: int) -> Optional[Tuple[int,int]]:
    best = None
    best_score = -1.0
    base_len = longest_road_length(g, pid)
    road_vertices = set()
    for (a, b), owner in g.occupied_e.items():
        if owner == pid:
            road_vertices.add(a)
            road_vertices.add(b)

    for e in g.edges:
        if not can_place_road(g, pid, e):
            continue
        a, b = e
        score = 0.0
        g.occupied_e[e] = pid
        new_len = longest_road_length(g, pid)
        if new_len > base_len:
            score += 1.0
        # future settlement potential
        if can_place_settlement(g, pid, a, require_road=True) or can_place_settlement(g, pid, b, require_road=True):
            score += 0.5
        g.occupied_e.pop(e, None)

        if a not in road_vertices:
            score += 0.2
        if b not in road_vertices:
            score += 0.2

        if score > best_score:
            best_score = score
            best = e
    return best

# -------------------- Graphics Items --------------------
class ClickableEllipse(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, rect: QtCore.QRectF, cb):
        super().__init__(rect)
        self._cb = cb
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self._base_pen = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 2)
        self._base_pen.setCapStyle(QtCore.Qt.RoundCap)
        self._hover_pen = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_hover"]), 3)
        self._hover_pen.setCapStyle(QtCore.Qt.RoundCap)

    def hoverEnterEvent(self, e):
        self.setPen(self._hover_pen)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setPen(self._base_pen)
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        if self._cb:
            self._cb()
        super().mousePressEvent(e)

class ClickableLine(QtWidgets.QGraphicsPathItem):
    def __init__(self, path: QtGui.QPainterPath, cb):
        super().__init__(path)
        self._cb = cb
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self._base = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 7)
        self._base.setCapStyle(QtCore.Qt.RoundCap)
        self._hover = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_hover"]), 9)
        self._hover.setCapStyle(QtCore.Qt.RoundCap)
        self.setPen(self._base)

    def hoverEnterEvent(self, e):
        self.setPen(self._hover)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setPen(self._base)
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        if self._cb:
            self._cb()
        super().mousePressEvent(e)

class ClickableHex(QtWidgets.QGraphicsPolygonItem):
    def __init__(self, poly: QtGui.QPolygonF, cb):
        super().__init__(poly)
        self._cb = cb
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self._base_pen = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 2)
        self._hover_pen = QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_hover"]), 3)
        self.setPen(self._base_pen)

    def hoverEnterEvent(self, e):
        self.setPen(self._hover_pen)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setPen(self._base_pen)
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        if self._cb:
            self._cb()
        super().mousePressEvent(e)

class DiscardDialog(QtWidgets.QDialog):
    def __init__(self, parent, res: Dict[str,int], need: int):
        super().__init__(parent)
        self.setWindowTitle("Discard")
        self.setModal(True)
        self._need = int(need)
        self._result: Dict[str,int] = {}

        root = QtWidgets.QVBoxLayout(self)
        lbl = QtWidgets.QLabel(f"Discard {self._need} card(s).")
        root.addWidget(lbl)

        form = QtWidgets.QFormLayout()
        self._spins: Dict[str, QtWidgets.QSpinBox] = {}
        for r in RESOURCES:
            sp = QtWidgets.QSpinBox()
            sp.setRange(0, int(res.get(r, 0)))
            sp.setValue(0)
            sp.valueChanged.connect(self._recalc)
            self._spins[r] = sp
            form.addRow(r, sp)
        root.addLayout(form)

        self._sum_lbl = QtWidgets.QLabel("0")
        form.addRow("Selected:", self._sum_lbl)

        self._btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._btns.accepted.connect(self._on_ok)
        self._btns.rejected.connect(self.reject)
        root.addWidget(self._btns)

        self._recalc()

    def _recalc(self):
        total = sum(sp.value() for sp in self._spins.values())
        self._sum_lbl.setText(str(total))
        ok_btn = self._btns.button(QtWidgets.QDialogButtonBox.Ok)
        ok_btn.setEnabled(total == self._need)

    def _on_ok(self):
        self._result = {r: sp.value() for r, sp in self._spins.items() if sp.value() > 0}
        self.accept()

    def selected(self) -> Dict[str,int]:
        return dict(self._result)

# -------------------- Main UI --------------------

class BoardView(QtWidgets.QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._zoom = 0
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self._panning = False
        self._pan_start = QtCore.QPoint()

    def wheelEvent(self, e: QtGui.QWheelEvent):
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 0.87
        self.scale(factor, factor)

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MiddleButton:
            self._panning = True
            self._pan_start = e.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._panning:
            delta = e.pos() - self._pan_start
            self._pan_start = e.pos()
            self.translate(delta.x()*-1, delta.y()*-1)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

class VictoryOverlay(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, on_rematch=None, on_menu=None):
        super().__init__(parent)
        self.setObjectName("victoryOverlay")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._on_rematch = on_rematch
        self._on_menu = on_menu

        self.setStyleSheet(f"""
#victoryOverlay {{
  background: {PALETTE['victory_overlay_bg_rgba']};
}}
#victoryCard {{
  background: {PALETTE['ui_panel_action']};
  border: 1px solid {PALETTE['ui_panel_border']};
  border-radius: 16px;
}}
""")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch(1)

        card = QtWidgets.QFrame()
        card.setObjectName("victoryCard")
        card_l = QtWidgets.QVBoxLayout(card)
        card_l.setContentsMargins(20, 18, 20, 18)
        card_l.setSpacing(10)

        self.title = QtWidgets.QLabel("Victory!")
        self.title.setStyleSheet("font-size:22px; font-weight:800;")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        card_l.addWidget(self.title)

        self.subtitle = QtWidgets.QLabel("")
        self.subtitle.setStyleSheet(f"font-size:13px; color:{PALETTE['ui_text_soft']};")
        self.subtitle.setAlignment(QtCore.Qt.AlignCenter)
        card_l.addWidget(self.subtitle)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:0; }}
            QTabBar::tab {{ padding:6px 10px; background:{PALETTE['ui_panel_tab']}; border-radius:10px; margin-right:6px; border:1px solid {PALETTE['ui_panel_outline']}; }}
            QTabBar::tab:selected {{ background:{PALETTE['ui_panel_tab_active']}; }}
        """)

        overview = QtWidgets.QWidget()
        overview_l = QtWidgets.QVBoxLayout(overview)
        overview_l.setContentsMargins(8, 6, 8, 6)
        self.overview_label = QtWidgets.QLabel("")
        self.overview_label.setWordWrap(True)
        self.overview_label.setStyleSheet(f"font-size:12px; color:{PALETTE['ui_text_bright']};")
        overview_l.addWidget(self.overview_label)
        overview_l.addStretch(1)
        self.tabs.addTab(overview, "Overview")

        dice = QtWidgets.QWidget()
        dice_l = QtWidgets.QGridLayout(dice)
        dice_l.setContentsMargins(8, 6, 8, 6)
        dice_l.setHorizontalSpacing(8)
        dice_l.setVerticalSpacing(6)
        self._dice_bars = {}
        self._dice_counts = {}
        row = 0
        for n in range(2, 13):
            lbl = QtWidgets.QLabel(str(n))
            lbl.setStyleSheet(f"color:{PALETTE['ui_text_muted']};")
            bar = QtWidgets.QProgressBar()
            bar.setTextVisible(False)
            bar.setMinimum(0)
            bar.setMaximum(1)
            bar.setValue(0)
            bar.setStyleSheet(f"""
                QProgressBar {{ background:{PALETTE['ui_progress_bg']}; border-radius:6px; height:10px; }}
                QProgressBar::chunk {{ background:{PALETTE['ui_progress_chunk']}; border-radius:6px; }}
            """)
            cnt = QtWidgets.QLabel("0")
            cnt.setStyleSheet(f"color:{PALETTE['ui_text_bright']}; font-weight:700;")
            dice_l.addWidget(lbl, row, 0)
            dice_l.addWidget(bar, row, 1)
            dice_l.addWidget(cnt, row, 2)
            self._dice_bars[n] = bar
            self._dice_counts[n] = cnt
            row += 1
        self.tabs.addTab(dice, "Dice Stats")

        card_l.addWidget(self.tabs)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_rematch = QtWidgets.QPushButton("Rematch")
        self.btn_menu = QtWidgets.QPushButton("Main Menu")
        self.btn_rematch.setStyleSheet(f"background:{PALETTE['ui_accent']}; color:{PALETTE['ui_text_dark']}; padding:10px 16px; border-radius:12px; font-weight:800;")
        self.btn_menu.setStyleSheet(f"background:{PALETTE['ui_panel_outline']}; color:{PALETTE['ui_text_bright']}; padding:10px 16px; border-radius:12px; font-weight:700;")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_rematch)
        btn_row.addWidget(self.btn_menu)
        btn_row.addStretch(1)
        card_l.addLayout(btn_row)

        root.addWidget(card, alignment=QtCore.Qt.AlignCenter)
        root.addStretch(1)

        self.btn_rematch.clicked.connect(self._handle_rematch)
        self.btn_menu.clicked.connect(self._handle_menu)
        self.hide()

    def set_callbacks(self, on_rematch=None, on_menu=None):
        if on_rematch is not None:
            self._on_rematch = on_rematch
        if on_menu is not None:
            self._on_menu = on_menu

    def _handle_rematch(self):
        if callable(self._on_rematch):
            self._on_rematch()

    def _handle_menu(self):
        if callable(self._on_menu):
            self._on_menu()

    def update_from_game(self, g):
        pid = g.winner_pid if g.winner_pid is not None else 0
        winner_name = g.players[pid].name if g.players else f"P{pid + 1}"
        winner_vp = g.players[pid].vp if g.players else 0
        self.subtitle.setText(f"Winner: {winner_name} (VP {winner_vp})")
        lr = "none" if g.longest_road_owner is None else f"P{g.longest_road_owner + 1} (len {g.longest_road_len})"
        la = "none"
        if g.largest_army_pid is not None:
            la = f"P{g.largest_army_pid + 1} (size {g.largest_army_size})"
        self.overview_label.setText(
            f"Final VP: P1 {g.players[0].vp} / P2 {g.players[1].vp}\n"
            f"Longest Road: {lr}\n"
            f"Largest Army: {la}\n"
            f"Total rolls: {len(g.roll_history)}"
        )

        counts = {n: 0 for n in range(2, 13)}
        for r in g.roll_history:
            if r in counts:
                counts[r] += 1
        max_count = max(counts.values()) if counts else 1
        if max_count <= 0:
            max_count = 1
        for n in range(2, 13):
            bar = self._dice_bars[n]
            bar.setMaximum(max_count)
            bar.setValue(counts[n])
            self._dice_counts[n].setText(str(counts[n]))

class StatusPanel(QtWidgets.QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("statusPanel")
        self.setStyleSheet(f"""
#statusPanel {{
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 {PALETTE['status_panel_stop1_rgba']},
    stop:1 {PALETTE['status_panel_stop2_rgba']});
  border: 1px solid {PALETTE['status_panel_border_rgba']};
  border-radius: 14px;
}}
""")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        self.badge_p1 = QtWidgets.QLabel("You 0 VP")
        self.badge_p2 = QtWidgets.QLabel("Bot 0 VP")
        for b in (self.badge_p1, self.badge_p2):
            b.setAlignment(QtCore.Qt.AlignCenter)
            b.setStyleSheet(f"font-size:12px; padding:5px 12px; border-radius:10px; background:{PALETTE['ui_panel_outline']};")
        top.addWidget(self.badge_p1)
        top.addWidget(self.badge_p2)
        root.addLayout(top)

        pills = QtWidgets.QHBoxLayout()
        self.badge_turn = QtWidgets.QLabel("Turn: -")
        self.badge_phase = QtWidgets.QLabel("Phase: -")
        self.badge_pending = QtWidgets.QLabel("Pending: none")
        for b in (self.badge_turn, self.badge_phase, self.badge_pending):
            b.setAlignment(QtCore.Qt.AlignCenter)
            b.setStyleSheet(f"font-size:11px; padding:4px 8px; border-radius:8px; background:{PALETTE['ui_panel_tab']}; color:{PALETTE['ui_text_bright']};")
        pills.addWidget(self.badge_turn)
        pills.addWidget(self.badge_phase)
        pills.addWidget(self.badge_pending)
        root.addLayout(pills)

        row = QtWidgets.QGridLayout()
        row.setHorizontalSpacing(8)
        row.setVerticalSpacing(4)
        lbl_lr = QtWidgets.QLabel("Longest Road")
        lbl_la = QtWidgets.QLabel("Largest Army")
        for lbl in (lbl_lr, lbl_la):
            lbl.setStyleSheet(f"color:{PALETTE['ui_text_muted']}; font-size:11px;")
        self.lbl_longest = QtWidgets.QLabel("none")
        self.lbl_army = QtWidgets.QLabel("none")
        for lbl in (self.lbl_longest, self.lbl_army):
            lbl.setStyleSheet("font-size:12px; font-weight:600;")
        row.addWidget(lbl_lr, 0, 0)
        row.addWidget(self.lbl_longest, 0, 1)
        row.addWidget(lbl_la, 1, 0)
        row.addWidget(self.lbl_army, 1, 1)
        root.addLayout(row)

    def update_from_game(self, g):
        self.badge_p1.setText(f"You {g.players[0].vp} VP")
        self.badge_p2.setText(f"Bot {g.players[1].vp} VP")
        active_style = f"font-size:12px; padding:4px 10px; border-radius:10px; background:{PALETTE['ui_accent']}; color:{PALETTE['ui_text_dark']}; font-weight:800;"
        idle_style = f"font-size:12px; padding:4px 10px; border-radius:10px; background:{PALETTE['ui_panel_outline']}; color:{PALETTE['ui_text_bright']};"
        if g.game_over and g.winner_pid is not None:
            self.badge_p1.setStyleSheet(active_style if g.winner_pid == 0 else idle_style)
            self.badge_p2.setStyleSheet(active_style if g.winner_pid == 1 else idle_style)
        else:
            self.badge_p1.setStyleSheet(active_style if g.turn == 0 else idle_style)
            self.badge_p2.setStyleSheet(active_style if g.turn == 1 else idle_style)
        if g.game_over:
            self.badge_phase.setText("Phase: game over")
            self.badge_turn.setText(f"Winner: P{g.winner_pid + 1}")
        else:
            self.badge_phase.setText(f"Phase: {g.phase}")
            self.badge_turn.setText(f"Turn: {g.players[g.turn].name}")
        pending = g.pending_action or "none"
        self.badge_pending.setText(f"Pending: {pending}")

        lr = "none" if g.longest_road_owner is None else f"P{g.longest_road_owner + 1} (len {g.longest_road_len})"
        la = "none"
        if g.largest_army_pid is not None:
            la = f"P{g.largest_army_pid + 1} (size {g.largest_army_size})"
        self.lbl_longest.setText(lr)
        self.lbl_army.setText(la)

class ResourceChip(QtWidgets.QFrame):
    def __init__(self, name: str):
        super().__init__()
        self.setObjectName("resChip")
        self.name = name
        self.setStyleSheet(f"""
#resChip {{
  background: {PALETTE['ui_panel_deep']};
  border: 1px solid {PALETTE['res_chip_border_rgba']};
  border-radius: 12px;
}}
""")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(6)

        self.icon = QtWidgets.QLabel()
        self.icon.setFixedSize(24, 24)
        self.icon.setPixmap(resource_icon_pixmap(name, 22))
        lay.addWidget(self.icon)

        self.count = QtWidgets.QLabel("0")
        self.count.setAlignment(QtCore.Qt.AlignCenter)
        self.count.setStyleSheet(f"font-size:12px; font-weight:800; background:{PALETTE['ui_panel_outline']}; border-radius:8px; padding:2px 6px;")
        lay.addWidget(self.count, 1)

    def set_count(self, value: int):
        self.count.setText(str(value))

class ResourcesPanel(QtWidgets.QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("resourcesPanel")
        self.setStyleSheet(f"""
#resourcesPanel {{
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 {PALETTE['resources_panel_stop1_rgba']},
    stop:1 {PALETTE['resources_panel_stop2_rgba']});
  border: 1px solid {PALETTE['resources_panel_border_rgba']};
  border-radius: 14px;
}}
""")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        self.hand_chips = {}
        self.bank_chips = {}

        hand_lbl = QtWidgets.QLabel("Hand")
        hand_lbl.setStyleSheet(f"color:{PALETTE['ui_text_muted']}; font-size:11px;")
        root.addWidget(hand_lbl)
        hand_row = QtWidgets.QHBoxLayout()
        hand_row.setSpacing(6)
        for r in RESOURCES:
            chip = ResourceChip(r)
            self.hand_chips[r] = chip
            hand_row.addWidget(chip)
        root.addLayout(hand_row)

        bank_lbl = QtWidgets.QLabel("Bank")
        bank_lbl.setStyleSheet(f"color:{PALETTE['ui_text_muted']}; font-size:11px;")
        root.addWidget(bank_lbl)
        bank_row = QtWidgets.QHBoxLayout()
        bank_row.setSpacing(6)
        for r in RESOURCES:
            chip = ResourceChip(r)
            self.bank_chips[r] = chip
            bank_row.addWidget(chip)
        root.addLayout(bank_row)

    def update_from_game(self, g):
        for r in RESOURCES:
            self.hand_chips[r].set_count(g.players[0].res[r])
            self.bank_chips[r].set_count(g.bank[r])

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config: Optional[GameConfig] = None, on_back_to_menu=None, online_controller=None, online_pid: int = 0):
        super().__init__()
        self.setWindowTitle("CATAN Desktop (UI v6)")
        self.resize(1400, 820)
        self._last_config = config or GameConfig()
        set_ui_palette(self._last_config.theme)
        self.bot_enabled = bool(self._last_config.bot_enabled)
        self.bot_difficulty = int(self._last_config.bot_difficulty)
        self._on_back_to_menu = on_back_to_menu
        self.online_controller = online_controller
        self.online_mode = online_controller is not None
        self.you_pid = int(online_pid)

        self.game = build_board(seed=random.randint(1, 999999), size=62.0)
        self.game.ui = self

        self.selected_action = None  # "settlement"/"road"/"city"/"dev"
        self.overlay_nodes: Dict[int, QtWidgets.QGraphicsItem] = {}
        self.overlay_edges: Dict[Tuple[int,int], QtWidgets.QGraphicsItem] = {}
        self.overlay_hex: Dict[int, QtWidgets.QGraphicsItem] = {}
        self.piece_items: List[QtWidgets.QGraphicsItem] = []
        self._shown_game_over = False

        root = QtWidgets.QWidget()
        root.setStyleSheet(f"background:{BG}; color:{TEXT};")
        self.setCentralWidget(root)

        # layout: map big + right panel
        h = QtWidgets.QHBoxLayout(root)
        h.setContentsMargins(18,18,18,18)
        h.setSpacing(14)

        # scene
        self.scene = QtWidgets.QGraphicsScene()
        self.scene.setBackgroundBrush(QtGui.QColor(BG))
        self.view = BoardView(self.scene)

        map_card = QtWidgets.QFrame()
        map_card.setStyleSheet(f"background:{PANEL}; border-radius:18px;")
        map_layout = QtWidgets.QVBoxLayout(map_card)
        map_layout.setContentsMargins(12,12,12,12)
        map_layout.addWidget(self.view, 1)

        # right panel
        right = QtWidgets.QFrame()
        right.setStyleSheet(f"background:{PANEL}; border-radius:18px;")
        right.setFixedWidth(420)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(12,12,12,12)
        right_layout.setSpacing(10)
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)

        self.resources_panel = ResourcesPanel()
        right_layout.addWidget(self.resources_panel)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setMaximumHeight(300)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:0; }}
            QTabBar::tab {{ padding:8px 12px; background:{PALETTE['ui_panel_tab']}; border-radius:10px; margin-right:6px; border:1px solid {PALETTE['ui_panel_outline']}; }}
            QTabBar::tab:selected {{ background:{PALETTE['ui_panel_tab_active']}; }}
        """)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(f"background:{PALETTE['ui_panel_input']}; border:1px solid {PALETTE['ui_panel_outline']}; border-radius:12px; padding:10px;")
        self.chat = QtWidgets.QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setStyleSheet(f"background:{PALETTE['ui_panel_input']}; border:1px solid {PALETTE['ui_panel_outline']}; border-radius:12px; padding:10px;")
        self.tabs.addTab(self.log, "Log")
        self.tabs.addTab(self.chat, "Chat")
        right_layout.addWidget(self.tabs, 1)

        self.chat_in = QtWidgets.QLineEdit()
        self.chat_in.setPlaceholderText("Type a message...")
        self.chat_in.setStyleSheet(f"background:{PALETTE['ui_panel_input']}; border:1px solid {PALETTE['ui_panel_outline']}; border-radius:12px; padding:10px;")
        self.chat_btn = QtWidgets.QPushButton("Send")
        self.chat_btn.setStyleSheet(f"background:{ACCENT}; color:{PALETTE['ui_text_dark']}; padding:10px 14px; border-radius:12px; font-weight:700;")
        self.chat_btn.clicked.connect(self.on_send_chat)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.chat_in, 1)
        row.addWidget(self.chat_btn)
        right_layout.addLayout(row)

        # top bar (dice + end turn) inside titlebar area using toolbar-like widget
        top = QtWidgets.QFrame()
        top.setStyleSheet(f"background:{PANEL}; border-radius:18px;")
        top_l = QtWidgets.QHBoxLayout(top)
        top_l.setContentsMargins(14,10,14,10)

        self.lbl_title = QtWidgets.QLabel("CATAN")
        self.lbl_title.setStyleSheet("font-size:18px; font-weight:800;")
        self.lbl_hint = QtWidgets.QLabel("Setup: place settlement. Spots show only when action selected.")
        self.lbl_hint.setStyleSheet("font-size:12px; opacity:0.9;")
        top_l.addWidget(self.lbl_title)
        top_l.addSpacing(14)
        top_l.addWidget(self.lbl_hint, 1)

        self.d1 = QtWidgets.QToolButton()
        self.d2 = QtWidgets.QToolButton()
        self.d1.setIcon(QtGui.QIcon(dice_face(1)))
        self.d2.setIcon(QtGui.QIcon(dice_face(1)))
        for b in (self.d1, self.d2):
            b.setIconSize(QtCore.QSize(44,44))
            b.setFixedSize(54,54)
            b.setStyleSheet(f"background:{PALETTE['ui_panel_soft']}; border-radius:14px;")
        self.d1.clicked.connect(self.on_roll_click)
        self.d2.clicked.connect(self.on_roll_click)

        self.btn_end = QtWidgets.QPushButton("End turn")
        self.btn_end.setStyleSheet(f"background:{PALETTE['ui_panel_end']}; padding:10px 14px; border-radius:12px; font-weight:800;")
        self.btn_end.clicked.connect(self.on_end_turn)

        self.btn_menu = QtWidgets.QPushButton("Menu")
        self.btn_menu.setStyleSheet(f"background:{PALETTE['ui_panel_outline']}; padding:10px 14px; border-radius:12px; font-weight:700;")
        self.btn_menu.clicked.connect(self._open_game_menu)
        self._esc_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        self._esc_shortcut.activated.connect(self._open_game_menu)

        top_l.addWidget(self.d1)
        top_l.addWidget(self.d2)
        top_l.addSpacing(8)
        top_l.addWidget(self.btn_end)
        top_l.addWidget(self.btn_menu)

        # bottom action bar (Colonist-like cards)
        bottom = QtWidgets.QFrame()
        bottom.setStyleSheet(f"background:{PANEL}; border-radius:18px;")
        bottom_l = QtWidgets.QHBoxLayout(bottom)
        bottom_l.setContentsMargins(12,10,12,10)
        bottom_l.setSpacing(10)

        def action_btn(key: str, tooltip: str, checkable: bool = True):
            b = QtWidgets.QToolButton()
            b.setCheckable(checkable)
            b.setIcon(QtGui.QIcon(make_action_icon(key)))
            b.setIconSize(QtCore.QSize(34, 34))
            b.setFixedSize(64, 60)
            b.setToolTip(tooltip)
            b.setStyleSheet(f"""
                QToolButton {{ background:{PALETTE['ui_panel_action']}; border:1px solid {PALETTE['ui_panel_outline']}; border-radius:14px; }}
                QToolButton:hover {{ background:{PALETTE['ui_panel_action_hover']}; }}
                QToolButton:checked {{ background:{PALETTE['ui_panel_action_checked']}; border:2px solid {PALETTE['ui_outline_light']}; }}
            """)
            if checkable:
                b.clicked.connect(lambda: self.select_action(key))
            return b

        self.btn_sett = action_btn("settlement", "Settlement (wood+brick+sheep+wheat)")
        self.btn_road = action_btn("road", "Road (wood+brick)")
        self.btn_city = action_btn("city", "City (2 wheat + 3 ore)")
        self.btn_dev  = action_btn("dev", "Dev card (sheep+wheat+ore)", checkable=False)
        self.btn_trade = action_btn("trade", "Trade with bank", checkable=False)
        self.btn_dev.setObjectName("btn_dev_action")
        self.btn_trade.setObjectName("btn_trade_bank")
        self.btn_dev.clicked.connect(self._open_dev_dialog)
        self.btn_trade.clicked.connect(self._open_trade_dialog)

        bottom_l.addWidget(self.btn_sett)
        bottom_l.addWidget(self.btn_road)
        bottom_l.addWidget(self.btn_city)
        bottom_l.addWidget(self.btn_dev)
        bottom_l.addWidget(self.btn_trade)
        bottom_l.addStretch(1)

        # main container: left area (top + map + bottom), right panel fixed
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(top, 0)
        left.addWidget(map_card, 1)
        left.addWidget(bottom, 0)

        h.addLayout(left, 1)
        h.addWidget(right, 0)

        self.victory_overlay = VictoryOverlay(
            root,
            on_rematch=self._restart_game,
            on_menu=self._back_to_menu,
        )
        self.victory_overlay.setGeometry(root.rect())

        self._draw_static_board()
        self._log(f"[SYS] New game seed={self.game.seed}. Setup: place settlement then road (x2).")
        self.select_action("settlement")
        self._fit_map()
        self._sync_ui()
        attach_dev_hand_overlay(self, self.view)

    # ---------- Drawing ----------
    def _fit_map(self):
        rect = self.scene.itemsBoundingRect().adjusted(-80,-80,80,80)
        if rect.isNull():
            return
        self.view.fitInView(rect, QtCore.Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_map()
        if hasattr(self, "victory_overlay"):
            self.victory_overlay.setGeometry(self.centralWidget().rect())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_map()
        if hasattr(self, "victory_overlay"):
            self.victory_overlay.setGeometry(self.centralWidget().rect())

    def _draw_static_board(self):
        self.scene.clear()
        if self.game.tiles:
            pts = []
            for t in self.game.tiles:
                pts.extend(hex_corners(t.center, self.game.size))
            min_x = min(p.x() for p in pts) - self.game.size * 2
            max_x = max(p.x() for p in pts) + self.game.size * 2
            min_y = min(p.y() for p in pts) - self.game.size * 2
            max_y = max(p.y() for p in pts) + self.game.size * 2
            rect = QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
            ocean_grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
            ocean_grad.setColorAt(0, QtGui.QColor(PALETTE["ui_bg"]))
            ocean_grad.setColorAt(1, QtGui.QColor(PALETTE["ui_panel_deep"]))
            ocean = QtWidgets.QGraphicsRectItem(rect)
            ocean.setBrush(QtGui.QBrush(ocean_grad))
            ocean.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            ocean.setZValue(-10)
            self.scene.addItem(ocean)
        # draw hexes + tokens
        for ti, t in enumerate(self.game.tiles):
            poly = QtGui.QPolygonF(hex_corners(t.center, self.game.size))
            # shadow (pseudo-3D)
            shadow = QtWidgets.QGraphicsPolygonItem(poly.translated(6,6))
            shadow.setBrush(QtGui.QColor(PALETTE["ui_shadow"]))
            shadow.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            shadow.setZValue(0)
            self.scene.addItem(shadow)

            item = QtWidgets.QGraphicsPolygonItem(poly)
            base = QtGui.QColor(TERRAIN_COLOR[t.terrain])
            grad = QtGui.QLinearGradient(
                t.center.x()-self.game.size, t.center.y()-self.game.size,
                t.center.x()+self.game.size, t.center.y()+self.game.size
            )
            grad.setColorAt(0, base.lighter(120))
            grad.setColorAt(1, base.darker(120))
            item.setBrush(QtGui.QBrush(grad))
            pen = QtGui.QPen(base.darker(150), 3)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            item.setPen(pen)
            item.setZValue(1)
            self.scene.addItem(item)

            # number token with pips
            if t.number is not None:
                token_r = self.game.size * 0.34
                sh = QtWidgets.QGraphicsEllipseItem(
                    t.center.x()-token_r+2, t.center.y()-token_r+2, token_r*2, token_r*2
                )
                sh.setBrush(QtGui.QColor(PALETTE["token_shadow_rgba"]))
                sh.setPen(QtGui.QPen(QtCore.Qt.NoPen))
                sh.setZValue(2.6)
                self.scene.addItem(sh)
                circ = QtWidgets.QGraphicsEllipseItem(
                    t.center.x()-token_r, t.center.y()-token_r, token_r*2, token_r*2
                )
                circ.setBrush(QtGui.QColor(PALETTE["ui_token_bg"]))
                circ.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_token_outline"]), 2))
                circ.setZValue(3)
                self.scene.addItem(circ)

                txt = QtWidgets.QGraphicsTextItem(str(t.number))
                color = PALETTE["ui_token_hot"] if t.number in (6,8) else PALETTE["ui_token_outline"]
                txt.setDefaultTextColor(QtGui.QColor(color))
                f = QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold)
                txt.setFont(f)
                b = txt.boundingRect()
                txt.setPos(t.center.x()-b.width()/2, t.center.y()-b.height()/2 - 3)
                txt.setZValue(4)
                self.scene.addItem(txt)

                pips = PIPS.get(t.number, 0)
                if pips:
                    pip_y = t.center.y() + token_r*0.40
                    start = t.center.x() - (pips-1)*6
                    for i in range(pips):
                        pip = QtWidgets.QGraphicsEllipseItem(start + i*12 - 3, pip_y-3, 6, 6)
                        pip.setBrush(QtGui.QColor(color))
                        pip.setPen(QtGui.QPen(QtCore.Qt.NoPen))
                        pip.setZValue(4)
                        self.scene.addItem(pip)

        # ports (badges on coast edges)
        self._draw_ports()

        # built pieces will be redrawn on refresh
        self._refresh_all_dynamic()

    def _draw_ports(self):
        center = QtCore.QPointF(0,0)
        for edge, ptype in self.game.ports:
            a,b = edge
            pa = self.game.vertices[a]
            pb = self.game.vertices[b]
            mid = (pa + pb) * 0.5
            # outward offset (choose normal pointing away from center)
            vx, vy = (pb.x()-pa.x()), (pb.y()-pa.y())
            nx, ny = (-vy, vx)
            ln = math.hypot(nx, ny) or 1.0
            nx, ny = nx/ln, ny/ln
            cand1 = QtCore.QPointF(mid.x()+nx*30, mid.y()+ny*30)
            cand2 = QtCore.QPointF(mid.x()-nx*30, mid.y()-ny*30)
            out = cand1 if (cand1-center).manhattanLength() > (cand2-center).manhattanLength() else cand2

            # rounded rect via path (PySide6 has no QGraphicsRoundedRectItem)
            rect = QtCore.QRectF(out.x()-22, out.y()-12, 44, 24)
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            box = QtWidgets.QGraphicsPathItem(path)
            box.setBrush(QtGui.QColor(PALETTE["ui_panel_input"]))
            box.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_panel_soft"]), 2))
            box.setZValue(6)
            self.scene.addItem(box)

            label = ptype.replace("2:1:", "2:1 ")
            txt = QtWidgets.QGraphicsTextItem(label)
            txt.setDefaultTextColor(QtGui.QColor(PALETTE["text"]))
            txt.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold))
            br = txt.boundingRect()
            txt.setPos(rect.center().x()-br.width()/2, rect.center().y()-br.height()/2-1)
            txt.setZValue(7)
            self.scene.addItem(txt)

    def _refresh_all_dynamic(self):
        # clear overlays and pieces
        for it in list(self.overlay_nodes.values()):
            self.scene.removeItem(it)
        for it in list(self.overlay_edges.values()):
            self.scene.removeItem(it)
        self.overlay_nodes.clear()
        self.overlay_edges.clear()
        for it in list(self.overlay_hex.values()):
            self.scene.removeItem(it)
        self.overlay_hex.clear()
        for it in list(self.piece_items):
            self.scene.removeItem(it)
        self.piece_items.clear()

        # draw roads + settlements/cities
        # roads
        for (a,b), pid in self.game.occupied_e.items():
            pa = self.game.vertices[a]
            pb = self.game.vertices[b]
            path = QtGui.QPainterPath(pa)
            path.lineTo(pb)
            base = QtWidgets.QGraphicsPathItem(path)
            dark = self.game.players[pid].color.darker(160)
            pen_base = QtGui.QPen(dark, 12)
            pen_base.setCapStyle(QtCore.Qt.RoundCap)
            base.setPen(pen_base)
            base.setZValue(10)
            self.scene.addItem(base)
            self.piece_items.append(base)

            it = QtWidgets.QGraphicsPathItem(path)
            pen = QtGui.QPen(self.game.players[pid].color.lighter(115), 8)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            it.setPen(pen)
            it.setZValue(11)
            self.scene.addItem(it)
            self.piece_items.append(it)

        # settlements/cities
        for vid,(pid,level) in self.game.occupied_v.items():
            p = self.game.vertices[vid]
            if level == 1:
                self._draw_house(p, self.game.players[pid].color, z=12)
            else:
                self._draw_city(p, self.game.players[pid].color, z=12)

        self._draw_robber()

        if self.game.pending_action == "robber_move" and self.game.pending_pid == (self.you_pid if self.online_mode else 0):
            for ti, t in enumerate(self.game.tiles):
                if ti == self.game.robber_tile:
                    continue
                poly = QtGui.QPolygonF(hex_corners(t.center, self.game.size))
                def on_click(_ti=ti):
                    self._on_hex_clicked(_ti)
                it = ClickableHex(poly, on_click)
                it.setBrush(QtGui.QColor(PALETTE["overlay_hex_rgba"]))
                it.setZValue(9)
                self.scene.addItem(it)
                self.overlay_hex[ti] = it

        # show ONLY legal placement spots for current action (offline only)
        if not self.online_mode:
            self._show_legal_spots()

    def _draw_robber(self):
        t = self.game.tiles[self.game.robber_tile]
        c = t.center
        r = self.game.size * 0.16
        rob = QtWidgets.QGraphicsEllipseItem(c.x()-r, c.y()-r, r*2, r*2)
        rob.setBrush(QtGui.QColor(PALETTE["robber_fill_rgba"]))
        rob.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_robber_text"]), 2))
        rob.setZValue(8)
        self.scene.addItem(rob)
        self.piece_items.append(rob)

        txt = QtWidgets.QGraphicsTextItem("R")
        txt.setDefaultTextColor(QtGui.QColor(PALETTE["ui_robber_text"]))
        txt.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        b = txt.boundingRect()
        txt.setPos(c.x()-b.width()/2, c.y()-b.height()/2-1)
        txt.setZValue(9)
        self.scene.addItem(txt)
        self.piece_items.append(txt)

    def _draw_house(self, p: QtCore.QPointF, col: QtGui.QColor, z: float):
        # simple "3D-ish" house (original vector)
        w, h = 18, 14
        base = QtGui.QPolygonF([
            QtCore.QPointF(p.x()-w/2, p.y()+h/2),
            QtCore.QPointF(p.x()+w/2, p.y()+h/2),
            QtCore.QPointF(p.x()+w/2, p.y()-h/6),
            QtCore.QPointF(p.x()-w/2, p.y()-h/6),
        ])
        roof = QtGui.QPolygonF([
            QtCore.QPointF(p.x()-w/2-2, p.y()-h/6),
            QtCore.QPointF(p.x(), p.y()-h/2-6),
            QtCore.QPointF(p.x()+w/2+2, p.y()-h/6),
        ])

        sh = QtWidgets.QGraphicsPolygonItem(base.translated(2,2))
        sh.setBrush(QtGui.QColor(PALETTE["ui_piece_shadow"]))
        sh.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        sh.setZValue(z-0.2)
        self.scene.addItem(sh)
        self.piece_items.append(sh)

        b = QtWidgets.QGraphicsPolygonItem(base)
        b.setBrush(col)
        b.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_dark"]), 2))
        b.setZValue(z)
        self.scene.addItem(b)
        self.piece_items.append(b)

        shine = QtWidgets.QGraphicsPolygonItem(base)
        shine.setBrush(col.lighter(130))
        shine.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        shine.setOpacity(0.25)
        shine.setZValue(z+0.05)
        self.scene.addItem(shine)
        self.piece_items.append(shine)

        r = QtWidgets.QGraphicsPolygonItem(roof)
        r.setBrush(col.darker(120))
        r.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_dark"]), 2))
        r.setZValue(z+0.1)
        self.scene.addItem(r)
        self.piece_items.append(r)

        r_hi = QtWidgets.QGraphicsPolygonItem(roof)
        r_hi.setBrush(col.lighter(125))
        r_hi.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        r_hi.setOpacity(0.25)
        r_hi.setZValue(z+0.15)
        self.scene.addItem(r_hi)
        self.piece_items.append(r_hi)

    def _draw_city(self, p: QtCore.QPointF, col: QtGui.QColor, z: float):
        # bigger block
        w, h = 22, 18
        poly = QtGui.QPolygonF([
            QtCore.QPointF(p.x()-w/2, p.y()+h/2),
            QtCore.QPointF(p.x()+w/2, p.y()+h/2),
            QtCore.QPointF(p.x()+w/2, p.y()-h/2),
            QtCore.QPointF(p.x()-w/2, p.y()-h/2),
        ])
        sh = QtWidgets.QGraphicsPolygonItem(poly.translated(2,2))
        sh.setBrush(QtGui.QColor(PALETTE["ui_piece_shadow"]))
        sh.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        sh.setZValue(z-0.2)
        self.scene.addItem(sh)
        self.piece_items.append(sh)

        it = QtWidgets.QGraphicsPolygonItem(poly)
        it.setBrush(col)
        it.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_dark"]), 2))
        it.setZValue(z)
        self.scene.addItem(it)
        self.piece_items.append(it)

        top = QtGui.QPolygonF([
            QtCore.QPointF(p.x()-w/2+2, p.y()-h/2+2),
            QtCore.QPointF(p.x()+w/2-2, p.y()-h/2+2),
            QtCore.QPointF(p.x()+w/2-2, p.y()-h/2+8),
            QtCore.QPointF(p.x()-w/2+2, p.y()-h/2+8),
        ])
        hi = QtWidgets.QGraphicsPolygonItem(top)
        hi.setBrush(col.lighter(130))
        hi.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        hi.setOpacity(0.3)
        hi.setZValue(z+0.05)
        self.scene.addItem(hi)
        self.piece_items.append(hi)

    # ---------- Logic/UI ----------
    def _log(self, s: str):
        self.log.appendPlainText(s)

    def _chat(self, s: str):
        self.chat.appendPlainText(s)

    def _sync_ui(self):
        g = self.game
        if g.game_over:
            self.victory_overlay.update_from_game(g)
            if not self._shown_game_over:
                self.victory_overlay.setGeometry(self.centralWidget().rect())
                self.victory_overlay.show()
                self.victory_overlay.raise_()
                self._shown_game_over = True
        else:
            if self._shown_game_over:
                self.victory_overlay.hide()
                self._shown_game_over = False

        self.status_panel.update_from_game(g)
        self.resources_panel.update_from_game(g)

        # hint text
        if g.game_over:
            self.lbl_hint.setText("Game over.")
        elif g.pending_action == "robber_move":
            self.lbl_hint.setText("Robber: click a hex to move it.")
        elif g.phase == "setup":
            self.lbl_hint.setText("Setup: place settlement then road. Spots show only for selected action.")
        else:
            self.lbl_hint.setText("Main: click dice to roll. Build by selecting card then clicking highlighted spots.")

        for b in (self.btn_sett, self.btn_road, self.btn_city, self.btn_dev, self.btn_trade, self.btn_end, self.d1, self.d2):
            b.setEnabled(not g.game_over)
        if self.online_mode:
            self.btn_dev.setEnabled(False)
            self.btn_trade.setEnabled(False)

    def _restart_game(self):
        self.game = build_board(seed=random.randint(1, 999999), size=62.0)
        self.game.ui = self
        self._shown_game_over = False
        if hasattr(self, "victory_overlay"):
            self.victory_overlay.hide()
        self.selected_action = None
        self.overlay_nodes.clear()
        self.overlay_edges.clear()
        self.overlay_hex.clear()
        self.piece_items.clear()
        self.scene.clear()
        self._draw_static_board()
        self._log(f"[SYS] New game seed={self.game.seed}. Setup: place settlement then road (x2).")
        self.select_action("settlement")
        self._fit_map()
        self._sync_ui()
        attach_dev_hand_overlay(self, self.view)

    def _back_to_menu(self):
        if callable(self._on_back_to_menu):
            self._on_back_to_menu()
        self.close()

    def set_online(self, controller, pid: int):
        self.online_controller = controller
        self.online_mode = controller is not None
        self.you_pid = int(pid)
        if self.online_mode:
            self.victory_overlay.set_callbacks(
                on_rematch=getattr(controller, "rematch", None),
                on_menu=self._back_to_menu,
            )
        self._sync_ui()

    def _open_game_menu(self):
        if self.game.pending_action is not None:
            self._log("[!] Resolve pending action first.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Menu")
        dlg.setModal(True)
        root = QtWidgets.QVBoxLayout(dlg)
        btn_resume = QtWidgets.QPushButton("Resume")
        btn_new = QtWidgets.QPushButton("New Game")
        btn_back = QtWidgets.QPushButton("Back to Main Menu")
        btn_quit = QtWidgets.QPushButton("Quit")
        for b in (btn_resume, btn_new, btn_back, btn_quit):
            root.addWidget(b)

        btn_resume.clicked.connect(dlg.reject)
        def _new_game():
            dlg.accept()
            self._restart_game()
        def _back_menu():
            dlg.accept()
            self._back_to_menu()
        def _quit():
            dlg.accept()
            QtWidgets.QApplication.instance().quit()
        btn_new.clicked.connect(_new_game)
        btn_back.clicked.connect(_back_menu)
        btn_quit.clicked.connect(_quit)
        dlg.exec()

    def _open_dev_dialog(self):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode:
            self._log("[!] Dev cards disabled in online mode.")
            return
        if str(g.phase).startswith("setup"):
            self._log("[!] Dev cards disabled during setup.")
            return
        dlg = DevDialog(self, g, 0)
        dlg.exec()
        self._refresh_all_dynamic()
        self._sync_ui()

    def _open_trade_dialog(self):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode:
            self._log("[!] Trade disabled in online mode.")
            return
        if str(g.phase).startswith("setup"):
            self._log("[!] Trade disabled during setup.")
            return
        dlg = TradeDialog(self, g, 0)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg._applied:
            give, get, qty, rate = dlg._applied
            self._log(f"[TRADE] {rate}:1 gave {give} -> got {get} x{qty}")
        self._refresh_all_dynamic()
        self._sync_ui()

    def hand_size(self, pid: int) -> int:
        return sum(self.game.players[pid].res.values())

    def discard_needed(self, pid: int) -> int:
        total = self.hand_size(pid)
        return total // 2 if total > 7 else 0

    def _apply_discard(self, pid: int, discard: Dict[str,int]):
        pres = self.game.players[pid].res
        for r, n in discard.items():
            q = min(int(n), int(pres.get(r, 0)))
            if q <= 0:
                continue
            pres[r] -= q
            self.game.bank[r] += q

    def _random_discard(self, pid: int, need: int):
        pres = self.game.players[pid].res
        bag = []
        for r, c in pres.items():
            bag += [r] * int(c)
        random.shuffle(bag)
        for _ in range(min(need, len(bag))):
            r = bag.pop()
            pres[r] -= 1
            self.game.bank[r] += 1

    def _start_robber_flow(self, pid: int, reason: str):
        g = self.game
        g.pending_action = "robber_move"
        g.pending_pid = pid
        g.pending_victims = []
        who = g.players[pid].name
        self._log(f"[ROB] {who} moves the robber ({reason}). Click a hex.")
        self._refresh_all_dynamic()
        self._sync_ui()

    def _steal_random(self, pid: int, target_pid: int):
        pres = self.game.players[target_pid].res
        bag = []
        for r, c in pres.items():
            bag += [r] * int(c)
        if not bag:
            self._log("[ROB] Target has no resources to steal.")
            return
        r = random.choice(bag)
        pres[r] -= 1
        self.game.players[pid].res[r] += 1
        self._log(f"[ROB] Stole 1 {r} from {self.game.players[target_pid].name}.")

    def _victims_for_tile(self, ti: int, pid: int) -> List[int]:
        g = self.game
        victims = set()
        for vid, (owner, _level) in g.occupied_v.items():
            if owner == pid:
                continue
            if ti in g.vertex_adj_hexes.get(vid, []):
                if self.hand_size(owner) > 0:
                    victims.add(owner)
        return sorted(victims)

    def _on_hex_clicked(self, ti: int):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if g.pending_action != "robber_move":
            return
        if g.pending_pid != (self.you_pid if self.online_mode else 0):
            return
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_move_robber(ti)
            return
        if ti == g.robber_tile:
            self._log("[ROB] Pick a different hex.")
            return
        g.robber_tile = ti
        victims = self._victims_for_tile(ti, g.pending_pid or 0)
        g.pending_victims = victims
        if not victims:
            g.pending_action = None
            g.pending_pid = None
            g.pending_victims = []
            self._log("[ROB] Robber moved. No victims.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return

        g.pending_action = "robber_steal"
        self._log("[ROB] Choose a victim to steal from.")
        names = [g.players[v].name for v in victims]
        choice, ok = QtWidgets.QInputDialog.getItem(self, "Robber", "Choose player to steal from:", names, 0, False)
        target_pid = None
        if ok:
            for v in victims:
                if g.players[v].name == choice:
                    target_pid = v
                    break
        if target_pid is None:
            target_pid = random.choice(victims)
        self._steal_random(g.pending_pid or 0, target_pid)
        g.pending_action = None
        g.pending_pid = None
        g.pending_victims = []
        self._refresh_all_dynamic()
        self._sync_ui()

    def _start_free_roads(self, pid: int):
        if pid == 0:
            self._log("[DEV] Road Building: place 2 free roads.")
            self.select_action("road")

    def _bot_log(self, msg: str):
        if BOT_LOG:
            self._log(msg)

    def _bot_discard(self, pid: int):
        need = self.discard_needed(pid)
        if need <= 0:
            return 0
        pres = self.game.players[pid].res
        for _ in range(need):
            max_q = max(pres.values()) if pres else 0
            if max_q <= 0:
                break
            choices = [r for r, q in pres.items() if q == max_q and q > 0]
            r = random.choice(choices)
            pres[r] -= 1
            self.game.bank[r] += 1
        return need

    def _bot_choose_victim(self, victims: List[int]) -> int:
        best = None
        best_size = -1
        for v in victims:
            size = self.hand_size(v)
            if size > best_size:
                best_size = size
                best = v
        return best if best is not None else random.choice(victims)

    def _robber_adjacent_to_pid(self, pid: int) -> bool:
        g = self.game
        for vid, (owner, _lvl) in g.occupied_v.items():
            if owner != pid:
                continue
            if g.robber_tile in g.vertex_adj_hexes.get(vid, []):
                return True
        return False

    def _bot_move_robber(self, pid: int, target_hex: int):
        g = self.game
        g.robber_tile = target_hex
        victims = self._victims_for_tile(target_hex, pid)
        if victims:
            target_pid = self._bot_choose_victim(victims)
            self._steal_random(pid, target_pid)
        else:
            self._log("[ROB] Bot moved robber. No victims.")
        g.pending_action = None
        g.pending_pid = None
        g.pending_victims = []

    def _bot_choose_robber_tile(self) -> int:
        g = self.game
        best = None
        best_score = -999
        for ti, _t in enumerate(g.tiles):
            if ti == g.robber_tile:
                continue
            score = 0
            for vid, (owner, _lvl) in g.occupied_v.items():
                if ti not in g.vertex_adj_hexes.get(vid, []):
                    continue
                if owner == 0:
                    score += 1
                elif owner == 1:
                    score -= 1
            if score > best_score:
                best_score = score
                best = ti
        if best is None:
            choices = [i for i in range(len(g.tiles)) if i != g.robber_tile]
            return random.choice(choices) if choices else g.robber_tile
        return best

    def _bot_road_vertices(self) -> set[int]:
        g = self.game
        verts = set()
        for (a, b), owner in g.occupied_e.items():
            if owner == 1:
                verts.add(a)
                verts.add(b)
        return verts

    def _bot_choose_road_edge(self) -> Optional[Tuple[int,int]]:
        return choose_best_road(self.game, 1)

    def _bot_place_road(self, e: Optional[Tuple[int,int]], use_free: bool = False) -> bool:
        g = self.game
        if e is None:
            return False
        if not can_place_road(g, 1, e):
            return False
        if use_free and int(g.free_roads.get(1, 0)) > 0:
            g.free_roads[1] = int(g.free_roads.get(1, 0)) - 1
        else:
            if not can_pay(g.players[1], COST["road"]):
                return False
            pay_to_bank(g, 1, COST["road"])
        g.occupied_e[e] = 1
        self._log("Bot built a road.")
        update_longest_road(g, self._log)
        check_win(g, self._log)
        return True

    def _bot_build_city_at(self, vid: int) -> bool:
        g = self.game
        if not can_pay(g.players[1], COST["city"]):
            return False
        if not can_upgrade_city(g, 1, vid):
            return False
        pay_to_bank(g, 1, COST["city"])
        g.occupied_v[vid] = (1, 2)
        g.players[1].vp += 1
        self._log("Bot upgraded to a city.")
        check_win(g, self._log)
        return True

    def _bot_build_settlement_at(self, vid: int) -> bool:
        g = self.game
        if not can_pay(g.players[1], COST["settlement"]):
            return False
        if not can_place_settlement(g, 1, vid, require_road=True):
            return False
        pay_to_bank(g, 1, COST["settlement"])
        g.occupied_v[vid] = (1, 1)
        g.players[1].vp += 1
        self._log("Bot built a settlement.")
        check_win(g, self._log)
        return True

    def _bot_build_city(self) -> bool:
        vid = choose_best_city(self.game, 1)
        if vid is None:
            return False
        return self._bot_build_city_at(vid)

    def _bot_build_settlement(self) -> bool:
        vid = choose_best_settlement(self.game, 1)
        if vid is None:
            return False
        return self._bot_build_settlement_at(vid)

    def _bot_buy_dev(self) -> bool:
        g = self.game
        if not can_pay(g.players[1], COST["dev"]):
            return False
        try:
            card = g.buy_dev(1)
            self._log(f"Bot bought dev: {card}.")
            return True
        except Exception:
            return False

    def _bot_choose_actions(self, pid: int) -> List[Tuple[str, object]]:
        g = self.game
        actions: List[Tuple[str, object]] = []
        if can_pay(g.players[pid], COST["city"]):
            vid = choose_best_city(g, pid)
            if vid is not None:
                actions.append(("city", vid))
                return actions
        if can_pay(g.players[pid], COST["settlement"]):
            vid = choose_best_settlement(g, pid)
            if vid is not None:
                actions.append(("settlement", vid))
                return actions
        if can_pay(g.players[pid], COST["road"]):
            e = choose_best_road(g, pid)
            if e is not None:
                actions.append(("road", e))
                return actions
        if can_pay(g.players[pid], COST["dev"]):
            actions.append(("dev", None))
        return actions

    def _bot_find_dev_index(self, pid: int, card_type: str) -> Optional[int]:
        cards = self.game.players[pid].dev_cards
        for i, c in enumerate(list(cards)):
            if isinstance(c, dict) and c.get("type") == card_type and not c.get("new", False):
                return i
        return None

    def _bot_play_knight(self) -> bool:
        g = self.game
        if g.dev_played_turn.get(1, False):
            return False
        if self.hand_size(0) <= 0 and not self._robber_adjacent_to_pid(1):
            return False
        idx = self._bot_find_dev_index(1, "knight")
        if idx is None:
            return False
        g.players[1].dev_cards.pop(idx)
        g.dev_played_turn[1] = True
        g.players[1].knights_played += 1
        g._update_largest_army()
        target = self._bot_choose_robber_tile()
        self._bot_move_robber(1, target)
        self._bot_log("Bot played knight.")
        return True

    def _bot_play_road_building(self) -> bool:
        g = self.game
        if g.dev_played_turn.get(1, False):
            return False
        idx = self._bot_find_dev_index(1, "road_building")
        if idx is None:
            return False
        g.players[1].dev_cards.pop(idx)
        g.dev_played_turn[1] = True
        g.free_roads[1] = int(g.free_roads.get(1, 0)) + 2
        for _ in range(2):
            e = choose_best_road(g, 1)
            if not self._bot_place_road(e, use_free=True):
                break
        self._bot_log("Bot played road building.")
        return True

    def _bot_play_year_of_plenty(self) -> bool:
        g = self.game
        if g.dev_played_turn.get(1, False):
            return False
        idx = self._bot_find_dev_index(1, "year_of_plenty")
        if idx is None:
            return False

        target_costs = [COST["city"], COST["settlement"], COST["road"], COST["dev"]]
        pres = g.players[1].res
        best_need = None
        for cost in target_costs:
            need = {r: max(0, cost[r] - pres.get(r, 0)) for r in cost}
            total = sum(need.values())
            if best_need is None or total < sum(best_need.values()):
                best_need = need
        if not best_need:
            best_need = {r: 0 for r in RESOURCES}
        picks = []
        for r, n in sorted(best_need.items(), key=lambda kv: kv[1], reverse=True):
            if n > 0:
                picks += [r] * n
        while len(picks) < 2:
            picks.append("wood")
        a = picks[0]
        b = picks[1]
        qa = 2 if a == b else 1
        qb = 0 if a == b else 1
        if g.bank.get(a, 0) < qa or (b != a and g.bank.get(b, 0) < qb):
            avail = sorted(RESOURCES, key=lambda r: g.bank.get(r, 0), reverse=True)
            if not avail or g.bank.get(avail[0], 0) <= 0:
                return False
            a = avail[0]
            b = avail[1] if len(avail) > 1 and g.bank.get(avail[1], 0) > 0 else a
            qa = 2 if a == b else 1
            qb = 0 if a == b else 1
            if g.bank.get(a, 0) < qa or (b != a and g.bank.get(b, 0) < qb):
                return False
        g.players[1].dev_cards.pop(idx)
        g.dev_played_turn[1] = True
        g.bank[a] -= qa
        g.players[1].res[a] += qa
        if qb > 0:
            g.bank[b] -= qb
            g.players[1].res[b] += qb
        self._bot_log("Bot played year of plenty.")
        return True

    def _bot_play_monopoly(self) -> bool:
        g = self.game
        if g.dev_played_turn.get(1, False):
            return False
        idx = self._bot_find_dev_index(1, "monopoly")
        if idx is None:
            return False
        pres = g.players[0].res
        r = max(pres.keys(), key=lambda k: pres.get(k, 0))
        taken = pres.get(r, 0)
        if taken <= 0:
            return False
        g.players[1].dev_cards.pop(idx)
        g.dev_played_turn[1] = True
        g.players[0].res[r] -= taken
        g.players[1].res[r] += taken
        self._bot_log(f"Bot played monopoly on {r}.")
        return True

    def select_action(self, key: str):
        if self.game.game_over:
            self._log(f"Game over. Winner: P{self.game.winner_pid}")
            return
        self.selected_action = key
        # make checkable group
        for b in (self.btn_sett, self.btn_road, self.btn_city):
            b.setChecked(False)
        {"settlement":self.btn_sett,"road":self.btn_road,"city":self.btn_city}[key].setChecked(True)
        self._refresh_all_dynamic()
        self._sync_ui()

    def on_send_chat(self):
        txt = self.chat_in.text().strip()
        if not txt:
            return
        self.chat_in.clear()
        self._chat(f"You: {txt}")
        # simple bot reply
        self._chat("Bot: ok.")

    def on_roll_click(self):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_roll()
            return
        if g.phase != "main":
            self._log("[!] Roll is available after setup.")
            return
        if g.turn != 0:
            self._log("[!] Wait: bot turn.")
            return
        if g.rolled:
            self._log("[!] Already rolled.")
            return
        a = random.randint(1,6)
        b = random.randint(1,6)
        g.last_roll = a+b
        g.rolled = True
        self.d1.setIcon(QtGui.QIcon(dice_face(a)))
        self.d2.setIcon(QtGui.QIcon(dice_face(b)))
        self._log(f"You rolled {g.last_roll}.")
        if g.last_roll == 7:
            need = self.discard_needed(0)
            if need > 0:
                dlg = DiscardDialog(self, g.players[0].res, need)
                if dlg.exec() != QtWidgets.QDialog.Accepted:
                    g.rolled = False
                    g.last_roll = None
                    self._log("[7] Discard canceled.")
                    return
                self._apply_discard(0, dlg.selected())
                self._log(f"[7] You discarded {need}.")
            bot_need = self.discard_needed(1)
            if bot_need > 0:
                self._bot_discard(1)
                self._log(f"[7] Bot discarded {bot_need}.")
            g.roll_history.append(g.last_roll)
            g.pending_action = "robber_move"
            g.pending_pid = 0
            g.pending_victims = []
            self._log("[7] Move the robber.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return
        g.roll_history.append(g.last_roll)
        distribute_for_roll(g, g.last_roll, self._log)
        self._refresh_all_dynamic()
        self._sync_ui()

    def on_end_turn(self):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_end_turn()
            return
        if g.phase == "setup":
            self._log("[!] Finish setup by placing required piece(s).")
            return
        if g.turn == 0 and not g.rolled:
            self._log("[!] Roll first.")
            return
        if g.pending_action is not None:
            self._log("[!] Resolve pending action first.")
            return
        g.end_turn_cleanup(g.turn)
        # end
        g.turn = 1 - g.turn
        g.rolled = False
        g.last_roll = None
        if g.turn == 1:
            if self.bot_enabled:
                self._bot_turn()
            else:
                self._log("Bot disabled. Skipping bot turn.")
                g.turn = 0
                g.rolled = False
                g.last_roll = None
        else:
            self._log("Turn: You")
        self._refresh_all_dynamic()
        self._sync_ui()

    def _bot_turn(self):
        g = self.game
        if g.game_over:
            return
        if not self.bot_enabled:
            return
        if g.pending_action is not None:
            return

        # roll if needed
        if not g.rolled:
            a = random.randint(1,6)
            b = random.randint(1,6)
            g.last_roll = a+b
            g.rolled = True
            g.roll_history.append(g.last_roll)
            self._log(f"Bot rolled {g.last_roll}.")
            if g.last_roll == 7:
                bot_need = self._bot_discard(1)
                if bot_need > 0:
                    self._log(f"[7] Bot discarded {bot_need}.")
                target = self._bot_choose_robber_tile()
                self._bot_move_robber(1, target)
            else:
                distribute_for_roll(g, g.last_roll, self._log)

        if g.game_over or g.pending_action is not None:
            return

        actions_done = 0
        while actions_done < 2:
            actions = self._bot_choose_actions(1)
            if not actions:
                break
            name, arg = actions[0]
            self._bot_log(f"Bot action: {name}")
            ok = False
            if name == "city":
                ok = self._bot_build_city_at(arg)
            elif name == "settlement":
                ok = self._bot_build_settlement_at(arg)
            elif name == "road":
                ok = self._bot_place_road(arg, use_free=False)
            elif name == "dev":
                ok = self._bot_buy_dev()
            if not ok:
                break
            actions_done += 1
            if g.game_over or g.pending_action is not None:
                return

        # dev cards (max 1 per turn)
        if self._bot_play_knight():
            pass
        elif self._bot_play_road_building():
            pass
        elif self._bot_play_year_of_plenty():
            pass
        elif self._bot_play_monopoly():
            pass
        if g.game_over:
            return
        if g.pending_action is not None:
            return

        # end turn back
        g.end_turn_cleanup(1)
        g.turn = 0
        g.rolled = False
        g.last_roll = None
        self._log("Turn: You")

    # ---------- Legal spots + placement handlers ----------
    def _show_legal_spots(self):
        g = self.game
        pid = g.turn
        if g.game_over:
            return
        if g.pending_action is not None:
            return
        if pid != 0 and g.phase == "main":
            return

        # setup rules: forced sequence settlement->road, no road requirement for settlement
        if g.phase == "setup":
            if g.setup_need == "settlement":
                # show all legal settlement nodes
                for vid in g.vertices.keys():
                    if can_place_settlement(g, g.setup_order[g.setup_idx], vid, require_road=False):
                        self._add_node_spot(vid, forced_pid=g.setup_order[g.setup_idx])
            else:
                # show only roads from anchor
                assert g.setup_anchor_vid is not None
                for e in g.edges:
                    if g.setup_anchor_vid in e and can_place_road(g, g.setup_order[g.setup_idx], e, must_touch_vid=g.setup_anchor_vid):
                        self._add_edge_spot(e, forced_pid=g.setup_order[g.setup_idx])
            return

        # main phase (player only for now)
        if pid != 0:
            return

        if self.selected_action == "settlement":
            # require road connection in main phase
            for vid in g.vertices.keys():
                if can_place_settlement(g, 0, vid, require_road=True):
                    self._add_node_spot(vid, forced_pid=0)
        elif self.selected_action == "road":
            for e in g.edges:
                if can_place_road(g, 0, e):
                    self._add_edge_spot(e, forced_pid=0)
        elif self.selected_action == "city":
            for vid in g.vertices.keys():
                if can_upgrade_city(g, 0, vid):
                    self._add_node_spot(vid, forced_pid=0)
        elif self.selected_action == "dev":
            # dev is click in UI later; keep no board overlays now
            pass

    def _add_node_spot(self, vid: int, forced_pid: int):
        if vid in self.overlay_nodes:
            return
        p = self.game.vertices[vid]
        r = 8
        rect = QtCore.QRectF(p.x()-r, p.y()-r, r*2, r*2)
        def on_click():
            self._on_node_clicked(vid, forced_pid)
        it = ClickableEllipse(rect, on_click)
        it.setBrush(QtGui.QColor(PALETTE["ui_panel_input"]))
        it.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 2))
        it.setZValue(20)
        self.scene.addItem(it)
        self.overlay_nodes[vid] = it

    def _add_edge_spot(self, e: Tuple[int,int], forced_pid: int):
        if e in self.overlay_edges:
            return
        a,b = e
        pa = self.game.vertices[a]
        pb = self.game.vertices[b]
        path = QtGui.QPainterPath(pa)
        path.lineTo(pb)
        def on_click():
            self._on_edge_clicked(e, forced_pid)
        it = ClickableLine(path, on_click)
        it.setZValue(19)
        self.scene.addItem(it)
        self.overlay_edges[e] = it

    def _on_node_clicked(self, vid: int, pid: int):
        g = self.game
        if g.pending_action is not None:
            self._log("[!] Resolve pending action first.")
            return
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode and self.online_controller:
            if g.phase == "setup":
                self.online_controller.cmd_place_settlement(vid, setup=True)
                return
            if self.selected_action == "settlement":
                self.online_controller.cmd_place_settlement(vid, setup=False)
            elif self.selected_action == "city":
                self.online_controller.cmd_upgrade_city(vid)
            return
        if g.phase == "setup":
            # settlement step
            if g.setup_need != "settlement":
                return
            if not can_place_settlement(g, pid, vid, require_road=False):
                return
            g.occupied_v[vid] = (pid, 1)
            g.players[pid].vp += 1
            self._log(f"{g.players[pid].name} placed a settlement.")
            update_longest_road(g, self._log)
            check_win(g, self._log)
            g.setup_need = "road"
            g.setup_anchor_vid = vid
            self._refresh_all_dynamic()
            self._sync_ui()
            return

        # main phase:
        if pid != 0:
            return
        if self.selected_action == "settlement":
            if not can_pay(g.players[0], COST["settlement"]):
                self._log("[!] Not enough resources for settlement.")
                return
            if not can_place_settlement(g, 0, vid, require_road=True):
                return
            pay_to_bank(g, 0, COST["settlement"])
            g.occupied_v[vid] = (0, 1)
            g.players[0].vp += 1
            self._log("You built a settlement.")
            update_longest_road(g, self._log)
            check_win(g, self._log)
        elif self.selected_action == "city":
            if not can_pay(g.players[0], COST["city"]):
                self._log("[!] Not enough resources for city.")
                return
            if not can_upgrade_city(g, 0, vid):
                return
            pay_to_bank(g, 0, COST["city"])
            g.occupied_v[vid] = (0, 2)
            g.players[0].vp += 1
            self._log("You upgraded to a city.")
            update_longest_road(g, self._log)
            check_win(g, self._log)
        self._refresh_all_dynamic()
        self._sync_ui()

    def _on_edge_clicked(self, e: Tuple[int,int], pid: int):
        g = self.game
        if g.pending_action is not None:
            self._log("[!] Resolve pending action first.")
            return
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if self.online_mode and self.online_controller:
            if g.phase == "setup":
                self.online_controller.cmd_place_road(e, setup=True)
                return
            if self.selected_action == "road":
                self.online_controller.cmd_place_road(e, setup=False)
            return
        if g.phase == "setup":
            if g.setup_need != "road":
                return
            if not can_place_road(g, pid, e, must_touch_vid=g.setup_anchor_vid):
                return
            g.occupied_e[e] = pid
            self._log(f"{g.players[pid].name} placed a road.")
            update_longest_road(g, self._log)
            check_win(g, self._log)
            g.setup_need = "settlement"
            g.setup_anchor_vid = None
            g.setup_idx += 1

            # finish setup after 4 placements (2 per player in 2p)
            if g.setup_idx >= len(g.setup_order):
                g.phase = "main"
                self._log("[SYS] Setup finished. Now roll dice to start.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return

        # main phase
        if pid != 0:
            return
        if self.selected_action != "road":
            return
        if not can_place_road(g, 0, e):
            return
        free_left = int(g.free_roads.get(0, 0))
        if free_left > 0:
            g.free_roads[0] = free_left - 1
            self._log("[DEV] Free road placed.")
        else:
            if not can_pay(g.players[0], COST["road"]):
                self._log("[!] Not enough resources for road.")
                return
            pay_to_bank(g, 0, COST["road"])
        g.occupied_e[e] = 0
        self._log("You built a road.")
        update_longest_road(g, self._log)
        check_win(g, self._log)
        self._refresh_all_dynamic()
        self._sync_ui()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
