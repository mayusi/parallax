"""sections.py — an asset's CROSS-SECTIONS laid over a reference model's: `lune run kit refs sections <asset> --ref ..`.

A part built from side photos is right from the side and can be wrong everywhere else: the Glock's frame was a solid
brick where the real one is a U-shaped shell, its slide's nose a hollow box where the real one is solid with a chin
hanging into the frame, its recoil spring 4 mm too high — none of it showed in side views, judges' notes or
silhouette matches, and all of it showed at once in sections cut at the same stations through the build and through a
reference model (2026-10-10). This cuts both, draws them over each other (reference red, ours blue) and MEASURES how
far apart they are at each station, so the worst stations are named, not guessed.

    python kit/refs/sections.py <asset> --ref <library id | model.glb> [--ref-only a,b] [--ref-hide a,b] [--flip]
        [--only a,b] [--hide a,b] [--scale auto | <ref mm per unit>] [--at d1,d2,..] [--along x1,x2,..]
        -> build/refs/<asset>_sections.png (+ _along.png) and one JSON result line

--at: cross sections d mm behind each model's FRONT-MOST point (default 0.5 .. 60, dense at the nose and every 20
mm on); --along: lengthwise sections x mm off the centre line. Both models are aligned on the top and the centre of
their REARMOST cross section; --scale auto (default) makes the reference as long as our build (a library model comes
in its own units). --ref-only / --ref-hide pick the reference's objects (a weapon light on its rail, a stand).
"""

import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

LIBRARY = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "library")
DEFAULT_AT = [0.5, 1.5, 3.0, 5.0, 8.0, 12.0, 18.0, 26.0, 40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0]
PX = 6.0   # px per mm on the sheets


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status in ("pass", "warn") else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _nums(text):
    return [float(t) for t in text.split(",") if t.strip()]


# ------------------------------------------------------------------------------------------------- pure geometry
def frame_of(slices):
    """(centre across, top) of the REARMOST cross section — what both models are aligned on (a section well behind
    the nose: the full body, not a tapering tip). None when nothing was cut there."""
    for sl in sorted(slices, key=lambda s: -s["d"]):
        pts = [p for s in sl["segs"] for p in s[:2]]
        if pts:
            us = [p[0] for p in pts]
            return (min(us) + max(us)) / 2, max(p[1] for p in pts)
    return None


def sample(segs, step=0.25):
    """points every ~step mm along segments [[u, h], [u, h], ..]"""
    out = []
    for s in segs:
        (a0, a1), (b0, b1) = s[0], s[1]
        n = max(1, int(math.hypot(b0 - a0, b1 - a1) / step))
        out += [(a0 + (b0 - a0) * k / n, a1 + (b1 - a1) * k / n) for k in range(n + 1)]
    return out


def _nearest(pts, ref_pts, cell=1.0):
    """distance from each point to the nearest of ref_pts (a grid hash: sections have thousands of points)"""
    grid = {}
    for q in ref_pts:
        grid.setdefault((int(math.floor(q[0] / cell)), int(math.floor(q[1] / cell))), []).append(q)
    out = []
    for p in pts:
        gx, gy = int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell))
        best = None
        for r in range(0, 40):   # (rings of cells until one holds a point, then one ring more)
            cand = [q for i in range(gx - r, gx + r + 1) for j in range(gy - r, gy + r + 1)
                    if max(abs(i - gx), abs(j - gy)) == r for q in grid.get((i, j), ())]
            for q in cand:
                d = math.hypot(p[0] - q[0], p[1] - q[1])
                best = d if best is None or d < best else best
            if best is not None and best <= r * cell:
                break
        out.append(best if best is not None else 40 * cell)
    return out


def deviation(ours, ref, step=0.25):
    """how far apart two sections are (mm): {"ref_to_ours": mean, "ours_to_ref": mean, "p90": the 90th percentile
    of both, "missing": share of the reference's points over 1.5 mm from anything of ours, "extra": ours from the
    reference's} — `missing` is shape the build lacks (a lip, a chin), `extra` shape the reference has not (a box
    where a U should be)"""
    a, b = sample(ours, step), sample(ref, step)
    if not a or not b:
        return {"ref_to_ours": None, "ours_to_ref": None, "p90": None, "missing": 1.0 if b else 0.0,
                "extra": 1.0 if a else 0.0}
    rb, ra = _nearest(b, a), _nearest(a, b)
    both = sorted(rb + ra)
    return {"ref_to_ours": round(sum(rb) / len(rb), 2), "ours_to_ref": round(sum(ra) / len(ra), 2),
            "p90": round(both[int(0.9 * (len(both) - 1))], 2),
            "missing": round(sum(1 for d in rb if d > 1.5) / len(rb), 3),
            "extra": round(sum(1 for d in ra if d > 1.5) / len(ra), 3)}


def shift(segs, du, dh):
    return [[[s[0][0] - du, s[0][1] - dh], [s[1][0] - du, s[1][1] - dh]] + s[2:] for s in segs]


def compare(ours, ref):
    """both cuts' cross sections aligned (each on its rearmost section's centre and top) -> rows per station"""
    fo, fr = frame_of(ours["cross"]), frame_of(ref["cross"])
    rows = []
    for so in ours["cross"]:
        sr = min(ref["cross"], key=lambda s: abs(s["d"] - so["d"]), default=None)
        if sr is None or abs(sr["d"] - so["d"]) > 1e-6:
            continue
        a = shift(so["segs"], *fo) if fo else so["segs"]
        b = shift(sr["segs"], *fr) if fr else sr["segs"]
        rows.append({"d": so["d"], **deviation(a, b)})
    return rows, fo, fr


# ------------------------------------------------------------------------------------------------- the sheets
def draw_cross(ours, ref, fo, fr, rows, path, depth=None, cols=5):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    def ext(js, f):
        pts = [p for s in js["cross"] for seg in s["segs"] for p in seg[:2]]
        if not pts or not f:
            return 0.0, 0.0, 1.0
        return (max(abs(p[0] - f[0]) for p in pts), max(f[1] - p[1] for p in pts), max(p[1] - f[1] for p in pts))
    wo, do, uo = ext(ours, fo)
    wr, dr_, ur = ext(ref, fr)
    half = max(wo, wr) + 3.0
    down = depth if depth else max(do, dr_) + 3.0
    up = max(uo, ur, 0.0) + 3.0
    pw, ph = int(2 * half * PX), int((down + up) * PX) + 24
    n = len(ours["cross"])
    img = Image.new("RGB", (pw * min(cols, max(n, 1)), ph * max(1, math.ceil(n / cols))), (255, 255, 255))
    g = ImageDraw.Draw(img)
    dev = {r["d"]: r for r in rows}
    for js, f, col in ((ref, fr, (215, 40, 40)), (ours, fo, (30, 60, 220))):
        for i, sl in enumerate(js["cross"]):
            if js is ref and not any(abs(sl["d"] - so["d"]) < 1e-6 for so in ours["cross"]):
                continue
            k = i if js is ours else next(j for j, so in enumerate(ours["cross"]) if abs(so["d"] - sl["d"]) < 1e-6)
            ox, oy = (k % cols) * pw, (k // cols) * ph
            for a, b, *_ in shift(sl["segs"], *f) if f else sl["segs"]:
                g.line((ox + pw / 2 + a[0] * PX, oy + 20 + (up - a[1]) * PX,
                        ox + pw / 2 + b[0] * PX, oy + 20 + (up - b[1]) * PX), fill=col, width=1)
    for k, sl in enumerate(ours["cross"]):
        ox, oy = (k % cols) * pw, (k // cols) * ph
        r = dev.get(sl["d"])
        g.text((ox + 4, oy + 3), f"{sl['d']:g} mm" + (f"  p90 {r['p90']} mm" if r and r["p90"] is not None else ""),
               fill=(0, 0, 0))
        for mm in range(0, int(down) + 1, 5):   # (5 mm ticks down from the aligned top)
            g.line((ox, oy + 20 + (up + mm) * PX, ox + (6 if mm % 10 else 12), oy + 20 + (up + mm) * PX),
                   fill=(0, 150, 0))
        g.rectangle((ox, oy, ox + pw - 1, oy + ph - 1), outline=(225, 225, 225))
    img.save(path)
    return path


def draw_along(ours, ref, fo, fr, path, length=None):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if not ours["along"]:
        return None
    L = length or max((p[0] for s in ours["along"] for seg in s["segs"] for p in seg[:2]), default=60.0)
    hs = [p[1] - fo[1] for s in ours["along"] for seg in s["segs"] for p in seg[:2]] if fo else [0.0]
    lo_h, hi_h = min(hs) - 3.0, max(hs) + 3.0
    px = min(PX, 1800.0 / max(L, 1.0))
    pw, ph = int(L * px) + 20, int((hi_h - lo_h) * px) + 24
    img = Image.new("RGB", (pw, ph * len(ours["along"])), (255, 255, 255))
    g = ImageDraw.Draw(img)
    for js, f, col in ((ref, fr, (215, 40, 40)), (ours, fo, (30, 60, 220))):
        for sl in js["along"]:
            k = next((j for j, so in enumerate(ours["along"]) if abs(so["x"] - sl["x"]) < 1e-6), None)
            if k is None:
                continue
            for a, b, *_ in sl["segs"]:
                if a[0] > L and b[0] > L:
                    continue
                g.line((pw - 10 - a[0] * px, k * ph + 20 + (hi_h - (a[1] - (f[1] if f else 0))) * px,
                        pw - 10 - b[0] * px, k * ph + 20 + (hi_h - (b[1] - (f[1] if f else 0))) * px), fill=col, width=1)
    for k, sl in enumerate(ours["along"]):
        g.text((4, k * ph + 3), f"x = {sl['x']:g} mm off the centre line (front at the right, 10 mm ticks)", fill=(0, 0, 0))
        for mm in range(0, int(L) + 1, 10):
            g.line((pw - 10 - mm * px, (k + 1) * ph - 4, pw - 10 - mm * px, (k + 1) * ph - 12), fill=(0, 150, 0))
        g.rectangle((0, k * ph, pw - 1, (k + 1) * ph - 1), outline=(225, 225, 225))
    img.save(path)
    return path


# ------------------------------------------------------------------------------------------------- the command
def manifest_mm_per_stud(man):
    """the build's real scale from its manifest: top level, its facts, or its CAD parts' (a code-CAD build records it
    per part: facts.cad[].mm_per_stud) -> mm per stud, 0.0 when none says"""
    for v in (man.get("mm_per_stud"), (man.get("facts") or {}).get("mm_per_stud")):
        if v:
            return float(v)
    for c in (man.get("facts") or {}).get("cad") or []:
        if isinstance(c, dict) and c.get("mm_per_stud"):
            return float(c["mm_per_stud"])
    return 0.0


def blender():
    return find_blender()


def _cut(exe, blend, src, out, extra):
    cmd = [exe, "-b"] + ([blend] if blend else []) + ["--factory-startup", "-P",
                                                       os.path.join(HERE, "sections_cut.py"), "--", src, out] + extra
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    said = None
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith("{"):
            try:
                said = json.loads(line)
                break
            except ValueError:
                pass
    if said is None or "error" in said or not os.path.isfile(out):
        tail = " | ".join([ln for ln in ((r.stdout or "") + (r.stderr or "")).splitlines() if ln.strip()][-3:])
        raise RuntimeError((said or {}).get("error") or tail[:400] or "Blender said nothing")
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    if not argv or argv[0].startswith("--") or not _arg(argv, "--ref"):
        return emit("fail", "refs sections: give the asset and --ref <library id | model.glb>",
                    "lune run kit refs sections <asset> --ref <id> [--ref-only a,b] [--flip] [--at d1,d2,..]")
    asset, ref = argv[0], _arg(argv, "--ref")
    build = os.path.join(ROOT, os.environ.get("KIT_BUILD", "build"))
    blend = os.path.join(build, "models", f"{asset}.blend")
    if not os.path.isfile(blend):
        return emit("fail", f"refs sections: no {os.path.relpath(blend, ROOT)} (build it first)",
                    f"lune run kit asset {asset}")
    mmps = float(_arg(argv, "--mm-per-stud", "0") or 0.0)
    man = os.path.join(build, "models", f"{asset}.manifest.json")
    if mmps <= 0 and os.path.isfile(man):
        with open(man, encoding="utf-8") as fh:
            mmps = manifest_mm_per_stud(json.load(fh))
    if mmps <= 0:
        return emit("fail", f"refs sections: {asset}'s manifest gives no mm_per_stud (a real size is needed to cut in mm)",
                    "give the asset a real size (its brief / a.mm_per_stud) and rebuild, or say it: --mm-per-stud <mm>")
    src = ref
    if not os.path.isfile(src):
        lib = os.path.join(LIBRARY, ref, "model.glb")
        if not os.path.isfile(lib):
            return emit("fail", f"refs sections: {ref} is neither a file nor a library model",
                        'lune run kit library find "<object>" / get <id>')
        src = lib
    exe = blender()
    if not exe:
        return emit("fail", "refs sections: Blender not found", "set BLENDER to blender's path")
    at = _nums(_arg(argv, "--at")) if _arg(argv, "--at") else DEFAULT_AT
    along = _nums(_arg(argv, "--along")) if _arg(argv, "--along") else [0.0]
    common = ["--at", ",".join(f"{v:g}" for v in at), "--along", ",".join(f"{v:g}" for v in along)]
    tmp = tempfile.mkdtemp(prefix=f"kit_sections_{asset}_")
    try:
        ours = _cut(exe, blend, "-", os.path.join(tmp, "ours.json"),
                    common + ["--kit", "--mm-per-unit", str(mmps)]
                    + sum([[f, _arg(argv, f)] for f in ("--only", "--hide") if _arg(argv, f)], []))
        scale = _arg(argv, "--scale", "auto")
        sel = sum([[f.replace("--ref-", "--"), _arg(argv, f)] for f in ("--ref-only", "--ref-hide") if _arg(argv, f)],
                  [])
        rx = common + sel + (["--flip"] if "--flip" in argv else []) + (
            ["--match-length", str(ours["length_mm"])] if scale == "auto" else ["--mm-per-unit", scale])
        refc = _cut(exe, None, src, os.path.join(tmp, "ref.json"), rx)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        return emit("fail", f"refs sections: the cut failed: {e}", "check the asset's .blend and the reference file")
    rows, fo, fr = compare(ours, refc)
    out_dir = os.path.join(build, "refs")
    os.makedirs(out_dir, exist_ok=True)
    depth = float(_arg(argv, "--depth", "0")) or None   # (mm under the top drawn: a pistol's nose without its grip)
    sheet = draw_cross(ours, refc, fo, fr, rows, os.path.join(out_dir, f"{asset}_sections.png"), depth=depth)
    long_ = draw_along(ours, refc, fo, fr, os.path.join(out_dir, f"{asset}_sections_along.png"),
                       length=float(_arg(argv, "--along-length", "70")))
    with open(os.path.join(out_dir, f"{asset}_sections.json"), "w", encoding="utf-8") as fh:
        json.dump({"ref": ref, "ref_mm_per_unit": refc["mm_per_unit"], "rows": rows}, fh, indent=1)
    rel = [os.path.relpath(p, ROOT).replace("\\", "/") for p in (sheet, long_) if p]
    worst = sorted([r for r in rows if r["p90"] is not None], key=lambda r: -r["p90"])[:3]
    said = "; ".join(f"{r['d']:g} mm behind the front: p90 {r['p90']} mm (the reference's shape missing "
                     f"{round(100 * r['missing'])}%, ours extra {round(100 * r['extra'])}%)" for r in worst)
    bad = [r for r in rows if r["p90"] is not None and r["p90"] > 1.5]
    return emit("warn" if bad else "pass",
                f"refs sections: {asset} vs {os.path.basename(os.path.dirname(src)) if src != ref else ref} at "
                f"{len(rows)} stations (the reference x{refc['mm_per_unit']:.2f} mm/unit); "
                + (f"{len(bad)} stations over 1.5 mm apart — worst {said}" if bad else "every station within 1.5 mm"),
                f"LOOK at {', '.join(rel)} (red the reference, blue ours, aligned on the rearmost section's top): where "
                "blue leaves red the part is the wrong SHAPE there (a solid where it is hollow, a missing lip) — fix that "
                f"part's CAD (kit cad check), rebuild, run this again", rows=rows, sheets=rel)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
