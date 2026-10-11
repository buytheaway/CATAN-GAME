// Test-only public snapshot harness. Never imported by App or the production bundle.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import GamePage from "../src/components/GamePage";
import { WSClient, type MatchState, type RoomState, type ServerError } from "../src/wsClient";
import { goldDiscoveryFixture, publicFogFixture } from "../tests/fixtures/publicFog";
import "../src/styles.css";
import "../src/shell/shell.css";

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

function Fixture() {
  const [match, setMatch] = useState<MatchState | null>(null);
  const [room, setRoom] = useState<RoomState | null>(null);
  const [status, setStatus] = useState("connected");
  const [error, setError] = useState<ServerError | null>(null);
  useEffect(() => {
    client.onMatchState = setMatch; client.onRoomState = setRoom; client.onStatus = setStatus; client.onError = setError;
    client.connect("ws://public-fixture.invalid/ws", "Explorer"); FixtureSocket.latest.onopen?.();
    const load = (mode: Parameters<typeof publicFogFixture>[0] | "gold" = "partial") => {
      const state = mode === "gold" ? goldDiscoveryFixture() : publicFogFixture(mode);
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
  return match ? <GamePage client={client} match={match} room={room} status={status} log={[]}
    error={error} onBackToLobby={() => {}} /> : <p>Loading public fixture…</p>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
