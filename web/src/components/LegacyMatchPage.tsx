import type { RoomState } from "../wsClient";
import { Panel, SectionHeader, StatusBadge } from "../shell/PageShell";

export default function LegacyMatchPage({ room, onHome }: { room: RoomState; onHome: () => void }) {
  return <Panel className="legacy-match" aria-label="Match compatibility">
    <SectionHeader title="This match uses an older ruleset" eyebrow={`Room ${room.room_code}`}>
      <StatusBadge tone="warm">Compatibility required</StatusBadge>
    </SectionHeader>
    <p>This saved match uses an older or unverified version of the game rules. Playing,
      automatic turns and rematch are disabled to protect the original state and scores.</p>
    <p>Your saved match and place are preserved. No scores or achievements have been converted.
      You can return Home and host a new game using the current rules.</p>
    <p>Map: {room.map_meta?.name ?? room.map_id} · Players: {room.players.filter(p => p.name).map(p => p.name).join(", ")}</p>
    <button className="btn primary" onClick={onHome}>Back to Home</button>
  </Panel>;
}
