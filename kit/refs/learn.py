"""learn.py — the kit LEARNS from the reference models it dissects (kit library inspect): what real models of a
category do, as numbers with their sources, so builds and checks stop guessing.

    python kit/refs/learn.py add <refs/<name>.inspect.json> --category firearm [--roles "Trigger1=hammer, ..."]
    python kit/refs/learn.py remove <name> --category firearm
    python kit/refs/learn.py show <category> [--group role:slide]
    python kit/refs/learn.py compare <refs/<asset>.inspect.json> --category firearm   (our build vs real models)

kit/learned/<category>.json keeps every SAMPLE (a value, the model and part it came from, its weight) so a model can be
added or removed and every range recomputed. Groups: all, role:<slide|grip|pin|spring|...> (from the part's name —
names can lie: --roles fixes them after looking at the tiles), kind:<pin|spring|flat|block|rod>, and
material:<dark_metal|bright_metal|wood|polymer|other>. A range = the 10th / 50th / 90th percentile with EACH MODEL
COUNTING ONCE (a 400-part model does not outvote a 20-part one).

Read it from a build: rbx.learned("firearm", "bevel_size_mm", "role:slide") -> the typical value (kit/blender).
"""

import datetime
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
STORE = os.path.join(REPO, "kit", "learned")

# a part's role from its name's words, most specific first ("Magazine_spring" is a spring, "Grip_screw" a screw)
ROLES = ["spring", "pin", "screw", "sight", "safety", "trigger", "hammer", "sear", "disconnector", "extractor",
         "ejector", "follower", "catch", "link", "bushing", "guide", "plug", "stop", "housing", "baffle", "suppressor",
         "can", "muzzle", "grip", "slide", "bolt", "barrel", "frame", "receiver", "magazine", "stock", "handguard",
         "rail", "scope", "case", "bullet", "primer", "round"]

# metric -> (read it from a part, weigh it, the side that is a PROBLEM in a build ("below" / "above" / "both" / None:
# for information only), the groups it is compared by ("role": the part's job — geometry; "material": its finish —
# surface), what to do about a gap)
METRICS = {
    "bevel_size_mm": (lambda p: _g(p, "edges", "bevel_size_mm", "typical"), lambda p: _g(p, "edges", "bevel_mm") or 1,
                      "both", "role", "round its edges to the real size (a.cad round_edges / a.box bevel=)"),
    "bevelled_share": (lambda p: _g(p, "edges", "bevelled_share"),
                       lambda p: (_g(p, "edges", "bevel_mm") or 0) + (_g(p, "edges", "sharp_mm") or 0) or 1,
                       "below", "role", "bevel more of its hard edges"),
    "chamfer_share": (lambda p: _g(p, "edges", "chamfer_share"), lambda p: _g(p, "edges", "bevel_mm") or 1,
                      None, "role", ""),
    "faces_per_cm2": (lambda p: _g(p, "surface", "faces_per_cm2"), lambda p: 1, None, "role", ""),
    "surface_noise_deg": (lambda p: _g(p, "surface", "noise_deg"), lambda p: 1, None, "role", ""),
    "texel_px_per_mm": (lambda p: _g(p, "uv_layout", "px_per_mm"), lambda p: 1, "below", "role",
                        "give it more texture pixels (a bigger map or a bigger UV island)"),
    # (seams on HARD edges: what a low-poly game model does — a hero master with real bevels has few hard edges, so it
    # is for information; the seams that SHOW are the ones across a flat face)
    "seams_on_hard_edges": (lambda p: _g(p, "uv_layout", "seams_on_hard_edges"), lambda p: _g(p, "uv_layout", "seam_mm") or 1,
                            None, "role", ""),
    "seams_across_flats": (lambda p: _g(p, "uv_layout", "seams_across_flats"), lambda p: _g(p, "uv_layout", "seam_mm") or 1,
                           "above", "role", "move its UV seams off its flat faces, onto its corners"),
    "facet_sag_mm": (lambda p: _g(p, "edges", "facet_sag_mm"), lambda p: _g(p, "edges", "facet_mm") or 1,
                     "above", "role", "more segments on its curves (they show as polygons)"),
    "uv_stretched_share": (lambda p: _g(p, "uv_layout", "stretched_share"), lambda p: 1, "above", "role",
                           "unwrap it again: its texture stretches"),
    "detail_strength_deg": (lambda p: _g(p, "baked_detail", "strength_deg"), lambda p: 1, "both", "material",
                            "match the strength of the detail its normal map carries"),
    "detail_share": (lambda p: _g(p, "baked_detail", "detail_share"), lambda p: 1, "both", "material",
                     "match how much of its surface carries baked detail"),
    "pattern_pitch_mm": (lambda p: _g(p, "baked_detail", "pattern", "pitch_mm") if _g(p, "baked_detail", "pattern", "found") else None,
                         lambda p: 1, "both", "role", "a pattern (checkering, knurling) at the real pitch"),
    "relief_mm": (lambda p: _g(p, "baked_detail", "relief_mm") if (_g(p, "baked_detail", "detail_share") or 0) >= 0.05 else None,
                  lambda p: 1, "both", "role", "its detail's depth to the real relief"),
    "roughness": (lambda p: _mid(_g(p, "colour_wear", "roughness_range")) if _g(p, "colour_wear", "roughness_range") else _mat(p, "roughness"),
                  lambda p: 1, "both", "material", "its finish's roughness"),
    "metallic": (lambda p: _mid(_g(p, "colour_wear", "metallic_range")) if _g(p, "colour_wear", "metallic_range") else _mat(p, "metallic"),
                 lambda p: 1, "both", "material", "its metalness"),
    "brightness_spread": (lambda p: _g(p, "colour_wear", "brightness_spread"), lambda p: 1, "both", "material",
                          "the colour variation across it (grain, wear, grime)"),
    "edge_wear": (lambda p: _g(p, "colour_wear", "edge_wear"), lambda p: 1, "both", "material",
                  "the wear on its outward edges"),
    "grime": (lambda p: _g(p, "colour_wear", "grime"), lambda p: 1, "both", "material", "the grime in its recesses"),
}


def _g(d, *keys):
    for k in keys:
        if not isinstance(d, dict) or d.get(k) is None:
            return None
        d = d[k]
    return d


def _mid(r):
    return (r[0] + r[1]) / 2 if r else None


def _mat(p, key):
    m = (p.get("material") or [{}])[0]
    return m.get(key) if isinstance(m.get(key), (int, float)) else None


def tokens(name):
    return [t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def role(name, fixes=None):
    if fixes and name in fixes:
        return fixes[name]
    toks = tokens(name)
    for r in ROLES:
        if r in toks:
            return r
    return None


def material_class(p):
    """dark_metal (blued / parkerised / black), bright_metal (stainless, nickel, bare), wood, polymer, other"""
    cw = p.get("colour_wear") or {}
    rgb = cw.get("colour_mean")
    if rgb is None:
        hexc = (p.get("material") or [{}])[0].get("base_srgb")
        rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)] if hexc else None
    if rgb is None:
        return "other"
    metal = METRICS["metallic"][0](p)
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    mx, mn = max(rgb), min(rgb)
    sat = (mx - mn) / mx if mx > 0 else 0.0
    if sat > 0.35 and rgb[0] >= rgb[1] >= rgb[2] and (metal is None or metal < 0.5):
        return "wood"
    if metal is not None and metal >= 0.5:
        return "bright_metal" if lum > 0.35 else "dark_metal"
    if lum < 0.25:
        return "dark_metal" if metal is None else "polymer"
    return "bright_metal" if metal is None and lum > 0.45 and sat < 0.15 else "other"


def _load(cat):
    """a category's knowledge (kit/learned/<cat>.json) — or a knowledge FILE given by its path (a selftest's own)"""
    path = cat if str(cat).endswith(".json") else os.path.join(STORE, f"{cat}.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"category": cat, "models": {}, "samples": {}}


def _save(cat, data):
    os.makedirs(STORE, exist_ok=True)
    with open(os.path.join(STORE, f"{cat}.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


def _groups(p, fixes):
    g = ["all", f"kind:{p.get('kind')}", f"material:{material_class(p)}"]
    r = role(p["name"], fixes)
    if r:
        g.append(f"role:{r}")
    return g


def samples_of(inspection, fixes=None):
    """-> {metric: {group: [[value, weight, part]]}} for one dissected model"""
    out = {}
    for p in inspection.get("parts", []):
        for metric, (read, weigh, *_rest) in METRICS.items():
            v = read(p)
            if v is None:
                continue
            for g in _groups(p, fixes):
                out.setdefault(metric, {}).setdefault(g, []).append([float(v), float(weigh(p)), p["name"]])
    return out


def _source(inspection):
    """the library record of a downloaded model (its licence and attribution), when there is one"""
    src = inspection.get("source") or ""
    meta = os.path.join(os.path.dirname(src), "model.json")
    if os.path.isfile(meta):
        with open(meta, encoding="utf-8") as fh:
            m = json.load(fh)
        return {"title": m.get("title"), "licence": m.get("license") or m.get("licence"),
                "attribution": m.get("attribution")}
    return {"file": src}


def add(path, cat, fixes=None):
    with open(path, encoding="utf-8") as fh:
        ins = json.load(fh)
    data = _load(cat)
    name = ins["name"]
    remove_model(data, name)
    data["models"][name] = {"added": datetime.date.today().isoformat(), "parts": len(ins.get("parts", [])),
                            **_source(ins), "roles_fixed": fixes or {}}
    for metric, groups in samples_of(ins, fixes).items():
        for g, rows in groups.items():
            data["samples"].setdefault(metric, {}).setdefault(g, []).extend([[v, w, name, part] for v, w, part in rows])
    _save(cat, data)
    return data


def remove_model(data, name):
    data["models"].pop(name, None)
    for groups in data["samples"].values():
        for g in list(groups):
            groups[g] = [r for r in groups[g] if r[2] != name]
            if not groups[g]:
                del groups[g]


def rng(rows):
    """weighted 10th / 50th / 90th percentile, each model's weights scaled to count once"""
    per = {}
    for v, w, model, *_ in rows:
        per[model] = per.get(model, 0.0) + w
    pts = sorted((v, w / per[m]) for v, w, m, *_ in rows if per[m] > 0)
    tot = sum(w for _, w in pts)
    if not pts or tot <= 0:
        return None

    def q(f):
        acc = 0.0
        for v, w in pts:
            acc += w
            if acc >= f * tot:
                return v
        return pts[-1][0]

    return {"low": round(q(0.1), 4), "typical": round(q(0.5), 4), "high": round(q(0.9), 4), "models": len(per),
            "parts": len(rows)}


def learned(cat, metric, group="all", stat="typical"):
    """the learned value for a build (None when nothing is known)"""
    r = rng(_load(cat)["samples"].get(metric, {}).get(group, []))
    return r[stat] if r else None


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def _arg(argv, key, default=None):
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


def _fixes(argv):
    raw = _arg(argv, "--roles")
    if not raw:
        return None
    return {a.strip(): b.strip().lower() for a, b in (x.split("=", 1) for x in raw.split(",") if "=" in x)}


def compare(path, cat):
    """our build against the learned ranges, per part role (geometry) and finish (surface): only the side that is a
    problem, the biggest gap first, each with what to do. Only where 2+ real models agree (one model is a hint), and a
    gap is measured against at least a quarter of the typical value."""
    with open(path, encoding="utf-8") as fh:
        ins = json.load(fh)
    data = _load(cat)
    ours = samples_of(ins)
    gaps = []
    for metric, (_, _, side, by, fix) in METRICS.items():
        if side is None:
            continue
        for g, rows in ours.get(metric, {}).items():
            if not (g == "all" or g.startswith(by + ":")):
                continue
            real = rng(data["samples"].get(metric, {}).get(g, []))
            mine = rng([[v, w, "ours", p] for v, w, p in rows])
            if not real or not mine or real["models"] < 2:  # one model is a hint, not what real models DO
                continue
            width = max(real["high"] - real["low"], abs(real["typical"]) * 0.25, 0.02)
            if mine["typical"] < real["low"] and side in ("below", "both"):
                gaps.append(((real["low"] - mine["typical"]) / width, metric, g, "below", mine, real, fix))
            elif mine["typical"] > real["high"] and side in ("above", "both"):
                gaps.append(((mine["typical"] - real["high"]) / width, metric, g, "above", mine, real, fix))
    gaps.sort(key=lambda x: -x[0])
    rows = [f"  {m:<20} {g:<20} yours {mine['typical']:<8g} real {real['low']:g}..{real['high']:g} ({real['models']} "
            f"model(s)) {side}: {fix}" for _, m, g, side, mine, real, fix in gaps]
    return gaps, rows


def main(argv):
    if not argv or argv[0] not in ("add", "remove", "show", "compare"):
        return emit("fail", "learn: needs add | remove | show | compare", "lune run kit learn <inspection> --category firearm")
    cmd, rest = argv[0], argv[1:]
    cat = _arg(rest, "--category") or (rest[0] if cmd == "show" and rest else None)
    if not cat:
        return emit("fail", f"learn {cmd}: needs --category <name>", "e.g. --category firearm")
    if cmd == "add":
        if not rest or not os.path.isfile(rest[0]):
            return emit("fail", f"learn add: no inspection file {rest[:1]}", "lune run kit library inspect ... first")
        data = add(rest[0], cat, _fixes(rest))
        n = sum(len(rows) for groups in data["samples"].values() for rows in groups.values())
        return emit("pass", f"learn: {os.path.basename(rest[0])} added to {cat} — {len(data['models'])} model(s), {n} "
                    "sample(s)", f"lune run kit learned show {cat}")
    if cmd == "remove":
        data = _load(cat)
        remove_model(data, rest[0])
        _save(cat, data)
        return emit("pass", f"learn: {rest[0]} removed from {cat}", f"lune run kit learned show {cat}")
    if cmd == "show":
        data = _load(cat)
        want = _arg(rest, "--group")
        rows = [f"  {cat}: {len(data['models'])} model(s): " + ", ".join(data["models"])]
        for metric in METRICS:
            for g, samples in sorted(data["samples"].get(metric, {}).items()):
                if (want and g != want) or (not want and not (g == "all" or g.startswith("role:"))):
                    continue
                r = rng(samples)
                if r:
                    rows.append(f"  {metric:<22} {g:<20} typical {r['typical']:<8g} ({r['low']:g}..{r['high']:g})  "
                                f"{r['models']} model(s), {r['parts']} part(s)")
        return emit("pass", f"learned {cat}: {len(data['models'])} model(s)", "use it: rbx.learned(...) in a build; "
                    f"lune run kit learned compare <inspection> --category {cat}", rows=rows)
    gaps, rows = compare(rest[0], cat)
    return emit("pass", f"learned compare: {len(gaps)} gap(s) against {cat}", "close the biggest gap first" if gaps
                else "none — within the real range on everything measured", rows=rows,
                gaps=[{"metric": m, "group": g, "side": s, "yours": mine["typical"], "real": real, "fix": fx}
                      for _, m, g, s, mine, real, fx in gaps])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
