import type { Resource } from "./actions";
import GameIcon from "./GameIcon";

/** The same resource language in the hand, trade draft and public offer terms. */
export default function ResourceCard({ resource, count = 0, variant = "hand", label, onClick, disabled = false }: {
  resource: Resource; count?: number; variant?: "hand" | "trade" | "option";
  label?: string; onClick?: () => void; disabled?: boolean;
}) {
  const className = `resource-card resource-${resource} resource-card--${variant}${variant === "hand" && !count ? " is-empty" : ""}`;
  const contents = <><span className="resource-count">{variant === "option" && !count ? "+" : count}</span>
    <GameIcon name={resource} /><span className="resource-label">{resource}</span></>;
  const props = { className, "data-resource": resource, "data-count": count,
    "aria-label": label ?? `${resource}: ${count}` };
  return onClick ? <button type="button" {...props} disabled={disabled} onClick={onClick}>{contents}</button>
    : <div {...props}>{contents}</div>;
}
