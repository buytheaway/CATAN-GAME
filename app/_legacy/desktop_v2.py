from __future__ import annotations
import argparse
import asyncio
import json
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import websockets

RES = ["wood","brick","sheep","wheat","ore"]

PALETTE = ["#e74c3c","#3498db","#2ecc71","#f1c40f"]
NEUTRAL = "#2b2a28"
BG = "#1f1e1c"

def dist_point_segment(px,py, ax,ay, bx,by):
    vx, vy = bx-ax, by-ay
    wx, wy = px-ax, py-ay
    c1 = vx*wx + vy*wy
    if c1 <= 0: return math.hypot(px-ax, py-ay)
    c2 = vx*vx + vy*vy
    if c2 <= c1: return math.hypot(px-bx, py-by)
    t = c1 / c2
    cx, cy = ax + t*vx, ay + t*vy
    return math.hypot(px-cx, py-cy)

class WSWorker(threading.Thread):
    def __init__(self, uri: str, name: str, inbox: queue.Queue, outbox: queue.Queue):
        super().__init__(daemon=True)
        self.uri = uri
        self.name = name
        self.inbox = inbox
        self.outbox = outbox
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self.inbox.put(("error", f"{type(e).__name__}: {e}"))

    async def _main(self):
        async with websockets.connect(self.uri) as ws:
            await ws.send(json.dumps({"type":"join","name":self.name}, ensure_ascii=False))
            self.inbox.put(("info", f"Connected: {self.uri}"))

            async def recv_loop():
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        self.inbox.put(("info", raw))
                        continue
                    if msg.get("type") == "state":
                        self.inbox.put(("state", msg))
                    elif msg.get("type") == "error":
                        self.inbox.put(("error", msg.get("message","error")))
                    else:
                        self.inbox.put(("info", msg))

            async def send_loop():
                while not self._stop.is_set():
                    try:
                        obj = self.outbox.get(timeout=0.1)
                    except queue.Empty:
                        await asyncio.sleep(0.05)
                        continue
                    await ws.send(json.dumps(obj, ensure_ascii=False))

            await asyncio.gather(recv_loop(), send_loop())

class App(tk.Tk):
    def __init__(self, host: str, port: int, room: str, name: str):
        super().__init__()
        self.title("CATAN Desktop v2 (Board + Trade)")
        self.geometry("1200x760")
        self.minsize(1100, 680)

        self.inbox = queue.Queue()
        self.outbox = queue.Queue()
        self.worker: WSWorker | None = None

        self.host_var = tk.StringVar(value=host)
        self.port_var = tk.IntVar(value=port)
        self.room_var = tk.StringVar(value=room)
        self.name_var = tk.StringVar(value=name)

        self.status_var = tk.StringVar(value="Disconnected")
        self.you_var = tk.StringVar(value="-")
        self.phase_var = tk.StringVar(value="-")
        self.current_var = tk.StringVar(value="-")
        self.rolled_var = tk.StringVar(value="-")
        self.lastroll_var = tk.StringVar(value="-")

        self.players_by_id = {}
        self.color_by_player = {}

        self.pub = {}
        self.priv = {}
        self.hints = {}

        self.sel_node = None
        self.sel_edge = None
        self.sel_hex  = None
        self.sel_offer = None

        self._build_ui()
        self.after(120, self._poll_inbox)
        self.after(600, self.redraw)

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.host_var, width=16).grid(row=0, column=1, padx=6)
        ttk.Label(top, text="Port").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.port_var, width=6).grid(row=0, column=3, padx=6)
        ttk.Label(top, text="Room").grid(row=0, column=4, sticky="w")
        ttk.Entry(top, textvariable=self.room_var, width=10).grid(row=0, column=5, padx=6)
        ttk.Label(top, text="Name").grid(row=0, column=6, sticky="w")
        ttk.Entry(top, textvariable=self.name_var, width=12).grid(row=0, column=7, padx=6)

        ttk.Button(top, text="Connect", command=self.connect).grid(row=0, column=8, padx=6)
        ttk.Button(top, text="Disconnect", command=self.disconnect).grid(row=0, column=9, padx=6)

        mid = ttk.Frame(self, padding=8)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # left: board
        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="Board (click: node / edge / hex)").pack(anchor="w")
        self.canvas = tk.Canvas(left, bg="#141312", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        selbar = ttk.Frame(left)
        selbar.pack(fill=tk.X, pady=(6,0))
        self.sel_lbl = ttk.Label(selbar, text="Selected: -")
        self.sel_lbl.pack(side=tk.LEFT)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=(6,0))
        ttk.Button(btns, text="Start", command=lambda: self.send({"type":"start"})).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Roll", command=lambda: self.send({"type":"roll"})).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="End", command=lambda: self.send({"type":"end"})).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Place (setup)", command=self.place_setup).pack(side=tk.LEFT, padx=10)
        ttk.Button(btns, text="Build Road", command=lambda: self.build_selected("road")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Build Settlement", command=lambda: self.build_selected("settlement")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Build City", command=lambda: self.build_selected("city")).pack(side=tk.LEFT, padx=4)

        # right panel
        right = ttk.Frame(mid, width=420)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10,0))

        status = ttk.LabelFrame(right, text="Status", padding=8)
        status.pack(fill=tk.X)
        self._srow(status, 0, "Conn:", self.status_var)
        self._srow(status, 1, "You:", self.you_var)
        self._srow(status, 2, "Phase:", self.phase_var)
        self._srow(status, 3, "Current:", self.current_var)
        self._srow(status, 4, "Rolled:", self.rolled_var)
        self._srow(status, 5, "LastRoll:", self.lastroll_var)

        resbox = ttk.LabelFrame(right, text="Your resources", padding=8)
        resbox.pack(fill=tk.X, pady=(10,0))
        self.res_lbl = ttk.Label(resbox, text="-")
        self.res_lbl.pack(anchor="w")

        players = ttk.LabelFrame(right, text="Players", padding=8)
        players.pack(fill=tk.BOTH, expand=True, pady=(10,0))
        self.players_txt = ScrolledText(players, height=10)
        self.players_txt.pack(fill=tk.BOTH, expand=True)

        trade = ttk.LabelFrame(right, text="Trade (players)", padding=8)
        trade.pack(fill=tk.BOTH, expand=True, pady=(10,0))

        form = ttk.Frame(trade)
        form.pack(fill=tk.X)
        ttk.Label(form, text="To").grid(row=0, column=0, sticky="w")
        self.to_var = tk.StringVar(value="*")
        self.to_combo = ttk.Combobox(form, textvariable=self.to_var, values=["*"], width=18, state="readonly")
        self.to_combo.grid(row=0, column=1, padx=6, sticky="w")

        ttk.Label(form, text="Give (e.g. wood=1 wheat=1)").grid(row=1, column=0, sticky="w")
        self.give_var = tk.StringVar(value="wood=1")
        ttk.Entry(form, textvariable=self.give_var).grid(row=1, column=1, padx=6, sticky="we")

        ttk.Label(form, text="Get (e.g. ore=1)").grid(row=2, column=0, sticky="w")
        self.get_var = tk.StringVar(value="ore=1")
        ttk.Entry(form, textvariable=self.get_var).grid(row=2, column=1, padx=6, sticky="we")

        form.columnconfigure(1, weight=1)

        tbtns = ttk.Frame(trade)
        tbtns.pack(fill=tk.X, pady=(6,0))
        ttk.Button(tbtns, text="Offer", command=self.offer_trade).pack(side=tk.LEFT, padx=4)
        ttk.Button(tbtns, text="Accept selected", command=self.accept_trade).pack(side=tk.LEFT, padx=4)
        ttk.Button(tbtns, text="Cancel my selected", command=self.cancel_trade).pack(side=tk.LEFT, padx=4)

        ttk.Label(trade, text="Offers (click one)").pack(anchor="w", pady=(6,0))
        self.offers_list = tk.Listbox(trade, height=8)
        self.offers_list.pack(fill=tk.BOTH, expand=True)
        self.offers_list.bind("<<ListboxSelect>>", self.on_offer_select)

        logbox = ttk.LabelFrame(right, text="Log", padding=8)
        logbox.pack(fill=tk.BOTH, expand=True, pady=(10,0))
        self.log = ScrolledText(logbox, height=8)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _srow(self, frame, r, label, var):
        ttk.Label(frame, text=label).grid(row=r, column=0, sticky="w")
        ttk.Label(frame, textvariable=var).grid(row=r, column=1, sticky="w", padx=8)

    def logi(self, s: str):
        self.log.insert(tk.END, s + "\n")
        self.log.see(tk.END)

    def connect(self):
        if self.worker:
            return
        host = self.host_var.get().strip()
        port = int(self.port_var.get())
        room = self.room_var.get().strip()
        name = self.name_var.get().strip() or "Player"
        uri = f"ws://{host}:{port}/ws/{room}"
        self.worker = WSWorker(uri, name, self.inbox, self.outbox)
        self.worker.start()
        self.status_var.set("Connecting...")

    def disconnect(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.status_var.set("Disconnected")

    def send(self, obj: dict):
        self.outbox.put(obj)

    def parse_res_line(self, s: str):
        out = {}
        for part in s.split():
            if "=" not in part:
                continue
            k,v = part.split("=",1)
            k = k.strip().lower()
            if k in RES:
                out[k] = int(v.strip())
        return out

    # actions
    def place_setup(self):
        if self.sel_node is None or self.sel_edge is None:
            self.logi("[place] Select node AND edge first")
            return
        self.send({"type":"place","node":int(self.sel_node),"edge":int(self.sel_edge)})

    def build_selected(self, kind: str):
        if kind == "road":
            if self.sel_edge is None:
                self.logi("[build road] Select edge first")
                return
            self.send({"type":"build","kind":"road","id":int(self.sel_edge)})
            return
        if kind in ("settlement","city"):
            if self.sel_node is None:
                self.logi(f"[build {kind}] Select node first")
                return
            self.send({"type":"build","kind":kind,"id":int(self.sel_node)})
            return

    def offer_trade(self):
        to = self.to_var.get()
        give = self.parse_res_line(self.give_var.get())
        get  = self.parse_res_line(self.get_var.get())
        self.send({"type":"offer_trade","to":to,"give":give,"get":get})

    def accept_trade(self):
        if not self.sel_offer:
            self.logi("[trade] Select offer in list")
            return
        self.send({"type":"accept_trade","offer_id":self.sel_offer})

    def cancel_trade(self):
        if not self.sel_offer:
            self.logi("[trade] Select offer in list")
            return
        self.send({"type":"cancel_trade","offer_id":self.sel_offer})

    # UI events
    def on_offer_select(self, _evt):
        sel = self.offers_list.curselection()
        if not sel:
            self.sel_offer = None
            return
        idx = sel[0]
        line = self.offers_list.get(idx)
        # line starts with "<id> ..."
        self.sel_offer = line.split(" ",1)[0].strip()

    def on_canvas_click(self, evt):
        if not self.pub.get("board"):
            return

        b = self.pub["board"]
        nodes = b["nodes"]
        edges = b["edges"]
        hexes = b["hexes"]

        # scale
        W = max(1, self.canvas.winfo_width())
        H = max(1, self.canvas.winfo_height())
        allx = [x["x"] for x in nodes] + [h["cx"] for h in hexes]
        ally = [x["y"] for x in nodes] + [h["cy"] for h in hexes]
        minx, maxx = min(allx), max(allx)
        miny, maxy = min(ally), max(ally)

        pad = 80
        sx = (W - 2*pad) / (maxx - minx + 1e-6)
        sy = (H - 2*pad) / (maxy - miny + 1e-6)
        s = min(sx, sy)

        def tx(x): return pad + (x - minx) * s
        def ty(y): return pad + (y - miny) * s

        px, py = evt.x, evt.y

        # nearest node
        best_n = None
        best_d = 1e9
        for n in nodes:
            dx = px - tx(n["x"])
            dy = py - ty(n["y"])
            d = math.hypot(dx,dy)
            if d < best_d:
                best_d = d
                best_n = n
        if best_n and best_d < 18:
            self.sel_node = best_n["id"]
            self.sel_lbl.config(text=f"Selected: node={self.sel_node} edge={self.sel_edge} hex={self.sel_hex}")
            self.redraw()
            return

        # nearest edge
        node_by_id = {n["id"]: n for n in nodes}
        best_e = None
        best_ed = 1e9
        for e in edges:
            a = node_by_id[e["a"]]
            b2 = node_by_id[e["b"]]
            d = dist_point_segment(px,py, tx(a["x"]),ty(a["y"]), tx(b2["x"]),ty(b2["y"]))
            if d < best_ed:
                best_ed = d
                best_e = e
        if best_e and best_ed < 12:
            self.sel_edge = best_e["id"]
            self.sel_lbl.config(text=f"Selected: node={self.sel_node} edge={self.sel_edge} hex={self.sel_hex}")
            self.redraw()
            return

        # nearest hex center
        best_h = None
        best_hd = 1e9
        for h in hexes:
            d = math.hypot(px - tx(h["cx"]), py - ty(h["cy"]))
            if d < best_hd:
                best_hd = d
                best_h = h
        if best_h and best_hd < 35:
            self.sel_hex = best_h["id"]
            self.sel_lbl.config(text=f"Selected: node={self.sel_node} edge={self.sel_edge} hex={self.sel_hex}")
            self.redraw()
            return

    # render
    def redraw(self):
        self.canvas.delete("all")
        if not self.pub.get("board"):
            return
        b = self.pub["board"]
        nodes = b["nodes"]; edges = b["edges"]; hexes = b["hexes"]
        robber_hex = self.pub.get("robber_hex")

        W = max(1, self.canvas.winfo_width())
        H = max(1, self.canvas.winfo_height())
        allx = [x["x"] for x in nodes] + [h["cx"] for h in hexes]
        ally = [x["y"] for x in nodes] + [h["cy"] for h in hexes]
        minx, maxx = min(allx), max(allx)
        miny, maxy = min(ally), max(ally)

        pad = 80
        sx = (W - 2*pad) / (maxx - minx + 1e-6)
        sy = (H - 2*pad) / (maxy - miny + 1e-6)
        s = min(sx, sy)

        def tx(x): return pad + (x - minx) * s
        def ty(y): return pad + (y - miny) * s

        # player colors
        for i,p in enumerate(self.pub.get("players",[])):
            self.players_by_id[p["id"]] = p
            if p["id"] not in self.color_by_player:
                self.color_by_player[p["id"]] = PALETTE[i % len(PALETTE)]

        # draw hexes (simple circles + labels)
        for h in hexes:
            cx, cy = tx(h["cx"]), ty(h["cy"])
            r = 42
            fill = "#2e7d32" if h["res"] == "wood" else \
                   "#b71c1c" if h["res"] == "brick" else \
                   "#fdd835" if h["res"] == "wheat" else \
                   "#c0ca33" if h["res"] == "sheep" else \
                   "#607d8b" if h["res"] == "ore" else "#6d4c41"
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=fill, outline="#111", width=2)
            txt = f"{h['res']}\n{h['num'] if h['num'] is not None else ''}".strip()
            self.canvas.create_text(cx, cy, text=txt, fill="#0a0a0a", font=("Segoe UI", 10, "bold"))
            if robber_hex == h["id"]:
                self.canvas.create_text(cx, cy+36, text="ROBBER", fill="#ffffff", font=("Segoe UI", 9, "bold"))
            if self.sel_hex == h["id"]:
                self.canvas.create_oval(cx-r-6, cy-r-6, cx+r+6, cy+r+6, outline="#ffffff", width=3)

        # nodes lookup
        node_by_id = {n["id"]: n for n in nodes}

        # draw roads
        for e in edges:
            a = node_by_id[e["a"]]
            b2 = node_by_id[e["b"]]
            x1,y1 = tx(a["x"]),ty(a["y"])
            x2,y2 = tx(b2["x"]),ty(b2["y"])
            owner = e.get("owner")
            if owner:
                col = self.color_by_player.get(owner, "#ffffff")
                self.canvas.create_line(x1,y1,x2,y2, fill=col, width=6)
            else:
                self.canvas.create_line(x1,y1,x2,y2, fill="#444", width=2)

            if self.sel_edge == e["id"]:
                self.canvas.create_line(x1,y1,x2,y2, fill="#ffffff", width=3)

        # draw buildings
        for n in nodes:
            x,y = tx(n["x"]),ty(n["y"])
            bkind = n.get("b")
            owner = n.get("owner")
            if bkind:
                col = self.color_by_player.get(owner, "#ffffff")
                if bkind == "settlement":
                    self.canvas.create_polygon(x, y-10, x-10, y+10, x+10, y+10, fill=col, outline="#111", width=2)
                else:
                    self.canvas.create_rectangle(x-10, y-10, x+10, y+10, fill=col, outline="#111", width=2)
            else:
                self.canvas.create_oval(x-4,y-4,x+4,y+4, fill="#ddd", outline="#111")

            if self.sel_node == n["id"]:
                self.canvas.create_oval(x-12,y-12,x+12,y+12, outline="#ffffff", width=2)

    def _render_side(self):
        self.status_var.set("Connected")
        self.you_var.set(self.you)
        self.phase_var.set(str(self.pub.get("phase")))
        self.current_var.set(str(self.pub.get("current_player")))
        self.rolled_var.set(str(self.pub.get("rolled")))
        self.lastroll_var.set(str(self.pub.get("last_roll")))

        # resources
        r = self.priv.get("resources") or {}
        self.res_lbl.config(text="  ".join([f"{k}:{r.get(k,0)}" for k in RES]))

        # players
        self.players_txt.delete("1.0", tk.END)
        for p in self.pub.get("players", []):
            self.players_txt.insert(tk.END, f"{p['name']} ({p['id']}) online={p['online']} VP={p['vp']} res#={p['res_count']} dev={p['dev_hand']}+{p['dev_new']}\n")

        # trade target list
        vals = ["*"] + [p["id"] for p in self.pub.get("players", []) if p["id"] != self.you]
        self.to_combo["values"] = vals
        if self.to_var.get() not in vals:
            self.to_var.set("*")

        # offers list
        self.offers_list.delete(0, tk.END)
        for o in self.pub.get("offers", []):
            if o["status"] != "open":
                continue
            frm = self.players_by_id.get(o["from"], {}).get("name", o["from"])
            to = "ALL" if o["to"] == "*" else self.players_by_id.get(o["to"], {}).get("name", o["to"])
            self.offers_list.insert(tk.END, f"{o['id']}  {frm} -> {to}  give={o['give']} get={o['get']}")

        self.redraw()

    def _poll_inbox(self):
        try:
            while True:
                kind, payload = self.inbox.get_nowait()
                if kind == "state":
                    self.you = payload.get("you","-")
                    self.pub = payload.get("public") or {}
                    self.priv = payload.get("private") or {}
                    self.hints = payload.get("hints") or {}
                    self._render_side()
                elif kind == "error":
                    self.logi(f"[ERROR] {payload}")
                else:
                    self.logi(str(payload))
        except queue.Empty:
            pass
        self.after(120, self._poll_inbox)
        self.after(600, self.redraw)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--room", default="room1")
    ap.add_argument("--name", default="Player")
    args = ap.parse_args()

    app = App(args.host, args.port, args.room, args.name)
    app.mainloop()

if __name__ == "__main__":
    main()


