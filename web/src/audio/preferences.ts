export type AudioPreferences = { master: number; sfx: number; music: number; muted: boolean };
export const AUDIO_STORAGE_KEY = "catan_audio_preferences_v1";
export const DEFAULT_AUDIO: Readonly<AudioPreferences> = { master: .7, sfx: .65, music: .12, muted: false };
type StorageLike = Pick<Storage, "getItem" | "setItem">;

function browserStorage(): StorageLike | undefined {
  try { return globalThis.localStorage; } catch { return undefined; }
}
export function volume(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback;
}
export function readAudioPreferences(storage = browserStorage()): AudioPreferences {
  try {
    const data = JSON.parse(storage?.getItem(AUDIO_STORAGE_KEY) ?? "null");
    if (data?.version === 1) return {
      master: volume(data.master, DEFAULT_AUDIO.master), sfx: volume(data.sfx, DEFAULT_AUDIO.sfx),
      music: volume(data.music, DEFAULT_AUDIO.music), muted: typeof data.muted === "boolean" ? data.muted : false,
    };
  } catch { /* Storage is optional; sound never gates the game. */ }
  return { ...DEFAULT_AUDIO };
}
export function writeAudioPreferences(preferences: AudioPreferences, storage = browserStorage()) {
  try { storage?.setItem(AUDIO_STORAGE_KEY, JSON.stringify({ version: 1, ...preferences })); } catch { /* Optional. */ }
}
