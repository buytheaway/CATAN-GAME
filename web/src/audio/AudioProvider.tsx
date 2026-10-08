import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import type { MatchState } from "../wsClient";
import { AudioManager } from "./AudioManager";
import { collectSoundEvents, type SoundCursor } from "./SoundEvents";
import { serverDice, type DiceRollVisual } from "../game/dice";

const AudioContext = createContext<AudioManager | null>(null);
export function AudioProvider({ children }: { children: ReactNode }) {
  const [manager] = useState(() => new AudioManager());
  useEffect(() => {
    const release = manager.retain();
    const gesture = (event: Event) => {
      if (!event.isTrusted || (event instanceof KeyboardEvent && (event.repeat || event.ctrlKey || event.metaKey || event.altKey))) return;
      void manager.unlock();
    };
    const visibility = () => manager.setVisible(document.visibilityState !== "hidden");
    visibility(); document.addEventListener("pointerdown", gesture, true); document.addEventListener("keydown", gesture, true);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      document.removeEventListener("pointerdown", gesture, true); document.removeEventListener("keydown", gesture, true);
      document.removeEventListener("visibilitychange", visibility); release();
    };
  }, [manager]);
  return <AudioContext.Provider value={manager}>{children}</AudioContext.Provider>;
}
export function useAudio() {
  const manager = useContext(AudioContext);
  const state = useSyncExternalStore(manager?.subscribe ?? (() => () => {}), manager?.getSnapshot ?? (() => null), manager?.getSnapshot ?? (() => null));
  return manager && state ? { manager, state } : null;
}
export function useMatchAudio(match: MatchState, connected: boolean, freshStart: boolean,
  dice: { reduced: boolean; roll: DiceRollVisual | null }) {
  const audio = useAudio(), manager = audio?.manager, visible = audio?.state.visible ?? false;
  const cursor = useRef<SoundCursor | null>(null);
  const key = `${match.room_code}:${match.match_id}`, state = match.state;
  useEffect(() => { manager?.enterMatch(); return () => manager?.leaveMatch(); }, [manager]);
  useEffect(() => {
    if (!manager) return;
    const live = connected && visible;
    if (!live || cursor.current?.key !== key) manager.cancelEffects();
    const newRoll = cursor.current?.key === key && cursor.current.live && live &&
      (state.game_events ?? []).some(event => event.type === "roll" && event.id > cursor.current!.lastId);
    // The dice hook publishes its authoritative visual start in the next React commit.
    const hasVisualRoll = !!serverDice(state.dice) && Number.isInteger(state.roll_count);
    if (newRoll && hasVisualRoll && !dice.reduced && dice.roll?.id !== `${key}:${state.roll_count}`) return;
    const next = collectSoundEvents(cursor.current, { key, tick: match.tick, state, pid: state.you_pid, live, freshStart,
      reduced: dice.reduced || !hasVisualRoll, diceElapsed: dice.roll ? performance.now() - dice.roll.startedAt : 0 });
    cursor.current = next.cursor; next.sounds.forEach(sound => manager.play(sound));
  }, [manager, key, match.tick, state, connected, visible, freshStart, dice.reduced, dice.roll]);
}
