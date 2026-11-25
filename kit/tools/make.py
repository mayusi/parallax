"""make.py — `lune run kit make <name> "<object>" [--tier prop|complex|hero]`: ONE command that makes a 3D model by
running EVERY stage of the pipeline itself, inside a hard time budget. The owner's rule (2026-10-09): a model takes 10
minutes (prop), 30 (complex), 60 (hero) — never hours of hand-written CAD; the kit runs the modules, not the builder.

    python kit/tools/make.py <name> "<object>" [--tier prop|complex|hero] [--private] [--keep]

The stages, each a slice of the budget (a step that would not fit what is left is SKIPPED, and says so):
  1 know       the object's category, its graded real sizes (a dossier's A/B facts, else the category's ranges)
  2 gather     photos of every view (a dossier's own pictures and turntable, else `refs find` + `refs rank`), each cut
               out; reference models (`library find` / `get`) — graded before anything uses them
  3 candidates base shapes from every generator that can take the photos (multi-view, single-photo, parts)
  4 tournament every candidate rendered from the photos' views and scored against them (outline + look); best wins
  5 fit        the winner at its real size
  6 surface    painted from the best photo
  7 mechanism  moving parts — only where the category has them and the shape has parts
  8 look       the build, the render beside the photo, the judge packet (hero)
Every module the tier calls for ends RAN or SKIPPED with a reason the code checked; one that did neither fails the
run (module coverage). Writes build/make/<name>/report.json + report.md, and the build script
assets/models/build_<name>.py that `kit asset <name>` builds (marked as made by kit make).
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "refs"))
_KIT = os.path.join(REPO, "kit")
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

TIERS = {"prop": 600, "complex": 1800, "hero": 3600}   # seconds: the owner's 10 / 30 / 60 minutes
# each stage's share of the budget (a step past its stage's share may still run if the whole budget allows)
SHARE = {"know": 0.05, "gather": 0.2, "candidates": 0.3, "tournament": 0.1, "fit": 0.05, "surface": 0.12,
         "mechanism": 0.03, "look": 0.15}
STAGES = list(SHARE)
# the modules each stage runs, per tier (anything listed must end RAN or SKIPPED-with-reason)
MODULES = {
    "know": ["category", "sizes", "pack"],
    "gather": ["photos", "rank", "cutouts", "trace", "models", "qualify"],
    "candidates": ["gen_multiview", "gen_single", "gen_parts"],
    "tournament": ["render_candidates", "score"],
    "fit": ["clean", "round", "size"],
    "surface": ["paint", "project"],
    "mechanism": ["joints"],
    "look": ["build", "compare", "judge_packet"],
}
CATEGORY_WORDS = {
    "pistol": ["pistol", "glock", "handgun", "1911", "beretta", "revolver", "sig ", "p320", "silverballer", "hardballer"],
    "rifle": ["rifle", "carbine", "ar-15", "ar15", "m4", "ak-47", "ak47", "sniper", "m107", "barrett", "shotgun"],
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=True))
    return 0 if status == "pass" else 1


class Run:
    """the budget, the module record and the kit calls of one `kit make` run"""

    def __init__(self, name, obj, tier, private):
        self.name, self.obj, self.tier, self.private = name, obj, tier, private
        self.fresh = False
        self.budget = TIERS[tier]
        self.t0 = time.time()
        self.dir = os.path.join(REPO, "build", "make", name)
        os.makedirs(self.dir, exist_ok=True)
        self.stages = {}       # stage -> {"seconds", "modules": {module: {...}}, "facts": {...}}
        self.facts = {}        # what later stages read (category, sizes, photos, candidates ...)
        self.log = open(os.path.join(self.dir, "make.log"), "w", encoding="utf-8")

    # ---------------------------------------------------------------- time
    def left(self):
        return self.budget - (time.time() - self.t0)

    def fits(self, need_s):
        """a step that needs `need_s` seconds runs only if the whole budget still has them"""
        return self.left() >= need_s

    # ---------------------------------------------------------------- the record
    def mod(self, stage, module, ran, reason="", **facts):
        """a module's outcome: ran (with what it found) or skipped (with the reason the code checked)"""
        rec = self.stages.setdefault(stage, {"seconds": 0.0, "modules": {}, "facts": {}})
        entry = {"ran": bool(ran), "reason": reason}
        entry.update({k: v for k, v in facts.items() if v is not None})
        rec["modules"][module] = entry
        self.say(f"[{stage}] {module}: {'ran' if ran else 'SKIPPED'}{' — ' + reason if reason else ''}")

    def say(self, text):
        line = f"{time.time() - self.t0:7.1f}s  {text}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    # ---------------------------------------------------------------- kit calls
    def kit(self, args, timeout=None):
        """`lune run kit <args>` -> (ok, the verdict's results [step results, last first], seconds). The verdict is the
        .verify file the command names on its last lines (every kit command writes one)."""
        t = time.time()
        timeout = timeout or max(30.0, self.left() + 30.0)
        self.say("kit " + " ".join(f'"{a}"' if " " in a else a for a in args))
        # (KIT_MAKE: these are kit make's OWN builds of the script it wrote — the owner's stage approvals, the model
        #  sheet and the blockout, are asked by kit make's own two stops (stage_stop: a complex / hero piece stops for
        #  them before any generator and before the bake) and again when the piece is built by hand afterwards)
        p = subprocess.Popen(["lune", "run", "kit", *args], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace", env={**os.environ, "KIT_MAKE": "1"})
        try:
            so, se = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # the whole tree: killing lune alone leaves its python (a generator holding the GPU) running on
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                p.kill()
            p.communicate()
            self.say(f"    | timed out after {timeout:.0f} s: stopped (with everything it started)")
            return False, [{"summary": f"timed out after {timeout:.0f} s"}], time.time() - t
        out = (so or "") + (se or "")
        code = p.returncode
        m = re.findall(r"verdict:\s*(\.verify/[^\s]+\.json)", out)
        results = []
        if m:
            try:
                with open(os.path.join(REPO, m[-1]), encoding="utf-8") as fh:
                    v = json.load(fh)
                results = [s.get("result") for s in reversed(v.get("steps", [])) if s.get("result")]
            except (OSError, ValueError):
                pass
        for line in out.splitlines()[-4:]:
            self.log.write("    | " + line + "\n")
        return code == 0, results, time.time() - t

    def write(self, ok, summary):
        coverage = []
        for st in STAGES:
            for module in self.planned(st):
                got = self.stages.get(st, {}).get("modules", {}).get(module)
                if got is None:
                    coverage.append(f"{st}.{module}")
                elif not got["ran"] and not got.get("reason"):
                    coverage.append(f"{st}.{module} (skipped with no reason)")
        report = {"name": self.name, "object": self.obj, "tier": self.tier, "budget_s": self.budget,
                  "seconds": round(time.time() - self.t0, 1), "ok": ok and not coverage, "summary": summary,
                  "uncovered": coverage, "stages": self.stages, "facts": self.facts}
        with open(os.path.join(self.dir, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, default=str)
        lines = [f"# kit make {self.name} — {self.obj} ({self.tier}, budget {self.budget // 60} min)", "",
                 f"{summary}", "", f"Total: {report['seconds']:.0f} s of {self.budget} s.", "",
                 "| stage | module | outcome | detail |", "| --- | --- | --- | --- |"]
        for st in STAGES:
            for module, got in self.stages.get(st, {}).get("modules", {}).items():
                detail = got.get("reason") or got.get("note") or ""
                lines.append(f"| {st} | {module} | {'ran' if got['ran'] else 'skipped'} | {detail} |")
        if coverage:
            lines += ["", "UNCOVERED (a module the tier calls for that neither ran nor said why): " + ", ".join(coverage)]
        with open(os.path.join(self.dir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return report

    def planned(self, stage):
        return MODULES[stage]


# ================================================================================================= stage 1: know
def category_of(obj):
    o = " " + obj.lower() + " "
    for cat, words in CATEGORY_WORDS.items():
        if any(w in o for w in words):
            return cat
    return "generic"


def kind_of(obj):
    """the real_sizes.json kind the object's words name (a chair, a desk lamp ...) or None"""
    with open(os.path.join(REPO, "kit", "real_sizes.json"), encoding="utf-8") as fh:
        kinds = json.load(fh)["kinds"]
    o = obj.lower()
    hits = [k for k in kinds if k.replace("_", " ") in o]
    return (max(hits, key=len), kinds[max(hits, key=len)]) if hits else (None, None)


STOP_WORDS = {"a", "an", "the", "of", "with", "and", "old", "new", "red", "big", "small", "wooden", "metal"}
DIM_OF = {("overall", "height"): "height", ("overall", "length"): "length", ("overall", "width"): "width",
          ("body", "diameter"): "round", ("belly", "diameter"): "round", ("base", "width"): None}


def sizes_from_dims(obj):
    """kit/real_specs rows for an object's words -> {height|length|width: {mm, grade, key}}: the rows whose object
    names its HEAD noun (the last word: "extinguisher", "barrel", "lamp") and shares the most words with it (at least
    two — "barrel" alone is also a gun's); several rows of one size: their median, grade B when 2+ sources agree within
    3%, else C; a round body's diameter is its width AND length"""
    try:
        sys.path.insert(0, os.path.join(REPO, "kit", "refs"))
        import dims  # noqa: PLC0415

        rows = dims.load_all()
    except Exception:  # noqa: BLE001 — no rows: the category ranges / the shape's own proportions
        return {}
    words = [w for w in re.findall(r"[a-z0-9]+", obj.lower()) if w not in STOP_WORDS]
    if not words:
        return {}
    head = words[-1]

    def overlap(r):
        have = set(re.findall(r"[a-z0-9]+", str(r.get("object", "")).lower()))
        return len(set(words) & have) if head in have else 0

    best = max((overlap(r) for r in rows), default=0)
    if best < min(2, len(words)):
        return {}
    picked = [r for r in rows if overlap(r) == best and str(r.get("unit", "mm")).lower() == "mm"]
    out = {}
    for (part, dim), key in DIM_OF.items():
        vals = [r for r in picked if r.get("part") == part and r.get("dim") == dim and float(r.get("value") or 0) > 0]
        if not key or not vals:
            continue
        v = sorted(float(x["value"]) for x in vals)
        mm = v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2
        agree = len({x.get("source") for x in vals}) >= 2 and (v[-1] - v[0]) / max(v[0], 1e-9) <= 0.03
        row = {"mm": mm, "grade": "B" if agree else "C", "key": f"dims:{vals[0].get('id')}"}
        for k in (("width", "length") if key == "round" else (key,)):
            out.setdefault(k, row)
    return out


def stage_know(r):
    cat = category_of(r.obj)
    r.facts["category"] = cat
    r.mod("know", "category", True, note=cat)
    sizes = {}
    # (a) the object's dossier: its graded facts (A maker / patent / owner, B two sites agree)
    try:
        import dossier  # noqa: PLC0415

        d = dossier.load(r.obj)
    except Exception:  # noqa: BLE001 — no dossier for this object
        d = None
    if d:
        r.facts["dossier"] = d.get("slug")
        r.facts["aliases"] = list((d.get("identity") or {}).get("aliases") or [])
        # the dossier's own grading (offline: its rows annotated as `kit dossier check` does, then graded): only A / B
        rows = dossier.annotate_rows(d, offline=True, reg=dossier.registry())
        for dim, f in dossier.frame_facts(d, dossier.grade_facts(d, rows)).items():
            sizes[dim] = {"mm": float(f["mm"]), "grade": f["grade"], "key": f["key"]}
    # (b) the category's real ranges (kit/real_sizes.json: Infinigen's numbers), the middle of each
    if not sizes:
        kind, rng = kind_of(r.obj)
        if rng:
            h = sum(rng["height"]) / 2 * 1000.0
            sizes["height"] = {"mm": h, "grade": "range", "key": f"real_sizes.{kind}.height"}
            for fp in rng.get("footprint") or []:
                sizes["length" if fp[0] == "wide" else "width"] = {"mm": (fp[1] + fp[2]) / 2 * 1000.0,
                                                                    "grade": "range",
                                                                    "key": f"real_sizes.{kind}.{fp[0]}"}
    # (c) SOURCED rows (kit refs dims: a maker's spec sheet, a shop listing) for these words — the made extinguisher
    #     came out 1000 mm tall while two shops said 387 mm
    if not sizes:
        sizes = sizes_from_dims(r.obj)
    r.facts["sizes"] = sizes
    if sizes:
        r.mod("know", "sizes", True, note=", ".join(f"{k} {v['mm']:.0f} mm ({v['grade']})" for k, v in sizes.items()))
    else:
        r.mod("know", "sizes", False, "no dossier fact and no real-size range for these words: the shape keeps its "
                                      "own proportions, scaled to its longest side")
    write_brief(r)   # (stage 0 from the owner's request: kit plan's brief gate)
    write_build(r, None)   # (the asset exists from here: kit pack and the later stages address it by name)
    args = ["pack", r.name, "object", r.obj, "--category", cat]
    if sizes.get("length"):
        args += ["--length", f"{sizes['length']['mm']:.1f}", "--source", size_source(r, sizes["length"])]
    ok, _res, _s = r.kit(args, timeout=120)
    # every graded size WITH the key it came from (a dossier fact, a real_sizes range): kit plan's gather gate needs a
    # sourced size — a size kit make knew but never wrote down left every made prop at "no sourced size"
    for dim, row in sizes.items():
        ok = r.kit(["pack", r.name, "size", f"object.{dim}", f"{row['mm']:.1f}", "--source",
                    size_source(r, row)], timeout=120)[0] and ok
    r.mod("know", "pack", ok, "" if ok else "kit pack refused the object or a size (see make.log)")


def size_source(r, row):
    """where a graded size came from, as kit pack's --source: the dossier's fact key, else the real_sizes row"""
    key = str(row.get("key") or "")
    return f"dossier:{r.facts['dossier']}:{key}" if r.facts.get("dossier") and not key.startswith("real_sizes.") \
        else key or "real_sizes"


# ================================================================================================= stage 2: gather
def dossier_photos(r):
    """the dossier's own pictures by view: its turntable's four cardinal frames (c<az>_l0: 24 azimuths, 15 deg apart;
    the dossier's evidence says which is which) else its side / front / back pictures"""
    slug = r.facts.get("dossier")
    if not slug:
        return {}
    root = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "evidence", slug)
    try:
        with open(os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "knowledge", f"{slug}.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    from PIL import Image  # noqa: PLC0415

    views, every = {}, {}
    turn = os.path.join(root, "turntable")
    names = {"side-left": "left", "side-right": "right", "rear": "back", "front": "front"}
    for e in d.get("evidence", []):
        if e.get("kind") != "picture" or e.get("withdrawn"):
            continue
        v = names.get((e.get("claimed") or {}).get("view") or "")
        if not v:
            continue
        orig = e.get("original") or ""
        path = os.path.join(turn, orig) if orig and os.path.isfile(os.path.join(turn, orig)) else (
            os.path.join(root, e["file"]) if e.get("file") and os.path.isfile(os.path.join(root, e["file"])) else None)
        if not path:
            continue
        every.setdefault(v, []).append(path)
        rig = path.startswith(turn)   # (the turntable frame: the four views from ONE camera rig, for the generators)
        if v not in views or (rig and not views[v].startswith(turn)):
            views[v] = path
    # a much sharper picture of the same view (the maker's 8124 px side against the turntable's 1512): traced and
    # PROJECTED instead — markings and stippling at 10x the pixels — while the generators keep the one-rig set
    sharp = {}
    for v, paths in every.items():
        px = {}
        for q in paths:
            with Image.open(q) as im:
                px[q] = im.size[0] * im.size[1]
        best = max(paths, key=px.get)
        if best != views[v] and px[best] >= 2 * px[views[v]]:
            sharp[v] = best
    r.facts["photos_sharp"] = sharp
    return views


def found_photos(r):
    """`refs find` + `refs rank`: licensed photos of the object, the best one of each view"""
    import find as refs_find  # noqa: PLC0415  (kit/refs/find.py: its folder name for the words)

    out = os.path.join("build", "refs", refs_find.slug(r.obj))
    if os.path.isfile(os.path.join(REPO, out, "found.json")):   # (found before: reused, never fetched twice)
        r.mod("gather", "photos", True, note=f"reused {out} (found before)")
    elif not r.fits(90):
        r.mod("gather", "photos", False, f"budget: {r.left():.0f} s left")
        return {}
    else:
        ok, res, _s = r.kit(["refs", "find", r.obj, "--n", "8"], timeout=min(150, r.left() * 0.2))
        out = next((x.get("out") for x in res if x and x.get("out")), None)
        r.mod("gather", "photos", ok and bool(out), "" if ok and out else "refs find returned no pictures", note=out)
        if not (ok and out):
            return {}
    idx = os.path.join(REPO, out, "index.json")
    if not os.path.isfile(idx) or os.path.getmtime(idx) < os.path.getmtime(os.path.join(REPO, out, "found.json")):
        r.kit(["refs", "rank", out, "--what", r.obj], timeout=240)
    rows = []
    if os.path.isfile(idx):
        with open(idx, encoding="utf-8") as fh:
            rows = json.load(fh).get("ranked") or []
    r.mod("gather", "rank", bool(rows), "" if rows else "refs rank wrote no index", note=f"{len(rows)} ranked")
    views = {}
    side_names = {"side": "left", "front": "front", "back": "back", "top": "top", "three-quarter": "three_quarter"}
    ranked = []
    for row in rows:   # best first
        if row.get("text"):
            continue   # (a picture of printed text: a page, a label — not the object)
        v = side_names.get(row.get("view"))
        if v and v not in views:
            views[v] = os.path.join(REPO, out, row["file"])
            ranked.append([v, float(row.get("score") or 0.0)])
    r.facts["ranked_views"] = ranked   # (each view's photo and how surely it shows the object, best first)
    return views


def is_named_object(r):
    """a REAL, named object (a make and model: words with a number, a weapon) is gathered from its real photos; a
    generic one ("a wooden chair") has no one true look — found photos are of many objects of the kind (a museum's
    Egyptian chair, another chair's part), so a concept agrees ONE design. --photos / --concept force a route."""
    route = getattr(r, "route", None)
    if route in ("photos", "concept"):
        return route == "photos"
    if getattr(r, "no_gen", False):   # (no generator: a concept picture is one — the real photos it is)
        return True
    return bool(re.search(r"\d", r.obj)) or r.facts.get("category") in ("pistol", "rifle")


def concept_views(r):
    """FLUX.2 klein's `views` sheet of the object (front, left side, back: ONE design) -> {view: picture}; a sheet
    the kit's own checks fault (a view repeating the front, a count off) is drawn again with another seed, once"""
    out = os.path.join(r.dir, "concept.png")
    said, problems, seed = None, [], 0
    for seed in (1, 2):
        if not r.fits(45):
            break
        ok, res, _s = r.kit(["vision", "concept", r.obj, "--sheet", "views", "--seed", str(seed), "-o", out],
                            timeout=300)
        said = next((x for x in res if x and x.get("views")), None) if ok else None
        if said:
            with open(os.path.splitext(out)[0] + ".json", encoding="utf-8") as fh:
                problems = json.load(fh).get("problems") or []
            if not problems:
                break
    if not said:
        r.mod("gather", "photos", False, "kit vision concept failed (see make.log)" if r.fits(45) else
              f"budget: a concept needs ~45 s, {r.left():.0f} s left")
        return {}
    files = {v: (said["views"].get(v) or {}).get("file") for v in ("front", "side", "back")}
    views = {("left" if v == "side" else v): os.path.join(REPO, f) if not os.path.isabs(f) else f
             for v, f in files.items() if f}
    # the SAME design from the front-left and above, drawn with its front as the reference (~30 s): what a single-photo
    # generator reads, what the painter sees the top from (a chest's lid, a chair's seat were plain strips), and the
    # look the tournament and the comparison hold it to
    if views.get("front") and r.fits(60 + RESERVE[r.tier]):
        tq = os.path.join(r.dir, "concept.three_quarter.png")
        ok, res, _s = r.kit(["vision", "concept", r.obj, "--sheet", "three_quarter", "--from", views["front"],
                             "-o", tq], timeout=240)
        if ok and os.path.isfile(tq):
            views["three_quarter"] = tq
    r.mod("gather", "photos", True, note=f"a CONCEPT (FLUX.2 klein, seed {seed}): {', '.join(sorted(views))} of ONE "
                                         f"design{' — its checks: ' + '; '.join(problems) if problems else ''}")
    r.mod("gather", "rank", False, "one generated design, its views labelled by the sheet: nothing to rank")
    return views


def stage_gather(r):
    views = dossier_photos(r)
    # views of ONE object from one rig (the dossier's turntable, a concept sheet) can feed a multi-view generator
    # together; found photos are of many objects of the kind (a chair, another chair): one at a time
    r.facts["photo_source"] = "dossier" if views else None
    if views:
        r.mod("gather", "photos", True, note=f"the dossier's {len(views)} views: {', '.join(sorted(views))}")
        r.mod("gather", "rank", False, "the dossier's pictures are already checked and labelled by view (two reviewers)")
    elif not is_named_object(r):
        views = concept_views(r)
        r.facts["photo_source"] = "concept" if views else None
    if not views:
        views = found_photos(r)
        r.facts["photo_source"] = "found" if views else None
    r.facts["views_consistent"] = r.facts["photo_source"] in ("dossier", "concept")
    r.facts["photos"] = views
    # every photo cut out (BiRefNet) and cropped tight round the object: the generators read the object, not the room
    cut = {}
    for v, path in views.items():
        if not r.fits(20):
            break
        ok, res, _s = r.kit(["vision", "cutout", path], timeout=120)
        out = next((x.get("out") for x in res if x and x.get("out")), None)
        if ok and out:
            cut[v] = crop_cutout(r, v, path, os.path.join(REPO, out))
    r.facts["cutouts"] = cut
    sharp = {}
    for v, path in (r.facts.get("photos_sharp") or {}).items():   # (projected instead of the rig's frame: see above)
        if not r.fits(40):
            break
        ok, res, _s = r.kit(["vision", "cutout", path], timeout=180)
        out = next((x.get("out") for x in res if x and x.get("out")), None)
        if not (ok and out):
            continue
        made = crop_cutout(r, f"{v}_sharp", path, os.path.join(REPO, out), longest=4096)
        side = side_check(made, cut.get(v)) if v in ("left", "right") else "same"
        if side == "other":
            v = "left" if v == "right" else "right"
        if side in ("same", "other") and cut.get(v):
            match_colour(made, cut[v])   # (another shoot's light: the maker's Glock photo is blue-grey, the rig's black)
        if side == "same":
            sharp[v] = made
        elif side == "other":   # (its label is wrong: the dossier's "side-right" Glock photo shows the LEFT side —
            label = "left" if v == "right" else "right"   # muzzle left, the left's roll mark reading true)
            r.say(f"[gather] the sharp {label} photo's outline is the {v} side's (its mirror fits the rig's {label} "
                  f"frame): used for the {v} side")
            if v in cut and v not in sharp:
                sharp[v] = made
    r.facts["cutouts_sharp"] = sharp
    r.facts["photos_mtime"] = max([os.path.getmtime(p) for p in views.values() if os.path.isfile(p)] or [0])
    r.mod("gather", "cutouts", bool(cut), "" if cut else ("no photos to cut out" if not views else
                                                         f"budget: {r.left():.0f} s left"),
          note=f"{len(cut)} of {len(views)}")
    stage_trace(r)
    stage_models(r)


TRACE_VIEW = {"left": ("side", "left"), "right": ("side", "right"), "front": ("front", None), "back": ("back", None)}
# an ORGANIC object (by its words): a curved form whose tapers are its shape — traced with --organic (the perspective
# check is for straight members: the skull's side photo failed it at "25% along its length")
ORGANIC_WORDS = {"skull", "head", "bust", "face", "skeleton", "bone", "bones", "creature", "monster", "animal",
                 "dragon", "beast", "rock", "boulder", "stone", "pebble", "tree", "stump", "log", "root", "roots",
                 "branch", "shell", "horn", "antler", "fruit", "mushroom", "plant", "flower", "leaf", "coral", "fossil",
                 "statue", "sculpture", "figurine", "body", "hand", "foot", "heart", "brain", "fish", "bird"}


def is_organic(obj):
    """the object's words name an organic form (whole words: "rock" in "rocket" is not one)"""
    return bool(set(re.findall(r"[a-z]+", (obj or "").lower())) & ORGANIC_WORDS)


def stage_trace(r):
    """each view of THE object traced (`kit trace`): its outline registers the photo to the model, so the build can
    measure the shape against it AND paint the photo onto it (a.project). Only views of one object: projecting another
    chair's photo onto this chair paints it wrong."""
    cut = r.facts.get("cutouts") or {}
    concept = r.facts.get("photo_source") == "concept"
    # found photos show many SPECIMENS of the kind: with a generator there, none is traced (projecting another chair's
    # photo paints this one wrong). With --no-gen nothing else can give a shape — the best side and front photos of
    # real specimens give the clay's outline (approximate: two specimens), measured, never projected
    specimens = not r.facts.get("views_consistent")
    if specimens and not getattr(r, "no_gen", False):
        r.mod("gather", "trace", False, "the photos show many objects of the kind (found photos): none is projected")
        return
    traced = {}
    sharp = r.facts.get("cutouts_sharp") or {}
    for v, (view, front) in TRACE_VIEW.items():
        if v not in cut or not r.fits(20):
            continue
        tname = f"{r.name}_{v}"
        args = ["trace", sharp.get(v, cut[v]), "--name", tname, "--bg", "light"] + (["--front", front] if front else []) \
            + (["--organic"] if is_organic(r.obj) else [])
        ok, _res, _s = r.kit(args, timeout=180)
        if ok and os.path.isfile(os.path.join(REPO, "assets", "models", f"{tname}.trace.json")):
            # (a concept's view is traced only to REGISTER it for painting — a generated picture is never measured:
            # no trace_match against it. For a generic object it is the agreed design, its colours the intended look;
            # unprojected, a treasure chest's planks and brass latch were lost to a plain painted brown)
            traced[v] = {"trace": tname, "view": view, "measure": not concept, **({"specimen": True} if specimens else {})}
    r.facts["traces"] = traced
    r.mod("gather", "trace", bool(traced), "" if traced else "kit trace failed on every view (see make.log)",
          note=", ".join(f"{v} -> {t['view']}" for v, t in traced.items())
          + (" (a concept: registered for painting, never measured)" if concept else "")
          + (" (different specimens, --no-gen: the clay's approximate outline, never projected)" if specimens else ""))


def match_colour(photo, rig_frame):
    """the photo's object pixels take the rig frame's colour statistics (each channel's mean and spread over the
    object, in place): a sharper picture from another shoot keeps its detail, the rig's white balance and exposure"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    a = np.asarray(Image.open(photo).convert("RGB")).astype(np.float64)
    b = np.asarray(Image.open(rig_frame).convert("RGB")).astype(np.float64)
    ma, mb = a.min(axis=2) < 245, b.min(axis=2) < 245   # (the crops sit on white)
    if ma.sum() < 100 or mb.sum() < 100:
        return
    for c in range(3):
        sa, sb = a[..., c][ma], b[..., c][mb]
        a[..., c][ma] = (sa - sa.mean()) / max(sa.std(), 1e-6) * sb.std() + sb.mean()
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(photo)


def side_check(photo, rig_frame):
    """is a side photo the side its label says? Its silhouette against the camera rig's frame of that side, as it is
    and mirrored: "same", "other" (the mirror fits clearly better: the opposite side), or "unsure" (neither fits)"""
    import numpy as np  # noqa: PLC0415

    if not rig_frame:
        return "same"
    a, _ = norm_mask(photo)
    b, _ = norm_mask(rig_frame)
    if a is None or b is None:
        return "unsure"
    iou = float((a & b).sum() / max(1, (a | b).sum()))
    m = np.fliplr(a)
    iou_m = float((m & b).sum() / max(1, (m | b).sum()))
    if iou >= 0.75 and iou >= iou_m:
        return "same"
    return "other" if iou_m >= 0.75 and iou_m > iou + 0.05 else "unsure"


def crop_cutout(r, view, photo, cut_png, longest=None):
    """the photo cut out with its mask, cropped to the object + 8%, on white -> build/make/<name>/view_<v>.png
    (longest: the crop scaled down to at most that many pixels on its long side)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    mk = np.asarray(Image.open(cut_png).convert("L"))
    obj = mk > 128
    if obj.mean() > 0.5:
        obj = ~obj
    src = Image.open(photo).convert("RGB")
    if src.size != (mk.shape[1], mk.shape[0]):
        src = src.resize((mk.shape[1], mk.shape[0]))
    ys, xs = np.nonzero(obj)
    if not len(xs):
        return photo
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    m = int(0.08 * max(x1 - x0, y1 - y0))
    a = np.asarray(src).copy()
    box = (max(0, x0 - m), max(0, y0 - m), min(a.shape[1], x1 + m), min(a.shape[0], y1 + m))
    rgba = np.dstack([a, (obj * 255).astype(np.uint8)])
    a[~obj] = 255
    out = os.path.join(r.dir, f"view_{view}.png")
    for im, path in ((Image.fromarray(rgba).crop(box), os.path.join(r.dir, f"view_{view}_rgba.png")),
                     (Image.fromarray(a).crop(box), out)):   # (rgba: for the generators)
        if longest and max(im.size) > longest:
            k = longest / max(im.size)
            im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS)
        im.save(path)
    return out


def stage_models(r):
    """reference MODELS: found and downloaded (licensed), each graded before anything uses it (refs/qualify)"""
    if not r.fits(60):
        r.mod("gather", "models", False, f"budget: {r.left():.0f} s left")
        return
    # the object's words, then shorter ("glock 17 gen5" finds nothing, "glock 17" does): the dossier's aliases first
    words = r.obj.split()
    queries = [r.obj] + list(r.facts.get("aliases") or []) + [" ".join(words[:k]) for k in range(len(words) - 1, 0, -1)]
    rows, ok, seen = [], False, set()
    for q in queries:
        if q.lower() in seen or not r.fits(30):
            continue
        seen.add(q.lower())
        t = time.time()
        ok, _res, _s = r.kit(["library", "find", q, "--n", "8"], timeout=120)
        lists = [p for p in glob.glob(os.path.join(REPO, "build", "library", "*", "candidates.json"))
                 if os.path.getmtime(p) >= t - 1]
        if ok and lists:
            with open(max(lists, key=os.path.getmtime), encoding="utf-8") as fh:
                got = json.load(fh)
            have = {m.get("uid") for m in rows}
            rows += [m for m in got if m.get("uid") not in have]
            r.facts.setdefault("models_query", []).append(q)
            if len(rows) >= 6:   # (enough to grade them against each other)
                break
    r.facts["models_found"] = [{k: m.get(k) for k in ("uid", "title", "faces", "licence", "author")}
                               for m in rows][:8]
    r.mod("gather", "models", ok and bool(rows), "" if ok and rows else "library find: no licensed model found",
          note=f"{len(rows)} found")
    qualify_models(r, rows)


HARD_SURFACE = ("pistol", "rifle")


def qualify_models(r, rows):
    """every reference model GRADED before anything uses it — not size alone (the 1.17M-face Glock scan passed that
    and was a mess): torn surfaces, floating debris, a raw scan's jagged surface on a hard-surface object, and its
    proportions against the object's sourced sizes (else the other references' median). Downloads the top ones not
    yet in the library cache while the budget allows. -> r.facts["guides"]: the models that passed"""
    lib = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "library")
    graded = []
    for m in rows[:6]:
        uid = str(m.get("uid") or "")
        have = glob.glob(os.path.join(lib, f"{uid}*", "model.glb"))
        if not have and r.fits(120) and len(graded) < 4:
            r.kit(["library", "get", uid], timeout=min(180, r.left() * 0.15))
            have = glob.glob(os.path.join(lib, f"{uid}*", "model.glb"))
        if not have:
            continue
        out = os.path.join(r.dir, "models", f"{uid[:12]}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if not os.path.isfile(out):
            subprocess.run([blender(), "-b", "--factory-startup", "-P",
                            os.path.join(REPO, "kit", "blender", "model_quality.py"), "--", have[0], out],
                           capture_output=True, text=True, timeout=600)
        try:
            with open(out, encoding="utf-8") as fh:
                q = json.load(fh)
        except (OSError, ValueError):
            continue
        graded.append((m, have[0], q))
    if not graded:
        r.mod("gather", "qualify", False, "no reference model downloaded to grade (no token, offline, or budget)")
        return
    sizes = r.facts.get("sizes") or {}
    want = sorted([v["mm"] for v in sizes.values() if v.get("grade") in ("A", "B")])

    def ratios(sz):
        a = sorted(float(x) for x in sz)
        return (a[2] / max(a[1], 1e-9), a[1] / max(a[0], 1e-9))

    if len(want) == 3:
        target, against = ratios(want), "the sourced sizes"
    else:
        rs = sorted(ratios(q["size"]) for _m, _p, q in graded)
        target, against = rs[len(rs) // 2], "the other references' median"
    guides, verdicts = [], []
    for m, path, q in graded:
        why = []
        if q["open_share"] > 0.02:
            why.append(f"torn: {q['open_share']:.1%} of its edges open")
        if q["speck_share"] > 0.05:
            why.append(f"debris: {q['speck_share']:.1%} of its faces float in specks (a scene, not the object)")
        if r.facts.get("category") in HARD_SURFACE and q["flat_share"] < 0.2 and q["sharp_share"] < 0.08:
            why.append(f"a raw scan's surface: jagged everywhere (flat {q['flat_share']:.2f}, sharp edges "
                       f"{q['sharp_share']:.2f}; a modelled one is ~0.3 / ~0.2)")
        got = ratios(q["size"])
        off = max(abs(got[0] / target[0] - 1), abs(got[1] / target[1] - 1))
        if off > 0.12:
            why.append(f"proportions {off:.0%} off {against} (extra pieces: a light, hands, an exploded layout)")
        ok = not why
        verdicts.append({"uid": m.get("uid"), "title": m.get("title"), "faces": q["faces"], "pass": ok,
                         "why": why, "path": path})
        if ok:
            guides.append(path)
    r.facts["model_verdicts"] = verdicts
    r.facts["guides"] = guides
    r.mod("gather", "qualify", True, note=f"{len(guides)} of {len(verdicts)} pass: " + "; ".join(
        f"{(v['title'] or v['uid'])[:28]}: {'ok' if v['pass'] else v['why'][0]}" for v in verdicts))


# ================================================================================================= stage 3: candidates
PRIVATE_ONLY = ("hunyuan", "partcrafter")   # Tencent-licensed engines: private assets only (rbx.PRIVATE_ONLY_ENGINES)


def is_colour(path):
    """a colour photo (not a black-and-white museum shot): the object's saturation, its upper quartile"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    sat = (a.max(axis=2) - a.min(axis=2))[a.sum(axis=2) < 3 * 245]
    return bool(len(sat)) and float(np.percentile(sat, 75)) > 18


def best_photo(r):
    """the one picture a single-photo generator reads — and its texture comes from: a COLOUR photo first (a black-and-
    white one makes a grey object), a three-quarter view (it shows depth), then the side, then any"""
    cut = r.facts.get("cutouts") or {}
    ranked = [(v, sc) for v, sc in (r.facts.get("ranked_views") or []) if v in cut]
    if ranked:   # found photos: the one that most surely shows THE object — a colour one only if it is nearly as sure
        top = ranked[0][1]
        for v, sc in ranked:
            if sc >= 0.5 * top and is_colour(cut[v]):
                return v, cut[v]
        return ranked[0][0], cut[ranked[0][0]]
    # (a concept's: its three-quarter view of the same design, else its front — a side profile alone gives a
    # single-photo generator no width)
    first = ("three_quarter", "front", "left") if r.facts.get("photo_source") == "concept" else (
        "three_quarter", "left", "right", "front")
    order = [v for v in first + ("three_quarter", "left", "right", "front", "back", "top") if v in cut]
    order = list(dict.fromkeys(order))
    for v in order:
        if is_colour(cut[v]):
            return v, cut[v]
    return (order[0], cut[order[0]]) if order else (None, None)


# seconds kept, once one candidate exists, for what follows the candidates: the tournament, the clean-up, the paint
# (~170 s cold) and the build — a second generator that would eat them leaves a run with nothing built (the chair,
# 2026-10-09: three generators, then 37 s left for a 90 s build)
RESERVE = {"prop": 330, "complex": 450, "hero": 600}


def gen(r, stage, module, tag, args, need_s, reserve=0):
    """one generator run -> the candidate's mesh path, or None (the module's outcome recorded either way). reserve:
    seconds that must stay after it (RESERVE, once a candidate exists)"""
    if getattr(r, "no_gen", False):
        r.mod(stage, module, False, "skipped: --no-gen (the owner chose a model made without generators)")
        return None
    cname = f"{r.name}__{tag}"
    made = [os.path.join(REPO, "assets", "models", f"{cname}.{k}.glb") for k in ("gen", "parts")]  # (parts: PartCrafter)
    have = next((p for p in made if os.path.isfile(p)), made[0])
    # its inputs: the photo files in its arguments, each by content (a candidate is reused only from the SAME photos)
    import hashlib  # noqa: PLC0415

    srcs = sorted(a for a in args(cname) if os.path.isfile(a))
    key = hashlib.sha256(b"".join(open(a, "rb").read() for a in srcs)).hexdigest()[:16]
    book = os.path.join(r.dir, "candidate_inputs.json")
    try:
        with open(book, encoding="utf-8") as fh:
            known = json.load(fh)
    except (OSError, ValueError):
        known = {}
    if not r.fresh and os.path.isfile(have) and known.get(cname) == key:
        r.mod(stage, module, True, note=f"{os.path.basename(have)} reused (made before from these same photos; "
                                        "--fresh makes it again)")
        return have
    if not r.fits(need_s + reserve):
        r.mod(stage, module, False, f"budget: needs ~{need_s} s" + (f" and {reserve} s kept for the tournament, paint "
                                                                     f"and build" if reserve else "")
              + f"; {r.left():.0f} s left")
        return None
    # (never past the time kept for what follows: Pixal3D on a treasure chest ran 450 s, killed, and the paint and the
    # build were left 43 s)
    ok, res, secs = r.kit(args(cname), timeout=min(need_s * 3, max(need_s, r.left() - reserve)))
    mesh = next((p for p in made if os.path.isfile(p)), None)
    if ok and mesh and os.path.getmtime(mesh) >= r.t0:
        known[cname] = key
        with open(book, "w", encoding="utf-8") as fh:
            json.dump(known, fh, indent=1)
        r.mod(stage, module, True, note=f"{os.path.basename(mesh)} in {secs:.0f} s")
        return mesh
    why = next((x.get("summary") for x in res if x and x.get("summary")), "the generator failed (see make.log)")
    r.mod(stage, module, False, f"failed: {why[:160]}")
    return None


def traced_hull(r):
    """the traced_hull candidate (module gen_hull): the sharpest side trace x the front (else back) trace -> its GLB"""
    traced = {v: t for v, t in (r.facts.get("traces") or {}).items() if t.get("measure", True)}
    sides = sorted((v for v in ("left", "right") if v in traced), key=lambda v: -trace_length_px(traced[v]["trace"]))
    ends = [v for v in ("front", "back") if v in traced]
    if not sides or not ends:
        r.mod("candidates", "gen_hull", False, "needs a traced side and a traced front or back of THE object's own "
                                               "photos (a concept's are never measured)")
        return None
    out = os.path.join(REPO, "assets", "models", f"{r.name}__hull.gen.glb")
    tp = [os.path.join(REPO, "assets", "models", f"{traced[v]['trace']}.trace.json") for v in (sides[0], ends[0])]
    # the PARTS LAYER: each traced side's relief (levers, panels, serrations, seams as height) pressed into its flank
    # (make_hull.py can press a side's relief into the flanks — the parts layer — but judged it lost: 43 against
    # the plain hull's 45.75, blotched and stair-stepped; off until it beats the plain hull)
    press = []
    p = subprocess.run([blender(), "-b", "--factory-startup", "-P", os.path.join(REPO, "kit", "blender",
                        "make_hull.py"), "--", *tp, out, *press], capture_output=True, text=True, timeout=300)
    said = next((json.loads(x) for x in reversed(p.stdout.splitlines()) if x.startswith("{")), None)
    if not (said and said.get("status") == "pass" and os.path.isfile(out)):
        r.mod("candidates", "gen_hull", False, f"make_hull failed: {(p.stderr or '')[-160:]}")
        return None
    r.mod("candidates", "gen_hull", True, note=f"{sides[0]} x {ends[0]} outlines: {said.get('summary')}")
    return out


def sculpted_hull(r):
    """the sculpted_hull candidate (module gen_sculpt_hull): the same two traced views as traced_hull, SCULPTED
    (make_sculpt_hull.py: rbx_sculpt's exact 2D distances intersected, meshed by OpenVDB) — always one closed surface,
    its edges rounded 1.2% of its length: a moulded or worn object's, where the boolean hull's are knife-sharp"""
    traced = {v: t for v, t in (r.facts.get("traces") or {}).items() if t.get("measure", True)}
    sides = sorted((v for v in ("left", "right") if v in traced), key=lambda v: -trace_length_px(traced[v]["trace"]))
    ends = [v for v in ("front", "back") if v in traced]
    if not sides or not ends:
        r.mod("candidates", "gen_sculpt_hull", False, "needs a traced side and a traced front or back of THE object's "
                                                      "own photos")
        return None
    out = os.path.join(REPO, "assets", "models", f"{r.name}__shull.gen.glb")
    tp = [os.path.join(REPO, "assets", "models", f"{traced[v]['trace']}.trace.json") for v in (sides[0], ends[0])]
    p = subprocess.run([blender(), "-b", "--factory-startup", "-P", os.path.join(REPO, "kit", "blender",
                        "make_sculpt_hull.py"), "--", *tp, out], capture_output=True, text=True, timeout=300)
    said = next((json.loads(x) for x in reversed(p.stdout.splitlines()) if x.startswith("{")), None)
    if not (said and said.get("status") == "pass" and os.path.isfile(out)):
        r.mod("candidates", "gen_sculpt_hull", False, f"make_sculpt_hull failed: {(p.stderr or '')[-160:]}")
        return None
    r.mod("candidates", "gen_sculpt_hull", True, note=f"{sides[0]} x {ends[0]} outlines: {said.get('summary')}")
    return out


def stage_candidates(r):
    cut = r.facts.get("cutouts") or {}
    rgba = {v: os.path.join(r.dir, f"view_{v}_rgba.png") for v in cut}
    cands = {}
    v1, p1 = best_photo(r)
    # (1) multi-view: views of ONE object (the dossier's turntable, a concept sheet) — Pixal3D and Hunyuan3D-2mv
    four = [v for v in ("front", "left", "back", "right") if v in cut]
    if not r.facts.get("views_consistent") or len(four) < 2:
        r.mod("candidates", "gen_multiview", False, "no views of ONE object from one rig (found photos are of many "
                                                    "objects of the kind): multi-view would blend them")
    else:
        # Pixal3D (MIT, pixel-aligned to every view) and Hunyuan3D-2mv (private): Hunyuan first where it may run (its
        # Glock judged 46 against Pixal3D's 34: correct proportions, a clean surface), else Pixal3D; a second runs
        # only if the paint and build still fit after it
        px_module = "gen_multiview_px" if r.private else "gen_multiview"
        # Pixal3D's side view is the camera at the object's RIGHT (its front on the picture's right): the right photo
        # as it is, else the left one mirrored
        px = [x for v in ("front", "back") if v in cut for x in ("--view", f"{v}={rgba[v]}")]
        if "right" in cut:
            px += ["--view", f"side={rgba['right']}"]
        elif "left" in cut:
            px += ["--view", f"side={rgba['left']}", "--flip", "side"]

        def run_px():
            if px.count("--view") < 2:
                r.mod("candidates", px_module, False, "Pixal3D needs two of side / front / back: " + ", ".join(four))
                return
            m = gen(r, "candidates", px_module, "px", lambda c: ["gen", "views", c] + px, 150,
                    RESERVE[r.tier] if cands else 0)
            if m:
                cands["pixal3d_views"] = m

        def run_hy():
            if not r.private:
                return
            # a hero / complex object: the FULL model (50 steps, ~4.5 min) — the turbo's Glock frame flank came out
            # ridged and its levers blobbed, the full one's clean; a prop: the turbo (its 10 minutes)
            full = False   # (the full model: judged the same as the turbo on the Glock, 4 min slower — `--model full` stays)
            m = gen(r, "candidates", "gen_multiview", "hyf" if full else "hy", lambda c: ["gen", "mv-shape", c] + [
                x for v in four for x in (f"--{v}", cut[v])] + (["--model", "full"] if full else []),
                330 if full else 240, RESERVE[r.tier] if cands else 0)
            if m:
                cands["hunyuan_multiview"] = m

        for run in (run_hy, run_px):
            run()
    # (1b) the TRACED HULL: a real object's side outline intersected with its front outline (make_hull.py, seconds)
    # — the photographed silhouette exactly, flat flanks, crisp edges: what a generator melts on a slab-sided object
    # (a pistol). The traces are the photos' own; a concept's are never measured
    hull = traced_hull(r)
    if hull:
        cands["traced_hull"] = hull
        shull = sculpted_hull(r)   # (the same views sculpted: closed always, its edges rounded — the tournament picks)
        if shull:
            cands["sculpted_hull"] = shull
    # (2) single photo: TRELLIS.2 (MIT) — and Hunyuan on the one photo when multi-view did not run (private)
    if not p1:
        r.mod("candidates", "gen_single", False, "no photo cut out")
    else:
        m = gen(r, "candidates", "gen_single", "tr", lambda c: ["gen", c, "--image", p1], 300,
                RESERVE[r.tier] if cands else 0)
        if m:
            cands["trellis_single"] = m
        if r.private and "hunyuan_multiview" not in cands:
            m2 = gen(r, "candidates", "gen_single_hy", "hy1", lambda c: ["gen", "mv-shape", c, "--front", p1], 240,
                     RESERVE[r.tier] if cands else 0)
            if m2:
                cands["hunyuan_single"] = m2
    # (3) parts: PartCrafter (private) — the object as separate parts (complex and hero)
    if r.tier == "prop":
        r.mod("candidates", "gen_parts", False, "prop tier: one mesh is enough (parts are generated for complex / hero)")
    elif not r.private:
        r.mod("candidates", "gen_parts", False, "PartCrafter is private-only (its licence) and this asset is public")
    elif not p1:
        r.mod("candidates", "gen_parts", False, "no photo cut out")
    else:
        m = gen(r, "candidates", "gen_parts", "pc", lambda c: ["gen", "parts", c, "--image", p1, "--parts", "8"], 240,
                RESERVE[r.tier] if cands else 0)
        if m:
            cands["partcrafter_parts"] = m
    r.facts["candidates"] = cands


# ================================================================================================= stage 4: tournament
RING = ["front", "right", "back", "left"]   # the side cameras round the object, a quarter turn apart


def blender():
    return find_blender()


def norm_mask(path):
    """a silhouette (alpha, or dark-on-white) cropped to the object and squeezed to 128 x 128: its shape alone"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    im = Image.open(path)
    if im.mode == "RGBA" and np.asarray(im)[..., 3].min() < 250:
        m = np.asarray(im)[..., 3] > 128
    else:
        g = np.asarray(im.convert("L")).astype(int)
        m = g < 245
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None, None
    crop = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    aspect = crop.shape[1] / max(1, crop.shape[0])
    return np.asarray(Image.fromarray(crop.astype(np.uint8) * 255).resize((128, 128))) > 127, aspect




def is_hard_surface(r):
    """a machined or built object (flat faces, real edges): its candidates are denoised with their edges kept and the
    tournament asks for crispness; an organic one (an animal, a plant) is left as generated"""
    # (the MACHINED categories only — words like "wood" or "metal" planarized curved props: dead-flat dark panels on
    #  the made barrel, flat facets on the extinguisher; a barrel is not a pistol slide)
    return r.facts.get("category") in HARD_SURFACE


def clean_candidate(r, key, mesh):
    """make_clean.py on one candidate (--denoise for a hard surface) -> (the cleaned GLB, what it said); reused while
    the cleaned file is newer than the candidate. The tournament scores shapes as the build will use them: Pixal3D's
    Glock is noisy raw (5.1 deg) and crisp denoised (1.3 deg, its edges kept); Hunyuan's is smooth either way"""
    hard = is_hard_surface(r)
    out = os.path.join(r.dir, "clean", f"{key}.glb")
    meta = out[:-4] + ".json"
    if os.path.isfile(out) and os.path.isfile(meta) and os.path.getmtime(out) >= os.path.getmtime(mesh):
        with open(meta, encoding="utf-8") as fh:
            said = json.load(fh)
        # (made from THIS file: keyed by name alone, the full model's clean was served for the turbo's candidate)
        if said.get("src") != os.path.abspath(mesh) or said.get("src_mtime") != round(os.path.getmtime(mesh), 1):
            said = {}
        # (a curved prop is never smoothed: an edge-keeping filter turned the extinguisher's noise into white
        #  crease "cracks" under its gloss — its raw surface read better)
        current = (not hard or "denoised" in (said.get("planarized") or {})) and said.get("faces_out", 0) <= 300000
        # (made by today's clean: capped, and flattened with an eased border)
        if bool(said.get("crispness_denoised")) == hard and current:
            return out, said
    os.makedirs(os.path.dirname(out), exist_ok=True)
    p = subprocess.run([blender(), "-b", "--factory-startup", "-P", os.path.join(REPO, "kit", "blender", "make_clean.py"),
                        "--", mesh, out] + (["--denoise"] if hard else []), capture_output=True, text=True, timeout=600)
    said = next((json.loads(x) for x in reversed(p.stdout.splitlines()) if x.startswith("{")), None)
    if not (said and os.path.isfile(out)):
        r.say(f"[tournament] make_clean failed on {key}: {(p.stderr or '')[-300:]}")
        return mesh, None
    said["src"], said["src_mtime"] = os.path.abspath(mesh), round(os.path.getmtime(mesh), 1)
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(said, fh, indent=1)
    return out, said


def crisp_score(said):
    """0..1: real edges (sharp share 0.06+) and flat faces (flat share 0.5+), half each — rbx_denoise.crispness"""
    c = (said or {}).get("crispness_denoised") or (said or {}).get("crispness")
    if not c:
        return None
    return 0.5 * min(1.0, c["sharp_share"] / 0.06) + 0.5 * min(1.0, c["flat_share"] / 0.5)


def stage_tournament(r):
    import numpy as np  # noqa: PLC0415

    cands = r.facts.get("candidates") or {}
    if not cands:
        r.mod("tournament", "render_candidates", False, "no candidate to render")
        r.mod("tournament", "score", False, "no candidate to score")
        return
    exe = blender()
    scores = {}
    cut = r.facts.get("cutouts") or {}
    vlook, plook = best_photo(r)
    hard = is_hard_surface(r)
    cleaned = r.facts.setdefault("cleaned", {})
    for key, mesh in cands.items():
        if not r.fits(60):
            break
        mesh, said = clean_candidate(r, key, mesh)
        cleaned[key] = {"mesh": mesh, "said": said}
        out = os.path.join(r.dir, "views", key)
        subprocess.run([exe, "-b", "--factory-startup", "-P", os.path.join(REPO, "kit", "blender", "make_views.py"),
                        "--", mesh, out], capture_output=True, text=True, timeout=180)
        if not os.path.isfile(os.path.join(out, "look.png")):
            continue
        # a single-photo generator takes its photo for the object's FRONT: its shape can come back turned. Every quarter
        # turn is tried (photo view i <-> rendered view i + k round the ring); the best is kept, and the build turns
        # the mesh by it (yaw = 90 k degrees about up)
        best = None
        for k in range(4):
            ious, aspects = [], []
            for v in ("front", "right", "back", "left", "top"):
                if v not in cut:
                    continue
                rv = v if v == "top" else RING[(RING.index(v) + k) % 4]
                if not os.path.isfile(os.path.join(out, f"{rv}.png")):
                    continue
                a, asp_a = norm_mask(os.path.join(out, f"{rv}.png"))
                b, asp_b = norm_mask(cut[v])
                if a is None or b is None:
                    continue
                if v == "top":   # (the top view turns with the yaw: its best of four rotations)
                    cands_ = [(np.rot90(a, j), asp_a if j % 2 == 0 else 1.0 / asp_a) for j in range(4)]
                    a, asp_a = max(cands_, key=lambda t: (t[0] & b).sum() / max(1, (t[0] | b).sum()))
                ious.append(float((a & b).sum() / max(1, (a | b).sum())))
                aspects.append(min(asp_a, asp_b) / max(asp_a, asp_b))
            if ious:
                o = float(np.mean(ious)) * float(np.mean(aspects))
                if best is None or o > best[0]:
                    best = (o, 90 * k)
        outline, yaw = (best if best else (None, 0))
        look = None
        if plook:
            ok, res, _s = r.kit(["vision", "similar", os.path.join(out, "look.png"), plook], timeout=120)
            look = next((x.get("similarity") for x in res if x and x.get("similarity") is not None), None)
        prop = None
        sizes = r.facts.get("sizes") or {}
        try:
            with open(os.path.join(out, "views.json"), encoding="utf-8") as fh:
                sx, sy, sz = json.load(fh)["size"]   # x right (width), y front (length), z up (height)
            if yaw in (90, 270):
                sx, sy = sy, sx
            want = [sizes.get(k, {}).get("mm") for k in ("width", "length", "height")]
            have = [sx, sy, sz]
            pairs = [(w, h) for w, h in zip(want, have) if w]
            if len(pairs) >= 2:
                (w0, h0) = pairs[0]
                errs = [abs((h / h0) / (w / w0) - 1) for w, h in pairs[1:]]
                prop = max(0.0, 1.0 - float(np.mean(errs)))
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            pass
        crisp = crisp_score(said) if hard else None
        # crispness is REPORTED, not scored: weighted 0.2 it picked Pixal3D's crisp Glock (crisp 1.0) over Hunyuan's
        # soft one (0.53) — and fresh judges gave the crisp one 34 against 46: its grip and frame warped, its levers
        # no better. A correct soft shape beats a crisp wrong one (2026-10-09)
        # proportions weigh 0.3 when a real object's GRADED sizes exist: they see the 3D errors a silhouette cannot
        # (Pixal3D's Glock 14% too thin and warped: judged 33.8; the hull's long raked grip). With these weights the
        # tournament ranked the 2026-10-09 Glock candidates in the fresh judges' own order; without graded sizes
        # (a concept) prop is None and the others share its weight
        parts = [(0.4, outline), (0.3, look), (0.3, prop)]
        have_w = sum(w for w, x in parts if x is not None)
        total = sum(w * x for w, x in parts if x is not None) / have_w if have_w else 0.0
        scores[key] = {"score": round(total, 4), "outline": outline and round(outline, 4), "look": look,
                       "proportions": prop and round(prop, 4), "crisp": crisp and round(crisp, 4), "yaw": yaw,
                       "views": out}
        r.say(f"[tournament] {key}: {scores[key]}")
    r.mod("tournament", "render_candidates", bool(scores), "" if scores else "no candidate rendered (see make.log)",
          note=f"{len(scores)} of {len(cands)} rendered")
    if scores:
        win = max(scores, key=lambda k: scores[k]["score"])
        use = getattr(r, "use", None)
        chosen = ""
        if use and use in scores and use != win:   # (--use: a person's pick over the scores, said in the report)
            chosen = f"{use} CHOSEN by --use over the scores' {win}; "
            win = use
        r.facts["tournament"] = scores
        r.facts["winner"] = win
        r.mod("tournament", "score", True, note=chosen + f"winner {win} ({scores[win]['score']:.3f}); " + ", ".join(
            f"{k} {s['score']:.3f}" for k, s in scores.items()))
    else:
        r.mod("tournament", "score", False, "nothing rendered to score")


# ================================================================================================= stage 5-6: fit, surface
def glb_topology(path):
    """a GLB's surface as a surface: its triangles welded at coincident corners, then {faces, verts, open_share} —
    the share of edges with ONE face. A sound generated shape is near 0; a shredded one (loose triangles each
    decimated alone: the 2026-10-09 Glock's paint, 0.68) renders as a see-through sketch, whatever the textures say."""
    import struct

    import numpy as np

    with open(path, "rb") as fh:
        raw = fh.read()
    n = struct.unpack("<I", raw[12:16])[0]
    doc = json.loads(raw[20:20 + n])
    blob = 20 + n + 8
    kinds = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = doc["accessors"][i]
        bv = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(kinds[a["componentType"]])
        k = width[a["type"]]
        o = blob + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or dt.itemsize * k
        if stride == dt.itemsize * k:
            return np.frombuffer(raw[o:o + a["count"] * stride], dt).reshape(-1, k)
        rows = np.frombuffer(raw[o:o + a["count"] * stride], np.uint8).reshape(-1, stride)[:, :dt.itemsize * k]
        return rows.copy().view(dt).reshape(-1, k)

    pts, tris = [], []
    for mesh in doc.get("meshes", []):
        for pr in mesh.get("primitives", []):
            if pr.get("mode", 4) != 4 or "POSITION" not in pr.get("attributes", {}):
                continue
            p = acc(pr["attributes"]["POSITION"]).astype(np.float64)
            t = acc(pr["indices"]).reshape(-1, 3) if "indices" in pr else np.arange(len(p)).reshape(-1, 3)
            tris.append(t.astype(np.int64) + sum(len(x) for x in pts))
            pts.append(p)
    if not tris:
        return {"faces": 0, "verts": 0, "open_share": 1.0}
    P, T = np.concatenate(pts), np.concatenate(tris)
    span = float((P.max(0) - P.min(0)).max()) or 1.0
    _, weld = np.unique(np.round(P / (span * 1e-5)).astype(np.int64), axis=0, return_inverse=True)
    F = weld.ravel()[T]
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return {"faces": int(len(F)), "verts": int(weld.max() + 1),
            "open_share": round(float((counts == 1).sum()) / max(1, len(counts)), 4)}


SHREDDED = 0.05   # open edges over all edges: a generator's mesh past this is torn, not just pinholed


STAVE_WORDS = ("barrel", "cask", "keg", "tub", "bucket", "butt", "hogshead")


def staves_args(r):
    """a wooden coopered object (a barrel, a cask, a tub) gets its staves pressed into its round body (rbx_lathe.staves:
    the made barrel read as one smooth beige drum) — make_clean applies them only when its body comes out round"""
    o = " " + r.obj.lower() + " "
    return ["--staves", "30"] if any(f" {w}" in o for w in STAVE_WORDS) else []


def stage_fit(r):
    sizes = r.facts.get("sizes") or {}
    if not r.facts.get("winner"):
        r.mod("fit", "clean", False, "no winning shape to clean")
        r.mod("fit", "size", False, "no winning shape to fit")
        return
    # the winner made sound: welded, specks dropped, small holes filled, every face turned outward, a hard surface's
    # noise filtered with its edges kept (make_clean.py, run on every candidate before the tournament)
    win = r.facts["winner"]
    src = r.facts["candidates"][win]
    done = (r.facts.get("cleaned") or {}).get(win) or {}
    cmesh, said = (done.get("mesh"), done.get("said")) if done.get("said") else clean_candidate(r, win, src)
    dst = os.path.join(REPO, "assets", "models", f"{r.name}.clean.glb")
    if said and os.path.isfile(cmesh):
        shutil.copy(cmesh, dst)
        # the WINNER's inner wall dropped (Pixal3D's shapes are thick hollow shells: the made barrel and extinguisher
        # were 52% faces no one sees — the AO bake read them as buried: the colour x 0.25, black blotches, owner 0 / 2)
        p = subprocess.run([blender(), "-b", "--factory-startup", "-P", os.path.join(REPO, "kit", "blender",
                                                                                     "make_clean.py"),
                            "--", dst, dst, "--inner-wall", "--round", *staves_args(r)], capture_output=True, text=True,
                           timeout=600)
        inner = next((json.loads(x) for x in reversed(p.stdout.splitlines()) if x.startswith("{")), None) or {}
        r.facts["inner_wall_dropped"] = inner.get("inner_wall_dropped", 0)
        # its ROUND slices trued onto their circles (rbx_lathe: a generated barrel is ±5-15% lumpy per slice; owner
        # 2026-10-16 batch 2 "still bad"): appendages, a square lantern, a fluted post stay as they are
        rnd = inner.get("round") or {}
        r.facts["round"] = rnd
        if rnd.get("moved"):
            r.mod("fit", "round", True, note=f"{rnd['round_share']:.0%} of its height round, trued onto the fitted "
                                             f"circles (largest move {rnd.get('largest_move', 0):.1%} of its height)"
                                             + (f"; staves pressed in ({rnd['staves']} skin vertices)"
                                                if rnd.get("staves") else ""))
        else:
            r.mod("fit", "round", False, f"no round body: {rnd.get('round_share', 0):.0%} of its slices round (a "
                                         "square, fluted or open shape keeps the generator's form)")
        r.facts["candidates"]["_clean"] = dst
        r.facts["clean_mesh"] = dst
        topo = glb_topology(dst)
        r.facts["topology"] = {"clean": topo}
        crisp = said.get("crispness_denoised") or said.get("crispness")
        r.mod("fit", "clean", True, note=f"{said.get('specks_dropped')} specks dropped, open edges "
                                         f"{said.get('open_edges')}, faces turned outward"
                                         + (", denoised with its edges kept" if said.get("crispness_denoised") else "")
                                         + (f", {r.facts['inner_wall_dropped']} inner-wall faces dropped"
                                            if r.facts.get("inner_wall_dropped") else "")
                                         + f"; as written: {topo}; crispness {crisp}")
    else:
        r.mod("fit", "clean", False, "make_clean failed (see make.log): the raw winner is used")
        r.mod("fit", "round", False, "make_clean failed: nothing to true")
    if sizes:
        graded = all(v.get("grade") in ("A", "B") for v in sizes.values()) and len(sizes) >= 2
        r.mod("fit", "size", True, note="fitted to " + " x ".join(f"{k} {v['mm']:.0f}" for k, v in sizes.items()) +
              (" mm, each axis (graded sizes: the generator's proportions are a guess)" if graded else
               " mm by its height (a category's range: the shape keeps its own proportions)"))
    else:
        r.mod("fit", "size", True, note="no sourced size: its own proportions, 1 m on its longest side")


def stage_surface(r):
    win = r.facts.get("winner")
    if not win:
        r.mod("surface", "paint", False, "no winning shape to paint")
        return
    if getattr(r, "no_gen", False):
        r.mod("surface", "paint", False, "skipped: --no-gen (Hunyuan Paint is a generator)")
        r.facts["surface_mesh"] = r.facts.get("clean_mesh") or r.facts["candidates"][win]
        return
    mesh = r.facts.get("clean_mesh") or r.facts["candidates"][win]
    photo = paint_photo(r)
    if win in ("trellis_single", "pixal3d_views") and not r.private:
        r.mod("surface", "paint", False, "a public asset keeps the winner's own texture (Hunyuan Paint is private-only)")
        r.facts["surface_mesh"] = mesh
        return
    # (a private one is painted whichever generator made its shape: Pixal3D's own colour map on the Glock was
    # blotchy — grey patches, white specks — where Hunyuan Paint's was clean)
    if not r.private:
        r.mod("surface", "paint", False, "Hunyuan Paint is private-only; a public asset keeps the generator's own "
                                         "texture (TRELLIS.2 bakes PBR maps with its shape)")
        r.facts["surface_mesh"] = mesh
        return
    if not photo:
        r.mod("surface", "paint", False, "no photo to paint from")
        r.facts["surface_mesh"] = mesh
        return
    if not r.fits(150):   # (~25-45 s since its inpaint was vectorised, and the build after it ~100 s)
        r.mod("surface", "paint", False, f"budget: needs ~45 s and ~100 s for the build, {r.left():.0f} s left")
        r.facts["surface_mesh"] = mesh
        return
    ok, res, secs = r.kit(["gen", "paint", mesh, "--image", photo, "--out", r.name], timeout=300)
    painted = os.path.join(REPO, "assets", "models", f"{r.name}.paint.glb")
    topo = glb_topology(painted) if ok and os.path.isfile(painted) and os.path.getmtime(painted) >= r.t0 else None
    if topo:
        r.facts.setdefault("topology", {})["paint"] = topo
    if topo and topo["open_share"] > SHREDDED:
        # the painter hands back ITS mesh (reduced, re-unwrapped): torn, it would render see-through — the clean
        # shape goes on unpainted (the photo projection still colours it)
        r.facts["surface_mesh"] = mesh
        r.mod("surface", "paint", False, f"the painted mesh came back torn ({topo['open_share']:.0%} of its edges "
                                         f"open, over {SHREDDED:.0%}): the clean shape is used")
    elif topo:
        r.facts["surface_mesh"] = painted
        r.mod("surface", "paint", True, note=f"painted from {os.path.basename(photo)} in {secs:.0f} s; "
                                             f"{topo['faces']} faces, {topo['open_share']:.1%} open edges")
    else:
        r.facts["surface_mesh"] = mesh
        why = next((x.get("summary") for x in res if x and x.get("summary")), "failed (see make.log)")
        r.mod("surface", "paint", False, f"failed: {why[:160]}")


def relief_map(r, v):
    """`kit vision relief` on view v's cut-out (the sharp one when there is one), at most 2048 px -> its .npz (the
    picture's sculpted relief: panels, serrations, levers), reused while newer than the cut-out; None if no time"""
    from PIL import Image  # noqa: PLC0415

    cut = (r.facts.get("cutouts_sharp") or {}).get(v) or (r.facts.get("cutouts") or {}).get(v)
    rgba = cut[:-4] + "_rgba.png" if cut else None
    if not rgba or not os.path.isfile(rgba):
        return None
    out = os.path.join(r.dir, f"relief_{v}.npz")
    if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(rgba):
        return out
    if not r.fits(220):   # (~50 s, and the build after it)
        return None
    small = os.path.join(r.dir, f"relief_{v}_in.png")
    with Image.open(rgba) as im:
        k = min(1.0, 2048 / max(im.size))
        im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS).save(small)
    ok, _res, _s = r.kit(["vision", "relief", small, "-o", out], timeout=min(240, max(60, r.left() - 160)))
    return out if ok and os.path.isfile(out) else None


def stage_project(r):
    traced = {v: t for v, t in (r.facts.get("traces") or {}).items() if not t.get("specimen")}
    if (r.facts.get("traces") or {}) and not traced:
        r.mod("surface", "project", False, "the traced photos are of different specimens (--no-gen): their outlines "
                                           "shape the clay, their pictures are never painted on")
        return
    if not traced:
        r.mod("surface", "project", False, "the concept's views could not be traced to register them (see make.log)"
              if r.facts.get("photo_source") == "concept" else
              "no traced view of THE object to project (found photos are of many objects)")
        return
    if not r.private:
        # (a PUBLIC asset's surface is its colour regions' kit finishes — write_build: the projected picture painted
        #  the muddy look back. Its views stay registered as the fallback for a shape with no texture, without the
        #  reliefs: ~40 s a view that ran the made barrel past its budget)
        r.mod("surface", "project", True, note="registered as the fallback only: a public asset's surface is its "
                                               "colour regions' kit finishes (import_mesh regions=)")
        return
    for v, t in traced.items():   # (each view's sculpted relief joins its lines in the normal map)
        t["relief_map"] = relief_map(r, v)
    r.mod("surface", "project", True, note="the build paints " + ", ".join(traced) + " onto the shape (a.project: "
                                           + ("the concept's agreed look: its grain, bands, fittings)"
                                              if r.facts.get("photo_source") == "concept" else
                                              "the photos' real markings, seams and wear)"))


def paint_photo(r):
    """the photo the surface is painted from: the SAME photo the winning shape came from (found photos are of many
    objects of the kind — another one's colours on this shape are wrong); a multi-view winner: the side view"""
    if r.facts.get("winner") in ("hunyuan_multiview", "pixal3d_views"):
        cut = r.facts.get("cutouts") or {}
        if r.facts.get("photo_source") == "concept":   # (its 3/4 shows the top too; else its front)
            return cut.get("three_quarter") or cut.get("front") or best_photo(r)[1]
        return cut.get("left") or cut.get("right") or best_photo(r)[1]
    return best_photo(r)[1]


def stage_surface_all(r):
    stage_surface(r)
    stage_project(r)


def stage_mechanism(r):
    cat = r.facts.get("category")
    if cat in ("pistol", "rifle") and "partcrafter_parts" in (r.facts.get("candidates") or {}):
        r.mod("mechanism", "joints", False, "the parts candidate's pieces are unnamed: joints need named parts "
                                           "(slide, trigger ...) — not automatic yet")
    else:
        r.mod("mechanism", "joints", False, "one generated mesh: no separate parts to joint" if cat in ("pistol", "rifle")
              else f"category '{cat}' has no moving parts")


# ================================================================================================= stage 8: look
MM = 280.0


# the generated surface's material by what the object is MADE of: its words first ("a wooden chair"), else its
# category. rough: a generator writes one flat guess (Hunyuan Paint: 0.9 everywhere: chalk); scan: a vetted CC0 scan's
# variation over it (kit/blender/rbx_scans) — one roughness everywhere reads as plastic (the judges, 2026-10-09)
SURFACE_WORDS = (("wood", {"rough": 0.6, "scan": "Wood096"}), ("leather", {"rough": 0.45, "scan": "Leather037"}),
                 ("steel", {"rough": 0.5, "scan": "Metal027"}), ("iron", {"rough": 0.55, "scan": "Metal027"}),
                 ("metal", {"rough": 0.5, "scan": "Metal027"}), ("plastic", {"rough": 0.45, "scan": "Plastic010"}),
                 ("stone", {"rough": 0.7, "scan": "Rock064"}), ("rock", {"rough": 0.7, "scan": "Rock064"}),
                 ("concrete", {"rough": 0.75, "scan": "Concrete034"}), ("brick", {"rough": 0.75, "scan": "Bricks104"}))
SURFACE_CATEGORY = {"pistol": {"rough": 0.55, "scan": "Plastic010"},   # (a polymer frame: most of what is seen)
                    "rifle": {"rough": 0.55, "scan": "Metal027"}}
RELIEF = 1.5   # a projected photo's fine structure in the normal map: serrations, stippling, stamped text (1 = engraving)


# what the object's LIFE did to its surface (a.material / a.import_mesh life=), read off its words: a generated body
# came out factory-fresh — no dirt in its crevices, no worn edges — the "surface story" fresh judges marked down
LIFE_WORDS = (("heavy", ("old", "worn", "rusty", "rusted", "weathered", "battered", "antique", "ancient", "abandoned",
                         "broken", "dirty", "damaged", "beat-up", "used")),
              ("new", ("new", "brand-new", "clean", "pristine", "mint", "polished", "shiny", "unused")))


def life_of(obj):
    """'an old wooden chest' -> "heavy", 'a new office chair' -> "new", else "light" (a thing in use, not abused)"""
    words = set(re.findall(r"[a-z]+(?:-[a-z]+)*", obj.lower()))
    for level, cues in LIFE_WORDS:
        if words & set(cues):
            return level
    return "light"


def surface_of(r):
    """the generated body's rough= / scan= (the scan at full strength: at half, a painted Glock's roughness still varied
    under the kit's 0.02 bar at two scales of three) and its life= (life_of: its words)"""
    words = r.obj.lower()
    for w, surf in SURFACE_WORDS:
        if w in words:
            return {**surf, "scan_mix": 1.0, "life": life_of(r.obj)}
    surf = SURFACE_CATEGORY.get(r.facts.get("category"))
    if surf:
        return {**surf, "scan_mix": 1.0, "life": life_of(r.obj)}
    # (no word, no category: the scan the roughness check itself would prescribe for these words — a bare rough=0.6
    #  baked ONE roughness over the whole hydrant: "reads as plastic", flagged on every made prop)
    try:
        sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
        import rbx_pbr  # noqa: PLC0415

        scan = rbx_pbr.scan_for(r.obj, 0.0)
    except Exception:  # noqa: BLE001 — no scans on this machine: the bare roughness, said by the build's check
        scan = None
    return {"rough": 0.6, "scan": scan, "scan_mix": 1.0, "life": life_of(r.obj)} if scan else \
        {"rough": 0.6, "life": life_of(r.obj)}


def face_colours(glb):
    """a GLB's faces -> (sRGB 0-255 at each face's UV centre in its base-colour texture (n,3), each face's area (n,))
    — plain numpy over the file (no Blender), or (None, None) when it has no texture / UVs"""
    import io  # noqa: PLC0415
    import struct  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    try:
        with open(glb, "rb") as fh:
            b = fh.read()
        n = struct.unpack("<I", b[12:16])[0]
        j = json.loads(b[20:20 + n])
        off = 20 + n + 8
    except (OSError, ValueError, struct.error):
        return None, None

    def acc(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        width = {"VEC2": 2, "VEC3": 3, "SCALAR": 1}[a["type"]]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
        return np.frombuffer(b, dtype=dt, count=a["count"] * width,
                             offset=off + bv.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(a["count"], width)

    rgbs, areas = [], []
    try:
        for mesh in j.get("meshes", []):
            for pr in mesh["primitives"]:
                at = pr["attributes"]
                if "TEXCOORD_0" not in at:
                    continue
                pbr = j["materials"][pr.get("material", 0)].get("pbrMetallicRoughness", {})
                tex = pbr.get("baseColorTexture")
                if not tex:
                    continue
                img_i = j["textures"][tex["index"]]["source"]
                bv = j["bufferViews"][j["images"][img_i]["bufferView"]]
                start = off + bv.get("byteOffset", 0)
                img = np.asarray(Image.open(io.BytesIO(b[start:start + bv["byteLength"]])).convert("RGB"), np.float64)
                pos = acc(at["POSITION"]).astype(np.float64)
                uv = acc(at["TEXCOORD_0"]).astype(np.float64)
                f = acc(pr["indices"]).reshape(-1, 3).astype(np.int64) if "indices" in pr else \
                    np.arange(len(pos)).reshape(-1, 3)
                c = uv[f].mean(axis=1)
                h, w = img.shape[:2]
                x = np.clip((c[:, 0] % 1.0) * w, 0, w - 1).astype(np.int64)
                y = np.clip((c[:, 1] % 1.0) * h, 0, h - 1).astype(np.int64)   # (glTF: v from the top)
                rgbs.append(img[y, x])
                areas.append(0.5 * np.linalg.norm(np.cross(pos[f[:, 1]] - pos[f[:, 0]], pos[f[:, 2]] - pos[f[:, 0]]),
                                                  axis=1))
    except (KeyError, IndexError, ValueError, OSError):
        return None, None
    if not rgbs:
        return None, None
    return np.concatenate(rgbs), np.concatenate(areas)


def view_colours(r, families):
    """each colour family -> the median sRGB of the view's object pixels that are that family (rbx_lathe.match_families:
    by kind and hue, so the view's light does not move a pixel to another family) — {family index: (r, g, b)}, only
    for a family with >= 2% of the pixels; {} without a cut-out view"""
    view = next((os.path.join(r.dir, f"view_{v}_rgba.png") for v in ("front", "back", "left", "right")
                 if os.path.isfile(os.path.join(r.dir, f"view_{v}_rgba.png"))), None)
    if not view or not families:
        return {}
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
    import rbx_lathe  # noqa: PLC0415

    im = np.asarray(Image.open(view).convert("RGBA"))
    px = im[im[..., 3] > 127][:, :3].astype(np.float64)
    if len(px) < 100:
        return {}
    px = px[:: max(1, len(px) // 60000)]
    lab = rbx_lathe.match_families(px, families)
    out = {}
    for i in range(len(families)):
        sel = px[lab == i]
        if len(sel) >= 0.02 * len(px):
            out[i] = tuple(float(v) for v in np.median(sel, axis=0))
    return out


def colour_regions(r, glb):
    """the made shape's colour regions -> [{name, srgb, share, kind, finish | scan, color, why}] (rbx_regions): its form
    kept, each colour region a real kit finish instead of the generator's muddy texture (owner 2026-10-16: the made
    props 2 / 0 / 3.5, "the colour and texture are horrible, the model is good")"""
    rgb, area = face_colours(glb)
    if rgb is None or len(rgb) < 10:
        return []
    sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
    import rbx_regions  # noqa: PLC0415

    found = rbx_regions.clusters(rgb, area)
    seen = view_colours(r, [m for _s, _sh, m in found])
    out, used = [], {}
    for i, (srgb, share, members) in enumerate(found):
        # its COLOUR from the view (the design itself), its family from the texture: the generator's texture is
        # washed out — the made barrel's oak (155, 131, 98) where the view's is a darker, warmer brown
        # — only when it names the same KIND of finish (a lamp's panes in the view are the dark inside seen through
        # the glass: grey steel there, a pale pane in the texture — the texture's kind stays)
        pick = rbx_regions.choose(srgb, share, [r.obj])
        if i in seen:
            alt = rbx_regions.choose(seen[i], share, [r.obj])
            if alt["kind"] == pick["kind"]:
                srgb, pick = seen[i], alt
        base = pick["kind"]
        used[base] = used.get(base, 0) + 1
        name = base if used[base] == 1 else f"{base}{used[base]}"
        out.append({"name": name, "srgb": [round(v) for v in srgb], "share": share,
                    "shades": [[round(v) for v in m] for m in members], **pick})
    return out


def colour_bands(r, regions):
    """a ROUND body's colour bands -> [(t0, t1, region name)]: the view's rows (front, else back, else a side) read at
    the slices make_clean --round trued (rbx_lathe.bands: a row >= 60% one family, judged by kind and hue — the
    concept's barrel is lit from above, its hoops dark grey at the bottom and pale at the top), merged into runs; only
    ROUND slices (a valve, a lantern keep the colour their own faces read). [] when nothing is round."""
    rnd = r.facts.get("round") or {}
    prof = rnd.get("profile") or []
    n = int(rnd.get("slices") or 0)
    view = next((os.path.join(r.dir, f"view_{v}_rgba.png") for v in ("front", "back", "left", "right")
                 if os.path.isfile(os.path.join(r.dir, f"view_{v}_rgba.png"))), None)
    if not (prof and n and view and regions):
        return []
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
    import rbx_lathe  # noqa: PLC0415

    lab = rbx_lathe.bands(np.asarray(Image.open(view).convert("RGBA")), n=n,
                          families=[g.get("shades") or [g["srgb"]] for g in regions])
    round_k = {min(n - 1, int(tc * n)) for tc, _r in prof}
    runs = []
    for k in range(n):
        name = regions[lab[k]]["name"] if (k in round_k and lab[k] is not None) else None
        if name and runs and runs[-1][2] == name and abs(runs[-1][1] - k / n) < 1e-9:
            runs[-1][1] = (k + 1) / n
        elif name:
            runs.append([k / n, (k + 1) / n, name])
    return [(round(a, 4), round(b, 4), nm) for a, b, nm in runs]


def region_lines(regions, life, round_body=False):
    """kit make's material lines for the regions + the regions= mapping (round_body: a wood scan's grain runs up it —
    a barrel's staves; the box projection laid it across them)"""
    lines = []
    for g in regions:
        if g.get("scan"):   # (wood: the measured colour, its scan, wood's roughness)
            up = ', scan_grain="up"' if round_body else ""
            lines.append(f'a.material("{g["name"]}", {tuple(g["color"])}, rough=0.62, scan="{g["scan"]}", scan_mix=1.0, '
                         f'life="{life}"{up})   # {g["why"]} ({g["share"]:.0%})')
        else:
            col = f', color={tuple(g["color"])}' if g.get("color") else ""
            lines.append(f'a.material("{g["name"]}", **rbx.finish("{g["finish"]}"{col}), life="{life}")   '
                         f'# {g["why"]} ({g["share"]:.0%})')
    # (every shade a region merged: matched against one colour each, shaded wood went to the steel)
    mapping = "{" + ", ".join(f'"{g["name"]}": {[tuple(m) for m in g.get("shades") or [g["srgb"]]]}'
                              for g in regions) + "}"
    return lines, mapping


BRIEF_MARK = "<!-- written by kit make from the owner's request; edit any answer: it is then the owner's -->"


def write_brief(r, mesh=None):
    """assets/models/<name>.brief.md from the owner's own REQUEST (`kit make <name> "<object>" --tier .. [--private]`):
    what it is, the tier (the clock's budget), what must work (a prop is static), whose design, and the parts plan of
    the route kit make runs (kit plan's stage-0 gate, mission 01-3d §5.1). Never over a brief the owner wrote: only a
    missing one, or one this function wrote (its first line says so) and nobody edited since."""
    path = os.path.join(REPO, "assets", "models", f"{r.name}.brief.md")
    try:
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
    except OSError:
        old = None
    if old is not None and not old.startswith(BRIEF_MARK):
        return path  # (the owner's brief: theirs)
    if old is not None:
        body = old.rpartition("<!-- sha:")[0]
        if old != body + f"<!-- sha:{_brief_sha(body)} -->\n":
            return path  # (edited since kit make wrote it — anywhere, a line added after its mark too: the owner's)
    sizes = r.facts.get("sizes") or {}
    said = ", ".join(f"{k} {v.get('mm'):g} mm ({v.get('grade', '?')})" for k, v in sizes.items()
                     if isinstance(v, dict) and v.get("mm")) or "the category's graded sizes (kit make know)"
    views = sorted((r.facts.get("views") or {}).keys()) if isinstance(r.facts.get("views"), dict) else []
    route = "photos" if is_named_object(r) else "concept"
    moving = "none (a prop is static)" if r.tier == "prop" else "<answer>"
    function = "static" if r.tier == "prop" else "<answer>"
    draft = (os.path.relpath(mesh, REPO).replace(os.sep, "/") if mesh else
             "the tournament's winner (kit make: build/make/" + r.name + "/report.md)")
    surf = surface_of(r)
    text = f"""{BRIEF_MARK}
# {r.name} — the brief

- what: {r.obj}
- end goal: master (kit make)
- quality: {r.tier}
- quality bar: the owner's verdicts on kit make props of this category (kit/knowledge/vault/3d/golden.md)
- style: realistic PBR
- view: world prop (third person, all sides)
- function: {function}
- moving parts: {moving}
- extras: none
- references: the object's {route} views kit make gathers ({', '.join(views) or 'front, side, back'}); sizes: {said}
- ownership: {"someone else's design (private=True: never uploaded)" if r.private else "a generic / public object"}
- hero features:
  1. the whole object | generated + projected | the object as the owner named it | {r.obj}
- parts plan:
  1. Body | generated (kit make tournament on measured criteria, never crispness){" + painted (private)" if r.private else " + colour regions -> kit finishes"} | the {route} views, graded sizes, reference models graded for quality | {"its paint" if r.private else "a kit finish per colour region (paint / steel / rubber / wood scan)"}, life {surf.get('life')}
- draft: {draft}
- reference models: the ones kit make grades (build/make/{r.name}/report.md)
"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + f"<!-- sha:{_brief_sha(text)} -->\n")
    return path


def _brief_sha(text):
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_build(r, mesh):
    """assets/models/build_<name>.py — the build `kit asset` runs, MADE BY kit make (its first line says so): the
    winning shape at its real size, painted. Before a winner exists: a stub that only names the asset."""
    sizes = r.facts.get("sizes") or {}
    w = sizes.get("width", {}).get("mm")
    h = sizes.get("height", {}).get("mm")
    ln = sizes.get("length", {}).get("mm")
    big = max([x for x in (w, h, ln) if x] or [1000.0])
    box = tuple(round((x or big) / MM, 4) for x in (w, h, ln))
    shape = winner_size(r)
    graded = all(v.get("grade") in ("A", "B") for v in sizes.values()) and len(sizes) >= 2
    if shape and not graded:
        # the size is only the CATEGORY's range (a dining chair's 0.93 m): the photo's object may be another kind of
        # it (a low Egyptian chair) — its height sets the scale, the shape keeps its own proportions
        sx, sy, sz = shape        # x right, y front (length), z up (height) — Blender's frame of the views
        k = (h or big) / MM / max(sz, 1e-9)
        box = (round(sx * k, 4), round(sz * k, 4), round(sy * k, 4))
    ground = r.facts.get("category") not in ("pistol", "rifle")
    photo = best_photo(r)[1]
    quality = {"hero": ', quality="hero"', "complex": "", "prop": ""}[r.tier]
    lines = [f'"""build_{r.name}.py — MADE BY kit make ({r.obj!r}, {r.tier}): do not hand-edit; run `lune run kit make '
             f'{r.name} "{r.obj}"` again. The winning generated shape at its real size, painted from the photo."""',
             "import os", "import sys", "",
             "_root = os.path.dirname(os.path.abspath(__file__))",
             'while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:',
             "    _root = os.path.dirname(_root)",
             'sys.path.insert(0, os.path.join(_root, "kit", "blender"))',
             "import rbx  # noqa: E402", "",
             f"MM = {MM}",
             f'a = rbx.Asset("{r.name}", size={box}, ground={ground}, stage="master", private={r.private}'
             f'{quality}' + (f', ref_image={os.path.relpath(photo, REPO).replace(os.sep, "/")!r}' if photo else "")
             + ")",
             "a.real_scale(MM)"]
    if mesh:
        win = r.facts.get("winner")
        yaw = ((r.facts.get("tournament") or {}).get(win or "") or {}).get("yaw", 0)
        # by its HEIGHT (a turn about up leaves it alone; the fit reads the mesh before turning it), turned by the
        # tournament's yaw
        surf = "".join(f", {k}={v!r}" for k, v in surface_of(r).items())
        # a PUBLIC asset keeps the generator's own texture (Hunyuan Paint is private-only) — muddy, its lighting baked
        # in: the owner rated three such props 2 / 0 / 3.5, "colour and texture horrible, the model is good". Its
        # colours only decide which kit FINISH each face gets (rbx_regions): paint, steel, rubber, wood with its scan
        regions = colour_regions(r, mesh) if not r.private else []
        r.facts["regions"] = regions
        if regions:
            mat_lines, mapping = region_lines(regions, surface_of(r).get("life", "light"),
                                              round_body=(r.facts.get("round") or {}).get("round_share", 0) >= 0.6)
            lines += mat_lines
            surf = f", rough=0.6, regions={mapping}"
            bands = colour_bands(r, regions)
            r.facts["bands"] = bands
            if bands:
                surf += f", bands={bands}"
        if graded:   # each axis to its graded size, in the mesh's own frame (the yaw turns it after: x <-> z)
            own = (box[2], box[1], box[0]) if yaw in (90, 270) else box
            fit = f"size={own}, stretch=True"
        else:
            fit = f"height={box[1]}"
        lines.append(f'a.import_mesh("Body", {os.path.relpath(mesh, REPO).replace(os.sep, "/")!r}, {fit}, '
                     f'rot=(0, {yaw}, 0){surf})')
        # the shape fitted to a REAL photo's outline (a generator's bulges back to what was photographed: the judges
        # called the Glock's grip 10% too fat) — only the views along the object's THIN axis (a pistol's sides: an
        # outline the camera sees nearly flat-on) with an outline 600+ px long; its 190 px front and back frames,
        # in perspective (the muzzle nearer the lens), dented the flanks when fitted too. A concept's: never.
        thin = min(range(3), key=lambda i: box[i])   # (box: x width, y height, z length)
        fit_views = {0: ("side",), 1: ("top",), 2: ("front", "back")}[thin]
        for v, t in (r.facts.get("traces") or {}).items():
            if t.get("measure", True) and t["view"] in fit_views and trace_length_px(t["trace"]) >= 600:
                # (a boolean cut to the outline's prism: crisp walls — dragging vertices onto it tore the flank)
                lines.append(f'a.trim_to_outline("{t["trace"]}", view="{t["view"]}")')
        for v, t in (r.facts.get("traces") or {}).items():   # THE object's photos: measured against, painted on
            if t.get("measure", True):   # (a specimen's photo: its silhouette only — never its inside lines)
                lines.append(f'a.trace_match("{t["trace"]}", view="{t["view"]}", bar=0.5'
                             + (", lines=False" if t.get("specimen") else "") + ")")
            # (the photo's colour as it is: flatten — each pixel over its surroundings — turned a black gun into a grey
            # pencil sketch with dark edges)
            # (and its fine structure as relief: the photo's serrations and stippling catch the light too; ONE side
            # view paints the other side mirrored — a concept's chest showed its right end plain)
            if t.get("specimen"):   # (another specimen's photo: measured against, never painted on)
                continue
            if regions:   # (the finishes ARE the surface: a projected picture painted the muddy look back on)
                continue
            one_side = t["view"] == "side" and not ({"left", "right"} - {v} <= set(r.facts.get("traces") or {}))
            rm = f", relief_map={os.path.relpath(t['relief_map'], REPO).replace(os.sep, '/')!r}"                 if t.get("relief_map") else ""
            lines.append(f'a.project("{t["trace"]}", view="{t["view"]}", mix=0.9, relief={RELIEF}{rm}'
                         + (", mirror=True" if one_side else "") + ")")
    else:
        lines.append(f'a.box("Placeholder", {box}, (0, {box[1] / 2 if ground else 0}, 0), "steel")   '
                     "# (kit make has not made the shape yet)")
        lines.insert(lines.index("a.real_scale(MM)") + 1, 'a.material("steel", **rbx.finish("machined_steel"))')
    # hand fixes ride ON TOP of the made model, never instead of it: assets/models/<name>.override.py (a, rbx in scope)
    lines += [f'_ov = os.path.join(os.path.dirname(os.path.abspath(__file__)), "{r.name}.override.py")',
              "if os.path.isfile(_ov):",
              "    import runpy  # noqa: E402",
              '    runpy.run_path(_ov, init_globals={"a": a, "rbx": rbx})']
    lines.append("a.build()")
    path = os.path.join(REPO, "assets", "models", f"build_{r.name}.py")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def trace_length_px(name):
    """a trace's outline length in its picture's pixels (its frame), 0 if unreadable"""
    try:
        with open(os.path.join(REPO, "assets", "models", f"{name}.trace.json"), encoding="utf-8") as fh:
            return float((json.load(fh).get("frame") or {}).get("length_px") or 0)
    except (OSError, ValueError):
        return 0.0


def winner_size(r):
    """the winning shape's own size (x right, y front, z up) from its tournament views, or None"""
    win = r.facts.get("winner")
    t = (r.facts.get("tournament") or {}).get(win or "")
    try:
        with open(os.path.join(t["views"], "views.json"), encoding="utf-8") as fh:
            sx, sy, sz = json.load(fh)["size"]
        return (sy, sx, sz) if t.get("yaw") in (90, 270) else (sx, sy, sz)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def stage_look(r):
    mesh = r.facts.get("surface_mesh")
    if not mesh:
        for m in ("build", "compare", "judge_packet"):
            r.mod("look", m, False, "no shape was made")
        return
    write_brief(r, mesh)
    write_build(r, mesh)
    if not r.fits(40):
        for m in ("build", "compare", "judge_packet"):
            r.mod("look", m, False, f"budget: {r.left():.0f} s left")
        return
    ok, res, secs = r.kit(["asset", r.name], timeout=max(120, r.left()))
    sheet = os.path.join(REPO, "build", "renders", f"{r.name}.png")
    built = os.path.isfile(sheet) and os.path.getmtime(sheet) >= r.t0
    gate = next((x.get("summary") for x in res if x and x.get("summary")), "")
    r.mod("look", "build", built, "" if built else f"the build failed: {gate[:160]}",
          note=f"{secs:.0f} s; its gates: {gate[:120]}")
    comp = os.path.join(REPO, "build", "renders", f"{r.name}_compare.png")
    if built and os.path.isfile(comp):
        shutil.copy(comp, os.path.join(r.dir, "compare.png"))
        r.mod("look", "compare", True, note=f"build/make/{r.name}/compare.png (the render beside the photo)")
    else:
        r.mod("look", "compare", False, "no comparison render (no reference picture, or the build failed)")
    if r.tier != "hero":
        r.mod("look", "judge_packet", False, f"{r.tier} tier: fresh judges are for heroes (the tournament judged it)")
    elif built:
        ok, _res, _s = r.kit(["judge", r.name], timeout=300)
        r.mod("look", "judge_packet", ok, "" if ok else "kit judge could not make the packet",
              note=f"build/judge/{r.name}/PROMPT.md: hand it to fresh judges")
    else:
        r.mod("look", "judge_packet", False, "nothing built to judge")


# ================================================================================================= the two stops
STOP_TIERS = ("complex", "hero", "aaa")
STOP_NAMES = {"sheet": "model sheet", "blockout": "blockout"}


def stage_stop(r, step):
    """KIT MAKE'S TWO STOPS (his limitations review, 2026-11-17: "halt kit make automatically at --stage sheet and
    --stage blockout for complex / hero / aaa briefs"): after the references are gathered the kit draws the MODEL SHEET
    (kit sheet) and goes on to any generator only once the owner approved it; after the shape is fitted it draws the
    BLOCKOUT (kit blockout, from the build script of the fitted shape) and goes on to the bake only once he approved
    that. The question is kit asset's own (kit make-gate -> LaneLocks.stageProblem): drawn, still true, approved,
    unchanged since. A prop never stops. -> True to go on; False: r.stopped says why and what to do."""
    if r.tier not in STOP_TIERS:
        return True
    if step == "blockout":
        mesh = r.facts.get("clean_mesh") or (r.facts.get("candidates") or {}).get(r.facts.get("winner") or "")
        if not mesh:
            return True   # (nothing was shaped: the stages after say so themselves)
        # (the build script only: the brief stays as the approved model sheet was drawn from it - rewritten here with
        #  the shape's path it would make that sheet, and so this blockout, stale on every run)
        write_build(r, mesh)
    drew, _res, _s = r.kit([step, r.name], timeout=900)
    r.say(f"[{step}] the {STOP_NAMES[step]} {'drawn' if drew else 'NOT drawn (the gate says why)'}")
    ok, _res, _s = r.kit(["make-gate", r.name, step, "--tier", r.tier], timeout=300)
    if ok:
        r.say(f"[{step}] the owner approved the {STOP_NAMES[step]} as it is now: going on")
        return True
    why = ""
    try:
        with open(os.path.join(REPO, ".verify", "make-gate.json"), encoding="utf-8") as fh:
            why = json.load(fh).get("next_action") or ""
    except (OSError, ValueError):
        pass
    r.stopped = (f"STOPPED for the owner at the {STOP_NAMES[step]} ({r.tier}): "
                 + (why or f"lune run kit make-gate {r.name} {step}"))
    r.stop_step = step
    r.say(r.stopped)
    return False


# ================================================================================================= the run
def main(argv):
    if len(argv) < 2 or argv[0].startswith("-"):
        return emit("fail", 'make: needs <name> "<object>"',
                    'lune run kit make chair "wooden chair" --tier prop')
    name, obj = argv[0], argv[1]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return emit("fail", f"make: '{name}' is not a snake_case name", 'lune run kit make chair "wooden chair"')
    tier = argv[argv.index("--tier") + 1] if "--tier" in argv else "prop"
    if tier not in TIERS:
        return emit("fail", f"make: --tier is prop, complex or hero (not {tier})", "")
    if "--no-gen" in argv and "--concept" in argv:
        return emit("fail", "make: --no-gen and --concept contradict (a concept picture IS a generator's)",
                    f'lune run kit make {name} "{obj}" --no-gen  (real photos)')
    r = Run(name, obj, tier, private="--private" in argv)
    r.fresh = "--fresh" in argv
    r.route = "photos" if "--photos" in argv else "concept" if "--concept" in argv else None
    r.use = argv[argv.index("--use") + 1] if "--use" in argv else None
    # NO GENERATORS (the owner's choice for a pure sculpt / code model): no 3D generator, no concept picture, no paint —
    # the real photos, their traced views and the hulls made from them (traced / sculpted); the sculpting and detail
    # ride on top in assets/models/<name>.override.py
    r.no_gen = "--no-gen" in argv
    r.stopped = None
    r.say(f"kit make {name}: '{obj}', {tier}, budget {r.budget} s" + (", NO generators" if r.no_gen else ""))
    fns = {"know": stage_know, "gather": stage_gather, "candidates": stage_candidates, "tournament": stage_tournament,
           "fit": stage_fit, "surface": stage_surface_all, "mechanism": stage_mechanism, "look": stage_look}
    for st in STAGES:
        t = time.time()
        try:
            fns[st](r)
        except Exception as e:  # noqa: BLE001 — a stage that crashed is reported, never hidden
            import traceback  # noqa: PLC0415

            r.say(f"[{st}] CRASHED: {e}\n{traceback.format_exc()}")
            for module in MODULES[st]:
                if module not in r.stages.get(st, {}).get("modules", {}):
                    r.mod(st, module, False, f"the stage crashed: {type(e).__name__}: {e}"[:200])
        r.stages.setdefault(st, {"seconds": 0.0, "modules": {}, "facts": {}})["seconds"] = round(time.time() - t, 1)
        # (the two stops: the model sheet before any generator, the blockout before the bake)
        stop_at = {"gather": "sheet", "fit": "blockout"}.get(st)
        if stop_at and not stage_stop(r, stop_at):
            for later in STAGES[STAGES.index(st) + 1:]:
                for module in MODULES[later]:
                    r.mod(later, module, False, f"waiting for the owner's approval of the {STOP_NAMES[stop_at]}")
            break
    if r.stopped:
        rep = r.write(False, f"{name}: {r.stopped}")
        return emit("fail", f"make {name}: {r.stopped}", r.stopped.split(": ", 1)[-1],
                    report=f"build/make/{name}/report.json", stopped=r.stop_step)
    win = r.facts.get("winner")
    built = (r.stages.get("look", {}).get("modules", {}).get("build") or {}).get("ran")
    summary = (f"{name}: {'built from ' + win if win and built else 'NOT built'} in {time.time() - r.t0:.0f} s of "
               f"{r.budget} s")
    rep = r.write(bool(built), summary)
    return emit("pass" if rep["ok"] else "fail",
                f"make {summary}; report build/make/{name}/report.md",
                f"LOOK at build/make/{name}/compare.png beside the photo, then build/make/{name}/report.md"
                + (f"; judges: build/judge/{name}/PROMPT.md" if r.tier == "hero" and built else ""),
                report=f"build/make/{name}/report.json")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
