import sys, math, random, time
from dataclasses import dataclass, field
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

# =========================================================
# Sprint 3 (UI v5): bank separated, setup snake 2x, ports, pseudo-3D pieces
# =========================================================

RES = ["wood", "brick", "sheep", "wheat", "ore"]

TERRAIN = ["forest","hills","pasture","fields","mountains","desert"]
TERRAIN_TO_RES = {
    "forest": "wood",
    "hills": "brick",
    "pasture": "sheep",
    "fields": "wheat",
    "mountains": "ore",
    "desert": None,
}

# base game terrain distribution (19)
TERRAIN_POOL = (
    ["forest"]*4 +
    ["hills"]*3 +
    ["pasture"]*4 +
    ["fields"]*4 +
    ["mountains"]*3 +
    ["desert"]*1
)

TOKENS_POOL = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]  # 18 tokens (no desert)

COST = {
    "road": {"wood":1, "brick":1},
    "settlement": {"wood":1, "brick":1, "sheep":1, "wheat":1},
    "city": {"wheat":2, "ore":3},
    "dev": {"sheep":1, "wheat":1, "ore":1},
}

# Colors (Colonist-ish dark ocean)
BG = "#0a2230"
PANEL = "#0d2b3a"
PANEL2 = "#0b2633"
TXT = "#e7f2f7"
MUTED = "#9ab6c3"
ACCENT = "#25c2a0"

TERRAIN_COL = {
    "forest":   ("#20c16a", "#169756"),
    "hills":    ("#f08a1c", "#c86e12"),
    "pasture":  ("#9ae65a", "#78c940"),
    "fields":   ("#ffd11a", "#d8af10"),
    "mountains":("#aab4c4", "#8993a4"),
    "desert":   ("#d6c79c", "#bdae7e"),
}

# ---------------------------------------------------------
# Geometry: radius-2 hex board (axial coords)
# ---------------------------------------------------------

def axial_coords_radius2():
    coords = []
    R = 2
    for q in range(-R, R+1):
        for r in range(-R, R+1):
            s = -q - r
            if abs(s) <= R and abs(q) <= R and abs(r) <= R:
                coords.append((q,r))
    return coords  # 19

def hex_center(q, r, size):
    # pointy-top axial -> pixel
    x = size * (3/2 * q)
    y = size * (math.sqrt(3) * (r + q/2))
    return (x,y)

def hex_corners(cx, cy, size):
    # pointy-top, angle offset -30deg
    pts = []
    for i in range(6):
        ang = math.radians(60*i - 30)
        pts.append((cx + size*math.cos(ang), cy + size*math.sin(ang)))
    return pts

def key_pt(x,y):
    return (round(x,3), round(y,3))

# ---------------------------------------------------------
# Board / ports
# ---------------------------------------------------------

@dataclass
class HexTile:
    hid: int
    q: int
    r: int
    terrain: str
    token: Optional[int]
    cx: float
    cy: float
    nodes: list[int]  # 6 node ids

@dataclass
class Port:
    pid: int
    edge: tuple[int,int]   # (nodeA,nodeB)
    kind: str              # "3:1" or a resource name for 2:1
    ratio: int             # 3 or 2
    pos: tuple[float,float]

@dataclass
class Board:
    size: float
    tiles: list[HexTile]
    nodes_pos: dict[int, tuple[float,float]]
    edges: dict[tuple[int,int], tuple[int,int]]  # edge_id -> (a,b) same key but stable
    node_neighbors: dict[int, set[int]]
    node_to_tiles: dict[int, list[int]]          # node -> list of tile indices
    edge_to_tiles_count: dict[tuple[int,int], int]
    ports: list[Port]
    center: tuple[float,float]

def build_board(seed: int, size: float = 62.0) -> Board:
    rnd = random.Random(seed)
    coords = axial_coords_radius2()
    rnd.shuffle(coords)

    terrains = TERRAIN_POOL[:]
    rnd.shuffle(terrains)

    tokens = TOKENS_POOL[:]
    rnd.shuffle(tokens)

    nodes_map = {}
    nodes_pos = {}
    node_id_seq = 0

    tiles = []
    all_edges_count = {}

    # First pass: create tiles + nodes
    for hid, (q,r) in enumerate(coords):
        cx, cy = hex_center(q,r,size)
        terr = terrains[hid]
        tok = None
        if terr != "desert":
            tok = tokens.pop()
        corners = hex_corners(cx, cy, size*0.98)

        node_ids = []
        for (x,y) in corners:
            k = key_pt(x,y)
            if k not in nodes_map:
                nodes_map[k] = node_id_seq
                nodes_pos[node_id_seq] = (x,y)
                node_id_seq += 1
            node_ids.append(nodes_map[k])

        t = HexTile(hid=hid, q=q, r=r, terrain=terr, token=tok, cx=cx, cy=cy, nodes=node_ids)
        tiles.append(t)

        # count edges
        for i in range(6):
            a = node_ids[i]
            b = node_ids[(i+1)%6]
            eid = (a,b) if a < b else (b,a)
            all_edges_count[eid] = all_edges_count.get(eid, 0) + 1

    # Build edges dict + node neighbors + node->tiles
    edges = {}
    node_neighbors = {nid:set() for nid in nodes_pos.keys()}
    node_to_tiles = {nid:[] for nid in nodes_pos.keys()}

    for t in tiles:
        for nid in t.nodes:
            node_to_tiles[nid].append(t.hid)
        for i in range(6):
            a = t.nodes[i]
            b = t.nodes[(i+1)%6]
            eid = (a,b) if a < b else (b,a)
            edges[eid] = eid
            node_neighbors[a].add(b)
            node_neighbors[b].add(a)

    # Board center
    cx_all = sum(t.cx for t in tiles)/len(tiles)
    cy_all = sum(t.cy for t in tiles)/len(tiles)
    center = (cx_all, cy_all)

    # Ports: pick 9 coastal edges (edges that belong to only 1 tile)
    coastal = [eid for eid,cnt in all_edges_count.items() if cnt == 1]

    # sort around circle by angle
    def edge_angle(eid):
        (ax,ay) = nodes_pos[eid[0]]
        (bx,by) = nodes_pos[eid[1]]
        mx,my = (ax+bx)/2, (ay+by)/2
        ang = math.atan2(my-center[1], mx-center[0])
        return ang

    coastal.sort(key=edge_angle)

    # pick 9 evenly spaced
    picks = []
    if len(coastal) >= 9:
        step = len(coastal)/9.0
        for i in range(9):
            picks.append(coastal[int(i*step) % len(coastal)])
    else:
        picks = coastal[:]

    port_kinds = ["3:1"]*4 + ["wood","brick","sheep","wheat","ore"]
    rnd.shuffle(port_kinds)

    ports = []
    for i, eid in enumerate(picks[:9]):
        (ax,ay) = nodes_pos[eid[0]]
        (bx,by) = nodes_pos[eid[1]]
        mx,my = (ax+bx)/2, (ay+by)/2
        # push label outward
        vx,vy = mx-center[0], my-center[1]
        ln = math.hypot(vx,vy) or 1.0
        vx,vy = vx/ln, vy/ln
        px,py = mx + vx*30, my + vy*30

        k = port_kinds[i]
        if k == "3:1":
            ratio = 3
        else:
            ratio = 2
        ports.append(Port(pid=i, edge=eid, kind=k, ratio=ratio, pos=(px,py)))

    return Board(
        size=size,
        tiles=tiles,
        nodes_pos=nodes_pos,
        edges=edges,
        node_neighbors=node_neighbors,
        node_to_tiles=node_to_tiles,
        edge_to_tiles_count=all_edges_count,
        ports=ports,
        center=center
    )

# ---------------------------------------------------------
# Game state
# ---------------------------------------------------------

@dataclass
class Player:
    name: str
    is_bot: bool = False
    resources: dict[str,int] = field(default_factory=lambda: {r:0 for r in RES})
    vp: int = 0
    settlements: set[int] = field(default_factory=set)
    cities: set[int] = field(default_factory=set)
    roads: set[tuple[int,int]] = field(default_factory=set)
    dev: int = 0

@dataclass
class GameState:
    seed: int
    board: Board
    players: list[Player]
    bank: dict[str,int]
    current: int = 0
    phase: str = "setup"     # "setup" or "main"
    rolled: bool = False
    last_roll: Optional[int] = None
    setup_expect: str = "settlement"
    setup_step: int = 0
    setup_order: list[int] = field(default_factory=list)
    pending_settlement_for_road: dict[int, Optional[int]] = field(default_factory=dict)

    def log_prefix(self):
        return f"Players: You(VP {self.players[0].vp}) | Bot(VP {self.players[1].vp})  Phase: {self.phase}  Turn: {self.players[self.current].name}"

def new_game(seed: Optional[int]=None) -> GameState:
    if seed is None:
        seed = int(time.time()) % 1_000_000
    board = build_board(seed=seed, size=66.0)

    pl = [
        Player("You", is_bot=False),
        Player("Bot", is_bot=True),
    ]
    bank = {r:19 for r in RES}

    gs = GameState(
        seed=seed,
        board=board,
        players=pl,
        bank=bank,
        current=0,
        phase="setup",
        rolled=False,
        last_roll=None,
        setup_expect="settlement",
        setup_step=0,
        setup_order=[0,1,1,0],  # snake for 2 players: settlements: You, Bot, Bot, You (each followed by road)
        pending_settlement_for_road={0:None, 1:None},
    )
    return gs

def roll_dice(rnd: random.Random):
    return rnd.randint(1,6) + rnd.randint(1,6)

def can_pay(player: Player, cost: dict[str,int]) -> bool:
    return all(player.resources[r] >= n for r,n in cost.items())

def pay(player: Player, bank: dict[str,int], cost: dict[str,int]) -> None:
    for r,n in cost.items():
        player.resources[r] -= n
        bank[r] += n

def gain(player: Player, bank: dict[str,int], res: str, n: int) -> int:
    if res is None:
        return 0
    take = min(bank[res], n)
    bank[res] -= take
    player.resources[res] += take
    return take

def node_has_piece(gs: GameState, node: int) -> bool:
    for p in gs.players:
        if node in p.settlements or node in p.cities:
            return True
    return False

def owner_of_node(gs: GameState, node: int) -> Optional[int]:
    for i,p in enumerate(gs.players):
        if node in p.settlements or node in p.cities:
            return i
    return None

def is_city(gs: GameState, player_idx: int, node: int) -> bool:
    return node in gs.players[player_idx].cities

def adjacent_has_settlement_or_city(gs: GameState, node: int) -> bool:
    for nb in gs.board.node_neighbors[node]:
        if node_has_piece(gs, nb):
            return True
    return False

def legal_setup_settlement(gs: GameState, node: int) -> bool:
    if node_has_piece(gs, node):
        return False
    if adjacent_has_settlement_or_city(gs, node):
        return False
    return True

def legal_setup_road(gs: GameState, edge: tuple[int,int], player_idx: int) -> bool:
    eid = edge if edge[0] < edge[1] else (edge[1],edge[0])
    if eid in gs.players[player_idx].roads:
        return False
    for p in gs.players:
        if eid in p.roads:
            return False
    a,b = eid
    anchor = gs.pending_settlement_for_road.get(player_idx)
    if anchor is None:
        return False
    # must touch the just-placed settlement
    return (a == anchor or b == anchor)

def legal_main_road(gs: GameState, edge: tuple[int,int], player_idx: int) -> bool:
    eid = edge if edge[0] < edge[1] else (edge[1],edge[0])
    # empty?
    for p in gs.players:
        if eid in p.roads:
            return False
    a,b = eid
    # touches own settlement/city?
    p = gs.players[player_idx]
    if a in p.settlements or a in p.cities or b in p.settlements or b in p.cities:
        return True
    # touches own road network?
    for re in p.roads:
        if a in re or b in re:
            return True
    return False

def legal_main_settlement(gs: GameState, node: int, player_idx: int) -> bool:
    if node_has_piece(gs, node):
        return False
    if adjacent_has_settlement_or_city(gs, node):
        return False
    # must connect to own road
    p = gs.players[player_idx]
    for eid in p.roads:
        if node in eid:
            return True
    return False

def legal_city(gs: GameState, node: int, player_idx: int) -> bool:
    p = gs.players[player_idx]
    return (node in p.settlements) and (node not in p.cities)

def distribute_resources(gs: GameState, roll: int) -> dict[int, dict[str,int]]:
    # returns per-player gained
    gained = {i:{r:0 for r in RES} for i in range(len(gs.players))}
    # for each tile with token == roll: give adjacent settlements/cities
    for t in gs.board.tiles:
        if t.token != roll:
            continue
        res = TERRAIN_TO_RES[t.terrain]
        if res is None:
            continue
        for node in t.nodes:
            owner = owner_of_node(gs, node)
            if owner is None:
                continue
            amount = 2 if is_city(gs, owner, node) else 1
            took = gain(gs.players[owner], gs.bank, res, amount)
            gained[owner][res] += took
    return gained

def starting_resources_for_node(gs: GameState, player_idx: int, node: int):
    # after second settlement: resources from adjacent tiles (non-desert)
    p = gs.players[player_idx]
    for hid in gs.board.node_to_tiles[node]:
        t = gs.board.tiles[hid]
        res = TERRAIN_TO_RES[t.terrain]
        if res:
            gain(p, gs.bank, res, 1)

def ports_for_player(gs: GameState, player_idx: int) -> list[Port]:
    p = gs.players[player_idx]
    owned = []
    for port in gs.board.ports:
        a,b = port.edge
        if a in p.settlements or a in p.cities or b in p.settlements or b in p.cities:
            owned.append(port)
    return owned

def best_trade_ratio(gs: GameState, player_idx: int, give_res: str) -> int:
    ratio = 4
    for port in ports_for_player(gs, player_idx):
        if port.kind == "3:1":
            ratio = min(ratio, 3)
        elif port.kind == give_res:
            ratio = min(ratio, 2)
    return ratio

# ---------------------------------------------------------
# Bot logic (simple)
# ---------------------------------------------------------

def node_score(gs: GameState, node: int) -> float:
    # prefer high probability tokens and diversity
    score = 0.0
    for hid in gs.board.node_to_tiles[node]:
        t = gs.board.tiles[hid]
        if t.token is None:
            continue
        # probability weight (6/8 best)
        prob = {2:1,12:1,3:2,11:2,4:3,10:3,5:4,9:4,6:5,8:5}.get(t.token, 0)
        score += prob * 1.0
    return score

def bot_choose_setup_settlement(gs: GameState, rnd: random.Random) -> int:
    legal = [n for n in gs.board.nodes_pos.keys() if legal_setup_settlement(gs,n)]
    legal.sort(key=lambda n: node_score(gs,n), reverse=True)
    return legal[0] if legal else rnd.choice(list(gs.board.nodes_pos.keys()))

def bot_choose_setup_road(gs: GameState, player_idx: int, rnd: random.Random) -> tuple[int,int]:
    anchor = gs.pending_settlement_for_road[player_idx]
    cand = []
    for eid in gs.board.edges.keys():
        if legal_setup_road(gs, eid, player_idx):
            cand.append(eid)
    if cand:
        # prefer outward / arbitrary
        return rnd.choice(cand)
    # fallback any edge touching anchor
    if anchor is not None:
        for nb in gs.board.node_neighbors[anchor]:
            eid = (anchor,nb) if anchor<nb else (nb,anchor)
            return eid
    return rnd.choice(list(gs.board.edges.keys()))

def bot_take_turn(gs: GameState, ui_log, ui_refresh):
    rnd = random.Random(gs.seed + 99991 + gs.current*7 + (gs.last_roll or 0))

    if gs.phase == "setup":
        # bot acts only when it's bot's setup action
        cur = gs.current
        p = gs.players[cur]
        if not p.is_bot:
            return
        if gs.setup_expect == "settlement":
            n = bot_choose_setup_settlement(gs, rnd)
            place_settlement(gs, n, ui_log)
            ui_refresh()
            QtCore.QTimer.singleShot(220, lambda: bot_take_turn(gs, ui_log, ui_refresh))
        else:
            e = bot_choose_setup_road(gs, cur, rnd)
            place_road(gs, e, ui_log)
            ui_refresh()
            QtCore.QTimer.singleShot(220, lambda: bot_take_turn(gs, ui_log, ui_refresh))
        return

    # main phase bot
    cur = gs.current
    p = gs.players[cur]
    if not p.is_bot:
        return

    if not gs.rolled:
        r = roll_dice(rnd)
        gs.rolled = True
        gs.last_roll = r
        ui_log(f"[ROLL] Bot rolled {r}.")
        gained = distribute_resources(gs, r)
        # show gained
        s = []
        for res,n in gained[cur].items():
            if n: s.append(f"{res}+{n}")
        if s:
            ui_log("[GAIN] " + ", ".join(s))
        ui_refresh()

    # try build: settlement if possible
    built = False
    # city
    for node in list(p.settlements):
        if can_pay(p, COST["city"]) and legal_city(gs, node, cur):
            pay(p, gs.bank, COST["city"])
            p.settlements.remove(node)
            p.cities.add(node)
            p.vp += 1  # settlement already counted, city adds +1 (total 2)
            ui_log("[BOT] Upgraded to City.")
            built = True
            break

    if not built and can_pay(p, COST["settlement"]):
        nodes = [n for n in gs.board.nodes_pos.keys() if legal_main_settlement(gs,n,cur)]
        if nodes:
            nodes.sort(key=lambda n: node_score(gs,n), reverse=True)
            n = nodes[0]
            pay(p, gs.bank, COST["settlement"])
            p.settlements.add(n)
            p.vp += 1
            ui_log("[BOT] Built Settlement.")
            built = True

    if not built and can_pay(p, COST["road"]):
        edges = [eid for eid in gs.board.edges.keys() if legal_main_road(gs,eid,cur)]
        if edges:
            pay(p, gs.bank, COST["road"])
            p.roads.add(edges[0])
            ui_log("[BOT] Built Road.")
            built = True

    ui_refresh()
    QtCore.QTimer.singleShot(250, lambda: end_turn(gs, ui_log, ui_refresh))

# ---------------------------------------------------------
# Game actions
# ---------------------------------------------------------

def advance_setup(gs: GameState, ui_log):
    # move to next expected action or main phase
    if gs.setup_expect == "settlement":
        gs.setup_expect = "road"
    else:
        gs.setup_expect = "settlement"
        gs.setup_step += 1

    if gs.setup_step >= len(gs.setup_order):
        gs.phase = "main"
        gs.current = 0
        gs.rolled = False
        gs.last_roll = None
        ui_log("[SYS] Setup complete. Main phase started. Your turn.")
        return

    gs.current = gs.setup_order[gs.setup_step]
    # clear per-step?
    if gs.setup_expect == "settlement":
        gs.pending_settlement_for_road[gs.current] = None

def place_settlement(gs: GameState, node: int, ui_log):
    cur = gs.current
    p = gs.players[cur]

    if gs.phase == "setup":
        if gs.setup_expect != "settlement":
            ui_log("[!] Need to place a road now.")
            return False
        if not legal_setup_settlement(gs, node):
            ui_log("[!] Illegal settlement spot.")
            return False

        p.settlements.add(node)
        p.vp += 1
        gs.pending_settlement_for_road[cur] = node
        ui_log(f"[SETUP] {p.name} placed a settlement.")

        # if this is second-round settlement for this player -> give starting resources
        # In snake order [0,1,1,0] settlements happen at steps: 0,1,2,3 (roads are between)
        # Our setup_step increments after road. So we detect using count of settlements per player.
        if len(p.settlements) == 2:
            starting_resources_for_node(gs, cur, node)
            ui_log(f"[SETUP] {p.name} gained starting resources (after 2nd settlement).")

        advance_setup(gs, ui_log)
        return True

    # main
    if not gs.rolled:
        ui_log("[!] Roll first.")
        return False
    if not can_pay(p, COST["settlement"]):
        ui_log("[!] Not enough resources for settlement.")
        return False
    if not legal_main_settlement(gs, node, cur):
        ui_log("[!] Illegal settlement spot (needs road + distance rule).")
        return False

    pay(p, gs.bank, COST["settlement"])
    p.settlements.add(node)
    p.vp += 1
    ui_log(f"[BUILD] {p.name} built a settlement.")
    return True

def place_road(gs: GameState, edge: tuple[int,int], ui_log):
    cur = gs.current
    p = gs.players[cur]
    eid = edge if edge[0] < edge[1] else (edge[1],edge[0])

    if gs.phase == "setup":
        if gs.setup_expect != "road":
            ui_log("[!] Need to place a settlement now.")
            return False
        if not legal_setup_road(gs, eid, cur):
            ui_log("[!] Illegal road (must touch the just-placed settlement).")
            return False

        p.roads.add(eid)
        gs.pending_settlement_for_road[cur] = None
        ui_log(f"[SETUP] {p.name} placed a road.")
        advance_setup(gs, ui_log)
        return True

    # main
    if not gs.rolled:
        ui_log("[!] Roll first.")
        return False
    if not can_pay(p, COST["road"]):
        ui_log("[!] Not enough resources for road.")
        return False
    if not legal_main_road(gs, eid, cur):
        ui_log("[!] Illegal road (must connect).")
        return False

    pay(p, gs.bank, COST["road"])
    p.roads.add(eid)
    ui_log(f"[BUILD] {p.name} built a road.")
    return True

def upgrade_city(gs: GameState, node: int, ui_log):
    cur = gs.current
    p = gs.players[cur]
    if not gs.rolled:
        ui_log("[!] Roll first.")
        return False
    if not can_pay(p, COST["city"]):
        ui_log("[!] Not enough resources for city.")
        return False
    if not legal_city(gs, node, cur):
        ui_log("[!] You can upgrade only your settlement.")
        return False
    pay(p, gs.bank, COST["city"])
    p.settlements.remove(node)
    p.cities.add(node)
    p.vp += 1
    ui_log("[BUILD] Upgraded to city.")
    return True

def buy_dev(gs: GameState, ui_log):
    cur = gs.current
    p = gs.players[cur]
    if not gs.rolled:
        ui_log("[!] Roll first.")
        return False
    if not can_pay(p, COST["dev"]):
        ui_log("[!] Not enough resources for dev card.")
        return False
    pay(p, gs.bank, COST["dev"])
    p.dev += 1
    ui_log("[BUILD] Bought a development card.")
    return True

def end_turn(gs: GameState, ui_log, ui_refresh):
    if gs.phase != "main":
        return
    gs.current = (gs.current + 1) % len(gs.players)
    gs.rolled = False
    gs.last_roll = None
    ui_log(f"[TURN] Turn: {gs.players[gs.current].name}")
    ui_refresh()
    # if bot, act
    QtCore.QTimer.singleShot(250, lambda: bot_take_turn(gs, ui_log, ui_refresh))

# ---------------------------------------------------------
# UI helpers (icons / dice)
# ---------------------------------------------------------

def make_svg_pix(svg: str, size: int) -> QtGui.QPixmap:
    renderer = QtGui.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    renderer.render(p)
    p.end()
    return QtGui.QPixmap.fromImage(img)

# We avoid QtSvg dependency by using drawn icons (QPainter) instead of QSvgRenderer.
# But PySide6_Addons includes QtSvg in many installs; to be safe, we draw icons ourselves.

def draw_resource_icon(res: str, size: int) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    # base circle
    p.setPen(QtCore.Qt.NoPen)
    bg = {
        "wood": "#1e9f59",
        "brick": "#d46a12",
        "sheep": "#7ccf3a",
        "wheat": "#e4b315",
        "ore": "#8e99ad",
    }[res]
    p.setBrush(QtGui.QColor(bg))
    p.drawRoundedRect(0,0,size,size, size*0.22, size*0.22)

    # white glyph
    p.setBrush(QtGui.QColor("#ffffff"))
    p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), max(2, size*0.06)))

    if res == "wood":
        # tree
        p.drawEllipse(QtCore.QRectF(size*0.30, size*0.18, size*0.40, size*0.42))
        p.drawRect(QtCore.QRectF(size*0.47, size*0.55, size*0.06, size*0.22))
    elif res == "brick":
        # bricks
        p.drawRoundedRect(QtCore.QRectF(size*0.18, size*0.28, size*0.64, size*0.18), size*0.05, size*0.05)
        p.drawRoundedRect(QtCore.QRectF(size*0.18, size*0.52, size*0.64, size*0.18), size*0.05, size*0.05)
        p.drawLine(size*0.50, size*0.28, size*0.50, size*0.46)
        p.drawLine(size*0.34, size*0.52, size*0.34, size*0.70)
        p.drawLine(size*0.66, size*0.52, size*0.66, size*0.70)
    elif res == "sheep":
        # sheep cloud + head
        p.drawEllipse(QtCore.QRectF(size*0.20, size*0.34, size*0.45, size*0.34))
        p.drawEllipse(QtCore.QRectF(size*0.44, size*0.30, size*0.34, size*0.30))
        p.drawEllipse(QtCore.QRectF(size*0.58, size*0.52, size*0.20, size*0.18))
    elif res == "wheat":
        # wheat stalk
        p.drawLine(size*0.50, size*0.24, size*0.50, size*0.78)
        for i in range(4):
            y = size*(0.34 + i*0.10)
            p.drawLine(size*0.50, y, size*0.38, y+size*0.06)
            p.drawLine(size*0.50, y, size*0.62, y+size*0.06)
    elif res == "ore":
        # rock
        path = QtGui.QPainterPath()
        path.moveTo(size*0.25, size*0.70)
        path.lineTo(size*0.35, size*0.35)
        path.lineTo(size*0.55, size*0.28)
        path.lineTo(size*0.72, size*0.45)
        path.lineTo(size*0.66, size*0.72)
        path.closeSubpath()
        p.drawPath(path)

    p.end()
    return pm

def draw_die(face: int, size: int) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    rect = QtCore.QRectF(1,1,size-2,size-2)
    p.setBrush(QtGui.QColor("#f5f7fb"))
    p.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 2))
    p.drawRoundedRect(rect, size*0.18, size*0.18)

    pip = QtGui.QColor("#0b1e2b")
    p.setBrush(pip)
    p.setPen(QtCore.Qt.NoPen)

    def dot(x,y):
        r = size*0.07
        p.drawEllipse(QtCore.QRectF(x-r, y-r, 2*r, 2*r))

    cx = size*0.5
    cy = size*0.5
    off = size*0.22
    pts = {
        1: [(cx,cy)],
        2: [(cx-off,cy-off),(cx+off,cy+off)],
        3: [(cx-off,cy-off),(cx,cy),(cx+off,cy+off)],
        4: [(cx-off,cy-off),(cx+off,cy-off),(cx-off,cy+off),(cx+off,cy+off)],
        5: [(cx-off,cy-off),(cx+off,cy-off),(cx,cy),(cx-off,cy+off),(cx+off,cy+off)],
        6: [(cx-off,cy-off),(cx+off,cy-off),(cx-off,cy),(cx+off,cy),(cx-off,cy+off),(cx+off,cy+off)],
    }[face]
    for x,y in pts:
        dot(x,y)

    p.end()
    return pm

# ---------------------------------------------------------
# Graphics items: hex / nodes / edges / pieces / ports
# ---------------------------------------------------------

class ClickableItem:
    def __init__(self, callback):
        self._cb = callback
    def mousePressEvent(self, ev):
        if self._cb:
            self._cb()
        ev.accept()

class HexItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, terrain: str, token: Optional[int], pts: list[tuple[float,float]]):
        super().__init__()
        path = QtGui.QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for x,y in pts[1:]:
            path.lineTo(x,y)
        path.closeSubpath()
        self.setPath(path)

        c1,c2 = TERRAIN_COL[terrain]
        grad = QtGui.QLinearGradient(QtCore.QPointF(min(p[0] for p in pts), min(p[1] for p in pts)),
                                     QtCore.QPointF(max(p[0] for p in pts), max(p[1] for p in pts)))
        grad.setColorAt(0.0, QtGui.QColor(c1))
        grad.setColorAt(1.0, QtGui.QColor(c2))
        self.setBrush(QtGui.QBrush(grad))
        self.setPen(QtGui.QPen(QtGui.QColor("#061820"), 3))

        # token
        self.token = token
        if token is not None:
            # draw token as child
            circ = QtWidgets.QGraphicsEllipseItem(-18, -18, 36, 36, self)
            # token placed at polygon center
            # compute center
            cx = sum(x for x,_ in pts)/6
            cy = sum(y for _,y in pts)/6
            circ.setPos(cx, cy)
            circ.setBrush(QtGui.QColor("#f5f7fb"))
            circ.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 2))

            txt = QtWidgets.QGraphicsSimpleTextItem(str(token), circ)
            f = QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)
            txt.setFont(f)
            txt.setBrush(QtGui.QColor("#ef4444" if token in (6,8) else "#0b1e2b"))
            br = txt.boundingRect()
            txt.setPos(-br.width()/2, -br.height()/2 - 1)

class NodeItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, nid: int, x: float, y: float, on_click):
        super().__init__(-7, -7, 14, 14)
        self.nid = nid
        self.setPos(x, y)
        self.setBrush(QtGui.QColor("#0b1e2b"))
        self.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 1))
        self.setZValue(10)
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self._legal = False

    def set_legal(self, ok: bool):
        self._legal = ok
        if ok:
            self.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2))
            self.setBrush(QtGui.QColor("#0b1e2b"))
        else:
            self.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 1))
            self.setBrush(QtGui.QColor("#0b1e2b"))

    def hoverEnterEvent(self, ev):
        if self._legal:
            self.setBrush(QtGui.QColor(ACCENT))
        ev.accept()

    def hoverLeaveEvent(self, ev):
        self.setBrush(QtGui.QColor("#0b1e2b"))
        ev.accept()

    def mousePressEvent(self, ev):
        if self._on_click:
            self._on_click(self.nid)
        ev.accept()

class EdgeItem(QtWidgets.QGraphicsLineItem):
    def __init__(self, eid: tuple[int,int], ax,ay,bx,by, on_click):
        super().__init__(QtCore.QLineF(ax,ay,bx,by))
        self.eid = eid if eid[0] < eid[1] else (eid[1],eid[0])
        self.setZValue(8)
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self._legal = False

        self._base_pen = QtGui.QPen(QtGui.QColor("#061820"), 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._legal_pen = QtGui.QPen(QtGui.QColor(ACCENT), 9, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._hover_pen = QtGui.QPen(QtGui.QColor("#22d3ee"), 9, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)

        self.setPen(self._base_pen)

    def set_legal(self, ok: bool):
        self._legal = ok
        self.setPen(self._legal_pen if ok else self._base_pen)

    def hoverEnterEvent(self, ev):
        if self._legal:
            self.setPen(self._hover_pen)
        ev.accept()

    def hoverLeaveEvent(self, ev):
        self.setPen(self._legal_pen if self._legal else self._base_pen)
        ev.accept()

    def mousePressEvent(self, ev):
        if self._on_click:
            self._on_click(self.eid)
        ev.accept()

class RoadPiece(QtWidgets.QGraphicsLineItem):
    def __init__(self, ax,ay,bx,by, color: str):
        super().__init__(QtCore.QLineF(ax,ay,bx,by))
        self.setZValue(20)
        shadow = QtGui.QPen(QtGui.QColor("#000000"), 10, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        main = QtGui.QPen(QtGui.QColor(color), 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        self._shadow = shadow
        self._main = main
        self.setPen(self._main)

    def paint(self, painter, option, widget=None):
        painter.setPen(self._shadow)
        painter.drawLine(self.line())
        painter.setPen(self._main)
        painter.drawLine(self.line())

class SettlementPiece(QtWidgets.QGraphicsPathItem):
    def __init__(self, x,y, color: str):
        super().__init__()
        self.setZValue(25)
        w = 18
        h = 16
        path = QtGui.QPainterPath()
        path.moveTo(-w/2, h/2)
        path.lineTo(-w/2, 0)
        path.lineTo(0, -h/2)
        path.lineTo(w/2, 0)
        path.lineTo(w/2, h/2)
        path.closeSubpath()
        self.setPath(path)
        self.setPos(x,y)
        self.setBrush(QtGui.QColor(color))
        self.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 2))
        eff = QtWidgets.QGraphicsDropShadowEffect()
        eff.setBlurRadius(12)
        eff.setColor(QtGui.QColor(0,0,0,180))
        eff.setOffset(2,3)
        self.setGraphicsEffect(eff)

class CityPiece(QtWidgets.QGraphicsPathItem):
    def __init__(self, x,y, color: str):
        super().__init__()
        self.setZValue(26)
        path = QtGui.QPainterPath()
        # base block + roof
        path.addRoundedRect(QtCore.QRectF(-10, -4, 20, 14), 3, 3)
        roof = QtGui.QPainterPath()
        roof.moveTo(-12, -4)
        roof.lineTo(0, -16)
        roof.lineTo(12, -4)
        roof.closeSubpath()
        path = roof.united(path)
        self.setPath(path)
        self.setPos(x,y)
        self.setBrush(QtGui.QColor(color))
        self.setPen(QtGui.QPen(QtGui.QColor("#0b1e2b"), 2))
        eff = QtWidgets.QGraphicsDropShadowEffect()
        eff.setBlurRadius(14)
        eff.setColor(QtGui.QColor(0,0,0,180))
        eff.setOffset(2,3)
        self.setGraphicsEffect(eff)

class PortBadge(QtWidgets.QGraphicsItemGroup):
    def __init__(self, port: Port):
        super().__init__()
        self.port = port
        x,y = port.pos
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(-20,-12, 40, 24), 8, 8)
        box = QtWidgets.QGraphicsPathItem(path)
        box.setBrush(QtGui.QColor("#0b1e2b"))
        box.setPen(QtGui.QPen(QtGui.QColor("#12394a"), 2))
        box.setPos(x,y)
        self.addToGroup(box)

        label = port.kind if port.kind == "3:1" else f"2:1"
        txt = QtWidgets.QGraphicsSimpleTextItem(label, box)
        f = QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold)
        txt.setFont(f)
        txt.setBrush(QtGui.QColor(TXT))
        br = txt.boundingRect()
        txt.setPos(-br.width()/2, -br.height()/2 - 1)

        # small resource dot for 2:1
        if port.kind != "3:1":
            dot = QtWidgets.QGraphicsEllipseItem(-4, -4, 8, 8, box)
            col = {
                "wood":"#1e9f59","brick":"#d46a12","sheep":"#7ccf3a","wheat":"#e4b315","ore":"#8e99ad"
            }[port.kind]
            dot.setBrush(QtGui.QColor(col))
            dot.setPen(QtCore.Qt.NoPen)
            dot.setPos(16, -2)

        self.setZValue(12)

# ---------------------------------------------------------
# Trade dialog
# ---------------------------------------------------------

class TradeDialog(QtWidgets.QDialog):
    def __init__(self, gs: GameState, player_idx: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trade")
        self.setStyleSheet(f"background:{PANEL}; color:{TXT};")
        self.setModal(True)
        self.gs = gs
        self.player_idx = player_idx

        lay = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel("Bank trade. Port ratios apply if you own the port.")
        info.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(info)

        form = QtWidgets.QFormLayout()
        self.cb_give = QtWidgets.QComboBox()
        self.cb_give.addItems(RES)
        self.cb_get = QtWidgets.QComboBox()
        self.cb_get.addItems(RES)
        self.spin_get = QtWidgets.QSpinBox()
        self.spin_get.setRange(1, 5)
        self.lbl_ratio = QtWidgets.QLabel("")
        self._update_ratio()

        self.cb_give.currentIndexChanged.connect(self._update_ratio)
        self.cb_get.currentIndexChanged.connect(self._update_ratio)
        self.spin_get.valueChanged.connect(self._update_ratio)

        form.addRow("Give:", self.cb_give)
        form.addRow("Get:", self.cb_get)
        form.addRow("Get amount:", self.spin_get)
        form.addRow("Cost:", self.lbl_ratio)
        lay.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("Trade")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        self.resize(360, 200)

    def _update_ratio(self):
        give = self.cb_give.currentText()
        get = self.cb_get.currentText()
        amt = self.spin_get.value()
        ratio = best_trade_ratio(self.gs, self.player_idx, give)
        self.lbl_ratio.setText(f"{ratio*amt} {give} -> {amt} {get}  (ratio {ratio}:1)")
        self._ratio = ratio
        self._amt = amt

    def trade(self) -> tuple[str,str,int,int]:
        # (give, get, give_amount, get_amount)
        give = self.cb_give.currentText()
        get = self.cb_get.currentText()
        amt = self.spin_get.value()
        ratio = best_trade_ratio(self.gs, self.player_idx, give)
        return (give, get, ratio*amt, amt)

# ---------------------------------------------------------
# Main UI
# ---------------------------------------------------------

class BoardView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setBackgroundBrush(QtGui.QColor(BG))
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        if delta > 0:
            self.scale(1.12, 1.12)
        else:
            self.scale(0.89, 0.89)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CATAN — Desktop (Sprint 3: UI v5)")
        self.resize(1500, 860)
        self.setStyleSheet(f"QMainWindow{{background:{BG};}}")

        self.gs = new_game()
        self.rnd = random.Random(self.gs.seed + 12345)

        self.selected_action = None  # "settlement","road","city","dev","trade"

        # root layout
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        root_lay = QtWidgets.QVBoxLayout(root)
        root_lay.setContentsMargins(14,14,14,14)
        root_lay.setSpacing(10)

        # top bar (small)
        top = QtWidgets.QFrame()
        top.setStyleSheet(f"background:{PANEL}; border-radius:14px;")
        top_lay = QtWidgets.QHBoxLayout(top)
        top_lay.setContentsMargins(14,10,14,10)

        self.lbl_title = QtWidgets.QLabel("CATAN")
        self.lbl_title.setStyleSheet("font-size:18px; font-weight:800;")
        self.lbl_hint = QtWidgets.QLabel("Setup: place settlement then road. Click highlighted spots.")
        self.lbl_hint.setStyleSheet(f"color:{MUTED};")

        top_lay.addWidget(self.lbl_title)
        top_lay.addSpacing(12)
        top_lay.addWidget(self.lbl_hint, 1)

        # dice (clickable)
        dice_box = QtWidgets.QHBoxLayout()
        self.btn_d1 = QtWidgets.QToolButton()
        self.btn_d2 = QtWidgets.QToolButton()
        for b in (self.btn_d1, self.btn_d2):
            b.setFixedSize(54,54)
            b.setIconSize(QtCore.QSize(54,54))
            b.setStyleSheet("QToolButton{border:0px;}")
        self._set_dice_faces(1,1)
        self.btn_d1.clicked.connect(self.on_roll_clicked)
        self.btn_d2.clicked.connect(self.on_roll_clicked)
        dice_box.addWidget(self.btn_d1)
        dice_box.addWidget(self.btn_d2)
        top_lay.addLayout(dice_box)

        self.btn_end = QtWidgets.QPushButton("End turn")
        self.btn_end.setFixedHeight(44)
        self.btn_end.setStyleSheet(
            f"QPushButton{{background:{ACCENT}; color:#052018; border:0; border-radius:12px; padding:10px 16px; font-weight:700;}}"
            f"QPushButton:disabled{{background:#1c5b50; color:#0a2a25;}}"
        )
        self.btn_end.clicked.connect(self.on_end_turn)
        top_lay.addSpacing(10)
        top_lay.addWidget(self.btn_end)

        root_lay.addWidget(top)

        # middle: board + side panel
        mid = QtWidgets.QHBoxLayout()
        mid.setSpacing(12)

        # board card
        board_card = QtWidgets.QFrame()
        board_card.setStyleSheet(f"background:{PANEL2}; border-radius:16px;")
        board_lay = QtWidgets.QVBoxLayout(board_card)
        board_lay.setContentsMargins(14,14,14,14)

        self.scene = QtWidgets.QGraphicsScene()
        self.view = BoardView(self.scene)
        self.view.setMinimumWidth(980)
        board_lay.addWidget(self.view)

        mid.addWidget(board_card, 3)

        # side panel
        side = QtWidgets.QFrame()
        side.setStyleSheet(f"background:{PANEL}; border-radius:16px;")
        side_lay = QtWidgets.QVBoxLayout(side)
        side_lay.setContentsMargins(14,14,14,14)
        side_lay.setSpacing(10)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        side_lay.addWidget(self.lbl_status)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane{border:0;}"
            "QTabBar::tab{background:#0b2633; color:#9ab6c3; padding:8px 12px; border-top-left-radius:10px; border-top-right-radius:10px;}"
            "QTabBar::tab:selected{background:#0a2230; color:#e7f2f7;}"
        )

        # log
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("background:#061820; border-radius:12px; padding:10px;")
        self.tabs.addTab(self.log, "Log")

        # chat (smaller)
        chat_wrap = QtWidgets.QWidget()
        chat_lay = QtWidgets.QVBoxLayout(chat_wrap)
        chat_lay.setContentsMargins(0,0,0,0)
        self.chat = QtWidgets.QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setStyleSheet("background:#061820; border-radius:12px; padding:10px;")
        chat_lay.addWidget(self.chat, 1)
        row = QtWidgets.QHBoxLayout()
        self.inp = QtWidgets.QLineEdit()
        self.inp.setPlaceholderText("Say something to Bot…")
        self.inp.returnPressed.connect(self.on_send_chat)
        self.inp.setStyleSheet("background:#081c26; border:1px solid #12394a; border-radius:10px; padding:10px;")
        self.btn_send = QtWidgets.QPushButton("Send")
        self.btn_send.clicked.connect(self.on_send_chat)
        self.btn_send.setStyleSheet(f"background:{ACCENT}; color:#052018; border:0; border-radius:10px; padding:10px 14px; font-weight:700;")
        row.addWidget(self.inp, 1)
        row.addWidget(self.btn_send)
        chat_lay.addLayout(row)
        self.tabs.addTab(chat_wrap, "Chat")

        # bank tab
        bank_wrap = QtWidgets.QWidget()
        bank_lay = QtWidgets.QVBoxLayout(bank_wrap)
        bank_lay.setContentsMargins(0,0,0,0)
        self.bank_list = QtWidgets.QListWidget()
        self.bank_list.setStyleSheet("background:#061820; border-radius:12px; padding:10px;")
        bank_lay.addWidget(self.bank_list, 1)
        self.tabs.addTab(bank_wrap, "Bank")

        side_lay.addWidget(self.tabs, 1)

        mid.addWidget(side, 1)
        root_lay.addLayout(mid, 1)

        # bottom bar: build cards + your resources (big icons)
        bottom = QtWidgets.QFrame()
        bottom.setStyleSheet(f"background:{PANEL}; border-radius:16px;")
        bottom_lay = QtWidgets.QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(14,12,14,12)
        bottom_lay.setSpacing(12)

        # build palette (under dice idea -> still bottom but compact)
        self.palette = QtWidgets.QHBoxLayout()
        self.btn_set = self._card_btn("Settlement")
        self.btn_road = self._card_btn("Road")
        self.btn_city = self._card_btn("City")
        self.btn_dev = self._card_btn("Dev")
        self.btn_trade = self._card_btn("Trade")
        self.btn_set.clicked.connect(lambda: self.select_action("settlement"))
        self.btn_road.clicked.connect(lambda: self.select_action("road"))
        self.btn_city.clicked.connect(lambda: self.select_action("city"))
        self.btn_dev.clicked.connect(lambda: self.select_action("dev"))
        self.btn_trade.clicked.connect(lambda: self.select_action("trade"))
        for b in (self.btn_set,self.btn_road,self.btn_city,self.btn_dev,self.btn_trade):
            self.palette.addWidget(b)
        pal_wrap = QtWidgets.QWidget()
        pal_wrap.setLayout(self.palette)
        bottom_lay.addWidget(pal_wrap, 0)

        bottom_lay.addStretch(1)

        # resources (your hand only) bigger icons
        self.res_bar = QtWidgets.QHBoxLayout()
        self.res_widgets = {}
        for r in RES:
            w = self._res_chip(r)
            self.res_widgets[r] = w
            self.res_bar.addWidget(w)
        res_wrap = QtWidgets.QWidget()
        res_wrap.setLayout(self.res_bar)
        bottom_lay.addWidget(res_wrap, 0)

        root_lay.addWidget(bottom)

        # prepare board graphics
        self.hex_items = []
        self.node_items = {}
        self.edge_items = {}
        self.road_items = {}
        self.settle_items = {}
        self.city_items = {}
        self.port_items = []

        self._build_scene()
        self._log(f"[SYS] New game seed={self.gs.seed}. Setup: place settlement then road.")
        self._refresh_all()

        # if bot starts in setup step, trigger
        QtCore.QTimer.singleShot(250, lambda: bot_take_turn(self.gs, self._log, self._refresh_all))

    # ---------- UI building ----------
    def _card_btn(self, text):
        b = QtWidgets.QPushButton(text)
        b.setFixedSize(120, 52)
        b.setCheckable(True)
        b.setStyleSheet(
            "QPushButton{background:#0b2633; color:#e7f2f7; border:1px solid #12394a; border-radius:14px; font-weight:800;}"
            "QPushButton:checked{background:#0a2230; border:2px solid #25c2a0;}"
            "QPushButton:hover{border:2px solid #1aa78b;}"
        )
        return b

    def _res_chip(self, res: str):
        w = QtWidgets.QFrame()
        w.setFixedSize(140, 52)
        w.setStyleSheet("background:#0b2633; border:1px solid #12394a; border-radius:14px;")
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(10,6,10,6)
        lay.setSpacing(10)

        icon = QtWidgets.QLabel()
        pm = draw_resource_icon(res, 38)
        icon.setPixmap(pm)
        icon.setFixedSize(38,38)

        lbl = QtWidgets.QLabel("0")
        lbl.setStyleSheet("font-size:18px; font-weight:900;")

        name = QtWidgets.QLabel(res)
        name.setStyleSheet(f"color:{MUTED}; font-size:11px;")

        col = QtWidgets.QVBoxLayout()
        col.setContentsMargins(0,0,0,0)
        col.addWidget(lbl)
        col.addWidget(name)

        lay.addWidget(icon)
        lay.addLayout(col, 1)

        w._count = lbl
        return w

    def _build_scene(self):
        self.scene.clear()
        self.hex_items.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.road_items.clear()
        self.settle_items.clear()
        self.city_items.clear()
        self.port_items.clear()

        # hexes
        for t in self.gs.board.tiles:
            corners = hex_corners(t.cx, t.cy, self.gs.board.size*0.98)
            item = HexItem(t.terrain, t.token, corners)
            self.scene.addItem(item)
            self.hex_items.append(item)

        # edges
        for eid in self.gs.board.edges.keys():
            a,b = eid
            ax,ay = self.gs.board.nodes_pos[a]
            bx,by = self.gs.board.nodes_pos[b]
            it = EdgeItem(eid, ax,ay,bx,by, self.on_edge_click)
            self.scene.addItem(it)
            self.edge_items[eid] = it

        # nodes
        for nid,(x,y) in self.gs.board.nodes_pos.items():
            it = NodeItem(nid, x,y, self.on_node_click)
            self.scene.addItem(it)
            self.node_items[nid] = it

        # ports
        for port in self.gs.board.ports:
            pb = PortBadge(port)
            self.scene.addItem(pb)
            self.port_items.append(pb)

        # fit
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-60,-60,60,60))
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    # ---------- logging / status ----------
    def _log(self, msg: str):
        self.log.appendPlainText(msg)

    def _chat(self, who: str, msg: str):
        self.chat.appendPlainText(f"{who}: {msg}")

    def _set_dice_faces(self, a: int, b: int):
        self.btn_d1.setIcon(QtGui.QIcon(draw_die(a, 54)))
        self.btn_d2.setIcon(QtGui.QIcon(draw_die(b, 54)))

    def _refresh_status_text(self):
        gs = self.gs
        cur = gs.players[gs.current].name
        if gs.phase == "setup":
            need = gs.setup_expect
            self.lbl_hint.setText(f"Setup: place {need}. Click highlighted spots.")
        else:
            if gs.current == 0:
                s = "Your turn — " + ("rolled." if gs.rolled else "not rolled. Click dice.")
            else:
                s = "Bot is thinking…"
            self.lbl_hint.setText(s)

        self.lbl_status.setText(
            f"{gs.log_prefix()} | rolled={gs.rolled} lastRoll={gs.last_roll} | seed={gs.seed}"
        )

        # end turn enabled only for human in main
        self.btn_end.setEnabled(gs.phase=="main" and gs.current==0 and gs.rolled)

    def _refresh_bank_tab(self):
        self.bank_list.clear()
        for r in RES:
            self.bank_list.addItem(f"{r}: {self.gs.bank[r]}")

    def _refresh_resources(self):
        you = self.gs.players[0]
        for r in RES:
            self.res_widgets[r]._count.setText(str(you.resources[r]))

    def _clear_palette_checks(self):
        for b in (self.btn_set,self.btn_road,self.btn_city,self.btn_dev,self.btn_trade):
            b.setChecked(False)

    # ---------- legal highlights ----------
    def _update_legals(self):
        gs = self.gs
        cur = gs.current
        action = self.selected_action

        # reset
        for nid,it in self.node_items.items():
            it.set_legal(False)
        for eid,it in self.edge_items.items():
            it.set_legal(False)

        if gs.phase == "setup":
            if gs.players[cur].is_bot:
                return
            if gs.setup_expect == "settlement":
                for nid in self.node_items.keys():
                    if legal_setup_settlement(gs, nid):
                        self.node_items[nid].set_legal(True)
            else:
                for eid in self.edge_items.keys():
                    if legal_setup_road(gs, eid, cur):
                        self.edge_items[eid].set_legal(True)
            return

        # main phase: human only gets highlights
        if cur != 0:
            return
        if not action:
            return

        if action == "road":
            for eid in self.edge_items.keys():
                if legal_main_road(gs, eid, 0):
                    self.edge_items[eid].set_legal(True)
        elif action == "settlement":
            for nid in self.node_items.keys():
                if legal_main_settlement(gs, nid, 0):
                    self.node_items[nid].set_legal(True)
        elif action == "city":
            for nid in self.node_items.keys():
                if legal_city(gs, nid, 0):
                    self.node_items[nid].set_legal(True)

    # ---------- render pieces ----------
    def _sync_pieces(self):
        # remove old pieces
        for it in list(self.road_items.values()):
            self.scene.removeItem(it)
        for it in list(self.settle_items.values()):
            self.scene.removeItem(it)
        for it in list(self.city_items.values()):
            self.scene.removeItem(it)
        self.road_items.clear()
        self.settle_items.clear()
        self.city_items.clear()

        colors = ["#ff4d4d", "#ffffff"]  # You red, Bot white
        for pi,p in enumerate(self.gs.players):
            col = colors[pi]
            # roads
            for eid in p.roads:
                a,b = eid
                ax,ay = self.gs.board.nodes_pos[a]
                bx,by = self.gs.board.nodes_pos[b]
                it = RoadPiece(ax,ay,bx,by, col)
                self.scene.addItem(it)
                self.road_items[(pi,eid)] = it
            # settlements
            for n in p.settlements:
                x,y = self.gs.board.nodes_pos[n]
                it = SettlementPiece(x,y, col)
                self.scene.addItem(it)
                self.settle_items[(pi,n)] = it
            # cities
            for n in p.cities:
                x,y = self.gs.board.nodes_pos[n]
                it = CityPiece(x,y, col)
                self.scene.addItem(it)
                self.city_items[(pi,n)] = it

    # ---------- actions ----------
    def select_action(self, act: str):
        self._clear_palette_checks()
        self.selected_action = act

        if act == "settlement":
            self.btn_set.setChecked(True)
            self._log("[UI] Selected: Settlement. Click a legal node.")
        elif act == "road":
            self.btn_road.setChecked(True)
            self._log("[UI] Selected: Road. Click a legal edge.")
        elif act == "city":
            self.btn_city.setChecked(True)
            self._log("[UI] Selected: City. Click your settlement to upgrade.")
        elif act == "dev":
            self.btn_dev.setChecked(True)
            self._log("[UI] Selected: Dev. Click Dev again to buy (no board click).")
            # immediate buy for simplicity
            if self.gs.phase=="main" and self.gs.current==0:
                buy_dev(self.gs, self._log)
                self.selected_action = None
                self._clear_palette_checks()
        elif act == "trade":
            self.btn_trade.setChecked(True)
            if self.gs.phase=="main" and self.gs.current==0:
                dlg = TradeDialog(self.gs, 0, self)
                if dlg.exec() == QtWidgets.QDialog.Accepted:
                    give, get, give_amt, get_amt = dlg.trade()
                    you = self.gs.players[0]
                    ratio = give_amt // max(get_amt,1)
                    if you.resources[give] < give_amt:
                        self._log("[!] Not enough to trade.")
                    elif self.gs.bank[get] < get_amt:
                        self._log("[!] Bank has not enough " + get)
                    else:
                        you.resources[give] -= give_amt
                        self.gs.bank[give] += give_amt
                        take = min(self.gs.bank[get], get_amt)
                        self.gs.bank[get] -= take
                        you.resources[get] += take
                        self._log(f"[TRADE] {give_amt} {give} -> {take} {get} (ratio {ratio}:1)")
                self.selected_action = None
                self._clear_palette_checks()

        self._refresh_all()

    def on_node_click(self, nid: int):
        gs = self.gs

        if gs.phase == "setup":
            if gs.players[gs.current].is_bot:
                return
            if gs.setup_expect == "settlement":
                ok = place_settlement(gs, nid, self._log)
                if ok:
                    self._sync_pieces()
            else:
                self._log("[!] Need a road now. Click an edge.")
            self._refresh_all()
            QtCore.QTimer.singleShot(220, lambda: bot_take_turn(gs, self._log, self._refresh_all))
            return

        # main
        if gs.current != 0:
            return

        if not self.selected_action:
            return

        if self.selected_action == "settlement":
            ok = place_settlement(gs, nid, self._log)
            if ok:
                self._sync_pieces()
        elif self.selected_action == "city":
            ok = upgrade_city(gs, nid, self._log)
            if ok:
                self._sync_pieces()

        self._refresh_all()

    def on_edge_click(self, eid: tuple[int,int]):
        gs = self.gs

        if gs.phase == "setup":
            if gs.players[gs.current].is_bot:
                return
            if gs.setup_expect == "road":
                ok = place_road(gs, eid, self._log)
                if ok:
                    self._sync_pieces()
            else:
                self._log("[!] Need a settlement now. Click a node.")
            self._refresh_all()
            QtCore.QTimer.singleShot(220, lambda: bot_take_turn(gs, self._log, self._refresh_all))
            return

        # main
        if gs.current != 0:
            return
        if self.selected_action != "road":
            return
        ok = place_road(gs, eid, self._log)
        if ok:
            self._sync_pieces()
        self._refresh_all()

    def on_roll_clicked(self):
        gs = self.gs
        if gs.phase != "main":
            self._log("[!] Roll available after setup.")
            return
        if gs.current != 0:
            return
        if gs.rolled:
            return
        r = roll_dice(self.rnd)
        d1 = max(1, min(6, r - random.randint(1,6)))
        d2 = r - d1
        d2 = max(1, min(6, d2))
        self._set_dice_faces(d1, d2)

        gs.rolled = True
        gs.last_roll = r
        self._log(f"[ROLL] You rolled {r}.")
        gained = distribute_resources(gs, r)
        s = []
        for res,n in gained[0].items():
            if n: s.append(f"{res}+{n}")
        if s:
            self._log("[GAIN] " + ", ".join(s))

        self._refresh_all()
        # bot will move after you end turn

    def on_end_turn(self):
        end_turn(self.gs, self._log, self._refresh_all)

    def on_send_chat(self):
        text = self.inp.text().strip()
        if not text:
            return
        self.inp.clear()
        self._chat("You", text)
        # simple bot reply based on state
        gs = self.gs
        if "help" in text.lower():
            self._chat("Bot", "Click dice to roll, select a build card, then click highlighted spots. Trade uses ports if you own them.")
        elif "trade" in text.lower():
            self._chat("Bot", "Use Trade card. If you have a port (3:1 or 2:1), ratio improves automatically.")
        else:
            self._chat("Bot", "OK. Focus on high-probability numbers (6/8/9/10) and diversify resources.")

    def _refresh_all(self):
        self._refresh_status_text()
        self._refresh_resources()
        self._refresh_bank_tab()
        self._sync_pieces()
        self._update_legals()

# ---------------------------------------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

