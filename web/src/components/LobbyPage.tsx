import { useEffect, useState } from "react";
import { RoomState, ServerError, WSClient } from "../wsClient";
import { MatchSettings, PlayerColors } from "./RoomSettings";
import RoomChat from "../game/RoomChat";
import { colorForPlayer } from "../board/colors";
import RecentGames from "./RecentGames";
import { AccountGames, useAuth } from "../auth/AuthUI";
import { Panel, SectionHeader, StatusBadge } from "../shell/PageShell";
import "../game/room.css";

export default function LobbyPage({
  client,
  room,
  status,
  wsDefault,
  error,
  onBackToHome,
}: {
  client: WSClient;
  room: RoomState | null;
  status: string;
  wsDefault: string;
  error: ServerError | null;
  onBackToHome?: () => void;
}) {
  const [url, setUrl] = useState(wsDefault);
  const auth = useAuth();
  const [name, setName] = useState("Player");
  const [roomCode, setRoomCode] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(4);
  const mapPresets = room?.map_presets ?? [];
  const [pendingMapId, setPendingMapId] = useState(client.pendingMapId);
  const [, refreshConfig] = useState(0);
  const mapId = pendingMapId ?? room?.map_id ?? "base_standard";
  const [customLabel, setCustomLabel] = useState("Custom map: none");
  const [copyStatus, setCopyStatus] = useState("");
  const isHost = room ? client.youPid === room.host_pid : false;
  const mapRules = room?.map_rules;
  const ruleBits: string[] = [];
  if (room?.settings?.target_vp !== undefined || mapRules?.target_vp !== undefined)
    ruleBits.push(`Target VP ${room?.settings?.target_vp ?? mapRules?.target_vp}`);
  if (mapRules?.robber_count !== undefined) ruleBits.push(`Robbers ${mapRules.robber_count}`);
  const ruleText = ruleBits.length ? ` | ${ruleBits.join(" | ")}` : "";

  useEffect(() => {
    client.onMapPending = setPendingMapId;
    client.onConfigPending = () => refreshConfig(version => version + 1);
    client.onCapabilities = () => refreshConfig(version => version + 1);
    setPendingMapId(client.pendingMapId);
    return () => { client.onMapPending = undefined; client.onConfigPending = undefined; client.onCapabilities = undefined; };
  }, [client]);

  useEffect(() => { setCustomLabel("Custom map: none"); setCopyStatus(""); }, [room?.room_code]);
  useEffect(() => { if (auth?.user) { setName(auth.user.display_name); setUrl(wsDefault); } }, [auth?.user?.display_name, wsDefault]);

  const onHost = () => {
    if (auth?.user && url !== wsDefault) return;
    if (auth?.user) client.leaveRoom();
    client.setName(name);
    if (!client.isOpen(url)) client.connect(url, name);
    client.host(maxPlayers);
  };

  const onJoin = () => {
    if (auth?.user && url !== wsDefault) return;
    if (auth?.user) client.leaveRoom();
    const code = roomCode.trim().toUpperCase();
    if (!code) return;
    client.loadToken(code, name, url);
    client.setName(name);
    if (!client.isOpen(url)) client.connect(url, name);
    client.join(code);
  };

  const connected = status === "connected";
  const confirmationPending = pendingMapId !== null || client.configPending;
  const onlinePlayers = room?.players.filter(p => p.name && p.connected).length ?? 0;
  const mapName = room?.map_meta?.name ?? room?.map_id ?? "Base Standard";

  const connectionFields = <>
    <label className="field" htmlFor="player-name"><span>Name</span>
      <input id="player-name" value={name} readOnly={!!auth?.user} onChange={e => setName(e.target.value)} aria-describedby="player-name-help" /></label>
    <p className="shell-help" id="player-name-help">{auth?.user ? "Your account display name is used at the table." : "The name other players will see. You can play as a guest."}</p>
    <details className="shell-details"><summary>Advanced connection</summary>
      <label className="field"><span>Server WS URL</span>
        <input value={url} disabled={!!auth?.user} onChange={e => setUrl(e.target.value)} spellCheck={false} /></label>
      <p className="shell-help">{auth?.user ? "Account games use this server and its sign-in session." : "Use the default address unless you are connecting to another server."}</p>
    </details>
  </>;

  return <div className="session-hub">
    {error && <div className="shell-error" role="alert">{error.message}</div>}
    {!room ? <>
      <section className="home-intro" aria-labelledby="home-title">
        <div><p className="shell-eyebrow">Your next island awaits</p><h1 id="home-title">Good company. A new frontier.</h1>
          <p className="home-description">Gather your friends, settle an island, and make your next move. Start a table or pick up where you left off.</p>
          <div className="shell-actions"><a className="btn primary" href="#host-game">Host a game <span aria-hidden="true">↗</span></a>
            <a className="btn" href="#join-game">Join a room</a></div>
        </div>
        <div className="home-chart" aria-hidden="true"><svg viewBox="0 0 320 200" focusable="false">
          <defs><pattern id="chart-hex" width="60" height="104" patternUnits="userSpaceOnUse">
            <path d="M30 0 60 17 60 52 30 69 0 52 0 17Z M0 52 30 69 30 104 M60 52 60 104" fill="none" stroke="currentColor" /></pattern></defs>
          <circle cx="163" cy="100" r="83" fill="none" stroke="currentColor" strokeDasharray="3 7" />
          <rect x="59" y="30" width="207" height="140" fill="url(#chart-hex)" />
          <path d="m46 155 55-12 28-44 62 7 43-54 42-10" fill="none" stroke="currentColor" strokeWidth="2" />
          <g fill="currentColor"><circle cx="101" cy="143" r="4"/><circle cx="129" cy="99" r="4"/><circle cx="191" cy="106" r="4"/><circle cx="234" cy="52" r="4"/></g>
        </svg><span>Build · Trade · Explore</span></div>
      </section>
      <div className="home-recovery"><AccountGames /><RecentGames client={client} wsDefault={wsDefault} error={error} /></div>
      <section className="session-setup" aria-label="Host or join a game">
        <div className="session-identity"><div><p className="shell-eyebrow">Before you sit down</p><h3>Your place at the table</h3></div>
          <div className="identity-fields">{connectionFields}</div></div>
        <div className="session-forms">
          <Panel id="host-game" className="host-panel"><SectionHeader eyebrow="A fresh start" title="Host a game" />
            <p className="shell-description">Open a room, choose an island, and invite your friends.</p>
            <form aria-label="Host game" onSubmit={e => { e.preventDefault(); onHost(); }}>
              <label className="field"><span>Max players</span><input type="number" value={maxPlayers} min={2} max={6} required
                onChange={e => setMaxPlayers(Number(e.target.value))} /></label>
              <p className="shell-help">Choose the map, custom JSON and match rules in your room. At least two connected players are needed to start.</p>
              <button className="btn primary" type="submit">Host</button>
            </form></Panel>
          <Panel id="join-game" className="join-panel"><SectionHeader eyebrow="Meet your friends" title="Join a room" />
            <p className="shell-description">Have an invitation? Enter the room code from your host.</p>
            <form aria-label="Join room" onSubmit={e => { e.preventDefault(); onJoin(); }}>
              <label className="field"><span>Room code</span><input value={roomCode} required
                onChange={e => setRoomCode(e.target.value)} placeholder="e.g. 9XX7UQ" autoCapitalize="characters" autoComplete="off" spellCheck={false} /></label>
              <p className="shell-help">Codes are case-insensitive. To recover your own seat, use Continue above.</p>
              <button className="btn" type="submit">Join</button>
            </form></Panel>
        </div>
      </section>
    </> : <>
      <header className="lobby-heading"><div><p className="shell-eyebrow">Your table</p><h1>Room <span className="room-code">{room.room_code}</span></h1>
        <p className="shell-description">{mapName} <span className="lobby-map-rules">{ruleText}</span></p></div>
        <div className="lobby-heading-actions"><StatusBadge tone={room.status === "lobby" ? "warm" : "live"}>
          {room.status === "lobby" ? "Lobby" : "In Game"}</StatusBadge>
          <span className="shell-help">{room.players.filter(p => p.name).length}/{room.max_players} players · {onlinePlayers} online</span>
          <div className="shell-actions"><button className="btn subtle" onClick={() => {
            void navigator.clipboard?.writeText(room.room_code).then(() => setCopyStatus("Room code copied.")).catch(() => setCopyStatus("Select the room code to copy it."));
            if (!navigator.clipboard) setCopyStatus("Select the room code to copy it.");
          }}>Copy code</button>{onBackToHome && <button className="btn subtle" onClick={onBackToHome}>Back to home</button>}</div>
          {copyStatus && <span className="shell-help" role="status">{copyStatus}</span>}
        </div></header>
      <div className="room-layout"><div className="room-primary">
        <Panel className="room-players" aria-label="Players"><SectionHeader eyebrow="Around the table" title="Players">
          <span className="shell-help">{room.max_players} seats</span></SectionHeader>
          <ul className="lobby-player-list">{room.players.map(p => <li key={p.pid} className={p.name ? "lobby-player" : "lobby-player is-empty"}>
            <span className="lobby-player-seat" style={p.name ? { background: colorForPlayer(p.pid, room.players) } : undefined} aria-hidden="true">{p.pid + 1}</span>
            <div className="lobby-player-name"><strong>{p.name || "Open seat"}</strong>
              <span>{p.name ? p.connected ? "Online" : "Disconnected" : "Waiting for a player"}{p.pid === client.youPid && p.name ? " · You" : ""}</span></div>
            {p.pid === room.host_pid && p.name && <StatusBadge tone="warm">Host</StatusBadge>}
          </li>)}</ul>
          <PlayerColors client={client} room={room} connected={connected} />
          <div className="room-start"><button onClick={() => client.startMatch()} className="btn primary" disabled={confirmationPending || !connected || room.status !== "lobby" || !isHost || onlinePlayers < 2}>Start Match</button>
            <p className="shell-help" role="status">{confirmationPending ? "Confirming room configuration…" : !connected ? "Waiting for the connection to return."
              : room.status !== "lobby" ? "This room already has a match." : !isHost ? "Your host will start the match."
              : onlinePlayers < 2 ? "Invite at least one more player to start." : "At least two players are connected. You can start."}</p></div>
        </Panel>
        <Panel className="room-conversation"><SectionHeader title="Room chat" eyebrow="Before the first roll" />
          <RoomChat messages={room.chat_history ?? []} send={text => client.sendChat(text)} disabled={!connected} /></Panel>
      </div><Panel className="room-configuration" aria-label="Room configuration"><SectionHeader title="The island & the rules" eyebrow={isHost ? "Host controls" : "Chosen by your host"} />
        <div className="room-map"><label className="field"><span>Map preset</span><select aria-label="Map preset" value={mapId}
          onChange={e => client.setMap(e.target.value)} disabled={!isHost || !connected || room.status !== "lobby"}>
          {mapPresets.length === 0 && <option value="base_standard">Base Standard</option>}
          {mapPresets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          {mapId !== "base_standard" && !mapPresets.some(p => p.id === mapId) && <option value={mapId}>{mapId}</option>}
        </select></label>
        {room.map_meta?.description && <p className="shell-help">{room.map_meta.description}</p>}
        <details className="shell-details"><summary>Custom map</summary><label className="field"><span>Custom map (JSON)</span>
          <input type="file" accept=".json" disabled={!isHost || !connected || room.status !== "lobby"} onChange={e => {
            const file = e.target.files?.[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
              if (client.roomState?.room_code !== room.room_code || client.roomState?.status !== "lobby") return;
              try {
                const data = JSON.parse(String(reader.result || ""));
                const mapName = data?.name || "Custom Map", desc = data?.description || "";
                setCustomLabel(`Custom map: ${mapName}${desc ? " - " + desc : ""}`);
                if (isHost && room.status === "lobby") client.setMap(undefined, data);
              } catch { setCustomLabel("Custom map: invalid JSON"); }
            };
            reader.readAsText(file);
          }} /></label><p className="shell-help" role="status">{customLabel}</p></details>
        </div>
        <MatchSettings client={client} room={room} connected={connected} />
        {room.test_mode ? <p className="test-room-warning">Development test room · debug actions enabled for host</p>
          : client.testToolsAvailable && isHost && room.status === "lobby" && <button className="btn subtle"
            disabled={!connected} onClick={() => client.enableTestMode()}>Enable Test Room</button>}
      </Panel></div>
    </>}
  </div>;
}
