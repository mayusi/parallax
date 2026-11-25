"""sharpen_math.py — the arithmetic of SHARPENING a generated part (kit gen sharpen; plain numpy, no Blender).

A 3D generator's shape is sound and its surface is soft: no feather ridges, no fur, a smeared colour map. A local
image model draws exactly that detail — but as a picture. The loop that joins them, one view at a time:

    render   the part as it is now from a view
    redraw   that render sharp (kit vision plate --from <render>: the redraw KEEPS the render's layout)
    project  the redraw back through the same camera into the part's own colour map

Every view builds on the ones before it, so the detail agrees across views. First run on the Gjallarhorn's wolf
(2026-11-12): six views, about 55 s each; the owner on the route's first part: "Wow, I'm actually kind of amazed".

Here: the cameras (view_direction, frame), where a point lands in a view's picture (ortho_uv), how much a view's
picture counts at a surface point (view_weight), the blend into the colour map (blend, in linear light), the maps a
game material needs from the sharpened colour (maps: colour / roughness / a tangent-space normal map), and the FOLD
that lays a generated pair of wings back along the part they sit on (find_split, fold) and FLARES them out to its
width while the head keeps its own (flare), with two fits for a head: its muzzle lengthened (snout) and the head
pitched down (nod). kit/gen/sharpen_part.py is the Blender side; kit/test/python/test_sharpen_math.py pins every convention below.

Space: Blender's (z up). A part's FACE yaw is the camera yaw from which it is seen face-on; yaw 0 = the camera on -Y
looking along +Y (TRELLIS.2's GLBs face it), positive yaw swings the camera towards +X.
"""

import math

import numpy as np

# the views a part is sharpened from, in order: (name, yaw from face-on, pitch, how the redraw's prompt says it)
VIEWS = (
    ("side_left", 90.0, 0.0, "seen from its left side"),
    ("front", 0.0, 0.0, "seen from the front, facing the camera"),
    ("side_right", -90.0, 0.0, "seen from its right side"),
    ("front_left", 45.0, 15.0, "seen from the front left"),
    ("front_right", -45.0, 15.0, "seen from the front right"),
    ("top", 90.0, 78.0, "seen from above"),
)
OWN_SAY = 0.03      # how much the generator's own colour counts where no view has drawn yet (and under every view)
FACING_POWER = 3.0  # a view counts by how squarely it sees a surface: facing ^ this


def view_direction(yaw, pitch):
    """the unit vector from the part to the camera for a camera yaw / pitch in degrees"""
    y, p = math.radians(float(yaw)), math.radians(float(pitch))
    return np.array([math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)])


def frame(width, height, megapixels=1.0, multiple=16, margin=1.10):
    """a view's picture size for an object `width` x `height` (any unit) in view: about `megapixels`, both sides a
    multiple of `multiple` (the image model's grid), the object inside a `margin` -> (pixels x, pixels y, the
    half-width and half-height the picture spans, in the object's unit). An orthographic camera's scale spans the
    LONGER side of the frame: the spans are derived from the rounded pixel sizes, never from the object's own"""
    w, h = float(width) * margin, float(height) * margin
    k = math.sqrt(megapixels * 1024.0 * 1024.0 / (w * h))
    rx, ry = max(multiple, int(w * k) // multiple * multiple), max(multiple, int(h * k) // multiple * multiple)
    if rx >= ry:
        return rx, ry, w / 2.0, w * ry / rx / 2.0
    return rx, ry, h * rx / ry / 2.0, h / 2.0


def ortho_uv(points, camera, half_w, half_h):
    """where points (N, 3) land in an orthographic camera's picture -> (N, 2), u right and v UP, both 0..1 across
    the frame. camera: its 4 x 4 world matrix (it looks along its own -Z, its +Y is the picture's up)"""
    inv = np.linalg.inv(np.asarray(camera, dtype=np.float64))
    cc = np.asarray(points, dtype=np.float64) @ inv[:3, :3].T + inv[:3, 3]
    return np.stack([cc[:, 0] / (2.0 * half_w) + 0.5, cc[:, 1] / (2.0 * half_h) + 0.5], axis=1)


def toward_camera(camera):
    """the unit vector from the scene to an orthographic camera (its +Z axis)"""
    z = np.asarray(camera, dtype=np.float64)[:3, 2]
    return z / np.linalg.norm(z)


def view_weight(normals, toward, seen, power=FACING_POWER):
    """how much a view's picture counts at each surface point: 0 where the view does not see it (`seen` 0: something
    stands between it and the camera) or it faces away, else (how squarely it faces the camera) ^ power"""
    facing = np.clip(np.asarray(normals, dtype=np.float64) @ np.asarray(toward, dtype=np.float64), 0.0, 1.0)
    return np.asarray(seen, dtype=np.float64) * facing ** float(power)


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, np.power((np.maximum(c, 0.0) + 0.055) / 1.055, 2.4))


def linear_to_srgb(c):
    c = np.asarray(c, dtype=np.float64)
    return np.clip(np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0.0), 1.0 / 2.4) - 0.055), 0, 1)


def blend(old, said, colour, weight):
    """one view's projected colour blended into the colour map, in LINEAR light: old (H, W, 3) with `said` (H, W) =
    the weight everything so far carries; colour (H, W, 3) with this view's `weight` -> (new map, new said). A texel
    no view touches keeps its colour exactly; a second view moves a texel only by its share of the weight"""
    said, weight = np.asarray(said, dtype=np.float64), np.clip(np.asarray(weight, dtype=np.float64), 0.0, 1.0)
    total = said + weight
    new = (np.asarray(old, dtype=np.float64) * said[..., None] + np.asarray(colour, dtype=np.float64) * weight[..., None]) \
        / np.maximum(total, 1e-9)[..., None]
    return new, total


def match_colour(picture, first, keep=0.3):
    """a redraw's colours brought to the FIRST redraw's (each one picks its own bronze): per channel, its mean moved
    to the first's and its spread most of the way (`keep` of its own contrast stays). Arrays 0..1, any shape (..., 3)"""
    a, b = np.asarray(picture, dtype=np.float64), np.asarray(first, dtype=np.float64)
    out = np.empty_like(a)
    for c in range(3):
        mean, spread = a[..., c].mean(), a[..., c].std() or 1.0
        gain = (1.0 - keep) * (b[..., c].std() / spread) + keep
        out[..., c] = (a[..., c] - mean) * gain + b[..., c].mean()
    return np.clip(out, 0.0, 1.0)


def _blur(a, sigma):
    """a small separable Gaussian (edges repeated)"""
    if sigma <= 0:
        return a
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for axis in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[axis] = (r, r)
        p = np.pad(a, pad, mode="edge")
        a = sum(k[i] * np.take(p, np.arange(i, i + a.shape[axis]), axis=axis) for i in range(2 * r + 1))
    return a


GOLD = ((0.0, (0.10, 0.06, 0.03)), (0.22, (0.45, 0.29, 0.11)), (0.60, (0.86, 0.66, 0.30)), (1.0, (1.0, 0.88, 0.60)))


def maps(colour, metal_ramp=None, normal_strength=1.0, used=None):
    """the sharpened colour map (H, W, 3 sRGB 0..1, row 0 at the TOP as a picture is stored) -> the maps of a game
    material:
      colour     itself — or, with metal_ramp (GOLD: [(light 0..1, (r, g, b)), ...]), its light and dark carried
                 onto that metal: dark patina in the recesses, bright metal on the raised edges
      roughness  (H, W): the recesses duller (0.62), the raised edges polished (0.26)
      normal     (H, W, 3) 0..1: a tangent-space normal map (x right, y UP, z out — glTF's) from the map's own light
                 and dark as height: a carved dark line reads as a groove
    used: the texels that are surface (default: not black padding) — the light range is read from them alone.
    The normal map is the colour's light and dark, not a measured height: keep normal_strength low (1.0; at 2.5 a
    redraw's speckle read as a crust on the wolf's gold)."""
    rgb = np.asarray(colour, dtype=np.float64)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    mask = (lum > 0.01) if used is None else np.asarray(used, dtype=bool)
    lo, hi = np.percentile(lum[mask], [2, 98]) if mask.any() else (0.0, 1.0)
    t = np.clip((lum - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    if metal_ramp:
        stops = np.array([s for s, _c in metal_ramp])
        cols = np.array([c for _s, c in metal_ramp])
        out = np.stack([np.interp(t, stops, cols[:, c]) for c in range(3)], axis=-1)
    else:
        out = rgb
    rough = 0.62 - 0.36 * t
    h = _blur(t, 0.8)
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5      # height rising to the right
    dy = (np.roll(h, 1, axis=0) - np.roll(h, -1, axis=0)) * 0.5      # height rising UP the picture (rows run down)
    k = float(normal_strength) * h.shape[0] / 1024.0
    n = np.stack([-dx * k, -dy * k, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return out, rough, n * 0.5 + 0.5


# ------------------------------------------------------------------------------------------------ the fold
def find_split(along, across, bins=160, clear=0.02):
    """where a pair of wings PART behind a head: `along` runs from the nose back, `across` is measured from the
    middle plane. The first slice — with only parted slices after it — whose points all keep `clear` (a share of
    the whole width) away from the middle -> the `along` value there, or None when the two never part"""
    along, across = np.asarray(along, dtype=np.float64), np.asarray(across, dtype=np.float64)
    edges = np.linspace(along.min(), along.max(), bins + 1)
    which = np.clip(np.digitize(along, edges) - 1, 0, bins - 1)
    wide = across.max() - across.min()
    split = bins
    for b in range(bins - 1, -1, -1):
        sel = which == b
        if sel.any() and np.abs(across[sel]).min() <= clear * wide:
            break
        split = b
    return None if split >= bins - 5 else float(edges[split])


def splay(along, across, split, bins=160):
    """each wing's angle from straight back, behind the split -> [(degrees, across at the split)] for the +across
    wing then the -across one (its middle line fitted through the slices' medians)"""
    along, across = np.asarray(along, dtype=np.float64), np.asarray(across, dtype=np.float64)
    edges = np.linspace(split, along.max(), max(8, bins // 2) + 1)
    out = []
    for side in (1.0, -1.0):
        ys, xs = [], []
        for b in range(len(edges) - 1):
            sel = (along >= edges[b]) & (along < edges[b + 1]) & (np.sign(across) == side)
            if sel.sum() >= 20:
                ys.append((edges[b] + edges[b + 1]) / 2.0)
                xs.append(float(np.median(across[sel])))
        if len(ys) < 3:
            raise ValueError("fold: a wing has too few points behind the split to measure")
        slope, x0 = np.polyfit(np.asarray(ys) - split, np.asarray(xs), 1)
        out.append((math.degrees(math.atan(slope * side)), float(x0)))
    return out


def fold(along, across, split, wings, keep=0.0, ease=0.10):
    """turn everything behind `split` on each side about a vertical hinge at (split, that wing's `across` there) by
    the wing's own splay (less `keep` degrees), eased in over `ease` of the whole length, so the wings run straight
    back -> (along, across) after. A point on the middle plane or ahead of the split does not move"""
    along, across = np.asarray(along, dtype=np.float64), np.asarray(across, dtype=np.float64)
    a2, c2 = along.copy(), across.copy()
    length = along.max() - along.min()
    for side, (deg, hinge) in zip((1.0, -1.0), wings):
        sel = (np.sign(across) == side) & (along > split)
        da = along[sel] - split
        t = np.clip(da / max(ease * length, 1e-9), 0.0, 1.0)
        ang = side * math.radians(max(0.0, deg - keep)) * (t * t * (3.0 - 2.0 * t))
        dc = across[sel] - hinge
        c2[sel] = hinge + dc * np.cos(ang) - da * np.sin(ang)
        a2[sel] = split + dc * np.sin(ang) + da * np.cos(ang)
    return a2, c2


def flare(along, across, factor, start=0.33, end=0.50):
    """widen what lies BEHIND a head and leave the head as it is -> across after. Ahead of `start` (a share of the
    whole length from the nose) nothing moves; behind `end` every point is `factor` times as far from the middle
    plane; between them it eases. A generated head-and-wings is as narrow as its head, but its wings lie on something
    wider (the wolf: a 96 mm housing): stretching the WHOLE part to reach round it made the face 1.59 times too
    broad (the owner, 2026-11-12: "Fix the face first")."""
    along, across = np.asarray(along, dtype=np.float64), np.asarray(across, dtype=np.float64)
    lo, length = along.min(), max(along.max() - along.min(), 1e-12)
    t = np.clip((along - (lo + start * length)) / max((end - start) * length, 1e-12), 0.0, 1.0)
    return across * (1.0 + (float(factor) - 1.0) * (t * t * (3.0 - 2.0 * t)))


def level(along, across, width, start=0.33, end=0.50, bins=96):
    """bring the body BEHIND a head to one width and leave the head as it is -> across after. `width` is the full
    width (a share of the whole length) the part has from `end` of its length back to its tail: at every station
    its outermost point lands on that width, whatever its own was; ahead of `start` nothing moves; between them it
    eases. A generated head-and-wings in ONE solid piece is a wedge - it widens steadily to its tail - but what it
    lies on has flat flanks: on the launcher's stock the wedge's front half sank inside the stock and only the wing
    tips showed, where the render's wing lies on the flank from the head to its tip. (`flare` multiplies: it would
    have pushed the tail half a width off the stock.)"""
    along, across = np.asarray(along, dtype=np.float64), np.asarray(across, dtype=np.float64)
    lo, length = along.min(), max(along.max() - along.min(), 1e-12)
    t = (along - lo) / length
    own = np.zeros(bins)                               # the part's own half width, station by station
    np.maximum.at(own, np.clip((t * bins).astype(int), 0, bins - 1), np.abs(across))
    seen = own > 0
    if not seen.any():
        return across.copy()
    centres = (np.arange(bins) + 0.5) / bins
    own = np.interp(centres, centres[seen], own[seen])  # (a station with no point takes its neighbours')
    pad = np.concatenate([own[:3][::-1], own, own[-3:][::-1]])
    own = np.convolve(pad, np.ones(7) / 7.0, mode="valid")   # (a smooth outline: a single feather tip is not a step)
    here = np.maximum(np.interp(t, centres, own), 1e-9)
    ease = np.clip((t - start) / max(end - start, 1e-12), 0.0, 1.0)
    ease = ease * ease * (3.0 - 2.0 * ease)
    return across * (1.0 + (0.5 * float(width) * length / here - 1.0) * ease)


def tail(along, factor, start=0.36, end=0.52, steps=512):
    """lengthen what lies BEHIND a head -> along after. Ahead of `start` (a share of the whole length from the nose)
    nothing moves; behind `end` every span is `factor` times as long; between them the stretch eases in, so no
    feather is cut by a step. A generator draws a head-and-wings with a head about as long as its wings, where a
    carved one has a small head and a long wing: the launcher's nose wolf measured 85 mm from nose to brow against
    its chart's 43, on the right overall length. Scaling the whole part cannot fix a proportion; this does, and the
    part is then sized by its whole length as before."""
    along = np.asarray(along, dtype=np.float64)
    lo, length = along.min(), max(along.max() - along.min(), 1e-12)
    grid = np.linspace(0.0, 1.0, steps + 1)
    ease = np.clip((grid - start) / max(end - start, 1e-12), 0.0, 1.0)
    local = 1.0 + (float(factor) - 1.0) * ease * ease * (3.0 - 2.0 * ease)
    new = np.concatenate([[0.0], np.cumsum((local[1:] + local[:-1]) / 2.0 * np.diff(grid))])
    return lo + length * np.interp((along - lo) / length, grid, new)


def snout(along, factor, upto=0.16):
    """lengthen a muzzle -> along after: everything AHEAD of `upto` (a share of the whole length from the nose: about
    where the eyes are) is `factor` times as far from that line; nothing behind it moves. A generator's wolf came
    out stub-nosed beside its reference (head 53 mm long x 72 tall against 55 x 50)."""
    along = np.asarray(along, dtype=np.float64)
    lo, length = along.min(), max(along.max() - along.min(), 1e-12)
    line = lo + upto * length
    return np.where(along < line, line - (line - along) * float(factor), along)


def nod(along, up, degrees, hinge=0.30, height=0.42, ease=0.12):
    """pitch a head DOWN about a hinge in its neck -> (along, up) after. The hinge: `hinge` of the whole length from
    the nose, `height` of the whole height from the bottom. What lies ahead of it turns by `degrees` (the nose
    drops), eased in over `ease` of the length; nothing behind the hinge moves. A generator sets a head level; a
    figurehead looks down, and seen from the front a level head shows a short broad face where a nodding one shows
    its long forehead and muzzle."""
    along, up = np.asarray(along, dtype=np.float64), np.asarray(up, dtype=np.float64)
    lo, length = along.min(), max(along.max() - along.min(), 1e-12)
    a0 = lo + hinge * length
    z0 = up.min() + height * (up.max() - up.min())
    ahead = np.clip((a0 - along) / max(ease * length, 1e-12), 0.0, 1.0)
    ang = math.radians(float(degrees)) * (ahead * ahead * (3.0 - 2.0 * ahead))
    va, vz = along - a0, up - z0
    return a0 + va * np.cos(ang) - vz * np.sin(ang), z0 + va * np.sin(ang) + vz * np.cos(ang)
