import { useEffect, useRef, type ReactNode } from "react";
import GameIcon from "./GameIcon";

/** Drawers are nonmodal; mandatory choices trap focus without changing their server lifecycle. */
export default function GameOverlay({ id, title, children, onClose, modal = false }: {
  id: string; title: string; children: ReactNode; onClose?: () => void; modal?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () => Array.from(panel.current?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input, select, [tabindex="0"]') ?? []);
    (focusable()[0] ?? panel.current)?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape" && close.current) { event.preventDefault(); close.current(); }
      if (modal && event.key === "Tab") {
        const nodes = focusable(), first = nodes[0], last = nodes[nodes.length - 1];
        if (!first) { event.preventDefault(); panel.current?.focus(); }
        else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      if (previous?.isConnected) previous.focus();
    };
  }, [modal]);
  return <div className={modal ? "game-modal-layer" : "game-drawer-layer"}>
    <div ref={panel} className={modal ? "game-choice card panel" : "game-drawer"} id={id}
      role="dialog" aria-modal={modal} aria-labelledby={`${id}-title`} tabIndex={-1}>
      <div className="overlay-heading"><h4 id={`${id}-title`}>{title}</h4>
        {onClose && <button className="game-button icon-button" aria-label={`Close ${title}`} onClick={onClose}>
          <GameIcon name="close" /></button>}</div>
      {children}
    </div>
  </div>;
}
