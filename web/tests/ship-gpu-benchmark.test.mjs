import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const { orders, stats, summarize } = createRequire(import.meta.url)('../e2e/ship-art-gpu.cjs');

test('GPU benchmark counterbalances both models at every order position', () => {
  const blocks = orders();
  assert.deepEqual(blocks, [['procedural', 'glb', 'glb', 'procedural'], ['glb', 'procedural', 'procedural', 'glb']]);
  for (const block of blocks) assert.equal(block.filter(model => model === 'glb').length, 2);
  for (let position = 0; position < 4; position++) assert.equal(new Set(blocks.map(block => block[position])).size, 2);
});
test('timing summaries retain chronological raw data and expose outliers', () => {
  const raw = [2, 1, 3, 100];
  assert.deepEqual(stats(raw), { count: 4, median: 2, p95: 100, min: 1, max: 100 });
  assert.deepEqual(raw, [2, 1, 3, 100]);
  assert.throws(() => stats([])); assert.throws(() => stats([NaN]));
});
test('invalid disjoint GPU timers remain counted and are never reported as valid GPU time', () => {
  const reading = { gpuSamples: [
    { gpuMs: 2, submitMs: 1, disjoint: false, calls: 10, triangles: 20 },
    { gpuMs: null, submitMs: 50, disjoint: true, calls: 10, triangles: 20 },
    { gpuMs: 4, submitMs: 3, disjoint: false, calls: 10, triangles: 20 },
  ], wallSamples: [{ wallMs: 8 }, { wallMs: 10 }] };
  const before = structuredClone(reading), summary = summarize([reading]);
  assert.equal(summary.gpuSamples, 3); assert.equal(summary.invalidGpuSamples, 1);
  assert.equal(summary.gpu.count, 2); assert.equal(summary.gpu.median, 2); assert.equal(summary.wall.median, 8);
  assert.deepEqual(reading, before);
  const invalid = summarize([{ ...reading, gpuSamples: [reading.gpuSamples[1]] }]);
  assert.equal(invalid.gpu, null); assert.equal(invalid.submit, null); assert.deepEqual(invalid.readingGpuMedians, [null]);
});
