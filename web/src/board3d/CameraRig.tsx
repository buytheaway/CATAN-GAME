import { useEffect, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { PerspectiveCamera } from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { cameraFrame } from "./coordinates";
import type { BoardBounds } from "./types";

export default function CameraRig({ bounds, resetVersion }: { bounds: BoardBounds; resetVersion: number }) {
  const { camera, gl, size, invalidate } = useThree();
  const controlsRef = useRef<OrbitControls | null>(null);
  const centerX = bounds.center[0];
  const centerZ = bounds.center[2];
  const radius = bounds.radius;
  const width = bounds.width;
  const depth = bounds.depth;
  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controlsRef.current = controls;
    controls.enablePan = false;
    controls.enableDamping = false;
    controls.minPolarAngle = Math.PI * 0.16;
    controls.maxPolarAngle = Math.PI * 0.36;
    controls.minAzimuthAngle = -Math.PI / 3;
    controls.maxAzimuthAngle = Math.PI / 3;
    const requestFrame = () => invalidate();
    controls.addEventListener("change", requestFrame);
    return () => {
      controls.removeEventListener("change", requestFrame);
      controls.dispose();
      controlsRef.current = null;
    };
  }, [camera, gl, invalidate]);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!(camera instanceof PerspectiveCamera) || !controls) return;
    const frame = cameraFrame({ center: [centerX, 0, centerZ], width, depth }, size.width / Math.max(1, size.height), camera.fov);
    camera.position.set(...frame.position);
    camera.near = Math.max(0.01, radius / 100);
    camera.far = frame.distance * 6;
    camera.updateProjectionMatrix();
    controls.target.set(...frame.target);
    controls.minDistance = frame.distance * 0.5;
    controls.maxDistance = frame.distance * 1.6;
    controls.update();
    invalidate();
    // Numeric bounds keep ordinary snapshots from resetting a player's camera.
  }, [camera, gl, centerX, centerZ, radius, width, depth, size.width, size.height, resetVersion, invalidate]);
  return null;
}
