import { MeshStandardMaterial, type Material } from "three";

export type WaterAppearance = "current" | "pilot";

const current = {
  cells: ["#286b8b", "#2a6e8c", "#296c87"], side: "#75909c", underlay: "#20526a",
  seam: "#25546a", wave: "#79a6b8", coast: "#416b71", foam: "#83a6a5", foamOpacity: .6,
  gradient: ["#286479", "#1a4e64", "#153a4e", "#0d2333"], outsideWave: "#82bdcc",
  fallback: "#286b8b", fallbackSide: "#18465f", fallbackWave: "#82bdcc",
} as const;
const pilot = {
  cells: ["#2d7087", "#30738a", "#2e6e84"], side: "#5c7781", underlay: "#244d60",
  seam: "#285568", wave: "#6b9aa7", coast: "#3c6973", foam: "#789eaa", foamOpacity: .48,
  gradient: ["#2a6074", "#1e4d62", "#153749", "#0d2333"], outsideWave: "#6b9aa7",
  fallback: "#31758a", fallbackSide: "#25586c", fallbackWave: "#6b9aa7",
} as const;

/** Presentation only. Unknown values keep production appearance. */
export const waterStyle = (appearance: WaterAppearance = "current") => appearance === "pilot" ? pilot : current;

export const SEA_WATER_PILOT = {
  HS_Water_Teal: "#31758a", HS_Water_Light: "#3a8092", HS_Water_Deep: "#2a687f", HS_Water_Edge: "#25586c",
  HS_Swell_Teal: "#3b7f91", HS_Swell_Shade: "#2b667b", HS_Swell_Light: "#488b9a",
  HS_Small_Ripples: "#548c99", HS_Sea_Foam: "#9cbcb9",
} as const;
export const SEA_WATER_ROUGHNESS = .88;

/** Lazy per-scene material leases; never edit the global GLTF template or its wood. */
export function createWaterMaterialCache() {
  const materials = new Map<Material, Material>();
  return {
    get(source: Material): Material {
      if (!(source instanceof MeshStandardMaterial) || !Object.prototype.hasOwnProperty.call(SEA_WATER_PILOT, source.name)) return source;
      if (!materials.has(source)) {
        const owned = source.clone();
        owned.color.set(SEA_WATER_PILOT[source.name as keyof typeof SEA_WATER_PILOT]);
        owned.roughness = SEA_WATER_ROUGHNESS;
        materials.set(source, owned);
      }
      return materials.get(source)!;
    },
    dispose() { materials.forEach(material => material.dispose()); materials.clear(); },
  };
}
