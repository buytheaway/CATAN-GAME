from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

import websockets
from rich.console import Console
from rich.table import Table

console = Console()

HELP = """
Commands
help
state
start [seed]                      (host only)
place <node> <edge>               (setup)

roll
discard wood=1 brick=0 wheat=0 sheep=0 ore=0
robber <hex> [victimId]

build road <edge>
build settlement <node>
build city <node>

trade bank give=wood:4 get=ore
buy dev

play knight <hex> [victimId]
play road <edge1> <edge2>
play monopoly <res>
play plenty <res1> <res2>

end
quit
"""

RES = {"wood","brick","wheat","sheep","ore"}

def parse_kv_counts(s: str) -> Dict[str,int]:
    # wood=1 brick=0 ...
    out: Dict[str,int] = {}
    parts = s.split()
    for p in parts:
        if "=" not in p:
            continue
        k,v = p.split("=",1)
        k = k.strip().lower()
        v = v.strip()
        if k in RES:
            out[k] = int(v)
    for r in RES:
        out.setdefault(r, 0)
    return out

def print_state(st: Dict[str, Any]):
    pub = st["public"]
    priv = st["private"]
    you = st["you"]
    host = st.get("host")
    hints = st.get("hints") or {}

    console.rule(f"STATE  you={you}{' (HOST)' if you==host else ''}")

    t = Table(show_header=True, header_style="bold")
    t.add_column("Name")
    t.add_column("Id")
    t.add_column("VP", justify="right")
    t.add_column("Res#", justify="right")
    t.add_column("K", justify="right")
    t.add_column("Dev", justify="right")
    for p in pub["players"]:
        mark = " (you)" if p["id"] == you else ""
        t.add_row(
            p["name"] + mark, p["id"],
            str(p["vp"]),
            str(p["res_count"]),
            str(p["knights"]),
            f'{p["dev_hand"]}+{p["dev_new"]}'
        )
    console.print(t)

    console.print(
        f"[bold]Phase:[/bold] {pub['phase']}  [bold]Turn:[/bold] {pub['turn']}  "
        f"[bold]Current:[/bold] {pub['current_player']}  [bold]Rolled:[/bold] {pub['rolled']}  "
        f"[bold]LastRoll:[/bold] {pub['last_roll']}  [bold]Deck:[/bold] {pub.get('dev_deck_left')}"
    )

    awards = pub.get("awards") or {}
    console.print(f"[bold]Awards:[/bold] LR={awards.get('longest_road_holder')}({awards.get('longest_road_len')}) "
                  f"LA={awards.get('largest_army_holder')}({awards.get('largest_army_size')})")

    if pub.get("winner"):
        console.print(f"[green][bold]WINNER:[/bold][/green] {pub['winner']}")

    console.print(f"[bold]Your resources:[/bold] {priv.get('resources')}")
    console.print(f"[bold]Your dev:[/bold] hand={priv.get('dev_hand')} new={priv.get('dev_new')} vp_cards={priv.get('vp_cards')}")

    if hints:
        console.print("[bold]Hints:[/bold]")
        for k, v in hints.items():
            console.print(f"  - {k}: {v}")

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--room", default="room1")
    ap.add_argument("--name", default="Player")
    args = ap.parse_args()

    uri = f"ws://{args.host}:{args.port}/ws/{args.room}"
    console.print(f"Connecting to {uri} as {args.name} ...")

    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type":"join","name":args.name}, ensure_ascii=False))

        latest_state: Dict[str, Any] | None = None

        async def receiver():
            nonlocal latest_state
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "state":
                    latest_state = msg
                    print_state(msg)
                elif msg.get("type") == "error":
                    console.print(f"[red]ERROR:[/red] {msg.get('message')}")
                else:
                    console.print(msg)

        async def input_loop():
            while True:
                line = await asyncio.to_thread(input, "> ")
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                cmd = parts[0].lower()

                if cmd in ("quit","exit"):
                    break
                if cmd == "help":
                    console.print(HELP)
                    continue
                if cmd == "state":
                    if latest_state:
                        print_state(latest_state)
                    else:
                        console.print("No state yet.")
                    continue

                try:
                    if cmd == "start":
                        seed = int(parts[1]) if len(parts) > 1 else None
                        await ws.send(json.dumps({"type":"start","seed":seed}, ensure_ascii=False))

                    elif cmd == "place":
                        node = int(parts[1]); edge = int(parts[2])
                        await ws.send(json.dumps({"type":"place","node":node,"edge":edge}, ensure_ascii=False))

                    elif cmd == "roll":
                        await ws.send(json.dumps({"type":"roll"}, ensure_ascii=False))

                    elif cmd == "discard":
                        give = parse_kv_counts(" ".join(parts[1:]))
                        await ws.send(json.dumps({"type":"discard","give":give}, ensure_ascii=False))

                    elif cmd == "robber":
                        hx = int(parts[1])
                        victim = parts[2] if len(parts) > 2 else None
                        await ws.send(json.dumps({"type":"robber","hex":hx,"victim":victim}, ensure_ascii=False))

                    elif cmd == "build":
                        kind = parts[1].lower()
                        id_ = int(parts[2])
                        await ws.send(json.dumps({"type":"build","kind":kind,"id":id_}, ensure_ascii=False))

                    elif cmd == "trade" and parts[1].lower() == "bank":
                        # trade bank give=wood:4 get=ore
                        raw = " ".join(parts[2:])
                        give_res = None; give_n = None; get_res = None
                        for token in raw.split():
                            if token.startswith("give="):
                                x = token.split("=",1)[1]
                                r,n = x.split(":",1)
                                give_res = r.lower().strip()
                                give_n = int(n)
                            if token.startswith("get="):
                                get_res = token.split("=",1)[1].lower().strip()
                        if not give_res or give_n is None or not get_res:
                            raise ValueError("format: trade bank give=wood:4 get=ore")
                        await ws.send(json.dumps({"type":"trade_bank","give_res":give_res,"give_n":give_n,"get_res":get_res}, ensure_ascii=False))

                    elif cmd == "buy" and parts[1].lower() == "dev":
                        await ws.send(json.dumps({"type":"buy_dev"}, ensure_ascii=False))

                    elif cmd == "play":
                        kind = parts[1].lower()
                        if kind == "knight":
                            hx = int(parts[2])
                            victim = parts[3] if len(parts) > 3 else None
                            await ws.send(json.dumps({"type":"play_dev","kind":"knight","hex":hx,"victim":victim}, ensure_ascii=False))
                        elif kind == "road":
                            e1 = int(parts[2]); e2 = int(parts[3])
                            await ws.send(json.dumps({"type":"play_dev","kind":"road","edge1":e1,"edge2":e2}, ensure_ascii=False))
                        elif kind == "monopoly":
                            res = parts[2].lower()
                            await ws.send(json.dumps({"type":"play_dev","kind":"monopoly","res":res}, ensure_ascii=False))
                        elif kind == "plenty":
                            r1 = parts[2].lower(); r2 = parts[3].lower()
                            await ws.send(json.dumps({"type":"play_dev","kind":"plenty","res1":r1,"res2":r2}, ensure_ascii=False))
                        else:
                            raise ValueError("unknown play kind")

                    elif cmd == "end":
                        await ws.send(json.dumps({"type":"end"}, ensure_ascii=False))

                    else:
                        console.print("Unknown command. Type 'help'.")
                except Exception:
                    console.print("Bad command format. Type 'help'.")

        recv_task = asyncio.create_task(receiver())
        await input_loop()
        recv_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
