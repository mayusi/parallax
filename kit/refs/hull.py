"""hull.py — a MEASURED 3D reference from a turntable: a maker's 360-degree product photos (one fixed camera, the object
turned in equal steps, a few camera heights) carved into the object's VISUAL HULL — its shape from its own photos, at
its real size, with the camera found from the photos themselves.

    python kit/refs/hull.py <folder> --length-mm 202 --name <name> [--cols 24] [--rows 5] [--pattern "c{i:03d}_l0.jpg"]
        [--side-col 6] [--front left|right] [--voxel 0.6] [--out refs] [--views-out build/refs]
        [--ortho-px-per-mm 5] [--camera <an earlier run's measure.json>]

The photos are frame i = row * cols + col (GLOCK's own 360 player: c0..c119, 24 turns of 15 degrees x 5 camera
heights); --side-col is the column whose photo shows the object square from its side, --front which way the object's
FRONT (a muzzle, a nose) points in that photo (left: the photo shows its left side). Silhouettes come from the plain
background (or a cut-out's alpha).

THE CAMERA, from the photos: its distance, its focal length, each row's elevation, where the turntable's axis stands in
the picture and which way it turns — found by making every silhouette agree with the hull carved from all of them
(each view's COVERAGE: the share of its silhouette the hull's projection fills — near 1 when everything agrees; a
wrong camera carves the hull away and the coverage drops). The turn's zero is the side photo's widest angle (from the
neighbouring columns), so the object's length lies along x. The size comes last: the hull is scaled so its length is
--length-mm (a dossier's A-graded length); its height and widths are then MEASURED — the checks against the other
published sizes.

What a visual hull cannot see — it only ever errs WIDE, never narrow:
  - a hollow no photo looks into (an ejection port seen only edge-on) is filled;
  - a width no photo sees ALONE is an upper bound: the end-on photos see the whole length at once (a pistol's 25.5 mm
    slide behind its wider grip), so only oblique photos bound the slide — GLOCK's turntable gives ~27 mm for it. The
    side view and the overall length / height are exact to about a voxel; the top / front / rear views are OUTLINES
    and upper bounds, not widths to build from;
  - thin protrusions a millimetre or two tall (a lever's tip, a sight) need the camera found to under a millimetre:
    a coarse calibration (small pictures, voxels of a few mm) filled the gap between GLOCK's sights; the FINE stage
    (bigger pictures, ~0.5 % voxels) and the camera's roll (a tripod not quite level) fix that, and the hull is
    STRAIGHTENED (its long axis in the top view) so a skew of a degree or two cannot spread the length into width.
--voxel is in real millimetres; specks the carving leaves apart from the body are dropped (the biggest connected piece
is the object). The camera found is saved (the measure.json's "rig"): `--camera <that file>` re-carves finer without
calibrating again.

  -> <out>/<name>.measure.json   size_mm [width, height, length] like kit refs measure, the camera found, every view's
                                 coverage, the voxel size (kit dossier add --kind model --measure <it>)
  -> <out>/<name>_hull.obj       the hull's voxel surface in mm, RIGHT-handed like any 3D tool reads it: the front at
                                 +x, up +y, the object's right side at +z (the carving frame is left-handed — its z
                                 looks INTO the side photo — so the OBJ is written mirrored back)
  A run whose photos disagree (coverage under 95%) or whose hull touches its carving box (clipped: an object taller or
  wider than the box, or off the turntable's axis) is a FAILURE: its measure.json says "status": "fail" and why
  ("problems"), and kit dossier add refuses it
  -> <views-out>/<name>_{side,top,front,rear}_ortho.png   ORTHOGRAPHIC silhouettes (the square views no camera takes)
                                 at --ortho-px-per-mm on white: side and top with the front to the right, top with the
                                 left side up, front seen from the front (its left side on the right), rear from behind
One JSON verdict line last.
"""

import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=True))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


# ------------------------------------------------------------------------------------------------- silhouettes
def silhouette(img, thresh=30):
    """the object's mask: a cut-out's alpha, else every pixel that differs from the plain background (the border's
    median colour) by more than thresh in a channel; specks dropped (the object is the biggest piece). Holes stay
    holes: the light through a trigger guard is shape."""
    from scipy import ndimage  # noqa: PLC0415

    if img.mode in ("RGBA", "LA"):
        a = np.asarray(img.convert("RGBA"))[..., 3]
        if (a < 16).mean() > 0.2:
            return a > 16
    rgb = np.asarray(img.convert("RGB"), dtype=np.int16)
    k = max(2, min(rgb.shape[:2]) // 200)
    border = np.concatenate([rgb[:k].reshape(-1, 3), rgb[-k:].reshape(-1, 3), rgb[:, :k].reshape(-1, 3),
                             rgb[:, -k:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    m = np.abs(rgb - bg).max(2) > thresh
    lab, n = ndimage.label(m)
    if n > 1:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = lab == (1 + int(np.argmax(sizes)))
    return m


def load_masks(folder, pattern, cols, rows, scale=1.0, every=1):
    """each photo's silhouette (scaled for the calibration; every Nth column) -> {(row, col): mask}"""
    out = {}
    for r in range(rows):
        for c in range(0, cols, every):
            p = os.path.join(folder, pattern.format(i=r * cols + c, row=r, col=c))
            if not os.path.isfile(p):
                continue
            im = Image.open(p)
            im.load()
            if scale != 1.0:
                im = im.resize((max(8, int(round(im.width * scale))), max(8, int(round(im.height * scale)))),
                               Image.BILINEAR)
            out[(r, c)] = silhouette(im)
    return out


# ---------------------------------------------------------------------------------------------- the camera model
class Rig:
    """one fixed camera aimed at the turntable's axis from distance D (mm), each row at its own elevation; the object
    turned by `turn` degrees per column (signed), zero at the side photo (+ a0); k = pixels per mm at the axis (the
    focal length is k * D); (du, dv[row]) = where the aimed point sits from the picture's centre; roll = the camera's
    tilt about its own axis (a tripod not quite level), degrees"""

    def __init__(self, w, h, cols, rows, side_col, k, D=1500.0, elev=None, du=0.0, dv=None, turn=None, a0=0.0,
                 roll=0.0):
        self.w, self.h, self.cols, self.rows, self.side_col = w, h, cols, rows, side_col
        self.k, self.D, self.du, self.a0, self.roll = float(k), float(D), float(du), float(a0), float(roll)
        self.elev = [float(e) for e in elev] if elev is not None else [0.0] * rows
        self.dv = [float(v) for v in dv] if dv is not None else [0.0] * rows
        self.turn = float(turn) if turn is not None else 360.0 / cols

    def vector(self):
        return np.array([math.log(self.k), math.log(self.D), self.du, *self.elev, *self.dv, self.roll])

    def from_vector(self, x):
        self.k, self.D, self.du = math.exp(x[0]), math.exp(min(x[1], 12.0)), float(x[2])
        self.elev = [float(v) for v in x[3:3 + self.rows]]
        self.dv = [float(v) for v in x[3 + self.rows:3 + 2 * self.rows]]
        if len(x) > 3 + 2 * self.rows:
            self.roll = float(x[3 + 2 * self.rows])
        return self

    def copy(self):
        return Rig(self.w, self.h, self.cols, self.rows, self.side_col, self.k, self.D, self.elev, self.du, self.dv,
                   self.turn, self.a0, self.roll)

    def scaled(self, s):
        """the same camera for pictures scaled by s"""
        return Rig(self.w * s, self.h * s, self.cols, self.rows, self.side_col, self.k * s, self.D, self.elev,
                   self.du * s, [v * s for v in self.dv], self.turn, self.a0, self.roll)

    def project(self, P, row, col):
        """object points P (N, 3: x along the length, y up, z across) -> pixel (u, v) in the photo (row, col)"""
        th = math.radians((col - self.side_col) * self.turn + self.a0)
        c, s = math.cos(th), math.sin(th)
        X = c * P[:, 0] + s * P[:, 2]
        Y = P[:, 1]
        Z = -s * P[:, 0] + c * P[:, 2]
        e = math.radians(self.elev[row])
        ce, se = math.cos(e), math.sin(e)
        zc = np.maximum(self.D - se * Y + ce * Z, 1e-3)
        f = self.k * self.D
        x_, y_ = f * X / zc, -f * (ce * Y + se * Z) / zc
        if self.roll:
            cr, sr = math.cos(math.radians(self.roll)), math.sin(math.radians(self.roll))
            x_, y_ = cr * x_ - sr * y_, sr * x_ + cr * y_
        return self.w / 2 + self.du + x_, self.h / 2 + self.dv[row] + y_


# -------------------------------------------------------------------------------------------------------- carving
def grid(lo, hi, step):
    axes = [np.arange(lo[i] + step / 2, hi[i], step, dtype=np.float32) for i in range(3)]
    g = np.stack(np.meshgrid(*axes, indexing="ij"), -1)
    return g.reshape(-1, 3), tuple(len(a) for a in axes), axes


def carve(rig, masks, P, chunk=500000):
    """the points every silhouette contains -> bool (N,). A point a photo's FRAME cuts off is unknown there, not
    empty (a tall object can leave the picture at the top camera): it must lie inside the silhouette of every photo
    that sees it, and be seen by at least a quarter of them (else nothing vouches for it)."""
    keep = np.ones(len(P), dtype=bool)
    seen = np.zeros(len(P), dtype=np.int32)
    for (row, col), m in masks.items():
        idx = np.nonzero(keep)[0]
        if not len(idx):
            break
        for a in range(0, len(idx), chunk):
            sel = idx[a:a + chunk]
            u, v = rig.project(P[sel], row, col)
            ui, vi = np.round(u).astype(np.int64), np.round(v).astype(np.int64)
            inside = (ui >= 0) & (ui < m.shape[1]) & (vi >= 0) & (vi < m.shape[0])
            ok = np.ones(len(sel), dtype=bool)
            ok[inside] = m[vi[inside], ui[inside]]
            keep[sel] = ok
            seen[sel] += inside
    return keep & (seen >= max(1, len(masks) // 4))


def coverage(rig, masks, P, keep, step):
    """each view's share of its silhouette that the hull's projection fills -> {(row, col): 0..1}"""
    from scipy import ndimage  # noqa: PLC0415

    out = {}
    pts = P[keep]
    r = max(1, int(math.ceil(rig.k * step * 0.6)))
    for (row, col), m in masks.items():
        if not len(pts):
            out[(row, col)] = 0.0
            continue
        u, v = rig.project(pts, row, col)
        ui, vi = np.round(u).astype(np.int64), np.round(v).astype(np.int64)
        ok = (ui >= 0) & (ui < m.shape[1]) & (vi >= 0) & (vi < m.shape[0])
        img = np.zeros(m.shape, dtype=np.uint8)
        img[vi[ok], ui[ok]] = 1
        img = ndimage.maximum_filter(img, size=2 * r + 1).astype(bool)
        out[(row, col)] = float((img & m).sum() / max(1, m.sum()))
    return out


# --------------------------------------------------------------------------------------------------- calibration
def mean_coverage(rig, masks, P, step):
    keep = carve(rig, masks, P)
    if keep.sum() < 20:
        return 0.0
    return float(np.mean(list(coverage(rig, masks, P, keep, step).values())))


def calibrate(rig, masks, box, step, stages=None, maxfev=200, log=None):
    """the camera that makes every silhouette agree -> (rig, mean coverage): Powell's method over the mean coverage,
    stage by stage (scale + aim, the elevations, the distance)"""
    from scipy.optimize import minimize  # noqa: PLC0415

    P, _, _ = grid(box[0], box[1], step)
    n = rig.rows
    stages = stages or [[0, 2, 3 + 2 * n] + list(range(3 + n, 3 + 2 * n)), list(range(3, 3 + n)), [1, 0]]
    cov = mean_coverage(rig, masks, P, step)
    for idx in stages:
        def loss(x, idx=idx):
            r = rig.copy()
            full = r.vector()
            full[idx] = x
            return 1.0 - mean_coverage(r.from_vector(full), masks, P, step)

        res = minimize(loss, rig.vector()[idx], method="Powell",
                       options={"xtol": 1e-3, "ftol": 1e-4, "maxfev": maxfev})
        if 1.0 - res.fun >= cov:
            full = rig.vector()
            full[idx] = res.x
            rig.from_vector(full)
            cov = 1.0 - float(res.fun)
        if log:
            log(f"  stage {idx[:2]}: coverage {cov:.4f}")
    return rig, cov


def side_offset(masks, side_col, cols, turn):
    """the turn's zero: the angle where the side photo's silhouette is widest (a parabola through the side column and
    its neighbours) -> degrees to add"""
    w = []
    for c in (side_col - 1, side_col, side_col + 1):
        m = masks.get((0, c % cols))
        if m is None:
            return 0.0
        xs = np.nonzero(m.any(0))[0]
        w.append(float(xs.max() - xs.min() + 1) if len(xs) else 0.0)
    den = w[0] - 2 * w[1] + w[2]
    if den >= 0:
        return 0.0
    off = 0.5 * (w[0] - w[2]) / den  # (in columns, -0.5..0.5 when the side column is the widest)
    return float(np.clip(off, -0.5, 0.5) * turn)


# ------------------------------------------------------------------------------------------------------- outputs
def write_obj(path, occ, step):
    """the filled voxels' surface (every face between a filled and an empty voxel) as an OBJ in mm, corners shared"""
    nx, ny, nz = occ.shape
    pad = np.zeros((nx + 2, ny + 2, nz + 2), dtype=np.int8)
    pad[1:-1, 1:-1, 1:-1] = occ
    quads = []
    # a face across `axis` at corner plane t (unpadded corner units), spanning the other two axes' voxel (a, b)
    offs = {0: ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), 1: ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)),
            2: ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))}
    for axis in range(3):
        d = np.diff(pad, axis=axis)
        for sign in (1, -1):
            idx = np.argwhere(d == sign)
            if not len(idx):
                continue
            base = idx.copy()
            others = [a for a in range(3) if a != axis]
            for a in others:
                base[:, a] -= 1          # (padded voxel index -> unpadded corner)
            # base[:, axis] = t: the corner plane between voxels t-1 and t
            corners = np.stack([base + np.array(o) for o in offs[axis]], 1)
            if sign == 1:                # (filled on the + side: the face looks to -axis)
                corners = corners[:, ::-1]
            quads.append(corners)
    if not quads:
        raise ValueError("the hull is empty")
    q = np.concatenate(quads)
    uniq, inv = np.unique(q.reshape(-1, 3), axis=0, return_inverse=True)
    faces = inv.reshape(-1, 4) + 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# visual hull (kit refs hull), millimetres, right-handed: front +x, up +y, right side +z\n")
        np.savetxt(fh, uniq * step, fmt="v %.3f %.3f %.3f")
        np.savetxt(fh, faces, fmt="f %d %d %d %d")
    return len(uniq), len(faces)


def clipped(occ):
    """the axes (0 length, 1 height, 2 width) on which the filled voxels touch the carving box: there the object may
    go on past it — its size there is the box's, not the object's"""
    filled = np.nonzero(occ)
    return [i for i in range(3) if len(filled[i]) and (filled[i].min() == 0 or filled[i].max() == occ.shape[i] - 1)]


def ortho(occ, step, px_per_mm, view):
    """an orthographic silhouette -> a PIL picture (black on white): side (x right, y up), top (x right, the left
    side +z up), front (z right, y up: seen from the front), rear (z left, y up)"""
    if view == "side":
        img = occ.any(2).T[::-1]          # (y, x), y up
    elif view == "top":
        img = occ.any(1).T[::-1]          # (z, x), +z up
    elif view == "front":
        img = occ.any(0)[::-1]            # (y, z), y up, +z right
    else:
        img = occ.any(0)[::-1, ::-1]      # rear: +z left
    pic = Image.fromarray(np.where(img, 0, 255).astype(np.uint8))
    scale = px_per_mm * step
    pic = pic.resize((max(1, int(round(pic.width * scale))), max(1, int(round(pic.height * scale)))), Image.NEAREST)
    pad = int(round(4 * px_per_mm))
    canvas = Image.new("L", (pic.width + 2 * pad, pic.height + 2 * pad), 255)
    canvas.paste(pic, (pad, pad))
    return canvas.convert("RGB")


# ------------------------------------------------------------------------------------------------------------ run
def run(folder, length_mm, name, cols=24, rows=5, pattern="c{i:03d}_l0.jpg", side_col=6, front="left", voxel=0.6,
        out="refs", views_out=os.path.join("build", "refs"), ortho_px=5.0, calib_scale=0.35, calib_every=2,
        maxfev=200, log=print, camera=None, fine_scale=0.7):
    t0 = time.time()
    full = load_masks(folder, pattern, cols, rows)
    if len(full) < max(8, cols // 2):
        raise ValueError(f"only {len(full)} photo(s) in {folder} match {pattern}")
    h, w = next(iter(full.values())).shape
    side = full.get((0, side_col))
    if side is None:
        raise ValueError(f"no photo for row 0, column {side_col} (--side-col)")
    ys, xs = np.nonzero(side)
    k0 = (xs.max() - xs.min() + 1) / float(length_mm)  # (pixels per mm at the axis: the side photo's length)
    turn0 = 360.0 / cols
    elev0 = ([0.0, 8.0, 20.0, 35.0, 50.0] + [55.0] * rows)[:rows]
    # where the turntable's axis stands in each row: the object's silhouette centre circles it as it turns, so the
    # mean centre over a whole turn sits on it (at the object's own centre height: the hull's origin)
    du, dv = [], []
    for r in range(rows):
        cs = [np.argwhere(full[(r, c)]).mean(0) for c in range(cols) if (r, c) in full and full[(r, c)].any()]
        if cs:
            cy, cx = np.mean(cs, 0)
            du.append(cx - w / 2)
            dv.append(cy - h / 2)
        else:
            dv.append(dv[-1] if dv else 0.0)
    base = Rig(w, h, cols, rows, side_col, k0, D=1500.0, elev=elev0, du=float(np.mean(du)) if du else 0.0, dv=dv)
    R, Hh = length_mm * 0.62, length_mm * 0.55
    box = (np.array([-R, -Hh, -R]), np.array([R, Hh, R]))
    small = load_masks(folder, pattern, cols, rows, calib_scale, calib_every)
    step = length_mm / 40.0
    if camera:  # (a camera found before for these photos: kit refs hull ... --camera <its measure.json>)
        rig = Rig(w, h, cols, rows, side_col, camera["k"], camera["D"], camera["elev"], camera["du"], camera["dv"],
                  camera["turn"], camera["a0"], camera.get("roll", 0.0))
        cov = float(camera.get("calibration_coverage", 0.0))
        log("camera reused")
    best = None
    for sign in (() if camera else (1.0, -1.0)):
        r0 = base.scaled(calib_scale)
        r0.turn = sign * turn0
        r0.a0 = side_offset(small if calib_every == 1 else load_masks(folder, pattern, cols, 1, calib_scale), side_col,
                            cols, r0.turn)
        r1, cov = calibrate(r0, small, box, step, stages=[[0, 2] + list(range(3 + rows, 3 + 2 * rows))],
                            maxfev=maxfev, log=log)
        log(f"turn {r0.turn:+.1f} deg per column: coverage {cov:.4f}")
        if best is None or cov > best[1]:
            best = (r1, cov)
    if not camera:
        rig, cov = calibrate(best[0], small, box, step, maxfev=maxfev, log=log)
        rig, cov = calibrate(rig, small, box, step / 1.5, maxfev=maxfev, log=log)
        rig = rig.scaled(1.0 / calib_scale)
    # the hull's own box (coarse)
    P, _, _ = grid(box[0], box[1], step)
    keep = carve(rig.scaled(calib_scale), small, P)
    if not keep.any():
        raise ValueError("the calibrated hull is empty: the photos do not agree on one object")
    pts = P[keep]
    lo, hi = pts.min(0) - 2 * step, pts.max(0) + 2 * step
    if not camera and fine_scale:
        # FINE calibration: the coarse camera (small pictures, voxels of a few mm) is good to 2-3 mm — enough to fill
        # the gap between a pistol's sights or cut a lever's tip; bigger pictures and ~0.5 % voxels in the hull's own
        # box bring it under a millimetre (GLOCK's FS turntable: a flat slide top at sight height before this)
        fine = load_masks(folder, pattern, cols, rows, fine_scale, calib_every)
        fstep = float(np.ptp(pts[:, 0]) + step) / 110.0
        fbox = (lo, hi)
        r_f = rig.scaled(fine_scale)
        r_f, cov = calibrate(r_f, fine, fbox, fstep, maxfev=max(40, maxfev // 2), log=log)
        rig = r_f.scaled(1.0 / fine_scale)
    if not camera:
        # STRAIGHT: the turn's zero came from the side photo's widest angle (to a degree or so); the hull's own long
        # axis in the top view gives it exactly — a skew of 1.5 degrees spreads 202 mm across 5 mm of width
        hstep = float(np.ptp(pts[:, 0])) / 120.0
        big = (lo - (hi - lo) * 0.1, hi + (hi - lo) * 0.1)

        def skew(r):
            Pc, _, _ = grid(big[0], big[1], hstep)
            q = Pc[carve(r.scaled(calib_scale), small, Pc)]
            if len(q) < 50:
                return 0.0
            xz = q[:, [0, 2]] - q[:, [0, 2]].mean(0)
            cxx, czz = float((xz[:, 0] ** 2).mean()), float((xz[:, 1] ** 2).mean())
            cxz = float((xz[:, 0] * xz[:, 1]).mean())
            return 0.5 * math.degrees(math.atan2(2 * cxz, cxx - czz))

        phi = skew(rig)
        log(f"  straighten: the long axis is {phi:+.2f} deg off x")
        if abs(phi) >= 0.1:  # (turning the photos' zero turns the hull rigidly: try both ways, keep the straighter)
            best_a0, best_phi = rig.a0, abs(phi)
            for cand in (rig.a0 - phi, rig.a0 + phi):
                r2 = rig.copy()
                r2.a0 = cand
                p2 = abs(skew(r2))
                if p2 < best_phi:
                    best_a0, best_phi = cand, p2
            rig.a0 = best_a0
            log(f"  straightened: {best_phi:.2f} deg left")
        P, _, _ = grid(box[0], box[1], step)
        keep = carve(rig.scaled(calib_scale), small, P)
        pts = P[keep] if keep.any() else pts
        lo, hi = pts.min(0) - 2 * step, pts.max(0) + 2 * step
    # (the photos fix the shape, not the size: the camera's units are the hull's — the coarse hull's length tells how
    #  many of them make a millimetre, so --voxel is real millimetres)
    s_coarse = float(length_mm) / float(np.ptp(pts[:, 0]) + step)
    voxel = voxel / s_coarse
    P, shape, axes = grid(lo, hi, voxel)
    keep = carve(rig, full, P)
    occ = keep.reshape(shape)
    # (specks the carving leaves apart from the body — a few voxels no photo happened to cut — would stretch every
    #  extent: the object is the biggest connected piece)
    from scipy import ndimage  # noqa: PLC0415

    lab, n = ndimage.label(occ)
    specks = 0
    if n > 1:
        sizes = ndimage.sum(occ, lab, range(1, n + 1))
        body = 1 + int(np.argmax(sizes))
        specks = int(occ.sum() - sizes[body - 1])
        occ = lab == body
        keep = occ.reshape(-1)
    cov_full = coverage(rig, full, P, keep, voxel)
    touching = clipped(occ)
    filled = np.nonzero(occ)
    if not len(filled[0]):
        raise ValueError("the fine hull is empty")
    ext = [float(axes[i][filled[i]].max() - axes[i][filled[i]].min() + voxel) for i in range(3)]
    s = float(length_mm) / ext[0]  # (the size: the hull's length IS the published length)
    sl = tuple(slice(filled[i].min(), filled[i].max() + 1) for i in range(3))
    occ = occ[sl]
    if front == "left":  # (the side photo shows the left side, the front pointing left: turn it 180 degrees about y)
        occ = occ[::-1, :, ::-1]
    size = [ext[2] * s, ext[1] * s, ext[0] * s]  # [width, height, length]
    os.makedirs(out, exist_ok=True)
    os.makedirs(views_out, exist_ok=True)
    obj = os.path.join(out, f"{name}_hull.obj")
    nv, nf = write_obj(obj, occ[:, :, ::-1], voxel * s)  # (right-handed: the right side at +z)
    views = {}
    for view in ("side", "top", "front", "rear"):
        p = os.path.join(views_out, f"{name}_{view}_ortho.png")
        ortho(occ, voxel * s, ortho_px, view).save(p)
        views[view] = p.replace("\\", "/")
    covs = sorted(cov_full.values())
    problems = []
    if float(np.mean(covs)) < 0.95:
        problems.append(f"the photos disagree with the hull (coverage {float(np.mean(covs)):.1%} < 95%): the camera "
                        "was not found — check --side-col / --front / --pattern, or the silhouettes")
    if touching:
        problems.append("the hull touches its carving box along its " + ", ".join(("length", "height", "width")[i]
                                                                               for i in touching)
                        + ": clipped — the object goes on past the box (taller or wider than it, or off the axis)")
    rec = {"name": name, "status": "fail" if problems else "pass", "problems": problems, "source": os.path.abspath(folder).replace("\\", "/"), "method": "visual hull (kit refs hull)",
           "size_mm": [round(v, 2) for v in size], "scaled_by": round(s, 6), "voxel_mm": round(voxel * s, 3),
           "ortho_px_per_mm": ortho_px, "obj": obj.replace("\\", "/"), "obj_verts": nv, "obj_faces": nf,
           "camera": {"px_per_mm_at_axis": round(rig.k, 4), "distance_mm": round(rig.D * s, 1),
                      "elevation_deg": [round(e, 2) for e in rig.elev], "turn_deg": rig.turn,
                      "turn_offset_deg": round(rig.a0, 3), "roll_deg": round(rig.roll, 3), "aim_px": [round(rig.du, 2)] + [round(v, 2) for v in rig.dv],
                      "calibration_coverage": round(cov, 4)},
           "rig": {"k": rig.k, "D": rig.D, "elev": rig.elev, "du": rig.du, "dv": rig.dv, "turn": rig.turn,
                   "a0": rig.a0, "roll": rig.roll, "w": w, "h": h, "cols": cols, "rows": rows, "side_col": side_col,
                   "calibration_coverage": round(cov, 4)},
           "coverage": {"mean": round(float(np.mean(covs)), 4), "worst": round(covs[0], 4),
                        "views": {f"r{r}c{c}": round(v, 4) for (r, c), v in sorted(cov_full.items())}},
           "views": views, "photos": len(full), "specks_dropped": specks, "seconds": round(time.time() - t0, 1)}
    path = os.path.join(out, f"{name}.measure.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    rec["path"] = path.replace("\\", "/")
    return rec


def main(argv):
    if not argv or argv[0].startswith("-"):
        return emit("fail", "refs hull: needs the folder of turntable photos", "lune run kit refs hull <folder> "
                    "--length-mm <the A-graded length> --name <name> [--cols 24 --rows 5 --side-col 6]")
    try:
        L = float(_arg(argv, "--length-mm", "0"))
        if not L > 0:
            return emit("fail", "refs hull: needs --length-mm (the object's published length: the hull's scale)",
                        "lune run kit dossier \"<object>\" (its graded overall length)")
        rec = run(argv[0], L, _arg(argv, "--name", "hull"), int(_arg(argv, "--cols", "24")),
                  int(_arg(argv, "--rows", "5")), _arg(argv, "--pattern", "c{i:03d}_l0.jpg"),
                  int(_arg(argv, "--side-col", "6")), _arg(argv, "--front", "left"), float(_arg(argv, "--voxel", "0.6")),
                  _arg(argv, "--out", "refs"), _arg(argv, "--views-out", os.path.join("build", "refs")),
                  float(_arg(argv, "--ortho-px-per-mm", "5")), log=lambda s: print(s, file=sys.stderr),
                  camera=(json.load(open(_arg(argv, "--camera"), encoding="utf-8")).get("rig")
                          if _arg(argv, "--camera") else None))
    except (ValueError, OSError) as e:
        return emit("fail", f"refs hull: {e}", "check the folder, --pattern and --side-col")
    w, h, l_ = rec["size_mm"]
    cov = rec["coverage"]
    ok = rec["status"] == "pass"
    return emit("pass" if ok else "fail",
                f"refs hull {rec['name']}: {l_:g} x {w:.1f} x {h:.1f} mm (length x width x height) from {rec['photos']} "
                f"photos; the views agree {cov['mean']:.1%} (worst {cov['worst']:.1%}); the camera "
                f"{rec['camera']['distance_mm']:g} mm away, elevations {rec['camera']['elevation_deg']} -> {rec['path']}",
                "compare its height and widths with the published ones, LOOK at the ortho views, then: kit dossier add "
                f"\"<object>\" --kind model --measure {rec['path']} --page <the turntable's page> --scope measure-only"
                if ok else "; ".join(rec["problems"]), **{k: v for k, v in rec.items() if k != "status"})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
