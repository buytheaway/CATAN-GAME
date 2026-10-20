// Matched original/corrected art using actual Board3D, PUBLIC snapshots and inputs.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startComparison, reference } = require('./ship-topology-demo.cjs');
const { observeScene } = require('./ships-visual.cjs');
const { fullyReady, sceneSettings } = require('./buildings-compare.cjs');
const { artReady, shipInfo, staticMode } = require('./ship-art-visual.cjs');
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ship-topology-visual-' + Date.now());
async function ghost(page) {
  const button = page.getByRole('button', { name: 'Ship', exact: true }); await button.click();
  const point = await page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    let target; scene.traverse(o => { if (o.userData.targetType === 'edge' && !o.userData.source) target ??= o; });
    if (!target) throw Error('No public legal ship target');
    const p = target.getWorldPosition(target.position.clone()).project(camera), r = gl.domElement.getBoundingClientRect();
    return { x: r.x + (p.x + 1) * r.width / 2, y: r.y + (1 - p.y) * r.height / 2 };
  });
  await page.mouse.move(point.x, point.y);
  await page.waitForFunction(() => { let yes = false; window.__scene.getState().scene.traverse(o => {
    yes ||= o.userData.piece === 'ship' && o.userData.preview; }); return yes; });
  return page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState(); let root;
    scene.traverse(o => { if (o.userData.piece === 'ship' && o.userData.preview) root = o; });
    const parts = []; root.traverse(o => { if (o.isMesh) { const hits = []; o.raycast({}, hits);
      parts.push({ name: o.material.name, side: o.material.side, opacity: o.material.opacity,
        transparent: o.material.transparent, castShadow: o.castShadow, hits: hits.length }); } });
    // Isolated ghost rendering counters, no production mutation or timed sample.
    const auto = gl.info.autoReset; gl.info.autoReset = false; gl.info.reset(); gl.render(root, camera);
    const calls = gl.info.render.calls, triangles = gl.info.render.triangles; gl.info.autoReset = auto; gl.render(scene, camera);
    window.__scene.getState().invalidate();
    return { edge: root.userData.edge, parts, calls, triangles };
  });
}
async function animation(page, origin, move) {
  await page.goto(origin + '/?demo=1&shipsart=1'); await fullyReady(page); await staticMode(page);
  await page.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(page);
  // Test-only clock control fixes the actual production cue's age for matched
  // capture. No pose, snapshot controller or production animation is replaced.
  await page.evaluate(() => { window.__artNow = performance.now(); performance.now = () => window.__artNow; });
  await page.getByLabel('Ship effects', { exact: true }).selectOption('motion');
  await page.evaluate(move => window.__fogFixture.ship(move), move);
  await page.waitForFunction(() => { let found = false; window.__scene.getState().scene.traverse(o => {
    found ||= !!(o.userData.shipVisual && o.userData.appearing); }); return found; });
  const frames = [];
  for (const age of [175, move ? 450 : 275, 1200]) {
    await page.evaluate(age => { window.__artStart ??= window.__artNow;
      window.__artNow = window.__artStart + age; window.__scene.getState().invalidate(); }, age);
    await page.waitForTimeout(100); frames.push({ age, info: await shipInfo(page) });
    const file = path.join(output, `${windowSide(page)}-${move ? 'movement' : 'construction'}-${age}.png`);
    await page.screenshot({ path: file }); frames.at(-1).screenshot = file;
  }
  const final = frames.at(-1).info;
  assert(final.ships.every(s => !s.pose.appearing && s.pose.scale.every(v => v === 1)));
  assert.equal(final.echoes.length, 0);
  return frames;
}
const sides = new WeakMap();
const windowSide = page => sides.get(page);
async function main() {
  await fs.mkdir(output, { recursive: true });
  const reportPath = path.join(output, 'comparison.json'); await fs.writeFile(reportPath, '{}', { flag: 'wx' });
  const report = { completed: false, reference, checks: [], errors: [], sides: {}, screenshots: [] };
  const demo = await startComparison(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try {
    for (const side of ['original', 'corrected']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
      try {
        await context.addInitScript(observeScene); const page = await context.newPage(); sides.set(page, side);
        page.on('pageerror', e => report.errors.push(side + ': ' + e.message));
        page.on('console', m => { if (m.type() === 'error') report.errors.push(side + ': ' + m.text()); });
        await page.goto(demo[side].origin + '/?demo=1&shipsart=1'); await fullyReady(page); await staticMode(page);
        assert.equal(await page.getByLabel('Ship model', { exact: true }).inputValue(), 'procedural');
        const shot = async name => { const file = path.join(output, `${side}-${name}.png`); await page.screenshot({ path: file }); report.screenshots.push(file); };
        await shot('procedural'); await page.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(page);
        const data = report.sides[side] = { settings: await sceneSettings(page), model: await shipInfo(page), angles: [], inputCameras: [] };
        const canonicalCamera = async (name, wanted) => {
          const actual = await sceneSettings(page); data.inputCameras.push({ name, settings: actual });
          if (wanted) await page.evaluate(camera => {
            const { camera: actual } = window.__scene.getState();
            actual.position.fromArray(camera.position); actual.quaternion.fromArray(camera.quaternion);
            actual.updateMatrixWorld(); window.__scene.getState().invalidate();
          }, wanted.camera);
        };
        await shot('normal');
        const canvas = page.locator('canvas'), rect = await canvas.boundingBox();
        await page.mouse.move(rect.x + rect.width * .6, rect.y + rect.height * .5); await page.mouse.wheel(0, -500); await page.waitForTimeout(250);
        await canonicalCamera('close', report.sides.original.close); data.close = await sceneSettings(page); await shot('close');
        for (const [name, dx, dy] of [['orbit-left', -250, 0], ['orbit-back', 350, 0], ['high', 0, 150], ['low', 0, -300]]) {
          await page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
          const x = rect.x + rect.width * .55, y = rect.y + rect.height * .5;
          await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx, y + dy, { steps: 12 }); await page.mouse.up();
          await page.mouse.move(1, 1); await page.waitForTimeout(150);
          // Pointer events can coalesce differently. Preserve actual input poses,
          // then use the original control-generated pose for matched capture only.
          await canonicalCamera(name, side === 'corrected' ? report.sides.original.angles.find(a => a.name === name).settings : null);
          data.angles.push({ name, settings: await sceneSettings(page) }); await shot(name);
        }
        await page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
        data.ghost = await ghost(page); await shot('legal-ghost');
        assert(data.ghost.parts.length === 3 && data.ghost.parts.every(p => p.transparent && p.opacity === .46 && !p.castShadow && !p.hits));
        await page.mouse.move(1, 1); await page.keyboard.press('Escape');
        await page.getByRole('button', { name: '50 tiles', exact: true }).click(); await artReady(page); await shot('50-hex');
        assert.equal((await shipInfo(page)).ships.length, 24);
        assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
        // Separate pages discard the controlled clock; normal final screenshots
        // above and GPU measurements never use this capture-only time control.
        data.animations = [];
        for (const move of [false, true]) {
          const animated = await context.newPage(); sides.set(animated, side);
          animated.on('pageerror', e => report.errors.push(side + ': ' + e.message));
          animated.on('console', m => { if (m.type() === 'error') report.errors.push(side + ': ' + m.text()); });
          try {
            const frames = await animation(animated, demo[side].origin, move);
            data.animations.push({ move, frames }); report.screenshots.push(...frames.map(f => f.screenshot));
          }
          finally { await animated.close(); }
        }
      } finally { await context.close(); }
    }
    assert.deepEqual(report.sides.original.settings, report.sides.corrected.settings);
    assert.deepEqual(report.sides.original.angles, report.sides.corrected.angles);
    assert.deepEqual(report.sides.original.close, report.sides.corrected.close);
    const roots = info => info.ships.map(s => ({ edge: s.edge, owner: s.owner, position: s.position, yaw: s.yaw }));
    assert.deepEqual(roots(report.sides.original.model), roots(report.sides.corrected.model));
    assert.deepEqual(report.sides.original.ghost.edge, report.sides.corrected.ghost.edge);
    for (const index of [0, 1]) for (const frame of [0, 1, 2]) {
      const a = report.sides.original.animations[index].frames[frame], b = report.sides.corrected.animations[index].frames[frame];
      assert.equal(a.age, b.age); assert.deepEqual(roots(a.info), roots(b.info));
      assert.deepEqual(a.info.ships.map(s => s.pose.scale), b.info.ships.map(s => s.pose.scale));
      assert.equal(a.info.echoes.length, b.info.echoes.length);
    }
    report.checks.push('matched public state/camera/shadows/owner anchors at normal, close, opposite azimuths and both allowed polar limits',
      'real legal hover ghost retains owner, opacity, raycast exclusion and no command', 'procedural default and 24 ships/50 hexes preserved');
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (e) { report.failure = e.stack; throw e; }
  finally { await fs.writeFile(reportPath, JSON.stringify(report, null, 2)); await browser.close(); demo.close(); }
  console.log(JSON.stringify({ completed: report.completed, checks: report.checks, output }, null, 2));
}
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
module.exports = { ghost };
