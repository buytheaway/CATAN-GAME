import os, sys, math, random, json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple, Optional, Set

from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from app.dev_hand_overlay import attach_dev_hand_overlay
from app.dev_ui import DevDialog
from app.trade_ui import TradeDialog
from app.config import GameConfig
from app.engine import rules as engine_rules
from app.engine import serialize as engine_serialize
from app.engine.state import COST, RESOURCES, TERRAIN_TO_RES, TradeOffer
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
        "sea": PALETTE["terrain_sea"],
        "gold": PALETTE["terrain_gold"],
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


_SVG_RENDERERS: Dict[str, QtSvg.QSvgRenderer] = {}
_SVG_PIXMAP_CACHE: Dict[Tuple[str, int, int, int], QtGui.QPixmap] = {}


def _svg_tinted_pixmap(rel: str, size: Tuple[int, int], color: QtGui.QColor) -> QtGui.QPixmap:
    w, h = int(size[0]), int(size[1])
    key = (rel, w, h, int(color.rgba()))
    cached = _SVG_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    renderer = _SVG_RENDERERS.get(rel)
    if renderer is None:
        renderer = load_svg(rel)
        _SVG_RENDERERS[rel] = renderer
    if not renderer.isValid() or w <= 0 or h <= 0:
        pm = QtGui.QPixmap()
        _SVG_PIXMAP_CACHE[key] = pm
        return pm
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    renderer.render(p, QtCore.QRectF(0, 0, w, h))
    p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
    p.fillRect(QtCore.QRectF(0, 0, w, h), color)
    p.end()
    _SVG_PIXMAP_CACHE[key] = pm
    return pm


def _rules_value(cfg: Any, key: str, default: Any) -> Any:
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    if cfg is None:
        return default
    return getattr(cfg, key, default)

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
    elif name in ("ship", "move_ship"):
        hull = QtGui.QPolygonF([
            QtCore.QPointF(size*0.18, size*0.62),
            QtCore.QPointF(size*0.82, size*0.62),
            QtCore.QPointF(size*0.70, size*0.78),
            QtCore.QPointF(size*0.30, size*0.78),
        ])
        p.drawPolygon(hull)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawLine(int(size*0.50), int(size*0.25), int(size*0.50), int(size*0.62))
        p.setBrush(fg)
        sail = QtGui.QPolygonF([
            QtCore.QPointF(size*0.50, size*0.28),
            QtCore.QPointF(size*0.72, size*0.58),
            QtCore.QPointF(size*0.50, size*0.58),
        ])
        p.drawPolygon(sail)
        if name == "move_ship":
            p.setPen(QtGui.QPen(fg, 2))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawLine(int(size*0.25), int(size*0.35), int(size*0.75), int(size*0.35))
            p.setBrush(fg)
            p.drawPolygon(QtGui.QPolygonF([
                QtCore.QPointF(size*0.75, size*0.28),
                QtCore.QPointF(size*0.88, size*0.35),
                QtCore.QPointF(size*0.75, size*0.42),
            ]))
    elif name == "pirate":
        p.setPen(QtGui.QPen(fg, 2))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(QtCore.QRectF(size*0.22, size*0.22, size*0.56, size*0.56))
        p.setBrush(fg)
        p.drawEllipse(QtCore.QRectF(size*0.38, size*0.40, size*0.08, size*0.08))
        p.drawEllipse(QtCore.QRectF(size*0.54, size*0.40, size*0.08, size*0.08))
        p.drawRect(QtCore.QRectF(size*0.42, size*0.58, size*0.16, size*0.08))
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
    map_id: str = "base_standard"
    map_meta: Dict[str, Any] = field(default_factory=dict)
    rules_config: Any = None
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
    occupied_ships: Dict[Tuple[int,int], int] = field(default_factory=dict)    # (a,b)-> pid

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
    robbers: List[int] = field(default_factory=list)
    pirate_tile: Optional[int] = None
    pending_action: Optional[str] = None   # "discard" | "robber_move" | "robber_steal" | None
    pending_pid: Optional[int] = None
    pending_victims: List[int] = field(default_factory=list)
    discard_required: Dict[int, int] = field(default_factory=dict)
    discard_submitted: Set[int] = field(default_factory=set)
    pending_gold: Dict[int, int] = field(default_factory=dict)
    pending_gold_queue: List[int] = field(default_factory=list)
    longest_road_owner: Optional[int] = None
    longest_road_len: int = 0
    game_over: bool = False
    winner_pid: Optional[int] = None
    roll_history: List[int] = field(default_factory=list)
    dev_deck: List[str] = field(default_factory=list)
    dev_played_turn: Dict[int, bool] = field(default_factory=dict)
    free_roads: Dict[int, int] = field(default_factory=dict)
    largest_army_owner: Optional[int] = None
    largest_army_size: int = 0
    trade_offers: List[TradeOffer] = field(default_factory=list)
    trade_offer_next_id: int = 1

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
        return engine_rules.player_ports(self, pid)

    def best_trade_rate(self, pid: int, give_res: str) -> int:
        return engine_rules.best_trade_rate(self, pid, give_res)

    def trade_with_bank(self, pid: int, give_res: str, get_res: str, get_qty: int) -> int:
        try:
            return engine_rules.trade_with_bank(self, pid, give_res, get_res, get_qty)
        except engine_rules.RuleError as exc:
            raise ValueError(exc.message) from None

    def end_turn_cleanup(self, pid: int) -> None:
        engine_rules.end_turn_cleanup(self, pid)

    def buy_dev(self, pid: int) -> str:
        try:
            return engine_rules.buy_dev(self, pid)
        except engine_rules.RuleError as exc:
            raise ValueError(exc.message) from None

    def play_dev(self, pid: int, card_type: str, **kwargs):
        try:
            return engine_rules.play_dev(self, pid, card_type, **kwargs)
        except engine_rules.RuleError as exc:
            raise ValueError(exc.message) from None


def _convert_base_state(base) -> Game:
    def _pt(p):
        return QtCore.QPointF(float(p[0]), float(p[1]))

    g = Game(seed=base.seed, size=base.size)
    g.map_id = str(base.map_id)
    g.map_meta = dict(getattr(base, "map_meta", {}) or {})
    g.rules_config = getattr(base, "rules_config", None)
    g.tiles = [
        HexTile(q=t.q, r=t.r, terrain=t.terrain, number=t.number, center=_pt(t.center))
        for t in base.tiles
    ]
    g.vertices = {int(k): _pt(v) for k, v in base.vertices.items()}
    g.vertex_adj_hexes = {int(k): list(v) for k, v in base.vertex_adj_hexes.items()}
    g.edges = set(base.edges)
    g.edge_adj_hexes = {k: list(v) for k, v in base.edge_adj_hexes.items()}
    g.ports = list(base.ports)

    g.players = []
    for p in base.players:
        pl = Player(p.name, QtGui.QColor(PLAYER_COLORS[p.pid]))
        pl.res = dict(p.res)
        pl.vp = int(p.vp)
        pl.dev_cards = list(getattr(p, "dev_cards", []))
        pl.knights_played = int(getattr(p, "knights_played", 0))
        g.players.append(pl)

    g.bank = dict(base.bank)
    g.occupied_v = dict(base.occupied_v)
    g.occupied_e = dict(base.occupied_e)
    g.occupied_ships = dict(getattr(base, "occupied_ships", {}))
    g.turn = int(base.turn)
    g.phase = base.phase
    g.rolled = bool(base.rolled)
    g.setup_order = list(base.setup_order)
    g.setup_idx = int(base.setup_idx)
    g.setup_need = base.setup_need
    g.setup_anchor_vid = base.setup_anchor_vid
    g.last_roll = base.last_roll
    g.robber_tile = int(base.robber_tile)
    g.robbers = list(getattr(base, "robbers", [g.robber_tile]))
    g.pirate_tile = getattr(base, "pirate_tile", None)
    g.pending_action = base.pending_action
    g.pending_pid = base.pending_pid
    g.pending_victims = list(base.pending_victims)
    g.discard_required = dict(base.discard_required)
    g.discard_submitted = set(base.discard_submitted)
    g.pending_gold = dict(getattr(base, "pending_gold", {}))
    g.pending_gold_queue = list(getattr(base, "pending_gold_queue", []))
    g.longest_road_owner = base.longest_road_owner
    g.longest_road_len = int(base.longest_road_len)
    g.largest_army_owner = base.largest_army_owner
    g.largest_army_size = int(base.largest_army_size)
    g.game_over = bool(base.game_over)
    g.winner_pid = base.winner_pid
    g.roll_history = list(getattr(base, "roll_history", []))
    g.dev_deck = list(getattr(base, "dev_deck", []))
    g.dev_played_turn = dict(getattr(base, "dev_played_turn", {}))
    g.free_roads = dict(getattr(base, "free_roads", {}))
    g.trade_offers = list(getattr(base, "trade_offers", []))
    g.trade_offer_next_id = int(getattr(base, "trade_offer_next_id", 1))
    return g


def _rules_cfg_to_dict(cfg: Any) -> Dict[str, Any]:
    if cfg is None:
        return {}
    if isinstance(cfg, dict):
        return dict(cfg)
    out = {}
    for key in ("target_vp", "max_roads", "max_settlements", "max_cities", "robber_count", "enable_seafarers", "max_ships", "enable_pirate", "enable_gold", "enable_move_ship"):
        if hasattr(cfg, key):
            out[key] = getattr(cfg, key)
    return out


def _ui_game_to_engine_dict(g: Game) -> Dict[str, Any]:
    def _edge_key(e: Tuple[int, int]) -> str:
        a, b = e
        return f"{a},{b}"

    data = {
        "state_version": 0,
        "seed": int(g.seed),
        "max_players": len(g.players),
        "size": float(g.size),
        "map_name": g.map_id,
        "map_id": g.map_id,
        "map_meta": dict(g.map_meta or {}),
        "rules": {},
        "rules_config": _rules_cfg_to_dict(g.rules_config),
        "phase": g.phase,
        "turn": g.turn,
        "rolled": bool(g.rolled),
        "setup_order": list(g.setup_order),
        "setup_idx": int(g.setup_idx),
        "setup_need": g.setup_need,
        "setup_anchor_vid": g.setup_anchor_vid,
        "last_roll": g.last_roll,
        "robber_tile": int(g.robber_tile),
        "robbers": list(g.robbers or [g.robber_tile]),
        "pirate_tile": g.pirate_tile,
        "pending_action": g.pending_action,
        "pending_pid": g.pending_pid,
        "pending_victims": list(g.pending_victims),
        "discard_required": {str(k): int(v) for k, v in g.discard_required.items()},
        "discard_submitted": [int(x) for x in g.discard_submitted],
        "pending_gold": {str(k): int(v) for k, v in g.pending_gold.items()},
        "pending_gold_queue": [int(x) for x in g.pending_gold_queue],
        "trade_offers": [
            {
                "offer_id": o.offer_id,
                "from_pid": o.from_pid,
                "to_pid": o.to_pid,
                "give": dict(o.give),
                "get": dict(o.get),
                "status": o.status,
                "created_turn": o.created_turn,
                "created_tick": o.created_tick,
            }
            for o in g.trade_offers
        ],
        "trade_offer_next_id": g.trade_offer_next_id,
        "longest_road_owner": g.longest_road_owner,
        "longest_road_len": g.longest_road_len,
        "largest_army_owner": g.largest_army_owner,
        "largest_army_size": g.largest_army_size,
        "game_over": g.game_over,
        "winner_pid": g.winner_pid,
        "players": [
            {
                "pid": idx,
                "name": p.name,
                "vp": p.vp,
                "res": dict(p.res),
                "knights_played": getattr(p, "knights_played", 0),
            }
            for idx, p in enumerate(g.players)
        ],
        "bank": dict(g.bank),
        "occupied_v": {str(k): [v[0], v[1]] for k, v in g.occupied_v.items()},
        "occupied_e": {_edge_key(e): owner for e, owner in g.occupied_e.items()},
        "occupied_ships": {_edge_key(e): owner for e, owner in g.occupied_ships.items()},
        "tiles": [
            {
                "q": t.q,
                "r": t.r,
                "terrain": t.terrain,
                "number": t.number,
                "center": [float(t.center.x()), float(t.center.y())],
            }
            for t in g.tiles
        ],
        "vertices": {str(k): [float(v.x()), float(v.y())] for k, v in g.vertices.items()},
        "edges": [[a, b] for a, b in sorted(g.edges)],
        "vertex_adj_hexes": {str(k): list(v) for k, v in g.vertex_adj_hexes.items()},
        "edge_adj_hexes": {_edge_key(e): v for e, v in g.edge_adj_hexes.items()},
        "ports": [[[a, b], kind] for (a, b), kind in g.ports],
    }
    hidden = {
        "dev_deck": list(g.dev_deck),
        "dev_played_turn": dict(g.dev_played_turn),
        "free_roads": dict(g.free_roads),
        "roll_history": list(g.roll_history),
        "player_dev_cards": [list(p.dev_cards) for p in g.players],
    }
    data["_offline_hidden"] = hidden
    return data


def build_board(
    seed: int,
    size: float,
    map_id: Optional[str] = None,
    player_names: Optional[List[str]] = None,
    max_players: int = 2,
    map_path: Optional[str] = None,
    map_data: Optional[Dict[str, Any]] = None,
) -> Game:
    if player_names is None:
        player_names = ["You", "Bot"]
    if map_path or map_data:
        map_id = None
    base = engine_rules.build_game(
        seed=seed,
        max_players=max_players,
        size=size,
        player_names=player_names,
        map_id=map_id,
        map_path=map_path,
        map_data=map_data,
    )
    return _convert_base_state(base)

def edge_neighbors_of_vertex(edges: Set[Tuple[int,int]], vid: int) -> Set[int]:
    return engine_rules.edge_neighbors_of_vertex(edges, vid)

def can_place_settlement(g: Game, pid: int, vid: int, require_road: bool) -> bool:
    return engine_rules.can_place_settlement(g, pid, vid, require_road=require_road)

def can_place_road(g: Game, pid: int, e: Tuple[int,int], must_touch_vid: Optional[int]=None) -> bool:
    return engine_rules.can_place_road(g, pid, e, must_touch_vid=must_touch_vid)

def can_place_ship(g: Game, pid: int, e: Tuple[int,int]) -> bool:
    return engine_rules.can_place_ship(g, pid, e)

def can_upgrade_city(g: Game, pid: int, vid: int) -> bool:
    return engine_rules.can_upgrade_city(g, pid, vid)

def distribute_for_roll(g: Game, roll: int, log_cb):
    engine_rules.distribute_for_roll(g, roll)
    log_cb(f"[ROLL] distributed resources for {roll} (bank limits applied).")

def can_pay(p: Player, cost: Dict[str,int]) -> bool:
    return engine_rules.can_pay(p, cost)
def pay_to_bank(g: Game, pid: int, cost: Dict[str,int]):
    engine_rules.pay_to_bank(g, pid, cost)

def longest_road_length(g: Game, pid: int) -> int:
    return engine_rules.longest_road_length(g, pid)

def update_longest_road(g: Game, log_cb=None) -> None:
    before_owner = g.longest_road_owner
    before_len = g.longest_road_len
    engine_rules.update_longest_road(g)
    if log_cb and (before_owner != g.longest_road_owner or before_len != g.longest_road_len):
        if g.longest_road_owner is None:
            log_cb("Longest Road: none")
        else:
            log_cb(f"Longest Road: P{g.longest_road_owner + 1} (len {g.longest_road_len})")

def check_win(g: Game, log_cb=None) -> None:
    before = g.game_over
    engine_rules.check_win(g)
    if log_cb and not before and g.game_over:
        log_cb(f"Game over. Winner: P{g.winner_pid}")

def expected_vertex_yield(g: Game, vid: int, pid: int) -> int:
    score = 0
    robbers = set(getattr(g, "robbers", []) or [g.robber_tile])
    for ti in g.vertex_adj_hexes.get(vid, []):
        if ti in robbers:
            continue
        t = g.tiles[ti]
        if t.number is None:
            continue
        res = TERRAIN_TO_RES.get(t.terrain)
        if not res:
            continue
        score += PIPS.get(t.number, 0)
        if res in ("ore", "wheat"):
            score += 0.2
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


class GoldChoiceDialog(QtWidgets.QDialog):
    def __init__(self, parent, need: int):
        super().__init__(parent)
        self.setWindowTitle("Gold Choice")
        self.setModal(True)
        self._need = int(need)
        self._res = "wood"
        self._qty = 1

        root = QtWidgets.QVBoxLayout(self)
        lbl = QtWidgets.QLabel(f"Choose {self._need} resource(s) from Gold.")
        root.addWidget(lbl)

        form = QtWidgets.QFormLayout()
        self._combo = QtWidgets.QComboBox()
        self._combo.addItems(list(RESOURCES))
        self._combo.currentTextChanged.connect(self._on_res)
        form.addRow("Resource", self._combo)

        self._spin = QtWidgets.QSpinBox()
        self._spin.setRange(1, max(1, self._need))
        self._spin.setValue(min(1, self._need))
        self._spin.valueChanged.connect(self._on_qty)
        form.addRow("Quantity", self._spin)
        root.addLayout(form)

        self._btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        root.addWidget(self._btns)

    def _on_res(self, val: str):
        self._res = str(val)

    def _on_qty(self, val: int):
        self._qty = int(val)

    def selected(self) -> Tuple[str, int]:
        return (self._res, int(self._qty))

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
        if g.largest_army_owner is not None:
            la = f"P{g.largest_army_owner + 1} (size {g.largest_army_size})"
        vp_line = " / ".join([f"P{i + 1} {p.vp}" for i, p in enumerate(g.players)])
        self.overview_label.setText(
            f"Final VP: {vp_line}\n"
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

        self.badge_row = QtWidgets.QHBoxLayout()
        self.badges: List[QtWidgets.QLabel] = []
        root.addLayout(self.badge_row)

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
        lbl_vp = QtWidgets.QLabel("Target VP")
        lbl_rb = QtWidgets.QLabel("Robbers")
        for lbl in (lbl_lr, lbl_la, lbl_vp, lbl_rb):
            lbl.setStyleSheet(f"color:{PALETTE['ui_text_muted']}; font-size:11px;")
        self.lbl_longest = QtWidgets.QLabel("none")
        self.lbl_army = QtWidgets.QLabel("none")
        self.lbl_target = QtWidgets.QLabel("-")
        self.lbl_robbers = QtWidgets.QLabel("-")
        for lbl in (self.lbl_longest, self.lbl_army, self.lbl_target, self.lbl_robbers):
            lbl.setStyleSheet("font-size:12px; font-weight:600;")
        row.addWidget(lbl_lr, 0, 0)
        row.addWidget(self.lbl_longest, 0, 1)
        row.addWidget(lbl_la, 1, 0)
        row.addWidget(self.lbl_army, 1, 1)
        row.addWidget(lbl_vp, 2, 0)
        row.addWidget(self.lbl_target, 2, 1)
        row.addWidget(lbl_rb, 3, 0)
        row.addWidget(self.lbl_robbers, 3, 1)
        root.addLayout(row)

    def _ensure_badges(self, count: int):
        while len(self.badges) < count:
            lbl = QtWidgets.QLabel("")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet(f"font-size:12px; padding:5px 12px; border-radius:10px; background:{PALETTE['ui_panel_outline']};")
            self.badges.append(lbl)
            self.badge_row.addWidget(lbl)
        while len(self.badges) > count:
            lbl = self.badges.pop()
            self.badge_row.removeWidget(lbl)
            lbl.deleteLater()

    def update_from_game(self, g):
        self._ensure_badges(len(g.players))
        for idx, p in enumerate(g.players):
            self.badges[idx].setText(f"P{idx + 1} {p.name} {p.vp} VP")
        active_style = f"font-size:12px; padding:4px 10px; border-radius:10px; background:{PALETTE['ui_accent']}; color:{PALETTE['ui_text_dark']}; font-weight:800;"
        idle_style = f"font-size:12px; padding:4px 10px; border-radius:10px; background:{PALETTE['ui_panel_outline']}; color:{PALETTE['ui_text_bright']};"
        if g.game_over and g.winner_pid is not None:
            for idx, lbl in enumerate(self.badges):
                lbl.setStyleSheet(active_style if g.winner_pid == idx else idle_style)
        else:
            for idx, lbl in enumerate(self.badges):
                lbl.setStyleSheet(active_style if g.turn == idx else idle_style)
        if g.game_over:
            self.badge_phase.setText("Phase: game over")
            self.badge_turn.setText(f"Winner: P{g.winner_pid + 1}")
        else:
            self.badge_phase.setText(f"Phase: {g.phase}")
            self.badge_turn.setText(f"Turn: {g.players[g.turn].name}")
        pending = g.pending_action or "none"
        self.badge_pending.setText(f"Pending: {pending}")
        cfg = getattr(g, "rules_config", None)
        if isinstance(cfg, dict):
            target_vp = int(cfg.get("target_vp", 10))
            robber_count = int(cfg.get("robber_count", 1))
        else:
            target_vp = int(getattr(cfg, "target_vp", 10)) if cfg is not None else 10
            robber_count = int(getattr(cfg, "robber_count", 1)) if cfg is not None else 1
        self.lbl_target.setText(str(target_vp))
        if robber_count <= 0:
            robber_count = len(getattr(g, "robbers", []) or [])
        self.lbl_robbers.setText(str(robber_count))

        lr = "none" if g.longest_road_owner is None else f"P{g.longest_road_owner + 1} (len {g.longest_road_len})"
        la = "none"
        if g.largest_army_owner is not None:
            la = f"P{g.largest_army_owner + 1} (size {g.largest_army_size})"
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
        self.setToolTip(f"{self.name}: {int(value)}")

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

    def update_from_game(self, g, pid: int = 0):
        if not g.players:
            return
        pid = max(0, min(int(pid), len(g.players) - 1))
        for r in RESOURCES:
            self.hand_chips[r].set_count(g.players[pid].res[r])
            self.bank_chips[r].set_count(g.bank[r])

class TradeOffersPanel(QtWidgets.QFrame):
    def __init__(self, on_create, on_accept, on_decline, on_cancel):
        super().__init__()
        self._on_create = on_create
        self._on_accept = on_accept
        self._on_decline = on_decline
        self._on_cancel = on_cancel
        self._offer_by_row: Dict[int, Dict[str, Any]] = {}
        self._player_names: List[str] = []
        self._you_pid = 0

        self.setStyleSheet(f"""
            TradeOffersPanel {{
                background: qlineargradient(
                  x1:0, y1:0, x2:1, y2:1,
                  stop:0 {PALETTE['ui_panel_soft']},
                  stop:1 {PALETTE['ui_panel_input']});
                border: 1px solid {PALETTE['ui_panel_outline']};
                border-radius: 16px;
            }}
        """)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        title = QtWidgets.QLabel("Player Trade")
        title.setStyleSheet("font-weight:700; font-size:12px;")
        root.addWidget(title)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)

        self.give_spins = {}
        self.get_spins = {}
        for i, res in enumerate(RESOURCES):
            give_lbl = QtWidgets.QLabel(res)
            give_lbl.setStyleSheet("font-size:11px; opacity:0.9;")
            give_sp = QtWidgets.QSpinBox()
            give_sp.setRange(0, 10)
            give_sp.setFixedWidth(52)
            get_sp = QtWidgets.QSpinBox()
            get_sp.setRange(0, 10)
            get_sp.setFixedWidth(52)
            self.give_spins[res] = give_sp
            self.get_spins[res] = get_sp
            form.addWidget(give_lbl, i, 0)
            form.addWidget(give_sp, i, 1)
            form.addWidget(get_sp, i, 2)
            if i == 0:
                form.addWidget(QtWidgets.QLabel("Give"), 0, 1)
                form.addWidget(QtWidgets.QLabel("Get"), 0, 2)

        self.cb_to = QtWidgets.QComboBox()
        self.cb_to.addItem("Any")
        form.addWidget(QtWidgets.QLabel("To"), len(RESOURCES), 0)
        form.addWidget(self.cb_to, len(RESOURCES), 1, 1, 2)
        root.addLayout(form)

        self.btn_create = QtWidgets.QPushButton("Create Offer")
        self.btn_create.clicked.connect(self._create_offer)
        root.addWidget(self.btn_create)

        self.list_offers = QtWidgets.QListWidget()
        self.list_offers.setStyleSheet(f"background:{PALETTE['ui_panel_input']}; border-radius:10px;")
        self.list_offers.itemSelectionChanged.connect(self._refresh_buttons)
        root.addWidget(self.list_offers, 1)

        row = QtWidgets.QHBoxLayout()
        self.btn_accept = QtWidgets.QPushButton("Accept")
        self.btn_decline = QtWidgets.QPushButton("Decline")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_accept.clicked.connect(self._accept_offer)
        self.btn_decline.clicked.connect(self._decline_offer)
        self.btn_cancel.clicked.connect(self._cancel_offer)
        row.addWidget(self.btn_accept)
        row.addWidget(self.btn_decline)
        row.addWidget(self.btn_cancel)
        root.addLayout(row)

    def _payload_from_spins(self, spins: Dict[str, QtWidgets.QSpinBox]) -> Dict[str, int]:
        payload = {}
        for res, sp in spins.items():
            val = int(sp.value())
            if val > 0:
                payload[res] = val
        return payload

    def _reset_spins(self):
        for sp in list(self.give_spins.values()) + list(self.get_spins.values()):
            sp.setValue(0)

    def _create_offer(self):
        give = self._payload_from_spins(self.give_spins)
        get = self._payload_from_spins(self.get_spins)
        if not give or not get:
            return
        to_idx = self.cb_to.currentIndex()
        to_pid = None
        if to_idx > 0:
            to_pid = to_idx - 1
        self._on_create(give, get, to_pid)
        self._reset_spins()

    def _selected_offer(self) -> Optional[Dict[str, Any]]:
        row = self.list_offers.currentRow()
        return self._offer_by_row.get(row)

    def _accept_offer(self):
        offer = self._selected_offer()
        if offer:
            self._on_accept(int(offer["offer_id"]))

    def _decline_offer(self):
        offer = self._selected_offer()
        if offer:
            self._on_decline(int(offer["offer_id"]))

    def _cancel_offer(self):
        offer = self._selected_offer()
        if offer:
            self._on_cancel(int(offer["offer_id"]))

    def _fmt_payload(self, payload: Dict[str, int]) -> str:
        parts = []
        for r in RESOURCES:
            q = int(payload.get(r, 0))
            if q:
                parts.append(f"{q} {r}")
        return ", ".join(parts) if parts else "-"

    def _offer_dict(self, offer: Any) -> Dict[str, Any]:
        if isinstance(offer, dict):
            return offer
        return {
            "offer_id": getattr(offer, "offer_id", -1),
            "from_pid": getattr(offer, "from_pid", 0),
            "to_pid": getattr(offer, "to_pid", None),
            "give": dict(getattr(offer, "give", {}) or {}),
            "get": dict(getattr(offer, "get", {}) or {}),
            "status": getattr(offer, "status", "active"),
            "created_turn": getattr(offer, "created_turn", 0),
            "created_tick": getattr(offer, "created_tick", 0),
        }

    def update_from_game(self, g, you_pid: int):
        self._you_pid = int(you_pid)
        self._player_names = [p.name for p in g.players]
        self.cb_to.blockSignals(True)
        self.cb_to.clear()
        self.cb_to.addItem("Any")
        for idx, p in enumerate(g.players):
            label = f"P{idx + 1}: {p.name}"
            self.cb_to.addItem(label)
        self.cb_to.blockSignals(False)

        self.list_offers.clear()
        self._offer_by_row.clear()
        row = 0
        for raw in g.trade_offers:
            offer = self._offer_dict(raw)
            if offer.get("status") != "active":
                continue
            from_pid = int(offer.get("from_pid", 0))
            to_pid = offer.get("to_pid", None)
            give_txt = self._fmt_payload(offer.get("give", {}))
            get_txt = self._fmt_payload(offer.get("get", {}))
            to_txt = "any" if to_pid is None else f"P{int(to_pid) + 1}"
            text = f"P{from_pid + 1} offers {give_txt} for {get_txt} ({to_txt})"
            self.list_offers.addItem(text)
            self._offer_by_row[row] = offer
            row += 1
        self._refresh_buttons()

    def _refresh_buttons(self):
        offer = self._selected_offer()
        you_pid = self._you_pid
        can_accept = False
        can_decline = False
        can_cancel = False
        if offer and offer.get("status") == "active":
            from_pid = int(offer.get("from_pid", -1))
            to_pid = offer.get("to_pid", None)
            allowed = (to_pid is None or int(to_pid) == int(you_pid))
            if int(you_pid) == from_pid:
                can_cancel = True
            elif allowed:
                can_accept = True
                can_decline = True
        self.btn_accept.setEnabled(can_accept)
        self.btn_decline.setEnabled(can_decline)
        self.btn_cancel.setEnabled(can_cancel)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        config: Optional[GameConfig] = None,
        on_back_to_menu=None,
        online_controller=None,
        online_pid: int = 0,
        dev_dialog_factory: Optional[Callable[..., QtWidgets.QDialog]] = None,
        trade_dialog_factory: Optional[Callable[..., QtWidgets.QDialog]] = None,
    ):
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
        self._dev_dialog_factory = dev_dialog_factory or DevDialog
        self._trade_dialog_factory = trade_dialog_factory or TradeDialog

        self.game = build_board(
            seed=random.randint(1, 999999),
            size=62.0,
            map_id=self._last_config.map_preset,
            map_path=self._last_config.map_path,
        )

        self.selected_action = None  # "settlement"/"road"/"city"/"dev"
        self.overlay_nodes: Dict[int, QtWidgets.QGraphicsItem] = {}
        self.overlay_edges: Dict[Tuple[int,int], QtWidgets.QGraphicsItem] = {}
        self.overlay_hex: Dict[int, QtWidgets.QGraphicsItem] = {}
        self.piece_items: List[QtWidgets.QGraphicsItem] = []
        self._shown_game_over = False
        self._discard_modal_open = False
        self._gold_modal_open = False
        self._bot_seen_offers: Set[int] = set()
        self._move_ship_from: Optional[Tuple[int, int]] = None

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

        self.trade_offers_panel = TradeOffersPanel(
            self._create_trade_offer,
            self._accept_trade_offer,
            self._decline_trade_offer,
            self._cancel_trade_offer,
        )
        right_layout.addWidget(self.trade_offers_panel)

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

        self.btn_save = QtWidgets.QPushButton("Save")
        self.btn_save.setStyleSheet(f"background:{PALETTE['ui_panel_outline']}; padding:10px 14px; border-radius:12px; font-weight:700;")
        self.btn_save.clicked.connect(self._save_game)
        self.btn_load = QtWidgets.QPushButton("Load")
        self.btn_load.setStyleSheet(f"background:{PALETTE['ui_panel_outline']}; padding:10px 14px; border-radius:12px; font-weight:700;")
        self.btn_load.clicked.connect(self._load_game)

        self.btn_menu = QtWidgets.QPushButton("Menu")
        self.btn_menu.setStyleSheet(f"background:{PALETTE['ui_panel_outline']}; padding:10px 14px; border-radius:12px; font-weight:700;")
        self.btn_menu.clicked.connect(self._open_game_menu)
        self._esc_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        self._esc_shortcut.activated.connect(self._open_game_menu)

        top_l.addWidget(self.d1)
        top_l.addWidget(self.d2)
        top_l.addSpacing(8)
        top_l.addWidget(self.btn_end)
        top_l.addWidget(self.btn_save)
        top_l.addWidget(self.btn_load)
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
        self.btn_ship = action_btn("ship", "Ship (wood+sheep)")
        self.btn_move_ship = action_btn("move_ship", "Move Ship (endpoint)")
        self.btn_city = action_btn("city", "City (2 wheat + 3 ore)")
        self.btn_pirate = action_btn("pirate", "Move Pirate")
        self.btn_dev  = action_btn("dev", "Dev card (sheep+wheat+ore)", checkable=False)
        self.btn_trade = action_btn("trade", "Trade with bank", checkable=False)
        self.btn_dev.setObjectName("btn_dev_action")
        self.btn_trade.setObjectName("btn_trade_bank")
        self.btn_dev.clicked.connect(self._open_dev_dialog)
        self.btn_trade.clicked.connect(self._open_trade_dialog)

        bottom_l.addWidget(self.btn_sett)
        bottom_l.addWidget(self.btn_road)
        bottom_l.addWidget(self.btn_ship)
        bottom_l.addWidget(self.btn_move_ship)
        bottom_l.addWidget(self.btn_city)
        bottom_l.addWidget(self.btn_pirate)
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

            # port visuals: ship + ratio badge + resource icon (no text label)
            def _normalize_port(p):
                s = str(p).strip().lower()
                if "3:1" in s or s in ("3", "3:1", "generic", "any"):
                    return "3:1", None
                for r in RESOURCES:
                    if r in s:
                        return "2:1", r
                return "3:1", None

            ratio, res = _normalize_port(ptype)

            ship_pm = _svg_tinted_pixmap("pieces/ship.svg", (34, 18), QtGui.QColor(PALETTE["ui_action_icon"]))
            if ship_pm.isNull():
                ship_pm = make_action_icon("ship", 30)
            ship = QtWidgets.QGraphicsPixmapItem(ship_pm)
            ship.setOffset(-ship_pm.width() / 2, -ship_pm.height() / 2)
            ship.setPos(out)
            ship.setZValue(6)
            ship.setToolTip(f"Port {ratio}" + (f" {res}" if res else ""))
            self.scene.addItem(ship)

            badge_r = 10
            badge_center = QtCore.QPointF(out.x() + 14, out.y() - 14)
            badge = QtWidgets.QGraphicsEllipseItem(
                badge_center.x() - badge_r,
                badge_center.y() - badge_r,
                badge_r * 2,
                badge_r * 2,
            )
            badge.setBrush(QtGui.QColor(PALETTE["ui_panel_tab_active"]))
            badge.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 1.5))
            badge.setZValue(7)
            self.scene.addItem(badge)

            txt = QtWidgets.QGraphicsTextItem(ratio)
            txt.setDefaultTextColor(QtGui.QColor(PALETTE["ui_text_bright"]))
            txt.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Bold))
            br = txt.boundingRect()
            txt.setPos(badge_center.x() - br.width()/2, badge_center.y() - br.height()/2 - 1)
            txt.setZValue(8)
            self.scene.addItem(txt)

            if res:
                icon_pm = resource_icon_pixmap(res, 20)
                icon = QtWidgets.QGraphicsPixmapItem(icon_pm)
                icon.setOffset(-icon_pm.width()/2, -icon_pm.height()/2)
                icon.setPos(QtCore.QPointF(out.x() - 16, out.y() - 14))
                icon.setZValue(7)
                self.scene.addItem(icon)

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
        for (a, b), pid in self.game.occupied_e.items():
            if self._draw_edge_svg("pieces/road.svg", a, b, self.game.players[pid].color, z=11.0, height=12):
                continue
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

        # ships (seafarers)
        for (a, b), pid in getattr(self.game, "occupied_ships", {}).items():
            if self._draw_edge_svg("pieces/ship.svg", a, b, self.game.players[pid].color, z=11.2, height=10):
                continue
            pa = self.game.vertices[a]
            pb = self.game.vertices[b]
            path = QtGui.QPainterPath(pa)
            path.lineTo(pb)
            base = QtWidgets.QGraphicsPathItem(path)
            dark = self.game.players[pid].color.darker(140)
            pen_base = QtGui.QPen(dark, 9)
            pen_base.setCapStyle(QtCore.Qt.RoundCap)
            pen_base.setStyle(QtCore.Qt.DashLine)
            base.setPen(pen_base)
            base.setZValue(10.5)
            self.scene.addItem(base)
            self.piece_items.append(base)

            it = QtWidgets.QGraphicsPathItem(path)
            pen = QtGui.QPen(self.game.players[pid].color.lighter(130), 5)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setStyle(QtCore.Qt.DashLine)
            it.setPen(pen)
            it.setZValue(11.2)
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
        self._draw_pirate()

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

        if self.selected_action == "pirate" and self._can_control_local_turn():
            for ti, t in enumerate(self.game.tiles):
                if t.terrain != "sea":
                    continue
                if self.game.pirate_tile is not None and ti == int(self.game.pirate_tile):
                    continue
                poly = QtGui.QPolygonF(hex_corners(t.center, self.game.size))
                def on_click(_ti=ti):
                    self._on_pirate_hex_clicked(_ti)
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
        size = int(self.game.size * 0.5)
        col = QtGui.QColor(PALETTE["robber_fill_rgba"])
        pm = _svg_tinted_pixmap("pieces/robber.svg", (size, size), col)
        if not pm.isNull():
            it = QtWidgets.QGraphicsPixmapItem(pm)
            it.setOffset(-pm.width() / 2, -pm.height() / 2)
            it.setPos(c)
            it.setZValue(8)
            self.scene.addItem(it)
            self.piece_items.append(it)
            return
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

    def _draw_pirate(self):
        if self.game.pirate_tile is None:
            return
        ti = int(self.game.pirate_tile)
        if ti < 0 or ti >= len(self.game.tiles):
            return
        t = self.game.tiles[ti]
        c = t.center
        r = self.game.size * 0.14
        pir = QtWidgets.QGraphicsEllipseItem(c.x()-r, c.y()-r, r*2, r*2)
        pir.setBrush(QtGui.QColor(PALETTE["ui_panel_outline"]))
        pir.setPen(QtGui.QPen(QtGui.QColor(PALETTE["ui_outline_light"]), 2))
        pir.setZValue(8)
        self.scene.addItem(pir)
        self.piece_items.append(pir)

        txt = QtWidgets.QGraphicsTextItem("P")
        txt.setDefaultTextColor(QtGui.QColor(PALETTE["ui_text_bright"]))
        txt.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold))
        b = txt.boundingRect()
        txt.setPos(c.x()-b.width()/2, c.y()-b.height()/2-1)
        txt.setZValue(9)
        self.scene.addItem(txt)
        self.piece_items.append(txt)

    def _draw_svg_piece(
        self,
        rel: str,
        pos: QtCore.QPointF,
        col: QtGui.QColor,
        size: Tuple[int, int],
        z: float,
        angle: Optional[float] = None,
        shadow: bool = True,
    ) -> bool:
        pm = _svg_tinted_pixmap(rel, size, col)
        if pm.isNull():
            return False
        w, h = pm.width(), pm.height()
        if shadow:
            sh_col = QtGui.QColor(col.darker(180))
            sh_col.setAlpha(160)
            sh_pm = _svg_tinted_pixmap(rel, (w, h), sh_col)
            if not sh_pm.isNull():
                sh = QtWidgets.QGraphicsPixmapItem(sh_pm)
                sh.setOffset(-w / 2, -h / 2)
                sh.setPos(pos + QtCore.QPointF(2, 2))
                if angle is not None:
                    sh.setTransformOriginPoint(w / 2, h / 2)
                    sh.setRotation(angle)
                sh.setZValue(z - 0.2)
                self.scene.addItem(sh)
                self.piece_items.append(sh)

        it = QtWidgets.QGraphicsPixmapItem(pm)
        it.setOffset(-w / 2, -h / 2)
        it.setPos(pos)
        if angle is not None:
            it.setTransformOriginPoint(w / 2, h / 2)
            it.setRotation(angle)
        it.setZValue(z)
        self.scene.addItem(it)
        self.piece_items.append(it)
        return True

    def _draw_edge_svg(
        self,
        rel: str,
        a: int,
        b: int,
        col: QtGui.QColor,
        z: float,
        height: int,
    ) -> bool:
        pa = self.game.vertices[a]
        pb = self.game.vertices[b]
        dx = pb.x() - pa.x()
        dy = pb.y() - pa.y()
        dist = math.hypot(dx, dy)
        length = max(8.0, dist - 8.0)
        angle = math.degrees(math.atan2(dy, dx))
        mid = QtCore.QPointF((pa.x() + pb.x()) / 2.0, (pa.y() + pb.y()) / 2.0)
        return self._draw_svg_piece(rel, mid, col, (int(length), int(height)), z, angle=angle, shadow=True)

    def _draw_house(self, p: QtCore.QPointF, col: QtGui.QColor, z: float):
        if self._draw_svg_piece("pieces/settlement.svg", p, col, (28, 28), z=z, shadow=True):
            return
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
        if self._draw_svg_piece("pieces/city.svg", p, col, (32, 32), z=z, shadow=True):
            return
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

    def _apply_cmd(self, cmd: Dict[str, Any], pid: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        try:
            _, events = engine_rules.apply_cmd(self.game, int(pid if pid is not None else self.game.turn), cmd)
            return events
        except engine_rules.RuleError as exc:
            msg = exc.message
            if exc.details:
                msg = f"{msg} ({exc.details})"
            self._log(f"[!] {msg}")
            return None

    def _test_force_roll(self, roll: int, discards: Optional[Dict[int, Dict[str, int]]] = None) -> None:
        if os.getenv("CATAN_TEST_MODE") is None:
            return
        g = self.game
        if g.game_over or g.pending_action is not None:
            return
        a = b = 1
        for aa in range(1, 7):
            bb = int(roll) - aa
            if 1 <= bb <= 6:
                a, b = aa, bb
                break
        self.d1.setIcon(QtGui.QIcon(dice_face(a)))
        self.d2.setIcon(QtGui.QIcon(dice_face(b)))
        cmd = {"type": "roll", "roll": int(roll)}
        if discards is not None:
            cmd["discards"] = discards
        if self._apply_cmd(cmd, pid=g.turn) is None:
            return
        self._refresh_all_dynamic()
        self._sync_ui()

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
        self.resources_panel.update_from_game(g, self.you_pid if self.online_mode else 0)
        self.trade_offers_panel.update_from_game(g, self.you_pid if self.online_mode else 0)

        # hint text
        if g.game_over:
            self.lbl_hint.setText("Game over.")
        elif g.pending_action == "discard":
            pid = self.you_pid if self.online_mode else 0
            need = int(g.discard_required.get(pid, 0))
            if need > 0:
                self.lbl_hint.setText(f"Discard {need} cards.")
            else:
                self.lbl_hint.setText("Waiting for other players to discard.")
        elif g.pending_action == "choose_gold":
            pid = self.you_pid if self.online_mode else 0
            need = int(g.pending_gold.get(pid, 0))
            if need > 0:
                self.lbl_hint.setText(f"Choose {need} gold resource(s).")
            else:
                self.lbl_hint.setText("Waiting for other players to choose gold.")
        elif g.pending_action == "robber_move":
            self.lbl_hint.setText("Robber: click a hex to move it.")
        elif g.phase == "setup":
            self.lbl_hint.setText("Setup: place settlement then road. Spots show only for selected action.")
        else:
            self.lbl_hint.setText("Main: click dice to roll. Build by selecting card then clicking highlighted spots.")

        for b in (self.btn_sett, self.btn_road, self.btn_ship, self.btn_move_ship, self.btn_city, self.btn_pirate, self.btn_dev, self.btn_trade, self.btn_end, self.d1, self.d2):
            b.setEnabled(not g.game_over)
        if g.phase == "main" and not g.rolled and not g.game_over:
            for b in (self.btn_sett, self.btn_road, self.btn_ship, self.btn_move_ship, self.btn_city, self.btn_pirate, self.btn_trade, self.btn_end):
                b.setEnabled(False)
        can_roll = (
            not g.game_over
            and g.phase == "main"
            and not g.rolled
            and g.pending_action is None
            and ((self.online_mode and g.turn == self.you_pid) or (not self.online_mode and g.turn == 0))
        )
        self.d1.setEnabled(bool(can_roll))
        self.d2.setEnabled(bool(can_roll))
        if hasattr(self, "btn_save"):
            self.btn_save.setEnabled(not self.online_mode and not g.game_over)
        if hasattr(self, "btn_load"):
            self.btn_load.setEnabled(not self.online_mode)
        enable_sea = bool(_rules_value(g.rules_config, "enable_seafarers", False))
        enable_move = bool(_rules_value(g.rules_config, "enable_move_ship", False))
        enable_pirate = bool(_rules_value(g.rules_config, "enable_pirate", False))
        self.btn_ship.setVisible(enable_sea)
        self.btn_move_ship.setVisible(enable_sea and enable_move)
        self.btn_pirate.setVisible(enable_pirate)
        if (not enable_sea and self.selected_action in ("ship", "move_ship")) or (not enable_pirate and self.selected_action == "pirate"):
            self.selected_action = "road"
            self.btn_road.setChecked(True)
        if self.online_mode:
            self.btn_dev.setEnabled(False)
            self.btn_trade.setEnabled(False)
        can_create_offer = (
            not g.game_over
            and g.phase == "main"
            and g.pending_action is None
            and ((self.online_mode and g.turn == self.you_pid) or (not self.online_mode and g.turn == 0))
        )
        self.trade_offers_panel.btn_create.setEnabled(bool(can_create_offer))

        if g.pending_action == "discard":
            pid = self.you_pid if self.online_mode else 0
            if self._needs_discard(pid):
                self._prompt_discard(pid)
        if g.pending_action == "choose_gold":
            pid = self.you_pid if self.online_mode else 0
            if self._needs_gold(pid):
                self._prompt_gold_choice(pid)
            if not self.online_mode and self._needs_gold(1):
                choice = self._bot_choose_gold(1)
                if choice:
                    res, qty = choice
                    if self._submit_gold_choice(1, res, qty):
                        self._log(f"[GOLD] Bot chose {qty} {res}.")
        if not self.online_mode and self.bot_enabled:
            self._handle_trade_offers_bot()

    def _restart_game(self):
        self.game = build_board(
            seed=random.randint(1, 999999),
            size=62.0,
            map_id=self._last_config.map_preset,
            map_path=self._last_config.map_path,
        )
        self._shown_game_over = False
        self._bot_seen_offers.clear()
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

    def _save_game(self):
        if self.online_mode:
            self._log("[!] Save disabled in online mode.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Game",
            "catan_save.json",
            "Catan Save (*.json);;All Files (*)",
        )
        if not path:
            return
        data = _ui_game_to_engine_dict(self.game)
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            self._log(f"[!] Save failed: {exc}")
            return
        self._log(f"[SYS] Game saved: {path}")

    def _load_game(self):
        if self.online_mode:
            self._log("[!] Load disabled in online mode.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Game",
            "",
            "Catan Save (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            self._log(f"[!] Load failed: {exc}")
            return
        hidden = data.get("_offline_hidden", {}) if isinstance(data, dict) else {}
        try:
            base = engine_serialize.from_dict(data)
            g = _convert_base_state(base)
        except Exception as exc:
            self._log(f"[!] Load failed: {exc}")
            return
        # restore hidden offline-only state
        if isinstance(hidden, dict):
            g.dev_deck = list(hidden.get("dev_deck", g.dev_deck))
            g.dev_played_turn = dict(hidden.get("dev_played_turn", g.dev_played_turn))
            g.free_roads = dict(hidden.get("free_roads", g.free_roads))
            g.roll_history = list(hidden.get("roll_history", g.roll_history))
            p_cards = hidden.get("player_dev_cards", [])
            if isinstance(p_cards, list):
                for idx, cards in enumerate(p_cards):
                    if idx < len(g.players) and isinstance(cards, list):
                        g.players[idx].dev_cards = list(cards)
        self.game = g
        self._shown_game_over = False
        self.selected_action = None
        self._move_ship_from = None
        self._gold_modal_open = False
        self._draw_static_board()
        self._refresh_all_dynamic()
        self._fit_map()
        self._sync_ui()
        self._log(f"[SYS] Game loaded: {path}")

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
        dlg = self._dev_dialog_factory(self, g, 0)
        if hasattr(dlg, "open_nonmodal") and callable(getattr(dlg, "open_nonmodal")):
            dlg.open_nonmodal()
        else:
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
        dlg = self._trade_dialog_factory(self, g, 0)
        if hasattr(dlg, "open_nonmodal") and callable(getattr(dlg, "open_nonmodal")):
            dlg.open_nonmodal()
        else:
            if dlg.exec() == QtWidgets.QDialog.Accepted and dlg._applied:
                give, get, qty, rate = dlg._applied
                self._log(f"[TRADE] {rate}:1 gave {give} -> got {get} x{qty}")
        self._refresh_all_dynamic()
        self._sync_ui()

    def _create_trade_offer(self, give: Dict[str, int], get: Dict[str, int], to_pid: Optional[int]) -> None:
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        cmd = {"type": "trade_offer_create", "give": dict(give), "get": dict(get), "to_pid": to_pid}
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_trade_offer_create(give, get, to_pid)
        else:
            events = self._apply_cmd(cmd, pid=0)
            if events is None:
                return
            self._log("[TRADE] Offer created.")
        self._sync_ui()

    def _accept_trade_offer(self, offer_id: int) -> None:
        cmd = {"type": "trade_offer_accept", "offer_id": int(offer_id)}
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_trade_offer_accept(offer_id)
        else:
            events = self._apply_cmd(cmd, pid=0)
            if events is None:
                return
            self._log("[TRADE] Offer accepted.")
        self._sync_ui()

    def _decline_trade_offer(self, offer_id: int) -> None:
        cmd = {"type": "trade_offer_decline", "offer_id": int(offer_id)}
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_trade_offer_decline(offer_id)
        else:
            events = self._apply_cmd(cmd, pid=0)
            if events is None:
                return
            self._log("[TRADE] Offer declined.")
        self._sync_ui()

    def _cancel_trade_offer(self, offer_id: int) -> None:
        cmd = {"type": "trade_offer_cancel", "offer_id": int(offer_id)}
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_trade_offer_cancel(offer_id)
        else:
            events = self._apply_cmd(cmd, pid=0)
            if events is None:
                return
            self._log("[TRADE] Offer canceled.")
        self._sync_ui()

    def hand_size(self, pid: int) -> int:
        return sum(self.game.players[pid].res.values())

    def discard_needed(self, pid: int) -> int:
        total = self.hand_size(pid)
        return total // 2 if total > 7 else 0

    def _needs_discard(self, pid: int) -> bool:
        g = self.game
        return g.pending_action == "discard" and pid in g.discard_required and pid not in g.discard_submitted

    def _needs_gold(self, pid: int) -> bool:
        g = self.game
        return g.pending_action == "choose_gold" and int(g.pending_gold.get(pid, 0)) > 0 and (g.pending_pid is None or g.pending_pid == pid)

    def _submit_gold_choice(self, pid: int, res: str, qty: int) -> bool:
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_choose_gold(res, qty)
            return True
        return self._apply_cmd({"type": "choose_gold", "res": res, "qty": int(qty)}, pid=pid) is not None

    def _submit_discard(self, pid: int, discards: Dict[str, int]) -> bool:
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_discard(discards)
            return True
        return self._apply_cmd({"type": "discard", "discards": discards}, pid=pid) is not None

    def _prompt_discard(self, pid: int) -> None:
        g = self.game
        if self._discard_modal_open:
            return
        need = int(g.discard_required.get(pid, 0))
        if need <= 0:
            return
        self._discard_modal_open = True
        dlg = DiscardDialog(self, g.players[pid].res, need)
        ok = dlg.exec() == QtWidgets.QDialog.Accepted
        self._discard_modal_open = False
        if not ok:
            self._log("[7] Discard canceled.")
            return
        discards = dlg.selected()
        if self._submit_discard(pid, discards):
            self._log(f"[7] P{pid + 1} discarded {need}.")

    def _prompt_gold_choice(self, pid: int) -> None:
        g = self.game
        if self._gold_modal_open:
            return
        need = int(g.pending_gold.get(pid, 0))
        if need <= 0:
            return
        self._gold_modal_open = True
        dlg = GoldChoiceDialog(self, need)
        ok = dlg.exec() == QtWidgets.QDialog.Accepted
        self._gold_modal_open = False
        if not ok:
            self._log("[GOLD] Choice canceled.")
            return
        res, qty = dlg.selected()
        if self._submit_gold_choice(pid, res, qty):
            self._log(f"[GOLD] P{pid + 1} chose {qty} {res}.")

    def _bot_choose_gold(self, pid: int) -> Optional[Tuple[str, int]]:
        g = self.game
        need = int(g.pending_gold.get(pid, 0))
        if need <= 0:
            return None
        # pick resource with largest bank to reduce failure
        res = max(RESOURCES, key=lambda r: int(g.bank.get(r, 0)))
        qty = min(need, int(g.bank.get(res, 0)))
        if qty <= 0:
            return None
        return res, qty

    def _handle_discard_flow(self) -> None:
        g = self.game
        if g.pending_action != "discard":
            return
        pid = self.you_pid if self.online_mode else 0
        if self._needs_discard(pid):
            self._prompt_discard(pid)
        if not self.online_mode and self._needs_discard(1):
            need = int(g.discard_required.get(1, 0))
            discards = self._bot_discard_plan(1, need)
            if self._submit_discard(1, discards):
                self._log(f"[7] Bot discarded {need}.")
        if g.pending_action == "robber_move":
            self._log("[7] Move the robber.")
            self._refresh_all_dynamic()
            self._sync_ui()

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
        victims = self._victims_for_tile(ti, g.pending_pid or 0)
        target_pid = None
        if victims:
            self._log("[ROB] Choose a victim to steal from.")
            names = [g.players[v].name for v in victims]
            choice, ok = QtWidgets.QInputDialog.getItem(self, "Robber", "Choose player to steal from:", names, 0, False)
            if ok:
                for v in victims:
                    if g.players[v].name == choice:
                        target_pid = v
                        break
            if target_pid is None:
                target_pid = victims[0]
        events = self._apply_cmd({"type": "move_robber", "tile": ti, "victim": target_pid}, pid=g.pending_pid or 0)
        if events is None:
            return
        for ev in events:
            if ev.get("type") == "move_robber" and ev.get("stolen"):
                self._log(f"[ROB] Stole 1 {ev.get('stolen')} from P{target_pid + 1}.")
        if not victims:
            self._log("[ROB] Robber moved. No victims.")
        self._refresh_all_dynamic()
        self._sync_ui()

    def _on_pirate_hex_clicked(self, ti: int):
        g = self.game
        if g.game_over:
            self._log(f"Game over. Winner: P{g.winner_pid}")
            return
        if not self._can_control_local_turn():
            return
        if g.tiles[ti].terrain != "sea":
            return
        if g.pirate_tile is not None and ti == int(g.pirate_tile):
            self._log("[PIRATE] Pick a different sea tile.")
            return
        if self.online_mode and self.online_controller:
            self.online_controller.cmd_move_pirate(ti)
            return
        if self._apply_cmd({"type": "move_pirate", "tile": ti}, pid=g.turn) is None:
            return
        self._log("[PIRATE] Pirate moved.")
        self._refresh_all_dynamic()
        self._sync_ui()

    def _start_free_roads(self, pid: int):
        if pid == 0:
            self._log("[DEV] Road Building: place 2 free roads.")
            self.select_action("road")

    def _bot_log(self, msg: str):
        if BOT_LOG:
            self._log(msg)

    def _bot_discard_plan(self, pid: int, need: int) -> Dict[str, int]:
        pres = self.game.players[pid].res
        plan = {r: 0 for r in RESOURCES}
        remaining = int(need)
        while remaining > 0:
            max_q = max(pres.values()) if pres else 0
            if max_q <= 0:
                break
            choices = sorted([r for r, q in pres.items() if q == max_q and q > 0])
            r = choices[0]
            plan[r] += 1
            pres[r] -= 1
            remaining -= 1
        # restore player res (plan is applied by engine)
        for r, q in plan.items():
            pres[r] += q
        return plan

    def _handle_trade_offers_bot(self) -> None:
        g = self.game
        for raw in g.trade_offers:
            offer = raw if isinstance(raw, dict) else {
                "offer_id": getattr(raw, "offer_id", -1),
                "from_pid": getattr(raw, "from_pid", -1),
                "to_pid": getattr(raw, "to_pid", None),
                "give": dict(getattr(raw, "give", {}) or {}),
                "get": dict(getattr(raw, "get", {}) or {}),
                "status": getattr(raw, "status", "active"),
            }
            if offer.get("status") != "active":
                continue
            offer_id = int(offer.get("offer_id", -1))
            if offer_id in self._bot_seen_offers:
                continue
            from_pid = int(offer.get("from_pid", -1))
            if from_pid == 1:
                continue
            to_pid = offer.get("to_pid", None)
            if to_pid is not None and int(to_pid) != 1:
                continue
            give = offer.get("give", {})
            get = offer.get("get", {})
            bot_res = g.players[1].res
            can_pay = all(bot_res.get(r, 0) >= int(q) for r, q in get.items())
            total_get = sum(int(q) for q in give.values())
            total_give = sum(int(q) for q in get.values())
            if can_pay and total_get >= total_give:
                if self._apply_cmd({"type": "trade_offer_accept", "offer_id": offer_id}, pid=1) is not None:
                    self._log("[TRADE] Bot accepted offer.")
            else:
                if self._apply_cmd({"type": "trade_offer_decline", "offer_id": offer_id}, pid=1) is not None:
                    self._log("[TRADE] Bot declined offer.")
            self._bot_seen_offers.add(offer_id)

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
        victims = self._victims_for_tile(target_hex, pid)
        target_pid = self._bot_choose_victim(victims) if victims else None
        events = self._apply_cmd({"type": "move_robber", "tile": target_hex, "victim": target_pid}, pid=pid)
        if events is None:
            return
        if not victims:
            self._log("[ROB] Bot moved robber. No victims.")

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
        events = self._apply_cmd({"type": "place_road", "eid": e, "free": bool(use_free)}, pid=1)
        if events is None:
            return False
        self._log("Bot built a road.")
        return True

    def _bot_build_city_at(self, vid: int) -> bool:
        if self._apply_cmd({"type": "upgrade_city", "vid": vid}, pid=1) is None:
            return False
        self._log("Bot upgraded to a city.")
        return True

    def _bot_build_settlement_at(self, vid: int) -> bool:
        if self._apply_cmd({"type": "place_settlement", "vid": vid, "setup": False}, pid=1) is None:
            return False
        self._log("Bot built a settlement.")
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
        events = self._apply_cmd({"type": "buy_dev"}, pid=1)
        if events is None:
            return False
        card = None
        for ev in events:
            if ev.get("type") == "buy_dev":
                card = ev.get("card")
                break
        self._log(f"Bot bought dev: {card}.")
        return True

    def _bot_plan_trade(self, pid: int) -> Optional[Tuple[str, str]]:
        g = self.game
        pres = g.players[pid].res
        target_costs = [COST["city"], COST["settlement"], COST["road"], COST["dev"]]
        best_cost = None
        best_need = None
        best_total = 999
        for cost in target_costs:
            need = {r: max(0, cost[r] - pres.get(r, 0)) for r in cost}
            total = sum(need.values())
            if total < best_total:
                best_total = total
                best_need = need
                best_cost = cost
        if not best_need or best_total <= 0 or not best_cost:
            return None
        need_res = sorted(best_need.keys(), key=lambda r: best_need[r], reverse=True)
        give_order = sorted(RESOURCES, key=lambda r: pres.get(r, 0) - best_cost.get(r, 0), reverse=True)
        for get_res in need_res:
            if best_need.get(get_res, 0) <= 0:
                continue
            for give in give_order:
                if give == get_res:
                    continue
                rate = g.best_trade_rate(pid, give)
                if pres.get(give, 0) >= rate and g.bank.get(get_res, 0) > 0:
                    return give, get_res
        return None

    def _bot_trade_bank(self, give: str, get: str) -> bool:
        events = self._apply_cmd({"type": "trade_bank", "give": give, "get": get, "get_qty": 1}, pid=1)
        if events is None:
            return False
        self._log(f"Bot traded {give} for {get}.")
        return True

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
        trade = self._bot_plan_trade(pid)
        if trade:
            actions.append(("trade", trade))
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
        if self._apply_cmd({"type": "play_dev", "card": "knight"}, pid=1) is None:
            return False
        if g.pending_action == "robber_move":
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
        if self._apply_cmd({"type": "play_dev", "card": "road_building"}, pid=1) is None:
            return False
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
        if self._apply_cmd({"type": "play_dev", "card": "year_of_plenty", "a": a, "qa": qa, "b": b, "qb": qb}, pid=1) is None:
            return False
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
        if self._apply_cmd({"type": "play_dev", "card": "monopoly", "r": r}, pid=1) is None:
            return False
        self._bot_log(f"Bot played monopoly on {r}.")
        return True

    def select_action(self, key: str):
        if self.game.game_over:
            self._log(f"Game over. Winner: P{self.game.winner_pid}")
            return
        if key in ("ship", "move_ship") and not bool(_rules_value(self.game.rules_config, "enable_seafarers", False)):
            return
        if key == "move_ship" and not bool(_rules_value(self.game.rules_config, "enable_move_ship", False)):
            return
        if key == "pirate" and not bool(_rules_value(self.game.rules_config, "enable_pirate", False)):
            return
        self.selected_action = key
        if key != "move_ship":
            self._move_ship_from = None
        # make checkable group
        for b in (self.btn_sett, self.btn_road, self.btn_ship, self.btn_move_ship, self.btn_city, self.btn_pirate):
            b.setChecked(False)
        {"settlement":self.btn_sett,"road":self.btn_road,"ship":self.btn_ship,"move_ship":self.btn_move_ship,"city":self.btn_city,"pirate":self.btn_pirate}[key].setChecked(True)
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
        if g.pending_action == "discard":
            self._handle_discard_flow()
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
        roll = a + b
        self.d1.setIcon(QtGui.QIcon(dice_face(a)))
        self.d2.setIcon(QtGui.QIcon(dice_face(b)))
        self._log(f"You rolled {roll}.")
        if roll == 7:
            if self._apply_cmd({"type": "roll", "roll": roll}, pid=0) is None:
                return
            self._refresh_all_dynamic()
            self._sync_ui()
            self._handle_discard_flow()
            return
        if self._apply_cmd({"type": "roll", "roll": roll}, pid=0) is None:
            return
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
        if self._apply_cmd({"type": "end_turn"}, pid=g.turn) is None:
            return
        if g.turn == 1:
            if self.bot_enabled:
                self._bot_turn()
            else:
                self._log("Bot disabled. Skipping bot turn.")
                self._apply_cmd({"type": "end_turn"}, pid=1)
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
            roll = a + b
            self._log(f"Bot rolled {roll}.")
            if self._apply_cmd({"type": "roll", "roll": roll}, pid=1) is None:
                return
            if roll == 7:
                self._handle_discard_flow()
                if g.pending_action == "robber_move" and g.pending_pid == 1:
                    target = self._bot_choose_robber_tile()
                    self._bot_move_robber(1, target)

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
            elif name == "trade":
                give, get = arg
                ok = self._bot_trade_bank(give, get)
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
        if self._apply_cmd({"type": "end_turn"}, pid=1) is None:
            return
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
        elif self.selected_action == "ship":
            for e in g.edges:
                if can_place_ship(g, 0, e):
                    self._add_edge_spot(e, forced_pid=0)
        elif self.selected_action == "move_ship":
            if self._move_ship_from is None:
                for e, owner in g.occupied_ships.items():
                    if owner != 0:
                        continue
                    if self._is_endpoint_ship_ui(0, e):
                        self._add_edge_spot(e, forced_pid=0)
            else:
                fa, fb = self._move_ship_from
                for e in g.edges:
                    if e in g.occupied_ships or e in g.occupied_e:
                        continue
                    if not self._edge_has_sea_ui(e):
                        continue
                    if self._edge_blocked_by_pirate_ui(e):
                        continue
                    if not (fa in e or fb in e):
                        continue
                    self._add_edge_spot(e, forced_pid=0)
        elif self.selected_action == "city":
            for vid in g.vertices.keys():
                if can_upgrade_city(g, 0, vid):
                    self._add_node_spot(vid, forced_pid=0)
        elif self.selected_action == "dev":
            # dev is click in UI later; keep no board overlays now
            pass

    def _can_control_local_turn(self) -> bool:
        g = self.game
        if g.game_over:
            return False
        if g.pending_action is not None:
            return False
        if self.online_mode:
            return g.phase == "main" and g.turn == self.you_pid
        return g.phase == "main" and g.turn == 0

    def _edge_has_sea_ui(self, e: Tuple[int, int]) -> bool:
        ek = (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
        for ti in self.game.edge_adj_hexes.get(ek, []):
            if self.game.tiles[ti].terrain == "sea":
                return True
        return False

    def _edge_is_sea_only_ui(self, e: Tuple[int, int]) -> bool:
        ek = (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
        adj = self.game.edge_adj_hexes.get(ek, [])
        if not adj:
            return False
        return all(self.game.tiles[ti].terrain == "sea" for ti in adj)

    def _edge_blocked_by_pirate_ui(self, e: Tuple[int, int]) -> bool:
        if self.game.pirate_tile is None:
            return False
        ek = (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
        return int(self.game.pirate_tile) in self.game.edge_adj_hexes.get(ek, [])

    def _route_degree_ui(self, pid: int, vid: int) -> int:
        deg = 0
        for e, owner in self.game.occupied_e.items():
            if owner == pid and vid in e:
                deg += 1
        for e, owner in self.game.occupied_ships.items():
            if owner == pid and vid in e:
                deg += 1
        return deg

    def _is_endpoint_ship_ui(self, pid: int, e: Tuple[int, int]) -> bool:
        a, b = e
        for v in (a, b):
            occ = self.game.occupied_v.get(v)
            if occ and occ[0] == pid:
                continue
            if self._route_degree_ui(pid, v) <= 1:
                return True
        return False

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
            if self._apply_cmd({"type": "place_settlement", "vid": vid, "setup": True}, pid=pid) is None:
                return
            self._log(f"{g.players[pid].name} placed a settlement.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return

        # main phase:
        if pid != 0:
            return
        if self.selected_action == "settlement":
            if self._apply_cmd({"type": "place_settlement", "vid": vid, "setup": False}, pid=0) is None:
                return
            self._log("You built a settlement.")
        elif self.selected_action == "city":
            if self._apply_cmd({"type": "upgrade_city", "vid": vid}, pid=0) is None:
                return
            self._log("You upgraded to a city.")
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
            elif self.selected_action == "ship":
                self.online_controller.cmd_build_ship(e)
            elif self.selected_action == "move_ship":
                if self._move_ship_from is None:
                    self._move_ship_from = e
                    self._refresh_all_dynamic()
                    return
                self.online_controller.cmd_move_ship(self._move_ship_from, e)
                self._move_ship_from = None
            return
        if g.phase == "setup":
            if g.setup_need != "road":
                return
            if self._apply_cmd({"type": "place_road", "eid": e, "setup": True}, pid=pid) is None:
                return
            self._log(f"{g.players[pid].name} placed a road.")
            if g.phase == "main":
                self._log("[SYS] Setup finished. Now roll dice to start.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return

        # main phase
        if pid != 0:
            return
        if self.selected_action == "move_ship":
            if self._move_ship_from is None:
                self._move_ship_from = e
                self._refresh_all_dynamic()
                return
            cmd = {"type": "move_ship", "from_eid": self._move_ship_from, "to_eid": e}
            self._move_ship_from = None
            if self._apply_cmd(cmd, pid=0) is None:
                return
            self._log("You moved a ship.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return
        if self.selected_action != "road":
            if self.selected_action != "ship":
                return
        if self.selected_action == "ship":
            if self._apply_cmd({"type": "build_ship", "eid": e}, pid=0) is None:
                return
            self._log("You built a ship.")
            self._refresh_all_dynamic()
            self._sync_ui()
            return
        free_left = int(g.free_roads.get(0, 0))
        cmd = {"type": "place_road", "eid": e, "free": free_left > 0}
        if self._apply_cmd(cmd, pid=0) is None:
            return
        if free_left > 0:
            self._log("[DEV] Free road placed.")
        self._log("You built a road.")
        self._refresh_all_dynamic()
        self._sync_ui()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
