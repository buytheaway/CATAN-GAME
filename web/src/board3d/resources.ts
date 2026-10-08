import {
  BoxGeometry, BufferGeometry, CircleGeometry, ConeGeometry, CylinderGeometry, ExtrudeGeometry,
  IcosahedronGeometry, MeshBasicMaterial, MeshStandardMaterial, OctahedronGeometry,
  PlaneGeometry, RingGeometry, Shape, SphereGeometry, TorusGeometry,
} from "three";
import { createPieceMaterials } from "./pieceAssets";

function extrude(points: [number, number][], depth: number, bevel: number) {
  const shape = new Shape();
  points.forEach(([x, y], i) => i ? shape.lineTo(x, y) : shape.moveTo(x, y));
  shape.closePath();
  return new ExtrudeGeometry(shape, {
    depth, bevelEnabled: bevel > 0, bevelSize: bevel, bevelThickness: bevel,
    bevelSegments: 1, steps: 1, curveSegments: 1,
  });
}

const factories = {
  box: () => new BoxGeometry(1, 1, 1),
  die: () => {
    const geometry = extrude([[-.37, -.37], [.37, -.37], [.37, .37], [-.37, .37]], .74, .055);
    geometry.translate(0, 0, -.37);
    return geometry;
  },
  plane: () => new PlaneGeometry(1, 1),
  disc: () => new CircleGeometry(1, 24),
  sphere: () => new SphereGeometry(1, 12, 8),
  dome: () => new SphereGeometry(1, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2),
  rock: () => new IcosahedronGeometry(1, 0),
  wool: () => new IcosahedronGeometry(1, 1),
  nugget: () => new OctahedronGeometry(1),
  cone: () => new ConeGeometry(1, 1, 6),
  cylinder: () => new CylinderGeometry(1, 1, 1, 24),
  hex: () => {
    const points = Array.from({ length: 6 }, (_, i): [number, number] =>
      [Math.sin(i * Math.PI / 3) * 0.94, Math.cos(i * Math.PI / 3) * 0.94]);
    const geo = extrude(points, 0.19, 0.03);
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, 0.04, 0); // Top stays exactly at TILE_TOP (0.26).
    return geo;
  },
  port: () => {
    const geo = extrude([[-0.31, -0.23], [0.31, -0.23], [0.31, 0.23], [-0.31, 0.23]], 0.055, 0.01);
    geo.rotateX(-Math.PI / 2);
    return geo;
  },
  road: () => {
    const geo = extrude([[-0.43, -0.065], [0.43, -0.065], [0.43, 0.065], [-0.43, 0.065]], 0.1, 0.012);
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, -0.015, 0);
    return geo;
  },
  house: () => {
    const geo = extrude([[-0.16, 0], [0.16, 0], [0.16, 0.22], [0, 0.36], [-0.16, 0.22]], 0.28, 0.008);
    geo.translate(0, 0, -0.14);
    return geo;
  },
  hull: () => {
    const geo = extrude([[-0.38, 0], [-0.23, -0.12], [0.24, -0.12], [0.4, 0], [0.24, 0.12], [-0.23, 0.12]], 0.12, 0.012);
    geo.rotateX(-Math.PI / 2);
    return geo;
  },
  sail: () => extrude([[-0.14, 0], [0.14, 0], [-0.14, 0.27]], 0.025, 0),
  wave: () => {
    const geo = new TorusGeometry(0.19, 0.012, 3, 12, Math.PI * 0.8);
    geo.rotateX(-Math.PI / 2);
    return geo;
  },
} satisfies Record<string, () => BufferGeometry>;

/** One pool per mounted scene. Only externally owned Three resources live here. */
export function createVisualResources() {
  const geometries = new Map<string, BufferGeometry>();
  const materials = new Map<string, MeshStandardMaterial | MeshBasicMaterial>();
  const pieces = createPieceMaterials();
  let leases = 0;
  const dispose = () => {
    geometries.forEach(g => g.dispose());
    materials.forEach(m => m.dispose());
    geometries.clear();
    materials.clear();
    pieces.dispose();
  };
  return {
    pieces,
    geometry(kind: keyof typeof factories) {
      if (!geometries.has(kind)) geometries.set(kind, factories[kind]());
      return geometries.get(kind)!;
    },
    ring(inner: number, outer: number, segments = 32) {
      const key = `ring:${inner}:${outer}:${segments}`;
      if (!geometries.has(key)) geometries.set(key, new RingGeometry(inner, outer, segments));
      return geometries.get(key)!;
    },
    standard(color: string, ghost = false, glow?: { color: string; intensity: number }, overlay = false) {
      const key = `standard:${color}:${ghost}:${glow?.color ?? "none"}:${glow?.intensity ?? 0}:${overlay}`;
      if (!materials.has(key)) materials.set(key, new MeshStandardMaterial({
        color, roughness: 0.78, transparent: ghost, opacity: ghost ? 0.46 : 1,
        depthWrite: !ghost && !overlay, depthTest: !overlay,
        emissive: glow?.color ?? "#000000", emissiveIntensity: glow?.intensity ?? 0,
      }));
      return materials.get(key)!;
    },
    flat(color: string, opacity = 1, overlay = false) {
      const key = `flat:${color}:${opacity}:${overlay}`;
      if (!materials.has(key)) materials.set(key, new MeshBasicMaterial({
        color, transparent: opacity < 1, opacity, depthWrite: !overlay && opacity === 1, depthTest: !overlay,
      }));
      return materials.get(key)!;
    },
    retain() { leases++; },
    release() {
      leases--;
      // React 18 StrictMode immediately remounts effects. Do not dispose live meshes.
      queueMicrotask(() => { if (leases === 0) dispose(); });
    },
  };
}
