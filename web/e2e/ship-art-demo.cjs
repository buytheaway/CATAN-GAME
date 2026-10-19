// Loopback-only public Board3D comparison. No backend or trusted game data.
const { startDemo } = require('./fog-visual-demo.cjs');
if (require.main === module) startDemo(Number(process.env.CATAN_SHIP_ART_PREVIEW_PORT || 18780))
  .then(({ origin }) => console.log('PUBLIC ship art pilot: ' + origin + '/?demo=1&shipsart=1'))
  .catch(error => { console.error(error); process.exitCode = 1; });
