"""rbx_looks.py — LOOKS: a real surface's whole recipe as a.material() keywords (kit/materials/looks.json). Plain
python (the test suite reads it without Blender).

    a.material("stock", **rbx.look("walnut_wood"), life="used")
    a.material("door", **rbx.look("powder_coat", color=(0.30, 0.05, 0.04)), life="light")
    a.material("cut", **rbx.look("end_grain"), grain=(0, 1, 0))

A look = its base values (a kit finish, a measured material, a scan's measured mean, or a labelled estimate — every
look says which: looks()), the scan that breaks it up, its micro-pattern at real size, how much its colour varies
(vary=), which grime it shows. Any keyword given to look() replaces the look's own (color= for a paint, rough=, vary=,
scan_mix= ...). The object's LIFE is a.material's: life="new|light|used|heavy" wears the look as its class.
"""

import json
import os

import rbx_materials
import rbx_pbr

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "materials", "looks.json")
KEYS = ("color", "metal", "rough", "scan", "scan_mix", "relief", "pattern", "pattern_mm", "pattern_depth", "vary",
        "grime_tone", "satin", "under", "scan_grain", "scan_color",   # (under: what wear chips through to)
        "layers")   # (the surface's own layers, rbx_layers: plain dicts - a.material checks them)
_CACHE = {}


def _all():
    if "looks" not in _CACHE:
        with open(PATH, encoding="utf-8") as fh:
            _CACHE["looks"] = json.load(fh)["looks"]
    return _CACHE["looks"]


def look(name, **override):
    """a look's a.material() keywords (finish= rides along so life= wears it as that finish's class)"""
    looks = _all()
    if name not in looks:
        raise KeyError(f'look "{name}" — use one of {", ".join(sorted(looks))}')
    spec = dict(looks[name])
    out = {}
    if "finish" in spec:
        out.update(rbx_pbr.finish(spec["finish"]))
        out["finish"] = spec["finish"]
    elif "real" in spec:
        r = rbx_materials.real(spec["real"])
        out.update({"color": tuple(r["color"]), "metal": float(r["metal"]), "rough": float(r["rough"])})
    for k in KEYS:
        if k in spec:
            out[k] = tuple(spec[k]) if k in ("color", "under") else spec[k]
    bad = [k for k in override if k not in KEYS and k != "finish"]
    if bad:
        raise TypeError(f"look: {', '.join(bad)} is not a look's key — pass it to a.material itself")
    out.update({k: (tuple(v) if k == "color" else v) for k, v in override.items()})
    out["color"] = tuple(float(c) for c in out["color"][:3])
    return out


def looks():
    """[(name, about, source)] — every look"""
    return [(n, s.get("about", ""), s.get("source", "")) for n, s in sorted(_all().items())]


def _main(argv):
    """kit materials --looks [query]: every look (or those whose name / about matches), with its values and source"""
    q = " ".join(argv).lower().strip()
    rows = []
    for name, about, source in looks():
        if q and q not in name and q not in about.lower():
            continue
        kw = look(name)
        rows.append({"name": name, "about": about, "source": source, "color": list(kw["color"]), "metal": kw["metal"],
                     "rough": kw["rough"], "scan": kw.get("scan"), "pattern": kw.get("pattern"),
                     "vary": kw.get("vary", 0.0)})
    print(json.dumps({"schema": 1, "status": "pass" if rows else "fail",
                      "summary": f"looks: {len(rows)} real surface recipe(s)" + (f' matching "{q}"' if q else ""),
                      "next_action": 'a.material("<name>", **rbx.look("<look>"), life="used")  (any key: '
                                     'rbx.look("<look>", color=..., rough=...))' if rows else
                                     "lune run kit materials --looks (all of them)", "looks": rows}))
    return 0 if rows else 1


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv[1:]))
