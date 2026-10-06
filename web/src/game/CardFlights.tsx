import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { GameplayEvent } from "../wsClient";
import { RESOURCES } from "./presentation";
import GameIcon from "./GameIcon";
import type { Resource } from "./actions";

type Transfer = { id: string; from: number | "bank"; to: number | "bank"; resource?: Resource; quantity: number; delay: number };
type Flight = Transfer & { x: number; y: number; dx: number; dy: number };
type EventCursor = { key: string; last: number; connected: boolean };

export function liveEvents(previous: EventCursor | null, key: string, connected: boolean, events: GameplayEvent[]) {
  if (!previous || previous.key !== key || !previous.connected || !connected) return [];
  return events.filter(e => e.id > previous.last);
}

/** Read only personalized server events. Never infer theft or opponents' faces from hand deltas. */
export function eventTransfers(event: GameplayEvent): Transfer[] {
  const transfers: Transfer[] = [];
  const add = (from: Transfer["from"], to: Transfer["to"], cards: Record<string, number> | undefined,
    quantity: number, delay = 0) => {
    if (cards) RESOURCES.forEach(r => { if (cards[r] > 0) transfers.push({ id: `${event.id}:${transfers.length}`,
      from, to, resource: r, quantity: cards[r], delay }); });
    else if (quantity > 0) transfers.push({ id: `${event.id}:back`, from, to, quantity, delay });
  };
  if (event.type === "production" && event.player_pid !== undefined)
    add("bank", event.player_pid, event.resources, event.quantity ?? 0, 900);
  if (event.type === "theft" && event.victim_pid !== undefined)
    add(event.victim_pid, event.actor_pid, event.resource ? { [event.resource]: 1 } : undefined, 1, 120);
  if (["discard", "buy_dev", "trade_bank"].includes(event.type))
    add(event.actor_pid, "bank", event.paid, event.quantity ?? 0);
  if (["trade_bank", "choose_gold"].includes(event.type) && event.gained)
    add("bank", event.actor_pid, event.gained, 0, 150);
  return transfers;
}

export default function CardFlights({ events, matchKey, pid, connected, reduced }: {
  events: GameplayEvent[]; matchKey: string; pid: number; connected: boolean; reduced: boolean;
}) {
  const cursor = useRef<EventCursor | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);
  const timers = useRef(new Set<number>());
  useEffect(() => () => { timers.current.forEach(window.clearTimeout); }, []);
  useEffect(() => {
    const last = Math.max(0, ...events.map(e => e.id));
    const previous = cursor.current;
    cursor.current = { key: matchKey, last: previous?.key === matchKey ? Math.max(previous.last, last) : last, connected };
    if (!previous || previous.key !== matchKey || !previous.connected || !connected || reduced) {
      timers.current.forEach(window.clearTimeout); timers.current.clear();
      setFlights([]); return;
    }
    const anchor = (target: Transfer["from"]) => {
      const id = target === pid ? "hand" : target;
      return document.querySelector<HTMLElement>(`[data-motion-anchor="${id}"]`)?.getBoundingClientRect();
    };
    const next = liveEvents(previous, matchKey, connected, events).flatMap(eventTransfers).flatMap(t => {
      const from = anchor(t.from), to = anchor(t.to);
      if (!from || !to || !from.width || !to.width) return [];
      return [{ ...t, x: from.x + from.width / 2, y: from.y + from.height / 2,
        dx: to.x + to.width / 2 - from.x - from.width / 2, dy: to.y + to.height / 2 - from.y - from.height / 2 }];
    });
    if (!next.length) return;
    setFlights(current => [...current, ...next].slice(-30));
    const timer = window.setTimeout(() => {
      setFlights(current => current.filter(f => !next.some(n => n.id === f.id)));
      timers.current.delete(timer);
    }, 2100);
    timers.current.add(timer);
  }, [events, matchKey, connected, reduced, pid]);
  return <div className="card-flight-layer" aria-hidden="true">{flights.map(f =>
    <span key={f.id} data-flight={f.resource ?? "back"} className={`flying-card ${f.resource ? `resource-${f.resource}` : "card-back"}`}
      style={{ left: f.x, top: f.y, "--flight-x": `${f.dx}px`, "--flight-y": `${f.dy}px`, animationDelay: `${f.delay}ms` } as CSSProperties}>
      {f.resource ? <GameIcon name={f.resource} /> : <span>CATAN</span>}<b>{f.quantity}</b>
    </span>)}</div>;
}
