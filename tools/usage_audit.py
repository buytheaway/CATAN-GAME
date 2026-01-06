import ast
import os
import re
from collections import defaultdict, deque
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


def iter_py_files() -> List[Path]:
    files: List[Path] = []
    for root, _dirs, filenames in os.walk(APP_DIR):
        root_path = Path(root)
        if _is_excluded(root_path):
            continue
        for name in filenames:
            if name.endswith(".py"):
                files.append(root_path / name)
    return files


def module_name_for(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_module_map(files: Iterable[Path]) -> Dict[str, Path]:
    module_to_path = {}
    for p in files:
        module_to_path[module_name_for(p)] = p
    return module_to_path


def _resolve_relative(current_module: str, level: int) -> Optional[str]:
    if level == 0:
        return ""
    parts = current_module.split(".")
    if len(parts) < level:
        return None
    return ".".join(parts[:-level])


def _iter_imports_ast(path: Path) -> Tuple[List[Tuple[str, Optional[str]]], List[str]]:
    """
    Returns:
      - list of (import_string, resolved_module_or_None)
      - list of dynamic import strings (string literal) or "" for unknown
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return [], ["<syntax_error>"]

    imports: List[Tuple[str, Optional[str]]] = []
    dynamic: List[str] = []
    current_module = module_name_for(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            level = node.level or 0
            base = _resolve_relative(current_module, level)
            if base is None:
                imports.append((f"{'.'*level}{mod}", None))
                continue
            full_mod = f"{base}.{mod}".strip(".") if mod else base
            if not node.names:
                imports.append((full_mod, full_mod))
                continue
            for alias in node.names:
                if alias.name == "*":
                    imports.append((full_mod, full_mod))
                else:
                    imports.append((f"{full_mod}.{alias.name}", f"{full_mod}.{alias.name}"))
                    imports.append((full_mod, full_mod))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                if isinstance(fn.value, ast.Name):
                    name = f"{fn.value.id}.{fn.attr}"
            if name in ("importlib.import_module", "import_module", "__import__"):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    dynamic.append(node.args[0].value)
                else:
                    dynamic.append("")

    return imports, dynamic


IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)
FROM_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+([a-zA-Z0-9_\.\*]+)", re.MULTILINE)


def _iter_imports_fallback(path: Path) -> Set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    mods: Set[str] = set()
    for m in IMPORT_RE.finditer(text):
        mods.add(m.group(1))
    for m in FROM_RE.finditer(text):
        base = m.group(1)
        name = m.group(2)
        mods.add(base)
        if name != "*":
            mods.add(f"{base}.{name}")
    return mods


def resolve_to_path(module: str, module_map: Dict[str, Path]) -> Optional[Path]:
    if module in module_map:
        return module_map[module]
    return None


def parse_entrypoints(module_map: Dict[str, Path]) -> Set[str]:
    entry_modules: Set[str] = set()
    for bat in ROOT.glob("RUN_*.bat"):
        text = bat.read_text(encoding="utf-8", errors="replace")
        # -m module
        for m in re.finditer(r"-m\s+([a-zA-Z0-9_\.]+)", text):
            entry_modules.add(m.group(1))
        # python path/to/file.py
        for m in re.finditer(r"(?:py|python)(?:\.exe)?\s+([^\s]+\.py)", text, re.IGNORECASE):
            rel = Path(m.group(1).strip("\"'"))
            if not rel.is_absolute():
                rel = (ROOT / rel).resolve()
            if rel.exists() and rel.suffix == ".py" and APP_DIR in rel.parents:
                entry_modules.add(module_name_for(rel))
    # keep only modules inside app/
    entry_modules = {m for m in entry_modules if m in module_map}
    return entry_modules


def bfs_reachable(entry_modules: Set[str], module_map: Dict[str, Path], graph: Dict[str, Set[str]]) -> Set[str]:
    reachable: Set[str] = set()
    q = deque(entry_modules)
    while q:
        mod = q.popleft()
        if mod in reachable:
            continue
        reachable.add(mod)
        for nxt in graph.get(mod, set()):
            if nxt not in reachable:
                q.append(nxt)
    return reachable


def build_graph(files: List[Path], module_map: Dict[str, Path]):
    graph: Dict[str, Set[str]] = defaultdict(set)
    ambiguous: List[str] = []
    dynamic_info: Dict[str, List[str]] = defaultdict(list)

    for f in files:
        mod = module_name_for(f)
        imports, dynamic = _iter_imports_ast(f)
        for imp_str, resolved in imports:
            if not resolved:
                ambiguous.append(f"{f}: unresolved import '{imp_str}'")
                continue
            # resolve if inside app
            path = resolve_to_path(resolved, module_map)
            if path is not None:
                graph[mod].add(resolved)
            else:
                # may be stdlib or third-party
                if resolved.startswith("app.") or resolved == "app":
                    ambiguous.append(f"{f}: unresolved app import '{resolved}' (from '{imp_str}')")

        for dyn in dynamic:
            if dyn:
                dynamic_info[mod].append(dyn)
                if resolve_to_path(dyn, module_map):
                    graph[mod].add(dyn)
            else:
                ambiguous.append(f"{f}: dynamic import with non-constant module")

    return graph, ambiguous, dynamic_info


def build_fallback_discrepancies(files: List[Path], module_map: Dict[str, Path], graph: Dict[str, Set[str]]) -> List[str]:
    discrep = []
    for f in files:
        mod = module_name_for(f)
        fallback_mods = _iter_imports_fallback(f)
        ast_mods = graph.get(mod, set())
        for fm in sorted(fallback_mods):
            if fm not in ast_mods and resolve_to_path(fm, module_map):
                discrep.append(f"{f}: fallback import '{fm}' not in AST graph")
    return discrep


def write_list(path: Path, items: Iterable[str]) -> None:
    path.write_text("\n".join(sorted(set(items))) + "\n", encoding="utf-8")


def scan_hacks(files: List[Path]) -> Dict[str, List[str]]:
    patterns = {
        "QTimer.singleShot": re.compile(r"QTimer\.singleShot"),
        "monkey_patch_Game": re.compile(r"\bGame\.[A-Za-z_][A-Za-z0-9_]*\s*="),
        "runtime_patch_import": re.compile(r"\bruntime_patch\b"),
        "ports_bridge_import": re.compile(r"\bports_bridge\b"),
        "findChild": re.compile(r"\bfindChild\s*\("),
        "objectName": re.compile(r"\bobjectName\s*\("),
        "text_search": re.compile(r"\.text\s*\("),
    }
    hits: Dict[str, List[str]] = {k: [] for k in patterns}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(text, 1):
            for name, rx in patterns.items():
                if rx.search(line):
                    hits[name].append(f"{f}:{i}: {line.strip()}")
    return hits


def main():
    files = iter_py_files()
    module_map = build_module_map(files)
    graph, ambiguous, dynamic_info = build_graph(files, module_map)
    entry_modules = parse_entrypoints(module_map)
    reachable = bfs_reachable(entry_modules, module_map, graph)
    all_modules = set(module_map.keys())
    unreachable = sorted(all_modules - reachable)

    fallback_discrep = build_fallback_discrepancies(files, module_map, graph)
    ambiguous_all = list(ambiguous) + list(fallback_discrep)

    reachable_files = [str(module_map[m].relative_to(ROOT)) for m in sorted(reachable)]
    unreachable_files = [str(module_map[m].relative_to(ROOT)) for m in sorted(unreachable)]

    write_list(ROOT / "reachable_files.txt", reachable_files)
    write_list(ROOT / "unreachable_files.txt", unreachable_files)
    write_list(ROOT / "ambiguous_imports.txt", ambiguous_all)

    # hack scan only on reachable files
    reachable_paths = [module_map[m] for m in reachable if m in module_map]
    hacks = scan_hacks(reachable_paths)

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    hacks_path = TOOLS_DIR / "hacks_report.md"
    with hacks_path.open("w", encoding="utf-8") as f:
        f.write("# Hacks Report (Reachable Files)\n\n")
        for key, items in hacks.items():
            f.write(f"## {key}\n\n")
            if not items:
                f.write("- none\n\n")
                continue
            for line in items:
                f.write(f"- {line}\n")
            f.write("\n")

    # usage audit report
    report_path = TOOLS_DIR / "usage_audit_report.md"
    import_counts = defaultdict(int)
    for src, dsts in graph.items():
        for d in dsts:
            import_counts[d] += 1
    risky = sorted(import_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Usage Audit Report\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Entry modules: {', '.join(sorted(entry_modules)) or 'none found'}\n")
        f.write(f"- Reachable files: {len(reachable_files)}\n")
        f.write(f"- Unreachable files: {len(unreachable_files)}\n")
        f.write(f"- Ambiguous imports: {len(ambiguous_all)}\n\n")

        f.write("## Top Unused Candidates\n\n")
        for p in unreachable_files[:20]:
            f.write(f"- {p} (unreachable from entrypoints)\n")
        if len(unreachable_files) > 20:
            f.write(f"- ... and {len(unreachable_files) - 20} more\n")
        f.write("\n")

        f.write("## Risky Files (high fan-in or dynamic imports)\n\n")
        if risky:
            for mod, cnt in risky:
                f.write(f"- {module_map[mod].relative_to(ROOT)} (imported by {cnt})\n")
        else:
            f.write("- none\n")
        f.write("\n")

        if dynamic_info:
            f.write("## Dynamic Imports\n\n")
            for mod, items in dynamic_info.items():
                f.write(f"- {mod}: {', '.join(items)}\n")
            f.write("\n")

        f.write("## Suggested Safe Actions\n\n")
        f.write("- Move unreachable files to `app/_legacy/` (no deletions).\n")
        f.write("- Keep ambiguous imports until resolved.\n")
        f.write("- Refactor hack patterns (see `tools/hacks_report.md`).\n")

    print("Usage audit complete.")
    print(f"Reachable: {len(reachable_files)}, Unreachable: {len(unreachable_files)}, Ambiguous: {len(ambiguous_all)}")
    print("Outputs:")
    print("- reachable_files.txt")
    print("- unreachable_files.txt")
    print("- ambiguous_imports.txt")
    print("- tools/usage_audit_report.md")
    print("- tools/hacks_report.md")
    print("\nRun: python tools/usage_audit.py")


if __name__ == "__main__":
    main()
