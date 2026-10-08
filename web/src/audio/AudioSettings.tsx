import GameIcon from "../game/GameIcon";
import GameOverlay from "../game/GameOverlay";
import { useAudio } from "./AudioProvider";
import type { AudioPreferences } from "./preferences";
import "./audio.css";

function Speaker({ muted }: { muted: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" className="audio-speaker"><path d="M4 9h4l5-4v14l-5-4H4z" />
    {muted ? <path d="m17 9 5 6m0-6-5 6" /> : <><path d="M16 8c3 2 3 6 0 8" /><path d="M19 5c5 4 5 10 0 14" /></>}</svg>;
}
export function AudioButton({ open, onClick, disabled = false }: { open: boolean; onClick: () => void; disabled?: boolean }) {
  const audio = useAudio();
  return audio && <button className={`game-button icon-button audio-entry${audio.state.preferences.muted ? " is-muted" : ""}`}
    aria-label="Audio settings" aria-expanded={open} aria-controls="audio-settings" disabled={disabled}
    title={audio.state.preferences.muted ? "Audio settings · muted" : "Audio settings"} onClick={onClick}>
    <Speaker muted={audio.state.preferences.muted} /></button>;
}
export default function AudioSettings({ onClose }: { onClose: () => void }) {
  const audio = useAudio();
  if (!audio) return null;
  const { manager, state } = audio, p = state.preferences;
  const slider = (key: Exclude<keyof AudioPreferences, "muted">, label: string) => <label className="audio-slider">
    <span>{label}<output>{Math.round(p[key] * 100)}%</output></span>
    <input type="range" aria-label={label} min="0" max="100" step="1" value={Math.round(p[key] * 100)}
      onChange={e => manager.setPreferences({ [key]: Number(e.target.value) / 100 })} /></label>;
  const blocked = state.ready === "unavailable";
  const canPause = state.musicWanted && state.ready !== "blocked";
  return <div className="audio-settings-popover"><GameOverlay id="audio-settings" title="Audio settings" onClose={onClose}>
    <p className="audio-intro">Quiet sounds for the table. Music starts when you press Play.</p>
    {slider("master", "Master volume")}{slider("sfx", "Sound effects volume")}{slider("music", "Music volume")}
    <label className="audio-mute"><input type="checkbox" checked={p.muted} onChange={e => {
      manager.setPreferences({ muted: e.target.checked }); if (!e.target.checked) void manager.unlock(true);
    }} />Mute all audio</label>
    <div className="audio-music"><div><strong>Tabletop ambient</strong><span>Original · continuous · optional</span></div>
      <button className="game-button" disabled={blocked || (!canPause && (p.muted || !p.master || !p.music))}
        onClick={() => manager.setMusic(!canPause)}>{canPause ? "Pause music" : "Play music"}</button></div>
    <button className="game-button audio-test" disabled={blocked || p.muted || !p.master || !p.sfx}
      onClick={() => void manager.unlock(true).then(() => manager.play({ cue: "settlement", id: `test:${performance.now()}` }))}>
      <GameIcon name="settlement" />Test sound</button>
    <p role="status" className="audio-status">{blocked ? "Audio is unavailable in this browser. You can keep playing."
      : state.ready === "blocked" ? "Playback is blocked. Press Test sound or Play music to try again."
      : p.muted ? "All audio is muted. Your volume settings are saved."
      : !state.visible ? "Audio is paused while this tab is hidden."
      : state.musicPlaying ? "Music playing quietly. Preferences are saved on this browser."
      : "Preferences are saved on this browser. Music stays paused after refresh."}</p>
  </GameOverlay></div>;
}
