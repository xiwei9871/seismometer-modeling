/**
 * TransitionManager — every object/material/camera transition is scheduled
 * here (spec §30/§31). One rAF-driven list; state changes cancel the previous
 * transient batch, resolve the target state, then run — never accumulate.
 *
 * Easing is deliberately boring: easeInOutCubic / easeOutQuart. No bounce,
 * no elastic, no overshoot.
 */

import * as THREE from 'three';

export const easeInOutCubic = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

export const easeOutQuart = (t: number): number => 1 - Math.pow(1 - t, 4);

interface Tween {
  tag: string;
  elapsed: number;
  duration: number;
  ease: (t: number) => number;
  update: (k: number) => void;
  done: () => void;
  /** resolves the returned promise without firing the completion callback */
  resolve: () => void;
  cancelled: boolean;
}

export class TransitionManager {
  private tweens: Tween[] = [];
  private clock = new THREE.Clock();

  /** Schedule a generic scalar tween. Returns a promise resolved at the end. */
  run(opts: {
    tag?: string;
    duration?: number;
    ease?: (t: number) => number;
    update: (k: number) => void;
    done?: () => void;
  }): Promise<void> {
    const duration = Math.max(0.0001, opts.duration ?? 0.9);
    return new Promise((resolve) => {
      this.tweens.push({
        tag: opts.tag ?? 'default',
        elapsed: 0,
        duration,
        ease: opts.ease ?? easeInOutCubic,
        update: opts.update,
        done: () => {
          opts.done?.();
          resolve();
        },
        resolve,
        cancelled: false,
      });
    });
  }

  /** Cancel every tween carrying `tag` (spec §31: cancel before re-resolve). */
  cancel(tag: string): void {
    const dead = this.tweens.filter((t) => t.tag === tag);
    this.tweens = this.tweens.filter((t) => t.tag !== tag);
    // Resolve cancelled tweens' promises so awaited Promise.all() callers
    // continue; done() is skipped since the tween never reached its end state.
    for (const t of dead) {
      t.cancelled = true;
      t.resolve();
    }
  }

  /** Tween an Object3D world position. */
  position(
    obj: THREE.Object3D,
    to: THREE.Vector3,
    opts: { duration?: number; tag?: string; ease?: (t: number) => number } = {},
  ): Promise<void> {
    const from = obj.position.clone();
    return this.run({
      ...opts,
      update: (k) => obj.position.lerpVectors(from, to, k),
    });
  }

  /** Tween camera position + controls target together (spec §30). */
  camera(
    cam: THREE.PerspectiveCamera,
    target: { position: THREE.Vector3; lookAt: THREE.Vector3 },
    controlsTarget: THREE.Vector3,
    opts: { duration?: number; tag?: string } = {},
  ): Promise<void> {
    const p0 = cam.position.clone();
    const t0 = controlsTarget.clone();
    return this.run({
      duration: opts.duration ?? 1.1,
      tag: opts.tag ?? 'camera',
      update: (k) => {
        cam.position.lerpVectors(p0, target.position, k);
        controlsTarget.lerpVectors(t0, target.lookAt, k);
      },
    });
  }

  /** Tween a material scalar property (opacity, emissiveIntensity...). */
  material(
    mat: THREE.Material,
    prop: 'opacity' | 'emissiveIntensity' | 'roughness' | 'envMapIntensity',
    to: number,
    opts: { duration?: number; tag?: string } = {},
  ): Promise<void> {
    const from = (mat as unknown as Record<string, number>)[prop] ?? 0;
    return this.run({
      duration: opts.duration ?? 0.5,
      tag: opts.tag ?? 'material',
      update: (k) => {
        (mat as unknown as Record<string, number>)[prop] = from + (to - from) * k;
      },
    });
  }

  /** Advance all tweens. Call once per frame from the render loop. */
  update(): void {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    const finished: Tween[] = [];
    for (const t of this.tweens) {
      t.elapsed += dt;
      const k = t.ease(Math.min(1, t.elapsed / t.duration));
      t.update(k);
      if (t.elapsed >= t.duration) finished.push(t);
    }
    this.tweens = this.tweens.filter((t) => !finished.includes(t));
    for (const t of finished) t.done();
  }

  /** True while at least one transition is still running. */
  busy(): boolean {
    return this.tweens.length > 0;
  }
}
