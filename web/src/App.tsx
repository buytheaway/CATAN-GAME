import { useEffect, useMemo, useRef, useState } from "react";
import { defaultWebSocketUrl, WSClient, MatchState, RoomState, ServerError } from "./wsClient";
import LobbyPage from "./components/LobbyPage";
import GamePage from "./components/GamePage";

const WS_DEFAULT = defaultWebSocketUrl();

export default function App() {
  const client = useMemo(() => new WSClient(), []);
  const restored = useRef(false);
  const [status, setStatus] = useState("idle");
  const [room, setRoom] = useState<RoomState | null>(null);
  const [match, setMatch] = useState<MatchState | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<ServerError | null>(null);

  useEffect(() => {
    client.onStatus = setStatus;
    client.onRoomState = (rs) => {
      setRoom(rs);
      setError(null);
    };
    client.onMatchState = (ms) => {
      setMatch(ms);
      setError(null);
    };
    client.onError = (err) => {
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
    <div className={match ? "app app--match" : "app"}>
      {!match && <h2>CATAN LAN Web</h2>}
      {match ? (
        <GamePage
          client={client}
          match={match}
          room={room}
          status={status}
          log={log}
          error={error}
          onBackToLobby={() => {
            client.leaveRoom();
            setMatch(null); setRoom(null); setError(null); setLog([]);
          }}
        />
      ) : (
        <LobbyPage
          client={client}
          room={room}
          status={status}
          wsDefault={WS_DEFAULT}
          error={error}
        />
      )}
    </div>
  );
}
