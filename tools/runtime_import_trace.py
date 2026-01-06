import argparse
import json
import re
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
TOOLS_DIR = ROOT / "tools"

EXCLUDE_DIRS = {
    APP_DIR / "_legacy",
    APP_DIR / "_legacy_bak",
}


def _is_excluded(path: Path) -> bool:
    for ex in EXCLUDE_DIRS:
        if ex in path.parents or path == ex:
            return True
    return False


def _iter_py_files() -> List[Path]:
    files: List[Path] = []
    for root, _dirs, names in os.walk(APP_DIR):
        root_path = Path(root)
        if _is_excluded(root_path):
            continue
        for name in names:
            if name.endswith(".py"):
                files.append(root_path / name)
    return files


def _module_name_for(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _build_module_map(files: Iterable[Path]) -> Dict[str, Path]:
    module_to_path: Dict[str, Path] = {}
    for p in files:
        module_to_path[_module_name_for(p)] = p
    return module_to_path


def _sanitize_name(mod: str) -> str:
    return mod.replace(".", "_")


def _child_run(target: str, out_path: Path, run_main: bool) -> None:
    imported: Set[str] = set()

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import builtins
    orig_import = builtins.__import__

    def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        try:
            imported.add(name)
        except Exception:
            pass
        return orig_import(name, globals, locals, fromlist, level)

    builtins.__import__ = tracking_import

    if target.endswith(".py") or os.path.sep in target:
        path = Path(target)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        run_name = "__main__" if run_main else "runtime_trace"
        runpy.run_path(str(path), run_name=run_name)
    else:
        if run_main:
            runpy.run_module(target, run_name="__main__")
        else:
            import importlib
            importlib.import_module(target)

    app_modules = set()
    for name, mod in list(sys.modules.items()):
        if not name:
            continue
        if name == "app" or name.startswith("app."):
            app_modules.add(name)

    payload = {
        "imported": sorted(imported),
        "app_modules": sorted(app_modules),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_child(target: str, out_path: Path, run_main: bool, extra_env: Optional[Dict[str, str]] = None) -> None:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--target",
        target,
        "--out",
        str(out_path),
    ]
    if run_main:
        cmd.append("--run-main")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)


def _load_payload(path: Path) -> Tuple[Set[str], Set[str]]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    return set(data.get("imported", [])), set(data.get("app_modules", []))


def _read_list(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()}


def _extract_ambiguous_paths(lines: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for line in lines:
        m = re.search(r"([A-Za-z]:\\\\[^:]+?\\.py)", line)
        if m:
            out.add(m.group(1))
            continue
        m = re.search(r"(app[\\/][^:]+?\\.py)", line)
        if m:
            out.add(m.group(1))
            continue
    return out


def _write_diff_report(
    report_path: Path,
    runtime_files: Set[str],
    static_reachable: Set[str],
    ambiguous_paths: Set[str],
) -> None:
    only_runtime = sorted(runtime_files - static_reachable)
    missing_runtime = sorted(static_reachable - runtime_files)
    ambiguous_missing = sorted(ambiguous_paths - runtime_files)

    lines: List[str] = []
    lines.extend(
        [
            "# Runtime Imports Diff",
            "",
            "## Summary",
            f"- Runtime files: {len(runtime_files)}",
            f"- Static reachable files: {len(static_reachable)}",
            f"- Ambiguous files: {len(ambiguous_paths)}",
            "",
            "## In Runtime but not Static Reachable",
        ]
    )
    lines.extend([f"- {p}" for p in only_runtime] if only_runtime else ["- none"])
    lines.extend(
        [
            "",
            "## Static Reachable but NOT in Runtime",
        ]
    )
    lines.extend([f"- {p}" for p in missing_runtime] if missing_runtime else ["- none"])
    lines.extend(
        [
            "",
            "## Ambiguous but NOT in Runtime",
        ]
    )
    lines.extend([f"- {p}" for p in ambiguous_missing] if ambiguous_missing else ["- none"])
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _update_usage_report(
    report_path: Path,
    runtime_files: Set[str],
    static_unreachable: Set[str],
    ambiguous_paths: Set[str],
) -> None:
    used = sorted(runtime_files)
    safe_unused = sorted(static_unreachable - runtime_files)
    maybe_unused = sorted(ambiguous_paths - runtime_files)

    lines: List[str] = []
    lines.extend(
        [
            "## Runtime Evidence",
            "",
            f"- USED: {len(used)}",
            f"- SAFE_UNUSED: {len(safe_unused)}",
            f"- MAYBE_UNUSED: {len(maybe_unused)}",
            "",
            "### USED",
        ]
    )
    lines.extend([f"- {p}" for p in used] if used else ["- none"])
    lines.extend(
        [
            "",
            "### SAFE_UNUSED",
        ]
    )
    lines.extend([f"- {p}" for p in safe_unused] if safe_unused else ["- none"])
    lines.extend(
        [
            "",
            "### MAYBE_UNUSED",
        ]
    )
    lines.extend([f"- {p}" for p in maybe_unused] if maybe_unused else ["- none"])
    lines.append("")
    section = "\n".join(lines)

    if report_path.exists():
        content = report_path.read_text(encoding="utf-8", errors="replace")
        if "## Runtime Evidence" in content:
            content = content.split("## Runtime Evidence")[0].rstrip() + "\n\n"
        report_path.write_text(content + section, encoding="utf-8")
    else:
        report_path.write_text("# Usage Audit Report\n\n" + section, encoding="utf-8")


def _write_safe_move_plan(path: Path, safe_unused: Set[str]) -> None:
    lines = [
        "# Safe Move Plan",
        "",
        "Move these files to `app/_legacy_next/` (no deletions).",
        "",
    ]
    if safe_unused:
        lines.extend(f"- {p}" for p in sorted(safe_unused))
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parent_main(entries: List[Tuple[str, bool, Optional[Dict[str, str]]]]) -> None:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, Path] = {}

    for target, run_main, extra_env in entries:
        out_name = f"runtime_imports_{_sanitize_name(target)}.txt"
        out_path = TOOLS_DIR / out_name
        _run_child(target, out_path, run_main=run_main, extra_env=extra_env)
        outputs[target] = out_path

    module_map = _build_module_map(_iter_py_files())

    runtime_union_modules: Set[str] = set()
    runtime_union_files: Set[str] = set()
    entry_files: Set[str] = set()
    for target, out_path in outputs.items():
        _imports, app_mods = _load_payload(out_path)
        runtime_union_modules.update(app_mods)
        for mod in app_mods:
            if mod in module_map:
                runtime_union_files.add(str(module_map[mod].relative_to(ROOT)))
        if target in module_map:
            entry_files.add(str(module_map[target].relative_to(ROOT)))
    runtime_union_files.update(entry_files)

    union_path = TOOLS_DIR / "runtime_imports_union.txt"
    union_path.write_text("\n".join(sorted(runtime_union_files)) + "\n", encoding="utf-8")

    static_reachable = _read_list(ROOT / "reachable_files.txt")
    static_unreachable = _read_list(ROOT / "unreachable_files.txt")
    ambiguous_lines = _read_list(ROOT / "ambiguous_imports.txt")
    ambiguous_paths = _extract_ambiguous_paths(ambiguous_lines)

    _write_diff_report(
        TOOLS_DIR / "runtime_imports_diff.md",
        runtime_union_files,
        static_reachable,
        ambiguous_paths,
    )

    _update_usage_report(
        TOOLS_DIR / "usage_audit_report.md",
        runtime_union_files,
        static_unreachable,
        ambiguous_paths,
    )

    safe_unused = static_unreachable - runtime_union_files
    _write_safe_move_plan(TOOLS_DIR / "safe_move_plan.md", safe_unused)

    print("Runtime import trace complete.")
    print("Outputs:")
    for target, out_path in outputs.items():
        print(f"- {out_path.relative_to(ROOT)}")
    print(f"- {union_path.relative_to(ROOT)}")
    print("- tools/runtime_imports_diff.md")
    print("- tools/safe_move_plan.md")
    print("- tools/usage_audit_report.md")
    print("\nRun: python tools/runtime_import_trace.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--target", help="Module or file to run")
    parser.add_argument("--out", help="Output file (child mode)")
    parser.add_argument("--run-main", action="store_true")
    args = parser.parse_args()

    if args.child:
        if not args.target or not args.out:
            raise SystemExit("--target and --out required in child mode")
        _child_run(args.target, Path(args.out), run_main=args.run_main)
        return

    entries = [
        ("app.main_menu", True, {"CATAN_TEST_MODE": "sp_quick"}),
        ("app.main_menu", True, {"CATAN_TEST_MODE": "ui_full_init"}),
        ("app.main_menu", True, {"CATAN_TEST_MODE": "mp_lobby"}),
        ("app.server_mp", False, None),
    ]
    parent_main(entries)


if __name__ == "__main__":
    main()
