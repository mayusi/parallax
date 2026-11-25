"""rbx_sizes.py — is the model the size its KIND is in the real world? (kit/real_sizes.json)

A chair built 6 studs tall passes every mesh gate, and its own size target too when the target was the mistake.
Asset(kind="chair") says what the object is; this compares its measured size with the range real ones come in. The
ranges were read from Infinigen's procedural asset factories (princeton-vl/infinigen, BSD-3-Clause: numbers only, every
row links the lines it came from) and become studs through the asset's real_scale(), or Roblox's own unit (1 stud =
0.28 m). Real objects stray (a throne is a chair), so the check WARNS, past a leeway, and never fails a build.
No bpy: kit/test/python/test_real_sizes.py runs it as plain python.
"""

import json
import os

TABLE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "real_sizes.json"))
_loaded = {}


def load(path=TABLE):
    """the size table (read once per path)"""
    if path not in _loaded:
        with open(path, encoding="utf-8") as fh:
            _loaded[path] = json.load(fh)
    return _loaded[path]


def kinds(table=None):
    return sorted((table or load())["kinds"])


def metres_per_stud(table, mm_per_stud=None):
    """the asset's own real_scale(), else Roblox's unit"""
    return float(mm_per_stud) / 1000.0 if mm_per_stud else float(table["stud_m"])


def source_name(row):
    """'Infinigen chair.py' — the files a row was read from, for a message"""
    names = [("Infinigen " if "/princeton-vl/infinigen/" in url else "") + url.split("#")[0].rsplit("/", 1)[-1]
             for url in row.get("source") or []]
    return ", ".join(names) or "no source"


def measures(row, size, m):
    """[(name, measured metres, (lo, hi) metres)]: the model's height, then its footprint smaller side first (the two
    horizontal sizes in any orientation: a bed built along X is still a bed)"""
    x, y, z = (float(v) * m for v in size)
    out = [("tall", y, tuple(row["height"]))] if row.get("height") else []
    for (name, lo, hi), v in zip(row.get("footprint") or [], sorted((x, z))):
        out.append((name, v, (lo, hi)))
    return out


def judge(size, kind, table=None, mm_per_stud=None):
    """size: the model's Roblox (x, y, z) in studs -> (ok, fix, fact); ok is None when the kind is not in the table"""
    t = table or load()
    row = t["kinds"].get(kind)
    if row is None:
        return (None, f'kind "{kind}" is not in kit/real_sizes.json (known: {", ".join(kinds(t))}) — name one of '
                      f"those, or add a row with its source", None)
    m = metres_per_stud(t, mm_per_stud)
    leeway = float(t.get("leeway", 0.25))
    unit = f"{m * 1000:.0f} mm a stud" + ("" if mm_per_stud else " (Roblox's unit)")
    ms = measures(row, size, m)
    fact = f"{kind}: " + ", ".join(f"{v:.2f} m {n} (real {lo:.2f}-{hi:.2f})" for n, v, (lo, hi) in ms) + f", at {unit}"
    worst, worst_ratio = None, 1.0
    for n, v, (lo, hi) in ms:
        if v > hi * (1 + leeway):
            ratio = v / hi
        elif v < lo * (1 - leeway):
            ratio = lo / max(v, 1e-9)
        else:
            continue
        if ratio > worst_ratio:
            worst, worst_ratio = (n, v, lo, hi), ratio
    if worst is None:
        return True, "", fact
    n, v, lo, hi = worst
    side = f"{v / hi:.2f}x the largest" if v > hi else f"{worst_ratio:.2f}x under the smallest"
    return (False,
            f"a {kind} is {lo:.2f}-{hi:.2f} m {n} ({lo / m:.1f}-{hi / m:.1f} studs at {unit}); this one is "
            f"{v / m:.2f} studs ({v:.2f} m), {side} — rescale it (and Asset(size=...)), or name the kind it really "
            f"is: {row['about']} (kit/real_sizes.json, from {source_name(row)})",
            fact)


def typical(kind, table=None, mm_per_stud=None):
    """the kind's middle size in studs as (x wide, y tall, z deep) — the footprint's larger side along X; None where
    the table leaves a size free — or None for a kind not in the table"""
    t = table or load()
    row = t["kinds"].get(kind)
    if row is None:
        return None
    m = metres_per_stud(t, mm_per_stud)
    fp = [round((lo + hi) / 2 / m, 1) for _, lo, hi in row.get("footprint") or []]
    tall = round(sum(row["height"]) / 2 / m, 1) if row.get("height") else None
    return (fp[1] if len(fp) > 1 else None, tall, fp[0] if fp else None)
