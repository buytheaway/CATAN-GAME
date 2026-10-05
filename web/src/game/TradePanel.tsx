import { useEffect } from "react";
import type { ServerError, TradeOffer } from "../wsClient";
import { RESOURCES, type GameSnapshot } from "./presentation";
import { bankDraftCommand, bankDraftReason, changeResource, maritimeRate, offerCreateReason, offerResponseReason,
  resourcePayload, type Resource, type ResourceCounts, type TradeDraft } from "./actions";
import GameOverlay from "./GameOverlay";
import GameIcon from "./GameIcon";
import ResourceCard from "./ResourceCard";

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
    <ResourceCard key={r} resource={r} count={resources[r]} variant="trade" />)}</div>;
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
      <div className="offer-terms"><div><span className="tray-caption">Gives</span><OfferResources resources={o.give} /></div>
        <div><span className="tray-caption">Wants</span><OfferResources resources={o.get} /></div></div>
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

export default function TradePanel({ state, pid, draft, onChange, targets, submit, waiting, error, onClose }: {
  draft: TradeDraft; onChange: (draft: TradeDraft) => void; targets: { pid: number; name: string }[];
  state: GameSnapshot; pid: number; submit: ActionSubmit; waiting: boolean; error: ServerError | null; onClose: () => void;
}) {
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } };
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("keydown", escape); if (previous?.isConnected) previous.focus(); };
  }, [onClose]);
  const bank = draft.target === "bank";
  const give = RESOURCES.filter(r => (draft.give[r] ?? 0) > 0);
  const availableTarget = ["everyone", "bank"].includes(draft.target) || targets.some(p => String(p.pid) === draft.target);
  const reason = !availableTarget ? "This player is disconnected. Choose another target."
    : bank ? bankDraftReason(state, pid, draft) : offerCreateReason(state, pid, draft.give, draft.want);
  const ratio = give.length === 1 ? maritimeRate(state, pid, give[0]) : null;
  const send = () => {
    if (waiting || reason) return;
    submit(bank ? bankDraftCommand(draft) : { type: "trade_offer_create", give: resourcePayload(draft.give),
      get: resourcePayload(draft.want), to_pid: draft.target === "everyone" ? null : Number(draft.target) }, onClose);
  };
  return <section className="trade-tray" id="trade-tray" role="dialog" aria-label="Trade tray" aria-modal="false" aria-busy={waiting}>
    <div className="tray-heading"><label>Trade with<select aria-label="Offer target" value={draft.target} disabled={waiting}
      onChange={e => onChange({ ...draft, target: e.target.value })}>
      <option value="everyone">Everyone</option>
      {targets.filter(p => p.pid !== pid).map(p => <option value={p.pid} key={p.pid}>{p.name}</option>)}
      <option value="bank">Bank</option>
      {!availableTarget && <option value={draft.target}>Disconnected player</option>}
    </select></label><button className="game-button icon-button" aria-label="Close Trade" onClick={onClose}><GameIcon name="close" /></button></div>
    <ActionFeedback error={error} waiting={waiting} />
    <div className="tray-want"><span className="tray-caption">{bank ? "You get" : "You want"}</span>
      <div className="tray-palette">{RESOURCES.map(r => <span className="wanted-option" key={r}>
        <ResourceCard resource={r} count={draft.want[r] ?? 0} variant="option" label={`Want ${r}`}
          disabled={waiting} onClick={() => onChange({ ...draft, want: changeResource(draft.want, r, 1) })} />
        {!!draft.want[r] && <button className="remove-card" aria-label={`Remove wanted ${r}`} disabled={waiting}
          onClick={() => onChange({ ...draft, want: changeResource(draft.want, r, -1) })}>×</button>}
      </span>)}</div>
    </div>
    <div className="tray-give"><span className="tray-caption">You give</span><div className="tray-selected">
      {give.map(r => <ResourceCard key={r} resource={r} count={draft.give[r]} variant="trade"
        label={`Remove give ${r}`} disabled={waiting}
        onClick={() => onChange({ ...draft, give: changeResource(draft.give, r, -1) })} />)}
      {!give.length && <span className="tray-hint">Click cards in your hand to give.</span>}
      {bank && ratio && <strong className="trade-ratio" aria-label={`Trade ratio ${ratio}:1`}>{ratio}:1</strong>}
      <button className="game-button primary-action" disabled={waiting || !!reason} onClick={send}>
        {bank ? "Trade with bank" : "Send offer"}</button>
    </div></div>
    {reason && <p className="tray-hint" role="status">{reason}</p>}
  </section>;
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
