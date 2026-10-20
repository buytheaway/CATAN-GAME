// 5C audit: real current GamePage/Board3D + PUBLIC synthetic display snapshots.
// Loopback only, no backend/DB/credentials, no production renderer or asset edits.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { startDemo } = require('./fog-visual-demo.cjs');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.env.CATAN_ART_REVIEW_OUTPUT || path.join(os.tmpdir(), 'catan-art-direction-5c'));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const htmlEscape = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const scenes = [
  { id: 'base', title: 'Base Standard', detail: 'Shipped map geometry · synthetic roads, settlements and cities' },
  { id: 'new-shores-3', title: 'Official New Shores · 3 players', detail: 'Exact shipped official layout · synthetic display occupancy' },
  { id: 'new-shores-4', title: 'Official New Shores · 4 players', detail: 'Exact shipped official layout · Gold, sea, ports and pirate' },
  { id: 'four-islands-3', title: 'Official Four Islands · 3 players', detail: 'Exact shipped official layout · synthetic display occupancy' },
  { id: 'four-islands-4', title: 'Official Four Islands · 4 players', detail: 'Exact shipped official layout · synthetic display occupancy' },
  { id: 'fog-before', title: 'Fog · before reveal', detail: 'Existing public seven-hex fixture · unknown terrain/number absent' },
  { id: 'fog-after', title: 'Fog · after reveal', detail: 'Synthetic public revealed frame · final still state, not a secret recipe' },
  { id: 'pieces', title: 'Piece study · procedural default', detail: 'Existing public fixture · four owner colors, buildings, threats and ports' },
  { id: 'pieces', title: 'Piece study · corrected Blender pilot', model: 'glb', detail: 'Same public occupancy and camera · experimental opt-in only' },
  { id: 'new-shores-4', title: 'New Shores · Blender pilot', model: 'glb', detail: 'Same official geometry and synthetic occupancy · opt-in ship comparison' },
  { id: 'pieces', title: 'White / purple owner study', model: 'glb', palette: 'light', detail: 'Existing project owner colors · synthetic display only' },
  { id: 'threats', title: 'Robber / pirate component study', detail: 'Existing public geometry · synthetic public pirate position · no owned ships' },
];
const query = item => new URLSearchParams({ shipsart: '1', scene: item.id, model: item.model || 'procedural', ...(item.palette ? { palette: item.palette } : {}) }).toString();
function assertPublicBoards(boards) {
  assert.equal(Object.keys(boards).length, 5);
  for (const board of Object.values(boards)) {
    assert(board.tiles.length >= 19 && board.edges.length > 0);
    for (const key of Object.keys(board)) assert(['size', 'tiles', 'vertices', 'edges', 'edge_adj_hexes', 'ports',
      'robber_tile', 'robbers', 'pirate_tile', 'rules_config', 'map_id', 'map_meta', 'display_players',
      'occupied_v', 'occupied_e', 'occupied_ships'].includes(key), 'unexpected board field: ' + key);
    for (const tile of board.tiles) assert(!Object.hasOwn(tile, 'assignment') && tile.terrain !== 'fog');
    for (const edge of [...Object.keys(board.occupied_e), ...Object.keys(board.occupied_ships)])
      assert(board.edges.some(e => e.join(',') === edge), 'fixture must retain real edge IDs');
  }
}
function gallery(report) {
  const ordered = [...(report?.captures || [])].sort((a, b) => {
    const ai = scenes.findIndex(s => query(s) === a.query), bi = scenes.findIndex(s => query(s) === b.query);
    const rank = c => c.zoom === 'normal' ? 0 : c.zoom === 'close' ? 1 : 2;
    return ai - bi || rank(a) - rank(b);
  });
  const cards = ordered.map(item => `<article><a href="/captures/${item.file}" target="_blank"><img loading="lazy" src="/captures/${item.file}" alt="${htmlEscape(item.title)}"></a>
    <h3>${htmlEscape(item.title)}</h3><p>${htmlEscape(item.detail)}</p><p>${htmlEscape(item.zoom)} · ${item.width}×${item.height} · ${htmlEscape(item.model)}</p>
    <a href="/preview?${item.query}">Open actual interactive scene</a> · <a href="/captures/${item.file}" download>PNG</a></article>`).join('');
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CATAN · 5C actual renderer review</title>
  <style>body{margin:0;background:#0d1c29;color:#e4edf3;font:16px/1.5 system-ui}main{max-width:1800px;margin:auto;padding:32px}h1{font-size:32px;line-height:1.2}h2{margin-top:40px}a{color:#9ee3d0}p{color:#b5c6d1}strong{color:#e9f2f6}.notice{border-left:3px solid #e0bd72;padding:4px 18px;background:#142b3b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:22px}article{background:#142837;border:1px solid #2d4656;border-radius:10px;overflow:hidden}article img{width:100%;display:block}article h3,article p,article>a{margin:12px 18px}article>a{display:inline-block}article>a:first-child{margin:0;display:block}nav{display:flex;flex-wrap:wrap;gap:10px}nav a{padding:8px 12px;background:#1d3a4b;border-radius:7px}code{overflow-wrap:anywhere}.directions{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}.directions section{padding:18px;background:#142837;border:1px solid #2d4656;border-radius:10px}@media(max-width:560px){main{padding:15px}.grid{grid-template-columns:1fr}}</style>
  <style>.grid{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:1000px){.grid{grid-template-columns:1fr}}</style>
  <main><h1>CATAN · Visual Phase 5C</h1><p>Actual current Board3D captures · art direction review · ${htmlEscape(report?.checkedAt || 'not captured yet')}</p>
  <div class="notice"><p><strong>Real rendering, synthetic PUBLIC snapshots.</strong> Official board geometry comes from the shipped map builder. Display occupancy is synthetic, not a played/legality-verified match. Fog uses only the existing public fixture. Still effects, unchanged lighting and default camera; Close uses the real wheel-zoom limit.</p>
  <p>Procedural ship remains production default. Blender pilot is opt-in. These are current-state screenshots, <strong>not rendered proposals or user-approved art</strong>. No new model/material/light variant was implemented.</p></div>
  <h2>Interactive public previews</h2><nav>${scenes.map(item => `<a href="/preview?${query(item)}">${htmlEscape(item.title)}</a>`).join('')}</nav>
  <p><a href="#captures">Actual screenshots</a> · <a href="#observations">Observed differences</a> · <a href="#directions">Direction options</a> · <a href="#priorities">Future art priorities</a></p>
  <h2 id="captures">Actual captures (${report?.captures?.length || 0})</h2><p>Click an image for the original PNG. Normal views show complete boards; Close intentionally crops at the existing gameplay zoom limit. No image generation, retouching or hidden-state source.</p><div class="grid">${cards || '<p>Run the capture command before serving this gallery.</p>'}</div>
  <h2 id="observations">Observed in the actual renderer</h2><ul>
  <li><strong>Observed occlusion:</strong> on <a href="/captures/05-four-islands-4-procedural-normal.png">Four Islands4 at the normal camera</a>, robber tile29 (Fields12, q=-3/r=2) is partly hidden by wheat/number presentation. The upper hat remains visible. This is a concrete readability issue, not missing state or a proven gameplay defect; occluded area is not quantified.</li>
  <li><strong>Working hierarchy:</strong> boards dominate; warm number/port tokens stay readable; terrain colors and silhouettes distinguish resources; threats are neutral dark figures.</li>
  <li><strong>Artistic inconsistency, not a proven bug:</strong> dense tall wheat and large sheep compete with smaller houses. Wood-rich Blender ships have a different detail rhythm from the blocky procedural pirate and decorative harbor boats.</li>
  <li><strong>Material/style discontinuity:</strong> bright cyan sea tiles with raised waves meet a darker flat decorative ocean. Fog is a soft white volume on a distinct slate base. Both are clear; integration needs a design decision.</li>
  <li><strong>Readability to evaluate:</strong> green ownership against forest, white against ivory sails/tokens. No color-blind or contrast certification is claimed.</li>
  <li><strong>Measured asset imbalance:</strong> fields GLB has 44,300 triangles in its mesh definitions versus 2,470 for mountains and 215 for the ship pilot. Source inventory is not GPU timing or proof of a bottleneck.</li>
  <li>Other listed style differences are artistic judgments. Close views intentionally crop at the existing zoom limit. Number labels deliberately draw over decorative relief; preserve readability when evaluating physical token clearance.</li></ul>
  <h2 id="directions">Direction proposal · not approved</h2><div class="directions"><section><h3>A · Clean stylized tabletop — recommended</h3><p>Keep flat faces and restrained bevels, matte shared colors and clear silhouettes. Navy/teal water, muted terrain, warm ivory tokens, exact owner colors. Neutral fill, one soft directional light; quiet sparse waves, no SSR. Compact houses/boats and coherent proportions before extra detail.</p><p>Low extra rendering risk if geometry/material counts stay bounded. Extends the accepted clean digital tabletop direction; no measured speedup claimed.</p></section>
  <section><h3>B · Premium handcrafted miniatures — alternative</h3><p>Warm umber, muted stone, deep teal sea and parchment, with exact owner colors retained. Painted wood/resin, restrained rounded edges, neutral contact shadows and tactile bases. Carved houses, compact vegetation and wooden sailboats; no realistic diorama.</p><p>Medium to high art effort. More silhouette geometry and optional texture memory; sharing/atlas and measured budgets required.</p></section>
  <section><h3>C · Atmospheric fantasy strategy — comparison only</h3><p>Slate/teal, cool fill and restrained amber accents; jagged terrain, taller buildings/rigging and darker misty water. Risks hiding ownership, numbers and Fog boundaries.</p><p>High art/performance cost if it adds transparencies, particles or post-processing. Conflicts with the accepted non-cinematic direction; not recommended or authorized.</p></section></div>
  <h2 id="priorities">Prioritized future work · proposals only</h2><ol><li>Choose A or B and agree a relative-size/silhouette sheet before producing more models.</li><li>Unify buildings, ships, pirate and docks through common bevels, wood/paint treatment and owner-color coverage.</li><li>Review wheat/pasture detail and material/primitive budgets while preserving gameplay-distance recognition.</li><li>Align the ocean/sea-tile family, then tune token clearance and Fog/base integration.</li><li>Evaluate owner colors at actual camera distance before considering any GLB default promotion.</li></ol>
  <h2>Evidence and limits</h2><p>Checkpoint <code>${htmlEscape(report?.checkpoint || '')}</code>; Chrome ${htmlEscape(report?.chrome || '')}; ${htmlEscape(JSON.stringify(report?.viewport || {}))}. <a href="/report.json">Capture report</a>. Snapshot, camera, geometry/material counts, asset responses and SHA-256 of each PNG are recorded. Counts are inventory, not a new GPU performance claim.</p>
  <p>This gallery does not test production gameplay, data recovery, mobile/color-blind accessibility or other GPUs. The historical contradictory GPU reports remain unchanged.</p></main></html>`;
}
async function startReview(port = 0) {
  await fs.mkdir(output, { recursive: true });
  const python = process.env.CATAN_REVIEW_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const boards = JSON.parse(execFileSync(python, ['-X', 'utf8', path.join(__dirname, 'art-review-boards.py')], { cwd: root, encoding: 'utf8' }));
  assertPublicBoards(boards);
  const boardBytes = Buffer.from(JSON.stringify(boards));
  await fs.writeFile(path.join(output, 'boards.json'), boardBytes);
  const demo = await startDemo();
  const controller = await fs.readFile(path.join(__dirname, 'art-review-controller.js'));
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let report; try { report = JSON.parse(await fs.readFile(path.join(output, 'capture-report.json'), 'utf8')); } catch {}
      if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(gallery(report)); return; }
      if (url.pathname === '/boards.json') { res.setHeader('Content-Type', 'application/json'); res.end(boardBytes); return; }
      if (url.pathname === '/report.json') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(report || {}, null, 2)); return; }
      if (url.pathname === '/art-review-controller.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(controller); return; }
      if (url.pathname.startsWith('/captures/')) {
        const file = url.pathname.slice('/captures/'.length);
        if (!/^[a-z0-9-]+\.png$/.test(file) || !report?.captures?.some(c => c.file === file)) { res.writeHead(404); res.end(); return; }
        res.setHeader('Content-Type', 'image/png'); res.end(await fs.readFile(path.join(output, file))); return;
      }
      if (url.pathname === '/preview') {
        const html = await (await fetch(demo.origin)).text();
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.end(html.replace('</body>', '<script src="/art-review-controller.js"></script></body>')); return;
      }
      if (['/fixture.js', '/fixture.css', '/favicon.ico'].includes(url.pathname) || /^\/(assets|models)\//.test(url.pathname)) {
        const response = await fetch(demo.origin + url.pathname);
        res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/octet-stream' });
        res.end(Buffer.from(await response.arrayBuffer())); return;
      }
      res.writeHead(404); res.end();
    } catch (error) { console.error(error.message); res.statusCode = 500; res.end('Review unavailable'); }
  });
  try { await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); }); }
  catch (error) { demo.server.close(); throw error; }
  return { server, boards, origin: 'http://127.0.0.1:' + server.address().port,
    close: () => { server.close(); demo.server.close(); } };
}
async function capture() {
  const { chromium } = require('playwright');
  const { observeScene } = require('./ships-visual.cjs');
  const { fullyReady, sceneSettings } = require('./buildings-compare.cjs');
  const { artReady, shipInfo } = require('./ship-art-visual.cjs');
  const review = await startReview(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  let report = { completed: false, checkedAt: new Date().toISOString(),
    checkpoint: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), chrome: browser.version(),
    viewport: { width: 2560, height: 1440, deviceScaleFactor: 1 },
    provenance: 'actual current GamePage/Board3D; shipped non-Fog geometry; synthetic PUBLIC occupancy; existing public Fog fixture only',
    method: 'Still effect controls, unchanged lights/materials/auto-fit; close via real wheel input; fresh page per scene; no GPU benchmark',
    boards: Object.fromEntries(Object.entries(review.boards).map(([id, b]) => [id, { map_id: b.map_id, tiles: b.tiles.length, ports: b.ports.length }])),
    captures: [], errors: [], assetResponses: [] };
  const reportFile = path.join(output, 'capture-report.json');
  if (process.argv.includes('--append')) {
    report = JSON.parse(await fs.readFile(reportFile, 'utf8'));
    assert(report.completed && report.checkpoint === execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim());
    await fs.writeFile(path.join(output, 'capture-report-before-append.json'), JSON.stringify(report, null, 2), { flag: 'wx' });
    report.completed = false; report.appendedAt = new Date().toISOString();
  }
  report.assets = [];
  for (const [folder, names] of [['terrain', ['forest', 'fields', 'pasture', 'hills', 'mountains', 'desert', 'sea', 'gold']],
    ['pieces', ['road', 'settlement', 'city', 'ship-pilot']]]) {
    for (const name of names) {
      const relative = `web/public/models/${folder}/${name}.glb`, bytes = await fs.readFile(path.join(root, relative));
      const gltf = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString('utf8'));
      const triangles = gltf.meshes.flatMap(m => m.primitives).reduce((sum, p) => sum + (gltf.accessors[p.indices ?? p.attributes.POSITION].count / 3), 0);
      report.assets.push({ path: relative, bytes: bytes.length, sha256: sha(bytes), triangles, meshes: gltf.meshes.length,
        materials: gltf.materials.map(m => ({ name: m.name, doubleSided: m.doubleSided ?? false,
          roughness: m.pbrMetallicRoughness?.roughnessFactor ?? 1, metallic: m.pbrMetallicRoughness?.metallicFactor ?? 1 })),
        textures: gltf.textures?.length || 0 });
    }
  }
  const context = await browser.newContext({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await context.addInitScript(observeScene);
  try {
    for (const [index, item] of scenes.entries()) {
      if (report.captures.some(c => c.query === query(item) && c.zoom === 'normal')) continue;
      const page = await context.newPage();
      page.on('pageerror', e => report.errors.push(item.title + ': ' + e.message));
      page.on('console', m => { if (m.type() === 'error') report.errors.push(item.title + ': ' + m.text()); });
      page.on('response', r => { if (/\/models\//.test(r.url())) report.assetResponses.push({ scene: index, path: new URL(r.url()).pathname, status: r.status() }); });
      try {
        await page.goto(review.origin + '/preview?' + query(item));
        await page.waitForFunction(() => window.__artReview?.ready || window.__artReview?.error);
        assert.equal(await page.evaluate(() => window.__artReview.error), undefined);
        await fullyReady(page);
        if (item.model === 'glb') await artReady(page);
        else assert.equal(await page.getByLabel('Ship model', { exact: true }).inputValue(), 'procedural');
        await page.mouse.move(1, 1);
        for (const zoom of ['normal', 'close']) {
          if (zoom === 'close') {
            const rect = await page.locator('canvas').boundingBox();
            await page.mouse.move(rect.x + rect.width * .55, rect.y + rect.height * .5);
            await page.mouse.wheel(0, -800); await page.waitForTimeout(300); await page.mouse.move(1, 1);
          }
          const file = String(index + 1).padStart(2, '0') + '-' + item.id + '-' + (item.model || 'procedural') + (item.palette ? '-' + item.palette : '') + '-' + zoom + '.png';
          await page.screenshot({ path: path.join(output, file) });
          const settings = await sceneSettings(page), frame = settings.publicState; delete settings.publicState;
          const info = await shipInfo(page);
          assert.equal(settings.scene.tiles, frame.tiles.length);
          assert.equal(info.ships.length, Object.keys(frame.occupied_ships).length);
          assert(frame.players.filter(p => p.pid !== frame.you_pid).every(p => !('res' in p) && !('dev_cards' in p)));
          assert(frame.tiles.filter(t => t.visibility === 'hidden').every(t => t.terrain === 'fog' && t.number === null));
          assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
          const inventory = await page.evaluate(() => {
            const { scene } = window.__scene.getState(); let tokens = 0; const mats = new Set(), geometry = new Set();
            scene.traverse(o => { if (o.userData.number != null && o.userData.tileIndex == null) tokens++; if (o.isMesh) { geometry.add(o.geometry.uuid);
              for (const mat of Array.isArray(o.material) ? o.material : [o.material]) mats.add(mat.uuid); } });
            return { tokens, geometries: geometry.size, materials: mats.size };
          });
          assert.equal(inventory.tokens, frame.tiles.filter(t => t.visibility !== 'hidden' && t.number != null && t.terrain !== 'sea' && t.terrain !== 'desert').length);
          report.captures.push({ file, title: item.title, detail: item.detail, model: item.model || 'procedural', zoom,
            query: query(item), width: 2560, height: 1440, sha256: sha(await fs.readFile(path.join(output, file))), settings,
            publicStateHash: sha(JSON.stringify(frame)), inventory, shipTriangles: info.ships.map(s => s.triangles) });
          if (item.id === 'threats' && zoom === 'normal') {
            for (const kind of ['robber', 'pirate']) {
              const clip = await page.evaluate(kind => {
                const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
                let figure; scene.traverse(o => { if (o.userData.piece === kind) figure = o; });
                if (!figure) throw Error('Missing actual ' + kind);
                const r = gl.domElement.getBoundingClientRect(), points = [];
                figure.traverse(o => { if (!o.isMesh) return; const p = o.geometry.attributes.position;
                  for (let i = 0; i < p.count; i++) { const v = o.position.clone().fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld).project(camera);
                    points.push([r.x + (v.x + 1) * r.width / 2, r.y + (1 - v.y) * r.height / 2]); } });
                const x = Math.max(0, Math.floor(Math.min(...points.map(p => p[0]))) - 25);
                const y = Math.max(0, Math.floor(Math.min(...points.map(p => p[1]))) - 25);
                return { x, y, width: Math.min(innerWidth, Math.ceil(Math.max(...points.map(p => p[0]))) + 25) - x,
                  height: Math.min(innerHeight, Math.ceil(Math.max(...points.map(p => p[1]))) + 25) - y };
              }, kind);
              const detailFile = '12-th' + kind + '-native-detail.png';
              await page.screenshot({ path: path.join(output, detailFile), clip });
              report.captures.push({ file: detailFile, title: kind + ' · actual native-pixel detail', detail: 'Direct browser clip from the normal view; no retouching or camera/mesh modification',
                model: 'procedural', zoom: 'native-pixel crop', query: query(item), width: clip.width, height: clip.height,
                sha256: sha(await fs.readFile(path.join(output, detailFile))), clip });
            }
          }
          await fs.writeFile(reportFile, JSON.stringify(report, null, 2));
          console.log('Captured ' + file);
        }
      } finally { await page.close(); }
    }
    assert.deepEqual(report.errors, []); assert(report.assetResponses.every(r => r.status === 200));
    report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(reportFile, JSON.stringify(report, null, 2));
    await context.close(); await browser.close(); review.close();
  }
  console.log('Actual captures: ' + report.captures.length + '; gallery artifacts: ' + output);
}
module.exports = { startReview, scenes, gallery, assertPublicBoards };
if (require.main === module) {
  (process.argv.includes('--capture') ? capture() : startReview(Number(process.env.CATAN_ART_REVIEW_PORT || 18785))
    .then(review => console.log('Actual Board3D gallery: ' + review.origin + '\nArtifacts: ' + output)))
    .catch(error => { console.error(error); process.exitCode = 1; });
}
