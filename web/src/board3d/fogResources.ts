import { Color, Float32BufferAttribute, MeshBasicMaterial, MeshStandardMaterial, ShaderMaterial } from "three";
import { MarchingCubes } from "three/examples/jsm/objects/MarchingCubes.js";

const noise = /* glsl */`
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
    return mix(mix(hash(i), hash(i+vec2(1.,0.)),f.x),
      mix(hash(i+vec2(0.,1.)), hash(i+vec2(1.,1.)),f.x),f.y);
  }
`;

/** One identical, terrain-independent cloud cluster for every hidden hex. */
export function createFogResources() {
  const time = { value: 0 };
  // Build one smooth union ONCE, not overlapping translucent spheres or a volumetric pass.
  const temporaryMaterial = new MeshStandardMaterial();
  const surface = new MarchingCubes(24, temporaryMaterial, false, false, 5000);
  surface.isolation = 35;
  [[.34, .50, .35], [.57, .56, .35], [.70, .48, .55], [.35, .53, .65], [.52, .62, .62]]
    .forEach(([x, y, z]) => surface.addBall(x, y, z, 1.2, 12));
  surface.update();
  const cloud = surface.geometry, count = cloud.drawRange.count;
  for (const key of ["position", "normal"]) {
    cloud.setAttribute(key, new Float32BufferAttribute(cloud.getAttribute(key).array.slice(0, count * 3), 3));
  }
  cloud.scale(1, .50, 1); cloud.translate(0, .35, 0);
  cloud.computeBoundingSphere(); temporaryMaterial.dispose();
  const material = (haze: boolean) => new ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { uTime: time, uOpacity: { value: 1 }, uHaze: { value: haze ? 1 : 0 },
      uLight: { value: new Color("#ecf3ef") }, uShade: { value: new Color("#88a9ba") } },
    vertexShader: /* glsl */`
      uniform float uTime;
      varying vec3 vPoint; varying vec3 vNormal; varying vec3 vView; varying float vLight;
      void main() {
        vec3 p = position;
        p.y += .012 * sin(p.x * 4. + p.z * 3. + uTime * .5);
        p.x += .012 * sin(p.z * 3. + uTime * .35);
        vPoint = p; vNormal = normalize(normalMatrix * normal);
        vLight = dot(normalize(normal), normalize(vec3(-.6, 1., .4)));
        vec4 view = modelViewMatrix * vec4(p, 1.); vView = -view.xyz;
        gl_Position = projectionMatrix * view;
      }
    `,
    fragmentShader: /* glsl */`
      uniform float uTime; uniform float uOpacity; uniform float uHaze;
      uniform vec3 uLight; uniform vec3 uShade;
      varying vec3 vPoint; varying vec3 vNormal; varying vec3 vView; varying float vLight;
      ${noise}
      void main() {
        vec2 drift = vec2(uTime * .027, -uTime * .018);
        vec2 plane = mix(vPoint.xz, vPoint.xy, uHaze);
        float grain = noise(plane * 4. + drift) * .7 + noise(plane * 9. - drift) * .3;
        float facing = max(0., dot(normalize(vNormal), normalize(vView)));
        float softEdge = smoothstep(.0, .62, facing);
        float light = clamp(.30 + .58 * vLight + .12 * grain, 0., 1.);
        vec3 color = mix(uShade, uLight, light);
        float alpha = mix(.94 * softEdge * (.85 + grain * .15), .25 + .22 * grain, uHaze);
        gl_FragColor = vec4(color, alpha * uOpacity);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  });
  const mist = material(false), haze = material(true);
  const top = new MeshStandardMaterial({ color: "#4e6777", roughness: .96 });
  const side = new MeshStandardMaterial({ color: "#304956", roughness: .96 });
  const mark = new MeshBasicMaterial({ color: "#a6beca" });
  return {
    cloud, mist, haze, top, side, mark, time,
    /** Only active reveals own clones; the clock uniform remains scene-shared. */
    revealMaterials() {
      const cloud = mist.clone(), veil = haze.clone();
      cloud.uniforms.uTime = time; veil.uniforms.uTime = time;
      const base = [top.clone(), side.clone()];
      const marks = mark.clone();
      [...base, cloud, veil, marks].forEach(m => { m.transparent = true; m.depthWrite = false; m.depthTest = false; });
      return { cloud, haze: veil, base, mark: marks, dispose() { [...base, cloud, veil, marks].forEach(m => m.dispose()); } };
    },
    dispose() { cloud.dispose(); [mist, haze, top, side, mark].forEach(m => m.dispose()); },
  };
}
