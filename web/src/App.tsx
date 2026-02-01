import { useEffect, useMemo, useState } from "react";
import { WSClient, MatchState, RoomState, ServerError } from "./wsClient";
import LobbyPage from "./components/LobbyPage";
import GamePage from "./components/GamePage";

const WS_DEFAULT = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";

export default function App() {
  const client = useMemo(() => new WSClient(), []);
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
  }, [client]);

  return (
    <div className="app">
      <h2>CATAN LAN Web</h2>
      {match ? (
        <GamePage
          client={client}
          match={match}
          room={room}
          status={status}
          log={log}
          error={error}
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
