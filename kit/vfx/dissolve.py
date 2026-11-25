"""dissolve.py - a DISSOLVE THE GAME SHOWS: a texture breaking up over the cells of a sheet.

    lune run kit vfx dissolve <key> --from <texture key | plain> [--cells 16] [--cell 256] [--pattern patches|dither]
                              [--scale 5] [--soft 0.08] [--edge 0.06 --edge-color r,g,b --edge-gain 1.6]
                              [--density 0.35] [--curve 1] [--seed 7] [--dot 4]

Why: a mesh layer's `erode` (and its edge fades) write per-vertex alpha, which Roblox IGNORES on a runtime mesh
(measured in Studio 2026-10-16, kit/knowledge/vault/vfx/refs/engine-facts.md): what dissolves in the browser player
pops off in the game. What the engine does show on a mesh is a SurfaceAppearance's texture alpha (a layer's
`surface`) and a sheet's cells stepped on the mesh (its `flipbook`). So the dissolve is baked INTO a sheet: cell 0 is
the texture whole, the last cell is empty, and in between it breaks up patch by patch through a pattern, a hot edge
along the front if asked. The layer plays it with

    "texture": "<key>", "surface": 1, "flipbook": {"layout": "4x4", "mode": "OneShot", "over": [0.6, 1]}

("over": the part of the layer's life the cells play in - whole before it, gone after it). A sprite plays the same
sheet as an ordinary OneShot flipbook.

  --from      a built FX texture (an "engine": "fx" spec; build/textures/<key>.png, its first cell if it is a
              sheet), or `plain`: an opaque square for a shell that has no texture - white, or --tint r,g,b (whether
              the game tints a white sheet by the layer's colour is NOT measured: bake the colour in to be sure)
  --pattern   patches = smooth noise that tiles (a shell whose texture wraps shows no seam), thin parts going first
              dither  = an ordered 8x8 screen (dithered transparency: a hard, even, printed fade), --dot px a dot
  --soft      the width of the front, as a share of the pattern (0 = a hard cut-out: alpha clipping whose
              threshold moves over the layer's life)
  --edge      a burning rim along the front (needs --edge-color), as a share of the pattern
  --density   how much the texture's own alpha steers the pattern (thin parts go first), 0-1
  --curve     above 1 the break-up starts slowly and ends fast; below 1 the other way

The pattern is levelled so that every cell removes an even share: no cell pops, none stalls. Its own checks (a sheet
that fails one writes NO spec and NO frames): source (there is something to dissolve), whole (cell 0 is the texture),
clears (the last cell is empty), monotone (nothing comes back), steps (every cell removes something, none a jump),
packs (every cell changes enough for the kit's packer to take the sheet), breaks (the middle cell is cut into pieces,
not faded evenly), tiles (a texture that wraps still wraps in every cell).
Writes build/fxlab/<key>/NNN.npy + assets/textures/<key>.json ("recipe": "dissolve", with the texture it came from
and its options) and the LOOK strip build/vfx/dissolve/<key>_strip.png: OPEN it. `lune run kit vfx` bakes it again
when its spec or its source texture changed, then packs, checks and registers it - in its OWN step, after the fx
textures of that run are packed (so it is always baked from the source as it is now).

    python kit/vfx/dissolve.py --specs <dir> --out <frames dir> --textures-dir <built textures> [--pack <packer>]
                                                   (the build step: every recipe "dissolve" spec that is stale is
                                                   baked; --pack: all of them are then packed and registered)
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import hashlib
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

SPECS = os.path.join("assets", "textures")
FRAMES = os.path.join("build", "fxlab")
BUILT = os.path.join("build", "textures")
LOOK = os.path.join("build", "vfx", "dissolve")
GRIDS = {4: 2, 16: 4, 64: 8}
PATTERNS = ("patches", "dither")
SOURCE = 0.005   # a source covering less of its cell than this has nothing to dissolve
WHOLE = 0.01     # cell 0 may differ from the source by this much alpha on average
CLEAR = 0.02     # the last cell's strongest alpha
BACK = 0.02      # the most alpha a pixel may gain from one cell to the next
JUMP = 3.0       # a cell may remove at most this many even shares
PACK = 0.001     # the least mean alpha a cell must change by (the packer refuses a sheet below 0.0008: "not moving")
FADE = 0.45      # at the middle cell, the share of the covered pixels that may be half-transparent
BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                  [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                  [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], dtype=np.float64)
DEFAULTS = {"cells": 16, "cell": 256, "pattern": "patches", "scale": 5.0, "soft": 0.08, "edge": 0.0, "edge_color": None,
            "edge_gain": 1.6, "density": 0.35, "curve": 1.0, "seed": 7, "dot": 4, "tint": None}


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status in ("pass", "warn") else 1


def periodic_noise(n, scale, seed):
    """smooth noise that TILES in both directions, about `scale` patches across (a low-pass of white noise in
    frequency space: every wave fits the square a whole number of times)"""
    rng = np.random.default_rng(seed)
    fy, fx = np.fft.fftfreq(n)[:, None] * n, np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    amp = np.exp(-(f / max(float(scale), 0.5)) ** 2)
    amp[0, 0] = 0
    v = np.real(np.fft.ifft2((rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) * amp))
    return (v - v.min()) / max(float(v.max() - v.min()), 1e-9)


def level(field, where):
    """the field with its values spread EVENLY over 0-1 on the pixels `where` (each pixel's rank among them): a
    threshold that rises evenly then removes an even share of them every step. Pixels outside keep their value"""
    flat = field[where]
    if flat.size == 0:
        return field.copy()
    order = np.argsort(flat, kind="stable")
    rank = np.empty(flat.size, dtype=np.float64)
    rank[order] = (np.arange(flat.size) + 0.5) / flat.size
    levelled = field.astype(np.float64).copy()
    levelled[where] = rank
    return levelled


def pattern_field(alpha, o):
    """0-1 per pixel: WHEN the pixel goes (low = first). patches: tiling noise steered by the texture's alpha;
    dither: an ordered screen, the same everywhere"""
    n = alpha.shape[0]
    covered = alpha > 0.02
    if o["pattern"] == "dither":
        dot = max(1, int(o["dot"]))
        yy, xx = np.mgrid[0:n, 0:n]
        return (BAYER[(yy // dot) % 8, (xx // dot) % 8] + 0.5) / 64.0
    noise = periodic_noise(n, o["scale"], int(o["seed"]))
    d = min(max(float(o["density"]), 0.0), 1.0)
    return level(noise * (1 - d) + np.clip(alpha, 0, 1) * d, covered)


def cells_of(src, o, field=None):
    """the source (straight RGBA, 0-1, square) breaking up over o["cells"] cells -> [cell] (straight RGBA)"""
    n = int(o["cells"])
    alpha = src[..., 3]
    field = pattern_field(alpha, o) if field is None else field
    soft = max(float(o["soft"]), 0.0)
    edge = max(float(o["edge"]), 0.0) if o.get("edge_color") is not None else 0.0
    cells = []
    for k in range(n):
        t = (k / float(n - 1)) ** float(o["curve"])
        if soft > 0:
            # the front is `soft` wide and a pixel is half gone at its middle: THAT line advances evenly from 0 to 1,
            # so every cell removes its share of the area however wide the front is and however many cells there
            # are (the threshold used to start a whole front early: with 64 cells, or a wide front, the first cells
            # removed nothing). The last cell is empty by rule: it takes the front's faint tail with it
            th = t - soft * 0.5
            keep = np.clip((field - th) / soft, 0, 1)
        else:
            keep = (field > (t * 1.0001 - 1e-6)).astype(np.float64) if k < n - 1 else np.zeros_like(field)
        if k == 0:
            keep = np.ones_like(field)
        if k == n - 1:
            keep = np.zeros_like(field)
        cell = src.copy()
        cell[..., 3] = alpha * keep
        if edge > 0 and 0 < k < n - 1:
            th_edge = th if soft > 0 else t
            band = np.clip(1 - np.abs(field - th_edge - edge * 0.5) / edge, 0, 1) * (keep > 0) * (alpha > 0.02)
            colour = np.asarray(o["edge_color"], dtype=np.float64)
            cell[..., :3] = np.clip(cell[..., :3] * (1 - band[..., None]) + colour[None, None, :] * band[..., None] * float(o["edge_gain"]), 0, 1)
        cells.append(cell)
    return cells


def wraps(alpha):
    """does this picture's alpha run off both its left and its right edge (a texture meant to tile along U)?"""
    return float(alpha[:, 0].mean()) > 0.02 and float(alpha[:, -1].mean()) > 0.02


def check(src, cells, o, field=None):
    """the sheet's own checks -> [{name, ok, value, limit, fix}]. `field`: the pattern the cells were cut by (the
    tiling check reads it; without it the cells themselves are read)"""
    alpha = src[..., 3]
    total = float(alpha.sum())
    n = len(cells)
    checks = []

    def add(name, ok, value, limit, fix):
        checks.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    cover = float((alpha > 0.02).mean())
    add("source", cover >= SOURCE, round(cover, 4), f">= {SOURCE} of the cell covered", "the source has nothing to dissolve: name a built texture, or `plain`")
    if total <= 0:
        return checks
    whole = float(np.abs(cells[0][..., 3] - alpha).mean())
    add("whole", whole <= WHOLE, round(whole, 4), f"<= {WHOLE}", "cell 0 must be the texture as it is: the layer shows it until the break-up begins")
    clear = float(cells[-1][..., 3].max())
    add("clears", clear <= CLEAR, round(clear, 4), f"<= {CLEAR}", "the last cell must be empty: the layer ends on it, anything left pops off")
    back = max(float((cells[k + 1][..., 3] - cells[k][..., 3]).max()) for k in range(n - 1))
    add("monotone", back <= BACK, round(back, 4), f"<= {BACK}", "a pixel that has gone must stay gone")
    # how much of the texture's AREA each cell still shows (a pixel counts while it keeps more than half its alpha):
    # area is what the eye follows; the thin parts that go first weigh little
    held = alpha > 0.02
    share = [float(((c[..., 3] / np.maximum(alpha, 1e-6))[held] > 0.5).mean()) if held.any() else 0.0 for c in cells]
    steps = [share[k] - share[k + 1] for k in range(n - 1)]
    even = 1.0 / (n - 1)
    add("steps", min(steps) > 1e-4 and max(steps) <= JUMP * even, [round(min(steps), 4), round(max(steps), 4)],
        f"every cell removes more than 0 and at most {JUMP:g} even shares ({JUMP * even:.3f})",
        "a cell that removes nothing is a held frame, one that removes too much is a pop: bring --curve nearer 1 (a front wider than the pattern, --soft near 1, is a fade: lower it)")
    change = min(float(np.abs(cells[k + 1][..., 3] - cells[k][..., 3]).mean()) for k in range(n - 1))
    add("packs", change >= PACK, round(change, 5), f">= {PACK} mean alpha changed by every cell (the packer refuses a sheet whose frames barely differ)",
        "the texture covers too little of its cell for this many cells: fewer --cells, or a source that fills its cell")
    mid = cells[n // 2][..., 3]
    covered = alpha > 0.1
    ratio = mid[covered] / alpha[covered]
    half = float(((ratio > 0.15) & (ratio < 0.85)).mean()) if covered.any() else 0.0
    add("breaks", half <= FADE, round(half, 3), f"<= {FADE} of the covered pixels half-transparent at the middle cell",
        "that is an even fade, not a break-up: lower --soft")
    if wraps(alpha):
        if o["pattern"] == "dither":
            # an ordered screen tiles exactly when a whole number of its 8-dot squares fits the cell
            period = 8 * max(1, int(o["dot"]))
            add("tiles", src.shape[1] % period == 0, [src.shape[1], period], "the cell a whole number of screens wide (8 dots each)",
                "the texture wraps and the screen does not fit the cell: --dot 1, 2, 4, 8 or 16")
        else:
            # the PATTERN must wrap: its step across the seam (the last column to the first) against its step between
            # two neighbouring columns, on average. The pattern is smooth, so this holds whatever the front's width
            # (read off the cells, a hard cut steps as hard inside as at its seam and a fair check is not possible)
            rows = [field] if field is not None else [c[..., 3] for c in cells]
            worst, at = 0.0, 0.0
            for a in rows:
                seam = float(np.abs(a[:, 0] - a[:, -1]).mean())
                inside = float(np.abs(a[:, 1:] - a[:, :-1]).mean())
                if seam - 2 * inside > worst:
                    worst, at = seam - 2 * inside, seam
            add("tiles", worst <= 0.03, round(at, 3), "the pattern's step across the seam <= twice its step between neighbouring columns + 0.03",
                "the texture wraps and the pattern shows a seam: lower --density (the noise itself tiles)")
    return checks


def premultiplied(cell):
    c = cell.astype(np.float64).copy()
    c[..., :3] *= c[..., 3:]
    return c


def source_id(path):
    """what the cells were baked from: the source picture's bytes ("plain" has none)"""
    if path is None:
        return "plain"
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def is_key(key):
    return isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", key) is not None and ".." not in key


def load_source(key, built, specs, cell, tint=None):
    """(straight RGBA 0-1 at cell x cell, the file it came from or None for plain); raises FileNotFoundError.
    A source is an FX texture (the kit packs those before it bakes a dissolve) or plain"""
    if key == "plain":
        px = np.ones((cell, cell, 4), dtype=np.float64)
        if tint is not None:
            px[..., :3] = np.asarray(tint, dtype=np.float64)[None, None, :]
        return px, None
    if not is_key(key):
        raise ValueError(f'"{key}" is not a texture key')
    spec_path = os.path.join(specs, f"{key}.json")
    if os.path.isfile(spec_path):
        try:
            its = json.load(open(spec_path, encoding="utf-8"))
        except (OSError, ValueError):
            its = None
        if isinstance(its, dict) and its.get("engine") != "fx":
            raise ValueError(f'"{key}" is not an fx texture ("engine": "{its.get("engine")}"): a dissolve is baked from an fx texture or from `plain`')
        if isinstance(its, dict) and its.get("recipe") == "dissolve":
            raise ValueError(f'"{key}" is itself a dissolve sheet: bake from the texture it came from')
    path = os.path.join(built, f"{key}.png")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    img = Image.open(path).convert("RGBA")
    grid = 1
    if os.path.isfile(spec_path):
        try:
            g = json.load(open(spec_path, encoding="utf-8")).get("grid", 1)
        except (OSError, ValueError, AttributeError):
            g = 1
        grid = g if isinstance(g, int) and g >= 1 else (g if isinstance(g, list) and len(g) == 2 else 1)
    cols, rows = (grid, grid) if isinstance(grid, int) else (max(1, int(grid[0])), max(1, int(grid[1])))
    if cols > 1 or rows > 1:
        img = img.crop((0, 0, img.width // cols, img.height // rows))
    return np.asarray(img.resize((cell, cell), Image.LANCZOS), dtype=np.float64) / 255.0, path


def checked(block):
    """a spec's "dissolve" block (or the command's options) as options that can be baked; raises ValueError"""
    if not isinstance(block, dict):
        raise ValueError("it is not a table")
    o = dict(DEFAULTS)
    for k, v in block.items():
        if k in o:
            o[k] = v
    o["cells"], o["cell"], o["seed"], o["dot"] = int(o["cells"]), int(o["cell"]), int(o["seed"]), int(o["dot"])
    for k in ("scale", "soft", "edge", "edge_gain", "density", "curve"):
        o[k] = float(o[k])
        if not math.isfinite(o[k]):
            raise ValueError(f"{k} is not a number")
    if o["cells"] not in GRIDS:
        raise ValueError("cells is 4, 16 or 64 (a 2x2, 4x4 or 8x8 sheet: what a mesh's flipbook plays)")
    if o["cell"] not in (64, 128, 256, 512) or o["cell"] * GRIDS[o["cells"]] > 1024:
        raise ValueError("cell is 64, 128, 256 or 512 and the sheet at most 1024 px (16 cells of 256, 64 of 128)")
    if o["pattern"] not in PATTERNS:
        raise ValueError("pattern is " + " or ".join(PATTERNS))
    if not (0 <= o["soft"] <= 1 and 0 <= o["edge"] <= 0.5 and 0 <= o["density"] <= 1 and 0.25 <= o["curve"] <= 4 and 0.5 <= o["scale"] <= 64 and 1 <= o["dot"] <= 64):
        raise ValueError("soft 0-1, edge 0-0.5, density 0-1, curve 0.25-4, scale 0.5-64, dot 1-64")
    if o["edge_color"] is not None:
        c = o["edge_color"]
        if not (isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 255 for x in c)):
            raise ValueError("edge_color is three numbers, 0-255 (or 0-1)")
        o["edge_color"] = [float(x) / 255.0 for x in c] if max(c) > 1 else [float(x) for x in c]
    if o["edge"] > 0 and o["edge_color"] is None:
        raise ValueError("a burning edge needs its colour: --edge-color r,g,b")
    if o["tint"] is not None:
        c = o["tint"]
        if not (isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 255 for x in c)):
            raise ValueError("tint is three numbers, 0-255 (or 0-1)")
        o["tint"] = [float(x) / 255.0 for x in c] if max(c) > 1 else [float(x) for x in c]
    return o


def settings(o):
    """the options as a spec keeps them"""
    keep = {k: o[k] for k in ("pattern", "cells", "cell", "soft", "density", "curve", "seed")}
    if o["pattern"] == "patches":
        keep["scale"] = o["scale"]
    else:
        keep["dot"] = o["dot"]
    if o["edge"] > 0 and o["edge_color"] is not None:
        keep.update(edge=o["edge"], edge_color=[round(c * 255) for c in o["edge_color"]], edge_gain=o["edge_gain"])
    if o.get("tint") is not None:
        keep["tint"] = [round(c * 255) for c in o["tint"]]
    return keep


def write_frames(frames_dir, key, cells, spec_path, src_id):
    fdir = os.path.join(frames_dir, key)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    for i, c in enumerate(cells):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), premultiplied(c).astype(np.float16))
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(cells), "spec_mtime": os.path.getmtime(spec_path), "engine": "dissolve", "source": src_id}, fh)


def strip(cells, path, tile=200):
    """the LOOK picture: every cell over a dark ground (top) and a light one (bottom), in order"""
    per_row = min(len(cells), 8)
    rows = int(math.ceil(len(cells) / float(per_row)))
    head = 20
    page = Image.new("RGB", (per_row * (tile + 6) + 6, rows * (2 * tile + head + 10) + 6), (20, 20, 24))
    pen = ImageDraw.Draw(page)
    for i, c in enumerate(cells):
        r, col = divmod(i, per_row)
        x, y = 6 + col * (tile + 6), 6 + r * (2 * tile + head + 10)
        pen.text((x + 2, y + 3), f"cell {i}", fill=(225, 225, 225))
        px = np.asarray(Image.fromarray((np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").resize((tile, tile), Image.LANCZOS), dtype=np.float64) / 255.0
        for k, ground in enumerate((0.10, 0.82)):
            over = ground * (1 - px[..., 3:]) + px[..., :3] * px[..., 3:]
            page.paste(Image.fromarray((np.clip(over, 0, 1) * 255 + 0.5).astype(np.uint8)), (x, y + head + k * (tile + 4)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.save(path)


def bake(key, source, o, built, specs, frames_dir, look_dir=None, write_spec=True):
    """one sheet -> (status, summary, next_action, extra). Nothing is written unless every check passes"""
    if o.get("tint") is not None and source != "plain":
        return ("fail", f"dissolve {key}: --tint colours a `plain` sheet; {source} has its own colours", "drop --tint, or bake --from plain", {})
    try:
        src, src_path = load_source(source, built, specs, o["cell"], o.get("tint"))
    except FileNotFoundError as e:
        return ("fail", f"dissolve {key}: no built texture {str(e).replace(os.sep, '/')}",
                "build the source texture first (lune run kit vfx), or name `plain` for a shell with no texture", {})
    field = pattern_field(src[..., 3], o)
    cells = cells_of(src, o, field)
    checks = check(src, cells, o, field)
    failed = [c for c in checks if not c["ok"]]
    look = None
    if look_dir:
        look = os.path.join(look_dir, f"{key}_strip.png")
        strip(cells, look)
    extra = {"checks": checks, "look": look.replace(os.sep, "/") if look else None}
    if failed:
        said = "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']}): {c['fix']}" for c in failed)
        had = os.path.isfile(os.path.join(specs, f"{key}.json"))
        return ("fail", f"dissolve {key}: {said}" + (" - the sheet of that name stays as it was" if had else " - nothing written"),
                failed[0]["fix"], extra)
    grid = GRIDS[o["cells"]]
    spec_path = os.path.join(specs, f"{key}.json")
    if write_spec:
        spec = {"engine": "fx", "recipe": "dissolve",
                "about": f"{source} breaking up over {o['cells']} cells ({o['pattern']}; kit/vfx/dissolve.py): cell 0 whole, the last cell empty. "
                         f"On a mesh: \"surface\": 1 and \"flipbook\": {{\"layout\": \"{grid}x{grid}\", \"mode\": \"OneShot\", \"over\": [start, end]}}",
                "frames": o["cells"], "grid": grid, "cell": o["cell"], "from": source, "dissolve": settings(o),
                "post": {"alpha": "coverage", "tonemap": False, "border": 0}}
        import fxfinish  # (a line or a fringe added to this sheet by hand is kept when the tool runs again)
        spec["post"].update(fxfinish.last_looks(spec_path))
        os.makedirs(specs, exist_ok=True)
        with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=1)
            fh.write("\n")
    write_frames(frames_dir, key, cells, spec_path, source_id(src_path))
    line = f'"texture": "{key}", "surface": 1, "flipbook": {{"layout": "{grid}x{grid}", "mode": "OneShot", "over": [0.6, 1]}}'
    return ("pass", f"dissolve {key}: {source} breaks up over {o['cells']} cells ({grid}x{grid}, {o['cell']} px, {o['pattern']})"
            + (", a burning edge" if o["edge"] > 0 else "") + f" - on a mesh layer: {line}",
            (f"OPEN {extra['look']}; " if look else "") + "then lune run kit vfx packs and registers it", dict(extra, flipbook=line))


def build_step(argv):
    """every recipe "dissolve" spec whose frames are missing, older than its spec, or baked from a source texture
    that has changed since, is baked again; with --pack <packer> all of them are then packed and registered.
    `kit vfx` runs this AFTER its fx textures are packed, so a source is always the one of this run (run before
    them, it baked from the source as it was a run earlier and said "current")"""
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else d  # noqa: E731
    specs, frames_dir, built = opt("--specs", SPECS), opt("--out", FRAMES), opt("--textures-dir", BUILT)
    done, errors, keys = [], [], []
    for f in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
        if not f.endswith(".json"):
            continue
        path = os.path.join(specs, f)
        try:
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "dissolve":
            continue
        key, source = f[:-5], spec.get("from")
        if source != "plain" and not is_key(source):
            errors.append(f'dissolve {key}: its spec\'s "from" is not a texture key')
            continue
        src_path = None if source == "plain" else os.path.join(built, f"{source}.png")
        try:
            with open(os.path.join(frames_dir, key, "frames.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            fresh = meta.get("spec_mtime") == os.path.getmtime(path) and meta.get("source") == source_id(src_path) and meta.get("source") is not None
        except (OSError, ValueError, AttributeError):
            fresh = False
        if fresh and "--force" not in argv:
            keys.append(key)
            continue
        try:
            block = dict(spec.get("dissolve") or {}, cells=spec.get("frames", 16), cell=spec.get("cell", 256)) if isinstance(spec.get("dissolve"), dict) else None
            status, said, _, _ = bake(key, source, checked(block), built, specs, frames_dir, write_spec=False)
        except ValueError as e:
            status, said = "fail", f'dissolve {key}: its spec\'s "dissolve" block is not one ({e})'
        except Exception as e:  # noqa: BLE001 - one broken spec must not stop the others, nor print a traceback
            status, said = "fail", f"dissolve {key}: could not be baked again ({type(e).__name__}: {e})"
        if status == "pass":
            done.append(said)
            keys.append(key)
        else:
            errors.append(said)
    packed = None
    if keys and "--pack" in argv:
        r = subprocess.run([sys.executable, opt("--pack", ""), "--specs", specs, "--frames", frames_dir, "--out", built,
                            "--registry", opt("--registry", os.path.join("assets", "effects", "_textures.json")), "--no-review", *keys],
                           capture_output=True, text=True, check=False)
        try:
            packed = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            packed = {"status": "fail", "summary": (r.stderr.strip().splitlines() or ["the packer printed nothing"])[-1]}
        if packed.get("status") != "pass":
            errors.append(f"the packer: {packed.get('summary')}")
    if errors:
        return out("fail", "dissolve: " + "; ".join(errors), "bake it again: lune run kit vfx dissolve <key> --from <texture key>", baked=done)
    tail = f", {len(keys)} packed" if packed else ""
    return out("pass", (f"dissolve: {len(done)} sheet(s) baked again" if done else "dissolve: every dissolve sheet's frames are current") + tail, "none", baked=done, packed=keys if packed else [])


FLAGS = {"--from": "source", "--tint": "tint", "--cells": "cells", "--cell": "cell", "--pattern": "pattern", "--scale": "scale", "--soft": "soft",
         "--edge": "edge", "--edge-color": "edge_color", "--edge-gain": "edge_gain", "--density": "density", "--curve": "curve",
         "--seed": "seed", "--dot": "dot"}
DIRS = ("--textures-dir", "--specs-dir", "--frames-dir", "--look-dir")


def _main(argv):
    if "--specs" in argv:
        return build_step(argv)
    usage = "lune run kit vfx dissolve <key> --from <texture key | plain> [--cells 16] [--pattern patches|dither] [--soft 0.08] [--edge 0.06 --edge-color r,g,b]"
    if not argv or argv[0].startswith("--"):
        return out("fail", "dissolve: needs the new sheet's key", usage)
    key, rest = argv[0], argv[1:]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        return out("fail", f'dissolve: "{key}" is not a texture key (lower-case letters, digits, _)', usage)
    block, dirs, i = {}, {}, 0
    while i < len(rest):
        a = rest[i]
        if a not in FLAGS and a not in DIRS:
            return out("fail", f"dissolve: {a} is not one of its options", usage)
        if i + 1 >= len(rest):
            return out("fail", f"dissolve: {a} needs a value", usage)
        v = rest[i + 1]
        if a in DIRS:
            dirs[a] = v
        elif a in ("--edge-color", "--tint"):
            try:
                block[FLAGS[a] if a == "--tint" else "edge_color"] = [float(x) for x in v.split(",")]
            except ValueError:
                return out("fail", f"dissolve: {a} is r,g,b", usage)
        elif a in ("--from", "--pattern"):
            block[FLAGS[a]] = v
        else:
            try:
                block[FLAGS[a]] = float(v)
            except ValueError:
                return out("fail", f"dissolve: {a} needs a number", usage)
        i += 2
    source = block.pop("source", None)
    if not source:
        return out("fail", "dissolve: needs --from <texture key> (or --from plain)", usage)
    if source == key:
        return out("fail", "dissolve: the new sheet needs its own key, not its source's", usage)
    try:
        o = checked(block)
    except ValueError as e:
        return out("fail", f"dissolve {key}: {e}", usage)
    try:
        status, said, nxt, extra = bake(key, source, o, dirs.get("--textures-dir", BUILT), dirs.get("--specs-dir", SPECS),
                                        dirs.get("--frames-dir", FRAMES), dirs.get("--look-dir", LOOK))
    except ValueError as e:
        return out("fail", f"dissolve {key}: {e}", usage)
    return out(status, said, nxt, **extra)


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a command answers in one line, never with a traceback
        return out("fail", f"dissolve: {type(e).__name__}: {e}", "lune run kit vfx dissolve <key> --from <texture key | plain>")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
