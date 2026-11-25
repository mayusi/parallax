"""preview.py — the kit's eyes for VFX: simulate a preset the way Vfx.luau plays it and draw a frame strip.

    python kit/vfx/preview.py --presets assets/effects --textures build/textures --out build/vfx [name ...]

Per preset: build/vfx/<name>.png — frames over time (front-loaded so the impact is seen), each labelled with
its time and the events that fired (sound, shake, screen flash). 3/4 elevated orthographic view, ground line,
R6 character (5 studs) for scale. Particles use the real generated textures, sizes/colour/transparency
sequences, drag, acceleration, spread, flipbooks, LightEmission (additive). Prints one JSON line:
{status, summary, next_action, effects:[{name, file, peak_particles, visible_until, duration, checks}]}.

Measured, not guessed: `visible_until` (when the last visible thing fades), `peak_particles` (live at once).
Gate: something still visible when the preset's `duration` ends gets CUT OFF in game (the holder part is
destroyed at `duration`) -> error with the fix. Too many live particles -> warn.
"""

import argparse
import json
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TILE = 300
COLS = 5
GRAVITY = 196.2  # studs/s², Workspace default
PITCH = math.radians(28)  # camera looks down this much
BG = np.array([22, 26, 34], dtype=np.float32) / 255
NORMALS = {
    "Top": (0, 1, 0),
    "Bottom": (0, -1, 0),
    "Left": (-1, 0, 0),
    "Right": (1, 0, 0),
    "Front": (0, 0, -1),
    "Back": (0, 0, 1),
}


# ---------------------------------------------------------------- sequences (Roblox semantics)
def seq(v, t, default=0.0):
    """NumberSequence value at normalized time t: number or [[t, v(, env)], ...]."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    for (t0, v0, *_), (t1, v1, *_) in zip(v, v[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
    return float(v[-1][1])


def cseq(v, t):
    """ColorSequence value (0..1 rgb): [r, g, b] or [[t, [r, g, b]], ...]."""
    if v is None:
        return np.ones(3, dtype=np.float32)
    if isinstance(v[0], (int, float)):
        return np.array(v, dtype=np.float32) / 255
    for (t0, c0), (t1, c1) in zip(v, v[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return (np.array(c0) + (np.array(c1) - np.array(c0)) * k).astype(np.float32) / 255
    return np.array(v[-1][1], dtype=np.float32) / 255


def rng_range(r, v):
    if isinstance(v, (int, float)):
        return float(v)
    return r.uniform(v[0], v[1])


def quad_out(k):
    k = min(max(k, 0.0), 1.0)
    return 1 - (1 - k) * (1 - k)


# ---------------------------------------------------------------- textures
class Textures:
    def __init__(self, folder, grids):
        self.folder = folder
        self.grids = grids
        self.raw = {}
        self.cache = {}
        self.missing = set()

    def _load(self, key):
        if key not in self.raw:
            path = os.path.join(self.folder, f"{key}.png")
            if os.path.isfile(path):
                im = Image.open(path).convert("RGBA")
            else:
                self.missing.add(key)
                im = soft_circle(128)
            self.raw[key] = im
        return self.raw[key]

    def sprite(self, key, px, frame, rot):
        px = max(2, int(px))
        rot = int(rot // 15 * 15) % 360
        ck = (key, px, frame, rot)
        if ck not in self.cache:
            im = self._load(key)
            g = self.grids.get(key, 1)
            if g > 1:
                w = im.width // g
                fx, fy = frame % g, frame // g % g
                im = im.crop((fx * w, fy * w, fx * w + w, fy * w + w))
            im = im.resize((px, px), Image.BILINEAR)
            if rot:
                im = im.rotate(rot, resample=Image.BILINEAR)
            a = np.asarray(im, dtype=np.float32) / 255
            if len(self.cache) > 4000:
                self.cache.clear()
            self.cache[ck] = a
        return self.cache[ck]


def soft_circle(n):
    y, x = np.mgrid[0:n, 0:n]
    d = np.sqrt((x - n / 2 + 0.5) ** 2 + (y - n / 2 + 0.5) ** 2) / (n / 2)
    a = np.clip(1 - d, 0, 1) ** 1.5
    rgba = np.dstack([np.ones_like(a), np.ones_like(a), np.ones_like(a), a])
    return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- v2: meshes, afterimages, grades
MESHES = {}  # name -> {"v": np.array (n, 3) Roblox studs at scale 1, "f": [[i, ...]]}
FORWARD = np.array([0.0, -math.sin(PITCH), math.cos(PITCH)])  # camera looks this way (see Canvas.project)


def primitive(shape):
    """Unit-size primitives as the runtime stand-ins (Cylinder stands upright along Y, like Vfx.luau)."""
    v, f = [], []
    if shape == "Block":
        v = [(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
        f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    elif shape == "Cylinder":
        n = 24
        for y in (-0.5, 0.5):
            for i in range(n):
                a = 2 * math.pi * i / n
                v.append((0.5 * math.cos(a), y, 0.5 * math.sin(a)))
        for i in range(n):
            j = (i + 1) % n
            f.append([i, j, n + j, n + i])
        f.append(list(range(n))[::-1])
        f.append(list(range(n, 2 * n)))
    elif shape == "Wedge":
        v = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5)]
        f = [[0, 3, 2, 1], [3, 4, 5, 2], [0, 1, 5, 4], [0, 4, 3], [1, 2, 5]]
    else:  # Ball
        rings, seg = 10, 20
        for i in range(rings + 1):
            for j in range(seg):
                th, ph = math.pi * i / rings, 2 * math.pi * j / seg
                v.append((0.5 * math.sin(th) * math.cos(ph), -0.5 * math.cos(th), 0.5 * math.sin(th) * math.sin(ph)))
        for i in range(rings):
            for j in range(seg):
                a, b = i * seg + j, i * seg + (j + 1) % seg
                f.append([a, b, b + seg, a + seg])
    return {"v": np.array(v, dtype=np.float64), "f": f}


def load_meshes(presets_dir):
    MESHES.clear()
    path = os.path.join(presets_dir, "_meshes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    for name, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        obj = str(entry.get("file", "")).replace(".fbx", ".obj")
        if os.path.isfile(obj):
            v, f = [], []
            with open(obj, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("v "):
                        v.append(tuple(float(x) for x in line.split()[1:4]))
                    elif line.startswith("f "):
                        f.append([int(x.split("/")[0]) - 1 for x in line.split()[1:]])
            MESHES[name] = {"v": np.array(v, dtype=np.float64), "f": f}
        else:
            prim = primitive(entry.get("fallback", "Ball"))
            prim["v"] = prim["v"] * np.array(entry.get("size", [1, 1, 1]))
            MESHES[name] = prim


def geometry(key):
    return MESHES.get(key) or primitive(key)


def scale_at(v, u):
    def vec(x):
        return np.array([x, x, x], dtype=np.float64) if isinstance(x, (int, float)) else np.array(x, dtype=np.float64)

    if isinstance(v, (int, float)) or (isinstance(v, list) and v and isinstance(v[0], (int, float))):
        return vec(v)
    for (t0, a), (t1, b) in zip(v, v[1:]):
        if t0 <= u <= t1:
            k = (u - t0) / (t1 - t0) if t1 > t0 else 0
            return vec(a) + (vec(b) - vec(a)) * k
    return vec(v[-1][1])


def rot_matrix(deg):
    x, y, z = (math.radians(a) for a in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rx @ ry @ rz  # CFrame.Angles order


def mesh_alive(el, age, attach):
    life = el.get("time", 1)
    if attach:
        return (age % life) / life if age >= 0 else None
    return age / life if 0 <= age <= life else None


def draw_mesh(cv, el, age, attach):
    u = mesh_alive(el, age, attach)
    if u is None:
        return
    alpha = 1 - seq(el.get("transparency"), u, 0)
    if alpha <= 0.01:
        return
    g = geometry(el["mesh"])
    sc = scale_at(el["scale"], u)
    spin = np.array(el.get("spin", [0, 0, 0]), dtype=np.float64) * (age % el.get("time", 1) if attach else age)
    m = rot_matrix(el.get("rotation", [0, 0, 0])) @ rot_matrix(spin)
    world = (g["v"] * sc) @ m.T + np.array(el.get("offset", [0, 0, 0]), dtype=np.float64)
    col = cseq(el.get("color"), u)
    material = el.get("material", "Neon")
    faces = []
    for f in g["f"]:
        pts = world[f]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n /= ln
        facing = float(n @ FORWARD)
        if facing >= 0:  # back face: Roblox culls it (double-sided kit meshes carry their own back faces)
            continue
        faces.append((float(pts.mean(axis=0) @ FORWARD), [cv.project(p) for p in pts], -facing))
    if not faces:
        return
    faces.sort(key=lambda x: -x[0])  # far first
    layer = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for _, poly, facing in faces:
        if material == "ForceField":
            a = alpha * min(1.0, 1.3 * (1 - facing) ** 1.5)  # glows at grazing angles
            shade = 1.0
        elif material == "Glass":
            a, shade = alpha * 0.35, 0.6 + 0.4 * facing
        elif material == "SmoothPlastic":
            a, shade = alpha, 0.45 + 0.55 * facing
        else:  # Neon
            a, shade = alpha * 0.85, 1.0
        c = np.clip(col * shade, 0, 1)
        dr.polygon(poly, fill=(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255), int(np.clip(a, 0, 1) * 255)))
    arr = np.asarray(layer, dtype=np.float32) / 255
    a = arr[..., 3:4]
    if material in ("Neon", "ForceField"):
        cv.img += arr[..., :3] * a
    else:
        cv.img[:] = cv.img * (1 - a) + arr[..., :3] * a


R6_BOXES = [((-0.5, 0), (1, 2)), ((0.5, 0), (1, 2)), ((0, 2), (2, 2)), ((-1.5, 2), (1, 2)), ((1.5, 2), (1, 2)), ((0, 4), (1.2, 1.2))]


def draw_r6(cv, x, color, alpha, additive):
    for (px, py), (w, h) in R6_BOXES:
        ax, ay = cv.project((x + px - w / 2, py, 0))
        bx, by = cv.project((x + px + w / 2, py + h, 0))
        xa, xb = int(max(min(ax, bx), 0)), int(min(max(ax, bx), TILE))
        ya, yb = int(max(min(ay, by), 0)), int(min(max(ay, by), TILE))
        if xa < xb and ya < yb:
            if additive:
                cv.img[ya:yb, xa:xb] += color * alpha
            else:
                cv.img[ya:yb, xa:xb] = cv.img[ya:yb, xa:xb] * (1 - alpha) + color * alpha


def grade_k(el, age, attach):
    """envelope 0..1 of a grade at `age` (attach: fades in and holds)."""
    fi, fo, hold = el.get("fadeIn", 0.15), el.get("fadeOut", 0.35), el.get("time", 0)
    if age < 0:
        return 0.0
    if age < fi:
        return quad_out(age / fi) if fi > 0 else 1.0
    if attach or age < fi + hold:
        return 1.0
    if age < fi + hold + fo:
        return 1 - quad_out((age - fi - hold) / fo)
    return 0.0


def apply_grade(img, el, k):
    """img: float RGB 0..1 numpy -> graded (tint, saturation, contrast, brightness, blur, fov zoom)."""
    tint = np.array(el.get("tint", [255, 255, 255]), dtype=np.float32) / 255
    img = img * (1 + (tint - 1) * k)
    lum = (img * np.array([0.299, 0.587, 0.114], dtype=np.float32)).sum(axis=2, keepdims=True)
    img = lum + (img - lum) * (1 + el.get("saturation", 0) * k)
    img = (img - 0.5) * (1 + el.get("contrast", 0) * k) + 0.5 + el.get("brightness", 0) * k
    img = np.clip(img, 0, 1)
    im = Image.fromarray((img * 255).astype(np.uint8), "RGB")
    if el.get("blur", 0) * k > 0.5:
        im = im.filter(ImageFilter.GaussianBlur(el["blur"] * k / 6))
    fov = el.get("fov", 0) * k
    if abs(fov) > 0.5:
        z = math.tan(math.radians(35)) / math.tan(math.radians(35 + fov / 2))  # >1 zooms in, <1 widens
        w = max(8, int(TILE * z))
        im2 = im.resize((w, w), Image.BILINEAR)
        out = Image.new("RGB", (TILE, TILE), tuple(int(c * 255) for c in BG))
        out.paste(im2, ((TILE - w) // 2, (TILE - w) // 2))
        im = out
    return np.asarray(im, dtype=np.float32) / 255


# ---------------------------------------------------------------- simulation
def cone_dir(r, normal, spread_deg):
    n = np.array(normal, dtype=np.float64)
    spread = math.radians(min(spread_deg, 180))
    if spread >= math.pi - 1e-3:
        v = np.array([r.gauss(0, 1) for _ in range(3)])
        return v / (np.linalg.norm(v) or 1)
    cos_t = r.uniform(math.cos(spread), 1)
    sin_t = math.sqrt(1 - cos_t * cos_t)
    phi = r.uniform(0, 2 * math.pi)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    w = np.cross(n, u)
    return n * cos_t + (u * math.cos(phi) + w * math.sin(phi)) * sin_t


def particles_of(el, duration, attach, r):
    """Spawn every particle of a particles element: list of dicts with full trajectories sampled at 1/60 s."""
    t0 = el.get("delay", 0) or 0
    spawns = [t0] * int(el.get("burst", 0) or 0)
    rate = el.get("rate", 0) or 0
    if rate > 0:
        window = duration - t0 if attach else (el.get("emit", 0.2) or 0.2)
        n = int(rate * window)
        spawns += [t0 + (i + r.random()) / rate for i in range(n)]
    out = []
    accel = np.array(el.get("acceleration", [0, 0, 0]), dtype=np.float64)
    drag = el.get("drag", 0) or 0
    normal = NORMALS.get(el.get("direction", "Top"), (0, 1, 0))
    for s in spawns:
        life = max(0.01, rng_range(r, el["lifetime"]))
        v = cone_dir(r, normal, el.get("spread", 0) or 0) * rng_range(r, el.get("speed", 0) or 0)
        p = np.zeros(3)
        traj = []
        dt = 1 / 60
        steps = max(1, int(life / dt))
        for _ in range(steps + 1):
            traj.append(p.copy())
            v = v * (2 ** (-drag * dt)) + accel * dt
            p = p + v * dt
        out.append(
            {
                "born": s,
                "life": life,
                "traj": traj,
                "rot0": rng_range(r, el.get("rotation", 0) or 0),
                "rotv": rng_range(r, el.get("rotSpeed", 0) or 0),
                "rand_frame": r.randrange(64),
            }
        )
    return out


def debris_of(el, duration, r):
    t0 = el.get("delay", 0) or 0
    out = []
    for _ in range(int(el.get("count", 0))):
        spread = math.radians(el.get("spread", 45))
        yaw, tilt = r.uniform(0, 2 * math.pi), r.uniform(0, spread)
        d = np.array([math.sin(tilt) * math.cos(yaw), math.cos(tilt), math.sin(tilt) * math.sin(yaw)])
        v = d * rng_range(r, el["speed"])
        p = np.array([0.0, 1.0, 0.0])
        life = el.get("lifetime", duration)
        size = rng_range(r, el["size"])
        traj = []
        dt = 1 / 60
        for _ in range(int(life / dt) + 1):
            traj.append(p.copy())
            v[1] -= GRAVITY * dt
            p = p + v * dt
            if p[1] < size / 2:  # bounce + friction on the ground
                p[1] = size / 2
                v[1] = -v[1] * 0.3
                v[0] *= 0.8
                v[2] *= 0.8
        out.append({"born": t0, "life": life, "traj": traj, "size": size})
    return out


# ---------------------------------------------------------------- drawing
class Canvas:
    def __init__(self, extent):
        self.img = np.ones((TILE, TILE, 3), dtype=np.float32) * BG
        self.ppu = TILE / (2 * extent)  # pixels per stud
        self.ground_y = TILE * 0.78

    def project(self, p):
        x, y, z = p
        sx = TILE / 2 + x * self.ppu
        sy = self.ground_y - (y * math.cos(PITCH) + z * math.sin(PITCH)) * self.ppu
        return sx, sy

    def blit(self, rgba, cx, cy, tint, alpha, additive):
        h, w = rgba.shape[:2]
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, TILE), min(y0 + h, TILE)
        if xa >= xb or ya >= yb:
            return
        s = rgba[ya - y0 : yb - y0, xa - x0 : xb - x0]
        a = s[..., 3:4] * alpha
        col = s[..., :3] * tint
        region = self.img[ya:yb, xa:xb]
        if additive:
            region += col * a
        else:
            region[:] = region * (1 - a) + col * a

    def disc(self, cx, cy, rx, ry, color, alpha, soft=0.25, additive=True):
        if rx < 0.5 or ry < 0.5 or alpha <= 0.003:
            return
        x0, x1 = int(max(cx - rx - 1, 0)), int(min(cx + rx + 2, TILE))
        y0, y1 = int(max(cy - ry - 1, 0)), int(min(cy + ry + 2, TILE))
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        a = (np.clip((1 - d) / soft, 0, 1) * alpha)[..., None]
        region = self.img[y0:y1, x0:x1]
        if additive:
            region += color * a
        else:
            region[:] = region * (1 - a) + color * a

    def ring(self, cx, cy, r, thick, color, alpha):
        if r < 1 or alpha <= 0.003:
            return
        ry = r * math.sin(PITCH)
        x0, x1 = int(max(cx - r - thick, 0)), int(min(cx + r + thick + 1, TILE))
        y0, y1 = int(max(cy - ry - thick, 0)), int(min(cy + ry + thick + 1, TILE))
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.sqrt(((xx - cx) / r) ** 2 + ((yy - cy) / max(ry, 1)) ** 2)
        a = (np.clip(1 - np.abs(d - 1) * r / max(thick, 1), 0, 1) * alpha)[..., None]
        self.img[y0:y1, x0:x1] += color * a

    def line(self, p0, p1, w0, w1, color, alpha):
        (x0, y0), (x1, y1) = p0, p1
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / 2) + 2
        for i in range(n):
            k = i / (n - 1)
            self.disc(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, max(1, (w0 + (w1 - w0) * k) / 2), max(1, (w0 + (w1 - w0) * k) / 2), color, alpha, soft=0.5)

    def r6(self):
        """A dim R6 silhouette (5 studs) at the left, standing on the ground line, for scale."""
        x = -TILE / 2 / self.ppu * 0.78
        parts = [((x - 0.5, 0), (1, 2)), ((x + 0.5, 0), (1, 2)), ((x, 2), (2, 2)), ((x - 1.5, 2), (1, 2)), ((x + 1.5, 2), (1, 2)), ((x, 4), (1.2, 1.2))]
        for (px, py), (w, h) in parts:
            ax, ay = self.project((px - w / 2, py, 0))
            bx, by = self.project((px + w / 2, py + h, 0))
            xa, xb = int(max(min(ax, bx), 0)), int(min(max(ax, bx), TILE))
            ya, yb = int(max(min(ay, by), 0)), int(min(max(ay, by), TILE))
            if xa < xb and ya < yb:
                self.img[ya:yb, xa:xb] = self.img[ya:yb, xa:xb] * 0.5 + np.array([0.32, 0.42, 0.62]) * 0.5

    def ground(self):
        y = int(self.ground_y)
        if 0 <= y < TILE:
            self.img[y:, :] = self.img[y:, :] * 0.85 + np.array([0.12, 0.13, 0.15]) * 0.15
            self.img[y, :] = np.array([0.35, 0.37, 0.42])


# ---------------------------------------------------------------- one preset
def simulate(name, preset, tex, seed=7):
    r = random.Random(seed)
    duration = float(preset.get("duration", 1))
    attach = preset.get("mode") == "attach"
    els = preset.get("elements", [])
    sims = []
    for el in els:
        k = el.get("kind")
        if k == "particles":
            sims.append((el, particles_of(el, duration, attach, r)))
        elif k == "debris":
            sims.append((el, debris_of(el, duration, r)))
        else:
            sims.append((el, None))
    return duration, attach, sims


def visible_alpha_particle(el, age, life):
    return (1 - seq(el.get("transparency"), age / life, 0)) * (1 if seq(el.get("size"), age / life, 1) > 0.02 else 0)


def measure(duration, sims):
    """peak live particles and the last time anything visible remains."""
    peak, last = 0, 0.0
    t_end = duration * 3 + 3
    ts = np.arange(0, t_end, 1 / 30)
    for t in ts:
        live = 0
        for el, ps in sims:
            k = el.get("kind")
            d = el.get("delay", 0) or 0
            if k == "particles":
                for p in ps:
                    age = t - p["born"]
                    if 0 <= age <= p["life"]:
                        live += 1
                        if visible_alpha_particle(el, age, p["life"]) > 0.02:
                            last = max(last, t)
            elif k == "debris":
                for p in ps:
                    if 0 <= t - p["born"] <= p["life"]:
                        last = max(last, t)
            elif k in ("flash", "ring"):
                tr = el.get("transparency", [0, 1])
                age = t - d
                if 0 <= age <= el.get("time", 0.3 if k == "flash" else 0.5):
                    if 1 - (tr[0] + (tr[1] - tr[0]) * quad_out(age / el.get("time", 0.3 if k == "flash" else 0.5))) > 0.02:
                        last = max(last, t)
            elif k == "beam":
                if 0 <= t - d <= el.get("time", min(0.4, duration)):
                    last = max(last, t)
            elif k == "mesh":
                u = mesh_alive(el, t - d, False)
                if u is not None and 1 - seq(el.get("transparency"), u, 0) > 0.02:
                    last = max(last, t)
        peak = max(peak, live)
    return peak, round(last, 2)


def frame_times(duration, els):
    base = [duration * ((k + 0.5) / 8) ** 1.6 for k in range(8)]
    for el in els:
        d = el.get("delay", 0) or 0
        if d > 0:
            base += [d + 0.06, d + 0.25]
    base = sorted({round(t, 2) for t in base if t < duration * 1.25})
    while len(base) > 10:  # drop the closest pair until 10 remain
        gaps = [(base[i + 1] - base[i], i) for i in range(len(base) - 1)]
        base.pop(min(gaps)[1] + 1)
    return base


def extent_of(sims):
    pts = []
    for el, ps in sims:
        k = el.get("kind")
        if k in ("particles", "debris"):
            for p in ps:
                for q in p["traj"][:: max(1, len(p["traj"]) // 6)]:
                    pts.append(max(abs(q[0]), abs(q[2]), abs(q[1]) / 1.4))
        elif k in ("flash", "ring"):
            pts.append(el["size"][1] / 2)
        elif k == "light":
            pts.append(min(el.get("range", 10), 40) * 0.5)
        elif k == "mesh":
            g = geometry(el["mesh"])
            biggest = max(float(np.abs(scale_at(el["scale"], u)).max()) for u in (0, 0.5, 1))
            off = max(abs(c) for c in el.get("offset", [0, 0, 0]))
            pts.append(float(np.abs(g["v"]).max()) * biggest + off)
        elif k == "afterimage":
            pts.append(12.0)
    e = float(np.percentile(pts, 96)) if pts else 8.0
    if any(el.get("kind") == "afterimage" for el, _ in sims):
        e = max(e, 12.0)  # room for the character to run across
    return min(max(e * 1.15, 6.5), 220)


def render(name, preset, tex, out_dir):
    duration, attach, sims = simulate(name, preset, tex)
    els = [el for el, _ in sims]
    peak, last = measure(duration, sims)
    extent = extent_of(sims)
    # frames span what is actually visible (a 0.4 s spark burst in a 0.8 s preset gets all 10 frames on the sparks)
    horizon = max(duration, 2.0) if attach else max(0.12, min(duration, last + 0.12))
    times = frame_times(horizon, els)
    if not attach and last > duration + 0.05:
        times = times[:-1] + [round(duration, 2)]  # show the moment it gets destroyed
    font = ImageFont.load_default()
    tiles = []
    br = random.Random(3)
    for t in times:
        cv = Canvas(extent)
        cv.ground()
        cv.r6()
        events = []
        grades = []
        screen = None
        shake = 0.0
        for el, ps in sims:
            k = el.get("kind")
            d = el.get("delay", 0) or 0
            age = t - d
            if k == "particles":
                additive = (el.get("lightEmission", 0) or 0) >= 0.5
                grid = tex.grids.get(el.get("texture"), 1)
                fb = el.get("flipbook")
                for p in ps:
                    a_ = t - p["born"]
                    if not (0 <= a_ <= p["life"]):
                        continue
                    u = a_ / p["life"]
                    alpha = 1 - seq(el.get("transparency"), u, 0)
                    size = seq(el.get("size", 1), u, 1)
                    if alpha <= 0.01 or size <= 0.01:
                        continue
                    pos = p["traj"][min(int(a_ * 60), len(p["traj"]) - 1)]
                    frame = 0
                    if fb and grid > 1:
                        n = grid * grid
                        mode = fb.get("mode", "Loop")
                        if mode == "OneShot":
                            frame = min(int(u * n), n - 1)
                        elif mode == "Random":
                            frame = p["rand_frame"] % n
                        else:
                            frame = int(a_ * fb.get("fps", 24)) % n
                    rot = p["rot0"] + p["rotv"] * a_
                    sp = tex.sprite(el["texture"], size * cv.ppu, frame, rot)
                    cx, cy = cv.project(pos)
                    cv.blit(sp, cx, cy, cseq(el.get("color"), u), alpha, additive)
            elif k == "debris":
                col = np.array(el.get("color", [60, 50, 45]), dtype=np.float32) / 255
                for p in ps:
                    a_ = t - p["born"]
                    if 0 <= a_ <= p["life"]:
                        cx, cy = cv.project(p["traj"][min(int(a_ * 60), len(p["traj"]) - 1)])
                        s = max(1.5, p["size"] * cv.ppu / 2)
                        cv.disc(cx, cy, s, s, col, 1.0, soft=0.05, additive=False)
            elif k == "flash" and 0 <= age <= el.get("time", 0.3):
                kk = quad_out(age / el.get("time", 0.3))
                tr = el.get("transparency", [0, 1])
                size = el["size"][0] + (el["size"][1] - el["size"][0]) * kk
                cx, cy = cv.project((0, 0, 0))
                col = np.array(el.get("color", [255, 255, 255]), dtype=np.float32) / 255
                cv.disc(cx, cy, size / 2 * cv.ppu, size / 2 * cv.ppu, col, 1 - (tr[0] + (tr[1] - tr[0]) * kk), soft=0.35)
            elif k == "ring" and 0 <= age <= el.get("time", 0.5):
                kk = quad_out(age / el.get("time", 0.5))
                tr = el.get("transparency", [0, 1])
                size = el["size"][0] + (el["size"][1] - el["size"][0]) * kk
                cx, cy = cv.project((0, 0, 0))
                col = np.array(el.get("color", [255, 255, 255]), dtype=np.float32) / 255
                cv.ring(cx, cy, size / 2 * cv.ppu, max(1.5, el.get("thickness", 1) * cv.ppu), col, 1 - (tr[0] + (tr[1] - tr[0]) * kk))
            elif k == "light":
                life = el.get("time", duration)
                if 0 <= age <= max(life, duration - d):
                    b0, b1 = el["brightness"]
                    b = b0 + (b1 - b0) * quad_out(age / life) if age <= life else b1
                    rng_ = min(el.get("range", 10), 60) * cv.ppu
                    cx, cy = cv.project((0, 0.5, 0))
                    col = np.array(el.get("color", [255, 255, 255]), dtype=np.float32) / 255
                    cv.disc(cx, cy, rng_, rng_ * 0.75, col, min(1.0, b / 10) * 0.35, soft=1.0)
            elif k == "beam" and 0 <= age <= el.get("time", min(0.4, duration)):
                fade = age / el.get("time", min(0.4, duration))
                a3 = np.array(el.get("from", [0, 0, 0]), dtype=np.float64)
                to = el.get("to")
                b3 = np.array([extent * 0.6, 0, 0]) if to == "target" else np.array(to, dtype=np.float64)
                segs = el.get("segments", 8) if el.get("lightning") else 1
                length = float(np.linalg.norm(b3 - a3)) or 1
                axis = (b3 - a3) / length
                side = np.cross(axis, [0, 1, 0] if abs(axis[1]) < 0.9 else [1, 0, 0])
                side /= np.linalg.norm(side)
                pts = []
                for i in range(segs + 1):
                    q = a3 + (b3 - a3) * (i / segs)
                    if 0 < i < segs:
                        amp = length * 0.06 * el.get("jitter", 1)
                        q = q + side * br.uniform(-amp, amp)
                    pts.append(cv.project(q))
                w = el.get("width", [1, 1])
                for i in range(segs):
                    kk = i / segs
                    col = cseq(el.get("color"), kk)
                    cv.line(pts[i], pts[i + 1], w[0] * cv.ppu, w[1] * cv.ppu, col, max(0.0, 1 - fade) * 0.9)
            elif k == "mesh":
                draw_mesh(cv, el, age, attach)
                if 0 <= age < 0.12 and not attach:
                    events.append(f"MESH {el['mesh']}")
            elif k == "afterimage":
                # the character runs left -> right across the preview, leaving copies every `interval`
                speed = extent * 1.3 / max(horizon, 0.1)
                xpos = lambda tt: -extent * 0.65 + speed * tt  # noqa: E731
                life, every = el.get("lifetime", 0.5), el.get("interval", 0.1)
                born = 0.0
                while born <= t:
                    a_ = t - born
                    if a_ <= life:
                        u = a_ / life
                        phase = (born / el["cycle"]) % 1 if el.get("cycle") else u
                        alpha_g = 1 - seq(el.get("transparency"), u, u)
                        if alpha_g > 0.01:
                            draw_r6(cv, xpos(born), cseq(el.get("color"), phase), alpha_g * 0.8, el.get("material", "Neon") in ("Neon", "ForceField"))
                    born += every
                draw_r6(cv, xpos(t), np.array([0.32, 0.42, 0.62]), 1.0, False)
            elif k == "grade":
                kk = grade_k(el, age, attach)
                if kk > 0.01:
                    grades.append((el, kk))
                    if age < 0.12:
                        events.append("GRADE")
            elif k == "screen" and 0 <= age <= el.get("time", 0.3):
                kk = quad_out(age / el.get("time", 0.3))
                screen = (np.array(el.get("color", [255, 255, 255]), dtype=np.float32) / 255, el.get("flash", 0.4) * (1 - kk))
                if age < 0.12:
                    events.append("SCREEN")
            elif k == "shake" and 0 <= age <= 0.6:
                shake = max(shake, el.get("intensity", 1) * 0.5 * max(0, 1 - age * 1.6))
                if age < 0.12:
                    events.append("SHAKE")
            elif k == "sound" and 0 <= age < max(0.12, times[0] + 0.01):
                events.append(f"SND {el.get('name')}")
        img = np.clip(cv.img, 0, 1)
        for el_g, kk in grades:
            img = apply_grade(img, el_g, kk)
        if screen is not None:
            col, b = screen
            img = np.clip(img + col * min(b, 1.0), 0, 1)
        im = Image.fromarray((img * 255).astype(np.uint8), "RGB")
        if shake > 0.02:
            off = int(min(10, shake * 8))
            im = im.transform(im.size, Image.AFFINE, (1, 0, off, 0, 1, -off // 2), fillcolor=(0, 0, 0))
        dr = ImageDraw.Draw(im)
        dr.text((6, 5), f"t={t:.2f}s", fill=(235, 235, 235), font=font)
        for i, e in enumerate(events[:3]):
            dr.text((6, 20 + i * 13), e, fill=(255, 200, 90), font=font)
        if t > duration and not attach:
            dr.text((6, TILE - 18), "after duration (destroyed)", fill=(255, 110, 110), font=font)
        tiles.append(im)
    rows = (len(tiles) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TILE + (COLS - 1) * 2, rows * TILE + (rows - 1) * 2), (60, 60, 60))
    for i, tl in enumerate(tiles):
        sheet.paste(tl, ((i % COLS) * (TILE + 2), (i // COLS) * (TILE + 2)))
    path = os.path.join(out_dir, f"{name}.png")
    sheet.save(path)

    checks = []
    if not attach and last > duration + 0.05:
        checks.append(
            {
                "name": "cut_off",
                "severity": "error",
                "value": last,
                "limit": duration,
                "fix": f"visible until {last}s but duration is {duration}s — the effect is destroyed mid-fade (a pop). "
                f"Raise duration to {math.ceil(last * 10) / 10}, or shorten lifetimes/time",
            }
        )
    if peak > 300:
        checks.append(
            {"name": "peak_particles", "severity": "warn", "value": peak, "limit": 300, "fix": "over 300 live particles hurts mobile — lower burst/rate or lifetime"}
        )
    if tex.missing:
        checks.append(
            {"name": "textures", "severity": "warn", "value": sorted(tex.missing), "limit": "built", "fix": "build the textures first: lune run kit vfx (textures step)"}
        )
    return {
        "name": name,
        "file": os.path.relpath(path).replace("\\", "/"),
        "duration": duration,
        "visible_until": last,
        "peak_particles": peak,
        "frames": times,
        "view_half_width_studs": round(extent, 1),
        "checks": checks,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", required=True)
    ap.add_argument("--textures", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("names", nargs="*")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    grids = {}
    tmap = os.path.join(args.presets, "_textures.json")
    if os.path.isfile(tmap):
        with open(tmap, encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                if isinstance(v, dict):
                    g = v.get("grid", 1) or 1
                    grids[k] = int(g[0] if isinstance(g, list) else g)
    if not os.path.isdir(args.presets):
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"vfx preview: no presets folder {args.presets}",
                          "next_action": "none", "effects": []}))
        return 0
    load_meshes(args.presets)
    names = args.names or sorted(f[:-5] for f in os.listdir(args.presets) if f.endswith(".json") and not f.startswith("_"))
    results, engine_only = [], []
    for n in names:
        with open(os.path.join(args.presets, f"{n}.json"), encoding="utf-8") as fh:
            preset = json.load(fh)
        if preset.get("version") == 3:  # layer-stack presets are made + judged in the browser PLAYER (mission 02-vfx v2): kit vfx play <name>
            engine_only.append(n)
            continue
        results.append(render(n, preset, Textures(args.textures, grids), args.out))
    errors = [(r["name"], c) for r in results for c in r["checks"] if c["severity"] == "error"]
    warns = [(r["name"], c) for r in results for c in r["checks"] if c["severity"] == "warn"]
    if errors:
        status = "fail"
        summary = "; ".join(f"{n}.{c['name']}={c['value']}" for n, c in errors)
        nxt = f"{errors[0][0]}: {errors[0][1]['fix']}"
    else:
        status = "pass"
        summary = f"{len(results)} preview(s) in {args.out}" + (f" ({len(warns)} warning(s))" if warns else "")
        if engine_only:
            summary += f"; v3 (made + judged in the player: lune run kit vfx play <name> [--record]): {', '.join(engine_only)}"
        nxt = (
            f"improve {warns[0][0]}: {warns[0][1]['fix']}"
            if warns
            else f"look at {args.out}/<name>.png: impact reads in the first frames? colours/size vs the R6? clean fade?"
        )
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt, "effects": results}))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
