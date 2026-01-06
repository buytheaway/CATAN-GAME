# Hacks Report (Reachable Files)

## QTimer.singleShot

- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\dev_hand_overlay.py:225: QtCore.QTimer.singleShot(50, self._reposition)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\dev_hand_overlay.py:229: QtCore.QTimer.singleShot(0, self._reposition)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_v6.py:1577: QtCore.QTimer.singleShot(30, self._fit_map)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_v6.py:1589: QtCore.QTimer.singleShot(0, self._fit_map)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_v6.py:1947: QtCore.QTimer.singleShot(30, self._fit_map)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_tweaks.py:86: QtCore.QTimer.singleShot(50, _go)
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_tweaks.py:87: QtCore.QTimer.singleShot(250, _go)

## monkey_patch_Game

- none

## runtime_patch_import

- none

## ports_bridge_import

- none

## findChild

- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\dev_ui.py:177: dev_btn = win.findChild(QtWidgets.QAbstractButton, "btn_dev_action")
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\trade_ui.py:151: dev_btn = win.findChild(QtWidgets.QAbstractButton, "btn_dev_action")
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\trade_ui.py:168: trade_btn = win.findChild(QtWidgets.QAbstractButton, "btn_trade_bank")

## objectName

- none

## text_search

- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_v6.py:2441: txt = self.chat_in.text().strip()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\ui_tweaks.py:33: t = (b.text() or "").strip().lower()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\dev_ui.py:134: t = it.text().split()[0].strip()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\dev_ui.py:180: if (b.text() or "").strip().lower() == "dev":
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:98: name = self.ed_name.text().strip() or "Player"
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:99: url = self.ed_url.text().strip()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:104: name = self.ed_name.text().strip() or "Player"
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:105: url = self.ed_url.text().strip()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:106: room = self.ed_room.text().strip().upper()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\lobby_ui.py:124: name = self.ed_name.text().strip()
- C:\Users\mukha\OneDrive\Documents\GitHub\CATAN-GAME\app\trade_ui.py:154: t = (b.text() or "").strip().lower()

