import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import ts from "typescript";

const NativeWebSocket = globalThis.WebSocket;

// Use the installed compiler, with no extra test dependency or generated files.
const source = readFileSync(new URL("../src/wsClient.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
}).outputText;
const { WSClient } = await import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);

class Socket {
  static OPEN = 1;
  static latest;
  readyState = 0;
  sent = [];
  constructor() { Socket.latest = this; }
  open() { this.readyState = Socket.OPEN; this.onopen(); }
  send(raw) { this.sent.push(JSON.parse(raw)); }
  receive(data) { this.onmessage({ data: JSON.stringify(data) }); }
}

beforeEach(() => {
  globalThis.WebSocket = Socket;
  const values = new Map();
  globalThis.localStorage = {
    setItem(key, value) { values.set(key, value); },
    getItem(key) { return values.get(key) ?? null; },
    removeItem(key) { values.delete(key); },
  };
  globalThis.window = { setTimeout };
});

function connectedClient() {
  const client = new WSClient();
  client.connect("ws://test/ws", "Alice");
  const socket = Socket.latest;
  socket.open();
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 1, last_seq_applied: 4 });
  return { client, socket };
}

function lobbyState(mapId = "base_standard", revision = 0, roomCode = "ROOM") {
  return { type: "room_state", room_code: roomCode, map_revision: revision,
    host_pid: 0, status: "lobby", max_players: 2, map_id: mapId,
    players: [{ pid: 0, name: "Alice", connected: true }, { pid: 1, name: "Bob", connected: true }] };
}

function lobbyClient() {
  const pair = connectedClient();
  pair.socket.receive(lobbyState());
  return pair;
}

test("map A remains pending through older/presence snapshots and confirmation sends no echo", () => {
  const { client, socket } = lobbyClient();
  const pending = [];
  client.onMapPending = id => pending.push(id);
  client.setMap("base_12vp");
  socket.receive(lobbyState());
  assert.equal(client.pendingMapId, "base_12vp");
  assert.equal(client.roomState.map_id, "base_standard");
  socket.receive(lobbyState("base_12vp", 1));
  assert.equal(client.pendingMapId, null);
  assert.equal(client.roomState.map_id, "base_12vp");
  assert.deepEqual(pending, ["base_12vp", null]);
  assert.deepEqual(socket.sent.filter(m => m.type === "set_map"), [{ type: "set_map", map_id: "base_12vp" }]);
});

test("rapid A to B keeps B visible and Start waits for the final server confirmation", () => {
  const { client, socket } = lobbyClient();
  client.setMap("base_12vp");
  client.setMap("seafarers_gold_haven");
  client.startMatch();
  assert.equal(socket.sent.filter(m => m.type === "set_map").length, 1);
  assert.equal(socket.sent.filter(m => m.type === "start_match").length, 0);
  socket.receive(lobbyState("base_12vp", 1));
  assert.equal(client.pendingMapId, "seafarers_gold_haven");
  assert.equal(socket.sent.at(-1).map_id, "seafarers_gold_haven");
  socket.receive(lobbyState("base_12vp", 1));
  assert.equal(client.pendingMapId, "seafarers_gold_haven");
  socket.receive(lobbyState("seafarers_gold_haven", 2));
  assert.equal(client.pendingMapId, null);
  client.startMatch();
  assert.equal(socket.sent.at(-1).type, "start_match");
});

test("older map revision after the new one never reaches React or rolls B back to A", () => {
  const { client, socket } = lobbyClient();
  const accepted = [];
  client.onRoomState = state => accepted.push(state.map_id);
  socket.receive(lobbyState("seafarers_gold_haven", 2));
  socket.receive(lobbyState("base_12vp", 1));
  socket.receive(lobbyState());
  assert.equal(client.roomState.map_id, "seafarers_gold_haven");
  assert.deepEqual(accepted, ["seafarers_gold_haven"]);
  assert.equal(socket.sent.filter(m => m.type === "set_map").length, 0);
});

test("participant accepts the final B and ignores stale A without sending any map selection", () => {
  const { client, socket } = lobbyClient();
  client.setName("Bob");
  socket.receive(lobbyState("base_12vp", 1));
  client.setMap("base_standard");
  socket.receive(lobbyState("seafarers_gold_haven", 2));
  socket.receive(lobbyState("base_12vp", 1));
  assert.equal(client.youPid, 1);
  assert.equal(client.roomState.map_id, "seafarers_gold_haven");
  assert.equal(client.pendingMapId, null);
  assert.equal(socket.sent.filter(m => m.type === "set_map").length, 0);
});

test("custom JSON keeps its payload and repeated custom IDs require a new revision", () => {
  const { client, socket } = lobbyClient();
  const first = { name: "My map", version: 1, tiles: [{ q: 0, r: 0, terrain: "forest", number: 6 }] };
  client.setMap(undefined, first);
  assert.equal(client.pendingMapId, "My map");
  assert.deepEqual(socket.sent.at(-1), { type: "set_map", map_data: first });
  socket.receive(lobbyState("My map", 1));
  const second = { ...first, tiles: [{ q: 0, r: 0, terrain: "gold", number: 8 }] };
  client.setMap(undefined, second);
  socket.receive(lobbyState("My map", 1));
  assert.equal(client.pendingMapId, "My map");
  assert.deepEqual(socket.sent.at(-1).map_data, second);
  socket.receive(lobbyState("My map", 2));
  assert.equal(client.pendingMapId, null);
});

test("map rejection rolls back or advances the queued selection; unrelated errors do neither", () => {
  const { client, socket } = lobbyClient();
  client.setMap("invalid");
  client.setMap("base_12vp");
  socket.receive({ type: "error", code: "invalid", message: "Other request failed", detail: {} });
  assert.equal(socket.sent.at(-1).map_id, "invalid");
  socket.receive({ type: "error", code: "invalid", message: "Unknown map_id", detail: { request_type: "set_map" } });
  assert.equal(socket.sent.at(-1).map_id, "base_12vp");
  assert.equal(client.pendingMapId, "base_12vp");
  socket.receive(lobbyState("base_12vp", 1));
  assert.equal(client.pendingMapId, null);
  client.setMap("invalid");
  socket.receive({ type: "error", code: "invalid", message: "Unknown map_id", detail: { request_type: "set_map" } });
  assert.equal(client.pendingMapId, null);
  assert.equal(client.roomState.map_id, "base_12vp");
});

test("disconnect drops unconfirmed choices and reconnect displays the authoritative server map", () => {
  const { client, socket } = lobbyClient();
  client.setMap("base_12vp");
  client.setMap("base_standard");
  window.setTimeout = () => 0;
  socket.readyState = 3;
  socket.onclose();
  assert.equal(client.pendingMapId, null);
  client.connect("ws://test/ws", "Alice");
  const replacement = Socket.latest;
  replacement.open();
  assert.equal(replacement.sent.at(-1).type, "reconnect");
  replacement.receive(lobbyState("seafarers_gold_haven", 4));
  assert.equal(client.roomState.map_id, "seafarers_gold_haven");
  assert.equal(replacement.sent.filter(m => m.type === "set_map").length, 0);
});

test("new room resets pending choices and accepts revision zero without inheriting the old map", () => {
  const { client, socket } = lobbyClient();
  socket.receive(lobbyState("base_12vp", 7));
  client.setMap("seafarers_gold_haven");
  client.setMap("base_20vp");
  client.host(2);
  assert.equal(client.pendingMapId, null);
  socket.receive(lobbyState("base_standard", 0, "NEW"));
  socket.receive(lobbyState("seafarers_gold_haven", 8));
  assert.equal(client.roomState.room_code, "NEW");
  assert.equal(client.roomState.map_revision, 0);
  assert.equal(client.roomState.map_id, "base_standard");
  assert.equal(socket.sent.at(-1).type, "create_room");
});

test("rejected ACK consumes sequence and removes the pending intent", () => {
  const { client, socket } = connectedClient();
  client.sendCmd({ type: "place_settlement", vid: 99999 });
  const cmd = socket.sent.at(-1);
  assert.equal(cmd.seq, 5);
  socket.receive({ type: "cmd_ack", cmd_id: cmd.cmd_id, seq: 5,
                   last_seq_applied: 5, applied: false, duplicate: false });
  const before = socket.sent.length;
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 1, last_seq_applied: 5 });
  assert.equal(socket.sent.length, before);
  client.sendCmd({ type: "roll" });
  assert.equal(socket.sent.at(-1).seq, 6);
});

test("reconnect replays only unconsumed commands with the original ID", () => {
  const { client, socket } = connectedClient();
  client.sendCmd({ type: "noop" });
  const consumed = socket.sent.at(-1);
  client.sendCmd({ type: "roll" });
  const pending = socket.sent.at(-1);
  const before = socket.sent.length;
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 1, last_seq_applied: 5 });
  assert.deepEqual(socket.sent.slice(before), [pending]);
  assert.notEqual(consumed.cmd_id, pending.cmd_id);
  socket.receive({ type: "cmd_ack", cmd_id: pending.cmd_id, seq: 6,
                   last_seq_applied: 6, applied: true, duplicate: false });
  const after = socket.sent.length;
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 1, last_seq_applied: 6 });
  assert.equal(socket.sent.length, after);
});

test("new match discards stale commands and restarts sequence at one", () => {
  const { client, socket } = connectedClient();
  client.sendCmd({ type: "roll" });
  const before = socket.sent.length;
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 1,
                   reconnect_token: "secret", match_id: 2, last_seq_applied: 0 });
  assert.equal(socket.sent.length, before);
  socket.receive({ type: "match_state", room_code: "ROOM", match_id: 2, tick: 0,
                   state: { you_pid: 1 } });
  client.sendCmd({ type: "place_settlement", vid: 1 });
  assert.equal(socket.sent.at(-1).match_id, 2);
  assert.equal(socket.sent.at(-1).seq, 1);
  assert.equal(client.youPid, 1);
});

test("a different room scopes sequence even when match IDs are equal", () => {
  const { client, socket } = connectedClient();
  client.sendCmd({ type: "roll" });
  socket.receive({ type: "reconnect_token", room_code: "OTHER", pid: 0,
                   reconnect_token: "other", match_id: 1, last_seq_applied: 0 });
  client.sendCmd({ type: "noop" });
  assert.equal(socket.sent.at(-1).seq, 1);
  assert.equal(socket.sent.at(-1).room_code, "OTHER");
});

test("a late ACK from the previous match cannot advance the new sequence", () => {
  const { client, socket } = connectedClient();
  client.sendCmd({ type: "roll" });
  const previous = socket.sent.at(-1);
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 2, last_seq_applied: 0 });
  socket.receive({ type: "cmd_ack", cmd_id: previous.cmd_id, seq: previous.seq,
                   last_seq_applied: previous.seq, applied: false, duplicate: false });
  client.sendCmd({ type: "noop" });
  assert.equal(socket.sent.at(-1).seq, 1);
});

test("an older snapshot cannot undo a newer tick or reset a new match", () => {
  const { client, socket } = connectedClient();
  socket.receive({ type: "match_state", room_code: "ROOM", match_id: 1, tick: 9,
                   state: { you_pid: 0 } });
  socket.receive({ type: "match_state", room_code: "ROOM", match_id: 1, tick: 8,
                   state: { you_pid: 0 } });
  assert.equal(client.matchState.tick, 9);
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 2, last_seq_applied: 0 });
  socket.receive({ type: "match_state", room_code: "ROOM", match_id: 1, tick: 10,
                   state: { you_pid: 0 } });
  assert.equal(client.matchId, 2);
});

test("a snapshot from a previous room cannot replace the current identity", () => {
  const { client, socket } = connectedClient();
  socket.receive({ type: "reconnect_token", room_code: "OTHER", pid: 1,
                   reconnect_token: "other", match_id: 1, last_seq_applied: 0 });
  socket.receive({ type: "match_state", room_code: "ROOM", match_id: 1, tick: 19,
                   state: { you_pid: 0 } });
  assert.equal(client.youPid, 1);
  client.sendCmd({ type: "noop" });
  assert.equal(socket.sent.at(-1).room_code, "OTHER");
});

test("saved token on an open socket reconnects, including a repeated Join", () => {
  const { client, socket } = connectedClient();
  client.loadToken("ROOM", "Alice");
  const before = socket.sent.length;
  client.join("ROOM");
  socket.receive({ type: "reconnect_token", room_code: "ROOM", pid: 0,
                   reconnect_token: "secret", match_id: 1, last_seq_applied: 4 });
  client.join("ROOM");
  assert.deepEqual(socket.sent.slice(before), [
    { type: "reconnect", room_code: "ROOM", reconnect_token: "secret" },
    { type: "reconnect", room_code: "ROOM", reconnect_token: "secret" },
  ]);
});

test("saved token reconnects after a queued Join socket opens", () => {
  localStorage.setItem("catan_reconnect_ROOM_Alice", JSON.stringify({ token: "saved", pid: 1 }));
  const client = new WSClient();
  client.loadToken("ROOM", "Alice");
  client.setName("Alice");
  client.join("ROOM");
  client.connect("ws://test/ws", "Alice");
  const socket = Socket.latest;
  assert.deepEqual(socket.sent, []);
  socket.open();
  assert.equal(socket.sent[1].type, "reconnect");
  assert.equal(socket.sent[1].reconnect_token, "saved");
  assert.equal(socket.sent.some((msg) => msg.type === "join_room"), false);
});

test("an open socket without a saved token performs an ordinary Join", () => {
  const client = new WSClient();
  client.connect("ws://test/ws", "Bob");
  const socket = Socket.latest;
  socket.open();
  client.loadToken("ROOM", "Bob");
  client.join("ROOM");
  assert.deepEqual(socket.sent.at(-1), { type: "join_room", room_code: "ROOM", name: "Bob" });
});

test("a queued Join without a token runs after the socket opens", () => {
  const client = new WSClient();
  client.loadToken("ROOM", "Bob");
  client.setName("Bob");
  client.join("ROOM");
  client.connect("ws://test/ws", "Bob");
  Socket.latest.open();
  assert.deepEqual(Socket.latest.sent[1], { type: "join_room", room_code: "ROOM", name: "Bob" });
});

test("rejected reconnect reports the error without a Join fallback or retry loop", () => {
  for (const code of ["forbidden", "not_found"]) {
    const { client, socket } = connectedClient();
    let error;
    client.onError = (value) => { error = value; };
    client.loadToken("ROOM", "Alice");
    client.join("ROOM");
    const before = socket.sent.length;
    socket.receive({ type: "error", code, message: "Reconnect rejected" });
    assert.equal(error.code, code);
    assert.equal(socket.sent.length, before);
    assert.equal(localStorage.getItem("catan_reconnect_ROOM_Alice"), null);
    let retry;
    window.setTimeout = (callback) => { retry = callback; return 1; };
    socket.onclose();
    retry();
    Socket.latest.open();
    assert.deepEqual(Socket.latest.sent, [{ type: "hello", version: 1, name: "Alice" }]);
  }
});

test("tokens are scoped to the requested room and player, including cache misses", () => {
  for (const [room, name] of [["OTHER", "Alice"], ["ROOM", "Bob"]]) {
    const { client, socket } = connectedClient();
    client.loadToken(room, name);
    client.setName(name);
    client.join(room);
    assert.deepEqual(socket.sent.at(-1), { type: "join_room", room_code: room, name });
    assert.notEqual(localStorage.getItem("catan_reconnect_ROOM_Alice"), null);
  }
});

test("direct Join to another room does not reuse the current room token", () => {
  const { client, socket } = connectedClient();
  client.join("OTHER");
  assert.deepEqual(socket.sent.at(-1), { type: "join_room", room_code: "OTHER", name: "Alice" });
});

test("creating a room ignores an old token on both open and unopened sockets", () => {
  for (const open of [false, true]) {
    localStorage.setItem("catan_reconnect_ROOM_Alice", JSON.stringify({ token: "old", pid: 0 }));
    const client = new WSClient();
    client.loadToken("ROOM", "Alice");
    if (open) {
      client.connect("ws://test/ws", "Alice");
      Socket.latest.open();
    }
    client.host(4);
    if (!open) {
      client.connect("ws://test/ws", "Alice");
      Socket.latest.open();
    }
    assert.equal(Socket.latest.sent.at(-1).type, "create_room");
    assert.notEqual(localStorage.getItem("catan_reconnect_ROOM_Alice"), null);
  }
});

test("unusable cached tokens clear previous identity instead of reusing it", () => {
  for (const raw of ["broken json", "null", '{"token":0}', '{"token":""}']) {
    const { client, socket } = connectedClient();
    localStorage.setItem("catan_reconnect_OTHER_Alice", raw);
    client.loadToken("OTHER", "Alice");
    client.join("OTHER");
    assert.equal(socket.sent.at(-1).type, "join_room");
    assert.equal(socket.sent.at(-1).room_code, "OTHER");
  }
});

// Pytest supplies a real FastAPI server when Node's native WebSocket is available.
if (process.env.CATAN_TEST_WS_URL) {
  test("real server restores the saved slot through the open-socket Join flow", async (t) => {
    const sockets = [];
    class LiveSocket extends NativeWebSocket {
      sent = [];
      constructor(url) { super(url); sockets.push(this); }
      send(raw) { this.sent.push(JSON.parse(raw)); super.send(raw); }
    }
    globalThis.WebSocket = LiveSocket;
    t.after(async () => {
      window.setTimeout = () => 0;
      await Promise.all(sockets.map((socket) => new Promise((resolve) => {
        if (socket.readyState === NativeWebSocket.CLOSED) return resolve();
        socket.addEventListener("close", resolve, { once: true });
        socket.close();
      })));
    });
    async function waitFor(check) {
      const deadline = Date.now() + 5000;
      while (!check()) {
        assert.ok(Date.now() < deadline, "timed out waiting for the server");
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
    }
    const url = process.env.CATAN_TEST_WS_URL;
    const owner = new WSClient();
    owner.setName("Alice");
    owner.host(2);
    owner.connect(url, "Alice");
    await waitFor(() => owner.roomState && localStorage.getItem(`catan_reconnect_${owner.roomState.room_code}_Alice`));
    const room = owner.roomState.room_code;
    const replacement = new WSClient();
    let updates = 0;
    replacement.onRoomState = () => { updates++; };
    replacement.connect(url, "Alice");
    await waitFor(() => replacement.isOpen());
    replacement.loadToken(room, "Alice");
    replacement.join(room);
    await waitFor(() => replacement.youPid === 0 && updates === 1);
    assert.deepEqual(sockets[1].sent.map((msg) => msg.type), ["hello", "reconnect"]);
    assert.equal(replacement.roomState.players.filter((p) => p.name === "Alice").length, 1);
    replacement.join(room);
    await waitFor(() => updates === 2);
    let revokedError;
    owner.onError = (error) => { revokedError = error; };
    owner.startMatch();
    await waitFor(() => revokedError);
    assert.equal(revokedError.code, "not_found");

    const newcomer = new WSClient();
    newcomer.connect(url, "Bob");
    await waitFor(() => newcomer.isOpen());
    newcomer.loadToken(room, "Bob");
    newcomer.join(room);
    await waitFor(() => newcomer.youPid === 1);
    assert.equal(sockets[2].sent.at(-1).type, "join_room");
    const invalid = new WSClient();
    let rejected;
    invalid.onError = (error) => { rejected = error; };
    localStorage.setItem(`catan_reconnect_${room}_Mallory`, JSON.stringify({ token: "invalid", pid: 0 }));
    invalid.connect(url, "Mallory");
    await waitFor(() => invalid.isOpen());
    invalid.loadToken(room, "Mallory");
    invalid.join(room);
    await waitFor(() => rejected);
    assert.equal(rejected.code, "forbidden");
    assert.equal(invalid.youPid, null);
    assert.equal(invalid.roomState, null);
    assert.deepEqual(sockets[3].sent.map((msg) => msg.type), ["hello", "reconnect"]);
    replacement.startMatch();
    await waitFor(() => replacement.matchState?.match_id === 1 && newcomer.matchState?.match_id === 1);
    replacement.rematch();
    await waitFor(() => replacement.matchState?.match_id === 2 && newcomer.matchState?.match_id === 2);
    assert.equal(replacement.seq, 0);
    assert.equal(replacement.youPid, 0);
  });
}
