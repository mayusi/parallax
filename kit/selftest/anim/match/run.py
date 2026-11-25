"""kit/selftest/anim/match/run.py — pose matching, distance matching and motion matching (kit/anim/match_tables.py,
src/kit/AnimMatch.luau; the owner's method lists 2026-11-13), on cuts the owner loved, generated in memory.

    python kit/selftest/anim/match/run.py same   tables baked from the loved cuts; the GAME's matcher
                                                 (src/kit/AnimMatch.luau, through kit/anim/match_run.luau) gives
                                                 the build's answers: a clip entered at the frame nearest a pose and
                                                 never past its Hit, the frame for a distance left, a frame of the
                                                 database finding itself and the motion staying on its clip
    python kit/selftest/anim/match/run.py back   a body that steps back on its way to the stop: no distance table
                                                 (one distance would mean two frames) - this case FAILS
    python kit/selftest/anim/match/run.py set    A MOTION SET (kit/anim/match_tables.py set, what `kit anim` runs for
                                                 assets/animations/motion/<Set>.motion.json): three loved cuts as
                                                 built clips give a database at 30 rows a second; the game's own
                                                 step (AnimMatch.motionStep) keeps a body that follows its clip on
                                                 it with no jump, and sends one that does another cut to that cut
    python kit/selftest/anim/match/run.py unbuilt  the same set naming a clip that was never built: no database
                                                 (this case FAILS)

Prints one JSON line {schema, status, summary, next_action}; what it writes is under build/selftest/ in a folder of
this run's own, removed at the end."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import match_tables as MT  # noqa: E402
import strike as S  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved")


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def loved(name):
    with open(os.path.join(LOVED, f"{name}.move.json"), encoding="utf-8") as fh:
        return S.generate(json.load(fh))[0]


def travelling(c, back=0.0):
    n = len(c["times"])
    c["root"] = []
    for i in range(n):
        u = i / (n - 1)
        z = -4.0 * (1 - (1 - u) ** 2) + (back * np.sin((u - 0.4) / 0.2 * np.pi) if 0.4 < u < 0.6 else 0.0)
        c["root"].append([0, 0, 0, 1, 0, 0, z])
    return c


def ask(run, table, queries):
    tp, qp = os.path.join(run, "table.json"), os.path.join(run, "queries.json")
    for p, v in ((tp, table), (qp, queries)):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(v, fh)
    r = subprocess.run(["lune", "run", os.path.join(ROOT, "kit", "anim", "match_run.luau"), tp, qp], capture_output=True, text=True,
                       encoding="utf-8", cwd=ROOT)
    return json.loads(r.stdout.strip().splitlines()[-1])["answers"]


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_match_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        kesa = loved("Katana1Kesa")
        if case == "back":
            cp = os.path.join(run, "Back.clip.json")
            with open(cp, "w", encoding="utf-8") as fh:
                json.dump(travelling(kesa, back=1.2), fh)
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = MT.main(["distance", cp, "--out", os.path.join(run, "t.json")])
            v = json.loads(said.getvalue().strip().splitlines()[-1])
            if code != 0 and os.path.isfile(os.path.join(run, "t.json")):
                return out("pass", "match selftest: a refused distance table was written all the same", "kit/anim/match_tables.py")
            return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
        if case in ("set", "unbuilt"):
            names = ["Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko"]
            by = {n: loved(n) for n in names}
            guard = {j: by["Katana1Kesa"]["joints"][j]["frames"][0] for j in by["Katana1Kesa"]["joints"]}
            by["Rest"] = {"name": "Rest", "rig": "R6", "fps": 60, "loop": True, "events": [], "times": [i / 60 for i in range(51)],
                          "joints": {j: {"frames": [list(f) for _ in range(51)]} for j, f in guard.items()}}
            names = names + ["Rest"]
            folder = os.path.join(run, "clips")
            os.makedirs(folder)
            for n in names:
                with open(os.path.join(folder, f"{n}.clip.json"), "w", encoding="utf-8") as fh:
                    json.dump(by[n], fh)
            sp, dbp = os.path.join(run, "Blade.motion.json"), os.path.join(run, "db.json")
            with open(sp, "w", encoding="utf-8") as fh:
                json.dump({"clips": names + (["Katana4Ghost"] if case == "unbuilt" else []), "rest": "Rest"}, fh)
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = MT.main(["set", sp, "--clips", folder, "--out", dbp])
            v = json.loads(said.getvalue().strip().splitlines()[-1])
            if case == "unbuilt":
                if code != 0 and os.path.isfile(dbp):
                    return out("pass", "match selftest: a refused motion set left a database behind", "kit/anim/match_tables.py set")
                return out("pass" if code == 0 else "fail", v["summary"], v["next_action"])
            if code != 0 or not shutil.which("lune"):
                return out("fail", f"match selftest (a motion set): no database, or no lune to ask the game's step ({v['summary']})",
                           "kit/anim/match_tables.py set")
            with open(dbp, encoding="utf-8") as fh:
                db = json.load(fh)

            def pose(n, i):
                return {j: by[n]["joints"][j]["frames"][i][:4] for j in by[n]["joints"]}
            qs = [  # the kesa plays and the body follows it; then the body does the makko
                {"step": True, "prev": pose("Katana1Kesa", 11), "pose": pose("Katana1Kesa", 12), "dt": 1 / 60, "current": ["Katana1Kesa", 6.0]},
                {"step": True, "prev": pose("Katana1Kesa", 23), "pose": pose("Katana1Kesa", 24), "dt": 1 / 60, "current": ["Katana1Kesa", 12.0]},
                {"step": True, "prev": pose("Katana3Makko", 19), "pose": pose("Katana3Makko", 20), "dt": 1 / 60, "current": ["Katana1Kesa", 9.0]}]
            game = ask(run, db, qs)
            want = [MT.motion_step(db, q["prev"], q["pose"], q["dt"], q["current"]) for q in qs]
            wrong = []
            if db.get("fps") != 30 or list(db["clips"]) != names or db.get("rest") != "Rest":
                wrong.append(f"the database is not the three cuts and their rest at 30 rows a second ({db.get('fps')}, {list(db['clips'])})")
            if game != want:
                wrong.append(f"the game's step answers {game}, the build's {want}")
            if any(g["clip"] != "Katana1Kesa" or g["jump"] for g in game[:2]):
                wrong.append(f"a body that follows the kesa was thrown about ({game[:2]})")
            if game[2]["clip"] != "Katana3Makko" or not game[2]["jump"]:
                wrong.append(f"a body doing the makko was not sent to it ({game[2]})")
            if wrong:
                return out("fail", "match selftest (a motion set): " + "; ".join(wrong), "kit/anim/match_tables.py / src/kit/AnimMatch.luau")
            return out("pass", "match selftest (a motion set): three loved cuts give a database at 30 rows a second; the game's own "
                               "step keeps a body that follows the kesa on it with no jump and sends one doing the makko to the makko",
                       "none - proceed")
        if not shutil.which("lune"):
            return out("fail", "match selftest: lune is not on this machine's path (the game's matcher cannot be asked)", "install lune")
        wrong = []
        hit = round(next(e["t"] for e in kesa["events"] if e["name"] == "Hit") * kesa["fps"])
        t = MT.pose_table(kesa)
        poses = [{j: kesa["joints"][j]["frames"][i][:4] for j in kesa["joints"]} for i in (0, 9, 18, hit - 1, len(kesa["times"]) - 1)]
        game = ask(run, t, [{"pose": p} for p in poses])
        if game != [MT.pose_match(t, p) for p in poses] or game[:4] != [0, 9, 18, hit - 1] or game[4] >= hit:
            wrong.append(f"pose matching: the game enters at {game} (its own frames 0, 9, 18, {hit - 1} asked, then a pose after the Hit)")
        d = MT.distance_table(travelling(loved("Katana1Kesa")))
        dist = [99, 3.0, 1.5, 0.4, 0]
        game = ask(run, d, [{"distance": x} for x in dist])
        if not np.allclose(game, [MT.distance_match(d, x) for x in dist], atol=1e-6) or any(a > b for a, b in zip(game, game[1:])):
            wrong.append(f"distance matching: the game's frames {game} for {dist} studs left")
        clips = [kesa, loved("Katana2GyakuKesa"), loved("Katana3Makko")]
        db = MT.motion_db(clips)
        qs, want = [], []
        # as a game asks: the frame on screen (its pose, how it turned since the frame before) -> the frame to play next
        for c, f, cur in ((clips[0], 20, None), (clips[0], 21, ["Katana1Kesa", 21]), (clips[2], 12, ["Katana1Kesa", 30])):
            pose, vel = MT.query_at(db, c, f)
            qs.append({"pose": pose, "vel": vel, **({"current": cur} if cur else {})})
            want.append([c["name"], f + 1])
        game = ask(run, db, qs)
        if game != want or game != [MT.motion_match(db, q["pose"], q["vel"], q.get("current")) for q in qs]:
            wrong.append(f"motion matching: the game plays {game}, the frames asked were {want}")
        if wrong:
            return out("fail", "match selftest: " + "; ".join(wrong), "kit/anim/match_tables.py / src/kit/AnimMatch.luau")
        return out("pass", "match selftest: on the loved cuts the game's matcher gives the build's answers - a clip is entered at "
                           "the frame nearest the pose and never past its Hit, a distance left gives its frame, a frame of the "
                           "database is followed by the next and a clip is left only for a motion that fits better", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("same", "back", "set", "unbuilt"):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
