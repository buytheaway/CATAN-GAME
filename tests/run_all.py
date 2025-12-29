from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CATAN_TEST_MODE", "1")

from tests.harness.engine import GameDriver, ScenarioFailure
from tests.harness.invariants import check_invariants

DEFAULT_SEEDS = list(range(1, 21))


def _load_scenarios() -> List[Dict[str, Any]]:
    scenarios = []
    base = Path(__file__).parent / "scenarios"
    for path in sorted(base.glob("scenario_*.py")):
        name = path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        run = getattr(mod, "run", None)
        if callable(run):
            scenarios.append({"name": name, "module": mod, "run": run})
    return scenarios


def _severity(kind: str) -> str:
    if kind == "crash":
        return "Blocker"
    if kind == "invariant":
        return "Critical"
    if kind == "ui_smoke":
        return "Minor"
    return "Major"


def _write_bug_report(path: Path, failures: List[Dict[str, Any]]) -> None:
    lines = ["# BUG_REPORT", ""]
    if not failures:
        lines.append("No failures detected.")
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    for idx, f in enumerate(failures, start=1):
        title = f"[{f['scenario']}] {f['reason']}"
        lines.append(f"## {idx}. {title}")
        lines.append("")
        lines.append(f"Severity: {_severity(f['kind'])}")
        lines.append(f"Seed: {f['seed']}")
        lines.append("")
        lines.append("Steps to reproduce:")
        lines.append("```")
        lines.append(f"seed={f['seed']}")
        for step in f.get("steps", []):
            lines.append(json.dumps(step, sort_keys=True))
        lines.append("```")
        lines.append("")
        lines.append("Expected vs Actual:")
        lines.append("")
        lines.append(f"- Expected: {f.get('expected', 'scenario/invariants pass')} ")
        lines.append(f"- Actual: {f.get('actual', f['reason'])}")
        lines.append("")
        if f.get("details"):
            lines.append("Details:")
            lines.append("```")
            lines.append(json.dumps(f["details"], indent=2, sort_keys=True))
            lines.append("```")
            lines.append("")
        if f.get("trace"):
            lines.append("Stack trace:")
            lines.append("```")
            lines.append(f["trace"])
            lines.append("```")
            lines.append("")
        if f.get("logs"):
            lines.append("Recent logs:")
            lines.append("```")
            for line in f["logs"]:
                lines.append(line)
            lines.append("```")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    scenarios = _load_scenarios()
    report: Dict[str, Any] = {
        "timestamp": int(time.time()),
        "scenarios": [],
    }
    failures: List[Dict[str, Any]] = []

    for sc in scenarios:
        mod = sc["module"]
        seeds = getattr(mod, "SEEDS", DEFAULT_SEEDS)
        for seed in seeds:
            driver = GameDriver(seed)

            def on_step(drv: GameDriver, action: Dict[str, Any], result: Dict[str, Any]):
                if not result.get("ok", False):
                    raise ScenarioFailure("action failed", kind="rule", details={"action": action, "result": result})
                inv = check_invariants(drv.game, drv.expected_totals)
                if inv:
                    raise ScenarioFailure("invariants failed", kind="invariant", details={"failures": inv})

            driver.on_step = on_step

            scenario_entry = {
                "scenario": sc["name"],
                "seed": seed,
                "ok": True,
                "summary": None,
            }

            try:
                result = sc["run"](driver) or {}
                inv = check_invariants(driver.game, driver.expected_totals)
                if inv:
                    raise ScenarioFailure("invariants failed", kind="invariant", details={"failures": inv})
                scenario_entry["summary"] = result.get("summary", driver.snapshot())
                scenario_entry["steps"] = result.get("steps", driver.steps)
            except ScenarioFailure as sf:
                scenario_entry["ok"] = False
                scenario_entry["summary"] = driver.snapshot()
                scenario_entry["steps"] = driver.steps
                failures.append({
                    "scenario": sc["name"],
                    "seed": seed,
                    "kind": sf.kind,
                    "reason": str(sf),
                    "details": sf.details,
                    "steps": driver.steps,
                    "logs": driver.logs[-50:],
                })
            except Exception:
                scenario_entry["ok"] = False
                scenario_entry["summary"] = driver.snapshot()
                scenario_entry["steps"] = driver.steps
                failures.append({
                    "scenario": sc["name"],
                    "seed": seed,
                    "kind": "crash",
                    "reason": "exception",
                    "details": {},
                    "steps": driver.steps,
                    "logs": driver.logs[-50:],
                    "trace": traceback.format_exc(),
                })

            report["scenarios"].append(scenario_entry)

    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"report_{ts}.json"
    report["failures"] = failures
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    bug_path = reports_dir / "BUG_REPORT.md"
    _write_bug_report(bug_path, failures)

    if failures:
        print(f"FAIL: {len(failures)} failures. See {bug_path} and {report_path}")
        return 1

    print(f"PASS: {len(report['scenarios'])} scenario runs. Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
