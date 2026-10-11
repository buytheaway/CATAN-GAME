// Chrome presentation acceptance on PUBLIC fixtures. No backend, WS endpoint or trusted map input.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { chromium } = require('playwright');
const { build } = require('../node_modules/esbuild');
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-fog3a-browser'));
const publicRoot = path.resolve(__dirname, '../public');
const report = { scope: 'synthetic PUBLIC fixtures; no live Fog multiplayer', checks: [], scenes: [], screenshots: [] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const check = label => { report.checks.push(label); console.log('PASS ' + label); };

function observeScene() {
  let id = 0;
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, inject: () => ++id, checkDCE() {},
    onCommitFiberRoot(_, root) {
      const store = root.current?.stateNode?.containerInfo;
      if (store?.getState && store.getState().scene) window.__scene = store;
    }, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
  };
}
async function sceneInfo(page) {
  return page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
    const tiles = [], ports = [], coast = [], pieces = [], revealing = [];
    scene.traverse(o => {
      const d = o.userData;
      if (d.terrain && d.tileIndex != null) {
        const nodes = []; o.traverse(n => nodes.push({ data: n.userData, geometry: n.geometry?.uuid,
          material: (Array.isArray(n.material) ? n.material : [n.material]).filter(Boolean).map(m => [m.type, m.color?.getHexString(), m.opacity]),
          position: n.position.toArray(), scale: n.scale.toArray(), cast: n.castShadow, receive: n.receiveShadow }));
        const projected = o.getWorldPosition(o.position.clone()).project(camera);
        tiles.push({ ...d, position: o.position.toArray(), nodes, screen: [projected.x, projected.y] });
      }
      if (d.kind && d.edge && !d.targetType) ports.push({ edge: d.edge, kind: d.kind });
      if (d.coastEdge) coast.push(d.coastEdge);
      if (d.owner != null && !d.ghost) pieces.push({ owner: d.owner, vertexId: d.vertexId, edge: d.edge, level: d.level });
      if (d.fogReveal && o.visible) revealing.push({ opacity: o.material.opacity, active: d.revealing });
    });
    return { tiles, ports, coast, pieces, revealing, frame: gl.info.render.frame,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures, calls: gl.info.render.calls };
  });
}
async function ready3d(page, count = 7) {
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await page.waitForFunction(count => {
    let n = 0; window.__scene?.getState().scene.traverse(o => { if (o.userData.terrain) n++; }); return n === count;
  }, count);
}
async function targetPoint(page, type, id) {
  await page.waitForFunction(({ type, id }) => {
    let found = false; window.__scene?.getState().scene.traverse(o => {
      const d = o.userData;
      if (type === 'tile' ? d.terrain && d.tileIndex === id
        : d.targetType === type && (type === 'vertex' ? d.vertexId === id : d.edge?.join(',') === id)) found = true;
    }); return found;
  }, { type, id });
  return page.evaluate(({ type, id }) => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
    let target; scene.traverse(o => {
      const d = o.userData;
      if (type === 'tile' ? d.terrain && d.tileIndex === id
        : d.targetType === type && (type === 'vertex' ? d.vertexId === id : d.edge?.join(',') === id)) target = o;
    });
    if (!target) throw Error('Target missing: ' + type + ' ' + id);
    const p = target.getWorldPosition(target.position.clone()).project(camera);
    const r = gl.domElement.getBoundingClientRect();
    return { x: r.left + (p.x + 1) * r.width / 2, y: r.top + (1 - p.y) * r.height / 2 };
  }, { type, id });
}
async function publish(page, transform, arg) {
  await page.evaluate(transform, arg);
  await sleep(60);
}
async function screenshot(page, name) {
  const file = path.join(output, name + '.png'); await page.screenshot({ path: file }); report.screenshots.push(file);
}
async function layout(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('.board3d-canvas')?.getBoundingClientRect();
    return { width: innerWidth, scroll: document.documentElement.scrollWidth,
      canvas: canvas && { x: canvas.x, y: canvas.y, width: canvas.width, height: canvas.height },
      dock: !!document.querySelector('.action-dock') };
  });
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  await build({ entryPoints: [path.join(__dirname, 'fog-fixture.tsx')], bundle: true,
    outfile: path.join(output, 'fixture.js'), format: 'iife', jsx: 'automatic', sourcemap: false,
    define: { 'import.meta.env': '{}', 'process.env.NODE_ENV': '"production"' } });
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>PUBLIC Fog fixture acceptance</title>'
    + '<link rel="stylesheet" href="/fixture.css"><style>html,body,#root{height:100%;width:100%;overflow:hidden}</style>'
    + '</head><body><div id="root"></div><script src="/fixture.js"></script></body></html>';
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    try {
      if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html'); res.end(html); return; }
      let file;
      if (['/fixture.js', '/fixture.css'].includes(url.pathname)) file = path.join(output, url.pathname.slice(1));
      else if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/models/')) {
        file = path.resolve(publicRoot, '.' + decodeURIComponent(url.pathname));
        if (!file.startsWith(publicRoot + path.sep)) throw Error('Invalid static path');
      } else { res.statusCode = 404; res.end(); return; }
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'application/octet-stream');
      res.end(await fs.readFile(file));
    } catch { res.statusCode = 404; res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(observeScene);
  const page = await context.newPage(), errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', req => requests.push(new URL(req.url()).pathname));
  try {
    await page.goto(origin + '?fixture=hidden'); await ready3d(page); await sleep(300);
    const allHidden = await sceneInfo(page); assert.equal(allHidden.tiles.length, 7);
    for (const t of allHidden.tiles) {
      assert.equal(t.terrain, 'fog'); assert.equal(t.visibility, 'hidden'); assert.equal(t.number, null);
      assert.ok(t.nodes.some(n => n.data.fogVisual));
      assert.ok(t.nodes.every(n => !n.data.terrainAsset && !n.data.terrainFallback && n.data.number == null));
    }
    assert.equal(allHidden.coast.length, 0); assert.equal(allHidden.ports.length, 0);
    const fingerprints = allHidden.tiles.map(t => JSON.stringify(t.nodes.slice(1).map(n => {
      const { tileIndex, ...data } = n.data; return { ...n, data };
    })));
    assert.equal(new Set(fingerprints).size, 1);
    assert.equal(requests.some(p => p.startsWith('/models/terrain/')), false);
    await screenshot(page, 'hidden-3d-desktop'); check('all unknown Three subtrees are identical neutral geometry/materials; no terrain GLB, tokens, ports or coast');

    const h = await targetPoint(page, 'tile', 3), count = await page.evaluate(() => window.__fogFixture.commands().length);
    await page.mouse.move(h.x, h.y); await page.mouse.click(h.x, h.y);
    assert.equal(await page.evaluate(() => window.__fogFixture.commands().length), count);
    await publish(page, () => {
      const next = window.__fogFixture.snapshot(); next.tick++;
      next.state.tiles[3] = { ...next.state.tiles[3], visibility: 'revealed', terrain: 'forest', number: 6 };
      window.__fogFixture.publish(next);
    });
    const during = await sceneInfo(page);
    assert.equal(during.tiles.find(t => t.tileIndex === 3).terrain, 'forest');
    assert.equal(during.tiles.find(t => t.tileIndex === 3).number, 6);
    assert.ok(during.revealing.length === 1 && during.revealing[0].opacity > 0);
    await sleep(500); assert.equal((await sceneInfo(page)).revealing.length, 0);
    await page.mouse.move(1, 1); await sleep(200);
    const idle = (await sceneInfo(page)).frame; await sleep(300); assert.equal((await sceneInfo(page)).frame, idle);
    check('hidden hover/click emits no command; committed 3D reveal is immediate, finite and returns to idle');

    await publish(page, () => window.__fogFixture.status('disconnected'));
    await publish(page, () => window.__fogFixture.status('connected'));
    await publish(page, () => {
      const next = window.__fogFixture.snapshot(); next.tick += 3;
      next.state.tiles[4] = { ...next.state.tiles[4], visibility: 'revealed', terrain: 'sea', number: null };
      window.__fogFixture.publish(next);
    });
    assert.equal((await sceneInfo(page)).revealing.length, 0);
    check('first fresh frame after reconnect shows new public sea without replaying offline discovery');

    await page.getByRole('button', { name: '2D', exact: true }).click();
    await publish(page, () => {
      const next = window.__fogFixture.snapshot(); next.tick++;
      next.state.tiles[6] = { ...next.state.tiles[6], visibility: 'revealed', terrain: 'gold', number: 8 };
      window.__fogFixture.publish(next);
    });
    assert.equal(await page.locator('[data-fog-reveal="6"]').count(), 1);
    assert.equal(await page.locator('[data-tile-index="6"][data-terrain="gold"] [data-number-token="8"]').count(), 1);
    await sleep(500); assert.equal(await page.locator('[data-fog-reveal]').count(), 0);
    await publish(page, () => { const old = window.__fogFixture.snapshot(); old.tick--;
      old.state.tiles[6] = { ...old.state.tiles[6], visibility: 'hidden', terrain: 'fog', number: null }; window.__fogFixture.publish(old); });
    assert.equal(await page.locator('[data-tile-index="6"][data-terrain="gold"]').count(), 1);
    await publish(page, () => window.__fogFixture.reject());
    assert.equal(await page.locator('[data-fog-reveal]').count(), 0);
    check('SVG committed reveal shows exact number; stale/error frames cannot roll it back or animate again');

    await publish(page, () => window.__fogFixture.load('partial'));
    const svg = await page.locator('[data-renderer="2d"]').innerHTML();
    assert.equal(await page.locator('[data-visibility="hidden"]').count(), 3);
    assert.equal(await page.locator('[data-visibility="hidden"] [data-number-token]').count(), 0);
    assert.match(svg, />3:1</); assert.match(svg, />2:1</);
    await screenshot(page, 'partial-svg-desktop'); await ready3d(page); await sleep(300);
    await page.waitForFunction(() => {
      let assets = 0; window.__scene.getState().scene.traverse(o => { if (o.userData.terrainAsset) assets++; }); return assets === 4;
    });
    const partial = await sceneInfo(page); assert.equal(partial.ports.length, 2); assert.equal(partial.pieces.length, 4);
    assert.equal(partial.tiles.filter(t => t.visibility === 'hidden').some(t => t.nodes.some(n => n.data.terrainAsset)), false);
    assert.ok(partial.tiles.filter(t => t.visibility === 'revealed').every(t => t.nodes.some(n => n.data.terrainAsset === t.terrain)));
    assert.deepEqual(partial.tiles.filter(t => t.number != null).map(t => [t.tileIndex, t.number]), [[0, 5], [2, 8]]);
    assert.equal(partial.revealing.length, 0); await screenshot(page, 'partial-3d-desktop');
    check('partial SVG/3D shows public Forest/Gold/Sea/Desert with real GLBs, exact pieces/ports/tokens; toggle has no historical reveal');

    await page.getByRole('button', { name: 'Road', exact: true }).click();
    const road = await page.evaluate(() => window.__fogFixture.snapshot().state.legal.roads[0]);
    const point = await targetPoint(page, 'edge', road.join(','));
    await page.mouse.move(point.x, point.y); await sleep(100); await page.mouse.click(point.x, point.y);
    await page.waitForFunction(() => window.__fogFixture.commands().some(m => m.cmd.type === 'place_road'));
    const cmd = await page.evaluate(() => window.__fogFixture.commands().at(-1).cmd);
    assert.deepEqual(cmd.eid, road); assert.equal(cmd.type, 'place_road');
    await publish(page, () => { window.__fogFixture.settle(false); window.__fogFixture.reject(); });
    assert.equal((await sceneInfo(page)).pieces.length, 4);
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    check('real 3D legal marker/ghost click delegates original road ID; rejection keeps occupancy and Cancel works');

    for (const view of ['3D', '2D']) {
      for (const mode of ['setup', 'free']) {
        await publish(page, () => window.__fogFixture.load('partial'));
        await publish(page, mode => {
          const next = window.__fogFixture.snapshot(); next.tick++;
          if (mode === 'setup') { next.state.phase = 'setup'; next.state.setup_need = 'road'; }
          else { next.state.legal.road_free = true; next.state.free_roads = { '0': 2 }; }
          window.__fogFixture.publish(next);
        }, mode);
        if (view === '3D') await ready3d(page);
        else await page.getByRole('button', { name: '2D', exact: true }).click();
        await page.getByRole('button', { name: 'Ship', exact: true }).click();
        const edge = await page.evaluate(() => window.__fogFixture.snapshot().state.legal.ships[0]);
        const before = await page.evaluate(() => window.__fogFixture.commands().length);
        if (view === '3D') { const p = await targetPoint(page, 'edge', edge.join(',')); await page.mouse.click(p.x, p.y); }
        else await page.locator(`[data-target-edge="${edge.join(',')}"]`).click();
        await page.waitForFunction(n => window.__fogFixture.commands().length > n, before);
        const cmd = await page.evaluate(() => window.__fogFixture.commands().at(-1).cmd);
        assert.equal(cmd.type, 'build_ship'); assert.deepEqual(cmd.eid, edge);
        assert.equal(mode === 'setup' ? cmd.setup : cmd.free, true);
        await publish(page, () => { window.__fogFixture.settle(false); window.__fogFixture.reject(); });
      }
    }
    check('SVG and real 3D hitboxes preserve setup Ship and Road Building free Ship payloads near Fog');
    await publish(page, () => window.__fogFixture.load('partial')); await ready3d(page);
    await page.getByRole('button', { name: 'Move Ship', exact: true }).click();
    const source = await page.evaluate(() => window.__fogFixture.snapshot().state.legal.move_ship.sources[0]);
    const sourcePoint = await targetPoint(page, 'edge', source.join(','));
    await page.mouse.click(sourcePoint.x, sourcePoint.y);
    await page.getByRole('button', { name: 'Cancel move', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Cancel move', exact: true }).click();
    await page.getByRole('button', { name: 'Cancel move', exact: true }).waitFor({ state: 'hidden' });
    await page.waitForFunction(source => {
      let reset = false; window.__scene.getState().scene.traverse(o => {
        if (o.userData.targetType === 'edge' && o.userData.edge.join(',') === source.join(',') && !o.userData.selected) reset = true;
      }); return reset;
    }, source);
    const resetPoint = await targetPoint(page, 'edge', source.join(','));
    await page.mouse.click(resetPoint.x, resetPoint.y);
    await page.getByRole('button', { name: 'Cancel move', exact: true }).waitFor();
    const destination = await page.evaluate(source => window.__fogFixture.snapshot().state.legal.move_ship.targets[source.join(',')][0], source);
    const movePoint = await targetPoint(page, 'edge', destination.join(','));
    const beforeMove = await page.evaluate(() => window.__fogFixture.commands().length);
    await page.mouse.click(movePoint.x, movePoint.y);
    await page.waitForFunction(n => window.__fogFixture.commands().length > n, beforeMove);
    const moved = await page.evaluate(() => window.__fogFixture.commands().at(-1).cmd);
    assert.deepEqual(moved, { type: 'move_ship', from_eid: source, to_eid: destination });
    await publish(page, () => { window.__fogFixture.settle(false); window.__fogFixture.reject(); });
    assert.equal((await sceneInfo(page)).pieces.length, 4);
    check('real 3D source/cancel/destination ship movement preserves authoritative IDs with no optimistic piece mutation');

    await publish(page, () => window.__fogFixture.load('gold'));
    const dialog = page.getByRole('dialog', { name: 'Gold Choice: 1', exact: true });
    await dialog.waitFor(); assert.match(await dialog.innerText(), /Discovery reward/);
    await page.getByLabel('Gold resource').selectOption('ore'); await dialog.getByRole('button', { name: 'Choose', exact: true }).click();
    await page.waitForFunction(() => window.__fogFixture.commands().at(-1)?.cmd.type === 'choose_gold');
    assert.equal(await dialog.getByRole('button', { name: 'Choose', exact: true }).isDisabled(), true);
    await publish(page, () => { window.__fogFixture.settle(false); window.__fogFixture.reject(); });
    assert.equal(await dialog.getByRole('button', { name: 'Choose', exact: true }).isEnabled(), true);
    const choice = await page.evaluate(() => window.__fogFixture.commands().at(-1).cmd);
    assert.deepEqual(choice, { type: 'choose_gold', res: 'ore', qty: 1 });
    await screenshot(page, 'gold-choice-desktop');
    await publish(page, () => { const next = window.__fogFixture.snapshot(); next.tick++;
      next.state.pending_action = null; next.state.pending_pid = null; next.state.pending_gold = {};
      next.state.game_events.push({ id: 3, tick: next.tick, at_ms: 2000, type: 'choose_gold', actor_pid: 0, quantity: 1, gained: { ore: 1 } });
      window.__fogFixture.publish(next); });
    await page.getByRole('button', { name: 'Event log', exact: true }).click();
    const log = await page.locator('.gameplay-events').innerText();
    assert.match(log, /Explorer discovered hex 2: gold \(8\)/); assert.match(log, /choose 1 resource/);
    assert.match(log, /Explorer collected gold resources/); assert.doesNotMatch(log, /\bore\b/);
    check('existing Gold modal waits for ACK/retry, exact choose_gold intent; public discovery/choice log omits private selected ore');

    await page.goto(origin + '?fixture=partial'); await ready3d(page); await sleep(200);
    assert.equal((await sceneInfo(page)).revealing.length, 0); check('refresh with already-revealed tiles produces no historical animation');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await publish(page, () => { const next = window.__fogFixture.snapshot(); next.tick++;
      next.state.tiles[3] = { ...next.state.tiles[3], terrain: 'forest', visibility: 'revealed', number: 6 }; window.__fogFixture.publish(next); });
    assert.equal((await sceneInfo(page)).revealing.length, 0);
    await page.getByRole('button', { name: '2D', exact: true }).click();
    assert.equal(await page.locator('[data-fog-reveal]').count(), 0); check('reduced motion skips 3D/SVG reveal feedback while updating terrain immediately');
    await page.emulateMedia({ reducedMotion: 'no-preference' });

    await publish(page, () => window.__fogFixture.load('large')); await ready3d(page, 50); await sleep(300);
    for (const [width, height] of [[1440, 900], [1024, 768]]) {
      await page.setViewportSize({ width, height }); await sleep(160);
      const info = await sceneInfo(page), bounds = await layout(page);
      assert.ok(info.tiles.every(t => Math.abs(t.screen[0]) <= 1 && Math.abs(t.screen[1]) <= 1));
      assert.ok(bounds.scroll <= width); assert.ok(bounds.canvas.width > 0 && bounds.canvas.height > 0);
      report.scenes.push({ viewport: [width, height], tiles: info.tiles.length, calls: info.calls,
        geometries: info.geometries, textures: info.textures, layout: bounds });
      await screenshot(page, 'large-3d-' + width);
    }
    await page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
    await page.getByRole('button', { name: '2D', exact: true }).click(); await screenshot(page, 'large-svg-1024');
    assert.ok((await layout(page)).scroll <= 1024);
    check('asymmetric 50-tile Fog board/camera fits desktop and narrower viewport in 3D/SVG without horizontal overflow');
    await publish(page, () => window.__fogFixture.load('normal')); await ready3d(page); await sleep(250);
    assert.equal((await sceneInfo(page)).tiles.some(t => t.terrain === 'fog'), false);
    await page.getByRole('button', { name: '2D', exact: true }).click();
    assert.equal(await page.locator('[data-number-token="5"]').count(), 7);
    check('Fog-disabled historical tile format retains ordinary SVG/3D rendering');
    assert.deepEqual(errors, []); report.pageErrors = errors;
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log('REPORT ' + path.join(output, 'report.json'));
  } catch (error) {
    report.failure = error.stack; report.pageErrors = errors;
    await screenshot(page, 'failure'); await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    throw error;
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
