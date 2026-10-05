import { useEffect, useRef, useState, type CSSProperties } from "react";
import { DIE_PIPS, DICE_DURATION_MS, isNewRoll, serverDice, type DiceFaces, type DiceRollVisual } from "./dice";

export function useDicePresentation(key: string, value: unknown, count = 0) {
  const faces = serverDice(value);
  const [reduced, setReduced] = useState(() => typeof window !== "undefined"
    && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const previous = useRef<{ key: string; count: number } | null>(null);
  const [roll, setRoll] = useState<DiceRollVisual | null>(null);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const change = () => setReduced(query.matches);
    change(); query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const animate = isNewRoll(previous.current, key, count);
    previous.current = { key, count };
    if (!faces || !animate || reduced) { setRoll(null); return; }
    setRoll({ id: `${key}:${count}`, faces, startedAt: performance.now() });
    const timer = window.setTimeout(() => setRoll(null), DICE_DURATION_MS + 80);
    return () => window.clearTimeout(timer);
  }, [key, count, faces?.[0], faces?.[1], reduced]);
  return { faces, roll, reduced };
}

export default function DiceHUD({ faces, roll, total }: { faces: DiceFaces | null; roll: DiceRollVisual | null; total?: number | null }) {
  return <section className="dice-hud" aria-label="Dice" aria-live="polite" aria-busy={!!roll}>
    <div className={`dice-pair${roll ? " is-rolling" : ""}`} key={roll?.id ?? "settled"}>
      {[0, 1].map(i => <span className="die-face" role="img" key={i}
        aria-label={faces ? `Die ${i + 1}: ${faces[i]}` : `Die ${i + 1}: not rolled`} data-face={faces?.[i] ?? "unknown"}>
        {faces ? DIE_PIPS[faces[i]].map(([x, y]) => <i className="die-pip" key={`${x}:${y}`}
          style={{ "--pip-x": x, "--pip-y": y } as CSSProperties} />) : <span className="die-placeholder">?</span>}
      </span>)}
    </div>
    <span className="dice-total">{faces ? `${faces[0]} + ${faces[1]} = ${faces[0] + faces[1]}`
      : total != null ? `Total ${total} · faces unavailable` : "Ready to roll"}</span>
  </section>;
}
