"""rbx_score.py — the quality score's ARITHMETIC, with no bpy: weights, the raw score from measured components, the
owner-calibrated map, the wood test, the ratchet. rbx_quality measures (in Blender); this file turns measurements
into numbers — and runs in plain python too (unit tests, `kit grades --fit`).

The weights are FITTED to the owner's blind grades: kit/weights.json (written by `lune run kit grades --write` only
when the refit beats the hand weights on grades it never saw) — without it, the hand weights below. A grade keeps the measured components of its build (kit/grades.json), so a refit, or a
new grade, re-scores every graded build — and the ratchet re-scores the accepted build the same way, so an unchanged
build can never fail it because the scale moved.
"""

import hashlib
import json
import math
import os
import re

KIT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)

TIERS = {"prop": 55, "hero": 75, "aaa": 88}
# distinct KINDS of small detail (50 identical fins are one kind), triangles the form deserves, per tier
VARIETY_TARGET = {"prop": 4, "hero": 10, "aaa": 16}
TRI_TARGET = {"prop": 2500, "hero": 9000, "aaa": 16000}
# the hand weights the kit used until the owner graded — and its fallback: the live weights are kit/weights.json, which
# only `lune run kit grades --write` writes (a refit that beat these on grades it never saw: see _main)
HAND_WEIGHTS = {"silhouette": 6, "detail": 18, "empty": 16, "variety": 14, "geometry": 8, "materials": 6,
                "surface": 12, "texture": 10, "markings": 5, "reference": 5}
RATCHET_RAW = 2.0  # a build more than this many RAW points below the accepted build (re-scored today) fails
# the MEASURING code's version: bump it whenever a component's definition changes (what a measure sees, not its
# weight). A grade or an accepted build keeps the version it was measured with: the ratchet compares only builds
# measured alike (a new measure would otherwise fail, or pass, an unchanged build), and grades are re-measured.
# 3 = 2026-10-06: texture = the albedo a player sees (views it can be measured on), see-through on the longer side,
#     craft counts every cut into wood
# 4 = 2026-10-06: craft counts carved REGIONS (a comb cutter's 37 grooves are 37), texture falls back to the best
#     view of a slender prop, see-through counts a slit's true area
# 5 = 2026-10-06: carved regions are each cut's OWN faces (tagged through the boolean: a cutter of the part's own
#     material, grooves that meet earlier ones), plus the carved share of the wood's surface
# 6 = 2026-10-06: every slot of a cutter is tagged (a comb fused of two materials), a cut is in wood where it borders
#     wood faces (a part fused of steel and wood), wood is measured per face over the parts that are seen (an internal
#     block no longer waters down the carved share) plus the walls carved into it (its own carved surface, in whatever
#     material the cutter declared), and lines baked on wood (floater seams) count with the grooves
# 7 = 2026-10-06: the walls carved into wood are marked on the mesh (face layer kit_wood_cut) and measured on the FINAL
#     model: a wall a later cut removed is gone, an internal part's walls are not seen, walls of the wood's own material
#     are counted once; a cut into the floor of an earlier recess is still a cut into the wood; text is exempt from the
#     baked lines by its tag, never by a name. Each build also records the sha of the script that made it.
# 8 = 2026-10-10: material zones are counted per FACE (a.zone's regions count: a part's first material alone missed
#     them — the stump's sawn top, a grip's textured panels), areas at the object's scale squared (the owner's OK)
MEASURE_VERSION = 8
MIN_COMPONENT_GRADES = 5  # with this many component-carrying grades, raw-only (older scale) grades are left out


def _load_weights():
    """kit/weights.json (the owner-fitted weights, written by `kit grades --write`), else the hand weights"""
    path = os.path.join(KIT, "weights.json")
    try:
        with open(path, encoding="utf-8") as fh:
            w = json.load(fh).get("weights") or {}
        if w and all(isinstance(v, (int, float)) and v >= 0 for v in w.values()):
            return {**HAND_WEIGHTS, **w}
    except (OSError, ValueError, AttributeError):
        pass
    return dict(HAND_WEIGHTS)


WEIGHTS = _load_weights()

# WOOD by what a material is called: whole words, camelCase split ("DarkWood", "WoodPlank"), and words ending or
# starting in "wood" ("redwood", "woodgrain"). Not wood: "keyboard", "dashboard", "spine", "cloak"; "board" alone
# (a circuit board), "ash" (ash grey: say "ashwood"), "woodland" (a camouflage pattern)
WOOD_WORDS = {"wood", "wooden", "plank", "planks", "timber", "lumber", "plywood", "oak", "pine", "walnut", "mahogany",
              "birch", "cedar", "maple", "teak", "spruce", "beech", "driftwood", "hardwood", "softwood"}
NOT_WOOD = {"woodland", "woodlands"}


def is_wood_name(name):
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "").lower()
    for t in re.split(r"[^a-z]+", words):
        if not t or t in NOT_WOOD:
            continue
        if t in WOOD_WORDS or t.endswith("wood") or t.startswith("wood"):
            return True
    return False


# an ORGANIC form's detail lives IN its surface and its palette in one material's tones (a stump is one bark, its
# detail sculpted into it; a gun is twenty parts in four materials): on an organic model these components are also
# earned by the measure named here (the owner's choice, 2026-10-10: organic props were scored on a gun's terms)
ORGANIC_FROM = {"variety": "detail", "materials": "texture"}


def effective(comp):
    """the components the weights multiply: as measured — except on an ORGANIC model (comp["organic"]: the share of
    what is seen that was sculpted, 0..1), whose variety is also earned by its surface detail and whose materials by
    its colour variation, blended by that share (nothing jumps at a line; a model with no "organic" — every grade and
    floor before it — is scored exactly as before)"""
    s = min(1.0, max(0.0, float(comp.get("organic", 0.0) or 0.0)))
    if not s:
        return comp
    out = dict(comp)
    for k, src in ORGANIC_FROM.items():
        if k in comp and src in comp:
            out[k] = comp[k] + s * max(0.0, comp[src] - comp[k])
    return out


def alike(then, now):
    """a floor / history entry measured before the organic share existed, weighed like the build it is compared with:
    the same object's sculpted share hardly moves, so the old components take today's (else a sculpted build's organic
    credit would hide a real drop against its floor) -> then's components"""
    if isinstance(then, dict) and isinstance(now, dict) and "organic" in now and "organic" not in then:
        return {**then, "organic": now["organic"]}
    return then


def raw_of(comp, tier, weights=None):
    """the raw 0-100 score from measured components — ONE formula for a build, a stored grade and an accepted
    build: weighted mean (of the effective components: an organic model's, above) x the craft factor (comp["craft"],
    1 = sound)"""
    comp = effective(comp)
    w = dict(weights or WEIGHTS)
    if tier == "prop":
        w["markings"] = 0
    if "reference" not in comp:
        w["reference"] = 0
    total = sum(w[k] for k in comp if w.get(k))
    if not total:
        return 0.0
    return round(sum(comp[k] * w[k] for k in comp if w.get(k)) / total * 100 * comp.get("craft", 1.0), 1)


def load_grades(path=None):
    try:
        with open(path or os.path.join(KIT, "grades.json"), encoding="utf-8") as fh:
            grades = json.load(fh)
        return [g for g in grades if isinstance(g, dict)]
    except (OSError, ValueError):
        return []


def current_grades(grades):
    """the grades whose components were measured by TODAY's measuring code (MEASURE_VERSION) — when there are enough of
    them; otherwise every grade with components (an older measure is still better than no calibration at all)"""
    comp = [g for g in grades if isinstance(g.get("components"), dict) and isinstance(g.get("owner"), (int, float))]
    now = [g for g in comp if g.get("measure") == MEASURE_VERSION]
    return now if len(now) >= MIN_COMPONENT_GRADES else comp


def grade_points(grades, weights=None):
    """(raw, owner) per grade on TODAY's scale: component grades re-scored (those measured by today's measuring code,
    when there are enough); raw-only grades (an older scale) only while fewer than MIN_COMPONENT_GRADES exist"""
    comp = current_grades(grades)
    pts = [(raw_of(g["components"], g.get("tier", "prop"), weights), float(g["owner"])) for g in comp]
    if len(comp) < MIN_COMPONENT_GRADES:
        pts += [(float(g["raw"]), float(g["owner"])) for g in grades
                if not isinstance(g.get("components"), dict) and isinstance(g.get("raw"), (int, float))
                and isinstance(g.get("owner"), (int, float))]
    return sorted(pts)


def isotonic_knots(pts):
    """monotone (non-decreasing) fit through (raw, owner) points, anchored at (0, 0): pool adjacent violators"""
    blocks = [[0.0, 0.0, 1.0]]
    for x, y in sorted(pts):
        blocks.append([x, y, 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            xs, ys, n = blocks.pop()
            blocks[-1][0] += xs
            blocks[-1][1] += ys
            blocks[-1][2] += n
    return [(b[0] / b[2], b[1] / b[2]) for b in blocks]


def map_knots(raw, knots):
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if raw <= x1:
            return round(max(0.0, min(100.0, y0 + (y1 - y0) * (raw - x0) / max(x1 - x0, 1e-6))), 1)
    (x0, y0), (x1, y1) = knots[-2], knots[-1]
    return round(max(0.0, min(100.0, y1 + (y1 - y0) / max(x1 - x0, 1e-6) * (raw - x1))), 1)


def calibrate(raw, grades=None, weights=None):
    """raw 0-100 -> the owner's scale through every grade (monotone: a higher raw never maps lower, so calibration
    never reorders two builds). -> (score, number of grades used); no grades -> (raw, 0)"""
    pts = grade_points(load_grades() if grades is None else grades, weights)
    if not pts:
        return raw, 0
    return map_knots(raw, isotonic_knots(pts)), len(pts)


def models_dir():
    """the project's model folder (kit.config.json paths.models), where accepted builds live beside the scripts"""
    try:
        with open(os.path.join(REPO, "kit.config.json"), encoding="utf-8") as fh:
            rel = (json.load(fh).get("paths") or {}).get("models") or "assets/models"
    except (OSError, ValueError):
        rel = "assets/models"
    return os.path.join(REPO, rel)


def _slash(path):
    return path.replace(chr(92), "/")


GIT_BROKEN = "git-broken"  # _committed: the project is a git repository, but git could not answer


def _git(root, *args):
    """run git in `root` as the repository says — never as the environment says (GIT_DIR / GIT_OBJECT_DIRECTORY / ...
    are dropped) and never through replace objects -> (returncode, stdout bytes)"""
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    out = subprocess.run(["git", "--no-replace-objects", "-C", root, *args], capture_output=True, env=env, timeout=20)
    return out.returncode, out.stdout


def _committed(path, root=None):
    """the last COMMITTED version of the floor at `path` -> (text, revision) — at HEAD, or before the commit that deleted
    it. Found in the project's repository (`root`, default REPO) by its path, CASE-INSENSITIVELY (Windows opens
    "Crate.accepted.json" as "crate.accepted.json"; git would not), else by its file name anywhere in the tree (a
    models folder moved in kit.config.json). (None, None): never committed, or no git repository; (GIT_BROKEN, None):
    a git repository git could not read — a floor that cannot be checked is a broken one, never a missing one"""
    import subprocess

    root = os.path.abspath(root or REPO)
    is_repo = os.path.exists(os.path.join(root, ".git"))
    rel = _slash(os.path.relpath(os.path.abspath(path), root))
    name = os.path.basename(rel)
    try:
        code, top = _git(root, "rev-parse", "--show-toplevel")
        if code != 0:
            return (GIT_BROKEN, None) if is_repo else (None, None)
        top = top.decode("utf-8").strip()
        if not is_repo and os.path.normcase(os.path.abspath(top)) != os.path.normcase(root):
            # (the project sits inside some other repository: its own path inside that one)
            rel = _slash(os.path.relpath(os.path.abspath(path), os.path.abspath(top)))
            root = os.path.abspath(top)
        if rel.startswith("../"):
            return None, None  # (a floor outside the repository: git cannot vouch for it)

        def find(rev):
            # (ls-tree takes no pathspec magic: every name at `rev`, matched here — the path case-insensitively, else
            # the file name in any folder)
            c, out = _git(root, "ls-tree", "-r", "--name-only", "-z", rev)
            names = [n for n in out.decode("utf-8").split(chr(0)) if n] if c == 0 else []
            exact = [n for n in names if n.lower() == rel.lower()]
            anywhere = [n for n in names if n.lower().rsplit("/", 1)[-1] == name.lower()]
            return (exact or anywhere or [None])[0]

        def show(rev, at):
            c, out = _git(root, "show", f"{rev}:{at}")
            return out.decode("utf-8") if c == 0 else None

        hit = find("HEAD")
        if hit:
            return show("HEAD", hit), "HEAD"
        for spec in (f":(icase){rel}", f":(icase,glob)**/{name}"):
            c, out = _git(root, "log", "-1", "--format=%H", "--", spec)
            h = out.decode("utf-8").strip() if c == 0 else ""
            if h:
                for rev in (h, f"{h}^"):
                    at = find(rev)
                    if at:
                        return show(rev, at), rev
        return None, None
    except (OSError, ValueError, subprocess.SubprocessError):
        return (GIT_BROKEN, None) if is_repo else (None, None)


def read_floor(path, root=None, git=True):
    """an accepted record (kit accept) -> (record, where). Once a floor is COMMITTED, the committed one holds (at HEAD,
    or before the commit that deleted it; found case-insensitively, wherever the models folder is): a change of floor —
    an owner's --lower, a re-base, a plain re-accept — takes effect when it is committed, and no edit, deletion or
    breakage of the file moves it (git shows every change of floor). A floor never committed is only its file.
    where = "file" (the file IS the committed floor, or nothing was committed yet); "git" (the file differs from the
    committed floor, is broken or gone: the committed one holds — record["restore"] says how to put it back);
    "unreadable" (broken and never committed, or a git repository git could not read: {"unreadable": True}); (None,
    None) — no floor. git=False reads the file alone (the selftest's own fixtures: weakening one fails the selftest)"""
    rec = None
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            rec = None
    text, rev = _committed(path, root) if git else (None, None)
    if text == GIT_BROKEN:
        return {"unreadable": True, "why": "the project is a git repository but git could not read it"}, "unreadable"
    old = None
    if text is not None:
        try:
            old = json.loads(text)
        except ValueError:
            old = None
    if isinstance(old, dict):
        if rec == old:
            return old, "file"
        rel = _slash(os.path.relpath(os.path.abspath(path), os.path.abspath(root or REPO)))
        return dict(old, restore=f"git checkout {rev} -- {rel}"), "git"
    if isinstance(rec, dict):
        return rec, "file"
    if os.path.isfile(path):
        return {"unreadable": True}, "unreadable"
    return None, None


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def accepted(name):
    """the accepted build of `name` (kit accept) or None; selftest fixtures keep theirs beside their script. A floor
    file that was deleted or broken is read from git (rec["from_git"] = its path); broken and never committed ->
    {"unreadable": True}"""
    fixture = os.path.join(KIT, "selftest", "blender", f"{name}.accepted.json")
    for path in (os.path.join(models_dir(), f"{name}.accepted.json"), fixture):
        rec, where = read_floor(path, git=path != fixture)
        if rec is not None:
            if where == "git":
                return dict(rec, from_git=_slash(os.path.relpath(path, REPO)))
            return dict(rec, asset=name) if where == "unreadable" else rec
    return None


def iteration_of(hist, build):
    """this build's iteration number from the quality history -> (iteration, the history without the entry it replaces).
    An absolute counter (the history is trimmed to 50 entries; its length would freeze the iteration at 51). An
    ITERATION is a new version of the model, not a run: a rebuild of the same build (`build` = its build_identity:
    the script and its a.param values; only a parts answer, the review or the brief changed) is that iteration measured
    again, and its old entry goes. Counting every run asked a hero for a review of a build nobody had changed — and the
    rebuild that answered it moved the number again."""
    hist = list(hist or [])
    if hist and build and hist[-1].get("script_sha") == build and "iteration" in hist[-1]:
        return hist[-1]["iteration"], hist[:-1]
    return ((hist[-1].get("iteration", len(hist)) + 1) if hist else 1), hist


def ratchet(acc, raw_now, tier, weights=None, margin=RATCHET_RAW, measure=None, now_comp=None):
    """is this build WORSE than the accepted one (kit accept)? -> (worse, accepted raw, how) on TODAY's raw scale:
    how = "components" — the accepted build's own measured components re-scored with today's weights, so a new owner
    grade or a refit can never fail a build that did not change; "measure" — the accepted build was measured by other
    measuring code (MEASURE_VERSION): not comparable, worse = None (re-accept it); "stored" — a record without
    components compared by the raw it stored (its scale may have moved since); (None, None, None) — nothing to compare"""
    if not isinstance(acc, dict):
        return None, None, None
    comp = alike(acc.get("components"), now_comp)
    if isinstance(comp, dict) and comp:
        if not all(_finite(v) for v in comp.values()):
            return None, None, None  # (a NaN compares False with everything: a floor of NaN is a broken floor)
        then = raw_of(comp, tier, weights)
        if measure is not None and acc.get("measure") != measure:
            return None, then, "measure"
        return raw_now < then - margin, then, "components"
    then = acc.get("raw")
    if _finite(then):
        return raw_now < then - margin, float(then), "stored"
    return None, None, None


# ---------------------------------------------------------------- fitting the weights to the owner (kit grades --fit)
FIT_COMPONENTS = ("silhouette", "detail", "empty", "variety", "geometry", "materials", "surface", "texture")
FIT_TOTAL = 90.0  # the fitted components share the hand weights' total (markings + reference keep theirs)
FIT_FLOOR = 0.5  # no component is ever switched off completely
FIT_LAMBDA = 3.0  # ridge strength toward the hand weights (21 grades cannot carry 8 free weights alone)
PASS_LINE = 55  # the owner's prop bar: pass / fail agreement is measured at it


def _rank(x):
    import numpy as np

    x = np.asarray(x, float)
    r = np.empty(len(x))
    r[x.argsort(kind="stable")] = np.arange(len(x))
    for v in np.unique(x):
        k = np.where(x == v)[0]
        r[k] = r[k].mean()
    return r


def spearman(a, b):
    import numpy as np

    ra, rb = _rank(a), _rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def _graded(grades):
    return current_grades(grades)


def fit_weights(grades, lam=FIT_LAMBDA, base=None):
    """weights for FIT_COMPONENTS that make the raw score follow the owner's grades: ridge regression of the owner's
    number on the components (x craft), pulled toward the hand weights by `lam`, every weight >= FIT_FLOOR, scaled to
    FIT_TOTAL. -> {component: weight} (+ markings / reference unchanged)"""
    import numpy as np

    base = dict(base or HAND_WEIGHTS)
    pts = _graded(grades)
    if len(pts) < MIN_COMPONENT_GRADES:
        return dict(base)
    eff = [effective(g["components"]) for g in pts]   # (the components raw_of weighs: an organic grade's, blended)
    x = np.array([[c.get(k, 0.0) * c.get("craft", 1.0) for k in FIT_COMPONENTS] for c in eff])
    y = np.array([float(g["owner"]) for g in pts])
    h = np.array([base[k] for k in FIT_COMPONENTS], float)
    # the scale that turns weights into owner points, from the hand weights themselves: owner ~ a + s * (x @ h)
    hx = x @ h
    s = float(np.polyfit(hx, y, 1)[0]) if hx.std() > 0 else 1.0
    s = s if s > 1e-6 else 1e-3
    # minimise |y - a - s x w|^2 + lam' |w - h|^2 over (a, w); lam' = lam x the data's mean per-grade curvature, so
    # lam = 3 means "the hand weights count like 3 more grades" whatever the number of grades
    xs = s * x
    lam_ = lam * float((xs ** 2).sum(0).mean()) / len(y)
    a_mat = np.c_[np.ones(len(y)), xs]
    reg = np.diag([0.0] + [lam_] * len(FIT_COMPONENTS))
    rhs = a_mat.T @ y + np.r_[0.0, lam_ * h]
    sol = np.linalg.solve(a_mat.T @ a_mat + reg, rhs)
    w = np.maximum(sol[1:], 0.0)
    if w.sum() <= 0:
        w = h.copy()
    # every weight >= FIT_FLOOR, the total FIT_TOTAL: the floor first, the rest shared in the fitted proportions
    w = FIT_FLOOR + w / w.sum() * (FIT_TOTAL - FIT_FLOOR * len(w))
    out = dict(base)
    out.update({k: round(float(v), 1) for k, v in zip(FIT_COMPONENTS, w)})
    return out


def _predict(train, test, weights):
    """the owner's number for `test` predicted from `train` alone: raw with `weights`, mapped through the isotonic
    calibration fitted on train's grades"""
    knots = isotonic_knots(grade_points(train, weights))
    return map_knots(raw_of(test["components"], test.get("tier", "prop"), weights), knots)


def evaluate(grades, weights_of):
    """LEAVE-ONE-OUT: every grade is predicted by weights + calibration fitted WITHOUT it. weights_of(train) -> weights.
    -> {spearman, pairs (same object, owner disagreed: share ordered right), pass_agree, mae, n, pred}"""
    import itertools

    import numpy as np

    pts = _graded(grades)
    pred = []
    for i, g in enumerate(pts):
        train = pts[:i] + pts[i + 1:]
        pred.append(_predict(train, g, weights_of(train)))
    owner = np.array([float(g["owner"]) for g in pts])
    pred = np.array(pred)
    obj = [str(g.get("object") or g.get("asset")) for g in pts]
    pairs = [(i, j) for i, j in itertools.combinations(range(len(pts)), 2) if obj[i] == obj[j] and owner[i] != owner[j]]
    right = sum(1 for i, j in pairs if (pred[i] - pred[j]) * (owner[i] - owner[j]) > 0)
    return {"spearman": round(spearman(owner, pred), 3), "pairs": round(right / len(pairs), 3) if pairs else None,
            "pairs_n": len(pairs), "pass_agree": round(float(np.mean((owner >= PASS_LINE) == (pred >= PASS_LINE))), 3),
            "mae": round(float(np.abs(owner - pred).mean()), 1), "n": len(pts), "pred": [round(float(p), 1) for p in pred]}


BOOT = 2000  # paired bootstrap resamples for the rank test (the owner's grades drawn with replacement)


VETO_P = 0.05  # a refit is refused when any metric's test says it is WORSE than the hand weights at this p
ADOPT_FAMILY = 0.25  # ... and kept when some metric's test says it is BETTER: a refit that is NOT better, at most this often
ADOPT_P = round(1 - (1 - ADOPT_FAMILY) ** (1 / 3), 4)  # = 0.0914 for each of the three looks (Sidak), so together they
# stay under ADOPT_FAMILY however many grades there are (at p < .20 each, the 25% measured on 21 grades was 35% at 24)


def _binom_le(k, n):
    """P(X <= k) for X ~ Binomial(n, 1/2)"""
    return sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n if n else 1.0


def tests(grades, pred_a, pred_b, n_boot=BOOT, seed=0):
    """does `a` beat `b` (both leave-one-out predictions of the owner's grades)? One test per metric, each sized to its
    metric: SAME-OBJECT PAIRS — an exact sign test over the pairs the two order differently (a pair only counts where
    they disagree); PASS / FAIL — an exact McNemar test over the grades one gets right and the other wrong; RANK — a
    paired bootstrap of the rank correlation's difference. -> {metric: {wins_a, wins_b, p_better, p_worse}}: one-sided
    p that `a` is better / worse (small = strong evidence)"""
    import itertools as _it

    import numpy as np

    pts = _graded(grades)
    owner = np.array([float(g["owner"]) for g in pts])
    obj = [str(g.get("object") or g.get("asset")) for g in pts]
    a, b = np.asarray(pred_a, float), np.asarray(pred_b, float)
    out = {}
    wa = wb = 0
    for i, j in _it.combinations(range(len(pts)), 2):
        if obj[i] != obj[j] or owner[i] == owner[j]:
            continue
        ra = bool((a[i] - a[j]) * (owner[i] - owner[j]) > 0)
        rb = bool((b[i] - b[j]) * (owner[i] - owner[j]) > 0)
        wa, wb = wa + int(ra and not rb), wb + int(rb and not ra)
    n = wa + wb
    out["pairs"] = {"wins_a": wa, "wins_b": wb, "p_better": round(1 - _binom_le(wa - 1, n), 4) if n else 1.0,
                    "p_worse": round(_binom_le(wa, n), 4) if n else 1.0}
    ca, cb = (owner >= PASS_LINE) == (a >= PASS_LINE), (owner >= PASS_LINE) == (b >= PASS_LINE)
    wa, wb = int(np.sum(ca & ~cb)), int(np.sum(cb & ~ca))
    n = wa + wb
    out["pass_agree"] = {"wins_a": wa, "wins_b": wb, "p_better": round(1 - _binom_le(wa - 1, n), 4) if n else 1.0,
                         "p_worse": round(_binom_le(wa, n), 4) if n else 1.0}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(pts), len(pts))
        if len(set(idx.tolist())) > 2:
            diffs.append(spearman(owner[idx], a[idx]) - spearman(owner[idx], b[idx]))
    d = np.array(diffs)
    out["rank"] = {"diff": round(spearman(owner, a) - spearman(owner, b), 3),
                   "p_better": round(float(np.mean(d <= 0)), 4) if len(d) else 1.0,
                   "p_worse": round(float(np.mean(d >= 0)), 4) if len(d) else 1.0}
    return out


def grade_key(g):
    """one grade's identity: project / asset @ when it was given"""
    return f"{g.get('project') or '?'}/{g.get('asset')}@{g.get('at') or '?'}"


def prospective(grades, fitted_on, weights):
    """the PROSPECTIVE test: `weights` on the FRESH grades — given after those weights were fitted (`fitted_on`: the
    grade keys the fit saw), so the fit never saw them — against the hand weights, both calibrated on the grades the
    fit saw. -> {"n": fresh grades} (+ "current" / "hand": {spearman, pass_agree, mae} when there are 3+), or None
    when the weights record no fit"""
    import numpy as np

    if not fitted_on:
        return None
    seen = set(fitted_on)
    pts = _graded(grades)
    fresh = [g for g in pts if grade_key(g) not in seen]
    base = [g for g in pts if grade_key(g) in seen]
    out = {"n": len(fresh)}
    if len(fresh) < 3 or len(base) < MIN_COMPONENT_GRADES:
        return out
    owner = np.array([float(g["owner"]) for g in fresh])
    for name, w in (("current", weights), ("hand", dict(HAND_WEIGHTS))):
        pred = np.array([_predict(base, g, w) for g in fresh])
        out[name] = {"spearman": round(spearman(owner, pred), 3),
                     "pass_agree": round(float(np.mean((owner >= PASS_LINE) == (pred >= PASS_LINE))), 3),
                     "mae": round(float(np.abs(owner - pred).mean()), 1)}
    return out


def fit_report(grades=None, lam=FIT_LAMBDA):
    """hand weights vs a fresh fit, both judged LEAVE-ONE-OUT on the same grades (the fit never sees the grade it
    predicts); the current weights are shown too, but they were fitted on these grades: in-sample, flattering"""
    grades = load_grades() if grades is None else grades
    hand = evaluate(grades, lambda _t: dict(HAND_WEIGHTS))
    fit = evaluate(grades, lambda t: fit_weights(t, lam))
    return {
        "hand": hand,
        "current": evaluate(grades, lambda _t: dict(WEIGHTS)),
        "fit": fit,
        "weights": fit_weights(grades, lam),
        "lam": lam,
        "tests": tests(grades, fit["pred"], hand["pred"]),
    }


def _main(argv):
    """python kit/blender/rbx_score.py fit [--write] [--lam N] [--grades path] — what `lune run kit grades` runs.
    The grades are KIT_GRADES (the kit home's canonical file, set by the kit command) or --grades (exploring only);
    --write goes to KIT_WEIGHTS_OUT (the home's weights.json) and is refused with --grades or --lam: a refit that
    becomes every build's weights is fitted on the canonical grades with the pre-set ridge, nothing else"""
    if "--write" in argv and ("--grades" in argv or "--lam" in argv):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "grades fit: --write takes the canonical grades and "
                          f"the pre-set ridge ({FIT_LAMBDA}) only — explore --grades / --lam without --write",
                          "next_action": "lune run kit grades --write"}))
        return 1
    grades_path = os.path.abspath(os.environ.get("KIT_GRADES") or os.path.join(KIT, "grades.json"))
    weights_path = os.path.abspath(os.environ.get("KIT_WEIGHTS_OUT") or os.path.join(KIT, "weights.json"))
    if "--write" in argv and os.path.dirname(grades_path) != os.path.dirname(weights_path):
        # weights are written BESIDE the grades they were fitted on: a fit on some other grades file can never become
        # the kit's weights (it would land beside that file)
        print(json.dumps({"schema": 1, "status": "fail", "summary": "grades fit: --write puts the weights beside the "
                          f"grades they were fitted on — {grades_path} and {weights_path} are in different folders",
                          "next_action": "lune run kit grades --write"}))
        return 1
    lam = float(argv[argv.index("--lam") + 1]) if "--lam" in argv else FIT_LAMBDA
    grades = load_grades(argv[argv.index("--grades") + 1] if "--grades" in argv else os.environ.get("KIT_GRADES"))
    n = len(_graded(grades))
    if n < MIN_COMPONENT_GRADES:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"grades fit: {n} grade(s) with measurements — needs "
                          f"{MIN_COMPONENT_GRADES}+", "next_action": "grade more builds: lune run kit grade <asset> <0-100> \"why\""}))
        return 1
    rep = fit_report(grades, lam)
    fit, cur = rep["fit"], rep["current"]
    hand = rep["hand"]
    t = rep["tests"]
    # the rule (2026-10-06): a refit is REFUSED when any metric's own test says it is worse than the hand weights (p <
    # VETO_P) and KEPT only when some metric's test says it is better (p < ADOPT_P). It was written after three
    # reviews rejected weaker gates, with these grades already seen — so these grades cannot also confirm it. What it
    # can and cannot do is measured (kit/test/python/test_grading.py simulates it on these grades): it keeps a refit
    # that is NO better at most one time in four — three looks at p < ADOPT_P (0.0914) each, Sidak-sized to
    # ADOPT_FAMILY: 17% on the 24 grades of 2026-10-06, 11% on the first 21 (one look at p < .20 each was 25% on 21
    # and 35% on 24: more grades make each look's p less coarse, so the old rule drifted up as grades came in) —
    # harmless when the two are equal — and the pairs test can only veto a loss of 5+ discordant pairs (a sign test on
    # fewer never reaches p < .05). The real test is PROSPECTIVE: grades given after the weights were fitted, which
    # they never saw (the report's "fresh" line).
    vetoed = [k for k, v in t.items() if v["p_worse"] < VETO_P]
    better_on = [k for k, v in t.items() if v["p_better"] < ADOPT_P]
    better = not vetoed and bool(better_on)
    def line(r):
        pairs = f"{r['pairs']:.0%}" if r["pairs"] is not None else "n/a (no object graded twice)"
        return f"rank {r['spearman']:+.2f}, same-object pairs {pairs}, pass/fail {r['pass_agree']:.0%}, MAE {r['mae']}"

    total = len([g for g in grades if isinstance(g.get("components"), dict)])
    stale = total - len([g for g in grades if isinstance(g.get("components"), dict) and g.get("measure") == MEASURE_VERSION])
    odds = (f"pairs {t['pairs']['wins_a']}-{t['pairs']['wins_b']} (sign test p better {t['pairs']['p_better']:.2f} / "
            f"worse {t['pairs']['p_worse']:.2f}), pass/fail {t['pass_agree']['wins_a']}-{t['pass_agree']['wins_b']} "
            f"(McNemar p {t['pass_agree']['p_better']:.2f} / {t['pass_agree']['p_worse']:.2f}), rank "
            f"{t['rank']['diff']:+.2f} (bootstrap p {t['rank']['p_better']:.2f} / {t['rank']['p_worse']:.2f})")
    try:
        with open(weights_path, encoding="utf-8") as fh:
            wfile = json.load(fh)
    except (OSError, ValueError):
        wfile = {}
    fitted_on = wfile.get("fitted_on") if isinstance(wfile, dict) else None
    now_w = {**HAND_WEIGHTS, **((wfile.get("weights") or {}) if isinstance(wfile, dict) else {})}
    pro = prospective(grades, fitted_on, now_w)
    if pro is None:
        fresh = "fresh grades: the current weights record no fit to test"
    elif "current" not in pro:
        fresh = (f"fresh grades (given after the weights were fitted, never seen by them): {pro['n']} — the next blind "
                 "round tests the weights on grades they never saw (3+ needed)")
    else:
        c, h = pro["current"], pro["hand"]
        fresh = (f"FRESH grades (never seen by the fit): {pro['n']} — current weights rank {c['spearman']:+.2f}, pass/fail "
                 f"{c['pass_agree']:.0%}, MAE {c['mae']} vs hand rank {h['spearman']:+.2f}, pass/fail "
                 f"{h['pass_agree']:.0%}, MAE {h['mae']}")
    summary = (f"grades fit on {n} owner grades, leave-one-out: hand weights {line(hand)} | refit {line(fit)} "
               f"(current weights, in-sample: {line(cur)}) | refit vs hand: {odds} | {fresh}"
               + (f" — {stale} of {total} grades were measured by older measuring code: re-measure them" if stale else ""))
    wrote = None
    if "--write" in argv:
        if better:
            path = weights_path
            with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
                json.dump({"weights": {k: rep["weights"][k] for k in FIT_COMPONENTS}, "lam": lam, "grades": n,
                           "loo": {k: fit[k] for k in ("spearman", "pairs", "pass_agree", "mae")},
                           "loo_hand": {k: hand[k] for k in ("spearman", "pairs", "pass_agree", "mae")},
                           "tests_vs_hand": t,
                           # the grades this fit saw: every grade given later is a FRESH, prospective test of it
                           "fitted_on": sorted(grade_key(g) for g in _graded(grades))}, fh, indent=2)
                fh.write(chr(10))
            wrote = os.path.relpath(path, REPO).replace("\\", "/") if os.path.abspath(path).startswith(REPO) else path
        else:
            summary += (f" — NOT written: worse at p < {VETO_P}: {', '.join(vetoed) or 'none'}; better at p < "
                        f"{ADOPT_P}: {', '.join(better_on) or 'none'}")
    print(json.dumps({"schema": 1, "status": "pass", "summary": summary + (f" — wrote {wrote}" if wrote else ""),
                      "wrote": wrote,
                      "next_action": ("commit kit/weights.json (every build is scored with it from now on)" if wrote else
                                      "lune run kit grades --write (writes a refit only when no metric's test says it "
                                      "is worse and one says it is better)"
                                      if better else "grade more builds — more grades, a better fit"),
                      "weights": rep["weights"], "tests": t, "fresh": pro,
                      "report": {k: {kk: vv for kk, vv in v.items() if kk != "pred"}
                                 for k, v in rep.items() if isinstance(v, dict) and "spearman" in v}}))
    return 0


REBUILD_NOISE = 0.1  # raw points: the same build measured twice (builds are not bit-reproducible) — not a lowering
FINGERPRINT_TRIS = 0.05  # the same script and kit rebuild within this share of triangles (booleans retry: tiny drift)
FINGERPRINT_SIZE = 0.02  # ... and within this share of the model's size on every axis


def fingerprint_diff(grade, entry):
    """how a rebuild (`entry`: a quality history entry) differs from the build the owner graded (`grade`'s tris / size),
    or "" — the same model (or a grade that kept no fingerprint)"""
    t0, t1 = grade.get("tris"), entry.get("tris")
    if isinstance(t0, (int, float)) and isinstance(t1, (int, float)) and abs(t1 - t0) > FINGERPRINT_TRIS * max(t0, 1):
        return f"{int(t0)} -> {int(t1)} triangles"
    s0, s1 = grade.get("size"), entry.get("size")
    if isinstance(s0, list) and isinstance(s1, list) and len(s0) == len(s1) == 3:
        big = max(max(s0), 1e-6)
        if any(abs(b - a) > FINGERPRINT_SIZE * big for a, b in zip(s0, s1)):
            return f"size {s0} -> {s1} studs"
    return ""


def floor_change(acc, entry):
    """would accepting `entry` (a quality history entry) LOWER the floor `acc` (an accepted record, or None when there is
    none yet)? Both re-scored with today's weights -> {first, lowering, rebase, same_script, changed, stale, then, now}:
    lowering — a drop of more than the rebuild noise below the floor (a floor walked down in small steps is still
    lowered); rebase — the floor is unreadable or was measured by other measuring code; same_script — the build was MADE
    by the floor's script (the sha written into the entry when it was built — never the file as it is now) AND it is the
    floor's model (the fingerprint the floor kept): a re-base is then the same build under a new ruler; a floor that kept
    no fingerprint can never be shown to be the same model (changed says why); stale — the build itself was measured by
    older measuring code"""
    tier = (entry or {}).get("tier", "prop")
    comp = (entry or {}).get("components")
    now = raw_of(comp, tier) if isinstance(comp, dict) else None
    stale = (entry or {}).get("measure") != MEASURE_VERSION
    base = {"first": False, "lowering": False, "rebase": False, "same_script": False, "stale": stale, "then": None,
            "now": now}
    if acc is None:
        return dict(base, first=True)
    sha = (entry or {}).get("script_sha")
    same = bool(sha) and isinstance(acc, dict) and acc.get("script_sha") == sha
    if not isinstance(acc, dict) or not isinstance(acc.get("components"), dict) or not acc.get("components") or \
            not all(_finite(v) for v in acc["components"].values()):
        return dict(base, rebase=True, changed="the floor is unreadable or keeps no (finite) measurements")
    then = raw_of(alike(acc["components"], comp), tier)
    rebase = acc.get("measure") != (entry or {}).get("measure")
    lowering = (not rebase) and now is not None and now < then - REBUILD_NOISE
    if not same:
        changed = "this build was made by another script than the accepted one" if acc.get("script_sha") else \
            "the floor does not say which script made it"
    elif acc.get("tris") is None:
        changed = "the floor kept no fingerprint (it predates them): it cannot be shown to be this model"
    else:
        changed = fingerprint_diff(acc, entry or {})
    return dict(base, lowering=lowering, rebase=rebase, same_script=same and not changed, changed=changed, then=then)


def script_sha(path):
    """a build script's identity: sha256 of its text with LF line endings (git may check it out with CRLF), 16 hex —
    the same as kit grade's (learn.luau scriptSha)"""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()[:16]
    except OSError:
        return None


def params_path(script):
    """the a.param values `kit fit --write` keeps for a build script: build_<x>.py -> <x>.params.json beside it"""
    stem = os.path.splitext(os.path.basename(script))[0]
    return os.path.join(os.path.dirname(script), f"{stem[6:] if stem.startswith('build_') else stem}.params.json")


def build_identity(script, params_text=""):
    """a BUILD's identity (16 hex): its script's text with LF line endings — and, when it ran with a.param values (kept
    beside it, or a fit's trial), those too: the same script with other numbers is another model. With no values it is
    the script's own sha (script_sha), so an asset without params keeps the identity it always had. Kept in step with
    learn.luau's buildSha."""
    try:
        with open(script, "rb") as fh:
            data = fh.read().replace(b"\r\n", b"\n")
    except OSError:
        return None
    if params_text:
        data += b"\n#a.param\n" + params_text.encode("utf-8").replace(b"\r\n", b"\n")
    sha = pack_inputs(script)
    if sha:  # the asset's pack values it reads (kit pack: a measured colour, a sourced size) are part of the model
        data += b"\n#pack\n" + sha.encode("ascii")
    return hashlib.sha256(data).hexdigest()[:16]


def pack_inputs(script):
    """the inputs_sha of the pack beside a build script (build_<x>.py -> <x>.pack.json: kit/tools/pack.py
    inputs_sha — what was CHOSEN that a build reads; a rescan never changes it), or None. learn.luau buildSha does
    the same."""
    folder, file = os.path.split(script)
    stem = file[:-3] if file.endswith(".py") else file
    stem = stem[6:] if stem.startswith("build_") else stem
    try:
        with open(os.path.join(folder, f"{stem}.pack.json"), encoding="utf-8") as fh:
            sha = json.load(fh).get("inputs_sha")
    except (OSError, ValueError, AttributeError):
        return None
    return sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{16}", sha) else None


def _floor_main(argv):
    """python kit/blender/rbx_score.py floor <accepted.json> <quality.json> — what `kit accept` asks before writing.
    The floor is read like the ratchet reads it: the COMMITTED floor whenever there is one (no edit of the file moves
    it); none here or anywhere in git = no floor yet. The identity written into a new floor is the BUILD's own (the
    script sha its history recorded when it was built, and its fingerprint)"""
    acc, where = read_floor(argv[0])
    if where == "unreadable":
        acc = "unreadable"
    with open(argv[1], encoding="utf-8") as fh:
        entry = json.load(fh)[-1]
    out = floor_change(acc, entry)
    print(json.dumps({"schema": 1, "status": "pass", "summary": "floor compared", "next_action": "none",
                      "from_git": where == "git", "previous": acc if isinstance(acc, dict) else None,
                      "script_sha": entry.get("script_sha"), "tris": entry.get("tris"), "size": entry.get("size"),
                      **out}))
    return 0


def _add_main(argv):
    """python kit/blender/rbx_score.py add <grades.json> <entry.json> — `kit grade` appends the owner's grade (python
    writes every grades file: one format, stable diffs)"""
    grades = []
    if os.path.isfile(argv[0]):  # a file it cannot read (a merge conflict, a bad edit) is never overwritten
        try:
            with open(argv[0], encoding="utf-8") as fh:
                grades = json.load(fh)
        except (OSError, ValueError) as e:
            grades = e
        if not isinstance(grades, list):
            print(json.dumps({"schema": 1, "status": "fail", "summary": f"grade: {argv[0]} cannot be read as a list of "
                              "grades — it is left as it is (every owner grade is in it)",
                              "next_action": f"repair {argv[0]} (git diff / git checkout), then grade again"}))
            return 1
    with open(argv[1], encoding="utf-8") as fh:
        add = json.load(fh)
    grades += add if isinstance(add, list) else [add]
    with open(argv[0], "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(grades, fh, indent=2)
        fh.write(chr(10))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"grade added ({len(grades)} in all)", "next_action": "none"}))
    return 0


def _refresh_main(argv):
    """python kit/blender/rbx_score.py refresh <grades.json> <history dir> <asset>... — what `kit grades --remeasure`
    runs after rebuilding: each named grade takes its build's fresh measurements (components, measure, raw, tier);
    the owner's number and note never change"""
    import time as _t

    path, hist_dir = argv[0], argv[1]
    # each wanted grade is "asset@project@sha": two projects may grade builds of the same name (every project has a
    # crate), and one asset may be graded twice — only the grade of the script that was rebuilt takes its measurements
    wanted = set()
    for t in argv[2:]:
        asset, project, sha = (t.split("@", 2) + ["", ""])[:3]
        wanted.add((asset, project or None, sha or None))
    with open(path, encoding="utf-8") as fh:
        grades = json.load(fh)
    done, changed = [], []
    for g in grades:
        if not isinstance(g, dict) or not isinstance(g.get("components"), dict):
            continue
        if (g.get("asset"), g.get("project"), g.get("script_sha")) not in wanted:
            continue
        hp = os.path.join(hist_dir, f"{g['asset']}.quality.json")
        try:
            with open(hp, encoding="utf-8") as fh:
                last = json.load(fh)[-1]
        except (OSError, ValueError, IndexError):
            continue
        if not isinstance(last.get("components"), dict):
            continue
        # the FINGERPRINT: the same script can build a different model when the kit's geometry changed under it — the
        # owner graded what they saw, so a grade whose build changed keeps its old measurements (re-grade it)
        diff = fingerprint_diff(g, last)
        if last.get("script_sha") and g.get("script_sha") and last["script_sha"] != g["script_sha"]:
            diff = "it was rebuilt from another script"
        if diff:
            changed.append(f"{g['asset']} ({diff})")
            continue
        day = _t.strftime("%Y-%m-%d")
        if g.get("tris") is None and last.get("tris") is not None:
            g["fingerprint_backfilled"] = (f"{day}: taken at a re-measure (none was kept when the owner graded it); "
                                           "later re-measures compare against it")
        g.update(components=last["components"], measure=last.get("measure"), raw=last.get("raw"),
                 tier=last.get("tier", g.get("tier", "prop")),
                 tris=g.get("tris", last.get("tris")), size=g.get("size", last.get("size")),
                 measured=f"{day}: re-measured (kit grades --remeasure) on the build the owner graded")
        done.append(g["asset"])
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(grades, fh, indent=2)
        fh.write(chr(10))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"refreshed {len(done)} grade(s)"
                      + (f"; {len(changed)} left as they were — the build is no longer the one the owner graded: "
                         + ", ".join(changed) if changed else ""),
                      "next_action": "ask the owner to grade the changed builds again" if changed else "none",
                      "refreshed": done, "changed": changed}))
    return 0


if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["floor"]:
        sys.exit(_floor_main(sys.argv[2:]))
    if sys.argv[1:2] == ["refresh"]:
        sys.exit(_refresh_main(sys.argv[2:]))
    if sys.argv[1:2] == ["add"]:
        sys.exit(_add_main(sys.argv[2:]))
    sys.exit(_main(sys.argv[1:]))
