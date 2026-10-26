// Real Chrome -> Nginx -> authoritative WS -> disposable PostgreSQL.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18095';
const origin = process.env.CATAN_E2E_ORIGIN;
if (process.env.CATAN_OWNER_TEST_DISPOSABLE !== '1' || !['127.0.0.1', 'localhost'].includes(new URL(origin).hostname))
  throw Error('Use the explicitly disposable owner acceptance stack only');
const h = require('./game-actions.cjs');
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-owner-toggle-' + Date.now());
const checks = [], secret = 'correct horse battery staple';
const check = name => { checks.push(name); console.log('PASS ' + name); };
async function request(c, url, data) {
  return c.page.evaluate(async ({url, data}) => {
    const r = await fetch(url, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: data === undefined ? undefined : {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
    return {status: r.status, body: await r.json()};
  }, {url, data});
}
async function login(c, username = 'buytheaway', register = false) {
  await c.page.getByRole('button', {name: 'Sign In', exact: true}).click();
  const dialog = c.page.getByRole('dialog');
  // Avoid moving the mode button on blur of an intentionally empty username.
  await dialog.getByLabel('Username', {exact: true}).fill(username);
  if (register) await dialog.getByRole('button', {name: 'Create account', exact: true}).click();
  if (register) await dialog.getByLabel('Display name', {exact: true}).fill('buytheaway');
  await dialog.getByLabel('Password', {exact: true}).fill(secret);
  await dialog.getByRole('button', {name: register ? 'Register' : 'Login', exact: true}).click();
  await dialog.waitFor({state: 'hidden'});
}
async function toggle(c, enabled) {
  const control = c.page.getByRole('switch', {name: 'Owner Test Mode'});
  if (await control.getAttribute('aria-checked') !== String(enabled)) await control.click();
  await c.page.waitForFunction(value => document.querySelector('[role="switch"][aria-label="Owner Test Mode"]')?.getAttribute('aria-checked') === String(value), enabled);
  assert.equal((await request(c, '/api/auth/me')).body.user.owner_test_mode.enabled, enabled);
}
async function rawCommand(c, cmd) {
  return h.action([c], c, () => c.page.evaluate(cmd => {
    const state = window.__ownerMatch;
    window.__sockets.at(-1).send(JSON.stringify({type: 'cmd', room_code: state.room_code, match_id: state.match_id,
      cmd_id: crypto.randomUUID(), seq: window.__ownerSeq + 1, cmd}));
  }, cmd), 'raw privileged rejection', true);
}
async function main() {
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const clients = [];
  try {
    const a = await h.newClient(browser, 'Owner'); clients.push(a);
    assert.equal(await a.page.getByRole('switch', {name: 'Owner Test Mode'}).count(), 0);
    assert.equal((await request(a, '/api/auth/test-mode', {enabled: true})).status, 401);
    check('guest has no toggle and cannot write preference');
    const foreign = await h.newClient(browser, 'Foreign'); clients.push(foreign);
    await login(foreign, 'owner_other_' + Date.now().toString(36), true);
    assert.equal(await foreign.page.getByRole('switch', {name: 'Owner Test Mode'}).count(), 0);
    assert.equal((await request(foreign, '/api/auth/test-mode', {enabled: true})).status, 403);
    check('other account with owner display name has no permission');
    await login(a); await toggle(a, false); await toggle(a, true);
    await a.page.screenshot({path: path.join(output, 'owner-home-on.png'), fullPage: true});
    await a.page.reload({waitUntil: 'networkidle'});
    await a.page.getByRole('switch', {name: 'Owner Test Mode'}).waitFor();
    assert.equal(await a.page.getByRole('switch').getAttribute('aria-checked'), 'true');
    check('owner UI persists ON across refresh');
    await a.page.getByRole('button', {name: 'Owner UI fixture', exact: true}).click();
    await a.page.getByRole('button', {name: 'Logout', exact: true}).click();
    await login(a);
    assert.equal(await a.page.getByRole('switch').getAttribute('aria-checked'), 'true');
    check('logout/login preserves durable preference');
    await a.page.getByLabel('Max players').fill('2');
    await a.page.getByRole('button', {name: 'Host', exact: true}).click();
    await h.wait(() => a.room, 'owner host');
    const b = await h.newClient(browser, 'Guest opponent'); clients.push(b);
    await b.page.getByLabel('Room code').fill(a.room.room_code);
    await b.page.getByRole('button', {name: 'Join', exact: true}).click();
    await h.wait(() => b.room && a.room.players.filter(p => p.connected).length === 2, 'guest join');
    await a.page.getByLabel('Starting player').selectOption('host');
    await a.page.getByLabel('Bank resource counts').selectOption('hidden');
    await h.wait(() => a.room.settings.starting_player === 'host' && a.room.settings.bank_visibility === 'hidden', 'settings');
    await a.page.getByRole('button', {name: 'Enable Test Room', exact: true}).click();
    await h.wait(() => a.room.test_mode && b.room.test_mode, 'explicit test lobby');
    await a.page.screenshot({path: path.join(output, 'owner-test-lobby.png'), fullPage: true});
    await a.page.getByRole('button', {name: 'Start Match', exact: true}).click();
    await h.wait(() => a.match && b.match, 'authoritative match start');
    await a.page.locator('canvas').waitFor();
    while (a.match.state.phase === 'setup') {
      const current = [a,b][a.match.state.turn], s = current.match.state;
      await h.action([a,b], current, () => h.clickTarget(current, s.setup_need === 'settlement' ? 'vertex' : 'edge',
        s.setup_need === 'settlement' ? s.legal.settlements[0] : s.legal.roads[0]), 'legal setup');
    }
    assert.equal(a.match.state.test_tools, true); assert.equal(b.match.state.test_tools, false);
    check('existing test-room workflow and real Board3D setup work without server flag');
    await a.page.getByRole('button', {name: 'Test Tools', exact: true}).click();
    const tools = a.page.getByRole('dialog', {name: 'Test Tools', exact: true});
    await tools.getByLabel('Test player').selectOption('0');
    await tools.getByLabel('Test resource').selectOption('wood');
    await tools.getByLabel('Test amount').fill('1');
    const wood = a.match.state.players[0].res.wood;
    await h.action([a,b], a, () => tools.getByRole('button', {name: 'Give resources', exact: true}).click(), 'owner grant');
    assert.equal(a.match.state.players[0].res.wood, wood + 1);
    h.privacy([a,b]);
    await a.page.screenshot({path: path.join(output, 'owner-test-tools-on.png')});
    check('authenticated privileged WS action and opponent privacy');
    await tools.getByRole('button', {name: 'Close Test Tools', exact: true}).click();
    await toggle(a, false);
    await h.wait(() => a.match.state.test_tools === false, 'live OFF publication');
    assert.equal(await a.page.getByRole('button', {name: 'Test Tools', exact: true}).count(), 0);
    await a.page.evaluate(({match, seq}) => { window.__ownerMatch = match; window.__ownerSeq = seq; }, {match: a.match, seq: a.acks.at(-1).last_seq_applied});
    await rawCommand(a, {type: 'test_action', action: 'give_resources', player: 0, resource: 'wood', amount: 1});
    assert.equal(a.match.state.players[0].res.wood, wood + 1);
    await a.page.screenshot({path: path.join(output, 'owner-test-tools-off.png')});
    check('OFF revokes open socket; raw action rejected without state change');
    await toggle(a, true); await h.wait(() => a.match.state.test_tools, 'restored permission');
    const tick = a.match.tick;
    await a.page.reload({waitUntil: 'networkidle'});
    await h.wait(() => a.match?.tick === tick, 'account Continue after refresh');
    await a.page.getByRole('button', {name: 'Test Tools', exact: true}).waitFor();
    assert.equal(a.match.state.test_tools, true);
    check('existing test match reconnect preserves account-owned host permission');
    await toggle(a, false);
    for (const c of clients) assert.deepEqual(c.jsErrors, []);
    check('all three Chrome clients have no runtime errors; preference left OFF');
  } catch (error) {
    for (const [index, client] of clients.entries()) {
      await client.page.screenshot({path: path.join(output, `failure-${index}.png`), fullPage: true});
    }
    throw error;
  } finally {
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({checks, origin, chrome: browser.version()}, null, 2));
    await browser.close();
    console.log('OUTPUT ' + output);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
