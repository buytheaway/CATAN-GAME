from __future__ import annotations

from PySide6 import QtCore, QtWidgets

_RES = ("wood","brick","sheep","wheat","ore")

def _norm_kind(kind):
    if kind is None:
        return None
    s = str(kind).strip().lower()
    # UI strings like "2:1 ore", "2:1 wheat", "3:1"
    if "3:1" in s or "3 to 1" in s or "3/1" in s or "3to1" in s or "generic" in s:
        return "3:1"
    for r in _RES:
        if r in s:
            return r
    # allow already normalized "wood"/"brick"/...
    if s in _RES:
        return s
    return s

def _norm_vid(v):
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return v

def _is_port_item(p):
    if isinstance(p, dict):
        k = p.get("kind")
        a = p.get("a", p.get("v1"))
        b = p.get("b", p.get("v2"))
        return (k is not None) and (a is not None) and (b is not None)
    # object
    k = getattr(p, "kind", None)
    a = getattr(p, "a", None) or getattr(p, "v1", None)
    b = getattr(p, "b", None) or getattr(p, "v2", None)
    return (k is not None) and (a is not None) and (b is not None)

def _to_port_dict(p):
    if isinstance(p, dict):
        kind = p.get("kind")
        a = p.get("a", p.get("v1"))
        b = p.get("b", p.get("v2"))
    else:
        kind = getattr(p, "kind", None)
        a = getattr(p, "a", None) or getattr(p, "v1", None)
        b = getattr(p, "b", None) or getattr(p, "v2", None)
    return {"kind": _norm_kind(kind), "a": _norm_vid(a), "b": _norm_vid(b)}

def _extract_ports(win):
    # common attribute names
    for name in ("ports","_ports","port_defs","_port_defs","_ui_ports","_ports_ui"):
        v = getattr(win, name, None)
        if isinstance(v, (list, tuple)) and v and _is_port_item(v[0]):
            return [_to_port_dict(x) for x in v]

    # scan __dict__ for any port-like list
    for name, v in getattr(win, "__dict__", {}).items():
        if isinstance(v, (list, tuple)) and v and _is_port_item(v[0]):
            return [_to_port_dict(x) for x in v]

    # last resort: scan QGraphicsScene items for badges with .port / ._port / .port_def
    scene = getattr(win, "scene", None) or getattr(win, "_scene", None)
    if scene is not None and hasattr(scene, "items"):
        try:
            items = scene.items()
            for it in items:
                for attr in ("port","_port","port_def","_port_def"):
                    pv = getattr(it, attr, None)
                    if pv is not None and _is_port_item(pv):
                        # could be single port, collect all we find
                        out = []
                        for it2 in items:
                            for attr2 in ("port","_port","port_def","_port_def"):
                                pv2 = getattr(it2, attr2, None)
                                if pv2 is not None and _is_port_item(pv2):
                                    out.append(_to_port_dict(pv2))
                                    break
                        if out:
                            return out
        except Exception:
            pass

    return None

def _get_game(win):
    for name in ("game","_game","g","state"):
        obj = getattr(win, name, None)
        if obj is not None and hasattr(obj, "players"):
            return obj
    return None

def _log(win, msg):
    fn = getattr(win, "_log", None)
    if callable(fn):
        fn(msg)
    else:
        print(msg)

def attach_ports_bridge(win: QtWidgets.QWidget):
    """
    Copies UI-defined ports into core: win.game.ports = [...]
    So core can compute 3:1 / 2:1 rates.
    """
    if getattr(win, "_ports_bridge_attached", False):
        return
    win._ports_bridge_attached = True

    game = _get_game(win)
    if game is None:
        _log(win, "[!] Ports bridge: cannot find game on window.")
        return

    def _do():
        if getattr(game, "ports", None):
            return
        ports = _extract_ports(win)
        if not ports:
            _log(win, "[!] Ports bridge: UI ports not found (no list with kind/a/b).")
            return
        game.ports = ports
        _log(win, f"[SYS] Ports bridged to core: {len(ports)} ports.")

    # run a couple of times (UI may build scene after window init)
    QtCore.QTimer.singleShot(0, _do)
    QtCore.QTimer.singleShot(50, _do)
    QtCore.QTimer.singleShot(200, _do)