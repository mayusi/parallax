"""kit/tools/pack.py — `lune run kit pack <asset> ...`: the asset's PACK, the one file every 3D module's result lands in
and every build reads from (in a build script: `pk = a.pack()`; kit/blender/rbx_pack.py).

Why: the kit's modules each wrote their own file and NOTHING joined them — a measured colour, a sourced size or a
reference model's grip slices reached a build only when someone copied the number in by hand, and mostly nobody did
(the Glock 17, 2026-10-08: every size typed into the script, no colour measured, one reference model). The pack is
that join: what the asset HAS is found by scanning (traces and their mm profiles, reference models, generated drafts,
colour pictures, fitted proportions — refreshed on every call), and what was CHOSEN is kept (the object and its real
length, each size with its source, each part's measured colour, the time each stage took).

    python kit/tools/pack.py <asset>                                    refresh + show (also: kit plan reads it)
    python kit/tools/pack.py <asset> object "<name>" [--length-mm L | --length dims:<id> | --length dossier]
                                                           [--category firearm]
    python kit/tools/pack.py <asset> size <part.dim> <mm | dims:<id> | dossier> [--source <url or note>]
      (dossier: the object's graded fact from kit dossier — A or B only)
    python kit/tools/pack.py <asset> colours --trace <trace> [--albedo <file.npz>]
    python kit/tools/pack.py <asset> time <stage> <seconds> [--what "<command>"]

assets/models/<asset>.pack.json:
  object   {name, length_mm, category, source}
  sizes    {"<part>.<dim>": {mm, source, trust, row}}          a size from the object's dossier (graded), a
                                                                kit/real_specs row (dims:<id>) or given
  colours  {"<part>": {srgb, rough, metal, pixels, albedo, trace}}   each traced part's MEDIAN colour, roughness and
           metalness inside its own mask on `kit vision albedo`'s lighting-free picture (Marigold-IID)
  found    (scanned, replaced every refresh) traces {name: view, source photo|model, picture, parts, profiles}, models
           {name: measure, inspect}, drafts {name: record, glb, engine, silhouette_iou}, albedo [npz], params
  timings  [{stage, what, seconds, at}]
One JSON verdict line last.
"""

import datetime
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
VIEWS = {"side": "side", "front": "front", "back": "back", "top": "top", "bottom": "top", "left": "side_left",
         "frontview": "front", "backview": "back"}
# a reference MODEL's outline: kit refs measure's mask (build/refs/<name>_<view>_mask.png) or a dissected library
# model's part render (build/library/...) — a downloaded photo lives in a search's own folder (build/refs/<search>/)
MODEL_SOURCE = re.compile(r"^build/(refs/[^/]+_mask\.png|library/.+)$")
UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _rel(root, p):
    return os.path.relpath(p, root).replace("\\", "/")


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def pack_path(asset, root=ROOT):
    return os.path.join(root, "assets", "models", f"{asset}.pack.json")


def load(asset, root=ROOT):
    d = _json(pack_path(asset, root))
    if not isinstance(d, dict):
        d = {}
    d.setdefault("schema", 1)
    d["asset"] = asset
    for k in ("sizes", "colours", "found"):
        d.setdefault(k, {})
    d.setdefault("object", {})
    d.setdefault("timings", [])
    return d


def inputs_sha(data):
    """16 hex over what was CHOSEN that a build reads (the object, the sizes, the colours) — a refresh, a scan or a
    timing never changes it, a new colour or size does. Builds fold it into their identity (rbx_score.build_identity,
    learn.luau buildSha): the same script with other pack values is another model."""
    import hashlib  # noqa: PLC0415

    chosen = {k: data.get(k) or {} for k in ("object", "sizes", "colours")}
    if not any(chosen.values()):
        return None  # (nothing chosen: a pack that only lists what the asset HAS is no build input)
    return hashlib.sha256(json.dumps(chosen, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def file_sha(path):
    """16 hex of a file's bytes (a trace's: a look is stale once it is traced again) or None"""
    import hashlib  # noqa: PLC0415

    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except OSError:
        return None


def save(asset, data, root=ROOT):
    data["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sha = inputs_sha(data)
    if sha:
        data["inputs_sha"] = sha
    else:
        data.pop("inputs_sha", None)
    path = pack_path(asset, root)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    return path


# ==================================================================== what the asset HAS (scanned)
def _view_of(stem, asset, t):
    words = stem.split("_")
    v = t.get("view") if isinstance(t, dict) else None
    if not v:
        v = VIEWS.get(stem[len(asset) + 1:]) or VIEWS.get(words[-1])
        if words[-1] == "left" and len(words) > 1 and VIEWS.get(words[-2]) == "side":
            v = "side_left"
    return v


def scan(asset, root=ROOT):
    """-> what the asset's files hold, by the kit's own naming: assets/models/<asset>_*.trace.json (+ .profiles.json),
    reference models measured / inspected under its name or cited by its script / brief / parts answers, generated
    drafts (<asset>*.gen.json / .parts.json), lighting-free colour pictures (*.albedo.npz of its traced pictures),
    fitted proportions (<asset>.params.json)"""
    models = os.path.join(root, "assets", "models")
    found = {"traces": {}, "models": {}, "drafts": {}, "albedo": [], "params": None}
    pictures = set()
    for path in sorted(glob.glob(os.path.join(models, f"{asset}_*.trace.json"))):
        t = _json(path)
        if not isinstance(t, dict):
            continue
        stem = os.path.basename(path)[:-len(".trace.json")]
        prof = path[:-len(".trace.json")] + ".profiles.json"
        pic = t.get("source") or t.get("image")
        src = "model" if MODEL_SOURCE.match(str(t.get("source", "")).replace("\\", "/")) else "photo"
        parts = t.get("parts") if isinstance(t.get("parts"), dict) else {}
        found["traces"][stem] = {"view": _view_of(stem, asset, t), "source": src, "picture": pic,
                                 "parts": sorted(parts.keys()),
                                 "profiles": _rel(root, prof) if os.path.isfile(prof) else None}
        if pic and src == "photo":
            pictures.add(os.path.normpath(os.path.join(root, pic)))
    texts = []
    for rel in (f"assets/models/build_{asset}.py", f"assets/models/{asset}.brief.md", f"assets/models/{asset}.parts.md",
                f"refs/{asset}.spec.json"):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                texts.append(fh.read())
        except OSError:
            pass
    names = set()
    for t in texts:
        names.update(re.findall(r"refs/(?:private/[\w-]+/|private/)?([\w.-]+?)\.(?:measure|inspect)\.json", t))
        names.update(re.findall(r"\bmeasure\(\s*[\"']([\w.-]+)[\"']", t))
        names.update(re.findall(r"build/library/([\w.-]+)/", t))
    for kind in ("measure", "inspect"):
        for p in glob.glob(os.path.join(root, "refs", "**", f"{asset}*.{kind}.json"), recursive=True):
            names.add(os.path.basename(p)[:-len(f".{kind}.json")])
    for n in sorted(names):
        if n.endswith("_build"):
            continue  # (an inspection of the asset's own build is no reference)
        entry = {}
        for kind in ("measure", "inspect"):
            hits = glob.glob(os.path.join(root, "refs", "**", f"{n}.{kind}.json"), recursive=True)
            entry[kind] = _rel(root, hits[0]) if hits else None
        if entry["measure"] or entry["inspect"]:
            found["models"][n] = entry
    for pat in (f"{asset}*.gen.json", f"{asset}*.parts.json"):
        for p in sorted(glob.glob(os.path.join(models, pat))):
            rec = _json(p) or {}
            name = os.path.basename(p).rsplit(".", 2)[0]
            glb = p[:-len(".json")] + ".glb"
            found["drafts"][name] = {"record": _rel(root, p), "glb": _rel(root, glb) if os.path.isfile(glb) else None,
                                     "engine": rec.get("engine") or rec.get("model"),
                                     "silhouette_iou": rec.get("silhouette_iou")}
    for p in sorted(set(glob.glob(os.path.join(models, f"{asset}*.albedo.npz")) +
                        glob.glob(os.path.join(root, "refs", "**", "*.albedo.npz"), recursive=True) +
                        glob.glob(os.path.join(root, "build", "vision", "*.albedo.npz")))):
        src = _npz_source(p)
        if src and os.path.normpath(os.path.join(root, src)) in pictures or os.path.basename(p).startswith(asset):
            found["albedo"].append(_rel(root, p))
    params = os.path.join(models, f"{asset}.params.json")
    found["params"] = _rel(root, params) if os.path.isfile(params) else None
    return found


def _npz_source(path):
    try:
        import numpy as np  # noqa: PLC0415
        with np.load(path) as z:
            return json.loads(str(z["meta"])).get("source") if "meta" in z.files else None
    except Exception:  # noqa: BLE001  (an unreadable file is simply not a colour picture of this asset)
        return None


def refresh(asset, root=ROOT):
    data = load(asset, root)
    data["found"] = scan(asset, root)
    return data


# ==================================================================== what was CHOSEN
def dims_row(row_id, root=ROOT):
    """a kit/real_specs row by its id -> the row (+ 'file'), or None"""
    for path in sorted(glob.glob(os.path.join(root, "kit", "real_specs", "*.json"))):
        rows = _json(path)
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and str(r.get("id")) == row_id:
                return {**r, "file": _rel(root, path)}
    return None


def withdrawn_why(row):
    """why the row's object's DOSSIER withdrew this row (added wrong), or None"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "refs"))
    import dossier  # noqa: PLC0415

    try:
        d = dossier.load(str(row.get("object") or ""))
    except dossier.Missing:
        return None  # (no dossier: nothing withdrew it)
    except Exception as e:  # noqa: BLE001 — a broken dossier cannot say it did not
        return f"the dossier of '{row.get('object')}' cannot be read ({e}): fix it first"
    w = (d.get("withdrawn_rows") or {}).get(str(row.get("id")))
    if not w:
        return None
    return f"withdrawn from the dossier of '{row.get('object')}' ({(w or {}).get('why') or 'no reason given'})"


def dossier_size(obj, key=None):
    """a size from the object's DOSSIER (kit/refs/dossier.py), graded A or B only — C is one unconfirmed source, D a
    disagreement: neither sizes a build. key None = the object's real length (its category's frame)."""
    if not obj:
        raise ValueError("no object chosen yet: kit pack <asset> object \"<name>\" --length dossier")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "refs"))
    import dossier  # noqa: PLC0415

    s = dossier.summary_for(obj, offline=True)
    if s is None:
        raise ValueError(f"no dossier for '{obj}' (lune run kit dossier new \"{obj}\" --category <kind>)")
    key = (key or (s.get("frame") or {}).get("length", {}).get("key") or "overall.length").lower()
    f = s["facts"].get(key)
    if not f or f.get("value") is None:
        raise ValueError(f"the dossier of '{obj}' has no {key} (it has: {', '.join(list(s['facts'])[:8]) or 'none'})")
    if f["grade"] not in ("A", "B"):
        raise ValueError(f"the dossier's {key} is grade {f['grade']} ({f['why']}) — only A / B size a build: "
                         f"lune run kit dossier \"{obj}\"")
    unit = str(f.get("unit", "mm")).lower()
    if unit not in UNIT_MM:
        raise ValueError(f"the dossier's {key} is in {unit}, not a length")
    return {"mm": round(float(f["value"]) * UNIT_MM[unit], 3), "source": f"dossier:{s['slug']}:{key}",
            "trust": "high" if f["grade"] == "A" else "medium", "grade": f["grade"], "row": f["why"]}


def resolve_size(value, root=ROOT, source=None, obj=None, key=None):
    """'186' / '186 mm' / '7.3 in' / 'dims:<id>' / 'dossier' (the object's graded fact for this key) -> {mm, source,
    trust, row}; raises ValueError with what to do"""
    v = str(value).strip()
    if v == "dossier":
        return dossier_size(obj, key)
    if v.startswith("dims:"):
        row = dims_row(v[5:], root)
        if row is None:
            raise ValueError(f"no kit/real_specs row {v} (lune run kit refs dims find \"<object> <part>\" lists them)")
        gone = withdrawn_why(row)
        if gone:
            raise ValueError(f"{v} sizes nothing: {gone} — lune run kit dossier \"{row.get('object')}\"")
        unit = str(row.get("unit", "mm")).lower()
        if unit not in UNIT_MM:
            raise ValueError(f"{v} is in {unit}, not a length")
        if float(row["value"]) <= 0:
            raise ValueError(f"{v} holds {row['value']} {unit}: no size")
        return {"mm": round(float(row["value"]) * UNIT_MM[unit], 3), "source": v, "trust": row.get("trust"),
                "row": f"{row.get('object')} · {row.get('part')} · {row.get('dim')} ({row.get('kind')}: "
                       f"{row.get('source')})"}
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch)?", v, re.IGNORECASE)
    if not m:
        raise ValueError(f"'{value}' is not a size: give mm (186), a unit (7.3 in) or a sourced row (dims:<id>)")
    mm = float(m.group(1)) * UNIT_MM[(m.group(2) or "mm").lower()]
    if mm <= 0:
        raise ValueError(f"'{value}' is no size (it must be over 0)")
    return {"mm": round(mm, 3), "source": source or "given", "trust": "medium" if source else "unsourced", "row": None}


def part_colours(trace_path, albedo_path, min_pixels=30):
    """each traced part's median colour (sRGB 0..1), roughness and metalness inside ITS OWN mask on the lighting-free
    picture: the trace's frame (x0, y1, length_px, front) maps its (u, v) rings onto the picture's pixels, as the build's
    colour_match does. -> ({part: {...}}, note)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415

    t = _json(trace_path) or {}
    fr = t.get("frame") or {}
    if not {"x0", "y1", "length_px"} <= set(fr):
        return {}, (f"{trace_path} has no frame — a trace made with --rotate / --straighten keeps none (its picture "
                    f"was turned), an old one predates frames: trace the picture square-on without them for colours")
    with np.load(albedo_path) as z:
        alb = z["albedo"].astype(np.float32)
        rough = z["rough"].astype(np.float32) if "rough" in z.files else None
        metal = z["metal"].astype(np.float32) if "metal" in z.files else None
        meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
    src = (t.get("source") or "").replace("\\", "/")
    if meta.get("source") and src and os.path.basename(meta["source"]) != os.path.basename(src):
        return {}, f"{albedo_path} is the colour of {meta['source']}, not of the traced picture {src}"
    H, W = alb.shape[:2]
    L, x0, y1 = float(fr["length_px"]), float(fr["x0"]), float(fr["y1"])
    left = t.get("front") == "left"
    out = {}
    parts = t.get("parts") if isinstance(t.get("parts"), dict) else {}
    for name, ring in sorted(parts.items()):
        pts = [(x0 + ((1 - u) if left else u) * L, y1 - v * L) for u, v in ring]
        if len(pts) < 3:
            continue
        img = Image.new("L", (W, H), 0)
        ImageDraw.Draw(img).polygon(pts, fill=1)
        mask = np.asarray(img, dtype=bool)
        n = int(mask.sum())
        if n < min_pixels:
            continue
        row = {"srgb": [round(float(x), 3) for x in np.median(alb[mask][:, :3], axis=0)], "pixels": n}
        if rough is not None:
            row["rough"] = round(float(np.median(rough[mask])), 3)
        if metal is not None:
            row["metal"] = round(float(np.median(metal[mask])), 3)
        out[name] = row
    return out, None


# ==================================================================== the command
def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _mm(v):
    """a length as written (a hand-edited pack may hold text: shown, never a crash)"""
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return f"'{v}' (no number)"


def summary_of(data):
    f = data.get("found") or {}
    obj = data.get("object") or {}
    return (f"{obj.get('name') or 'object not set'}"
            + (f", {_mm(obj.get('length_mm'))} mm" if obj.get("length_mm") else "")
            + f" · {len(f.get('traces') or {})} trace(s) ({sum(1 for t in (f.get('traces') or {}).values() if t.get('profiles'))} "
              f"with mm profiles) · {len(f.get('models') or {})} reference model(s) · {len(f.get('drafts') or {})} draft(s) · "
              f"{len(data.get('sizes') or {})} size(s) · {len(data.get('colours') or {})} part colour(s)")


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if "--root" in argv and argv.index("--root") + 1 >= len(argv):
        return emit("fail", "pack: --root needs a folder", "lune run kit pack <asset> [--root <project folder>]")
    root = os.path.abspath(_arg(argv, "--root", ROOT))
    args = [a for i, a in enumerate(argv) if a != "--root" and (i == 0 or argv[i - 1] != "--root")]
    if not args or args[0].startswith("-"):
        return emit("fail", "pack: needs an asset", "lune run kit pack <asset> [object | size | colours | time ...]")
    asset, sub, rest = args[0], (args[1] if len(args) > 1 else "show"), args[2:]
    if not (os.path.isfile(os.path.join(root, "assets", "models", f"build_{asset}.py"))
            or os.path.isfile(os.path.join(root, "assets", "models", f"{asset}.brief.md"))
            or os.path.isfile(pack_path(asset, root))):
        return emit("fail", f"pack: no asset '{asset}'", f"lune run kit new asset {asset}")
    data = refresh(asset, root)
    said = ""
    try:
        if sub == "object":
            if not rest or rest[0].startswith("-"):
                return emit("fail", "pack object: needs the object's name", f'lune run kit pack {asset} object "Glock 17 Gen 5" '
                            "--length dims:<id>")
            obj = {"name": rest[0], "category": _arg(rest, "--category", (data["object"] or {}).get("category"))}
            length = _arg(rest, "--length") or _arg(rest, "--length-mm")
            if length:
                size = resolve_size(length, root, _arg(rest, "--source"), obj=rest[0])
                obj.update(length_mm=size["mm"], source=size["source"], trust=size["trust"])
            data["object"] = {**data["object"], **{k: v for k, v in obj.items() if v is not None}}
            said = f"object: {data['object']}"
        elif sub == "size":
            if len(rest) < 2:
                return emit("fail", "pack size: needs <part.dim> and a value", f"lune run kit pack {asset} size "
                            "slide.length dims:<id>   (or 186 / 7.3 in --source <url>)")
            data["sizes"][rest[0]] = resolve_size(rest[1], root, _arg(rest, "--source"),
                                                  obj=(data["object"] or {}).get("name"), key=rest[0])
            row = data["sizes"][rest[0]]
            said = f"size {rest[0]} = {row['mm']:g} mm (" + (
                f"{row['source']})" if row["trust"] != "unsourced" else "UNSOURCED: give --source <url / page>, or a "
                "dims:<id> row)")
        elif sub == "colours":
            trace = _arg(rest, "--trace")
            if not trace:
                return emit("fail", "pack colours: needs --trace <trace>", f"lune run kit pack {asset} colours --trace "
                            f"{asset}_photo_side [--albedo <file.npz>]")
            tpath = trace if trace.endswith(".json") else os.path.join(root, "assets", "models", f"{trace}.trace.json")
            t = _json(tpath)
            if not isinstance(t, dict):
                return emit("fail", f"pack colours: no trace {trace}", "lune run kit trace <picture> --name <trace>")
            alb = _arg(rest, "--albedo")
            if not alb:
                pic = os.path.normpath(os.path.join(root, str(t.get("source") or "")))
                alb = next((os.path.join(root, a) for a in data["found"]["albedo"]
                            if os.path.normpath(os.path.join(root, _npz_source(os.path.join(root, a)) or "")) == pic), None)
            if not alb or not os.path.isfile(alb if os.path.isabs(alb) else os.path.join(root, alb)):
                pic = t.get("source") or "<the traced picture>"
                return emit("fail", f"pack colours: no lighting-free colour picture of {pic}",
                            f"lune run kit vision albedo {pic} -o assets/models/{asset}.albedo.npz   then this again")
            alb = alb if os.path.isabs(alb) else os.path.join(root, alb)
            got, note = part_colours(tpath, alb)
            if note:
                return emit("fail", f"pack colours: {note}", "trace the picture again / take the albedo of the "
                            "traced picture")
            kept = []
            for part, row in got.items():
                old = data["colours"].get(part)
                if old and old.get("trace") != _rel(root, tpath) and old.get("pixels", 0) > row["pixels"]:
                    kept.append(f"{part} (kept {old.get('trace')}: {old.get('pixels')} px > {row['pixels']})")
                    continue  # (another trace measured this part over more pixels: the better sample stays)
                data["colours"][part] = {**row, "albedo": _rel(root, alb), "trace": _rel(root, tpath)}
            said = f"{len(got)} part colour(s) from {_rel(root, alb)}: " + ", ".join(
                f"{p} {r['srgb']}" for p, r in list(got.items())[:4]) + (f"; {'; '.join(kept)}" if kept else "")
        elif sub == "time":
            if len(rest) < 2:
                return emit("fail", "pack time: needs <stage> <seconds>", f"lune run kit pack {asset} time gather 1260")
            import math  # noqa: PLC0415

            if not math.isfinite(float(rest[1])) or float(rest[1]) < 0:
                return emit("fail", f"pack time: '{rest[1]}' is no time in seconds", f"lune run kit pack {asset} time "
                            f"{rest[0]} <seconds>")
            data["timings"].append({"stage": rest[0], "seconds": round(float(rest[1]), 1), "what": _arg(rest, "--what"),
                                    "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
            said = f"time: {rest[0]} {float(rest[1]):g} s"
        elif sub == "looked":
            # a trace is DATA only once someone looked at its sheet (kit plan's gather lock): ok, or retraced
            if len(rest) < 2 or rest[1] not in ("ok", "retraced"):
                return emit("fail", "pack looked: needs <trace> ok|retraced", f"LOOK at build/renders/<trace>_trace.png, "
                            f"then lune run kit pack {asset} looked <trace> ok")
            tpath = os.path.join(root, "assets", "models", f"{rest[0]}.trace.json")
            if not re.fullmatch(r"[\w.-]+", rest[0]) or not os.path.isfile(tpath):
                return emit("fail", f"pack looked: no trace {rest[0]}", f"lune run kit trace <picture> --name {rest[0]}")
            data.setdefault("looked", {})[rest[0]] = {
                "verdict": rest[1], "sha": file_sha(tpath), "note": _arg(rest, "--note"),
                "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            said = f"looked: {rest[0]} {rest[1]}"
        elif sub != "show":
            return emit("fail", f"pack: unknown '{sub}'", "object | size | colours | time | looked (or nothing: show)")
    except ValueError as e:
        return emit("fail", f"pack {sub}: {e}", "fix the value and run it again")
    path = save(asset, data, root)
    line = summary_of(data)
    print(f"pack {asset}: {line}" + (f"\n  {said}" if said else ""))
    nxt = f"in build_{asset}.py: pk = a.pack()  ->  pk.size(\"slide.length\"), pk.profile(\"slide\"), pk.colour(\"slide\")"
    if not (data["object"] or {}).get("length_mm"):
        nxt = (f"set the object and its real length: lune run kit pack {asset} object \"<name>\" --length dims:<id> "
               f"(lune run kit refs dims find \"<object>\")")
    elif data["found"]["albedo"] and not data["colours"]:
        nxt = f"measure each part's colour: lune run kit pack {asset} colours --trace <the photo trace>"
    return emit("pass", f"pack {asset}: {line}" + (f" — {said}" if said else ""), nxt, pack=_rel(root, path))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
