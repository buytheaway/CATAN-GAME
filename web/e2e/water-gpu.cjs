const { main } = require('./ocean-gpu.cjs');
const { passes } = require('./readability-gpu.cjs');
const { startWater, reference } = require('./water-demo.cjs');
const h = require('./ocean-support.cjs');
const options = { start: startWater, reference, scenes: ['base', 'new-shores-4', 'four-islands-4', 'fifty'],
  query: (...args) => h.query(...args) + '&water=pilot' };
const job = process.argv.includes('--passes') ? passes(process.argv.at(-1), options) : main(options);
job.catch(error => { console.error(error); process.exitCode = 1; });
