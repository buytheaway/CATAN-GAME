import { useState } from "react";
import type { ServerError, TradeOffer } from "../wsClient";
import { RESOURCES, type GameSnapshot } from "./presentation";
import { addressedOffers, bankTradeReason, maritimeRate, offerCreateReason, offerResponseReason,
  personalPlayer, resourcePayload, type Resource, type ResourceCounts } from "./actions";
import GameOverlay from "./GameOverlay";
import GameIcon from "./GameIcon";

export type ActionSubmit = (cmd: Record<string, unknown>, after?: () => void) => void;
export function ActionFeedback({ error, waiting }: { error: ServerError | null; waiting: boolean }) {
  return <>{error && <p className="action-error" role="alert">{error.message}</p>}
    {waiting && <p role="status">Waiting for server…</p>}</>;
}
export function ResourcePicker({ label, counts, onChange, max, disabled = false }: {
  label: string; counts: ResourceCounts; onChange: (value: ResourceCounts) => void;
  max: (resource: Resource) => number; disabled?: boolean;
}) {
  return <fieldset className="resource-picker"><legend>{label}</legend>{RESOURCES.map(r => {
    const value = counts[r] ?? 0;
    const update = (n: number) => onChange({ ...counts, [r]: Math.max(0, Math.min(max(r), Math.trunc(n) || 0)) });
    return <div className={`picker-row resource-${r}`} key={r}>
      <span><GameIcon name={r} />{r}</span>
      <button className="game-button counter-button" aria-label={`Decrease ${label} ${r}`}
        disabled={disabled || !value} onClick={() => update(value - 1)}>−</button>
      <input aria-label={`${label} ${r}`} type="number" min={0} max={max(r)} value={value}
        disabled={disabled} onChange={e => update(Number(e.target.value))} />
      <button className="game-button counter-button" aria-label={`Increase ${label} ${r}`}
        disabled={disabled || value >= max(r)} onClick={() => update(value + 1)}>+</button>
    </div>;
  })}</fieldset>;
}
function OfferResources({ resources }: { resources: Record<string, number> }) {
  return <div className="offer-resources">{RESOURCES.filter(r => resources[r] > 0).map(r =>
    <span className={`offer-resource resource-${r}`} key={r}><GameIcon name={r} />{resources[r]} {r}</span>)}</div>;
}
export function TradeOffers({ state, pid, waiting, submit }: {
  state: GameSnapshot; pid: number; waiting: boolean; submit: ActionSubmit;
}) {
  const offers = (state.trade_offers ?? []).filter(o => o.from_pid === pid || o.to_pid === pid || o.to_pid === null);
  const name = (id: number) => state.players.find(p => p.pid === id)?.name ?? `Player ${id + 1}`;
  return <div className="trade-offers">{offers.length ? [...offers].reverse().map(o => {
    const own = o.from_pid === pid;
    const acceptReason = offerResponseReason(state, pid, o, true);
    const rejectReason = offerResponseReason(state, pid, o, false);
    return <article className="trade-offer" key={o.offer_id}>
      <div className="offer-heading"><strong>{own ? "You offer" : `${name(o.from_pid)} offers`}</strong>
        <span className="offer-status">{o.status}</span></div>
      <OfferResources resources={o.give} /><span className="offer-for">for</span><OfferResources resources={o.get} />
      <p>{o.to_pid === null ? "To everyone" : `To ${name(o.to_pid)}`}</p>
      {o.status === "active" && <div className="offer-actions">{own ?
        <button className="game-button" disabled={waiting || !!state.pending_action || !!state.game_over}
          onClick={() => submit({ type: "trade_offer_cancel", offer_id: o.offer_id })}>Cancel offer</button> : <>
          <button className="game-button primary-action" disabled={waiting || !!acceptReason} title={acceptReason ?? undefined}
            onClick={() => submit({ type: "trade_offer_accept", offer_id: o.offer_id })}>Accept</button>
          <button className="game-button" disabled={waiting || !!rejectReason} title={rejectReason ?? undefined}
            onClick={() => submit({ type: "trade_offer_decline", offer_id: o.offer_id })}>Reject</button>
        </>}</div>}
      {!own && o.status === "active" && acceptReason && <p>{acceptReason}</p>}
      {!own && o.status === "active" && o.to_pid === null && <p>Reject closes this offer for everyone.</p>}
    </article>;
  }) : <p>No trade offers yet.</p>}</div>;
}

export default function TradePanel({ state, pid, submit, waiting, error, onClose }: {
  state: GameSnapshot; pid: number; submit: ActionSubmit; waiting: boolean; error: ServerError | null; onClose: () => void;
}) {
  const [tab, setTab] = useState<"bank" | "players">(addressedOffers(state, pid).length ? "players" : "bank");
  const [give, setGive] = useState<Resource>("wood"), [get, setGet] = useState<Resource>("ore");
  const [offered, setOffered] = useState<ResourceCounts>({}), [wanted, setWanted] = useState<ResourceCounts>({});
  const [target, setTarget] = useState("everyone");
  const hand = personalPlayer(state, pid)?.res ?? {};
  const bankReason = bankTradeReason(state, pid, give, get);
  const createReason = offerCreateReason(state, pid, offered, wanted);
  const ratio = maritimeRate(state, pid, give);
  return <GameOverlay id="trade-panel" title="Trade" modal onClose={onClose}>
    <div className="action-tabs" role="tablist" aria-label="Trade type">
      {(["bank", "players"] as const).map(t => <button className="game-button" role="tab" key={t}
        aria-selected={tab === t} aria-controls={`trade-${t}`} onClick={() => setTab(t)}>{t === "bank" ? "Bank" : "Players"}</button>)}
    </div>
    <ActionFeedback error={error} waiting={waiting} />
    {tab === "bank" ? <div id="trade-bank" role="tabpanel">
      <div className="bank-exchange">
        <label className="field">Give<select aria-label="Give resource" value={give} disabled={waiting}
          onChange={e => setGive(e.target.value as Resource)}>{RESOURCES.map(r => <option key={r}>{r}</option>)}</select></label>
        <strong className="trade-ratio" aria-label={`Trade ratio ${ratio}:1`}>{ratio}:1</strong>
        <label className="field">Receive<select aria-label="Receive resource" value={get} disabled={waiting}
          onChange={e => setGet(e.target.value as Resource)}>{RESOURCES.map(r => <option key={r}>{r}</option>)}</select></label>
      </div>
      <p className="trade-summary">Give {ratio} {give} · Receive 1 {get}</p>
      {bankReason && <p id="bank-disabled-reason">{bankReason}</p>}
      <button className="game-button primary-action" disabled={waiting || !!bankReason}
        aria-describedby={bankReason ? "bank-disabled-reason" : undefined}
        onClick={() => submit({ type: "trade_bank", give, get, get_qty: 1 })}>Trade with bank</button>
    </div> : <div id="trade-players" role="tabpanel">
      <div className="offer-editor">
        <ResourcePicker label="You give" counts={offered} onChange={setOffered} max={r => hand[r] ?? 0} disabled={waiting} />
        <ResourcePicker label="You want" counts={wanted} onChange={setWanted} max={() => 19} disabled={waiting} />
      </div>
      <label className="field">Target<select aria-label="Offer target" value={target} disabled={waiting}
        onChange={e => setTarget(e.target.value)}><option value="everyone">Everyone</option>
        {state.players.filter(p => p.pid !== pid).map(p => <option value={p.pid} key={p.pid}>{p.name}</option>)}</select></label>
      {createReason && <p>{createReason}</p>}
      <button className="game-button primary-action" disabled={waiting || !!createReason}
        onClick={() => submit({ type: "trade_offer_create", give: resourcePayload(offered), get: resourcePayload(wanted),
          to_pid: target === "everyone" ? null : Number(target) })}>Send offer</button>
      <p>Offers stay open until resolved or the turn ends. To change one, cancel it and send a new offer.</p>
      <TradeOffers state={state} pid={pid} waiting={waiting} submit={submit} />
    </div>}
  </GameOverlay>;
}

export function IncomingTrades({ state, pid, offers, submit, waiting, error, onClose }: {
  state: GameSnapshot; pid: number; offers: TradeOffer[]; submit: ActionSubmit; waiting: boolean;
  error: ServerError | null; onClose: () => void;
}) {
  return <GameOverlay id="incoming-trades" title="Trade offers" onClose={onClose}>
    <ActionFeedback error={error} waiting={waiting} />
    <TradeOffers state={{ ...state, trade_offers: offers }} pid={pid} waiting={waiting} submit={submit} />
  </GameOverlay>;
}
