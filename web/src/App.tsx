import { useEffect, useMemo, useRef, useState } from "react";
import { defaultWebSocketUrl, WSClient, MatchState, RoomState, ServerError } from "./wsClient";
import LobbyPage from "./components/LobbyPage";
import GamePage from "./components/GamePage";
import { AuthProvider, AccountControls } from "./auth/AuthUI";
import { PageShell } from "./shell/PageShell";
import { AudioProvider } from "./audio/AudioProvider";
import LegacyMatchPage from "./components/LegacyMatchPage";
import { needsCompatibility } from "./matchCompatibility";

const WS_DEFAULT = defaultWebSocketUrl();

export default function App() {
  const client = useMemo(() => new WSClient(), []);
  const restored = useRef(false);
  const lobbyRoom = useRef<string | null>(null);
  const freshStart = useRef<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [room, setRoom] = useState<RoomState | null>(null);
  const [match, setMatch] = useState<MatchState | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<ServerError | null>(null);

  useEffect(() => {
    client.onStatus = setStatus;
    client.onRoomState = (rs) => {
      if (rs.status === "lobby") lobbyRoom.current = rs.room_code;
      setRoom(rs);
      if (needsCompatibility(rs)) setMatch(null);
      setError(null);
    };
    client.onMatchState = (ms) => {
      if (lobbyRoom.current === ms.room_code) {
        freshStart.current = `${ms.room_code}:${ms.match_id}`; lobbyRoom.current = null;
      }
      setMatch(ms);
      setError(null);
    };
    client.onError = (err) => {
      if (["session_expired", "seat_taken_over", "seat_not_owned", "unauthenticated"].includes(err.code)) {
        lobbyRoom.current = null; freshStart.current = null;
        setMatch(null); setRoom(null);
      }
      setError(err);
      setLog((prev) => [...prev, `[ERR] ${err.code}: ${err.message}`]);
    };
    client.onLog = (msg) => setLog((prev) => [...prev, `[WS] ${msg}`]);
    if (!restored.current) {
      restored.current = true;
      client.restoreCurrentGame(WS_DEFAULT);
    }
  }, [client]);

  return (
    <AudioProvider><AuthProvider client={client} onExit={() => { lobbyRoom.current = null; freshStart.current = null; setMatch(null); setRoom(null); setError(null); }}>
      {room && needsCompatibility(room) ? (
        <PageShell status={status} account={<AccountControls shell />}>
          <LegacyMatchPage room={room} onHome={() => {
            client.leaveRoom(); lobbyRoom.current = null; freshStart.current = null;
            setMatch(null); setRoom(null); setError(null); setLog([]);
          }} />
        </PageShell>
      ) : match ? (
        <div className="app app--match">
        <GamePage
          client={client}
          match={match}
          room={room}
          status={status}
          log={log}
          error={error}
          freshStart={freshStart.current === `${match.room_code}:${match.match_id}`}
          onBackToLobby={() => {
            client.leaveRoom();
            lobbyRoom.current = null; freshStart.current = null;
            setMatch(null); setRoom(null); setError(null); setLog([]);
          }}
        />
        </div>
      ) : (
        <PageShell status={status} account={<AccountControls shell />}>
        <LobbyPage
          client={client}
          room={room}
          status={status}
          wsDefault={WS_DEFAULT}
          error={error}
          onBackToHome={() => { client.leaveRoom(); lobbyRoom.current = null; freshStart.current = null; setRoom(null); setError(null); setLog([]); }}
        />
        </PageShell>
      )}
    </AuthProvider></AudioProvider>
  );
}
