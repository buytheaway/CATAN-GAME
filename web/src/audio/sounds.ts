export const SOUND_CUES = ["dice_roll", "dice_land", "production", "hand", "road", "settlement", "city",
  "trade_offer", "trade_accept", "trade_cancel", "bank_trade", "dev_buy", "dev_play", "turn",
  "robber", "pirate", "theft", "game_start", "victory", "game_over", "ship", "ship_move"] as const;
export type SoundCue = typeof SOUND_CUES[number];
type Note = { frequency: number; at?: number; duration?: number; gain?: number; type?: OscillatorType; end?: number };
type Rustle = { frequency: number; at?: number; duration?: number; gain?: number };
type Recipe = { notes?: Note[]; noise?: Rustle[] };
const tap = (frequency: number, at = 0, gain = .2): Note => ({ frequency, at, gain, duration: .12, end: frequency * .62 });
const paper = (frequency: number, at = 0, gain = .2): Rustle => ({ frequency, at, gain, duration: .13 });
// Original synthesis recipes: wood contacts, card rustles and soft resonances; no third-party recordings.
const RECIPES: Record<SoundCue, Recipe> = {
  dice_roll: { notes: [0, .12, .27, .43, .6].map((at, i) => tap(180 - i * 12, at, .14)),
    noise: [0, .12, .27, .43, .6].map(at => paper(1350, at, .12)) },
  dice_land: { notes: [tap(140, 0, .26), tap(190, .035, .22)], noise: [paper(800, 0, .18)] },
  production: { notes: [{ frequency: 392, duration: .25, gain: .07, type: "triangle" }], noise: [paper(1100, 0, .22)] },
  hand: { noise: [paper(2000, 0, .2), paper(1600, .09, .14)] },
  road: { notes: [tap(145, 0, .28)], noise: [paper(650, 0, .19)] },
  settlement: { notes: [tap(205, 0, .24), tap(270, .09, .17)], noise: [paper(950, 0, .16)] },
  city: { notes: [tap(180), tap(245, .09), tap(330, .19, .15)], noise: [paper(750, 0, .18)] },
  trade_offer: { notes: [{ frequency: 440, duration: .25, gain: .1, type: "triangle" },
    { frequency: 554.37, at: .13, duration: .28, gain: .08, type: "triangle" }] },
  trade_accept: { notes: [tap(260, 0, .13), tap(390, .12, .1)], noise: [paper(1700, 0, .2)] },
  trade_cancel: { notes: [tap(280, 0, .1), tap(210, .07, .08)] },
  bank_trade: { notes: [tap(320, .1, .16)], noise: [paper(2300, 0, .2), paper(1400, .12, .16)] },
  dev_buy: { notes: [tap(420, .12, .1)], noise: [paper(2400, 0, .24)] },
  dev_play: { notes: [tap(340, 0, .12)], noise: [paper(1000, 0, .23), paper(1700, .07, .15)] },
  turn: { notes: [{ frequency: 261.63, duration: .45, gain: .1, type: "triangle" },
    { frequency: 392, at: .08, duration: .5, gain: .06 }] },
  robber: { notes: [tap(100, 0, .2)], noise: [paper(450, .04, .18)] },
  pirate: { notes: [tap(125, .05, .18)], noise: [{ frequency: 650, duration: .35, gain: .19 }] },
  theft: { noise: [paper(1500, 0, .22), paper(950, .06, .12)] },
  game_start: { notes: [196, 293.66, 392].map((frequency, i) =>
    ({ frequency, at: i * .07, duration: .65, gain: .08, type: "sine" })) },
  victory: { notes: [261.63, 329.63, 392, 523.25].map((frequency, i) =>
    ({ frequency, at: i * .16, duration: .85, gain: .085, type: "sine" })) },
  game_over: { notes: [{ frequency: 392, duration: .6, gain: .07 },
    { frequency: 293.66, at: .22, duration: .65, gain: .075 }] },
  ship: { notes: [tap(310, 0, .2)], noise: [paper(1100, .04, .15)] },
  ship_move: { noise: [{ frequency: 650, duration: .3, gain: .2 }], notes: [tap(195, .14, .1)] },
};

/** Bounded deterministic noise, shared by all voices in one context. */
export function noiseBuffer(context: BaseAudioContext, seconds = .4): AudioBuffer {
  const buffer = context.createBuffer(1, Math.ceil(22050 * seconds), 22050), samples = buffer.getChannelData(0);
  let seed = 0x6ca7a;
  for (let i = 0; i < samples.length; i++) { seed = (1664525 * seed + 1013904223) >>> 0; samples[i] = seed / 0x80000000 - 1; }
  return buffer;
}

export function synthesizeSound(context: BaseAudioContext, bus: AudioNode, noise: AudioBuffer,
  cue: SoundCue, when: number, ended: () => void) {
  const recipe = RECIPES[cue], sources: AudioScheduledSourceNode[] = [], nodes: AudioNode[] = [];
  let remaining = 0, stopped = false, end = when;
  const finish = () => { if (--remaining === 0) { nodes.forEach(n => n.disconnect()); ended(); } };
  const envelope = (at: number, duration: number, level: number) => {
    const gain = context.createGain(); nodes.push(gain); gain.connect(bus);
    gain.gain.setValueAtTime(0, at); gain.gain.linearRampToValueAtTime(level, at + .006);
    gain.gain.exponentialRampToValueAtTime(.0001, at + duration); gain.gain.setValueAtTime(0, at + duration + .01);
    return gain;
  };
  const schedule = (source: AudioScheduledSourceNode, at: number, duration: number) => {
    sources.push(source); nodes.push(source); remaining++; source.onended = finish;
    source.start(at); source.stop(at + duration + .025); end = Math.max(end, at + duration + .025);
  };
  for (const note of recipe.notes ?? []) {
    const at = when + (note.at ?? 0), duration = note.duration ?? .2, source = context.createOscillator();
    source.type = note.type ?? "sine"; source.frequency.setValueAtTime(note.frequency, at);
    if (note.end) source.frequency.exponentialRampToValueAtTime(note.end, at + duration);
    source.connect(envelope(at, duration, note.gain ?? .12)); schedule(source, at, duration);
  }
  for (const rustle of recipe.noise ?? []) {
    const at = when + (rustle.at ?? 0), duration = rustle.duration ?? .15, source = context.createBufferSource();
    source.buffer = noise; const filter = context.createBiquadFilter(); nodes.push(filter);
    filter.type = "lowpass"; filter.frequency.value = rustle.frequency;
    source.connect(filter); filter.connect(envelope(at, duration, rustle.gain ?? .18)); schedule(source, at, duration);
  }
  return { end, stop() {
    if (stopped) return; stopped = true;
    sources.forEach(source => { source.onended = null; try { source.stop(); } catch { /* Already ended. */ } });
    nodes.forEach(node => node.disconnect()); ended();
  } };
}

/** Original nonrhythmic ambient: sustained open voicing with incommensurate slow swells. */
export function ambientMusic(context: AudioContext, bus: AudioNode) {
  const nodes: AudioNode[] = [], sources: AudioScheduledSourceNode[] = [];
  const fade = context.createGain(), now = context.currentTime; nodes.push(fade); fade.connect(bus);
  fade.gain.setValueAtTime(0, now); fade.gain.linearRampToValueAtTime(.7, now + 1.5);
  [146.83, 220, 329.63, 369.99].forEach((frequency, i) => {
    const tone = context.createOscillator(), level = context.createGain(), swell = context.createOscillator(), depth = context.createGain();
    nodes.push(tone, level, swell, depth); sources.push(tone, swell);
    tone.frequency.value = frequency; level.gain.value = .04; depth.gain.value = .018;
    swell.frequency.value = 1 / [17, 23, 31, 37][i]; swell.connect(depth); depth.connect(level.gain);
    tone.connect(level); level.connect(fade); tone.start(); swell.start();
  });
  let stopped = false;
  return { stop(immediate = false) {
    if (stopped) return; stopped = true;
    if (immediate || context.state !== "running") {
      sources.forEach(source => { try { source.stop(); } catch { /* Closed. */ } }); nodes.forEach(node => node.disconnect());
      return;
    }
    const at = context.currentTime; let remaining = sources.length;
    fade.gain.cancelScheduledValues(at);
    fade.gain.setValueAtTime(.7 * Math.min(1, Math.max(0, (at - now) / 1.5)), at);
    fade.gain.linearRampToValueAtTime(0, at + .08);
    sources.forEach(source => {
      source.onended = () => { if (--remaining === 0) nodes.forEach(node => node.disconnect()); };
      source.stop(at + .09);
    });
  } };
}
