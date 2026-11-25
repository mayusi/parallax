"""fxfinish.py — turns fxlab's HDR frames into Roblox-ready textures: glow, streaks, hot-core-to-white, alpha, sheet.

    python kit/vfx/fxfinish.py --specs assets/textures --frames build/fxlab --out build/textures [name ...]

For every "engine": "fx" spec whose frames exist (build/fxlab/<name>/*.npy from kit/vfx/fxlab.py):
  1. glow    — bloom (gaussian, energy above 1 spreads) + optional star streaks (light-ray flares), on HDR values
  2. tone    — 1 - exp(-x * exposure) per channel: the hottest parts saturate to WHITE while the edges keep their hue
               (the anime / film look: white-hot core, gold body, amber rim)
  3. alpha   — "glow": alpha = max(coverage, brightness) and colour un-premultiplied, so a glow halo on black becomes
               a soft sprite that works with Roblox LightEmission 1 (additive) and 0 (solid);
               "coverage": the render's own alpha (lit dust / smoke volumes)
  4. colour  — "color" keeps the baked colours (ColorSequence white in the preset); "gray" keeps only brightness
               (the preset's colour tints it); "cel" N posterises brightness into N bands (anime cel shading);
               "cel_color" the same bands keeping the baked hue (a white-hot core stays white on an orange body);
               "cut": 0.35 thresholds the alpha into a hard drawn silhouette (with "outline": an inked cel puff)
               "edges": {...} EDGE DETECTION - a line wherever the picture STEPS, inside the shape as well as round it
               (the border between two tones of a cel look, a core against its body, one colour against another),
               not only round the silhouette as "outline" does: {"threshold": 0.08 (how sharp a step is a line: a
               full step measures about 0.32, the border of two of four bands about 0.1, a soft ramp next to
               nothing), "grow": 0 (extra px of line), "color": [r, g, b] 0-1, "keep": true (false = the LINES ALONE:
               line art)}. It runs after every other look AND after "erode" (a dissolve's holes get their lines),
               before the cell's border fade. A sheet that asks for edges and has none in any frame is refused
               "aberration": {...} CHROMATIC ABERRATION - the picture's RED and BLUE are pulled apart as a lens does
               at the edge of its view: {"amount": 0.03 (how far each parts from green at the cell's edge, as a
               share of the cell: 0.004 to 0.1), "mode": "radial" (red drawn larger, blue smaller, about the cell's
               middle: nothing parts at the middle, most at the rim) | "axis" (red slid one way, blue the other,
               along "angle" degrees by `amount` of the cell's SHORT side, the same everywhere)}. It is a real split of the three colours of THIS
               picture (Roblox cannot split the screen's), the last look of all: after "edges", before the cell's
               border fade. Refused on a strip that wraps or a beam's texture, when it would part the colours by under a pixel of
               the sheet as it is saved, and when no frame gets a fringe
               "inbetween": true | {"loop": false} MOTION VECTORS - the sheet's `grid` is FILLED from fewer
               rendered frames: every cell is a moment of the frames' own timeline, and a moment between two
               frames is drawn by the picture's own motion. For every two frames in a row the packer measures
               where each bit of the picture goes (a motion vector a pixel, both ways), then draws the cell by
               moving the two frames part of the way along those vectors and mixing them (a cross-fade leaves two
               ghosts; this leaves one shape, part of the way). N frames fill all cols x rows cells: the first
               cell is the first frame and the last cell the last frame ("loop": true - the sheet plays round:
               the last cell is one step short of the first frame again). The grid must have MORE cells than
               there are frames, and no cell is left empty (Roblox plays every cell). It runs after every look
               and "erode", before "edges" and "aberration" (lines and fringes are drawn on every cell).
               Refused when nothing moves between any two frames; when, over the whole sheet, the vectors do
               not account for half of the change between frames (the picture changes instead of moving, or
               the frames are too far apart to follow); and when a part of the picture is not followed (a
               small thing that jumps while the rest drifts)
  5. sheet   — frames packed into a grid (Grid2x2/4x4/8x8 or Custom cols x rows), a transparent border per cell
               (mip bleed), or a seamless strip for beams ("wrap": true keeps the left/right edges joined;
               "beam": true turns it upright — Roblox runs a beam texture's vertical axis along the beam)
Gate per texture: power-of-two size <= 1024 (strips: each side), RGBA, not empty, cell borders clear, frames
actually change (an animated sheet whose frames are identical is a bug). Also writes build/textures/_fx_review.png:
every texture over black and over grey, labelled — LOOK at it.
Prints one JSON line: {status, summary, next_action, textures:[{name, file, grid, checks}]}.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def load_frames(fdir):
    files = sorted(f for f in os.listdir(fdir) if f.endswith(".npy"))
    return [np.load(os.path.join(fdir, f)).astype(np.float32) for f in files]


def bloom(rgb, size, strength, radius):
    """energy above 1 (and a little below) spreads in two gaussian scales"""
    if strength <= 0:
        return rgb
    hot = np.clip(rgb - 0.6, 0, None)
    r = max(1.0, radius * size)
    halo = ndimage.gaussian_filter(hot, (r, r, 0)) * 0.65 + ndimage.gaussian_filter(hot, (r * 3, r * 3, 0)) * 0.35
    return rgb + halo * strength * 4


def _decay_max(a, decay):
    """along axis 1, both ways: out[i] = max(a[i], out[i-1] * decay) — a glare ray that does not grow with area"""
    out = a.copy()
    for i in range(1, a.shape[1]):
        np.maximum(out[:, i], out[:, i - 1] * decay, out=out[:, i])
    back = a.copy()
    for i in range(a.shape[1] - 2, -1, -1):
        np.maximum(back[:, i], back[:, i + 1] * decay, out=back[:, i])
    return np.maximum(out, back)


def _decay_one_way(a, decay):
    out = a.copy()
    for i in range(1, a.shape[1]):
        np.maximum(out[:, i], out[:, i - 1] * decay, out=out[:, i])
    return out


def streaks(rgb, size, count, length, strength, angle):
    """star flare: the hottest points smeared along `count` directions (4 = a cross, 6 = a star, 2 = anamorphic)"""
    if count <= 0 or strength <= 0:
        return rgb
    hot = np.clip(rgb - 1.0, 0, None)
    decay = float(np.exp(-4.0 / max(3.0, length * size)))
    rays = np.zeros_like(rgb)
    even = count % 2 == 0
    lines = count // 2 if even else count  # an even count draws lines (two rays each); an odd one draws single rays
    for i in range(lines):
        a = angle + (180.0 if even else 360.0) * i / lines
        rot = ndimage.rotate(hot, a, axes=(1, 0), reshape=False, order=1)
        sm = _decay_max(rot, decay) if even else _decay_one_way(rot, decay)
        rays = np.maximum(rays, ndimage.rotate(sm, -a, axes=(1, 0), reshape=False, order=1))
    rays = ndimage.gaussian_filter(rays, (0.7, 0.7, 0))
    return rgb + np.clip(rays - hot, 0, None) * strength


EDGE_SIGMA = 1.0  # the picture is smoothed by this before its steps are measured (single-pixel noise is no edge)
EDGE_LEAST = 24  # a sheet whose strongest frame has fewer line pixels than this has no edge (a count, not a share:
# a small hard shape on a big cell is a real line)


def edge_lines(col, a, ed, wrap=False, silhouette=True):
    """EDGE DETECTION on one finished frame (straight colour `col`, alpha `a`) -> the line's strength per pixel (0..1).
    A step of `threshold` a pixel or more in ANY colour channel of the picture as it is seen (colour x alpha: red
    against green is a step though both are as bright) or in its alpha (the silhouette; left out with silhouette
    false), after a one-pixel smoothing, is a line. A full step measures about 0.32, a ramp over 20 px about 0.05.
    wrap: the strip joins left to right, so a step across that seam is measured too"""
    thr = max(1e-3, float(ed.get("threshold", 0.08)))
    seen = np.clip(col, 0, 1) * a[..., None]  # (nothing outside the shape has a colour)
    fields = [seen[..., 0], seen[..., 1], seen[..., 2]] + ([a] if silhouette else [])
    mag = np.zeros(a.shape)
    for field in fields:
        sm = ndimage.gaussian_filter(field.astype(np.float64), EDGE_SIGMA, mode=("nearest", "wrap") if wrap else "nearest")
        gy = np.gradient(sm, axis=0)
        gx = (np.roll(sm, -1, axis=1) - np.roll(sm, 1, axis=1)) / 2 if wrap else np.gradient(sm, axis=1)
        mag = np.maximum(mag, np.hypot(gx, gy))
    line = np.clip((mag - thr) / (thr * 0.5), 0, 1)
    grow = int(ed.get("grow", 0))
    if grow > 0:
        line = ndimage.grey_dilation(line, size=(2 * grow + 1, 2 * grow + 1), mode="wrap" if wrap else "nearest")
    return line


FINAL_LOOKS = ("edges", "aberration")     # the looks drawn on a FINISHED cell: they change no colour of the sheet below them


def last_looks(spec_path):
    """the final looks (post.edges, post.aberration) the spec that is THERE asks for -> {name: block}. A tool that
    writes its sheet's spec again (kit vfx dissolve, kit vfx ink) keeps them: it wrote a fixed "post" on every run,
    and a line or a fringe added to the sheet by hand was gone the next time the tool ran"""
    try:
        with open(spec_path, encoding="utf-8") as fh:
            post = json.load(fh).get("post")
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: post[k] for k in FINAL_LOOKS if isinstance(post, dict) and isinstance(post.get(k), dict)}


def inner_lines(line, a):
    """how many of a frame's line pixels lie INSIDE its shape (four pixels or more in from its silhouette): a sheet
    whose lines are all on its silhouette has an outline, not the steps inside it that edge detection is for"""
    inside = ndimage.binary_erosion(a > 0.5, iterations=4)
    return int(((line > 0.5) & inside).sum())


def apply_edges(f, ed, wrap=False, silhouette=True):
    """one finished frame (straight RGBA) with its edge lines drawn -> (the frame, the line). The line is laid OVER
    the picture as paint is: where it leaves the shape its colour is its own, not the nothing behind it (a bright
    line would otherwise carry a dark fringe)"""
    col, a = f[..., :3], f[..., 3]
    line = edge_lines(col, a, ed, wrap, silhouette)
    ec = np.array(ed.get("color", [0.04, 0.05, 0.09]), dtype=np.float64)
    if ed.get("keep", True) is False:  # line art: the lines alone
        return np.dstack([np.broadcast_to(ec, col.shape), line]), line
    under = a * (1 - line)
    a2 = np.maximum(a, line)
    out = (col * under[..., None] + ec * line[..., None]) / np.maximum(under + line, 1e-6)[..., None]
    return np.dstack([np.where((under + line)[..., None] > 1e-6, out, col), a2]), line


def aberration_block(ab, size, wrap, beam=False):
    """a spec's post.aberration as the packer reads it -> None (off) or the block; raises ValueError saying what is wrong"""
    if ab is None or ab is False:
        return None
    if not isinstance(ab, dict):
        raise ValueError('post.aberration is a block: {"amount": 0.03, "mode": "radial"} or {"amount": 0.03, "mode": "axis", "angle": 0}')
    unread = sorted(set(ab) - {"amount", "mode", "angle"})
    if unread:
        raise ValueError(f"post.aberration does not read {', '.join(unread)} (it reads amount, mode, angle)")
    amount, mode, angle = ab.get("amount", 0.03), ab.get("mode", "radial"), ab.get("angle", 0)

    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v

    if not (num(amount) and 0.004 <= amount <= 0.1):
        raise ValueError("post.aberration.amount is 0.004 to 0.1: how far red and blue part from green at the cell's edge, as a share of the cell")
    if mode not in ("radial", "axis"):
        raise ValueError('post.aberration.mode is "radial" (parted about the middle) or "axis" (slid apart along angle)')
    if not (num(angle) and -360 <= angle <= 360):
        raise ValueError("post.aberration.angle is degrees, -360 to 360")
    if "angle" in ab and mode != "axis":
        raise ValueError('post.aberration.angle is read with "mode": "axis" only')
    if wrap or beam:
        raise ValueError("post.aberration is not for a strip that wraps or a beam's texture (it repeats along the beam: its colours would part at every join)")
    if amount * size < 1:
        raise ValueError(f"post.aberration.amount {amount} parts the colours by {amount * size:.2f} px on a cell of {size:g} px (as the sheet is saved): "
                         f"under a pixel shows nothing - {math.ceil(1000 / size) / 1000:.3f} or more, or a larger cell")
    return ab


def apply_aberration(f, ab):
    """one finished frame (straight RGBA) with its red and blue pulled apart -> the frame. What moves is each colour's
    LIGHT as it is seen (colour x alpha); where a moved colour reaches past the shape the picture is as opaque as
    that light is bright and no more - a shape with little red in it (ice blue, cyan) gets a faint red fringe, never
    a dark ring. A picture that fills its cell keeps its colours at the cell's edge (the edge is drawn on outward)"""
    h, w = f.shape[:2]
    a = f[..., 3]
    seen = np.clip(f[..., :3], 0, 1) * a[..., None]
    amount, mode = float(ab.get("amount", 0.03)), ab.get("mode", "radial")

    def moved(plane, sign):
        if mode == "axis":
            ang = math.radians(float(ab.get("angle", 0)))
            far = amount * min(w, h) * sign  # (ONE length whichever way it slides: a share of the cell's short side)
            return ndimage.shift(plane, (-math.sin(ang) * far, math.cos(ang) * far), order=1, mode="nearest")  # (counter-clockwise, y up)
        # radial: the plane drawn larger (red) or smaller (blue) about the cell's middle; at the edge it has moved by
        # `amount` of the half cell... of the cell: scale so the rim moves by amount x the cell's size
        scale = 1 + sign * 2 * amount
        cy, cx = (h - 1) / 2, (w - 1) / 2
        return ndimage.affine_transform(plane, [1 / scale, 1 / scale], offset=[cy - cy / scale, cx - cx / scale], order=1, mode="nearest")

    red = moved(seen[..., 0], 1)
    blue = moved(seen[..., 2], -1)
    a2 = np.clip(np.maximum(a, np.maximum(red, blue)), 0, 1)
    out = np.dstack([red, seen[..., 1], blue]) / np.maximum(a2, 1e-6)[..., None]
    return np.dstack([np.clip(np.where(a2[..., None] > 1e-6, out, 0), 0, 1), a2])


def fringe_cut(before, after):
    """how much of a parted colour reaches the CELL'S EDGE where the picture had nothing (0..1, the most on the
    outermost ring of pixels): a fringe that arrives there is cut by the cell - in the game a hard straight end
    to a soft colour. A picture that fills its cell has its own light there already: nothing is cut"""
    gain = np.clip(after[..., 3] - before[..., 3], 0, 1)
    return float(max(gain[0].max(), gain[-1].max(), gain[:, 0].max(), gain[:, -1].max()))


FRINGE_CUT = 0.25       # a fringe this strong at the cell's edge is seen to end there
INBETWEEN_LEAST = 0.5   # px: under this much motion in every pair of frames there is nothing for a vector to follow
INBETWEEN_FOLLOW = 0.5  # the share of ALL the change between frames that moving them along their vectors must account for
INBETWEEN_PART = 0.4    # the same, for any sixteenth of the cell that holds a fiftieth of the change or more


def inbetween_block(ib):
    """a spec's post.inbetween as the packer reads it -> None (off) or {loop}; raises ValueError in words"""
    if ib is None or ib is False:
        return None
    if ib is True:
        return {"loop": False}
    if not isinstance(ib, dict):
        raise ValueError('post.inbetween is true, or a block: {"loop": true} for a sheet that plays round')
    for key in ib:
        if key != "loop":
            raise ValueError(f"post.inbetween does not read {key} (it reads loop: the grid says how many cells there are)")
    loop = ib.get("loop", False)
    if not isinstance(loop, bool):
        raise ValueError("post.inbetween.loop is true or false")
    return {"loop": loop}


def moments(n, count, loop):
    """the place on the frames' timeline of each of `count` cells: [(frame before, how far on to the next 0..1)].
    The first cell is frame 0; without loop the last cell is the last frame; with loop the cell after the last
    would be frame 0 again"""
    out = []
    for k in range(count):
        at = k * n / count if loop else k * (n - 1) / (count - 1)
        i = min(int(math.floor(at + 1e-9)), n - 1)
        t = at - i
        out.append((i, 0.0 if t < 1e-9 else t))
    return out


def _premult(f):
    return np.dstack([f[..., :3] * f[..., 3:], f[..., 3:]]).astype(np.float32)


def _grey(p):
    """what the vectors are measured on: the picture's light and its cover, 8 bits"""
    return np.clip((0.5 * p[..., :3].max(axis=2) + 0.5 * p[..., 3]) * 255 + 0.5, 0, 255).astype(np.uint8)


def motion(a, b):
    """the motion vectors from frame a to frame b (premultiplied, float32): (h, w, 2) px - where the picture at each
    pixel of a is in b (OpenCV's dense optical flow, Farneback)"""
    import cv2

    size = min(a.shape[0], a.shape[1])
    win = max(9, (size // 12) | 1)
    return cv2.calcOpticalFlowFarneback(_grey(a), _grey(b), None, 0.5, 5, win, 4, 7, 1.5, 0)


def moved(p, flow, t):
    """frame p carried `t` of the way along its vectors"""
    import cv2

    h, w = p.shape[:2]
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(p, xx - t * flow[..., 0], yy - t * flow[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def inbetween(frames, ib, count):
    """the finished frames (straight RGBA, float) -> `count` cells along their timeline: a cell ON a frame is that
    frame, a cell between two is drawn by moving both part of the way along the motion between them. Raises
    ValueError (in words) when there is no motion to follow or the vectors do not follow it"""
    pm = [_premult(c) for c in frames]
    n = len(pm)
    flows, most = {}, 0.0
    total_change = total_left = 0.0
    tiles_change, tiles_left = np.zeros((4, 4)), np.zeros((4, 4))
    h, w = pm[0].shape[:2]

    def pair(i):
        nonlocal most, total_change, total_left
        if i not in flows:
            a, b = pm[i], pm[(i + 1) % n]
            fwd, back = motion(a, b), motion(b, a)
            flows[i] = (fwd, back)
            lit = np.maximum(a[..., 3], b[..., 3]) > 0.05
            if lit.any():
                most = max(most, float(np.percentile(np.hypot(fwd[..., 0], fwd[..., 1])[lit], 95)))
            change, left = np.abs(a - b).sum(-1), np.abs(moved(a, fwd, 1.0) - b).sum(-1)
            total_change += float(change.sum())
            total_left += float(left.sum())
            for r in range(4):
                for c in range(4):
                    part = (slice(r * h // 4, (r + 1) * h // 4), slice(c * w // 4, (c + 1) * w // 4))
                    tiles_change[r, c] += float(change[part].sum())
                    tiles_left[r, c] += float(left[part].sum())
        return flows[i]

    out = []
    for i, t in moments(n, count, ib["loop"]):
        if t == 0.0:
            out.append(frames[i])
            continue
        fwd, back = pair(i)
        mix = (1 - t) * moved(pm[i], fwd, t) + t * moved(pm[(i + 1) % n], back, 1 - t)
        alpha = np.clip(mix[..., 3:], 0, 1)
        out.append(np.dstack([np.where(alpha > 1e-4, mix[..., :3] / np.maximum(alpha, 1e-4), 0.0), alpha]).astype(np.float64).clip(0, 1))
    if most < INBETWEEN_LEAST:
        raise ValueError(f"post.inbetween found no motion between any two frames (the most is {most:.2f} px): the picture stands still - "
                         "the cells between would be copies; drop inbetween")
    follow = 1 - total_left / total_change if total_change > 0 else 1.0
    if follow < INBETWEEN_FOLLOW:
        raise ValueError(f"post.inbetween: over the whole sheet the motion vectors account for {max(follow, 0):.2f} of the change between frames "
                         f"(needs {INBETWEEN_FOLLOW}): the picture changes instead of moving (it fades, grows fast, changes colour, or two things cross), "
                         "or its frames are too far apart to follow - render more frames, or drop inbetween")
    for r in range(4):
        for c in range(4):
            if tiles_change[r, c] >= 0.02 * total_change and 1 - tiles_left[r, c] / tiles_change[r, c] < INBETWEEN_PART:
                raise ValueError(f"post.inbetween: a part of the picture is not followed (row {r + 1}, column {c + 1} of a 4 x 4 split of the cell: the vectors "
                                 f"account for {max(1 - tiles_left[r, c] / tiles_change[r, c], 0):.2f} of its change, needs {INBETWEEN_PART}) - something small "
                                 "there jumps further than it is wide and would be drawn twice; render more frames, or drop inbetween")
    return out


def edges_block(ed):
    """a spec's post.edges as the packer reads it -> None (off) or the block; raises ValueError saying what is wrong"""
    if ed is None or ed is False:
        return None
    if not isinstance(ed, dict):
        raise ValueError('post.edges is a block: {"threshold": 0.08, "grow": 0, "color": [r, g, b], "keep": true}')

    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v

    unread = sorted(set(ed) - {"threshold", "grow", "color", "keep"})
    col = ed.get("color", [0, 0, 0])
    if unread:
        raise ValueError(f"post.edges does not read {', '.join(unread)} (it reads threshold, grow, color, keep)")
    if not (num(ed.get("threshold", 0.08)) and 0.01 <= ed.get("threshold", 0.08) <= 0.3):
        raise ValueError("post.edges.threshold is 0.01 to 0.3 (a full step measures about 0.32: above 0.3 nothing is a line)")
    if not (isinstance(ed.get("grow", 0), int) and not isinstance(ed.get("grow", 0), bool) and 0 <= ed.get("grow", 0) <= 8):
        raise ValueError("post.edges.grow is a whole number of pixels, 0 to 8")
    if not (isinstance(col, list) and len(col) == 3 and all(num(c) and 0 <= c <= 1 for c in col)):
        raise ValueError("post.edges.color is [r, g, b], each 0 to 1")
    if not isinstance(ed.get("keep", True), bool):
        raise ValueError("post.edges.keep is true (lines over the picture) or false (the lines alone)")
    return ed


def finish_frame(px, post, size):
    rgb, cov = px[..., :3], np.clip(px[..., 3], 0, 1)
    glow = post.get("glow", {})
    rgb = bloom(rgb, size, glow.get("bloom", 0.0), glow.get("radius", 0.04))
    st = post.get("streaks", {})
    rgb = streaks(rgb, size, int(st.get("count", 0)), st.get("length", 0.3), st.get("strength", 0.3), st.get("angle", 0.0))
    # post.tonemap false = the picture as painted (a drawn plate: paper white must stay 255, the tone curve would make it 161)
    tm = np.clip(rgb, 0, 1) if post.get("tonemap", True) is False else 1 - np.exp(-np.clip(rgb, 0, None) * post.get("exposure", 1.0))
    mode = post.get("alpha", "glow")
    if mode == "coverage":
        a = cov
        col = np.where(a[..., None] > 1e-3, tm / np.maximum(a[..., None], 1e-3), 0)
    else:
        lum = tm.max(axis=2)
        a = np.clip(np.maximum(cov * post.get("solid", 1.0), lum * post.get("glow_alpha", 1.0)), 0, 1)
        col = np.where(a[..., None] > 1e-3, tm / np.maximum(a[..., None], 1e-3), 0)
    col = np.clip(col, 0, 1)
    look = post.get("color", "color")
    if look in ("gray", "cel"):
        g = (col * np.array([0.3, 0.55, 0.15])).sum(axis=2)
        g = g / max(float(np.percentile(g[a > 0.05], 99.5)) if (a > 0.05).any() else 1.0, 1e-3)
        if look == "cel":
            n = int(post.get("bands", 3))
            soft = 0.08
            q = np.floor(np.clip(g, 0, 0.999) * n) / (n - 1)
            frac = (np.clip(g, 0, 0.999) * n) % 1
            g = np.clip(q + np.clip((frac - (1 - soft)) / soft, 0, 1) / (n - 1), 0, 1)
            fl = float(post.get("floor", 0))  # the darkest band's tone (drawn smoke's shadow is a colour, never black)
            g = fl + (1 - fl) * g
        col = np.repeat(np.clip(g, 0, 1)[..., None], 3, axis=2)
    elif look == "cel_color":  # (2026-11-10) anime bands that KEEP the baked hue: a fire crescent's white-hot edge stays white
        # and its body orange-red ("cel" turns everything grey for one preset tint, which loses a hot core)
        lum = (col * np.array([0.3, 0.55, 0.15])).sum(axis=2)
        ref = max(float(np.percentile(lum[a > 0.05], 99.5)) if (a > 0.05).any() else 1.0, 1e-3)
        g = np.clip(lum / ref, 0, 0.999)
        n = int(post.get("bands", 3))
        soft = 0.08
        q = np.floor(g * n) / (n - 1)
        frac = (g * n) % 1
        gq = np.clip(q + np.clip((frac - (1 - soft)) / soft, 0, 1) / (n - 1), 0, 1)
        col = np.clip(col * (gq / np.maximum(g, 1e-3))[..., None], 0, 1)
    cut = post.get("cut")
    if cut:  # a HARD silhouette (a drawn puff, not a soft volume - R4 2026-10-23, anime smoke): alpha thresholded at `cut`
        a = np.clip((a - (float(cut) - 0.03)) / 0.06, 0, 1)  # with a 1-2 px anti-aliased edge
    ol = post.get("outline")
    if ol:  # an ink line round every shape (the hand-inked look of a drawn puff / burst)
        m = a > float(ol.get("threshold", 0.45))
        ring = ndimage.binary_dilation(m, iterations=max(1, int(ol.get("width", 3)))) & ~m
        oc = np.array(ol.get("color", [0.04, 0.05, 0.09]), dtype=col.dtype)
        col = np.where(ring[..., None], oc, col)
        a = np.where(ring, 1.0, a)
    return np.dstack([col, a])



def fbm(h, w, scale, seed, octaves=5):
    """tileable-enough fractal value noise in 0..1 (numpy, deterministic per seed): the erosion pattern"""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = max(2, int(scale * (2 ** o)))
        grid = rng.random((cells + 1, cells + 1))
        z = ndimage.zoom(grid, (h / cells, w / cells), order=3)[:h, :w]
        out += z * amp
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / max(1e-6, out.max() - out.min())


def erode(f, k, er, size, seed):
    """the professional dissolve: the frame breaks apart through a noise pattern as the flipbook plays (k 0..1),
    a hot edge burning along the erosion front — instead of fading out evenly.
    er: {start 0.0, end 1.0 (threshold over the life), scale 5 (noise cells), soft 0.06, edge 0.05 (front width),
    edge_color [r, g, b] (the burning rim; omit = none), edge_gain 1.6, density 0.5 (how much the alpha itself
    biases the erosion: thin parts go first)}"""
    h, w = f.shape[:2]
    n = fbm(h, w, er.get("scale", 5), seed)
    a = f[..., 3]
    dens = er.get("density", 0.5)
    field = n * (1 - dens) + np.clip(a, 0, 1) * dens  # thin smoke erodes first, the dense core last
    # the threshold is relative to this frame's densest point: `end` 1.02 = the last frame just clears, the one before
    # still holds its core (consecutive frames always differ; a one-shot ends on its last frame)
    fmax = float(field[a > 0.02].max()) if (a > 0.02).any() else 1.0
    thr = fmax * (er.get("start", 0.0) + (er.get("end", 1.02) - er.get("start", 0.0)) * (k ** er.get("curve", 1.3)))
    soft = er.get("soft", 0.06)
    keep = np.clip((field - thr) / max(1e-4, soft), 0, 1)
    out = f.copy()
    out[..., 3] = a * keep
    if er.get("edge_color") is not None and thr > 0.001:
        ew = er.get("edge", 0.05)
        band = np.clip(1 - np.abs(field - thr - ew * 0.5) / max(1e-4, ew), 0, 1) * (a > 0.02)
        ec = np.array(er["edge_color"], dtype=np.float64)
        gain = er.get("edge_gain", 1.6)
        out[..., :3] = np.clip(out[..., :3] * (1 - band[..., None]) + ec[None, None, :] * band[..., None] * gain, 0, 1)
        out[..., 3] = np.maximum(out[..., 3], band * a * 0.9)
    return out

def edge_fade(img, border, wrap):
    """alpha forced to 0 at the cell edge (mip bleed / clipping); returns (img, worst alpha the fade had to remove)"""
    h, w = img.shape[:2]
    yy = np.minimum(np.arange(h), np.arange(h)[::-1])[:, None]
    xx = np.minimum(np.arange(w), np.arange(w)[::-1])[None, :]
    fy = np.clip(yy / max(border, 1), 0, 1)
    fx = np.ones_like(xx, dtype=np.float64) if wrap else np.clip(xx / max(border, 1), 0, 1)
    m = np.minimum(fy, fx) if not wrap else np.broadcast_to(fy * fy * (3 - 2 * fy), (h, w))  # a strip's sides: a smooth roll-off
    removed = float((img[..., 3] * (1 - m)).max())
    out = img.copy()
    out[..., 3] *= m
    return out, removed


def build(name, spec, frames_dir):
    frames = load_frames(os.path.join(frames_dir, name))
    if not frames:
        raise FileNotFoundError(f"no frames in {frames_dir}/{name} — run the Blender step (lune run kit vfx)")
    post = dict(spec.get("post", {}))
    if spec.get("plate"):  # a full-screen plate: the picture as painted, edge to edge, fitted to a 1024 width
        post.update({"border": 0, "tonemap": False})
    wrap = bool(spec.get("wrap", False))
    grid = spec.get("grid", 1)
    cols, rows = (grid, grid) if isinstance(grid, int) else (int(grid[0]), int(grid[1]))
    fh, fw = frames[0].shape[:2]
    # post.border 0 = no edge fade at all (a full-screen plate: a drawn impact frame shown edge to edge); default 3 %
    # a strip that wraps along its length still needs its SIDES faded (a beam's width): otherwise every beam draws
    # hard straight edges. wrap: the fade runs across the rows only (edge_fade), over `side` of the height (8 %)
    if wrap:
        border = max(2, int(fh * post.get("side", 0.2)))
    else:
        border = 0 if post.get("border", 0.03) <= 0 else max(2, int(min(fw, fh) * post.get("border", 0.03)))
    ib = inbetween_block(post.get("inbetween"))
    if ib is not None and (wrap or spec.get("plate") or len(frames) < 2):
        raise ValueError("post.inbetween is for a sheet of two or more cells: not a strip that wraps, a plate or a single picture")
    if ib is not None and len(frames) >= cols * rows:
        raise ValueError(f"post.inbetween fills a grid from FEWER frames: {len(frames)} frames on a {cols}x{rows} grid leave no cell to draw "
                         "(a larger grid, or fewer rendered frames)")
    if len(frames) > cols * rows:
        raise ValueError(f"{len(frames)} frames do not fit a {cols}x{rows} grid")
    sheet = np.zeros((fh * rows, fw * cols, 4), dtype=np.float64)
    clipped = 0.0
    finished = []
    ed = edges_block(post.get("edges"))
    most = 0  # the most line pixels any frame got
    inner = 0  # ... and the most of them INSIDE the shape
    saved = spec.get("size")  # (the sheet may be saved smaller than it is made: the fringe shrinks with it)
    saved_w = (saved[0] if isinstance(saved, list) else saved) if saved else (1024 if spec.get("plate") else fw * cols)
    ab = aberration_block(post.get("aberration"), min(fw, fh) * saved_w / (fw * cols), wrap, bool(spec.get("beam")))
    parted = 0  # the most pixels of fringe any frame got
    cut_fringe = 0.0  # ... and the most of it that reaches the cell's edge
    looks = []
    for i, px in enumerate(frames):
        f = finish_frame(px, post, max(fw, fh))
        if post.get("erode"):  # bake the dissolve into the flipbook (Roblox has no custom shaders: the erosion lives in the frames)
            f = erode(f, i / max(1, len(frames) - 1), post["erode"], max(fw, fh), int(spec.get("seed", 1)) * 7 + 3)
        looks.append(f)
    if ib is not None:  # MOTION VECTORS: the cells between the rendered ones (lines and fringes are drawn on them too)
        looks = inbetween(looks, ib, cols * rows)
    for i, f in enumerate(looks):
        plain = f
        if ed is not None:  # EDGE DETECTION, on the frame as it will be seen: after every look and after the dissolve
            # (with an ink ring round the shape already, the silhouette is not lined a second time)
            f, line = apply_edges(f, ed, wrap, silhouette=not post.get("outline"))
            most = max(most, int((line > 0.5).sum()))
            inner = max(inner, inner_lines(line, plain[..., 3]))
        if ab is not None:  # CHROMATIC ABERRATION: the last look of all (a drawn line parts into its colours too)
            before = f
            f = apply_aberration(f, ab)
            cut_fringe = max(cut_fringe, fringe_cut(before, f))
            parted = max(parted, int((np.abs(f[..., :3] * f[..., 3:] - before[..., :3] * before[..., 3:]).max(axis=2) > 0.5).sum()))  # (a pixel whose light changed by half or more: a fringe the eye finds)
        f, rem = edge_fade(f, border, wrap) if border > 0 else (f, 0.0)
        if (ed is not None or ab is not None) and border > 0:
            rem = edge_fade(plain, border, wrap)[1]  # (how much of the SHAPE the border cut, not of its line or fringe)
        if wrap and border > 0:
            rem = 0.0  # a beam's body meeting its side fade is expected, not a clipped shape
        clipped = max(clipped, rem)
        finished.append(f)
        r, c = divmod(i, cols)
        sheet[r * fh : (r + 1) * fh, c * fw : (c + 1) * fw] = f
    if ab is not None and parted < EDGE_LEAST:
        # the step was asked for and showed nothing: an empty or flat picture, a shape with no red or blue in it, or
        # (radial) a small shape at the cell's middle, where nothing parts
        raise ValueError(f"post.aberration parted next to nothing in any frame ({parted} px of fringe): the picture is flat or empty, has no red or blue "
                         "to part, or (radial) sits small at the cell's middle where nothing parts - a larger amount, \"mode\": \"axis\", or drop aberration")
    if ed is not None and most < EDGE_LEAST:
        # the step was asked for and drew nothing (nothing is written: the packer saves after this returns)
        raise ValueError(f"post.edges found no edge in any frame at threshold {ed.get('threshold', 0.08)}: the picture has no step that sharp "
                         "(a soft glow has none) - lower the threshold, give it bands (\"color\": \"cel\") or a \"cut\", or drop edges")
    out_size = spec.get("size")
    if spec.get("plate") and not out_size:
        out_size = [1024, max(16, int(round(1024 * sheet.shape[0] / sheet.shape[1] / 8)) * 8)]
    img = Image.fromarray((np.clip(sheet, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
    if out_size and img.size != tuple(out_size if isinstance(out_size, list) else (out_size, out_size)):
        img = img.resize(tuple(out_size if isinstance(out_size, list) else (out_size, out_size)), Image.LANCZOS)
    if spec.get("beam"):
        # Roblox Beams run an image's VERTICAL axis along the beam (Attachment0 -> 1) and its horizontal axis across
        # the width (measured in Studio 2026-10-10): a strip rendered lengthwise is turned upright here
        img = img.transpose(Image.ROTATE_90)
    change = 1.0
    if len(finished) > 1:
        diffs = [float(np.abs(finished[i + 1][..., 3] - finished[i][..., 3]).mean()) for i in range(len(finished) - 1)]
        change = min(diffs)
    if ab is not None:
        img.info["fringe_cut"] = round(cut_fringe, 3)  # (read by check(): a fringe cut by its cell is said)
    if ed is not None:
        img.info["edge_inner"] = inner  # (read by check(): a sheet lined on its silhouette alone is said)
    return img, (cols, rows), clipped, change, len(looks)


def check(img, grid, clipped, change, n, wrap, plate=False, want=1):
    checks = []

    def add(name, ok, value, limit, fix, severity="error"):
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "value": value, "limit": limit, "fix": "" if ok else fix})

    w, h = img.size
    pow2 = all(v > 0 and (v & (v - 1)) == 0 for v in (w, h))
    if plate:  # a full-screen plate is an ImageLabel picture, not a mipmapped sprite: any sides <= 1024
        add("pow2", max(w, h) <= 1024, [w, h], "plate: sides <= 1024", "fit the plate into 1024")
    else:
        add("pow2", pow2, [w, h], "power of two sides", "render cell x grid to 256/512/1024")
    add("max_size", max(w, h) <= 1024, [w, h], "<= 1024", "Roblox downscales above 1024")
    if not wrap:
        add("multiple", w % grid[0] == 0 and h % grid[1] == 0, [w, h, *grid], "size divisible by grid", "Roblox refuses a flipbook whose size is not a multiple of its layout")
    a = np.asarray(img)[..., 3].astype(np.float64) / 255
    add("not_empty", a.max() > 0.2, round(float(a.max()), 3), "> 0.2", "nothing visible — raise strength/density or exposure")
    add("not_clipped", clipped < 0.25, round(clipped, 3), "< 0.25", "the shape runs off its cell and was cut by the edge fade — shrink it (camera ortho / scale)", "warn")
    if img.info.get("fringe_cut") is not None:
        add("fringe_whole", img.info["fringe_cut"] < FRINGE_CUT, img.info["fringe_cut"], f"< {FRINGE_CUT} at the cell's edge",
            "post.aberration pushes a colour to the cell's edge, where it is cut off straight: a smaller shape in its cell, a smaller amount, "
            "or \"mode\": \"axis\" along the way the shape has room", "warn")
    if img.info.get("edge_inner") is not None:
        # (a warning: an outline is a look of its own - but it is not the method Edge detection, whose lines are inside)
        add("inner_lines", img.info["edge_inner"] >= EDGE_LEAST, img.info["edge_inner"], f">= {EDGE_LEAST} px inside the shape",
            "post.edges drew the shape's silhouette only: that is an outline (post.outline draws one), not edge detection - give the "
            "picture steps inside it (bands: \"color\": \"cel\"; five bands or more want a threshold near 0.05), or lower the threshold", "warn")
    if wrap:  # a beam strip's sides must reach (near) zero, or every beam draws hard straight edges
        a = np.asarray(img).astype(float) / 255.0
        lum = a[..., 3] * a[..., :3].max(axis=2)
        k = max(1, min(lum.shape) // 40)  # a beam texture is upright (its width along x); a plain wrap strip runs along x
        side = float(max(lum[:, :k].mean(), lum[:, -k:].mean())) if lum.shape[0] >= lum.shape[1] else float(max(lum[:k].mean(), lum[-k:].mean()))
        add("soft_sides", side < 0.02, round(side, 3), "< 0.02", "a beam strip whose sides are not dark draws hard straight edges: narrow its band or raise post.side", "error")
    # the frames the spec asks for must all be there (2026-10-24: an imported SHEET came back as ONE frame and was laid out
    # as a 16-cell flipbook with 15 empty cells - five textures played their whole sheet for one frame, then nothing)
    if want > 1:
        add("frames_count", n == want, [n, want], "the spec's frames", "the source gave a different number of frames than the spec's `frames`: a sheet must be ONE image with `grid` (sliced), or a directory of frames")
    if n > 1:
        add("frames_change", change > 0.0008, round(change, 5), "> 0.0008", "two frames in a row are identical — the animation is not moving")
    return checks


def review(items, path):
    """every finished texture over black and over mid grey, labelled"""
    tiles = []
    for name, img in items:
        im = img.copy()
        im.thumbnail((512, 512))
        w, h = im.size
        tile = Image.new("RGB", (w * 2 + 12, h + 22), (30, 30, 34))
        for j, bg in enumerate(((0, 0, 0), (96, 96, 100))):
            base = Image.new("RGBA", (w, h), (*bg, 255))
            tile.paste(Image.alpha_composite(base, im).convert("RGB"), (j * (w + 4) + 4, 18))
        ImageDraw.Draw(tile).text((6, 3), name, fill=(235, 235, 235))
        tiles.append(tile)
    if not tiles:
        return
    W = max(t.width for t in tiles)
    H = sum(t.height for t in tiles)
    sheet = Image.new("RGB", (W, H), (20, 20, 24))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height
    sheet.save(path)


def glow_block(post):
    """post.emissive: a GLOW MASK packed beside the sheet (the V3 doc, VFX stage C.2 / D.1: "an albedo atlas + its
    paired EmissiveMaskContent map"). A mesh shows a sheet through a SurfaceAppearance, and its EmissiveMask was the
    sheet itself: every lit pixel glowed alike, the dim smoke as much as the white-hot core. true, or
    {"floor": 0..1, "soft": 0..0.5}: a pixel glows where the light it gives
    rises past floor (its luminance times its alpha), softened over +-soft -> None when the spec asks for none"""
    g = post.get("emissive") if isinstance(post, dict) else None
    if g is None or g is False:
        return None
    if g is True:
        g = {}
    if not isinstance(g, dict):
        raise ValueError('post.emissive is true or {"floor": 0..1, "soft": 0..0.5}')
    floor, soft = g.get("floor", 0.6), g.get("soft", 0.12)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (floor, soft)):
        raise ValueError("post.emissive floor and soft are numbers")
    if not (0 < floor < 1) or not (0 <= soft <= 0.5):
        raise ValueError(f"post.emissive floor {floor} is in (0, 1) and soft {soft} in [0, 0.5]")
    return {"floor": float(floor), "soft": float(soft)}


def glow_mask(img, gb):
    """the finished sheet (as saved: resized, a beam turned upright) -> (the grey mask picture, the share of the sheet
    that glows past half)"""
    a = np.asarray(img.convert("RGBA")).astype(np.float64) / 255.0
    # its luminance, not its brightest channel: a saturated red tail has a full red channel and is not white-hot
    light = (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722) * a[..., 3]
    lo, hi = gb["floor"] - gb["soft"], gb["floor"] + gb["soft"]
    m = np.clip((light - lo) / max(hi - lo, 1e-6), 0.0, 1.0) if hi > lo else (light >= gb["floor"]).astype(np.float64)
    m = m * m * (3.0 - 2.0 * m)
    return Image.fromarray((m * 255.0 + 0.5).astype(np.uint8), "L").convert("RGB"), float((m > 0.5).mean())


def register(path, results, ids_path="assets/ids.json"):
    """every finished texture gets a VFX registry entry; an id kit upload already recorded (assets/ids.json) is
    copied in, so a texture uploaded before its entry existed still plays"""
    if not results or not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    uploaded = {}
    if os.path.isfile(ids_path):
        with open(ids_path, encoding="utf-8") as fh:
            uploaded = json.load(fh).get("textures", {})
    for r in results:
        g = r["grid"]
        grid = g[0] if g[0] == g[1] else g
        e = reg.get(r["name"]) if isinstance(reg.get(r["name"]), dict) else {"id": "", "fallback": "rbxasset://textures/particles/sparkles_main.dds"}
        e["grid"] = grid
        e["file"] = r["file"]
        if uploaded.get(r["name"]) and e.get("id") != uploaded[r["name"]]:
            e["id"] = uploaded[r["name"]]  # kit upload's record is the truth about what is live
        glow = r.get("emissive")
        if glow:
            # the mask is a texture of its own (its own upload, its own id); the sheet's entry names it
            g = reg.get(glow["name"]) if isinstance(reg.get(glow["name"]), dict) else {"id": "", "fallback": e.get("fallback", "")}
            g["grid"], g["file"], g["glow_of"] = grid, glow["file"], r["name"]
            if uploaded.get(glow["name"]) and g.get("id") != uploaded[glow["name"]]:
                g["id"] = uploaded[glow["name"]]
            reg[glow["name"]] = g
            e["emissive"] = glow["name"]
        else:
            e.pop("emissive", None)
        reg[r["name"]] = e
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=2, sort_keys=True)  # the format kit upload writes: two writers, one format (no whole-file churn)
        fh.write("\n")


def derived(spec):
    """is this sheet baked FROM another built texture (a dissolve; a comp that maps a source)? Its frames can only be
    made once that texture is packed, so the general pass leaves it to its own step"""
    if spec.get("recipe") == "dissolve":
        return True
    comp = spec.get("comp")
    return spec.get("recipe") == "comp" and isinstance(comp, dict) and comp.get("source") is not None


def main():
    argv = sys.argv[1:]
    opts = {"--specs": "assets/textures", "--frames": "build/fxlab", "--out": "build/textures", "--registry": "assets/effects/_textures.json"}
    names = []
    flags = set()
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i] in ("--skip-derived", "--no-review"):
            flags.add(argv[i])
            i += 1
        else:
            names.append(argv[i])
            i += 1
    specs = opts["--specs"]
    os.makedirs(opts["--out"], exist_ok=True)
    names = names or sorted(f[:-5] for f in os.listdir(specs) if f.endswith(".json"))
    results, errors, shown = [], [], []
    for nm in names:
        path = os.path.join(specs, f"{nm}.json")
        if not os.path.isfile(path):
            errors.append(f"{nm}: no spec {path}")
            continue
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        if spec.get("engine") != "fx":
            continue
        if "--skip-derived" in flags and derived(spec):
            continue  # baked FROM a packed texture: its own step bakes and packs it after this pass (kit vfx)
        try:
            img, grid, clipped, change, n = build(nm, spec, opts["--frames"])
        except (FileNotFoundError, ValueError) as e:
            errors.append(f"{nm}: {e}")
            continue
        out = os.path.join(opts["--out"], f"{nm}.png")
        try:
            gb = glow_block(spec.get("post"))
        except ValueError as e:
            errors.append(f"{nm}: {e}")
            continue
        img.save(out)
        glow = None
        if gb is not None:
            mask, share = glow_mask(img, gb)
            if share <= 0.0:
                errors.append(f"{nm}: post.emissive: nothing in the sheet gives light past {gb['floor']} - nothing would glow "
                              "(a lower floor, or drop emissive)")
                continue
            gout = os.path.join(opts["--out"], f"{nm}_glow.png")
            mask.save(gout)
            glow = {"name": f"{nm}_glow", "file": gout.replace("\\", "/"), "share": round(share, 4)}
        want = int(spec.get("frames", 1) or 1)
        if want > 1 and isinstance(spec.get("post"), dict) and inbetween_block(spec["post"].get("inbetween")) is not None:
            want = grid[0] * grid[1]  # (the grid, filled: the rendered frames and the cells between)
        cs = check(img, grid, clipped, change, n, bool(spec.get("wrap")), bool(spec.get("plate")), want)
        results.append({"name": nm, "file": out.replace("\\", "/"), "grid": list(grid), "frames": n, "checks": cs,
                        **({"emissive": glow} if glow else {})})
        shown.append((nm, img))
        for c in cs:
            if not c["ok"] and c["severity"] == "error":
                errors.append(f"{nm}: {c['name']}={c['value']} — {c['fix']}")
    if "--no-review" not in flags:  # (a step packing only its own few sheets must not draw over the run's review sheet)
        review(shown, os.path.join(opts["--out"], "_fx_review.png"))
    register(opts["--registry"], results)
    warns = [f"{r['name']}: {c['name']}={c['value']} — {c['fix']}" for r in results for c in r["checks"] if not c["ok"] and c["severity"] == "warn"]
    print(
        json.dumps(
            {
                "schema": 1,
                "status": "fail" if errors else "pass",
                "summary": "; ".join(errors) if errors else f"{len(results)} fx texture(s) finished" + (f"; warnings: {'; '.join(warns)}" if warns else ""),
                "next_action": errors[0] if errors else f"LOOK at {opts['--out']}/_fx_review.png (over black and grey); then upload: lune run kit upload --only build/textures/",
                "textures": results,
            }
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
