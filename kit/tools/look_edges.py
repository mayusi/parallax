"""look_edges.py — `kit look edges`: are the build's EDGES as round as the reference's — part by part, everywhere, not
only at the inventoried details (the owner, 2026-10-22: "the edges etc too, everything on anything we ever work
on")? The build is rendered orthographic from the picture's side and registered on its silhouette (kit look
details' machinery), then every edge of both is measured the same way at the SAME resolution (kit/refs/edges.py:
the ramp across the edge -> a radius in mm, calibrated in Blender) and compared per traced part (--parts) or per
~15 mm cell. A part whose edges are sharper than the art's needs a bigger round_mm / a cage; softer ones a smaller.

    lune run kit look edges <asset> --part <word> --picture <path> (--trace <t> --length-mm L | --mm-per-px f)
        [--parts <parts.json>] [--view side|left] [--cell 15]
        (no --parts: EVERY build part is its own region — the parts' ids rendered with the same camera)

Writes build/renders/<asset>_edges.png (the reference, each region tinted: red = the build's edges SHARPER than the
art, blue = softer) + .json (per region: the art's radius, the build's, the difference); prints one JSON line.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "kit", "refs"))
EXPORTS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "models")
RENDERS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "renders")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def compare_regions(w_ref, w_build, regions, mm_per_px, margin):
    """per region: the art's median radius, the build's, their difference and a verdict (pure: test_look_edges.py).
    margin: the difference under which they are called the same (the calibration's error)"""
    import edges as E  # noqa: PLC0415

    out = {}
    for name, m in regions.items():
        a, b = E.summarise(w_ref, m, mm_per_px), E.summarise(w_build, m, mm_per_px)
        if not a or not b:
            continue
        d = round(b["radius_mm"] - a["radius_mm"], 2)
        verdict = "sharper than the art" if d < -margin else ("softer than the art" if d > margin else "matches")
        out[name] = {"art_mm": a["radius_mm"], "build_mm": b["radius_mm"], "diff_mm": d, "verdict": verdict,
                     "art_round_share": a["round"], "build_round_share": b["round"], "samples": min(a["samples"],
                                                                                                    b["samples"])}
    return out


DESIGNED = ("screw", "pin", "rivet", "gem", "inlay", "logo", "text", "motto", "maker", "bead", "link", "ring", "bore")


def suggest(res, cad, words):
    """each compared region's build part(s) (a.cad facts whose name holds the region's name and a --part word) ->
    its NEXT round_mm: the current one moved by the measured difference, capped at 0.48 x the part's thinnest side
    (a round can't be wider than half the part) and never under 0.2 mm (pure)"""
    out = {}
    for region, r in res.items():
        for c in cad:
            n = c.get("part", "")
            if region.lower() not in n.lower() or not any(w.lower() in n.lower() for w in words):
                continue
            if any(d in n.lower() for d in DESIGNED):  # (a screw / gem / inlay in that region: its shape is designed)
                continue
            bb = c.get("bbox_mm") or [[0, 0, 0], [1e9, 1e9, 1e9]]
            thin = min(hi - lo for lo, hi in zip(*bb))
            param = "fillet_mm" if c.get("fillet_mm") else "round_mm"   # (a CAD fillet, or the mesh round)
            cur = float(c.get(param) or 0.0)
            nxt = min(0.48 * thin, max(0.2, cur - r["diff_mm"]))
            out[n] = {"region": region, "param": param, "round_mm_now": round(cur, 2), "round_mm_next": round(nxt, 2),
                      "capped": nxt >= 0.48 * thin - 1e-6, "thinnest_mm": round(thin, 2)}
    return out


def decode_ids(rgba, transform=None):
    """an --ids render -> (H, W) int part ids (0 = no part): R = 16 x (id % 16) + 8, G = 16 x (id // 16) + 8 (pure)"""
    import numpy as np  # noqa: PLC0415

    c = rgba[..., :3].astype(np.float32) / 255.0
    if transform and transform != "Raw":   # (a view transform's sRGB curve: undone)
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    r = np.rint((c[..., 0] * 255.0 - 8.0) / 16.0).astype(int)
    g = np.rint((c[..., 1] * 255.0 - 8.0) / 16.0).astype(int)
    ids = g * 16 + r
    ids[(rgba[..., 3] < 250) | (r < 0) | (g < 0)] = 0
    return ids


def part_regions(id_rgba, reg, shape, part_ids, words, transform=None):
    """each build part's pixels on the PICTURE: its ids decoded, laid on with the clay render's registration (the
    same camera); mirror twins (~m) joined to their part; only the parts the --part words name"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    ids = decode_ids(id_rgba, transform)
    im = ids[:, ::-1] if reg["flip"] else ids
    M = np.float32([[reg["s"], 0, reg["tx"]], [0, reg["s"], reg["ty"]]])
    H, W = shape
    warped = cv2.warpAffine(im.astype(np.float32), M, (W, H), flags=cv2.INTER_NEAREST)
    out = {}
    for name, k in part_ids.items():
        base = name.split("~")[0]
        if words and not any(w.lower() in base.lower() for w in words):
            continue
        m = warped == k
        if m.any():
            out[base] = out.get(base, np.zeros((H, W), bool)) | m
    return out


def cells(mask, cell_px):
    """the object's area cut into square cells (regions named by their place: c<col>_<row>)"""
    import numpy as np  # noqa: PLC0415

    H, W = mask.shape
    out = {}
    for y in range(0, H, cell_px):
        for x in range(0, W, cell_px):
            m = np.zeros_like(mask)
            m[y:y + cell_px, x:x + cell_px] = True
            m &= mask
            if m.sum() > 0.15 * cell_px * cell_px:
                out[f"c{x // cell_px}_{y // cell_px}"] = m
    return out


def overlay(ref, regions, res, path):
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415

    img = ref.astype(np.float32).copy()
    for name, r in res.items():
        m = regions[name]
        if r["verdict"] == "matches":
            continue
        tint = np.array([255, 40, 40] if r["diff_mm"] < 0 else [40, 120, 255], np.float32)
        k = min(0.65, 0.2 + abs(r["diff_mm"]) * 0.25)
        img[m] = img[m] * (1 - k) + tint * k
    im = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    for name, r in res.items():
        if r["verdict"] != "matches" and not name.startswith("c"):
            ys, xs = np.nonzero(regions[name])
            dr.text((int(xs.mean()), int(ys.mean())), f"{name} {r['diff_mm']:+.1f}mm", fill=(255, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    import edges as E  # noqa: PLC0415
    import look  # noqa: PLC0415
    import look_details as LD  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--part" not in argv or "--picture" not in argv:
        return emit("fail", "look edges: needs <asset> --part <word> --picture <path> (--trace <t> --length-mm L | "
                    "--mm-per-px f)", "lune run kit look edges <asset> --part <prefix> --picture refs/x_side.png "
                    "--trace assets/models/x_side.trace.json --length-mm 280")
    asset, pic = argv[0], arg(argv, "--picture")
    blend = os.path.join(EXPORTS, f"{asset}.blend")
    if not os.path.isfile(blend) or not os.path.isfile(pic):
        return emit("fail", f"look edges: no build of {asset} / no picture {pic}", f"lune run kit asset {asset}")
    if "--trace" in argv:
        with open(arg(argv, "--trace"), encoding="utf-8") as fh:
            fr = json.load(fh)["frame"]
        mpp, ox, oy = float(arg(argv, "--length-mm", 0) or 0) / float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    else:
        mpp, ox, oy = float(arg(argv, "--mm-per-px", 0) or 0), 0.0, 0.0
    if mpp <= 0:
        return emit("fail", "look edges: give --trace <t> --length-mm L or --mm-per-px f", "the picture's mm frame")
    with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
        bounds = json.load(fh).get("part_bounds") or {}
    words = [w for w in arg(argv, "--part").split(",") if w]
    hits = [n for n in bounds if any(w.lower() in n.lower() for w in words)]
    if not hits:
        return emit("fail", f"look edges: no part of {asset} matches {words}", "parts: " + ", ".join(sorted(bounds)[:20]))
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    ref = np.asarray(Image.open(pic).convert("RGB"))
    ref_mask, bgc = LD.object_mask(ref)

    def render(v, mode="--clay"):
        path = os.path.join(RENDERS, f"{asset}_ortho_{v}_{mode.strip('-')}.png")
        # (in CLAY, the edge calibration's matte grey: a glossy metal's rim reads as a step whatever its round)
        p = subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"),
                            "--", path, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", v, "--px",
                            str(int(max(ref.shape) * 1.1)), mode], capture_output=True, text=True, timeout=1800)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("LOOK_ORTHO ")), None)
        if not line or not os.path.isfile(path):
            raise RuntimeError((p.stderr or p.stdout)[-240:])
        render.info = json.loads(line[len("LOOK_ORTHO "):])
        return np.asarray(Image.open(path).convert("RGBA"))
    view = arg(argv, "--view", "side")
    try:
        rgba = render(view)
        reg = LD.register(ref_mask, rgba[..., 3] > 127)
        other = {"side": "left", "left": "side"}.get(view)
        if reg["flip"] and other and "--view" not in argv:
            rgba2 = render(other)
            reg2 = LD.register(ref_mask, rgba2[..., 3] > 127, flips=(False,))
            if reg2["iou"] >= reg["iou"] - 0.05:
                rgba, reg, view = rgba2, reg2, other
    except RuntimeError as e:
        return emit("fail", f"look edges: the render failed: {e}", "read the error above")
    view_used = view
    built = LD.warp_render(rgba, reg, ref.shape[:2], bgc)
    gr = np.asarray(Image.fromarray(ref).convert("L"))
    gb = np.asarray(Image.fromarray(built).convert("L"))
    w_ref, _ = E.edge_widths(gr)
    w_build, _ = E.edge_widths(gb)
    if "--parts" in argv:
        with open(arg(argv, "--parts"), encoding="utf-8") as fh:
            doc = json.load(fh)
        regions = {k: m & ref_mask for k, m in E.part_masks(doc.get("parts", doc), gr.shape, mpp, ox, oy).items()}
    else:  # EVERY build part its own region: the parts' id render, laid on the picture like the clay one
        regions = {}
        ids = (json.load(open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8")).get("part_ids")
               or {})
        if ids:
            try:
                idr = render(view_used, "--ids")
                regions = part_regions(idr, reg, ref.shape[:2], ids, words, render.info.get("transform"))
                regions = {k: m & ref_mask for k, m in regions.items() if (m & ref_mask).sum() > 40}
            except RuntimeError:
                regions = {}
        if not regions:
            regions = cells(ref_mask, max(8, int(float(arg(argv, "--cell", 15)) / mpp)))
    res = compare_regions(w_ref, w_build, regions, mpp, margin=max(0.4, 0.5 * float(E.CAL.get("err_mm", 0.8))))
    with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
        man = json.load(fh)
    cad = ((man.get("facts") or {}).get("cad") or (man.get("design") or {}).get("cad") or [])
    nxt = suggest({k: v for k, v in res.items() if v["verdict"] != "matches"}, cad, words)
    out = os.path.join(RENDERS, f"{asset}_edges.png")
    overlay(ref, regions, res, out)
    with open(out.replace(".png", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"picture": pic, "registration": reg, "mm_per_px": mpp, "regions": res, "round_mm_next": nxt},
                  fh, indent=1)
    sharp = sorted((r for r in res.items() if r[1]["verdict"] == "sharper than the art"), key=lambda r: r[1]["diff_mm"])
    soft = [n for n, r in res.items() if r["verdict"] == "softer than the art"]
    rel = os.path.relpath(out, REPO).replace(os.sep, "/")
    ok = reg["iou"] >= 0.6
    return emit("pass" if ok else "fail",
                f"look edges {asset}: {len(res)} region(s) compared (overlap {reg['iou']:.2f}); "
                f"{len(sharp)} SHARPER than the art" + (": " + ", ".join(f"{n} {r['art_mm']:.1f} vs {r['build_mm']:.1f}"
                                                                        f" mm" for n, r in sharp[:6]) if sharp else "")
                + f"; {len(soft)} softer" + (f"; next round_mm for {len(nxt)} a.cad part(s) in the .json" if nxt else ""),
                (f"LOOK at {rel} (red: round those edges more - round_mm / edge_roles / a.cage; blue: less); set "
                 "each part's round_mm to its round_mm_next, rebuild, run this again") if ok else
                "the silhouettes did not line up: the right --part / --view", overlay=rel, iou=reg["iou"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
