const { startDemo } = require('./fog-visual-demo.cjs');
startDemo(Number(process.env.CATAN_SHIP_PREVIEW_PORT || 18773))
  .then(({ origin }) => console.log('PUBLIC synthetic ship preview: ' + origin + '/?demo=1&ships=1'))
  .catch(error => { console.error(error); process.exitCode = 1; });
