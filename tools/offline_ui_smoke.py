from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CATAN_TEST_MODE", "ui_full_init")

from PySide6 import QtWidgets

from app import ui_v6
from app.config import GameConfig
from app.dev_ui import DevDialog
from app.trade_ui import TradeDialog
from app.engine import rules as engine_rules


class NonModalDevDialog(DevDialog):
    def open_nonmodal(self):
        self.show()
        QtWidgets.QApplication.processEvents()
        self.close()


class NonModalTradeDialog(TradeDialog):
    def open_nonmodal(self):
        self.show()
        QtWidgets.QApplication.processEvents()
        self.close()


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cfg = GameConfig()
    win = ui_v6.MainWindow(cfg, dev_dialog_factory=NonModalDevDialog, trade_dialog_factory=NonModalTradeDialog)
    win.show()
    app.processEvents()

    # Start new game via real handler
    win._restart_game()
    app.processEvents()

    # Move to main phase for smoke actions
    g = win.game
    g.phase = "main"
    g.turn = 0
    g.rolled = False

    # Open non-modal dialogs
    win._open_trade_dialog()
    win._open_dev_dialog()

    # Force a robber roll via test hook
    win._test_force_roll(7)
    if g.pending_action == "robber_move":
        target = 0 if g.robber_tile != 0 else 1
        win._on_hex_clicked(target)

    # Trigger win and show overlay
    g.players[0].vp = 10
    engine_rules.check_win(g)
    win._sync_ui()
    app.processEvents()

    shown = bool(getattr(win, "_shown_game_over", False))
    if not shown:
        raise RuntimeError("Victory overlay not shown")

    win.close()
    app.processEvents()
    print("PASS: offline UI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
