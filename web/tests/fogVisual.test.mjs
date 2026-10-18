import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";

const compiled = await build({ stdin: { contents: `
  export * from "./src/board3d/fogPresentation";
  export * from "./src/board3d/fogResources";
  export * from "./src/board3d/resources";
  export { FOG_REVEAL_MS } from "./src/board/fogReveal";`,
  resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, format: "cjs", platform: "node", external: ["react"] });
const module = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  createRequire(import.meta.url), module, module.exports);
const { createFogResources, createVisualResources, fogQuality, fogProgress, fogDispersal,
  FOG_3D_REVEAL_MS, FOG_REVEAL_MS, FOG_IDLE_HZ } = module.exports;

test("3D reveal has a finite independent lifetime; SVG timing remains 420 ms", () => {
  assert.equal(FOG_REVEAL_MS, 420); assert.equal(FOG_3D_REVEAL_MS, 1000);
  assert.equal(fogProgress(100, 0), 0); assert.equal(fogProgress(100, 100), 0);
  assert.equal(fogProgress(100, 600), .5); assert.equal(fogProgress(100, 1100), 1);
  assert.equal(fogProgress(100, 100000), 1);
});

test("dispersal starts at the identical hidden pose and ends transparent, lifted and bounded", () => {
  assert.deepEqual(fogDispersal(0), { opacity: 1, spread: 1, lift: 0 });
  let previous = fogDispersal(0);
  for (let i = 1; i <= 100; i++) {
    const next = fogDispersal(i / 100);
    assert(next.opacity <= previous.opacity && next.opacity >= 0);
    assert(next.spread >= previous.spread && next.spread <= 1.15);
    assert(next.lift >= previous.lift && next.lift <= .38);
    previous = next;
  }
  assert.equal(previous.opacity, 0);
});

test("reduced motion disables ambient movement; explicit simple/low-precision fallback remains available", () => {
  assert.equal(fogQuality("mist", false), "mist"); assert.equal(fogQuality("mist", true), "still");
  assert.equal(fogQuality("still", false), "still"); assert.equal(fogQuality("simple", true), "simple");
  assert.equal(fogQuality("mist", false, true), "simple");
  assert(FOG_IDLE_HZ > 0 && FOG_IDLE_HZ <= 15);
});

test("hidden geometry and material inputs are identical without tile/terrain/number data", () => {
  const a = createFogResources(), b = createFogResources();
  assert.deepEqual(a.cloud.attributes.position.array, b.cloud.attributes.position.array);
  assert.deepEqual(a.cloud.attributes.normal.array, b.cloud.attributes.normal.array);
  assert.equal(a.mist.vertexShader, b.mist.vertexShader); assert.equal(a.mist.fragmentShader, b.mist.fragmentShader);
  assert.deepEqual(Object.keys(a.mist.uniforms).sort(), ["uHaze", "uLight", "uOpacity", "uShade", "uTime"]);
  a.cloud.computeBoundingBox(); const bounds = a.cloud.boundingBox;
  assert(bounds.min.x >= -.9 && bounds.max.x <= .9 && bounds.min.z >= -.9 && bounds.max.z <= .9);
  assert(bounds.min.y > .15 && bounds.max.y < .9);
  assert(a.cloud.attributes.position.count / 3 < 2500);
  assert.equal(a.mist.depthWrite, false); assert.equal(a.haze.depthWrite, false);
  a.dispose(); b.dispose();
});

test("simultaneous reveals own isolated fades while sharing geometry and the single scene clock", () => {
  const fog = createFogResources(), a = fog.revealMaterials(), b = fog.revealMaterials();
  assert.notEqual(a.cloud, b.cloud); assert.notEqual(a.base[0], b.base[0]);
  assert.equal(a.cloud.uniforms.uTime, fog.time); assert.equal(b.haze.uniforms.uTime, fog.time);
  a.cloud.uniforms.uOpacity.value = .2; a.base[0].opacity = .3;
  assert.equal(b.cloud.uniforms.uOpacity.value, 1); assert.equal(fog.mist.uniforms.uOpacity.value, 1);
  assert.equal(b.base[0].opacity, 1); assert.equal(fog.top.opacity, 1);
  assert.equal(a.cloud.depthTest, false); assert.equal(a.mark.depthTest, false);
  fog.time.value = 17; assert.equal(b.cloud.uniforms.uTime.value, 17);
  a.dispose(); b.dispose(); fog.dispose();
});

test("reveal disposal releases only owned clones; scene disposal owns the shared resources", async () => {
  const pool = createVisualResources(); pool.retain(); const fog = pool.fog();
  assert.equal(pool.fog(), fog);
  const reveal = fog.revealMaterials(); let clones = 0, shared = 0;
  for (const m of [...reveal.base, reveal.cloud, reveal.haze, reveal.mark]) m.addEventListener("dispose", () => clones++);
  for (const resource of [fog.cloud, fog.top, fog.side, fog.mist, fog.haze, fog.mark]) resource.addEventListener("dispose", () => shared++);
  reveal.dispose(); assert.equal(clones, 5); assert.equal(shared, 0);
  pool.release(); pool.retain(); await Promise.resolve(); assert.equal(shared, 0);
  pool.release(); await Promise.resolve(); assert.equal(shared, 6);
});
