// Local PUBLIC fixture preview. No app server, credentials, trusted recipe or network WebSocket.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { build } = require('../node_modules/esbuild');

async function startDemo(port = 0, sourceRef = null) {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'catan-fog-visual-'));
  const publicRoot = path.resolve(__dirname, '../public');
  // Test-only controlled A/B: read committed frontend blobs without checkout/reset.
  const repoRoot = path.resolve(__dirname, '../..'), sourceRoot = path.resolve(__dirname, '../src') + path.sep;
  const plugins = sourceRef ? [{ name: 'committed-frontend', setup(builder) {
    builder.onLoad({ filter: /\.(tsx?|jsx?|css)$/ }, args => {
      if (!args.path.startsWith(sourceRoot)) return;
      const relative = path.relative(repoRoot, args.path).split(path.sep).join('/');
      return { contents: execFileSync('git', ['show', sourceRef + ':' + relative], { cwd: repoRoot, encoding: 'utf8' }),
        loader: path.extname(args.path).slice(1), resolveDir: path.dirname(args.path) };
    });
  } }] : [];
  await build({ entryPoints: [path.join(__dirname, 'fog-fixture.tsx')], bundle: true,
    outfile: path.join(output, 'fixture.js'), format: 'iife', jsx: 'automatic', sourcemap: false, plugins,
    define: { 'import.meta.env': '{}', 'process.env.NODE_ENV': '"production"' } });
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>CATAN public Fog visual preview</title>'
    + '<link rel="stylesheet" href="/fixture.css"><style>html,body,#root{height:100%;width:100%;overflow:hidden}</style>'
    + '</head><body><div id="root"></div><script src="/fixture.js"></script></body></html>';
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      if (url.pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
      if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); return; }
      let file;
      if (['/fixture.js', '/fixture.css'].includes(url.pathname)) file = path.join(output, url.pathname.slice(1));
      else if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/models/')) {
        file = path.resolve(publicRoot, '.' + decodeURIComponent(url.pathname));
        if (!file.startsWith(publicRoot + path.sep)) throw Error('Invalid static path');
      } else { res.writeHead(404); res.end(); return; }
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript'
        : file.endsWith('.css') ? 'text/css' : 'application/octet-stream');
      res.end(await fs.readFile(file));
    } catch { res.statusCode = 404; res.end(); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  return { server, output, origin: 'http://127.0.0.1:' + server.address().port };
}
module.exports = { startDemo };
if (require.main === module) startDemo(Number(process.env.CATAN_FOG_PREVIEW_PORT || 18772))
  .then(({ origin }) => console.log('PUBLIC synthetic Fog preview: ' + origin + '/?demo=1'))
  .catch(error => { console.error(error); process.exitCode = 1; });
