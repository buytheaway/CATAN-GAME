import { readAudioPreferences, volume, writeAudioPreferences, type AudioPreferences } from "./preferences";
import { ambientMusic, noiseBuffer, synthesizeSound } from "./sounds";
import type { SoundRequest } from "./SoundEvents";

type Ready = "locked" | "running" | "suspended" | "blocked" | "unavailable";
export type AudioState = { preferences: AudioPreferences; ready: Ready; visible: boolean; musicWanted: boolean; musicPlaying: boolean };
type Voice = { end: number; priority: number; stop: () => void };
type StorageLike = Pick<Storage, "getItem" | "setItem">;
export const MAX_SOUND_VOICES = 6;
export const AUDIO_MIX_LIMITS = { threshold: -12, knee: 12, ratio: 8, attack: .001, release: .15 } as const;
function browserContext(): AudioContext {
  const Constructor = globalThis.AudioContext ?? (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Constructor) throw new Error("Audio unavailable");
  return new Constructor();
}

/** One page-owned context. Sound is optional presentation and never queues locked historical effects. */
export class AudioManager {
  private state: AudioState;
  private listeners = new Set<() => void>();
  private context?: AudioContext;
  private master?: GainNode;
  private sfx?: GainNode;
  private music?: GainNode;
  private limiter?: DynamicsCompressorNode;
  private noise?: AudioBuffer;
  private ambient?: ReturnType<typeof ambientMusic>;
  private voices = new Set<Voice>();
  private seen = new Set<string>();
  private cooldown = new Map<string, number>();
  private active = false;
  private disposed = false;
  private attempted = false;
  private resuming?: Promise<void>;
  private leases = 0;

  constructor(private factory: () => AudioContext = browserContext, private storage?: StorageLike) {
    this.state = { preferences: readAudioPreferences(storage), ready: "locked", visible: true, musicWanted: false, musicPlaying: false };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<AudioState>) {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch }; this.listeners.forEach(listener => listener());
  }
  retain() {
    this.leases++; let released = false;
    return () => {
      if (released) return; released = true; this.leases--;
      // React StrictMode's immediate effect replay reacquires the same context.
      queueMicrotask(() => { if (!this.leases) this.dispose(); });
    };
  }
  unlock(explicitRetry = false): Promise<void> {
    if (this.disposed || !this.state.visible || this.resuming) return this.resuming ?? Promise.resolve();
    if (this.context?.state === "running") return Promise.resolve();
    if (this.attempted && !explicitRetry) return Promise.resolve();
    this.attempted = true;
    try {
      if (!this.context) {
        const context = this.factory(); this.context = context;
        this.master = context.createGain(); this.sfx = context.createGain(); this.music = context.createGain();
        this.limiter = context.createDynamicsCompressor();
        for (const [key, value] of Object.entries(AUDIO_MIX_LIMITS)) this.limiter[key as keyof typeof AUDIO_MIX_LIMITS].value = value;
        this.sfx.connect(this.master); this.music.connect(this.master); this.master.connect(this.limiter); this.limiter.connect(context.destination);
        this.noise = noiseBuffer(context); this.mix();
        context.onstatechange = () => {
          if (this.disposed || this.context !== context) return;
          this.update({ ready: context.state === "running" ? "running" : "suspended" }); this.syncMusic();
        };
      }
      const context = this.context;
      this.resuming = context.resume().then(() => {
        if (this.disposed || this.context !== context) return;
        this.update({ ready: context.state === "running" ? "running" : "blocked" }); this.syncMusic();
      }).catch(() => { this.update({ ready: "blocked" }); }).finally(() => { this.resuming = undefined; });
      return this.resuming;
    } catch {
      this.update({ ready: "unavailable" }); return Promise.resolve();
    }
  }
  setPreferences(patch: Partial<AudioPreferences>) {
    const old = this.state.preferences;
    const preferences = { master: volume(patch.master, old.master), sfx: volume(patch.sfx, old.sfx),
      music: volume(patch.music, old.music), muted: typeof patch.muted === "boolean" ? patch.muted : old.muted };
    writeAudioPreferences(preferences, this.storage); this.update({ preferences });
    if (preferences.muted || !preferences.master || !preferences.sfx) this.cancelEffects();
    this.mix(); this.syncMusic();
  }
  private mix() {
    if (!this.context || !this.master || !this.sfx || !this.music) return;
    const { master, sfx, music, muted } = this.state.preferences, at = this.context.currentTime;
    for (const [node, value] of [[this.master, muted ? 0 : master], [this.sfx, sfx], [this.music, music]] as const) {
      node.gain.cancelScheduledValues(at); node.gain.setTargetAtTime(value, at, .02);
    }
  }
  enterMatch() { this.active = true; this.syncMusic(); }
  leaveMatch() {
    this.active = false; this.cancelEffects(); this.seen.clear(); this.cooldown.clear();
    this.update({ musicWanted: false }); this.syncMusic();
    this.suspendContext();
    this.attempted = false;
  }
  setVisible(visible: boolean) {
    if (visible === this.state.visible) return;
    this.update({ visible });
    if (!visible) { this.cancelEffects(); this.syncMusic(); this.suspendContext(); }
    else if (this.context && this.active && !this.state.preferences.muted && this.state.preferences.master > 0) void this.unlock(true);
    else this.attempted = false;
  }
  private suspendContext() {
    const context = this.context;
    void context?.suspend().then(() => {
      // A rapid hide/show or leave/Continue can finish suspend after the new gesture.
      if (!this.disposed && this.context === context && this.active && this.state.visible
        && !this.state.preferences.muted && this.state.preferences.master > 0) return this.unlock(true);
    }).catch(() => {});
  }
  setMusic(wanted: boolean) {
    this.update({ musicWanted: wanted });
    if (wanted) void this.unlock(true);
    this.syncMusic();
  }
  private syncMusic() {
    const { preferences: p, visible, musicWanted } = this.state;
    const playing = this.active && visible && musicWanted && !p.muted && p.master > 0 && p.music > 0 && this.context?.state === "running";
    if (playing && !this.ambient && this.context && this.music) {
      try { this.ambient = ambientMusic(this.context, this.music); } catch { this.update({ ready: "unavailable" }); }
    } else if (!playing && this.ambient) { this.ambient.stop(!visible || !this.active || p.muted); this.ambient = undefined; }
    if (this.state.musicPlaying !== !!this.ambient) this.update({ musicPlaying: !!this.ambient });
  }
  play(request: SoundRequest): boolean {
    if (this.seen.has(request.id)) return false;
    this.seen.add(request.id); if (this.seen.size > 192) this.seen.delete(this.seen.values().next().value!);
    const { preferences: p, visible } = this.state, context = this.context;
    if (this.disposed || !this.active || !visible || p.muted || !p.master || !p.sfx || context?.state !== "running" || !this.sfx || !this.noise) return false;
    const when = context.currentTime + .008 + Math.max(0, request.delay ?? 0) / 1000, priority = request.priority ?? 3;
    if (["production", "hand"].includes(request.cue)) {
      const last = this.cooldown.get(request.cue);
      if (last != null && when - last < .55) return false;
      this.cooldown.set(request.cue, when);
    }
    if (this.voices.size >= MAX_SOUND_VOICES) {
      const lowest = [...this.voices].sort((a, b) => a.priority - b.priority)[0];
      if (lowest.priority >= priority) return false;
      lowest.stop();
    }
    try {
      let voice: Voice;
      const sound = synthesizeSound(context, this.sfx, this.noise, request.cue, when, () => this.voices.delete(voice));
      voice = { ...sound, priority }; this.voices.add(voice);
      if (request.cue === "victory" && this.music) {
        this.music.gain.cancelScheduledValues(context.currentTime);
        this.music.gain.setTargetAtTime(p.music * .45, when, .04);
        this.music.gain.setTargetAtTime(p.music, sound.end + .15, .3);
      }
      return true;
    } catch { return false; }
  }
  cancelEffects() { [...this.voices].forEach(voice => voice.stop()); this.voices.clear(); this.cooldown.clear(); }
  dispose() {
    if (this.disposed) return;
    this.active = false; this.cancelEffects(); this.ambient?.stop(true); this.ambient = undefined;
    this.disposed = true; this.listeners.clear(); this.seen.clear();
    if (this.context) { this.context.onstatechange = null; void this.context.close().catch(() => {}); }
    [this.master, this.sfx, this.music, this.limiter].forEach(node => node?.disconnect());
    this.context = undefined; this.noise = undefined;
  }
}
