"""PHOTOGRAMMETRY: photos of a real thing -> a mesh the kit builds with (the owner's limitations, D-R02: "No integrated
general photogrammetry route ... integrate calibration / SfM / MVS, metric scale, cleanup and game conversion;
demonstrate a repeatable capture-to-engine result"; the 3D methods audit, stage L).

    python kit/tools/photoscan.py <photos folder> <name> [--quality low|medium|high] [--size <m> --axis height]

Runs COLMAP (vetted 2026-11-16, VETLOG: ~/.cache/roblox-kit/tools/colmap-4.2.1, local, on the GPU):
  1. CALIBRATION and STRUCTURE FROM MOTION: features in every photo, matched, the cameras solved (one lens for all
     the photos: shoot them with one camera at one zoom) - the photos that could not be placed are named.
  2. MULTI-VIEW STEREO: depth for every photo, fused into a dense coloured point cloud.
  3. A SURFACE: Poisson's closed surface through the points, its overreaching skin trimmed.
Then Blender (kit/blender/photoscan_finish.py) makes it a kit mesh:
  4. LEVEL: up is where the cameras' own "up" points on average (people hold a camera level), the object's base on
     the ground, its middle on the origin.
  5. SCALE: a size you know (--size 0.62 --axis height: metres along that axis) makes it metric; without one it
     stays unscaled and says so (a.import_mesh(height=) scales it then).
  6. CLEAN: only the largest connected piece is kept (a scrap of the table, a hand); the floor the object stood on
     is cut away below its lowest point; the triangles cut to a budget.
  7. COLOUR: the points' colours baked into a texture on a fresh unwrap - a GLB a.import_mesh reads.
-> assets/models/<name>.scan.glb + <name>.scan.json (what each step found: photos placed, the solve's error in
pixels, points, triangles, the up it chose, the scale it used) and the summary / next_action lines."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VETTED_COLMAP = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "tools", "colmap-4.2.1", "app", "bin",
                             "colmap.exe" if os.name == "nt" else "colmap")


def colmap_bin():
    """the COLMAP binary: KIT_COLMAP, else the vetted download (VETLOG 2026-11-16: the Windows CUDA build), else
    `colmap` on PATH (the Linux / macOS packages), else the vetted path - so a missing COLMAP's error names where the
    vetted build belongs"""
    forced = os.environ.get("KIT_COLMAP")
    if forced:
        return forced
    if os.path.isfile(VETTED_COLMAP):
        return VETTED_COLMAP
    return shutil.which("colmap") or VETTED_COLMAP


COLMAP = colmap_bin()
QUALITY = {   # (the longest image side the stereo works at, Poisson's depth, the triangle budget)
    "low": (1000, 9, 60000), "medium": (1600, 10, 150000), "high": (2400, 11, 300000)}
PLACED_BAR = 0.8      # under this share of the photos placed, the capture is said to be weak
ERROR_BAR = 1.5       # pixels: a mean reprojection error over this is said


TRIMS = (7, 5, 3)     # Poisson's trims tried in turn (see scan)


def ply_vertices(path):
    """how many vertices a PLY file says it holds (its header) -> int, 0 when none or no file"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096).split(b"end_header")[0].decode("ascii", "replace")
    except OSError:
        return 0
    for ln in head.splitlines():
        if ln.startswith("element vertex"):
            return int(ln.split()[2])
    return 0


def blender():
    sys.path.insert(0, HERE)
    import cad_check  # noqa: PLC0415

    return cad_check.blender()


def run(args, log, cwd=None):
    """one COLMAP step; its output appended to `log`; -> seconds. A failed step raises with its last lines."""
    t = time.time()
    with open(log, "a", encoding="utf-8", errors="replace") as fh:
        fh.write("\n$ colmap " + " ".join(args) + "\n")
        fh.flush()
        r = subprocess.run([COLMAP, *args], cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        tail = open(log, encoding="utf-8", errors="replace").read().splitlines()[-6:]
        raise RuntimeError(f"colmap {args[0]} failed (exit {r.returncode}): " + " | ".join(tail))
    return round(time.time() - t, 1)


def read_model(txt_dir):
    """COLMAP's text model -> {"cameras": [{"image", "centre" (3,), "up" (3,): the image's up in the world}],
    "points": n, "error": mean reprojection error in pixels or None}"""
    import numpy as np  # noqa: PLC0415

    def quat(qw, qx, qy, qz):
        return np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                         [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                         [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])

    cams = []
    with open(os.path.join(txt_dir, "images.txt"), encoding="utf-8") as fh:
        rows = [ln for ln in fh.read().splitlines() if not ln.startswith("#")]   # (an image with no matched points has an EMPTY second line: kept, or the pairs slip)
    for ln in rows[::2]:   # (every other line is the image's 2-D points)
        if not ln.strip():
            continue
        f = ln.split()
        r = quat(*map(float, f[1:5]))
        t = np.array(list(map(float, f[5:8])))
        centre = -r.T @ t
        up = -r.T @ np.array([0.0, 1.0, 0.0])          # (COLMAP's camera: x right, y DOWN, z forward)
        cams.append({"image": " ".join(f[9:]), "centre": centre.tolist(), "up": up.tolist()})
    errors, points = [], 0
    with open(os.path.join(txt_dir, "points3D.txt"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("#") or not ln.strip():
                continue
            points += 1
            errors.append(float(ln.split()[7]))
    return {"cameras": cams, "points": points, "error": round(sum(errors) / len(errors), 3) if errors else None}


OUTLINE_BAR = 0.93    # the scan's outline over the photos' (median IoU): under this the scan is not the object
#                       (measured 2026-11-16: a good synthetic scan 0.99, the 24-photo doubled one 0.88)
OUTLINE_WORST = 0.85  # ... and no single photo's under this (the doubled one: 0.79)
OUTLINE_PX = 480      # the outlines are compared at this width
UP_BAR = 0.5          # the cameras' own "up" must agree this well (mean cosine with their average) to level by it
ORBIT_GAP = 120.0     # degrees: a capture leaving a gap this wide round the object is levelled less surely (said)
BASE_BAR = 0.2       # a base filled in over this share of the footprint: a scale from the height fails
BASE_NOTE = 0.05     # ... over this: said (measured 2026-11-16: the good capture 0.09 and 4% large, the thin 0.34)
HEIGHT_BAR = 0.97    # the scan's height over the object's in its photos (median): under this a scale read from the
#                      height is that much too large, whatever the base's fill says (2026-11-18: the capture's
#                      render varies - one thin render filled only 14% of its base, stood 0.923 tall and came out
#                      10% too wide, accepted; the good capture 0.995)
MARK = ".photoscan-work"   # (a work folder this tool made: the only kind it ever deletes)
LOCK = ".photoscan-lock"   # (held by the run using the work folder: a second run waits for it - see hold_work)
WAIT = 3600.0              # seconds a run waits for another run's work folder before it refuses (PHOTOSCAN_WAIT)
SEED = 1                  # (the camera solve's random numbers: fixed, so a capture always gives the same scan)


CUT = r'''
import json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, sys.argv[1])
import run
for src, fusion_png, small_npy, w, h in json.load(open(sys.argv[2])):
    im = Image.open(src).convert("RGB")
    m = run.cutout(im)
    full = Image.fromarray(((m > 0.5) * 255).astype(np.uint8))
    full.save(fusion_png)
    small = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)) / 255.0
    np.save(small_npy, small.astype(np.float32))
'''


def _image_rows(txt):
    """COLMAP's images.txt -> [(image id, (qw, qx, qy, qz), (tx, ty, tz), camera id, name)]. An image with no
    matched points has an EMPTY second line (kept, or the pairs slip); a name may hold spaces (the review)."""
    with open(os.path.join(txt, "images.txt"), encoding="utf-8") as fh:
        rows = [ln for ln in fh.read().splitlines() if not ln.startswith("#")]
    out = []
    for ln in rows[::2]:
        if not ln.strip():   # (a blank line at the file's end)
            continue
        f = ln.split()
        out.append((f[0], tuple(map(float, f[1:5])), tuple(map(float, f[5:8])), f[8], " ".join(f[9:])))
    return out


def _rot(q):
    qw, qx, qy, qz = q
    return [[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]]


def cutouts(work, dense, log):
    """the object cut out of every undistorted photo (kit/vision cutout, BiRefNet): a full-size mask for COLMAP's
    fusion (dense/masks/<image>.png: only the object's points are fused - a table, a floor, a street behind are
    not) and a small one for the outline check -> the views for photoscan_outline.py (without "to_scan")"""
    txt = os.path.join(work, "txt_dense")
    os.makedirs(txt, exist_ok=True)
    run(["model_converter", "--input_path", os.path.join(dense, "sparse"), "--output_path", txt,
         "--output_type", "TXT"], log)
    cams = {}
    with open(os.path.join(txt, "cameras.txt"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("#") or not ln.strip():
                continue
            f = ln.split()   # (undistorted: PINHOLE w h fx fy cx cy)
            cams[f[0]] = [float(x) for x in f[2:8]]
    fusion_dir, small_dir = os.path.join(dense, "masks"), os.path.join(work, "outlines")
    os.makedirs(fusion_dir, exist_ok=True)
    os.makedirs(small_dir, exist_ok=True)
    views, jobs = [], []
    for _id, q, t, cam, name in _image_rows(txt):
        w0, h0, fx, fy, cx, cy = cams[cam]
        k = OUTLINE_PX / w0
        w, h = OUTLINE_PX, max(1, int(round(h0 * k)))
        small = os.path.join(small_dir, name + ".npy")
        jobs.append([os.path.join(dense, "images", name), os.path.join(fusion_dir, name + ".png"), small, w, h])
        views.append({"image": name, "R": _rot(q), "t": list(t), "width": w, "height": h,
                      "fx": fx * k, "fy": fy * k, "cx": cx * k, "cy": cy * k, "mask": small})
    todo = [j for j in jobs if not (os.path.isfile(j[1]) and os.path.isfile(j[2]))]
    if todo:
        jobs_path = os.path.join(work, "cutout_jobs.json")
        json.dump(todo, open(jobs_path, "w", encoding="utf-8"))
        r_ = subprocess.run([sys.executable, "-c", CUT, os.path.join(REPO, "kit", "vision"), jobs_path],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r_.returncode != 0:
            raise RuntimeError("photoscan: the photos' cut-out failed: " + (r_.stderr or r_.stdout)[-400:])
    return views


def outline(work, views, glb, to_scan):
    """the scan seen through its own cameras against the object cut out of each photo
    (kit/blender/photoscan_outline.py) -> {"median", "worst", "views", "height": {"median", "shortest"}}"""
    spec = os.path.join(work, "outline_views.json")
    json.dump({"to_scan": to_scan, "views": views}, open(spec, "w", encoding="utf-8"))
    out = os.path.join(work, "outline.json")
    r_ = subprocess.run([blender(), "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                         os.path.join(REPO, "kit", "blender", "photoscan_outline.py"), "--", glb, spec, out],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r_.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError("photoscan: the outline check failed: " + (r_.stderr or r_.stdout)[-400:])
    return json.load(open(out, encoding="utf-8"))


def prepare(images, folder):
    """the photos as COLMAP must see them: each turned upright by its own EXIF orientation (a phone's portrait photo
    is stored on its side with a flag COLMAP 4.2.1 ignores - the review: such a photo was skipped, and an all-portrait
    capture levelled by noise), copied into `folder`; one size for all (one camera) -> [names]. Refuses photos of
    different sizes, naming them."""
    from PIL import Image, ImageOps  # noqa: PLC0415

    os.makedirs(folder, exist_ok=True)
    names = sorted(f for f in os.listdir(images) if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")))
    sizes = {}
    for n in names:
        with Image.open(os.path.join(images, n)) as im:
            up = ImageOps.exif_transpose(im).convert("RGB")
            sizes.setdefault(up.size, []).append(n)
            up.save(os.path.join(folder, os.path.splitext(n)[0] + ".jpg"), quality=95)
    if len(sizes) > 1:
        common = max(sizes, key=lambda s: len(sizes[s]))
        odd = [f"{n} ({s[0]} x {s[1]})" for s, ns in sizes.items() if s != common for n in ns]
        raise ValueError(f"photoscan: the photos are not all one size ({common[0]} x {common[1]} for most; "
                         f"{', '.join(odd[:4])}{' ...' if len(odd) > 4 else ''}) - one camera, one zoom, one "
                         "orientation: shoot them again so, or take the odd ones out")
    return sorted(os.listdir(folder))


def levelling(cameras):
    """how surely the cameras say which way is up -> {"agreement": mean cosine of each camera's up with their
    average, "gap": the widest angle round the object no camera stands in (degrees)}"""
    import numpy as np  # noqa: PLC0415

    ups = np.array([c["up"] for c in cameras], float)
    mean = ups.mean(axis=0)
    mean = mean / max(float(np.linalg.norm(mean)), 1e-12)
    centres = np.array([c["centre"] for c in cameras], float)
    flat = centres - centres.mean(axis=0)
    flat = flat - np.outer(flat @ mean, mean)
    a = flat[0] / max(float(np.linalg.norm(flat[0])), 1e-12)
    b = np.cross(mean, a)
    ang = np.sort(np.degrees(np.arctan2(flat @ b, flat @ a)) % 360.0)
    gaps = np.diff(np.concatenate([ang, ang[:1] + 360.0])) if len(ang) else np.array([360.0])
    return {"agreement": round(float((ups @ mean).mean()), 3), "gap": round(float(gaps.max()), 1)}


def sparse_steps(db, photos_dir, sparse_dir):
    """the camera solve's three COLMAP runs, set so the same photos give the same cameras, bit for bit (measured
    2026-11-18: the same thin capture came out refused for its base, refused for its outline, or accepted). The
    threaded extractor numbers the photos in the order its threads finish, and the pairs' RANSAC and the mapper
    follow that numbering; the GPU extractor's features differ from run to run too. So: CPU features on one thread
    (the photos numbered by name; 13 s for 32 photos of 1024 x 768 where the GPU took 1 s - the stereo after it
    takes minutes), a fixed seed for the pairs' RANSAC and the mapper (both -1 = random by default), the mapper on
    one thread (threaded, the thin capture's cameras came out otherwise 1 run in 5; one thread: 5 of 5 the same, as
    fast). The GPU matcher repeats once the numbering and seed are fixed (4 of 4). The fusion and the surface after
    the stereo are on one thread too (below): threaded, each run fused other points."""
    return [
        ["feature_extractor", "--database_path", db, "--image_path", photos_dir, "--ImageReader.single_camera", "1",
         "--FeatureExtraction.use_gpu", "0", "--FeatureExtraction.num_threads", "1"],
        # (always exhaustive: the vocabulary-tree matcher would fetch an unvetted file from the network)
        ["exhaustive_matcher", "--database_path", db, "--FeatureMatching.use_gpu", "1",
         "--TwoViewGeometry.random_seed", str(SEED)],
        ["mapper", "--database_path", db, "--image_path", photos_dir, "--output_path", sparse_dir,
         "--Mapper.random_seed", str(SEED), "--Mapper.num_threads", "1"],
    ]


def clear_work(work):
    """empties a work folder this tool made, its MARK LAST: a delete stopped half way (a file still open in another
    run - Windows will not delete it) leaves the folder marked, so the next run may clear it. (shutil.rmtree took the
    mark first - a dot name lists first - and a stopped delete left a folder no run would ever touch again.)"""
    for entry in os.listdir(work):
        if entry in (MARK, LOCK):
            continue
        path = os.path.join(work, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def hold_work(work, wait=None):
    """the work folder held for this run -> the open lock file (closing it, or the run ending, lets it go). Another
    run holding it: this one waits for it (up to `wait` seconds, PHOTOSCAN_WAIT, default WAIT), then refuses by name.
    (2026-11-20: two test runs at once scanned into one work folder - the second cleared it while the first's COLMAP
    held its database open; Windows refused the delete and the tool died with a bare traceback, exit 1, nothing on
    stdout. The OS lock goes with the process, so a run that crashed never blocks the next.)"""
    if wait is None:
        wait = float(os.environ.get("PHOTOSCAN_WAIT", WAIT))
    fh = open(os.path.join(work, LOCK), "a+")
    start, said = time.time(), False
    while True:
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if said:
                print(f"photoscan: {work} is free after {time.time() - start:.0f} s", file=sys.stderr)
            return fh
        except OSError:
            if time.time() - start >= wait:
                fh.close()
                raise RuntimeError(f"photoscan: another photoscan run is using the work folder {work} (waited "
                                   f"{wait:.0f} s) - let it finish, or give another --work") from None
            if not said:
                print(f"photoscan: another run is using {work} - waiting for it (up to {wait:.0f} s)",
                      file=sys.stderr)
                said = True
            time.sleep(min(5.0, max(0.1, wait / 10)))


def scan(images, name, quality="medium", size=None, axis="height", out_dir=None, work=None, reuse=False):
    """the whole route -> the report (dict). Raises with the step that failed. reuse: a previous run's cameras and
    dense points (its work folder) are kept and the surface on is made again - the stereo is the slow part"""
    if not os.path.isfile(COLMAP):
        raise RuntimeError(f"COLMAP is not at {COLMAP} - see VETLOG.md (2026-11-16) for the vetted download")
    side, depth, budget = QUALITY[quality]
    out_dir = out_dir or os.path.join(REPO, "assets", "models")
    work = os.path.abspath(work or os.path.join(REPO, "build", "scan", name))
    if os.path.abspath(images) == work or os.path.abspath(images).startswith(work + os.sep):
        raise ValueError(f"photoscan: the work folder {work} holds the photos - give another --work")
    if os.path.isdir(work) and os.listdir(work) and not os.path.isfile(os.path.join(work, MARK)):
        raise ValueError(f"photoscan: {work} is not empty and was not made by photoscan - it is never deleted; "
                         "give an empty or new --work")
    os.makedirs(work, exist_ok=True)
    open(os.path.join(work, MARK), "a").close()
    held = hold_work(work)   # (before anything in it is read, cleared or written: another run may be in it)
    try:
        return _scan(images, name, quality, size, axis, out_dir, work, reuse, side, depth, budget)
    finally:
        held.close()


def _scan(images, name, quality, size, axis, out_dir, work, reuse, side, depth, budget):
    """scan's route, its work folder already held"""
    fused = os.path.join(work, "dense", "fused.ply")
    reuse = bool(reuse) and ply_vertices(fused) > 0     # (only what a previous run really made)
    if not reuse:
        try:
            clear_work(work)
        except OSError as e:   # (a file another program holds open: said by name, never a bare traceback)
            raise RuntimeError(f"photoscan: the work folder {work} could not be cleared - "
                               f"{getattr(e, 'filename', None) or 'a file in it'} is held open by another program "
                               f"({e.strerror or e}): close it, or give another --work") from e
    os.makedirs(os.path.join(work, "sparse"), exist_ok=True)
    photos_dir = os.path.join(work, "photos")
    photos = sorted(os.listdir(photos_dir)) if reuse else prepare(images, photos_dir)
    if len(photos) < 8:
        raise ValueError(f"photoscan: {len(photos)} photos in {images} - 8 at the very least, 30 to 60 round the "
                         "object at two or three heights is a capture")
    log = os.path.join(work, "colmap.log")
    db = os.path.join(work, "database.db")
    secs = {"reused": reuse}
    if not reuse:
        for step, args in zip(("features", "matching", "cameras"), sparse_steps(db, photos_dir,
                                                                                 os.path.join(work, "sparse"))):
            secs[step] = run(args, log)
    models = sorted(m for m in os.listdir(os.path.join(work, "sparse")) if m.isdigit())
    if not models:
        raise RuntimeError("photoscan: COLMAP could not place the cameras at all - too little texture, or photos "
                           "too far apart (each should share most of its view with the next)")
    # (several models: the capture fell apart into pieces; the largest is used and the rest said)
    sizes = {}
    for m in models:
        txt = os.path.join(work, "txt_" + m)
        os.makedirs(txt, exist_ok=True)
        run(["model_converter", "--input_path", os.path.join(work, "sparse", m), "--output_path", txt,
             "--output_type", "TXT"], log)
        sizes[m] = read_model(txt)
    best = max(sizes, key=lambda m: len(sizes[m]["cameras"]))
    model = sizes[best]
    dense = os.path.join(work, "dense")
    if not reuse:
        secs["undistort"] = run(["image_undistorter", "--image_path", photos_dir, "--input_path",
                                 os.path.join(work, "sparse", best), "--output_path", dense,
                                 "--max_image_size", str(side)], log)
    t = time.time()
    views = cutouts(work, dense, log)
    secs["cutouts"] = round(time.time() - t, 1)
    if not reuse:
        secs["stereo"] = run(["patch_match_stereo", "--workspace_path", dense,
                              "--PatchMatchStereo.geom_consistency", "true"], log)
        secs["fusion"] = run(["stereo_fusion", "--workspace_path", dense, "--output_path", fused,
                              "--StereoFusion.mask_path", os.path.join(dense, "masks"),
                              "--StereoFusion.num_threads", "1"], log)   # (threaded: other points each run; 1.2 -> 3.1 s)
    meshed = os.path.join(dense, "meshed.ply")
    # Poisson's trim cuts the surface where the points are thin. COLMAP's default (10) cut away the WHOLE surface
    # of the urn trial (an empty file, no word in the log) - 7 first, lower only when that comes back empty; the
    # skin a low trim leaves is cut by the finish (faces far from every point)
    secs["surface"], trim = 0.0, None
    for trim in TRIMS:
        secs["surface"] += run(["poisson_mesher", "--input_path", fused, "--output_path", meshed,
                                "--PoissonMeshing.depth", str(depth), "--PoissonMeshing.trim", str(trim),
                                "--PoissonMeshing.num_threads", "1"], log)   # (threaded: another surface each run)
        if ply_vertices(meshed) > 0:
            break
    else:
        raise RuntimeError(f"photoscan: Poisson made no surface from {ply_vertices(fused):,} points at any trim of "
                           f"{TRIMS} - too few points (more photos, more texture on the object)")
    level = levelling(model["cameras"])
    report = {"name": name, "photos": len(photos), "placed": len(model["cameras"]), "trim": trim,
              "pieces": len(models), "error_px": model["error"], "sparse_points": model["points"],
              "quality": quality, "seconds": secs, "colmap": "4.2.1", "level": level}
    cams_path = os.path.join(work, "cameras.json")
    json.dump(model["cameras"], open(cams_path, "w", encoding="utf-8"))
    glb = os.path.join(out_dir, f"{name}.scan.glb")
    finish = os.path.join(REPO, "kit", "blender", "photoscan_finish.py")
    args = [blender(), "-b", "--factory-startup", "--python-exit-code", "2", "-P", finish, "--", meshed, cams_path,
            glb, str(budget), "--points", fused]
    if size:
        args += ["--size", str(float(size)), "--axis", axis]
    t = time.time()
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    secs["finish"] = round(time.time() - t, 1)
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("FINISH ")), None)
    if r.returncode != 0 or not line:
        raise RuntimeError("photoscan: the Blender finish failed: " + (r.stderr or r.stdout)[-600:])
    report.update(json.loads(line[7:]))
    report["glb"] = os.path.relpath(glb, REPO).replace("\\", "/")
    t = time.time()
    report["outline"] = outline(work, views, glb, report.pop("to_scan"))
    secs["outline"] = round(time.time() - t, 1)
    said, notes = [], []
    if report["placed"] < PLACED_BAR * report["photos"]:
        said.append(f"only {report['placed']} of {report['photos']} photos were placed")
    lost = sorted({c["image"] for m in models if m != best for c in sizes[m]["cameras"]}
                  - {c["image"] for c in model["cameras"]})
    report["photos_in_other_pieces"] = len(lost)
    if lost:   # (a stray second model of photos the main one has too is no split)
        said.append(f"the capture fell apart: {len(lost)} photos were placed only in a separate piece (the "
                    "largest is used) - more overlap between neighbouring photos")
    if report["error_px"] is not None and report["error_px"] > ERROR_BAR:
        said.append(f"the camera solve is off by {report['error_px']} pixels on average")
    if level["agreement"] < UP_BAR:
        said.append(f"the cameras do not agree which way is up (agreement {level['agreement']:.2f}, under "
                    f"{UP_BAR}) - the scan cannot be levelled by them: hold the camera upright")
    if level["gap"] > ORBIT_GAP:   # (the review: a half orbit tilted the scan 7.7 degrees; the scale shrinks with it)
        notes.append(f"the photos leave {level['gap']:.0f} degrees round the object unseen: its level (and a scale "
                     "read from its height) is less sure - walk all the way round")
    base = report.get("base_filled", 0.0)
    tall = (report["outline"].get("height") or {}).get("median")
    short = tall is not None and tall < HEIGHT_BAR
    if size and axis == "height" and (base > BASE_BAR or short):
        said.append(f"the base was not photographed ({base:.0%} of its footprint had to be filled in"
                    + (f"; seen through its own cameras the scan stands {1 - tall:.0%} shorter than the object in "
                       "the photos" if short else "")
                    + "): the height the scale is read from is short, so the scan comes out too large (the 24-photo "
                    "trial: 14%) - give a size across it (--axis width or length) or shoot lower, from below the "
                    "middle")
    elif base > BASE_NOTE:
        notes.append(f"{base:.0%} of the base was filled in (not photographed)"
                     + (": a scale read from the height may come out a few percent large" if size and
                        axis == "height" else ""))
    if short and not (size and axis == "height"):
        notes.append(f"seen through its own cameras the scan stands {1 - tall:.0%} shorter than the object in the "
                     "photos: its bottom is missing")
    o = report["outline"]
    if o["median"] < OUTLINE_BAR or (o["worst"] and o["worst"][0][1] < OUTLINE_WORST):
        said.append(f"seen through its own cameras the scan does not cover the object in the photos (outline "
                    f"overlap {o['median']:.2f}, the worst {o['worst'][0][0]} at {o['worst'][0][1]:.2f}; a good scan "
                    f"is over {OUTLINE_BAR}) - more photos, larger, more overlap")
    report["weak"], report["notes"] = said, notes
    json.dump(report, open(os.path.join(out_dir, f"{name}.scan.json"), "w", encoding="utf-8"), indent=1)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("images")
    ap.add_argument("name")
    ap.add_argument("--quality", default="medium", choices=sorted(QUALITY))
    ap.add_argument("--size", type=float, default=None, help="a size you know, in metres")
    ap.add_argument("--axis", default="height", choices=("height", "length", "width"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--reuse", action="store_true", help="keep a previous run's cameras and dense points")
    a = ap.parse_args()
    try:
        rep = scan(a.images, a.name, a.quality, a.size, a.axis, a.out, a.work, a.reuse)
    except (RuntimeError, ValueError, OSError) as e:   # (OSError: a file it could not read or write - said)
        print(f"summary: photoscan failed - {e}")
        print("next_action: fix what it names and run it again")
        return 1
    print(json.dumps(rep, indent=1))
    if rep["weak"]:   # (a capture that fails a check gives no mesh to build with - its files stay, to look at)
        print(f"summary: photoscan {a.name} FAILED its capture checks: " + "; ".join(rep["weak"]))
        print(f"next_action: retake the photos as said, run it again; the failed scan is {rep['glb']} (look, do "
              "not build with it)")
        return 2
    print(f"summary: photoscan {a.name}: {rep['placed']} of {rep['photos']} photos placed, error "
          f"{rep['error_px']} px, {rep['triangles']:,} triangles, "
          + (f"metric from {a.axis} {a.size} m" if a.size else "NOT metric (no --size)")
          + f", outline over the photos {rep['outline']['median']:.2f}")
    print(f"next_action: look at {rep['glb']} in Blender, then build it: a.import_mesh(\"Body\", \"{rep['glb']}\", "
          "height=<studs>) in a master script, and kit optimize")
    return 0


if __name__ == "__main__":
    sys.exit(main())
