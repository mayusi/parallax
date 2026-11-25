"""spin.py — UI MESH VISUALS: a flat UI piece becomes a real bevelled 3D mesh (gold, chrome, silver or enamel, the
artwork on its front face) rendered as a turntable — a spinning coin, emblem or medallion as a flipbook + a sprite
sheet for the 2D UI, and the mesh itself (FBX) for a ViewportFrame.

    python kit/ui/spin.py <identity>/<piece> [--material gold|chrome|silver|enamel] [--frames 24] [--res 384]
        [--depth 0.12] [--bevel 0.03] [--motion spin|sway|flip|land] [--back <id>/<piece>] [--no-face] [--samples 24] [--exposure 0] [--gloss 0.5] [--relief N] [--depth-relief H] [--art assets/ui/art]

`--frames 0` makes the mesh only (the FBX + sidecar, no flipbook): any flat picture -> a bevelled, textured mesh for
a ViewportFrame, a VFX card or a 3D prop (other pipelines call it; they never need its frames).

The silhouette: the piece's opaque pixels vectorised by vtracer (polygon mode, the kit's vetted vectoriser), parsed
here (M / L / Z + translate) and handed to Blender (kit/ui/spin_blender.py): extruded, bevelled, the front face mapped
with the piece's own pixels. Writes, beside the piece:
  <piece>_spin_f000.png ...     the flipbook, flat beside the piece (the reel's `art` prop plays it; in game: an ImageLabel's frames)
  <piece>_spin_sheet.png        every frame in a grid (cols x rows in the sidecar: ImageRectOffset in game)
  <piece>_spin.fbx              the mesh (a ViewportFrame: Ui.model)
  <piece>_spin.spin.json        the recipe, the sheet layout, the source
"""
import argparse
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def silhouette_polys(img, speckle=6, alpha=128):
    """the opaque pixels (alpha above `alpha`) as polygons (image pixels), via vtracer in polygon mode"""
    import vtracer  # noqa: PLC0415
    a = np.array(img.getchannel("A"))
    mask = Image.fromarray(np.where(a > alpha, 0, 255).astype(np.uint8), "L")
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    svg = vtracer.convert_raw_image_to_svg(buf.getvalue(), img_format="png", colormode="binary", hierarchical="stacked",
                                           mode="polygon", filter_speckle=speckle, corner_threshold=60, length_threshold=4.0,
                                           max_iterations=10, splice_threshold=45, path_precision=2)
    polys = []
    for m in re.finditer(r"<path\b([^>]*)>", svg):
        attrs = m.group(1)
        d = re.search(r'\bd="([^"]*)"', attrs)
        if not d:
            continue
        fill = re.search(r'fill="([^"]*)"', attrs)
        if fill and fill.group(1).lower() not in ("#000", "#000000", "black"):
            continue  # (vtracer may write the paper as a white path)
        tx = ty = 0.0
        t = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", attrs)
        if t:
            tx, ty = float(t.group(1)), float(t.group(2))
        for sub in re.split(r"(?=M)", d.group(1)):
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", sub)]
            pts = [(nums[i] + tx, nums[i + 1] + ty) for i in range(0, len(nums) - 1, 2)]
            if len(pts) >= 3:
                polys.append(pts)
    return polys


def signed_area(poly):
    xs, ys = np.array([p[0] for p in poly]), np.array([p[1] for p in poly])
    return 0.5 * float(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1)))


def sliver(poly, size, min_area=0.0004, min_round=0.06):
    """a polygon too small or too thin to stand as a relief step (vtracer leaves hairline spikes on a brightness
    level's ragged edge; extruded, they stab out of the piece): tiny area, or 4*pi*A/P^2 (1 = a disc) near zero"""
    xs, ys = np.array([p[0] for p in poly]), np.array([p[1] for p in poly])
    area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
    per = float(np.hypot(np.diff(np.append(xs, xs[0])), np.diff(np.append(ys, ys[0]))).sum())
    return area < min_area * size[0] * size[1] or 4 * math.pi * area / max(per * per, 1e-9) < min_round


def relief_layers(img, base_polys, n, depth, alpha=128, bevel=0.0):
    """a stepped relief: layer 0 is the whole silhouette; layer k (1..n-1) the opaque pixels at or above the k-th
    brightness level, each extruded a little thinner and raised so its front sits a step above the one below
    (a stamped emblem: the bright metal stands proud, the dark recesses sink)"""
    a = np.array(img.getchannel("A"))
    lum = np.array(img.convert("L"), dtype=np.float32)
    opaque = a > alpha
    if opaque.sum() == 0:
        return None
    # the base's front sits at depth/2 + its bevel: every step starts above THAT (a bevel larger than a step buried it)
    front = depth / 2 + bevel
    step = depth * 0.35
    layers = [{"polys": base_polys, "z": 0.0, "depth": depth}]
    # the levels are spaced evenly in BRIGHTNESS (not by pixel share: a big dark plate would pull every quantile onto itself)
    lo, hi = (float(v) for v in np.percentile(lum[opaque], [2, 98]))
    for k in range(1, n):
        q = lo + (hi - lo) * k / n
        mask = np.where(opaque & (lum >= q), 255, 0).astype(np.uint8)
        piece = Image.new("RGBA", img.size, (0, 0, 0, 0))
        piece.putalpha(Image.fromarray(mask, "L"))
        raw = silhouette_polys(piece, speckle=10)
        # holes wind against the outlines (even-odd): only OUTLINES may be dropped as slivers, a dropped hole would fill
        # a letter's counter solid
        outer = np.sign(signed_area(max(raw, key=lambda p: abs(signed_area(p))))) if raw else 1
        polys = [p for p in raw if np.sign(signed_area(p)) != outer or not sliver(p, img.size)]
        if polys:
            # its front face = the base front + k steps; centred extrusion: z = that front - depth_k / 2
            dk = depth * 0.5
            layers.append({"polys": polys, "z": front + k * step - dk / 2, "depth": dk})
    return layers


def depth_grid(img, out_path, alpha=128, cells=200, ramp=0.06):
    """the piece's depth (Depth Anything V2 Small, the kit's vetted model; bright = near) on a grid of `cells` along its
    long side: 0..1 inside the silhouette (normalised on its own 2nd..98th percentile), NaN outside, eased down to 0
    within `ramp` of the edge so the relief meets the base instead of floating over it -> a .npy for Blender"""
    import contextlib
    import warnings
    sys.path.insert(0, os.path.join(HERE, "..", "vision"))
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stderr(io.StringIO()):
        import run as V  # noqa: PLC0415
    rgb = Image.new("RGB", img.size, (128, 128, 128))
    rgb.paste(img, mask=img.getchannel("A"))
    d = V.depth(rgb)
    dz = grid_from_depth(d, np.array(img.getchannel("A")) > alpha, cells, ramp)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.save(out_path, dz.astype(np.float32))
    return out_path


def grid_from_depth(d, a, cells=200, ramp=0.06):
    """a depth map (HxW, bright = near) + the opaque mask -> the relief grid: 0..1 inside, NaN outside, eased to 0 at
    the edge (pure: no model)"""
    from scipy import ndimage as ndi
    lo, hi = np.percentile(d[a], [2, 98]) if a.any() else (0.0, 1.0)
    d = np.clip((d - lo) / max(1e-6, hi - lo), 0, 1)
    h, w = d.shape
    gw, gh = (cells, max(2, round(cells * h / w))) if w >= h else (max(2, round(cells * w / h)), cells)
    dz = np.array(Image.fromarray((d * 65535).astype(np.uint16)).resize((gw, gh), Image.BILINEAR), dtype=np.float32) / 65535
    m = np.array(Image.fromarray(a.astype(np.uint8) * 255).resize((gw, gh), Image.NEAREST)) > 127
    dz = ndi.gaussian_filter(dz, 1.0)
    # (padded: a mask touching the border has no zero there, and its relief stood as a cliff at the image edge)
    edge = np.maximum(ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] - 1, 0) / max(1.0, ramp * max(gw, gh))  # (the outermost cells sit ON the base)
    dz = dz * np.clip(edge, 0, 1) ** 0.7
    dz[~m] = np.nan
    return dz


def _keyed(keys, t):
    """linear between [t, degrees] keys (t 0..1), held outside them"""
    keys = sorted(keys)
    if t <= keys[0][0]:
        return float(keys[0][1])
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return float(v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0))
    return float(keys[-1][1])


def rotations(motion="spin", n=24, curve=None):
    """every frame's rotation (radians x, y, z) — the turntable as DATA (Blender only plays the list). `curve`: a motion
    of your own, {"x": [[t, deg], ...], "y": [...], "z": [...]} over t 0..1 (--motion-file)"""
    out = []
    for i in range(n):
        t = i / n
        if curve:
            out.append([math.radians(_keyed(curve[ax], t)) if curve.get(ax) else 0.0 for ax in ("x", "y", "z")])
        elif motion == "sway":  # a card catching the light
            out.append([math.radians(8 * math.sin(2 * math.pi * t)), math.radians(28 * math.sin(2 * math.pi * t)), 0.0])
        elif motion == "land":  # a medal arriving, once: three turns spinning down to rest face-on, a dying wobble
            e = 1 - (1 - t) ** 3
            out.append([math.radians(14 * math.sin(6 * math.pi * t) * (1 - t)), 3 * 2 * math.pi * (1 - e), 0.0])
        elif motion == "flip":  # a reveal, once: the back held, a turn easing out with a small overshoot, the face settles
            k = min(1.0, max(0.0, (t - 0.15) / 0.6))
            e = 1 - (1 - k) ** 3
            over = math.sin(math.pi * min(1.0, max(0.0, (t - 0.6) / 0.4))) * 0.12 * (1 - k * 0.5)
            out.append([math.radians(10 * math.sin(math.pi * k)), math.pi * (1 + e) + over, 0.0])
        else:  # a coin, an emblem
            out.append([0.0, 2 * math.pi * t, 0.0])
    return out


def depth_layers(img, d, k):
    """the piece cut into k depth slices (far -> near) by the depth estimate's levels: each slice keeps the piece's
    pixels whose depth falls in its band, the rest transparent"""
    a = np.array(img.getchannel("A"))
    rgba = np.array(img.convert("RGBA"))
    inside = a > 0
    lo, hi = np.percentile(d[inside], [2, 98]) if inside.any() else (0.0, 1.0)
    dn = np.clip((d - lo) / max(1e-6, hi - lo), 0, 0.999999)
    band = (dn * k).astype(int)
    out = []
    for j in range(k):
        layer = rgba.copy()
        layer[..., 3] = np.where(inside & (band == j), a, 0)
        out.append(Image.fromarray(layer, "RGBA"))
    return out


def blender():
    return find_blender()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--material", default="gold")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--res", type=int, default=384)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--depth", type=float, default=0.12)
    ap.add_argument("--bevel", type=float, default=0.03)
    ap.add_argument("--motion", default="spin", choices=["spin", "sway", "flip", "land"])
    ap.add_argument("--cards", type=int, default=0, help="K > 1: export the piece as K depth-sliced PARALLAX cards (an FBX of K quads) for VFX; no turntable")
    ap.add_argument("--edge", default=None, help="the sides + bevel: gold|chrome|silver|enamel or #rrggbb (default: the same metal)")
    ap.add_argument("--motion-file", default=None, help='a motion of your own: {"x": [[t, deg], ...], "y": [...], "z": [...]} over t 0..1')
    ap.add_argument("--depth-relief", type=float, default=0.0,
                    help="H > 0: the front becomes a SCULPTED relief, raised up to H (scene units; the piece's long side = 2) by a depth estimate")
    ap.add_argument("--relief", type=int, default=0, help="N > 1: a stepped relief, the piece's brighter levels raised in N steps")
    ap.add_argument("--back", default=None, help="<identity>/<piece> printed on the reverse (a card's back; --motion flip reveals the face)")
    ap.add_argument("--gloss", type=float, default=0.5, help="the face's clear coat: 0.5 a lacquered card, ~0.1 a printed logo (the coat's glare washes red to pink)")
    ap.add_argument("--exposure", type=float, default=0.0, help="the render's exposure (a big flat face burns: about -0.8)")
    ap.add_argument("--alpha", type=int, default=128, help="the silhouette's alpha cut (a faint piece: lower it)")
    ap.add_argument("--no-face", action="store_true", help="metal only (no artwork on the front face)")
    ap.add_argument("--art", default="assets/ui/art")
    ap.add_argument("--blender", default=None)
    a = ap.parse_args()
    if "/" not in a.target:
        return emit("fail", "spin: name the piece as <identity>/<piece>", "lune run kit ui spin witch/card_clock --material gold")
    ident, piece = a.target.split("/", 1)
    src = os.path.join(a.art, ident, f"{piece}.png")
    if not os.path.isfile(src):
        return emit("fail", f"spin: no piece at {src}", "make the flat piece first (render, ink, letter, smear...)")
    t0 = time.time()
    img = Image.open(src).convert("RGBA")
    polys = silhouette_polys(img, alpha=a.alpha)
    if not polys:
        return emit("fail", "spin: the piece has no opaque silhouette to extrude", "a piece with a transparent background")
    back_src = None
    if a.back:
        back_src = os.path.abspath(os.path.join(a.art, f"{a.back}.png"))
        if not os.path.isfile(back_src):
            return emit("fail", f"spin: no back piece at {back_src}", "name it as <identity>/<piece>, a PNG in the art folder")
    layers = relief_layers(img, polys, a.relief, a.depth, a.alpha, a.bevel) if a.relief > 1 else None
    if a.cards > 1:  # parallax cards: the piece sliced by depth into K alpha-cut quads, one FBX (VFX / a ViewportFrame)
        import contextlib
        import warnings
        sys.path.insert(0, os.path.join(HERE, "..", "vision"))
        warnings.filterwarnings("ignore")
        with contextlib.redirect_stderr(io.StringIO()):
            import run as V  # noqa: PLC0415
        rgb = Image.new("RGB", img.size, (128, 128, 128))
        rgb.paste(img, mask=img.getchannel("A"))
        layers = depth_layers(img, V.depth(rgb), a.cards)
        paths = []
        for j, im in enumerate(layers):
            pth = os.path.join(a.art, ident, f"{piece}_cards_{j}.png")
            im.save(pth)
            paths.append(os.path.abspath(pth))
        exe = a.blender or blender()
        if not exe:
            return emit("fail", "spin: Blender not found", "lune run kit doctor")
        work = os.path.join(ROOT, "build", "ui", "spin")
        os.makedirs(work, exist_ok=True)
        fbx = os.path.join(a.art, ident, f"{piece}_cards.fbx")
        job_path = os.path.join(work, f"{ident}_{piece}.cards.json")
        json.dump({"layers": paths, "size": list(img.size), "gap": a.depth, "fbx": os.path.abspath(fbx)}, open(job_path, "w", encoding="utf-8"))
        r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P", os.path.join(HERE, "cards_blender.py"), "--", "--job", job_path],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0 or "CARDS_DONE" not in r.stdout:
            return emit("fail", f"spin --cards: Blender failed: {(r.stdout + r.stderr)[-400:]}", "read the Blender output above")
        return emit("pass", f"spin: {ident}/{piece} -> {a.cards} parallax cards ({piece}_cards_0..{a.cards - 1}.png, far -> near) + {os.path.basename(fbx)}",
                    "VFX: import the FBX (each card its own object, the near ones in front); UI: stack the PNGs and slide them at different speeds",
                    fbx=fbx, cards=[os.path.basename(p) for p in paths])
    curve = None
    if a.motion_file:
        try:
            curve = json.load(open(a.motion_file, encoding="utf-8"))
        except (OSError, ValueError) as err:
            return emit("fail", f"spin: the motion file {a.motion_file} could not be read ({err})", 'write {"y": [[0, 0], [1, 360]]}')
    relief_grid = None
    if a.depth_relief > 0:
        relief_grid = {"path": depth_grid(img, os.path.join(ROOT, "build", "ui", "spin", f"{ident}_{piece}.relief.npy"), a.alpha),
                       "height": a.depth_relief}
    exe = a.blender or blender()
    if not exe:
        return emit("fail", "spin: Blender not found", "lune run kit doctor")
    out_dir = os.path.join(a.art, ident, f"{piece}_spin")
    work = os.path.join(ROOT, "build", "ui", "spin")
    os.makedirs(work, exist_ok=True)
    frames_tmp = os.path.join(work, f"{ident}_{piece}")
    shutil.rmtree(frames_tmp, ignore_errors=True)
    fbx = os.path.join(a.art, ident, f"{piece}_spin.fbx")
    job = {"polys": polys, "image": os.path.abspath(src), "size": list(img.size), "material": a.material, "face": not a.no_face,
           "depth": a.depth, "bevel": a.bevel, "frames": a.frames, "res": a.res, "samples": a.samples, "motion": a.motion,
           "exposure": a.exposure, "gloss": a.gloss, "back": back_src, "layers": layers, "relief_grid": relief_grid, "rotations": rotations(a.motion, max(0, a.frames), curve), "edge": a.edge, "out": os.path.abspath(frames_tmp), "fbx": os.path.abspath(fbx)}
    job_path = os.path.join(work, f"{ident}_{piece}.job.json")
    json.dump(job, open(job_path, "w", encoding="utf-8"))
    r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P", os.path.join(HERE, "spin_blender.py"), "--", "--job", job_path],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or "SPIN_DONE" not in r.stdout:
        return emit("fail", f"spin: Blender failed: {(r.stdout + r.stderr)[-400:]}", "read the Blender output above")
    if a.frames <= 0:  # the mesh only: the FBX is replaced, a flipbook's sidecar facts are KEPT (its frames stay valid)
        side_path = os.path.join(a.art, ident, f"{piece}_spin.spin.json")
        side = {}
        if os.path.isfile(side_path):
            try:
                side = json.load(open(side_path, encoding="utf-8"))
            except ValueError:
                side = {}
        side.setdefault("frames", 0)
        side.update({"schema": 1, "kind": "spin", "from": src, "fbx": os.path.basename(fbx), "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "mesh": {"material": a.material, "face": not a.no_face, "depth": a.depth, "bevel": a.bevel, "relief": a.relief,
                              "gloss": a.gloss, "polys": len(polys)}})
        side.setdefault("about", f"a {a.material} 3D mesh of {piece} ({len(polys)} outline(s) extruded + bevelled, its art on the front)")
        with open(side_path, "w", encoding="utf-8", newline="\n") as fh_:
            json.dump(side, fh_, indent=1)
        return emit("pass", f"spin: {ident}/{piece} -> mesh {os.path.basename(fbx)} only ({len(polys)} outline(s); {time.time() - t0:.0f}s)",
                    f"load {fbx} in a ViewportFrame (Ui.model) or import it in Blender", fbx=fbx)
    frames = sorted(f for f in os.listdir(frames_tmp) if f.endswith(".png"))
    # the frames sit FLAT beside the piece (<piece>_spin_f000.png): the art index, uploads and the vault see top-level
    # pieces only
    shutil.rmtree(out_dir, ignore_errors=True)
    for old_f in os.listdir(os.path.join(a.art, ident)):
        if old_f.startswith(f"{piece}_spin_f") and old_f.endswith(".png"):
            os.remove(os.path.join(a.art, ident, old_f))
    ims = []
    for i, f in enumerate(frames):
        shutil.copyfile(os.path.join(frames_tmp, f), os.path.join(a.art, ident, f"{piece}_spin_f{i:03d}.png"))
        ims.append(Image.open(os.path.join(frames_tmp, f)).convert("RGBA"))
    cols = math.ceil(math.sqrt(len(ims)))
    rows = math.ceil(len(ims) / cols)
    fw, fh = ims[0].size
    sheet = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, ((i % cols) * fw, (i // cols) * fh))
    sheet_path = os.path.join(a.art, ident, f"{piece}_spin_sheet.png")
    sheet.save(sheet_path)
    side = {"schema": 1, "kind": "spin", "from": src, "material": a.material, "face": not a.no_face, "motion": a.motion, "exposure": a.exposure, "gloss": a.gloss,
            "frames": len(ims), "frame_size": [fw, fh], "sheet": {"cols": cols, "rows": rows}, "depth": a.depth, "bevel": a.bevel,
            "polys": len(polys), "relief": a.relief, "fbx": os.path.basename(fbx),
            "about": f"a {a.material} 3D mesh of {piece} ({len(polys)} outline(s) extruded + bevelled, its art on the front) turning: {len(ims)} frames",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(a.art, ident, f"{piece}_spin.spin.json"), "w", encoding="utf-8", newline="\n") as fh_:
        json.dump(side, fh_, indent=1)
    return emit("pass", f"spin: {ident}/{piece} -> {len(ims)} {a.material} frames ({fw}x{fh}), sheet {cols}x{rows}, mesh {os.path.basename(fbx)} ({len(polys)} outline(s); {time.time() - t0:.0f}s)",
                f"LOOK at {sheet_path}; play it: a reel track {{\"prop\": \"art\", \"keys\": [[0, \"{ident}/{piece}_spin_f000\"], ...]}}",
                sheet=sheet_path, frames=f"{ident}/{piece}_spin_f000..f{len(ims) - 1:03d}", fbx=fbx)


if __name__ == "__main__":
    sys.exit(main())
