const { startDemo } = require('./fog-visual-demo.cjs');
startDemo(Number(process.env.CATAN_THREAT_PREVIEW_PORT || 18777))
  .then(({ origin }) => console.log('PUBLIC synthetic robber/pirate preview: ' + origin + '/?demo=1&threats=1'))
  .catch(error => { console.error(error); process.exitCode = 1; });
