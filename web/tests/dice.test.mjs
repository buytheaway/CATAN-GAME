import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { Euler, Vector3 } from "three";

const compiled = await build({ stdin: { contents: 'export * from "./dice";',
  resolveDir: fileURLToPath(new URL("../src/game/", import.meta.url)), loader: "ts" },
  bundle: true, write: false, platform: "node", format: "esm" });
const { serverDice, isNewRoll, finalDieRotation, diePose, DIE_PIPS, DICE_DURATION_MS } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

test("only an exact server pair is accepted; sums, missing and forged values produce no faces", () => {
  for (const pair of [[1, 6], [4, 5], [2, 2]]) assert.deepEqual(serverDice(pair), pair);
  for (const value of [9, null, undefined, [], [4], [4, 5, 6], [0, 6], [1, 7], [1.5, 4], ["4", 5]])
    assert.equal(serverDice(value), null);
});

test("roll identity handles identical consecutive pairs, duplicate snapshots and new matches", () => {
  assert.equal(isNewRoll(null, "room:1", 1), false); // Initial load/reconnect reads final faces immediately.
  assert.equal(isNewRoll({ key: "room:1", count: 1 }, "room:1", 2), true);
  assert.equal(isNewRoll({ key: "room:1", count: 2 }, "room:1", 2), false);
  assert.equal(isNewRoll({ key: "room:1", count: 2 }, "room:1", 1), false);
  assert.equal(isNewRoll({ key: "room:1", count: 2 }, "room:2", 0), false);
});

test("all six dice orientations settle with the matching numbered face pointing up", () => {
  const normals = [[0, 1, 0], [0, 0, 1], [1, 0, 0], [-1, 0, 0], [0, 0, -1], [0, -1, 0]];
  normals.forEach((normal, index) => {
    const face = index + 1;
    const rotation = finalDieRotation(face);
    const up = new Vector3(...normal).applyEuler(new Euler(...rotation));
    assert.ok(up.distanceTo(new Vector3(0, 1, 0)) < 1e-8);
    assert.equal(DIE_PIPS[face].length, face);
    for (const side of [0, 1]) {
      assert.deepEqual(diePose(1, face, side).rotation, rotation);
      assert.deepEqual(diePose(5, face, side), diePose(1, face, side));
    }
  });
});

test("dice trajectory is finite, deterministic, time limited and never produces another gameplay result", () => {
  assert.ok(DICE_DURATION_MS >= 700 && DICE_DURATION_MS <= 1200);
  for (const face of [1, 2, 3, 4, 5, 6]) for (const p of [0, .2, .5, .8, 1]) {
    const pose = diePose(p, face, 0);
    assert.deepEqual(pose, diePose(p, face, 0));
    assert.ok([...pose.position, ...pose.rotation].every(Number.isFinite));
    assert.deepEqual(Object.keys(pose).sort(), ["position", "rotation"]);
  }
});
