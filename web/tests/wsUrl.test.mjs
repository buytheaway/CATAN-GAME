import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { build } from "esbuild";

const cases = [
  { name: "production uses the page origin and port", prod: true, override: "ws://old-server:8000/ws",
    protocol: "http:", host: "game.local:8088", expected: "ws://game.local:8088/ws" },
  { name: "HTTPS production selects secure WebSocket", prod: true, override: "",
    protocol: "https:", host: "game.example", expected: "wss://game.example/ws" },
  { name: "development preserves VITE_WS_URL", prod: false, override: "ws://lan-server:8000/ws",
    protocol: "http:", host: "localhost:5173", expected: "ws://lan-server:8000/ws" },
  { name: "development uses the same-origin Vite WS proxy so account cookies reach the backend", prod: false, override: "",
    protocol: "http:", host: "localhost:5173", expected: "ws://localhost:5173/ws" },
];

for (const scenario of cases) {
  test(scenario.name, async () => {
    const compiled = await build({
      entryPoints: [fileURLToPath(new URL("../src/wsClient.ts", import.meta.url))],
      bundle: true, write: false, format: "cjs",
      define: {
        "import.meta.env.PROD": String(scenario.prod),
        "import.meta.env.VITE_WS_URL": JSON.stringify(scenario.override),
      },
    });
    let connectedUrl;
    const module = { exports: {} };
    runInNewContext(compiled.outputFiles[0].text, {
      module, exports: module.exports,
      window: { location: { protocol: scenario.protocol, host: scenario.host } },
      WebSocket: class { constructor(url) { connectedUrl = url; } },
    });
    const { WSClient, defaultWebSocketUrl } = module.exports;
    assert.equal(defaultWebSocketUrl(), scenario.expected);
    new WSClient().connect("", "Alice");
    assert.equal(connectedUrl, scenario.expected);
  });
}
