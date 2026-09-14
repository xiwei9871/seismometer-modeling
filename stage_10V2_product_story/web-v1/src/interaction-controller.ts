/**
 * InteractionController — pointer events -> semantic selection (spec §16/§17).
 *
 * Raycast hit geometry -> registry.getLogicalParent -> select the COMPONENT,
 * never the raw mesh. Hover is a restrained highlight; click semantics depend
 * on mode (handled by the state machine through callbacks).
 */

import * as THREE from 'three';
import { SemanticEntity, SemanticRegistry } from './semantic-registry';
import { MaterialStateManager } from './material-state-manager';

export interface InteractionHandlers {
  onSelect: (entity: SemanticEntity) => void;
  onInspect: (entity: SemanticEntity) => void;
}

export class InteractionController {
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private hovered: SemanticEntity | null = null;
  private pickables: THREE.Object3D[] = [];

  constructor(
    private dom: HTMLElement,
    private camera: THREE.Camera,
    private registry: SemanticRegistry,
    private materials: MaterialStateManager,
    private handlers: InteractionHandlers,
  ) {
    dom.addEventListener('pointermove', this.onPointerMove);
    dom.addEventListener('pointerdown', this.onPointerDown);
    dom.addEventListener('dblclick', this.onDoubleClick);
  }

  /** Rebuild the pickable set from the currently-visible selectable nodes. */
  refreshPickables(scene: THREE.Object3D): void {
    this.pickables = [];
    scene.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (mesh.isMesh && mesh.visible) this.pickables.push(mesh);
    });
  }

  private entityAt(event: PointerEvent | MouseEvent): SemanticEntity | null {
    const rect = this.dom.getBoundingClientRect();
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickables, false);
    for (const hit of hits) {
      const entity = this.registry.getLogicalParent(hit.object);
      if (entity && entity.selectable && entity.object3D.visible) return entity;
    }
    return null;
  }

  private onPointerMove = (event: PointerEvent): void => {
    const entity = this.entityAt(event);
    if (entity === this.hovered) return;
    if (this.hovered) this.materials.setHover(this.hovered.object3D, false);
    this.hovered = entity;
    if (entity && entity.hoverable) {
      this.materials.setHover(entity.object3D, true);
      this.dom.style.cursor = 'pointer';
    } else {
      this.dom.style.cursor = 'default';
    }
  };

  private onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    const entity = this.entityAt(event);
    if (entity) this.handlers.onSelect(entity);
  };

  private onDoubleClick = (event: MouseEvent): void => {
    const entity = this.entityAt(event);
    if (entity) this.handlers.onInspect(entity);
  };

  clearHover(): void {
    if (this.hovered) this.materials.setHover(this.hovered.object3D, false);
    this.hovered = null;
    this.dom.style.cursor = 'default';
  }

  dispose(): void {
    this.dom.removeEventListener('pointermove', this.onPointerMove);
    this.dom.removeEventListener('pointerdown', this.onPointerDown);
    this.dom.removeEventListener('dblclick', this.onDoubleClick);
  }
}
