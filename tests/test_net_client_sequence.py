import json
from copy import deepcopy
from types import SimpleNamespace

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from app.net_client import NetClient
from app.engine import rules
from app.engine.serialize import to_player_dict
from app.online_controller import OnlineGameController
from app import ui_v6


def test_desktop_queue_consumed_rejections_reconnect_and_rematch():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    client = NetClient()
    sent = []
    client.send = sent.append

    def token(match_id, last):
        client._on_message(json.dumps({"type": "reconnect_token", "room_code": "ROOM",
            "reconnect_token": "secret", "pid": 0, "match_id": match_id,
            "last_seq_applied": last}))

    token(1, 0)
    cmd_id = client.send_cmd(1, 1, {"type": "place_settlement", "vid": 99999})
    client._on_message(json.dumps({"type": "cmd_ack", "cmd_id": cmd_id, "seq": 1,
                                  "last_seq_applied": 1, "applied": False}))
    assert not client._pending_cmds
    old = len(sent)
    token(1, 1)
    assert len(sent) == old
    pending_id = client.send_cmd(1, 2, {"type": "roll"})
    old = len(sent)
    token(1, 1)
    assert len(sent) == old + 1 and sent[-1]["cmd_id"] == pending_id
    token(1, 2)  # Lost ACK: the token prunes commands already consumed.
    assert not client._pending_cmds
    client.send_cmd(1, 3, {"type": "roll"})
    old = len(sent)
    token(2, 0)
    assert client.match_id == 2 and not client._pending_cmds
    assert client._last_seq_applied == 0 and len(sent) == old
    client._on_message(json.dumps({"type": "cmd_ack", "cmd_id": pending_id, "seq": 2,
                                  "last_seq_applied": 2, "applied": True}))
    assert client._last_seq_applied == 0
    application.processEvents()


def test_desktop_controller_preserves_reconnected_sequence_and_private_counts():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    net = NetClient()
    window = SimpleNamespace(set_online=lambda *_: None, _draw_static_board=lambda: None,
                             _refresh_all_dynamic=lambda: None, _sync_ui=lambda: None)
    controller = OnlineGameController(net, window, 0)
    net._on_message(json.dumps({"type": "reconnect_token", "room_code": "ROOM",
        "reconnect_token": "secret", "pid": 1, "match_id": 1, "last_seq_applied": 9}))
    g = rules.build_game(1, 2)
    g.players[0].res["wood"] = 4
    g.players[1].res["ore"] = 3
    view = to_player_dict(g, 1)
    view["you_pid"] = 1
    net._on_message(json.dumps({"type": "match_state", "room_code": "ROOM",
                               "match_id": 1, "tick": 0, "state": view}))
    assert controller.seq == 9 and controller.you_pid == window.you_pid == 1
    assert window.game.players[0].resource_count == 4
    assert all(q == 0 for q in window.game.players[0].res.values())
    assert window.game.players[1].res["ore"] == 3
    net._on_message(json.dumps({"type": "reconnect_token", "room_code": "ROOM",
        "reconnect_token": "secret", "pid": 1, "match_id": 2, "last_seq_applied": 0}))
    net._on_message(json.dumps({"type": "match_state", "room_code": "ROOM",
                               "match_id": 2, "tick": 0, "state": view}))
    assert controller.seq == 0
    controller.seq = 20
    net._on_message(json.dumps({"type": "reconnect_token", "room_code": "OTHER",
        "reconnect_token": "other", "pid": 1, "match_id": 2, "last_seq_applied": 0}))
    net._on_message(json.dumps({"type": "match_state", "room_code": "OTHER",
                               "match_id": 2, "tick": 1, "state": view}))
    assert controller.seq == 0
    stale = deepcopy(view)
    stale["players"][1]["res"]["ore"] = 99
    net._on_message(json.dumps({"type": "match_state", "room_code": "OTHER",
                               "match_id": 2, "tick": 0, "state": stale}))
    assert window.game.players[1].res["ore"] == 3
    application.processEvents()


def test_shared_monopoly_helper_accepts_desktop_player_model():
    g = ui_v6.build_board(seed=1, size=58.0)
    g.phase, g.turn, g.rolled = "main", 0, True
    g.players[0].dev_cards = [{"type": "monopoly", "new": False}]
    rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"wood": 3}})
    before = deepcopy(g)
    try:
        g.play_dev(0, "monopoly", r="invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid Monopoly should be rejected")
    assert g == before
    g.play_dev(0, "monopoly", r="wood")
    assert g.players[0].res["wood"] == 3 and g.players[1].res["wood"] == 0
