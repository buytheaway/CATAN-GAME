import asyncio, json, math, threading, time
from dataclasses import dataclass
from queue import Queue, Empty

import websockets
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import tkinter as tk

# ---------- look ----------
BG = "#0b1220"
PANEL = "#111a2e"
PANEL2 = "#0f172a"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#22c55e"
ACCENT2 = "#38bdf8"
DANGER = "#ef4444"

RES_COLORS = {
  "wood":"#22c55e",
  "brick":"#f97316",
  "sheep":"#a3e635",
  "wheat":"#facc15",
  "ore":"#94a3b8",
  "desert":"#eab308",
  "sea":"#0ea5e9"
}

def clamp(x,a,b): return max(a,min(b,x))

# ---------- net protocol (compatible with our earlier prototype style) ----------
# send: {"t":"join","name":...} then {"t":"cmd","cmd":"start|roll|end|..."} and trade messages
# recv: {"t":"hello","you":id} / {"t":"state", "state":{...}, "board":{...}} / {"t":"chat",...} / {"t":"trade",...}

@dataclass
class Sel:
    kind: str = ""   # "node" | "edge" | "hex"
    id: str = ""

class NetThread(threading.Thread):
    def __init__(self, out_q: Queue, in_q: Queue, host: str, port: int, room: str, name: str):
        super().__init__(daemon=True)
        self.out_q, self.in_q = out_q, in_q
        self.host, self.port, self.room, self.name = host, port, room, name
        self.stop_flag = False
        self.connected = False

    def stop(self):
        self.stop_flag = True

    def run(self):
        asyncio.run(self._main())

    async def _main(self):
        uri = f"ws://{self.host}:{self.port}/ws/{self.room}"
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                self.connected = True
                await ws.send(json.dumps({"t":"join","name":self.name}))
                self.out_q.put(("log", f"Connected: {uri} as {self.name}"))

                recv_task = asyncio.create_task(self._recv_loop(ws))
                send_task = asyncio.create_task(self._send_loop(ws))
                done, pending = await asyncio.wait([recv_task, send_task], return_when=asyncio.FIRST_COMPLETED)
                for p in pending:
                    p.cancel()
        except Exception as e:
            self.out_q.put(("err", f"Net error: {type(e).__name__}: {e}"))
        finally:
            self.connected = False
            self.out_q.put(("status", {"conn":"disconnected"}))

    async def _recv_loop(self, ws):
        while not self.stop_flag:
            msg = await ws.recv()
            try:
                data = json.loads(msg)
            except Exception:
                self.out_q.put(("log", msg))
                continue
            t = data.get("t") or data.get("type")
            self.out_q.put((t or "msg", data))

    async def _send_loop(self, ws):
        while not self.stop_flag:
            try:
                item = self.in_q.get(timeout=0.2)
            except Empty:
                continue
            try:
                await ws.send(json.dumps(item))
            except Exception as e:
                self.out_q.put(("err", f"Send error: {e}"))
                break

# ---------- Board Canvas ----------
class BoardCanvas(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg=BG, highlightthickness=0)
        self.board = None
        self.state = None
        self.sel = Sel()
        self.scale = 1.0
        self.pad = 24
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._click)

    def set_data(self, board, state):
        self.board, self.state = board, state
        self.redraw()

    def _fit(self):
        if not self.board: return
        W = max(10, self.winfo_width())
        H = max(10, self.winfo_height())
        minx=min(h["cx"] for h in self.board["hexes"]); maxx=max(h["cx"] for h in self.board["hexes"])
        miny=min(h["cy"] for h in self.board["hexes"]); maxy=max(h["cy"] for h in self.board["hexes"])
        # add radius margin
        R=self.board.get("hex_size", 70)
        minx-=R*1.2; maxx+=R*1.2
        miny-=R*1.2; maxy+=R*1.2
        bw=maxx-minx; bh=maxy-miny
        s=min((W-self.pad*2)/bw, (H-self.pad*2)/bh)
        self.scale=clamp(s,0.6,1.35)
        self._minx, self._miny = minx, miny

    def _tx(self, x): return (x-self._minx)*self.scale + self.pad
    def _ty(self, y): return (y-self._miny)*self.scale + self.pad

    def redraw(self):
        self.delete("all")
        if not self.board: 
            self._empty()
            return
        self._fit()
        self._draw_sea()
        self._draw_hexes()
        self._draw_edges()
        self._draw_nodes()
        self._draw_selection()

    def _empty(self):
        self.create_text(self.winfo_width()//2, self.winfo_height()//2, text="Connect to a room", fill=MUTED, font=("Segoe UI", 14, "bold"))

    def _draw_sea(self):
        # subtle grid / vignette
        W,H=self.winfo_width(), self.winfo_height()
        self.create_rectangle(0,0,W,H, fill=BG, outline=BG)
        for i in range(0, W, 32):
            self.create_line(i,0,i,H, fill="#0a162d")
        for j in range(0, H, 32):
            self.create_line(0,j,W,j, fill="#0a162d")

    def _hex_points(self, cx, cy, R):
        pts=[]
        for k in range(6):
            ang = math.radians(60*k - 30)
            x = cx + R*math.cos(ang)
            y = cy + R*math.sin(ang)
            pts += [self._tx(x), self._ty(y)]
        return pts

    def _draw_hexes(self):
        R=self.board.get("hex_size", 70)
        for h in self.board["hexes"]:
            res=h["res"]
            pts=self._hex_points(h["cx"], h["cy"], R*self.scale)
            fill=RES_COLORS.get(res,"#64748b")
            outline="#0b1220"
            self.create_polygon(pts, fill=fill, outline=outline, width=3)

            # token
            if h.get("num"):
                x=self._tx(h["cx"]); y=self._ty(h["cy"])
                self.create_oval(x-18,y-18,x+18,y+18, fill="#f8fafc", outline="#0f172a", width=2)
                num=str(h["num"])
                col=DANGER if num in ("6","8") else "#111827"
                self.create_text(x,y-1, text=num, fill=col, font=("Segoe UI", 12, "bold"))

    def _draw_nodes(self):
        if not self.state: return
        nodes=self.board["nodes"]
        pieces=self.state.get("pieces",{})
        settlements=pieces.get("settlements",{})
        for n in nodes:
            x=self._tx(n["x"]); y=self._ty(n["y"])
            r=6
            self.create_oval(x-r,y-r,x+r,y+r, fill="#1f2937", outline="#0f172a")
            if n["id"] in settlements:
                p=settlements[n["id"]]
                col=p.get("color","#e5e7eb")
                self.create_oval(x-10,y-10,x+10,y+10, fill=col, outline="#0f172a", width=2)

    def _draw_edges(self):
        if not self.state: return
        edges=self.board["edges"]
        pieces=self.state.get("pieces",{})
        roads=pieces.get("roads",{})
        for e in edges:
            x1=self._tx(e["x1"]); y1=self._ty(e["y1"])
            x2=self._tx(e["x2"]); y2=self._ty(e["y2"])
            key=e["id"]
            if key in roads:
                col=roads[key].get("color", "#e5e7eb")
                self.create_line(x1,y1,x2,y2, fill=col, width=6, capstyle="round")
            else:
                self.create_line(x1,y1,x2,y2, fill="#0f172a", width=3, capstyle="round")

    def _draw_selection(self):
        if not self.sel.kind or not self.board: return
        if self.sel.kind=="node":
            n=next((x for x in self.board["nodes"] if x["id"]==self.sel.id), None)
            if not n: return
            x=self._tx(n["x"]); y=self._ty(n["y"])
            self.create_oval(x-14,y-14,x+14,y+14, outline=ACCENT2, width=3)
        if self.sel.kind=="edge":
            e=next((x for x in self.board["edges"] if x["id"]==self.sel.id), None)
            if not e: return
            x1=self._tx(e["x1"]); y1=self._ty(e["y1"])
            x2=self._tx(e["x2"]); y2=self._ty(e["y2"])
            self.create_line(x1,y1,x2,y2, fill=ACCENT2, width=8, capstyle="round")

    def _click(self, ev):
        if not self.board: return
        x=ev.x; y=ev.y
        # pick nearest node/edge
        best=("","",1e9)
        for n in self.board["nodes"]:
            dx=self._tx(n["x"])-x; dy=self._ty(n["y"])-y
            d=dx*dx+dy*dy
            if d<best[2]:
                best=("node", n["id"], d)
        for e in self.board["edges"]:
            # distance to segment approx by endpoints
            dx=self._tx((e["x1"]+e["x2"])/2)-x
            dy=self._ty((e["y1"]+e["y2"])/2)-y
            d=dx*dx+dy*dy
            if d<best[2]:
                best=("edge", e["id"], d)
        if best[2] < 28*28:
            self.sel = Sel(best[0], best[1])
        else:
            self.sel = Sel()
        self.redraw()
        self.event_generate("<<SelectionChanged>>", when="tail")

# ---------- App ----------
class App(tb.Window):
    def __init__(self, host="127.0.0.1", port=8000, room="room1", name="Player"):
        super().__init__(themename="darkly")
        self.title("CATAN Desktop v3")
        self.geometry("1200x760")
        self.configure(bg=BG)

        self.out_q = Queue()
        self.in_q = Queue()
        self.net = None

        self.you = None
        self.board = None
        self.state = None

        self._build_ui(host,port,room,name)
        self.after(60, self._poll)

    def _build_ui(self, host, port, room, name):
        # top bar
        top = tb.Frame(self, bootstyle="dark")
        top.pack(fill=X, padx=14, pady=(14,10))

        self.var_host = tk.StringVar(value=host)
        self.var_port = tk.IntVar(value=port)
        self.var_room = tk.StringVar(value=room)
        self.var_name = tk.StringVar(value=name)

        def entry(lbl, var, w=14):
            tb.Label(top, text=lbl, foreground=MUTED).pack(side=LEFT, padx=(0,6))
            e = tb.Entry(top, textvariable=var, width=w)
            e.pack(side=LEFT, padx=(0,12))
            return e

        entry("Host", self.var_host, 16)
        entry("Port", self.var_port, 8)
        entry("Room", self.var_room, 12)
        entry("Name", self.var_name, 12)

        self.btn_connect = tb.Button(top, text="Connect", bootstyle="success", command=self.connect)
        self.btn_connect.pack(side=LEFT, padx=(4,8))
        self.btn_disc = tb.Button(top, text="Disconnect", bootstyle="secondary", command=self.disconnect)
        self.btn_disc.pack(side=LEFT)

        self.lbl_status = tb.Label(top, text="● Disconnected", foreground=DANGER)
        self.lbl_status.pack(side=RIGHT, padx=(8,0))

        # main layout
        body = tb.Panedwindow(self, orient=HORIZONTAL, bootstyle="dark")
        body.pack(fill=BOTH, expand=True, padx=14, pady=(0,14))

        # left card (board)
        left = tb.Frame(body, bootstyle="dark")
        body.add(left, weight=3)

        self.resources_bar = tb.Frame(left, bootstyle="dark")
        self.resources_bar.pack(fill=X, pady=(0,10))

        self.res_labels = {}
        for r in ["wood","brick","sheep","wheat","ore"]:
            pill = tb.Label(self.resources_bar, text=f"{r}:0", padding=(10,6), foreground="#0b1220",
                            background=RES_COLORS[r], font=("Segoe UI", 10, "bold"))
            pill.pack(side=LEFT, padx=(0,8))
            self.res_labels[r]=pill

        card = tb.Frame(left, bootstyle="dark")
        card.pack(fill=BOTH, expand=True)

        self.canvas = BoardCanvas(card)
        self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<<SelectionChanged>>", lambda e: self._sync_actions())

        # right panel
        right = tb.Frame(body, bootstyle="dark")
        body.add(right, weight=2)

        self.nb = tb.Notebook(right, bootstyle="dark")
        self.nb.pack(fill=BOTH, expand=True)

        # players tab
        tab_players = tb.Frame(self.nb, bootstyle="dark")
        self.nb.add(tab_players, text="Players")
        self.txt_players = tk.Text(tab_players, height=10, bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat")
        self.txt_players.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # chat tab
        tab_chat = tb.Frame(self.nb, bootstyle="dark")
        self.nb.add(tab_chat, text="Chat")
        self.txt_chat = tk.Text(tab_chat, bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat")
        self.txt_chat.pack(fill=BOTH, expand=True, padx=10, pady=(10,8))
        chat_row = tb.Frame(tab_chat, bootstyle="dark")
        chat_row.pack(fill=X, padx=10, pady=(0,10))
        self.var_chat = tk.StringVar()
        tb.Entry(chat_row, textvariable=self.var_chat).pack(side=LEFT, fill=X, expand=True, padx=(0,8))
        tb.Button(chat_row, text="Send", bootstyle="info", command=self.send_chat).pack(side=LEFT)

        # trade tab (simple)
        tab_trade = tb.Frame(self.nb, bootstyle="dark")
        self.nb.add(tab_trade, text="Trade")
        self.trade_info = tk.Text(tab_trade, bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat", height=10)
        self.trade_info.pack(fill=BOTH, expand=True, padx=10, pady=(10,8))

        trow = tb.Frame(tab_trade, bootstyle="dark")
        trow.pack(fill=X, padx=10, pady=(0,10))
        self.var_trade_to = tk.StringVar(value="")
        self.var_trade_give = tk.StringVar(value="wood:1")
        self.var_trade_get  = tk.StringVar(value="ore:1")
        tb.Label(trow, text="To", foreground=MUTED).pack(side=LEFT)
        tb.Entry(trow, textvariable=self.var_trade_to, width=14).pack(side=LEFT, padx=(6,10))
        tb.Label(trow, text="Give", foreground=MUTED).pack(side=LEFT)
        tb.Entry(trow, textvariable=self.var_trade_give, width=16).pack(side=LEFT, padx=(6,10))
        tb.Label(trow, text="Get", foreground=MUTED).pack(side=LEFT)
        tb.Entry(trow, textvariable=self.var_trade_get, width=16).pack(side=LEFT, padx=(6,10))
        tb.Button(trow, text="Offer", bootstyle="warning", command=self.trade_offer).pack(side=LEFT)

        # bottom actions (clean)
        bottom = tb.Frame(self, bootstyle="dark")
        bottom.pack(fill=X, padx=14, pady=(0,14))

        self.btn_primary = tb.Button(bottom, text="Start", bootstyle="success", command=self.primary_action, width=14)
        self.btn_primary.pack(side=LEFT, padx=(0,10))

        self.btn_ctx = tb.Button(bottom, text="Place / Build", bootstyle="info", command=self.context_action, width=18)
        self.btn_ctx.pack(side=LEFT, padx=(0,10))

        self.build_menu_btn = tb.Menubutton(bottom, text="Build ▾", bootstyle="secondary")
        self.build_menu = tk.Menu(self.build_menu_btn, tearoff=0)
        self.build_menu.add_command(label="Build Settlement (select node)", command=lambda: self._set_mode("build_settlement"))
        self.build_menu.add_command(label="Build Road (select edge)", command=lambda: self._set_mode("build_road"))
        self.build_menu_btn["menu"] = self.build_menu
        self.build_menu_btn.pack(side=LEFT)

        self.lbl_hint = tb.Label(bottom, text="Tip: click node/edge on board", foreground=MUTED)
        self.lbl_hint.pack(side=RIGHT)

        self.mode = ""  # "" | "setup_settlement" | "setup_road" | "build_settlement" | "build_road"

    # ---- connect/disconnect ----
    def connect(self):
        if self.net and self.net.connected: return
        host=self.var_host.get().strip()
        port=int(self.var_port.get())
        room=self.var_room.get().strip()
        name=self.var_name.get().strip() or "Player"
        self.net = NetThread(self.out_q, self.in_q, host, port, room, name)
        self.net.start()
        self._set_conn(True)

    def disconnect(self):
        if self.net:
            self.net.stop()
        self._set_conn(False)

    def _set_conn(self, on):
        if on:
            self.lbl_status.config(text="● Connecting...", foreground=ACCENT2)
        else:
            self.lbl_status.config(text="● Disconnected", foreground=DANGER)

    # ---- sending ----
    def send_cmd(self, cmd: str, **kw):
        self.in_q.put({"t":"cmd","cmd":cmd, **kw})

    def send_chat(self):
        txt=self.var_chat.get().strip()
        if not txt: return
        self.var_chat.set("")
        self.in_q.put({"t":"chat","text":txt})

    def trade_offer(self):
        to=self.var_trade_to.get().strip()
        give=self.var_trade_give.get().strip()
        get=self.var_trade_get.get().strip()
        self.in_q.put({"t":"trade_offer","to":to,"give":give,"get":get})

    # ---- UI actions ----
    def primary_action(self):
        if not self.state:
            self.send_cmd("ping")
            return
        phase=self.state.get("phase","lobby")
        if phase=="lobby":
            self.send_cmd("start")
        elif phase in ("setup","main"):
            if not self.state.get("rolled", False):
                self.send_cmd("roll")
            else:
                self.send_cmd("end")

    def _set_mode(self, mode):
        self.mode = mode
        self._sync_actions()

    def context_action(self):
        if not self.state or not self.canvas.sel.kind: return
        sel=self.canvas.sel
        phase=self.state.get("phase","lobby")

        # setup flow: first settlement then road
        if phase=="setup":
            if self.mode in ("", "setup_settlement") and sel.kind=="node":
                self.send_cmd("place_settlement", node=sel.id)
                self.mode="setup_road"
            elif self.mode=="setup_road" and sel.kind=="edge":
                self.send_cmd("place_road", edge=sel.id)
                self.mode="setup_settlement"
            return

        # main build
        if self.mode=="build_settlement" and sel.kind=="node":
            self.send_cmd("build_settlement", node=sel.id)
        elif self.mode=="build_road" and sel.kind=="edge":
            self.send_cmd("build_road", edge=sel.id)

    def _sync_actions(self):
        phase=(self.state or {}).get("phase","lobby")
        rolled=(self.state or {}).get("rolled",False)

        if phase=="lobby":
            self.btn_primary.config(text="Start")
            self.btn_ctx.config(text="Place / Build", state=DISABLED)
            self.build_menu_btn.config(state=DISABLED)
            self.mode=""
        elif phase=="setup":
            self.btn_primary.config(text="Roll (disabled)", state=DISABLED)
            self.build_menu_btn.config(state=DISABLED)
            # in setup you alternate settlement/road
            if self.mode in ("", "setup_settlement"):
                self.mode="setup_settlement"
                self.btn_ctx.config(text="Place Settlement (select node)", state=NORMAL)
            else:
                self.btn_ctx.config(text="Place Road (select edge)", state=NORMAL)
        else:
            self.btn_primary.config(state=NORMAL)
            self.btn_primary.config(text=("End Turn" if rolled else "Roll Dice"))
            self.btn_ctx.config(state=NORMAL, text="Do action on selection")
            self.build_menu_btn.config(state=NORMAL)
            if self.mode=="":
                self.mode="build_settlement"

    # ---- state updates ----
    def _apply_state(self, data):
        # data may be whole message or only state dict
        board=data.get("board") or self.board
        state=data.get("state") or data.get("s") or data.get("state_obj") or data.get("state")
        if board: self.board = board
        if state: self.state = state

        # resources
        you = (self.state or {}).get("you") or self.you
        if you and "players" in (self.state or {}):
            me = self.state["players"].get(you)
            if me and "res" in me:
                for k,v in me["res"].items():
                    if k in self.res_labels:
                        self.res_labels[k].config(text=f"{k}:{v}")

        # players tab
        self.txt_players.delete("1.0","end")
        pl = (self.state or {}).get("players",{})
        for pid,p in pl.items():
            cur = " ←" if pid==(self.state or {}).get("current") else ""
            self.txt_players.insert("end", f"{p.get('name','?')}  VP:{p.get('vp',0)}  id:{pid[:6]}{cur}\n")

        # trade tab
        self.trade_info.delete("1.0","end")
        offers=(self.state or {}).get("offers",[])
        if offers:
            for o in offers:
                self.trade_info.insert("end", f"#{o['id'][:6]} from {o['from_name']} -> {o['to_name']} give {o['give']} get {o['get']} status:{o['status']}\n")
        else:
            self.trade_info.insert("end","No trade offers.\n")

        # board
        if self.board and self.state:
            self.canvas.set_data(self.board, self.state)

        self._sync_actions()

    def _poll(self):
        try:
            while True:
                kind, payload = self.out_q.get_nowait()
                if kind=="log":
                    self._chat_sys(payload)
                elif kind=="err":
                    self._chat_sys(payload, error=True)
                elif kind in ("hello","msg"):
                    if isinstance(payload, dict):
                        self.you = payload.get("you") or self.you
                elif kind=="state":
                    if isinstance(payload, dict):
                        self._apply_state(payload)
                elif kind=="chat":
                    self._chat_line(payload.get("from","?"), payload.get("text",""))
                elif kind=="status":
                    if payload.get("conn")=="disconnected":
                        self.lbl_status.config(text="● Disconnected", foreground=DANGER)
                else:
                    # unknown message -> log
                    if isinstance(payload, dict):
                        self._chat_sys(json.dumps(payload, ensure_ascii=False))
        except Empty:
            pass
        finally:
            # connection indicator
            if self.net and self.net.connected:
                self.lbl_status.config(text="● Connected", foreground=ACCENT)
            self.after(60, self._poll)

    def _chat_sys(self, text, error=False):
        self.nb.select(1)  # chat tab
        self.txt_chat.insert("end", f"[SYS] {text}\n")
        self.txt_chat.see("end")

    def _chat_line(self, who, text):
        self.nb.select(1)
        self.txt_chat.insert("end", f"{who}: {text}\n")
        self.txt_chat.see("end")

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--room", default="room1")
    ap.add_argument("--name", default="Player")
    args=ap.parse_args()
    App(args.host,args.port,args.room,args.name).mainloop()

if __name__=="__main__":
    main()

