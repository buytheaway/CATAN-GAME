# Game UI Phase 2 / Game UX 2.1 browser checks

The runner uses installed Chrome through Playwright and real production web/backend
Docker images. Playwright is a test runner only: install it outside the repository
or provide it through `NODE_PATH`. It is not a frontend runtime dependency.

```powershell
docker compose build
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait
# Example if Playwright is already installed in a separate tool directory:
$env:NODE_PATH = '<tool directory>/node_modules'
node web/e2e/game-actions.cjs
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml down
```

The isolated stack binds only `127.0.0.1:18080`; it does not restart production
containers or modify their rooms. Output defaults to the OS temporary directory
`catan-game-ux-2-1`. Override with `CATAN_E2E_OUTPUT`. Set `CATAN_E2E_CASE`
to a mode such as `direct`, `dice` or `gold` for an individual regression check;
omit it to run all 17 cases.

`fixture_server.py` prepares funded hands, old cards, port ownership and near-win
scores **only in the test container**, for the first match of `fixture-*` rooms.
Setup placements use the existing engine. Rematch is completely unmodified.
The test backend injects a deterministic dice function for reliable progression.
No production initializer, debug command or snapshot interception is added.

Every UI action travels through nginx, the real WebSocket endpoint, ownership,
command sequences, the normal executor and player-specific serialization. The
initializer also compares the complete GameState and public dice metadata before/after
every rejected command. Native-WebSocket fault injection deliberately corrupts selected commands
to exercise error recovery without bypassing the client's sequence bookkeeping.
Read-only DevTools observation projects actual Three objects for real mouse clicks.

Coverage includes bank ratios 4/3/2, rejected bank trade, targeted/broadcast offers,
accept/reject/cancel/end-turn expiration, purchase and aging, all five dev card
types, before-roll play, new-card and one-card limits, two free-road placements,
Year of Plenty with insufficient hidden bank quantity and corrected retry,
Monopoly transfers, opponent privacy, passive VP, winning VP purchase, final-score
reveal, post-game rejection, ordinary and disconnected-host rematch, lost-rematch
connection/retry, token/pid/
sequence reset, explicit exit/rejoin, unprepared setup/roll, 2D/3D parity and layout.

Game UX 2.1 adapts all existing cases to the direct dock/private card hand and
resource-hand Trade Tray. Additional cases cover paid Road/Settlement/City, local
Give/Want add/remove without balance mutations, cost preview, exact/repeated
server 4+5 faces, finite dice animation/idle/reduced motion/refresh, public-only
bank availability, and Gold Haven lobby selection/Ship/build/move/pirate. Actual
scene projections check port endpoint IDs, geometry framing and HUD occlusion at
1920×1080, 1440×900 and 1280×720. Screenshots and measurements go to the output
directory; no production snapshot interception or gameplay results are fabricated.

Prepared states are fixtures, not a claimed naturally played full match. Exact
bank/deck contents and engine event logs are absent from the normal public view;
the UI keeps server authority for facts it cannot know.
