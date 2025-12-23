from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Tuple
import random
from .catan_core import Game, pip_count

@dataclass
class BotConfig:
    think_ms: int = 350

class SimpleBot:
    def __init__(self, cfg: Optional[BotConfig] = None):
        self.cfg = cfg or BotConfig()

    def play_step(self, g: Game) -> bool:
        # returns True if did something
        if not g.cur_player().is_bot:
            return False

        ph = g.phase()
        pid = g.current

        if ph.startswith("setup"):
            _, act = g.setup_action()
            if act == "settlement":
                vids = list(g.legal_settlement_vertices(pid))
                if not vids:
                    return False
                # prefer high pip sum around vertex
                scored: List[Tuple[int,int]] = []
                for vid in vids:
                    score = 0
                    for tid in g.board.vertex_tiles.get(vid, []):
                        t = g.board.tiles[tid]
                        score += pip_count(t.number)
                    scored.append((score, vid))
                scored.sort(reverse=True)
                best = scored[0][1]
                g.place_settlement(pid, best)
                g.log.append("[BOT] placed settlement")
                return True

            if act == "road":
                eids = list(g.legal_road_edges(pid))
                if not eids:
                    return False
                eid = random.choice(eids)
                g.place_road(pid, eid)
                g.log.append("[BOT] placed road")
                return True

            return False

        # main
        if not g.rolled:
            g.roll_dice()
            g.log.append("[BOT] rolled")
            return True

        # build priorities: city > settlement > road else end
        # city
        for vid in list(g.legal_city_vertices(pid)):
            try:
                if g.has_cost(pid, g.cost_city()):
                    g.place_city(pid, vid)
                    g.log.append("[BOT] built city")
                    return True
            except:
                pass

        # settlement
        if g.has_cost(pid, g.cost_settlement()):
            vids = list(g.legal_settlement_vertices(pid))
            if vids:
                # again prefer high pips
                best = None
                bestScore = -1
                for vid in vids:
                    score = 0
                    for tid in g.board.vertex_tiles.get(vid, []):
                        t = g.board.tiles[tid]
                        score += pip_count(t.number)
                    if score > bestScore:
                        bestScore = score
                        best = vid
                if best is not None:
                    g.place_settlement(pid, best)
                    g.log.append("[BOT] built settlement")
                    return True

        # road
        if g.has_cost(pid, g.cost_road()):
            eids = list(g.legal_road_edges(pid))
            if eids:
                g.place_road(pid, random.choice(eids))
                g.log.append("[BOT] built road")
                return True

        g.end_turn()
        g.log.append("[BOT] end turn")
        return True