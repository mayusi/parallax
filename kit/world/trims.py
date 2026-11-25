"""trims.py - the W3 kit's SHARED TRIM SHEETS (LIMITATIONS_FIXES_V4 5.1 / 5.4 step 2 / 13.5: "<= 3 shared 1024 x 1024
PBR trim sheets (35-70 px/stud, <= 15 unique maps total inside Roblox's ~100-map cap)").

Why: every gothic piece the kit made baked its OWN 1024 atlas (kit/world/gothic_blender.py gothic_atlas, seeded per
piece): a town of 30 houses carried 30+ colour maps, a third of what Roblox keeps resident for a whole scene. A trim
sheet is the AAA answer (Insomniac / Naughty Dog trims): one texture holds horizontal STRIPS - ashlar, a plinth's
rusticated course, a moulding, quoin blocks, cobbles; slate, oak, a beam, iron, glass - each strip tiles left to right,
and every module maps its faces onto a strip. Two sheets (stone; roof + wood) dress all eighteen modules: 6 maps.

Each sheet is three maps (Roblox SurfaceAppearance: ColorMap, NormalMap, RoughnessMap), made here procedurally from
the strip's own pattern (courses, joints, bevels, grain) - the colour from tones and noise, the normal from a height
field (joints recessed, block faces domed), the roughness from the same pattern. Pure numpy; PIL writes the PNGs.

TEXEL DENSITY: a sheet is SHEET px across = SPAN studs (64 px/stud); a strip's height in px is its height in studs
x 64. kit/world/modkit.py maps every face at that density and its check refuses a face outside 35..70 px/stud.
Not here: scanned textures (the vetted Poly Haven CC0 sets could be baked into strips later - this is the pattern
route, measured, not a scan), and how the strips read in Roblox's renderer (an upload is the owner's)."""
import os

import numpy as np

SHEET = 1024  # px a side
SPAN = 16.0  # studs across a sheet: 64 px a stud
PX = SHEET / SPAN

# the strips: name -> (sheet, top px, height px). Heights are whole studs at 64 px.
STRIPS = {
    # sheet "stone"
    "ashlar": ("stone", 0, 512),  # 8 studs of coursed ashlar (2-stud courses)
    "plinth": ("stone", 512, 128),  # a rusticated base course
    "moulding": ("stone", 640, 128),  # a moulded band: string course, cornice, sill, coping
    "quoin": ("stone", 768, 128),  # long-and-short corner blocks
    "cobble": ("stone", 896, 128),  # setts on a street or a court
    # sheet "roof"
    "slate": ("roof", 0, 512),  # 8 studs of slate courses
    "oak": ("roof", 512, 256),  # 4 studs of vertical oak boards (a door, a dormer cheek)
    "beam": ("roof", 768, 128),  # a timber beam's grain (a jetty, a lintel)
    "iron": ("roof", 896, 64),  # wrought iron (mullions, bars, straps)
    "glass": ("roof", 960, 64),  # leaded glass
}
# a strip's course in studs (its pattern repeats up the strip this often): a face's v is laid on a grid of whole
# courses measured from the storey's floor, so the courses of two modules side by side line up
COURSE = {"ashlar": 2.0, "plinth": 1.0, "quoin": 1.0, "cobble": 0.5, "slate": 0.75}
SHEETS = ("stone", "roof")
MAPS = ("color", "normal", "roughness")


def strip_studs(name):
    """a strip's height in studs"""
    return STRIPS[name][2] / PX


def _noise(shape, rng, scales):
    out = np.zeros(shape)
    for cell, amp in scales:
        small = rng.random((max(2, shape[0] // cell + 2), max(2, shape[1] // cell + 2)))
        ys = np.linspace(0, small.shape[0] - 1.001, shape[0])
        xs = np.linspace(0, small.shape[1] - 1.001, shape[1])
        y0, x0 = ys.astype(int), xs.astype(int)
        ty, tx = (ys - y0)[:, None], (xs - x0)[None, :]
        a = small[y0][:, x0] * (1 - tx) + small[y0][:, x0 + 1] * tx
        b = small[y0 + 1][:, x0] * (1 - tx) + small[y0 + 1][:, x0 + 1] * tx
        out += amp * (a * (1 - ty) + b * ty)
    return out


def _wrap_noise(h, rng, scales):
    """noise that tiles left to right (a strip must: its u runs on past 1)"""
    n = _noise((h, SHEET + 64), rng, scales)
    t = np.linspace(0, 1, 64)[None, :]
    n[:, :64] = n[:, :64] * t + n[:, SHEET:SHEET + 64] * (1 - t)
    return n[:, :SHEET]


CELL = 256  # px: a vertical joint every 4 studs in the coursed strips - a module's edge (its u starts at 0, its width
# a whole number of 4-stud bays) always falls on a joint, so two modules side by side show no cut block


def _blocks(h, course, lengths, rng, joint=4, offset=True, cell=CELL):
    """a coursed bond: (height field 0..1 - joints 0, faces domed, colour index per block) for a strip h px tall;
    its courses from the strip's BOTTOM up (a face's v is measured from the floor: courses line up across modules)"""
    height = np.zeros((h, SHEET))
    tone = np.zeros((h, SHEET))
    y = h % course  # (a part course at the strip's top, never at its foot)
    row = 0
    while y < h:
        y1 = min(h, y + course)
        # the joints of a course: random lengths inside each cell, the cell's own edges always joints
        xs = [0]
        for c0 in range(0, SHEET, cell):
            x = c0
            if offset and row % 2 and cell >= 2 * lengths[0]:  # (a running bond: odd courses start mid-block)
                x = c0 + int(rng.uniform(lengths[0] // 2, cell // 2))
                xs.append(x)
            while c0 + cell - x > lengths[1]:
                x += int(rng.uniform(*lengths))
                if c0 + cell - x < lengths[0] // 2:
                    break
                xs.append(x)
            if xs[-1] != c0 + cell:
                xs.append(c0 + cell)
        row += 1
        for a, b in zip(xs[:-1], xs[1:]):
            t = rng.uniform(0.74, 1.16)
            cols = np.arange(a, b) % SHEET
            yy = np.arange(y, y1)
            # a block's face: domed toward its middle, its edges bevelled down to the joint
            u = (np.arange(b - a) + 0.5) / (b - a)
            v = (yy - y + 0.5) / max(1, y1 - y)
            dome = np.minimum(np.minimum(u, 1 - u)[None, :] * (b - a), np.minimum(v, 1 - v)[:, None] * (y1 - y))
            face = np.clip(dome / joint, 0, 1) ** 0.6
            height[np.ix_(yy, cols)] = face
            tone[np.ix_(yy, cols)] = t
        y = y1
    return height, tone


def _stone(hf, tone, hpx, rng, spread=0.6, pits=0.32, chip=0.55):
    """dressed stone, not tiles (the owner, 2026-11-23, on the first W3 frames: the ashlar read as a value-shuffled
    block grid): every block's tone pulled toward the mean (spread of the old 0.74..1.16), each face TOOLED (fine pits
    and tool marks in the height, so it catches light across its whole face, not only at a flat plateau's rim), its
    arrises CHIPPED (the bevel's width wanders along the edge), a mineral speckle, darker into the joints (occlusion)
    and rain streaks down the face -> (height, colour multiplier)"""
    fine = _wrap_noise(hpx, rng, [(6, 0.45), (3, 0.35), (2, 0.2)])
    fine = (fine - fine.min()) / max(1e-6, np.ptp(fine))
    edge = _wrap_noise(hpx, rng, [(24, 0.6), (8, 0.4)])
    edge = (edge - edge.min()) / max(1e-6, np.ptp(edge))
    # chipped arrises: where the bevel is (0 < hf < 1) its rise is bent by a slow noise, so the edge is not ruled
    bevel = (hf > 0) & (hf < 1)
    out = np.where(bevel, np.clip(hf ** (0.6 + chip * edge), 0, 1), hf)
    # tooled faces: pits and tool lines across the face, strongest where the face is up (not inside the joints)
    out = np.clip(out - pits * (1 - fine) * np.clip(out, 0, 1), 0, 1)
    tone = 1 + (tone - 0.95) * spread
    speckle = 0.9 + 0.2 * fine
    occl = np.clip(0.55 + out * 0.9, 0, 1)  # the stone darkens into its joints
    wash = _wrap_noise(4, rng, [(2, 1.0)])[:1, :]  # one row: each column's own wash, the same all the way down
    wash = 0.93 + 0.1 * (wash - wash.min()) / max(1e-6, np.ptp(wash))
    return out, tone * speckle * occl * wash


def make_sheet(sheet, seed=7, stone=(74, 76, 80), slate=(36, 39, 46)):
    """-> {map: float array [SHEET, SHEET, 3 or 1]} for one sheet"""
    rng = np.random.default_rng(seed + (0 if sheet == "stone" else 101))
    color = np.zeros((SHEET, SHEET, 3))
    height = np.zeros((SHEET, SHEET))
    rough = np.zeros((SHEET, SHEET))
    base = np.array(stone, float) / 255
    for name, (sh, top, hpx) in STRIPS.items():
        if sh != sheet:
            continue
        grain = _wrap_noise(hpx, rng, [(64, 0.5), (16, 0.3), (4, 0.2)])
        if name == "ashlar":
            hf, tone = _blocks(hpx, 128, (96, 224), rng)
            hf, tone = _stone(hf, tone, hpx, rng)
            col = base[None, None, :] * tone[..., None] * (0.88 + 0.18 * grain)[..., None]
            # slow warm / cool staining across the wall (iron, lichen, soot), a few % per channel
            stain = np.stack([_wrap_noise(hpx, rng, [(160, 0.7), (48, 0.3)]) for _ in range(3)], axis=-1)
            col *= 0.96 + 0.08 * (stain - stain.min()) / max(1e-6, np.ptp(stain))
            soot = np.linspace(1.0, 0.82, hpx)[::-1][:, None]  # (darker toward the strip's top: rain and soot)
            col *= soot[..., None]
            r = 0.78 + 0.12 * grain
        elif name == "plinth":
            hf, tone = _blocks(hpx, 64, (128, 256), rng, joint=10)
            hf, tone = _stone(hf, tone, hpx, rng, pits=0.4, chip=0.8)  # (rusticated: rougher)
            col = base[None, None, :] * 0.8 * tone[..., None] * (0.8 + 0.3 * grain)[..., None]
            r = 0.85 + 0.1 * grain
        elif name == "moulding":
            v = (np.arange(hpx) + 0.5) / hpx
            # a profile: a fillet, a cyma (an S curve), a fillet, a drip - read across the strip's height
            prof = np.select([v < 0.15, v < 0.55, v < 0.7], [0.9, 0.9 - 0.7 * np.sin((v - 0.15) / 0.4 * np.pi / 2), 0.25], 0.6)
            hf = np.repeat(prof[:, None], SHEET, axis=1) * (0.95 + 0.05 * grain)
            col = base[None, None, :] * (0.88 + 0.25 * hf)[..., None] * (0.85 + 0.2 * grain)[..., None]
            r = 0.72 + 0.12 * grain
        elif name == "quoin":
            hf, tone = _blocks(hpx, 64, (96, 192), rng, joint=6, offset=False)
            hf, tone = _stone(hf, tone, hpx, rng, spread=0.35)
            col = base[None, None, :] * 1.08 * tone[..., None] * (0.82 + 0.28 * grain)[..., None]
            r = 0.76 + 0.12 * grain
        elif name == "cobble":
            hf, tone = _blocks(hpx, 32, (28, 48), rng, joint=6)
            col = base[None, None, :] * 0.7 * tone[..., None] * (0.75 + 0.35 * grain)[..., None]
            r = 0.6 + 0.2 * grain
        elif name == "slate":
            hf, tone = _blocks(hpx, 48, (40, 88), rng, joint=3)
            hf = hf * (np.linspace(0.4, 1.0, 48)[None, :].repeat(hpx // 48 + 1, 0).ravel()[:hpx][:, None])
            col = np.array(slate, float)[None, None, :] / 255 * tone[..., None] * (0.8 + 0.3 * grain)[..., None]
            r = 0.55 + 0.2 * grain
        elif name == "oak":
            boards = (np.arange(SHEET) % 96 < 3).astype(float)
            streak = _wrap_noise(hpx, rng, [(256, 0.2), (4, 0.8)])
            hf = (1 - boards)[None, :] * (0.85 + 0.15 * streak)
            col = np.array([62, 42, 28], float)[None, None, :] / 255 * (0.8 + 0.35 * streak)[..., None] * (0.6 + 0.4 * hf)[..., None]
            r = 0.7 + 0.15 * streak
        elif name == "beam":
            streak = _wrap_noise(hpx, rng, [(4, 0.7), (64, 0.3)])
            hf = 0.9 + 0.1 * streak
            col = np.array([48, 34, 24], float)[None, None, :] / 255 * (0.75 + 0.4 * streak)[..., None]
            r = 0.75 + 0.1 * streak
        elif name == "iron":
            hf = 0.9 + 0.1 * grain
            col = np.array([22, 22, 24], float)[None, None, :] / 255 * (0.8 + 0.4 * grain)[..., None]
            r = 0.45 + 0.2 * grain
        else:  # glass: leaded diamonds
            u = np.arange(SHEET)[None, :] % 32
            v = np.arange(hpx)[:, None] % 32
            lead = (np.abs(u - v) < 2) | (np.abs(u + v - 32) < 2)
            hf = np.where(lead, 1.0, 0.5)
            col = np.where(lead[..., None], np.array([20, 20, 22]) / 255, np.array([70, 62, 30]) / 255 * (0.7 + 0.5 * grain)[..., None])
            r = np.where(lead, 0.5, 0.08)
        if name in ("ashlar", "plinth", "quoin", "cobble", "slate"):
            # the joints read in the colour too: mortar dark in the recess, a pale lip where the bevel catches light
            joint = np.clip(hf * 2.5, 0, 1)
            lip = np.clip(1 - np.abs(hf - 0.35) / 0.2, 0, 1) * 0.12
            col = col * (0.35 + 0.65 * joint)[..., None] + lip[..., None]
        color[top:top + hpx] = np.clip(col, 0, 1)
        height[top:top + hpx] = hf
        rough[top:top + hpx] = np.clip(r, 0.02, 1)
    # the normal map from the height field (tangent space, +y up in the picture), wrapping left to right
    gy, gx = np.gradient(height * 3.0)
    gx[:, 0] = (height[:, 1] - height[:, -1]) * 1.5
    n = np.stack([-gx, gy, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return {"color": color, "normal": n * 0.5 + 0.5, "roughness": rough[..., None], "height": height}


def _png(path, img):
    """a uint8 picture (H x W, or H x W x 3) as a PNG with the standard library alone (Blender's Python has no PIL)"""
    import struct
    import zlib

    h, w = img.shape[:2]
    kind, rows = (0, img) if img.ndim == 2 else (2, img.reshape(h, w * img.shape[2]))
    raw = b"".join(b"\x00" + rows[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, kind, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def names():
    """the sheets' map files: kit_trim_<sheet>_<map>.png, in order (a world mesh's upload key is the file's stem)"""
    return [f"kit_trim_{sheet}_{m}.png" for sheet in SHEETS for m in MAPS]


def write(out, seed=7):
    """the sheets as PNGs: <out>/kit_trim_<sheet>_<map>.png -> [paths]"""
    try:
        from PIL import Image
    except ImportError:  # (inside Blender: the standard library writes them)
        Image = None  # noqa: N806

    os.makedirs(out, exist_ok=True)
    paths = []
    for sheet in SHEETS:
        maps = make_sheet(sheet, seed)
        for m in MAPS:  # (the height field is the normal's source, not a map of its own)
            a = maps[m]
            img = (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)
            img = img[..., 0] if img.shape[-1] == 1 else img
            p = os.path.join(out, f"kit_trim_{sheet}_{m}.png")
            if Image is not None:
                Image.fromarray(img).save(p)
            else:
                _png(p, np.ascontiguousarray(img))
            paths.append(p)
    return paths


def ensure(out, seed=7, sources=()):
    """the sheets' maps in `out`, written only when one is missing or older than this file (or one of `sources`):
    -> (paths, written?)"""
    paths = [os.path.join(out, n) for n in names()]
    newest = max([os.path.getmtime(os.path.abspath(__file__))] + [os.path.getmtime(s) for s in sources if os.path.isfile(s)])
    if all(os.path.isfile(p) and os.path.getmtime(p) >= newest for p in paths):
        return paths, False
    return write(out, seed), True
