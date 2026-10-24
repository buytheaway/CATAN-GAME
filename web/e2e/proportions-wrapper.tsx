// Preview-only opt-in. Production App neither imports this nor reads the query.
import ActualBoard3D from "__OCEAN_ACTUAL_BOARD__";
import { useSyncExternalStore } from "react";
let detail = new URLSearchParams(location.search).get("detail") === "pilot" ? "pilot" : "current";
const listeners = new Set<() => void>();
window.addEventListener("catan-proportions-preview", event => {
  const next = (event as CustomEvent).detail;
  if (next !== "current" && next !== "pilot") return;
  detail = next; listeners.forEach(listener => listener());
});
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export default function ProportionsBoard(props: any) {
  const value = useSyncExternalStore(subscribe, () => detail);
  return <ActualBoard3D {...props} oceanRings={1} oceanFrame={true}
    terrainDetail={new URLSearchParams(location.search).get("source") !== "before" ? value : "current"} />;
}
