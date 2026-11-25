"""identity_from.py — an identity DRAFT derived from measured references, not typed from memory: the palette
(ink / paper / the one accent, found in the stills), where the accent lives, how much of the frame each takes,
the lean of the accent field, and the rules those numbers imply — every field with its evidence line.

    python kit/ui/identity_from.py <identity> [--refs assets/ui/refs] [--out assets/ui/refs/<identity>/identity.from-refs.json]

Reads every <still>.layout.json in refs/<identity>/ (kit ui measure writes them) and the stills themselves for
the dominant saturated colour. The human merges the draft into <identity>.json — the draft never overwrites it.
"""
import argparse
import colorsys
import glob
import json
import os
import time

import numpy as np
from PIL import Image


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def dominant_accent(path, min_sat=0.5, min_val=0.35):
    """the most common SATURATED colour in a still (binned hue / sat / val) — the one accent"""
    im = Image.open(path).convert("RGB")
    im.thumbnail((400, 400))
    a = np.array(im).astype(np.float32) / 255.0
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    val = mx
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    pick = (sat >= min_sat) & (val >= min_val)
    if pick.sum() < 50:
        return None, 0.0
    hue = np.zeros_like(mx)
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.0
    bins = (np.floor(hue[pick] * 24).astype(int) % 24)
    counts = np.bincount(bins, minlength=24)
    h = (int(counts.argmax()) + 0.5) / 24.0
    sel = pick & (np.floor(hue * 24).astype(int) % 24 == int(counts.argmax()))
    rgb = a[sel].mean(axis=0)
    share = float(sel.mean())
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb), share


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("identity")
    ap.add_argument("--refs", default="assets/ui/refs")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    folder = os.path.join(a.refs, a.identity)
    layouts = sorted(glob.glob(os.path.join(folder, "*.layout.json")))
    if not layouts:
        return emit("fail", f"identity_from: no measured stills in {folder}", f"lune run kit ui measure {folder}/<still>  (for every reference), then again")
    evidence = []
    accents, acc_shares, paper_shares, ink_shares, slopes, acc_quads = [], [], [], [], [], []
    for lp in layouts:
        L = json.load(open(lp, encoding="utf-8"))
        still = L["still"] if os.path.isfile(L["still"]) else os.path.join(folder, os.path.basename(L["still"]))
        col, share = dominant_accent(still) if os.path.isfile(still) else (None, 0.0)
        if col:
            accents.append((col, share))
        sh = L.get("shares", {})
        acc_shares.append(sh.get("accent", 0))
        paper_shares.append(sh.get("paper", 0))
        ink_shares.append(sh.get("ink", 0))
        if L.get("accent", {}).get("top_edge_slope") is not None:
            slopes.append(L["accent"]["top_edge_slope"])
        acc_quads.append(L.get("quadrants", {}))
        evidence.append(f"{os.path.basename(lp)}: accent {sh.get('accent', 0):.0%} paper {sh.get('paper', 0):.0%} ink {sh.get('ink', 0):.0%}, dominant saturated colour {col} ({share:.0%} of the frame), accent top-edge slope {L.get('accent', {}).get('top_edge_slope')}")
    accent = max(accents, key=lambda t: t[1])[0] if accents else None
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    acc_mean, paper_mean, ink_mean = mean(acc_shares), mean(paper_shares), mean(ink_shares)
    slope_mean = mean(slopes)
    lean_deg = round(float(np.degrees(np.arctan(slope_mean))), 1) if slope_mean is not None else None
    # where the accent lives: the quadrant with the most of it, averaged
    quad_tot = {}
    for q in acc_quads:
        for k, v in q.items():
            quad_tot[k] = quad_tot.get(k, 0) + v.get("accent", 0)
    accent_home = max(quad_tot, key=quad_tot.get) if quad_tot else None
    rules = []
    if acc_mean is not None and acc_mean < 0.45:
        rules.append(f"the accent is a FIELD on about {acc_mean:.0%} of the frame (measured), not a wash: everything else is ink and paper")
    if lean_deg is not None and abs(lean_deg) >= 3:
        rules.append(f"the accent field's edge leans about {lean_deg} degrees (measured): nothing on it sits level")
    if accent_home:
        rules.append(f"the accent lives {dict(tl='top-left', tr='top-right', bl='bottom-left', br='bottom-right')[accent_home]} (measured): that is where the hero piece goes")
    draft = {"name": a.identity, "from_refs": [os.path.basename(x) for x in layouts], "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "tokens_measured": {"accent": accent, "ink": "#000000", "paper": "#f0f0f0"},
             "shares_measured": {"accent": acc_mean, "paper": paper_mean, "ink": ink_mean},
             "accent_field": {"home_quadrant": accent_home, "edge_slope": slope_mean, "edge_lean_deg": lean_deg},
             "rules": rules, "evidence": evidence}
    # (next to the stills, never in identities/: every json there is read as an identity pack)
    out = a.out or os.path.join(folder, "identity.from-refs.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(draft, fh, indent=1)
    return emit("pass", f"identity_from: {a.identity} draft from {len(layouts)} measured still(s) → {out}: accent {accent} on {acc_mean:.0%}, paper {paper_mean:.0%}, ink {ink_mean:.0%}, field lean {lean_deg}°, home {accent_home}",
                f"merge what is better than your guess into assets/ui/identities/{a.identity}.json (tokens.accent, shape rules, bans); the draft keeps its evidence lines", draft=out)


if __name__ == "__main__":
    raise SystemExit(main())
