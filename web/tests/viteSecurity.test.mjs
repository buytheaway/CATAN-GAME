import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer as createHttpServer } from "node:http";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer, preview } from "vite";

// Only synthetic files are served or probed. Never request the repository's .env.
const configFile = fileURLToPath(new URL("../vite.config.ts", import.meta.url));
const canary = "PUBLIC_SYNTHETIC_FILE_CANARY";
const deniedNames = [".env", ".env.synthetic", "synthetic-key.pem"];
let directory, root, outside, dev, staticPreview, backend, origin;
const originalBackend = process.env.VITE_WS_URL;

before(async () => {
  directory = await mkdtemp(join(tmpdir(), "catan-vite-security-"));
  root = join(directory, "public-fixture");
  outside = join(directory, "outside.txt");
  await mkdir(join(root, "dist"), { recursive: true });
  const html = '<div>PUBLIC_VITE_FIXTURE</div><script type="module" src="/main.js"></script>';
  await writeFile(join(root, "index.html"), html);
  await writeFile(join(root, "main.js"), 'document.body.dataset.fixture = "ready";');
  await writeFile(join(root, "dist", "index.html"), "PUBLIC_PREVIEW_FIXTURE");
  await writeFile(outside, canary);
  for (const name of deniedNames) await writeFile(join(root, name), canary);
  backend = createHttpServer((req, res) => {
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ path: req.url, synthetic: true }));
  });
  await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
  process.env.VITE_WS_URL = `ws://127.0.0.1:${backend.address().port}/ws`;
  dev = await createServer({
    configFile, root, envDir: root, publicDir: false, logLevel: "silent",
    server: { port: 0, fs: { allow: [root] } },
  });
  await dev.listen();
  origin = `http://127.0.0.1:${dev.httpServer.address().port}`;
  staticPreview = await preview({ configFile, root, envDir: root, logLevel: "silent", preview: { port: 0 } });
});

after(async () => {
  await dev?.close();
  if (staticPreview) await new Promise(resolve => staticPreview.httpServer.close(resolve));
  if (backend) await new Promise(resolve => backend.close(resolve));
  if (originalBackend === undefined) delete process.env.VITE_WS_URL;
  else process.env.VITE_WS_URL = originalBackend;
  if (directory) {
    const target = resolve(directory);
    assert.equal(dirname(target), resolve(tmpdir()));
    assert.ok(basename(target).startsWith("catan-vite-security-"));
    await rm(target, { recursive: true, force: true });
  }
});

async function rejected(path, allowSpaFallback = false) {
  const response = await fetch(origin + path);
  const body = await response.text();
  assert.ok(!body.includes(canary), `${path} disclosed synthetic file contents`);
  // Reserved percent-encoded characters may remain literal and miss the file,
  // returning the normal SPA fallback rather than a filesystem response.
  const spaFallback = allowSpaFallback && response.status === 200
    && response.headers.get("content-type")?.startsWith("text/html")
    && body.includes("PUBLIC_VITE_FIXTURE");
  assert.ok(response.status >= 400 || spaFallback, `${path} must not serve a file; got ${response.status}`);
}

test("development and preview listeners default to IPv4 loopback", () => {
  assert.equal(dev.config.server.host, "127.0.0.1");
  assert.equal(dev.httpServer.address().address, "127.0.0.1");
  assert.equal(staticPreview.config.preview.host, "127.0.0.1");
  assert.equal(staticPreview.httpServer.address().address, "127.0.0.1");
});

test("normal development modules and preview pages remain available", async () => {
  const page = await fetch(origin + "/");
  assert.equal(page.status, 200);
  assert.match(await page.text(), /PUBLIC_VITE_FIXTURE/);
  const module = await fetch(origin + "/main.js");
  assert.equal(module.status, 200);
  assert.match(await module.text(), /dataset.fixture/);
  const pagePreview = await fetch(`http://127.0.0.1:${staticPreview.httpServer.address().port}/`);
  assert.equal(pagePreview.status, 200);
  assert.match(await pagePreview.text(), /PUBLIC_PREVIEW_FIXTURE/);
});

test("direct requests cannot read denied synthetic environment or PEM files", async () => {
  for (const name of deniedNames) {
    await rejected(`/${name}`);
    await rejected(`/${name}?raw`);
    await rejected(`/@fs/${join(root, name).replaceAll("\\", "/")}?raw`);
  }
});

test("Windows NTFS stream and encoded path aliases cannot bypass file denial", {
  skip: process.platform !== "win32" ? "NTFS aliases require Windows" : false,
}, async () => {
  for (const name of deniedNames) {
    await rejected(`/${name}::$DATA?raw`);
    await rejected(`/${name}%3A%3A%24DATA?raw`, true);
    await rejected(`/@fs/${join(root, name).replaceAll("\\", "/")}::$DATA?raw`);
  }
});

test("outside allow-list and Wasm-query requests disclose no synthetic bytes", async () => {
  await rejected(`/@fs/${outside.replaceAll("\\", "/")}?raw`);
  for (const name of deniedNames) await rejected(`/${name}?vite-wasm-instance`);
  await rejected(`/@fs/${outside.replaceAll("\\", "/")}?vite-wasm-instance`);
});

test("development API proxy preserves the configured backend and request path", async () => {
  const response = await fetch(origin + "/api/synthetic?probe=1");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { path: "/api/synthetic?probe=1", synthetic: true });
  assert.equal(dev.config.server.proxy["/ws"].target, `http://127.0.0.1:${backend.address().port}`);
  assert.equal(dev.config.server.proxy["/ws"].ws, true);
});
