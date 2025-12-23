from __future__ import annotations

import argparse
import asyncio
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import websockets

RES = {"wood","brick","wheat","sheep","ore"}

def parse_discard(s: str) -> dict:
    # wood=1 brick=0 ...
    out = {r: 0 for r in RES}
    parts = s.split()
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = k.strip().lower()
        if k in RES:
            out[k] = int(v.strip())
    return out

def parse_trade_bank(tokens: list[str]) -> tuple[str,int,str]:
    # trade bank give=wood:4 get=ore
    give_res = None
    give_n = None
    get_res = None
    for t in tokens:
        t = t.strip()
        if t.startswith("give="):
            x = t.split("=",1)[1]
            r, n = x.split(":",1)
            give_res = r.strip().lower()
            give_n = int(n.strip())
        if t.startswith("get="):
            get_res = t.split("=",1)[1].strip().lower()
    if not give_res or give_n is None or not get_res:
        raise ValueError("format: trade bank give=wood:4 get=ore")
    return give_res, give_n, get_res

def cmd_to_msg(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split()
    cmd = parts[0].lower()

    if cmd == "start":
        seed = int(parts[1]) if len(parts) > 1 else None
        return {"type": "start", "seed": seed}

    if cmd == "place":
        return {"type": "place", "node": int(parts[1]), "edge": int(parts[2])}

    if cmd == "roll":
        return {"type": "roll"}

    if cmd == "discard":
        give = parse_discard(" ".join(parts[1:]))
        return {"type": "discard", "give": give}

    if cmd == "robber":
        hx = int(parts[1])
        victim = parts[2] if len(parts) > 2 else None
        return {"type": "robber", "hex": hx, "victim": victim}

    if cmd == "build":
        kind = parts[1].lower()
        id_ = int(parts[2])
        return {"type": "build", "kind": kind, "id": id_}

    if cmd == "trade" and len(parts) >= 2 and parts[1].lower() == "bank":
        give_res, give_n, get_res = parse_trade_bank(parts[2:])
        return {"type": "trade_bank", "give_res": give_res, "give_n": give_n, "get_res": get_res}

    if cmd == "buy" and len(parts) >= 2 and parts[1].lower() == "dev":
        return {"type": "buy_dev"}

    if cmd == "play":
        kind = parts[1].lower()
        if kind == "knight":
            hx = int(parts[2])
            victim = parts[3] if len(parts) > 3 else None
            return {"type": "play_dev", "kind": "knight", "hex": hx, "victim": victim}
        if kind == "road":
            e1 = int(parts[2]); e2 = int(parts[3])
            return {"type": "play_dev", "kind": "road", "edge1": e1, "edge2": e2}
        if kind == "monopoly":
            return {"type": "play_dev", "kind": "monopoly", "res": parts[2].lower()}
        if kind == "plenty":
            return {"type": "play_dev", "kind": "plenty", "res1": parts[2].lower(), "res2": parts[3].lower()}
        raise ValueError("unknown play kind")

    if cmd == "end":
        return {"type": "end"}

    if cmd in ("help","state","quit","exit"):
        return {"type": "_local", "cmd": cmd}

    raise ValueError("Unknown command. Examples: roll | place 12 45 | build road 10 | trade bank give=wood:4 get=ore | buy dev | end")

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
        self.title("CATAN Desktop Client")
        self.geometry("980x680")
        self.minsize(860, 600)

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

        self._build_ui()
        self.after(120, self._poll_inbox)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.host_var, width=16).grid(row=0, column=1, padx=6)
        ttk.Label(top, text="Port").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.port_var, width=6).grid(row=0, column=3, padx=6)
        ttk.Label(top, text="Room").grid(row=0, column=4, sticky="w")
        ttk.Entry(top, textvariable=self.room_var, width=10).grid(row=0, column=5, padx=6)
        ttk.Label(top, text="Name").grid(row=0, column=6, sticky="w")
        ttk.Entry(top, textvariable=self.name_var, width=12).grid(row=0, column=7, padx=6)

        self.btn_connect = ttk.Button(top, text="Connect", command=self.connect)
        self.btn_connect.grid(row=0, column=8, padx=6)
        self.btn_disconnect = ttk.Button(top, text="Disconnect", command=self.disconnect, state="disabled")
        self.btn_disconnect.grid(row=0, column=9, padx=6)

        mid = ttk.Frame(self, padding=10)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))

        right = ttk.Frame(mid, width=360)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        # log
        ttk.Label(left, text="Log / State").pack(anchor="w")
        self.log = ScrolledText(left, height=18)
        self.log.pack(fill=tk.BOTH, expand=True)

        # command line
        cmdbar = ttk.Frame(left)
        cmdbar.pack(fill=tk.X, pady=(10,0))
        ttk.Label(cmdbar, text="Command").pack(side=tk.LEFT)
        self.cmd_entry = ttk.Entry(cmdbar)
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.cmd_entry.bind("<Return>", lambda e: self.send_command())
        ttk.Button(cmdbar, text="Send", command=self.send_command).pack(side=tk.LEFT)

        # quick buttons
        quick = ttk.Frame(left)
        quick.pack(fill=tk.X, pady=(10,0))
        ttk.Button(quick, text="start", command=lambda: self._send_line("start")).pack(side=tk.LEFT, padx=4)
        ttk.Button(quick, text="roll", command=lambda: self._send_line("roll")).pack(side=tk.LEFT, padx=4)
        ttk.Button(quick, text="end", command=lambda: self._send_line("end")).pack(side=tk.LEFT, padx=4)
        ttk.Button(quick, text="help", command=self._show_help).pack(side=tk.LEFT, padx=4)

        # status panel
        box = ttk.LabelFrame(right, text="Status", padding=10)
        box.pack(fill=tk.X)

        def row(r, label, var):
            ttk.Label(box, text=label).grid(row=r, column=0, sticky="w")
            ttk.Label(box, textvariable=var).grid(row=r, column=1, sticky="w", padx=8)

        row(0, "Conn:", self.status_var)
        row(1, "You:", self.you_var)
        row(2, "Phase:", self.phase_var)
        row(3, "Current:", self.current_var)
        row(4, "Rolled:", self.rolled_var)
        row(5, "LastRoll:", self.lastroll_var)

        # players
        pbox = ttk.LabelFrame(right, text="Players", padding=10)
        pbox.pack(fill=tk.BOTH, expand=True, pady=(10,0))
        self.players = ScrolledText(pbox, height=14)
        self.players.pack(fill=tk.BOTH, expand=True)

    def _log(self, s: str):
        self.log.insert(tk.END, s + "\n")
        self.log.see(tk.END)

    def _show_help(self):
        self._log("Commands:")
        self._log("  start [seed]")
        self._log("  place <node> <edge>")
        self._log("  roll")
        self._log("  discard wood=1 brick=0 wheat=0 sheep=0 ore=0")
        self._log("  robber <hex> [victimId]")
        self._log("  build road <edge> | build settlement <node> | build city <node>")
        self._log("  trade bank give=wood:4 get=ore")
        self._log("  buy dev")
        self._log("  play knight <hex> [victimId] | play road <e1> <e2> | play monopoly <res> | play plenty <r1> <r2>")
        self._log("  end")

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
        self.btn_connect.config(state="disabled")
        self.btn_disconnect.config(state="normal")

    def disconnect(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.status_var.set("Disconnected")
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")

    def _send_line(self, line: str):
        self.cmd_entry.delete(0, tk.END)
        self.cmd_entry.insert(0, line)
        self.send_command()

    def send_command(self):
        line = self.cmd_entry.get().strip()
        if not line:
            return
        try:
            msg = cmd_to_msg(line)
            if msg and msg.get("type") == "_local":
                if msg["cmd"] == "help":
                    self._show_help()
                self.cmd_entry.delete(0, tk.END)
                return
            if msg:
                self.outbox.put(msg)
                self._log(f"> {line}")
        except Exception as e:
            self._log(f"[BAD CMD] {e}")
        finally:
            self.cmd_entry.delete(0, tk.END)

    def _render_state(self, st: dict):
        pub = st.get("public") or {}
        priv = st.get("private") or {}
        you = st.get("you") or "-"

        self.status_var.set("Connected")
        self.you_var.set(you)
        self.phase_var.set(str(pub.get("phase")))
        self.current_var.set(str(pub.get("current_player")))
        self.rolled_var.set(str(pub.get("rolled")))
        self.lastroll_var.set(str(pub.get("last_roll")))

        self.players.delete("1.0", tk.END)
        pls = pub.get("players") or []
        for p in pls:
            self.players.insert(tk.END, f"{p['name']} ({p['id']})  VP={p['vp']}  Res#={p['res_count']}  K={p['knights']}  Dev={p['dev_hand']}+{p['dev_new']}\n")

        # concise state dump + hints
        hints = st.get("hints") or {}
        self._log(f"[STATE] phase={pub.get('phase')} current={pub.get('current_player')} rolled={pub.get('rolled')} roll={pub.get('last_roll')} winner={pub.get('winner')}")
        self._log(f"[YOU] res={priv.get('resources')} dev={priv.get('dev_hand')} new={priv.get('dev_new')} vp_cards={priv.get('vp_cards')}")
        if hints:
            self._log(f"[HINTS] {hints}")

    def _poll_inbox(self):
        try:
            while True:
                kind, payload = self.inbox.get_nowait()
                if kind == "state":
                    self._render_state(payload)
                elif kind == "error":
                    self._log(f"[ERROR] {payload}")
                else:
                    self._log(str(payload))
        except queue.Empty:
            pass
        self.after(120, self._poll_inbox)

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
