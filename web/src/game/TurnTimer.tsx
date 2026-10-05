import { useEffect, useMemo, useState } from "react";
import type { TurnTimerState } from "../wsClient";

export function timerSeconds(timer: TurnTimerState, elapsedMs = 0): number {
  return Math.ceil(Math.max(0, timer.remaining_ms - Math.max(0, elapsedMs)) / 1000);
}

export default function TurnTimer({ timer }: { timer?: TurnTimerState | null }) {
  const anchor = useMemo(() => performance.now(), [timer]);
  const [now, setNow] = useState(anchor);
  useEffect(() => {
    if (!timer || timer.stage === "blocked" || timer.stage === "stopped") return;
    const interval = window.setInterval(() => setNow(performance.now()), 250);
    return () => window.clearInterval(interval);
  }, [timer]);
  if (!timer) return null;
  const seconds = timerSeconds(timer, now - anchor);
  const blocked = timer.stage === "blocked" || timer.stage === "stopped";
  return <span className={`turn-timer${blocked ? " is-blocked" : seconds <= 5 ? " is-urgent" : seconds <= 10 ? " is-warning" : ""}`}
    aria-label={blocked ? "Timer waiting for required action" : `Turn timer: ${seconds} seconds`}
    title={blocked ? "Required action: the server will not choose for you." : timer.stage === "grace" ? "20-second action grace period" : "Server turn deadline"}>
    {blocked ? "Action required" : `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`}
  </span>;
}
