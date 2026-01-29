import { useEffect, useState } from "react";
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
  const isHost = room ? client.youPid === room.host_pid : false;
  const mapRules = room?.map_rules;
  const ruleBits: string[] = [];
  if (mapRules?.target_vp !== undefined) ruleBits.push(`Target VP ${mapRules.target_vp}`);
  if (mapRules?.robber_count !== undefined) ruleBits.push(`Robbers ${mapRules.robber_count}`);
  const ruleText = ruleBits.length ? ` | ${ruleBits.join(" · ")}` : "";

  useEffect(() => {
    const next = room?.map_id || (mapPresets.length ? mapPresets[0].id : "base_standard");
    if (next && next !== mapId) {
      setMapId(next);
    }
  }, [room?.map_id, mapPresets.length, mapId]);

  const onHost = () => {
    client.connect(url, name);
    client.host(maxPlayers);
  };

  const onJoin = () => {
    const code = roomCode.trim().toUpperCase();
    if (!code) return;
    client.loadToken(code, name);
    client.connect(url, name);
    client.join(code);
  };

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "grid", gap: 8, maxWidth: 420 }}>
        <label>
          Server WS URL
          <input value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label>
          Room code
          <input value={roomCode} onChange={(e) => setRoomCode(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label>
          Max players
          <input
            type="number"
            value={maxPlayers}
            min={2}
            max={6}
            onChange={(e) => setMaxPlayers(Number(e.target.value))}
            style={{ width: "100%" }}
          />
        </label>
        <label>
          Map preset
          <select
            value={mapId}
            onChange={(e) => setMapId(e.target.value)}
            disabled={!isHost || room?.status !== "lobby"}
            style={{ width: "100%" }}
          >
            {mapPresets.length === 0 ? <option value="base_standard">Base Standard</option> : null}
            {mapPresets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onHost}>Host</button>
          <button onClick={onJoin}>Join</button>
          <button onClick={() => client.setMap(mapId)} disabled={!isHost || !mapId || room?.status !== "lobby"}>Set Map</button>
        </div>
        <div>Status: {status}</div>
        {error ? <div style={{ color: "crimson" }}>Error: {error.message}</div> : null}
      </div>

      <div style={{ marginTop: 16 }}>
        <h4>Room</h4>
        {room ? (
          <div>
            <div>Room: {room.room_code}</div>
            <div>Players: {room.players.length} / {room.max_players}</div>
            {room.map_meta ? (
              <div>Map: {room.map_meta.name} {room.map_meta.description ? `— ${room.map_meta.description}` : ""}{ruleText}</div>
            ) : room.map_id ? (
              <div>Map: {room.map_id}{ruleText}</div>
            ) : null}
            <ul>
              {room.players.map((p) => (
                <li key={p.pid}>
                  P{p.pid + 1}: {p.name || "(empty)"} {p.connected ? "(online)" : ""} {p.pid === room.host_pid ? "[host]" : ""}
                </li>
              ))}
            </ul>
            <button onClick={() => client.startMatch()} disabled={room.host_pid !== client.youPid || room.players.filter((p) => p.name).length < 2}>
              Start Match
            </button>
          </div>
        ) : (
          <div>No room yet</div>
        )}
      </div>
    </div>
  );
}
