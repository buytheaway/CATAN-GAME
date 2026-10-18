const { startDemo } = require('./fog-visual-demo.cjs');
startDemo(Number(process.env.CATAN_BUILDING_PREVIEW_PORT || 18775))
  .then(({ origin }) => console.log('PUBLIC synthetic construction preview: ' + origin + '/?demo=1&buildings=1'))
  .catch(error => { console.error(error); process.exitCode = 1; });
