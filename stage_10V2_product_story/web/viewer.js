import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const app = document.getElementById("app");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x24282f);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

const camera = new THREE.PerspectiveCamera(30, innerWidth / innerHeight, 1, 20000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;

const keyLight = new THREE.DirectionalLight(0xffffff, 1.6);
keyLight.position.set(300, -400, 700);
scene.add(keyLight);
scene.add(new THREE.AmbientLight(0xffffff, 0.25));

const manifest = await (await fetch("./story_manifest.json")).json();
const FPS = manifest.fps;
const FRAME0 = manifest.frame_start;
const N_FRAMES = manifest.frame_end - FRAME0 + 1;
const DURATION = N_FRAMES / FPS;

const partIdOf = (name) => {
  if (name.startsWith("PCB_COMP_")) return name;
  const m = name.match(/^PART_(\d{3})/);
  return m ? m[0] : null;
};
const isSourceHidden = (pid) =>
  pid && pid.startsWith("PART_") && parseInt(pid.slice(5), 10) >= 23;

const gltf = await new GLTFLoader().loadAsync("./" + manifest.glb);
const model = gltf.scene;
model.traverse((node) => {
  const pid = node.name ? partIdOf(node.name) : null;
  if (node.name && node.name.startsWith("T10V2_")) node.visible = false;
  if (pid && isSourceHidden(pid)) node.visible = false;
  node.userData.partId = pid;
});
scene.add(model);

const mixer = new THREE.AnimationMixer(model);
const clips = gltf.animations;
const action = clips.length ? mixer.clipAction(clips[0]) : null;
if (action) action.play();
mixer.setTime(0);

const scrub = document.getElementById("scrub");
const timeLabel = document.getElementById("time");
const playBtn = document.getElementById("play");
const titleEl = document.getElementById("shotTitle");
const subEl = document.getElementById("shotSub");
const shotsEl = document.getElementById("shots");

let playing = false;
let camTween = null;

function shotAt(t) {
  const frame = FRAME0 + t * FPS;
  return manifest.shots.find((s) => frame < s.frame_end + 1) || manifest.shots.at(-1);
}

function applyVisibility(shot) {
  const subjects = new Set(shot.subject_parts);
  model.traverse((node) => {
    const pid = node.userData.partId;
    if (!pid || (node.name && node.name.startsWith("T10V2_"))) return;
    if (isSourceHidden(pid)) { node.visible = false; return; }
    if (shot.mode !== "isolate") { node.visible = true; return; }
    const isSubject =
      subjects.has(pid) ||
      (shot.focus_components && pid.startsWith("PCB_COMP_"));
    node.visible = isSubject;
  });
}

function flyTo(shot) {
  const preset = manifest.cameras[shot.camera];
  if (!preset) return;
  camTween = {
    t0: performance.now(),
    dur: 700,
    fromPos: camera.position.clone(),
    toPos: new THREE.Vector3(...preset.location),
    fromTgt: controls.target.clone(),
    toTgt: new THREE.Vector3(...preset.target),
  };
}

let lastShot = null;
function gotoShot(shot, jumpTime = true) {
  if (jumpTime) mixer.setTime((shot.frame_start - FRAME0 + 2) / FPS);
  applyVisibility(shot);
  flyTo(shot);
  titleEl.textContent = shot.title;
  subEl.textContent = shot.shot_id.toLowerCase().replaceAll("_", " ");
  [...shotsEl.children].forEach((b) =>
    b.classList.toggle("active", b.dataset.id === shot.shot_id));
}

for (const shot of manifest.shots) {
  const b = document.createElement("button");
  b.textContent = shot.title;
  b.dataset.id = shot.shot_id;
  b.onclick = () => { playing = false; playBtn.textContent = "▶ play"; gotoShot(shot); };
  shotsEl.appendChild(b);
}

playBtn.onclick = () => {
  playing = !playing;
  playBtn.textContent = playing ? "⏸ pause" : "▶ play";
};
scrub.oninput = () => {
  playing = false;
  playBtn.textContent = "▶ play";
  mixer.setTime((scrub.value / 899) * DURATION);
};

const clock = new THREE.Clock();
function tick() {
  requestAnimationFrame(tick);
  const dt = clock.getDelta();
  if (playing && action) {
    mixer.update(dt);
    const t = mixer.time % DURATION;
    scrub.value = Math.round((t / DURATION) * 899);
  }
  const t = mixer.time;
  const shot = shotAt(t);
  if (shot !== lastShot) {
    lastShot = shot;
    gotoShot(shot, false);
  }
  const ss = Math.floor(t % 60), mm = Math.floor(t / 60);
  timeLabel.textContent = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  if (camTween) {
    const k = Math.min(1, (performance.now() - camTween.t0) / camTween.dur);
    const e = 1 - Math.pow(1 - k, 3);
    camera.position.lerpVectors(camTween.fromPos, camTween.toPos, e);
    controls.target.lerpVectors(camTween.fromTgt, camTween.toTgt, e);
    if (k >= 1) camTween = null;
  }
  controls.update();
  renderer.render(scene, camera);
}
gotoShot(manifest.shots[0]);
tick();

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
