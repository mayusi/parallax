"""refs.py — a world's REFERENCES measured by script, then its identity; renders compared to it (mission 05 5.1/5.5).

    python kit/world/refs.py <refs_dir> <identity.json> [--name <World>]      measure every still -> REFS.md + identity
    python kit/world/refs.py --vs <render.png> <identity.json>                  one difference + one edit (no score)
    (normally: lune run kit world refs <Name> [--vs <render>])

Per still (PIL + numpy only): the HORIZON line (% from the top: where the sky's own colour stops), the VALUE
structure (mean luminance of sky / far / mid / near bands), HAZE (contrast and saturation lost from near to far:
aerial perspective), SATURATION, and the dominant PALETTE (k-means, 6 colours with shares). The identity is the
median over the stills (and their spread); a render is measured the same way and the biggest gap, scaled by the
stills' spread, comes back as ONE difference + ONE edit in the world's own knobs (camera height, Atmosphere,
terrain colours, lighting). Stills are measure-only references: never shipped, never uploaded.
"""

import glob
import json
import os
import sys

import numpy as np

EXT = (".png", ".jpg", ".jpeg", ".webp")


def load(path, width=480):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    h = max(1, int(im.height * width / im.width))
    return np.asarray(im.resize((width, h), Image.BILINEAR), dtype=np.float64) / 255.0


def luminance(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def saturation(a):
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def horizon(a):
    """the row (fraction from the top) where the SKY stops. Two cues, either ends it: colour (the share of the row
    within reach of the top band's colour falls under half) and texture (sky is smooth, land is not: the row's mean
    horizontal luminance change rises well above the top band's). Golden haze makes land the sky's colour; texture
    still tells them apart."""
    h = a.shape[0]
    lum = luminance(a)
    tex = np.abs(np.diff(lum, axis=1)).mean(axis=1)
    tex = np.convolve(tex, np.ones(5) / 5, mode="same")
    band = max(3, h // 20)
    sky_tex = float(np.median(tex[1:band]))
    top = a[:band].reshape(-1, 3)
    sky = np.median(top, axis=0)
    spread = max(0.05, float(np.percentile(np.linalg.norm(top - sky, axis=1), 90)) * 1.4)
    share = (np.linalg.norm(a - sky, axis=-1) < spread + 0.05).mean(axis=1)
    share = np.convolve(share, np.ones(5) / 5, mode="same")
    thr = max(0.012, 3.0 * sky_tex)
    for row in range(band, h):
        if tex[row] > thr or share[row] < 0.5:
            return row / h
    return 1.0


def kmeans(px, k=6, iters=12, seed=1):
    rng = np.random.default_rng(seed)
    c = px[rng.choice(len(px), size=min(k, len(px)), replace=False)]
    for _ in range(iters):
        d = ((px[:, None, :] - c[None, :, :]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(len(c)):
            m = px[lab == j]
            if len(m):
                c[j] = m.mean(0)
    d = ((px[:, None, :] - c[None, :, :]) ** 2).sum(-1)
    lab = d.argmin(1)
    shares = np.bincount(lab, minlength=len(c)) / len(px)
    order = np.argsort(-shares)
    return [{"rgb": [int(round(v * 255)) for v in c[i]], "share": round(float(shares[i]), 3)} for i in order]


def measure(path):
    a = load(path)
    h = a.shape[0]
    hz = horizon(a)
    r = int(hz * h)
    lum, sat = luminance(a), saturation(a)
    far_end = min(h, r + max(2, int(0.15 * h)))
    mid_end = min(h, far_end + max(2, int(0.25 * h)))
    bands = {"sky": (0, r), "far": (r, far_end), "mid": (far_end, mid_end), "near": (mid_end, h)}
    values, contrast, sats = {}, {}, {}
    for k, (y0, y1) in bands.items():
        if y1 - y0 < 2:
            values[k] = contrast[k] = sats[k] = None
            continue
        values[k] = round(float(lum[y0:y1].mean()), 3)
        contrast[k] = round(float(lum[y0:y1].std()), 3)
        sats[k] = round(float(sat[y0:y1].mean()), 3)
    # haze = aerial perspective: the far band loses saturation and drifts toward the sky's brightness, relative to
    # the near band (silhouette contrast is not haze: a crisp ridge line stays crisp through thick haze)
    haze = None
    if None not in (values.get("far"), values.get("near"), values.get("sky"), sats.get("far"), sats.get("near")):
        desat = 1 - sats["far"] / max(sats["near"], 1e-6)
        toward_sky = 1 - abs(values["far"] - values["sky"]) / max(abs(values["near"] - values["sky"]), 1e-6)
        haze = round(float(np.clip(0.5 * desat + 0.5 * toward_sky, 0, 1)), 3)
    px = a[::4, ::4].reshape(-1, 3)
    return {"file": os.path.basename(path), "horizon_pct": round(hz * 100, 1), "values": values,
            "contrast": contrast, "saturation": sats, "haze": haze, "palette": kmeans(px)}


def median_of(ms, key, sub=None):
    vals = [(m[key] if sub is None else (m[key] or {}).get(sub)) for m in ms]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return None, None
    return round(float(np.median(vals)), 3), round(float(np.std(vals)), 3)


def build_identity(ms, name):
    ident = {"world": name, "stills": len(ms), "measured_by": "kit/world/refs.py"}
    ident["horizon_pct"], ident["horizon_spread"] = median_of(ms, "horizon_pct")
    ident["haze"], ident["haze_spread"] = median_of(ms, "haze")
    ident["values"] = {k: median_of(ms, "values", k)[0] for k in ("sky", "far", "mid", "near")}
    ident["saturation"] = {k: median_of(ms, "saturation", k)[0] for k in ("sky", "far", "mid", "near")}
    pal = {}
    for m in ms:  # the stills' palettes merged (shares summed per coarse colour)
        for p in m["palette"]:
            key = tuple(int(v // 32) for v in p["rgb"])
            e = pal.setdefault(key, {"rgb": np.zeros(3), "share": 0.0})
            e["rgb"] += np.array(p["rgb"]) * p["share"]
            e["share"] += p["share"]
    top = sorted(pal.values(), key=lambda e: -e["share"])[:8]
    total = sum(e["share"] for e in top) or 1
    ident["palette"] = [{"rgb": [int(v) for v in (e["rgb"] / max(e["share"], 1e-9)).round()], "share": round(e["share"] / total, 3)} for e in top]
    return ident


def refs_md(ms, ident):
    lines = [f"# {ident['world']} references (measured by kit/world/refs.py: measure-only stills, never shipped)", "",
             "| still | horizon % | sky | far | mid | near | haze | far sat | near sat |", "|---|---|---|---|---|---|---|---|---|"]
    for m in ms:
        v, s = m["values"], m["saturation"]
        lines.append(f"| {m['file']} | {m['horizon_pct']} | {v['sky']} | {v['far']} | {v['mid']} | {v['near']} | {m['haze']} | {s['far']} | {s['near']} |")
    v = ident["values"]
    lines += ["", f"**Identity (median of {ident['stills']}):** horizon {ident['horizon_pct']} % (spread {ident['horizon_spread']}), "
              f"values sky {v['sky']} / far {v['far']} / mid {v['mid']} / near {v['near']}, haze {ident['haze']}.",
              "", "Palette: " + ", ".join(f"rgb{tuple(p['rgb'])} {p['share'] * 100:.0f} %" for p in ident["palette"])]
    return "\n".join(lines) + "\n"


def compare(render, ident):
    """the render vs the identity -> (differences sorted by size in spreads, ONE edit)"""
    m = measure(render)
    diffs = []

    def add(key, got, want, spread, floor, words, edit):
        if got is None or want is None:
            return
        size = abs(got - want) / max(spread or 0, floor)
        if size >= 1:
            diffs.append((size, key, words.format(got=got, want=want), edit))

    add("horizon", m["horizon_pct"], ident.get("horizon_pct"), ident.get("horizon_spread"), 5,
        "horizon at {got} % vs the references' {want} %",
        "lower the camera / raise the far land" if (m["horizon_pct"] or 0) < (ident.get("horizon_pct") or 0) else "raise the camera / lower the far ridge so more sky shows")
    add("haze", m["haze"], ident.get("haze"), ident.get("haze_spread"), 0.08, "haze {got} vs {want}",
        "Atmosphere.Density +0.05 / Haze +1 (the far land should fade more)" if (m["haze"] or 0) < (ident.get("haze") or 0) else "Atmosphere.Density -0.05 (the far land is washed out)")
    for band in ("far", "near", "sky"):
        add(f"value_{band}", (m["values"] or {}).get(band), (ident.get("values") or {}).get(band), None, 0.06,
            f"{band} band luminance {{got}} vs {{want}}",
            {"far": "Atmosphere colour / Haze toward the references' far value",
             "near": "terrainColors / ColorCorrection.Brightness toward the near value",
             "sky": "Sky / Atmosphere.Color toward the references' sky value"}[band])
    add("sat_near", (m["saturation"] or {}).get("near"), (ident.get("saturation") or {}).get("near"), None, 0.07,
        "near saturation {got} vs {want}", "ColorCorrection.Saturation (or the terrain palette) toward the references")
    diffs.sort(key=lambda d: -d[0])
    return m, diffs


def main(argv):
    if "--vs" in argv:
        render = argv[argv.index("--vs") + 1]
        rest = [a for a in argv if a not in ("--vs", render)]
        if not rest or not os.path.isfile(rest[0]) or not os.path.isfile(render):
            print(json.dumps({"status": "fail", "summary": "usage: refs.py --vs <render.png> <identity.json>", "next_action": "measure the references first: lune run kit world refs <Name>"}))
            return 2
        ident = json.load(open(rest[0], encoding="utf-8"))
        m, diffs = compare(render, ident)
        if not diffs:
            print(json.dumps({"status": "pass", "summary": f"{os.path.basename(render)}: inside the references on every measure", "next_action": "show the owner", "measured": m}))
            return 0
        print(json.dumps({"status": "pass", "summary": f"{os.path.basename(render)}: {diffs[0][2]} (the biggest of {len(diffs)} difference(s))",
                          "next_action": f"ONE edit: {diffs[0][3]}", "differences": [d[2] for d in diffs], "edit": diffs[0][3], "measured": m}))
        return 0
    if len(argv) < 2:
        print(json.dumps({"status": "fail", "summary": "usage: refs.py <refs_dir> <identity.json> [--name W]", "next_action": "lune run kit world refs <Name>"}))
        return 2
    refs_dir, ident_path = argv[0], argv[1]
    name = argv[argv.index("--name") + 1] if "--name" in argv else os.path.basename(os.path.normpath(refs_dir))
    stills = sorted(f for f in glob.glob(os.path.join(refs_dir, "*")) if f.lower().endswith(EXT))
    if not stills:
        print(json.dumps({"status": "fail", "summary": f"no stills in {refs_dir}", "next_action": f"put >= 6 real stills (the owner's picks) in {refs_dir}"}))
        return 1
    ms = [measure(s) for s in stills]
    ident = build_identity(ms, name)
    os.makedirs(os.path.dirname(os.path.abspath(ident_path)), exist_ok=True)
    with open(ident_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(ident, fh, indent=1)
    with open(os.path.join(refs_dir, "REFS.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(refs_md(ms, ident))
    ok = len(ms) >= 6
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"refs {name}: {len(ms)} still(s) measured -> REFS.md + {ident_path.replace(os.sep, '/')} (horizon {ident['horizon_pct']} %, haze {ident['haze']})",
                      "next_action": "compare a render: lune run kit world refs <Name> --vs <render.png>" if ok else f"{6 - len(ms)} more still(s): the identity needs >= 6",
                      "identity": ident}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
