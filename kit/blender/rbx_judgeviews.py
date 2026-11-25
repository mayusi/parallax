"""rbx_judgeviews.py — every full build keeps SIX standard views of itself (+ the brief's game camera + its region
close-ups) in build/judge/<name>/builds/<build id>/, so `kit judge <name> --pair` can put any two builds side by side
at the same camera and light (kit/blender/judge_pair.py).

    front, back, left, right, top   orthographic, Cycles + the studio light (what the hero render uses)
    three_quarter                   perspective, from the hero direction
    game_<camera>.png               the brief's `view:` answer (first person, third person, top-down, in the world)
    r_<region>.png                  the build's region close-ups (refs/<name>.regions.json), copied
    f_<n>_<feature>.png             one PAIR per hero feature of the brief that names a box in a traced picture: the
                                    reference's box FIRST (left, or on top for a long low feature), then the model's
                                    SAME box from that picture's camera, its larger side FEATURE_PX pixels
    features.json                   every hero feature: its pair, or why it has none
    meta.json                       build id, iteration, the frame, the view size, which files exist

A --geo build (a shape round: seconds, no bake) keeps the same views in build/judge/<name>/geo/, shaded in the parts'
own colours (Workbench), so a shape round is never blind (rbx_judgeviews.geo).

THE SIZE THE OWNER JUDGES AT (2026-11-11, card 32nd): the views were 512 x 384 until then — a hero weapon's wolf head
was about 40 px wide in what the session looked at, and its score wandered 62-68 for eleven rounds. VIEW_SIZES is
1024 wide or more, and a hero feature gets its own close-up whatever its share of the model.

THE SAME CAMERA, build after build: the views are framed on a STICKY box (builds/frame.json) — kept while the model
still fits inside it and fills most of it, re-made only when the model outgrew it or shrank well inside it. Two
builds of one model are then seen from the same place, so a part that grew looks bigger. Region close-ups use a
sticky box per region the same way (rbx.py _region_renders). The softbox is placed on the frame, not the model.

The pure helpers (sticky_box, game_cameras, brief_view, prune, view_size, feature_frame, feature_window, pane_size,
picture_box, pair_layout, features_key) need no Blender: kit/test/python/test_judge_pair.py.
"""

import json
import math
import os
import re
import shutil
import time

VIEWS = (  # (name, Roblox-space direction from the model to the camera, orthographic)
    ("front", (0.0, 0.0, -1.0), True),
    ("back", (0.0, 0.0, 1.0), True),
    ("left", (-1.0, 0.0, 0.0), True),
    ("right", (1.0, 0.0, 0.0), True),
    ("top", (0.0, 1.0, 0.0001), True),
    ("three_quarter", (-0.75, 0.4, -0.6), False),
)
VIEW_SIZE = (512, 384)  # the views of builds made before 2026-11-11 (their meta.json has no "view_size")
GAME_SIZE = (768, 432)
# the size the owner judges at, by tier (view_size / game_size): four times the old pixels at half the samples
VIEW_SIZES = {"prop": (1024, 768), "complex": (1024, 768), "hero": (1280, 960), "aaa": (1280, 960)}
GAME_SIZES = {"prop": (1280, 720), "complex": (1280, 720), "hero": (1280, 720), "aaa": (1280, 720)}
VIEW_SAMPLES = 16  # Cycles, with the denoiser (the 512-px views used 32)
FEATURE_PX = 1024  # a hero feature's close-up: its box this many pixels across, whatever its share of the model
FEATURE_MARGIN = 0.08  # of the box's larger side, kept round it in both the reference crop and the render
PAIR_STACK = 1.6  # a feature wider than this x its height: reference above, render below (else side by side)
PAIR_GAP = 8  # white pixels between a pair's two panes
GEO_SIZE = (1024, 768)  # a --geo build's shaded views (Workbench: under a second each)
GREY = (0.33, 0.35, 0.38)  # what a transparent (Workbench) render and a cut-out reference are laid on, as stored
CLAY = (0.62, 0.6, 0.57)  # the blockout's one matte colour (kit blockout): form, with no colour to flatter it
R6_TONE = (0.3, 0.42, 0.62)  # the R6 character beside the clay model in the scale view
CLAY_MARGIN = 0.04  # round the object's box, in a clay view laid beside its reference picture
GAME_FOV = 70.0  # Roblox's default Camera.FieldOfView (vertical, degrees)
KEEP_BUILDS = 30  # builds whose views are kept (the accepted and the judged build are always kept on top of these)
BG = (0.42, 0.45, 0.5)
# what a brief's `view:` answer says -> the game cameras rendered (first match wins per camera; several may match)
GAME_WORDS = (
    ("first_person", ("first person", "first-person", "fps", "viewmodel", "view model", "in hand", "in the hand")),
    ("third_person", ("third person", "third-person", "over the shoulder", "over-the-shoulder", "tps")),
    ("top_down", ("top-down", "top down", "topdown", "isometric", "overhead", "from above", "strategy")),
    ("world", ("in the world", "on the ground", "on the floor", "on a wall", "world", "placed", "scenery", "distance")),
)
GAME_TITLES = {
    "first_person": "first person: the eye 1.5 studs left of, above and behind the grip, looking ahead, 70 deg FOV",
    "third_person": "third person: Roblox's default camera 12 studs behind and 3 above the head, 70 deg FOV",
    "top_down": "top-down: 28 studs above and 16 behind, looking down at it, 70 deg FOV",
    "world": "in the world: a standing player's eye (4.5 studs up) 10 studs away at front-left, 70 deg FOV",
}


def view_size(tier):
    """the six views' pixel size for a tier (an unknown tier: a prop's)"""
    return VIEW_SIZES.get(str(tier or "").lower(), VIEW_SIZES["prop"])


def game_size(tier):
    return GAME_SIZES.get(str(tier or "").lower(), GAME_SIZES["prop"])


def _norm(path):
    return os.path.normpath(str(path)).replace("\\", "/").lower()


def trace_of_picture(picture, traces):
    """the traced view a feature's picture IS -> (view, trace): the trace whose `source` is that picture (its path,
    else its file name when exactly one trace has it); (None, None) when no traced view shows it"""
    if not picture:
        return None, None
    want = _norm(picture)
    named = [(v, t) for v, t in sorted((traces or {}).items()) if isinstance(t, dict) and t.get("source")]
    hits = [(v, t) for v, t in named if _norm(t["source"]) == want]
    if not hits:
        base = os.path.basename(want)
        hits = [(v, t) for v, t in named if os.path.basename(_norm(t["source"])) == base]
        if len({_norm(t["source"]) for _, t in hits}) > 1:  # (two different pictures of that name: not ours to pick)
            return None, None
    return hits[0] if hits else (None, None)


def feature_frame(feature, traces):
    """where a hero feature lies ON THE MODEL, from its box in a traced picture (the brief: `<picture> x0,y0,x1,y1`)
    -> {"view", "front", "a": [a0, a1], "b": [b0, b1], "hr", "picture"}: fractions of the traced outline's box, a
    along the picture's x (left -> right), b up from its bottom (rbx_project.from_picture's frame), and the box's
    height over its length. Or {"why": ...} when it cannot be placed: a close-up that is not a traced view has no
    place on the model, and a rotated / straightened trace has no plain pixel frame."""
    name = str((feature or {}).get("name") or "feature")
    box = (feature or {}).get("box")
    if not (feature or {}).get("picture"):
        return {"why": f"{name}: the brief names no picture for it (`<picture> x0,y0,x1,y1`, then its size in mm)"}
    if not box or len(box) != 4:
        return {"why": f"{name}: its picture has no box in the brief (`{feature['picture']} x0,y0,x1,y1`)"}
    view, t = trace_of_picture(feature["picture"], traces)
    if t is None:
        return {"why": f"{name}: {os.path.basename(str(feature['picture']))} is not a traced view of the model — "
                       "trace that picture (lune run kit trace) or give the feature's box in a traced picture"}
    fr = t.get("frame") or {}
    if not {"x0", "y1", "length_px"} <= set(fr):
        return {"why": f"{name}: the {view} trace has no plain pixel frame (traced with --rotate / --straighten, or "
                       "before frames) — re-run kit trace on the levelled picture"}
    x0, y1, length = float(fr["x0"]), float(fr["y1"]), float(fr["length_px"])
    hr = max(float(t.get("height_ratio") or 0.3), 1e-6)
    if length <= 0:
        return {"why": f"{name}: the {view} trace's frame has no length"}
    bx0, bx1 = sorted((float(box[0]), float(box[2])))
    by0, by1 = sorted((float(box[1]), float(box[3])))
    a0, a1 = (bx0 - x0) / length, (bx1 - x0) / length  # along the picture, from the outline's left edge
    b0, b1 = (y1 - by1) / (hr * length), (y1 - by0) / (hr * length)  # up from the outline's bottom edge
    if min(a1, b1) <= 0.0 or max(a0, b0) >= 1.0 or a1 - a0 <= 0 or b1 - b0 <= 0:
        return {"why": f"{name}: its box lies outside the traced object in {os.path.basename(str(t.get('source')))}"}
    front = "left" if str(t.get("front", "right")).lower() == "left" else "right"
    return {"view": view, "front": front, "a": [round(a0, 5), round(a1, 5)], "b": [round(b0, 5), round(b1, 5)],
            "hr": round(hr, 5), "picture": t.get("source")}


def picture_camera(view, front="right", lies="side"):
    """the camera that sees the model the way a PICTURE of `view` lies (rbx_project.basis: dir = from the model to the
    camera, right = the picture's +x, up = the picture's up; Blender space) -> (dir, right, up, mirror).
    A side picture whose front is on the left is the model's LEFT flank, seen from -X. side_left (rbx_precision's
    name for that flank) is the same camera; mirror = its picture has the front on the right (a flipped picture).
    lies="down" (a top view only, see top_lies): a reference model's mask, its front at the BOTTOM of the picture
    and the model's right side on the picture's left."""
    import rbx_project  # noqa: PLC0415

    if view == "top" and lies == "down":
        return (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), False
    mirror = False
    if view == "side_left":
        view, mirror, front = "side", front != "left", "left"
    d, r, u = rbx_project.basis(view, front)
    return tuple(float(x) for x in d), tuple(float(x) for x in r), tuple(float(x) for x in u), mirror


def top_lies(hr, along, across):
    """how a traced TOP view lies in its picture -> "side" | "down". A photo's trace runs back -> front across the
    picture (the model's length is the picture's width); a reference model's mask (kit refs measure) has its front
    DOWN (the length is the picture's height). The way whose proportions the trace has, as the build's own
    measurement decides it (rbx_precision.reference_match): hr = the outline's height over its length, along /
    across = the model's size front to back / side to side."""
    want = 1.0 / max(float(hr), 1e-6)  # the picture's width over its height
    side = max(float(along), 1e-6) / max(float(across), 1e-6)
    return "side" if abs(math.log(side / want)) <= abs(math.log((1.0 / side) / want)) else "down"


def feature_window(a, b, hr, ext, mirror=False, margin=FEATURE_MARGIN):
    """a feature's window on its picture camera's plane, in studs: `ext` = the model's (rmin, rmax, umin, umax)
    along the camera's right and up -> (centre along right, centre along up, width, height), the margin (of the
    box's larger side) added all round.
    The picture is laid on the model the way the build measures a traced view (rbx_precision.reference_match): ONE
    scale — the outline's longer side on the model's longer side — and the two boxes' centres together. So both
    panes show the same millimetres at the same size, and a model whose proportions are off shows its feature out
    of place instead of being stretched to fit (trace_match's align= is not applied: the whole outline lays it)."""
    rmin, rmax, umin, umax = (float(v) for v in ext[:4])
    hr = max(float(hr), 1e-6)
    unit = max(rmax - rmin, umax - umin) / max(1.0, hr)  # studs per length of the traced outline
    a0, a1 = (1.0 - a[1], 1.0 - a[0]) if mirror else (a[0], a[1])
    w, h = (a1 - a0) * unit, (b[1] - b[0]) * hr * unit
    pad = margin * max(w, h)
    return ((rmin + rmax) / 2 + ((a0 + a1) / 2 - 0.5) * unit, (umin + umax) / 2 + ((b[0] + b[1]) / 2 - 0.5) * hr * unit,
            w + 2 * pad, h + 2 * pad)


def pane_size(w, h, px=FEATURE_PX):
    """a close-up's pixels: its larger side is `px`"""
    big = max(float(w), float(h), 1e-9)
    return max(8, int(round(px * w / big))), max(8, int(round(px * h / big)))


def picture_box(box, margin=FEATURE_MARGIN):
    """the reference's crop for a feature: its box (x0, y0, x1, y1 in the picture's pixels, y down) with the same
    margin as the render -> whole pixels (x0, y0, x1, y1); it may run off the picture (the crop is padded there, so
    both panes keep the same framing)"""
    bx0, bx1 = sorted((float(box[0]), float(box[2])))
    by0, by1 = sorted((float(box[1]), float(box[3])))
    pad = margin * max(bx1 - bx0, by1 - by0)
    x0, y0 = int(math.floor(bx0 - pad)), int(math.floor(by0 - pad))
    x1, y1 = int(math.ceil(bx1 + pad)), int(math.ceil(by1 + pad))
    return x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)


def pair_layout(w, h):
    """how a feature's two panes sit: a long, low feature (a barrel, a blade) one above the other, else side by side
    -> "stack" | "side"; the REFERENCE is always first (on top / on the left)"""
    return "stack" if float(w) > PAIR_STACK * float(h) else "side"


def features_key(features, traces):
    """what the feature close-ups are made from, beyond the build itself: the brief's features (name, picture, box)
    and each traced view's frame — the same key and the same build: the same pictures"""
    import hashlib  # noqa: PLC0415

    feats = [[f.get("name"), f.get("picture"), f.get("box")] for f in features or []]
    views = [[v, t.get("source"), t.get("front"), t.get("frame"), t.get("height_ratio")]
             for v, t in sorted((traces or {}).items()) if isinstance(t, dict)]
    blob = json.dumps([feats, views, FEATURE_PX, FEATURE_MARGIN, PAIR_STACK], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def views_kept(old, frame_box, size, kinds, have):
    """may a build's kept views be used again? Only when its record (meta.json) is of the same frame, the same view
    SIZE (a build kept at the old 512 x 384 has no "view_size": it is rendered again at the size the owner judges
    at), the same game cameras, and every picture is still there (`have`: the file names present)"""
    if not isinstance(old, dict):
        return False
    names = [v for v, _, _ in VIEWS] + [f"game_{k}" for k in kinds]
    return (old.get("frame") == frame_box and old.get("view_size") == list(size)
            and sorted(old.get("game") or {}) == sorted(kinds) and all(f"{n}.png" in have for n in names))


def sticky_box(old, lo, hi, pad=0.04, slack=1.3, tol=0.02):
    """the frame to render from -> (box [[lo], [hi]], kept). `old` (the last build's box) is KEPT while the model's
    box (lo, hi) fits inside it (within tol x its largest side) and fills it (its largest side >= the frame's / slack);
    otherwise a new frame: the model's box grown by pad x its largest side on every side."""
    lo, hi = [float(v) for v in lo], [float(v) for v in hi]
    big = max(max(h - l for l, h in zip(lo, hi)), 1e-6)
    if old and len(old) == 2:
        olo, ohi = [float(v) for v in old[0]], [float(v) for v in old[1]]
        obig = max(max(h - l for l, h in zip(olo, ohi)), 1e-6)
        inside = all(olo[i] - tol * obig <= lo[i] and hi[i] <= ohi[i] + tol * obig for i in range(3))
        if inside and big >= obig / slack:
            return [olo, ohi], True
    return [[v - pad * big for v in lo], [v + pad * big for v in hi]], False


def game_cameras(text):
    """a brief's `view:` answer -> the game cameras it names (GAME_WORDS order), [] when it names none (or is blank /
    still <answer>)"""
    raw = str(text or "").lower()
    if not raw.strip() or "<answer>" in raw:
        return []
    t = " " + re.sub(r"[^a-z0-9-]+", " ", raw) + " "
    return [kind for kind, words in GAME_WORDS if any(f" {w} " in t if len(w) <= 3 else w in t for w in words)]


def brief_view(facts, script_path=None, name=None):
    """how players see the model, from the brief: facts["brief"]["view"] (or facts["quality"]["brief"]["view"]) when
    the build parsed it; else the `- view:` line of <name>.brief.md beside the build script. -> text or None"""
    for holder in (facts or {}, (facts or {}).get("quality") or {}):
        b = holder.get("brief") if isinstance(holder, dict) else None
        if isinstance(b, dict) and str(b.get("view") or "").strip():
            return str(b["view"]).strip()
    if script_path and name:
        path = os.path.join(os.path.dirname(os.path.abspath(script_path)), f"{name}.brief.md")
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(r"\s*[-*]\s*view\s*:\s*(.+)", line, re.I)
                    if m and "<answer>" not in m.group(1):
                        return m.group(1).strip()
        except OSError:
            pass
    return None


def safe(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(name)).strip("_") or "region"


def prune(root, keep=KEEP_BUILDS, protect=()):
    """keep the `keep` newest build folders under root (by meta.json "at", else the folder's time) and every build
    in `protect`; remove the rest -> the removed build ids"""
    entries = []
    for b in os.listdir(root) if os.path.isdir(root) else []:
        d = os.path.join(root, b)
        if not os.path.isdir(d):
            continue
        try:
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
                at = json.load(fh).get("at") or ""
        except (OSError, ValueError):
            at = ""
        entries.append((at or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(d))), b))
    entries.sort(reverse=True)
    gone = []
    for i, (_, b) in enumerate(entries):
        if i >= keep and b not in protect:
            shutil.rmtree(os.path.join(root, b), ignore_errors=True)
            gone.append(b)
    return gone


def _protected(repo, name):
    out = set()
    for suffix in ("accepted", "judge"):
        try:
            with open(os.path.join(repo, "assets", "models", f"{name}.{suffix}.json"), encoding="utf-8") as fh:
                b = json.load(fh).get("build")
            if b:
                out.add(str(b))
        except (OSError, ValueError, AttributeError):
            pass
    return out


# ---------------------------------------------------------------------------------------------- Blender side
def _bounds(objs):
    from mathutils import Vector  # noqa: PLC0415

    cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return (Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs))),
            Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs))))


def frame(asset, objs):
    """this build's sticky frame (Blender space) for the six views and every region -> {"box": [lo, hi], "kept":
    bool, "regions": {name: [lo, hi]}}; decided once per build (the region close-ups render first) and written to
    build/judge/<name>/builds/frame.json"""
    if getattr(asset, "_judge_frame", None) is not None:
        return asset._judge_frame
    import rbx  # noqa: PLC0415 — (loaded: it is the module calling this)

    path = os.path.join(rbx.BUILD, "judge", asset.name, "builds", "frame.json")
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    lo, hi = _bounds(objs)
    box, kept = sticky_box(old.get("box"), tuple(lo), tuple(hi))
    regions = {}
    for name, rlo, rhi in getattr(asset, "_region_boxes", None) or []:
        if rlo is not None:
            regions[name], _ = sticky_box((old.get("regions") or {}).get(name), tuple(rlo), tuple(rhi))
    fr = {"box": box, "kept": kept, "regions": regions}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"box": box, "regions": regions, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, fh, indent=1)
    asset._judge_frame = fr
    return fr


def region_boxes(asset, objs):
    """[(region, lo, hi)] for the close-ups: each region's sticky box (None where the model has no part of it)"""
    from mathutils import Vector  # noqa: PLC0415

    fr = frame(asset, objs)
    out = []
    for name, lo, hi in asset._region_boxes:
        box = fr["regions"].get(name) if lo is not None else None
        out.append((name, Vector(box[0]), Vector(box[1])) if box else (name, None, None))
    return out


def _game_camera(kind, lo, hi):
    """(eye, look direction) in Roblox space for a game camera, from the frame box (Blender lo / hi)"""
    from mathutils import Vector  # noqa: PLC0415

    rlo = Vector((lo.x, lo.z, -hi.y))  # Blender (x, y, z) = Roblox (x, -z, y)
    rhi = Vector((hi.x, hi.z, -lo.y))
    c = (rlo + rhi) / 2
    length, height = rhi.z - rlo.z, rhi.y - rlo.y
    grip = Vector((c.x, rlo.y + 0.3 * height, rhi.z - 0.25 * length))  # a held thing: the hand a quarter from the back
    head = grip + Vector((-1.5, 1.5, 1.5))  # Roblox's first person eye, relative to the right hand's tool
    if kind == "first_person":
        pitch = math.radians(8)
        return head, Vector((0, -math.sin(pitch), -math.cos(pitch)))
    if kind == "third_person":
        eye = head + Vector((0, 3.0, 12.0))
        return eye, (head - eye).normalized()
    if kind == "top_down":
        eye = c + Vector((0, 28.0, 16.0))
        return eye, (c - eye).normalized()
    eye = Vector((c.x - 6.0, rlo.y + 4.5, c.z - 8.0))  # world: a standing player's eye, front-left
    return eye, (c - eye).normalized()


def _product(asset, objs, lo, hi):
    """the judge's light: Cycles under the product studio (steel lit like a product shot), denoised"""
    import rbx  # noqa: PLC0415

    sc = asset.scene
    asset._studio(objs, BG, box=(lo, hi), look="product")
    sc.render.engine = "CYCLES"
    rbx.cycles_device(sc)
    sc.cycles.samples = VIEW_SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.denoising_use_gpu = sc.cycles.device == "GPU"
    sc.render.film_transparent = False
    # (many stills of one unmoving model: the scene is sent to the renderer once, not once a still — render() turns
    # it off again when the last one is written)
    sc.render.use_persistent_data = os.environ.get("KIT_JUDGE_PERSISTENT", "1") != "0"
    st = sc.render.image_settings
    st.file_format, st.color_mode, st.compression = "PNG", "RGB", 90


def _shaded(asset, objs, clay=None):
    """a shape round's light: Workbench, the parts in their own colours under its studio light with cavity shading,
    on a transparent film (laid on GREY afterwards) — under a second a view, no bake needed.
    clay: one matte colour for everything instead (the blockout: proportions and form, nothing else)"""
    sc = asset.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = True
    sh = sc.display.shading
    sh.light, sh.show_cavity = "STUDIO", True
    sh.cavity_type = "BOTH"  # (creases darkened and edges lit, in the world and on screen: the forms read)
    sh.show_object_outline, sh.show_xray = False, False
    spec = {v["mat"].name: v["color"] for v in asset.mats.values()}
    for o in objs:
        for m in o.data.materials:
            if m and m.name in spec:  # (workbench reads diffuse_color, which nothing else sets)
                m.diffuse_color = (*spec[m.name], 1.0)
    sh.color_type = "MATERIAL"
    if clay is not None:
        sh.color_type, sh.single_color = "SINGLE", tuple(clay)
    st = sc.render.image_settings
    st.file_format, st.color_mode, st.compression = "PNG", "RGBA", 90


def _on_grey(arr):
    """an RGBA picture (float, top row first) laid on GREY -> opaque"""
    import numpy as np  # noqa: PLC0415

    a = arr[..., 3:4]
    out = arr.copy()
    out[..., :3] = arr[..., :3] * a + np.array(GREY, np.float32) * (1.0 - a)
    out[..., 3] = 1.0
    return out


def _resize(arr, w, h):
    """a (rows, columns, 4) picture resampled to h x w, bilinear (numpy: there is no PIL inside Blender's Python)"""
    import numpy as np  # noqa: PLC0415

    rows, cols = arr.shape[:2]
    if (rows, cols) == (h, w):
        return arr
    ys = np.clip((np.arange(h) + 0.5) * rows / h - 0.5, 0, rows - 1)
    xs = np.clip((np.arange(w) + 0.5) * cols / w - 0.5, 0, cols - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, rows - 1), np.minimum(x0 + 1, cols - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = arr[y0][:, x0] * (1 - fx) + arr[y0][:, x1] * fx
    bot = arr[y1][:, x0] * (1 - fx) + arr[y1][:, x1] * fx
    return (top * (1 - fy) + bot * fy).astype(np.float32)


def _shoot(asset, objs, fr, kinds, out, shaded=False, clay=None, prefix=""):
    """render the six views + the game cameras `kinds` from the frame into `out` -> (views, {camera: title}).
    shaded: a --geo build's views (Workbench, the parts' own colours, GEO_SIZE, no game camera); clay: in one
    matte colour instead; prefix: before each file's name (clay_front.png)"""
    import bpy  # noqa: PLC0415
    import rbx  # noqa: PLC0415
    from mathutils import Vector  # noqa: PLC0415

    sc = asset.scene
    lo, hi = Vector(fr["box"][0]), Vector(fr["box"][1])
    keep = set(objs)
    for o in sc.objects:
        if o.type == "MESH":
            o.hide_render = o not in keep
    if shaded:
        _shaded(asset, objs, clay=clay)
    else:
        _product(asset, objs, lo, hi)
    size = GEO_SIZE if shaded else view_size(asset.quality)
    cam = bpy.data.objects.new("JudgeCam", bpy.data.cameras.new("JudgeCam"))
    asset.collection.objects.link(cam)
    sc.camera = cam
    center, ext = (lo + hi) / 2, hi - lo
    big = max(ext.length, 0.01)
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]

    def shot(path):
        tmp = path[:-4] + ".tmp.png"
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        if shaded:  # (a transparent film: the view on the judge's grey)
            import rbx_precision  # noqa: PLC0415

            rbx_precision._save_pixels(_on_grey(rbx_precision._load_pixels(tmp)), tmp)
        rbx._replace(tmp, path)

    sc.render.resolution_x, sc.render.resolution_y = size
    aspect = size[0] / size[1]
    views = []
    for name, d, ortho in VIEWS:
        direction = (rbx.BL_FROM_RBX.to_3x3() @ Vector(d)).normalized()
        cam.data.sensor_fit = "AUTO"
        if ortho:
            # the frame's extent across this view (Blender: x = Roblox x, y = Roblox -z, z = Roblox y)
            axis = max(range(3), key=lambda i: abs(direction[i]))
            w, h = {0: (ext.y, ext.z), 1: (ext.x, ext.z), 2: (ext.x, ext.y)}[axis]
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = max(w, h * aspect) * 1.04
            cam.location = center + direction * (big * 2 + 5)
        else:
            cam.data.type = "PERSP"
            cam.data.lens = 50
            right = direction.cross(Vector((0, 0, 1)))
            right = right.normalized() if right.length > 1e-6 else Vector((1, 0, 0))
            up = right.cross(direction).normalized()
            tan_h = 18.0 / 50 * 0.92
            tan_v = tan_h / aspect
            need = max(max((p - center).dot(direction) + abs((p - center).dot(right)) / tan_h,
                           (p - center).dot(direction) + abs((p - center).dot(up)) / tan_v) for p in corners)
            cam.location = center + direction * max(need, 0.05)
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_start, cam.data.clip_end = 0.005, big * 40 + 100
        shot(os.path.join(out, f"{prefix}{name}.png"))
        views.append(name)
    # the game cameras the brief names (J5): what a player actually sees of it
    games = {}
    sc.render.resolution_x, sc.render.resolution_y = game_size(asset.quality)
    m3 = rbx.BL_FROM_RBX.to_3x3()
    for kind in [] if shaded else kinds:
        eye, look = _game_camera(kind, lo, hi)
        cam.data.type = "PERSP"
        cam.data.sensor_fit = "VERTICAL"
        cam.data.angle_y = math.radians(GAME_FOV)
        cam.location = m3 @ eye
        cam.rotation_euler = (m3 @ look).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_start, cam.data.clip_end = 0.02, 2000
        shot(os.path.join(out, f"game_{kind}.png"))
        games[kind] = GAME_TITLES[kind]
    bpy.data.objects.remove(cam)
    return views, games


def _points(objs):
    """every vertex of objs in world space -> (n, 3) float64"""
    import numpy as np  # noqa: PLC0415

    chunks = []
    for o in objs:
        n = len(o.data.vertices)
        if not n:
            continue
        co = np.empty(n * 3, np.float32)
        o.data.vertices.foreach_get("co", co)
        m = np.array(o.matrix_world, np.float64)
        chunks.append(co.reshape(n, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3])
    return np.concatenate(chunks) if chunks else np.zeros((0, 3))


def _view_camera(view, front, hr, shown):
    """the picture camera of a traced view for the parts it shows -> (dir, right, up, mirror, extents): a top view
    is laid the way its outline's proportions say (top_lies)"""
    import numpy as np  # noqa: PLC0415
    import rbx_project  # noqa: PLC0415

    pts = _points(shown)
    d, r, u, mirror = picture_camera(view, front)
    ext = rbx_project.extents(pts, (np.array(d), np.array(r), np.array(u)))
    if view == "top" and top_lies(hr, ext[1] - ext[0], ext[3] - ext[2]) == "down":
        d, r, u, mirror = picture_camera(view, front, lies="down")
        ext = rbx_project.extents(pts, (np.array(d), np.array(r), np.array(u)))
    return d, r, u, mirror, ext


def _crop(arr, box):
    """a picture's box (x0, y0, x1, y1; y down) on GREY: where the box runs off the picture, and behind a cut-out"""
    import numpy as np  # noqa: PLC0415

    x0, y0, x1, y1 = box
    h, w = arr.shape[:2]
    out = np.empty((y1 - y0, x1 - x0, 4), np.float32)
    out[...] = (*GREY, 1.0)
    sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = _on_grey(arr[sy0:sy1, sx0:sx1])
    return out


def _pair(ref, shot):
    """the reference crop and the model's crop as ONE picture -> (pixels, layout): the reference first (on the left;
    on top for a long low feature), resampled to the model crop's height (its width when stacked: the two crops
    frame the same box at one scale, so they come out the same size), PAIR_GAP white pixels between"""
    import numpy as np  # noqa: PLC0415

    h, w = shot.shape[:2]
    layout = pair_layout(w, h)
    if layout == "stack":
        ref = _resize(ref, w, max(1, int(round(ref.shape[0] * w / ref.shape[1]))))
        return np.concatenate([ref, np.ones((PAIR_GAP, w, 4), np.float32), shot], axis=0), layout
    ref = _resize(ref, max(1, int(round(ref.shape[1] * h / ref.shape[0]))), h)
    return np.concatenate([ref, np.ones((h, PAIR_GAP, 4), np.float32), shot], axis=1), layout


def _picture_file(repo, *names):
    """the first of `names` (a trace's source, a brief's picture) that is a file: under the repo (how every kit
    file names a picture), else as given -> its full path"""
    for n in names:
        if not n:
            continue
        for p in (os.path.join(repo, str(n)), str(n)):
            if os.path.isfile(p):
                return os.path.abspath(p)
    return None


def _feature_shots(asset, groups, features, traces, out, shaded=False):
    """one PAIR per hero feature that names a box in a traced picture: the picture's box beside the model's SAME box,
    seen from that picture's camera (the parts its trace ignores hidden, its pose applied), FEATURE_PX on its larger
    side. -> a row per feature: {rank, name, route, picture, box, file, layout, view, px} or {..., file: None, why}.
    groups: {mesh group: object}. shaded: a --geo build's (Workbench) instead of the judge's light."""
    import bpy  # noqa: PLC0415
    import rbx  # noqa: PLC0415
    import rbx_precision  # noqa: PLC0415
    from mathutils import Matrix, Vector  # noqa: PLC0415

    rows, placed = [], []
    for f in features or []:
        row = {"rank": f.get("rank"), "name": f.get("name"), "route": f.get("route"), "picture": f.get("picture"),
               "box": f.get("box")}
        fr = feature_frame(f, traces)
        # (the TRACE's own picture first: the box is placed by that picture's frame)
        path = None if "why" in fr else _picture_file(rbx.REPO, fr.get("picture"), f.get("picture"))
        if "why" in fr:
            row.update(file=None, why=fr["why"])
        elif path is None:
            row.update(file=None, why=f"{f.get('name')}: its picture {f.get('picture')} is not a file in this project")
        else:
            row.update(view=fr["view"], front=fr["front"])
            placed.append((len(rows), f, fr, path))
        rows.append(row)
    if not placed:
        return rows
    sc = asset.scene
    everything = list(groups.values())
    lo, hi = _bounds(everything)
    big = max((hi - lo).length, 0.01)
    if shaded:
        _shaded(asset, everything)
    else:
        fb = frame(asset, everything)["box"]  # (the six views' frame: the same softbox, the same light)
        _product(asset, everything, Vector(fb[0]), Vector(fb[1]))
    sc.render.resolution_percentage = 100
    cam = bpy.data.objects.new("FeatureCam", bpy.data.cameras.new("FeatureCam"))
    asset.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type, cam.data.sensor_fit = "ORTHO", "AUTO"
    pictures = {}
    by_view = {}
    for item in placed:
        by_view.setdefault((item[2]["view"], item[2]["front"]), []).append(item)
    try:
        for (view, front), items in by_view.items():
            opts = (getattr(asset, "ref_options", None) or {}).get(view) or {}
            ignored = set(opts.get("ignore") or ())
            shown = [o for g, o in groups.items() if g not in ignored]
            if not shown:
                for i, f, _fr, _p in items:
                    rows[i].update(file=None, why=f"{f.get('name')}: the {view} trace ignores every part of the model")
                continue
            posed = []
            try:
                posed = asset._pose_as_pictured(groups, opts.get("pose")) if opts.get("pose") else []
                if posed:
                    bpy.context.view_layer.update()
                keep = set(shown)
                for o in sc.objects:
                    if o.type == "MESH":
                        o.hide_render = o not in keep
                d, r, u, mirror, ext = _view_camera(view, front, items[0][2]["hr"], shown)
                dv, rv, uv = Vector(d), Vector(r), Vector(u)
                for i, f, fr, path in items:
                    try:  # (one close-up failing names itself: a build's verdict is never lost to a picture)
                        cr, cu, w, h = feature_window(fr["a"], fr["b"], fr["hr"], ext, mirror)
                        px = pane_size(w, h)
                        at = rv * cr + uv * cu + dv * (ext[5] + big + 5.0)
                        cam.matrix_world = Matrix(((r[0], u[0], d[0], at.x), (r[1], u[1], d[1], at.y),
                                                   (r[2], u[2], d[2], at.z), (0.0, 0.0, 0.0, 1.0)))
                        cam.data.ortho_scale = max(w, h)
                        cam.data.clip_start, cam.data.clip_end = 0.005, (ext[5] - ext[4]) + 2 * big + 20.0
                        sc.render.resolution_x, sc.render.resolution_y = px
                        tmp = os.path.join(out, f"_f{i}.tmp.png")
                        sc.render.filepath = tmp
                        bpy.ops.render.render(write_still=True)
                        shot = rbx_precision._load_pixels(tmp)
                        os.remove(tmp)
                        shot = _on_grey(shot) if shaded else shot.copy()
                        if mirror:
                            shot = shot[:, ::-1]
                        if path not in pictures:
                            pictures[path] = rbx_precision._load_pixels(path)
                        ref = _crop(pictures[path], picture_box(f["box"]))
                        pair, layout = _pair(ref, shot)
                        name = f"f_{int(f.get('rank') or i + 1)}_{safe(f.get('name'))}.png"
                        rbx_precision._save_pixels(pair, os.path.join(out, name))
                        rows[i].update(file=name, layout=layout, px=list(px),
                                       reference_px=[ref.shape[1], ref.shape[0]])
                    except Exception as e:  # noqa: BLE001
                        rows[i].update(file=None, why=f"{f.get('name')}: its close-up could not be made "
                                                      f"({type(e).__name__}: {str(e)[:120]})")
            finally:
                for o_, m_ in posed:
                    o_.matrix_world = m_
                if posed:
                    bpy.context.view_layer.update()
    finally:
        bpy.data.objects.remove(cam)
        own = set(everything)
        for o in sc.objects:  # (as the six views leave it: the model's own parts are what a render shows)
            if o.type == "MESH":
                o.hide_render = o not in own
    return rows


LAYOUT_NOTE = ("each f_<n>_<feature>.png: the REFERENCE's box first (left; on top when the feature is long and low), "
               "then the MODEL's same box from that picture's camera — look at every one, at its own size")


def _features(asset, groups, features, traces, out, reuse_ok, shaded=False):
    """the hero features' pairs in `out` (+ features.json) -> (rows, seconds spent). Kept when the build's views
    were kept and nothing the pairs are made from changed (features_key)."""
    import rbx  # noqa: PLC0415

    path = os.path.join(out, "features.json")
    import hashlib  # noqa: PLC0415

    seen = hashlib.sha1()  # (each feature's picture AS IT IS: a picture replaced at the same path is another pair)
    for f in features or []:
        fr = feature_frame(f, traces)
        pic = None if "why" in fr else _picture_file(rbx.REPO, fr.get("picture"), f.get("picture"))
        try:
            with open(pic, "rb") as fh:
                seen.update(hashlib.sha1(fh.read()).digest())
        except (OSError, TypeError):
            seen.update(b"-")
    # (and how each view is laid on the model: the parts its trace ignores, the pose it is pictured in)
    opts = getattr(asset, "ref_options", None) or {}
    seen.update(json.dumps({v: [sorted(o.get("ignore") or ()), o.get("pose") or {}] for v, o in sorted(opts.items())},
                           sort_keys=True, default=str).encode())
    key = features_key(features, traces) + "-" + seen.hexdigest()[:8]
    if not features:
        for f in os.listdir(out):
            if f == "features.json" or re.match(r"f_\d+_.*\.png$", f):
                os.remove(os.path.join(out, f))
        return [], 0.0
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = None
    if (reuse_ok and isinstance(old, dict) and old.get("key") == key
            and all(os.path.isfile(os.path.join(out, r["file"])) for r in old.get("features") or [] if r.get("file"))):
        return old.get("features") or [], 0.0
    for f in os.listdir(out):
        if re.match(r"f_\d+_.*\.png$", f):
            os.remove(os.path.join(out, f))
    t0 = time.time()
    rows = _feature_shots(asset, groups, features, traces, out, shaded=shaded)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"key": key, "how_to_read": LAYOUT_NOTE, "features": rows}, fh, indent=1)
    return rows, round(time.time() - t0, 1)


def _feature_facts(rows):
    """what the build says about its feature close-ups: how many, and each gap in the owner's words"""
    made = [r for r in rows if r.get("file")]
    gaps = [r["why"] for r in rows if not r.get("file") and r.get("why")]
    return {"features": len(made), **({"feature_gaps": gaps} if gaps else {})}


def say(result):
    """one line for a build's summary: where its pictures are and what must be looked at (render / geo's result)"""
    if not result:
        return ""
    w, h = result.get("view_size") or VIEW_SIZE
    text = f"LOOK: {result['folder']}/ — {result.get('views', 0)} views at {w} x {h}"
    if result.get("features"):
        text += (f" + {result['features']} hero feature pair(s) f_*.png (the reference's box, then the model's same "
                 "box): open every one")
    gaps = result.get("feature_gaps") or []
    if gaps:
        text += (f"; {len(gaps)} hero feature(s) have NO close-up — " + "; ".join(gaps[:2])
                 + (f" (+{len(gaps) - 2} more: features.json)" if len(gaps) > 2 else ""))
    return text


def _groups(objs, groups):
    return dict(groups) if groups else {o.name: o for o in objs}


def render(asset, objs, manifest, facts, features=None, traces=None, groups=None):
    """the six views (+ game cameras + a pair per hero feature) of this build -> build/judge/<name>/builds/<build
    id>/ ; -> what was kept. The same build again (an unchanged model: the same meshes and maps, so the same build
    id) from the same frame at the same size keeps the views it has: a cached rebuild costs nothing here.
    features / traces: the brief's hero features and the traced views (rbx_plan); groups: {mesh group: object}."""
    import rbx  # noqa: PLC0415

    build = manifest.get("build_id")
    if not build:
        return None
    root = os.path.join(rbx.BUILD, "judge", asset.name, "builds")
    out = os.path.join(root, build)
    fr = frame(asset, objs)
    said = brief_view(facts, getattr(asset, "script_path", None), getattr(asset, "optimize_of", None) or asset.name)
    kinds = game_cameras(said) if said else []
    size = list(view_size(asset.quality))
    try:
        with open(os.path.join(out, "meta.json"), encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = None
    reuse = views_kept(old, fr["box"], size, kinds, set(os.listdir(out)) if os.path.isdir(out) else set())
    t0 = time.time()
    try:
        if reuse:
            views, games = list(old.get("views") or []), dict(old.get("game") or {})
        else:
            if os.path.isdir(out):  # (nothing stale left behind)
                shutil.rmtree(out, ignore_errors=True)
            os.makedirs(out, exist_ok=True)
            views, games = _shoot(asset, objs, fr, kinds, out)
        view_seconds = round(time.time() - t0, 1)
        rows, feature_seconds = _features(asset, _groups(objs, groups), features, traces, out, reuse)
    finally:
        asset.scene.render.use_persistent_data = False  # (_product: kept for these stills only)
    regions = {}  # (the close-ups are rendered by every build: copied fresh)
    for name, rel in (manifest.get("regions") or {}).items():
        src = os.path.join(rbx.REPO, rel) if rel else None
        if src and os.path.isfile(src):
            shutil.copyfile(src, os.path.join(out, f"r_{safe(name)}.png"))
            regions[name] = f"r_{safe(name)}.png"
        else:
            regions[name] = None
    q = (facts or {}).get("quality") or {}
    meta = {"asset": asset.name, "build": build, "iteration": q.get("iteration"), "score": q.get("score"),
            "tier": asset.quality, "script_sha": getattr(asset, "script_sha", None),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"), "frame": fr["box"], "frame_kept": fr["kept"],
            "view_size": size, "views": views, "game": games, "brief_view": said, "regions": regions,
            "features": {r["name"]: r.get("file") for r in rows}}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    gone = prune(root, KEEP_BUILDS, _protected(rbx.REPO, asset.name) | {build})
    return {"folder": os.path.relpath(out, rbx.REPO).replace("\\", "/"), "views": len(views), "view_size": size,
            "game": sorted(games), "regions": sum(1 for v in regions.values() if v), "frame_kept": fr["kept"],
            **_feature_facts(rows), "seconds": {"views": view_seconds, "features": feature_seconds},
            **({"reused": True} if reuse else {}), **({"pruned": len(gone)} if gone else {})}


def _clay_refs(asset, groups, traces, out):
    """the model in clay from each traced picture's own camera, framed on the picture's object box (+ CLAY_MARGIN) at
    the picture's scale — what the blockout sheet lays beside the reference -> {view: {"file", "px", "front"}}"""
    import bpy  # noqa: PLC0415
    import rbx  # noqa: PLC0415
    import rbx_precision  # noqa: PLC0415
    from mathutils import Matrix, Vector  # noqa: PLC0415

    sc = asset.scene
    everything = list(groups.values())
    lo, hi = _bounds(everything)
    big = max((hi - lo).length, 0.01)
    _shaded(asset, everything, clay=CLAY)
    sc.render.resolution_percentage = 100
    cam = bpy.data.objects.new("ClayCam", bpy.data.cameras.new("ClayCam"))
    asset.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type, cam.data.sensor_fit = "ORTHO", "AUTO"
    made = {}
    try:
        for view, t in sorted((traces or {}).items()):
            fr = t.get("frame") if isinstance(t, dict) else None
            if not isinstance(fr, dict) or not {"x0", "y1", "length_px"} <= set(fr):
                continue  # (a rotated / straightened trace has no plain frame: nothing to lay the model on)
            opts = (getattr(asset, "ref_options", None) or {}).get(view) or {}
            shown = [o for g, o in groups.items() if g not in set(opts.get("ignore") or ())]
            if not shown:
                continue
            front = "left" if str(t.get("front", "right")).lower() == "left" else "right"
            posed = []
            try:
                posed = asset._pose_as_pictured(groups, opts.get("pose")) if opts.get("pose") else []
                if posed:
                    bpy.context.view_layer.update()
                keep = set(shown)
                for o in sc.objects:
                    if o.type == "MESH":
                        o.hide_render = o not in keep
                hr = max(float(t.get("height_ratio") or 0.3), 1e-6)
                d, r, u, mirror, ext = _view_camera(view, front, hr, shown)
                cr, cu, w, h = feature_window([0.0, 1.0], [0.0, 1.0], hr, ext, mirror, margin=CLAY_MARGIN)
                px = pane_size(w, h, GEO_SIZE[0])
                at = Vector(r) * cr + Vector(u) * cu + Vector(d) * (ext[5] + big + 5.0)
                cam.matrix_world = Matrix(((r[0], u[0], d[0], at.x), (r[1], u[1], d[1], at.y),
                                           (r[2], u[2], d[2], at.z), (0.0, 0.0, 0.0, 1.0)))
                cam.data.ortho_scale = max(w, h)
                cam.data.clip_start, cam.data.clip_end = 0.005, (ext[5] - ext[4]) + 2 * big + 20.0
                sc.render.resolution_x, sc.render.resolution_y = px
                name = f"clay_ref_{safe(view)}.png"
                tmp = os.path.join(out, name[:-4] + ".tmp.png")
                sc.render.filepath = tmp
                bpy.ops.render.render(write_still=True)
                shot = _on_grey(rbx_precision._load_pixels(tmp))
                rbx_precision._save_pixels(shot[:, ::-1] if mirror else shot, tmp)
                rbx._replace(tmp, os.path.join(out, name))
                made[view] = {"file": name, "px": list(px), "front": front}
            finally:
                for o_, m_ in posed:
                    o_.matrix_world = m_
                if posed:
                    bpy.context.view_layer.update()
    finally:
        bpy.data.objects.remove(cam)
        for o in sc.objects:
            if o.type == "MESH":
                o.hide_render = o not in set(everything)
    return made


def _clay_scale(asset, objs, out):
    """the model in clay beside a plain R6 character (5 studs tall), three-quarter -> the file name, or None"""
    import bpy  # noqa: PLC0415
    import rbx  # noqa: PLC0415
    import rbx_precision  # noqa: PLC0415
    from mathutils import Vector  # noqa: PLC0415

    sc = asset.scene
    lo, hi = _bounds(objs)
    r6 = asset._r6(lo, hi)
    was = [(o, tuple(o.color)) for o in objs]
    cam = None
    try:
        both = list(objs) + list(r6)
        for o in sc.objects:
            if o.type == "MESH":
                o.hide_render = o not in set(both)
        _shaded(asset, objs, clay=CLAY)
        sh = sc.display.shading
        sh.color_type = "OBJECT"  # (the figure in its own tone: what is the model and what is the scale reads at once)
        for o in objs:
            o.color = (*CLAY, 1.0)
        for o in r6:
            o.color = (*R6_TONE, 1.0)
        blo, bhi = _bounds(both)
        center, ext = (blo + bhi) / 2, bhi - blo
        corners = [Vector((x, y, z)) for x in (blo.x, bhi.x) for y in (blo.y, bhi.y) for z in (blo.z, bhi.z)]
        cam = bpy.data.objects.new("ScaleCam", bpy.data.cameras.new("ScaleCam"))
        asset.collection.objects.link(cam)
        sc.camera = cam
        # (from the model's side: _r6 stands the figure at its +x, so from -x the model is never behind it)
        direction = (rbx.BL_FROM_RBX.to_3x3() @ Vector((-0.75, 0.35, -0.6))).normalized()
        cam.data.type, cam.data.lens, cam.data.sensor_fit = "PERSP", 50, "AUTO"
        aspect = GEO_SIZE[0] / GEO_SIZE[1]
        right = direction.cross(Vector((0, 0, 1))).normalized()
        up = right.cross(direction).normalized()
        tan_h = 18.0 / 50 * 0.9
        need = max(max((p - center).dot(direction) + abs((p - center).dot(right)) / tan_h,
                       (p - center).dot(direction) + abs((p - center).dot(up)) / (tan_h / aspect)) for p in corners)
        cam.location = center + direction * max(need, 0.05)
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_start, cam.data.clip_end = 0.005, max(ext.length, 0.01) * 40 + 100
        sc.render.resolution_x, sc.render.resolution_y = GEO_SIZE
        tmp = os.path.join(out, "clay_scale.tmp.png")
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        rbx_precision._save_pixels(_on_grey(rbx_precision._load_pixels(tmp)), tmp)
        rbx._replace(tmp, os.path.join(out, "clay_scale.png"))
        return "clay_scale.png"
    finally:
        if cam is not None:
            bpy.data.objects.remove(cam)
        for o, colour in was:  # (the parts' own object colour back: nothing of the scale view stays on the model)
            o.color = colour
        for o in r6:
            bpy.data.objects.remove(o)
        for o in sc.objects:
            if o.type == "MESH":
                o.hide_render = o not in set(objs)


def geo(asset, objs, features=None, traces=None, groups=None, clay=False, extra=None):
    """a --geo build's pictures (a shape round: no bake, no export) -> build/judge/<name>/geo/ : the six views in the
    parts' own colours (Workbench, GEO_SIZE) and a pair per hero feature, replaced by every geo build — so a shape
    round is LOOKED AT, not only measured. -> what was written.
    clay (kit blockout): also the six views in ONE matte colour (clay_<view>.png: form with no colour to flatter
    it), the model from each traced picture's own camera at the picture's scale (clay_ref_<view>.png) and beside an
    R6 character (clay_scale.png). extra: facts kept in meta.json for the blockout sheet (the views' overlaps)."""
    import rbx  # noqa: PLC0415

    out = os.path.join(rbx.BUILD, "judge", asset.name, "geo")
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    fr = frame(asset, objs)
    t0 = time.time()
    views, _ = _shoot(asset, objs, fr, [], out, shaded=True)
    view_seconds = round(time.time() - t0, 1)
    rows, feature_seconds = _features(asset, _groups(objs, groups), features, traces, out, False, shaded=True)
    lo, hi = _bounds(objs)
    meta = {"asset": asset.name, "mode": "geo", "tier": asset.quality, "script_sha": getattr(asset, "script_sha", None),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"), "frame": fr["box"], "frame_kept": fr["kept"],
            "view_size": list(GEO_SIZE), "views": views, "features": {r["name"]: r.get("file") for r in rows},
            # (Roblox studs: x across, y up, z along — Blender's x, z, y)
            "size": [round(hi.x - lo.x, 4), round(hi.z - lo.z, 4), round(hi.y - lo.y, 4)], **(extra or {})}
    clay_seconds = 0.0
    if clay:
        t1 = time.time()
        clay_views, _ = _shoot(asset, objs, fr, [], out, shaded=True, clay=CLAY, prefix="clay_")
        meta["clay"] = {"views": [f"clay_{v}.png" for v in clay_views],
                        "refs": _clay_refs(asset, _groups(objs, groups), traces, out),
                        "scale": _clay_scale(asset, objs, out)}
        clay_seconds = round(time.time() - t1, 1)
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return {"folder": os.path.relpath(out, rbx.REPO).replace("\\", "/"), "views": len(views),
            "view_size": list(GEO_SIZE), **_feature_facts(rows), **({"clay": len(meta["clay"]["views"])} if clay else {}),
            "seconds": {"views": view_seconds, "features": feature_seconds, **({"clay": clay_seconds} if clay else {})}}
