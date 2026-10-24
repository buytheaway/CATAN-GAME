// Real material/geometry facts, not estimated image colors or hidden map data.
const h = require('./ocean-support.cjs');
async function inventory(page, includeGeometry = false) {
  return page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    const materials = new Map(), rows = [];
    const material = m => ({ name: m.name, type: m.type, color: m.color?.getHexString(),
      roughness: m.roughness, metalness: m.metalness, specularIntensity: m.specularIntensity,
      side: m.side, transparent: m.transparent, opacity: m.opacity, toneMapped: m.toneMapped,
      depthTest: m.depthTest, depthWrite: m.depthWrite });
    function mesh(n, role) {
      if (!n.isMesh) return;
      const list = Array.isArray(n.material) ? n.material : [n.material];
      list.forEach(m => materials.set(m.uuid, material(m)));
      const attr = n.geometry.getAttribute('position'), world = n.position.clone();
      let low = Infinity, high = -Infinity;
      for (let i = 0; i < attr.count; i++) {
        world.fromBufferAttribute(attr, i).applyMatrix4(n.matrixWorld);
        low = Math.min(low, world.y); high = Math.max(high, world.y);
      }
      rows.push({ role, name: n.name, materials: list.map(material), elevation: [low, high],
        castShadow: n.castShadow, receiveShadow: n.receiveShadow,
        triangles: (n.geometry.index?.count || attr.count) / 3, instances: n.isInstancedMesh ? n.count : 1,
        ...(n.instanceColor ? { firstTint: n.instanceColor && (() => { const c = list[0].color.clone(); n.getColorAt(0, c); return c.getHexString(); })() } : {}) });
    }
    let sea = false;
    scene.traverse(n => {
      if (!sea && n.userData.terrainAsset === 'sea') { sea = true; n.traverse(m => mesh(m, 'playable-sea')); }
      if (n.userData.decorativeOceanHexes) n.traverse(m => mesh(m, 'decorative-ring'));
      if (n.userData.decorativeOcean) n.traverse(m => mesh(m, 'surrounding-water'));
    });
    const geometry = [], buffers = [], seen = new Map();
    scene.traverse(n => {
      if (!n.isMesh) return;
      if (!seen.has(n.geometry)) {
        seen.set(n.geometry, buffers.length);
        buffers.push({ groups: n.geometry.groups, positions: Array.from(n.geometry.getAttribute('position').array),
          indices: n.geometry.index ? Array.from(n.geometry.index.array) : null });
      }
      geometry.push({ name: n.name, data: n.userData, matrix: n.matrixWorld.toArray(), visible: n.visible,
        count: n.isInstancedMesh ? n.count : 1, buffer: seen.get(n.geometry),
        instances: n.isInstancedMesh ? Array.from(n.instanceMatrix.array) : null });
    });
    gl.render(scene, camera);
    return { rows, materials: [...materials.values()], geometry: { nodes: geometry, buffers }, renderer: {
      outputColorSpace: gl.outputColorSpace, toneMapping: gl.toneMapping, exposure: gl.toneMappingExposure,
      shadowType: gl.shadowMap.type, shadows: gl.shadowMap.enabled },
      render: { ...gl.info.render }, resources: { ...gl.info.memory, programs: gl.info.programs.length },
      lights: scene.children.filter(n => n.isLight).map(n => ({ type: n.type, intensity: n.intensity, color: n.color.getHexString() })),
      assets: performance.getEntriesByType('resource').filter(e => new URL(e.name).pathname.startsWith('/models/'))
        .map(e => ({ path: new URL(e.name).pathname, encodedBytes: e.encodedBodySize, transferBytes: e.transferSize })) };
  }).then(result => {
    // React may remount an InstancedMesh after its material args change. Child
    // traversal order is not geometry: compare complete content/world/ID records.
    const buffers = result.geometry.buffers.map(buffer => h.hash(buffer));
    const nodes = result.geometry.nodes.map(node => JSON.stringify({ ...node, buffer: buffers[node.buffer] })).sort();
    const geometryHash = h.hash({ buffers: [...buffers].sort(), nodes });
    const raw = result.geometry; delete result.geometry;
    result.rows.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
    return { ...result, geometryHash, geometryHashMethod: 'complete world/ID/buffer records, independent of traversal order',
      ...(includeGeometry ? { geometry: raw } : {}) };
  });
}
module.exports = { inventory };
// Separate untimed inspection after GPU timing; no resource/network instrumentation
// runs inside a measured span. Preserve the raw report and fresh output file.
async function main(file) {
  const fs = require('node:fs/promises'), path = require('node:path'), assert = require('node:assert/strict');
  const { chromium } = require('playwright'), { startWater, reference } = require('./water-demo.cjs');
  const { ready } = require('./water-capture.cjs');
  const measured = JSON.parse(await fs.readFile(file, 'utf8'));
  assert(measured.completed && measured.reference === reference);
  const report = { completed: false, reference, checkedAt: new Date().toISOString(), cases: {} };
  const demo = await startWater(); let browser;
  try {
    assert.deepEqual(demo.bundleHashes, measured.bundleHashes); report.bundleHashes = demo.bundleHashes;
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const publicRoot = path.resolve(__dirname, '../public');
    for (const scene of ['base', 'new-shores-4', 'four-islands-4', 'fifty']) for (const side of ['before', 'after']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
      try {
        await context.addInitScript(h.observeScene); const page = await context.newPage();
        await page.goto(demo.origin + '/preview?' + h.query(scene, side) + '&water=pilot'); await ready(page);
        await h.useCamera(page, measured.measurements[scene + '-static'].canonicalCamera);
        const data = await inventory(page);
        for (const asset of data.assets) {
          const assetFile = path.resolve(publicRoot, '.' + asset.path); assert(assetFile.startsWith(publicRoot + path.sep));
          const bytes = await fs.readFile(assetFile); asset.fileBytes = bytes.length; asset.sha256 = h.hash(bytes);
        }
        data.assetFileBytes = data.assets.reduce((sum, asset) => sum + asset.fileBytes, 0);
        data.scene = await h.inventory(page); report.cases[scene + '-' + side] = data;
      } finally { await context.close(); }
    }
    for (const scene of ['base', 'new-shores-4', 'four-islands-4', 'fifty']) {
      const signature = side => report.cases[scene + '-' + side].assets.map(({ path, fileBytes, sha256 }) => ({ path, fileBytes, sha256 }))
        .sort((a, b) => a.path.localeCompare(b.path));
      assert.deepEqual(signature('before'), signature('after'), 'pilot must not download new or modified model assets');
    }
    report.completed = true;
  } finally {
    await browser?.close(); await demo.close();
    await fs.writeFile(path.join(path.dirname(file), 'material-inventory.json'), JSON.stringify(report, null, 2), { flag: 'wx' });
  }
  console.log('WATER MATERIAL/ASSET INVENTORY ' + path.dirname(file));
}
if (require.main === module) main(process.argv[2]).catch(error => { console.error(error); process.exitCode = 1; });
