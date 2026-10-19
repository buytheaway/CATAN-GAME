// Test-only public snapshot harness. Never imported by App or the production bundle.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import GamePage from "../src/components/GamePage";
import { WSClient, type MatchState, type RoomState, type ServerError } from "../src/wsClient";
import { goldDiscoveryFixture, publicFogFixture } from "../tests/fixtures/publicFog";
import { publicShipFixture, shipPreviewChange } from "../tests/fixtures/publicShips";
import { publicShipArtFixture } from "../tests/fixtures/publicShipArt";
import { publicBuildingFixture, buildingPreviewChange, type BuildingPreviewKind } from "../tests/fixtures/publicBuildings";
import { publicThreatFixture, threatPreviewChange, type ThreatPreviewKind } from "../tests/fixtures/publicThreats";
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
const shipArtPreview = new URLSearchParams(location.search).get("shipsart") === "1";
const buildingPreview = new URLSearchParams(location.search).get("buildings") === "1";
const threatPreview = new URLSearchParams(location.search).get("threats") === "1";
const reducedPreview = (shipPreview || shipArtPreview || buildingPreview || threatPreview) && new URLSearchParams(location.search).get("reduce") === "1";
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
      const state = shipArtPreview ? publicShipArtFixture(mode === "large") : threatPreview ? publicThreatFixture(mode === "large") : buildingPreview ? publicBuildingFixture(mode === "large") : shipPreview ? publicShipFixture(mode === "large")
        : mode === "gold" ? goldDiscoveryFixture() : publicFogFixture(mode);
      if (preview && !shipPreview && !shipArtPreview && !buildingPreview && !threatPreview && mode === "partial") {
        // Public fixture geometry only: put the existing real ship on the sea/fog boundary.
        const boundary = state.edges!.find(edge => {
          const adjacent = state.edge_adj_hexes![edge.join(",")];
          return adjacent.includes(1) && adjacent.some(i => state.tiles[i].visibility === "hidden");
        });
        if (boundary) state.occupied_ships = { [boundary.join(",")]: 0 };
      }
      setStatus("connected"); setError(null); matchId++;
      const room: RoomState = { type: "room_state", room_code: "FIXTURE", map_revision: 0, host_pid: 0,
        status: "in_match", max_players: state.players.length,
        players: state.players.map(p => ({ pid: p.pid, name: p.name, color: p.color, connected: true })) };
      FixtureSocket.latest.receive(room);
      FixtureSocket.latest.receive({ type: "match_state", room_code: "FIXTURE", match_id: matchId,
        tick: mode === "gold" ? 2 : 1, state });
    };
    const building = (kind: BuildingPreviewKind, batch = false) => {
      const next = structuredClone(client.matchState)!;
      let changed = buildingPreviewChange(next.state, kind);
      if (batch) changed = buildingPreviewChange(next.state, "settlement") || changed;
      if (!changed) return;
      next.tick++;
      FixtureSocket.latest.receive(next);
    };
    const threat = (kind: ThreatPreviewKind, theft = false) => {
      const next = structuredClone(client.matchState)!;
      next.tick++; threatPreviewChange(next.state, kind, next.tick, theft);
      FixtureSocket.latest.receive(next);
    };
    (window as any).__fogFixture = {
      load,
      building,
      threat,
      theft: () => threat("robber", true),
      threatSequence: async () => {
        const epoch = client.matchState?.match_id;
        for (const kind of ["robber", "pirate", "robber", "pirate"] as const) {
          if (client.matchState?.match_id !== epoch) return;
          threat(kind, true);
          await new Promise(resolve => window.setTimeout(resolve, 250));
        }
      },
      sequence: async () => {
        const epoch = client.matchState?.match_id;
        for (const kind of ["road", "settlement", "upgrade"] as const) {
          if (client.matchState?.match_id !== epoch) return;
          building(kind);
          await new Promise(resolve => window.setTimeout(resolve, 250));
        }
      },
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
      <strong>{shipArtPreview ? "Ship art comparison" : threatPreview ? "Robber & pirate preview" : buildingPreview ? "Construction preview" : shipPreview ? "Ship animation preview" : "Fog visual preview"}</strong><small>Synthetic public snapshots · no server</small>
      <div>
        {threatPreview ? <>
          <button onClick={() => (window as any).__fogFixture.threat("robber")}>Move robber</button>
          <button onClick={() => (window as any).__fogFixture.threat("pirate")}>Move pirate</button>
          <button onClick={() => (window as any).__fogFixture.theft()}>Generic theft</button>
          <button onClick={() => (window as any).__fogFixture.threatSequence()}>Movement sequence</button>
          <button onClick={() => (window as any).__fogFixture.building("road")}>Construct road</button>
          <button onClick={() => (window as any).__fogFixture.ship(false)}>Construct ship</button>
          <a href={reducedPreview ? "?demo=1&threats=1" : "?demo=1&threats=1&reduce=1"}>{reducedPreview ? "Normal motion" : "Reduced motion"}</a>
        </> : buildingPreview ? <>
          <button onClick={() => (window as any).__fogFixture.building("road")}>Construct road</button>
          <button onClick={() => (window as any).__fogFixture.building("settlement")}>Construct settlement</button>
          <button onClick={() => (window as any).__fogFixture.building("upgrade")}>Upgrade city</button>
          <button onClick={() => (window as any).__fogFixture.sequence()}>Build sequence</button>
          <button onClick={() => (window as any).__fogFixture.building("road", true)}>Build together</button>
          <button onClick={() => (window as any).__fogFixture.ship(false)}>Construct ship</button>
          <a href={reducedPreview ? "?demo=1&buildings=1" : "?demo=1&buildings=1&reduce=1"}>{reducedPreview ? "Normal motion" : "Reduced motion"}</a>
        </> : shipPreview || shipArtPreview ? <>
          <button onClick={() => (window as any).__fogFixture.ship(false)}>Construct ship</button>
          <button onClick={() => (window as any).__fogFixture.ship(true)}>Move ship</button>
          <button onClick={() => (window as any).__fogFixture.fleet()}>Multiple ships</button>
          <a href={reducedPreview ? `?demo=1&${shipArtPreview ? "shipsart" : "ships"}=1` : `?demo=1&${shipArtPreview ? "shipsart" : "ships"}=1&reduce=1`}>{reducedPreview ? "Normal motion" : "Reduced motion"}</a>
        </> : <>
          <button onClick={() => (window as any).__fogFixture.reveal(1)}>Reveal one</button>
          <button onClick={() => (window as any).__fogFixture.reveal(2)}>Reveal two</button>
        </>}
        <button onClick={() => (window as any).__fogFixture.load("partial")}>Reset preview</button>
        <button onClick={() => (window as any).__fogFixture.load("large")}>50 tiles</button>
      </div>
      <small>Drag to orbit · scroll to zoom. {shipArtPreview ? "Compare Ship model in the board controls. Four public owner colors; no game commands." : threatPreview ? "Generic theft includes a new public move. No resource identity is displayed." : shipPreview || buildingPreview ? "Reset before replaying each operation. Motion is presentation only." : "Reveal buttons deliver a new public fixture frame."}</small>
    </aside>}
  </> : <p>Loading public fixture…</p>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
