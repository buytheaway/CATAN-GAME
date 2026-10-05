import { useId } from "react";
import GameIcon from "./GameIcon";
import { costPreview, type CostAction } from "./costs";

export default function ActionButton({ action, label, resources, disabled, selected, free = false, reason, onClick }: {
  action: CostAction; label: string; resources: Record<string, number>; disabled: boolean;
  selected?: boolean; free?: boolean; reason?: string | null; onClick: () => void;
}) {
  const id = useId();
  const costs = costPreview(action, resources, free);
  return <span className="cost-action" tabIndex={disabled ? 0 : undefined}
    aria-label={disabled ? `${label} unavailable${reason ? `: ${reason}` : ""}` : undefined}>
    <button className="game-button dock-action" disabled={disabled} aria-pressed={selected}
      aria-describedby={id} onClick={() => { if (!disabled) onClick(); }}>
      <GameIcon name={action} /><span>{label}</span>
    </button>
    <span className="cost-preview" role="tooltip" id={id}>
      <span className="cost-icons">{free ? <strong>Free placement</strong> : costs.map(c =>
        <span key={c.resource} className={`cost-resource resource-${c.resource}${c.available ? "" : " is-missing"}`}
          data-available={c.available} aria-label={`${c.resource} ×${c.quantity}: ${c.available ? "owned" : "missing"}`}>
          <GameIcon name={c.resource} />{c.quantity > 1 && <b>×{c.quantity}</b>}
        </span>)}</span>
      {reason && <span className="cost-reason">{reason}</span>}
    </span>
  </span>;
}
