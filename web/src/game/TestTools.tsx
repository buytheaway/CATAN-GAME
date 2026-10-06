import { useState } from "react";
import type { GameSnapshot } from "./presentation";
import { RESOURCES } from "./presentation";
import { DEV_CARDS, type DevType, type Resource } from "./actions";
import GameOverlay from "./GameOverlay";
import { ActionFeedback, type ActionSubmit } from "./TradePanel";
import type { ServerError } from "../wsClient";

export default function TestTools({ state, waiting, submit, onClose, error = null }: {
  state: GameSnapshot; waiting: boolean; submit: ActionSubmit; onClose: () => void; error?: ServerError | null;
}) {
  const [player, setPlayer] = useState(state.turn);
  const [resource, setResource] = useState<Resource>("wood");
  const [amount, setAmount] = useState(1);
  const [card, setCard] = useState<DevType>("knight");
  const [faces, setFaces] = useState([6, 1]);
  const send = (action: string, fields: Record<string, unknown> = {}) => submit({ type: "test_action", action, ...fields });
  return <GameOverlay id="test-tools" title="Test Tools" modal onClose={onClose}>
    <p className="test-room-warning">Development room only. Every action is validated and logged by the server.</p>
    <ActionFeedback waiting={waiting} error={error} />
    {state.phase !== "main" && <p>Finish initial placement to use test actions.</p>}
    <fieldset disabled={waiting || state.phase !== "main"}><label className="field">Test player<select aria-label="Test player" value={player} onChange={e => setPlayer(Number(e.target.value))}>
      {state.players.map(p => <option value={p.pid} key={p.pid}>{p.name}</option>)}</select></label>
      <div className="test-tools-row"><label className="field">Test resource<select aria-label="Test resource" value={resource} onChange={e => setResource(e.target.value as Resource)}>
        {RESOURCES.map(r => <option key={r}>{r}</option>)}</select></label>
        <label className="field">Test amount<input aria-label="Test amount" type="number" min={1} max={100} value={amount} onChange={e => setAmount(Number(e.target.value))} /></label>
        <button className="game-button" onClick={() => send("give_resources", { player, resource, amount })}>Give resources</button>
        <button className="game-button" onClick={() => send("remove_resources", { player, resource, amount })}>Remove resources</button></div>
      <div className="test-tools-row"><label className="field">Test card<select aria-label="Test card" value={card} onChange={e => setCard(e.target.value as DevType)}>
        {Object.entries(DEV_CARDS).map(([type, info]) => <option key={type} value={type}>{info.name}</option>)}</select></label>
        <button className="game-button" onClick={() => send("give_dev", { player, card })}>Give development card</button></div>
      <div className="test-tools-row">{faces.map((f, i) => <label className="field" key={i}>Next die {i + 1}<select aria-label={`Next die ${i + 1}`} value={f}
        onChange={e => setFaces(current => current.map((v, n) => n === i ? Number(e.target.value) : v))}>
        {[1, 2, 3, 4, 5, 6].map(v => <option key={v}>{v}</option>)}</select></label>)}
        <button className="game-button" onClick={() => send("set_next_dice", { dice: faces })}>Set next dice</button></div>
      <div className="test-tools-row"><button className="game-button" onClick={() => send("force_turn", { player })}>Force turn</button>
        <button className="game-button" onClick={() => send("set_vp", { player, vp: (state.rules_config?.target_vp ?? 10) - 1 })}>Near win</button>
        <button className="game-button" onClick={() => send("trigger_seven")}>Trigger seven</button></div>
    </fieldset>
  </GameOverlay>;
}
