import { useState } from "react";
import type { ResourceCounts } from "./actions";
import { changeResource, countResources, resourcePayload } from "./actions";
import { RESOURCES } from "./presentation";
import ResourceCard from "./ResourceCard";
import GameOverlay from "./GameOverlay";
import { ActionFeedback, type ActionSubmit } from "./TradePanel";
import type { ServerError } from "../wsClient";

export default function DiscardPicker({ hand, required, waiting, submit, error = null }: {
  hand: Record<string, number>; required: number; waiting: boolean; submit: ActionSubmit; error?: ServerError | null;
}) {
  const [selected, setSelected] = useState<ResourceCounts>({});
  const total = countResources(selected);
  const valid = total === required && RESOURCES.every(r => (selected[r] ?? 0) <= (hand[r] ?? 0));
  return <GameOverlay id="discard-choice" title={`Discard ${required} cards`} modal>
    <ActionFeedback waiting={waiting} error={error} />
    <p>Return cards to the bank. Click a card to select; use − to remove.</p>
    <div className="discard-cards">{RESOURCES.map(r => <div key={r} className={`discard-stack${selected[r] ? " is-selected" : ""}`}>
      <ResourceCard resource={r} count={hand[r] ?? 0} label={`Discard ${r}`} disabled={waiting || total >= required || (selected[r] ?? 0) >= (hand[r] ?? 0)}
        onClick={() => setSelected(s => changeResource(s, r, 1, hand[r] ?? 0))} />
      <span>{selected[r] ?? 0} selected</span><button className="game-button" aria-label={`Remove discard ${r}`}
        disabled={waiting || !selected[r]} onClick={() => setSelected(s => changeResource(s, r, -1))}>−</button>
    </div>)}</div>
    <p className="discard-total" role="status">Selected: {total} / {required}</p>
    <button className="game-button primary-action" disabled={waiting || !valid}
      onClick={() => submit({ type: "discard", discards: resourcePayload(selected) })}>Confirm Discard</button>
  </GameOverlay>;
}
