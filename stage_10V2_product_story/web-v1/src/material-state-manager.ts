/**
 * MaterialStateManager — visual levels without permanently editing
 * materials (spec §14/§55). Original values are stashed once per material;
 * every level change tweens from the CURRENT value; restore() returns the
 * material to its stash exactly — no drift.
 *
 * Levels: FOCUS 1.0 | RELATED 0.4–0.6 | DISTANT 0.15–0.3 | XRAY ~0.18.
 */

import * as THREE from 'three';
import { TransitionManager } from './transition-manager';

export type VisualLevel =
  | 'FOCUS' | 'RELATED' | 'SHELL' | 'DISTANT' | 'XRAY' | 'HIDDEN';

const LEVEL_OPACITY: Record<VisualLevel, number> = {
  FOCUS: 1.0,
  RELATED: 0.5,
  SHELL: 0.6,
  DISTANT: 0.22,
  XRAY: 0.16,
  HIDDEN: 0.0,
};

interface Stash {
  opacity: number;
  transparent: boolean;
  emissiveIntensity: number;
  depthWrite: boolean;
}

export class MaterialStateManager {
  private stash = new Map<THREE.Material, Stash>();

  constructor(private tweens: TransitionManager) {}

  private materialsOf(obj: THREE.Object3D): THREE.MeshStandardMaterial[] {
    const mats: THREE.MeshStandardMaterial[] = [];
    obj.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (!mesh.isMesh) return;
      const list = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const m of list)
        if ((m as THREE.MeshStandardMaterial).isMeshStandardMaterial)
          mats.push(m as THREE.MeshStandardMaterial);
    });
    return mats;
  }

  private ensure(mat: THREE.MeshStandardMaterial): Stash {
    let s = this.stash.get(mat);
    if (!s) {
      s = {
        opacity: mat.opacity,
        transparent: mat.transparent,
        emissiveIntensity: mat.emissiveIntensity ?? 1,
        depthWrite: mat.depthWrite,
      };
      this.stash.set(mat, s);
    }
    return s;
  }

  /** Tween an object's materials to a visual level. HIDDEN also drops the node. */
  setLevel(obj: THREE.Object3D, level: VisualLevel, duration = 0.6): void {
    const target = LEVEL_OPACITY[level];
    for (const mat of this.materialsOf(obj)) {
      const s = this.ensure(mat);
      void this.tweens.material(mat, 'opacity', target * s.opacity, {
        duration,
        tag: 'material',
      });
      if (target < 1) {
        mat.transparent = true;
        mat.depthWrite = false;
      } else {
        // restore after fade-in completes
        void this.tweens.run({
          duration,
          tag: 'material',
          update: () => {},
          done: () => {
            mat.transparent = s.transparent;
            mat.depthWrite = s.depthWrite;
          },
        });
      }
    }
    if (level === 'HIDDEN') {
      obj.visible = true; // visible during fade
      void this.tweens.run({
        duration,
        tag: 'material',
        update: () => {},
        done: () => {
          obj.visible = false;
        },
      });
    } else {
      obj.visible = true;
    }
  }

  /** Subtle hover cue — spec §15: restrained, no glow, no scale, no float. */
  setHover(obj: THREE.Object3D, on: boolean): void {
    for (const mat of this.materialsOf(obj)) {
      const s = this.ensure(mat);
      void this.tweens.material(
        mat,
        'emissiveIntensity',
        on ? s.emissiveIntensity * 1.35 : s.emissiveIntensity,
        { duration: 0.15, tag: 'material' },
      );
    }
  }

  /** Exact restoration to the load-time stash (spec §55). */
  restore(obj: THREE.Object3D, duration = 0.4): void {
    for (const mat of this.materialsOf(obj)) {
      const s = this.stash.get(mat);
      if (!s) continue;
      mat.visible = true;
      void this.tweens.material(mat, 'opacity', s.opacity, { duration, tag: 'material' });
      void this.tweens.material(mat, 'emissiveIntensity', s.emissiveIntensity, {
        duration,
        tag: 'material',
      });
      void this.tweens.run({
        duration,
        tag: 'material',
        update: () => {},
        done: () => {
          mat.transparent = s.transparent;
          mat.depthWrite = s.depthWrite;
        },
      });
    }
    obj.visible = true;
  }
}
