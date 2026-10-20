// Original and corrected PUBLIC art on the same real Board3D. No production flag.
const { startDemo } = require('./fog-visual-demo.cjs');
const fs = require('node:fs/promises');
const path = require('node:path');
const reference = '986c99c3cd1b0a7bb38857b75401a4dde2f1bd2a';
async function startComparison(originalPort = 0, correctedPort = 0) {
  const original = await startDemo(originalPort, null, reference);
  try {
    // Match the original asset's in-memory response path; disk I/O belongs to
    // neither side's cold network/parse comparison.
    const corrected = await startDemo(correctedPort, null,
      await fs.readFile(path.join(__dirname, '../public/models/pieces/ship-pilot.glb')));
    return { original, corrected, close: () => { original.server.close(); corrected.server.close(); } };
  } catch (error) { original.server.close(); throw error; }
}
module.exports = { startComparison, reference };
if (require.main === module) startComparison(Number(process.env.CATAN_SHIP_ORIGINAL_PORT || 18781), Number(process.env.CATAN_SHIP_CORRECTED_PORT || 18782))
  .then(({ original, corrected }) => {
    console.log('Original GLB:  ' + original.origin + '/?demo=1&shipsart=1');
    console.log('Corrected GLB: ' + corrected.origin + '/?demo=1&shipsart=1');
    console.log('Choose Ship model > GLB pilot on either page; Procedural compares the unchanged default.');
    console.log('Use Reset, Construct/Move, 50 tiles and wheel/orbit controls. Both are PUBLIC synthetic snapshots.');
  }).catch(error => { console.error(error); process.exitCode = 1; });
