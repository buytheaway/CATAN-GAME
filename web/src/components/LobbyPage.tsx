import { useEffect, useRef, useState } from "react";
import { RoomState, ServerError, WSClient } from "../wsClient";

export default function LobbyPage({
  client,
  room,
  status,
  wsDefault,
  error,
}: {
  client: WSClient;
  room: RoomState | null;
  status: string;
  wsDefault: string;
  error: ServerError | null;
}) {
  const [url, setUrl] = useState(wsDefault);
  const [name, setName] = useState("Player");
  const [roomCode, setRoomCode] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(4);
  const mapPresets = room?.map_presets ?? [];
  const [mapId, setMapId] = useState("");
  const [customLabel, setCustomLabel] = useState("Custom map: none");
  const isHost = room ? client.youPid === room.host_pid : false;
  const lastSentMap = useRef<string | null>(null);
  const mapRules = room?.map_rules;
  const ruleBits: string[] = [];
  if (mapRules?.target_vp !== undefined) ruleBits.push(`Target VP ${mapRules.target_vp}`);
  if (mapRules?.robber_count !== undefined) ruleBits.push(`Robbers ${mapRules.robber_count}`);
  const ruleText = ruleBits.length ? ` | ${ruleBits.join(" | ")}` : "";

  useEffect(() => {
    const next = room?.map_id || (mapPresets.length ? mapPresets[0].id : "base_standard");
    if (next && next !== mapId) {
      setMapId(next);
    }
  }, [room?.map_id, mapPresets.length, mapId]);

  useEffect(() => {
    if (!room || !isHost || room.status !== "lobby") return;
    if (!mapId) return;
    if (room.map_id === mapId) return;
    if (lastSentMap.current === mapId) return;
    lastSentMap.current = mapId;
    client.setMap(mapId);
  }, [mapId, room, isHost, client]);

  const onHost = () => {
    client.setName(name);
    if (client.isOpen()) {
      client.host(maxPlayers);
      return;
    }
    client.host(maxPlayers);
    client.connect(url, name);
  };

  const onJoin = () => {
    const code = roomCode.trim().toUpperCase();
    if (!code) return;
    client.loadToken(code, name);
    client.setName(name);
    if (client.isOpen()) {
      client.join(code);
      return;
    }
    client.join(code);
    client.connect(url, name);
  };

  return (
    <div className="lobby-grid">
      <div className="panel card">
        <h3>Connection</h3>
        <label className="field">
          <span>Server WS URL</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Room code</span>
          <input value={roomCode} onChange={(e) => setRoomCode(e.target.value)} placeholder="e.g. 9XX7UQ" />
        </label>
        <label className="field">
          <span>Max players</span>
          <input
            type="number"
            value={maxPlayers}
            min={2}
            max={6}
            onChange={(e) => setMaxPlayers(Number(e.target.value))}
          />
        </label>
        <label className="field">
          <span>Map preset</span>
          <select
            value={mapId}
            onChange={(e) => setMapId(e.target.value)}
            disabled={!isHost || room?.status !== "lobby"}
          >
            {mapPresets.length === 0 ? <option value="base_standard">Base Standard</option> : null}
            {mapPresets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Custom map (JSON)</span>
          <input
            type="file"
            accept=".json"
            disabled={!isHost || room?.status !== "lobby"}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const reader = new FileReader();
              reader.onload = () => {
                try {
                  const data = JSON.parse(String(reader.result || ""));
                  const name = data?.name || "Custom Map";
                  const desc = data?.description || "";
                  setCustomLabel(`Custom map: ${name}${desc ? " - " + desc : ""}`);
                  if (isHost && room?.status === "lobby") {
                    client.setMap(undefined, data);
                  }
                } catch (err) {
                  setCustomLabel("Custom map: invalid JSON");
                }
              };
              reader.readAsText(file);
            }}
          />
        </label>
        <div className="muted">{customLabel}</div>
        <div className="row">
          <button onClick={onHost} className="btn primary">Host</button>
          <button onClick={onJoin} className="btn">Join</button>
        </div>
        <div className="status">Status: <strong>{status}</strong></div>
        {error ? <div className="error">Error: {error.message}</div> : null}
      </div>

      <div className="panel card">
        <h3>Room</h3>
        {room ? (
          <div>
            <div className="badge">Room: {room.room_code}</div>
            <div className="muted">Players: {room.players.filter((p) => p.name).length} / {room.max_players}</div>
            {room.map_meta ? (
              <div className="muted">Map: {room.map_meta.name} {room.map_meta.description ? "- " + room.map_meta.description : ""}{ruleText}</div>
            ) : room.map_id ? (
              <div className="muted">Map: {room.map_id}{ruleText}</div>
            ) : null}
            <ul>
              {room.players.map((p) => (
                <li key={p.pid}>
                  P{p.pid + 1}: {p.name || "(empty)"} {p.connected ? "(online)" : ""} {p.pid === room.host_pid ? "[host]" : ""}
                </li>
              ))}
            </ul>
            <button onClick={() => client.startMatch()} className="btn primary" disabled={room.host_pid !== client.youPid || room.players.filter((p) => p.name).length < 2}>
              Start Match
            </button>
          </div>
        ) : (
          <div className="muted">No room yet</div>
        )}
      </div>
    </div>
  );
}
