// Test-only material comparison. Production App never imports this module.
import { useSyncExternalStore } from "react";
import ActualBoard3D from "__OCEAN_ACTUAL_BOARD__";

const params = new URLSearchParams(location.search);
let options = { rings: Number(params.get("rings") ?? 1) as 0 | 1 | 2,
  frame: params.get("frame") !== "0", water: params.get("water") === "pilot" ? "pilot" : "current" };
const listeners = new Set<() => void>();
window.addEventListener("catan-ocean-preview", event => {
  const value = (event as CustomEvent).detail;
  if (![0, 1, 2].includes(value?.rings) || typeof value?.frame !== "boolean") return;
  options = { ...options, rings: value.rings, frame: value.frame };
  listeners.forEach(listener => listener());
});
window.addEventListener("catan-water-preview", event => {
  const water = (event as CustomEvent).detail;
  if (water !== "current" && water !== "pilot") return;
  options = { ...options, water }; listeners.forEach(listener => listener());
});
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export default function WaterPreviewBoard(props: any) {
  const value = useSyncExternalStore(subscribe, () => options);
  return <ActualBoard3D {...props} oceanRings={value.rings} oceanFrame={value.frame}
    waterAppearance={params.get("source") === "before" ? "current" : value.water} />;
}
