/**
 * SemanticRegistry — built ONCE after the GLB loads (spec §5/§16).
 *
 * The GLB scene graph stays flat (baked world transforms); the semantic tree
 * lives here. Raycast hits resolve geometry -> logical component -> system,
 * which is what lets a click on a PCB capacitor select CMP_MAIN_PCB.
 */

import * as THREE from 'three';

export type SemanticRole = 'HERO' | 'PRIMARY' | 'SECONDARY' | 'SUPPORT' | 'HIDDEN';
export type SemanticType = 'device' | 'system' | 'component' | 'geometry';

export interface SemanticEntity {
  id: string;
  type: SemanticType;
  object3D: THREE.Object3D;
  systemId?: string;
  sourcePart?: string;
  displayName: string;
  role: SemanticRole;
  selectable: boolean;
  hoverable: boolean;
  inspectable: boolean;
  presentationPriority: number;
  /** Assembled world position captured at load — NEVER mutated (spec §6). */
  basePosition: THREE.Vector3;
}

interface ManifestComponent {
  semanticId: string;
  systemId: string;
  displayName: string;
  role: SemanticRole;
  inspectable: boolean;
  assembled: [number, number, number];
  inspect?: [number, number, number];
  extractDirection?: [number, number, number];
}

interface ManifestSystem {
  displayName: string;
  oneLiner: string;
  order: number;
  parts: string[];
  explodeVector: [number, number, number];
}

export interface Manifest {
  version: number;
  glb: string;
  unit: string;
  systems: Record<string, ManifestSystem>;
  components: Record<string, ManifestComponent>;
  cameraPresets: Record<string, unknown>;
}

export class SemanticRegistry {
  private byId = new Map<string, SemanticEntity>();
  private byNode = new Map<THREE.Object3D, SemanticEntity>();
  private bySystem = new Map<string, SemanticEntity[]>();
  private manifestComponents: Record<string, ManifestComponent>;
  private manifestSystems: Record<string, ManifestSystem>;

  constructor(scene: THREE.Object3D, manifest: Manifest) {
    this.manifestComponents = manifest.components;
    this.manifestSystems = manifest.systems;
    this.index(scene);
  }

  private index(scene: THREE.Object3D): void {
    scene.traverse((node) => {
      const extras = (node.userData ?? {}) as Record<string, unknown>;
      const semanticId = extras['semanticId'] as string | undefined;
      if (!semanticId) return;
      const type = (extras['type'] as SemanticType) ?? 'component';
      const entity: SemanticEntity = {
        id: semanticId,
        type,
        object3D: node,
        systemId: (extras['systemId'] as string) ?? undefined,
        sourcePart: (extras['sourcePart'] as string) ?? undefined,
        displayName: (extras['displayName'] as string) ?? semanticId,
        role: (extras['role'] as SemanticRole) ?? 'SECONDARY',
        selectable: Boolean(extras['selectable']),
        hoverable: Boolean(extras['hoverable']),
        inspectable: Boolean(extras['inspectable']),
        presentationPriority: Number(extras['presentationPriority'] ?? 0),
        basePosition: node.getWorldPosition(new THREE.Vector3()),
      };
      this.byId.set(semanticId, entity);
      node.traverse((child) => this.byNode.set(child, entity));
      if (entity.systemId) {
        const list = this.bySystem.get(entity.systemId) ?? [];
        list.push(entity);
        this.bySystem.set(entity.systemId, list);
      }
    });
  }

  get(id: string): SemanticEntity | undefined {
    return this.byId.get(id);
  }

  /** Resolve any hit geometry up to its logical component (spec §16). */
  getLogicalParent(node: THREE.Object3D): SemanticEntity | undefined {
    let cur: THREE.Object3D | null = node;
    while (cur) {
      const entity = this.byNode.get(cur);
      if (entity) return entity;
      cur = cur.parent;
    }
    return undefined;
  }

  getSystemOf(node: THREE.Object3D): string | undefined {
    return this.getLogicalParent(node)?.systemId;
  }

  getChildren(systemId: string): SemanticEntity[] {
    return (this.bySystem.get(systemId) ?? []).filter((e) => e.type !== 'system');
  }

  components(): SemanticEntity[] {
    return [...this.byId.values()].filter((e) => e.type === 'component');
  }

  geometry(): SemanticEntity[] {
    return [...this.byId.values()].filter((e) => e.type === 'geometry');
  }

  systems(): string[] {
    return Object.keys(this.manifestSystems).sort(
      (a, b) => this.manifestSystems[a].order - this.manifestSystems[b].order,
    );
  }

  system(id: string): ManifestSystem | undefined {
    return this.manifestSystems[id];
  }

  componentSpec(partId: string): ManifestComponent | undefined {
    return this.manifestComponents[partId];
  }

  partIds(): string[] {
    return Object.keys(this.manifestComponents);
  }

  componentSpecBySemantic(semanticId: string): ManifestComponent | undefined {
    return Object.values(this.manifestComponents).find(
      (c) => c.semanticId === semanticId,
    );
  }

  /** Integrity check — spec §49 acceptance. */
  validate(): string[] {
    const problems: string[] = [];
    const ids = new Set<string>();
    for (const e of this.byId.values()) {
      if (ids.has(e.id)) problems.push(`duplicate semanticId ${e.id}`);
      ids.add(e.id);
    }
    for (const [partId, spec] of Object.entries(this.manifestComponents)) {
      if (!this.byId.has(spec.semanticId))
        problems.push(`manifest component ${partId} missing from GLB`);
    }
    for (const sysId of Object.keys(this.manifestSystems)) {
      if (!this.bySystem.has(sysId))
        problems.push(`system ${sysId} has no GLB components`);
    }
    return problems;
  }
}
