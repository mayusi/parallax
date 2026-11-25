"""hybrid_fabricate.py — THE HYBRID ROUTE (LIMITATIONS_FIXES_V4 3D-X, 2.5 / 13.2): a piece whose machined parts are CAD
and whose sculpted parts are GENERATED, each part on the route its form needs, joined in one build.

    python kit/gen/hybrid_fabricate.py <asset> --plate <concept.png> --part <Name>=x0,y0,x1,y1[@quads] ...
        [--res 1024|512] [--seed 1] [--gen-glb <Name>=<a generated .glb already made>] [--root .]
    python kit/gen/hybrid_fabricate.py <asset> --hulls [--threshold 0.05] [--max 16]

The parts plan (the brief's `- parts plan:` lines, kit/tools/plan.py) names each part's route; a part routed
`generated` is an AI PART and the rest are the build script's own (code: a.cad from build123d, a.cast to pour CAD
parts as one with a real fillet, relief: a.ornament). For each AI part this:
  1. crops its picture from the concept plate (--part Name=box, pixels) and cuts it out (kit vision cutout --rgba:
     BiRefNet, MIT),
  2. generates it with TRELLIS.2 at 1024 (kit/gen/trellis2_run.py --res 1024, its own env; cached by the cut-out's
     sha256, the seed and the resolution - a second run of the same picture never regenerates),
  3. RETOPOLOGISES it (kit/gen/retopo_part.py: Instant Meshes quads at the part's budget, its colour baked across,
     the generator's surface kept as one watertight skin: the part's HIGH),
and writes build/hybrid/<asset>/hybrid.json - each part's route and files. The build script places them
(rbx_hybrid.ai_part: a.import_mesh(low, high=...) on the high-and-low route, Asset(low=...)); `--hulls` then cuts the
BUILT game mesh into convex collision pieces (kit/gen/hulls.py: CoACD, its own env) and measures them.

fabricate_hybrid(concept_plate, spec, parts_map) is the same as a function (13.2's contract):
  spec = {"asset": name, "parts": {Name: {"box": [x0, y0, x1, y1], "quads": 3000, "image": optional cut-out,
          "gen_glb": optional already-generated glb}}, "res": 1024, "seed": 1, "root": "."}
  parts_map = {Name: "cad" | "ai_part" | "ornament"} (None: read from the brief's parts plan)
  -> the manifest's path. Every step's failure stops with its reason (a missing env, weights, binary) - never a
  stand-in result."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = os.path.expanduser("~")
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

ENVS = os.path.join(HOME, ".cache", "roblox-kit", "envs")
TRELLIS_PY = os.environ.get("KIT_TRELLIS2_PY") or os.path.join(ENVS, "trellis2", "Scripts", "python.exe")
COACD_PY = os.environ.get("KIT_COACD_PY") or os.path.join(ENVS, "coacd", "Scripts", "python.exe")
BLENDER = find_blender() or "blender"
ROUTE_OF = {"generated": "ai_part", "code": "cad", "relief": "ornament", "projected": "ornament",
            "sculpt": "ai_part"}   # (a brief's route word -> the hybrid route; a sculpt's organic form is generated here)
DEFAULT_QUADS = 3000
BUILD = os.environ.get("KIT_BUILD") or "build"   # (the build folder, as the kit's Blender steps read it)


class HybridError(RuntimeError):
    pass


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def last_json(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and '"status"' in line:
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def routes_from_brief(asset, root=ROOT):
    """the brief's parts plan -> {part: hybrid route}; {} when the brief has none"""
    sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
    import plan as P  # noqa: PLC0415

    for base in (os.path.join(root, "assets", "models"), os.path.join(ROOT, "assets", "models")):
        path = os.path.join(base, f"{asset}.brief.md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                rows = P.parts_plan(f.read()) or []
            out = {}
            for r in rows:
                kinds = {ROUTE_OF[w] for w in r.get("routes") or [] if w in ROUTE_OF}
                out[r["name"]] = "ai_part" if "ai_part" in kinds else ("ornament" if kinds == {"ornament"} else "cad")
            return out
    return {}


def crop(plate, box, out):
    """the part's picture from the plate (box in pixels, x0, y0, x1, y1) -> out"""
    from PIL import Image  # noqa: PLC0415

    im = Image.open(plate).convert("RGB")
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    if not (0 <= x0 < x1 <= im.width and 0 <= y0 < y1 <= im.height):
        raise HybridError(f"crop: box {box} is not inside the plate ({im.width} x {im.height})")
    im.crop((x0, y0, x1, y1)).save(out)
    return out


def cutout(picture):
    """BiRefNet's cut-out (kit vision) -> <picture>_rgba.png"""
    out = picture[:-4] + "_mask.png"
    res = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "vision", "run.py"), "cutout", picture, "-o", out,
                          "--rgba"], capture_output=True, text=True, cwd=ROOT)
    rgba = out[:-4] + "_rgba.png"
    if res.returncode != 0 or not os.path.isfile(rgba):
        raise HybridError(f"cutout failed: {(res.stdout + res.stderr)[-400:]}")
    return rgba


def generate(rgba, out_glb, res=1024, seed=1):
    """TRELLIS.2 on the cut-out, cached: a .gen.glb whose record names the same picture, seed and resolution is kept
    -> (glb, its record, cached?)"""
    rec_path = out_glb[:-4] + ".json"
    pic = sha256(rgba)
    if os.path.isfile(out_glb) and os.path.isfile(rec_path):
        with open(rec_path, encoding="utf-8") as f:
            rec = json.load(f)
        # (the fields this step writes after a generation: the same picture, seed and resolution are kept)
        if rec.get("picture_sha256") == pic and rec.get("seed") == int(seed) and rec.get("res") == int(res):
            return out_glb, rec, True
    if not os.path.isfile(TRELLIS_PY):
        raise HybridError(f"TRELLIS.2's env is missing ({TRELLIS_PY}): kit/gen/README.md sets it up")
    t0 = time.time()
    r = subprocess.run([TRELLIS_PY, os.path.join(HERE, "trellis2_run.py"), rgba, out_glb, "--seed", str(seed),
                        "--res", str(res)], capture_output=True, text=True, cwd=ROOT)
    said = last_json(r.stdout)
    if r.returncode != 0 or not os.path.isfile(out_glb) or (said and said.get("status") == "fail"):
        raise HybridError(f"TRELLIS.2 failed: {(said or {}).get('summary') or (r.stdout + r.stderr)[-500:]}")
    rec = {}
    if os.path.isfile(rec_path):
        with open(rec_path, encoding="utf-8") as f:
            rec = json.load(f)
    rec.update({"picture_sha256": pic, "seed": int(seed), "res": int(res), "seconds": round(time.time() - t0, 1)})
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return out_glb, rec, False


def retopo(gen_glb, out_glb, quads):
    """kit/gen/retopo_part.py in Blender -> its facts"""
    if not os.path.isfile(BLENDER):
        raise HybridError(f"Blender not found ({BLENDER}): set BLENDER")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(HERE, "retopo_part.py"), "--", gen_glb, out_glb, "--quads", str(int(quads))],
                       capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace")
    said = last_json(r.stdout)
    if r.returncode != 0 or not said or said.get("status") != "pass":
        raise HybridError(f"retopo failed: {(said or {}).get('summary') or (r.stdout + r.stderr)[-500:]}")
    return said


def manifest_path(asset, root=ROOT):
    return Path(root) / BUILD / "hybrid" / asset / "hybrid.json"


def fabricate_hybrid(concept_plate, spec, parts_map=None):
    """13.2's contract: the AI parts generated, retopologised and written into the manifest -> its path"""
    asset = spec["asset"]
    root = spec.get("root", ROOT)
    work = Path(root) / BUILD / "hybrid" / asset
    work.mkdir(parents=True, exist_ok=True)
    routes = dict(routes_from_brief(asset, root))
    routes.update(parts_map or {})
    for name in spec.get("parts") or {}:   # (a part given a picture box is generated, whatever the plan said)
        routes.setdefault(name, "ai_part")
    res, seed = int(spec.get("res", 1024)), int(spec.get("seed", 1))
    out = {"asset": asset, "plate": str(concept_plate).replace("\\", "/") if concept_plate else None,
           "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "res": res, "seed": seed, "parts": {}}
    for name, route in sorted(routes.items()):
        if route != "ai_part":
            out["parts"][name] = {"route": route}
            continue
        p = (spec.get("parts") or {}).get(name) or {}
        t0 = time.time()
        gen = p.get("gen_glb")
        rec, cached = None, None
        if not gen:
            pic = p.get("image")
            if not pic:
                if not p.get("box") or not concept_plate:
                    raise HybridError(f"{name}: an AI part needs its picture - --part {name}=x0,y0,x1,y1 on the plate "
                                      "(or a cut-out image)")
                pic = crop(str(concept_plate), p["box"], str(work / f"{name}_crop.png"))
            rgba = pic if pic.lower().endswith("_rgba.png") else cutout(pic)
            gen, rec, cached = generate(rgba, str(work / f"{name}.gen.glb"), res, seed)
        facts = retopo(gen, str(work / f"{name}.glb"), p.get("quads", DEFAULT_QUADS))
        out["parts"][name] = {"route": "ai_part", "gen": str(gen).replace("\\", "/"),
                              "low": facts["low"], "high": facts["high"], "generated_cached": cached,
                              "generator": {k: (rec or {}).get(k) for k in ("engine", "seed", "res", "seconds")}
                              if rec else "given",
                              "retopo": {k: facts.get(k) for k in ("remesher", "quads", "polygons", "quad_share",
                                                                   "triangles", "open_edges", "pinched_edges",
                                                                   "distance", "seconds")},
                              "seconds": round(time.time() - t0, 1)}
    path = manifest_path(asset, root)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return path


def hulls(asset, root=ROOT, threshold=0.05, most=16):
    """the BUILT game meshes (build/models/<asset>_<group>.fbx) cut into convex collision pieces -> {group: facts}"""
    if not os.path.isfile(COACD_PY):
        raise HybridError(f"CoACD's env is missing ({COACD_PY}): VETLOG coacd 1.0.14 - a venv with its wheel")
    models = Path(root) / BUILD / "models"
    fbx = sorted(models.glob(f"{asset}_*.fbx"))
    fbx = [f for f in fbx if not f.stem.endswith("_high")]
    if not fbx:
        raise HybridError(f"no built game mesh for {asset} in {models} (build it first)")
    work = Path(root) / BUILD / "hybrid" / asset
    work.mkdir(parents=True, exist_ok=True)
    out = {}
    for f in fbx:
        group = f.stem[len(asset) + 1:]
        obj = work / f"{group}.obj"
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(HERE, "mesh_to_obj.py"), "--", str(f), str(obj)], capture_output=True,
                           text=True, cwd=ROOT)
        if r.returncode != 0 or not obj.is_file():
            raise HybridError(f"{group}: could not write its OBJ ({(r.stdout + r.stderr)[-300:]})")
        r = subprocess.run([COACD_PY, os.path.join(HERE, "hulls.py"), str(obj), str(work / f"{group}.hulls.json"),
                            "--threshold", str(threshold), "--max", str(most)], capture_output=True, text=True,
                           cwd=ROOT)
        said = last_json(r.stdout)
        if not said:
            raise HybridError(f"{group}: CoACD said nothing ({(r.stdout + r.stderr)[-300:]})")
        out[group] = said
    path = manifest_path(asset, root)
    man = {}
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            man = json.load(fh)
    man["hulls"] = {g: {k: v.get(k) for k in ("status", "hull_count", "coverage", "excess", "seconds")}
                    for g, v in out.items()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1)
    return out


def _parts_args(argv):
    parts = {}
    for flag, key in (("--part", "box"), ("--gen-glb", "gen_glb"), ("--image", "image")):
        for i, a in enumerate(argv):
            if a == flag and i + 1 < len(argv):
                name, _, val = argv[i + 1].partition("=")
                p = parts.setdefault(name, {})
                if key == "box":
                    box, _, q = val.partition("@")
                    p["box"] = [float(x) for x in box.split(",")]
                    if q:
                        p["quads"] = int(q)
                else:
                    p[key] = val
    return parts


def main(argv):
    if not argv or argv[0].startswith("-"):
        return emit("fail", "hybrid_fabricate: <asset> --plate <png> --part Name=x0,y0,x1,y1[@quads] | --hulls",
                    "name the piece")
    asset = argv[0]

    def opt(flag, default):
        return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default
    root = opt("--root", ROOT)
    try:
        if "--hulls" in argv:
            got = hulls(asset, root, opt("--threshold", 0.05), opt("--max", 16))
            bad = [g for g, v in got.items() if v.get("status") != "pass"]
            said = "; ".join(f"{g}: {v.get('summary', '')[7:]}" for g, v in got.items())
            return emit("fail" if bad else "pass", f"hybrid hulls {asset}: {said}",
                        "a lower --threshold for the groups named" if bad else
                        f"the pieces are in build/hybrid/{asset}/<group>.hulls.json")
        spec = {"asset": asset, "parts": _parts_args(argv), "res": opt("--res", 1024), "seed": opt("--seed", 1),
                "root": root}
        path = fabricate_hybrid(opt("--plate", ""), spec, None)
    except HybridError as e:
        return emit("fail", f"hybrid {asset}: {e}", "fix what it names and run it again")
    with open(path, encoding="utf-8") as f:
        man = json.load(f)
    ai = {n: p for n, p in man["parts"].items() if p["route"] == "ai_part"}
    said = ", ".join(f"{n} {p['retopo']['quads']:,} quads ({p['retopo']['quad_share']:.0%}, "
                     f"{p['retopo']['remesher']})" for n, p in ai.items())
    emit("pass", f"hybrid {asset}: {len(ai)} AI part(s) made - {said or 'none'}; "
                 f"{len(man['parts']) - len(ai)} part(s) left to the build (cad / ornament)",
         f"in the build: rbx_hybrid.ai_part(a, '{asset}', '<Part>', ...) in an Asset(low=...); then "
         f"python kit/gen/hybrid_fabricate.py {asset} --hulls", manifest=str(path).replace("\\", "/"))


if __name__ == "__main__":
    main(sys.argv[1:])
