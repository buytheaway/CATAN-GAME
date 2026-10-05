import { useState } from "react";
import type { ServerError } from "../wsClient";
import { RESOURCES, type GameSnapshot } from "./presentation";
import { buyDevReason, countResources, DEV_CARDS, devHand, devPlayReason, plentyCommand, plentyReason,
  type DevType, type Resource, type ResourceCounts } from "./actions";
import { ActionFeedback, ResourcePicker, type ActionSubmit } from "./TradePanel";
import GameOverlay from "./GameOverlay";
import GameIcon from "./GameIcon";

export function DevelopmentHand({ state, pid, onCard }: {
  state: GameSnapshot; pid: number; onCard: (type: DevType | null) => void;
}) {
  const hand = devHand(state, pid);
  return <section className="development-hand" aria-label="Your development cards">
    <div className="hud-caption">Development cards</div>
    <div className="dev-mini-cards">{hand.length ? hand.map(c => {
      const reason = devPlayReason(state, pid, c.type);
      return <button className={`dev-mini-card ${reason ? "not-playable" : "playable"}`} key={c.type}
        title={reason ?? "Playable"} onClick={() => onCard(c.type)}
        aria-label={`${c.name}: ${c.count}. ${reason ?? "Playable"}`}>
        <GameIcon name={c.icon} /><span>{c.name}</span><b>{c.count}</b>
        <span className="sr-only">{c.fresh} bought this turn</span>
      </button>;
    }) : <button className="dev-empty" onClick={() => onCard(null)}>No cards · Buy</button>}</div>
  </section>;
}

export default function DevelopmentPanel({ state, pid, selected, submit, waiting, error, onClose, onBoardPlay }: {
  state: GameSnapshot; pid: number; selected: DevType | null; submit: ActionSubmit; waiting: boolean;
  error: ServerError | null; onClose: () => void; onBoardPlay: () => void;
}) {
  const hand = devHand(state, pid);
  const [card, setCard] = useState<DevType | null>(selected);
  const [resources, setResources] = useState<ResourceCounts>({});
  const [monopoly, setMonopoly] = useState<Resource>("wood");
  const purchaseReason = buyDevReason(state, pid);
  const info = card ? DEV_CARDS[card] : null;
  const playReason = card === "year_of_plenty" ? plentyReason(state, pid, resources)
    : card ? devPlayReason(state, pid, card) : "Select a card.";
  const selectedHand = hand.find(c => c.type === card);
  const play = () => {
    if (!card || playReason || waiting) return;
    const cmd = card === "year_of_plenty" ? plentyCommand(resources)
      : card === "monopoly" ? { type: "play_dev", card, r: monopoly } : { type: "play_dev", card };
    submit(cmd, card === "knight" || card === "road_building" ? onBoardPlay : undefined);
  };
  return <GameOverlay id="development-panel" title="Development cards" modal onClose={onClose}>
    <ActionFeedback error={error} waiting={waiting} />
    <div className="dev-purchase"><strong>Buy a development card</strong>
      <p className="dev-cost"><GameIcon name="ore" />1 Ore <GameIcon name="sheep" />1 Sheep <GameIcon name="wheat" />1 Wheat</p>
      {purchaseReason && <p>{purchaseReason}</p>}
      <button className="game-button primary-action" disabled={waiting || !!purchaseReason}
        onClick={() => submit({ type: "buy_dev" })}>Buy Dev Card</button>
    </div>
    <div className="dev-card-list" aria-label="Own card types">{hand.map(c => <button className="game-button dev-card-choice"
      key={c.type} aria-pressed={card === c.type} disabled={waiting} onClick={() => setCard(c.type)}>
      <GameIcon name={c.icon} /><span>{c.name}<small>{c.count} held · {c.fresh} new</small></span>
    </button>)}</div>
    {info && card && <section className="dev-detail" aria-label={info.name}>
      <h5><GameIcon name={info.icon} />{info.name}</h5><p>{info.description}</p>
      {selectedHand && <p>{selectedHand.count - selectedHand.fresh} older · {selectedHand.fresh} bought this turn</p>}
      {card === "year_of_plenty" && <>
        <ResourcePicker label="Choose resources" counts={resources} onChange={setResources} disabled={waiting}
          max={r => state.bank_available?.[r] ? Math.max(0, 2 - countResources(resources) + (resources[r] ?? 0)) : 0} />
        <p>{countResources(resources)} / 2 selected</p>
      </>}
      {card === "monopoly" && <label className="field">Resource<select aria-label="Monopoly resource"
        value={monopoly} disabled={waiting} onChange={e => setMonopoly(e.target.value as Resource)}>
        {RESOURCES.map(r => <option key={r}>{r}</option>)}</select></label>}
      {playReason && <p>{playReason}</p>}
      {card !== "victory_point" && <button className="game-button primary-action" disabled={waiting || !!playReason}
        onClick={play}>Play {info.name}</button>}
    </section>}
    {!hand.length && <p>Your private hand is empty. Bought cards appear after confirmation.</p>}
    <p>One development card may be played per turn; new cards wait until your next turn.</p>
  </GameOverlay>;
}
