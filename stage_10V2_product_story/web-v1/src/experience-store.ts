/**
 * ExperienceStore — single source of interaction truth (spec §8/§35).
 *
 * Vanilla typed store (the project is not React, so no zustand): immutable-ish
 * state object, setState() merges and notifies. Every visual result derives
 * from this state — nothing accumulates on the scene graph.
 */

export type ExperienceMode =
  | 'overview'
  | 'architecture'
  | 'xray'
  | 'inspection'
  | 'function';

export interface ExperienceState {
  mode: ExperienceMode;
  focusedSystem: string | null;
  selectedComponent: string | null;
  hoveredComponent: string | null;
  architectureExplode: number;
  xrayEnabled: boolean;
  xraySystem: string | null;
  inspectionProgress: number;
  cameraPreset: string | null;
  autoRotate: boolean;
  ready: boolean;
}

export const INITIAL_STATE: ExperienceState = {
  mode: 'overview',
  focusedSystem: null,
  selectedComponent: null,
  hoveredComponent: null,
  architectureExplode: 0,
  xrayEnabled: false,
  xraySystem: null,
  inspectionProgress: 0,
  cameraPreset: null,
  autoRotate: false,
  ready: false,
};

type Listener = (state: ExperienceState, prev: ExperienceState) => void;

export class ExperienceStore {
  private state: ExperienceState = { ...INITIAL_STATE };
  private listeners = new Set<Listener>();

  get(): ExperienceState {
    return this.state;
  }

  set(patch: Partial<ExperienceState>): void {
    const prev = this.state;
    this.state = { ...this.state, ...patch };
    for (const fn of this.listeners) fn(this.state, prev);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  reset(): void {
    this.set({ ...INITIAL_STATE, ready: true });
  }
}
