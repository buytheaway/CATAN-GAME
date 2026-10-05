import type { RoomState, WSClient } from "../wsClient";
import { ROOM_COLORS } from "../board/colors";

export function MatchSettings({ client, room, connected }: { client: WSClient; room: RoomState; connected: boolean }) {
  const settings = { dice_mode: "random", starting_player: "random", turn_timer: 0, bank_visibility: "visible",
    target_vp: room.map_rules?.target_vp ?? 10, ...room.settings, ...client.pendingSettings };
  const disabled = !connected || room.status !== "lobby" || client.youPid !== room.host_pid;
  return <fieldset className="room-settings" disabled={disabled}>
    <legend>Match settings {disabled ? "· read only" : "· host"}</legend>
    <div className="room-settings-grid">
      <label className="field"><span>Dice mode</span><select value={settings.dice_mode}
        onChange={e => client.setSettings({ dice_mode: e.target.value as "random" | "balanced" })}>
        <option value="random">Random</option><option value="balanced">Balanced</option></select></label>
      <label className="field"><span>Starting player</span><select value={settings.starting_player}
        onChange={e => client.setSettings({ starting_player: e.target.value as "random" | "host" })}>
        <option value="random">Random</option><option value="host">Host</option></select></label>
      <label className="field"><span>Turn timer</span><select value={settings.turn_timer}
        onChange={e => client.setSettings({ turn_timer: Number(e.target.value) as 0 | 30 | 60 | 90 | 120 })}>
        <option value={0}>Off</option>{[30, 60, 90, 120].map(seconds => <option key={seconds} value={seconds}>{seconds} sec</option>)}</select></label>
      <label className="field"><span>Bank resource counts</span><select value={settings.bank_visibility}
        onChange={e => client.setSettings({ bank_visibility: e.target.value as "visible" | "hidden" })}>
        <option value="visible">Visible</option><option value="hidden">Hidden</option></select></label>
      <label className="field"><span>Target VP</span><select value={settings.target_vp}
        onChange={e => client.setSettings({ target_vp: Number(e.target.value) })}>
        {(settings.target_vp < 3 || settings.target_vp > 30) && <option value={settings.target_vp}>{settings.target_vp} VP (preset)</option>}
        {Array.from({ length: 28 }, (_, i) => i + 3).map(vp => <option key={vp} value={vp}>{vp} VP</option>)}</select></label>
    </div>
    {settings.dice_mode === "balanced" && <p className="settings-hint">Balanced: shuffled 2d6 outcomes, refreshed after 24 rolls. No guaranteed number.</p>}
  </fieldset>;
}

export function PlayerColors({ client, room, connected }: { client: WSClient; room: RoomState; connected: boolean }) {
  const own = room.players.find(p => p.pid === client.youPid);
  const selected = client.pendingColor ?? own?.color;
  return <fieldset className="player-color-picker" disabled={!connected || room.status !== "lobby" || !own}>
    <legend>Your color</legend>
    <div>{Object.entries(ROOM_COLORS).map(([name, color]) => {
      const occupied = room.players.some(p => p.name && p.pid !== client.youPid && p.color === name);
      return <button type="button" key={name} className="color-choice" aria-label={`Choose ${name}`}
        aria-pressed={selected === name} disabled={occupied} title={occupied ? `${name} is occupied` : name}
        onClick={() => client.setColor(name)}><span className="color-dot" style={{ background: color }} />{name}</button>;
    })}</div>
  </fieldset>;
}
