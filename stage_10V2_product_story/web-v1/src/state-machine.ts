/**
 * ExperienceStateMachine — modes + reversible transitions (spec §7–§9, §32).
 *
 * FINAL = BASE + STATE_TRANSFORM + TRANSIENT — every target position is
 * computed from the manifest (assembled / explode vectors / inspect layout),
 * never read from the node's current transform. setMode() is idempotent and
 * reversible: any state can be reached from any state with zero drift.
 */

import * as THREE from 'three';
import { ExperienceStore } from './experience-store';
import { SemanticRegistry } from './semantic-registry';
import { MaterialStateManager } from './material-state-manager';
import { CameraController } from './camera-controller';
import { TransitionManager } from './transition-manager';

/**
 * Component nodes live in the GLB's local mm space (the scene root applies the
 * mm->m scale). Camera/controls live in world meters — UNIT applies only
 * there. Component targets therefore stay in mm.
 */
const mm = (v: [number, number, number]) =>
  new THREE.Vector3(v[0], v[1], v[2]);

export class ExperienceStateMachine {
  constructor(
    private store: ExperienceStore,
    private registry: SemanticRegistry,
    private materials: MaterialStateManager,
    private camera: CameraController,
    private tweens: TransitionManager,
  ) {}

  /** Absolute scene-space target for a component under the given state. */
  private targetPosition(partId: string, mode: string): THREE.Vector3 {
    const spec = this.registry.componentSpec(partId);
    if (!spec) return new THREE.Vector3();
    const base = mm(spec.assembled);
    if (mode === 'inspection' && spec.inspect) return mm(spec.inspect);
    if (mode === 'architecture') {
      const sys = this.registry.system(spec.systemId);
      if (sys) {
        const f = this.store.get().architectureExplode || 1;
        return base.add(mm(sys.explodeVector).multiplyScalar(f));
      }
    }
    return base;
  }

  private moveComponent(partId: string, to: THREE.Vector3, duration: number): Promise<void> {
    const sem = this.registry.componentSpec(partId)!.semanticId;
    const entity = this.registry.get(sem);
    if (!entity) return Promise.resolve();
    return this.tweens.position(entity.object3D, to, { duration, tag: 'motion' });
  }

  /** Restore every component to its assembled base — exact, no drift (§50). */
  private allToBase(duration = 0.9): Promise<void>[] {
    return this.registry
      .partIds()
      .map((partId) =>
        this.moveComponent(partId, mm(this.registry.componentSpec(partId)!.assembled), duration),
      );
  }

  async setMode(mode: 'overview' | 'architecture' | 'inspection', systemId?: string): Promise<void> {
    // §31: cancel previous transient transitions, then resolve the new state.
    this.tweens.cancel('motion');
    this.tweens.cancel('material');
    this.tweens.cancel('camera');

    if (mode === 'overview') return this.enterOverview();
    if (mode === 'architecture') return this.enterArchitecture();
    if (mode === 'inspection' && systemId) return this.enterInspection(systemId);
  }

  private async enterOverview(): Promise<void> {
    this.store.set({
      mode: 'overview',
      focusedSystem: null,
      xrayEnabled: false,
      xraySystem: null,
      architectureExplode: 0,
      inspectionProgress: 0,
      selectedComponent: null,
    });
    void this.camera.goTo('overviewHero', 1.2);
    const jobs = this.allToBase(1.0);
    for (const e of this.registry.components()) this.materials.restore(e.object3D, 0.7);
    for (const e of this.registry.geometry()) this.materials.restore(e.object3D, 0.7);
    await Promise.all(jobs);
  }

  private async enterArchitecture(): Promise<void> {
    this.store.set({
      mode: 'architecture',
      focusedSystem: null,
      xrayEnabled: false,
      xraySystem: null,
      inspectionProgress: 0,
    });
    // §11: one macro explode — four system layers only, no secondary detail.
    this.store.set({ architectureExplode: 1 });
    void this.camera.goTo('architectureHero', 1.2);
    const jobs: Promise<void>[] = [];
    for (const sysId of this.registry.systems()) {
      for (const partId of this.registry.system(sysId)!.parts)
        jobs.push(this.moveComponent(partId, this.targetPosition(partId, 'architecture'), 1.0));
    }
    for (const e of this.registry.components()) this.materials.restore(e.object3D, 0.7);
    for (const e of this.registry.geometry()) this.materials.restore(e.object3D, 0.7);
    await Promise.all(jobs);
  }

  /**
   * Staged inspection sequence (§32):
   *  camera→context → housing x-ray → system highlight → extract →
   *  camera→inspect → secondary explode → enable orbit.
   */
  private async enterInspection(systemId: string): Promise<void> {
    this.store.set({
      mode: 'inspection',
      focusedSystem: systemId,
      xrayEnabled: true,
      xraySystem: systemId,
      selectedComponent: null,
      inspectionProgress: 0,
    });

    const sysParts = new Set(this.registry.system(systemId)!.parts);
    const sysEntities = this.registry
      .getChildren(systemId)
      .filter((e) => e.type === 'component');
    const others = this.registry
      .components()
      .filter((e) => !sysParts.has(e.sourcePart ?? ''));

    // 1-2. camera to context + x-ray everything that is not the system.
    void this.camera.goTo(`${systemId}.context`, 1.0);
    for (const e of others) this.materials.setLevel(e.object3D, 'XRAY', 0.7);
    for (const e of sysEntities) this.materials.setLevel(e.object3D, 'FOCUS', 0.4);
    await sleep(650);

    // 3-5. extract the system to its inspect layout, hide the context,
    //      move the camera into the inspection preset.
    for (const e of others) this.materials.setLevel(e.object3D, 'HIDDEN', 0.8);
    void this.camera.goTo(`${systemId}.inspect`, 1.2);
    const jobs = this.registry
      .system(systemId)!
      .parts.map((partId) =>
        this.moveComponent(partId, this.targetPosition(partId, 'inspection'), 1.1),
      );
    // PCB presentation components ride along with the board (logical children).
    for (const e of this.registry.geometry()) {
      if (e.systemId === systemId) this.materials.setLevel(e.object3D, 'FOCUS', 0.4);
      else this.materials.setLevel(e.object3D, 'HIDDEN', 0.8);
    }
    await Promise.all(jobs);
    this.store.set({ inspectionProgress: 1 });
  }

  /** Secondary explode inside inspection: click a core to extract it (§21). */
  async toggleComponentExtract(partId: string, extracted: boolean): Promise<void> {
    const spec = this.registry.componentSpec(partId);
    if (!spec?.inspect) return;
    const target = mm(spec.inspect);
    if (extracted && spec.extractDirection) {
      target.add(mm(spec.extractDirection).multiplyScalar(28));
    }
    await this.moveComponent(partId, target, 0.7);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
