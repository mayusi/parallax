"""align.py — ALIGNMENT and SPACING lint: the near-misses a pro removes and an AI-made layout is full of.

    near_misses(boxes) -> [("near_align", path, message)] + [("uneven_gap", parent, message)]

boxes: {node path: (x, y, w, h)} of one drawn frame (the preview's ALL_BOXES). Among SIBLINGS (one parent):
- two edges or centres 1..3 px apart (left, right, top, bottom, centre x, centre y) are meant to line up and don't;
- three or more siblings in a row (or a column) whose gaps differ by 1..4 px were meant to be evenly spaced.
Exact matches and clear differences (> 3 px) are design; only the near-miss is flagged. Decoration that is offset on
purpose (a Shadow, a Plate, a Glow, fx layers, a 1-glyph cell) is skipped.

THE GATE (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4, "align.py 1-3 px anti-slop lint"): every compiled screen laid out at
desktop like the engine (kit/ui/preview.py layout_screen, the same boxes the preview draws, nothing drawn: ~2 ms a
screen), its near-misses counted:

    python kit/ui/align.py check [--models src/ui] [--fail] [Screen ...]

`kit verify` runs it as a WARNING with the count (most near-misses sit on screens only the owner can judge: a 2 px
step can be a hand-set offset he liked); --fail makes any near-miss a failure (kit selftest's bad fixture, a new
screen's own check).
"""
import argparse
import json
import os
import sys

SKIP = ("Shadow", "Plate", "Glow", "Gradient", "Band", "Grow", "KitPath", "KitPathOutline", "Rays", "Field", "Ground")
NEAR = (1.0, 3.0)
GAP = (1.0, 4.0)


def _skip(path):
    name = path.rsplit(".", 1)[-1]
    return name.startswith("Fx_") or name in SKIP or (len(name) <= 3 and name[:1] in "CG" and name[1:].isdigit())


def _siblings(boxes):
    groups = {}
    for path, b in boxes.items():
        if "." not in path or _skip(path) or b[2] <= 2 or b[3] <= 2:
            continue
        groups.setdefault(path.rsplit(".", 1)[0], []).append((path, b))
    return groups


def near_misses(boxes):
    out = []
    for parent, kids in _siblings(boxes).items():
        seen = set()
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                (pa, a), (pb, b) = kids[i], kids[j]
                lines = {
                    "left": (a[0], b[0]), "right": (a[0] + a[2], b[0] + b[2]),
                    "top": (a[1], b[1]), "bottom": (a[1] + a[3], b[1] + b[3]),
                    "centre x": (a[0] + a[2] / 2, b[0] + b[2] / 2), "centre y": (a[1] + a[3] / 2, b[1] + b[3] / 2),
                }
                for edge, (u, v) in lines.items():
                    d = abs(u - v)
                    if NEAR[0] <= d <= NEAR[1] and (pa, pb) not in seen:
                        seen.add((pa, pb))
                        out.append(("near_align", pa, f"its {edge} is {d:.0f}px off {pb.rsplit('.', 1)[-1]}'s — line them up "
                                    "exactly or move them clearly apart (a near-miss reads as a mistake)"))
        # rows and columns: 3+ siblings sharing a centre line, sorted along it
        for axis in (0, 1):
            other = 1 - axis
            bands = {}
            for p, b in kids:
                key = round((b[other] + b[other + 2] / 2) / 4)
                bands.setdefault(key, []).append((p, b))
            for row in bands.values():
                if len(row) < 3:
                    continue
                row.sort(key=lambda t: t[1][axis])
                gaps = [row[k + 1][1][axis] - (row[k][1][axis] + row[k][1][axis + 2]) for k in range(len(row) - 1)]
                spread = max(gaps) - min(gaps)
                if GAP[0] <= spread <= GAP[1] and min(gaps) >= 0:
                    out.append(("uneven_gap", parent, f"{len(row)} items in a {'row' if axis == 0 else 'column'} with gaps "
                                f"{', '.join(f'{g:.0f}' for g in gaps)}px — make them equal (a layout with a gap does it for you)"))
    return out


def palette(model, boxes):
    """PALETTE discipline (v7.13): the colours a screen PAINTS (fills, text, tinted pictures), weighted by the area they
    cover in the drawn layout, clustered (near colours are one) -> [("palette_count" | "palette_balance", path, msg)].
    More than 7 colours over 2% of the painted area reads busy; no colour over 40% means no dominant (60-30-10)."""
    weights = {}

    def add(rgb, area):
        key = tuple(int(c * 255) // 24 for c in rgb)
        weights[key] = weights.get(key, 0.0) + area

    def walk(inst, path):
        p = inst.get("Properties") or {}
        b = boxes.get(path)
        name = str(inst.get("Name") or "")
        if p.get("Visible") is False or name.startswith("Fx_"):
            return
        if b:
            area = max(0.0, b[2] * b[3])
            cls = inst.get("ClassName")
            if (p.get("BackgroundTransparency", 0) or 0) < 0.5 and (p.get("BackgroundColor3") or {}).get("Color3"):
                add(p["BackgroundColor3"]["Color3"], area)
            if cls in ("TextLabel", "TextButton") and str(p.get("Text") or "").strip() and (p.get("TextColor3") or {}).get("Color3"):
                add(p["TextColor3"]["Color3"], area * 0.25)
            ic = (p.get("ImageColor3") or {}).get("Color3")
            if cls in ("ImageLabel", "ImageButton") and ic and min(ic) < 0.98:
                add(ic, area * 0.6)
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    total = sum(weights.values())
    if total <= 0:
        return []
    # merge near clusters (within ~2 quantization steps)
    keys = sorted(weights, key=lambda k: -weights[k])
    merged = []
    for k in keys:
        for m in merged:
            if sum(abs(a - b) for a, b in zip(k, m[0])) <= 3:
                m[1] += weights[k]
                break
        else:
            merged.append([k, weights[k]])
    shares = sorted((w / total for _, w in merged), reverse=True)
    out = []
    many = sum(1 for s in shares if s >= 0.02)
    if many > 7:
        out.append(("palette_count", "screen", f"{many} colours each cover >= 2% of what is painted — a pro palette holds ~3-5 "
                    "(a ground, a support, an accent): fold the strays into the identity's tokens"))
    if shares and shares[0] < 0.4:
        out.append(("palette_balance", "screen", f"no dominant colour (the biggest covers {shares[0] * 100:.0f}%) — the 60-30-10 "
                    "rule: one colour ~60%, a second ~30%, the accent ~10%"))
    return out


def check_models(models_dir, names=None):
    """every compiled ScreenGui in models_dir (or the named ones) -> {screen: [(kind, path, message)]}, the near-misses
    on its desktop layout (screens with none are listed with an empty list)"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import preview
    out = {}
    files = sorted(f for f in os.listdir(models_dir) if f.endswith(".model.json")) if os.path.isdir(models_dir) else []
    for f in files:
        name = f[: -len(".model.json")]
        if names and name not in names:
            continue
        with open(os.path.join(models_dir, f), encoding="utf-8") as fh:
            model = json.load(fh)
        if model.get("ClassName") not in ("ScreenGui", "BillboardGui", "SurfaceGui"):
            continue
        out[name] = near_misses(preview.desktop_boxes(model))  # (a world screen: at its canvas size)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="align.py")
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--fail", action="store_true", help="any near-miss fails (default: a warning with the count)")
    a = ap.parse_args(argv)
    found = check_models(a.models, set(a.names) if a.names else None)
    if a.names:
        missing = sorted(set(a.names) - set(found))
        if missing:
            print(json.dumps({"schema": 1, "status": "fail", "summary": f"align: no compiled screen {', '.join(missing)} in {a.models}",
                              "next_action": "lune run kit ui (compile the screen first)"}))
            return 1
    hit = {n: r for n, r in found.items() if r}
    n_align = sum(1 for r in hit.values() for k, _, _ in r if k == "near_align")
    n_gap = sum(1 for r in hit.values() for k, _, _ in r if k == "uneven_gap")
    worst = sorted(hit, key=lambda n: (-len(hit[n]), n))
    listing = ", ".join(f"{n} {len(hit[n])}" for n in worst)
    report = {n: [{"kind": k, "path": p, "message": m} for k, p, m in r] for n, r in hit.items()}
    if not hit:
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"align: {len(found)} screen(s), no 1-3 px near-miss",
                          "next_action": None, "screens": {}}))
        return 0
    first = worst[0]
    k, p, m = hit[first][0]
    summary = (f"align: {len(hit)} of {len(found)} screen(s) have 1-3 px near-misses ({n_align} edge(s) / centre(s) "
               f"nearly lined up, {n_gap} uneven gap(s)) - {listing}")
    status = "fail" if a.fail else "pass"
    if not a.fail:
        summary += " (a WARNING: the owner judges the screens that carry them)"
    print(json.dumps({"schema": 1, "status": status, "summary": summary,
                      "next_action": f"improve {first} {p}: {m} (python kit/ui/align.py check {first})",
                      "warnings": n_align + n_gap, "screens": report}))
    return 1 if a.fail else 0


if __name__ == "__main__":
    sys.exit(main())
