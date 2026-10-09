# Game UI / Game Room UX browser checks

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
`catan-game-ux-2-2`. Override with `CATAN_E2E_OUTPUT`. Set `CATAN_E2E_CASE`
to a mode such as `direct`, `dice`, `gold`, `roomux` or `roomuxhidden` for an
individual regression check; omit it to run all 19 cases.

`fixture_server.py` prepares funded hands, old cards, port ownership and near-win
scores **only in the test container**, for the first match of `fixture-*` rooms.
Setup placements use the existing engine. Rematch is completely unmodified.
The test backend injects a deterministic Random dice function for reliable progression.
Balanced room cases use the real secure production bag algorithm. The 17 previous
cases explicitly choose Host/Hidden/Off so their original gameplay/privacy
assertions do not depend on the new Random starter/Visible bank defaults.
No production fixture initializer or snapshot interception is added. UX 2.3 separately adds explicitly gated production Test Room commands, off by default.

Every UI action travels through nginx, the real WebSocket endpoint, ownership,
command sequences, the normal executor and player-specific serialization. The
initializer also compares the complete GameState and public dice metadata before/after
every rejected command. Native-WebSocket fault injection deliberately corrupts selected commands
to exercise error recovery without bypassing the client's sequence bookkeeping.
Read-only DevTools observation projects actual Three objects for real mouse clicks.

Coverage includes bank ratios 4/3/2, rejected bank trade, broadcast offers (old targeted server path is retained),
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

Game / Room UX 2.2 adds two-client `roomux` (Random starter/Visible bank) and
`roomuxhidden` (Host/Hidden bank), both with Balanced dice, 60s timer and 12 VP.
They verify host/read-only settings, occupied colors, actual white/orange Three
materials, initial starter, four accepted rolls and exact shared pairs/sums,
decreasing HUD countdown, lobby/game plain-text chat and a separate log tab,
visible/collapsible bank policy, retained token/color/deadline/chat on refresh and rematch
with retained settings/colors, reset dice/timer/match/sequence and first seq=1.
Rematch is an existing server-permitted request, not a fixture-created win.
Automatic timer expiry/grace/mandatory branches are covered by controlled-clock
Python tests; this runner does not claim a long real-time expiry run.

Prepared states are fixtures, not a claimed naturally played full match. Hidden
bank counts and all deck contents/count/order remain absent; Visible intentionally
publishes exact bank counts. UX 2.3 now has a bounded recipient-filtered committed gameplay feed. Screenshots and
state observation describe actual server execution; full natural games,
mobile/low-end/load and desktop-client feature parity are not certified here.

## Game UX 2.3 feedback checks

`playtest-feedback.cjs` adds eight real Chrome/WS cases. Use an explicit external
output directory to keep screenshots/reports outside the working tree:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-game-ux-2-3/after'
$env:CATAN_ENABLE_TEST_TOOLS = '0'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
$env:CATAN_TEST_MODE_CHECK = 'off'
node web/e2e/playtest-feedback.cjs
$env:CATAN_ENABLE_TEST_TOOLS = '1'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
$env:CATAN_TEST_MODE_CHECK = 'on'
node web/e2e/playtest-feedback.cjs
# Restore OFF for ordinary-room regression checks.
$env:CATAN_ENABLE_TEST_TOOLS = '0'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
node web/e2e/game-actions.cjs
```

ON does not enable cheats in normal rooms. The host explicitly enables a Test
Room in lobby, then named actions still require active host ownership and the
normal command sequence. Cases check OFF/normal-room/participant denial,
resource give/remove, specific dev draw, one-shot dice, near-win/final VP,
invalid-source atomic retry, production flights, three-client theft privacy,
card discard with custom threshold and rejected retry, threshold equality,
and a shifted 50-hex custom JSON visual fixture. The fixture is local test data,
not a new preset or generator. Snapshots/feed/real animations are observed;
no resources are fabricated by client animation or inferred theft deltas.

Existing 19 cases are updated for direct Knight/Road Building, broadcast-only
tray, visible Bank and longer finite dice. Base/Gold/50 framing is measured at
1920/1440/1280; finite motion returns to 0 idle frames. 2D unmount checks Three
resource cleanup. Reports may contain test command payloads; committed evidence
is sanitized in docs/design/references/game-ux-2-3/verification.json, without
reconnect tokens, hidden decks or raw personal snapshots. No full natural match,
mobile or low-end/load certification is implied.

## Seafarers S2A maps / real multiplayer

`seafarers-s2a.cjs` runs the ordinary two-client lobby/setup flow on Gold Haven
and Pirate Lanes against the actual FastAPI/WS/PostgreSQL application and built
production frontend. It explicitly uses host Test Tools for deterministic dice,
matured Knight and expansion funding. It does not manufacture map/state snapshots
or claim a naturally played full match. No production database is needed.

Use an isolated disposable PostgreSQL database whose name ends in `_test`, with
`DATABASE_URL` already configured for that database. Apply the current migrations
only to that test database, build the frontend, then start the local test server:

```powershell
# In web/: npm run build; at repository root with the test DATABASE_URL:
.venv/Scripts/python.exe -B -m alembic upgrade head
$env:CATAN_PERSISTENCE_MODE = 'durable'
$env:CATAN_AUTH_MODE = 'development'
$env:CATAN_AUTH_ORIGINS = 'http://127.0.0.1:18766'
$env:CATAN_ENABLE_TEST_TOOLS = '1'
.venv/Scripts/python.exe -B -m web.e2e.seafarers_s2a_server
```

The test launcher refuses a non-test database, mounts `web/dist`, listens on
loopback only and selects psycopg's supported event loop on Windows. It adds no
gameplay endpoints or fixtures. In another terminal, use an available external
Playwright installation and Chrome, keeping output outside the repository:

```powershell
# If Playwright is installed externally, set NODE_PATH to its node_modules.
$env:CATAN_E2E_ORIGIN = 'http://127.0.0.1:18766'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-s2a-hardening/browser'
node web/e2e/seafarers-s2a.cjs
```

Checks include setup ships/Gold, paid island crossing/settlement/city/road, an
invalid coordinate rejection, real pirate and Seven/discard/robber actions,
personalized privacy, 37 terrain GLBs/number tokens/ports/ownership IDs, SVG/3D,
1920/1440/1280 framing, orbit/zoom/reset and durable guest refresh. Camera checks
wait for the actual React reset effect. Summary/screenshots contain geometry and
counts, without reconnect proofs or dumped private hands. Stop only the local
test server/container you started after verification; leave other services alone.
