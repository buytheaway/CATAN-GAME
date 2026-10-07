import type { ReactNode } from "react";
import "./shell.css";

export function Brand() {
  return <div className="shell-brand">
    <span className="shell-studio">Danik Inc. Entertainment</span>
    <span className="shell-product">CATAN.КОЛОНИЗАТОРЫ</span>
  </div>;
}

export function StatusBadge({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "live" | "warm";
}) {
  return <span className={`shell-status shell-status--${tone}`}>{children}</span>;
}

export function PageShell({ children, account, status }: { children: ReactNode; account: ReactNode; status: string }) {
  const labels: Record<string, string> = { idle: "Not connected", connected: "Connected", connecting: "Connecting…",
    reconnecting: "Reconnecting…", disconnected: "Disconnected", closed: "Disconnected" };
  const connection = labels[status] ?? status;
  return <div className="app-shell">
    <header className="shell-header"><Brand />
      <div className="shell-header-actions"><span className="shell-connection" role="status">
        <StatusBadge tone={status === "connected" ? "live" : "neutral"}>{connection}</StatusBadge>
      </span>{account}</div>
    </header>
    <main className="shell-main">{children}</main>
    <footer className="shell-footer"><span>Danik Inc. Entertainment</span><span>A table worth coming back to.</span></footer>
  </div>;
}

export function SectionHeader({ title, eyebrow, children }: { title: string; eyebrow?: string; children?: ReactNode }) {
  return <div className="shell-section-heading"><div>
    {eyebrow && <p className="shell-eyebrow">{eyebrow}</p>}<h3>{title}</h3>
  </div>{children}</div>;
}

export function Panel({ children, className = "", ...props }: {
  children: ReactNode; className?: string; id?: string; "aria-label"?: string;
}) {
  return <section className={`shell-panel ${className}`} tabIndex={props.id ? -1 : undefined} {...props}>{children}</section>;
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="shell-empty"><span className="shell-empty-mark" aria-hidden="true">◇</span>
    <div><strong>{title}</strong><p>{children}</p></div></div>;
}
