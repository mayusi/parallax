"""motion_vocab.py — the R6 MOTION VOCABULARY + SCRIPTED COMPOSITION (owner-approved "animate anything on R6" plan,
steps 2, 4 and 5, 2026-10-12): a model DIRECTS in words, real human-made motion PERFORMS. The model never sets a joint.

Step 2 - primitives: every clip of the catalog (kit/anim/motion_lib.py) is cut where the whole body slows down (minima
of the summed hand / foot / torso speed) into short pieces, each labelled from its own motion:
    strike  - holds the fastest hand moment of the clip (>= 60% of its peak): measured direction, hand, speed
    windup  - the moving piece right before a strike          recover - the moving piece right after one
    hold    - the body nearly still                           move    - anything else (steps, turns, gestures)
    cycle   - a whole looping clip (walks, runs, idles)
Every primitive keeps its clip's tags / verdict / licence and its first and last pose (for joins).

Step 4 - a SCRIPT is what a model writes:  {"name": "...", "steps": [{"say": "two handed overhead", "take": "windup"},
    {"say": "overhead chop", "take": "strike"}, {"take": "recover"}, {"say": "guard idle", "take": "cycle", "seconds": 1}]}
  "say" = words searched in the vocabulary, "take" = the label wanted (or "whole" = the entire clip; "id" pins a clip).
  A step with no "say" CONTINUES the previous step's clip with its next piece of that label (human continuity).

Step 5 - priors learned from the data, not tuned by hand: each step's piece is chosen among the best word matches by
  the JOIN COST (pose distance from where the last piece ended to where this one starts; the next piece of the same
  clip costs nothing - real transitions beat any blend), the crossfade grows with that distance, and the learned R6
  arm slides polish the result (derive.polish).

    python kit/anim/motion_vocab.py build                      -> _artifacts/r6lib/vocab.json + vocab_poses.npz
    python kit/anim/motion_vocab.py find "overhead chop" [--take strike] [--k 10]
    python kit/anim/motion_vocab.py compose <script.json> [--render] [--seed N]  -> _artifacts/r6lib/composed/<name>"""
import copy
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import derive as D  # noqa: E402
import motion_lib as ML  # noqa: E402
import pose_space as PS  # noqa: E402

LIB = ML.LIB
VOCAB = os.path.join(LIB, "vocab.json")
POSES = os.path.join(LIB, "vocab_poses.npz")
OUT = os.path.join(LIB, "composed")
FPS = 60
MIN_SEG = 8          # frames (0.13 s): shorter pieces merge into their neighbour
STRIKE_SHARE = 0.6   # a piece is a strike when its fastest hand reaches 60% of the clip's fastest
STILL = 2.0          # studs/s: below this mean hand speed a piece is a hold
LABEL_WORDS = {"strike": "strike hit attack swing slash punch", "windup": "windup anticipation prepare raise",
               "recover": "recover recovery return settle followthrough", "hold": "hold pose still",
               "move": "move step turn", "cycle": "loop cycle idle"}


def load_clip(cid):
    c = json.load(open(os.path.join(LIB, "clips", f"{cid}.clip.json"), encoding="utf-8"))
    if int(round(float(c.get("fps") or 30))) != FPS:
        D.op_retime(c, duration=float(c["times"][-1]), fps=FPS)
    return c


def _body_speeds(c, rig):
    W = C.world_frames(c, rig)
    n = len(W)

    def pt(part, local):
        return np.array([(np.asarray(w[part]) @ np.array([*local, 1.0]))[:3] for w in W])

    hands = [pt("Right Arm", (0, -1, 0)), pt("Left Arm", (0, -1, 0))]
    feet = [pt("Right Leg", (0, -1, 0)), pt("Left Leg", (0, -1, 0))]
    head = pt("Head", (0, 0.5, 0))
    sp = lambda P: np.r_[0.0, np.linalg.norm(np.diff(P, axis=0), axis=1) * FPS]  # noqa: E731
    hs = np.maximum(sp(hands[0]), sp(hands[1]))
    body = hs + np.maximum(sp(feet[0]), sp(feet[1])) + sp(head)
    return W, hands, hs, body, n


def segment(c, rig):
    """cut points + labels of one clip at 60 fps -> [(a, b, label, facts)] covering frames a..b"""
    W, hands, hs, body, n = _body_speeds(c, rig)
    if c.get("loop") or n < 2 * MIN_SEG:
        return [(0, n - 1, "cycle" if c.get("loop") else "move", {})]
    s = np.convolve(body, np.ones(7) / 7, mode="same")
    cuts = [0]
    for i in range(MIN_SEG, n - MIN_SEG):
        lo, hi = max(0, i - 6), min(n, i + 7)
        if s[i] == s[lo:hi].min() and s[i] < 0.7 * s[lo:hi].max() and i - cuts[-1] >= MIN_SEG:
            cuts.append(i)
    if n - 1 - cuts[-1] < MIN_SEG and len(cuts) > 1:
        cuts.pop()
    cuts.append(n - 1)
    peak = float(hs.max())
    segs = []
    for a, b in zip(cuts, cuts[1:]):
        hp = float(hs[a:b + 1].max())
        f = {"peak": round(hp, 1), "secs": round((b - a) / FPS, 3)}
        if peak > 14 and hp >= STRIKE_SHARE * peak:
            i = a + int(np.argmax(hs[a:b + 1]))
            k = 0 if np.ptp(hands[0][a:b + 1], axis=0).sum() >= np.ptp(hands[1][a:b + 1], axis=0).sum() else 1
            v = hands[k][min(n - 1, i + 2)] - hands[k][max(0, i - 2)]
            v = v / max(np.linalg.norm(v), 1e-9)
            R = np.asarray(W[i]["Torso"])[:3, :3]
            rh, fh = R[:, 0] * [1, 0, 1], -R[:, 2] * [1, 0, 1]
            x = float(v @ rh / max(np.linalg.norm(rh), 1e-9))
            fw = float(v @ fh / max(np.linalg.norm(fh), 1e-9))
            d = "downward" if v[1] < -0.6 else "upward" if v[1] > 0.6 else "thrust" if fw > 0.6 else "horizontal" if abs(x) > 0.6 else "diagonal"
            f.update(dir=d, hand="right" if k == 0 else "left", hit_at=round((i - a) / FPS, 3))
            label = "strike"
        elif float(hs[a:b + 1].mean()) < STILL:
            label = "hold"
        else:
            label = "move"
        segs.append([a, b, label, f])
    for i, sg in enumerate(segs):                  # windup / recover = the moving pieces around a strike
        if sg[2] == "move" and i + 1 < len(segs) and segs[i + 1][2] == "strike":
            sg[2] = "windup"
        elif sg[2] == "move" and i > 0 and segs[i - 1][2] == "strike":
            sg[2] = "recover"
    return [tuple(s) for s in segs]


def build():
    cat = ML.load()
    rig = C.load_rig("r6")
    prims, starts, ends = [], [], []
    for r in cat:
        try:
            c = load_clip(r["id"])
            segs = segment(c, rig)
            V = PS.clip_vectors(c)
        except Exception:
            continue
        for k, (a, b, label, f) in enumerate(segs):
            tags = [t for t in r["tags"] if t not in ("loop",)]
            if "dir" in f:
                tags = [t for t in tags if t not in ("downward", "upward", "thrust", "horizontal", "diagonal")] + [f["dir"]]
            prims.append({"pid": f"{r['id']}#{k}", "id": r["id"], "k": k, "a": a, "b": b, "label": label, "facts": f,
                          "name": r["name"], "kind": r["kind"], "pack": r["pack"], "tags": tags, "verdict": r["verdict"],
                          "licence": r["licence"], "n": len(segs)})
            starts.append(V[a])
            ends.append(V[b])
    json.dump({"schema": 1, "prims": prims}, open(VOCAB, "w", encoding="utf-8"), indent=0)
    np.savez(POSES, start=np.array(starts), end=np.array(ends))
    return prims


_V = None


def load():
    global _V
    if _V is None:
        prims = json.load(open(VOCAB, encoding="utf-8"))["prims"]
        P = np.load(POSES)
        _V = (prims, P["start"], P["end"], {p["pid"]: i for i, p in enumerate(prims)})
    return _V


def doc(p):
    return ML.words(p["name"]) * 2 + ML.words(p["pack"]) + ML.words(p["kind"].replace("/", " ")) + p["tags"] * 2 + LABEL_WORDS[p["label"]].split()


def find(say, take=None, k=20, game_only=True, prims=None):
    """the vocabulary pieces matching the words (and the label), best first: [(score, index)]"""
    prims = prims if prims is not None else load()[0]
    pool = [(i, p) for i, p in enumerate(prims) if (not game_only or p["licence"] == "game") and (take is None or p["label"] == take)]
    if not say:
        return [(ML.VERDICT_WEIGHT.get(p["verdict"], 0.9), i) for i, p in pool][:k]
    cat = [{"id": i, "name": p["name"], "pack": p["pack"], "kind": p["kind"], "tags": p["tags"] + LABEL_WORDS[p["label"]].split(),
            "verdict": p["verdict"], "licence": p["licence"]} for i, p in pool]
    return [(s, r["id"]) for s, r in ML.find(say, k=k, game_only=False, cat=cat)]


def torso_yaw(fr):
    """the facing (deg about +Y) of a Torso joint frame [qx,qy,qz,qw,...]: its -Z axis on the floor"""
    R = C.quat_mat(np.asarray(fr[:4], float))
    f = -R[:, 2]
    return float(np.degrees(np.arctan2(-f[0], -f[2])))


def op_turn(c, deg):
    """turn the whole character about the vertical axis through the root (the Torso joint carries the body): every
    Torso rotation is pre-multiplied and its position turned - used so a piece STARTS facing where the last one ended"""
    a = np.radians(deg)
    q = np.array([0.0, np.sin(a / 2), 0.0, np.cos(a / 2)])
    Ry = C.quat_mat(q)
    F = D.frames_of(c, "Torso")
    out = []
    for f in F:
        f = np.asarray(f, float)
        R = Ry @ C.quat_mat(f[:4])
        out.append(np.concatenate([C.mat_quat(R), Ry @ f[4:7]]))
    D.set_frames(c, "Torso", out)
    return c


def mirror_vec(v):
    """a pose vector mirrored left <-> right (derive.op_mirror on a one-frame clip)"""
    fr = PS.from_vec(v)
    c = {"fps": FPS, "times": [0.0], "joints": {j: {"frames": [fr[j]]} for j in PS.JOINTS}}
    D.op_mirror(c)
    return PS.to_vec({j: list(c["joints"][j]["frames"][0]) for j in PS.JOINTS})


def piece(i, prims):
    p = prims[i]
    c = load_clip(p["id"])
    D.op_trim(c, start=p["a"] / FPS, end=p["b"] / FPS)
    return c


def compose(script, seed=0, k=12):
    """a script -> (clip, the pieces used). Each step: the best join among the top-k word matches."""
    prims, S, E, by_pid = load()
    rng = np.random.default_rng(seed)
    out, used, prev, last_say = None, [], None, ""
    for st in script["steps"]:
        take = st.get("take")
        mirror = bool(st.get("mirror"))
        if st.get("id"):
            cands = [(1.0, i) for i, p in enumerate(prims) if p["id"] == st["id"] and (take in (None, "whole") or p["label"] == take)]
        elif not st.get("say") and prev is not None:
            # continue the same clip: its next piece with that label, else simply its next piece ("rest" = all of
            # what is left of the clip); past the clip's end, search again with the last words said
            pp = prims[prev]
            nxt = [by_pid[f"{pp['id']}#{j}"] for j in range(pp["k"] + 1, pp["n"]) if f"{pp['id']}#{j}" in by_pid]
            if take == "rest" and nxt:
                cands = [(1.0, nxt[0])]
                st = dict(st, _rest=nxt)
            else:
                lab = [i for i in nxt if take is None or prims[i]["label"] == take]
                cands = [(1.0, (lab or nxt)[0])] if (lab or nxt) else find(last_say, take, k=k)
        else:
            cands = find(st.get("say", ""), None if take == "whole" else take, k=k)
            last_say = st.get("say", "")
        if not cands:
            raise ValueError(f"no piece for step {st}")
        if prev is None:
            # the first step: the best match, with a little variety between seeds among near-equal scores
            top = [i for s, i in cands if s >= 0.85 * cands[0][0]]
            pick = int(top[int(rng.integers(len(top)))])
            join = 0.0
        else:
            end = mirror_vec(E[prev]) if used[-1][1] else E[prev]
            best = None
            for rank, (s, i) in enumerate(cands):
                same = prims[i]["id"] == prims[prev]["id"] and prims[i]["k"] == prims[prev]["k"] + 1
                jc = 0.0 if same else float(np.linalg.norm(S[i] - end))
                cost = jc + 0.15 * rank - 0.05 * s + float(rng.uniform(0, 0.05))
                if best is None or cost < best[0]:
                    best = (cost, i, jc)
            _, pick, join = best
        if take == "whole":
            c = load_clip(prims[pick]["id"])
        elif st.get("_rest"):
            last = prims[st["_rest"][-1]]
            c = load_clip(prims[pick]["id"])
            D.op_trim(c, start=prims[pick]["a"] / FPS, end=last["b"] / FPS)
            pick = st["_rest"][-1]
        else:
            c = piece(pick, prims)
        if mirror:
            D.op_mirror(c)
        if out is not None and join != 0.0 and "Torso" in c["joints"] and "Torso" in out["joints"]:
            # continuity of facing: a piece from another clip starts turned to where the body already faces (a piece
            # of the SAME clip is already continuous)
            d = torso_yaw(D.frames_of(out, "Torso")[-1]) - torso_yaw(D.frames_of(c, "Torso")[0])
            op_turn(c, (d + 180) % 360 - 180)
        if st.get("seconds") and c.get("times"):
            want = float(st["seconds"])
            if prims[pick]["label"] == "cycle" and c["times"][-1] > 0:
                reps = max(1, int(np.ceil(want / c["times"][-1])))
                one = copy.deepcopy(c)
                for _ in range(reps - 1):
                    D.op_concat(c, one, crossfade=0)
                D.op_trim(c, start=0.0, end=want)
            else:
                D.op_retime(c, duration=want, fps=FPS)
        if st.get("tempo"):
            D.op_retime(c, duration=float(c["times"][-1]) * float(st["tempo"]), fps=FPS)
        if out is None:
            out = c
        else:
            fade = 0 if join == 0.0 else int(min(14, max(4, round(join * 1.5))))
            D.op_concat(out, c, crossfade=fade)
        used.append((pick, mirror, round(join, 2)))
        prev = pick
    out["name"] = script.get("name", "Composed")
    out["loop"] = bool(script.get("loop"))
    out["fps"] = FPS
    if script.get("polish", True):
        D.polish(out, kind="attack")
    out["composed_from"] = [{"pid": prims[i]["pid"], "name": prims[i]["name"], "label": prims[i]["label"], "mirror": m, "join": j} for i, m, j in used]
    return out, used


def render(c, odir, name, size=300):
    os.makedirs(odir, exist_ok=True)
    path = os.path.join(odir, f"{name}.clip.json")
    json.dump(c, open(path, "w", encoding="utf-8"))
    look = f"{name}.r6"
    p = subprocess.run([ML.BLENDER, "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec", "--python-exit-code", "2", "-P",
                        "kit/anim/look_r6.py", "--", look, "--clip", path, "--out", odir, "--size", str(size)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run([sys.executable, "kit/anim/look_sheet.py", os.path.join(odir, f"{look}.look")], capture_output=True)
    g = os.path.join(odir, f"{look}.look.gif")
    return path, (g if os.path.isfile(g) else None), p.returncode


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "build":
        prims = build()
        by = {}
        for p in prims:
            by[p["label"]] = by.get(p["label"], 0) + 1
        ML.emit("pass" if prims else "fail", f"vocabulary: {len(prims)} pieces from {len({p['id'] for p in prims})} clips; by label {by}",
                'python kit/anim/motion_vocab.py find "<words>" --take strike')
        return 0
    if argv[0] == "find":
        prims = load()[0]
        take = argv[argv.index("--take") + 1] if "--take" in argv else None
        k = int(argv[argv.index("--k") + 1]) if "--k" in argv else 10
        res = find(argv[1], take, k=k)
        for s, i in res:
            p = prims[i]
            print(f"{s:6.2f}  {p['pid']:<28} {p['label']:<8} [{p['verdict']}] '{p['name']}' {p['facts']} tags {p['tags']}")
        ML.emit("pass" if res else "warn", f"{len(res)} pieces", "write a script and run compose")
        return 0
    if argv[0] == "compose":
        script = json.load(open(argv[1], encoding="utf-8"))
        seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 0
        c, used = compose(script, seed=seed)
        name = script.get("name", "Composed")
        odir = os.path.join(OUT, name)
        if "--render" in argv:
            path, gif, rc = render(c, odir, name)
        else:
            os.makedirs(odir, exist_ok=True)
            path, gif = os.path.join(odir, f"{name}.clip.json"), None
            json.dump(c, open(path, "w", encoding="utf-8"))
        ML.emit("pass", f"composed {name}: {len(used)} pieces ({', '.join(x['name'] + ':' + x['label'] for x in c['composed_from'])}), {c['times'][-1]:.2f} s -> {path}" + (f", gif {gif}" if gif else ""),
                "look at the gif; change the words of a step to swap a piece")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")       # clip names carry emoji; a Windows console codec would crash
    sys.exit(main(sys.argv[1:]))
