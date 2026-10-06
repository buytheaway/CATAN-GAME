import { useEffect, useState } from "react";
import { RoomState, ServerError, WSClient } from "../wsClient";
import { MatchSettings, PlayerColors } from "./RoomSettings";
import RoomChat from "../game/RoomChat";
import { colorForPlayer } from "../board/colors";
import RecentGames from "./RecentGames";
import "../game/room.css";

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
  const [pendingMapId, setPendingMapId] = useState(client.pendingMapId);
  const [, refreshConfig] = useState(0);
  const mapId = pendingMapId ?? room?.map_id ?? "base_standard";
  const [customLabel, setCustomLabel] = useState("Custom map: none");
  const isHost = room ? client.youPid === room.host_pid : false;
  const mapRules = room?.map_rules;
  const ruleBits: string[] = [];
  if (mapRules?.target_vp !== undefined) ruleBits.push(`Target VP ${mapRules.target_vp}`);
  if (mapRules?.robber_count !== undefined) ruleBits.push(`Robbers ${mapRules.robber_count}`);
  const ruleText = ruleBits.length ? ` | ${ruleBits.join(" | ")}` : "";

  useEffect(() => {
    client.onMapPending = setPendingMapId;
    client.onConfigPending = () => refreshConfig(version => version + 1);
    client.onCapabilities = () => refreshConfig(version => version + 1);
    setPendingMapId(client.pendingMapId);
    return () => { client.onMapPending = undefined; client.onConfigPending = undefined; client.onCapabilities = undefined; };
  }, [client]);

  useEffect(() => { setCustomLabel("Custom map: none"); }, [room?.room_code]);

  const onHost = () => {
    client.setName(name);
    if (!client.isOpen(url)) client.connect(url, name);
    client.host(maxPlayers);
  };

  const onJoin = () => {
    const code = roomCode.trim().toUpperCase();
    if (!code) return;
    client.loadToken(code, name, url);
    client.setName(name);
    if (!client.isOpen(url)) client.connect(url, name);
    client.join(code);
  };

  return (
    <div>
      {!room && <RecentGames client={client} wsDefault={wsDefault} error={error} />}
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
            aria-label="Map preset"
            value={mapId}
            onChange={(e) => client.setMap(e.target.value)}
            disabled={!isHost || room?.status !== "lobby"}
          >
            {mapPresets.length === 0 ? <option value="base_standard">Base Standard</option> : null}
            {mapPresets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
            {mapId !== "base_standard" && !mapPresets.some((p) => p.id === mapId)
              ? <option value={mapId}>{mapId}</option> : null}
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
                if (client.roomState?.room_code !== room?.room_code
                    || client.roomState?.status !== "lobby") return;
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
            <MatchSettings client={client} room={room} connected={status === "connected"} />
            {room.test_mode ? <p className="test-room-warning">Development test room · debug actions enabled for host</p>
              : client.testToolsAvailable && isHost && room.status === "lobby" && <button className="btn"
                disabled={status !== "connected"} onClick={() => client.enableTestMode()}>Enable Test Room</button>}
            <ul>
              {room.players.map((p) => (
                <li key={p.pid}>
                  {p.name && <span className="color-dot" style={{ background: colorForPlayer(p.pid, room.players) }} />}
                  P{p.pid + 1}: {p.name || "(empty)"} {p.connected ? "(online)" : ""} {p.pid === room.host_pid ? "[host]" : ""}
                </li>
              ))}
            </ul>
            <PlayerColors client={client} room={room} connected={status === "connected"} />
            <button onClick={() => client.startMatch()} className="btn primary" disabled={pendingMapId !== null || client.configPending || room.status !== "lobby" || room.host_pid !== client.youPid || room.players.filter((p) => p.name && p.connected).length < 2}>
              Start Match
            </button>
            {(pendingMapId !== null || client.configPending) && <p className="muted">Confirming room configuration…</p>}
            <details className="lobby-chat"><summary>Room chat</summary><RoomChat messages={room.chat_history ?? []}
              send={text => client.sendChat(text)} disabled={status !== "connected"} /></details>
          </div>
        ) : (
          <div className="muted">No room yet</div>
        )}
      </div>
      </div>
    </div>
  );
}
