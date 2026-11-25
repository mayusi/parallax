// player.js — the kit's browser player for version-3 VFX presets (kit vfx play). Plays a preset with the rules
// measured in Roblox (additive sprites + flipbooks, beams whose texture runs along their length, standing walls,
// runtime meshes, lights, debris, screen grades, impact frames, shake, fov, hit-stop, sounds, camera paths) at full
// frame rate in any browser, with a scrub bar, layer mutes and live METRICS (intensity curve, coverage, palette,
// live particles). Not pixel-identical to Roblox — the Studio booth stays the final truth — but seconds, not minutes.
// Record mode (?record=1&view=cine&fps=24): steps the clock deterministically and POSTs every frame + the metrics to
// the kit's local capture server, which writes the mp4, the contact sheet and <name>.metrics.json.
import * as THREE from "/lib/vendor/three.module.js";

const Q = Object.fromEntries(new URL(location.href).searchParams.entries());

// ---------------------------------------------------------------- sequences (the same shapes as VfxStage.luau)
function numAt(v, u, dflt, e) { // e in [-1, 1]: this particle's draw inside each keypoint's envelope {t, v, envelope} (Roblox's)
  if (v == null) return dflt;
  if (typeof v === "number") return v;
  const at = (q) => q[1] + (e && q[2] ? q[2] * e : 0);
  for (let i = 0; i < v.length - 1; i++) {
    const a = v[i], b = v[i + 1];
    if (u <= b[0]) {
      const k = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 0;
      return at(a) + (at(b) - at(a)) * Math.min(Math.max(k, 0), 1);
    }
  }
  return at(v[v.length - 1]);
}
function isSeq(v) { return Array.isArray(v) && Array.isArray(v[0]); }
function rgb(c, palette) {
  if (typeof c === "string") c = (palette && palette[c]) || [255, 0, 255];
  return new THREE.Color(c[0] / 255, c[1] / 255, c[2] / 255);
}
function colorAt(v, u, palette) {
  if (v == null) return new THREE.Color(1, 1, 1);
  if (!isSeq(v)) return rgb(v, palette);
  for (let i = 0; i < v.length - 1; i++) {
    const a = v[i], b = v[i + 1];
    if (u <= b[0]) {
      const k = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 0;
      return rgb(a[1], palette).lerp(rgb(b[1], palette), Math.min(Math.max(k, 0), 1));
    }
  }
  return rgb(v[v.length - 1][1], palette);
}
function vecAt(v, u) {
  const toV = (x) => (typeof x === "number" ? new THREE.Vector3(x, x, x) : new THREE.Vector3(x[0], x[1], x[2]));
  if (typeof v === "number" || (Array.isArray(v) && typeof v[0] === "number")) return toV(v);
  for (let i = 0; i < v.length - 1; i++) {
    const a = v[i], b = v[i + 1];
    if (u <= b[0]) {
      const k = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 0;
      return toV(a[1]).lerp(toV(b[1]), Math.min(Math.max(k, 0), 1));
    }
  }
  return toV(v[v.length - 1][1]);
}
function rangeRand(v, rng) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  return v[0] + (v[1] - v[0]) * rng();
}
function ease(k, style) {
  k = Math.min(Math.max(k, 0), 1);
  if (style === "in") return k * k;
  if (style === "linear") return k;
  return 1 - (1 - k) * (1 - k) * (1 - k);
}
function mulberry(seed) { // a small deterministic rng (record mode must be repeatable)
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
// calibration multipliers (brightness curves measured against the Roblox booth; see kit/vfx/calibrate.py)
const CAL_DEFAULT = Object.freeze({ sprite: 0.4, beam: 0.7, light: 18 }); // rounds 3-9 (hand-set): the charge phase follows sprites, the hit follows beams, the base is the arena
const CAL = { ...CAL_DEFAULT };
// MEASURED CALIBRATION (LIMITATIONS_FIXES_V4 VFX-X / Phase 1 item 3): assets/effects/_calibrated.json rides in the bundle
// (bundle.calibration: kit/vfx/calibrate.py fit - a least-squares fit of the Studio booth against this player under
// each judging sky). Its "all" multipliers, then the preset's own sky's, laid over the hand-set ones; none: the hand-set
// ones, said in the metrics -> where the numbers came from
function applyCalibration(cal, sky) {
  Object.assign(CAL, CAL_DEFAULT);
  if (!cal || typeof cal !== "object") return "hand-set (no assets/effects/_calibrated.json)";
  const pick = (o) => { for (const k of Object.keys(CAL_DEFAULT)) if (o && typeof o[k] === "number" && isFinite(o[k]) && o[k] > 0) CAL[k] = o[k]; };
  pick(cal.all);
  const own = cal.skies && cal.skies[sky];
  pick(own);
  return own ? `measured (${sky})` : (cal.all ? "measured (all skies)" : "hand-set (the calibration names no multipliers)");
}
// CAL.sprite was measured on ADDITIVE glow (LightEmission 1): a normal-blended sprite (LightEmission 0, an unlit smoke puff) is
// drawn at its texture's own colour, so the multiplier scales with lightEmission (2026-10-18: smoke read 2.5x too dark)
const DEG = Math.PI / 180;
// the judging skies (booth.sky): night = the original arena, day = the original daylight; overcast / sunset added
// 2026-10-18 for realism judging (a big blast must read under the light the game will actually have)
const SKIES = {
  night: { fog: 0x0d0a12, density: 0.0018, background: null, hemi: [0x50506a, 0x1e1a18, 0.07], sun: [0xffb070, 0.17], sunPos: [-60, 40, 60], floor: 0x3f3626, zenith: 0x05061a, horizon: 0x0e0c17, ground: 0x06050a },
  day: { fog: 0xbcd8f2, density: 0.0011, background: 0x8fc0f0, hemi: [0xcfe4ff, 0x8a7a64, 1.05], sun: [0xfff6e6, 1.5], sunPos: [-60, 90, 60], floor: 0xc2ab84, zenith: 0x2f78e0, horizon: 0xc4e2ff, ground: 0x9c8b70 },
  overcast: { fog: 0xa9adb3, density: 0.0024, background: 0x9da2a8, hemi: [0xc9ccd2, 0x6d675f, 1.15], sun: [0xe8ecf0, 0.35], sunPos: [-20, 120, 30], floor: 0x8f8574, zenith: 0x7f858e, horizon: 0xb7bbc0, ground: 0x6f685e },
  sunset: { fog: 0xc98a62, density: 0.0016, background: 0xd88a55, hemi: [0xffb98a, 0x4a3a40, 0.55], sun: [0xff9a52, 1.6], sunPos: [-120, 18, 40], floor: 0x9a7552, zenith: 0x3a4a86, horizon: 0xffa866, ground: 0x4a3830 },
};

// ---------------------------------------------------------------- textures
const texCache = new Map();
// every texture load in flight: a recording must not draw frame 1 before its pictures arrive (a layer in the first
// fraction of a second recorded invisible - flame_arc's ignition licks, 2026-10-16)
const texPending = new Set();
function loadTex(url) {
  let done;
  const pr = new Promise((r) => { done = r; });
  texPending.add(pr);
  const settle = () => { texPending.delete(pr); done(); };
  return new THREE.TextureLoader().load(url, settle, undefined, settle);
}
export async function texturesSettled(ms = 8000) { // resolves when every texture asked for so far has loaded (or failed), or after ms
  const until = performance.now() + ms;
  while (texPending.size && performance.now() < until) await Promise.race([Promise.all([...texPending]), new Promise((r) => setTimeout(r, 100))]);
  return texPending.size === 0;
}
// view variants (impostors): the texture whose yaw is nearest the camera's angle round the effect (VfxStage.pickView)
function pickView(views, p) {
  const c = p.camera.position.clone().sub(p.origin || new THREE.Vector3());
  const yaw = ((Math.atan2(-c.x, c.z) * 180 / Math.PI) % 360 + 360) % 360;
  let best = null, bestD = Infinity;
  for (const [k, tex] of Object.entries(views)) { const d = Math.abs(((yaw - Number(k)) + 540) % 360 - 180); if (d < bestD) { best = tex; bestD = d; } }
  return best;
}
// surface-aware layers: `onMaterial` overrides picked by the ground material (VfxStage withMaterial: same rule)
function withMaterial(el, mat) {
  const om = el.onMaterial; if (!om) return el;
  let pick = null;
  for (const [pattern, over] of Object.entries(om)) if (pattern !== "*" && pattern.split("|").includes(mat)) pick = over;
  pick = pick || om["*"]; if (!pick) return el;
  if (pick.mute) return null;
  const c = Object.assign({}, el, pick); delete c.onMaterial; return c;
}
// lit variants (a sprite's `lit` = { left, right, top, back, front }): the texture whose baked key light matches where the
// scene's sun is seen from the camera - the same rule as VfxStage.pickLit (sun high = top)
function pickLit(lit, p) {
  const want = (() => {
    const sun = p.env && p.env.sun ? p.env.sun.position.clone().normalize() : new THREE.Vector3(0, 1, 0);
    if (sun.y >= 0.6) return "top"; // a sun above ~37 degrees lights the top (VfxStage.pickLit: same rule)
    const travel = new THREE.Vector3(-sun.x, 0, -sun.z);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(p.camera.quaternion);
    const look = new THREE.Vector3(0, 0, -1).applyQuaternion(p.camera.quaternion); look.y = 0; if (look.lengthSq() > 1e-6) look.normalize();
    const dr = travel.dot(right), df = travel.dot(look);
    return Math.abs(dr) >= Math.abs(df) ? (dr > 0 ? "left" : "right") : (df > 0 ? "front" : "back");
  })();
  if (lit[want]) return lit[want];
  for (const k of ["top", "left", "right", "front", "back"]) if (lit[k]) return lit[k];
  return null;
}
// blockout (kit vfx play --blockout): every texture becomes one soft blob and meshes go plain, so an effect's TIMING
// and SHAPES are judged before any texture work (the pros block in, in context, first: GDC 2023 VFX roundtable)
let blockTex = null;
function blockoutTexture() {
  if (blockTex) return blockTex;
  const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.55, "rgba(255,255,255,0.85)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  blockTex = new THREE.CanvasTexture(c); blockTex.colorSpace = THREE.SRGBColorSpace; return blockTex;
}
function texture(bundle, key) {
  if (!key) return null;
  if (bundle.blockout) return blockoutTexture();
  const e = bundle.textures[key];
  if (!e) return null;
  if (!texCache.has(key)) {
    const t = loadTex(e.url);
    t.colorSpace = THREE.SRGBColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    texCache.set(key, t);
  }
  return texCache.get(key);
}
function gridOf(bundle, key) { const e = bundle.textures[key]; return e ? (Array.isArray(e.grid) ? e.grid : [e.grid || 1, e.grid || 1]) : [1, 1]; }

// ---------------------------------------------------------------- sprites: one instanced quad mesh per layer, CPU sim
const SPRITE_VS = `
attribute vec3 iPos; attribute vec3 iVel; attribute vec4 iMisc; // size, rot(rad), squash, alpha
attribute vec4 iColor; attribute vec3 iFrame; // frame a, frame b, crossfade t (Roblox FlipbookBlendFrames)
uniform int orientation; uniform float cells; uniform vec2 grid; uniform float zOff;
varying vec2 vUv; varying vec2 vUv2; varying float vMix; varying vec4 vColor;
vec2 cellUv(float f) { float col = mod(f, grid.x); float row = floor(f / grid.x); return vec2((uv.x + col) / grid.x, 1.0 - (1.0 - uv.y + row) / grid.y); }
void main() {
  vec2 corner = position.xy; // -0.5..0.5
  float s = iMisc.x; float rot = iMisc.y; float sq = iMisc.z;
  vec2 sz = vec2(s / (1.0 + max(sq, 0.0)), s * (1.0 + max(sq, 0.0)));
  if (sq < 0.0) sz = vec2(s * (1.0 - sq), s / (1.0 - sq));
  vec2 c = corner * sz;
  float cr = cos(rot), sr = sin(rot);
  vec2 r = vec2(c.x * cr - c.y * sr, c.x * sr + c.y * cr);
  vec3 right, up;
  vec3 toCam = normalize(cameraPosition - iPos);
  if (orientation == 2) { // VelocityParallel: like Roblox, the texture's UP runs along the velocity (streak textures are
    // drawn vertical; squash stretches along it). The quad's X along it drew every spark as a bar across its path (2026-10-15)
    vec3 d = length(iVel) > 1e-4 ? normalize(iVel) : vec3(0.0, 1.0, 0.0);
    up = d; right = normalize(cross(d, toCam)); if (length(right) < 1e-4) right = vec3(1.0, 0.0, 0.0);
  } else if (orientation == 3) { // VelocityPerpendicular: the quad lies across the velocity (its normal = velocity)
    vec3 n = length(iVel) > 1e-4 ? normalize(iVel) : vec3(0.0, 1.0, 0.0);
    vec3 a = abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    right = normalize(cross(a, n)); up = cross(n, right);
  } else if (orientation == 1) { // FacingCameraWorldUp
    up = vec3(0.0, 1.0, 0.0); right = normalize(cross(up, toCam));
  } else { // FacingCamera
    right = normalize(cross(vec3(0.0, 1.0, 0.0), toCam)); if (length(right) < 1e-4) right = vec3(1.0, 0.0, 0.0); up = cross(toCam, right);
  }
  vec3 world = iPos + right * r.x + up * r.y + toCam * zOff; // ZOffset: Roblox pushes the sprite toward the camera (studs)
  gl_Position = projectionMatrix * viewMatrix * vec4(world, 1.0);
  vUv = cellUv(iFrame.x); vUv2 = cellUv(iFrame.y); vMix = iFrame.z;
  vColor = vec4(iColor.rgb, iColor.a * iMisc.w); // iMisc.w = 1 - the transparency curve: written since the player's first version, never READ until 2026-10-22 (every sprite showed no fade in / out)
}`;
const SPRITE_FS = `
uniform sampler2D map; uniform float lightEmission; uniform float brightness; uniform float dimming;
varying vec2 vUv; varying vec2 vUv2; varying float vMix; varying vec4 vColor;
void main() {
  vec4 t = texture2D(map, vUv);
  if (vMix > 0.0) t = mix(t, texture2D(map, vUv2), vMix); // the game's linear crossfade between flipbook frames
  float a = t.a * vColor.a;
  vec3 c = t.rgb * vColor.rgb * brightness * dimming;
  // Roblox: LightEmission 1 = additive, 0 = alpha blend; in between = a mix. Premultiplied output with ONE blend
  // mode (src + dst * (1 - src.a)): additive = colour kept, alpha 0.
  float le = clamp(lightEmission, 0.0, 1.0);
  gl_FragColor = vec4(c * a, a * (1.0 - le));
}`;

class SpriteLayer {
  constructor(player, el) {
    this.p = player; this.el = el; this.rng = mulberry(player.seed + hashName(el.name));
    const b = player.bundle;
    const max = Math.min(1500, (el.count || 0) + Math.ceil((el.rate || 0) * ((el.for || 0) + maxLife(el.lifetime))) + 2);
    this.max = max;
    const geo = new THREE.InstancedBufferGeometry();
    const base = new THREE.PlaneGeometry(1, 1);
    geo.index = base.index; geo.attributes.position = base.attributes.position; geo.attributes.uv = base.attributes.uv;
    this.pos = new Float32Array(max * 3); this.vel = new Float32Array(max * 3); this.misc = new Float32Array(max * 4);
    this.col = new Float32Array(max * 4); this.frame = new Float32Array(max * 3);
    geo.setAttribute("iPos", new THREE.InstancedBufferAttribute(this.pos, 3));
    geo.setAttribute("iVel", new THREE.InstancedBufferAttribute(this.vel, 3));
    geo.setAttribute("iMisc", new THREE.InstancedBufferAttribute(this.misc, 4));
    geo.setAttribute("iColor", new THREE.InstancedBufferAttribute(this.col, 4));
    geo.setAttribute("iFrame", new THREE.InstancedBufferAttribute(this.frame, 3));
    const orient = { FacingCamera: 0, FacingCameraWorldUp: 1, VelocityParallel: 2, VelocityPerpendicular: 3 }[el.orientation || "FacingCamera"];
    const grid = el.flipbook && !b.blockout ? gridOf(b, el.texture) : [1, 1];
    const le = el.lightEmission || 0;
    this.mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: texture(b, el.texture) }, orientation: { value: orient }, grid: { value: new THREE.Vector2(grid[0], grid[1]) }, cells: { value: grid[0] * grid[1] },
        zOff: { value: el.zOffset || 0 }, lightEmission: { value: le }, brightness: { value: (1 + (CAL.sprite - 1) * Math.min(Math.max(le, 0), 1)) * (el.brightness == null ? 1 : el.brightness) }, dimming: { value: 1 - 0.6 * (el.lightInfluence || 0) } },
      vertexShader: SPRITE_VS, fragmentShader: SPRITE_FS, transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendEquation: THREE.AddEquation,
    });
    this.mesh = new THREE.Mesh(geo, this.mat); this.mesh.frustumCulled = false; this.mesh.renderOrder = 10 + (el.zOffset || 0);
    player.scene.add(this.mesh);
    this.live = []; this.emitted = false; this.acc = 0; this.grid = grid; this.lastT = 0;
    this.twin = el.twin ? Object.assign({}, el, el.twin, { name: el.name + "_twin", twin: null, count: el.twin.count != null ? el.twin.count : el.count, rate: el.twin.rate != null ? el.twin.rate : el.rate }) : null;
    if (this.twin) this.twinLayer = new SpriteLayer(player, Object.assign(this.twin, { zOffset: (el.zOffset || 0) + (el.twin.zOffset || 0) }));
  }
  spawn(n, t) {
    const el = this.el, p = this.p, b = p.bundle;
    const frame = p.frameAt(el.point, el.aim, el.rotate);
    for (let i = 0; i < n && this.live.length < this.max; i++) {
      const r = this.rng;
      let local = new THREE.Vector3(0, 0, 0);
      let dir;
      const dirMap = { Top: [0, 1, 0], Bottom: [0, -1, 0], Left: [-1, 0, 0], Right: [1, 0, 0], Front: [0, 0, -1], Back: [0, 0, 1] };
      const nrm = v3(dirMap[el.direction || "Top"]);
      if (el.shape) {
        const sz = v3(el.shape.size || [10, 10, 10]).multiplyScalar(p.scale);
        const type = el.shape.type || "Sphere";
        const surface = el.shape.style === "Surface";
        if (type === "Box") {
          local.set((r() - 0.5) * sz.x, (r() - 0.5) * sz.y, (r() - 0.5) * sz.z);
          if (surface) { const ax = Math.floor(r() * 3); const s = r() < 0.5 ? -0.5 : 0.5; if (ax === 0) local.x = s * sz.x; else if (ax === 1) local.y = s * sz.y; else local.z = s * sz.z; }
          dir = nrm.clone();
        } else if (type === "Cylinder" || type === "Disc") {
          const a = r() * Math.PI * 2, rad = surface ? 0.5 : Math.sqrt(r()) * 0.5;
          local.set(Math.cos(a) * rad * sz.x, type === "Disc" ? 0 : (r() - 0.5) * sz.y, Math.sin(a) * rad * sz.z);
          dir = new THREE.Vector3(Math.cos(a), 0, Math.sin(a));
        } else { // Sphere
          const u = r() * 2 - 1, a = r() * Math.PI * 2, rr = surface ? 0.5 : Math.cbrt(r()) * 0.5, q = Math.sqrt(1 - u * u);
          local.set(q * Math.cos(a) * rr * sz.x, u * rr * sz.y, q * Math.sin(a) * rr * sz.z);
          dir = new THREE.Vector3(q * Math.cos(a), u, q * Math.sin(a));
        }
        if ((el.shape.inOut || "Outward") === "Inward") dir.negate();
      } else {
        dir = nrm.clone();
      }
      // spread: a cone around dir
      const spread = el.spread == null ? 0 : (typeof el.spread === "number" ? el.spread : el.spread[0]);
      if (spread > 0) {
        const ang = r() * spread * DEG, yaw = r() * Math.PI * 2;
        const a = Math.abs(dir.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
        const side = new THREE.Vector3().crossVectors(dir, a).normalize(), up2 = new THREE.Vector3().crossVectors(side, dir);
        dir = dir.clone().multiplyScalar(Math.cos(ang)).addScaledVector(side, Math.sin(ang) * Math.cos(yaw)).addScaledVector(up2, Math.sin(ang) * Math.sin(yaw)).normalize();
      }
      const worldPos = local.applyMatrix4(frame);
      const worldDir = dir.transformDirection(frame);
      const speed = rangeRand(el.speed || 0, r) * p.scale;
      const life = rangeRand(el.lifetime || 1, r) * (el.lifeScale || 1);
      this.live.push({ born: t, life, pos: worldPos, vel: worldDir.multiplyScalar(speed), rot: rangeRand(el.rotation || 0, r) * DEG, rotSpeed: rangeRand(el.rotSpeed || 0, r) * DEG,
        seed: r(), locked: el.lockedToPart ? frame.clone() : null, local: el.lockedToPart ? local.clone() : null });
    }
  }
  update(t, dt, frozen) {
    if (this.el.views && !this.litPicked) { this.litPicked = true; const k = pickView(this.el.views, this.p); const tx = k ? texture(this.p.bundle, k) : null; if (tx) this.mat.uniforms.map.value = tx; this.litKey = k; } // impostors: the view the camera is on
    if (this.el.lit && !this.litPicked) { this.litPicked = true; const k = pickLit(this.el.lit, this.p); const tx = k ? texture(this.p.bundle, k) : null; if (tx) this.mat.uniforms.map.value = tx; this.litKey = k; } // lit variants: the one the scene's sun matches
    const el = this.el, p = this.p;
    const at = el.at || 0;
    if (!frozen && t >= at) {
      if (!this.emitted && (el.count || 0) > 0) { this.emitted = true; this.spawn(el.count, t); }
      const on = (el.rate || 0) > 0 && t < at + (el.for || 0);
      if (on && dt > 0) { this.acc += el.rate * dt; const n = Math.floor(this.acc); if (n > 0) { this.acc -= n; this.spawn(n, t); } }
    }
    const ts = (el.timeScale || 1);
    const acc = v3(el.acceleration || [0, 0, 0]).multiplyScalar(p.scale);
    const drag = el.drag || 0;
    const dragK = drag > 0 ? Math.exp(-dt * ts * drag * 0.693) : 1; // Roblox Drag = half-life of speed (s)
    const wind = el.wind && drag > 0 ? v3(p.wind).multiplyScalar(p.scale) : null; // the game uses Workspace.GlobalWind; the player booth.wind
    let n = 0;
    for (let i = this.live.length - 1; i >= 0; i--) {
      const q = this.live[i];
      const age = (t - q.born) * ts;
      if (age >= q.life) { this.live.splice(i, 1); continue; }
      if (dt > 0) {
        q.vel.addScaledVector(acc, dt * ts);
        if (wind) q.vel.sub(wind).multiplyScalar(dragK).add(wind); else q.vel.multiplyScalar(dragK); // wind: drag pulls toward the wind (Roblox WindAffectsDrag)
        q.pos.addScaledVector(q.vel, dt * ts);
        q.rot += q.rotSpeed * dt * ts;
      }
      if (q.locked) { const f = p.frameAt(el.point, el.aim, el.rotate); q.pos.copy(q.local).applyMatrix4(f); }
      const u = age / q.life;
      const size = Math.max(0, numAt(el.size == null ? 1 : el.size, u, 1, ((q.seed * 7919.37) % 1) * 2 - 1)) * p.scale; // the envelope from the particle's own seed (no new random draw)
      const tr = numAt(el.transparency == null ? 0 : el.transparency, u, 0);
      const sq = numAt(el.squash == null ? 0 : el.squash, u, 0);
      const c = colorAt(el.color, u, p.palette);
      const fb = el.flipbook;
      let fa = 0, fbn = 0, mixT = 0;
      if (fb) { // frame a, the next frame b, and how far between them: the game crossfades (FlipbookBlendFrames, the kit's default)
        const cells = this.grid[0] * this.grid[1];
        const fps = typeof fb.fps === "number" ? fb.fps : 24;
        const mode = fb.mode || "OneShot";
        let x = age * fps + (fb.startRandom ? q.seed * cells : 0);
        if (mode === "OneShot") { x = Math.min(cells - 1, u * cells); fa = Math.floor(x); fbn = Math.min(cells - 1, fa + 1); }
        else if (mode === "PingPong") { const m = x % (2 * cells), seq = (i) => (i < cells ? i : 2 * cells - 1 - i); fa = seq(Math.floor(m)); fbn = seq((Math.floor(m) + 1) % (2 * cells)); x = m; }
        else { if (mode === "Random") x = q.seed * 1000 + age * fps; fa = Math.floor(x) % cells; fbn = (fa + 1) % cells; }
        mixT = fb.blend === false ? 0 : x - Math.floor(x);
      }
      this.pos.set([q.pos.x, q.pos.y, q.pos.z], n * 3);
      this.vel.set([q.vel.x, q.vel.y, q.vel.z], n * 3);
      this.misc.set([size, q.rot, sq, 1 - tr], n * 4);
      this.col.set([c.r, c.g, c.b, 1], n * 4);
      this.frame.set([fa, fbn, mixT], n * 3);
      n++;
    }
    this.mesh.count = n;
    const g = this.mesh.geometry;
    g.instanceCount = n; // an InstancedBufferGeometry draws instanceCount (default: ALL): without this a dead layer kept drawing its last particles as ghosts
    this.mesh.visible = n > 0;
    for (const k of ["iPos", "iVel", "iMisc", "iColor", "iFrame"]) g.attributes[k].needsUpdate = true;
    this.alive = n;
    if (this.twinLayer) this.twinLayer.update(t, dt, frozen);
    return n + (this.twinLayer ? this.twinLayer.alive : 0);
  }
  dispose() { this.p.scene.remove(this.mesh); this.mesh.geometry.dispose(); this.mat.dispose(); if (this.twinLayer) this.twinLayer.dispose(); }
}
function maxLife(v) { return v == null ? 1 : (typeof v === "number" ? v : v[1]); }
// which cell of a sheet a mesh layer shows now (VfxStage's sheetFrame, the same rule: kit/selftest/vfx/dissolve/run.py runs
// both texts on one sweep). OneShot: the cells over the layer's life u, or over "over": [u0, u1] of it; else at fps
function sheetFrame(fb, u, age, frames, start) {
  if (fb.mode === "OneShot") {
    let uu = u;
    if (Array.isArray(fb.over)) {
      const u0 = typeof fb.over[0] === "number" ? fb.over[0] : 0, u1 = typeof fb.over[1] === "number" ? fb.over[1] : 1;
      uu = Math.min(1, Math.max(0, (u - u0) / Math.max(u1 - u0, 1e-4)));
    }
    return Math.min(Math.floor(uu * frames), frames - 1);
  }
  return (Math.floor(age * (fb.fps || 24)) + start) % frames;
}
// (end of sheetFrame)

// A LENS FLARE's pictures for a light at (lx, ly) of the screen (0,0 top left): a glow on the light, a level streak
// through it, ghosts on the line from the light through the middle (VfxStage.luau `flareMarks`: the same rule;
// kit/vfx/flare.py `marks`; kit/selftest/vfx/flare/run.py parity runs all three). Sizes: shares of the screen's HEIGHT
const FLARE_K = [0.35, 0.62, 0.9, 1.25, 1.6, 1.85, 2.1, 2.4];
const FLARE_S = [0.22, 0.4, 0.16, 0.6, 0.3, 0.9, 0.25, 0.5];
const FLARE_A = [0.5, 0.35, 0.6, 0.25, 0.4, 0.18, 0.45, 0.2];
function flareMarks(lx, ly, aspect, f) {
  const size = typeof f.size === "number" ? f.size : 0.18;
  const n = Math.max(0, Math.min(8, Math.floor(typeof f.ghosts === "number" ? f.ghosts : 5)));
  const streak = typeof f.streak === "number" ? f.streak : 0;
  const squeeze = Math.max(1, Math.min(3, typeof f.squeeze === "number" ? f.squeeze : 1));
  const d = Math.max(Math.abs(lx - 0.5), Math.abs(ly - 0.5)) * 2;
  const vis = d <= 1 ? 1 : d >= 1.3 ? 0 : 1 - (d - 1) / 0.3;
  const out = [];
  if (vis <= 0) return out;
  out.push({ kind: 1, i: 0, x: lx, y: ly, w: size, h: size, a: vis, c: 0 });
  if (streak > 0) out.push({ kind: 2, i: 0, x: lx, y: ly, w: streak * aspect, h: size * 0.35, a: vis * 0.9, c: 0 });
  for (let i = 1; i <= n; i++) {
    const s = size * FLARE_S[i - 1];
    out.push({ kind: 3, i, x: lx + (0.5 - lx) * FLARE_K[i - 1], y: ly + (0.5 - ly) * FLARE_K[i - 1], w: s * squeeze, h: s, a: vis * FLARE_A[i - 1], c: i / n });
  }
  return out;
}
// (end of flareMarks)

// A PIECE THAT COMES TO REST: one step of a fracture piece's flight when its debris layer says "rest" (VfxStage.luau
// `debrisStep`: the same arithmetic; kit/vfx/settle.py `step` is the rule; kit/selftest/vfx/settle/run.py parity runs
// all three). s = [x, y, z, vx, vy, vz, tilt, yaw, tilt speed, yaw speed, at rest 0 / 1]
function debrisStep(s, dt, g, floor, hy, hw) {
  let [x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest] = s;
  if (rest === 1) return s;
  vy = vy - g * dt;
  x = x + vx * dt;
  y = y + vy * dt;
  z = z + vz * dt;
  tilt = tilt + wt * dt;
  yaw = yaw + wy * dt;
  const h = Math.abs(Math.cos(tilt)) * hy + Math.abs(Math.sin(tilt)) * hw;
  if (y <= floor + h) {
    y = floor + h;
    if (vy < 0) {
      if (-vy > g * dt * 2) { vy = -vy * 0.3; vx = vx * 0.6; vz = vz * 0.6; wt = wt * 0.5; wy = wy * 0.6; }
      else vy = 0;
    }
    if (vy === 0) {
      const k = Math.max(0, 1 - 6 * dt);
      vx = vx * k; vz = vz * k; wy = wy * k; wt = 0;
      const target = Math.floor(tilt / Math.PI + 0.5) * Math.PI;
      tilt = tilt + (target - tilt) * Math.min(1, 10 * dt);
      y = floor + Math.abs(Math.cos(tilt)) * hy + Math.abs(Math.sin(tilt)) * hw;
      if (Math.sqrt(vx * vx + vz * vz) < g * 0.004 && Math.abs(target - tilt) < 0.01) { rest = 1; tilt = target; vx = 0; vz = 0; wy = 0; y = floor + hy; }
    }
  }
  return [x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest];
}
// (end of debrisStep)

// PIECES THAT MEET (VfxStage.luau `debrisMeet`: the same arithmetic; kit/vfx/settle.py `meet` is the rule): all the
// pieces of a "rest" debris layer that have left the slab, one step - what each lies ON, pieces on the ground that
// lie IN each other pushed apart, then every piece's own debrisStep. -> [the new states, the floor under each]
// turn: the yaw of the frame the slab is played in (the mirror of a piece on its other face is about its OWN z: mirrored first, turned after); unit: the play's scale
const DEBRIS_SKIN = 0.02, DEBRIS_PART = 8, DEBRIS_NUDGE = 0.001, DEBRIS_HITCH = 1 / 30;
function debrisLying(s, shape, turn) {
  const flip = Math.floor(s[6] / Math.PI + 0.5) % 2 !== 0, c = Math.cos(s[7] + turn), n = Math.sin(s[7] + turn), out = new Array(shape.length);
  for (let k = 0; k < shape.length; k += 2) {
    const px = shape[k]; let pz = shape[k + 1];
    if (flip) pz = -pz;
    out[k] = s[0] + px * c + pz * n; out[k + 1] = s[2] - px * n + pz * c;
  }
  return out;
}
function debrisWithin(poly, x, z) {
  let pos = false, neg = false; const n = poly.length;
  for (let k = 0; k < n; k += 2) {
    const ax = poly[k], az = poly[k + 1], bx = poly[(k + 2) % n], bz = poly[(k + 3) % n];
    const cr = (bx - ax) * (z - az) - (bz - az) * (x - ax);
    if (cr > 0) pos = true; else if (cr < 0) neg = true;
  }
  return !(pos && neg);
}
function debrisApart(a, b) {
  let best = Infinity, bx = 0, bz = 0;
  for (const poly of [a, b]) {
    const n = poly.length;
    for (let k = 0; k < n; k += 2) {
      const ex = poly[(k + 2) % n] - poly[k], ez = poly[(k + 3) % n] - poly[k + 1], ln = Math.sqrt(ex * ex + ez * ez);
      if (ln < 1e-9) continue;
      const nx = ez / ln, nz = -ex / ln;
      let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
      for (let q = 0; q < a.length; q += 2) { const d = a[q] * nx + a[q + 1] * nz; a0 = Math.min(a0, d); a1 = Math.max(a1, d); }
      for (let q = 0; q < b.length; q += 2) { const d = b[q] * nx + b[q + 1] * nz; b0 = Math.min(b0, d); b1 = Math.max(b1, d); }
      const o = Math.min(a1, b1) - Math.max(a0, b0);
      if (o <= 0) return [0, 0, 0];
      if (o < best - 1e-9) { best = o; if (a0 + a1 < b0 + b1) { bx = -nx; bz = -nz; } else { bx = nx; bz = nz; } }
    }
  }
  return best === Infinity ? [0, 0, 0] : [best, bx, bz];
}
function debrisMeet(states, shapes, H, W, A, dt, g, base, turn, unit) {
  const n = states.length, S = states.map((s) => s.slice()), mvx = S.map(() => 0), mvz = S.map(() => 0), skin = DEBRIS_SKIN * unit, pushMost = DEBRIS_PART * unit * Math.min(dt, DEBRIS_HITCH);
  let overlapped = false;
  const lies = S.map((s) => Math.abs(s[6] - Math.floor(s[6] / Math.PI + 0.5) * Math.PI) < 0.01);
  const half = S.map((s, i) => Math.abs(Math.cos(s[6])) * H[i] + Math.abs(Math.sin(s[6])) * W[i]), poly = S.map((s, i) => debrisLying(s, shapes[i], turn));
  const reach = shapes.map((sh) => { let r = 0; for (let k = 0; k < sh.length; k += 2) r = Math.max(r, sh[k] * sh[k] + sh[k + 1] * sh[k + 1]); return Math.sqrt(r); });
  const order = S.map((_, i) => i), floor = S.map(() => base), down = S.map(() => false), pushed = S.map(() => false);
  for (let a = 1; a < n; a++) { // from the lowest up: what a piece lies on is always lower than it
    const k = order[a]; let b = a - 1;
    while (b >= 0 && S[order[b]][1] > S[k][1]) { order[b + 1] = order[b]; b--; }
    order[b + 1] = k;
  }
  for (let a = 0; a < n; a++) {
    const i = order[a], bottom = S[i][1] - half[i], fell = Math.max(0, -S[i][4] * dt); // (a falling piece is caught by a top it passed in this step)
    for (let b = 0; b < a; b++) {
      const j = order[b], top = S[j][1] + half[j];
      if (down[j] && lies[j] && top > floor[i] && top <= bottom + fell + 1e-6 && debrisWithin(poly[j], S[i][0], S[i][2])) floor[i] = top;
    }
    down[i] = S[i][4] === 0 && bottom <= floor[i] + 1e-6;
    if (S[i][10] === 1 && Math.abs(bottom - floor[i]) > 1e-6) S[i][10] = 0; // what it lay on has gone (or come): not at rest
  }
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    if (!(down[i] && down[j])) continue;
    if (Math.min(S[i][1] + half[i], S[j][1] + half[j]) - Math.max(S[i][1] - half[i], S[j][1] - half[j]) <= 1e-4) continue; // one lies ON the other, or over it
    const dx = S[i][0] - S[j][0], dz = S[i][2] - S[j][2];
    if (dx * dx + dz * dz >= (reach[i] + reach[j]) * (reach[i] + reach[j])) continue;
    const [deep, nx, nz] = debrisApart(poly[i], poly[j]);
    if (deep <= skin + 1e-9) continue;
    overlapped = true; // (the early stop is not taken while any two lie in each other: VfxStage the same)
    const m = Math.min(deep - skin / 2, pushMost), // (parted to HALF the skin: not at the edge of being pushed again)
      wi = A[j] / (A[i] + A[j]), mi = m * wi, mj = m * (1 - wi);
    mvx[i] += nx * mi; mvz[i] += nz * mi; mvx[j] -= nx * mj; mvz[j] -= nz * mj; // (all a step's pushes are worked out from where the pieces lay at its start, and added)
  }
  for (let i = 0; i < n; i++) { // pushes that cancel (a piece jammed between others) move nothing: it can be at rest
    const d = Math.sqrt(mvx[i] * mvx[i] + mvz[i] * mvz[i]);
    if (d > DEBRIS_NUDGE * unit) { const k = Math.min(1, pushMost / d); S[i][0] += mvx[i] * k; S[i][2] += mvz[i] * k; pushed[i] = true; S[i][10] = 0; }
  }
  return [S.map((s, i) => { const o = debrisStep(s, dt, g, floor[i], H[i], W[i]); if (pushed[i]) o[10] = 0; return o; }), floor, overlapped]; // (a piece being pushed is not at rest)
}
// (end of debrisMeet)

// A PIECE AS IT SITS IN THE SLAB (VfxStage.luau `debrisStart`: the same arithmetic; kit/vfx/settle.py `start` is the
// rule) -> [its eleven numbers in the layer's own frame, half its height, half its width]
function debrisStart(pc, thick, scale, push) {
  const xs = pc.points.map((q) => q[0]), zs = pc.points.map((q) => q[1]);
  const ox = (Math.min(...xs) + Math.max(...xs)) / 2, oz = (Math.min(...zs) + Math.max(...zs)) / 2, k = scale * push;
  const shape = []; for (const q of pc.points) shape.push((q[0] - ox) * scale, (q[1] - oz) * scale); // its flat outline in its OWN axes
  return [[(pc.centre[0] + ox) * scale, thick * scale / 2, (pc.centre[1] + oz) * scale, pc.vel[0] * k, pc.vel[1] * k, pc.vel[2] * k, 0, 0, pc.spin[0] * push, pc.spin[1] * push, 0], // (the layer's speed scales the spin too)
    thick * scale / 2, Math.max(Math.max(...zs) - Math.min(...zs), 0.05) * scale / 2, shape];
}
// (end of debrisStart)

// the frame's YAW, the turn about the up axis a slab's pieces are met by (VfxStage.luau `frameYaw`: Roblox's
// CFrame:ToOrientation; the settle parity runs both on the same turns)
function frameYaw(q) { return new THREE.Euler().setFromQuaternion(q, "YXZ").y; }
// (end of frameYaw)

// AN AUTHORED VECTOR FIELD's velocity at a place (studs from the swarm layer's point, world axes): the sum of its
// elements - wind, vortex, point, path (VfxStage.luau `fieldAt`: the same arithmetic; kit/vfx/field.py `at` is the
// rule; kit/selftest/vfx/field/run.py parity runs all three)
function fieldAt(elements, x, y, z) {
  let vx = 0, vy = 0, vz = 0;
  for (const e of elements) {
    const kind = e.kind;
    if (kind === "wind") {
      const d = e.dir, n = Math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
      if (n > 1e-9) { const s = e.speed / n; vx = vx + d[0] * s; vy = vy + d[1] * s; vz = vz + d[2] * s; }
    } else if (kind === "vortex") {
      const a = e.at, ax = Array.isArray(e.axis) && e.axis.length === 3 ? e.axis : [0, 1, 0], n = Math.sqrt(ax[0] * ax[0] + ax[1] * ax[1] + ax[2] * ax[2]), rad = e.radius;
      if (n > 1e-9 && rad > 1e-9) {
        const nx = ax[0] / n, ny = ax[1] / n, nz = ax[2] / n, rx = x - a[0], ry = y - a[1], rz = z - a[2];
        const h = rx * nx + ry * ny + rz * nz, px = rx - h * nx, py = ry - h * ny, pz = rz - h * nz;
        const d = Math.sqrt(px * px + py * py + pz * pz);
        const lift = (e.lift || 0) * Math.exp(-((d / (2 * rad)) * (d / (2 * rad))));
        vx = vx + nx * lift; vy = vy + ny * lift; vz = vz + nz * lift;
        if (d > 1e-9) {
          const f = (d / rad) * Math.exp(1 - d / rad), ux = px / d, uy = py / d, uz = pz / d, turn = e.speed * f, pull = (e.pull || 0) * f;
          vx = vx + (ny * uz - nz * uy) * turn - ux * pull;
          vy = vy + (nz * ux - nx * uz) * turn - uy * pull;
          vz = vz + (nx * uy - ny * ux) * turn - uz * pull;
        }
      }
    } else if (kind === "point") {
      const a = e.at, rx = x - a[0], ry = y - a[1], rz = z - a[2], d = Math.sqrt(rx * rx + ry * ry + rz * rz), rad = e.radius;
      if (d > 1e-9 && rad > 1e-9) { const core = d / (0.25 * rad), s = e.speed * Math.exp(-((d / rad) * (d / rad))) * (1 - Math.exp(-(core * core))) / d; vx = vx + rx * s; vy = vy + ry * s; vz = vz + rz * s; }
    } else if (kind === "path") {
      const pts = e.points; let best = -1, cx = 0, cy = 0, cz = 0, tx = 0, ty = 0, tz = 0;
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i], p1 = pts[i + 1], sx = p1[0] - p0[0], sy = p1[1] - p0[1], sz = p1[2] - p0[2], ln = Math.sqrt(sx * sx + sy * sy + sz * sz);
        if (ln > 1e-9) {
          let u = ((x - p0[0]) * sx + (y - p0[1]) * sy + (z - p0[2]) * sz) / (ln * ln); u = Math.max(0, Math.min(1, u));
          const qx = p0[0] + sx * u, qy = p0[1] + sy * u, qz = p0[2] + sz * u, dd = (x - qx) * (x - qx) + (y - qy) * (y - qy) + (z - qz) * (z - qz);
          if (best < 0 || dd < best) { best = dd; cx = qx; cy = qy; cz = qz; tx = sx / ln; ty = sy / ln; tz = sz / ln; }
        }
      }
      const rad = e.radius;
      if (best >= 0 && rad > 1e-9) {
        const w = Math.exp(-(best / (rad * rad))), along = e.speed * w, pull = (e.pull || 0) / rad * w;
        vx = vx + tx * along + (cx - x) * pull; vy = vy + ty * along + (cy - y) * pull; vz = vz + tz * along + (cz - z) * pull;
      }
    }
  }
  return [vx, vy, vz];
}
// (end of fieldAt)

// A POINT CLOUD (a swarm layer's "cloud"): the new speed, along one axis, of a particle `d` from its point moving at
// `v`, pulled at `w` over a step `dt` (VfxStage.luau `cloudPull`: the same arithmetic; kit/vfx/points.py `pull` is the rule)
function cloudPull(d, v, w, dt) {
  return (v - w * w * d * dt) / (1 + 2 * w * dt + w * w * dt * dt);
}
// (end of cloudPull)

// FORCED PERSPECTIVE: the size multiplier of a mesh layer `dist` studs from the camera - (dist / ref) ^ keep, held
// between min and max (VfxStage.luau `forcedScale`: the same arithmetic; kit/vfx/forced.py `scale` is the rule)
function forcedScale(dist, f) {
  const ref = f.ref, keep = typeof f.keep === "number" ? f.keep : 1, lo = typeof f.min === "number" ? f.min : 0.25, hi = typeof f.max === "number" ? f.max : 4;
  if (typeof ref !== "number" || !(ref > 1e-6)) return 1;
  const s = Math.pow(Math.max(dist, 1e-3) / ref, keep);
  return Math.max(lo, Math.min(hi, s));
}
// (end of forcedScale)
function hashName(s) { let h = 7; for (const ch of String(s || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; }

// ---------------------------------------------------------------- beams: a ribbon strip; texture V runs along the beam
class BeamLayer {
  constructor(player, el) {
    this.p = player; this.el = el; this.rng = mulberry(player.seed + hashName(el.name));
    const copies = Math.max(1, el.copies || 1), plane = el.plane || "camera";
    this.plane = plane; this.copies = copies;
    this.strips = [];
    const tex = texture(player.bundle, el.texture);
    for (let c = 0; c < copies; c++) {
      const jitter = (el.jitter || 0) * player.scale;
      const off = new THREE.Vector3(this.rng() * 2 - 1, this.rng() * 2 - 1, this.rng() * 2 - 1).multiplyScalar(jitter);
      const speed = rangeRand(el.textureSpeed == null ? 1 : el.textureSpeed, this.rng);
      const faces = plane === "camera" ? [0] : [1, -1];
      for (const face of faces) {
        // soft ends fade the vertex rows near each end: a 1-segment strip has ONLY end rows, so it drew nothing at all
        // (Roblox fades along the length with a sequence, whatever the segments: a straight beam gets >= 8 rows here)
        // (only a STRAIGHT beam: a curved one keeps its segments - Roblox's Beam.Segments draws that polyline in game)
        const straight = !el.curve || (el.curve[0] === 0 && el.curve[1] === 0);
        const segs = Math.max(el.segments || 10, el.softEnds === 0 || !straight ? 1 : 8);
        const geo = new THREE.BufferGeometry();
        const n = (segs + 1) * 2;
        geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
        geo.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(n * 2), 2));
        const idx = [];
        for (let i = 0; i < segs; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
        geo.setIndex(idx);
        const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide,
          blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, color: 0xffffff });
        mat.onBeforeCompile = (sh) => { // premultiplied output + per-vertex alpha along the length + brightness
          sh.uniforms.uBright = this.uBright = this.uBright || { value: 1 };
          sh.uniforms.uLE = { value: el.lightEmission == null ? 1 : el.lightEmission };
          sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nattribute float aAlpha; varying float vAlpha;").replace("#include <uv_vertex>", "#include <uv_vertex>\nvAlpha = aAlpha;");
          sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uBright; uniform float uLE; varying float vAlpha;")
            .replace("#include <dithering_fragment>", "#include <dithering_fragment>\n float a = gl_FragColor.a * vAlpha; gl_FragColor = vec4(gl_FragColor.rgb * uBright * a, a * (1.0 - clamp(uLE, 0.0, 1.0)));");
        };
        geo.setAttribute("aAlpha", new THREE.BufferAttribute(new Float32Array(n), 1));
        const mesh = new THREE.Mesh(geo, mat); mesh.frustumCulled = false; mesh.renderOrder = 20 + (el.zOffset || 0) + c * (el.zStep || 0.05);
        mesh.visible = false; player.scene.add(mesh);
        this.strips.push({ mesh, geo, mat, off, face, copy: c, speed, segs, scroll: 0 });
      }
    }
  }
  update(t, dt, frozen) {
    const el = this.el, p = this.p;
    const at = el.at || 0, life = Math.max(el.life || 1, 1e-3);
    const u = (t - at) / life, alive = t >= at && u <= 1;
    for (const s of this.strips) s.mesh.visible = alive;
    if (!alive) return 0;
    const p0 = p.worldPoint(el.from), p1 = p.worldPoint(el.to);
    const grow = el.grow ? ease((t - at) / el.grow, el.growEase) : 1;
    const w = numAt(el.width == null ? 1 : el.width, u, 1) * p.scale;
    const vis = 1 - numAt(el.fade, u, 0);
    const bright = numAt(el.brightness, u, 1);
    const taper = el.taper || [1, 1];
    const col = colorAt(el.color, 0, p.palette);
    let dir = new THREE.Vector3().subVectors(p1, p0); if (dir.length() < 1e-4) dir.set(0, 0, 1); dir.normalize();
    const camDir = new THREE.Vector3();
    for (const s of this.strips) {
      const k = this.copies > 1 ? s.copy / (this.copies - 1) : 0;
      const wk = 1 + (el.widthSpread || 0) * (k - 0.5) * 2;
      const q0 = p0.clone().addScaledVector(s.off, 0.25), q1 = p0.clone().lerp(p1, grow).add(s.off);
      // width direction: camera-facing ribbon, or the wall's vY (up) / flat (sideways)
      let wdir;
      if (this.plane === "camera") { camDir.subVectors(p.camera.position, q0.clone().lerp(q1, 0.5)); wdir = new THREE.Vector3().crossVectors(dir, camDir).normalize(); if (wdir.length() < 1e-4) wdir.set(0, 1, 0); }
      else if (this.plane === "flat") { wdir = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)); if (wdir.length() < 1e-4) wdir.set(1, 0, 0); wdir.normalize(); }
      else { const w0 = Math.abs(dir.y) < 0.95 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0); wdir = w0.clone().addScaledVector(dir, -dir.dot(w0)).normalize(); }
      const pos = s.geo.attributes.position.array, uv = s.geo.attributes.uv.array, al = s.geo.attributes.aAlpha.array;
      const len = q0.distanceTo(q1);
      if (!frozen) s.scroll += s.speed * dt;
      const reps = (el.textureMode || "Wrap") === "Wrap" ? len / ((el.textureLength || 10) * p.scale) : 1;
      const cv = el.curve || [0, 0], cax = el.curveAxis ? new THREE.Vector3(el.curveAxis[0], el.curveAxis[1], el.curveAxis[2]).normalize() : (s.face === 0 ? new THREE.Vector3(1, 0, 0) : dir.clone());
      const b1 = q0.clone().addScaledVector(cax, cv[0] * p.scale), b2 = q1.clone().addScaledVector(cax, -cv[1] * p.scale), curved = cv[0] !== 0 || cv[1] !== 0;
      for (let i = 0; i <= s.segs; i++) {
        const f = i / s.segs;
        const c = curved ? q0.clone().multiplyScalar((1 - f) ** 3).addScaledVector(b1, 3 * (1 - f) ** 2 * f).addScaledVector(b2, 3 * (1 - f) * f * f).addScaledVector(q1, f ** 3) : q0.clone().lerp(q1, f);
        const ww = w * (taper[0] + (taper[1] - taper[0]) * f) * wk;
        const a = c.clone().addScaledVector(wdir, -ww / 2), b = c.clone().addScaledVector(wdir, ww / 2);
        pos.set([a.x, a.y, a.z, b.x, b.y, b.z], i * 6);
        // Roblox: the texture's vertical axis runs along the beam (TextureSpeed scrolls it)
        const v = f * reps - s.scroll;
        uv.set([0, v, 1, v], i * 4);
        const tr = numAt(el.transparency == null ? 0 : el.transparency, f, 0);
        const se = el.softEnds == null ? 0.12 : el.softEnds; // soft ends: no flat cap at either end of a beam
        const endK = se > 0 ? Math.min(1, f / se) * Math.min(1, (1 - f) / se) : 1;
        al[i * 2] = al[i * 2 + 1] = (1 - tr) * vis * endK * endK * (3 - 2 * endK);
      }
      s.geo.attributes.position.needsUpdate = s.geo.attributes.uv.needsUpdate = s.geo.attributes.aAlpha.needsUpdate = true;
      s.mat.color.copy(col);
      if (this.uBright) this.uBright.value = bright * CAL.beam;
    }
    return 0;
  }
  dispose() { for (const s of this.strips) { this.p.scene.remove(s.mesh); s.geo.dispose(); s.mat.dispose(); } }
}

// ---------------------------------------------------------------- meshes (the shapes of VfxMesh.luau)
function gridGeo(cols, rows, at, uvAt) { // uvAt(u, v) -> [s, t] overrides the grid's own (u, v) texture mapping
  const pos = [], uv = [], idx = [];
  for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) { const u = i / cols, v = j / rows; const p = at(u, v); pos.push(p[0], p[1], p[2]); if (uvAt) { const q = uvAt(u, v); uv.push(q[0], q[1]); } else uv.push(u, v); }
  const w = cols + 1;
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) { const a = j * w + i, b = a + 1, c = a + w + 1, d = a + w; idx.push(a, b, c, a, c, d); }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); g.setIndex(idx); g.computeVertexNormals();
  g.userData.grid = { cols, rows };
  const uvg = []; for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) uvg.push(i / cols, j / rows);
  g.userData.uvg = uvg; // each vertex's own (u, v) on its grid: the fades read it (merged strips keep theirs)
  return g;
}
// several grids as ONE mesh (a shape made of separate strips: a crown of spikes). Same as VfxMesh's list of grids.
function mergeGeo(list) {
  const pos = [], uv = [], idx = [], uvg = []; let base = 0;
  for (const g of list) {
    pos.push(...g.attributes.position.array); uv.push(...g.attributes.uv.array); uvg.push(...g.userData.uvg);
    for (const k of g.index.array) idx.push(k + base);
    base += g.attributes.position.count; g.dispose();
  }
  const m = new THREE.BufferGeometry();
  m.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); m.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); m.setIndex(idx); m.computeVertexNormals();
  m.userData.uvg = uvg; return m;
}
// per-vertex alpha from the grid's (u, v): fadeIn / fadeOut ramp the shape in from v = 0 and out to v = 1 (a flame
// shell's feet and tips), fadeSides = sin(pi u)^k (a tongue's edges). Same rule as VfxMesh.alphaAt.
function gridAlpha(p, u, v) {
  const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / Math.max(b - a, 1e-6))); return t * t * (3 - 2 * t); };
  let a = 1;
  if (p.fadeIn) a *= ss(0, p.fadeIn, v);
  if (p.fadeOut) a *= 1 - ss(1 - p.fadeOut, 1, v);
  if (p.fadeSides) a *= Math.pow(Math.max(Math.sin(Math.PI * u), 0), p.fadeSides);
  return a;
}
function fadeGeo(g, p) {
  if (!(p.fadeIn || p.fadeOut || p.fadeSides) || !g.userData.uvg) return;
  const uvg = g.userData.uvg, col = [];
  for (let k = 0; k < uvg.length; k += 2) col.push(1, 1, 1, gridAlpha(p, uvg[k], uvg[k + 1]));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 4));
}
// a crown of sharp blades round an axis (an anime aura's strands): `count` blades on a ring of `radius` (+-`spread`),
// heights h0..h1, leaning OUT by `lean` (x height) and curving, `width` (thin at the root, widest low, a point at the tip); `cross` 1 = each
// blade is two crossed planes (seen from every side). `seed` picks the layout. Same rule as VfxMesh spikes.
function spikeGrids(p, grid) {
  const n = Math.max(1, Math.round(p.count || 24)), R = p.radius == null ? 1.4 : p.radius, sp = p.spread == null ? 0.4 : p.spread;
  const h0 = p.h0 == null ? 3 : p.h0, h1 = p.h1 == null ? 7 : p.h1, lean = p.lean == null ? 0.5 : p.lean, W = p.width == null ? 0.35 : p.width;
  const rings = p.rings || 4, sd = p.seed || 0, cross = p.cross == null ? 1 : p.cross;
  const h = (i) => { const x = Math.sin(i * 12.9898 + sd * 78.233) * 43758.5453; return x - Math.floor(x); };
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = (i + h(4 * i) * 0.8) / n * TAU, r = R + (h(4 * i + 1) - 0.5) * 2 * sp, H = h0 + (h1 - h0) * h(4 * i + 2), w = W * (0.7 + 0.6 * h(4 * i + 3));
    const ox = Math.cos(a), oz = Math.sin(a);
    const planes = cross ? [[-oz, ox], [ox, oz]] : [[-oz, ox]];
    for (const [px, pz] of planes) out.push(grid(1, rings, (u, v) => { const o = r + lean * H * Math.pow(v, 1.5), s = (u - 0.5) * w * Math.pow(1 - v, 0.9) * Math.min(1, v / 0.18 + 0.15); // thin at the root, widest low, a point at the tip
      return [ox * o + px * s, H * v, oz * o + pz * s]; }));
  }
  return out;
}
// a flame shell's radius at height v (0 feet .. 1 tip): `base` at the feet, `tip` at the top, 1 at the belly, lobed
// round its axis (more at the top). Same rule as VfxMesh.flameRadius.
// a mesh's spin angles (degrees) at `age`: spin is [x, y, z] degrees per second, or keys [[u, [x, y, z]], ...] of that
// SPEED over the layer's life - the angle is its integral (exact: the speed is linear between keys), so a whirl can
// spin UP and wind down. VfxStage.spinAngle does the same.
function spinAngle(spin, age, life) {
  if (!spin) return [0, 0, 0];
  if (typeof spin[0] === "number") return [spin[0] * age, spin[1] * age, spin[2] * age];
  const u = age / life, pts = [0], out = [0, 0, 0];
  for (const k of spin) if (k[0] > 0 && k[0] < u) pts.push(k[0]);
  pts.push(u);
  for (let i = 0; i < pts.length - 1; i++) {
    const a = vecAt(spin, pts[i]), b = vecAt(spin, pts[i + 1]), w = (pts[i + 1] - pts[i]) * life / 2;
    out[0] += (a.x + b.x) * w; out[1] += (a.y + b.y) * w; out[2] += (a.z + b.z) * w;
  }
  return out;
}
function flameRadius(p, u, v) {
  const base = p.base == null ? 0.55 : p.base, tip = p.tip == null ? 0.12 : p.tip, lobes = p.lobes || 5, lobe = p.lobe == null ? 0.12 : p.lobe;
  const r = base * (1 - v) + tip * v + (1 - 0.5 * (base + tip)) * Math.pow(Math.sin(Math.PI * v), 0.9);
  return r * (1 + lobe * Math.sin(lobes * u * TAU + (p.seed || 0)) * v);
}
const TAU = Math.PI * 2;
// the slash ARC's geometry: a line-for-line mirror of src/kit/VfxArc.luau (arc v2, 2026-10-23: torn edges `jag`, a bowed
// cross-section `ridge`, `twist`, layered `strands`, and the SWEEP window [tail, head] the slash draws itself over).
// Returns [x, y, z, ua] - ua = where on the full arc the vertex sits (the texture stays pinned there as it sweeps).
function arcRows(p) { return p.ridge ? 6 : 2; }
function arcStrands(p) { return Math.min(5, Math.max(1, Math.floor(p.strands || 1))); }
function arcEdge(ua, f, s) { const t = ua * f * 2 * Math.PI; return 0.5 * Math.sin(t + s) + 0.3 * Math.sin(2.3 * t + 1.7 * s) + 0.2 * Math.sin(4.1 * t + 2.9 * s); }
export function arcPoint(p, u, v, k, tail, head) {
  const r = p.radius == null ? 1 : p.radius, wd = p.width == null ? 0.35 : p.width, span = (p.arc || 160) * DEG;
  const sk = Math.min(0.95, Math.max(0.05, p.skew == null ? 0.5 : p.skew));
  const t0 = tail == null ? 0 : tail, t1 = head == null ? 1 : head, ua = t0 + (t1 - t0) * u, a = (ua - 0.5) * span;
  const w = u < sk ? 0.5 * u / sk : 0.5 + 0.5 * (u - sk) / (1 - sk);
  const taper = Math.pow(Math.max(Math.sin(Math.PI * w), 0), p.taper == null ? 0.7 : p.taper);
  const n = arcStrands(p), off = k - (n - 1) / 2;
  const rk = r + off * (p.strandSpread == null ? 0.6 : p.strandSpread) * wd * 0.5, wk = wd * (1 - 0.35 * Math.abs(off) / n), zk = -Math.abs(off) * wd * 0.15;
  let vv = v - 0.5; const jag = p.jag || 0;
  if (jag) { const s = (p.seed == null ? 1 : p.seed) + k * 3.1, f = p.jagFreq == null ? 9 : p.jagFreq; const e = v >= 0.5 ? 0.6 * arcEdge(ua, f, s) : arcEdge(ua, f * 1.4, s + 5.3); vv *= 1 + 2 * jag * e * Math.abs(2 * v - 1); }
  const across = vv * wk * taper, bulge = (p.ridge || 0) * wk * taper * (1 - Math.pow(2 * v - 1, 2)), th = (p.twist || 0) * DEG * (ua - 0.5);
  const radial = across * Math.cos(th) - bulge * Math.sin(th), normal = across * Math.sin(th) + bulge * Math.cos(th) + zk, rr = rk + radial;
  return p.vertical ? [Math.cos(a) * rr, Math.sin(a) * rr, normal, ua] : [Math.sin(a) * rr, normal, -Math.cos(a) * rr, ua];
}
const SHAPES = {
  // a mesh sequence (kit/vfx/meshseq.py): frame 0's grid; MeshLayer.seqFrame walks the frames (VfxMesh seq, same rule)
  seq: (p) => { const d = p.data; if (!d || !d.frames || !d.frames.length) return gridGeo(1, 1, (u, v) => [(u - 0.5) * 0.01, (v - 0.5) * 0.01, 0]); const f0 = d.frames[0], w = d.cols + 1;
    /* `strips`: that many SEPARATE grids of cols x rows, one after another in every frame (strands of hair); the merged vertices keep the frames' order (VfxMesh seq: the same) */
    const strips = typeof d.strips === "number" && d.strips > 1 ? Math.floor(d.strips) : 1, per = w * (d.rows + 1) * 3, gs = [];
    for (let s = 0; s < strips; s++) gs.push(gridGeo(d.cols, d.rows, (u, v) => { const k = s * per + (Math.round(v * d.rows) * w + Math.round(u * d.cols)) * 3; return [f0[k], f0[k + 1], f0[k + 2]]; }));
    return gs.length === 1 ? gs[0] : mergeGeo(gs); },
  ring: (p) => { const i0 = p.inner == null ? 0.8 : p.inner, o = p.outer == null ? 1 : p.outer; return gridGeo(p.segments || 48, 1, (u, v) => { const r = i0 + (o - i0) * v; return [Math.cos(u * TAU) * r, 0, Math.sin(u * TAU) * r]; },
    p.planar ? (u, v) => { const r = (i0 + (o - i0) * v) / o; return [0.5 + 0.5 * Math.cos(u * TAU) * r, 0.5 + 0.5 * Math.sin(u * TAU) * r]; } : null); },
  disc: (p) => gridGeo(p.segments || 48, p.rings || 4, (u, v) => [Math.cos(u * TAU) * v, 0, Math.sin(u * TAU) * v], p.planar ? (u, v) => [0.5 + 0.5 * Math.cos(u * TAU) * v, 0.5 + 0.5 * Math.sin(u * TAU) * v] : null),
  // ONE PIECE of a broken slab (VfxMesh "piece", the same four rows round the outline; kit/vfx/fracture.py)
  piece: (p) => { const pts = p.points || [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], n = pts.length, h = p.height == null ? 0.5 : p.height;
    const c = p.centre || [0, 0], sl = p.slab || [1, 1];
    const at = (u, v) => { const q = pts[Math.floor(u * n + 0.5) % n], row = Math.floor(v * 3 + 0.5), mid = row === 0 || row === 3; return [mid ? 0 : q[0], row >= 2 ? h / 2 : -h / 2, mid ? 0 : q[1]]; };
    return gridGeo(n, 3, at, (u, v) => { const q = at(u, v); return [0.5 + (c[0] + q[0]) / sl[0], 0.5 + (c[1] + q[2]) / sl[1]]; }); },
  rock: (p) => { const sd = p.seed == null ? 1 : p.seed, cuts = p.cuts || 9, jag = p.jag == null ? 0.38 : p.jag, flat = p.flat == null ? 0.72 : p.flat, spike = p.spike || 0;
    const h = (i) => { const x = Math.sin(i * 12.9898 + sd * 78.233) * 43758.5453; return x - Math.floor(x); };
    const pl = []; for (let k = 0; k < cuts; k++) { let nx = h(3 * k) * 2 - 1, ny = h(3 * k + 1) * 2 - 1, nz = h(3 * k + 2) * 2 - 1; const L = Math.hypot(nx, ny, nz) || 1; pl.push([nx / L, ny / L, nz / L, 1 - jag * h(100 + k)]); }
    return gridGeo(p.segments || 12, p.rings || 8, (u, v) => { const lat = (v - 0.5) * Math.PI; const d = [Math.cos(u * TAU) * Math.cos(lat), Math.sin(lat), Math.sin(u * TAU) * Math.cos(lat)];
      let r = 1; for (const q of pl) { const dn = d[0] * q[0] + d[1] * q[1] + d[2] * q[2]; if (dn > 1e-3) r = Math.min(r, q[3] / dn); }
      const tp = 1 - spike * Math.max(0, d[1] * r); return [d[0] * r * tp, d[1] * r * flat, d[2] * r * tp]; }); }, // spike: the top narrows to a point (a crystal, a shard)
  // a liquid CROWN (Edgerton's coronet): a thin wall flaring base -> radius, its rim rolled into a lip, scalloped (VfxMesh.crown)
  crown: (p) => { const R = p.radius == null ? 1.75 : p.radius, b = p.base == null ? 1 : p.base, h = p.height == null ? 1.6 : p.height, lip = p.lip == null ? 0.18 : p.lip, n = p.scallops == null ? 18 : p.scallops, sc = p.scallop == null ? 0.12 : p.scallop;
    return gridGeo(p.segments || 64, p.rings || 20, (u, v) => { let r, y;
      if (v < 0.8) { const t = v / 0.8; r = b + (R - b) * Math.pow(t, 1.6); y = h * t; } else { const th = (v - 0.8) / 0.2 * 1.25 * Math.PI; r = R + lip - lip * Math.cos(th); y = h + lip * Math.sin(th); }
      r *= 1 + sc * Math.sin(n * u * TAU) * Math.max(0, (v - 0.6) / 0.4); return [Math.cos(u * TAU) * r, y, Math.sin(u * TAU) * r]; }); },
  tube: (p) => { const r0 = p.radiusBottom == null ? 1 : p.radiusBottom, r1 = p.radiusTop == null ? 1 : p.radiusTop, h = p.height == null ? 1 : p.height; return gridGeo(p.segments || 32, p.rings || 8, (u, v) => { const r = r0 + (r1 - r0) * v; return [Math.cos(u * TAU) * r, v * h, Math.sin(u * TAU) * r]; }); },
  cone: (p) => { const r0 = p.radius == null ? 1 : p.radius, h = p.height == null ? 1 : p.height; return gridGeo(p.segments || 32, p.rings || 8, (u, v) => { const r = r0 * (1 - v); return [Math.cos(u * TAU) * r, v * h, Math.sin(u * TAU) * r]; }); },
  // a torus in XZ: u around the ring, v around the tube (VfxMesh torus, same rule) - a uvScroll along v rolls it
  torus: (p) => { const R = p.radius == null ? 1 : p.radius, r = p.tube == null ? 0.3 : p.tube; return gridGeo(p.segments || 48, p.rings || 16, (u, v) => { const c = R + r * Math.cos(v * TAU); return [Math.cos(u * TAU) * c, r * Math.sin(v * TAU), Math.sin(u * TAU) * c]; }); },
  sphere: (p) => gridGeo(p.segments || 32, p.rings || 16, (u, v) => { const lat = (v - 0.5) * Math.PI; return [Math.cos(u * TAU) * Math.cos(lat), Math.sin(lat), Math.sin(u * TAU) * Math.cos(lat)]; }),
  dome: (p) => { const h = p.height == null ? 1 : p.height; return gridGeo(p.segments || 32, p.rings || 10, (u, v) => { const lat = v * Math.PI / 2; return [Math.cos(u * TAU) * Math.cos(lat), Math.sin(lat) * h, Math.sin(u * TAU) * Math.cos(lat)]; }); },
  spiral: (p) => { const r = p.radius == null ? 1 : p.radius, h = p.height == null ? 2 : p.height, turns = p.turns || 2, wd = p.width == null ? 0.3 : p.width; return gridGeo(p.segments || 96, 1, (u, v) => { const a = u * turns * TAU; const rr = r * (p.flare ? 1 + (p.flare - 1) * u : 1); return [Math.cos(a) * rr, u * h + (v - 0.5) * wd, Math.sin(a) * rr]; }); },
  arc: (p) => { // the slash crescent (arc v2: VfxArc's maths); vertical 1 = standing in XY, bulging +X (a wave flying along +X)
    const cols = p.segments || 48, rows = arcRows(p), n = arcStrands(p), gs = [];
    for (let k = 0; k < n; k++) gs.push(gridGeo(cols, rows, (u, v) => arcPoint(p, u, v, k, 0, 1).slice(0, 3)));
    const g = n === 1 ? gs[0] : mergeGeo(gs); g.userData.grid = { cols, rows, strands: n }; return g; },
  // a flame shell round a body: a lathe from the feet (y 0) to the tip (y height), lobed; u around x `tiles`, v up x `vtiles`
  flame: (p) => { const R = p.radius == null ? 1 : p.radius, h = p.height == null ? 2 : p.height, tu = p.tiles || 2, tv = p.vtiles || 1;
    const tw = (p.twist || 0) * DEG; // twist: degrees the shell turns from feet to tip (a fire whirl's helix)
    return gridGeo(p.segments || 40, p.rings || 16, (u, v) => { const r = R * flameRadius(p, u, v), a = u * TAU + tw * v; return [Math.cos(a) * r, v * h, Math.sin(a) * r]; }, (u, v) => [u * tu, v * tv]); },
  // one flame tongue: a curved vertical ribbon on a cylinder of `radius`, `arc` degrees wide at the bottom, narrowing
  // by `taper` and leaning out by `lean` studs at the top; u across, v up
  tongue: (p) => { const R = p.radius == null ? 1 : p.radius, h = p.height == null ? 2 : p.height, span = (p.arc == null ? 40 : p.arc) * DEG, taper = p.taper == null ? 0.7 : p.taper, lean = p.lean || 0;
    return gridGeo(p.segments || 8, p.rings || 12, (u, v) => { const a = (u - 0.5) * span * (1 - taper * v); const r = R + lean * v * v; return [Math.sin(a) * r, v * h, -Math.cos(a) * r]; }); },
  // lightning: a thin jagged tube along +Y from 0 to `length`, `kinks` random bends `amp` studs off the line (3D, so it
  // reads as a zig-zag from every side), thinner at both ends; `seed` picks the bends. Same rule as VfxMesh boltAt.
  bolt: (p) => { const K = Math.max(2, Math.round(p.kinks || 8)), L = p.length == null ? 4 : p.length, A = p.amp == null ? 0.35 : p.amp, W = p.width == null ? 0.06 : p.width, sd = p.seed || 0;
    const h = (i) => { const x = Math.sin(i * 12.9898 + sd * 78.233) * 43758.5453; return x - Math.floor(x); };
    const pts = []; for (let j = 0; j <= K; j++) { const end = j === 0 || j === K; pts.push([end ? 0 : (h(2 * j) - 0.5) * 2 * A, j / K * L, end ? 0 : (h(2 * j + 1) - 0.5) * 2 * A]); }
    return gridGeo(p.segments || 5, K * 2, (u, v) => { const sv = Math.min(v * K, K - 1e-6), j = Math.floor(sv), f = sv - j, a = pts[j], c = pts[j + 1];
      const r = W * (0.35 + 0.65 * Math.pow(Math.sin(Math.PI * v), 0.5));
      return [a[0] + (c[0] - a[0]) * f + Math.cos(u * TAU) * r, a[1] + (c[1] - a[1]) * f, a[2] + (c[2] - a[2]) * f + Math.sin(u * TAU) * r]; }); },
  spikes: (p) => mergeGeo(spikeGrids(p, (c, r, at) => gridGeo(c, r, at))),
  // a CORONA: `count` sharp crossed blades pointing OUT of a sphere of `radius` in every direction (spread evenly on a
  // golden spiral), lengths l0..l1, base `width`; a sun's corona, an energy ball's spiky rim, a starburst. Same rule as VfxMesh.
  corona: (p) => { const n = Math.max(1, Math.round(p.count || 60)), R = p.radius == null ? 1 : p.radius, l0 = p.l0 == null ? 0.3 : p.l0, l1 = p.l1 == null ? 0.8 : p.l1;
    const W = p.width == null ? 0.15 : p.width, sd = p.seed || 0, rings = p.rings || 3, list = [];
    const h = (i) => { const x = Math.sin(i * 12.9898 + sd * 78.233) * 43758.5453; return x - Math.floor(x); };
    for (let i = 0; i < n; i++) {
      const y = 1 - 2 * (i + 0.5) / n, r = Math.sqrt(Math.max(0, 1 - y * y)), ph = i * 2.399963 + sd;
      const d = [Math.cos(ph) * r, y, Math.sin(ph) * r];
      let a = [d[2], 0, -d[0]]; let la = Math.hypot(a[0], a[1], a[2]); if (la < 1e-4) { a = [1, 0, 0]; la = 1; } a = a.map((x) => x / la);
      const b2 = [d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0]];
      const L = l0 + (l1 - l0) * h(4 * i + 2), w = W * (0.7 + 0.6 * h(4 * i + 3));
      for (const q of [a, b2]) list.push(gridGeo(1, rings, (u, v) => { const o = R + L * v, sw = (u - 0.5) * w * Math.pow(1 - v, 0.9);
        return [d[0] * o + q[0] * sw, d[1] * o + q[1] * sw, d[2] * o + q[2] * sw]; }));
    }
    return mergeGeo(list); },
  // crossed vertical cards through the axis (a flipbook drawing given depth): `count` planes, width x height, centred,
  // each carrying the whole image upright. Same rule as VfxMesh cards.
  cards: (p) => { const n = Math.max(1, Math.round(p.count || 3)), W = p.width == null ? 1 : p.width, H = p.height == null ? 1 : p.height, list = [];
    for (let i = 0; i < n; i++) { const a = Math.PI * i / n, cx = Math.cos(a), cz = Math.sin(a); list.push(gridGeo(1, 1, (u, v) => [cx * (u - 0.5) * W, (v - 0.5) * H, cz * (u - 0.5) * W])); }
    return mergeGeo(list); },
  Ball: () => new THREE.SphereGeometry(0.5, 24, 12), Block: () => new THREE.BoxGeometry(1, 1, 1), Cylinder: () => new THREE.CylinderGeometry(0.5, 0.5, 1, 24),
};
let TOON_RAMP = null; // three flat tone bands for cel-shaded solids
function toonRamp() { if (!TOON_RAMP) { const d = new Uint8Array([70, 70, 70, 255, 160, 160, 160, 255, 255, 255, 255, 255]); TOON_RAMP = new THREE.DataTexture(d, 3, 1, THREE.RGBAFormat); TOON_RAMP.minFilter = TOON_RAMP.magFilter = THREE.NearestFilter; TOON_RAMP.needsUpdate = true; } return TOON_RAMP; }
class MeshLayer {
  constructor(player, el) {
    this.p = player; this.el = el;
    const shape = el.shape || "ring";
    const params = shape === "seq" ? Object.assign({}, el.params, { data: (player.bundle.seq || {})[(el.params || {}).seq] }) : (el.params || {});
    const geo = (SHAPES[shape] || SHAPES.ring)(params);
    fadeGeo(geo, params);
    if (shape === "seq" && params.data && params.data.frames.length > 1) this.seq = params;
    geo.computeBoundingBox(); const bb = geo.boundingBox; this.native = new THREE.Vector3().subVectors(bb.max, bb.min); this.center = new THREE.Vector3().addVectors(bb.max, bb.min).multiplyScalar(0.5);
    if (SHAPES[shape] === SHAPES.Ball || SHAPES[shape] === SHAPES.Block || SHAPES[shape] === SHAPES.Cylinder) this.native.set(1, 1, 1);
    const mat = el.material || "Neon";
    let tex = player.bundle.blockout ? null : texture(player.bundle, el.texture); // blockout: plain shapes
    if (tex && (el.uvScroll || el.flipbook)) { // its own copy (its own offset / cell): the cached texture is shared by every layer
      tex = loadTex(player.bundle.textures[el.texture].url); tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = tex.wrapT = THREE.RepeatWrapping; }
    this.solid = mat === "Glass" || mat === "SmoothPlastic" || !!el.toon;
    this.mat = el.toon // cel-shaded: flat tone bands, no gradients (a drawn object)
      ? new THREE.MeshToonMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, color: 0xffffff, gradientMap: toonRamp(), emissive: 0x000000 })
      : this.solid && el.reflectance > 0 // a MIRROR (liquid metal, chrome): the engine's part Reflectance mirrors the sky -
      // here a metal reflecting the booth's own sky (player.envMap) with the lights' sharp highlights (quicksilver 2026-10-25:
      // grey Lambert read as clay - "meshs ... very low quality")
      ? new THREE.MeshStandardMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, color: 0xffffff, metalness: Math.min(1, el.reflectance), roughness: el.roughness == null ? 0.12 : el.roughness, envMap: player.envMap(), flatShading: !el.smooth, emissive: 0x000000 })
      : this.solid // a solid (ice, stone) is lit and faceted, with a little self-light so it reads at night
      ? new THREE.MeshLambertMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, color: 0xffffff, flatShading: !el.smooth, emissive: 0x000000 }) // `smooth`: a cloud lobe, not a faceted stone (the engine's mesh normals are smooth anyway)
      : new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide, color: 0xffffff, vertexColors: !!geo.attributes.color,
        // a `surface` layer is a SurfaceAppearance in the game (AlphaMode Transparency + EmissiveMask): it BLENDS, it does
        // not add - drawn additive here it washed its cel bands to white over anything behind it (flame_arc round 7)
        blending: (mat === "Neon" || mat === "ForceField") && el.surface == null ? THREE.AdditiveBlending : THREE.NormalBlending });
    if (mat === "ForceField" && el.surface == null && !this.solid) { // the engine's ForceField glows at GRAZING angles (a fresnel
      // edge, faint face-on) - drawn as a flat additive fill, a VfxTech `rim` shell painted its whole mesh (magma_mantle r2, 2026-10-25)
      this.mat.onBeforeCompile = (sh) => {
        sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying float vFres;")
          .replace("#include <project_vertex>", "#include <project_vertex>\nvFres = abs(dot(normalize(normalMatrix * normal), normalize(-mvPosition.xyz)));");
        sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying float vFres;")
          .replace("#include <dithering_fragment>", "#include <dithering_fragment>\n gl_FragColor.rgb *= 0.12 + 0.88 * pow(1.0 - vFres, 2.5);");
      };
    }
    this.mesh = new THREE.Mesh(geo, this.mat); this.mesh.visible = false; this.mesh.renderOrder = 15; player.scene.add(this.mesh);
    if (el.outline != null) { // the ink line: an inflated back-face shell drawn FIRST without writing depth, so the object paints over it and only its rim shows
      this.outlineMat = new THREE.MeshBasicMaterial({ color: colorAt(el.outline, 0, player.palette), side: THREE.BackSide, transparent: true, depthWrite: false });
      const o = new THREE.Mesh(geo, this.outlineMat); o.scale.setScalar(1 + (el.outlineWidth == null ? 0.06 : el.outlineWidth)); o.renderOrder = this.mesh.renderOrder - 1; this.mesh.add(o); }
    this.pivot = el.pivot || (shape === "tube" || shape === "crown" || shape === "cone" || shape === "spiral" || shape === "flame" || shape === "tongue" || shape === "bolt" || shape === "spikes" ? "base" : "center"); // cards: centred, like the sprite they replace
    if (el.wobble) { // the base points, their angle round the axis and their height (0..1): VfxMesh.deform does the same
      const a = geo.attributes.position.array, bb = geo.boundingBox, hy = Math.max(bb.max.y - bb.min.y, 1e-6);
      this.base = Float32Array.from(a); this.wob = [];
      for (let i = 0; i < a.length; i += 3) this.wob.push(Math.atan2(a[i + 2], a[i]), (a[i + 1] - bb.min.y) / hy);
    }
  }
  // erode [start, end, soft]: a dissolve instead of a fade — every vertex has a smooth noise value (patches), its tips
  // and faded edges going first; between start and end of the life the threshold sweeps 0 -> 1. Same rule as VfxMesh.
  erodeAt(u) {
    const g = this.mesh.geometry;
    if (!this.erodeN) {
      const pos = this.base || g.attributes.position.array, n = pos.length / 3; let sd = 0; // the UNWOBBLED points (as VfxMesh) for (const ch of String(this.el.shape || "ring")) sd = (sd * 31 + ch.charCodeAt(0)) % 997; sd *= 0.37; // VfxMesh's seed
      if (!g.attributes.color) { const c = new Float32Array(n * 4).fill(1); g.setAttribute("color", new THREE.BufferAttribute(c, 4)); this.mat.vertexColors = true; this.mat.needsUpdate = true; }
      const col = g.attributes.color.array; this.erodeBase = new Float32Array(n); this.erodeN = new Float32Array(n);
      for (let k = 0; k < n; k++) {
        const x = pos[3 * k], y = pos[3 * k + 1], z = pos[3 * k + 2], a = col[4 * k + 3];
        const nz = 0.5 + 0.25 * Math.sin(1.7 * x + 2.3 * z + sd) * Math.cos(1.3 * y + sd * 1.7) + 0.25 * Math.sin(2.9 * y + 1.1 * x - sd * 0.7);
        this.erodeBase[k] = a; this.erodeN[k] = nz * 0.65 + a * 0.35;
      }
    }
    const [e0, e1, soft] = [this.el.erode[0], this.el.erode[1], this.el.erode[2] == null ? 0.15 : this.el.erode[2]];
    const th = Math.min(1.2, Math.max(0, (u - e0) / Math.max(e1 - e0, 1e-4))) * (1 + soft), col = g.attributes.color.array;
    for (let k = 0; k < this.erodeN.length; k++) {
      const x = Math.min(1, Math.max(0, (th - this.erodeN[k]) / Math.max(soft, 1e-4)));
      col[4 * k + 3] = this.erodeBase[k] * (1 - x * x * (3 - 2 * x));
    }
    g.attributes.color.needsUpdate = true;
  }
  seqFrame(age) { // the baked frames at fps (lerped; loop wraps, else the last frame holds)
    const d = this.seq.data, n = d.frames.length, fps = this.seq.fps || 24, loop = this.seq.loop === true;
    let f = age * fps; f = loop ? f % n : Math.min(Math.max(f, 0), n - 1);
    if (Math.abs(f - (this.lastSeqF == null ? -1 : this.lastSeqF)) < 1e-3) return; this.lastSeqF = f;
    const a = Math.floor(f), b = loop ? (a + 1) % n : Math.min(a + 1, n - 1), t = f - a, fa = d.frames[a], fb = d.frames[b];
    const attr = this.mesh.geometry.attributes.position, arr = attr.array;
    for (let i = 0; i < arr.length; i++) arr[i] = fa[i] + (fb[i] - fa[i]) * t;
    attr.needsUpdate = true; this.mesh.geometry.computeVertexNormals();
  }
  deform(age) { // wobble [amp, freq, speed]: each point moves out from the axis by amp * h^1.5 * sin(freq*angle + speed*age + 4h)
    const [amp, freq, speed] = this.el.wobble, a = this.mesh.geometry.attributes.position, arr = a.array, b = this.base;
    for (let k = 0, i = 0; i < arr.length; i += 3, k += 2) {
      const ang = this.wob[k], h = this.wob[k + 1], d = amp * Math.pow(h, 1.5) * Math.sin(freq * ang + speed * age + 4 * h);
      arr[i] = b[i] + Math.cos(ang) * d; arr[i + 1] = b[i + 1]; arr[i + 2] = b[i + 2] + Math.sin(ang) * d;
    }
    a.needsUpdate = true;
  }
  // the SWEEP (arcs): the whole grid laid over the window [tail, head] of the full arc - the slash draws itself in along
  // the swing and erases behind - by moving the vertices (as VfxMesh: the engine ignores vertex alpha); u pinned to the arc
  sweepAt(tail, head) {
    tail = Math.min(1, Math.max(0, tail)); head = Math.min(1, Math.max(0, head)); if (head < tail) { const x = tail; tail = head; head = x; }
    if (this.lastSweep && Math.abs(this.lastSweep[0] - tail) < 1e-4 && Math.abs(this.lastSweep[1] - head) < 1e-4) return; this.lastSweep = [tail, head];
    const g = this.mesh.geometry, gr = g.userData.grid, pos = g.attributes.position.array, uv = g.attributes.uv.array, p = this.el.params || {};
    let idx = 0;
    for (let k = 0; k < (gr.strands || 1); k++) for (let j = 0; j <= gr.rows; j++) for (let i = 0; i <= gr.cols; i++, idx++) {
      const q = arcPoint(p, i / gr.cols, j / gr.rows, k, tail, head); pos[idx * 3] = q[0]; pos[idx * 3 + 1] = q[1]; pos[idx * 3 + 2] = q[2]; uv[idx * 2] = q[3]; uv[idx * 2 + 1] = j / gr.rows; }
    g.attributes.position.needsUpdate = true; g.attributes.uv.needsUpdate = true;
  }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3);
    const alive = t >= at && (t - at) / life <= 1;
    this.mesh.visible = alive; if (!alive) return 0;
    // step: the layer's clock held on drawings (12 = "on twos", the anime cadence) — every curve, scroll and wobble
    const age = el.step ? Math.floor((t - at) * el.step) / el.step : t - at, u = age / life;
    const sc = vecAt(el.scale == null ? 1 : el.scale, u).multiplyScalar(p.scale);
    const frame = p.frameAt(el.point, el.aim, el.rotate);
    // forced perspective: the layer's size answers the camera's distance (VfxStage: the same, from the layer's point)
    // (on drawings - "step" - the size is the one at the drawing's START, held for the whole drawing: VfxStage the same)
    // the transform as a function of the size `k`: an impact frame drawn through a camera of its OWN (cut, subject)
    // gives a forced layer the size THAT camera's distance asks (`reforce`): it kept the main camera's (stage 13)
    const spinNow = spinAngle(el.spin, age, life);
    const build = (k) => {
      const m = new THREE.Matrix4().copy(frame);
      if (el.move) { const mv = vecAt(el.move, u).multiplyScalar(p.scale); m.multiply(new THREE.Matrix4().makeTranslation(mv.x, mv.y, mv.z)); } // a position offset over life (VfxStage does the same)
      if (this.pivot === "base" || this.pivot === "origin") m.multiply(new THREE.Matrix4().makeTranslation(0, 0, 0)); else m.multiply( // ("origin": a sequence's own origin on its point - VfxStage moves the part by its first frame's middle to the same place)
      new THREE.Matrix4().makeTranslation(-this.center.x * k.x, -this.center.y * k.y, -this.center.z * k.z));
      const spin = spinNow;
      m.multiply(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(spin[0] * DEG, spin[1] * DEG, spin[2] * DEG, "XYZ")));
      m.multiply(new THREE.Matrix4().makeScale(k.x, k.y, k.z));
      return m;
    };
    const forced = el.forced && typeof el.forced === "object";
    const point = new THREE.Vector3().setFromMatrixPosition(frame);
    this.forcedRemake = forced ? (camPos) => build(sc.clone().multiplyScalar(forcedScale(camPos.distanceTo(point), el.forced))) : null;
    const used = forced ? sc.clone().multiplyScalar(forcedScale(p.viewAt(el.step ? at + age : t).pos.distanceTo(point), el.forced)) : sc; // (studs; the view of THIS time, at a drawing's start on `step`)
    this.mesh.matrixAutoUpdate = false; this.mesh.matrix.copy(build(used));
    this.mat.opacity = 1 - numAt(el.transparency, u, 0);
    this.mat.color.copy(colorAt(el.color, u, p.palette));
    if (this.solid) { this.mat.emissive.copy(this.mat.color).multiplyScalar(numAt(el.glow, u, el.reflectance > 0 ? 0 : 0.3)); this.mat.depthWrite = this.mat.opacity > 0.85; } // a mirror has no self-light: it would paint flat grey over its reflections
    if (this.outlineMat) this.outlineMat.opacity = this.mat.opacity;
    if (el.uvScroll && this.mat.map) this.mat.map.offset.set(el.uvScroll[0] * age, el.uvScroll[1] * age);
    if (this.base) this.deform(age);
    if (this.seq) this.seqFrame(age);
    if (el.erode) this.erodeAt(u);
    if (el.sweep && (el.shape || "ring") === "arc") this.sweepAt(numAt(el.sweep.tail, u, 0), numAt(el.sweep.head, u, 1));
    if (el.flipbook && this.mat.map) { // a flipbook sheet played on the mesh: show the frame's cell (VfxStage does the same with UVs)
      const fb = el.flipbook, n = { "2x2": 2, "4x4": 4, "8x8": 8 }[fb.layout || "4x4"] || 4, frames = n * n;
      if (this.flipStart == null) this.flipStart = fb.startRandom ? Math.floor(mulberry(hashName(el.name))() * 64) : 0;
      const f = sheetFrame(fb, u, age, frames, this.flipStart);
      const col = f % n, row = Math.floor(f / n);
      this.mat.map.repeat.set(1 / n, 1 / n); this.mat.map.offset.set(col / n, 1 - (row + 1) / n);
    }
    return 0;
  }
  dispose() { this.p.scene.remove(this.mesh); this.mesh.geometry.dispose(); this.mat.dispose(); }
}

// ---------------------------------------------------------------- decals, lights, debris, screen, impact, shake, fov, sound, glow
class DecalLayer {
  constructor(player, el) {
    this.p = player; this.el = el;
    this.mat = new THREE.MeshBasicMaterial({ map: texture(player.bundle, el.texture), transparent: true, depthWrite: false, blending: THREE.NormalBlending, color: 0xffffff });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.mat); this.mesh.rotation.x = -Math.PI / 2; this.mesh.visible = false; this.mesh.renderOrder = 5; player.scene.add(this.mesh);
  }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life, alive = t >= at && u <= 1;
    this.mesh.visible = alive; if (!alive) return 0;
    const sz = vecAt(el.size == null ? 10 : el.size, u).multiplyScalar(p.scale);
    const rot = el.rotate || [0, 0, 0];
    const pos = p.worldPoint(el.point || [0, 0, 0]);
    this.mesh.position.set(pos.x, pos.y + 0.05, pos.z);
    this.mesh.rotation.set(-Math.PI / 2, 0, -(rot[1] || 0) * DEG);
    this.mesh.scale.set(sz.x, sz.z, 1);
    const g = numAt(el.glow, u, 1);
    this.mat.color.copy(colorAt(el.color, u, p.palette)).multiplyScalar(Math.min(g, 6));
    this.mat.opacity = 1 - numAt(el.transparency, u, 0);
    return 0;
  }
  dispose() { this.p.scene.remove(this.mesh); this.mat.dispose(); }
}
class LightLayer { // type point | spot (a cone along the layer's +Y, aim / rotate) | surface (a wide cone from a panel)
  constructor(player, el) {
    this.p = player; this.el = el; this.type = el.type || "point";
    if (this.type === "point") this.light = new THREE.PointLight(0xffffff, 0, 16, 1.5);
    else { const half = Math.min(89, (el.angle || (this.type === "surface" ? 90 : 60)) / 2) * DEG; this.light = new THREE.SpotLight(0xffffff, 0, 16, half, this.type === "surface" ? 0.9 : 0.35, 1.5); player.scene.add(this.light.target); }
    this.light.visible = false; player.scene.add(this.light);
  }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life, alive = t >= at && u <= 1;
    this.light.visible = alive; if (!alive) return 0;
    const pos = p.worldPoint(el.point || [0, 0, 0]); this.light.position.copy(pos);
    if (this.type !== "point") { const m = p.frameAt(el.point || [0, 0, 0], el.aim, el.rotate); const up = new THREE.Vector3(0, 1, 0).transformDirection(m); this.light.target.position.copy(pos).add(up.multiplyScalar(10)); this.light.target.updateMatrixWorld(); }
    this.light.distance = Math.min(numAt(el.range, u, 16) * p.scale, 60); this.light.intensity = numAt(el.brightness, u, 1) * CAL.light; this.light.color.copy(colorAt(el.color, u, p.palette));
    return 0;
  }
  dispose() { this.p.scene.remove(this.light); if (this.light.target) this.p.scene.remove(this.light.target); }
}
class DebrisLayer {
  constructor(player, el) { this.p = player; this.el = el; this.rng = mulberry(player.seed + hashName(el.name)); this.chunks = null; }
  update(t, dt) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3);
    if (t < at) return 0;
    if (!this.chunks) {
      this.chunks = [];
      const frame = p.frameAt(el.point, el.aim, el.rotate), size = typeof el.size === "number" ? [el.size, el.size] : (el.size || [0.5, 1.5]), speed = typeof el.speed === "number" ? [el.speed, el.speed] : (el.speed || [20, 40]);
      const spread = (el.spread || 60) * DEG, rock = el.shape === "rock", hot = el.material === "Neon";
      // "pieces": a fracture plan's own pieces (VfxStage: the same rule) - each starts where it sat in the slab, is
      // pushed as the plan says and leaves when the break reaches it
      const plan = typeof el.pieces === "string" ? (p.bundle.fractures || {})[el.pieces] : null;
      if (plan && Array.isArray(plan.pieces)) {
        const thick = plan.size[2], made = plan.made && typeof plan.made.speed === "number" ? plan.made.speed : 0, push = typeof el.speed === "number" && made > 0 ? el.speed / made : 1;
        const origin = new THREE.Vector3().setFromMatrixPosition(frame), turn = new THREE.Quaternion().setFromRotationMatrix(frame);
        for (const pc of plan.pieces) {
          const col = colorAt(el.color || [70, 60, 52], this.rng(), p.palette), glass = el.material === "Glass" || el.material === "Ice";
          const mat = hot ? new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide })
            : el.toon ? new THREE.MeshToonMaterial({ color: col, gradientMap: toonRamp(), side: THREE.DoubleSide, emissive: col.clone().multiplyScalar(0.25) }) // (a fracture's pieces read "toon" as thrown chunks do)
            : new THREE.MeshLambertMaterial({ color: col, flatShading: true, side: THREE.DoubleSide, transparent: glass, opacity: glass ? 0.85 : 1, emissive: glass ? col.clone().multiplyScalar(0.3) : 0x000000 });
          // (the game's MeshPart sits and TURNS on the middle of its mesh's box, not on the piece's own centre: the same here)
          const xs = pc.points.map((q) => q[0]), zs = pc.points.map((q) => q[1]), ox = (Math.min(...xs) + Math.max(...xs)) / 2, oz = (Math.min(...zs) + Math.max(...zs)) / 2;
          const mesh = new THREE.Mesh(SHAPES.piece({ points: pc.points, height: thick, centre: pc.centre, slab: [plan.size[0], plan.size[1]] }).translate(-ox, 0, -oz), mat); p.scene.add(mesh);
          if (el.outline != null) { const o = new THREE.Mesh(mesh.geometry, new THREE.MeshBasicMaterial({ color: colorAt(el.outline, 0, p.palette), side: THREE.BackSide, depthWrite: false })); o.scale.setScalar(1.1); o.renderOrder = -1; mesh.add(o); }
          mesh.userData.base = new THREE.Vector3(p.scale, p.scale, p.scale); mesh.userData.debris = true; mesh.quaternion.copy(turn); mesh.scale.copy(mesh.userData.base);
          const [s0, hy0, hw0, s0shape] = debrisStart(pc, thick, p.scale, push); // (the piece as it sits in the slab: VfxStage the same)
          const pos = new THREE.Vector3(s0[0], s0[1], s0[2]).applyQuaternion(turn).add(origin);
          mesh.position.copy(pos);
          this.chunks.push({ mesh, pos, vel: new THREE.Vector3(s0[3], s0[4], s0[5]).applyQuaternion(turn), spin: new THREE.Vector3(pc.spin[0], pc.spin[1], pc.spin[2]).multiplyScalar(push), floor: p.origin.y, h: thick * p.scale / 2, wait: pc.delay });
          if (el.rest === true) { const c = this.chunks[this.chunks.length - 1]; // comes to rest (debrisStep)
            c.st = [c.pos.x, c.pos.y, c.pos.z, c.vel.x, c.vel.y, c.vel.z, 0, 0, s0[8], s0[9], 0]; c.hy = hy0; c.turn = turn.clone();
            c.hw = hw0; mat.transparent = true; c.opacity = mat.opacity; // (it tips about its own X: the side that stands up is its Z)
            c.shape = s0shape; // its flat outline in its OWN axes (debrisStart; debrisMeet turns it by the frame's yaw)
            c.yaw0 = frameYaw(turn);
            c.area = Math.max(typeof pc.area === "number" ? pc.area : 0, 1e-6);
            for (const o of mesh.children) o.material.transparent = true; }
        }
      } else if (typeof el.pieces === "string") {
        console.warn(`debris layer "${el.name}": no fracture plan "${el.pieces}" in this bundle (kit vfx fracture, then kit vfx play again) - nothing flies`); // (VfxStage: the same)
      } else for (let i = 0; i < (el.count || 6); i++) {
        const s = rangeRand(size, this.rng) * p.scale;
        const col = colorAt(el.color || [70, 60, 52], this.rng(), p.palette); // a colour per chunk, picked along the sequence (as the engine does)
        const glass = el.material === "Glass" || el.material === "Ice";
        const mat = hot ? new THREE.MeshBasicMaterial({ color: col })
          : el.toon ? new THREE.MeshToonMaterial({ color: col, gradientMap: toonRamp(), emissive: col.clone().multiplyScalar(0.25) })
          : new THREE.MeshLambertMaterial({ color: col, flatShading: rock, transparent: glass, opacity: glass ? 0.85 : 1, emissive: glass ? col.clone().multiplyScalar(0.3) : 0x000000 });
        const sy = 0.5 + 0.5 * this.rng(), sz = 0.6 + 0.6 * this.rng();
        const geo = rock ? SHAPES.rock({ seed: i + 1 + (el.seed || 0) * 37, cuts: el.cuts, jag: el.jag, spike: el.spike, flat: el.flat }) : new THREE.BoxGeometry(s, s * sy, s * sz);
        const mesh = new THREE.Mesh(geo, mat); p.scene.add(mesh);
        mesh.userData.base = rock ? new THREE.Vector3(s / 2, s * sy / 2, s * sz / 2) : new THREE.Vector3(1, 1, 1);
        if (el.outline != null) { const o = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: colorAt(el.outline, 0, p.palette), side: THREE.BackSide, depthWrite: false })); o.scale.setScalar(1.1); o.renderOrder = -1; mesh.add(o); }
        const yaw = this.rng() * TAU, tilt = this.rng() * spread;
        const dir = new THREE.Vector3(Math.sin(tilt) * Math.cos(yaw), Math.cos(tilt), Math.sin(tilt) * Math.sin(yaw)).transformDirection(frame);
        const origin = new THREE.Vector3().setFromMatrixPosition(frame);
        mesh.userData.debris = true; this.chunks.push({ mesh, pos: origin.clone(), vel: dir.multiplyScalar(rangeRand(speed, this.rng) * p.scale), spin: new THREE.Vector3(this.rng() * 12 - 6, this.rng() * 12 - 6, this.rng() * 12 - 6), floor: el.floor === "world" ? 0 : p.origin.y, h: s / 2 }); // floor "world" = the engine's real physics; here the stage's ground (y 0)
      }
    }
    const u = (t - at) / life, g = (el.gravity || 120) * p.scale;
    if (el.rest === true && u <= 1) { // "rest": the pieces that have left the slab take ONE step together (debrisMeet; VfxStage: the same)
      const live = this.chunks.filter((c) => c.st && !(c.wait && t - at < c.wait));
      // an EARLY STOP (VfxStage: the same): once a step left every piece exactly as it was, at rest, the rule is not run
      // again until another piece leaves the slab
      if (live.length && this.stillAt !== live.length) { const met = debrisMeet(live.map((c) => c.st), live.map((c) => c.shape), live.map((c) => c.hy), live.map((c) => c.hw), live.map((c) => c.area), dt, g, live[0].floor, live[0].yaw0, p.scale); const got = met[0];
        const same = !met[2] && live.every((c, i) => got[i][10] === 1 && got[i].every((v, k) => v === c.st[k])); live.forEach((c, i) => { c.st = got[i]; }); if (dt * DEBRIS_PART > DEBRIS_NUDGE) this.stillAt = same ? live.length : null; } // (only a step with time to push in: VfxStage the same)
    }
    for (const c of this.chunks) {
      if (u > 1) { c.mesh.visible = false; continue; }
      if (c.wait && t - at < c.wait) continue; // the break has not reached this piece
      if (c.st) { // "rest": lands, slides, tips flat and lies there; fades over the last 15 % of the life (VfxStage: the same)
        const st = c.st; // (stepped above, all together)
        c.mesh.position.set(st[0], st[1], st[2]); c.mesh.quaternion.copy(c.turn).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), st[7])).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), st[6]));
        const seen = 1 - Math.min(Math.max((u - 0.85) / 0.15, 0), 1); c.mesh.material.opacity = c.opacity * seen; for (const o of c.mesh.children) o.material.opacity = seen; continue; }
      c.vel.y -= g * dt; c.pos.addScaledVector(c.vel, dt);
      if (c.pos.y < c.floor + c.h) { c.pos.y = c.floor + c.h; c.vel.set(c.vel.x * 0.5, -c.vel.y * 0.25, c.vel.z * 0.5); }
      c.mesh.rotation.x += c.spin.x * dt; c.mesh.rotation.y += c.spin.y * dt; c.mesh.rotation.z += c.spin.z * dt;
      const shrink = 1 - Math.min(Math.max((u - 0.7) / 0.3, 0), 1);
      c.mesh.scale.copy(c.mesh.userData.base).multiplyScalar(Math.max(shrink, 0.01)); c.mesh.position.copy(c.pos);
    }
    return 0;
  }
  dispose() { if (this.chunks) for (const c of this.chunks) { this.p.scene.remove(c.mesh); c.mesh.geometry.dispose(); } }
}
class ScreenLayer { // feeds the post pass: brightness / contrast / saturation / tint / bloom boost
  constructor(player, el) { this.p = player; this.el = el; }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life;
    if (!(t >= at && u <= 1)) return 0;
    const k = p.falloff(el.radius);
    p.post.brightness += numAt(el.brightness, u, 0) * k; p.post.contrast += numAt(el.contrast, u, 0) * k; p.post.saturation += numAt(el.saturation, u, 0) * k;
    const amt = numAt(el.tintAmount, u, 1) * k; if (el.tint && amt > 0) { p.post.tint.lerp(colorAt(el.tint, u, p.palette), amt); }
    p.post.bloom += numAt(el.bloom, u, 0) * k; p.post.blur += numAt(el.blur, u, 0) * k;
    return 0;
  }
  dispose() {}
}
// an onomatopoeia plate: big jagged letters drawn on a canvas (white on transparent; the shader colours them)
function onomatopoeia(text, font, L) { // the word as a GRAPHIC: a heavy scaffold face, skewed, cut by the blade, staggered; a small subline
  L = L || {};
  const cv = document.createElement("canvas"); cv.width = 1024; cv.height = 512; const g = cv.getContext("2d");
  g.clearRect(0, 0, cv.width, cv.height); g.textAlign = "center"; g.textBaseline = "middle";
  const fam = font || "Impact, 'Arial Black', sans-serif"; const chars = Array.from(String(text).toUpperCase());
  const skew = L.skew == null ? -0.22 : L.skew, stagger = L.stagger || 0, cut = L.cut == null ? true : !!L.cut;
  let size = 400; const widthOf = () => { g.font = `900 ${size}px ${fam}`; return chars.reduce((w, ch) => w + g.measureText(ch).width + size * 0.03, 0); };
  while (widthOf() > 900 && size > 60) size -= 20;
  const rng = mulberry(hashName(text)); const cy = L.sub ? 300 : 262; const total = widthOf(); let x = 512 - total / 2;
  const drawWord = (dx, dy) => { let xx = x; let i = 0;
    for (const ch of chars) { const w = g.measureText(ch).width; const cx = xx + w / 2;
      const lag = stagger * (chars.length - 1 - i) * size * 0.16; // the trailing letters lag behind on the entry frame
      const jitter = 1 + (rng() - 0.5) * 0.08;
      g.save(); g.translate(cx + dx - lag, cy + dy + (rng() - 0.5) * size * 0.04); g.transform(1, 0, skew, 1, 0, 0); g.scale(jitter, 1 / jitter * (1 + (rng() - 0.5) * 0.06)); g.fillText(ch, 0, 0); g.restore();
      xx += w + size * 0.03; i++; } };
  g.fillStyle = "#0f0"; // the letters live in the green channel (the ghost word in red)
  if (cut) { // the blade cut: the word sliced along a diagonal, the upper half shifted a step along the cut
    const y0 = cy + size * 0.1, slope = -0.18;
    g.save(); g.beginPath(); g.moveTo(-200, y0 + slope * (-200 - 512)); g.lineTo(1300, y0 + slope * (1300 - 512)); g.lineTo(1300, -200); g.lineTo(-200, -200); g.closePath(); g.clip(); drawWord(size * 0.05, -size * 0.03); g.restore();
    g.save(); g.beginPath(); g.moveTo(-200, y0 + slope * (-200 - 512) + size * 0.035); g.lineTo(1300, y0 + slope * (1300 - 512) + size * 0.035); g.lineTo(1300, 800); g.lineTo(-200, 800); g.closePath(); g.clip(); drawWord(0, 0); g.restore();
  } else drawWord(0, 0);
  if (L.ghost) { // a ghost word (kanji, a second word) hollow behind the band, in the red channel; the shader hatches it
    const gf = L.ghostFont || "'Yu Gothic', 'Meiryo', 'MS Gothic', sans-serif"; let gs = 300; g.font = `900 ${gs}px ${gf}`;
    while (g.measureText(L.ghost).width > 980 && gs > 80) { gs -= 20; g.font = `900 ${gs}px ${gf}`; }
    g.save(); g.globalCompositeOperation = "destination-over"; g.strokeStyle = "#f00"; g.lineWidth = 10; g.lineJoin = "round"; g.strokeText(String(L.ghost), 512, 262); g.restore(); }
  if (L.sub) { // the subline: small spaced capitals above the name
    const sub = String(L.sub).toUpperCase(); const ss = Math.round(size * 0.17); g.font = `700 ${ss}px ${fam}`; const sp = ss * 0.5; g.fillStyle = "#0f0";
    const sw = Array.from(sub).reduce((w, ch) => w + g.measureText(ch).width + sp, 0); let sx = 512 - sw / 2;
    for (const ch of Array.from(sub)) { const w = g.measureText(ch).width; g.fillText(ch, sx + w / 2, cy - size * 0.62); sx += w + sp; } }
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.NoColorSpace; t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; t.needsUpdate = true; t.userData.mid = (512 - cy) / 512; return t;
}
// the drawing knobs of an impact frame (impact style "frame" -> draw {}); `x` = exaggeration, the master over the shape work
function frameDraw(d, x) {
  const n = (v, def) => (v == null ? def : v);
  return { warp: n(d.warp, 1) * x, grow: n(d.grow, 1) * x, smear: n(d.smear, 1) * x, outline: n(d.outline, 1), hatch: n(d.hatch, 0), splatter: n(d.splatter, 1) * x,
    zoom: n(d.zoom, 0.04), shake: n(d.shake, 0.008), flash: n(d.flash, 0), lineart: !!d.lineart, boil: d.boil == null ? true : !!d.boil, rim: n(d.rim, 1), soot: n(d.soot, 1), mass: n(d.mass, 0), wedge: n(d.wedge, 1), star: n(d.star, 0), void: n(d.void, 0), crack: n(d.crack, 0), bolts: n(d.bolts, 0), specks: n(d.specks, 1), smoke: n(d.smoke, 0), semantic: d.semantic == null ? true : !!d.semantic, abstract: !!d.abstract,
    // the SLASH, drawn from the effect's arc meshes (impact frames v4, 2026-10-23): slash = the cut as a calligraphic
    // stroke along the arc (white core, accent body, ink edge, dry-brush breaks); split = the frame cut in two along
    // it, the far side tone-inverted; slide = that side slid along the cut (screen heights); cutSmear = the energy
    // smeared along the cut instead of away from the hit
    slash: n(d.slash, 0), split: n(d.split, 0), slide: n(d.slide, 0), cutSmear: n(d.cutSmear, 0),
    // the KANADA FLARE (research 2026-10-23: Kanada's "straight speedlines, light flares and minimalist impact frames"):
    // razor-straight lines through the hit - a long cross, short diagonals, tapering from the centre - and ghost rings
    // along one axis; white on dark paper, ink on light paper. flare = its size (screen heights)
    flare: n(d.flare, 0),
    // SELECTIVE COLOUR (R2, research: Raiden's ultimate desaturates everything but her - impossible in-engine, where
    // colour correction is global; a baked frame can): the world stays flat grey paper / ink, the effect is drawn in its
    // REAL rendered colour instead of being thresholded to ink. selective = how much of its colour comes through (0-1)
    selective: n(d.selective, 0) };
}
const ANIME_FS = `
uniform sampler2D scene; uniform sampler2D mask; uniform float aspect; uniform vec2 focus; uniform vec2 px;
uniform float look; uniform vec3 shadowC; uniform vec3 lightC; uniform vec3 hatchC; uniform vec3 energyC; uniform vec3 coreC;
uniform vec3 edgeC; uniform vec3 linesC; uniform float zoom; uniform float linesK; uniform float coreSize; uniform float expose; uniform float seed;
varying vec2 vUv;
float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
vec3 tmc(vec3 c){ c *= expose; return c / (1.0 + c); }
float lum(vec3 c){ return dot(c, vec3(0.3, 0.59, 0.11)); }
// tapered radial speed lines converging on the focus: 1 inside a line
float rays(vec2 dv, float n, float r0, float width) {
  float dl = length(dv); float a = atan(dv.y, dv.x) / 6.2831853 + 0.5; float sl = a * n; float slot = floor(sl); float fr = fract(sl);
  float start = r0 + 0.25 * hash21(vec2(slot, seed));
  if (hash21(vec2(slot, seed + 5.0)) < 0.38 || dl < start) return 0.0;
  float w = width * (0.4 + hash21(vec2(slot, seed + 9.0))) * smoothstep(start, start + 0.35, dl);
  return abs(fr - 0.5) < w ? 1.0 : 0.0;
}
void main() {
  vec2 uv = vUv; vec2 dv = vec2((uv.x - focus.x) * aspect, uv.y - focus.y); float dl = length(dv);
  vec3 col;
  if (look < 0.5) { // TONE: the shot, duotoned, hatched, line-art, energy glowing in its own colour
    vec2 su = focus + (uv - focus) / zoom;
    vec3 c = tmc(texture2D(scene, su).rgb); float L = lum(c);
    col = mix(shadowC, lightC, smoothstep(0.08, 0.75, L));
    vec2 q = vec2(uv.x * aspect, uv.y) * 140.0;
    if (L < 0.42 && fract((q.x + q.y) * 0.5) < 0.35 * (1.0 - L / 0.42)) col = hatchC;
    if (L < 0.2 && fract((q.x - q.y) * 0.5) < 0.3 * (1.0 - L / 0.2)) col = hatchC;
    // line art: luminance edges, thin and dark
    vec2 st = px * 1.2 / zoom;
    float gx = lum(tmc(texture2D(scene, su + vec2(st.x, 0.0)).rgb)) - lum(tmc(texture2D(scene, su - vec2(st.x, 0.0)).rgb));
    float gy = lum(tmc(texture2D(scene, su + vec2(0.0, st.y)).rgb)) - lum(tmc(texture2D(scene, su - vec2(0.0, st.y)).rgb));
    if (length(vec2(gx, gy)) > 0.16) col = hatchC * 0.55;
    // the energy: anything bright and coloured keeps its own hue, white at the core, and glows across the frame
    float glow = 0.0; vec3 gcol = vec3(0.0);
    for (int k = 0; k < 12; k++) { float a = float(k) * 0.5236; vec2 o = su + vec2(cos(a), sin(a)) * 0.022 / zoom * (1.0 + float(k / 6));
      vec3 e = tmc(texture2D(scene, o).rgb); float ch = max(e.r, max(e.g, e.b)) - min(e.r, min(e.g, e.b)); float w = smoothstep(0.45, 0.85, lum(e)) * smoothstep(0.1, 0.35, ch + lum(e) * 0.3);
      glow += w; gcol += e * w; }
    glow /= 12.0;
    float chc = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    if (L > 0.5 && (chc > 0.18 || L > 0.85)) col = mix(energyC, vec3(1.0), smoothstep(0.7, 0.95, L));
    col += energyC * glow * 1.4;
    if (linesK > 0.0 && rays(dv, 120.0, 0.25, 0.08 * linesK) > 0.5) col = mix(col, linesC, 0.75);
  } else if (look < 1.5) { // BURST: a radial colour field, tapered speed lines, a white-hot core blooming out
    col = mix(coreC, edgeC, smoothstep(0.02, 0.85, dl));
    if (rays(dv, 90.0, coreSize * 0.6, 0.16 * linesK) > 0.5) col = linesC;
    float core = exp(-pow(dl / max(coreSize, 1e-3), 2.0) * 2.2);
    col = mix(col, vec3(1.0), clamp(core * 1.4, 0.0, 1.0));
    // the subject's shape, a darker cut-out inside the light (the figure in the blast)
    vec2 su = focus + (uv - focus) / zoom; vec3 m = texture2D(mask, su).rgb;
    if (max(m.r, max(m.g, m.b)) > 0.004 && core < 0.6) col = mix(col, edgeC * 0.35, 0.65);
  } else { // SKY: a sky gradient, white radial lines, a white starburst at the hit
    col = mix(lightC, shadowC, smoothstep(0.0, 1.0, uv.y));
    if (rays(dv, 70.0, coreSize * 0.5, 0.11 * linesK) > 0.5) col = linesC;
    float a = atan(dv.y, dv.x) / 6.2831853 * 14.0; float tri = abs(fract(a) - 0.5) * 2.0;
    float R = coreSize * (0.55 + 0.6 * tri * hash21(vec2(floor(a), seed + 2.0)));
    if (dl < R) col = vec3(1.0); else if (dl < R + 0.012) col = mix(col, vec3(1.0), 0.6);
  }
  gl_FragColor = vec4(col, 1.0);
}`;
const COMIC_FS = `
uniform sampler2D scene; uniform sampler2D word; uniform float aspect; uniform vec2 focus; uniform vec2 focus2;
uniform vec3 paper; uniform vec3 ink; uniform vec3 spot; uniform vec3 spot2; uniform vec3 wordColor; uniform vec3 balloonColor;
uniform float panels; uniform float slant; uniform vec3 zoom; uniform float cell; uniform float misreg; uniform float linesMode;
uniform float wordOn; uniform vec2 wordPos; uniform float wordSize; uniform float wordRot; uniform float balloon; uniform float invert;
uniform float seed; uniform vec2 px; uniform float push; uniform vec2 shakeOff;
uniform sampler2D mask; uniform float expose; uniform vec3 skyTone;
varying vec2 vUv;
float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
vec3 tmc(vec3 c){ c *= expose; return c / (1.0 + c); }
float lumAt(vec2 u){ return dot(tmc(texture2D(scene, u).rgb), vec3(0.3, 0.59, 0.11)); }
float mk(vec2 u){ vec3 m = texture2D(mask, u).rgb; return max(m.r, max(m.g, m.b)) > 0.004 ? 1.0 : 0.0; }
void main() {
  vec2 uv = vUv + shakeOff; vec2 q = vec2(uv.x * aspect, uv.y);
  float sl = tan(slant); float s = q.x + (uv.y - 0.5) * sl;
  float b1 = aspect * (panels > 2.5 ? 0.37 : 0.55), b2 = aspect * 0.71;
  float pid = 0.0; float ed = 10.0;
  if (panels > 1.5) { pid = s > b1 ? 1.0 : 0.0; ed = abs(s - b1); if (panels > 2.5) { if (s > b2) pid = 2.0; ed = min(ed, abs(s - b2)); } }
  float gut = 0.011, bw = 0.0055;
  float margin = min(min(q.x, aspect - q.x), min(uv.y, 1.0 - uv.y));
  vec3 col;
  // which shot this panel shows: its centre on screen, what it frames, how close
  float zz = (pid < 0.5 ? zoom.x : pid < 1.5 ? zoom.y : zoom.z) * push;
  vec2 tgt = pid > 1.5 ? focus2 : focus;
  vec2 pc;
  if (panels < 1.5) pc = focus;
  else { float cs = pid < 0.5 ? b1 * 0.5 : (pid < 1.5 ? (panels > 2.5 ? (b1 + b2) * 0.5 : (b1 + aspect) * 0.5) : (b2 + aspect) * 0.5); pc = vec2(cs / aspect, 0.5); }
  vec2 su = tgt + (uv - pc) / zz;
  if (su.x < 0.0 || su.x > 1.0 || su.y < 0.0 || su.y > 1.0) col = paper;
  else {
    vec3 c = tmc(texture2D(scene, su).rgb); float L = dot(c, vec3(0.3, 0.59, 0.11));
    // Ben-Day halftone at 45 degrees: the darker, the bigger the ink dot
    vec2 hp = mat2(0.7071, -0.7071, 0.7071, 0.7071) * (q / cell); vec2 hc = floor(hp) + 0.5; float d = length(hp - hc);
    float obj = mk(su);
    col = paper;
    if (obj < 0.5) { // the empty page: paper, a light screen-tone of sky up top
      if (su.y > 0.45 && d < 0.26 * smoothstep(0.45, 1.0, su.y)) col = skyTone;
    } else {
      float dark = 1.0 - smoothstep(0.06, 0.5, L); // three printed tones: solid ink, Ben-Day dots, clean paper
      if (L < 0.04) col = ink; else if (d < dark * 0.64) col = ink;
    }
    // the energy printed in flat spot inks, off-register (the spot plate sampled a little to the side)
    vec2 so = su + vec2(misreg, -misreg * 0.6) / zz;
    vec3 ce = tmc(texture2D(scene, so).rgb); float Le = dot(ce, vec3(0.3, 0.59, 0.11)); float ch = max(ce.r, max(ce.g, ce.b)) - min(ce.r, min(ce.g, ce.b));
    if (Le > 0.42 && (ch > 0.16 || Le > 0.8)) {
      vec3 nc = normalize(ce + 1e-4); float a1 = dot(nc, normalize(spot + 1e-4)), a2 = dot(nc, normalize(spot2 + 1e-4));
      vec3 sp = a1 >= a2 ? spot : spot2;
      col = Le > 0.86 ? vec3(1.0) : sp;
      if (Le > 0.86 && fract((hp.x + hp.y) * 0.5) < 0.18) col = sp; // a hatch of spot through the white-hot core
    }
    // ink outlines (edges of the luminance)
    vec2 st = px * 1.6 / zz;
    float gx = -lumAt(su + vec2(-st.x, -st.y)) - 2.0 * lumAt(su + vec2(-st.x, 0.0)) - lumAt(su + vec2(-st.x, st.y)) + lumAt(su + vec2(st.x, -st.y)) + 2.0 * lumAt(su + vec2(st.x, 0.0)) + lumAt(su + vec2(st.x, st.y));
    float gy = -lumAt(su + vec2(-st.x, -st.y)) - 2.0 * lumAt(su + vec2(0.0, -st.y)) - lumAt(su + vec2(st.x, -st.y)) + lumAt(su + vec2(-st.x, st.y)) + 2.0 * lumAt(su + vec2(0.0, st.y)) + lumAt(su + vec2(st.x, st.y));
    if (length(vec2(gx, gy)) > 0.32) col = ink;
    // the silhouette: a heavy ink line where an object meets the empty page
    vec2 st2 = px * 2.6 / zz;
    float ms = mk(su + vec2(st2.x, 0.0)) + mk(su - vec2(st2.x, 0.0)) + mk(su + vec2(0.0, st2.y)) + mk(su - vec2(0.0, st2.y));
    if (ms > 0.5 && ms < 3.5) col = ink;
    // comic action lines over the shot
    vec2 dv = vec2((uv.x - pc.x) * aspect, uv.y - pc.y); float dl = length(dv);
    if (linesMode > 0.5 && linesMode < 1.5) {
      float ang = atan(dv.y, dv.x) / 6.2831853 + 0.5; float sl2 = ang * 110.0; float slot = floor(sl2); float fr = fract(sl2);
      float r0 = 0.16 + 0.22 * hash21(vec2(slot, seed));
      if (hash21(vec2(slot, seed + 3.0)) > 0.42 && dl > r0 && fr < 0.28 * min(1.0, (dl - r0) * 3.0)) col = ink;
    } else if (linesMode > 1.5) {
      vec2 r2 = mat2(cos(slant), -sin(slant), sin(slant), cos(slant)) * dv; float band = floor(r2.y * 140.0);
      float x0 = hash21(vec2(band, seed)) * 1.4 - 0.7;
      if (hash21(vec2(band, seed + 7.0)) > 0.55 && fract(r2.y * 140.0) < 0.3 && r2.x > x0 && r2.x < x0 + 0.5 + 0.6 * hash21(vec2(band, seed + 9.0))) col = ink;
    }
    if (invert > 0.5) col = vec3(1.0) - col;
  }
  // gutters and the page margin
  if (panels > 1.5) { if (ed < gut) col = paper; else if (ed < gut + bw) col = ink;
    if (margin < 0.016) col = paper; else if (margin < 0.016 + bw) col = ink; }
  // the SFX word in a spiky burst balloon, a thick outline and a block shadow
  if (wordOn > 0.5) {
    vec2 wq = vec2((uv.x - wordPos.x) * aspect, uv.y - wordPos.y); float cr = cos(wordRot), sr = sin(wordRot); wq = vec2(cr * wq.x - sr * wq.y, sr * wq.x + cr * wq.y);
    if (balloon > 0.5) {
      vec2 bq = vec2(wq.x / 2.1, wq.y); float ba = atan(bq.y, bq.x) / 6.2831853 * 18.0; float tri = abs(fract(ba) - 0.5) * 2.0;
      float R = wordSize * (0.78 + 0.34 * tri + 0.12 * hash21(vec2(floor(ba), seed + 1.0)));
      float rr = length(bq);
      if (rr < R + 0.012) col = ink; if (rr < R) col = balloonColor;
    }
    vec2 tuv = vec2(wq.x / (wordSize * 2.0), wq.y / wordSize) + 0.5; vec2 tp = vec2(0.006, 0.012) / wordSize;
    if (tuv.x > -0.1 && tuv.x < 1.1 && tuv.y > -0.2 && tuv.y < 1.2) {
      float sh = 0.0; for (int k = 1; k <= 7; k++) { vec2 o = tuv - vec2(0.9, -1.4) * tp * float(k); if (o.x > 0.0 && o.x < 1.0 && o.y > 0.0 && o.y < 1.0) sh = max(sh, texture2D(word, o).g); }
      float ol = 0.0; for (int k = 0; k < 12; k++) { float a = float(k) * 0.5236; vec2 o = tuv + vec2(cos(a), sin(a)) * tp * 1.6; if (o.x > 0.0 && o.x < 1.0 && o.y > 0.0 && o.y < 1.0) ol = max(ol, texture2D(word, o).g); }
      float g0 = (tuv.x > 0.0 && tuv.x < 1.0 && tuv.y > 0.0 && tuv.y < 1.0) ? texture2D(word, tuv).g : 0.0;
      if (sh > 0.5 || ol > 0.5) col = ink;
      if (g0 > 0.5) { col = wordColor; if (tuv.y > 0.6) col = mix(wordColor, vec3(1.0), 0.45); if (abs(tuv.x * 0.6 + tuv.y - 1.05) < 0.03) col = vec3(1.0); }
    }
  }
  col *= 0.965 + 0.035 * hash21(floor(vUv * vec2(520.0, 300.0)));
  gl_FragColor = vec4(col, 1.0);
}`;
class ImpactLayer {
  constructor(player, el) { this.p = player; this.el = el; this.plate = el.image ? texture(player.bundle, el.image) : null; if (this.plate) { this.plate.wrapS = this.plate.wrapT = THREE.ClampToEdgeWrapping; }
    // a lines TEXTURE (a motif) is loaded NOW, at build time (2026-10-25: loaded on first use, the first frame of every
    // sequence drew before its texture arrived - no motif on the strike frame, only on the later beats)
    const procLines = { none: 1, fine: 1, bold: 1, both: 1, perspective: 1, cut: 1 };
    if (el.style === "frame" && typeof el.lines === "string" && !procLines[el.lines] && !el.lines.startsWith("#")) {
      this.linesTex = this.linesTex || {};
      if (!this.linesTex[el.lines]) { const t = texture(player.bundle, el.lines); if (t) t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; this.linesTex[el.lines] = t; }
    }
    if (el.text) { this.textTex = onomatopoeia(el.text, el.textFont, el.lettering || {}); player.renderer.initTexture(this.textTex); } }
  update(t0) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3);
    const t = p.frameTime == null ? t0 : p.frameTime; // impact frames run on the held clock inside a hit-stop
    if (!(t >= at && t <= at + life)) return 0;
    if (p.frameTime == null && p.heldWindows && p.heldWindows.some((w) => at >= w.at - 1e-3 && at < w.at + w.len)) return 0; // already shown during the hold
    if (this.plate) { p.plate = { tex: this.plate, alpha: 1 - (el.imageTransparency || 0) }; }
    if (el.style === "anime") { // TV-anime cut-in frames from the real scene: tone (duotone + hatch + glowing energy) | burst | sky
      const named = (v, d) => v == null ? d : v === "white" ? new THREE.Color(1, 1, 1) : v === "black" ? new THREE.Color(0, 0, 0) : rgb(v, p.palette);
      const u = Math.min(1, Math.max(0, (t - at) / life)); const k = (v, d) => (v == null ? d : numAt(v, u, d));
      p.frame = { name: el.name, comic: { anime: true, look: { tone: 0, burst: 1, sky: 2 }[el.look || "tone"] || 0,
          shadow: named(el.shadow, new THREE.Color(0.05, 0.08, 0.22)), light: named(el.light, new THREE.Color(0.62, 0.78, 1.0)), hatch: named(el.hatch, new THREE.Color(0.02, 0.03, 0.12)),
          energy: named(el.energy, new THREE.Color(1, 0.2, 0.15)), core: named(el.core, new THREE.Color(1, 0.95, 0.85)), edge: named(el.edge, new THREE.Color(0.75, 0.04, 0.06)),
          lines: named(el.linesColor, new THREE.Color(1, 1, 1)), zoom: k(el.zoom, 1) * k(el.push, 1), linesK: k(el.linesK, 1), coreSize: k(el.coreSize, 0.18),
          expose: el.expose == null ? 2.2 : el.expose },
        camera: el.camera || "closeup", focus: el.focus || [0, 0, 0], focus2: null, draw: frameDraw({}, 1) };
      return 0;
    }
    if (el.style === "comic") { // the real lit scene printed as a comic page (see drawComic)
      const named = (v, d) => v == null ? d : v === "white" ? new THREE.Color(1, 1, 1) : v === "black" ? new THREE.Color(0, 0, 0) : rgb(v, p.palette);
      if (el.text && !this.textTex) this.textTex = onomatopoeia(el.text, el.textFont, el.lettering || { band: false });
      const u = Math.min(1, Math.max(0, (t - at) / life)); const k = (v, d) => (v == null ? d : numAt(v, u, d));
      const z = Array.isArray(el.zoom) ? el.zoom : [el.zoom == null ? 1 : el.zoom, 1, 1];
      p.frame = { name: el.name, comic: { panels: Math.max(1, Math.min(3, Math.round(el.panels || 1))), slant: k(el.slant, 8), zoom: [z[0] || 1, z[1] || 1, z[2] || 1],
          halftone: el.halftone == null ? 0.011 : el.halftone, misreg: el.misreg == null ? 0.004 : el.misreg, lines: { none: 0, radial: 1, speed: 2 }[el.lines || "radial"] || 0,
          paper: named(el.paper, new THREE.Color(0.97, 0.95, 0.88)), ink: named(el.ink, new THREE.Color(0.04, 0.04, 0.06)), spot: named(el.spot, new THREE.Color(0.3, 1, 0.45)),
          spot2: named(el.spot2, new THREE.Color(1, 0.15, 0.12)), wordColor: named(el.wordColor, new THREE.Color(1, 0.86, 0.1)), balloonColor: named(el.balloonColor, new THREE.Color(1, 1, 1)),
          word: el.text ? this.textTex : null, wordPos: el.wordPos || [0.5, 0.5], wordSize: k(el.wordSize, 0.3), wordRot: k(el.wordRot, -10), balloon: !!el.balloon,
          invert: !!el.invert, push: k(el.push, 1), shake: k(el.shake, 0), expose: el.expose == null ? (p.day ? 2.0 : 3.0) : el.expose,
          skyTone: named(el.skyTone, new THREE.Color(0.55, 0.75, 1.0)) },
        camera: el.camera || "closeup", focus: el.focus || [0, 0, 0], focus2: el.focus2 == null ? null : el.focus2, draw: frameDraw({}, 1) };
      return 0;
    }
    if (el.style === "frame") { // the frame built from the scene: paper, ink silhouettes, energy as hot / marks, radial lines at the focus
      const named = (v, d) => v == null ? d : v === "white" ? new THREE.Color(1, 1, 1) : v === "black" ? new THREE.Color(0, 0, 0) : rgb(v, p.palette);
      const paper = named(el.paper, new THREE.Color(1, 1, 1)); const light = (paper.r * 0.3 + paper.g * 0.59 + paper.b * 0.11) > 0.5;
      const ink = named(el.ink, light ? new THREE.Color(0, 0, 0) : new THREE.Color(1, 1, 1));
      const accent = named(el.accent, null);
      const en = Array.isArray(el.energy) ? el.energy : [0.22, 0.8];
      const lm = el.lines == null ? "fine" : el.lines; const procedural = { none: 0, fine: 1, bold: 2, both: 3, perspective: 5, cut: 6 };
      if (el.text && !this.textTex) this.textTex = onomatopoeia(el.text, el.textFont, el.lettering || {}); // (normally made in the constructor)
      // a lines TEXTURE per key (2026-10-25: one cached texture served every frame - an effect's second motif drew its first)
      if (!(lm in procedural)) { this.linesTex = this.linesTex || {}; if (!this.linesTex[lm]) { const t = texture(p.bundle, lm); if (t) t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; this.linesTex[lm] = t; } this.lines = this.linesTex[lm]; }
      p.frame = { name: el.name, fill: el.fill, roll: el.roll, paper, ink, hot: named(el.hot, accent || ink), mark: named(el.mark, ink), lines: lm in procedural ? null : this.lines, linesMode: lm in procedural ? procedural[lm] : 4, camera: el.camera || "closeup", linesColor: named(el.linesColor, ink),
        text: el.text ? (() => { const L = el.lettering || {}; const u = Math.min(1, Math.max(0, (t - at) / life)); const k = (v, d) => (v == null ? d : numAt(v, u, d)); // a knob may be a curve over the frame's life
          return { tex: this.textTex, size: (el.textSize == null ? 0.55 : el.textSize) * k(L.scale, 1), rot: (el.textRot == null ? -12 : el.textRot) + k(L.tilt, 0), color: named(el.textColor, accent || paper), at: el.textPos === "center" || el.textPos === "band" ? el.textPos : (el.textAt || null),
          stretch: k(L.stretch, 1), squash: k(L.squash, 1), offset: k(L.offset, 0), band: L.band == null ? true : !!L.band, bandLines: k(L.bandLines, 1), bandColor: named(L.bandColor, ink), bandOffset: k(L.bandOffset, 0),
          distort: k(L.distort, 0), spot: k(L.spot, 0), reveal: k(L.reveal, 1), claws: L.claws == null ? 1 : L.claws, clawSpacing: k(L.clawSpacing, 0.16), jag: k(L.jag, 0), shatter: k(L.shatter, 0), crawl: k(L.crawl, 1),
          rough: k(L.rough, 0), drips: k(L.drips, 0), blood: named(L.blood, new THREE.Color(0.55, 0.02, 0.03)), spin: k(L.spin, 0),
          cover: !!L.cover, cutAngle: k(L.cutAngle, -18), gap: k(L.gap, 0), slide: k(L.slide, 0), cutFlash: k(L.cutFlash, 0), cardColor: named(L.cardColor, new THREE.Color(0, 0, 0)),
          split: k(L.split, 1), glint: k(L.glint, -1), trail: k(L.trail, 0), mid: this.textTex && this.textTex.userData.mid != null ? this.textTex.userData.mid : 0.49 }; })() : null, draw: frameDraw(el.draw || {}, el.exaggeration == null ? 1 : el.exaggeration), linesScale: el.linesScale == null ? 1.6 : el.linesScale, linesStrength: el.linesStrength == null ? 1 : el.linesStrength, hole: el.linesHole == null ? 0.08 : el.linesHole, focus: el.focus || el.point || "target", subject: el.subject || "actor", markT: en[0], hotT: en[1] };
      if (!el.mode) return 0;
    }
    const mode = el.mode || (el.image || el.style ? "none" : "white");
    if (mode === "none") return 0;
    if (mode === "flash") { p.post.brightness += 1; } // a flat white-out, as the engine's ColorCorrection at brightness 1
    else if (mode === "ink") { p.post.brightness += -1; p.post.contrast += 2.5; } // the anime ink frame: black world, only the hottest light stays (colour kept: the strokes carry the tint)
    else if (mode === "black") { p.post.brightness += -0.6; p.post.contrast += 3; p.post.saturation += -1; }
    else if (mode === "mono") { p.post.brightness += 0.1; p.post.contrast += 2.5; p.post.saturation += -1; }
    else if (mode === "invert") { p.post.contrast += -2; } // the negative frame: (c - 0.5) * (1 - 2) + 0.5 = 1 - c
    else { p.post.brightness += 0.9; p.post.contrast += 1.5; p.post.saturation += -0.6; }
    if (el.tint) p.post.tint.copy(rgb(el.tint, p.palette));
    return 0;
  }
  dispose() {}
}
// shake: noise of `amplitude` degrees + the KICK (VfxStage, same rule): `kick` [x, y] degrees the PICTURE jolts with the
// strike (x right, y up) under `kickCurve` (default a 0.06-of-life punch eased home) - the camera turns the other way
const KICK_CURVE = [[0, 0], [0.06, 1], [0.35, 0.3], [1, 0]];
class ShakeLayer { constructor(player, el) { this.p = player; this.el = el; } update(t) { const el = this.el, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life; if (t >= at && u <= 1) { const fall = this.p.falloff(el.radius); this.p.feel.shake += numAt(el.amplitude, u, 0) * fall;
  if (Array.isArray(el.kick)) { const k = numAt(el.kickCurve || KICK_CURVE, u, 0) * fall; this.p.feel.kickX += (el.kick[0] || 0) * k; this.p.feel.kickY -= (el.kick[1] || 0) * k; } } return 0; } dispose() {} }
class FovLayer { constructor(player, el) { this.p = player; this.el = el; } update(t) { const el = this.el, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life; if (t >= at && u <= 1) this.p.feel.fov += numAt(el.delta, u, 0) * this.p.falloff(el.radius); return 0; } dispose() {} }
class SoundLayer {
  constructor(player, el) { this.p = player; this.el = el; this.played = false; }
  update(t) {
    const el = this.el, p = this.p;
    if (this.played || t < (el.at || 0)) return 0;
    this.played = true;
    const url = p.bundle.sounds[el.sound]; if (!url || p.muteSound) return 0;
    try { const a = new Audio(url); a.volume = Math.min(1, (el.volume || 1) / 3); a.playbackRate = typeof el.pitch === "number" ? el.pitch : (el.pitch ? (el.pitch[0] + el.pitch[1]) / 2 : 1); a.play().catch(() => {}); } catch (e) { /* no audio */ }
    return 0;
  }
  dispose() {}
}
// highlight: Roblox's Highlight on the actor ("@body"): a flat fill blended over the body + a rim round its SILHOUETTE.
// The rim is an inflated back-face shell per part, drawn only where the body did not mark the stencil — so the joins
// between parts get no line, like Roblox's screen-space outline of the whole model.
class HighlightLayer {
  constructor(player, el) {
    this.p = player; this.el = el; this.parts = [];
    const target = String(el.target || "").slice(1);
    const root = target === "body" ? player.actor && player.actor.group : (player.actor && player.actor[target]);
    if (!root) return;
    const meshes = []; root.traverse((o) => { if (o.isMesh && o.visible && !o.userData.hl) meshes.push(o); });
    for (const m of meshes) { const bm = m.material; bm.stencilWrite = true; bm.stencilRef = 1; bm.stencilFunc = THREE.AlwaysStencilFunc; bm.stencilZPass = THREE.ReplaceStencilOp; }
    for (const m of meshes) {
      const fill = new THREE.Mesh(m.geometry, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -4 }));
      const rim = new THREE.Mesh(m.geometry, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, depthWrite: false, side: THREE.BackSide,
        stencilWrite: true, stencilRef: 1, stencilFunc: THREE.NotEqualStencilFunc, stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilZPass: THREE.KeepStencilOp }));
      const sz = new THREE.Vector3(); if (!m.geometry.boundingBox) m.geometry.computeBoundingBox(); m.geometry.boundingBox.getSize(sz);
      rim.scale.set(1 + 0.14 / Math.max(sz.x, 0.05), 1 + 0.14 / Math.max(sz.y, 0.05), 1 + 0.14 / Math.max(sz.z, 0.05));
      fill.userData.hl = rim.userData.hl = true; fill.renderOrder = 12; rim.renderOrder = 11; fill.visible = rim.visible = false;
      m.add(fill); m.add(rim); this.parts.push({ fill, rim });
    }
  }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life, on = t >= at && u <= 1;
    for (const { fill, rim } of this.parts) {
      fill.visible = rim.visible = on; if (!on) continue;
      fill.material.color.copy(colorAt(el.fill, u, p.palette)); fill.material.opacity = 1 - numAt(el.fillTransparency, u, 0.6);
      rim.material.color.copy(colorAt(el.outline, u, p.palette)); rim.material.opacity = 1 - numAt(el.outlineTransparency, u, 0);
    }
    return 0;
  }
  dispose() { for (const { fill, rim } of this.parts) { fill.parent && fill.parent.remove(fill); rim.parent && rim.parent.remove(rim); fill.material.dispose(); rim.material.dispose(); } }
}
class GlowLayer { // the actor's blade turns to light
  constructor(player, el) { this.p = player; this.el = el; }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life;
    const blade = p.actor && p.actor.blade; if (!blade) return 0;
    if (t >= at && u <= 1) { blade.material.emissive.copy(colorAt(el.color, u, p.palette)); blade.material.emissiveIntensity = 2.5; blade.material.color.set(0xffffff); }
    else { blade.material.emissiveIntensity = 0; blade.material.color.set(0xe2e6f0); }
    return 0;
  }
  dispose() { const blade = this.p.actor && this.p.actor.blade; if (blade) blade.material.emissiveIntensity = 0; }
}
// trail: a ribbon through the recent positions of two points (a sword's edge: "target": "@blade" + "span", or from/to)
class TrailLayer {
  constructor(player, el) {
    this.p = player; this.el = el; this.hist = []; this.maxSamples = 120;
    const geo = new THREE.BufferGeometry();
    const n = this.maxSamples * 2;
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(n * 2), 2));
    geo.setAttribute("aAlpha", new THREE.BufferAttribute(new Float32Array(n), 1));
    const idx = []; for (let i = 0; i < this.maxSamples - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    geo.setIndex(idx); geo.setDrawRange(0, 0);
    this.mat = new THREE.MeshBasicMaterial({ map: texture(player.bundle, el.texture), transparent: true, depthWrite: false, side: THREE.DoubleSide, color: 0xffffff, blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor });
    this.mat.onBeforeCompile = (sh) => {
      // "mesh": true = the engine's RIBBON (VfxMesh.ribbon): a SurfaceAppearance part - it blends (no LightEmission add),
      // its colour is the texture's, its fade along the trail only the texture's alpha (the engine ignores vertex alpha)
      sh.uniforms.uBright = { value: el.mesh ? 1 : (el.brightness == null ? 1 : el.brightness) * CAL.beam }; sh.uniforms.uLE = { value: el.mesh ? 0 : (el.lightEmission == null ? 1 : el.lightEmission) };
      sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nattribute float aAlpha; varying float vAlpha;").replace("#include <uv_vertex>", "#include <uv_vertex>\nvAlpha = aAlpha;");
      sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uBright; uniform float uLE; varying float vAlpha;")
        .replace("#include <dithering_fragment>", "#include <dithering_fragment>\n float a = gl_FragColor.a * vAlpha; gl_FragColor = vec4(gl_FragColor.rgb * uBright * a, a * (1.0 - clamp(uLE, 0.0, 1.0)));");
    };
    this.mesh = new THREE.Mesh(geo, this.mat); this.mesh.frustumCulled = false; this.mesh.renderOrder = 22; this.mesh.visible = false; player.scene.add(this.mesh);
  }
  ends() {
    const el = this.el, p = this.p;
    if (typeof el.target === "string" && el.target.startsWith("@")) {
      const span = el.span || [[0, -1, 0], [0, 1, 0]];
      const b = p.actor.blade; // the only part anchor the player has
      return [v3(span[0]).multiplyScalar(p.scale).applyMatrix4(b.matrixWorld), v3(span[1]).multiplyScalar(p.scale).applyMatrix4(b.matrixWorld)];
    }
    return [p.worldPoint(el.from || [0, -1, 0]), p.worldPoint(el.to || [0, 1, 0])];
  }
  update(t, dt, frozen) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life, alive = t >= at && u <= 1;
    const lifetime = el.lifetime || 0.5;
    if (alive && !frozen && dt > 0) { const [a, b] = this.ends(); this.hist.push({ t, a, b }); if (this.hist.length > this.maxSamples) this.hist.shift(); }
    this.hist = this.hist.filter((h) => t - h.t <= lifetime);
    const n = this.hist.length;
    this.mesh.visible = n >= 2;
    if (n < 2) return 0;
    const pos = this.mesh.geometry.attributes.position.array, uv = this.mesh.geometry.attributes.uv.array, al = this.mesh.geometry.attributes.aAlpha.array;
    for (let i = 0; i < n; i++) {
      const h = this.hist[i]; const age = (t - h.t) / lifetime; const f = i / (n - 1);
      const tr = el.mesh ? numAt(el.transparency == null ? 0 : el.transparency, Math.min(Math.max(u, 0), 1), 0) : numAt(el.transparency == null ? 0 : el.transparency, age, 0);
      const ws = numAt(el.widthScale == null ? 1 : el.widthScale, age, 1);
      const mid = h.a.clone().lerp(h.b, 0.5); const a = mid.clone().lerp(h.a, ws), b = mid.clone().lerp(h.b, ws);
      pos.set([a.x, a.y, a.z, b.x, b.y, b.z], i * 6); uv.set([f, 0, f, 1], i * 4); al[i * 2] = al[i * 2 + 1] = 1 - tr;
    }
    const g = this.mesh.geometry; g.attributes.position.needsUpdate = g.attributes.uv.needsUpdate = g.attributes.aAlpha.needsUpdate = true; g.setDrawRange(0, (n - 1) * 6);
    this.mat.color.copy(el.mesh ? new THREE.Color(1, 1, 1) : colorAt(el.color, 0, p.palette)); // a SurfaceAppearance ignores the part's Color
    return 0;
  }
  dispose() { this.p.scene.remove(this.mesh); this.mesh.geometry.dispose(); this.mat.dispose(); }
}
function hideLayer(l) { // peek: everything but one layer goes invisible for this frame (the next update restores it)
  if (l.mesh) l.mesh.visible = false;
  if (l.meshes) for (const m of l.meshes) m.visible = false; // (a swarm of stones draws by eight meshes)
  if (l.strips) for (const s of l.strips) s.mesh.visible = false;
  if (l.light) l.light.visible = false;
  if (l.chunks) for (const c of l.chunks) c.mesh.visible = false;
  if (l.twinLayer && l.twinLayer.mesh) l.twinLayer.mesh.visible = false;
}
// swarm: scripted particles (VfxStage builders.swarm, the same maths): curl-noise swirl, attraction / vortex, gravity,
// drag, a floor to bounce on, a trail behind each. Spheres (or boxes) in one instanced mesh; trails as fading lines
function hash3(i, j, k) { const x = Math.sin(i * 127.1 + j * 311.7 + k * 74.7) * 43758.5453; return x - Math.floor(x); }
function noise3(x, y, z) {
  const i = Math.floor(x), j = Math.floor(y), k = Math.floor(z), fx = x - i, fy = y - j, fz = z - k;
  const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy), uz = fz * fz * (3 - 2 * fz), L = (a, b, t) => a + (b - a) * t;
  const x00 = L(hash3(i, j, k), hash3(i + 1, j, k), ux), x10 = L(hash3(i, j + 1, k), hash3(i + 1, j + 1, k), ux);
  const x01 = L(hash3(i, j, k + 1), hash3(i + 1, j, k + 1), ux), x11 = L(hash3(i, j + 1, k + 1), hash3(i + 1, j + 1, k + 1), ux);
  return L(L(x00, x10, uy), L(x01, x11, uy), uz) * 2 - 1;
}
function curl3(x, y, z) {
  const e = 0.1, psi = (px, py, pz) => [noise3(px, py, pz), noise3(px + 31.4, py + 7.1, pz + 2.9), noise3(px + 11.3, py + 53.7, pz + 17.2)];
  const dx1 = psi(x + e, y, z), dx0 = psi(x - e, y, z), dy1 = psi(x, y + e, z), dy0 = psi(x, y - e, z), dz1 = psi(x, y, z + e), dz0 = psi(x, y, z - e), k = 1 / (2 * e);
  return new THREE.Vector3(((dy1[2] - dy0[2]) - (dz1[1] - dz0[1])) * k, ((dz1[0] - dz0[0]) - (dx1[2] - dx0[2])) * k, ((dx1[1] - dx0[1]) - (dy1[0] - dy0[0])) * k);
}
// F1b onBounce (src/kit/VfxBounce.luau: the same rule): a bounce's landing speed (straight down, preset units) -> how
// many sparks it throws; 0 under `min` or once the layer has thrown `max` bursts
function bounceBurst(s, land, used) {
  if (!s || typeof land !== "number" || land !== land) return 0;
  const min = s.min == null ? 4 : s.min, maxB = s.max == null ? 24 : s.max;
  if (land < min || used >= maxB) return 0;
  const count = s.count == null ? 4 : s.count, k = Math.max(0, Math.min(1, land / Math.max(min * 3, 1e-3)));
  return Math.max(1, Math.min(count, Math.floor(count * k + 0.5)));
}
class SwarmLayer {
  constructor(player, el) {
    this.p = player; this.el = el; const n = this.n = Math.max(1, Math.min(el.shape === "Rock" ? 40 : 150, el.count || 40));
    const r = mulberry((el.seed || 1) * 7919 + hashName(el.name));
    const lt = el.lifetime == null ? [1, 1] : (typeof el.lifetime === "number" ? [el.lifetime, el.lifetime] : el.lifetime);
    const sp = el.speed == null ? [4, 8] : (typeof el.speed === "number" ? [el.speed, el.speed] : el.speed);
    this.q = [];
    for (let i = 0; i < n; i++) {
      const u = r() * 2 - 1, th = r() * Math.PI * 2, s = Math.sqrt(1 - u * u), dir = new THREE.Vector3(s * Math.cos(th), u, s * Math.sin(th));
      this.q.push({ born: (el.at || 0) + (el.spawn || 0) * i / Math.max(n - 1, 1), life: lt[0] + (lt[1] - lt[0]) * r(), off: dir.clone().multiplyScalar((el.radius || 1) * Math.cbrt(r()) * player.scale),
        vel0: dir.clone().multiplyScalar((sp[0] + (sp[1] - sp[0]) * r()) * player.scale), seed: r() * 100, pos: null, vel: null, hist: [] });
    }
    // "shape": "Rock" - MESH PARTICLES: every particle a faceted stone that tumbles (VfxStage: the same; there each
    // particle is its own stone of EIGHT, cycled; here the same eight, each drawn as instances of itself)
    const rocky = el.shape === "Rock", rk = (rocky && el.rock && typeof el.rock === "object") ? el.rock : {};
    let geo = el.shape === "Block" ? new THREE.BoxGeometry(1, 1, 1) : new THREE.SphereGeometry(0.5, 10, 8);
    const stone = (k) => { const g = SHAPES.rock({ seed: 500 + k + (el.seed || 0) * 37, cuts: rk.cuts, jag: rk.jag, spike: rk.spike, flat: rk.flat }); g.computeBoundingBox(); // (VfxStage: seed 500 + (i - 1) % 8 + ...)
      const bb = g.boundingBox, side = Math.max(bb.max.x - bb.min.x, bb.max.y - bb.min.y, bb.max.z - bb.min.z, 1e-3); // `size` is the stone's LONGEST side
      g.translate(-(bb.max.x + bb.min.x) / 2, -(bb.max.y + bb.min.y) / 2, -(bb.max.z + bb.min.z) / 2); g.scale(1 / side, 1 / side, 1 / side); return g; };
    if (rocky) { geo = stone(0);
      const tum = Array.isArray(el.tumble) ? el.tumble : [2, 6]; // (drawn after every other number, so a swarm of balls keeps the numbers it had)
      for (const q of this.q) { const u = r() * 2 - 1, th = r() * Math.PI * 2, s = Math.sqrt(1 - u * u); q.axis = new THREE.Vector3(s * Math.cos(th), u, s * Math.sin(th)); q.rate = tum[0] + (tum[1] - tum[0]) * r(); } }
    const neon = (el.material || (rocky ? "Slate" : "Neon")) === "Neon"; // (a stone is stone unless said: VfxStage the same)
    this.mat = neon ? new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })
      : el.reflectance > 0 // mirror beads (liquid metal): the meshes' metal on the booth sky; the engine sets Part.Reflectance
      ? new THREE.MeshStandardMaterial({ transparent: true, flatShading: rocky, metalness: Math.min(1, el.reflectance), roughness: el.roughness == null ? 0.12 : el.roughness, envMap: player.envMap() })
      : new THREE.MeshLambertMaterial({ transparent: true, flatShading: rocky }); // (a stone's facets show: the debris layer's stones the same)
    this.mesh = new THREE.InstancedMesh(geo, this.mat, n); this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.mesh.frustumCulled = false;
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3); player.scene.add(this.mesh);
    // the meshes a particle is drawn by: one for a swarm of balls or blocks; EIGHT for stones (particle i is stone i % 8, as
    // the game cycles them) - every mesh holds a place for every particle, at no size where the particle is another's
    this.meshes = [this.mesh];
    if (rocky) { for (let k = 1; k < Math.min(8, n); k++) { const im = new THREE.InstancedMesh(stone(k), this.mat, n); im.instanceMatrix.setUsage(THREE.DynamicDrawUsage); im.frustumCulled = false;
        im.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3); player.scene.add(im); this.meshes.push(im); }
      const none = new THREE.Matrix4().makeScale(0, 0, 0); for (const im of this.meshes) for (let i = 0; i < n; i++) im.setMatrixAt(i, none); }
    if (el.trail) { this.trailMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.6, blending: neon ? THREE.AdditiveBlending : THREE.NormalBlending, vertexColors: false }); this.trails = []; }
    this.last = null; this.alive = 0;
    // F1b: the bounce's own burst - small additive spheres (VfxStage: ONE ParticleEmitter, Emit(n) at the contact)
    const ob = (el.floor && typeof el.floor === "object") ? el.floor.onBounce : null;
    if (ob && typeof ob === "object") {
      const cap = Math.min(600, (ob.max == null ? 24 : ob.max) * (ob.count == null ? 4 : ob.count));
      this.sub = { spec: ob, used: 0, cap, live: [], rng: mulberry((el.seed || 1) * 104729 + 7),
        mesh: new THREE.InstancedMesh(new THREE.SphereGeometry(0.5, 6, 4), new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
          color: new THREE.Color(...(ob.color || [255, 236, 190]).map((c) => c / 255)) }), cap) };
      this.sub.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.sub.mesh.frustumCulled = false; player.scene.add(this.sub.mesh);
      const none = new THREE.Matrix4().makeScale(0, 0, 0); for (let i = 0; i < cap; i++) this.sub.mesh.setMatrixAt(i, none);
    }
    // "field": an AUTHORED vector field (kit vfx field; the bundle's fields) - VfxStage: the same rule
    // "cloud": a POINT CLOUD (kit vfx points; the bundle's points) - VfxStage: the same rule
    this.cloud = null;
    if (el.cloud && typeof el.cloud === "object" && typeof el.cloud.name === "string") { const c = (player.bundle.points || {})[el.cloud.name];
      if (c && Array.isArray(c.points) && c.points.length > 0) this.cloud = c.points; else console.warn(`swarm layer "${el.name}": no cloud "${el.cloud.name}" in this bundle (kit vfx points, then kit vfx play again)`); }
    this.field = null;
    if (el.field && typeof el.field === "object" && typeof el.field.name === "string") { const f = (player.bundle.fields || {})[el.field.name];
      if (f && Array.isArray(f.elements) && f.elements.length > 0) this.field = f.elements; else console.warn(`swarm layer "${el.name}": no field "${el.field.name}" in this bundle (kit vfx field, then kit vfx play again)`); }
  }
  update(t) {
    const el = this.el, p = this.p, dt = this.last == null ? 0 : Math.max(0, Math.min(t - this.last, 1 / 15)); this.last = t;
    // drag may be a curve over the LAYER's life like attract (VfxStage: the same): held in a shell, then a free fall
    const m = new THREE.Matrix4(), curl = el.curl, att = el.attract, grav = (el.gravity || 0) * p.scale, floor = el.floor;
    const drag = numAt(el.drag || 0, Math.max(0, Math.min(1, (t - (el.at || 0)) / Math.max(el.life || 1, 1e-3))), 0);
    let alive = 0, opacity = 0;
    for (let i = 0; i < this.n; i++) {
      const q = this.q[i], age = t - q.born;
      if (age < 0 || age > q.life) { if (age < 0) q.pos = null; q.hist = []; q.dead = age > q.life; m.makeScale(0, 0, 0); this.meshes[i % this.meshes.length].setMatrixAt(i, m); continue; } q.dead = false; // a dead particle's trail goes with it (it drew on the ground for the rest of the effect)
      if (!q.pos) { q.pos = p.worldPoint(el.point || [0, 0, 0]).add(q.off); q.vel = q.vel0.clone(); }
      const v = q.vel, pos = q.pos;
      if (curl) { const sc = (curl.scale || 4) * p.scale; v.addScaledVector(curl3(pos.x / sc + q.seed * 0.01, pos.y / sc + t * (curl.speed == null ? 0.3 : curl.speed), pos.z / sc), (curl.strength == null ? 10 : curl.strength) * p.scale * dt); }
      // attract strength / swirl may be curves over the LAYER's life (VfxStage: the same): an implosion that lets go
      if (att) { const lu = Math.max(0, Math.min(1, (t - (el.at || 0)) / Math.max(el.life || 1, 1e-3))), str = numAt(att.strength == null ? 20 : att.strength, lu, 20), sw = numAt(att.swirl || 0, lu, 0);
        const to = p.worldPoint(att.point || el.point || [0, 0, 0]).sub(pos); const d = Math.max(to.length(), 0.5); to.normalize(); v.addScaledVector(to, str * p.scale * dt);
        if (sw) v.addScaledVector(new THREE.Vector3().crossVectors(to, new THREE.Vector3(0, 1, 0)), sw * p.scale / Math.sqrt(d) * dt); }
      if (this.field) { const lu = Math.max(0, Math.min(1, (t - (el.at || 0)) / Math.max(el.life || 1, 1e-3))), base = p.worldPoint(el.point || [0, 0, 0]);
        const f = fieldAt(this.field, (pos.x - base.x) / p.scale, (pos.y - base.y) / p.scale, (pos.z - base.z) / p.scale), g = p.scale * numAt(el.field.gain, lu, 1), k = 1 - Math.exp(-(typeof el.field.follow === "number" ? el.field.follow : 6) * dt); // (the same at any frame rate)
        v.x += (f[0] * g - v.x) * k; v.y += (f[1] * g - v.y) * k; v.z += (f[2] * g - v.z) * k; }
      v.y -= grav * dt; if (drag > 0) v.multiplyScalar(Math.exp(-drag * 0.693 * dt));
      /* the cloud's pull LAST, on the speed everything else has made (VfxStage: the same place) */
      if (this.cloud) { const lu = Math.max(0, Math.min(1, (t - (el.at || 0)) / Math.max(el.life || 1, 1e-3))), w = numAt(el.cloud.pull, lu, 8); /* a curve over the LAYER's life: 0 lets go */
        if (w > 0) { const pt = this.cloud[i % this.cloud.length], reach = (typeof el.cloud.size === "number" ? el.cloud.size : 4) * p.scale, base = p.worldPoint(el.point || [0, 0, 0]);
          v.set(cloudPull(pos.x - (base.x + pt[0] * reach), v.x, w, dt), cloudPull(pos.y - (base.y + pt[1] * reach), v.y, w, dt), cloudPull(pos.z - (base.z + pt[2] * reach), v.z, w, dt)); } }
      pos.addScaledVector(v, dt);
      if (floor) { const fy = p.worldPoint([0, floor.y || 0, 0]).y; if (pos.y < fy) { const land = Math.max(-v.y, 0); pos.y = fy; v.set(v.x * 0.8, -v.y * (floor.bounce == null ? 0.4 : floor.bounce), v.z * 0.8);
        if (this.sub) { const sb = this.sub, ob = sb.spec, nB = bounceBurst(ob, land / p.scale, sb.used);
          if (nB > 0) { sb.used++; const sp2 = ob.speed || [4, 10], spread = (ob.spread == null ? 35 : ob.spread) * DEG, life = ob.life == null ? 0.35 : ob.life;
            for (let k = 0; k < nB && sb.live.length < sb.cap; k++) { const th = sb.rng() * Math.PI * 2, ph = spread * Math.sqrt(sb.rng()), spd = (sp2[0] + (sp2[1] - sp2[0]) * sb.rng()) * p.scale;
              sb.live.push({ pos: pos.clone(), vel: new THREE.Vector3(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th)).multiplyScalar(spd), born: t, life: life * (0.7 + 0.3 * sb.rng()) }); } } } } }
      const u = age / q.life, size = Math.max(numAt(el.size == null ? 0.3 : el.size, u, 0.3) * p.scale, 0.05), c = colorAt(el.color, u, p.palette);
      opacity = Math.max(opacity, 1 - numAt(el.transparency, u, 0));
      if (q.axis) m.compose(pos, new THREE.Quaternion().setFromAxisAngle(q.axis, q.rate * age), new THREE.Vector3(size, size, size)); else { m.makeScale(size, size, size); m.setPosition(pos); }
      const im = this.meshes[i % this.meshes.length]; im.setMatrixAt(i, m); im.setColorAt(i, c);
      if (this.trails) { q.hist.push(pos.clone()); const keep = Math.max(2, Math.round((el.trail.lifetime || 0.25) * 60)); if (q.hist.length > keep) q.hist.shift(); }
      alive++;
    }
    if (this.sub) { const sb = this.sub, g2 = (sb.spec.gravity == null ? 40 : sb.spec.gravity) * p.scale, sz = (sb.spec.size == null ? 0.15 : sb.spec.size) * p.scale, mm = new THREE.Matrix4();
      sb.live = sb.live.filter((s2) => t - s2.born <= s2.life);
      for (const s2 of sb.live) { s2.vel.y -= g2 * dt; s2.pos.addScaledVector(s2.vel, dt); }
      for (let i = 0; i < sb.cap; i++) { const s2 = sb.live[i]; if (s2) { const k2 = Math.max(0.001, sz * (1 - (t - s2.born) / s2.life)); mm.makeScale(k2, k2, k2); mm.setPosition(s2.pos); } else mm.makeScale(0, 0, 0); sb.mesh.setMatrixAt(i, mm); }
      sb.mesh.instanceMatrix.needsUpdate = true; alive += sb.live.length; }
    this.mat.opacity = opacity; for (const im of this.meshes) { im.visible = true; im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true; }
    if (this.trails) {
      for (const l of this.trails) { this.p.scene.remove(l); l.geometry.dispose(); } this.trails = [];
      for (const q of this.q) if (q.pos && !q.dead && q.hist.length > 1) { const g = new THREE.BufferGeometry().setFromPoints(q.hist); const l = new THREE.Line(g, this.trailMat); this.p.scene.add(l); this.trails.push(l); }
    }
    this.alive = alive; return alive;
  }
  dispose() { if (this.sub) { this.p.scene.remove(this.sub.mesh); this.sub.mesh.geometry.dispose(); this.sub.mesh.material.dispose(); } for (const im of this.meshes) { this.p.scene.remove(im); im.geometry.dispose(); } this.mat.dispose(); if (this.trails) for (const l of this.trails) { this.p.scene.remove(l); l.geometry.dispose(); } }
}
// lens: the camera's marks on a huge hit, as full-screen images (VfxStage builders.lens: ImageLabels): vignette,
// aberration (lens_fringe red + cyan at two sizes), dirt (tinted by color), zoom (radial streaks rushing in)
class LensLayer {
  constructor(player, el) { this.p = player; this.el = el; }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life;
    if (t < at || u > 1) return 0;
    const k = p.falloff(el.radius), add = (key, alpha, tint, scale, z, rot, offset) => { const tex = texture(p.bundle, key); if (tex) p.lensOverlays.push({ tex, alpha: Math.max(0, Math.min(1, alpha * k)), tint, scale, z, rot: rot || 0, offset: offset || [0, 0] }); };
    const white = new THREE.Color(1, 1, 1);
    if (el.zoom != null) add("lens_zoom", numAt(el.zoom, u, 0), el.zoomColor ? colorAt(el.zoomColor, u, p.palette) : white, 1.25 - 0.25 * u, 1);
    if (el.aberration != null) { const ab = Math.max(0, Math.min(1, numAt(el.aberration, u, 0))); add("lens_fringe", ab, new THREE.Color(1, 50 / 255, 40 / 255), 1 + 0.03 * ab, 2); add("lens_fringe", ab, new THREE.Color(40 / 255, 210 / 255, 1), 1 - 0.015 * ab, 2); }
    if (el.dirt != null) add(el.dirtTexture || "lens_dirt", numAt(el.dirt, u, 0), colorAt(el.color || [255, 240, 220], u, p.palette), 1, 3);
    if (el.vignette != null) add("lens_vignette", numAt(el.vignette, u, 0), white, 1, 4);
    // STREAKS (research 2026-10-23: directional speed lines / motion streaks): parallel lines across the screen at
    // `streakAngle` degrees (0 = level, counter-clockwise), sliding along it at `streakSpeed` screen widths a second;
    // drawn oversized (1.6) so a turned overlay never shows its edge. VfxStage: a rotated ImageLabel, same numbers
    if (el.streaks != null) { const a = (el.streakAngle || 0) * DEG, A = p.canvas.width / p.canvas.height, side = Math.sqrt(A * A + 1) * 1.02;
      // streakSpeed screen widths a second -> the texture's u (the square spans `side` x the half-width; it shows half the sheet)
      const uOff = ((((el.streakSpeed == null ? 1.5 : el.streakSpeed) * (t - at) * A) / side) * 0.5) % 0.5;
      add("lens_streaks", numAt(el.streaks, u, 0), el.streakColor ? colorAt(el.streakColor, u, p.palette) : white, 1, 0.5, a, [0, 0]);
      const o = p.lensOverlays[p.lensOverlays.length - 1]; if (o && o.tex && o.z === 0.5) { o.square = true; o.uvOff = uOff; } }
    // FLARE: the lens answering a light at the layer's `point` (VfxStage: the same marks, as ImageLabels) - nothing
    // when the point is behind the camera
    // (the light is put on the screen in drawLens, with the camera THIS frame is drawn through: here the camera is
    // still last frame's, and a shake or a fast turn would slide the glow off its light)
    if (el.flare && typeof el.flare === "object") p.lensFlares.push({ f: el.flare, at: new THREE.Vector3().setFromMatrixPosition(p.frameAt(el.point, el.aim, el.rotate)), s: Math.max(0, Math.min(1, numAt(el.flare.strength, u, 1) * k)) });
    return 0;
  }
  dispose() {}
}
// the ROCK RING (src/kit/VfxRockRing.luau, copied here number for number - kit/test/spec/vfxrockring.spec.luau runs both in
// node): a crater on a PART floor lays the rock_ring mark in the floor's colour and throws up a ring of chunks of the floor
function rockRingMul32(a, b) { const lo = b % 65536, hi = (b - lo) / 65536; return ((a * hi) % 4294967296 * 65536 + a * lo) % 4294967296; }
function rockRingHash(i, k, seed) {
  let x = (i * 73856093 + k * 19349663 + seed * 83492791) % 4294967296;
  x = (x ^ (x >>> 16)) >>> 0; x = rockRingMul32(x, 0x45d9f3b);
  x = (x ^ (x >>> 16)) >>> 0; x = rockRingMul32(x, 0x45d9f3b);
  x = (x ^ (x >>> 16)) >>> 0;
  return x / 4294967296;
}
function rockRingPlan(radius, seed, count) {
  const n = (typeof count === "number" && count === count) ? Math.min(Math.max(Math.floor(count), 0), 32) : Math.min(Math.max(Math.floor(radius * 1.2 + 0.5), 6), 18);
  const out = [];
  for (let i = 1; i <= n; i++) {
    const h = (k) => rockRingHash(i, k, seed), size = radius * (0.2 + 0.18 * h(3));
    out.push({ angle: (i - 0.5 + 0.6 * (h(1) - 0.5)) / n * 2 * Math.PI, distance: radius * (0.92 + 0.2 * h(2)),
      size: [size * (0.8 + 0.5 * h(4)), size * (0.55 + 0.55 * h(5)), size * (0.7 + 0.5 * h(6))], tilt: (20 + 25 * h(7)) * Math.PI / 180, yaw: 2 * Math.PI * h(8) });
  }
  return out;
}
function rockRingRise(t, life) {
  if (t <= 0 || life <= 0 || t >= life) return 0;
  const up = Math.min(1, t / 0.08), s = 1.70158, u = up - 1, burst = 1 + (s + 1) * u * u * u + s * u * u, from = life * 0.75;
  return t <= from ? burst : burst * (1 - (t - from) / (life - from));
}
function rockRingFade(t, life) { if (life <= 0 || t >= life) return 1; const from = life * 0.75; return t <= from ? 0 : (t - from) / (life - from); }
// crater: the game carves terrain (VfxStage builders.crater) and restores it after `life`; the player shows the hole as a
// dark sunken disc with a lighter torn rim on its floor. On a PART floor (a scene file's plate, G2) the game lays the
// rock ring instead, and so does the player (the same plan, the rock_ring mark, chunks in the floor's colour)
class CraterLayer {
  constructor(player, el) {
    this.p = player; this.el = el;
    if (player.partFloor) { this.buildRing(player, el); return; }
    const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
    const rg = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    rg.addColorStop(0, "rgba(18,14,12,0.95)"); rg.addColorStop(0.62, "rgba(34,27,22,0.9)"); rg.addColorStop(0.78, "rgba(120,104,86,0.85)"); rg.addColorStop(0.9, "rgba(70,60,50,0.5)"); rg.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = rg; g.fillRect(0, 0, 128, 128);
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    this.mesh = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshLambertMaterial({ map: tex, transparent: true, depthWrite: false }));
    this.mesh.rotation.x = -Math.PI / 2; this.mesh.visible = false; this.mesh.renderOrder = 1; player.scene.add(this.mesh);
  }
  buildRing(player, el) {
    const seed = el.seed || 1, floor = player.partFloor;
    this.ring = new THREE.Group(); this.ring.visible = false; player.scene.add(this.ring);
    this.markMat = new THREE.MeshLambertMaterial({ map: texture(player.bundle, el.texture || "rock_ring"), color: floor.clone(), transparent: true, depthWrite: false });
    this.mark = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.markMat); this.mark.rotation.x = -Math.PI / 2; this.mark.renderOrder = 1; this.ring.add(this.mark);
    this.chunks = []; this.planned = null; this.seed = seed;
  }
  layRing(r) { // the game's chunks at their rest frame (VfxStage layRing: frame = fromMatrix(hit, side, up), flat floor: side +Z)
    const p = this.p, seed = this.seed, frame = new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 1, 0), new THREE.Vector3(-1, 0, 0));
    rockRingPlan(r, seed, this.el.rocks).forEach((rock, idx) => {
      const out = new THREE.Vector3(Math.cos(rock.angle), 0, Math.sin(rock.angle));
      const rest = frame.clone().multiply(new THREE.Matrix4().makeTranslation(out.x * rock.distance, 0, out.z * rock.distance))
        .multiply(new THREE.Matrix4().makeRotationAxis(new THREE.Vector3(-out.z, 0, out.x).normalize(), -rock.tilt))
        .multiply(new THREE.Matrix4().makeRotationY(rock.yaw));
      const m = new THREE.Mesh(new THREE.BoxGeometry(rock.size[0], rock.size[1], rock.size[2]),
        new THREE.MeshLambertMaterial({ color: p.partFloor.clone().lerp(new THREE.Color(0, 0, 0), 0.06 + 0.12 * rockRingHash(idx + 1, 9, seed)) }));
      m.matrixAutoUpdate = false; this.ring.add(m); this.chunks.push({ mesh: m, rest, height: rock.size[1] });
    });
    this.planned = r;
  }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3);
    if (this.ring) {
      const alive = t >= at && t <= at + life; this.ring.visible = alive; if (!alive) return 0;
      const pos = p.worldPoint(el.point || [0, 0, 0]), r = (el.radius || 6) * p.scale;
      if (this.planned !== r) { for (const c of this.chunks) { this.ring.remove(c.mesh); c.mesh.geometry.dispose(); c.mesh.material.dispose(); } this.chunks = []; this.layRing(r); }
      this.ring.position.set(pos.x, 0.02, pos.z);
      const w = r / 0.32; this.mark.scale.set(w, w, 1); this.mark.position.y = 0.03;
      const lt = t - at, up = rockRingRise(lt, life);
      for (const c of this.chunks) c.mesh.matrix.copy(c.rest).multiply(new THREE.Matrix4().makeTranslation(0, c.height * (up * 0.85 - 0.5), 0));
      this.markMat.opacity = 1 - rockRingFade(lt, life);
      return 0;
    }
    const alive = t >= at && t <= at + life; this.mesh.visible = alive; if (!alive) return 0;
    const pos = p.worldPoint(el.point || [0, 0, 0]); const r = (el.radius || 6) * p.scale * 1.15;
    this.mesh.position.set(pos.x, 0.05, pos.z); this.mesh.scale.set(r, r, 1);
    return 0;
  }
  dispose() {
    if (this.ring) {
      for (const c of this.chunks) { c.mesh.geometry.dispose(); c.mesh.material.dispose(); }
      this.mark.geometry.dispose(); this.markMat.dispose(); this.p.scene.remove(this.ring); return;
    }
    this.p.scene.remove(this.mesh); this.mesh.geometry.dispose(); this.mesh.material.dispose();
  }
}
// world: the whole scene reacts (exposure, fog / atmosphere, sky, sun, ambient, sun rays, depth of field). The game
// drives Lighting / Atmosphere / SunRaysEffect / DepthOfFieldEffect (VfxStage builders.world); here the same curves move
// the arena's fog, sky dome, hemisphere + sun lights and the post pass. Several world layers add up.
class WorldLayer {
  constructor(player, el) { this.p = player; this.el = el; }
  update(t) {
    const el = this.el, p = this.p, at = el.at || 0, life = Math.max(el.life || 1, 1e-3), u = (t - at) / life;
    if (t < at || u > 1) return 0;
    const k = p.falloff(el.radius), w = p.world;
    w.exposure += numAt(el.exposure, u, 0) * k;
    w.fog *= 1 + (numAt(el.fog, u, 1) - 1) * k;
    if (el.fogColor != null) { w.fogColor = colorAt(el.fogColor, u, p.palette); w.fogMix = Math.max(w.fogMix, numAt(el.fogAmount, u, 1) * k); }
    if (el.sky != null) { w.sky = colorAt(el.sky, u, p.palette); w.skyMix = Math.max(w.skyMix, numAt(el.skyAmount, u, 1) * k); }
    w.sun *= 1 + (numAt(el.sun, u, 1) - 1) * k;
    w.ambient *= 1 + (numAt(el.ambient, u, 1) - 1) * k;
    w.rays += numAt(el.sunRays, u, 0) * k;
    w.dof += numAt(el.dof, u, 0) * k;
    // the game's DepthOfFieldEffect: FocusDistance = focus x scale, else the camera's distance to the effect (VfxStage)
    if (el.dof != null) w.dofFocus = el.focus != null ? el.focus * p.scale : p.camera.position.length();
    return 0;
  }
  dispose() {}
}
const KINDS = { sprite: SpriteLayer, beam: BeamLayer, mesh: MeshLayer, decal: DecalLayer, light: LightLayer, debris: DebrisLayer, screen: ScreenLayer, impact: ImpactLayer, shake: ShakeLayer, fov: FovLayer, sound: SoundLayer, glow: GlowLayer, trail: TrailLayer, highlight: HighlightLayer, world: WorldLayer, crater: CraterLayer, lens: LensLayer, swarm: SwarmLayer };

// ---------------------------------------------------------------- the stage: scene, actor, camera views, post, metrics
// DETAIL TIERS (src/kit/VfxBudget.luau: the same rule; kit/test/python/test_vfx_tiers.py runs both on every preset): a
// layer plays at a detail level when its tier (its own, or the kit's rule for it) is at or under the level, and emits
// the share of its count its tierCount gives the level. The page plays a level with ?detail=Low | Medium | High
// (lune run kit vfx play <name> --detail Low); with none, everything plays as written.
const TIER_RANK = { Low: 1, Medium: 2, High: 3 };
const TIER_CORE = { sound: 1, shake: 1, screen: 1, fov: 1, impact: 1, world: 1, lens: 1, highlight: 1, glow: 1, crater: 1, decal: 1, beam: 1, trail: 1 };
const TIER_EMITS = { sprite: 1, swarm: 1, debris: 1 };
function tierAmount(v) { return typeof v === "number" ? v : (Array.isArray(v) && typeof v[0] === "number" && typeof v[1] === "number" ? Math.max(v[0], v[1]) : 0); }
function tierSize(scale) {
  if (typeof scale === "number") return Math.abs(scale);
  let most = 0;
  if (scale && typeof scale === "object" && !Array.isArray(scale) && (scale.from != null || scale.to != null)) { // an ease written out: { from, to, ease, keys }
    for (const v of [scale.from, scale.to]) { if (typeof v === "number") most = Math.max(most, Math.abs(v)); else if (Array.isArray(v)) for (const x of v) if (typeof x === "number") most = Math.max(most, Math.abs(x)); }
    return most > 0 ? most : 1;
  }
  if (!Array.isArray(scale)) return 1;
  for (const v of scale) {
    if (typeof v === "number") most = Math.max(most, Math.abs(v));
    else if (Array.isArray(v)) {
      const inner = v[1];
      if (typeof inner === "number") most = Math.max(most, Math.abs(inner));
      else if (Array.isArray(inner)) { for (const x of inner) if (typeof x === "number") most = Math.max(most, Math.abs(x)); }
      else for (const x of v) if (typeof x === "number") most = Math.max(most, Math.abs(x));
    }
  }
  return most > 0 ? most : 1;
}
function tierMoment(el) { const at = el.at; if (typeof at === "string") return at; if (typeof at !== "number" || at !== at) return "0"; return String(Math.floor(at * 10 + 0.5)); }
function tierLeast(v, d) {
  if (typeof v === "number") return v;
  if (!Array.isArray(v)) return d;
  let least = null;
  for (const k of v) { const x = Array.isArray(k) ? k[1] : k; if (typeof x === "number" && (least === null || x < least)) least = x; }
  return least === null ? d : least;
}
function tierMost(v, d) {
  if (typeof v === "number") return v;
  if (!Array.isArray(v)) return d;
  let most = null;
  for (const k of v) { const x = Array.isArray(k) ? k[1] : k; if (typeof x === "number" && (most === null || x > most)) most = x; }
  return most === null ? d : most;
}
function tierVec(v) {
  if (!Array.isArray(v)) return "";
  const out = [];
  for (let i = 0; i < 3; i++) {
    const x = v[i];
    let n = typeof x === "number" && x === x ? Math.floor(x * 100 + 0.5) : 0;
    n = Math.min(Math.max(n, -1e9), 1e9);
    if (n === 0) n = 0;
    out.push(String(n));
  }
  return out.join(",");
}
function tierElement(el) {
  const seq = el.params && typeof el.params === "object" && typeof el.params.seq === "string" ? el.params.seq : "";
  return [tierMoment(el), typeof el.shape === "string" ? el.shape : "", tierVec(el.point), tierVec(el.aim), seq].join("|");
}
export function autoTiers(layers) { // -> { index (0-based): { tier?, tierCount? } } for the layers that say none of their own
  const plan = {};
  if (!Array.isArray(layers)) return plan;
  const lights = {}, lightOrder = [], elements = {}, order = [];
  layers.forEach((el, i) => {
    if (!el || typeof el !== "object" || TIER_CORE[el.kind]) return;
    const own = el.tier != null || el.tierCount != null || el.critical === true;
    if (TIER_EMITS[el.kind]) {
      if (own) return;
      const n = Math.max(tierAmount(el.count), tierAmount(el.rate));
      if (n >= 6) plan[i] = { tierCount: { Low: 0.4, Medium: 0.7 } }; else if (n >= 3) plan[i] = { tierCount: { Low: 0.6 } };
    } else if (el.kind === "light") {
      const m = tierMoment(el); if (!lights[m]) { lights[m] = []; lightOrder.push(m); }
      lights[m].push({ i, own, solid: 0, much: tierMost(el.range, 0) * tierMost(el.brightness, 0) });
    } else if (el.kind === "mesh") {
      const key = tierElement(el); if (!elements[key]) { elements[key] = []; order.push(key); }
      const life = typeof el.life === "number" && el.life > 0 ? el.life : 1;
      elements[key].push({ i, own, solid: 1 - Math.min(Math.max(tierLeast(el.transparency, 0), 0), 1), much: life * tierSize(el.scale) });
    }
  });
  const ranked = (group) => group.sort((a, b) => (a.solid !== b.solid ? b.solid - a.solid : a.much !== b.much ? b.much - a.much : a.i - b.i));
  for (const m of lightOrder) ranked(lights[m]).forEach((g, r) => { if (r + 1 > 1 && !g.own) plan[g.i] = { tier: "Medium" }; });
  for (const key of order) {
    const group = ranked(elements[key]);
    const n = group.length, core = Math.max(1, Math.floor(n * 0.4 + 0.5)), mid = Math.max(core, Math.ceil(n * 0.75));
    group.forEach((g, r) => { if (g.own) return; if (r + 1 > mid) plan[g.i] = { tier: "High" }; else if (r + 1 > core) plan[g.i] = { tier: "Medium" }; });
  }
  return plan;
}
function tierScaled(v, f) {
  if (typeof v === "number") return v <= 0 ? v : Math.max(1, Math.floor(v * f + 0.5));
  if (Array.isArray(v) && v.length === 2 && typeof v[0] === "number" && typeof v[1] === "number") return [Math.max(1, Math.floor(v[0] * f + 0.5)), Math.max(1, Math.floor(v[1] * f + 0.5))];
  return v;
}
export function layerAtLevel(el, level, given) { // the layer as a level plays it: null when dropped, a copy when its emission is cut
  if (!el || typeof el !== "object") return el;
  const have = TIER_RANK[level];
  const tier = el.tier != null ? el.tier : (given ? given.tier : undefined), share = el.tierCount != null ? el.tierCount : (given ? given.tierCount : undefined);
  if (have && TIER_RANK[tier] && have < TIER_RANK[tier]) return null;
  let f = 1;
  if (have && share && typeof share === "object" && typeof share[level] === "number" && share[level] === share[level]) f = Math.min(Math.max(share[level], 0), 1);
  if (f >= 1) return el;
  const c = { ...el, count: tierScaled(el.count, f), rate: tierScaled(el.rate, f) };
  if (el.count === undefined) delete c.count;
  if (el.rate === undefined) delete c.rate;
  if (el.twin && typeof el.twin === "object" && el.twin.count != null) c.twin = { ...el.twin, count: tierScaled(el.twin.count, f) };
  return c;
}
// (end of the tier rule)

// WHAT THIS PREVIEW IS NOT (the owner's limitations file, F-R05): a layer the player shows otherwise than the game
// does, or that neither can show truly, says so beside its name - footage from here is not proof of those things.
// -> the notes of one layer, in plain words (none: [])
export function previewNotes(el) {
  const notes = [];
  if (!el || typeof el !== "object") return notes;
  if (el.kind === "debris") notes.push(el.pieces && el.rest === true
    ? "pieces land on ONE flat floor at the effect's origin (the game's rule is the same): no walls, slopes or moving floors, they do not meet in the air - not proof of a collision"
    : "chunks bounce on ONE flat floor at the effect's origin: no walls, slopes or moving floors - not proof of a collision");
  if (el.kind === "mesh" && el.haze != null) notes.push("haze is drawn PLAIN here: the game bends the picture behind it (Glass), on desktop at high graphics only");
  if (el.kind === "mesh" && el.erode != null) notes.push("erode shows HERE only: the game does not show a mesh breaking up");
  if (el.kind === "mesh" && el.shape === "seq" && el.pivot === "base") notes.push('pivot "base" on a mesh sequence is another place in the game: use "origin"');
  if (el.kind === "mesh" && el.shape === "seq" && el.pivot !== "origin" && el.pivot !== "base" && el.spin != null) notes.push("a spinning mesh sequence with no pivot turns about its point here and about its first frame's middle in the game");
  return notes;
}
// (end of previewNotes)

export class Player {
  constructor(canvas, bundle, opts = {}) {
    // ?res=2: render (and record) at 2x the 1280x720 stage, 3x at most - the owner, 2026-10-19: "make the vfx higher res"
    // (the stage has no antialiasing; a 2x frame resolves the edges). Opt-in: without it nothing changes
    if (Q.res && +Q.res > 1) { const k = Math.min(3, +Q.res); canvas.width = Math.round(1280 * k); canvas.height = Math.round(720 * k); }
    this.canvas = canvas; this.bundle = bundle; this.preset = bundle.preset; this.palette = this.preset.palette || {}; this.points = this.preset.points || {};
    this.scale = opts.scale || 1; this.seed = opts.seed || 7; this.muteSound = !!opts.muteSound;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true, alpha: false });
    this.renderer.setPixelRatio(1); this.renderer.outputColorSpace = THREE.SRGBColorSpace; this.renderer.toneMapping = THREE.NoToneMapping;
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x07081a);
    this.camera = new THREE.PerspectiveCamera(70, 16 / 9, 0.3, 2000);
    this.origin = new THREE.Vector3(0, 0, 0); this.originM = new THREE.Matrix4();
    this.views = bundle.views || {};
    this.calFrom = applyCalibration(bundle.calibration, ((this.preset || {}).booth || {}).sky || "night");
    this.buildArena(); this.buildActor();
    this.time = 0; this.timeScale = 1; this.frozen = false; this.holdUntil = null; this.finished = false;
    this.muted = new Set(opts.mute || []);
    this.layers = []; this.feel = { shake: 0, fov: 0, kickX: 0, kickY: 0 }; this.post = this.freshPost(); this.world = this.freshWorld();
    this.view = opts.view || "hero";
    // sky: the judging sky this play was lit by (kit vfx play --sky / booth.sky): calibrate.py --sky refuses a recording
    // made under another
    this.metrics = { frames: [], view: this.view, cal: { ...CAL }, cal_from: this.calFrom, scene: this.sceneInfo || null, sky: this.skyName };
    this.buildLayers();
    this.setupPost();
    this.noise = mulberry(99);
  }
  applyWorld() { // the scene's own light, moved by this frame's world layers (none = the base scene, exactly)
    const e = this.env, w = this.world; if (!e || !w) return;
    const ex = Math.pow(2, w.exposure);
    e.fog.density = e.density * w.fog;
    e.fog.color.copy(e.fogColor); if (w.fogColor) e.fog.color.lerp(w.fogColor, Math.min(w.fogMix, 1));
    e.hemi.intensity = e.hemiI * w.ambient * ex; e.sun.intensity = e.sunI * w.sun * ex;
    const u = e.skyMat.uniforms; u.zenith.value.copy(e.zenith); u.horizon.value.copy(e.horizon);
    if (w.sky) { u.horizon.value.lerp(w.sky, Math.min(w.skyMix, 1)); u.zenith.value.lerp(w.sky, Math.min(w.skyMix, 1) * 0.6); }
    if (w.fogColor) u.horizon.value.lerp(w.fogColor, Math.min(w.fogMix, 1) * 0.5);
    if (e.background && this.scene.background) { this.scene.background.copy(u.horizon.value); }
    this.post.brightness += w.exposure * 0.18; // exposure also lifts what lights cannot reach (emissive, sprites)
    this.post.bloom += w.rays * 1.4; // sun rays: the bright parts bloom outward
    // depth of field (R6 2026-10-23): drawn from the depth buffer in the final pass, the far field only, like the game's
    // DepthOfFieldEffect (FarIntensity = dof, FocusDistance, InFocusRadius 30) - it used to blur the whole frame
  }
  freshWorld() { return { exposure: 0, fog: 1, fogColor: null, fogMix: 0, sky: null, skyMix: 0, sun: 1, ambient: 1, rays: 0, dof: 0, dofFocus: 30 }; }
  freshPost() { return { brightness: 0, contrast: 0, saturation: 0, tint: new THREE.Color(1, 1, 1), bloom: 0, blur: 0 }; }
  buildArena() {
    const s = this.scene;
    // booth.sky: the light an effect is judged under - night (the default arena), day (a stadium, a festival),
    // overcast (flat grey light: realism has nowhere to hide), sunset (low warm sun, long contrast). Realism cannot be
    // judged in one night arena (board/plans/archive/aaa-vfx-research.md)
    const skyName = ((this.preset || {}).booth || {}).sky || "night", K = SKIES[skyName] || SKIES.night;
    const day = skyName !== "night"; this.day = day; this.skyName = skyName;
    this.wind = ((this.preset || {}).booth || {}).wind || [6, 0, 2]; // what a `wind: true` sprite drifts with here (the game: Workspace.GlobalWind)
    s.fog = new THREE.FogExp2(K.fog, K.density);
    if (K.background != null) s.background = new THREE.Color(K.background);
    // calibrated 2026-10-10 against the Roblox booth (cine view): base 16 / charge 23 / hit 65 / tail 29 mean brightness
    const hemi = new THREE.HemisphereLight(K.hemi[0], K.hemi[1], K.hemi[2]); s.add(hemi);
    const sun = new THREE.DirectionalLight(K.sun[0], K.sun[1]); sun.position.set(K.sunPos[0], K.sunPos[1], K.sunPos[2]); s.add(sun);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(900, 900, 1, 1), new THREE.MeshLambertMaterial({ color: K.floor })); floor.rotation.x = -Math.PI / 2; floor.position.set(0, 0, -200); s.add(floor);
    const rng = mulberry(7), rock = new THREE.MeshLambertMaterial({ color: 0x76685c }), lime = new THREE.MeshLambertMaterial({ color: 0xb0a28c });
    // rocks never sit in front of a camera: skip any within 40 studs of a view position / path key (the booth's
    // Roblox arena has nothing there either)
    const camPts = []; for (const v of Object.values(this.views || {})) { if (v.pos) camPts.push(v3(v.pos)); for (const k of v.path || []) if (k.pos) camPts.push(v3(k.pos)); }
    // booth.scene "bare": the effect brings its own world (no rocks, posts or wall); a scene FILE (bundle.scene, G2: the
    // 2-fighter arena, kit/vfx/scenes/g2.json) replaces the down-range set with its own (buildScene)
    const bare = ((this.preset || {}).booth || {}).scene === "bare" || !!(this.bundle && this.bundle.scene);
    if (!bare) for (let i = 1; i <= 26; i++) { const z = -(30 + rng() * 300), x = (26 + rng() * 44) * (i % 2 === 0 ? 1 : -1), sz = 3 + rng() * 6; const bx = rng() * 0.6 - 0.3, by = rng() * 6, bz = rng() * 0.6 - 0.3; if (camPts.some((c) => c.distanceTo(new THREE.Vector3(x, sz * 0.3, z)) < 40)) continue; const m = new THREE.Mesh(new THREE.BoxGeometry(sz, sz * (0.5 + rng() * 0.7), sz * (0.7 + rng() * 0.6)), rock); m.position.set(x, sz * 0.3, z); m.rotation.set(bx, by, bz); s.add(m); }
    if (!bare) for (let i = 1; i <= 6; i++) { const z = -70 - i * 38; for (const side of [-1, 1]) { const h = 26 + i * 2; const m = new THREE.Mesh(new THREE.BoxGeometry(5, h, 5), lime); m.position.set(side * (34 + i * 3), h / 2, z); s.add(m); } }
    const wall = new THREE.Mesh(new THREE.BoxGeometry(70, 30, 8), new THREE.MeshLambertMaterial({ color: 0x8c7e6e })); wall.position.set(0, 15, -300); if (!bare) s.add(wall);
    // sky: a gradient dome (zenith -> horizon haze -> below) instead of a flat colour; the horizon band sits where
    // the booth's Roblox sky meets its fog
    const skyMat = new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, fog: false,
      uniforms: { zenith: { value: new THREE.Color(K.zenith) }, horizon: { value: new THREE.Color(K.horizon) }, ground: { value: new THREE.Color(K.ground) } },
      vertexShader: "varying vec3 vW; void main(){ vW = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: "uniform vec3 zenith; uniform vec3 horizon; uniform vec3 ground; varying vec3 vW; void main(){ float y = normalize(vW).y; vec3 c = y > 0.0 ? mix(horizon, zenith, pow(min(y * 1.6, 1.0), 0.55)) : mix(horizon, ground, min(-y * 6.0, 1.0)); gl_FragColor = vec4(c, 1.0); }" });
    const sky = new THREE.Mesh(new THREE.SphereGeometry(900, 24, 12), skyMat); s.add(sky);
    // what a `world` layer moves (WorldLayer -> applyWorld): the base values, so every frame starts from the scene's own
    this.env = { fog: s.fog, density: K.density, fogColor: new THREE.Color(K.fog), hemi, hemiI: K.hemi[2], sun, sunI: K.sun[1], skyMat,
      zenith: new THREE.Color(K.zenith), horizon: new THREE.Color(K.horizon), ground: new THREE.Color(K.ground == null ? 0x302820 : K.ground), background: s.background ? s.background.clone() : null };
    // scale references: a 4-stud grid on the ground (faint), a 10-stud ring and the forward axis at the origin
    const gridMat = new THREE.LineBasicMaterial({ color: 0x5a5146, transparent: true, opacity: 0.1, fog: true });
    const gp = []; for (let i = -40; i <= 40; i++) { const x = i * 4; gp.push(x, 0.02, 60, x, 0.02, -340); gp.push(-160, 0.02, -x - 140, 160, 0.02, -x - 140); }
    const gridGeo = new THREE.BufferGeometry(); gridGeo.setAttribute("position", new THREE.Float32BufferAttribute(gp, 3)); s.add(new THREE.LineSegments(gridGeo, gridMat));
    const ringPts = []; for (let i = 0; i <= 64; i++) { const a = (i / 64) * Math.PI * 2; ringPts.push(Math.cos(a) * 10, 0.03, Math.sin(a) * 10); }
    const ringGeo = new THREE.BufferGeometry(); ringGeo.setAttribute("position", new THREE.Float32BufferAttribute(ringPts, 3));
    s.add(new THREE.Line(ringGeo, new THREE.LineBasicMaterial({ color: 0x8a7a5c, transparent: true, opacity: 0.5 })));
    const axisGeo = new THREE.BufferGeometry(); axisGeo.setAttribute("position", new THREE.Float32BufferAttribute([0, 0.03, 0, 0, 0.03, -20], 3));
    s.add(new THREE.Line(axisGeo, new THREE.LineBasicMaterial({ color: 0x8a7a5c, transparent: true, opacity: 0.5 })));
    // a contact shadow under the actor (the booth's rig casts one)
    const shadow = new THREE.Mesh(new THREE.CircleGeometry(1.6, 24), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.45, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.set(0, 0.04, 0); if ((((this.preset || {}).booth || {}).motion || {}).actor !== false) s.add(shadow); // no actor, no actor's shadow (it sat under a nuke's stem)
    const moon = new THREE.Mesh(new THREE.SphereGeometry(10, 16, 12), new THREE.MeshBasicMaterial({ color: 0x8c8c9c, fog: false })); moon.position.set(-250, 160, -500); if (!day) s.add(moon);
    this.victim = null; this.sceneAnchors = {};
    if (this.bundle && this.bundle.scene) this.buildScene(this.bundle.scene);
  }
  // G2, THE 2-FIGHTER SCENE (LIMITATIONS_FIXES_V4 3.4 step 1: the 24-stud arena the player is calibrated in): the
  // scene file's floor plate + curb and its victim, an R6 of boxes (legs / arms 1 x 2 x 1, torso 2 x 2 x 1, the head)
  // facing the attacker. The attacker is the actor (buildActor) on the origin. kit/vfx/booth.luau builds the same
  // layout in Studio from the same file; kit/vfx/duel.py checks the file. "@victim" is the victim's body (highlight
  // layers), "@victim<Name>" the scene's anchors (points). Reported in the metrics (metrics.scene).
  buildScene(sc) {
    const s = this.scene, a = sc.arena || {}, size = a.size || 24, c = a.center || [0, 0, 0], curb = a.curb || {};
    const rgb = (v, d) => (Array.isArray(v) ? new THREE.Color(v[0] / 255, v[1] / 255, v[2] / 255) : new THREE.Color(d));
    const plate = new THREE.Mesh(new THREE.BoxGeometry(size, 0.2, size), new THREE.MeshLambertMaterial({ color: rgb((a.floor || {}).color, 0x767068) }));
    plate.position.set(c[0], -0.08, c[2]); s.add(plate); // its top 0.02 above the ground: the arena reads as a plate on it
    this.partFloor = plate.material.color.clone(); // a PART floor: a crater on it is the rock ring (CraterLayer), as in the game
    const ch = curb.height || 0, cw = curb.width || 0;
    if (ch > 0 && cw > 0) {
      const cm = new THREE.MeshLambertMaterial({ color: rgb(a.curbColor, 0x56504a) });
      for (const [w, d, x, z] of [[size, cw, 0, -(size - cw) / 2], [size, cw, 0, (size - cw) / 2], [cw, size - 2 * cw, -(size - cw) / 2, 0], [cw, size - 2 * cw, (size - cw) / 2, 0]]) {
        const b = new THREE.Mesh(new THREE.BoxGeometry(w, ch, d), cm); b.position.set(c[0] + x, ch / 2, c[2] + z); s.add(b);
      }
    }
    const v = (sc.fighters || []).find((f) => f.role === "victim");
    if (v) {
      const g = new THREE.Group(), col = v.colors || {};
      const limb = new THREE.MeshLambertMaterial({ color: rgb(col.body, 0x5c2a26) }), torso = new THREE.MeshLambertMaterial({ color: rgb(col.torso, 0x96928a) }), skin = new THREE.MeshLambertMaterial({ color: rgb(col.head, 0xf0d6be) });
      const box = (w, h, d, m, x, y, z) => { const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z); g.add(b); return b; };
      box(1, 2, 1, limb, -0.5, 1, 0); box(1, 2, 1, limb, 0.5, 1, 0); box(2, 2, 1, torso, 0, 3, 0); box(1, 2, 1, limb, -1.5, 3, 0); box(1, 2, 1, limb, 1.5, 3, 0); box(1.2, 1.2, 1.2, skin, 0, 4.6, 0);
      const f = v.face || [0, 0, 1]; g.rotation.y = Math.atan2(-f[0], -f[2]); // the group's forward is -Z, like the actor's
      g.position.set(v.pos[0], v.pos[1], v.pos[2]); s.add(g); g.updateMatrixWorld(true);
      const sh = new THREE.Mesh(new THREE.CircleGeometry(1.6, 24), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.45, depthWrite: false }));
      sh.rotation.x = -Math.PI / 2; sh.position.set(v.pos[0], 0.04, v.pos[2]); s.add(sh);
      this.victim = g;
    }
    for (const [k, p] of Object.entries(sc.anchors || {})) if (Array.isArray(p)) this.sceneAnchors[k] = new THREE.Vector3(p[0], p[1], p[2]);
    this.sceneInfo = { name: sc.name || "?", arena: size, fighters: (sc.fighters || []).length, victim: v ? v.pos : null };
  }
  buildActor() { // a blocky stand-in with the sword (the Studio booth has the real R15 rig); anchors blade/tip/hilt/bladeMid
    const g = new THREE.Group(); this.scene.add(g);
    const cloth = new THREE.MeshLambertMaterial({ color: 0x263a8c }), armor = new THREE.MeshLambertMaterial({ color: 0xc4c8d2 }), skin = new THREE.MeshLambertMaterial({ color: 0xf0d6be });
    const box = (w, h, d, m, x, y, z) => { const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z); g.add(b); return b; };
    box(0.9, 2, 0.9, cloth, -0.5, 1, 0); box(0.9, 2, 0.9, cloth, 0.5, 1, 0.3); box(1.9, 1.9, 1, armor, 0, 3.2, 0); const head = box(1.2, 1.2, 1.2, skin, 0, 4.75, 0); head.scale.set(1, 1, 1);
    const arms = new THREE.Group(); arms.position.set(0, 3.9, 0); g.add(arms);
    const armMat = cloth;
    const mk = (w, h, d, m, x, y, z) => { const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z); arms.add(b); return b; };
    mk(0.6, 2.2, 0.6, armMat, -0.55, 1.0, -0.15); mk(0.6, 2.2, 0.6, armMat, 0.55, 1.0, -0.15);
    mk(1.3, 0.22, 0.3, new THREE.MeshLambertMaterial({ color: 0xdcb446 }), 0, 2.75, -0.3); mk(0.22, 0.75, 0.22, new THREE.MeshLambertMaterial({ color: 0x283c96 }), 0, 2.3, -0.3);
    const blade = mk(0.34, 4.6, 0.09, new THREE.MeshLambertMaterial({ color: 0xe2e6f0, emissive: 0xffd080, emissiveIntensity: 0 }), 0, 5.15, -0.3);
    this.actor = { group: g, arms, blade };
    if (this.victim) this.actor.victim = this.victim; // "@victim": the scene's victim (a highlight layer's target)
    const m = (this.bundle.motion || {});
    if (m.actor === false) { g.visible = false; g.userData.hidden = true; } // the effect ALONE (mission 02-vfx v2): the stand-in stays only as the anchors' frame
    if (m.weapon === false) { blade.visible = false; for (const c of arms.children) if (c !== blade && c.geometry && c.geometry.parameters.height < 1) c.visible = false; }
    this.motion = { raise: m.raise || 0.6, swingAt: m.swingAt || 2.5, swingTime: m.swingTime || 0.14, rest: (m.rest == null ? 150 : m.rest) * DEG, up: (m.up || 0) * DEG, down: (m.down == null ? 105 : m.down) * DEG };
  }
  pose(t) {
    const m = this.motion; let a;
    if (t < m.raise) { const k = t / m.raise; a = m.rest + (m.up - m.rest) * (1 - (1 - k) * (1 - k)); }
    else if (t < m.swingAt) a = m.up; else { let k = Math.min(Math.max((t - m.swingAt) / m.swingTime, 0), 1); k = k * k * (3 - 2 * k); a = m.up + (m.down - m.up) * k; }
    this.actor.arms.rotation.x = -a;
  }
  anchor(name) { // world position of an actor anchor; "tip^170" = 170 studs along the blade from the tip
    const m = /^([A-Za-z0-9_]+)\^(-?[\d.]+)$/.exec(name); const along = m ? parseFloat(m[2]) * this.scale : 0; if (m) name = m[1];
    const b = this.actor.blade; const local = { blade: 0, bladeMid: 0, tip: 2.3, hilt: -2.3 }[name];
    if (local == null) { const sa = this.sceneAnchors && this.sceneAnchors[name]; return sa ? sa.clone().multiplyScalar(this.scale).add(new THREE.Vector3(0, along, 0)) : null; } // a scene's anchor (G2: @victimChest): a fixed point, "^n" n studs up
    return new THREE.Vector3(0, local + along, 0).applyMatrix4(b.matrixWorld);
  }
  localPoint(v) {
    if (Array.isArray(v)) return v3(v).multiplyScalar(this.scale);
    if (v === "target" && this.target) return this.target.clone();
    const named = this.points[v]; if (named) return v3(named).multiplyScalar(this.scale);
    return new THREE.Vector3();
  }
  worldPoint(v) {
    if (typeof v === "string" && v.startsWith("@")) { const a = this.anchor(v.slice(1)); if (a) return a; return this.origin.clone(); }
    return this.localPoint(v || [0, 0, 0]).applyMatrix4(this.originM);
  }
  frameAt(point, aim, rot) { // +Y aimed at `aim` when given
    const p = this.worldPoint(point);
    let m;
    if (aim != null) { const a = this.worldPoint(aim); if (a.distanceTo(p) > 1e-3) { const look = new THREE.Matrix4().lookAt(p, a, new THREE.Vector3(0, 1, 0)); m = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0)); m.premultiply(look); } else m = new THREE.Matrix4(); }
    else m = new THREE.Matrix4();
    if (rot) m.multiply(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(rot[0] * DEG, rot[1] * DEG, rot[2] * DEG, "XYZ")));
    m.setPosition(p);
    return m;
  }
  falloff(radius) { if (!radius) return 1; return Math.min(Math.max(1 - this.camera.position.distanceTo(this.origin) / radius, 0), 1); }
  buildLayers() {
    for (const l of this.layers) l.dispose(); this.layers = [];
    const ground = ((this.preset || {}).booth || {}).ground || "Ground"; // the surface under the effect (the game raycasts it)
    // ?detail=Low | Medium | High: the layers as that level plays them (VfxStage: the same rule) - else all of them
    const level = TIER_RANK[Q.detail] ? Q.detail : null, tiers = level ? autoTiers(this.preset.layers) : {};
    let index = -1;
    for (const raw of this.preset.layers || []) {
      index += 1;
      const el = layerAtLevel(withMaterial(raw, ground), level, tiers[index]); if (!el) continue;
      if (this.isMuted(el.name)) continue;
      const K = KINDS[el.kind]; if (K) this.layers.push(new K(this, el));
    }
  }
  isMuted(name) { if (!name) return false; for (const m of this.muted) { if (m.endsWith("*") ? name.startsWith(m.slice(0, -1)) : name === m) return true; } return false; }
  // camera ------------------------------------------------------------------------------------------------
  // orbit: the page feeds drag / wheel / pan into this.orbit (per view); a moving (path) view takes the orbit as an
  // offset around its own frame, so you can still look around a cinematic
  orbitState() { if (!this.orbits) this.orbits = {}; return this.orbits[this.view] || (this.orbits[this.view] = { yaw: 0, pitch: 0, dolly: 1, pan: new THREE.Vector3() }); }
  orbit(dYaw, dPitch) { const o = this.orbitState(); o.yaw += dYaw; o.pitch = Math.max(-1.4, Math.min(1.4, o.pitch + dPitch)); }
  dolly(k) { const o = this.orbitState(); o.dolly = Math.max(0.15, Math.min(6, o.dolly * k)); }
  pan(dx, dy) { const o = this.orbitState(); const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 1); o.pan.addScaledVector(right, dx).addScaledVector(up, dy); }
  resetOrbit() { if (this.orbits) delete this.orbits[this.view]; }
  applyOrbit(f) {
    const o = this.orbits && this.orbits[this.view]; if (!o || (o.yaw === 0 && o.pitch === 0 && o.dolly === 1 && o.pan.lengthSq() === 0)) return f;
    const look = f.look.clone().add(o.pan); const rel = f.pos.clone().sub(f.look);
    const r = rel.length() * o.dolly; const sph = new THREE.Spherical().setFromVector3(rel);
    sph.theta += o.yaw; sph.phi = Math.max(0.05, Math.min(Math.PI - 0.05, sph.phi + o.pitch)); sph.radius = r;
    return { pos: look.clone().add(new THREE.Vector3().setFromSpherical(sph)), look, fov: f.fov };
  }
  // free cam: fly anywhere (the page feeds WASD / QE / shift and mouse look into it); entering it starts from the
  // current camera so nothing jumps
  enterFree() {
    const cur = this.viewAt(this.time);
    const dir = cur.look.clone().sub(cur.pos).normalize();
    this.free = { pos: cur.pos.clone(), yaw: Math.atan2(dir.x, dir.z), pitch: Math.asin(Math.max(-1, Math.min(1, dir.y))), fov: cur.fov, speed: 40 };
    this.view = "free";
  }
  freeLook(dYaw, dPitch) { if (!this.free) return; this.free.yaw += dYaw; this.free.pitch = Math.max(-1.5, Math.min(1.5, this.free.pitch + dPitch)); }
  freeMove(keys, dt) { // keys: { w, a, s, d, q, e, fast }
    const f = this.free; if (!f) return false;
    const sp = f.speed * (keys.fast ? 3 : 1) * dt;
    const fwd = new THREE.Vector3(Math.sin(f.yaw) * Math.cos(f.pitch), Math.sin(f.pitch), Math.cos(f.yaw) * Math.cos(f.pitch));
    const right = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0)).normalize();
    let moved = false;
    if (keys.w) { f.pos.addScaledVector(fwd, sp); moved = true; } if (keys.s) { f.pos.addScaledVector(fwd, -sp); moved = true; }
    if (keys.d) { f.pos.addScaledVector(right, sp); moved = true; } if (keys.a) { f.pos.addScaledVector(right, -sp); moved = true; }
    if (keys.e) { f.pos.y += sp; moved = true; } if (keys.q) { f.pos.y -= sp; moved = true; }
    return moved;
  }
  viewAt(t) {
    if (this.view === "free" && this.free) {
      const f = this.free; const dir = new THREE.Vector3(Math.sin(f.yaw) * Math.cos(f.pitch), Math.sin(f.pitch), Math.cos(f.yaw) * Math.cos(f.pitch));
      return { pos: f.pos.clone(), look: f.pos.clone().add(dir), fov: f.fov };
    }
    const v = this.views[this.view] || this.views.hero || { pos: [-15, 5, -24], look: [0, 7, 0], fov: 66 };
    const frame = (pos, look, fov) => this.applyOrbit({ pos: v3(pos).applyMatrix4(this.originM), look: v3(look).applyMatrix4(this.originM), fov: fov || 70 });
    if (!v.path) return frame(v.pos, v.look, v.fov);
    const k = v.path; if (t <= k[0].t) return frame(k[0].pos, k[0].look, k[0].fov);
    for (let i = 0; i < k.length - 1; i++) { const a = k[i], b = k[i + 1]; if (t <= b.t) { let u = (t - a.t) / Math.max(b.t - a.t, 1e-3); u = u * u * (3 - 2 * u); return frame(v3(a.pos).lerp(v3(b.pos), u).toArray(), v3(a.look).lerp(v3(b.look), u).toArray(), (a.fov || 70) + ((b.fov || 70) - (a.fov || 70)) * u); } }
    const l = k[k.length - 1]; return frame(l.pos, l.look, l.fov);
  }
  applyCamera(t, dt) {
    const v = this.viewAt(t);
    this.camera.position.copy(v.pos); this.camera.lookAt(v.look); this.camera.fov = v.fov + this.feel.fov; this.camera.updateProjectionMatrix();
    // kick + shake turn the camera about ITS OWN axes (rotateX / rotateY = the game's camera.CFrame * CFrame.Angles(p, y, 0));
    // rotation.x / .y after lookAt are world Euler angles: from the hero / side views they went the wrong way (review 3)
    if (this.feel.kickX || this.feel.kickY) { this.camera.rotateX(this.feel.kickY * DEG); this.camera.rotateY(this.feel.kickX * DEG); } // yaw +x: the picture moves right; pitch -y: it moves up
    if (this.feel.shake > 0.001) { const s = this.feel.shake * DEG, tt = t * 22; this.camera.rotateX(this.noiseAt(tt, 0.3) * s); this.camera.rotateY(this.noiseAt(tt, 4.1) * s); this.camera.rotateZ(this.noiseAt(tt, 9.7) * s * 0.6); }
    this.camera.aspect = this.canvas.width / this.canvas.height; this.camera.updateProjectionMatrix();
  }
  noiseAt(x, y) { return Math.sin(x * 1.3 + y * 7.1) * 0.5 + Math.sin(x * 2.9 + y * 3.3) * 0.3 + Math.sin(x * 5.7 + y) * 0.2; }
  // clock --------------------------------------------------------------------------------------------------
  warpAt(t) { // preset.timewarp [[t, rate], ...]: the clock's speed at effect time t (1 outside the keys)
    const w = this.preset.timewarp; if (!Array.isArray(w) || w.length === 0) return 1;
    if (t <= w[0][0]) return w[0][0] > 0 && t < w[0][0] ? 1 : w[0][1];
    for (let i = 0; i < w.length - 1; i++) { const a = w[i], b = w[i + 1]; if (t <= b[0]) return a[1] + (b[1] - a[1]) * ((t - a[0]) / Math.max(1e-6, b[0] - a[0])); }
    return t > w[w.length - 1][0] ? 1 : w[w.length - 1][1];
  }
  step(dt) {
    if (this.finished) return;
    if (this.holdLeft > 0) { // inside a hit-stop: the world stands still, the impact frames run on the held clock (deterministic: by dt)
      this.holdLeft -= dt / (this.record ? 1 : (this.holdScale || 1));
      this.frameTime = this.time + Math.min(this.holdSpan, (this.holdLen - Math.max(0, this.holdLeft)) * this.holdSpan / this.holdLen); // span < hold: the frames linger
      this.render(0, true);
      if (this.holdLeft > 0) return;
      this.holdUntil = null; this.frameTime = null; }
    this.frameTime = null;
    let d = this.frozen ? 0 : dt * this.timeScale * this.warpAt(this.time); // timewarp: bullet time, slow silences
    let t = this.time + d;
    if (this.target != null && t >= this.target) { d = Math.max(0, this.target - this.time); t = this.target; this.target = null; this.frozen = true; }
    for (const h of this.preset.hitstop || []) { if (this.time < h.at && t >= h.at) { t = h.at; d = h.at - this.time; this.holdLen = h.hold || 0.08; this.holdSpan = Math.min(this.holdLen, h.span || this.holdLen); this.holdLeft = this.holdLen; this.holdUntil = 1;
      (this.heldWindows = this.heldWindows || []).push({ at: h.at, len: this.holdSpan }); // the frames shown on the held clock are spent: the world resumes without replaying them
      break; } }
    this.time = t;
    this.render(d, false);
    if (t >= (this.preset.duration || 5)) this.finished = true;
  }
  render(d, frozen) {
    const t = this.time;
    this.pose(t); this.actor.group.updateMatrixWorld(true);
    this.feel.shake = 0; this.feel.fov = 0; this.feel.kickX = 0; this.feel.kickY = 0; this.post = this.freshPost(); this.plate = null; this.frame = null;
    this.world = this.freshWorld(); this.lensOverlays = []; this.lensFlares = [];
    let alive = 0;
    for (const l of this.layers) alive += l.update(t, d, frozen || this.frozen) || 0;
    this.alive = alive;
    this.applyWorld();
    if (this.peek) for (const l of this.layers) if (l.el && l.el.name !== this.peek) hideLayer(l);
    this.applyCamera(t, d);
    this.draw();
  }
  // which layers are drawn near a screen point (px in canvas space): their emitter points projected, nearest first
  layersAt(px, py, radius = 70) {
    const w = this.canvas.width, h = this.canvas.height; const out = [];
    for (const l of this.layers) {
      const el = l.el; if (!el) continue;
      const kind = el.kind; let p = null;
      if (kind === "beam" || kind === "trail") { const a = this.worldPoint(el.from || el.target || [0, 0, 0]), b = this.worldPoint(el.to || [0, 1, 0]); p = a.clone().lerp(b, 0.5); }
      else if (["sprite", "light", "mesh", "decal", "debris", "sound"].includes(kind)) p = this.worldPoint(el.point || [0, 0, 0]);
      if (!p) continue;
      const live = l.live ? l.live.length > 0 : (l.mesh ? l.mesh.visible : (l.light ? l.light.visible : (l.strips ? l.strips.some((s) => s.mesh.visible) : false)));
      const v = p.clone().project(this.camera); if (v.z > 1) continue;
      const sx = (v.x + 1) / 2 * w, sy = (1 - v.y) / 2 * h; const dpx = Math.hypot(sx - px, sy - py);
      if (dpx <= radius) out.push({ name: el.name, kind, dist: Math.round(dpx), live, x: Math.round(sx), y: Math.round(sy) });
    }
    return out.sort((a, b) => (b.live - a.live) || (a.dist - b.dist));
  }
  reload(bundle) { // hot reload: a new bundle (the preset changed on disk); keep the clock, the view, the mutes
    const t = this.time, wasFrozen = this.frozen;
    this.bundle = bundle; this.preset = bundle.preset; this.palette = this.preset.palette || {}; this.points = this.preset.points || {};
    if (bundle.views) this.views = bundle.views;
    this.calFrom = applyCalibration(bundle.calibration, ((this.preset || {}).booth || {}).sky || "night");
    this.metrics.cal = { ...CAL }; this.metrics.cal_from = this.calFrom;
    for (const l of this.layers) l.dispose(); this.layers = [];
    this.seek(Math.min(t, this.preset.duration || 5)); this.frozen = wasFrozen; if (!wasFrozen) this.render(0, false);
  }
  seek(t) { // rebuild and run the clock up to t deterministically (scrubbing)
    this.time = 0; this.finished = false; this.holdUntil = null; this.holdLeft = 0; this.frameTime = null; this.heldWindows = []; this.target = null; this.frozen = false;
    this.buildLayers();
    const dt = 1 / 60; const wasMute = this.muteSound; this.muteSound = true;
    const sub = (d) => { this.time += d; this.pose(this.time); this.actor.group.updateMatrixWorld(true); this.feel.shake = 0; this.feel.fov = 0; this.feel.kickX = 0; this.feel.kickY = 0; this.post = this.freshPost(); this.world = this.freshWorld(); this.lensOverlays = []; this.lensFlares = []; for (const l of this.layers) l.update(this.time, d, false); };
    while (this.time + dt <= t) sub(dt);
    if (t - this.time > 1e-4) sub(t - this.time); // the remainder: a frame step lands on the exact frame
    this.muteSound = wasMute; this.frozen = true; this.render(0, true);
  }
  // post: bloom + grade ------------------------------------------------------------------------------------
  setupPost() {
    const r = this.renderer;
    const w = this.canvas.width, h = this.canvas.height;
    const mk = (sw, sh) => new THREE.WebGLRenderTarget(sw, sh, { type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: true, stencilBuffer: true }); // stencil: highlight rims
    // the depth of field reads the scene's depth; depth + STENCIL (the highlight rims need the stencil)
    this.rtScene = mk(w, h); { const dt = new THREE.DepthTexture(w, h); dt.format = THREE.DepthStencilFormat; dt.type = THREE.UnsignedInt248Type; this.rtScene.depthTexture = dt; }
    // rtA / rtB: the bloom blur; rtC / rtD: the screen blur + depth of field (R1, R6)
    this.rtA = mk(w >> 2, h >> 2); this.rtB = mk(w >> 2, h >> 2); this.rtC = mk(w >> 2, h >> 2); this.rtD = mk(w >> 2, h >> 2); this.rtMetrics = new THREE.WebGLRenderTarget(64, 36, { type: THREE.UnsignedByteType });
    const quad = new THREE.PlaneGeometry(2, 2); this.postScene = new THREE.Scene(); this.postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.threshMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null }, threshold: { value: 1.0 } }, vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tex; uniform float threshold; varying vec2 vUv; void main(){ vec3 c = texture2D(tex, vUv).rgb; float l = max(c.r, max(c.g, c.b)); gl_FragColor = vec4(c * smoothstep(threshold * 0.6, threshold * 1.4, l), 1.0); }" });
    this.blurMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null }, dir: { value: new THREE.Vector2(1, 0) }, px: { value: new THREE.Vector2(1 / (w >> 2), 1 / (h >> 2)) }, spread: { value: 2.0 } }, vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tex; uniform vec2 dir; uniform vec2 px; uniform float spread; varying vec2 vUv; void main(){ vec3 s = vec3(0.0); float w[5]; w[0]=0.227; w[1]=0.194; w[2]=0.121; w[3]=0.054; w[4]=0.016; s += texture2D(tex, vUv).rgb * w[0]; for (int i = 1; i < 5; i++) { vec2 o = dir * px * float(i) * spread; s += texture2D(tex, vUv + o).rgb * w[i]; s += texture2D(tex, vUv - o).rgb * w[i]; } gl_FragColor = vec4(s, 1.0); }" });
    this.finalMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null }, bloom: { value: null }, blurTex: { value: null }, blurMix: { value: 0 }, depthTex: { value: null }, camNear: { value: 0.1 }, camFar: { value: 2000 }, dofK: { value: 0 }, dofFocus: { value: 30 }, dofRadius: { value: 30 }, bloomK: { value: 0.9 }, brightness: { value: 0 }, contrast: { value: 0 }, saturation: { value: 0 }, tint: { value: new THREE.Color(1, 1, 1) } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: `uniform sampler2D tex; uniform sampler2D bloom; uniform sampler2D blurTex; uniform float blurMix; uniform sampler2D depthTex; uniform float camNear; uniform float camFar; uniform float dofK; uniform float dofFocus; uniform float dofRadius; uniform float bloomK; uniform float brightness; uniform float contrast; uniform float saturation; uniform vec3 tint; varying vec2 vUv;
        void main(){ float bm = blurMix;
          if (dofK > 0.0) { float z = texture2D(depthTex, vUv).x * 2.0 - 1.0; float zl = 2.0 * camNear * camFar / (camFar + camNear - z * (camFar - camNear));
            bm = max(bm, dofK * smoothstep(dofFocus + dofRadius, dofFocus + dofRadius + 60.0, zl)); } // the far field blurs past the in-focus range
          vec3 c = mix(texture2D(tex, vUv).rgb, texture2D(blurTex, vUv).rgb, bm) + texture2D(bloom, vUv).rgb * bloomK; c = c / (1.0 + c * 0.12); c = pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2));
          c = c * tint; float l = dot(c, vec3(0.3, 0.59, 0.11)); c = mix(vec3(l), c, 1.0 + saturation); c = (c - 0.5) * (1.0 + contrast) + 0.5 + brightness; gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0); }` });
    this.postMesh = new THREE.Mesh(quad, this.finalMat); this.postScene.add(this.postMesh);
    this.plateMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null }, alpha: { value: 1 }, uvScale: { value: new THREE.Vector2(1, 1) }, uvOff: { value: new THREE.Vector2(0, 0) } }, transparent: true, depthTest: false, depthWrite: false,
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tex; uniform float alpha; uniform vec2 uvScale; uniform vec2 uvOff; varying vec2 vUv; void main(){ vec4 c = texture2D(tex, vUv * uvScale + uvOff); gl_FragColor = vec4(pow(clamp(c.rgb, 0.0, 1.0), vec3(1.0 / 2.2)), c.a * alpha); }" });
    this.plateMesh = new THREE.Mesh(quad, this.plateMat); this.plateScene = new THREE.Scene(); this.plateScene.add(this.plateMesh);
    // lens overlays (LensLayer -> this.lensOverlays): full-screen images ALPHA-blended over the frame like Roblox
    // ImageLabels (no additive in Roblox UI), tinted, scaled about the centre
    this.lensMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null }, alpha: { value: 1 }, tint: { value: new THREE.Color(1, 1, 1) }, scale: { value: 1 }, rot: { value: 0 }, offset: { value: new THREE.Vector2() }, aspect: { value: 16 / 9 }, squareK: { value: 0 }, uvOff: { value: 0 }, stretch: { value: new THREE.Vector2(1, 1) } }, transparent: true, depthTest: false, depthWrite: false,
      // rot turns the overlay in PIXEL space (aspect-corrected, as a rotated ImageLabel); offset slides it (clip units)
      vertexShader: "uniform float scale; uniform float rot; uniform vec2 offset; uniform float aspect; uniform float squareK; uniform float uvOff; uniform vec2 stretch; varying vec2 vUv; void main(){ vUv = squareK > 0.5 ? vec2(uv.x * 0.5 + uvOff, uv.y) : uv; vec2 q = squareK > 0.5 ? position.xy * sqrt(aspect * aspect + 1.0) * 1.02 : position.xy * scale * stretch; if (squareK < 0.5) q.x *= aspect; q = vec2(cos(rot) * q.x - sin(rot) * q.y, sin(rot) * q.x + cos(rot) * q.y); q.x /= aspect; gl_Position = vec4(q + offset, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tex; uniform float alpha; uniform vec3 tint; varying vec2 vUv; void main(){ vec4 c = texture2D(tex, vUv); gl_FragColor = vec4(pow(clamp(c.rgb, 0.0, 1.0), vec3(1.0 / 2.2)) * tint, c.a * alpha); }" });
    this.lensMesh = new THREE.Mesh(quad, this.lensMat); this.lensScene = new THREE.Scene(); this.lensScene.add(this.lensMesh);
    this.inkMat = new THREE.MeshBasicMaterial({ color: 0x000000, fog: false });
    this.warmFrameShaders = true; // the frame composite compiles on first use: do it at load, not at the first hit (a visible hitch)
    this.rtFrame = new THREE.WebGLRenderTarget(this.canvas.width, this.canvas.height, { type: THREE.UnsignedByteType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter }); // the held-frame cache, allocated now
    this.frameMat = new THREE.ShaderMaterial({ uniforms: { sil: { value: null }, energy: { value: null }, lines: { value: null }, paper: { value: new THREE.Color(1, 1, 1) }, ink: { value: new THREE.Color(0, 0, 0) }, hot: { value: new THREE.Color(0, 0, 0) }, mark: { value: new THREE.Color(0, 0, 0) }, linesColor: { value: new THREE.Color(0, 0, 0) },
        hotT: { value: 0.8 }, markT: { value: 0.22 }, linesMode: { value: 0 }, linesScale: { value: 1.6 }, linesStrength: { value: 1 }, hole: { value: 0.08 }, aspect: { value: 16 / 9 }, focus: { value: new THREE.Vector2(0.5, 0.5) }, seed: { value: 0 },
        warp: { value: 1 }, grow: { value: 1 }, smear: { value: 1 }, outline: { value: 1 }, hatch: { value: 0 }, splatter: { value: 1 }, zoom: { value: 0.04 }, shake: { value: 0.008 }, flash: { value: 0 }, lineart: { value: 0 }, rim: { value: 0 }, soot: { value: 0 }, mass: { value: 0 },
        segs: { value: [new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4()] }, segW: { value: [0, 0, 0, 0] }, segN: { value: 0 }, specks: { value: Array.from({ length: 48 }, () => new THREE.Vector2()) }, speckN: { value: 0 },
        wedge: { value: 1 }, star: { value: 0 }, voidK: { value: 0 }, crackK: { value: 0 }, boltsK: { value: 0 }, speckK: { value: 1 }, smoke: { value: 0 }, abstractK: { value: 0 }, vanish: { value: new THREE.Vector2(0.5, 0.5) }, hasVanish: { value: 0 },
        textTex: { value: null }, textOn: { value: 0 }, textPos: { value: new THREE.Vector2(0.5, 0.5) }, textSize: { value: 0.5 }, textRot: { value: 0 }, textColor: { value: new THREE.Color(0, 0, 0) },
        textStretch: { value: 1 }, textSquash: { value: 1 }, textOffset: { value: 0 }, bandOn: { value: 0 }, bandLines: { value: 1 }, bandColor: { value: new THREE.Color(0, 0, 0) },
        textSplit: { value: 1 }, textGlint: { value: -1 }, textTrail: { value: 0 }, textMid: { value: 0.49 }, accentColor: { value: new THREE.Color(1, 1, 1) }, bandOffset: { value: 0 },
        coverOn: { value: 0 }, cutAngle: { value: 0 }, sliceGap: { value: 0 }, sliceSlide: { value: 0 }, cutFlash: { value: 0 }, cardPaper: { value: new THREE.Color(0, 0, 0) }, cardInk: { value: new THREE.Color(1, 1, 1) },
        rough: { value: 0 }, drips: { value: 0 }, blood: { value: new THREE.Color(0.5, 0, 0) }, spin: { value: 0 }, claws: { value: 1 }, clawSpacing: { value: 0.16 }, jag: { value: 0 }, shatter: { value: 0 }, crawl: { value: 1 }, distort: { value: 0 }, fTime: { value: 0 }, spot: { value: 0 }, reveal: { value: 1 },
        cutPts: { value: Array.from({ length: 24 }, () => new THREE.Vector2()) }, cutW: { value: new Array(24).fill(0) }, cutN: { value: 0 }, cutDir: { value: new THREE.Vector2(1, 0) },
        slashK: { value: 0 }, splitK: { value: 0 }, splitSlide: { value: 0 }, cutSmearK: { value: 0 }, flareK: { value: 0 }, selectiveK: { value: 0 } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: `uniform sampler2D sil; uniform sampler2D energy; uniform sampler2D lines; uniform vec3 paper; uniform vec3 ink; uniform vec3 hot; uniform vec3 mark; uniform vec3 linesColor;
        uniform float hotT; uniform float markT; uniform float linesMode; uniform float linesScale; uniform float linesStrength; uniform float hole; uniform float aspect; uniform vec2 focus; uniform float seed;
        uniform float warp; uniform float grow; uniform float smear; uniform float outline; uniform float hatch; uniform float splatter; uniform float zoom; uniform float shake; uniform float flash; uniform float lineart; uniform float rim; uniform float soot; uniform float mass;
        uniform vec4 segs[4]; uniform float segW[4]; uniform float segN; uniform vec2 specks[48]; uniform float speckN;
        uniform float wedge; uniform float star; uniform float voidK; uniform float crackK; uniform float boltsK; uniform float speckK; uniform float smoke; uniform float abstractK; uniform vec2 vanish; uniform float hasVanish;
        uniform sampler2D textTex; uniform float textOn; uniform vec2 textPos; uniform float textSize; uniform float textRot; uniform vec3 textColor;
        uniform float textStretch; uniform float textSquash; uniform float textOffset; uniform float bandOn; uniform float bandLines; uniform vec3 bandColor;
        uniform float textSplit; uniform float textGlint; uniform float textTrail; uniform float textMid; uniform vec3 accentColor; uniform float bandOffset;
        uniform float coverOn; uniform float cutAngle; uniform float sliceGap; uniform float sliceSlide; uniform float cutFlash; uniform vec3 cardPaper; uniform vec3 cardInk; uniform float rough; uniform float drips; uniform vec3 blood; uniform float spin; uniform float claws; uniform float clawSpacing; uniform float jag; uniform float shatter; uniform float crawl; uniform float distort; uniform float fTime; uniform float spot; uniform float reveal;
        uniform vec2 cutPts[24]; uniform float cutW[24]; uniform float cutN; uniform vec2 cutDir; uniform float slashK; uniform float splitK; uniform float splitSlide; uniform float cutSmearK; uniform float flareK; uniform float selectiveK;
        varying vec2 vUv;
        vec2 segDist(vec2 p, vec2 a, vec2 b){ vec2 ab = b - a; float t = clamp(dot(p - a, ab) / max(dot(ab, ab), 1e-6), 0.0, 1.0); return vec2(length(p - (a + ab * t)), t); }
        float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
        float vnoise(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f); float a = hash21(i), b = hash21(i + vec2(1.0, 0.0)), c = hash21(i + vec2(0.0, 1.0)), d = hash21(i + vec2(1.0, 1.0)); return mix(mix(a, b, u.x), mix(c, d, u.x), u.y); }
        float eAt(vec2 uv){ vec3 c = texture2D(energy, uv).rgb; return max(c.r, max(c.g, c.b)); }
        float sAt(vec2 uv){ return texture2D(sil, uv).r; }
        // THE CUT (impact frames v4): the slash's arc projected to the screen - cutPts carry it already extended past both
        // tips along their tangents (zero width there), so its line divides the whole frame. -> (distance, index along,
        // side +-1, the stroke's half-width there), in aspect-corrected screen units
        vec4 cutField(vec2 qw){ float best = 1e9, bi = 0.0, side = -1.0, bw = 0.0;
          for (int i = 0; i < 23; i++) { if (float(i) >= cutN - 1.0) break;
            vec2 a = vec2(cutPts[i].x * aspect, cutPts[i].y), b = vec2(cutPts[i + 1].x * aspect, cutPts[i + 1].y); vec2 sd = segDist(qw, a, b);
            if (sd.x < best) { best = sd.x; bi = float(i) + sd.y; vec2 ab = b - a; side = sign(ab.x * (qw.y - a.y) - ab.y * (qw.x - a.x)); bw = mix(cutW[i], cutW[i + 1], sd.y); } }
          return vec4(best, bi, side, bw); }
        // the full-screen name card: paper, streaks, the ghost word hatched, the name huge with a hard shadow and a split-tone face
        vec3 cardAt(vec2 p) {
          vec3 col = cardPaper;
          if (fract(p.y * 55.0 + hash21(vec2(floor(p.x * 2.5), floor(p.y * 55.0))) * 7.0) < 0.06 && hash21(vec2(floor(p.y * 55.0), floor(p.x * 4.0) + seed)) > 0.55) col = mix(cardPaper, cardInk, 0.55);
          vec2 dd = p - vec2(0.5 * aspect, 0.5); float cr = cos(textRot), sr = sin(textRot); vec2 tq = vec2(cr * dd.x - sr * dd.y, sr * dd.x + cr * dd.y);
          if (spot > 0.0) { // pull: ink speed lines converge on the word from the screen edges, the edges crushed to black
            float ang = atan(dd.y, dd.x); float K = 150.0; float slotI = floor((ang / 6.2831853 + 0.5) * K); float fs = fract((ang / 6.2831853 + 0.5) * K) - 0.5;
            float r = length(dd / vec2(1.0, 0.62)); float r0 = 0.42 + 0.22 * hash21(vec2(slotI, 7.0)); float wdt = 0.5 * clamp((r - r0) / 0.6, 0.0, 1.0) * (0.4 + hash21(vec2(slotI, 9.0)));
            if (r > r0 && abs(fs) < wdt * 0.5 && hash21(vec2(slotI, floor(fTime * 12.0))) > 0.25) col = mix(col, cardInk, 0.85 * min(1.0, spot));
            float vig = smoothstep(0.55, 1.05, length(dd / vec2(aspect * 0.5, 0.5))); col = mix(col, cardPaper, vig * min(1.0, spot)); }
          if (distort > 0.0) { // the word is alive: a heat ripple runs through it, rows glitch sideways, the whole word breathes
            tq.x += sin(tq.y * 34.0 + fTime * 46.0) * 0.006 * distort + sin(tq.y * 9.0 - fTime * 21.0) * 0.004 * distort;
            tq.y += sin(tq.x * 22.0 + fTime * 31.0) * 0.004 * distort;
            float row = floor(tq.y * 14.0 + 7.0); float tick = floor(fTime * 18.0);
            float gl = hash21(vec2(row, tick)); if (gl > 0.78) tq.x += (hash21(vec2(row, tick + 3.0)) - 0.5) * 0.11 * distort;
            tq *= 1.0 + sin(fTime * 9.0) * 0.012 * distort; }
          tq = vec2((tq.x - textOffset) / textStretch, tq.y / textSquash);
          vec2 tuv = tq / vec2(textSize * 2.0, textSize) + 0.5; vec2 tpx = vec2(0.006, 0.012) / textSize;
          tuv += (vec2(vnoise(tuv * 38.0 + seed), vnoise(tuv * 38.0 + 9.0 + seed)) - 0.5) * 0.012 * rough; // torn letter edges
          // blood: splatter flecks around the word, drips running down off the letters
          if (drips > 0.0 && tuv.x > 0.02 && tuv.x < min(0.98, reveal >= 1.0 ? 2.0 : mix(0.05, 0.95, reveal)) && tuv.y > 0.0 && tuv.y < 1.0) {
            vec2 cl = floor(tuv * vec2(90.0, 45.0)); vec2 cc = cl + vec2(hash21(cl + 3.1), hash21(cl + 7.7)); float hb = hash21(cl + 1.9);
            if (hb > 0.93 && distance(tuv * vec2(90.0, 45.0), cc) < 0.18 + 0.45 * hash21(cl + 5.3)) col = blood;
            float colx = floor(tuv.x * 110.0); float hc = hash21(vec2(colx, 4.2)); float fx = fract(tuv.x * 110.0);
            if (hc > 0.55 && abs(fx - 0.5) < 0.18 + 0.12 * hc) { float L = (0.06 + 0.3 * hash21(vec2(colx, 8.8))) * drips; float hit = 0.0;
              for (int k = 1; k <= 8; k++) { vec2 up = vec2(tuv.x, tuv.y + L * float(k) / 8.0); if (up.y < 1.0 && texture2D(textTex, up).g > 0.5) hit = 1.0; }
              if (hit > 0.5) col = blood; } }
          if (tuv.x > 0.0 && tuv.x < 1.0 && tuv.y > 0.0 && tuv.y < 1.0) {
            vec4 g0 = texture2D(textTex, tuv);
            float front = reveal >= 1.0 ? 2.0 : mix(0.05, 0.95, reveal); bool hidden = tuv.x > front; // the stamp-in: letters land left to right
            if (hidden) g0.g = 0.0;
            if (g0.r > 0.5 && g0.g < 0.5 && fract(tq.y * 160.0) < 0.5) col = mix(cardPaper, cardInk, 0.4);
            float sh = texture2D(textTex, clamp(tuv - vec2(1.2, -1.8) * tpx, 0.0, 1.0)).g;
            float ol = 0.0; for (int k = 0; k < 8; k++) { float a2 = float(k) * 0.785398; ol = max(ol, texture2D(textTex, clamp(tuv + vec2(cos(a2), sin(a2)) * tpx * 0.6, 0.0, 1.0)).g); }
            if (hidden) { sh = 0.0; ol = 0.0; }
            if (sh > 0.5) col = cardInk; if (ol > 0.5) col = cardPaper;
            if (distort > 0.0) { float echo = texture2D(textTex, clamp(tuv + vec2(0.012 * sin(fTime * 27.0) + 0.008, -0.006) * distort, 0.0, 1.0)).g; // a blood echo trailing the letters
              if (echo > 0.5 && g0.g < 0.5 && !hidden) col = blood; }
            if (g0.g > 0.5) { bool top = textSplit > 0.5 && tuv.y > textMid + 0.05 + 0.02 * sin(tuv.x * 9.0); col = top ? mix(textColor, vec3(1.0), 0.55) : textColor;
              if (!top && textGlint >= 0.0 && abs((tuv.x + tuv.y * 0.35) - textGlint) < 0.018) col = vec3(1.0);
              if (reveal < 1.0 && tuv.x > front - 0.09) col = vec3(1.0); // the letter that just landed burns white
              // dry brush: ragged horizontal gaps dragged through the strokes, blood soaking the lower edge
              float drag = fract(tuv.y * 52.0 + vnoise(vec2(tuv.x * 6.0, tuv.y * 52.0)) * 2.0);
              if (rough > 0.0 && drag < 0.11 * rough && vnoise(vec2(tuv.x * 14.0 + seed, floor(tuv.y * 52.0))) > 0.45) col = cardPaper;
              if (drips > 0.0 && texture2D(textTex, tuv - vec2(0.0, 0.035)).g < 0.5 && vnoise(vec2(tuv.x * 30.0, seed)) > 0.4) col = blood; } }
          return col;
        }
        // focus lines (shuuchuusen) drawn in polar space: K slots around the hit; groups of 8 with gaps; each line its own
        // start radius, length and weight; thin toward the centre, thick at the outer end (the ray rule); a hand wobble
        float focusLines(float ang, float d, float K, float w0, float sd, float keep) {
          float u = (ang / 6.2831853 + 0.5) * K; float i = floor(u); float fr = fract(u) - 0.5;
          float g = floor(i / 8.0);
          float present = step(1.0 - keep, hash21(vec2(g, sd))) * step(0.22, hash21(vec2(i, sd + 3.0)));
          float r0 = hole + 0.02 + 0.28 * hash21(vec2(i, sd + 7.0));
          float len = 0.22 + 0.7 * hash21(vec2(i, sd + 11.0));
          float t = clamp((d - r0) / len, 0.0, 1.0);
          float width = w0 * (0.15 + 0.85 * t) * (0.5 + 1.0 * hash21(vec2(i, sd + 13.0)));
          float dist = abs(fr) * (6.2831853 / K) * d;
          float wob = (vnoise(vec2(d * 26.0, i * 0.37 + sd)) - 0.5) * 0.0035;
          return step(dist + wob, width) * step(r0, d) * step(d, r0 + len) * present;
        }
        void main(){
          // 1 the zoom punch toward the hit and the per-frame jitter
          // 0 the SPLIT: the frame cut in two along the slash; the far side is slid along the cut (and inverted at the end)
          vec2 uv = focus + (vUv - focus) * (1.0 - zoom);
          vec4 cf0 = cutN > 1.5 ? cutField(vec2(uv.x * aspect, uv.y)) : vec4(1e9, 0.0, -1.0, 0.0);
          bool farSide = splitK > 0.0 && cf0.z > 0.0;
          if (farSide) uv -= vec2(cutDir.x / aspect, cutDir.y) * splitSlide;
          uv += (vec2(hash21(vec2(seed, 1.7)), hash21(vec2(2.3, seed))) - 0.5) * shake;
          vec2 q = vec2(uv.x * aspect, uv.y);
          // 2 the hand: a slow sway plus a fine jag, re-rolled every frame (line boil)
          vec2 w = (vec2(vnoise(q * 6.0 + seed * 7.1), vnoise(q * 6.0 + 31.7 + seed * 7.1)) - 0.5) * 0.02
                 + (vec2(vnoise(q * 40.0 + seed * 3.3), vnoise(q * 40.0 + 17.0 + seed * 3.3)) - 0.5) * 0.006;
          vec2 uvw = uv + w * warp;
          float s = abstractK > 0.5 ? 0.0 : sAt(uvw);
          // 3 the energy, exaggerated: grown and SMEARED away from the hit
          float e = abstractK > 0.5 ? 0.0 : eAt(uvw);
          vec2 px = vec2(1.0 / aspect, 1.0) * 0.004 * grow;
          e = max(e, max(max(eAt(uvw + vec2(px.x, 0.0)), eAt(uvw - vec2(px.x, 0.0))), max(eAt(uvw + vec2(0.0, px.y)), eAt(uvw - vec2(0.0, px.y)))));
          vec2 dq = vec2((uvw.x - focus.x) * aspect, uvw.y - focus.y); float d = length(dq); vec2 dir = dq / max(d, 1e-4); vec2 duv = vec2(dir.x / aspect, dir.y);
          float ang = atan(dir.y, dir.x);
          for (int i = 1; i <= 6; i++) { float t = float(i) / 6.0; e = max(e, eAt(uvw - duv * t * 0.08 * smear) * (1.0 - t * 0.6)); }
          if (cutSmearK > 0.0) { vec2 cdu = vec2(cutDir.x / aspect, cutDir.y); // the energy dragged ALONG the cut (a slash's smear runs with the blade)
            for (int i = 1; i <= 8; i++) { float t = float(i) / 8.0; e = max(e, max(eAt(uvw - cdu * t * 0.14 * cutSmearK), eAt(uvw + cdu * t * 0.05 * cutSmearK)) * (1.0 - t * 0.55)); } }
          float hotM = step(hotT, e), markM = step(markT, e), core = step(0.97, e);
          // 4 the outline: a sobel of the silhouette + hot masks
          float o = 0.0;
          if (outline > 0.0) { vec2 ow = vec2(1.0 / aspect, 1.0) * 0.0035 * outline;
            float mx = abs(max(sAt(uvw + vec2(ow.x, 0.0)), step(hotT, eAt(uvw + vec2(ow.x, 0.0)))) - max(sAt(uvw - vec2(ow.x, 0.0)), step(hotT, eAt(uvw - vec2(ow.x, 0.0)))));
            float my = abs(max(sAt(uvw + vec2(0.0, ow.y)), step(hotT, eAt(uvw + vec2(0.0, ow.y)))) - max(sAt(uvw - vec2(0.0, ow.y)), step(hotT, eAt(uvw - vec2(0.0, ow.y)))));
            o = step(0.5, max(mx, my)); }
          // 5 compose: paper, the silhouettes (filled, or line art hatched inside), the marks, the energy as a drawn form
          vec3 c = paper;
          float hl = step(0.5, fract((q.x + q.y) * 52.0 + seed));
          if (s > 0.5) { c = lineart > 0.5 ? mix(paper, ink, hl * 0.6) : ink; }
          if (markM > 0.5) { c = (hatch > 0.0 && hotM < 0.5) ? mix(mark, paper, hl * hatch) : mark; }
          if (hotM > 0.5) c = hot;
          if (core > 0.5) c = vec3(1.0);
          if (selectiveK > 0.0) { vec3 ec = texture2D(energy, uvw).rgb; float el = max(ec.r, max(ec.g, ec.b));
            c = vec3(dot(c, vec3(0.3, 0.59, 0.11))); // the world: grey
            if (e > markT * 0.6 && el > 0.06) c = mix(c, ec / el * min(1.0, 0.35 + el) * 1.15, selectiveK * smoothstep(markT * 0.6, markT * 1.4, e)); } // the energy: its own hue (the halo without one stays grey)
          vec2 qw = vec2(uvw.x * aspect, uvw.y); vec2 fq = vec2(focus.x * aspect, focus.y);
          // CLOUDS: ink smoke as a cluster of carved ellipses around the hit, a white core inside (drawn under everything else)
          if (smoke > 0.0) { float body = 0.0, coreC = 0.0;
            for (int k = 0; k < 9; k++) { float fk = float(k); float a2 = 6.2831853 * hash21(vec2(fk, seed + 41.0)); float rr = (0.04 + 0.16 * hash21(vec2(fk, seed + 43.0))) * smoke;
              vec2 cc = fq + vec2(cos(a2), sin(a2) * 0.6) * rr; float rad = (0.05 + 0.1 * hash21(vec2(fk, seed + 47.0))) * smoke; vec2 dv = qw - cc; float an = atan(dv.y, dv.x);
              float carved = rad * (1.0 + 0.3 * (vnoise(vec2(an * 2.2 + fk, seed)) - 0.5) * 2.0);
              if (length(dv * vec2(1.0, 1.25)) < carved) body = 1.0; if (length(dv * vec2(1.0, 1.25)) < carved * 0.45) coreC = 1.0; }
            if (body > 0.5 && s < 0.5) c = ink; if (coreC > 0.5 && s < 0.5) c = vec3(1.0); }
          // WEDGE: every alive beam / tube drawn as a wedge from the hit outward: white core, accent body, jagged edge, motion strokes
          if (wedge > 0.0) for (int i = 0; i < 4; i++) { if (float(i) >= segN) break;
            vec2 a = vec2(segs[i].x * aspect, segs[i].y), b = vec2(segs[i].z * aspect, segs[i].w); vec2 sd = segDist(qw, a, b);
            float wdt = segW[i] * mix(1.0, 0.3, sd.t) * (1.0 + 0.5 * (vnoise(vec2(sd.t * 28.0, float(i) * 7.0 + seed)) - 0.5)) * wedge;
            if (sd.x < wdt + 0.005) c = ink; if (sd.x < wdt) c = hot; if (sd.x < wdt * 0.42) c = vec3(1.0);
            float band = (sd.x - wdt) / 0.016; float cellT = floor(sd.t * 14.0); float hb = hash21(vec2(floor(band) + float(i) * 9.0, cellT + seed));
            if (sd.x > wdt * 1.15 && sd.x < wdt * 2.4 && fract(band) > 0.8 && hb > 0.62 && hash21(vec2(cellT, floor(band) + seed + 3.0)) > 0.35) c = ink; }
          // STAR: the flash at the hit as a spiky star
          float starR = 0.0;
          if (star > 0.0) { // nine bold spikes of random length around a white core (the flash of refs 13 / 10d), a thick ink rim
            float slot = floor((ang / 6.2831853 + 0.5) * 9.0 + seed * 0.0); float fs = fract((ang / 6.2831853 + 0.5) * 9.0) - 0.5;
            float spike = star * (0.06 + 0.3 * hash21(vec2(slot, seed + 21.0))) * max(0.0, 1.0 - abs(fs) * 1.7); starR = star * 0.07 + spike;
            if (d < starR + 0.016 && s < 0.5) c = ink; if (d < starR && s < 0.5) c = vec3(1.0); }
          // KANADA FLARE: straight razor lines through the hit (a long cross, short diagonals, each thickest at the centre),
          // two ghost rings along the long axis, a hot centre - straight and angular, never soft
          if (flareK > 0.0) { vec3 fc = dot(paper, vec3(0.3, 0.59, 0.11)) > 0.5 ? ink : vec3(1.0); float rot = 0.35 + 0.5 * hash21(vec2(7.0, floor(seed / 97.0)));
            for (int k = 0; k < 4; k++) { float a = rot + float(k) * 0.7853982; vec2 dir = vec2(cos(a), sin(a));
              float len = flareK * (mod(float(k), 2.0) < 0.5 ? 0.62 : 0.24); float along = abs(dot(dq, dir)), acr = abs(dq.x * dir.y - dq.y * dir.x);
              if (along < len && acr < 0.0045 * flareK * (1.0 - along / len) + 0.0006) c = fc; }
            for (int k = 1; k <= 2; k++) { vec2 cc = vec2(cos(rot), sin(rot)) * 0.2 * float(k) * flareK; float rr = 0.022 * float(k) * flareK;
              if (abs(length(dq - cc) - rr) < 0.0022) c = fc; }
            if (d < 0.011 * flareK) c = vec3(1.0); }
          // VOID: the black hole at the hit (back half of its disc, the core, the photon ring, the lensed arc, the front half)
          // BOLTS: lightning tearing out of the hit (One For All): forked zig-zags, white-hot core, accent glow, ink edge
          if (boltsK > 0.0) {
            float nB = floor(5.0 + 4.0 * boltsK);
            for (int k = 0; k < 17; k++) { if (float(k) >= nB) break;
              float a0 = hash21(vec2(float(k), seed + 31.0)) * 6.2831853; float reach = 0.25 + 0.55 * hash21(vec2(float(k), seed + 37.0));
              vec2 dirB = vec2(cos(a0), sin(a0)); vec2 nrmB = vec2(-dirB.y, dirB.x);
              float along = dot(dq, dirB); if (along < 0.0 || along > reach) continue;
              float seg = along * 26.0; float sI = floor(seg); float sf = fract(seg);
              float o0 = (hash21(vec2(sI, float(k) + seed)) - 0.5), o1 = (hash21(vec2(sI + 1.0, float(k) + seed)) - 0.5);
              float off = mix(o0, o1, sf) * 0.05 * (0.4 + along * 2.0);
              float dB = abs(dot(dq, nrmB) - off); float wB = 0.006 * boltsK * (1.0 - along / reach) + 0.0015;
              // a fork off every few segments
              float fk = hash21(vec2(sI, float(k) + seed + 9.0)); float dF = 10.0;
              if (fk > 0.72) { vec2 fdir = normalize(dirB + nrmB * (fk - 0.86) * 4.0); vec2 fo = dirB * (sI / 26.0) + nrmB * off;
                vec2 rel = dq - fo; float fa = dot(rel, fdir); if (fa > 0.0 && fa < 0.06) dF = abs(dot(rel, vec2(-fdir.y, fdir.x))); }
              float dd2 = min(dB, dF);
              if (dd2 < wB * 2.6) c = ink; if (dd2 < wB * 1.8) c = hot; if (dd2 < wB * 0.8) c = vec3(1.0); }
          }
          if (voidK > 0.0) {
            float vR = 0.085 * voidK; float ca = cos(-0.21), sa = sin(-0.21);
            vec2 e = vec2(ca * dq.x - sa * dq.y, sa * dq.x + ca * dq.y);
            float ell = length(vec2(e.x / (2.8 * vR), e.y / (0.40 * vR)));
            float stripe = fract(atan(e.y, e.x) * 3.0 / 6.2831853 + ell * 2.5 + vnoise(vec2(ell * 9.0, seed)) * 0.4);
            vec3 discC = stripe < 0.45 ? hot : vec3(1.0);
            if (ell < 1.0 && ell > 0.5 && e.y > 0.0) c = ell < 0.56 ? ink : discC;              // the far half, behind
            if (d > vR * 1.16 && d < vR * 1.42 && dq.y > 0.0 && abs(dq.x) < vR * 1.3) c = d < vR * 1.22 ? ink : hot; // the lensed arc
            if (d < vR + 0.014) c = ink; if (d < vR + 0.009) c = vec3(1.0); if (d < vR) c = vec3(0.0);            // rim, photon ring, core
            if (crackK > 0.0 && d < vR * (1.0 + 2.6 * crackK)) { // the hole bursting: jagged white fissures out of the core
              float sl = floor((ang / 6.2831853 + 0.5) * 7.0); float fa = fract((ang / 6.2831853 + 0.5) * 7.0) - 0.5;
              float jag = (vnoise(vec2(d * 40.0, sl + seed)) - 0.5) * 0.35;
              float w = 0.09 * (1.0 - d / (vR * (1.0 + 2.6 * crackK)));
              if (abs(fa + jag) < w + 0.03 && hash21(vec2(sl, seed + 4.0)) > 0.25) c = ink;
              if (abs(fa + jag) < w && hash21(vec2(sl, seed + 4.0)) > 0.25) c = vec3(1.0); }
            if (ell < 1.0 && ell > 0.5 && e.y <= 0.0) c = ell < 0.56 ? ink : discC; }            // the near half, in front
          // SPECKS: live particles as tapered V marks flying away from the hit
          if (speckK > 0.0) for (int k = 0; k < 48; k++) { if (float(k) >= speckN) break;
            vec2 sp = vec2(specks[k].x * aspect, specks[k].y); vec2 dd = sp - fq; float dl = length(dd); if (dl < 1e-4) continue; dd /= dl;
            float len = (0.015 + 0.035 * hash21(vec2(float(k), seed + 5.0))) * speckK; vec2 sdk = segDist(qw, sp, sp + dd * len);
            if (sdk.x < 0.0045 * speckK * (1.0 - sdk.t) && d > starR) c = ink; }
          // soot: short radial ink strokes inside the energy's edge (the manga explosion: soot on the light bulb)
          if (soot > 0.0 && hotM > 0.5) { float bodyOut = step(hotT, eAt(uvw + duv * 0.02 * soot)); float strokes = step(0.55, fract(ang * 70.0 + d * 6.0 + seed)) * step(0.5, hash21(vec2(floor(ang * 70.0), seed)));
            if (bodyOut < 0.5 && strokes > 0.5 && core < 0.5) c = ink; }
          if (o > 0.5) c = ink;
          // rim light: the silhouettes carry a light edge on the side facing the hit
          if (rim > 0.0 && s > 0.5) { float sIn = sAt(uvw - duv * 0.008 * rim); if (sIn < 0.5) c = vec3(1.0); }
          // 6 splatter: ink drops around the energy and the hit
          if (splatter > 0.0) { vec2 g = q * 28.0; vec2 cell = floor(g); float h1 = hash21(cell + seed);
            vec2 cc = cell + vec2(hash21(cell + 1.3 + seed), hash21(cell + 7.9 + seed)); float rad = 0.12 + 0.3 * hash21(cell + 3.1 + seed);
            float near = max(markM, 1.0 - smoothstep(0.1, 0.5, d));
            if (h1 < 0.35 * splatter * near && distance(g, cc) < rad) c = ink; }
          // 7 the lines converging on the hit: drawn focus lines (fine / bold / both) or a texture, with a clean hole
          if (linesMode > 0.5 && linesMode < 3.5) {
            float on = 0.0;
            if (linesMode < 1.5 || linesMode > 2.5) on = max(on, focusLines(ang, d, 230.0, 0.0022 * linesStrength, seed, 0.55));
            if (linesMode > 1.5) on = max(on, focusLines(ang, d, 54.0, 0.0075 * linesStrength, seed + 50.0, 0.45));
            if (on > 0.5 && d > max(hole, starR + 0.012)) c = linesColor; }
          else if (linesMode > 3.5 && linesMode < 4.5) { vec2 luv = dq / linesScale + 0.5;
            if (luv.x >= 0.0 && luv.x <= 1.0 && luv.y >= 0.0 && luv.y <= 1.0) { vec4 ls = texture2D(lines, luv);
              float a = max(ls.r, max(ls.g, ls.b)) * linesStrength * smoothstep(hole * 0.5, hole, d);
              float br = step(0.15, hash21(vec2(floor(ang * 20.0), floor(d * 16.0)) + seed));
              c = mix(c, linesColor, step(0.35, a) * br); } }
          if (linesMode > 4.5 && linesMode < 5.5) { // perspective: fine lines converging on the beam's far end, plus bold ones on the hit
            float on = focusLines(ang, d, 54.0, 0.0075 * linesStrength, seed + 50.0, 0.45);
            if (hasVanish > 0.5) { vec2 dv = vec2((uvw.x - vanish.x) * aspect, uvw.y - vanish.y); float dvl = length(dv); float angv = atan(dv.y, dv.x);
              on = max(on, focusLines(angv, dvl, 200.0, 0.0022 * linesStrength, seed + 90.0, 0.6) * step(0.03, dvl)); }
            if (on > 0.5 && d > max(hole, starR + 0.012)) c = linesColor; }
          vec4 cf = cutN > 1.5 ? cutField(qw) : vec4(1e9, 0.0, -1.0, 0.0);
          if (linesMode > 5.5) { // CUT lines: parallel speed lines running WITH the slash (not at the hit), broken, tapered, each its own reach
            vec2 nq = vec2(-cutDir.y, cutDir.x); float along = dot(qw - fq, cutDir), acr = dot(qw - fq, nq);
            float slot = floor(acr * 120.0), fr = fract(acr * 120.0) - 0.5;
            float pres = step(0.5, hash21(vec2(slot, seed + 61.0))) * step(0.3, hash21(vec2(floor(slot / 6.0), seed + 62.0)));
            float st = (hash21(vec2(slot, seed + 63.0)) - 0.6) * 2.6, ln = 0.3 + 1.1 * hash21(vec2(slot, seed + 67.0));
            float tt = clamp((along - st) / ln, 0.0, 1.0), wl = (0.08 + 0.42 * hash21(vec2(slot, seed + 71.0))) * sin(3.14159 * tt) * linesStrength;
            float clearOf = cutN > 1.5 ? step(cf.w * max(slashK, 1.0) * 1.8 + 0.012, cf.x) : 1.0;
            if (pres * step(abs(fr), wl) * step(st, along) * step(along, st + ln) * clearOf > 0.5) c = linesColor; }
          if (farSide) c = vec3(1.0) - c; // the far side of the cut: the tones inverted
          if (splitK > 0.0 && cutN > 1.5 && cf.x < 0.0022 * splitK && cf.w <= 0.0) c = vec3(1.0); // the cut's hairline beyond the stroke, across the frame
          if (slashK > 0.0 && cf.w > 0.0) { // THE STROKE: the cut drawn with a brush - ink edge, accent body, white core; its outer part breaks into bristles
            float w = cf.w * slashK, across = cf.x / max(w, 1e-4);
            float dry = step(0.6, across) * step(hash21(vec2(floor(across * 9.0), floor(cf.y * 2.5) + seed)), 0.42);
            if (cf.x < w + 0.007 && dry < 0.5) c = ink;
            if (cf.x < w && dry < 0.5) c = hot;
            if (cf.x < w * 0.42) c = vec3(1.0); }
          // the onomatopoeia: big jagged letters at the hit, tilted
          if (textOn > 0.5 && coverOn < 0.5) { float cr = cos(textRot), sr = sin(textRot); vec2 tq = vec2((vUv.x - textPos.x) * aspect, vUv.y - textPos.y); tq = vec2(cr * tq.x - sr * tq.y, sr * tq.x + cr * tq.y);
            // the band the word sits on: a diagonal stripe across the frame with torn edges and streaks along it
            vec2 guv = tq / vec2(textSize * 2.0, textSize) + 0.5; // the ghost word, hollow and hatched, behind everything of the card
            float bandDark = step(dot(bandColor, vec3(0.3, 0.59, 0.11)), 0.5); vec3 ghostCol = bandOn > 0.5 ? mix(vec3(0.0), vec3(1.0), bandDark) : ink;
            if (bandOn > 0.5) { float bh0 = textSize * 0.36 * (1.0 + 0.3 * (vnoise(vec2(tq.x * 5.0 + seed, seed * 1.3)) - 0.5) * 2.0); // (the band is laid first; the ghost watermark goes over it, under the word)
              float bx = tq.x - bandOffset; // the band's own slide: it whips in, the word follows
              if (abs(abs(tq.y) - bh0) < 0.007 && bx > -1.5 && bx < 1.5) c = accentColor;
              if (abs(tq.y) < bh0 && bx > -1.5) { c = bandColor;
                if (bandLines > 0.0) { float st = fract(tq.y * 40.0 + hash21(vec2(floor(tq.x * 14.0), seed)) * 3.0); float gap = hash21(vec2(floor(tq.x * 14.0), floor(tq.y * 40.0) + seed));
                  if (st < 0.08 * bandLines && gap > 0.55 && abs(tq.y) > bh0 * 0.55) c = paper; } }
              else if (abs(tq.y) < bh0 + 0.09 && hash21(vec2(floor(tq.y * 90.0), floor(tq.x * 3.0) + seed)) > 0.72 && fract(tq.y * 90.0) < 0.25 && abs(tq.x) < 1.2) c = bandColor; }
            if (guv.x > 0.0 && guv.x < 1.0 && guv.y > 0.0 && guv.y < 1.0) { vec4 gt = texture2D(textTex, guv); if (gt.r > 0.5 && gt.g < 0.5 && fract(tq.y * 140.0) < 0.5) c = ghostCol; }
            tq = vec2((tq.x - textOffset) / textStretch, tq.y / textSquash); // the slam: offset along the band, the smear, the squash on contact
            vec2 tuv = tq / vec2(textSize * 2.0, textSize) + 0.5; vec2 tpx = vec2(0.012, 0.024) / textSize; // one outline step in the plate's uv
            if (tuv.x > -0.1 && tuv.x < 1.1 && tuv.y > -0.1 && tuv.y < 1.1) {
              float ta = texture2D(textTex, clamp(tuv, 0.0, 1.0)).g;
              float sh = texture2D(textTex, clamp(tuv - vec2(0.9, -1.4) * tpx, 0.0, 1.0)).g; // the hard shadow: the word lifted off the paper
              float ol = 0.0, halo = 0.0; for (int k = 0; k < 8; k++) { float a2 = float(k) * 0.785398; vec2 dk = vec2(cos(a2), sin(a2)) * tpx;
                ol = max(ol, texture2D(textTex, clamp(tuv + dk * 0.55, 0.0, 1.0)).g); halo = max(halo, texture2D(textTex, clamp(tuv + dk * 1.25, 0.0, 1.0)).g); }
              // trails: motion lines streaming off the letters on the entry frame
              if (textTrail > 0.0 && ta < 0.5) { float ahead = 0.0; for (int k = 1; k <= 6; k++) ahead = max(ahead, texture2D(textTex, clamp(tuv + vec2(float(k) * 0.04 * textTrail, 0.0), 0.0, 1.0)).g);
                if (ahead > 0.5 && fract(tuv.y * 36.0 + hash21(vec2(floor(tuv.y * 36.0), seed))) < 0.35 && hash21(vec2(floor(tuv.y * 36.0), seed + 2.0)) > 0.3) c = paper; }
              // halo (the band / paper) isolates the word, then the hard shadow and the outline, then the face: split-tone (white top, accent bottom), a glint sweeping across on the contact frame
              if (halo > 0.5) c = bandOn > 0.5 ? bandColor : paper; if (sh > 0.5) c = vec3(0.0); if (ol > 0.5) c = vec3(0.0);
              if (ta > 0.5) { bool top = textSplit > 0.5 && tuv.y > textMid + 0.05 + 0.02 * sin(tuv.x * 9.0); c = top ? mix(textColor, vec3(1.0), 0.55) : textColor;
                if (!top && textGlint >= 0.0 && abs((tuv.x + tuv.y * 0.35) - textGlint) < 0.022) c = vec3(1.0); } } }
          // 8 the white mass around the hit (the silhouettes and the energy survive inside it)
          if (flash > 0.0) { float fr2 = flash * (0.75 + 0.5 * vnoise(vec2(ang * 2.5 + seed, seed * 0.7)));
            if (d < fr2 && s < 0.5 && hotM < 0.5) c = paper; }
          // 9 black masses from the frame edges (the calligraphy frame)
          if (mass > 0.0) { float edge = max(abs(vUv.x - 0.5) * 2.0, abs(vUv.y - 0.5) * 2.0); float n = vnoise(q * 3.0 + seed) * 0.6 + vnoise(q * 9.0 + seed * 2.0) * 0.4;
            if (edge * edge * mass * 0.8 + n * 0.7 > 1.28 && hotM < 0.5) c = ink; }
          // 10 the name card over the whole frame, clawed open: parallel jagged slashes crawl across it, then it breaks apart
          if (coverOn > 0.5 && textOn > 0.5) {
            vec2 cuv = vUv + (vec2(hash21(vec2(seed, 1.7)), hash21(vec2(2.3, seed))) - 0.5) * shake; // centred on the screen, not on the hit
            vec2 qq = vec2(cuv.x * aspect, cuv.y); vec2 ctr = vec2(0.5 * aspect, 0.5);
            vec2 tdir = vec2(cos(cutAngle), sin(cutAngle)); vec2 nrm = vec2(-tdir.y, tdir.x);
            float along = dot(qq - ctr, tdir); float sd0 = dot(qq - ctr, nrm);
            float zz = (abs(fract(along * 7.0 + vnoise(vec2(along * 2.5, seed)) * 0.9) - 0.5) - 0.25) * 0.07 * jag; // the zig-zag of a crack
            float sd = sd0 + zz + (vnoise(vec2(along * 26.0, 3.0)) - 0.5) * 0.03 * rough;
            float n = max(1.0, claws); float hw = sliceGap * 0.5 / n;
            float strip = 0.0; bool inGap = false; float edge = 10.0; float lineD = 10.0;
            for (int i = 0; i < 4; i++) { if (float(i) >= n) break;
              float oi = (float(i) - (n - 1.0) * 0.5) * clawSpacing;
              float ci = oi + (float(i) - (n - 1.0) * 0.5) * 2.0 * hw;
              float zi = zz * (1.0 + 0.6 * sin(float(i) * 2.3)); float sdi = sd0 + zi + (vnoise(vec2(along * 26.0, 3.0 + float(i))) - 0.5) * 0.03 * rough;
              if (sdi > ci + hw) strip = float(i) + 1.0;
              if (abs(sdi - ci) < hw) inGap = true;
              edge = min(edge, abs(abs(sdi - ci) - hw)); lineD = min(lineD, abs(sdi - oi)); }
            float crawlEdge = -0.5 * aspect - 0.2 + crawl * (aspect + 0.6); // the cracks run across the card from one side
            if (inGap && sliceGap > 0.001) { // the gap: sparks, blood chips
              vec2 gcl = floor(qq * 70.0); if (hash21(gcl + seed) > 0.982) c = hash21(gcl + 2.0) > 0.5 ? accentColor : vec3(1.0);
              if (hash21(gcl + seed + 5.0) > 0.992) c = blood; }
            else {
              float mid = strip - n * 0.5; float dj = mid * 2.0 * hw;
              float sgn = mod(strip, 2.0) < 0.5 ? -1.0 : 1.0; float slideJ = sliceSlide * sgn * (1.0 + 0.45 * abs(mid));
              // shards: each strip breaks into chunks along the cut, every chunk flung its own way, cracks between them
              float chunkU = along * 4.0 + strip * 1.7 + vnoise(vec2(sd0 * 9.0, strip)) * 0.6; float chunk = floor(chunkU);
              float eT = (hash21(vec2(chunk, strip + 11.0)) - 0.5) * 0.35 * shatter * min(1.0, sliceGap * 2.0);
              float eN = (hash21(vec2(chunk, strip + 23.0)) - 0.2) * 0.25 * shatter * min(1.0, sliceGap * 2.0) * (mid >= 0.0 ? 1.0 : -1.0);
              float crack = fract(chunkU); bool inCrack = shatter > 0.0 && sliceGap > 0.001 && (crack < 0.03 * shatter * min(1.0, sliceGap * 2.0) || crack > 1.0 - 0.03 * shatter * min(1.0, sliceGap * 2.0));
              if (!inCrack) {
                vec2 piv = ctr + nrm * dj; float ra = -spin * mid / max(0.5, n * 0.5) * (1.0 + 0.5 * hash21(vec2(chunk, strip)) * shatter);
                vec2 src = ctr + tdir * (along - slideJ - eT) + nrm * (sd0 - dj - eN); vec2 rel = src - piv;
                src = piv + vec2(cos(ra) * rel.x - sin(ra) * rel.y, sin(ra) * rel.x + cos(ra) * rel.y);
                c = cardAt(src);
                if (sliceGap > 0.001 && edge < 0.008) c = vec3(1.0); if (sliceGap > 0.001 && edge < 0.003) c = accentColor; } }
            // before it opens: the cracks crawl across the card, white-hot with a blood core, branching off as they go
            if (sliceGap < 0.001 && cutFlash > 0.0 && along < crawlEdge) {
              if (lineD < 0.0035 + 0.004 * cutFlash) c = vec3(1.0); if (lineD < 0.0015 * cutFlash) c = blood;
              float br = fract(along * 5.0 + 0.3); if (lineD < 0.08 && abs(lineD - br * 0.08) < 0.002 * cutFlash && hash21(vec2(floor(along * 5.0), seed)) > 0.35) c = vec3(1.0); }
          }
          gl_FragColor = vec4(pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2)), 1.0); }` });
  }
  // the effect's data at this instant: every alive beam / tube as a world axis (from -> to, width), live particles
  frameData(f) {
    const F = this.worldPoint(f.focus); const axes = []; const pts = [];
    for (const l of this.layers) {
      const el = l.el; if (!el || el.frames === false) continue; // an opted-out layer seeds no axes / specks either
      if (l.strips && l.strips.length && l.strips[0].mesh.visible) { const a = this.worldPoint(el.from || el.target || [0, 0, 0]), b = this.worldPoint(el.to || [0, 1, 0]); const w = (typeof el.width === "number" ? el.width : numAt(el.width, 0.5, 1)) * this.scale; axes.push({ a, b, w }); }
      else if (l.mesh && l.mesh.visible && l.native && (el.shape === "tube" || el.shape === "cone") && el.aim != null) { const a = this.worldPoint(el.point || [0, 0, 0]), b = this.worldPoint(el.aim); const ws = new THREE.Vector3(); l.mesh.getWorldScale(ws); axes.push({ a, b, w: Math.max(0.5, (l.native ? l.native.x : 1) * Math.max(ws.x, ws.z) * 0.5) }); }
      if (l.live && l.live.length) { for (let i = 0; i < l.live.length && pts.length < 48; i += Math.max(1, Math.floor(l.live.length / 12))) pts.push(l.live[i].pos); }
    }
    // the SLASH (impact frames v4): every visible arc mesh's centreline (row 1 of its 2-row grid: v = 0.5) and its band's
    // edges (rows 0 and 2) in the world, 20 samples; a point the sweep / erode has hidden (vertex alpha) carries no stroke.
    // The arc nearest the hit is the frame's cut.
    let cut = null;
    for (const l of this.layers) {
      const el = l.el; if (!el || el.shape !== "arc" || !l.mesh || !l.mesh.visible) continue;
      const g = l.mesh.geometry, gr = g.userData.grid; if (!gr || gr.rows % 2) continue;
      const pos = g.attributes.position, col = g.attributes.color, w = gr.cols + 1, n = gr.strands || 1, cr = gr.rows / 2, per = w * (gr.rows + 1);
      const c0 = Math.floor(n / 2) * per, c1 = n % 2 ? c0 : c0 - per; // an even count: the mean of the two central strands
      l.mesh.updateMatrixWorld(true);
      const at = (k) => new THREE.Vector3().fromBufferAttribute(pos, c1 + k).add(new THREE.Vector3().fromBufferAttribute(pos, c0 + k)).multiplyScalar(0.5).applyMatrix4(l.mesh.matrixWorld);
      const cp = [];
      for (let k = 0; k < 20; k++) { const i = Math.round((k / 19) * gr.cols); cp.push({ mid: at(cr * w + i), lo: at(i), hi: at(gr.rows * w + i), vis: !col || col.getW(c0 + cr * w + i) > 0.15 }); }
      const dmin = Math.min(...cp.map((c) => c.mid.distanceTo(F)));
      if (!cut || dmin < cut.d) cut = { d: dmin, pts: cp, name: el.name };
    }
    // the axis nearest the hit first; the hit end first on each
    for (const x of axes) { if (x.b.distanceTo(F) < x.a.distanceTo(F)) { const t = x.a; x.a = x.b; x.b = t; } x.dist = x.a.distanceTo(F); }
    axes.sort((p, q) => p.dist - q.dist);
    return { F, axes: axes.slice(0, 4), pts, cut };
  }
  // the cut-in camera of an impact frame: the hit re-framed so the subject fills the frame (close, low, a dutch roll);
  // with a beam at the hit the camera stands beside and behind it so the wedge crosses the frame
  // the scene objects of every layer with `frames: false` - kept out of every impact-frame style (review 2026-10-25: the
  // comic / anime styles and debris chunks ignored it at first)
  noFrameObjects() {
    const set = new Set();
    for (const l of this.layers) {
      if (!l.el || l.el.frames !== false) continue;
      if (l.mesh) set.add(l.mesh); if (l.meshes) for (const m of l.meshes) set.add(m); if (l.twinLayer && l.twinLayer.mesh) set.add(l.twinLayer.mesh);
      if (l.strips) for (const st of l.strips) set.add(st.mesh);
      if (l.chunks) for (const c of l.chunks) if (c.mesh) set.add(c.mesh);
    }
    return set;
  }
  // the environment a mirror reflects (reflectance): the booth's sky as an equirect gradient - zenith, a slightly brighter
  // horizon, the ground below - prefiltered once (PMREM) and shared by every reflective mesh
  envMap() {
    if (this.envTex) return this.envTex;
    const e = this.env || {}, c = document.createElement("canvas"); c.width = 256; c.height = 128; const g = c.getContext("2d");
    const css = (v, d) => "#" + (v && v.isColor ? v : new THREE.Color(v == null ? d : v)).getHexString();
    const hz = (e.horizon && e.horizon.isColor ? e.horizon.clone() : new THREE.Color(e.horizon == null ? 0x8090a0 : e.horizon)).multiplyScalar(1.6);
    const gr = g.createLinearGradient(0, 0, 0, 128);
    gr.addColorStop(0, css(e.zenith, 0x203050)); gr.addColorStop(0.46, css(e.horizon, 0x8090a0)); gr.addColorStop(0.5, "#" + hz.getHexString());
    gr.addColorStop(0.54, css(e.ground, 0x302820)); gr.addColorStop(1, css(e.ground, 0x302820));
    g.fillStyle = gr; g.fillRect(0, 0, 256, 128);
    const t = new THREE.CanvasTexture(c); t.mapping = THREE.EquirectangularReflectionMapping; t.colorSpace = THREE.SRGBColorSpace;
    const pm = new THREE.PMREMGenerator(this.renderer); this.envTex = pm.fromEquirectangular(t).texture; pm.dispose(); t.dispose();
    return this.envTex;
  }
  // the SUBJECT of an impact frame, from the current camera: what the frame will draw (its energy by brightness - lights
  // stay on for lit layers - and its silhouettes as ink) as a 128x72 mask -> the box holding 3-97 % of its pixels, in NDC
  // (cx, cy, half spans hx, hy) + the share of the frame it covers. Sprites draw with their own instanced shader, so the
  // energy pass renders normally; only the silhouettes take the ink override. null when nothing is drawn.
  subjectMask(energy, sil) {
    const r = this.renderer, s = this.scene, cam = this.camera, W = 128, H = 72;
    const rt = this.rtSubj || (this.rtSubj = new THREE.WebGLRenderTarget(W, H, { type: THREE.UnsignedByteType }));
    const buf = this.subjBuf || (this.subjBuf = new Uint8Array(W * H * 4)); const mask = new Uint8Array(W * H);
    const vis = s.children.map((o) => [o, o.visible]); const was = new Map(vis); const bg = s.background, ov = s.overrideMaterial, fog = s.fog, fogD = fog ? fog.density : 0;
    s.background = null; if (fog) fog.density = 0; r.setClearColor(0x000000, 1);
    const pass = (objs, override) => {
      for (const [o] of vis) if (!o.isLight) o.visible = false;
      for (const o of objs) if (was.get(o)) o.visible = true; // only what was showing (review: dead layers' meshes are hidden)
      s.overrideMaterial = override; r.setRenderTarget(rt); r.clear(); r.render(s, cam); r.readRenderTargetPixels(rt, 0, 0, W, H, buf);
      for (let i = 0; i < W * H; i++) if (Math.max(buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]) > 24) mask[i] = 1;
    };
    pass(energy, null);
    if (sil.length) { this.inkMat.color.setRGB(1, 1, 1); pass(sil, this.inkMat); }
    for (const [o, v] of vis) o.visible = v; s.overrideMaterial = ov; s.background = bg; if (fog) fog.density = fogD; r.setRenderTarget(null);
    // particles smaller than a mask pixel never rasterize (noctiluca's 0.27-stud plankton: an empty mask, an unaimed
    // camera): splat every live particle's projected position too - sprite instances (iPos) and swarm instances
    const pv = new THREE.Vector3(), mtx = new THREE.Matrix4();
    const splat = () => { if (pv.z < -1 || pv.z > 1 || Math.abs(pv.x) > 1 || Math.abs(pv.y) > 1) return; const x = Math.min(W - 1, ((pv.x + 1) / 2 * W) | 0), y = Math.min(H - 1, ((pv.y + 1) / 2 * H) | 0); mask[y * W + x] = 1; };
    for (const o of energy) {
      if (!was.get(o)) continue;
      const g = o.geometry;
      if (o.isInstancedMesh) { for (let k = 0; k < o.count; k++) { o.getMatrixAt(k, mtx); pv.setFromMatrixPosition(mtx).applyMatrix4(o.matrixWorld).project(cam); splat(); } }
      else if (g && g.attributes && g.attributes.iPos) { const a = g.attributes.iPos.array, c = g.instanceCount || 0; for (let k = 0; k < c; k++) { pv.set(a[k * 3], a[k * 3 + 1], a[k * 3 + 2]).project(cam); splat(); } }
    }
    const cols = new Float64Array(W), rows = new Float64Array(H); let n = 0;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (mask[y * W + x]) { cols[x]++; rows[y]++; n++; }
    if (n < 6) return null;
    const span = (h) => { let acc = 0, lo = 0, hi = h.length - 1; for (let i = 0; i < h.length; i++) { acc += h[i]; if (acc >= n * 0.03) { lo = i; break; } }
      acc = 0; for (let i = h.length - 1; i >= 0; i--) { acc += h[i]; if (acc >= n * 0.03) { hi = i; break; } } return [lo, hi + 1]; };
    const [x0, x1] = span(cols), [y0, y1] = span(rows); // readPixels rows run bottom-up: row 0 = NDC y -1
    return { cx: ((x0 + x1) / W) - 1, cy: ((y0 + y1) / H) - 1, hx: (x1 - x0) / W, hy: (y1 - y0) / H, share: n / (W * H) };
  }
  // camera "subject" (2026-10-24, the owner on nine originals: "bad impact frames" - the frames kept the wide shot, the
  // effect a speck in an empty frame): aim at the subject's box and zoom until it fills `fill` (0.8) of the frame, then
  // roll (-9 degrees: a dutch angle). A crop, not a dolly: a telephoto close-up of the effect itself.
  frameOnSubject(f, energy, sil) {
    const m = this.subjectMask(energy, sil); if (!m) return;
    const cam = this.camera, fill = f.fill || 0.8, fov0 = cam.fov, pos0 = cam.position.clone(), quat0 = cam.quaternion.clone();
    const ctr = new THREE.Vector3(m.cx, m.cy, 0.5).unproject(cam);
    const tanH = Math.tan((fov0 * DEG) / 2) * Math.max(m.hx, m.hy, 0.02) / fill;
    cam.lookAt(ctr); cam.rotateZ((f.roll == null ? -9 : f.roll) * DEG);
    const clampFov = (v) => Math.min(Math.min(100, fov0 * 1.6), Math.max(6, v));
    cam.fov = clampFov((2 * Math.atan(tanH)) / DEG); cam.updateProjectionMatrix();
    // once more from where it now looks (review 2026-10-25: a box near the frame's edge came out ~0.55 instead of 0.82)
    // a subject lost after aiming (a few just-spawned particles zoomed into empty space - noctiluca's first beat) -> the
    // frame keeps the view it had
    const m2 = this.subjectMask(energy, sil); if (!m2) { cam.position.copy(pos0); cam.quaternion.copy(quat0); cam.fov = fov0; cam.updateProjectionMatrix(); return; }
    const got = Math.max(m2.hx, m2.hy); if (got < 0.02) return;
    // bounded (a sparse subject - a few particles - re-measures far smaller from close up: unbounded, noctiluca zoomed
    // 62 -> 44 -> 6 degrees and lost it), and kept only if the subject is still in the frame
    const fov1 = cam.fov, want = (2 * Math.atan(Math.tan((fov1 * DEG) / 2) * got / fill)) / DEG;
    cam.fov = clampFov(Math.min(fov1 * 1.4, Math.max(fov1 * 0.6, want))); cam.updateProjectionMatrix();
    if (!this.subjectMask(energy, sil)) { cam.fov = fov1; cam.updateProjectionMatrix(); }
  }
  frameCamera(f, data) {
    const cam = this.camera;
    const F = this.worldPoint(f.focus); const A = this.actor.group.position.clone().add(new THREE.Vector3(0, 3, 0));
    if (f.camera === "cut" && data && data.cut) { // impact frames v4: SQUARE to the slash (on its arc's plane normal, the side the camera
      // already watches from), the whole cut and the figure in frame, a dutch roll - the cut reads as the shape it is
      const P = data.cut.pts.map((c) => c.mid), a = P[0], b = P[P.length - 1], m = P[Math.floor(P.length / 2)];
      const nrm = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(m, a)); if (nrm.lengthSq() < 1e-8) nrm.set(1, 0, 0); nrm.normalize();
      if (nrm.dot(cam.position.clone().sub(m)) < 0) nrm.negate();
      const box = new THREE.Box3().setFromPoints([...P, this.actor.group.position.clone(), A.clone().add(new THREE.Vector3(0, 2, 0))]);
      const ctr = box.getCenter(new THREE.Vector3()), ext = box.getSize(new THREE.Vector3()).length(), fov = 52;
      cam.position.copy(ctr).addScaledVector(nrm, (ext * 0.5 * 1.15) / Math.tan((fov * DEG) / 2)); if (cam.position.y < 0.6) cam.position.y = 0.6;
      cam.lookAt(ctr); cam.rotateZ(-8 * DEG); cam.fov = fov; cam.updateProjectionMatrix(); return;
    }
    const axis = data && data.axes.length && data.axes[0].dist < 6 ? data.axes[0] : null;
    if (axis && (f.camera === "closeup" || f.camera === "low" || f.camera === "wide")) {
      const bd = axis.b.clone().sub(axis.a); bd.y *= 0.3; if (bd.lengthSq() < 1e-4) bd.set(0, 0, -1); bd.normalize();
      const side = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), bd); if (side.lengthSq() < 1e-6) side.set(1, 0, 0); side.normalize();
      const P = { closeup: { back: 9, side: 5, up: 3.5, ahead: 12, fov: 66, roll: -7, mixA: 0.5 }, low: { back: 7.5, side: 4, up: 1.0, ahead: 10, fov: 76, roll: 9, mixA: 0.45 }, wide: { back: 18, side: 12, up: 7, ahead: 26, fov: 58, roll: -11, mixA: 0.4 } }[f.camera];
      const pos = F.clone().sub(bd.clone().multiplyScalar(P.back)).add(side.multiplyScalar(P.side)).add(new THREE.Vector3(0, P.up, 0)); if (pos.y < 0.6) pos.y = 0.6;
      const look = F.clone().add(bd.multiplyScalar(P.ahead)).add(new THREE.Vector3(0, 1, 0)).lerp(A, P.mixA);
      cam.position.copy(pos); cam.lookAt(look); cam.rotateZ(P.roll * DEG); cam.fov = P.fov; cam.updateProjectionMatrix();
      // fit: the figure whole (feet, head, the blade tip) stays inside 90 % of the frame — widen the lens if it does not
      const marks = [this.actor.group.position.clone(), A.clone().add(new THREE.Vector3(0, 2.5, 0)), this.anchor("tip") || A];
      for (let k = 0; k < 6; k++) { let over = 0; for (const m of marks) { const v = m.clone().project(cam); over = Math.max(over, Math.abs(v.x) - 0.9, Math.abs(v.y) - 0.9); } if (over <= 0) break; cam.fov = Math.min(100, cam.fov * (1 + over * 0.6 + 0.05)); cam.updateProjectionMatrix(); }
      return;
    }
    const presets = { closeup: { az: 40, el: -12, k: 0.9, min: 7, fov: 62, roll: -6, look: 0.45 }, low: { az: 25, el: -32, k: 0.7, min: 6.5, fov: 72, roll: 8, look: 0.4 }, wide: { az: 70, el: 16, k: 1.5, min: 14, fov: 56, roll: -10, look: 0.5 } };
    const p = typeof f.camera === "object" ? Object.assign({}, presets.closeup, f.camera) : (presets[f.camera] || presets.closeup);
    const FA = A.clone().sub(F); let dist = FA.length();
    const curFwd = new THREE.Vector3(); cam.getWorldDirection(curFwd); curFwd.y = 0; if (curFwd.lengthSq() < 1e-6) curFwd.set(0, 0, -1); curFwd.normalize();
    let fdir, L, r;
    if (dist > 40 || dist < 0.5) { // the hit is its own subject (a landing point far from the rig): frame the hit from the current side
      fdir = curFwd.clone().negate(); L = F.clone().add(new THREE.Vector3(0, 5, 0)); r = p.min * 2.4;
    } else { fdir = FA.clone().normalize(); L = F.clone().lerp(A, p.look); r = Math.max(p.min, dist * p.k); }
    const azR = p.az * DEG, elR = p.el * DEG;
    const side = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), fdir); if (side.lengthSq() < 1e-6) side.set(1, 0, 0); side.normalize();
    const dirH = fdir.clone().multiplyScalar(Math.cos(azR)).add(side.multiplyScalar(Math.sin(azR))); dirH.y = 0; dirH.normalize();
    const pos = L.clone().add(dirH.multiplyScalar(r * Math.cos(elR))).add(new THREE.Vector3(0, r * Math.sin(elR), 0));
    if (pos.y < 0.6) pos.y = 0.6;
    cam.position.copy(pos); cam.lookAt(L); cam.rotateZ(p.roll * DEG); cam.fov = p.fov; cam.updateProjectionMatrix();
  }
  // impact style "frame": the frame built from the scene — pass A the subjects as a mask, pass B the effect's energy over
  // black, then the composite (the drawing). The result goes to the screen, the metrics target and the record target.
  blitFrame() { // the composed frame from the cache to the screen, the metrics target and the record target
    const r = this.renderer; r.outputColorSpace = THREE.LinearSRGBColorSpace;
    if (!this.blitMat) this.blitMat = new THREE.ShaderMaterial({ uniforms: { tex: { value: null } }, depthTest: false, depthWrite: false,
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tex; varying vec2 vUv; void main(){ gl_FragColor = texture2D(tex, vUv); }" });
    this.blitMat.uniforms.tex.value = this.rtFrame.texture; this.postMesh.material = this.blitMat;
    r.setRenderTarget(null); r.render(this.postScene, this.postCam);
    r.setRenderTarget(this.rtMetrics); r.render(this.postScene, this.postCam); r.setRenderTarget(null); this.sampleMetrics();
    if (this.record) {
      if (!this.rtFinal) this.rtFinal = new THREE.WebGLRenderTarget(this.canvas.width, this.canvas.height, { type: THREE.UnsignedByteType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
      r.setRenderTarget(this.rtFinal); r.render(this.postScene, this.postCam); r.setRenderTarget(null);
    }
  }
  warmFrame() { // compile the frame composite + the blit once, off-screen, so the first impact frame does not stall
    if (!this.warmFrameShaders) return; this.warmFrameShaders = false;
    const r = this.renderer; const u = this.frameMat.uniforms; u.sil.value = this.rtA.texture; u.energy.value = this.rtScene.texture; u.lines.value = this.rtA.texture; u.textTex.value = this.rtA.texture;
    for (const [lm, tx] of [[1, 0], [2, 1], [5, 1], [4, 0]]) { u.linesMode.value = lm; u.textOn.value = tx; u.smoke.value = 1; u.segN.value = 1; u.speckN.value = 1; u.star.value = 1; this.postMesh.material = this.frameMat; r.setRenderTarget(this.rtMetrics); r.render(this.postScene, this.postCam); }
    u.smoke.value = 0; u.segN.value = 0; u.speckN.value = 0; u.textOn.value = 0; r.setRenderTarget(null);
  }
  drawComic() { // impact style "comic": the real lit scene printed as a comic page (panels, halftone, spot inks, action lines, an SFX balloon)
    this.frameSubject = null; // (review 2026-10-25) a comic frame measures no subject: no stale sf from an earlier frame
    const r = this.renderer, f = this.frame, s = this.scene, C = f.comic;
    const cp = this.camera.position; const W = this.canvas.width, H = this.canvas.height;
    const ft = this.frameTime == null ? this.time : this.frameTime;
    const key = `${f.name}|${this.view}|${Math.floor(ft * 24)}|${W}x${H}|${cp.x.toFixed(1)},${cp.y.toFixed(1)},${cp.z.toFixed(1)}|comic`;
    if (this.rtFrame && (this.rtFrame.width !== W || this.rtFrame.height !== H)) { this.rtFrame.dispose(); this.rtFrame = null; this.frameKey = null; }
    if (!this.rtFrame) this.rtFrame = new THREE.WebGLRenderTarget(W, H, { type: THREE.UnsignedByteType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    if (this.frameKey === key) { this.blitFrame(); return; }
    if (!this.comicMat) this.comicMat = new THREE.ShaderMaterial({ depthTest: false, depthWrite: false,
      uniforms: { scene: { value: null }, word: { value: null }, aspect: { value: 1 }, focus: { value: new THREE.Vector2(0.5, 0.5) }, focus2: { value: new THREE.Vector2(0.5, 0.5) },
        paper: { value: new THREE.Color() }, ink: { value: new THREE.Color() }, spot: { value: new THREE.Color() }, spot2: { value: new THREE.Color() }, wordColor: { value: new THREE.Color() }, balloonColor: { value: new THREE.Color() },
        panels: { value: 1 }, slant: { value: 0 }, zoom: { value: new THREE.Vector3(1, 1, 1) }, cell: { value: 0.012 }, misreg: { value: 0.004 }, linesMode: { value: 1 },
        wordOn: { value: 0 }, wordPos: { value: new THREE.Vector2(0.5, 0.5) }, wordSize: { value: 0.3 }, wordRot: { value: 0 }, balloon: { value: 0 }, invert: { value: 0 },
        seed: { value: 1 }, px: { value: new THREE.Vector2(1 / W, 1 / H) }, push: { value: 1 }, shakeOff: { value: new THREE.Vector2() },
        mask: { value: null }, expose: { value: 1.6 }, skyTone: { value: new THREE.Color(0.55, 0.75, 1.0) } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: COMIC_FS });
    const noFrame = this.noFrameObjects(); // `frames: false` layers stay out of comic / anime frames too
    const saved = []; for (const o of s.children) { if (o.isLine || o.isLineSegments || noFrame.has(o)) { saved.push([o, o.visible]); o.visible = false; } }
    const cam = this.camera; const camSaved = { pos: cam.position.clone(), quat: cam.quaternion.clone(), fov: cam.fov };
    const data = this.frameData(f);
    if (f.camera && f.camera !== "none") this.frameCamera(f, data);
    const reforced = []; if (f.camera && f.camera !== "none") for (const l of this.layers) if (l.forcedRemake && l.mesh && l.mesh.visible) { reforced.push([l.mesh, l.mesh.matrix.clone()]); l.mesh.matrix.copy(l.forcedRemake(cam.position)); } // (a forced layer at THIS camera's size)
    const lin = (c) => c.clone().convertSRGBToLinear();
    r.outputColorSpace = THREE.LinearSRGBColorSpace; r.setClearColor(0x000000, 1);
    r.setRenderTarget(this.rtScene); r.clear(); r.render(s, cam);
    // the object mask: the same shot without the backdrop (sky, floor, decals, the moon): what is drawn vs the empty page
    // (an InstancedMesh is never backdrop: a swarm's Ball particles are SphereGeometry and were erased from every frame -
    // ember_murmuration's embers, 2026-10-24)
    const hid = []; for (const o of s.children) { const gt = o.geometry && o.geometry.type; if (o.visible && !o.isInstancedMesh && (gt === "PlaneGeometry" || gt === "SphereGeometry" || gt === "CircleGeometry")) { hid.push(o); o.visible = false; } }
    const bg = s.background, fogD = s.fog ? s.fog.density : 0; s.background = null; if (s.fog) s.fog.density = 0;
    if (!this.rtMask || this.rtMask.width !== W >> 1) { if (this.rtMask) this.rtMask.dispose(); this.rtMask = new THREE.WebGLRenderTarget(W >> 1, H >> 1, { type: THREE.HalfFloatType }); }
    r.setRenderTarget(this.rtMask); r.clear(); r.render(s, cam);
    for (const o of hid) o.visible = true; s.background = bg; if (s.fog) s.fog.density = fogD;
    const u = this.comicMat.uniforms; u.scene.value = this.rtScene.texture; u.mask.value = this.rtMask.texture; u.expose.value = C.expose;
    if (!C.anime) u.skyTone.value.copy(lin(C.skyTone)); u.aspect.value = W / H; u.px.value.set(1 / W, 1 / H);
    const toUv = (p) => { const v = p.clone().project(cam); return [(v.x + 1) / 2, (v.y + 1) / 2]; };
    const f1 = toUv(this.worldPoint(f.focus)); u.focus.value.set(f1[0], f1[1]);
    const f2 = f.focus2 != null ? toUv(this.worldPoint(f.focus2)) : f1; u.focus2.value.set(f2[0], f2[1]);
    if (!C.anime) for (const k of ["paper", "ink", "spot", "spot2", "wordColor", "balloonColor"]) u[k].value.copy(lin(C[k]));
    if (!C.anime) { u.panels.value = C.panels; u.slant.value = C.slant * DEG; u.zoom.value.set(C.zoom[0], C.zoom[1], C.zoom[2]); u.cell.value = C.halftone; u.misreg.value = C.misreg; }
    if (!C.anime) { u.linesMode.value = C.lines; u.balloon.value = C.balloon ? 1 : 0; u.invert.value = C.invert ? 1 : 0; u.push.value = C.push; }
    u.seed.value = Math.floor(ft * 24) + 1; const sk = C.shake || 0; u.shakeOff.value.set((Math.sin(ft * 157.0) * 0.5) * sk, (Math.cos(ft * 131.0) * 0.5) * sk);
    u.wordOn.value = C.word ? 1 : 0; if (C.word) { u.word.value = C.word; u.wordPos.value.set(C.wordPos[0], C.wordPos[1]); u.wordSize.value = C.wordSize; u.wordRot.value = C.wordRot * DEG; } else u.word.value = this.rtA.texture;
    if (C.anime) { // the anime cut-in: its own shader over the same scene render + mask
      if (!this.animeMat) this.animeMat = new THREE.ShaderMaterial({ depthTest: false, depthWrite: false,
        uniforms: { scene: { value: null }, mask: { value: null }, aspect: { value: 1 }, focus: { value: new THREE.Vector2(0.5, 0.5) }, px: { value: new THREE.Vector2() },
          look: { value: 0 }, shadowC: { value: new THREE.Color() }, lightC: { value: new THREE.Color() }, hatchC: { value: new THREE.Color() }, energyC: { value: new THREE.Color() },
          coreC: { value: new THREE.Color() }, edgeC: { value: new THREE.Color() }, linesC: { value: new THREE.Color() }, zoom: { value: 1 }, linesK: { value: 1 }, coreSize: { value: 0.18 },
          expose: { value: 2.2 }, seed: { value: 1 } },
        vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }", fragmentShader: ANIME_FS });
      const a = this.animeMat.uniforms; a.scene.value = this.rtScene.texture; a.mask.value = this.rtMask.texture; a.aspect.value = W / H; a.px.value.set(1 / W, 1 / H);
      a.focus.value.copy(u.focus.value); a.look.value = C.look; a.zoom.value = C.zoom; a.linesK.value = C.linesK; a.coreSize.value = C.coreSize; a.expose.value = C.expose; a.seed.value = Math.floor(ft * 24) + 1;
      for (const [k2, v] of [["shadowC", C.shadow], ["lightC", C.light], ["hatchC", C.hatch], ["energyC", C.energy], ["coreC", C.core], ["edgeC", C.edge], ["linesC", C.lines]]) a[k2].value.copy(lin(v));
      this.postMesh.material = this.animeMat;
    } else this.postMesh.material = this.comicMat;
    r.setRenderTarget(this.rtFrame); r.render(this.postScene, this.postCam); r.setRenderTarget(null); this.frameKey = key;
    for (const [o, v] of saved) o.visible = v;
    for (const [mesh, mx] of reforced) mesh.matrix.copy(mx);
    cam.position.copy(camSaved.pos); cam.quaternion.copy(camSaved.quat); cam.fov = camSaved.fov; cam.updateProjectionMatrix();
    this.blitFrame();
  }
  drawFrame() {
    const r = this.renderer, f = this.frame, s = this.scene;
    const cp = this.camera.position; const W = this.canvas.width, H = this.canvas.height;
    const ft = this.frameTime == null ? this.time : this.frameTime;
    const key = `${f.name}|${this.view}|${Math.floor(ft * 24)}|${W}x${H}|${cp.x.toFixed(1)},${cp.y.toFixed(1)},${cp.z.toFixed(1)}`;
    if (this.rtFrame && (this.rtFrame.width !== W || this.rtFrame.height !== H)) { this.rtFrame.dispose(); this.rtFrame = null; this.frameKey = null; }
    if (!this.rtFrame) this.rtFrame = new THREE.WebGLRenderTarget(W, H, { type: THREE.UnsignedByteType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    if (this.frameKey === key) { this.blitFrame(); return; } // the clock stands still on a held frame: draw it once
    const saved = []; const sil = []; const energy = [];
    // a layer with `frames: false` stays out of the impact frames (2026-10-25: quenchstrike's heat-shimmer dome and water ring
    // inked as a giant dark dome over the strike, and took the subject camera's box)
    const noFrame = this.noFrameObjects();
    for (const o of s.children) {
      saved.push([o, o.visible]);
      if (noFrame.has(o)) { o.visible = false; continue; }
      if (o === this.actor.group) { if (!o.userData.hidden) sil.push(o); continue; }
      if (o.isLight) continue; // lights stay: hiding them changes every lit material's program (a hitch on the way back)
      if (o.isLine || o.isLineSegments) { o.visible = false; continue; }
      // a swarm (InstancedMesh) is never backdrop: its lit rocks are ink figures, its Neon embers are energy (both were
      // erased - Ball swarms as "sky spheres", Block swarms as non-debris boxes: ember_murmuration, gravity_lance 2026-10-24)
      if (o.isInstancedMesh) { if (o.material && o.material.isMeshLambertMaterial) sil.push(o); else energy.push(o); continue; }
      const gt = o.geometry && o.geometry.type;
      if (gt === "PlaneGeometry" || gt === "SphereGeometry" || gt === "CircleGeometry") { o.visible = false; continue; } // floor, sky, moon, decals, the contact shadow: paper
      if (gt === "BoxGeometry" && o.material && o.material.isMeshLambertMaterial) { if (f.subject === "all" || o.userData.debris) sil.push(o); else o.visible = false; continue; }
      energy.push(o);
    }
    const cam = this.camera; const camSaved = { pos: cam.position.clone(), quat: cam.quaternion.clone(), fov: cam.fov };
    const data = this.frameData(f);
    if (f.draw.semantic) { // the beams and tubes are drawn as wedges from their axes: their renders leave the energy pass
      const drawn = new Set(); for (const l of this.layers) { if (l.strips) for (const st of l.strips) drawn.add(st.mesh); if (l.native && l.mesh) drawn.add(l.mesh); }
      for (let i = energy.length - 1; i >= 0; i--) if (drawn.has(energy[i])) { energy[i].visible = false; energy.splice(i, 1); }
    }
    if (f.camera === "subject") this.frameOnSubject(f, energy, sil);
    else if (f.camera && f.camera !== "none") this.frameCamera(f, data);
    const reforced = []; if (f.camera && f.camera !== "none") for (const l of this.layers) if (l.forcedRemake && l.mesh && l.mesh.visible) { reforced.push([l.mesh, l.mesh.matrix.clone()]); l.mesh.matrix.copy(l.forcedRemake(cam.position)); } // (a forced layer at THIS camera's size)
    // how much of the frame its subject fills (the box's larger half span in NDC: 1 = edge to edge), whatever the camera
    const sm = this.subjectMask(energy, sil); this.frameSubject = { fill: sm ? +Math.max(sm.hx, sm.hy).toFixed(3) : 0, share: sm ? +sm.share.toFixed(3) : 0 };
    const lin = (c) => c.clone().convertSRGBToLinear();
    // the fog stays an object with density 0 (removing it would switch every material to its fog-less program
    // variant and back: a ~500 ms hitch on the first normal frame after the sequence)
    const prevOverride = s.overrideMaterial, prevBg = s.background, prevFog = s.fog, prevDensity = s.fog ? s.fog.density : 0; s.background = null; if (s.fog) s.fog.density = 0;
    r.outputColorSpace = THREE.LinearSRGBColorSpace;
    for (const o of energy) o.visible = false; for (const o of sil) o.visible = true;
    // an instanced swarm's per-particle colours multiply even an override material: grey rocks drew their white ink at
    // ~0.36, under the 0.5 ink threshold, and vanished (gravity_lance's frozen rubble) - drop them for the ink pass
    const instCol = sil.filter((o) => o.isInstancedMesh && o.instanceColor).map((o) => [o, o.instanceColor]); for (const [o] of instCol) o.instanceColor = null;
    s.overrideMaterial = this.inkMat; this.inkMat.color.setRGB(1, 1, 1);
    r.setClearColor(0x000000, 1); r.setRenderTarget(this.rtA); r.clear(); r.render(s, cam);
    for (const [o, c] of instCol) o.instanceColor = c;
    for (const o of sil) o.visible = false; for (const [o, v] of saved) if (energy.includes(o)) o.visible = v;
    s.overrideMaterial = null; r.setClearColor(0x000000, 1); r.setRenderTarget(this.rtScene); r.clear(); r.render(s, cam);
    const u = this.frameMat.uniforms; u.sil.value = this.rtA.texture; u.energy.value = this.rtScene.texture; u.paper.value.copy(lin(f.paper)); u.ink.value.copy(lin(f.ink)); u.hot.value.copy(lin(f.hot)); u.mark.value.copy(lin(f.mark)); u.linesColor.value.copy(lin(f.linesColor));
    const dw = f.draw; u.seed.value = dw.boil ? Math.floor(ft * 24) + 1 : 1; u.warp.value = dw.warp; u.grow.value = dw.grow; u.smear.value = dw.smear; u.outline.value = dw.outline; u.hatch.value = dw.hatch; u.splatter.value = dw.splatter; u.zoom.value = dw.zoom; u.shake.value = dw.shake; u.flash.value = dw.flash; u.lineart.value = dw.lineart ? 1 : 0; u.rim.value = dw.rim; u.soot.value = dw.soot; u.mass.value = dw.mass;
    u.hotT.value = f.hotT; u.markT.value = f.markT; u.linesMode.value = f.linesMode; u.lines.value = f.lines; u.linesScale.value = f.linesScale; u.linesStrength.value = f.linesStrength; u.hole.value = f.hole; u.aspect.value = this.canvas.width / this.canvas.height;
    const fp = this.worldPoint(f.focus).project(cam); u.focus.value.set((fp.x + 1) / 2, (fp.y + 1) / 2);
    const toUv = (p) => { const v = p.clone().project(cam); return v.z < 1 && v.z > -1 ? [(v.x + 1) / 2, (v.y + 1) / 2] : null; };
    let ns = 0; for (const x of data.axes) { const a = toUv(x.a), b = toUv(x.b); if (!a || !b || ns >= 4) continue; u.segs.value[ns].set(a[0], a[1], b[0], b[1]);
      const mid = x.a.clone().lerp(x.b, 0.15); const dcam = cam.position.distanceTo(mid); u.segW.value[ns] = Math.min(0.25, Math.max(0.012, (x.w * 1.2) / (2 * dcam * Math.tan(cam.fov * DEG / 2)))); ns++; }
    u.segN.value = ns; let np = 0; for (const p of data.pts) { const v = toUv(p); if (!v || np >= 48) continue; u.specks.value[np].set(v[0], v[1]); np++; } u.speckN.value = np;
    u.wedge.value = dw.abstract ? 0 : dw.wedge; u.star.value = dw.star; u.voidK.value = dw.void; u.crackK.value = dw.crack; u.boltsK.value = dw.bolts; u.speckK.value = dw.abstract ? 0 : dw.specks; u.smoke.value = dw.smoke; u.abstractK.value = dw.abstract ? 1 : 0;
    // the cut on screen: its centreline extended past both tips along their tangents (zero width there) so the line
    // divides the frame; the stroke's half-width = half the projected band (at least a hair), 0 where hidden
    let cn = 0; let cutMids = null; let cutWs = [];
    if (data.cut && (dw.slash > 0 || dw.split > 0 || f.linesMode === 6 || dw.cutSmear > 0)) {
      const A = this.canvas.width / this.canvas.height, Q = (v) => new THREE.Vector2(v[0] * A, v[1]);
      const P = data.cut.pts.map((c) => ({ m: toUv(c.mid), lo: toUv(c.lo), hi: toUv(c.hi), vis: c.vis })).filter((c) => c.m);
      if (P.length >= 2) {
        const mids = P.map((c) => Q(c.m)), ws = P.map((c) => (c.vis && c.lo && c.hi ? Math.max(0.006, Q(c.lo).distanceTo(Q(c.hi)) / 2) : 0));
        const n = mids.length, t0 = mids[0].clone().sub(mids[1]).normalize(), t1 = mids[n - 1].clone().sub(mids[n - 2]).normalize();
        const ext = [mids[0].clone().addScaledVector(t0, 3), ...mids, mids[n - 1].clone().addScaledVector(t1, 3)], wx = [0, ...ws, 0];
        cn = Math.min(24, ext.length); for (let i = 0; i < cn; i++) { u.cutPts.value[i].set(ext[i].x / A, ext[i].y); u.cutW.value[i] = wx[i]; }
        u.cutDir.value.set(1, 0); const dir = mids[n - 1].clone().sub(mids[0]); if (dir.lengthSq() > 1e-8) u.cutDir.value.copy(dir.normalize());
        cutMids = P.map((c, i) => (ws[i] > 0 ? c.m : null)).filter(Boolean); cutWs = ws.filter((x) => x > 0);
      }
    }
    if (!cn) u.cutDir.value.set(1, 0); // no arc this frame: cut lines run level, nothing is smeared along a stale cut
    u.flareK.value = dw.flare; u.selectiveK.value = dw.selective; u.cutN.value = cn; u.slashK.value = dw.slash; u.splitK.value = dw.split; u.splitSlide.value = dw.slide; u.cutSmearK.value = cn ? dw.cutSmear : 0;
    u.hasVanish.value = 0; if (data.axes.length) { const vp = toUv(data.axes[0].b); if (vp) { u.vanish.value.set(vp[0], vp[1]); u.hasVanish.value = 1; } }
    u.textOn.value = f.text && f.text.tex ? 1 : 0; if (f.text && f.text.tex) { u.textTex.value = f.text.tex; u.textSize.value = f.text.size; u.textRot.value = f.text.rot * DEG; u.textColor.value.copy(lin(f.text.color));
      const tp = f.text.at === "center" ? [0.5, 0.56] : f.text.at === "band" ? [0.5, u.focus.value.y < 0.5 ? 0.7 : 0.3] : (f.text.at ? toUv(this.worldPoint(f.text.at)) : null);
      u.textPos.value.set(tp ? tp[0] : u.focus.value.x, tp ? ((f.text.at === "center" || f.text.at === "band") ? tp[1] : Math.min(0.78, tp[1] + 0.22)) : Math.min(0.78, u.focus.value.y + 0.22));
      u.textStretch.value = f.text.stretch; u.textSquash.value = f.text.squash; u.textOffset.value = f.text.offset; u.bandOn.value = f.text.band ? 1 : 0; u.bandLines.value = f.text.bandLines; u.bandColor.value.copy(lin(f.text.bandColor));
      u.textSplit.value = f.text.split; u.textGlint.value = f.text.glint; u.textTrail.value = f.text.trail; u.textMid.value = f.text.mid; u.accentColor.value.copy(lin(f.hot)); u.bandOffset.value = f.text.bandOffset;
      u.rough.value = f.text.rough; u.drips.value = f.text.drips; u.blood.value.copy(lin(f.text.blood)); u.spin.value = f.text.spin * DEG;
      u.distort.value = f.text.distort; u.fTime.value = ft; u.spot.value = f.text.spot; u.reveal.value = f.text.reveal;
      u.claws.value = f.text.claws; u.clawSpacing.value = f.text.clawSpacing; u.jag.value = f.text.jag; u.shatter.value = f.text.shatter; u.crawl.value = f.text.crawl;
      u.coverOn.value = f.text.cover ? 1 : 0; u.cutAngle.value = f.text.cutAngle * DEG; u.sliceGap.value = f.text.gap; u.sliceSlide.value = f.text.slide; u.cutFlash.value = f.text.cutFlash;
      const cp2 = f.text.cardColor; u.cardPaper.value.copy(lin(cp2)); const lum = cp2.r * 0.3 + cp2.g * 0.59 + cp2.b * 0.11; u.cardInk.value.set(lum > 0.5 ? 0 : 1, lum > 0.5 ? 0 : 1, lum > 0.5 ? 0 : 1); }
    else u.coverOn.value = 0;
    this.postMesh.material = this.frameMat;
    r.setRenderTarget(this.rtFrame); r.render(this.postScene, this.postCam); r.setRenderTarget(null); this.frameKey = key;
    // the proof the frame DRAWS the cut (frames_draw_cut), by a CONTROL: the same frame drawn again with the stroke off
    // (slash 0, everything else identical) and both read across the cut where the zoom punch puts it. Only the stroke
    // differs between the two, so a pixel that CHANGED is the stroke - the arc's own glow, the split's inverted half or
    // the paper can never pass for it (two reviews broke every colour rule). Only for a frame that asks for the stroke.
    this.cutCheck = null;
    if (dw.slash > 0 && cutMids && cutMids.length > 2) {
      if (!this.rtFrameCtl || this.rtFrameCtl.width !== W || this.rtFrameCtl.height !== H) { if (this.rtFrameCtl) this.rtFrameCtl.dispose(); this.rtFrameCtl = new THREE.WebGLRenderTarget(W, H, { type: THREE.UnsignedByteType }); }
      u.slashK.value = 0; r.setRenderTarget(this.rtFrameCtl); r.render(this.postScene, this.postCam); r.setRenderTarget(null); u.slashK.value = dw.slash;
      const pa = new Uint8Array(4), pb = new Uint8Array(4), zoom = dw.zoom, F2 = u.focus.value, A = W / H;
      const changed = (x, y) => { if (x < 0.01 || x > 0.99 || y < 0.01 || y > 0.99) return null; const X = Math.floor(x * W), Y = Math.floor(y * H);
        r.readRenderTargetPixels(this.rtFrame, X, Y, 1, 1, pa); r.readRenderTargetPixels(this.rtFrameCtl, X, Y, 1, 1, pb);
        return Math.abs(pa[0] - pb[0]) + Math.abs(pa[1] - pb[1]) + Math.abs(pa[2] - pb[2]) > 60; };
      const toScreen = (m) => [F2.x + (m[0] - F2.x) / (1 - zoom), F2.y + (m[1] - F2.y) / (1 - zoom)]; // where the zoom punch draws m
      let on = 0, n = 0;
      for (let i = 1; i < cutMids.length - 1; i++) {
        const m = toScreen(cutMids[i]), a = toScreen(cutMids[i - 1]), b = toScreen(cutMids[i + 1]);
        let tx = (b[0] - a[0]) * A, ty = b[1] - a[1]; const tl = Math.hypot(tx, ty) || 1; tx /= tl; ty /= tl;
        const w = Math.max(0.004, (cutWs[i] || 0.006) * dw.slash) / (1 - zoom), nx = -ty / A, ny = tx;
        // across the stroke (the hand warp moves a drawn line ~1-2 % of the screen): any CHANGED pixel within the half-width
        const probes = [0, 0.3, -0.3, 0.6, -0.6, 0.9, -0.9].map((k) => changed(m[0] + nx * k * w, m[1] + ny * k * w)).filter((v) => v !== null);
        if (!probes.length) continue; n++;
        if (probes.some(Boolean)) on++;
      }
      this.cutCheck = { frame: f.name, on: n ? +(on / n).toFixed(2) : 0, samples: n };
    }
    for (const [o, v] of saved) o.visible = v; s.overrideMaterial = prevOverride; s.background = prevBg; s.fog = prevFog; if (s.fog) s.fog.density = prevDensity;
    for (const [mesh, mx] of reforced) mesh.matrix.copy(mx);
    cam.position.copy(camSaved.pos); cam.quaternion.copy(camSaved.quat); cam.fov = camSaved.fov; cam.updateProjectionMatrix();
    this.blitFrame();
  }
  drawLens() { // the lens layers' overlays, back to front (zoom, fringe, dirt, vignette)
    const all = (this.lensOverlays || []).slice(), A = this.canvas.width / Math.max(this.canvas.height, 1);
    for (const fl of this.lensFlares || []) { // a flare's marks, from where its light falls on the screen NOW
      this.camera.updateMatrixWorld(); const v = fl.at.clone();
      if (!(A > 0) || v.clone().applyMatrix4(this.camera.matrixWorldInverse).z >= 0) continue; // behind the camera: nothing
      v.project(this.camera);
      for (const m of flareMarks((v.x + 1) / 2, (1 - v.y) / 2, A, fl.f)) { const tex = texture(this.bundle, m.kind === 1 ? "lens_glow" : m.kind === 2 ? "lens_streak" : "lens_ghost");
        if (tex) all.push({ tex, alpha: Math.max(0, Math.min(1, m.a * fl.s)), tint: colorAt(fl.f.color || [255, 240, 220], m.c, this.palette), scale: 1, z: 5, rot: 0, offset: [2 * m.x - 1, 1 - 2 * m.y], stretch: [m.w / A, m.h] }); } }
    const list = all.filter((o) => o.alpha > 0.001 && o.tex); if (!list.length) return;
    const r = this.renderer, u = this.lensMat.uniforms; r.autoClear = false;
    for (const o of list.sort((a, b) => a.z - b.z)) { u.tex.value = o.tex; u.alpha.value = Math.min(o.alpha, 1); u.tint.value.copy(o.tint); u.scale.value = o.scale; u.rot.value = o.rot || 0; u.offset.value.set((o.offset || [0, 0])[0], (o.offset || [0, 0])[1]); u.aspect.value = this.canvas.width / this.canvas.height; u.squareK.value = o.square ? 1 : 0; u.uvOff.value = o.uvOff || 0; u.stretch.value.set((o.stretch || [1, 1])[0], (o.stretch || [1, 1])[1]); /* (a flare's mark: its own width and height, shares of the screen) */ if (o.square) o.tex.wrapS = THREE.RepeatWrapping; r.render(this.lensScene, this.postCam); }
    r.autoClear = true;
  }
  draw() {
    if (this.warmFrameShaders) this.warmFrame();
    if (!this.frame) this.cutCheck = null;
    if (this.frame) { if (this.frame.comic) this.drawComic(); else this.drawFrame(); return; }
    const r = this.renderer; r.outputColorSpace = THREE.LinearSRGBColorSpace;
    r.setRenderTarget(this.rtScene); r.clear(); r.render(this.scene, this.camera);
    this.postMesh.material = this.threshMat; this.threshMat.uniforms.tex.value = this.rtScene.texture; this.threshMat.uniforms.threshold.value = 1.0 / (1 + this.post.bloom * 0.8);
    r.setRenderTarget(this.rtA); r.render(this.postScene, this.postCam);
    this.postMesh.material = this.blurMat; this.blurMat.uniforms.tex.value = this.rtA.texture; this.blurMat.uniforms.dir.value.set(1, 0); r.setRenderTarget(this.rtB); r.render(this.postScene, this.postCam);
    this.blurMat.uniforms.tex.value = this.rtB.texture; this.blurMat.uniforms.dir.value.set(0, 1); r.setRenderTarget(this.rtA); r.render(this.postScene, this.postCam);
    // SCREEN BLUR (R1 2026-10-23; it was tracked, never drawn): the whole frame blurred like Roblox's BlurEffect - `blur` is
    // its Size (pixels, 0-56): the kernel spreads with it and the blurred copy takes over the frame by ~Size 12
    const blurSize = Math.max(0, this.post.blur), dofK = Math.min(1, Math.max(0, this.world.dof || 0));
    if (blurSize > 0.05 || dofK > 0.001) {
      // repeated SMALL passes (spread 1.5) instead of one wide kernel: a spread over ~2 drew ghost copies (review 3)
      const passes = Math.max(1, Math.min(6, Math.ceil(Math.max(blurSize, dofK * 24) / 8))); this.blurMat.uniforms.spread.value = 1.5;
      let src = this.rtScene.texture;
      for (let k = 0; k < passes; k++) {
        this.blurMat.uniforms.tex.value = src; this.blurMat.uniforms.dir.value.set(1, 0); r.setRenderTarget(this.rtC); r.render(this.postScene, this.postCam);
        this.blurMat.uniforms.tex.value = this.rtC.texture; this.blurMat.uniforms.dir.value.set(0, 1); r.setRenderTarget(this.rtD); r.render(this.postScene, this.postCam);
        src = this.rtD.texture; }
      this.blurMat.uniforms.spread.value = 2.0;
    }
    this.postMesh.material = this.finalMat; const u = this.finalMat.uniforms; u.tex.value = this.rtScene.texture; u.bloom.value = this.rtA.texture; u.bloomK.value = 0.9 + this.post.bloom;
    u.blurTex.value = this.rtD.texture; u.blurMix.value = Math.min(1, blurSize / 12);
    u.depthTex.value = this.rtScene.depthTexture; u.camNear.value = this.camera.near; u.camFar.value = this.camera.far; u.dofK.value = dofK; u.dofFocus.value = this.world.dofFocus || 30; u.dofRadius.value = 30;
    u.brightness.value = this.post.brightness; u.contrast.value = this.post.contrast; u.saturation.value = this.post.saturation; u.tint.value.copy(this.post.tint);
    r.setRenderTarget(null); r.render(this.postScene, this.postCam);
    if (this.plate) { // a drawn impact plate over the whole frame (cover-fit: the picture's centre fills the view)
      const img = this.plate.tex.image; const ia = img && img.width ? img.width / img.height : 1, ca = this.canvas.width / this.canvas.height;
      const u = this.plateMat.uniforms; u.tex.value = this.plate.tex; u.alpha.value = this.plate.alpha;
      if (ca > ia) { u.uvScale.value.set(1, ia / ca); u.uvOff.value.set(0, (1 - ia / ca) / 2); } else { u.uvScale.value.set(ca / ia, 1); u.uvOff.value.set((1 - ca / ia) / 2, 0); }
      r.autoClear = false; r.render(this.plateScene, this.postCam); r.autoClear = true;
    }
    this.drawLens();
    // metrics: a 64x36 read-back of the final frame
    r.setRenderTarget(this.rtMetrics); r.render(this.postScene, this.postCam); if (this.plate) { r.autoClear = false; r.render(this.plateScene, this.postCam); r.autoClear = true; } this.drawLens(); r.setRenderTarget(null);
    this.sampleMetrics();
    if (this.record) { // record mode: the frame is read back from our own target (a hidden tab's screen buffer stops updating — measured: 40 identical frames)
      if (!this.rtFinal) this.rtFinal = new THREE.WebGLRenderTarget(this.canvas.width, this.canvas.height, { type: THREE.UnsignedByteType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
      r.setRenderTarget(this.rtFinal); r.render(this.postScene, this.postCam); if (this.plate) { r.autoClear = false; r.render(this.plateScene, this.postCam); r.autoClear = true; } this.drawLens(); r.setRenderTarget(null); // the lens too (review 3: recordings never showed it)
    }
  }
  capturePng() { return this.captureJpeg(1, "image/png"); }
  captureJpeg(quality = 0.92, type = "image/jpeg") { // the current frame as a JPEG data url, independent of the page's visibility
    const w = this.canvas.width, h = this.canvas.height;
    if (!this.rtFinal) return this.canvas.toDataURL(type, quality);
    const buf = this.captureBuf || (this.captureBuf = new Uint8Array(w * h * 4));
    this.renderer.readRenderTargetPixels(this.rtFinal, 0, 0, w, h, buf);
    if (!this.capCanvas) { this.capCanvas = document.createElement("canvas"); this.capCanvas.width = w; this.capCanvas.height = h; this.capCtx = this.capCanvas.getContext("2d"); this.capImg = this.capCtx.createImageData(w, h); }
    const d = this.capImg.data, row = w * 4; // WebGL rows run bottom-up
    for (let y = 0; y < h; y++) d.set(buf.subarray((h - 1 - y) * row, (h - y) * row), y * row);
    for (let i = 3; i < d.length; i += 4) d[i] = 255;
    this.capCtx.putImageData(this.capImg, 0, 0);
    return this.capCanvas.toDataURL(type, quality);
  }
  sampleMetrics() {
    const buf = this.metricsBuf || (this.metricsBuf = new Uint8Array(64 * 36 * 4));
    this.renderer.readRenderTargetPixels(this.rtMetrics, 0, 0, 64, 36, buf);
    let sum = 0, bright = 0, hot = 0; const hues = new Array(12).fill(0); let lit = 0;
    for (let i = 0; i < 64 * 36; i++) { const R = buf[i * 4], G = buf[i * 4 + 1], B = buf[i * 4 + 2]; const mx = Math.max(R, G, B), mn = Math.min(R, G, B); const l = (R + G + B) / 3; sum += l; if (mx > 110) { bright++; if (mx - mn > 40) { lit++; let h; if (mx === R) h = ((G - B) / (mx - mn)) % 6; else if (mx === G) h = (B - R) / (mx - mn) + 2; else h = (R - G) / (mx - mn) + 4; hues[((Math.round(h * 2) % 12) + 12) % 12]++; } } if (mn > 235) hot++; }
    const n = 64 * 36;
    // FOCAL POINT (R5 2026-10-23, the research's "a clear focal point, readable even during intense moments"): the
    // pixels clearly brighter than this view's first frame (the scene before the effect) are the effect; `focal` = the
    // share of them in the LARGEST connected region (1 = one clear shape, low = scattered clutter); fpx = how many
    if (!this.metricsBase || this.time < (this.metricsBaseT == null ? 0 : this.metricsBaseT)) { // a 3x3 max: shake / kick moves edges a pixel or two
      const mx0 = new Uint8Array(n); for (let i = 0; i < n; i++) mx0[i] = Math.max(buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]);
      this.metricsBaseMin = new Uint8Array(n); for (let y = 0; y < 36; y++) for (let x = 0; x < 64; x++) { let m = 255; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < 64 && yy < 36) m = Math.min(m, mx0[yy * 64 + xx]); } this.metricsBaseMin[y * 64 + x] = m; }
      this.metricsBase = new Uint8Array(n); for (let y = 0; y < 36; y++) for (let x = 0; x < 64; x++) { let m = 0; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < 64 && yy < 36) m = Math.max(m, mx0[yy * 64 + xx]); } this.metricsBase[y * 64 + x] = m; } }
    this.metricsBaseT = this.time;
    const on = new Uint8Array(n); let fpx = 0, dpx = 0;
    // dpx (2026-11-10): pixels clearly DARKER than the scene before (a void, ink, a dark core on a day sky) - fpx sees only
    // brighter ones, so a dark strike filling the shot measured as nothing (frames_on_screen reads both)
    for (let i = 0; i < n; i++) { const mx = Math.max(buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]); if (mx > 110 && mx > this.metricsBase[i] + 40) { on[i] = 1; fpx++; } else if (this.metricsBaseMin && mx < this.metricsBaseMin[i] - 40) dpx++; }
    let biggest = 0; const seen = new Uint8Array(n), stack = [];
    for (let i = 0; i < n; i++) { if (!on[i] || seen[i]) continue; let size = 0; stack.push(i); seen[i] = 1;
      while (stack.length) { const j = stack.pop(); size++; const x = j % 64, y = (j / 64) | 0;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= 64 || yy >= 36) continue; const k = yy * 64 + xx; if (on[k] && !seen[k]) { seen[k] = 1; stack.push(k); } } }
      biggest = Math.max(biggest, size); }
    this.frameMetrics = { t: +this.time.toFixed(3), mean: +(sum / n).toFixed(1), coverage: +(bright / n).toFixed(3), hot: +(hot / n).toFixed(3), hues: hues.map((x) => +(x / Math.max(lit, 1)).toFixed(3)), alive: this.alive, cut: this.cutCheck || undefined,
      fpx, dpx, focal: fpx >= 12 ? +(biggest / fpx).toFixed(2) : undefined, sf: this.frame && this.frameSubject ? this.frameSubject.fill : undefined };
  }
}

// ---------------------------------------------------------------- metrics summary + gate
export function summarize(frames, preset, viewName, moving) {
  // a smoothed intensity curve (5-frame mean), its global peak, and every other PROMINENT local peak (rises at
  // least 12% of the global peak above the valley before it, 0.3 s apart) that no declared hit explains
  const raw = frames.map((f) => f.mean);
  const means = raw.map((_, i) => { let s = 0, n = 0; for (let k = -2; k <= 2; k++) { const j = i + k; if (j >= 0 && j < raw.length) { s += raw[j]; n++; } } return s / n; });
  const peakI = means.indexOf(Math.max(...means)); const peak = means[peakI] || 0;
  const hits = preset.hits || (preset.hitstop || []).map((h) => h.at);
  const extraPeaks = [];
  let valley = means[0] || 0;
  for (let i = 1; i < means.length - 1; i++) {
    valley = Math.min(valley, means[i]);
    const isMax = means[i] > means[i - 1] && means[i] >= means[i + 1];
    // a climax FALLS: before anything brighter comes the curve drops 12 % of the peak below it - a held level (a plateau,
    // a blown dome, a charge held into the hit) is no second climax; the clip's END counts as a fall, so a late flare is
    // still caught (review 2026-10-25). Known limit, by choice: a build-up that sags < 12 % and holds into the hit passes
    let after = means[i], j = i + 1;
    // a dip in the 0.4 s before a hit is its WIND-UP (the darkening before a strike), not this bump's fall
    for (; j < means.length && means[j] <= means[i]; j++) if (!hits.some((h) => frames[j].t >= h - 0.4 && frames[j].t < h)) after = Math.min(after, means[j]);
    const falls = j >= means.length || means[i] - after > 0.12 * peak;
    if (isMax && falls && means[i] - valley > 0.12 * peak && i !== peakI) {
      const t = frames[i].t;
      // a bump well below the real hit (a growing charge) is not a second hit: only peaks >= 40% of the peak count
      const explained = hits.some((h) => t >= h - 0.1 && t <= h + 0.7) || Math.abs(frames[peakI].t - t) < 0.7 || means[i] < 0.5 * peak;
      if (!explained && (!extraPeaks.length || t - extraPeaks[extraPeaks.length - 1] > 0.3)) extraPeaks.push(+t.toFixed(2));
      valley = means[i];
    }
    // the rise is measured from the dip since the LAST bump, never from the dark start (orrery 2026-10-25: a 0.3-level
    // plateau wiggle at 1.03, measured from the first frame, read as a second climax; review: reset at every local max)
    if (isMax) valley = means[i];
  }
  const maxCov = Math.max(...frames.map((f) => f.coverage));
  // a declared impact frame (kind "impact") is stylized on purpose (a white-out, a stark black-and-white grade): those
  // moments count neither as blown out nor towards the palette
  const flashWindows = (preset.layers || []).filter((l) => l.kind === "impact").map((l) => [l.at || 0, (l.at || 0) + (l.life || 0.1) + 0.05]);
  const inFlash = (t) => flashWindows.some(([a, b]) => t >= a && t <= b);
  const huePresence = new Array(12).fill(0); for (const f of frames) if (!inFlash(f.t)) f.hues.forEach((v, i) => { huePresence[i] = Math.max(huePresence[i], v); });
  const hueCount = huePresence.filter((v) => v > 0.08).length;
  const maxHot = Math.max(...frames.filter((f) => !inFlash(f.t)).map((f) => f.hot), 0);
  // impact frames are OPTIONAL (the owner, 2026-10-25: "not everything needs impact frame ... you can impress me with the
  // effect itself" - replacing the earlier "a module of every hit" rule): a hit may have none. A sequence a preset DOES have
  // must start ON a hit (else it does not line up with the attack) and every frame sits inside a hitstop
  const frameLayers = (preset.layers || []).filter((l) => l.kind === "impact" && (l.style === "frame" || l.style === "comic" || l.style === "anime" || l.image));
  const stops = preset.hitstop || [];
  const impactHits = stops.length ? stops.map((s) => s.at) : hits; // the hits that hold the clock are the impact moments
  const seqStarts = frameLayers.filter((l) => !frameLayers.some((o) => o !== l && Math.abs((o.at || 0) + (o.life || 0.08) - (l.at || 0)) < 0.011)).map((l) => l.at || 0);
  const framesOffHit = seqStarts.filter((t) => !impactHits.some((h) => t >= h - 0.06 && t <= h + 0.12)).map((t) => +t.toFixed(2));
  const framesOutside = frameLayers.filter((l) => !stops.some((s) => (l.at || 0) >= s.at - 0.06 && (l.at || 0) + (l.life || 0.08) <= s.at + (s.span || s.hold || 0.08) + 0.06)).map((l) => l.name);
  // DISSIPATION (2026-10-23, the owner: "a natural, deliberately animated breakdown rather than simply fading everything
  // out"): in the tail of the effect's visible life (its last 30%), a FADE is the brightness above the scene's own falling
  // by half while the covered area hardly shrinks (opacity alone); a POP is the coverage collapsing in one frame. A
  // breakdown (erode, scatter, shrink, a sweep erasing) takes the coverage down with the light.
  const calm = frames.filter((f) => !inFlash(f.t));
  const base = calm.length ? Math.min(...calm.map((f) => f.mean)) : 0, bgCov = calm.length ? Math.min(...calm.map((f) => f.coverage)) : 0;
  // the EFFECT's footprint: fpx = pixels clearly brighter than the scene before it (R5) - on a bright day sky plain coverage
  // is ~1 on every frame and says nothing; recordings without fpx fall back to coverage minus the static background
  const cov = (f) => (f.fpx != null ? f.fpx / (64 * 36) : Math.max(0, f.coverage - bgCov));
  const live = calm.filter((f) => cov(f) > 0.004);
  let fadeAt = null, popAt = null;
  if (live.length >= 8) {
    const t0 = live[0].t, t1 = live[live.length - 1].t, tail = live.filter((f) => f.t >= t0 + 0.7 * (t1 - t0));
    if (tail.length >= 4) {
      const m0 = Math.max(tail[0].mean - base, 1e-3), c0 = Math.max(cov(tail[0]), 1e-4);
      for (const f of tail) if (fadeAt == null && (f.mean - base) / m0 < 0.5 && cov(f) / c0 > 0.8) fadeAt = +f.t.toFixed(2);
      // the pop is judged on EVERY frame from the tail on (the frame it vanished in has no coverage: not "live")
      const after = calm.filter((f) => f.t >= tail[0].t);
      for (let i = 1; i < after.length; i++) if (popAt == null && cov(after[i - 1]) - cov(after[i]) > 0.6 * c0 && cov(after[i - 1]) > 0.01) popAt = +after[i].t.toFixed(2);
    }
  }
  // FOCAL (R5): in the effect's biggest moments (>= half its peak pixel count, impact frames excluded) the median share
  // of it in one connected region; below 0.45 it is scattered - no clear focal point
  const fx = calm.filter((f) => f.focal != null), fmax = Math.max(0, ...fx.map((f) => f.fpx || 0));
  const big = fx.filter((f) => (f.fpx || 0) >= 0.5 * fmax).map((f) => f.focal).sort((a, b) => a - b);
  const focalMed = big.length ? big[Math.floor(big.length / 2)] : null;
  // STRIKE SNAP (R5, the sakuga rule "prepare long - STRIKE in a frame - relax long"): at each hit the light must climb
  // from 10 % to 90 % of its rise within 0.15 s (3-4 frames at 24); a slow ramp into a hit reads soft
  const slow = [];
  for (const h of hits) {
    // an impact-frame sequence that STARTS on the hit is the strike itself, held on the clock (2026-10-24: with its windows
    // excluded, the first calm frame after a 0.29 s slash sequence was always the "peak", so strike_snap measured the
    // frames' own length - 0.32 s - and no hit with a long frame sequence could pass). The time the frames hide is not
    // counted as rise; everything the camera does see still is
    // (review 2026-10-24: frames are matched with frames_at_hits' own tolerance (-0.06 .. +0.12 s), and the windows stop at
    // the NEXT hit - a framed hit's window reaching into the next hit's rise measured that rise as its own)
    let held = 0;
    const mine = flashWindows.filter(([a]) => a >= h - 0.06 && a <= h + 0.12);
    if (mine.length) {
      let end = Math.min(...mine.map(([a]) => a)); for (const [a, b] of [...flashWindows].sort((x, y) => x[0] - y[0])) if (a <= end + 0.02 && b > end) end = b;
      held = Math.max(0, end - h);
    }
    const nextHit = Math.min(...hits.filter((x) => x > h + 0.02), Infinity), stop = Math.min(h + 0.35 + held, nextHit - 0.02);
    const pre = calm.filter((f) => f.t >= h - 0.4 && f.t <= h - 0.02), post = calm.filter((f) => f.t >= h && f.t <= stop);
    if (pre.length < 2 || post.length < 2) continue;
    const lo = Math.min(...pre.map((f) => f.mean)), hi = Math.max(...post.map((f) => f.mean)); if (hi - lo < 4) continue;
    const ramp = calm.filter((f) => f.t >= h - 0.4 && f.t <= stop);
    const t90 = ramp.find((f) => f.mean >= lo + 0.9 * (hi - lo)); if (!t90) continue;
    const below = ramp.filter((f) => f.t < t90.t && f.mean < lo + 0.1 * (hi - lo)), t10 = below.length ? below[below.length - 1] : null;
    // t10 -> t90 as always, minus ONLY the time the frames actually hide between them (review 2026-10-24: measuring from
    // the frames' end dropped t10 - a slow ramp INTO a framed hit went unmeasured, and a 0.01 s frame bought a slow ramp)
    const hidden = t10 && held > 0 ? Math.max(0, Math.min(t90.t, h + held) - Math.max(t10.t, h)) : 0;
    const late = t10 ? t90.t - t10.t - hidden : 0;
    if (t10 && late > 0.15) slow.push(`${+h.toFixed(2)}: ${+late.toFixed(2)} s` + (hidden > 0 ? ` (+${+hidden.toFixed(2)} s under frames)` : ""));
  }
  // impact frames v4: a frame that strokes the cut must really draw it on the slash's centreline
  const cutFrames = frames.filter((f) => f.cut && f.cut.samples >= 4);
  const cutMiss = [...new Set(cutFrames.filter((f) => f.cut.on < 0.6).map((f) => `${f.cut.frame} ${f.cut.on}`))];
  const cutSeen = [...new Set(cutFrames.map((f) => f.cut.frame))].length;
  // FRAMES FILL (2026-10-25, the owner: "bad impact frames" on five originals - the effect a speck on flat paper): the median
  // share of the frame its subject spans (sf: the drawn mask's larger half span in NDC, 1 = edge to edge) over the drawn frames
  const sfs = frames.filter((f) => f.sf != null).map((f) => f.sf).sort((a, b) => a - b);
  const fillMed = sfs.length ? sfs[Math.floor(sfs.length / 2)] : null;
  const FRAMES_FILL_MIN = 0.2; // calibrated 2026-10-25: starblade (9.5) frames 0.53-0.69, moonflower (7) 0.33, gravity_lance (praised) 0.29 - a floor for the speck, not a bar
  // FRAMES ON SCREEN (2026-11-10, the owner's "bad impact frames" on seam / sandfall / quicksilver / noctiluca, 2026-10-24,
  // and "an impact frame doesn't line up with the attack itself ... set depending on what's happening on my screen",
  // 2026-10-25): a sequence that RE-FRAMES the shot (any frame camera but "none" - the player's default is "closeup") must
  // cut away from a strike the viewer SAW: the live footprint in the second before it >= 3 % of the hero view (the shot
  // the owner watches). Measured on the judged recordings: the four pieces named for bad frames 0.000-0.017 and vortex
  // (5) 0.010; starblade (9.5) 0.43 / 0.13, sumi_seal (praised) 0.058, quenchstrike 0.052. Live-view frames (camera
  // "none") draw the shot itself and are not asked (gravity_lance's dark core on a day sky has no bright footprint).
  // Known limit: the footprint is measured against the view's FIRST frame, so whatever is already on screen at t = 0 is
  // part of the scene, not the strike
  const FRAMES_ON_SCREEN_MIN = 0.03;
  // the hero view, else the booth's first view when it has no hero (review 2026-11-10: side-only / cine-only booths were
  // never asked); the footprint counts dark pixels too (dpx: a void or ink strike), where the recording has them
  const boothViews = ((preset.booth || {}).views || []);
  const askView = !boothViews.length || boothViews.includes("hero") ? "hero" : boothViews[0];
  const onScreenAsked = viewName === askView && !moving;
  const seenCov = (f) => cov(f) + (f.dpx != null ? f.dpx / (64 * 36) : 0);
  const offScreen = [];
  if (onScreenAsked) {
    for (const t0 of seqStarts) {
      const seq = frameLayers.filter((l) => (l.at || 0) >= t0 - 0.011 && (l.at || 0) <= t0 + 0.6);
      if (!seq.some((l) => (l.camera || "closeup") !== "none")) continue;
      const pre = calm.filter((f) => f.t >= t0 - 1.0 && f.t <= t0 - 0.02).map(seenCov);
      const seen = pre.length ? Math.max(...pre) : 0;
      if (seen < FRAMES_ON_SCREEN_MIN) offScreen.push(`${+t0.toFixed(2)}: ${+seen.toFixed(3)}`);
    }
  }
  const checks = [
    { name: "frames_at_hits", ok: framesOffHit.length === 0, value: framesOffHit, limit: "impact frames are optional; a frame sequence starts ON a hit (a hitstop's, else a declared hit)", fix: "move the sequence to its hit's time - or drop it: not every hit needs frames (the owner, 2026-10-25)" },
    { name: "frames_in_hitstop", ok: framesOutside.length === 0, value: framesOutside, limit: "every impact frame inside a hitstop window", fix: "the clock holds on an impact frame: add hitstop {at, hold} covering the frames" },
    { name: "one_peak_per_hit", ok: moving || extraPeaks.length === 0, value: moving ? "n/a (moving camera)" : extraPeaks, limit: "intensity only falls after a hit (declare the hits in preset.hits); judged from static views only", fix: "a layer brightens with no hit there: move it earlier, shorten it, or declare the hit" },
    { name: "readable", ok: maxCov >= 0.03, value: maxCov, limit: ">= 3% of the frame at its biggest", fix: "too small from this camera: scale the hit's flash / body up, or bring it closer" },
    { name: "palette", ok: hueCount <= 4, value: hueCount, limit: "<= 4 hues on screen", fix: "a colour outside the palette: use palette names, drop the stray hue" },
    { name: "frames_draw_cut", ok: cutMiss.length === 0, value: cutMiss.length ? cutMiss : cutSeen, limit: ">= 60% of the slash's centreline drawn (white core / accent) in every frame that strokes the cut", fix: "the frame camera loses the arc or the stroke is under something: camera \"cut\", draw.slash >= 1, the arc alive and full size at the hit" },
    { name: "dissipates", ok: moving || (fadeAt == null && popAt == null), value: moving ? "n/a (moving camera)" : { fade: fadeAt, pop: popAt }, limit: "the tail breaks down (coverage falls with the light), never a plain opacity fade or a one-frame pop; judged from static views", fix: "dissolve instead of fading: erode [start, 1] on meshes (or kit vfx animepass), sprites shrinking / scattering at the end, a sweep tail on arcs; a pop: overlap the last layers' ends" },
    { name: "focal", ok: moving || focalMed == null || focalMed >= 0.45, value: moving ? "n/a (moving camera)" : focalMed, limit: "in its biggest moments >= 45 % of the effect in ONE connected shape (a clear focal point); judged from static views", fix: "scattered clutter: fewer, bigger shapes; group the particles round the main form; drop layers that compete with it" },
    { name: "strike_snap", ok: slow.length === 0, value: slow, limit: "at each hit the light climbs 10 -> 90 % within 0.15 s (prepare long, STRIKE in a frame)", fix: "a slow ramp into the hit: start the hit layers AT the hit with their peak in the first 1-3 frames (front-loaded curves), move the build-up before it" },
    { name: "frames_fill", ok: fillMed == null || fillMed >= FRAMES_FILL_MIN, value: fillMed, limit: `impact frames: the subject spans >= ${FRAMES_FILL_MIN} of the frame (median)`, fix: "a speck in an empty frame: this hit is too small on screen for frames - drop them (the owner, 2026-10-25: not every hit needs frames), or make the strike itself bigger in the shot; a re-framed close-up no longer lines up with the attack" },
    { name: "frames_on_screen", ok: offScreen.length === 0, value: onScreenAsked ? offScreen : viewName === askView ? "n/a (moving camera)" : `n/a (${askView} view only)`, limit: `frames that re-frame the shot cut away from a strike ON screen: the live effect (brighter or darker than the scene) >= ${FRAMES_ON_SCREEN_MIN} of the ${askView} view in the second before them`, fix: "the strike is a speck when the frames cut in (the owner, 2026-10-24: 'bad impact frames' x4): drop the frames - not every hit needs them - or draw them from the live shot (camera \"none\"), or make the strike itself big on screen before cutting away" },
    { name: "not_blown_out", ok: maxHot <= 0.35, value: maxHot, limit: "<= 35% of the frame pure white (outside declared impact frames)", fix: "additive layers stack to white: fewer / dimmer sprites near the camera, shorter flood" },
  ];
  return { view: viewName, peak: { t: frames[peakI] ? frames[peakI].t : 0, mean: +peak.toFixed(1) }, maxCoverage: maxCov, hues: huePresence.map((v) => +v.toFixed(2)), checks, frames };
}
