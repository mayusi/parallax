"""round.py — `kit rate`: the OWNER grading page (mission 01-3d §5.10, task fg3b). The owner's verdict is the only
quality signal; this makes giving it take seconds per model: a round of built assets in a local 3D viewer (orbit,
views, clay / wire, compare two, R6 scale, the asset's own reference photos beside it), a 0-10 score and words per
model, saved as the owner clicks; `import` records every score through `kit verdict asset` (the one verdict record:
>= 7 golden, <= 3 graveyard). Local only (127.0.0.1): a private design is shown, never uploaded.

    python kit/grading/round.py make <round> <asset> [<asset> ...]   -> build/grading/<round>/ (models, refs, round.json)
    python kit/grading/round.py import <round>                       -> kit verdict asset <name> <score> "<words>"
    python kit/grading/round.py list
"""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)
if KIT not in sys.path:
    sys.path.insert(0, KIT)
from blender_path import find_blender  # noqa: E402
ROUNDS = os.path.join(REPO, "build", "grading")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _rel(p):
    return os.path.relpath(p, REPO).replace("\\", "/")


def blender():
    """the kit's Blender (kit/blender_path.py: KIT_BLENDER, BLENDER, the OS's install folders newest first, then PATH)"""
    return find_blender()


def references(asset):
    """the asset's own reference PICTURES for the side panel: the build's reference_image, then each traced view's
    photo (a hull mask is no picture) -> [(label, path)]"""
    sys.path.insert(0, os.path.join(KIT, "blender"))
    import verifier as V  # noqa: PLC0415

    out, seen = [], set()
    m = _json(os.path.join(REPO, "build", "models", f"{asset}.manifest.json")) or {}
    ref = m.get("reference_image")
    if ref and os.path.isfile(os.path.join(REPO, ref)):
        out.append(("reference", os.path.join(REPO, ref)))
        seen.add(os.path.normcase(os.path.abspath(os.path.join(REPO, ref))))
    for view, name in sorted(V.traces_by_view(asset).items()):
        _n, t = V.photo_trace(view, name)
        pic = V._picture(t) if t else None
        if pic and os.path.isfile(pic) and not V.is_mask(pic) and os.path.normcase(os.path.abspath(pic)) not in seen:
            seen.add(os.path.normcase(os.path.abspath(pic)))
            out.append((view, pic))
    return out[:6]


def make(rnd, assets):
    if not NAME.match(rnd or ""):
        return _out("fail", f"rate: '{rnd}' is no round name (lowercase, digits, - _)", "lune run kit rate make props-1 "
                    "<asset> ...")
    if not assets:
        return _out("fail", "rate make: name the assets to grade", f"lune run kit rate make {rnd} <asset> [<asset> ...]")
    exe = blender()
    if not exe:
        return _out("fail", "rate make: no Blender found", "set KIT_BLENDER to blender.exe")
    root = os.path.join(ROUNDS, rnd)
    os.makedirs(os.path.join(root, "models"), exist_ok=True)
    os.makedirs(os.path.join(root, "refs"), exist_ok=True)
    old = _json(os.path.join(root, "round.json")) or {}
    items, problems = {i["asset"]: i for i in old.get("items") or []}, []
    for a in assets:
        blend = os.path.join(REPO, "build", "models", f"{a}.blend")
        m = _json(os.path.join(REPO, "build", "models", f"{a}.manifest.json")) or {}
        if not os.path.isfile(blend):
            problems.append(f"{a}: no build (build/models/{a}.blend) — lune run kit asset {a}")
            continue
        glb = os.path.join(root, "models", f"{a}.glb")
        r = subprocess.run([exe, "-b", blend, "--factory-startup", "-P", os.path.join(KIT, "grading", "page",
                                                                                     "export_glb.py"), "--", glb, a],
                           capture_output=True, text=True, timeout=900)
        if not os.path.isfile(glb) or "EXPORTED" not in (r.stdout or ""):
            problems.append(f"{a}: the GLB export failed ({(r.stderr or r.stdout or '')[-160:].strip()})")
            continue
        refs = []
        for k, (label, pic) in enumerate(references(a)):
            dst = os.path.join(root, "refs", f"{a}_{k}{os.path.splitext(pic)[1].lower()}")
            shutil.copyfile(pic, dst)
            refs.append({"label": label, "file": f"refs/{os.path.basename(dst)}"})
        items[a] = {"asset": a, "glb": f"models/{a}.glb", "refs": refs, "build_id": m.get("build_id"),
                    "tier": m.get("tier"), "private": bool(m.get("private"))}
    data = {"round": rnd, "created": old.get("created") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "items": list(items.values())}
    with open(os.path.join(root, "round.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    if not data["items"]:
        return _out("fail", f"rate make {rnd}: nothing to grade — {'; '.join(problems)}", "build the assets first")
    return _out("pass", f"rate round {rnd}: {len(data['items'])} model(s) ready"
                + (f"; skipped: {'; '.join(problems)}" if problems else ""),
                f"lune run kit rate serve {rnd}   then the OWNER opens http://127.0.0.1:{PORT}/ and scores each 0-10 "
                f"with words; then: lune run kit rate import {rnd}", round=_rel(root), problems=problems)


PORT = 8796


def import_round(rnd):
    root = os.path.join(ROUNDS, rnd)
    data = _json(os.path.join(root, "round.json"))
    if not data:
        return _out("fail", f"rate import: no round {rnd}", "lune run kit rate make <round> <asset> ...")
    ratings = _json(os.path.join(root, "ratings.json")) or {}
    done, skipped, recorded = ratings.get("_imported") or {}, [], []
    by = {i["asset"]: i for i in data.get("items") or []}
    for a, r in sorted(ratings.items()):
        if a.startswith("_") or a not in by or not isinstance(r, dict) or r.get("score") is None:
            continue
        key = f"{r.get('score')}|{r.get('at')}"
        if done.get(a) == key:
            continue   # (this score is in the record already)
        words = str(r.get("words") or "").strip()
        if not words:
            skipped.append(f"{a}: a score without words (the record keeps the owner's words: ask for one line)")
            continue
        cmd = ["lune", "run", "kit", "verdict", "asset", a, str(r["score"]), words, "--quoted-from",
               f"{_rel(root)}/ratings.json"]
        if by[a].get("build_id"):
            cmd += ["--build", str(by[a]["build_id"])]
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            skipped.append(f"{a}: kit verdict refused it ({(p.stdout or p.stderr).strip().splitlines()[-1:]})")
            continue
        done[a] = key
        recorded.append(f"{a} {r['score']}/10")
    ratings["_imported"] = done
    with open(os.path.join(root, "ratings.json"), "w", encoding="utf-8") as fh:
        json.dump(ratings, fh, indent=1)
    if not recorded and not skipped:
        return _out("pass", f"rate import {rnd}: nothing new (the owner has not scored anything new)",
                    f"lune run kit rate serve {rnd} — the owner scores, then import again")
    return _out("pass" if recorded else "fail", f"rate import {rnd}: {len(recorded)} verdict(s) recorded"
                + (f" ({', '.join(recorded)})" if recorded else "") + (f"; skipped: {'; '.join(skipped)}" if skipped else ""),
                "act on the words: every verdict is in kit/knowledge/vault/3d/verdicts (>= 7 golden, <= 3 graveyard)",
                recorded=recorded, skipped=skipped)


def list_rounds():
    rows = []
    for p in sorted(glob.glob(os.path.join(ROUNDS, "*", "round.json"))):
        d = _json(p) or {}
        r = _json(os.path.join(os.path.dirname(p), "ratings.json")) or {}
        n = len(d.get("items") or [])
        scored = sum(1 for k, v in r.items() if not k.startswith("_") and isinstance(v, dict) and v.get("score") is not None)
        rows.append(f"{d.get('round')}: {scored}/{n} scored ({d.get('created')})")
    print("\n".join(rows) or "(no rounds yet)")
    return _out("pass", f"rate: {len(rows)} round(s)", "lune run kit rate make <round> <asset> ...", rounds=rows)


def main(argv):
    if not argv or argv[0] not in ("make", "import", "list"):
        return _out("fail", "rate: make <round> <asset> ... | import <round> | list", "lune run kit rate make props-1 "
                    "hydrant chair")
    if argv[0] == "list":
        return list_rounds()
    if len(argv) < 2:
        return _out("fail", f"rate {argv[0]}: needs a round name", f"lune run kit rate {argv[0]} <round>")
    return make(argv[1], argv[2:]) if argv[0] == "make" else import_round(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
