"""evolve.py — INTERACTIVE EVOLUTION of a move (owner-approved plan v3, idea 1, 2026-10-12): the owner sees ~12 whole
animations, clicks the ones they like, the next 12 are bred from those picks. The owner's eye is the judge - every
candidate is built ONLY from human-made loved animation (never hand-posed): a GENOME = a loved base swing + optional
loved arms (phase-aligned, kit/anim/learn_compose.py) + mirror + tempo (heavier / lighter) + an impact hitstop + an
amplitude + the learned R6 arm slides; the greatsword in the right fist.

    python kit/anim/evolve.py start <Move> [--pool attack]     round 0 (random genomes from the loved pool)
    python kit/anim/evolve.py next <Move>                      breed from the owner's picks of the latest round
Rounds live in _artifacts/r6lib/evolve/<Move>/round_<n>/ (genomes.json, c<i>.clip.json, c<i>.gif); the picker server
(_scratch/r6lib_server.py, /evolve) shows them and saves picks.json."""
import copy
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
import derive as D  # noqa: E402
import learn_compose as LC  # noqa: E402
import motion_match as MM  # noqa: E402
from blender_path import find_blender  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
EVO = os.path.join(LIB, "evolve")
BLENDER = find_blender() or "blender"
N = 12
SWORDY = ("sword", "slash", "swing", "katana", "blade", "great", "cleave", "combat", "m1", "attack", "combo", "lmb", "slam")


def pool(kinds=("attack", "m1/combo")):
    picks = json.load(open(os.path.join("assets", "animations", "library", "owner_picks.json"), encoding="utf-8"))["picks"]
    out = []
    for r in picks:
        if r["verdict"] == "love" and not r["laggy"] and r["kind"] in kinds and 0.3 <= (r["duration"] or 0) <= 2.2:
            p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
            if os.path.isfile(p):
                w = 3 if any(s in f"{r['name']} {r['pack']}".lower() for s in SWORDY) else 1
                out.append((r["id"], w))
    return out


def lib(cid):
    return MM.resample60(json.load(open(os.path.join(LIB, "clips", f"{cid}.clip.json"), encoding="utf-8")))


def random_genome(rng, P):
    ids, ws = zip(*P)
    g = {"base": rng.choices(ids, ws)[0], "arms": rng.choices(ids, ws)[0] if rng.random() < 0.4 else None,
         "mirror": rng.random() < 0.3, "tempo": round(rng.uniform(1.0, 1.45), 2), "hitstop": rng.choice([0, 3, 5, 7]),
         "amp": round(rng.uniform(0.95, 1.25), 2), "slide": rng.choice([0.0, 1.5, 2.5])}
    return g


def mutate(g, rng, P):
    g = dict(g)
    ids, ws = zip(*P)
    for k in rng.sample(["arms", "mirror", "tempo", "hitstop", "amp", "slide"], 2):
        if k == "arms":
            g["arms"] = rng.choices(ids, ws)[0] if rng.random() < 0.5 else None
        elif k == "mirror":
            g["mirror"] = not g["mirror"]
        elif k == "tempo":
            g["tempo"] = round(min(1.7, max(0.8, g["tempo"] * rng.uniform(0.85, 1.18))), 2)
        elif k == "hitstop":
            g["hitstop"] = rng.choice([0, 3, 5, 7, 9])
        elif k == "amp":
            g["amp"] = round(min(1.4, max(0.85, g["amp"] * rng.uniform(0.9, 1.12))), 2)
        else:
            g["slide"] = rng.choice([0.0, 1.5, 2.5])
    return g


def cross(a, b, rng):
    return {k: (a if rng.random() < 0.5 else b)[k] for k in a}


def express(g):
    c = copy.deepcopy(lib(g["base"]))
    if g.get("arms") and g["arms"] != g["base"]:
        c = LC.compose(c, lib(g["arms"]))
    if g.get("mirror"):
        D.op_mirror(c)
    if g.get("amp", 1.0) != 1.0:
        D.op_amplify(c, ["Torso", "Right Arm", "Left Arm"], g["amp"])
    if g.get("tempo", 1.0) != 1.0:
        D.op_retime(c, duration=float(c["times"][-1]) * g["tempo"], fps=60)
    if g.get("hitstop"):
        D.op_hold(c, D.impact_index(c) / 60.0, int(g["hitstop"]))
    if g.get("slide"):
        D.op_r6slide(c, g["slide"], kind="attack")
    c["loop"] = False
    return c


def with_sword(c, length=4.6):
    import numpy as np
    import clip as C
    W = C.world_frames(c, C.load_rig("r6"))
    tips, grips = [], []
    for w in W:
        m = np.asarray(w["Right Arm"])
        g = m[:3, :3] @ np.array([0.0, -1.0, 0.0]) + m[:3, 3]
        d = m[:3, :3] @ np.array([0.0, 0.0, -1.0])
        grips.append([float(v) for v in g])
        tips.append([float(v) for v in g + d * length])
    c["sword"] = {"tip": tips, "grip_path": grips, "length": length, "grip": 0.75}
    return c


def render(cdir, i, c):
    path = os.path.join(cdir, f"c{i}.clip.json")
    json.dump(c, open(path, "w", encoding="utf-8"))
    name = f"c{i}.r6"
    p = subprocess.run([BLENDER, "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec", "--python-exit-code", "2", "-P",
                        "kit/anim/look_r6.py", "--", name, "--clip", path, "--out", cdir, "--size", "260"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run(["python", "kit/anim/look_sheet.py", os.path.join(cdir, f"{name}.look")], capture_output=True)
    gif = os.path.join(cdir, f"{name}.look.gif")
    if os.path.isfile(gif):
        os.replace(gif, os.path.join(cdir, f"c{i}.gif"))
    return os.path.isfile(os.path.join(cdir, f"c{i}.gif"))


def make_round(move, genomes, n_round):
    cdir = os.path.join(EVO, move, f"round_{n_round}")
    os.makedirs(cdir, exist_ok=True)
    clips = []
    for g in genomes:
        try:
            clips.append(with_sword(express(g)))
        except Exception as e:
            clips.append(None)
            g["error"] = str(e)[:120]
    with ThreadPoolExecutor(3) as ex:
        ok = list(ex.map(lambda ic: render(cdir, ic[0], ic[1]) if ic[1] else False, enumerate(clips)))
    json.dump({"move": move, "round": n_round, "genomes": genomes, "ok": ok}, open(os.path.join(cdir, "genomes.json"), "w"), indent=1)
    json.dump({"move": move, "round": n_round, "status": "ready"}, open(os.path.join(EVO, move, "state.json"), "w"))
    return cdir, ok


def latest(move):
    st = json.load(open(os.path.join(EVO, move, "state.json")))
    return st["round"]


def main(argv):
    cmd, move = argv[0], argv[1]
    rng = random.Random()
    P = pool()
    os.makedirs(os.path.join(EVO, move), exist_ok=True)
    if cmd == "start":
        json.dump({"move": move, "round": 0, "status": "breeding"}, open(os.path.join(EVO, move, "state.json"), "w"))
        cdir, ok = make_round(move, [random_genome(rng, P) for _ in range(N)], 0)
    else:
        r = latest(move)
        prev = json.load(open(os.path.join(EVO, move, f"round_{r}", "genomes.json")))["genomes"]
        picks_path = os.path.join(EVO, move, f"round_{r}", "picks.json")
        picked = [prev[i] for i in (json.load(open(picks_path)) if os.path.isfile(picks_path) else [])] or prev[:2]
        json.dump({"move": move, "round": r + 1, "status": "breeding"}, open(os.path.join(EVO, move, "state.json"), "w"))
        kids = [dict(p) for p in picked]                                   # the picks survive unchanged (elitism)
        while len(kids) < N:
            a, b = rng.choice(picked), rng.choice(picked)
            kid = cross(a, b, rng) if a is not b and rng.random() < 0.5 else dict(a)
            kids.append(mutate(kid, rng, P) if rng.random() < 0.85 else random_genome(rng, P))
        cdir, ok = make_round(move, kids[:N], r + 1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"evolve {move}: {cdir} ({sum(ok)}/{len(ok)} rendered)", "next_action": "the owner picks at http://localhost:8765/evolve"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
