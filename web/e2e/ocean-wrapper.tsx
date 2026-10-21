// Test-only import wrapper: production App never imports this module.
import { useSyncExternalStore } from "react";
import ActualBoard3D from "__OCEAN_ACTUAL_BOARD__";

let options = { rings: Number(new URLSearchParams(location.search).get("rings") ?? 1) as 0 | 1 | 2,
  frame: new URLSearchParams(location.search).get("frame") !== "0" };
const listeners = new Set<() => void>();
window.addEventListener("catan-ocean-preview", event => {
  const detail = (event as CustomEvent).detail;
  if (![0, 1, 2].includes(detail?.rings) || typeof detail?.frame !== "boolean") return;
  options = { rings: detail.rings, frame: detail.frame };
  listeners.forEach(listener => listener());
});
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export default function OceanPreviewBoard(props: any) {
  const value = useSyncExternalStore(subscribe, () => options);
  return <ActualBoard3D {...props} oceanRings={value.rings} oceanFrame={value.frame} />;
}
