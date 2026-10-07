// Real Chrome + existing HTTP/WS server. Playwright is supplied by the external E2E runner.
// CATAN_E2E_DIST=1 serves the built UI to this browser only, without restarting nginx/backend.
// Only the explicit outage case intercepts an API response; normal auth/rooms/recovery are real.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const origin = process.env.CATAN_E2E_ORIGIN || 'http://localhost';
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-product-shell-phase-1');
const dist = path.resolve(__dirname, '../dist');
const clients = [], checks = [], screenshots = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(predicate, label) {
  const until = Date.now() + 15000;
  while (!predicate()) { if (Date.now() > until) throw Error('Timeout: ' + label); await sleep(40); }
}
async function newClient(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  // Fulfilled static documents have no remote address; Chrome's local-network permission
  // is explicit for this isolated test origin. The actual API/WS server is still used.
  if (process.env.CATAN_E2E_DIST === '1') await context.grantPermissions(['local-network-access'], { origin });
  if (process.env.CATAN_E2E_DIST === '1') await context.route(`${origin}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== '/' && !pathname.startsWith('/assets/')) return route.continue();
    const file = path.resolve(dist, pathname === '/' ? 'index.html' : '.' + pathname);
    if (path.relative(dist, file).startsWith('..')) return route.abort();
    const mime = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    await route.fulfill({ body: await fs.readFile(file), contentType: mime });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const c = { context, page, room: null, match: null, jsErrors: [], consoleErrors: [], authPosts: 0, frames: [], wsErrors: [] };
  clients.push(c);
  page.on('pageerror', e => c.jsErrors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().startsWith('Failed to load resource:')) c.consoleErrors.push(m.text()); });
  page.on('request', request => { if (request.method() === 'POST' && /\/api\/auth\/(register|login)$/.test(request.url())) c.authPosts++; });
  page.on('websocket', socket => {
    socket.on('socketerror', e => c.wsErrors.push(String(e)));
    socket.on('framereceived', ({ payload }) => {
    const m = JSON.parse(String(payload));
    c.frames.push(m.type);
    if (m.type === 'room_state') c.room = m;
    if (m.type === 'match_state') c.match = m;
    if (m.type === 'chat_state' && c.room) c.room.chat_history = m.chat_history;
    });
  });
  await page.goto(origin, { waitUntil: 'networkidle' });
  if (name) await page.getByLabel('Name', { exact: true }).fill(name);
  return c;
}
async function shot(c, name) {
  await c.page.screenshot({ path: path.join(output, name + '.png'), fullPage: true }); screenshots.push(name);
}
async function fit(c) {
  const size = await c.page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
    inputs: [...document.querySelectorAll('.app-shell input:not([type=file])')].filter(el => el.offsetWidth).map(el => el.getBoundingClientRect().width) }));
  assert(size.scroll <= size.width + 1, `horizontal overflow ${size.scroll}/${size.width}`);
  assert(size.inputs.every(width => width <= 580), 'unnecessarily wide form');
}
async function host(c, count = 4) {
  c.room = null;
  await c.page.getByLabel('Max players').fill(String(count));
  await c.page.getByRole('button', { name: 'Host', exact: true }).click();
  await wait(() => c.room, 'Host room');
  await c.page.getByRole('heading', { name: 'Room ' + c.room.room_code, exact: true }).waitFor();
  return c.room.room_code;
}
async function join(c, code) {
  c.room = null;
  await c.page.getByLabel('Room code', { exact: true }).fill(code.toLowerCase());
  await c.page.getByRole('button', { name: 'Join', exact: true }).click();
  await wait(() => c.room?.room_code === code, 'Join room');
  await c.page.getByRole('heading', { name: 'Room ' + code, exact: true }).waitFor();
}
async function home(c) {
  await c.page.getByRole('button', { name: 'Back to home', exact: true }).click();
  await c.page.getByRole('heading', { name: 'Good company. A new frontier.' }).waitFor();
  await c.page.waitForFunction(() => !document.querySelector('.recent-games[aria-busy=true],.account-games[aria-busy=true]'));
}
function card(c, code) { return c.page.locator('.recent-game').filter({ hasText: 'Room ' + code }); }

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const a = await newClient(browser, 'Captain'), b = await newClient(browser, 'Navigator');
    await fit(a); await shot(a, 'home-signed-out-1920');
    await a.page.getByLabel('Max players').focus(); await shot(a, 'host-configuration-1920');
    await b.page.getByLabel('Room code').fill('9XX7UQ'); await b.page.getByLabel('Room code').focus(); await shot(b, 'join-configuration-1920');
    checks.push('Signed-out Home, independent Host/Join and zero-game state');

    const first = await host(a);
    assert(await a.page.getByRole('button', { name: 'Start Match', exact: true }).isDisabled());
    await join(b, first);
    await wait(() => a.room.players.filter(p => p.name && p.connected).length === 2, 'two players');
    assert.equal(await a.page.locator('.lobby-player').count(), 4);
    assert.equal(await a.page.locator('.lobby-player.is-empty').count(), 2);
    assert(!(await a.page.getByRole('button', { name: 'Start Match', exact: true }).isDisabled()));
    assert(await b.page.getByRole('button', { name: 'Start Match', exact: true }).isDisabled());
    for (const label of ['Map preset', 'Dice mode', 'Turn timer', 'Target VP', 'Starting player', 'Bank resource counts', 'Discard threshold'])
      assert(await b.page.getByLabel(label, { exact: true }).isDisabled(), label + ' must be host-only');
    await a.page.getByText('Custom map', { exact: true }).click();
    const custom = JSON.parse(await fs.readFile(path.resolve(__dirname, '../../app/assets/maps/base_standard.json'), 'utf8'));
    custom.id = 'ux_imported_base'; custom.name = 'UX Imported Island';
    await a.page.getByLabel('Custom map (JSON)', { exact: true }).setInputFiles({ name: 'island.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(custom)) });
    await wait(() => b.room.map_meta?.name === 'UX Imported Island', 'custom map');
    const revision = a.room.map_revision;
    await a.page.getByLabel('Custom map (JSON)', { exact: true }).setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{invalid') });
    await a.page.getByText('Custom map: invalid JSON', { exact: true }).waitFor();
    assert.equal(a.room.map_revision, revision);
    await a.page.getByText('Custom map', { exact: true }).click();
    await a.page.getByLabel('Map preset', { exact: true }).selectOption('seafarers_gold_haven');
    await wait(() => a.room.map_id === 'seafarers_gold_haven' && b.room.map_id === 'seafarers_gold_haven', 'confirmed map');
    await a.page.getByLabel('Dice mode', { exact: true }).selectOption('balanced');
    await a.page.getByLabel('Target VP', { exact: true }).selectOption('12');
    await wait(() => b.room.settings?.dice_mode === 'balanced' && b.room.settings?.target_vp === 12, 'settings confirmation');
    await a.page.getByRole('button', { name: 'Choose white', exact: true }).click();
    await wait(() => b.room.players.find(p => p.name === 'Captain')?.color === 'white', 'color confirmation');
    assert(await b.page.getByRole('button', { name: 'Choose white', exact: true }).isDisabled());
    await b.page.getByLabel('Chat message', { exact: true }).fill('See you on the island.');
    await b.page.getByRole('button', { name: 'Send', exact: true }).click();
    await a.page.getByText('See you on the island.', { exact: true }).waitFor();
    await fit(a); await fit(b); await shot(a, 'room-host-two-players-1920'); await shot(b, 'room-participant-1920');
    checks.push('Four-slot room/two players, host permissions, confirmed map/settings/color and real chat');

    await a.page.reload({ waitUntil: 'networkidle' });
    await a.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    assert.equal(await a.page.getByLabel('Map preset', { exact: true }).inputValue(), 'seafarers_gold_haven');
    await home(a); assert.equal(await a.page.locator('.recent-game').count(), 1); await shot(a, 'home-one-recent-1920');
    await card(a, first).getByRole('button', { name: 'Continue', exact: true }).click();
    await a.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    await home(a); const second = await host(a, 2); assert.notEqual(first, second);
    await home(a); assert.equal(await a.page.locator('.recent-game').count(), 2); await shot(a, 'home-recent-1920');
    const saved = await a.page.evaluate(() => localStorage.getItem('catan_recent_games'));
    await a.context.route('**/api/reconnect/inspect-many', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await a.page.getByRole('button', { name: 'Check again', exact: true }).click();
    await a.page.getByText('Temporarily unavailable', { exact: true }).first().waitFor();
    assert.equal(await a.page.evaluate(() => localStorage.getItem('catan_recent_games')), saved);
    assert(await card(a, first).getByRole('button', { name: 'Continue', exact: true }).isDisabled()); await shot(a, 'home-unavailable-1920');
    await a.context.unroute('**/api/reconnect/inspect-many');
    await a.page.getByRole('button', { name: 'Check again', exact: true }).click();
    await a.page.waitForFunction(() => document.querySelectorAll('.recent-game .btn.primary:not(:disabled)').length === 2);
    await a.page.evaluate(() => {
      const saved = JSON.parse(localStorage.getItem('catan_recent_games'));
      saved.entries.push({ room_code: 'ZZZZZZ', reconnect_token: 'invalid-e2e-proof', last_known_name: 'Expired', last_seen_at: Date.now() });
      localStorage.setItem('catan_recent_games', JSON.stringify(saved));
    });
    await a.page.getByRole('button', { name: 'Check again', exact: true }).click();
    await a.page.waitForFunction(() => !JSON.parse(localStorage.getItem('catan_recent_games')).entries.some(entry => entry.room_code === 'ZZZZZZ'));
    assert.equal(await a.page.locator('.recent-game').count(), 2);
    for (const width of [1440, 1280, 900, 768, 480]) { await a.page.setViewportSize({ width, height: 900 }); await fit(a); }
    await a.page.setViewportSize({ width: 900, height: 900 }); await shot(a, 'home-narrow-900');
    await a.page.setViewportSize({ width: 1920, height: 1080 });
    await card(a, first).getByRole('button', { name: 'Continue', exact: true }).click();
    await a.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    await a.page.setViewportSize({ width: 900, height: 900 }); await fit(a); await shot(a, 'room-narrow-900');
    await a.page.setViewportSize({ width: 1920, height: 1080 });
    checks.push('Custom JSON/invalid JSON; refresh, guest Continue, one/multiple games, confirmed invalid cleanup, temporary outage preserves proofs, responsive 1440/1280/900/768/480');

    const account = await newClient(browser);
    await account.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await account.page.getByRole('heading', { name: 'Sign In', exact: true }).waitFor();
    await account.page.getByRole('dialog').waitFor(); await shot(account, 'login-1920');
    assert.equal(await account.page.getByLabel('Username', { exact: true }).getAttribute('aria-describedby'), 'auth-username-help');
    await account.page.getByRole('button', { name: 'Close account' }).focus(); await account.page.keyboard.press('Shift+Tab');
    assert.equal(await account.page.evaluate(() => document.activeElement.textContent), 'Create account');
    await account.page.keyboard.press('Tab'); assert.equal(await account.page.evaluate(() => document.activeElement.getAttribute('aria-label')), 'Close account');
    await account.page.keyboard.press('Escape'); assert(await account.page.getByRole('button', { name: 'Sign In', exact: true }).evaluate(el => el === document.activeElement));
    await account.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await account.page.getByRole('heading', { name: 'Sign In', exact: true }).waitFor();
    await account.page.getByLabel('Username', { exact: true }).fill('captain@example.com');
    await account.page.getByLabel('Password', { exact: true }).fill('short');
    const before = account.authPosts;
    await account.page.getByRole('button', { name: 'Login', exact: true }).click();
    assert.equal(account.authPosts, before); assert.equal(await account.page.locator('input[aria-invalid=true]').count(), 2);
    await shot(account, 'auth-validation-1920');
    await account.page.getByRole('button', { name: 'Create account', exact: true }).click();
    const username = 'ux_' + Date.now().toString(36), password = '  Compass 🌊 horizon  ';
    await account.page.getByLabel('Username', { exact: true }).fill(username);
    await account.page.getByLabel('Display name', { exact: true }).fill('Капитан UX');
    await account.page.getByLabel('Password', { exact: true }).fill(password);
    assert.equal(await account.page.getByLabel('Display name', { exact: true }).getAttribute('maxlength'), null);
    assert.equal(await account.page.getByLabel('Password', { exact: true }).getAttribute('maxlength'), null);
    await shot(account, 'registration-1920');
    await account.page.getByRole('button', { name: 'Register', exact: true }).click();
    await account.page.getByRole('button', { name: 'Капитан UX', exact: true }).waitFor();
    assert(await account.page.getByLabel('Name', { exact: true }).evaluate(el => el.readOnly));
    await join(account, first);
    await home(account); await account.page.locator('.account-games .recent-game').waitFor(); await shot(account, 'home-account-1920');
    await card(account, first).getByRole('button', { name: 'Continue', exact: true }).click();
    await account.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    await account.page.getByRole('button', { name: 'Капитан UX', exact: true }).click();
    await account.page.getByRole('button', { name: 'Logout', exact: true }).click();
    await account.page.getByRole('button', { name: 'Sign In', exact: true }).waitFor();
    await account.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await account.page.getByLabel('Username', { exact: true }).fill(username.toUpperCase());
    await account.page.getByLabel('Password', { exact: true }).fill('valid but wrong password');
    await account.context.route('**/api/auth/login', async route => { await sleep(250); await route.continue(); });
    await account.page.getByRole('button', { name: 'Login', exact: true }).click();
    await account.page.getByRole('dialog').filter({ has: account.page.getByRole('button', { name: 'Please wait…', exact: true }) }).waitFor();
    await account.page.keyboard.press('Tab');
    assert(await account.page.getByRole('dialog').evaluate(el => el === document.activeElement || el.contains(document.activeElement)));
    await account.page.getByRole('alert').filter({ hasText: 'Username or password is incorrect.' }).waitFor();
    await account.context.unroute('**/api/auth/login');
    await account.page.getByLabel('Password', { exact: true }).fill(password);
    await account.page.getByRole('button', { name: 'Login', exact: true }).click();
    await account.page.getByRole('button', { name: 'Капитан UX', exact: true }).waitFor();
    await card(account, first).getByRole('button', { name: 'Continue', exact: true }).click();
    await account.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    await account.page.reload({ waitUntil: 'networkidle' });
    await account.page.getByRole('heading', { name: 'Room ' + first, exact: true }).waitFor();
    checks.push('Real register/Unicode display name/Login/Logout/account Continue+refresh; inline email/password errors; modal keyboard trap/restore');

    await a.page.getByRole('button', { name: 'Start Match', exact: true }).click();
    await wait(() => a.match && b.match && account.match, 'match from confirmed configuration');
    assert.equal(a.match.state.map_meta.name, 'Seafarers: Gold Haven');
    assert.equal(a.match.state.rules_config.target_vp, 12);
    assert.equal(await a.page.locator('.app-shell').count(), 0);
    assert.equal(await a.page.locator('.app--match').count(), 1);
    await a.page.getByRole('button', { name: '2D', exact: true }).waitFor();
    checks.push('Start uses confirmed Gold Haven/12 VP; original match branch and renderer controls remain');
    for (const c of clients) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.consoleErrors, []); }
    const report = { checks, screenshots, origin, frontend: process.env.CATAN_E2E_DIST === '1' ? 'production dist via browser-only static routing' : 'server frontend',
      backend: 'real existing server; one isolated test account and two guest rooms', jsErrors: 0 };
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } catch (e) {
    console.error(JSON.stringify(clients.map(c => ({ frames: c.frames, wsErrors: c.wsErrors, jsErrors: c.jsErrors, consoleErrors: c.consoleErrors }))));
    for (let i = 0; i < clients.length; i++) await shot(clients[i], 'failure-' + i).catch(() => {});
    throw e;
  } finally { await browser.close(); }
})().catch(e => { console.error(e.stack); process.exitCode = 1; });
