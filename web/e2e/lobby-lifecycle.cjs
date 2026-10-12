// Real Chrome/Nginx acceptance on an isolated localhost test stack. No game fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18094';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-lobby-lifecycle');
const h = require('./game-actions.cjs');
const origin = process.env.CATAN_E2E_ORIGIN;
assert(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(origin).hostname), 'Localhost only');
const checks = [];
function check(label) { checks.push(label); console.log('PASS ' + label); }
async function host(c) {
  c.room = null;
  await c.page.getByLabel('Max players').fill('2');
  await c.page.getByRole('button', { name: 'Host', exact: true }).click();
  await h.wait(() => c.room, 'Host');
  await c.page.getByRole('button', { name: 'Close Lobby', exact: true }).waitFor();
  return c.room.room_code;
}
async function join(c, code) {
  c.room = null;
  await c.page.getByLabel('Room code').fill(code);
  await c.page.getByRole('button', { name: 'Join', exact: true }).click();
  await h.wait(() => c.room?.room_code === code, 'Join / reconnect');
}
async function close(c, accept) {
  const dialog = c.page.waitForEvent('dialog');
  const click = c.page.getByRole('button', { name: 'Close Lobby', exact: true }).click();
  const confirmation = await dialog;
  assert.equal(confirmation.type(), 'confirm');
  assert.match(confirmation.message(), /cannot be reconnected/);
  if (accept) await confirmation.accept(); else await confirmation.dismiss();
  await click;
}
async function closed(c, code) {
  await c.page.getByRole('status').filter({ hasText: `Lobby ${code} was closed by its host` }).waitFor();
  assert.equal(await c.page.getByRole('button', { name: 'Start Match', exact: true }).count(), 0);
  assert.equal(await c.page.locator('.recent-game').filter({ hasText: code }).count(), 0);
  assert.equal(await c.page.getByRole('button', { name: 'Host', exact: true }).count(), 1);
}
async function raw(c, payload) {
  await c.page.evaluate(message => {
    const socket = window.__sockets.findLast(s => s.readyState === WebSocket.OPEN);
    if (!socket) throw Error('No controlling socket');
    socket.send(JSON.stringify(message));
  }, payload);
}
async function register(c) {
  await c.page.locator('.auth-launch').click();
  const dialog = c.page.getByRole('dialog');
  // Exercise ordinary keyboard activation; auth UI itself is outside this phase.
  await dialog.getByRole('button', { name: 'Create account', exact: true }).focus();
  await c.page.keyboard.press('Enter');
  await dialog.getByRole('heading', { name: 'Create account', exact: true }).waitFor();
  await dialog.getByLabel('Username', { exact: true }).fill('lifecycle_' + Date.now().toString(36));
  await dialog.getByLabel('Display name', { exact: true }).fill('Lifecycle Account');
  await dialog.getByLabel('Password', { exact: true }).fill('synthetic lifecycle test password');
  await dialog.getByRole('button', { name: 'Register', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
}
async function main() {
  const output = process.env.CATAN_E2E_OUTPUT;
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const clients = [];
  try {
    const a = await h.newClient(browser, 'Lifecycle Host'); clients.push(a);
    const b = await h.newClient(browser, 'Lifecycle Guest'); clients.push(b);
    const first = await host(a);
    await join(b, first);
    await h.wait(() => a.room.players[1].connected, 'participant connected');
    assert.equal(await b.page.getByRole('button', { name: 'Close Lobby', exact: true }).count(), 0);
    await raw(b, { type: 'close_room', room_code: first, request_id: 'participant-close', expected_match_id: 0 });
    await h.wait(() => b.errors.some(e => e.detail?.request_id === 'participant-close'), 'participant refused');
    assert.equal(b.errors.at(-1).code, 'forbidden');
    await close(a, false);
    assert.equal(await a.page.getByRole('button', { name: 'Close Lobby', exact: true }).isEnabled(), true);
    assert.equal(a.room.room_code, first);
    check('Non-host cannot close; cancelling host confirmation preserves the lobby');

    await a.page.getByRole('button', { name: 'Back to home', exact: true }).click();
    await h.wait(() => !b.room.players[0].connected, 'host disconnected');
    const card = a.page.locator('.recent-game').filter({ hasText: first });
    await card.getByRole('button', { name: 'Continue', exact: true }).waitFor();
    a.room = null;
    await card.getByRole('button', { name: 'Continue', exact: true }).click();
    // Existing reconnect publishes the recovered room to the reconnecting client;
    // it does not broadcast a presence refresh to the other socket here.
    await h.wait(() => a.room?.room_code === first && a.room.players[0].connected, 'guest host Continue');
    assert.equal(await a.page.getByRole('button', { name: 'Close Lobby', exact: true }).isEnabled(), true);
    check('Back to home disconnects without closure; guest Continue retains ownership');

    await close(a, true);
    await Promise.all([closed(a, first), closed(b, first)]);
    await a.page.screenshot({ path: path.join(output, 'guest-lobby-closed.png') });
    await b.page.reload({ waitUntil: 'networkidle' });
    assert.equal(await b.page.locator('.recent-game').filter({ hasText: first }).count(), 0);
    await b.page.getByLabel('Name', { exact: true }).fill(b.name);
    await b.page.getByLabel('Room code').fill(first);
    await b.page.getByRole('button', { name: 'Join', exact: true }).click();
    await b.page.getByRole('alert').filter({ hasText: 'Room not found' }).waitFor();
    check('Host closure notifies both clients, removes guest Continue, and refuses closed-room Join after refresh');

    const active = await host(a);
    await join(b, active);
    await h.wait(() => a.room.players[1].connected, 'new lobby participant');
    await a.page.getByRole('button', { name: 'Start Match', exact: true }).click();
    await h.wait(() => a.match && b.match, 'Base start');
    await a.page.locator('.game-shell').waitFor();
    assert.equal(await a.page.getByRole('button', { name: 'Close Lobby', exact: true }).count(), 0);
    const before = a.match.tick;
    await raw(a, { type: 'close_room', room_code: active, request_id: 'active-close', expected_match_id: 0 });
    await h.wait(() => a.errors.some(e => e.detail?.request_id === 'active-close'), 'active closure refused');
    assert.equal(a.errors.at(-1).code, 'invalid');
    assert.equal(a.match.tick, before);
    assert.equal(a.match.state.phase, 'setup');
    check('New Base match still starts; active match has no Close Lobby control and rejects raw closure');

    const account = await h.newClient(browser, 'Before account'); clients.push(account);
    await register(account);
    const accountCode = await host(account);
    await close(account, true);
    await closed(account, accountCode);
    const status = await account.page.evaluate(async () => {
      const active = await fetch('/api/games/active');
      return { status: active.status, games: (await active.json()).games };
    });
    assert.equal(status.status, 200);
    assert(!status.games.some(g => g.room_code === accountCode));
    assert.equal(await account.page.locator('.account-games .recent-game').filter({ hasText: accountCode }).count(), 0);
    const next = await host(account);
    assert.notEqual(next, accountCode);
    await close(account, true);
    await closed(account, next);
    check('Account closure removes Active Games without logout; same session can create and close a fresh lobby');
    for (const c of clients) assert.deepEqual(c.jsErrors, []);
    check('All real browser clients remain free of JavaScript runtime errors');
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ origin, chrome: browser.version(), checks }, null, 2));
  } finally {
    for (const c of clients) await c.context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
