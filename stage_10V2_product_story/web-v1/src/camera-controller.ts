/**
 * CameraController — single owner of camera position/target/fov (spec §28–30).
 * Presets come from the manifest; transitions are smooth tweens through the
 * TransitionManager — never a hard reset, never bounce.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransitionManager } from './transition-manager';

export interface CameraPreset {
  position: [number, number, number];
  target: [number, number, number];
  lens_mm?: number;
  fstop?: number | null;
}

/** mm -> three.js scene units. The GLB ships in mm; we render in meters. */
export const UNIT = 0.001;

export class CameraController {
  readonly controls: OrbitControls;
  private presets: Record<string, CameraPreset>;

  constructor(
    private camera: THREE.PerspectiveCamera,
    dom: HTMLElement,
    private tweens: TransitionManager,
    presets: Record<string, unknown>,
  ) {
    this.presets = presets as Record<string, CameraPreset>;
    this.controls = new OrbitControls(camera, dom);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.rotateSpeed = 0.55;
    this.controls.minDistance = 0.08;
    this.controls.maxDistance = 3.0;
  }

  preset(name: string): CameraPreset | undefined {
    // supports dotted paths: 'SYS_SENSOR.inspect' -> presets.SYS_SENSOR.inspect
    return name
      .split('.')
      .reduce<unknown>((o, key) => (o as Record<string, unknown>)?.[key], this.presets) as
      | CameraPreset
      | undefined;
  }

  /** Apply a preset instantly (used once at boot). */
  jumpTo(name: string): void {
    const p = this.preset(name);
    if (!p?.position || !p?.target) return;
    if (p.lens_mm) this.applyLens(p.lens_mm);
    this.camera.position.set(...p.position).multiplyScalar(UNIT);
    this.controls.target.set(...p.target).multiplyScalar(UNIT);
    this.controls.update();
  }

  /** Tween to a preset — position + target + lens together (spec §30). */
  goTo(name: string, duration = 1.1): Promise<void> {
    const p = this.preset(name);
    if (!p?.position || !p?.target) return Promise.resolve();
    return this.goToPoseLens(
      new THREE.Vector3(...p.position).multiplyScalar(UNIT),
      new THREE.Vector3(...p.target).multiplyScalar(UNIT),
      p.lens_mm,
      duration,
    );
  }

  /** Tween to an explicit pose (e.g. system context framing). */
  goToPose(
    position: THREE.Vector3,
    target: THREE.Vector3,
    duration = 1.1,
  ): Promise<void> {
    return this.tweens.camera(
      this.camera,
      { position, lookAt: target },
      this.controls.target,
      { duration, tag: 'camera' },
    );
  }

  /** Blender AUTO sensor-fit: lens controls horizontal fov; derive vertical. */
  private applyLens(lensMm: number): void {
    const hfov = 2 * Math.atan(18 / lensMm);
    const vfov = 2 * Math.atan(Math.tan(hfov / 2) / this.camera.aspect);
    this.camera.fov = vfov * (180 / Math.PI);
    this.camera.updateProjectionMatrix();
  }

  /** Tween to an explicit pose, optionally carrying the preset's lens. */
  goToPoseLens(
    position: THREE.Vector3,
    target: THREE.Vector3,
    lensMm: number | undefined,
    duration = 1.1,
  ): Promise<void> {
    if (lensMm) this.applyLens(lensMm);
    return this.goToPose(position, target, duration);
  }

  setOrbitEnabled(on: boolean): void {
    this.controls.enabled = on;
  }

  update(): void {
    this.controls.update();
  }
}
