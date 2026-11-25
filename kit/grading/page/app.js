// Owner Grading — the kit's local three.js viewer + the owner's 0-10 score and words per model (kit rate serve <round>,
// 127.0.0.1 only). The round: /api/round (models + their reference pictures); scores: /api/ratings, POST /api/rate.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const $ = (id) => document.getElementById(id);
const canvas = $("view");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const pmrem = new THREE.PMREMGenerator(renderer);
const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

function makeScene() {
  const s = new THREE.Scene();
  s.environment = envTex;
  s.background = new THREE.Color(0x24242b);
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-3, 6, -4);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  s.add(key);
  const fill = new THREE.DirectionalLight(0xbcd2ff, 0.5);
  fill.position.set(4, 2, 3);
  s.add(fill);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(12, 64), new THREE.ShadowMaterial({ opacity: 0.35 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  s.add(ground);
  const grid = new THREE.GridHelper(12, 12 * 4, 0x55555f, 0x33333b); // quarter-stud lines, 1 stud = 1 unit
  grid.material.transparent = true;
  grid.material.opacity = 0.55;
  s.add(grid);
  const r6 = makeR6();
  r6.visible = false;
  s.add(r6);
  return { scene: s, key, fill, grid, r6, model: null };
}

function makeR6() {
  // R6: legs 1x2x1, torso 2x2x1, arms 1x2x1, head ~1.2x1x1 = 5 studs; stands left of the item
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: 0x5b78a8, roughness: 0.7 });
  const box = (w, h, d, x, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = true; g.add(m); };
  box(1, 2, 1, -0.5, 1, 0); box(1, 2, 1, 0.5, 1, 0); box(2, 2, 1, 0, 3, 0);
  box(1, 2, 1, -1.5, 3, 0); box(1, 2, 1, 1.5, 3, 0); box(1.2, 1, 1, 0, 4.5, 0);
  return g;
}

const A = makeScene(), B = makeScene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 200);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
const loader = new GLTFLoader();
const cache = new Map();

const state = { items: [], ratings: {}, idx: 0, look: "tex", light: "studio", compare: false, cmp: null, r6: false, view: "q34" };

function fit(slot) {
  const m = slot.model;
  if (!m) return { center: new THREE.Vector3(), size: 3 };
  const box = new THREE.Box3().setFromObject(m);
  const size = box.getSize(new THREE.Vector3());
  return { center: box.getCenter(new THREE.Vector3()), size: Math.max(size.x, size.y, size.z) };
}

async function loadGLB(item) {
  const url = `./round/${item.glb}`;
  if (!cache.has(url)) cache.set(url, loader.loadAsync(url));
  const gltf = await cache.get(url);
  const root = gltf.scene.clone(true);
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.userData.tex = o.material; } });
  return root;
}

function applyLook(slot) {
  if (!slot.model) return;
  slot.model.traverse((o) => {
    if (!o.isMesh) return;
    if (state.look === "tex") o.material = o.userData.tex;
    else if (state.look === "clay") o.material = new THREE.MeshStandardMaterial({ color: 0xb9b6b0, roughness: 0.62, metalness: 0 });
    else o.material = new THREE.MeshBasicMaterial({ color: 0xe9e6e1, wireframe: true });
  });
}

function applyLight(slot) {
  const L = { studio: [0x24242b, 1.6, 0.5, 1.0], bright: [0xd9d7d2, 2.2, 0.9, 1.25], moody: [0x0c0c0f, 1.3, 0.15, 0.55] }[state.light];
  slot.scene.background.set(L[0]);
  slot.key.intensity = L[1];
  slot.fill.intensity = L[2];
  slot.scene.environmentIntensity = L[3];
  slot.grid.visible = $("tGrid").classList.contains("on");
}

function placeItem(slot) {
  // the item as built (Roblox frame, studs), on the ground; with the R6 on: beside it
  const m = slot.model;
  if (!m) return;
  m.position.set(0, 0, 0);
  const box = new THREE.Box3().setFromObject(m);
  m.position.y -= box.min.y;
  m.position.x -= (box.min.x + box.max.x) / 2;
  m.position.z -= (box.min.z + box.max.z) / 2;
  slot.r6.visible = state.r6;
  if (state.r6) slot.r6.position.set(-(1.6 + (box.max.x - box.min.x) / 2 + 0.6), 0, 0);
}

async function setSlot(slot, item) {
  if (slot.model) slot.scene.remove(slot.model);
  slot.model = null;
  if (!item) return;
  $("loading").style.display = "flex";
  try { slot.model = await loadGLB(item); } catch (e) { $("loading").textContent = `could not load ${item.asset}`; return; }
  slot.scene.add(slot.model);
  $("loading").style.display = "none";
  applyLook(slot); applyLight(slot); placeItem(slot);
}

function setView(v) {
  state.view = v;
  const slots = state.compare ? [A, B] : [A];
  let size = 0;
  const c = new THREE.Vector3();
  for (const s of slots) { const f = fit(s); size = Math.max(size, f.size); c.add(f.center); }
  c.divideScalar(slots.length);
  if (state.r6) { size = Math.max(size, 6); c.y = Math.max(c.y, 2.5); }
  const d = size * 1.9 + 0.4;
  const dirs = { q34: [0.75, 0.42, -0.85], front: [0, 0.02, -1], side: [1, 0.02, 0], back: [0, 0.02, 1], top: [0.0001, 1, -0.0001] };
  camera.position.copy(c).addScaledVector(new THREE.Vector3(...dirs[v]).normalize(), d);
  controls.target.copy(c);
  camera.near = d / 200; camera.far = d * 50; camera.updateProjectionMatrix();
  controls.update();
  document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
}

const cur = () => state.items[state.idx];
const fmt = (s) => (s == null ? "–" : String(s));

function renderList() {
  $("list").innerHTML = "";
  state.items.forEach((it, i) => {
    const r = state.ratings[it.asset] || {};
    const d = document.createElement("div");
    d.className = "cand" + (i === state.idx ? " on" : "");
    const lab = document.createElement("span"); lab.className = "lab"; lab.textContent = it.asset;
    const sc = document.createElement("span"); sc.className = "sc" + (r.score != null ? " has" : ""); sc.textContent = fmt(r.score);
    d.append(lab, sc);
    d.onclick = () => select(i);
    $("list").appendChild(d);
  });
  const done = state.items.filter((it) => (state.ratings[it.asset] || {}).score != null).length;
  $("progress").innerHTML = `<b>${done}/${state.items.length}</b> scored`;
  const sel = $("cmpSel");
  sel.innerHTML = "";
  state.items.forEach((it) => { const o = document.createElement("option"); o.value = it.asset; o.textContent = `vs ${it.asset}`; sel.appendChild(o); });
  const other = state.items[(state.idx + 1) % state.items.length];
  sel.value = state.cmp && state.items.some((x) => x.asset === state.cmp) ? state.cmp : (other || {}).asset;
}

function renderRefs() {
  const it = cur();
  const tabs = $("reftabs");
  tabs.innerHTML = "";
  const refs = (it && it.refs) || [];
  $("refimg").style.display = refs.length ? "block" : "none";
  $("noref").textContent = refs.length ? "" : "no reference picture in this build";
  refs.forEach((r, i) => {
    const b = document.createElement("button");
    b.className = "btn" + (i === 0 ? " on" : "");
    b.textContent = r.label;
    b.onclick = () => { $("refimg").src = `./round/${r.file}`; tabs.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); };
    tabs.appendChild(b);
  });
  if (refs.length) $("refimg").src = `./round/${refs[0].file}`;
}

function showScore() {
  const it = cur();
  const r = (it && state.ratings[it.asset]) || {};
  $("curLab").textContent = it ? it.asset : "";
  $("labA").textContent = it ? it.asset : "";
  $("score").value = r.score != null ? r.score : 5;
  $("scoreNum").textContent = fmt(r.score);
  $("words").value = r.words || "";
  $("status").textContent = r.at ? `saved ${r.at}` : "not scored yet";
  $("status").className = "status" + (r.at ? " ok" : "");
}

async function select(i) {
  if (!state.items.length) return;
  state.idx = (i + state.items.length) % state.items.length;
  renderList(); renderRefs(); showScore();
  await setSlot(A, cur());
  if (state.compare) await setSlot(B, state.items.find((x) => x.asset === $("cmpSel").value));
  setView(state.view);
}

let dirty = false;
async function save(advance) {
  const it = cur();
  if (!it) return;
  const body = { asset: it.asset, score: Number($("score").value), words: $("words").value };
  const res = await fetch("./api/rate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await res.json();
  if (!res.ok) { $("status").textContent = "save failed: " + (j.error || res.status); $("status").className = "status"; return; }
  state.ratings[it.asset] = j.saved;
  dirty = false;
  renderList(); showScore();
  if (advance) select(state.idx + 1);
}

document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
document.querySelectorAll("[data-look]").forEach((b) => (b.onclick = () => {
  state.look = b.dataset.look;
  document.querySelectorAll("[data-look]").forEach((x) => x.classList.toggle("on", x === b));
  applyLook(A); applyLook(B);
}));
document.querySelectorAll("[data-light]").forEach((b) => (b.onclick = () => {
  state.light = b.dataset.light;
  document.querySelectorAll("[data-light]").forEach((x) => x.classList.toggle("on", x === b));
  applyLight(A); applyLight(B);
}));
$("tRot").onclick = () => { controls.autoRotate = !controls.autoRotate; $("tRot").classList.toggle("on", controls.autoRotate); };
$("tR6").onclick = () => { state.r6 = !state.r6; $("tR6").classList.toggle("on", state.r6); placeItem(A); placeItem(B); setView(state.view); };
$("tGrid").onclick = () => { $("tGrid").classList.toggle("on"); applyLight(A); applyLight(B); };
$("tCmp").onclick = async () => {
  state.compare = !state.compare;
  $("tCmp").classList.toggle("on", state.compare);
  $("labB").style.display = state.compare ? "block" : "none";
  if (state.compare) { state.cmp = $("cmpSel").value; $("labB").textContent = state.cmp; await setSlot(B, state.items.find((x) => x.asset === state.cmp)); }
  setView(state.view);
};
$("cmpSel").onchange = async () => { state.cmp = $("cmpSel").value; $("labB").textContent = state.cmp; if (state.compare) { await setSlot(B, state.items.find((x) => x.asset === state.cmp)); setView(state.view); } };
$("score").oninput = () => { $("scoreNum").textContent = $("score").value; dirty = true; $("status").textContent = "unsaved"; $("status").className = "status"; };
$("words").oninput = () => { dirty = true; $("status").textContent = "unsaved"; $("status").className = "status"; };
$("save").onclick = () => save(true);
$("prev").onclick = () => select(state.idx - 1);
$("next").onclick = () => select(state.idx + 1);
[0, 2, 4, 5, 6, 7, 7.5, 8, 8.5, 9, 9.5, 10].forEach((v) => {
  const b = document.createElement("button");
  b.textContent = v;
  b.onclick = () => { $("score").value = v; $("score").oninput(); };
  $("quick").appendChild(b);
});
addEventListener("keydown", (e) => {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
  const k = e.key.toLowerCase();
  if (k === "arrowright") select(state.idx + 1);
  else if (k === "arrowleft") select(state.idx - 1);
  else if ("12345".includes(k) && k.length === 1) setView(["q34", "front", "side", "back", "top"][Number(k) - 1]);
  else if (k === "t" || k === "c" || k === "w") document.querySelector(`[data-look="${{ t: "tex", c: "clay", w: "wire" }[k]}"]`).click();
  else if (k === "r") $("tRot").click();
  else if (k === "m") $("tR6").click();
  else if (k === "x") $("tCmp").click();
  else if (k === "enter") save(true);
});
addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

function resize() { renderer.setSize(canvas.clientWidth, canvas.clientHeight, false); }
addEventListener("resize", resize);

function frame() {
  requestAnimationFrame(frame);
  controls.update();
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio())) resize();
  renderer.setScissorTest(true);
  if (state.compare) {
    camera.aspect = (w / 2) / h; camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, w / 2, h); renderer.setScissor(0, 0, w / 2, h); renderer.render(A.scene, camera);
    renderer.setViewport(w / 2, 0, w / 2, h); renderer.setScissor(w / 2, 0, w / 2, h); renderer.render(B.scene, camera);
  } else {
    camera.aspect = w / h; camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, w, h); renderer.setScissor(0, 0, w, h); renderer.render(A.scene, camera);
  }
}

(async () => {
  const round = await (await fetch("./api/round")).json();
  state.items = round.items || [];
  state.ratings = await (await fetch("./api/ratings")).json();
  $("roundName").textContent = round.round ? `round ${round.round}` : "";
  resize();
  frame();
  if (!state.items.length) { $("loading").textContent = "this round has no models"; return; }
  await select(0);
})();
