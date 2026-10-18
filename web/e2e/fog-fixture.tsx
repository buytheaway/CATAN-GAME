// Test-only public snapshot harness. Never imported by App or the production bundle.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import GamePage from "../src/components/GamePage";
import { WSClient, type MatchState, type RoomState, type ServerError } from "../src/wsClient";
import { goldDiscoveryFixture, publicFogFixture } from "../tests/fixtures/publicFog";
import { publicShipFixture, shipPreviewChange } from "../tests/fixtures/publicShips";
import "../src/styles.css";
import "../src/shell/shell.css";
import "./fog-preview.css";

class FixtureSocket {
  static OPEN = 1;
  static latest: FixtureSocket;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: Array<Record<string, any>> = [];
  constructor() { FixtureSocket.latest = this; }
  send(raw: string) { this.sent.push(JSON.parse(raw)); }
  receive(message: unknown) { this.onmessage?.({ data: JSON.stringify(message) }); }
  close() { this.readyState = 3; this.onclose?.(); }
}
window.WebSocket = FixtureSocket as unknown as typeof WebSocket;
const client = new WSClient();
let matchId = 0;
const preview = new URLSearchParams(location.search).get("demo") === "1";
const shipPreview = new URLSearchParams(location.search).get("ships") === "1";
const reducedPreview = shipPreview && new URLSearchParams(location.search).get("reduce") === "1";
if (reducedPreview) {
  const native = window.matchMedia.bind(window);
  window.matchMedia = query => {
    const media = native(query);
    if (query === "(prefers-reduced-motion: reduce)") Object.defineProperty(media, "matches", { value: true });
    return media;
  };
}

function Fixture() {
  const [match, setMatch] = useState<MatchState | null>(null);
  const [room, setRoom] = useState<RoomState | null>(null);
  const [status, setStatus] = useState("connected");
  const [error, setError] = useState<ServerError | null>(null);
  useEffect(() => {
    client.onMatchState = setMatch; client.onRoomState = setRoom; client.onStatus = setStatus; client.onError = setError;
    client.connect("ws://public-fixture.invalid/ws", "Explorer"); FixtureSocket.latest.onopen?.();
    const load = (mode: Parameters<typeof publicFogFixture>[0] | "gold" = "partial") => {
      const state = shipPreview ? publicShipFixture(mode === "large")
        : mode === "gold" ? goldDiscoveryFixture() : publicFogFixture(mode);
      if (preview && !shipPreview && mode === "partial") {
        // Public fixture geometry only: put the existing real ship on the sea/fog boundary.
        const boundary = state.edges!.find(edge => {
          const adjacent = state.edge_adj_hexes![edge.join(",")];
          return adjacent.includes(1) && adjacent.some(i => state.tiles[i].visibility === "hidden");
        });
        if (boundary) state.occupied_ships = { [boundary.join(",")]: 0 };
      }
      setStatus("connected"); setError(null); matchId++;
      const room: RoomState = { type: "room_state", room_code: "FIXTURE", map_revision: 0, host_pid: 0,
        status: "in_match", max_players: 2,
        players: state.players.map(p => ({ pid: p.pid, name: p.name, color: p.color, connected: true })) };
      FixtureSocket.latest.receive(room);
      FixtureSocket.latest.receive({ type: "match_state", room_code: "FIXTURE", match_id: matchId,
        tick: mode === "gold" ? 2 : 1, state });
    };
    (window as any).__fogFixture = {
      load,
      snapshot: () => structuredClone(client.matchState),
      publish: (message: MatchState) => FixtureSocket.latest.receive(message),
      status: (value: string) => client.onStatus?.(value),
      reveal: (count = 1) => {
        // Simulates a NEW authorized PUBLIC snapshot, never a trusted hidden assignment.
        const next = structuredClone(client.matchState)!;
        const samples = [["forest", 6], ["sea", null], ["gold", 8]] as const;
        next.state.tiles.filter(tile => tile.visibility === "hidden").slice(0, count).forEach((tile, i) => {
          tile.visibility = "revealed"; [tile.terrain, tile.number] = samples[i % samples.length];
        });
        next.tick++;
        FixtureSocket.latest.receive(next);
      },
      ship: (move = false) => {
        const next = structuredClone(client.matchState)!;
        const changed = shipPreviewChange(next.state, move);
        if (!changed) return;
        next.tick++;
        next.state.game_events!.push({ id: (next.state.game_events!.at(-1)?.id ?? 0) + 1,
          tick: next.tick, at_ms: Date.now(), actor_pid: 0, type: move ? "move_ship" : "build_ship" });
        if (!move) for (const index of next.state.edge_adj_hexes![changed.target.join(",")]) {
          const tile = next.state.tiles[index];
          if (tile.visibility === "hidden") { tile.visibility = "revealed"; tile.terrain = "sea"; tile.number = null; }
        }
        FixtureSocket.latest.receive(next);
      },
      fleet: () => {
        const next = structuredClone(client.matchState)!;
        for (const edge of next.state.edges!.filter(e => next.state.edge_adj_hexes![e.join(",")]
          .some(i => next.state.tiles[i].terrain === "sea")).slice(0, 5))
          next.state.occupied_ships[edge.join(",")] = Number(edge[0] % 2);
        next.tick++; FixtureSocket.latest.receive(next);
      },
      reject: () => FixtureSocket.latest.receive({ type: "error", code: "invalid", message: "Fixture rejected command" }),
      commands: () => FixtureSocket.latest.sent.filter(m => m.type === "cmd"),
      settle: (applied = false) => {
        const cmd = FixtureSocket.latest.sent.filter(m => m.type === "cmd").at(-1);
        if (cmd) FixtureSocket.latest.receive({ type: "cmd_ack", cmd_id: cmd.cmd_id, seq: cmd.seq,
          last_seq_applied: cmd.seq, applied, duplicate: false });
      },
    };
    load(new URLSearchParams(location.search).get("fixture") as Parameters<typeof load>[0] || "partial");
    return () => { delete (window as any).__fogFixture; };
  }, []);
  return match ? <>
    <GamePage client={client} match={match} room={room} status={status} log={[]}
      error={error} onBackToLobby={() => {}} />
    {preview && <aside className="fog-preview" aria-label="Synthetic public Fog preview">
      <strong>{shipPreview ? "Ship animation preview" : "Fog visual preview"}</strong><small>Synthetic public snapshots · no server</small>
      <div>
        {shipPreview ? <>
          <button onClick={() => (window as any).__fogFixture.ship(false)}>Construct ship</button>
          <button onClick={() => (window as any).__fogFixture.ship(true)}>Move ship</button>
          <button onClick={() => (window as any).__fogFixture.fleet()}>Multiple ships</button>
          <a href={reducedPreview ? "?demo=1&ships=1" : "?demo=1&ships=1&reduce=1"}>{reducedPreview ? "Normal motion" : "Reduced motion"}</a>
        </> : <>
          <button onClick={() => (window as any).__fogFixture.reveal(1)}>Reveal one</button>
          <button onClick={() => (window as any).__fogFixture.reveal(2)}>Reveal two</button>
        </>}
        <button onClick={() => (window as any).__fogFixture.load("partial")}>Reset preview</button>
        <button onClick={() => (window as any).__fogFixture.load("large")}>50 tiles</button>
      </div>
      <small>Drag to orbit · scroll to zoom. {shipPreview ? "Reset before replaying each operation. Motion is presentation only." : "Reveal buttons deliver a new public fixture frame."}</small>
    </aside>}
  </> : <p>Loading public fixture…</p>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
