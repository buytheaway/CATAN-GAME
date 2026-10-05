import type { ReactNode } from "react";

// Small native SVG marks: no font, icon package or downloaded image required.
const marks: Record<string, ReactNode> = {
    wood: <><path d="m12 3-6 7h3l-4 6h6v5h2v-5h6l-4-6h3z" /></>,
    brick: <><path d="M3 5h18v5H3zM3 10h18v5H3zM3 15h18v5H3zM12 5v5M8 10v5M16 10v5M12 15v5" /></>,
    sheep: <><path d="M5 10a3 3 0 0 1 4-3 3 3 0 0 1 6 0 4 4 0 0 1 4 6 5 5 0 0 1-6 4H7a4 4 0 0 1-2-7zM7 17v4M15 17v4" /><path d="m19 9 3 2-2 4h-3" /></>,
    wheat: <><path d="M12 21V3m0 7L7 6V3l5 4 5-4v3zm0 6-5-4V9l5 4 5-4v3" /></>,
    ore: <><path d="m5 6 9-3 7 8-5 10-12-2-2-7zM5 6l5 7 11-2M10 13l6 8M10 13l-6 6" /></>,
    roll: <><rect x="3" y="3" width="18" height="18" rx="4" /><path d="M7 7h.01M17 7h.01M12 12h.01M7 17h.01M17 17h.01" strokeWidth="3" /></>,
    build: <><path d="m3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7" /></>,
    settlement: <><path d="m3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7" /></>,
    city: <><path d="M3 21V10l6-5 6 5v11M15 21V3h6v18M7 14h4M17 7h2M17 12h2M2 21h20" /></>,
    road: <><path d="m8 3-4 18m12-18 4 18M12 4v3m0 4v3m0 4v3" /></>,
    ship: <><path d="m3 16 4 5h10l4-5zM12 16V3l7 10h-7M10 6 5 13h5" /></>,
    move_ship: <><path d="m3 16 4 5h10l4-5zM12 16V7l6 6h-6M4 4h7m-2-2 2 2-2 2" /></>,
    robber: <><circle cx="12" cy="6" r="3" /><path d="m9 10-4 11h14l-4-11z" /></>,
    pirate: <><path d="m3 16 4 5h10l4-5zM9 16V3h11v7H9M13 5l4 3m0-3-4 3" /></>,
    trade: <><path d="M3 7h17m-4-4 4 4-4 4M21 17H4m4-4-4 4 4 4" /></>,
    dev: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="m12 7 1.4 3 3.3.4-2.4 2.4.6 3.3-2.9-1.6-2.9 1.6.6-3.3-2.4-2.4 3.3-.4z" /></>,
    end: <><path d="m5 4 12 8-12 8zM20 4v16" /></>,
    log: <><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" strokeWidth="2.5" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    reset: <><path d="M4 9a8 8 0 1 1 0 6M4 3v6h6" /></>,
};
export default function GameIcon({ name }: { name: string }) {
  return <svg className="game-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {marks[name] ?? marks.build}
  </svg>;
}
