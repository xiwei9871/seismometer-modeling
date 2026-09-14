/**
 * V1 Interactive Digital Product — Sensor vertical slice.
 *
 * Boot: load GLB (semantic extras) + manifest -> SemanticRegistry -> wire
 * store / state machine / camera / materials / interaction.
 *
 * Flow (spec §61): Overview -> hover -> click system -> X-Ray locate ->
 * Inspect -> extraction + secondary explode -> free orbit -> Back -> exact
 * restoration. Manual interaction and the chapter rail share the same state
 * machine (§45).
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { ExperienceStore } from './experience-store';
import { SemanticRegistry, Manifest, SemanticEntity } from './semantic-registry';
import { TransitionManager } from './transition-manager';
import { CameraController, UNIT } from './camera-controller';
import { MaterialStateManager } from './material-state-manager';
import { ExperienceStateMachine } from './state-machine';
import { InteractionController } from './interaction-controller';

const canvas = document.getElementById('view') as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x111417);

// Studio environment: soft PBR reflections without an external HDRI file.
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.9;

const camera = new THREE.PerspectiveCamera(
  40,
  window.innerWidth / window.innerHeight,
  0.01,
  50,
);

// restrained studio rig: key + rim so graphite parts keep readable edges
const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(0.6, 1.1, 0.8);
scene.add(key);
const rim = new THREE.DirectionalLight(0xbfd4ff, 0.9);
rim.position.set(-0.8, 0.6, -0.9);
scene.add(rim);
scene.add(new THREE.AmbientLight(0xffffff, 0.15));

// ground shadow-catcher: soft radial gradient disc under the product
const shadowTex = makeRadialShadowTexture();
const shadow = new THREE.Mesh(
  new THREE.PlaneGeometry(1.6, 1.6),
  new THREE.MeshBasicMaterial({
    map: shadowTex,
    transparent: true,
    depthWrite: false,
    opacity: 0.55,
  }),
);
shadow.rotation.x = -Math.PI / 2;
shadow.position.y = 0;
scene.add(shadow);

function makeRadialShadowTexture(): THREE.Texture {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d')!;
  const g = ctx.createRadialGradient(128, 128, 10, 128, 128, 128);
  g.addColorStop(0, 'rgba(0,0,0,0.85)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  return tex;
}

// ---------------------------------------------------------------------------

const store = new ExperienceStore();
const tweens = new TransitionManager();
let registry: SemanticRegistry;
let materials: MaterialStateManager;
let cameraCtl: CameraController;
let machine: ExperienceStateMachine;
let interaction: InteractionController;
let manifest: Manifest;
let extracted = new Set<string>();

async function boot(): Promise<void> {
  manifest = (await (await fetch('./manifest_v1.json')).json()) as Manifest;

  const gltf = await new GLTFLoader().loadAsync('./' + manifest.glb);
  const root = gltf.scene;
  root.scale.setScalar(UNIT); // GLB ships mm -> render in meters
  scene.add(root);
  root.updateMatrixWorld(true);

  // PCB presentation components become real children of CMP_MAIN_PCB so they
  // ride along when the board moves (logical parent, spec §22).
  let board: THREE.Object3D | undefined;
  const compNodes: THREE.Object3D[] = [];
  root.traverse((n) => {
    const ud = n.userData as { semanticId?: string; logicalParent?: string };
    if (ud.semanticId === 'CMP_MAIN_PCB') board = n;
    if (ud.logicalParent) compNodes.push(n);
  });
  if (board) for (const n of compNodes) board.attach(n);

  registry = new SemanticRegistry(root, manifest);
  const problems = registry.validate();
  if (problems.length) console.error('semantic registry:', problems);

  materials = new MaterialStateManager(tweens);
  cameraCtl = new CameraController(camera, canvas, tweens, manifest.cameraPresets);
  machine = new ExperienceStateMachine(store, registry, materials, cameraCtl, tweens);
  interaction = new InteractionController(canvas, camera, registry, materials, {
    onSelect: (entity) => void onSelect(entity),
    onInspect: (entity) => void onInspect(entity),
  });
  interaction.refreshPickables(root);

  cameraCtl.jumpTo('overviewHero');
  store.set({ ready: true, mode: 'overview', cameraPreset: 'overviewHero' });
  buildRail();
  hud('ready');

  // debug hook (spec §43): ?debug=1 surface + console introspection
  (window as unknown as { __app: object }).__app = {
    THREE, scene, camera, cameraCtl, registry, store, machine, tweens,
  };
}

function onSelect(entity: SemanticEntity): void {
  const st = store.get();
  if (st.mode === 'inspection') {
    // inside inspection: cores toggle a secondary extraction (spec §21)
    if (entity.sourcePart && entity.systemId === st.focusedSystem) {
      const id = entity.sourcePart;
      if (entity.inspectable && entity.id.startsWith('CMP_SENSOR_')) {
        if (extracted.has(id)) extracted.delete(id);
        else extracted.add(id);
        void machine.toggleComponentExtract(id, extracted.has(id));
        hud(entity.displayName + (extracted.has(id) ? ' — extracted' : ''));
      } else {
        hud(entity.displayName);
      }
    }
    return;
  }
  store.set({ selectedComponent: entity.id });
  hud(entity.displayName);
  if (entity.systemId && entity.inspectable) void enterContext(entity.systemId);
}

function onInspect(entity: SemanticEntity): void {
  if (entity.systemId) void machine.setMode('inspection', entity.systemId);
}

/** Click a system: first show WHERE it is (x-ray locate), spec §13/§18. */
async function enterContext(systemId: string): Promise<void> {
  store.set({ mode: 'xray', focusedSystem: systemId, xrayEnabled: true, xraySystem: systemId });
  void cameraCtl.goTo(`${systemId}.context`, 1.0);
  const sysParts = new Set(registry.system(systemId)!.parts);
  for (const e of registry.components()) {
    const isSystem = sysParts.has(e.sourcePart ?? '');
    const isShell = e.role === 'SECONDARY';
    materials.setLevel(
      e.object3D,
      isSystem ? 'FOCUS' : isShell ? 'XRAY' : 'DISTANT',
      0.7,
    );
  }
  inspectBtn.style.display = 'block';
}

function buildRail(): void {
  const rail = document.getElementById('rail')!;
  rail.innerHTML = '';
  const items: [string, string, () => void][] = [
    ['01', 'Overview', () => backToOverview()],
    ['02', 'Architecture', () => void machine.setMode('architecture')],
    ['03', 'Sensing', () => void enterContext('SYS_SENSOR')],
    ['04', 'Acquisition', () => void enterContext('SYS_ACQUISITION')],
    ['05', 'Power', () => void enterContext('SYS_POWER')],
  ];
  for (const [num, label, fn] of items) {
    const b = document.createElement('button');
    b.className = 'rail-btn';
    b.innerHTML = `<span class="num">${num}</span>${label}`;
    b.onclick = fn;
    rail.appendChild(b);
  }
}

const inspectBtn = document.getElementById('inspect-btn') as HTMLButtonElement;
inspectBtn.onclick = () => {
  const sys = store.get().focusedSystem;
  if (sys) void machine.setMode('inspection', sys);
};

const backBtn = document.getElementById('back-btn') as HTMLButtonElement;
backBtn.onclick = () => backToOverview();

function backToOverview(): void {
  extracted.clear();
  inspectBtn.style.display = 'none';
  void machine.setMode('overview');
}

function hud(text: string): void {
  const el = document.getElementById('hud');
  if (el) el.textContent = text;
}

// reflect mode in the UI chrome
store.subscribe((s, prev) => {
  if (s.mode === prev.mode) return;
  backBtn.style.display = s.mode === 'overview' ? 'none' : 'block';
  inspectBtn.style.display = s.mode === 'xray' ? 'block' : 'none';
  interaction?.clearHover();
  interaction?.refreshPickables(scene);
  const sys = s.focusedSystem ? registry?.system(s.focusedSystem) : undefined;
  hud(
    s.mode === 'inspection' && sys
      ? `${sys.displayName} — orbit freely, click a core to extract`
      : s.mode === 'xray' && sys
        ? `${sys.displayName} — inside the device`
        : '',
  );
});

// ---------------------------------------------------------------------------

function resize(): void {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}
window.addEventListener('resize', resize);
resize();

renderer.setAnimationLoop(() => {
  tweens.update();
  cameraCtl?.update();
  renderer.render(scene, camera);
});

void boot();
