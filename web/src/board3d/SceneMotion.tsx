import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useThree } from "@react-three/fiber";
import { FOG_IDLE_HZ } from "./fogPresentation";

type Listener = (seconds: number, delta: number) => void;
type Clock = { seconds: { current: number }; subscribe: (listener: Listener) => () => void };
const Motion = createContext<Clock | null>(null);
export const AMBIENT_HZ = FOG_IDLE_HZ;

/** Shared Fog/ship demand-render clock; finite feedback still uses useFrame. */
export function SceneMotion({ reduced, connected, children }: { reduced: boolean; connected: boolean; children: ReactNode }) {
  const invalidate = useThree(s => s.invalidate);
  const listeners = useRef(new Set<Listener>()), seconds = useRef(0);
  const settings = useRef({ reduced, connected, mounted: true });
  settings.current.reduced = reduced; settings.current.connected = connected;
  const timer = useRef<number>();
  const schedule = useCallback(() => {
    window.clearInterval(timer.current); timer.current = undefined;
    if (!settings.current.mounted || settings.current.reduced || !settings.current.connected
      || document.hidden || !listeners.current.size) return;
    let previous = performance.now();
    timer.current = window.setInterval(() => {
      const now = performance.now(), delta = Math.min(.2, (now - previous) / 1000); previous = now;
      seconds.current += delta;
      listeners.current.forEach(listener => listener(seconds.current, delta));
      invalidate();
    }, 1000 / AMBIENT_HZ);
  }, [invalidate]);
  const clock = useMemo<Clock>(() => ({ seconds, subscribe(listener) {
    listeners.current.add(listener); schedule();
    return () => { listeners.current.delete(listener); schedule(); };
  } }), [schedule]);
  useEffect(() => {
    settings.current.mounted = true; schedule();
    document.addEventListener("visibilitychange", schedule);
    return () => { settings.current.mounted = false; window.clearInterval(timer.current);
      document.removeEventListener("visibilitychange", schedule); };
  }, [schedule, connected, reduced]);
  return <Motion.Provider value={clock}>{children}</Motion.Provider>;
}

export function useAmbientMotion(listener: Listener, enabled: boolean) {
  const clock = useContext(Motion), latest = useRef(listener); latest.current = listener;
  if (!clock) throw new Error("Ambient motion requires SceneMotion");
  useEffect(() => enabled ? clock.subscribe((seconds, delta) => latest.current(seconds, delta)) : undefined,
    [clock, enabled]);
  return clock.seconds;
}
