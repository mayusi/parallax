"""build_wine_barrel.py — a new French oak wine barrel (Bordeaux barrique, 225 L). Run: lune run kit asset wine_barrel

DESIGN (the brief: assets/models/wine_barrel.brief.md; the owner 2026-10-17: "make me a 3d model of a BARREL properly")
  what it is: a new 225 L Bordeaux barrique, standing on one head; a showcase piece
  size: 950 mm tall, 690 mm at the belly, 550 mm at the heads (pack: Tonnellerie Gillet + Winegrowers Supplies)
  silhouette: the bulge; six bright hoops cutting it into bands
  big: 30 staves, 2 heads · medium: 6 hoops, the chime (the head set below the stave ends) · small: 12 nails, the bung,
  the seams between staves and head boards
  palette: pale new oak (209, 161, 127 in the photo), board-to-board tone; galvanized steel; a white silicone bung
EVERY NUMBER FROM DATA: the profile from the traced photo (wine_barrel_side), the heights and diameters from the
pack's two-source sizes, the hoop heights measured on the same photo — nothing typed from memory.
"""

import json
import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

MM = 280.0
pk_path = os.path.join(_root, "assets", "models", "wine_barrel.pack.json")
with open(pk_path, encoding="utf-8") as fh:
    sizes = json.load(fh).get("sizes") or {}
H = float(sizes["overall.height"]["mm"])        # 950 (two sources agree)
R_BELLY = float(sizes["belly.diameter"]["mm"]) / 2   # 345 (690 / 685 from two sources)
R_HEAD = float(sizes["head.diameter"]["mm"]) / 2     # 275 (Gillet: "Diamètre en tête : 0,55 m")
T = 27.0        # stave thickness (Gillet: staves 25 / 27 mm)
N = 30          # staves (photo: ~11 seams across the visible half of the belly)
SEAM = 0.25     # degrees between staves (~1.5 mm at the belly: the dark seam lines in the photo)
CHIME = 42.0    # the stave ends past the head (the photo's top hoop sits on it)

# the profile: the traced outline's width at each height, top and bottom averaged (the camera looks down a little:
# the halves differ by the perspective, the barrel does not), as a curve in u = (2f - 1)^2 pinned to the measured
# belly and head radii
with open(os.path.join(_root, "assets", "models", "wine_barrel_side.trace.json"), encoding="utf-8") as fh:
    outline = np.array(json.load(fh)["outline"], float)


def width_at(h):
    xs = []
    for k in range(len(outline)):
        a, b = outline[k], outline[(k + 1) % len(outline)]
        if (a[1] - h) * (b[1] - h) <= 0 and a[1] != b[1]:
            xs.append(a[0] + (h - a[1]) / (b[1] - a[1]) * (b[0] - a[0]))
    return max(xs) - min(xs) if len(xs) >= 2 else np.nan


lo, hi = outline[:, 1].min(), outline[:, 1].max()
fs = np.linspace(0.08, 0.92, 22)
w = np.array([width_at(lo + f * (hi - lo)) for f in fs])
w = (w + w[::-1]) / 2
w = w / np.nanmax(w)
u = (2 * fs - 1) ** 2
# r(u) = R_BELLY - (R_BELLY - R_HEAD) * (a u + (1 - a) u^2): its shape `a` from the photo, its ends from the sizes
drop = (1 - w) * R_BELLY / (R_BELLY - R_HEAD)
A = np.column_stack([u - u ** 2])
a_shape = float(np.clip(np.linalg.lstsq(A, drop - u ** 2, rcond=None)[0][0], 0.0, 1.5))


def r_out(y):
    uu = (2 * np.asarray(y, float) / H - 1) ** 2
    return R_BELLY - (R_BELLY - R_HEAD) * (a_shape * uu + (1 - a_shape) * uu ** 2)


ys = np.linspace(0, H, 49)
PROFILE = [[round(float(r_out(y)), 3), round(float(y), 3)] for y in ys]
# the hoops: (from the top, from the bottom) as fractions of the height, measured on wine_barrel_side (rows of the
# grey bands at its middle column, the halves averaged): chime, second, quarter
HOOPS = [(0.000, 0.055), (0.125, 0.165), (0.310, 0.360)]
HOOP_T = 2.0    # galvanized band thickness

a = rbx.Asset("wine_barrel", tex=2048, size=(round(2 * R_BELLY / MM, 4), round(H / MM, 4), round(2 * R_BELLY / MM, 4)),
              ground=True, stage="master", private=False, ref_image="refs/wine_barrel_side.jpg")
a.real_scale(MM)


def lin(c):
    c = np.asarray(c, float) / 255.0
    return tuple(float(round(v, 4)) for v in np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


OAK = (209, 161, 127)   # the photo's stave field median (refs/wine_barrel_side.jpg)
for i, k in enumerate((1.0, 0.92, 1.07)):   # three tones board to board, as new staves differ
    a.material(f"oak{i}", lin(np.clip(np.array(OAK) * k, 0, 255)), rough=0.72, scan="Wood066", scan_mix=1.0,
               scan_color=0.35, scan_grain="up", vary=0.2, life="new")   # (a faint grain: new oak's is fine and subtle)
a.material("galvanized", **rbx.finish("machined_steel", rough=0.22), life="new")   # (galvanized band: a bright, fairly sharp reflection, as in the photo)
a.material("silicone", (0.78, 0.78, 0.76), rough=0.55)
a.material("inside", lin((70, 38, 42)), rough=0.8, scan="Wood066", scan_mix=1.0, scan_color=0.3)   # (the inner wall behind the seams: wine-stained oak)

STAVE = '''
step = 360.0 / P["n"]
arc = step - P["seam"]
outer = [(r, y) for r, y in P["profile"]]
inner = [(r - P["t"], y) for r, y in reversed(P["profile"])]
with BuildPart() as part:
    with BuildSketch(Plane.XY):
        with BuildLine():
            Polyline(*(outer + inner), close=True)
        make_face()
    revolve(axis=Axis.Y, revolution_arc=arc)
part = part.part.rotate(Axis.Y, P["phi"] - arc / 2)
'''
for k in range(N):
    phi = step = 360.0 / N
    phi = step / 2 + k * step   # (a stave centred on 90 deg: the FRONT, -Z, carries the bung)
    a.cad(f"Stave{k:02d}", STAVE, f"oak{(k * 7) % 3}", params={"profile": PROFILE, "t": T, "n": N, "seam": SEAM,
                                                            "phi": phi}, tol=0.3, angle=6.0)

# the inner wall: the staves' inside face as one shell a hair inside them — what the seams show (light passed
# straight through the 1.5 mm seams: see_through)
LINER = '''
band = [(r, y) for r, y in P["profile"] if P["y0"] <= y <= P["y1"]]   # (between the heads: the chime shows oak)
outer = [(r - P["t"] - 0.3, y) for r, y in band]
inner = [(r - P["t"] - 2.3, y) for r, y in reversed(band)]
with BuildPart() as part:
    with BuildSketch(Plane.XY):
        with BuildLine():
            Polyline(*(outer + inner), close=True)
        make_face()
    revolve(axis=Axis.Y)
'''
a.cad("Inside", LINER, "inside", params={"profile": PROFILE, "t": T, "y0": CHIME + 30.0, "y1": H - CHIME - 30.0},
      tol=0.3, angle=6.0)

HOOP = '''
lo_y, hi_y = P["y0"], P["y1"]
outer = [(r + P["t"], y) for r, y in P["band"]]
inner = [(r, y) for r, y in reversed(P["band"])]
with BuildPart() as part:
    with BuildSketch(Plane.XY):
        with BuildLine():
            Polyline(*(outer + inner), close=True)
        make_face()
    revolve(axis=Axis.Y)
part = fillet(part.part.edges(), 0.6)   # (a rolled band's edges are soft, never knife-sharp)
'''
hoop_spans = []
for i, (f0, f1) in enumerate(HOOPS):
    for end in ("top", "bottom"):
        y0, y1 = ((1 - f1) * H, (1 - f0) * H) if end == "top" else (f0 * H, f1 * H)
        y0, y1 = max(y0, 2.0), min(y1, H - 2.0)   # (the chime hoop stops just short of the stave ends)
        band = [[round(float(r_out(y)), 3), round(float(y), 3)] for y in np.linspace(y0, y1, 9)]
        name = f"Hoop{i}{end[0].upper()}"
        a.cad(name, HOOP, "galvanized", params={"band": band, "t": HOOP_T, "y0": y0, "y1": y1}, tol=0.2, angle=4.0)
        hoop_spans.append((name, (y0 + y1) / 2))

BUNG_PHI = 318.0   # the stave the showcase camera faces (stave 26: 6 + 12 x 26 deg) carries the bung, as in the photo
# two dome nails on each hoop, on one line up the barrel (the photo: every hoop's pair sits under the last)
for name, yc in hoop_spans:
    rr = (float(r_out(yc)) + HOOP_T + 1.2) / MM   # (a dome head sits ON the band: mostly above it)
    for j, d in enumerate((-2.2, 2.2)):   # degrees either side of the line
        ang = np.radians(BUNG_PHI - 12.0 + d)   # the nail line, one stave beside the bung
        a.sphere(f"{name}Nail{j}", 4.5 / MM, (rr * np.cos(ang), yc / MM, -rr * np.sin(ang)), "galvanized",
                 scale=(1.0, 1.0, 0.45))

# the heads: boards set into the staves below their ends (the chime), five boards a hair apart
HEAD = '''
r = P["r"]
boards = None
for b in range(P["boards"]):
    w = 2 * r / P["boards"]
    x0 = -r + b * w + P["gap"] / 2
    slab = Box(w - P["gap"], P["t"], 2 * r + 2, align=(Align.MIN, Align.CENTER, Align.CENTER))
    slab = slab.translate((x0, 0, 0))
    piece = Cylinder(r, P["t"], rotation=(90, 0, 0)) & slab
    boards = piece if boards is None else boards + piece
# the head's outer face bevelled at its rim (a cooper planes it to sit in the croze), each board's edges eased
part = chamfer(boards.edges().filter_by(GeomType.CIRCLE), P["bevel"])
'''
for end, y in (("Top", H - CHIME - 15.0), ("Bottom", CHIME + 15.0)):
    a.cad(f"Head{end}", HEAD, "oak1", pos=(0, y / MM, 0),
          params={"r": round(float(r_out(y)) - T + 0.5, 3), "t": 30.0, "boards": 5, "gap": 1.2, "bevel": 6.0}, tol=0.3, angle=6.0)

# the bung: a white silicone plug at the belly in the front stave
BUNG = '''
part = Cone(P["r1"], P["r0"], P["h"])   # (along z: its wide end out, -z)
part = part.translate((0, 0, -P["rb"])).rotate(Axis.Y, P["phi"] - 90.0)   # (round to its stave, as the staves turn)
'''
yb = H / 2
a.cad("Bung", BUNG, "silicone", pos=(0, yb / MM, 0), params={"r0": 22.0, "r1": 26.0, "h": 24.0,
                                                           "rb": float(r_out(yb)) + 6.0, "phi": BUNG_PHI},
      tol=0.2, angle=6.0)

a.expect("Hoop0T", touches="Stave00")
a.build()
