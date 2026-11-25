"""kit vfx migrate - the four legacy preset keys the v3 stage never reads, found and fixed (the V3 doc, VFX stage A.1).

The validator (src/kit/VfxValidate3.luau) WARNS on four things a v3 preset carries but the stage and the player never
play the way it reads (the 2026-10-23 audit): a sprite's `spreadAngle` (the cone key is `spread`: the layer emits a
needle), a fov layer's `fov` (the stage reads `delta`: the punch never plays), a shake's `frequency` (the noise runs
at a fixed rate) and a big opaque camera-facing card standing on the ground (it tilts back and lifts off the floor
when the camera looks up: `"orientation": "FacingCameraWorldUp"` keeps it standing). Warnings because switching them
on CHANGES A JUDGED LOOK.

    python kit/vfx/legacy.py [--effects <dir>] [<name> ...]            what each preset carries and the fix (writes nothing)
    python kit/vfx/legacy.py [--effects <dir>] --apply <name> ...      rewrite those presets (key order and layout kept)
    python kit/vfx/legacy.py [--effects <dir>] --identical [<name> ...]  ONLY the fixes that change nothing played
        (LIMITATIONS_FIXES_V4 3.4 step 4, "burn the warnings" where the meaning is identical): a shake's `frequency`
        dropped, a sprite's `spreadAngle` dropped where its `spread` is set, a fov layer's `fov` dropped where its
        `delta` is set - keys neither the stage nor the player reads (kit/test/python/test_vfx_legacy_identical.py
        holds that to their source). A rename or a card turned upright is never made here; judged pieces included,
        since nothing they show changes
        a preset the owner gave a verdict refuses unless --judged "<the owner's words>" says he wants it changed
    python kit/vfx/legacy.py --gate --effects <dir> --name <name>     (the build's, in Python: the build itself checks
        the validator's own warnings against kit/vfx/legacy_keys.json, see kit/lib/vfxlegacy.luau)

The fixes: spreadAngle -> spread (dropped where a `spread` is already there: the stage reads that one), fov -> delta
(likewise), frequency dropped, the big ground card gets "orientation": "FacingCameraWorldUp". The card rule is the
validator's, line for line (biggest size key, its bottom edge at or under y = 1, light emission under 0.5, no
orientation or FacingCamera); kit/test/python/test_vfx_legacy.py holds it to the validator on the same fixtures.
Prints one JSON line last: {"status", "summary", "next_action", "presets": [...]}.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameroot  # noqa: E402

FIXES = ("spreadAngle", "fov", "frequency", "orientation")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _vec(x):
    return isinstance(x, list) and len(x) == 3 and all(_num(v) for v in x)


def big_ground_card(el, points):
    """VfxValidate3's rule (kind == "sprite"): a card >= 40 studs, its bottom at or under the floor, opaque, facing
    the camera freely"""
    biggest = 0
    size = el.get("size")
    if _num(size):
        biggest = size
    elif isinstance(size, list):
        for kv in size:
            if isinstance(kv, list) and len(kv) >= 2 and _num(kv[1]):
                biggest = max(biggest, kv[1])
    pt = el.get("point")
    if isinstance(pt, str) and isinstance(points, dict):
        pt = points.get(pt)
    on_ground = _vec(pt) and pt[1] - biggest / 2 <= 1
    le = el.get("lightEmission")
    opaque = not _num(le) or le < 0.5
    return biggest >= 40 and on_ground and opaque and el.get("orientation") in (None, "FacingCamera")


def hits(preset):
    """every legacy key in a preset -> [{"path", "key", "fix"}] (paths as the file is laid out: layers[3].fov)"""
    out = []
    points = preset.get("points") if isinstance(preset, dict) else None

    def walk(x, path):
        if isinstance(x, dict):
            kind = x.get("kind")
            if "spreadAngle" in x and kind == "sprite":
                out.append({"path": f"{path}.spreadAngle", "key": "spreadAngle",
                            "fix": "drop (spread is set)" if "spread" in x else "rename to spread"})
            if kind == "fov" and "fov" in x:
                out.append({"path": f"{path}.fov", "key": "fov",
                            "fix": "drop (delta is set)" if "delta" in x else "rename to delta"})
            if kind == "shake" and "frequency" in x:
                out.append({"path": f"{path}.frequency", "key": "frequency", "fix": "drop"})
            if kind == "sprite" and big_ground_card(x, points):
                out.append({"path": f"{path}.orientation", "key": "orientation",
                            "fix": 'set "FacingCameraWorldUp"'})
            for k, v in x.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i + 1}]")  # 1-based, as the validator names layers
    walk(preset, "")
    return out


def _renamed(d, old, new):
    """d with key old renamed to new IN PLACE of it (the file's key order kept), or dropped when new is there"""
    if new in d:
        return {k: v for k, v in d.items() if k != old}
    return {(new if k == old else k): v for k, v in d.items()}


def migrated(preset, identical=False):
    """the preset with every fix applied (a new object; the original is untouched); identical: only the drops of keys
    nothing reads"""
    points = preset.get("points") if isinstance(preset, dict) else None

    def fix(x):
        if isinstance(x, dict):
            kind = x.get("kind")
            if "spreadAngle" in x and kind == "sprite" and (not identical or "spread" in x):
                x = _renamed(x, "spreadAngle", "spread")
            if kind == "fov" and "fov" in x and (not identical or "delta" in x):
                x = _renamed(x, "fov", "delta")
            if kind == "shake" and "frequency" in x:
                x = {k: v for k, v in x.items() if k != "frequency"}
            if kind == "sprite" and not identical and big_ground_card(x, points):
                x = dict(x)
                x["orientation"] = "FacingCameraWorldUp"
            return {k: fix(v) for k, v in x.items()}
        if isinstance(x, list):
            return [fix(v) for v in x]
        return x
    return fix(preset)


def judged():
    """the effects the owner gave a verdict: the vault's verdict notes and the library's record"""
    names = set()
    vd = os.path.join("kit", "knowledge", "vault", "vfx", "verdicts")
    if os.path.isdir(vd):
        for f in os.listdir(vd):
            if f.endswith(".md") and "--" in f:
                names.add(f.split("--")[0].replace("-", "_"))
    try:
        names.update(json.load(open(os.path.join("library", "vfx", "verdicts.json"), encoding="utf-8")).keys())
    except (OSError, ValueError, AttributeError):
        pass
    return names


# --- the rewrite: span-exact text edits, so a preset keeps its own layout (most keep one layer per line: a JSON dump
# would turn every file into a whole-file diff of the owner's pieces) -----------------------------------------------

_WS = " \t\r\n"


def _skip(s, i):
    while i < len(s) and s[i] in _WS:
        i += 1
    return i


def _string_end(s, i):
    """s[i] == '"' -> the index just past the closing quote"""
    i += 1
    while s[i] != '"':
        i += 2 if s[i] == "\\" else 1
    return i + 1


def _node(s, i):
    """the JSON value at s[i] -> (node, end): an object is {"items": [(key, key_start, key_end, value_node)],
    "start", "end"}, a list {"list": [nodes], ...}, anything else {"start", "end"}"""
    i = _skip(s, i)
    c = s[i]
    if c == "{":
        items, j = [], _skip(s, i + 1)
        while s[j] != "}":
            ks = j
            ke = _string_end(s, j)
            key = json.loads(s[ks:ke])
            j = _skip(s, ke)
            assert s[j] == ":"
            val, j = _node(s, j + 1)
            items.append((key, ks, ke, val))
            j = _skip(s, j)
            if s[j] == ",":
                j = _skip(s, j + 1)
        return {"items": items, "start": i, "end": j + 1}, j + 1
    if c == "[":
        out, j = [], _skip(s, i + 1)
        while s[j] != "]":
            v, j = _node(s, j)
            out.append(v)
            j = _skip(s, j)
            if s[j] == ",":
                j = _skip(s, j + 1)
        return {"list": out, "start": i, "end": j + 1}, j + 1
    if c == '"':
        e = _string_end(s, i)
        return {"start": i, "end": e}, e
    j = i
    while j < len(s) and s[j] not in ",]}" + _WS:
        j += 1
    return {"start": i, "end": j}, j


def _edits(s, node, value, points, out, identical=False):
    """the text edits that migrate `value` (the parsed JSON at `node`) -> out: [(start, end, text)]"""
    if isinstance(value, dict):
        items = node["items"]
        kind = value.get("kind")

        def drop(idx):
            _, ks, _, v = items[idx]
            if idx + 1 < len(items):
                out.append((ks, items[idx + 1][1], ""))               # the pair, its comma and the space after
            elif idx > 0:
                out.append((items[idx - 1][3]["end"], v["end"], ""))  # the comma before, and the pair
            else:
                out.append((ks, v["end"], ""))

        def rename(idx, new):
            _, ks, ke, _ = items[idx]
            out.append((ks, ke, json.dumps(new)))

        names = [k for k, *_ in items]
        if "spreadAngle" in value and kind == "sprite" and (not identical or "spread" in value):
            i = names.index("spreadAngle")
            drop(i) if "spread" in value else rename(i, "spread")
        if kind == "fov" and "fov" in value and (not identical or "delta" in value):
            i = names.index("fov")
            drop(i) if "delta" in value else rename(i, "delta")
        if kind == "shake" and "frequency" in value:
            drop(names.index("frequency"))
        if kind == "sprite" and not identical and big_ground_card(value, points):
            if "orientation" in value:
                v = items[names.index("orientation")][3]
                out.append((v["start"], v["end"], '"FacingCameraWorldUp"'))
            elif items:
                end = items[-1][3]["end"]
                out.append((end, end, ', "orientation": "FacingCameraWorldUp"'))
            else:
                out.append((node["start"] + 1, node["start"] + 1, '"orientation": "FacingCameraWorldUp"'))
        for (k, _, _, v), sub in zip(items, value.values()):
            _edits(s, v, sub, points, out, identical)
    elif isinstance(value, list):
        for v, sub in zip(node["list"], value):
            _edits(s, v, sub, points, out, identical)


def rewrite(text, identical=False):
    """the file's text with every fix made in place (nothing else in the file changes); checked: it parses to
    exactly migrated(the file)"""
    preset = json.loads(text)
    start = len(text) - len(text.lstrip("﻿"))
    node, _ = _node(text, start)
    edits = []
    _edits(text, node, preset, preset.get("points") if isinstance(preset, dict) else None, edits, identical)
    out = text
    for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:a] + rep + out[b:]
    if json.loads(out) != migrated(preset, identical):
        raise ValueError("the in-place rewrite does not parse to the migrated preset (nothing was written)")
    return out


def write(path, text, identical=False):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(rewrite(text, identical))


def identical_hits(preset):
    """the hits the --identical mode fixes: drops of keys nothing reads"""
    return [h for h in hits(preset) if h["fix"].startswith("drop")]


def emit(status, summary, next_action, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit vfx migrate")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--effects", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--judged", default=None, help="the owner's words: he wants a judged piece changed")
    ap.add_argument("--identical", action="store_true", help="only drop the keys nothing reads (no look changes)")
    a = ap.parse_args(argv)
    effects = a.effects or os.path.join(gameroot.game_root(), "assets", "effects")
    if not os.path.isdir(effects):
        return emit("fail", f"migrate: no effects folder {effects}", "run it in a kit project")
    names = a.names or sorted(f[:-5] for f in os.listdir(effects) if f.endswith(".json") and not f.startswith("_"))
    if a.identical:
        done, dropped = [], 0
        for n in names:
            path = os.path.join(effects, f"{n}.json")
            if not os.path.isfile(path):
                return emit("fail", f"migrate: no preset {path}", "lune run kit vfx migrate lists them")
            text = open(path, encoding="utf-8", newline="").read()
            try:
                preset = json.loads(text)
            except ValueError as e:
                return emit("fail", f"migrate: {n} is not JSON ({e})", f"fix {path}")
            found = identical_hits(preset)
            if found:
                write(path, text, identical=True)
                done.append(n)
                dropped += len(found)
        left = sum(len(hits(json.load(open(os.path.join(effects, f"{n}.json"), encoding="utf-8")))) for n in names)
        return emit("ok", f"migrate --identical: dropped {dropped} unread key(s) from {len(done)} preset(s); {left} "
                    "legacy key(s) left - each changes a look, so each waits for the owner (--apply <name>)",
                    "lune run kit verify (the preset warnings fall by the keys dropped)", presets=done)
    if a.apply and not a.names:
        return emit("fail", "migrate --apply: name the presets to rewrite (it changes how they look)",
                    "lune run kit vfx migrate (the report) first, then --apply <name> ...")
    owner_judged = judged()
    rows, refused, written = [], [], []
    for n in names:
        path = os.path.join(effects, f"{n}.json")
        if not os.path.isfile(path):
            return emit("fail", f"migrate: no preset {path}", "lune run kit vfx migrate lists them")
        text = open(path, encoding="utf-8", newline="").read()
        try:
            preset = json.loads(text)
        except ValueError as e:
            return emit("fail", f"migrate: {n} is not JSON ({e})", f"fix {path}")
        found = hits(preset)
        if not found:
            continue
        is_judged = n in owner_judged
        counts = {k: sum(1 for h in found if h["key"] == k) for k in FIXES}
        row = {"name": n, "judged": is_judged, "counts": {k: v for k, v in counts.items() if v}}
        if preset.get("use"):
            # (a part's layers are checked where they LAND - a card on a use's ground point is a ground card: the
            # build's own warnings for this preset name those; this file's own layers are all that is fixed here)
            row["composed"] = "its parts' layers are checked where they land: read lune run kit vfx " + n
        if a.apply:
            if is_judged and not (a.judged and a.judged.strip()):
                refused.append(n)
                row["refused"] = "the owner judged it: his words first (--judged)"
            else:
                write(path, text)
                written.append(n)
                row["written"] = True
        else:
            row["hits"] = found
        rows.append(row)
    total = {k: sum(r["counts"].get(k, 0) for r in rows) for k in FIXES}
    told = ", ".join(f"{v} {k}" for k, v in total.items() if v) or "none"
    if a.apply:
        if refused:
            return emit("fail", f"migrate: rewrote {len(written)}; refused {len(refused)} the owner judged "
                        f"({', '.join(refused)})", "show him each before / after; his words: --judged \"<them>\"",
                        presets=rows)
        return emit("ok", f"migrate: rewrote {len(written)} preset(s) ({told})",
                    "lune run kit vfx " + " ".join(written) + " (and look: the cone, the punch and the card now play)",
                    presets=rows)
    nj = sum(1 for r in rows if r["judged"])
    return emit("ok" if not rows else "warn",
                f"migrate: {len(rows)} preset(s) carry legacy keys ({told}); {nj} of them the owner judged",
                "nothing written; --apply <name> ... rewrites (it changes the look: record it and look first)"
                if rows else "nothing to do", presets=rows)


if __name__ == "__main__":
    sys.exit(main())
