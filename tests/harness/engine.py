from __future__ import annotations

import random
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.engine import rules as engine_rules
from app.engine.state import RESOURCES


class ScenarioFailure(Exception):
    def __init__(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


class GameDriver:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.game = engine_rules.build_game(seed=self.seed, max_players=2, size=62.0)
        self.logs: List[str] = []
        self.steps: List[Dict[str, Any]] = []
        self.on_step: Optional[Callable[["GameDriver", Dict[str, Any], Dict[str, Any]], None]] = None
        self.expected_totals = self._compute_resource_totals()

    def _log(self, msg: str) -> None:
        self.logs.append(str(msg))

    def _compute_resource_totals(self) -> Dict[str, int]:
        totals = {r: int(self.game.bank.get(r, 0)) for r in RESOURCES}
        for p in self.game.players:
            for r, q in p.res.items():
                totals[r] += int(q)
        return totals

    def replace_game(self, game) -> None:
        self.game = game
        self.expected_totals = self._compute_resource_totals()

    def snapshot(self) -> Dict[str, Any]:
        g = self.game
        return {
            "seed": g.seed,
            "phase": g.phase,
            "turn": g.turn,
            "vp": [p.vp for p in g.players],
            "longest_road": {
                "owner": g.longest_road_owner,
                "len": g.longest_road_len,
            },
            "largest_army": {
                "owner": g.largest_army_owner,
                "size": g.largest_army_size,
            },
            "bank": dict(g.bank),
        }

    def fail(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None) -> None:
        raise ScenarioFailure(message, kind=kind, details=details)

    def do(self, action: Dict[str, Any]) -> Dict[str, Any]:
        result = self.apply_action(action)
        self.steps.append(dict(action))
        if self.on_step:
            self.on_step(self, action, result)
        return result

    def legal_settlement_vertices(self, pid: int, require_road: bool) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if engine_rules.can_place_settlement(self.game, pid, vid, require_road=require_road):
                out.append(vid)
        return out

    def legal_city_vertices(self, pid: int) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if engine_rules.can_upgrade_city(self.game, pid, vid):
                out.append(vid)
        return out

    def legal_road_edges(self, pid: int, must_touch_vid: Optional[int] = None) -> List[Tuple[int, int]]:
        out = []
        for e in self.game.edges:
            if engine_rules.can_place_road(self.game, pid, e, must_touch_vid=must_touch_vid):
                out.append(e)
        return out

    def apply_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        g = self.game
        try:
            pid = int(action.get("pid", g.turn))
            _, events = engine_rules.apply_cmd(g, pid, action)
            result: Dict[str, Any] = {"ok": True}
            for ev in events:
                if ev.get("type") == "trade_bank":
                    result["rate"] = ev.get("rate")
                if ev.get("type") == "buy_dev":
                    result["card"] = ev.get("card")
                if ev.get("type") == "play_dev":
                    result["result"] = ev.get("result")
                if ev.get("type") == "roll" and ev.get("pending"):
                    result["pending"] = ev.get("pending")
            return result
        except engine_rules.RuleError as exc:
            return {
                "ok": False,
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "exception": traceback.format_exc(),
            }
