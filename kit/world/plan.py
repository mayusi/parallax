"""plan.py — `kit world plan <Name>`: ONE world's route, stage by stage, from the game's own files (mission 05 5.10).

    python kit/world/plan.py <Name>        (cwd = the repo; KIT_GAME / games/.active name the game)

Stages: [direction ->] refs -> terrain -> materials -> meshes -> dressing -> check -> look -> studio -> verdict. Each is done /
partly done / to do with what is missing, and the first stage not done gets its exact commands (at most five).
Reads only; prints one JSON verdict line (stages, next stage, commands).
"""

import glob
import json
import os
import re
import sys

STYLISED = ("q_",)  # Quaternius: stylised packs never in a realistic world


def game_root():
    g = os.environ.get("KIT_GAME")
    if not g:  # ("none" is an answer - the project root; it read games/.active and planned in the active game instead)
        p = os.path.join("games", ".active")
        g = open(p, encoding="utf-8").read().strip() if os.path.isfile(p) else ""
    return os.path.join("games", g) if g and g != "none" and os.path.isdir(os.path.join("games", g)) else "."


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def walk_ops(bp, key):
    """every generator spec of kind `key` in the blueprint's build list"""
    out = []
    for step in bp.get("build") or []:
        for k, v in step.items():
            if k == key and isinstance(v, dict):
                out.append(v)
    return out


def mesh_names(bp):
    names = set()
    for step in bp.get("build") or []:
        for v in step.values():
            if isinstance(v, dict):
                for k in ("meshes", "spireMeshes"):
                    names.update(x for x in v.get(k) or [] if isinstance(x, str))
                if isinstance(v.get("mesh"), str):
                    names.add(v["mesh"])
    return names


ANSWERS = os.path.join("board", "answers.json")  # kit/lib/answers.luau's record (a test points it elsewhere)


def digest(data):
    """kit/lib/vault.luau Vault.digest: djb2 over the bytes, line ends as LF"""
    h = 5381
    for b in data.replace(b"\r\n", b"\n"):
        h = (h * 33 + b) % 4294967296
    return "%08x" % h


STOP = set("the and for with from that this into over under then them they their there when where what which while each "
           "every more most only also have has had was were been being make made like just than none room floor".split())


def _words(text):
    return {w for w in re.findall(r"[a-z]{4,}", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "").lower()) if w not in STOP}


def layout_line(path, d):
    """one past layout in a line: its building, floors, rooms and what the rooms are for"""
    b = d.get("building") or {}
    floors = d.get("floors") or []
    rooms = [r for f in floors if isinstance(f, dict) for r in (f.get("rooms") or []) if isinstance(r, dict)]
    purposes = []
    for r in rooms:
        p = str(r.get("purpose") or r.get("name") or "").strip()
        if p and p not in purposes:
            purposes.append(p)
    size = f"{b.get('front')} x {b.get('depth')} m, " if b.get("front") and b.get("depth") else ""
    return (f"{path.replace(os.sep, '/')}: {size}{len(floors)} floor(s), {len(rooms)} room(s)"
            + (f" ({', '.join(purposes[:6])}{', ...' if len(purposes) > 6 else ''})" if purposes else ""))


LAYOUT_FAMILIES = ("town", "interior")  # the past layouts are house interiors: examples for these worlds only


def layout_examples(root, name, bp, k=2, family=None):
    """the past house layouts (any game's assets/worlds/**/*.layout.json - the world lane's own plans) for a world of a
    town / interior family (kit/lib/families.luau decides it and passes --family: one rule, in one language), the ones
    sharing most words with this world first: offered as examples at plan time (2026-11-08, sprint 5: proposal 11).
    An arena, an island: [] - long texts share generic words ("owner", "build") with any layout"""
    if family not in LAYOUT_FAMILIES:
        return []
    text = " ".join([name, str(bp.get("_about") or ""), str(bp.get("about") or "")])
    for rel in (f"{name}.brief.md", os.path.join("direction", f"{name}.md")):
        p = os.path.join(root, "assets", "worlds", rel)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                text += " " + fh.read()
    want = _words(text)
    found = sorted(set(glob.glob(os.path.join("games", "*", "assets", "worlds", "**", "*.layout.json"), recursive=True)
                       + glob.glob(os.path.join("assets", "worlds", "**", "*.layout.json"), recursive=True)))
    rows = []
    for p in found:
        d = load(p)
        if not isinstance(d, dict):
            continue
        floors = d.get("floors") or []
        rooms = " ".join(f"{r.get('name', '')} {r.get('purpose', '')}" for f in floors if isinstance(f, dict)
                         for r in (f.get("rooms") or []) if isinstance(r, dict))
        shared = want & _words(f"{os.path.basename(p)} {d.get('about') or ''} {rooms}")
        if shared:
            rows.append((len(shared), p, d))
    rows.sort(key=lambda r: (-r[0], r[1]))
    return [layout_line(p, d) for _n, p, d in rows[:k]]


def answers_key(path):
    """a sheet's key in board/answers.json: its project-relative path, "/" separated (kit/lib/answers.luau's key())"""
    return os.path.relpath(path).replace(os.sep, "/")


def lessons_state(path, record=None):
    """the world lessons sheet: "to do" without one, "done" when `kit world lessons <Name>` passed this very text
    (board/answers.json keeps its digest), else "partial". The check itself lives in kit/lib/answers.luau only."""
    if not os.path.isfile(path):
        return "to do"
    with open(path, "rb") as f:
        d = digest(f.read())
    rec = load(record or ANSWERS)
    entry = rec.get(answers_key(path)) if isinstance(rec, dict) else None
    return "done" if isinstance(entry, dict) and entry.get("answered") == d else "partial"


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: plan.py <Name>", "next_action": "lune run kit world plan <Name>"}))
        return 2
    name = argv[0]
    root = game_root()
    bp_path = os.path.join(root, "assets", "worlds", f"{name}.json")
    bp = load(bp_path)
    if not bp:
        print(json.dumps({"status": "fail", "summary": f"no blueprint {bp_path}", "next_action": f"lune run kit new world {name}"}))
        return 1
    g = os.path.basename(root) if root != "." else ""
    gflag = f" --game {g}" if g else ""
    ids = load(os.path.join(root, "assets", "ids.json")) or {}
    stages = []

    def stage(key, title, status, missing, commands):
        stages.append({"key": key, "title": title, "status": status, "missing": missing, "commands": commands[:5]})

    # 0 direction (kit world direction <Piece>): every direction doc of this game's world pieces is picked by the owner
    # before its pieces are built (the owner, 2026-10-24: creative direction is the weak link, not the craft)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import direction as directionlib  # noqa: E402

    docs = sorted(glob.glob(os.path.join(root, "assets", "worlds", "direction", "*.md")))
    states = {os.path.splitext(os.path.basename(d))[0]: directionlib.check(d, "world")[0] for d in docs}
    if docs:
        st = "done" if all(v == "picked" for v in states.values()) else "partial"
        stage("direction", "direction picked by the owner (per original piece)", st,
              [f"{k}: {v}" for k, v in states.items() if v != "picked"],
              [f"lune run kit world direction {k}{gflag}" for k, v in states.items() if v != "picked"])

    # 1 refs: measured stills + an identity
    refs_dir = os.path.join(root, "assets", "worlds", "refs", name)
    stills = [f for f in glob.glob(os.path.join(refs_dir, "*")) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    has_refs_md = os.path.isfile(os.path.join(refs_dir, "REFS.md"))
    identity = os.path.isfile(os.path.join(root, "assets", "worlds", "identities", f"{name.lower()}.json"))
    st = "done" if len(stills) >= 6 and has_refs_md and identity else ("partial" if stills else "to do")
    stage("refs", "references + identity", st,
          [m for m, bad in ((f"{6 - len(stills)} more still(s) (>= 6)", len(stills) < 6), ("REFS.md (measured)", not has_refs_md),
                            ("the world identity", not identity)) if bad],
          [f"put >= 6 real stills (the owner's picks) in {refs_dir.replace(os.sep, '/')}/",
           f"lune run kit world refs {name}{gflag}"])

    # 1b lessons answered (2026-11-08, sprint 3: the world pilot of the 3D study's lesson gate): the lessons ranked for
    # this world (kit world lessons <Name>), each one to answer applied or skipped with a reason, before building
    lp = os.path.join(root, "assets", "worlds", f"{name}.lessons.md")
    st = lessons_state(lp)
    missing = {"to do": ["the lessons sheet (the world lessons ranked for this world)"],
               "partial": ["the sheet answered and checked: each lesson to answer applied / skipped (6+ words), "
                           "then the command passes on that text"],
               "done": []}[st]
    stage("lessons", "the world lessons answered before building", st, missing,
          [f"lune run kit world lessons {name}{gflag}"])

    # 2 terrain: a heightmap (painted), real land when the design has a dem
    terr = [t.get("heightmap") for t in bp.get("terrain") or [] if isinstance(t, dict) and t.get("heightmap")]
    main_hm = next((t for t in terr if not t.get("backdrop")), None)
    hm = load(os.path.join(root, main_hm["source"])) if main_hm and main_hm.get("source") else None
    design = load(os.path.join(root, "assets", "worlds", "terrain", f"{name}.design.json")) or {}
    missing = []
    if not hm:
        missing.append("a heightmap op")
    elif not hm.get("paint"):
        missing.append("the painted roles (re-run kit world terrain)")
    if not design.get("dem"):
        missing.append("real land (a design \"dem\": kit world dem)")
    st = "done" if hm and hm.get("paint") and design.get("dem") else ("partial" if hm else "to do")
    stage("terrain", "terrain (real land, rivers, painter)", st, missing,
          [f"lune run kit world dem {name} --bbox lon0,lat0,lon1,lat1{gflag}",
           f"add \"dem\": {{\"file\": \"{name}.dem.tif\", \"blur\": 1.2}} to assets/worlds/terrain/{name}.design.json",
           # (no --stream: kit world terrain takes the river route by default, and none on a design with a "dem" - real
           # land is river-carved already; a fixed --stream 0 here made the noise + thermal recipe the terrain gate refuses)
           f"lune run kit world terrain {name} --design assets/worlds/terrain/{name}.design.json --erosion 40000 --thermal 10{gflag}"])

    # 3 materials: MaterialVariant maps made and uploaded
    reg = load(os.path.join(root, "build", "terrainmaps", "terrainmaps.json")) or {}
    tm_ids = ids.get("terrainmaps") or {}
    files = {f for r in reg.values() for f in (r.get("color"), r.get("normal"), r.get("roughness")) if f}
    up = [f for f in files if os.path.splitext(f)[0] in tm_ids]
    st = "done" if files and len(up) == len(files) else ("partial" if files else "to do")
    stage("materials", "MaterialVariants from the scans", st,
          ([] if files else ["the maps (kit world materials)"]) + ([f"{len(files) - len(up)} map(s) not uploaded"] if files and len(up) < len(files) else []),
          [f"lune run kit world materials{gflag}", f"lune run kit upload{gflag}", f"lune run kit world{gflag}"])

    # 4 meshes: real meshes, uploaded, none stylised
    names = mesh_names(bp)
    mreg = load(os.path.join(root, "build", "worldmeshes", "meshes.json")) or {}
    pieces = set()
    for n in names:
        r = mreg.get(n) or {}
        pieces.update(r.get("parts") or [n])
    mids = ids.get("worldmeshes") or {}
    no_id = sorted(p for p in pieces if p not in mids)
    stylised = sorted(n for n in names if n.startswith(STYLISED))
    missing = ([f"{len(no_id)} mesh piece(s) not uploaded"] if no_id else []) + ([f"stylised meshes in use: {', '.join(stylised[:4])}"] if stylised else [])
    st = "done" if names and not no_id and not stylised else ("partial" if names else "to do")
    stage("meshes", "real meshes (vetted CC0)", st, missing,
          [f"assets/worlds/imports/<set>.json -> lune run kit world import <set>{gflag}",
           "replace stylised (q_*) names in forest / scatter \"meshes\" with scanned ones", f"lune run kit upload{gflag}"])

    # 5 dressing: roads first, scatter / forest present
    has_roads = bool(walk_ops(bp, "path"))
    has_dress = bool(walk_ops(bp, "scatter") or walk_ops(bp, "forest"))
    st = "done" if has_roads and has_dress else ("partial" if has_dress or has_roads else "to do")
    stage("dressing", "dressing (roads first)", st,
          [m for m, bad in (("roads / paths", not has_roads), ("scatter / forest", not has_dress)) if bad],
          [f"edit assets/worlds/{name}.json (path steps BEFORE scatter / forest)", f"lune run kit world check {name}{gflag}"])

    # 6 check: this world's own check, run now (the global last-check file may be another world's)
    summ = ""
    compiled = os.path.join(root, "build", "worlds", f"{name}.json")
    if os.path.isfile(compiled):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join("kit", "world", "worldcheck.py"), compiled,
                            "--out", os.path.join(root, "build", "worlds", "checks")], capture_output=True, text=True)
        try:
            summ = str(json.loads(r.stdout.strip().splitlines()[-1]).get("summary") or "")
        except (ValueError, IndexError):
            summ = "the check crashed"
    ok_check = " 0 error(s)" in summ
    st = "done" if ok_check and "0 warning(s)" in summ else ("partial" if ok_check else "to do")
    stage("check", "check (plays, look lint)", st,
          [] if st == "done" else [summ[:160] or "no check run yet"], [f"lune run kit world check {name}{gflag}"])

    # 7 look: every station on its own page, beside the reference still CHOSEN for it (kit/world/lookpages.py: a
    # pair made by order alone is not a comparison anybody chose; "none" + why is a choice)
    look = os.path.join(root, "build", "worlds", "look", f"{name}.png")
    index = os.path.join(root, "build", "worlds", "look", name, "pages", "index.json")
    fresh = os.path.isfile(look) and os.path.getmtime(look) >= os.path.getmtime(bp_path)
    rows = (load(index) or {}).get("pages") or [] if fresh and os.path.isfile(index) else []
    by_order = [r.get("station") for r in rows if r.get("paired") == "order"]
    no_still = bool(rows) and all(r.get("paired") == "none" and not r.get("reference") for r in rows)
    paired = bool(rows) and not by_order and not no_still
    st = "done" if paired else ("partial" if fresh else "to do")
    stage("look", "look: a page a station beside its reference", st,
          [m for m, bad in (("a look newer than the blueprint (a page a station)", not fresh),
                            (f"a still chosen for every station ({len(by_order)} paired by order only: "
                             f"assets/worlds/refs/{name}/stations.json)", fresh and bool(by_order)),
                            ("reference stills to judge it beside", fresh and (no_still or not rows))) if bad],
          [f"lune run kit world look {name}{gflag}", f"lune run kit world shots {name}{gflag}"])

    # 8 studio: the stations in Roblox's own light (kit world studio: a capture newer than the blueprint), then a walk
    # log from the MCP
    walk = os.path.join(root, "build", "worlds", "studio", f"{name}.walk.json")
    shot = os.path.join(root, "build", "worlds", "studio", name, "shots", "capture.json")
    lit = os.path.isfile(shot) and os.path.getmtime(shot) >= os.path.getmtime(bp_path)
    stage("studio", "Studio: its own light on the stations, then the walk (MCP, 0 console errors)",
          "done" if os.path.isfile(walk) else ("partial" if lit else "to do"),
          [m for m, bad in (("the stations captured in Roblox Studio, newer than the blueprint", not lit),
                            ("a Studio walk recorded", not os.path.isfile(walk))) if bad],
          [f"lune run kit world studio {name}{gflag}",
           f"lune run kit world studio {name} --capture{gflag}   (with the scratch place open; then run its capture.luau once through the MCP)",
           f"rojo serve {root.replace(os.sep, '/')}/default.project.json (Studio: connect)",
           f"walk the stations through the Studio MCP; record {walk.replace(os.sep, '/')}"])

    # 9 verdict: the owner's latest on this world (>= 7 and newer than the blueprint = done)
    latest = None
    for f in glob.glob(os.path.join("kit", "knowledge", "vault", "world", "verdicts", "*.md")):
        front = {}
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        if text.startswith("---"):
            for line in text.split("---", 2)[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    front[k.strip()] = v.strip().strip('"')
        if str(front.get("name", "")).lower().startswith(name.lower()):
            words = text.split("---", 2)[2].strip().splitlines()[0] if text.count("---") >= 2 else ""
            if latest is None or front.get("date", "") > latest["date"]:
                latest = {"date": front.get("date", ""), "score": float(front.get("score", 0) or 0), "words": words}
    import datetime
    bp_date = datetime.date.fromtimestamp(os.path.getmtime(bp_path)).isoformat()
    if latest and latest["score"] >= 7 and latest["date"] >= bp_date:
        st, missing = "done", []
    elif latest:
        st, missing = "partial", [f"latest {latest['score']:g}/10 on {latest['date']}: \"{latest['words'][:60]}\""
                                  + (" (older than the blueprint)" if latest["date"] < bp_date else "")]
    else:
        st, missing = "to do", ["no verdict yet"]
    stage("verdict", "the owner's verdict", st, missing,
          [f"the owner walks it; lune run kit verdict world {name} <0-10> \"<the owner's words>\""])

    first = next((s for s in stages if s["status"] != "done"), None)
    done = sum(1 for s in stages if s["status"] == "done")
    print(json.dumps({
        "status": "pass",
        "summary": f"world plan {name}: {done}/{len(stages)} stages done" + (f"; next: {first['title']} ({first['status']})" if first else ""),
        "next_action": (first["commands"][0] if first else f"done: the owner's next gap on {name}"),
        "stages": stages,
        "next": first["key"] if first else None,
        "examples": layout_examples(root, name, bp, family=argv[argv.index("--family") + 1]
                                    if "--family" in argv and argv.index("--family") + 1 < len(argv) else None),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
