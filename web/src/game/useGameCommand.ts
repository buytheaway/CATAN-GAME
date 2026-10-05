import { useEffect, useRef, useState } from "react";
import type { WSClient } from "../wsClient";

/** UI waiting is correlated with its own consumed intent, not another player's snapshot. */
export function useGameCommand(client: WSClient, matchKey: string) {
  const pending = useRef<{ id: string; key: string; after?: () => void } | null>(null);
  const [waiting, setWaiting] = useState(false);
  useEffect(() => {
    pending.current = null;
    setWaiting(false);
  }, [matchKey]);
  useEffect(() => {
    const previous = client.onCommandSettled;
    const settled: typeof previous = (id, applied) => {
      previous?.(id, applied);
      const request = pending.current;
      if (!request || request.id !== id) return;
      pending.current = null;
      setWaiting(false);
      if (applied === true) request.after?.();
    };
    client.onCommandSettled = settled;
    return () => { if (client.onCommandSettled === settled) client.onCommandSettled = previous; };
  }, [client]);
  return {
    waiting: waiting && pending.current?.key === matchKey,
    submit(cmd: Record<string, unknown>, after?: () => void) {
      if (pending.current?.key === matchKey || !client.isOpen()) return;
      const id = client.sendCmd(cmd);
      if (!id) return;
      pending.current = { id, key: matchKey, after };
      setWaiting(true);
    },
  };
}
