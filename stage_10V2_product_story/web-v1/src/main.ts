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
renderer.localClippingEnabled = true; // fixture open-top cutaway (inspection)
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
  manifest = (await (await fetch('./manifest_v1.json?v=60')).json()) as Manifest;

  const gltf = await new GLTFLoader().loadAsync('./' + manifest.glb + '?v=57');
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

  // top-cover indicator LEDs — collect their materials for the blink driver,
  // plus a camera-facing glow sprite per lens so a 3mm LED reads at overview
  // distance under ACES tonemapping
  root.traverse((n) => {
    const m = n as THREE.Mesh;
    if (!m.isMesh || !/^LED_/.test(m.name)) return;
    const list = Array.isArray(m.material) ? m.material : [m.material];
    for (const mm of list)
      if ((mm as THREE.MeshStandardMaterial).isMeshStandardMaterial)
        ledMats.add(mm as THREE.MeshStandardMaterial);
    // LED mesh nodes carry an identity transform (verts baked in world
    // space) — getWorldPosition reads (0,0,0); the bbox centre is the true
    // lens location for the glow sprite
    const wp = new THREE.Box3()
      .setFromObject(m)
      .getCenter(new THREE.Vector3());
    const sm = new THREE.SpriteMaterial({
      map: ledGlowTex(),
      transparent: true,
      depthWrite: false,
      // NormalBlending keeps the core saturated over the bright top cover;
      // additive only whitened the deck and washed the blink out
      blending: THREE.NormalBlending,
      opacity: 0,
    });
    const sp = new THREE.Sprite(sm);
    sp.scale.setScalar(7);                       // ~7mm lamp disc — keeps the 5mm-spaced trio distinct
    sp.position.copy(
      root.worldToLocal(wp.clone().add(new THREE.Vector3(0, 0.0022, 0))),
    );
    root.add(sp);
    ledSprites.push(sp);
  });
  ledT0 = performance.now();   // blink clock starts once the device is visible

  // shell skin materials — each housing part owns a dedicated material used
  // only by its shell mesh, so recolouring can't leak into small hardware
  root.traverse((n) => {
    const mesh = n as THREE.Mesh;
    if (!mesh.isMesh) return;
    const list = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const m of list) {
      const ms = m as THREE.MeshStandardMaterial;
      if (!ms.isMeshStandardMaterial) continue;
      if (ms.name.startsWith('T10V2_PART_001')) shellMats.lower.push(ms);
      else if (ms.name.startsWith('T10V2_PART_002')) shellMats.upper.push(ms);
      else if (ms.name.startsWith('T10V2_PART_005')) shellMats.handle.push(ms);
    }
  });
  // the upper cover read "too bright": its base colour is already dark —
  // the sheen is RoomEnvironment specular. Matte it down so it reads as
  // engineering plastic (and the LEDs gain contrast for free)
  for (const m of shellMats.upper) {
    m.roughness = 0.55;
    m.envMapIntensity = 0.5;
  }
  for (const mats of Object.values(shellMats))
    for (const m of mats)
      if (!shellOrig.has(m))
        shellOrig.set(m, {
          roughness: m.roughness,
          metalness: m.metalness,
          envMapIntensity: m.envMapIntensity,
        });
  buildPalette();

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
  // overview = look-only; structure exploration starts in architecture mode
  if ((st.mode === 'architecture' || st.mode === 'xray') &&
      entity.systemId && entity.inspectable)
    void enterContext(entity.systemId);
}

function onInspect(entity: SemanticEntity): void {
  // overview is look-only: dblclick-inspect is armed in structure views only
  const m = store.get().mode;
  if (entity.systemId && (m === 'architecture' || m === 'xray' || m === 'inspection'))
    void machine.setMode('inspection', entity.systemId);
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
    ['03', 'Sensing', () => void inspectSystem('SYS_SENSOR')],
    ['04', 'Acquisition', () => void inspectSystem('SYS_ACQUISITION')],
    ['05', 'Power', () => void inspectSystem('SYS_POWER')],
    ['06', 'Transmission', () => void focusTransmission()],
  ];
  for (const [num, label, fn] of items) {
    const b = document.createElement('button');
    b.className = 'rail-btn';
    b.innerHTML = `<span class="num">${num}</span>${label}`;
    b.onclick = fn;
    rail.appendChild(b);
  }
}

/** Transmission chapter: the device stays assembled & opaque like overview —
 *  only the antenna + on-board radio module get focus, plus the arc FX. */
async function focusTransmission(): Promise<void> {
  store.set({
    mode: 'xray',
    focusedSystem: 'SYS_TRANSMISSION',
    xrayEnabled: false,
    xraySystem: null,
    selectedComponent: null,
  });
  void cameraCtl.goTo('SYS_TRANSMISSION.context', 1.0);
  await machine.reassemble(1.0);
  // a narrow x-ray window: only the HANDLE turns translucent — the antenna is
  // sealed inside its left leg (internal antenna = waterproofing); the rest
  // of the device stays opaque like overview
  {
    const spec = registry.componentSpec('PART_005');
    const e = spec && registry.get(spec.semanticId);
    if (e) materials.setLevel(e.object3D, 'XRAY', 0.8);
  }
  // subtle emissive lift marks the two radio parts
  for (const id of ['WIFI_ANTENNA', 'WIFI_MODULE']) {
    const e = registry.get(id);
    if (e) materials.setHover(e.object3D, true);
  }
}

/** Chapter click = straight to inspection layout (spec-rework: the staged
 *  sequence inside enterInspection already shows the locate/x-ray beat). */
async function inspectSystem(sys: string): Promise<void> {
  await machine.setMode('inspection', sys);
  // auto-extracted parts (fixture-released cores) are marked so a click
  // toggles them back IN rather than double-popping
  for (const [pid, spec] of Object.entries(manifest.components))
    if (spec.systemId === sys && spec.extractDirection) extracted.add(pid);
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
  if (s.mode === prev.mode && s.focusedSystem === prev.focusedSystem) return;
  backBtn.style.display = s.mode === 'overview' ? 'none' : 'block';
  inspectBtn.style.display = s.mode === 'xray' ? 'block' : 'none';
  interaction?.clearHover();
  interaction?.refreshPickables(scene);
  const sys = s.focusedSystem ? registry?.system(s.focusedSystem) : undefined;
  // transmission chapter: antenna -> cloud signal path rendered in-scene
  window.clearTimeout(txTimer);
  if (s.focusedSystem === 'SYS_TRANSMISSION' && s.mode !== 'overview')
    txTimer = window.setTimeout(buildTxFX, 1100);
  else clearTxFX();
  hud(
    s.mode === 'inspection' && sys
      ? s.focusedSystem === 'SYS_TRANSMISSION'
        ? `${sys.displayName} — antenna sealed inside the handle`
        : `${sys.displayName} — orbit freely, click a core to extract`
      : s.mode === 'xray' && sys
        ? s.focusedSystem === 'SYS_TRANSMISSION'
          ? `${sys.displayName} — field data leaves the device here`
          : `${sys.displayName} — inside the device`
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

// ---- transmission data-path FX ---------------------------------------------
// module -> antenna -> cloud, told with icons + motion only (no text):
// blinking activity dot on the radio module, feed-line pulses into the antenna,
// expanding broadcast rings + wifi glyph above the handle, dashed arc carrying
// pulse packets into a cloud node.

let txGroup: THREE.Group | null = null;
const ledMats = new Set<THREE.MeshStandardMaterial>();
const ledSprites: THREE.Sprite[] = [];
let ledT0 = 0;
let _ledGlowTex: THREE.Texture | null = null;
function ledGlowTex(): THREE.Texture {
  if (_ledGlowTex) return _ledGlowTex;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.3, 'rgba(255,255,255,0.95)');
  grad.addColorStop(0.55, 'rgba(255,255,255,0.3)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  _ledGlowTex = new THREE.CanvasTexture(c);
  return _ledGlowTex;
}

// shell colour customizer — car-configurator style preset swatches for the
// three exterior skins (upper cover / lower cover / handle). Colours persist
// in localStorage; MaterialStateManager never touches .color so choices
// survive every show/hide transition.
type ShellKey = 'upper' | 'lower' | 'handle';
const shellMats: Record<ShellKey, THREE.MeshStandardMaterial[]> = {
  upper: [], lower: [], handle: [],
};
// original PBR finish per material — a custom colour means "same paint job",
// so roughness/metalness/env are normalised to one finish; reset restores it
const shellOrig = new Map<THREE.MeshStandardMaterial,
  { roughness: number; metalness: number; envMapIntensity: number }>();
const CUSTOM_FINISH = { roughness: 0.55, metalness: 0.0, envMapIntensity: 0.5 };
const SHELL_DEFS: Record<ShellKey, string> = {
  upper: '#40444a', lower: '#ef6e27', handle: '#7c848e',
};
const SHELL_LABELS: Record<ShellKey, string> = {
  upper: '上盖', lower: '下盖', handle: '提手',
};
const SHELL_SWATCHES = ['#3f454c', '#9aa0a8', '#5f6b54', '#c2a273', '#e07020', '#31465e', '#d7d9d4'];
const SHELL_STORE = 'sf_shell_colors';
let shellSel: ShellKey = 'upper';

function shellColors(): Partial<Record<ShellKey, string>> {
  try { return JSON.parse(localStorage.getItem(SHELL_STORE) || '{}'); }
  catch { return {}; }
}
function setShellColor(
  key: ShellKey, hex: string,
  opts: { save?: boolean; restore?: boolean } = {},
): void {
  const { save = true, restore = false } = opts;
  for (const m of shellMats[key]) {
    m.color.set(hex);
    const o = shellOrig.get(m);
    if (!o) continue;
    // custom colour = one shared "paint" finish across all three shells, so
    // the same swatch reads the same on plastic and metal parts; reset puts
    // back the original finish (e.g. the handle's anodised metal look)
    const f = restore ? o : CUSTOM_FINISH;
    m.roughness = f.roughness;
    m.metalness = f.metalness;
    m.envMapIntensity = f.envMapIntensity;
  }
  if (save) {
    const all = shellColors();
    all[key] = hex;
    try { localStorage.setItem(SHELL_STORE, JSON.stringify(all)); } catch { /* private mode */ }
  }
}
function buildPalette(): void {
  const host = document.getElementById('palette');
  if (!host) return;
  host.innerHTML = '';
  const tabs = document.createElement('div');
  tabs.className = 'pal-tabs';
  const dots = document.createElement('div');
  dots.className = 'pal-dots';
  const markCurrent = () => {
    const cur = shellColors()[shellSel] || SHELL_DEFS[shellSel];
    dots.querySelectorAll('.pal-dot').forEach((d) =>
      d.classList.toggle('current', (d as HTMLElement).dataset.c === cur));
  };
  for (const key of ['upper', 'lower', 'handle'] as ShellKey[]) {
    const b = document.createElement('button');
    b.className = 'pal-tab' + (key === shellSel ? ' active' : '');
    b.textContent = SHELL_LABELS[key];
    b.onclick = () => {
      shellSel = key;
      tabs.querySelectorAll('.pal-tab').forEach((t) => t.classList.remove('active'));
      b.classList.add('active');
      markCurrent();
    };
    tabs.appendChild(b);
  }
  for (const hex of SHELL_SWATCHES) {
    const d = document.createElement('button');
    d.className = 'pal-dot';
    d.dataset.c = hex;
    d.style.background = hex;
    d.title = hex;
    d.onclick = () => { setShellColor(shellSel, hex); markCurrent(); };
    dots.appendChild(d);
  }
  const reset = document.createElement('button');
  reset.className = 'pal-dot reset';
  reset.textContent = '↺';
  reset.title = '恢复默认色';
  reset.onclick = () => {
    setShellColor(shellSel, SHELL_DEFS[shellSel], { restore: true });
    const all = shellColors();
    delete all[shellSel];
    try { localStorage.setItem(SHELL_STORE, JSON.stringify(all)); } catch { /* private mode */ }
    markCurrent();
  };
  dots.appendChild(reset);
  host.appendChild(tabs);
  host.appendChild(dots);
  markCurrent();
  // re-apply persisted choices now that materials exist
  for (const [key, hex] of Object.entries(shellColors()))
    if (key in shellMats) setShellColor(key as ShellKey, hex, { save: false });
}
let txCurve: THREE.QuadraticBezierCurve3 | null = null;
let txFeed: THREE.QuadraticBezierCurve3 | null = null;
let txPulses: THREE.Mesh[] = [];
let txFeedPulses: THREE.Mesh[] = [];
let txRings: THREE.Mesh[] = [];
let txDot: THREE.Mesh | null = null;
let txT = 0;
let txTimer = 0;

function iconSprite(draw: (g: CanvasRenderingContext2D) => void): THREE.Sprite {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 256;
  draw(c.getContext('2d')!);
  return new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(c), transparent: true, depthTest: false,
  }));
}

function wifiSprite(): THREE.Sprite {           // classic wifi glyph: dot + 3 arcs
  const sp = iconSprite((g) => {
    g.strokeStyle = 'rgba(140,210,255,0.95)';
    g.fillStyle = 'rgba(140,210,255,0.95)';
    g.lineWidth = 15; g.lineCap = 'round';
    for (const r of [48, 84, 120]) {
      g.beginPath(); g.arc(128, 196, r, Math.PI * 1.25, Math.PI * 1.75); g.stroke();
    }
    g.beginPath(); g.arc(128, 190, 15, 0, Math.PI * 2); g.fill();
  });
  sp.scale.set(0.052, 0.052, 1);
  return sp;
}

function cloudSprite(): THREE.Sprite {          // cloud glyph + upload arrow
  const sp = iconSprite((g) => {
    g.fillStyle = 'rgba(232,238,244,0.96)';
    const puff = (x: number, y: number, r: number) => {
      g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
    };
    puff(82, 140, 38); puff(128, 112, 50); puff(180, 136, 40); puff(130, 158, 44);
    g.strokeStyle = 'rgba(64,96,128,0.9)';
    g.lineWidth = 13; g.lineCap = 'round'; g.lineJoin = 'round';
    g.beginPath(); g.moveTo(128, 164); g.lineTo(128, 118); g.stroke();
    g.beginPath(); g.moveTo(108, 140); g.lineTo(128, 118); g.lineTo(148, 140); g.stroke();
  });
  sp.scale.set(0.095, 0.095, 1);
  return sp;
}

function clearTxFX(): void {
  if (txGroup) { scene.remove(txGroup); txGroup = null; }
  txPulses = []; txFeedPulses = []; txRings = [];
  txCurve = null; txFeed = null; txDot = null;
  for (const id of ['WIFI_ANTENNA', 'WIFI_MODULE']) {
    const e = registry?.get(id);
    if (e) {
      materials.setHover(e.object3D, false);
      materials.restore(e.object3D, 0.4);
    }
  }
}

function buildTxFX(): void {
  clearTxFX();
  const ant = registry.get('WIFI_ANTENNA');
  const mod = registry.get('WIFI_MODULE');
  if (!ant) return;
  const g = new THREE.Group();
  g.name = 'TX_FLOW';

  const tip = ant.object3D.getWorldPosition(new THREE.Vector3())
    .add(new THREE.Vector3(0, 0.032, 0));
  const cloudPos = new THREE.Vector3(0.19, 0.42, -0.12);
  const ctrl = tip.clone().lerp(cloudPos, 0.45).add(new THREE.Vector3(0, 0.14, 0));
  txCurve = new THREE.QuadraticBezierCurve3(tip, ctrl, cloudPos);

  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(txCurve.getPoints(72)),
    new THREE.LineDashedMaterial({
      color: 0x6fc8ff, dashSize: 0.014, gapSize: 0.009,
      transparent: true, opacity: 0.85,
    }),
  );
  line.computeLineDistances();
  g.add(line);

  const pg = new THREE.SphereGeometry(0.0032, 12, 12);
  const pm = new THREE.MeshBasicMaterial({ color: 0xa8e2ff });
  for (let i = 0; i < 5; i++) {
    const m = new THREE.Mesh(pg, pm);
    g.add(m); txPulses.push(m);
  }

  const cloud = cloudSprite();
  cloud.position.copy(cloudPos);
  g.add(cloud);

  // broadcast: expanding horizontal rings + wifi glyph above the handle
  const ringGeo = new THREE.RingGeometry(0.009, 0.0115, 48);
  const ringBase = tip.clone().add(new THREE.Vector3(0, 0.052, 0));
  for (let i = 0; i < 3; i++) {
    const r = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({
      color: 0x8cd2ff, transparent: true, opacity: 0.8,
      side: THREE.DoubleSide, depthWrite: false,
    }));
    r.rotation.x = -Math.PI / 2;
    r.position.copy(ringBase);
    g.add(r); txRings.push(r);
  }
  const wifi = wifiSprite();
  wifi.position.copy(ringBase).add(new THREE.Vector3(0, 0.062, 0));
  g.add(wifi);
  materials.setHover(ant.object3D, true);

  // feed: module -> antenna base, short dashed hop + blink on the module
  if (mod) {
    const mp = mod.object3D.getWorldPosition(new THREE.Vector3())
      .add(new THREE.Vector3(0, 0.014, 0));
    const feedBase = tip.clone().add(new THREE.Vector3(0, -0.014, 0));
    txFeed = new THREE.QuadraticBezierCurve3(
      mp, mp.clone().lerp(feedBase, 0.5).add(new THREE.Vector3(0, 0.055, 0)), feedBase,
    );
    const fl = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(txFeed.getPoints(32)),
      new THREE.LineDashedMaterial({
        color: 0x6fc8ff, dashSize: 0.008, gapSize: 0.005,
        transparent: true, opacity: 0.6,
      }),
    );
    fl.computeLineDistances();
    g.add(fl);
    for (let i = 0; i < 3; i++) {
      const m = new THREE.Mesh(pg, pm.clone());
      g.add(m); txFeedPulses.push(m);
    }
    txDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.0038, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x9fdcff, transparent: true }),
    );
    txDot.position.copy(mp);
    g.add(txDot);
    materials.setHover(mod.object3D, true);
  }

  scene.add(g);
  txGroup = g;
}

renderer.setAnimationLoop(() => {
  tweens.update();
  cameraCtl?.update();
  // top-cover LEDs: ~0.3s red self-test flash for the first 10s after
  // load, then settle into a ~1s green heartbeat blink. Dome emissive +
  // glow sprite are driven together so the blink reads at overview distance.
  if (ledMats.size) {
    const lt = (performance.now() - ledT0) / 1000;
    const boot = lt < 10;
    const on = boot ? lt % 0.3 < 0.15 : lt % 1.0 < 0.16;
    const c = boot ? [0.85, 0.04, 0.015] : [0.12, 0.8, 0.2];
    for (const m of ledMats) {
      m.emissive.setRGB(on ? c[0] : 0.01, on ? c[1] : 0.01, on ? c[2] : 0.01);
      m.emissiveIntensity = on ? 4.5 : 0.6;
    }
    // sprite opacity follows the LED lens material so the glow fades out
    // whenever the top cover is dimmed/hidden by the state machine
    const coverOp = ledMats.values().next().value?.opacity ?? 1;
    for (const sp of ledSprites) {
      const sm = sp.material as THREE.SpriteMaterial;
      sm.color.setRGB(c[0], c[1], c[2]);
      sm.opacity = on ? 0.75 * coverOp : 0.0;
    }
  }
  if (txGroup) {
    txT += 0.008;
    if (txCurve) {
      txPulses.forEach((m, i) => {
        const t = (txT + i / txPulses.length) % 1;
        m.position.copy(txCurve!.getPointAt(t));
      });
    }
    if (txFeed) {
      txFeedPulses.forEach((m, i) => {
        const t = (txT * 1.25 + i / txFeedPulses.length) % 1;
        m.position.copy(txFeed!.getPointAt(t));
      });
    }
    txRings.forEach((r, i) => {
      const t = (txT * 0.45 + i / txRings.length) % 1;
      r.scale.setScalar(1 + t * 3.4);
      (r.material as THREE.MeshBasicMaterial).opacity = (1 - t) * 0.75;
      r.position.y += 0;
    });
    if (txDot) {
      (txDot.material as THREE.MeshBasicMaterial).opacity =
        0.35 + 0.65 * Math.abs(Math.sin(txT * 22));
    }
  }
  renderer.render(scene, camera);
});

void boot();
