import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { createVisualResources } from "./resources";

const Resources = createContext<ReturnType<typeof createVisualResources> | null>(null);

export function VisualResources({ children }: { children: ReactNode }) {
  const pool = useMemo(createVisualResources, []);
  useEffect(() => {
    pool.retain();
    return () => pool.release();
  }, [pool]);
  return <Resources.Provider value={pool}>{children}</Resources.Provider>;
}

export function useVisualResources() {
  const pool = useContext(Resources);
  if (!pool) throw new Error("Board3D visual resources require a scene provider");
  return pool;
}
