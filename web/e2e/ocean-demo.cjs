// Loopback-only actual Board3D A/B. All snapshots are synthetic PUBLIC display data.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { build } = require('../node_modules/esbuild');
const { createHash } = require('node:crypto');
const { assertPublicBoards } = require('./art-direction-review.cjs');
const root = path.resolve(__dirname, '../..');
const reference = 'b61215b1ea1f2693b0f828720f8384ac4e291327';
const scenes = ['base', 'new-shores-3', 'new-shores-4', 'four-islands-3', 'four-islands-4', 'fog-before', 'fog-after', 'seven', 'fifty', 'outer-legal'];
const outputRoot = () => path.resolve(process.env.CATAN_OCEAN_OUTPUT || path.join(os.tmpdir(), 'catan-ocean-5d2'));
async function bundleSource(sourceRef) {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'catan-ocean-bundle-'));
  const sourceRoot = path.join(root, 'web/src') + path.sep;
  const actual = path.join(root, 'web/src/board3d/Board3D.tsx');
  const wrapper = await fs.readFile(path.join(__dirname, 'ocean-wrapper.tsx'), 'utf8');
  const plugins = [{ name: 'test-only-ocean-options', setup(builder) {
    builder.onResolve({ filter: /(?:^|\/)Board3D$/ }, args => {
      if (!args.importer.endsWith('BoardRenderer.tsx')) return;
      return { path: 'ocean-preview-wrapper', namespace: 'ocean' };
    });
    builder.onResolve({ filter: /^__OCEAN_ACTUAL_BOARD__$/ }, () => ({ path: actual }));
    builder.onLoad({ filter: /.*/, namespace: 'ocean' }, () => ({ contents: wrapper, loader: 'tsx', resolveDir: __dirname }));
  } }, ...(sourceRef ? [{ name: 'committed-public-renderer', setup(builder) {
    builder.onLoad({ filter: /\.(tsx?|jsx?|css)$/ }, args => {
      if (!args.path.startsWith(sourceRoot)) return;
      const relative = path.relative(root, args.path).split(path.sep).join('/');
      return { contents: execFileSync('git', ['show', sourceRef + ':' + relative], { cwd: root, encoding: 'utf8' }),
        loader: path.extname(args.path).slice(1), resolveDir: path.dirname(args.path) };
    });
  } }] : [])];
  await build({ entryPoints: [path.join(__dirname, 'fog-fixture.tsx')], bundle: true,
    outfile: path.join(output, 'fixture.js'), format: 'iife', jsx: 'automatic', plugins,
    define: { 'import.meta.env': '{}', 'process.env.NODE_ENV': '"production"' } });
  return output;
}
const escape = text => String(text).replace(/[&<>"']/g, value => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[value]));
function gallery(report) {
  return `<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CATAN 5D.2 ocean review</title><style>body{background:#102332;color:#e9f4fa;font:16px/1.5 system-ui;margin:24px}a{color:#a0e8db}nav{display:flex;gap:14px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}article{background:#193445;padding:12px}img{width:100%}code{overflow-wrap:anywhere}@media(max-width:900px){.grid{grid-template-columns:1fr}}</style><h1>5D.2 · actual hex ocean and frame</h1><p>Real GamePage/Board3D; synthetic PUBLIC display states. Existing playable terrain, coordinates and IDs are unchanged. Outer ships are display scaffolding, not a legality-certified match. Public Fog previews contain no secret assignments.</p><p>Before renderer: <code>${reference}</code>. Current renderer is the working tree. Procedural ship remains default; GLB is opt-in.</p><nav>${scenes.map(scene => `<a href="/preview?shipsart=1&scene=${scene}&source=after&rings=1&fixture=${scene === 'fifty' ? 'large' : 'partial'}">${escape(scene)}</a>`).join('')}</nav><p><a href="/report.json">Capture report</a> · ${escape(report?.checkedAt || 'Run ocean-capture.cjs to populate screenshots.')}</p><div class="grid">${(report?.captures || []).map(item => `<article><a href="/captures/${escape(item.file)}"><img loading="lazy" src="/captures/${escape(item.file)}"></a><h3>${escape(item.scene)} · ${escape(item.source)} · rings ${item.rings} · ${escape(item.zoom)}</h3><p>${escape(item.detail || '')}</p><a href="/preview?${escape(item.query)}">Open same interactive scene</a></article>`).join('')}</div></html>`;
}
async function startOcean(port = 0) {
  if (execFileSync('git', ['rev-parse', reference], { cwd: root, encoding: 'utf8' }).trim() !== reference) throw Error('Checkpoint unavailable');
  const output = outputRoot(); await fs.mkdir(output, { recursive: true });
  const python = process.env.CATAN_REVIEW_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const boards = JSON.parse(execFileSync(python, ['-X','utf8',path.join(__dirname,'art-review-boards.py')], {cwd:root,encoding:'utf8'}));
  assertPublicBoards(boards);
  const legalOuter = JSON.parse(execFileSync(python, ['-X','utf8',path.join(__dirname,'ocean-boards.py')], {cwd:root,encoding:'utf8'}));
  const bundles = { before: await bundleSource(reference), after: await bundleSource(null) };
  const bundleHashes = Object.fromEntries(await Promise.all(Object.entries(bundles).map(async ([key,folder]) =>
    [key,createHash('sha256').update(await fs.readFile(path.join(folder,'fixture.js'))).digest('hex')])));
  const controller = await fs.readFile(path.join(__dirname,'ocean-controller.js'));
  const publicRoot = path.join(root,'web/public');
  const report = async () => { try { return JSON.parse(await fs.readFile(path.join(output,'capture-report.json'),'utf8')); } catch { return null; } };
  const server = http.createServer(async (req,res) => {
    try {
      const url = new URL(req.url,'http://127.0.0.1');
      if(url.pathname === '/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(gallery(await report()));return;}
      if(url.pathname === '/boards.json') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(boards));return;}
      if(url.pathname === '/legal-outer.json') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(legalOuter));return;}
      if(url.pathname === '/report.json') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(await report() || {},null,2));return;}
      if(url.pathname === '/ocean-controller.js') {res.setHeader('Content-Type','text/javascript');res.end(controller);return;}
      if(url.pathname === '/preview') {
        const side = url.searchParams.get('source') === 'before' ? 'before' : 'after';
        res.setHeader('Content-Type','text/html; charset=utf-8');
        res.end(`<!doctype html><html><meta charset="utf-8"><title>CATAN ocean public preview</title><link rel="stylesheet" href="/${side}/fixture.css"><style>html,body,#root{height:100%;width:100%;overflow:hidden}</style><body><div id="root"></div><script src="/${side}/fixture.js"></script><script src="/ocean-controller.js"></script></body></html>`);return;
      }
      if(url.pathname === '/favicon.ico') {res.writeHead(204);res.end();return;}
      if(url.pathname.startsWith('/captures/')) {
        const name = url.pathname.slice(10);
        if(!/^[a-z0-9-]+\.png$/.test(name) || !(await report())?.captures.some(c => c.file === name)) {res.writeHead(404);res.end();return;}
        res.setHeader('Content-Type','image/png');res.end(await fs.readFile(path.join(output,name)));return;
      }
      let file;
      const bundle = url.pathname.match(/^\/(before|after)\/(fixture\.(?:js|css))$/);
      if(bundle) file = path.join(bundles[bundle[1]],bundle[2]);
      else if(/^\/(?:models|assets)\//.test(url.pathname)) {
        file = path.resolve(publicRoot,'.'+decodeURIComponent(url.pathname));
        if(!file.startsWith(publicRoot+path.sep)) throw Error('Invalid static path');
      } else {res.writeHead(404);res.end();return;}
      res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'application/octet-stream');res.end(await fs.readFile(file));
    } catch(error) {console.error(error.message);res.statusCode=404;res.end();}
  });
  await new Promise((resolve,reject) => {server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
  return {server,boards,legalOuter,output,bundleHashes,origin:'http://127.0.0.1:'+server.address().port,close:()=>new Promise(resolve=>server.close(resolve))};
}
module.exports={startOcean,reference,scenes,gallery};
if(require.main===module) startOcean(Number(process.env.CATAN_OCEAN_PORT||18786))
  .then(demo=>console.log('PUBLIC ocean gallery: '+demo.origin+'/')).catch(error=>{console.error(error);process.exitCode=1;});
