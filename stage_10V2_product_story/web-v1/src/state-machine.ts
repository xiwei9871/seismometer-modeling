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
  /** parts whose top was clipped open for the current inspection */
  private clipped: THREE.Mesh[] = [];
  /** cloned lid halves lifted off split fixtures */
  private lids: THREE.Mesh[] = [];

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
    if (mode === 'inspection' && spec.inspect) {
      const p = mm(spec.inspect);
      // cores self-extract along their axis so a fixture reads "open"
      if (spec.extractDirection)
        p.add(mm(spec.extractDirection).multiplyScalar(28));
      return p;
    }
    if (mode === 'architecture') {
      const sys = this.registry.system(spec.systemId);
      if (sys) {
        const f = this.store.get().architectureExplode || 1;
        base.add(mm(sys.explodeVector).multiplyScalar(f));
        // per-part offset spreads stacked members (e.g. mezzanine B board)
        if (spec.explodeOffset) base.add(mm(spec.explodeOffset));
        return base;
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

  /** Reassemble every part + restore all materials without touching the
   *  store — used by chapters that present over the assembled device. */
  async reassemble(duration = 1.0): Promise<void> {
    this.tweens.cancel('motion');
    const jobs = this.allToBase(duration);
    for (const e of this.registry.components()) this.materials.restore(e.object3D, 0.7);
    for (const e of this.registry.geometry()) this.materials.restore(e.object3D, 0.7);
    await Promise.all(jobs);
  }

  /** Remove split-half clip planes + delete the lifted lid clones. */
  private clearClips(): void {
    for (const m of this.clipped) {
      const mat = m.material as THREE.MeshStandardMaterial;
      if (mat?.clippingPlanes) mat.clippingPlanes = null;
    }
    for (const lid of this.lids) lid.parent?.remove(lid);
    this.clipped = [];
    this.lids = [];
  }

  /** Split a fixture-type part into bottom half + lifted lid along a world
   *  clip plane (`openTop` mm above its inspect pos). The source mesh keeps
   *  y ≤ cut; a clone keeps y > cut and rises, so a one-piece STL reads as a
   *  two-half fixture opening — no geometry edit (rules-safe). */
  private applyOpenTop(partId: string): void {
    const spec = this.registry.componentSpec(partId);
    if (!spec?.openTop) return;
    const entity = this.registry.get(spec.semanticId);
    if (!entity) return;
    const baseY = spec.inspect ? spec.inspect[1] : spec.assembled[1];
    const cut = (baseY + spec.openTop) / 1000;          // world metres
    const keepBelow = new THREE.Plane(new THREE.Vector3(0, -1, 0), cut);
    const keepAbove = new THREE.Plane(new THREE.Vector3(0, 1, 0), -cut);
    entity.object3D.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh || mesh.userData.isLid) return;
      if (!mesh.userData.openTopCloned) {
        mesh.material = (mesh.material as THREE.MeshStandardMaterial).clone();
        mesh.userData.openTopCloned = true;
      }
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.side = THREE.DoubleSide;
      mat.clippingPlanes = [keepBelow];
      this.clipped.push(mesh);
      if (spec.splitLid === false) return;    // bay stub: clip, no lid
      // lid clone — same geometry; its clip plane RIDES with the lift so the
      // rendered piece stays exactly the top-half slice, never a full copy
      const lid = mesh.clone();
      lid.userData.isLid = true;
      lid.material = mat.clone();
      const lm = lid.material as THREE.MeshStandardMaterial;
      lm.side = THREE.DoubleSide;
      const lidPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -cut);
      lm.clippingPlanes = [lidPlane];
      mesh.parent!.add(lid);
      this.lids.push(lid);
      const y0 = lid.position.y;
      const lift = 44;                    // mm, local space
      void this.tweens.run({
        duration: 0.7,
        tag: 'motion',
        update: (k) => {
          lid.position.y = y0 + k * lift;
          lidPlane.constant = -(cut + (k * lift) / 1000);
        },
      });
    });
  }

  async setMode(mode: 'overview' | 'architecture' | 'inspection', systemId?: string): Promise<void> {
    // §31: cancel previous transient transitions, then resolve the new state.
    this.tweens.cancel('motion');
    this.tweens.cancel('material');
    this.tweens.cancel('camera');
    this.clearClips();

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

    // no locate beat — non-system parts fade straight out; parts flagged
    // ghostInInspectFor THIS system stay translucent (e.g. the handle must
    // remain x-rayed so the antenna reads inside it).
    for (const e of others) {
      const keep = e.sourcePart
        ? this.registry.componentSpec(e.sourcePart)?.ghostInInspectFor
        : undefined;
      this.materials.setLevel(
        e.object3D,
        keep?.includes(systemId) ? 'XRAY' : 'HIDDEN',
        0.5,
      );
    }
    for (const e of sysEntities) {
      // shell parts flagged ghostInInspect (battery tubes) turn translucent
      // so the contents they hold stay readable without any disassembly.
      const ghost = e.sourcePart
        ? this.registry.componentSpec(e.sourcePart)?.ghostInInspect
        : false;
      this.materials.setLevel(e.object3D, ghost ? 'SHELL' : 'FOCUS', 0.4);
    }
    // geometry entities (cells, PCB dressing) hide/focus up front — otherwise
    // they linger on stage through the whole staged reveal
    for (const e of this.registry.geometry()) {
      const ghost = e.sourcePart
        ? this.registry.componentSpec(e.sourcePart)?.ghostInInspect
        : false;
      if (e.systemId === systemId)
        this.materials.setLevel(e.object3D, ghost ? 'SHELL' : 'FOCUS', 0.4);
      else this.materials.setLevel(e.object3D, 'HIDDEN', 0.5);
    }
    void this.camera.goTo(`${systemId}.inspect`, 1.2);
    // let the stage clear before the system travels
    await sleep(600);
    // staged reveal: container parts (openTop) travel first WITH their
    // contents riding inside, then open, then the contents burst out —
    // reads as "fixture comes out, opens, cores emerge from inside it".
    const sysPartIds = this.registry.system(systemId)!.parts;
    const containers = sysPartIds.filter(
      (p) => this.registry.componentSpec(p)?.openTop !== undefined,
    );
    const contents = sysPartIds.filter(
      (p) => this.registry.componentSpec(p)?.openTop === undefined,
    );
    // ride-along offset: contents keep their position relative to the first
    // container while it travels, so they stay inside the closed fixture
    let rideDelta: THREE.Vector3 | null = null;
    if (containers.length) {
      const c = this.registry.componentSpec(containers[0])!;
      rideDelta = this.targetPosition(containers[0], 'inspection')
        .clone()
        .sub(mm(c.assembled));
    }
    await Promise.all([
      ...containers.map((partId) =>
        this.moveComponent(partId, this.targetPosition(partId, 'inspection'), 1.1),
      ),
      ...(rideDelta
        ? contents.map((partId) => {
            const spec = this.registry.componentSpec(partId)!;
            return this.moveComponent(
              partId,
              mm(spec.assembled).add(rideDelta),
              1.1,
            );
          })
        : []),
    ]);
    // fixture-style parts open up once settled (clip plane lifts the lid)
    for (const partId of containers) this.applyOpenTop(partId);
    if (containers.length) await sleep(950);
    const jobs = contents.map((partId) =>
      this.moveComponent(partId, this.targetPosition(partId, 'inspection'), 1.1),
    );
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
