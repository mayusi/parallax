"""moveset.py — a MOVESET as one thing: every move derived from loved curves, checked as a SET (do the combos chain?
is the tempo consistent? does every move start and end in the guard?), drawn on one contact sheet, and put on the
owner's rig as editable keys.

    python kit/anim/moveset.py assets/animations/movesets/<Set>.json [--sheet <png>] [--no-rig]

The set file:
    {"name": "Brawler", "guard": {"clip": "RefBwIdle", "frame": 0},
     "moves": {"BrawlerIdle": {"from": "RefBwIdle", "loop": true, "ops": [...]},
               "BrawlerM1": {"from": "RefBwA1", "ops": [{"op": "chain", ...}]}, ...},
     "chains": [["BrawlerM1", "BrawlerM2", "BrawlerM3", "BrawlerM4"]],
     "reduce": 2}
Why (2026-10-11): single good clips are not a moveset. A player sees moves back to back: a hit that ends where the
next one cannot start POPS, a set whose hits have different tempos reads as made by different hands, and an idle
that holds dead still between hits reads as a mannequin. So the set is checked as a set:
- CHAIN SEAMS: each move's last frame vs the next move's first (degrees, worst joint); and the GUARD: a chain's
  first move starts there, its last move ends there, a standalone action does both. Over 8 deg is a pop. Inside a
  chain a hit hands off to the next hit (the pack's own design); if the player stops mid-combo the runtime's fade to
  the idle covers it, so a mid-chain end is reported, not failed
- TEMPO: each action's startup / active / recovery (the fastest limb), the strike's peak speed and snap
- SNAPS (kit/anim/snaps.py) per move: on attacks a strike IS fast - this reports, it does not fix
Each move's recipe is written to assets/animations/<Move>.derive.json (the editable source), derived to
build/animations/<Move>.src.clip.json and put on the owner's rig as reduced keys: assets/animations/<Move>.pose.json
(`kit anim <Move>` then bakes it off the rig)."""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import book as BK  # noqa: E402
import derive as D  # noqa: E402
import keyreduce as KR  # noqa: E402
import pose_from as PF  # noqa: E402
import snaps as SN  # noqa: E402

SEAM_DEG = 8.0


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def pose_dist(a, b):
    """the worst joint's difference between two frames {joint: frame} (degrees + studs x 30)"""
    worst = 0.0
    for j in a:
        if j in b:
            fa, fb = np.asarray(a[j], float), np.asarray(b[j], float)
            worst = max(worst, KR.qang(fa[:4], fb[:4]) + 30 * float(np.linalg.norm(fa[4:7] - fb[4:7])))
    return worst


def frame(clip, i):
    return {j: d["frames"][i] for j, d in clip["joints"].items()}


def strike_frame(clip):
    fps = float(clip.get("fps") or 30)
    best, at = -1.0, 0
    for j in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        if j in clip["joints"]:
            s = SN.speeds(clip["joints"][j]["frames"], fps, bool(clip.get("loop")))
            if s.max() > best:
                best, at = float(s.max()), int(np.argmax(s))
    return at


def sheet(clips, out):
    """one row per move: start, anticipation, strike, follow-through, end (side view silhouettes)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import clip as C
    import silhouette as SI
    rig = C.load_rig("r6")
    names = list(clips)
    cols = ["start", "anticipation", "strike", "follow-through", "end"]
    fig, axes = plt.subplots(len(names), len(cols), figsize=(1.5 * len(cols), 1.6 * len(names)), squeeze=False)
    for r, name in enumerate(names):
        c = clips[name]
        frames = C.world_frames(c, rig)
        n = len(frames)
        s = strike_frame(c)
        picks = [0, max(0, s - max(2, n // 10)), s, min(n - 1, s + max(3, n // 8)), n - 1]
        floor = min(min(C.lowest(rig, p, f[p]) for p in ("Right Leg", "Left Leg") if p in f) for f in frames)
        for k, i in enumerate(picks):
            ax = axes[r][k]
            SI.draw_pose(ax, rig, frames[i], "side", floor)
            ax.set_title(f"{cols[k]} {i}", fontsize=6, pad=1)
            ax.set_aspect("equal")
            ax.set_xlim(-4.2, 4.2)
            ax.set_ylim(-3.8, 3.2)
            ax.set_xticks([])
            ax.set_yticks([])
        axes[r][0].set_ylabel(name, fontsize=7)
    fig.subplots_adjust(left=0.06, right=0.995, top=0.97, bottom=0.01, wspace=0.03, hspace=0.25)
    fig.savefig(out, dpi=100)
    plt.close(fig)


def main(argv):
    if not argv:
        return emit("fail", "moveset: needs assets/animations/movesets/<Set>.json", "lune run kit anim moveset <Set>")
    with open(argv[0], encoding="utf-8") as fh:
        ms = json.load(fh)
    build = os.environ.get("KIT_BUILD", "build")
    anims = os.path.join("assets", "animations")
    guard = ms.get("guard")
    clips, report, problems = {}, {}, []
    chains = ms.get("chains") or []
    must_start = {ch[0] for ch in chains}
    must_end = {ch[-1] for ch in chains}
    in_chain = {m for ch in chains for m in ch}
    authored = set()
    for name, recipe in ms["moves"].items():
        if recipe.get("authored"):
            # an AUTHORED move: its source is assets/animations/<name>.pose.json (kit anim <name> bakes it); the set
            # only checks the built clip - nothing is derived or rewritten
            c = D.load_clip(name)
            authored.add(name)
        else:
            recipe = dict(recipe, name=name)
            with open(os.path.join(anims, f"{name}.derive.json"), "w", encoding="utf-8", newline="") as fh:
                json.dump(recipe, fh, indent=1)
                fh.write(chr(10))
            c, log = D.derive(recipe)
        if name not in authored:
            out = os.path.join(build, "animations", f"{name}.src.clip.json")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(c, fh, indent=1)
        clips[name] = c
        m = BK.measure(c)
        r = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in m.items()
             if k in ("kind", "duration_s", "startup_s", "active_s", "recovery_s", "peak speed", "snap", "holds", "snaps/s", "torso turn range")}
        if guard and not c.get("loop"):
            g = frame(D.load_clip(guard["clip"]), int(guard.get("frame", 0)))
            r["start vs guard"] = round(pose_dist(frame(c, 0), g), 1)
            r["end vs guard"] = round(pose_dist(frame(c, -1), g), 1)
            need = []
            if name in (ms.get("experiments") or []):
                pass                                      # an experiment (a judged variant), not a move of the set
            elif name not in in_chain or name in must_start:
                need.append("start vs guard")
            if name not in (ms.get("experiments") or []) and (name not in in_chain or name in must_end):
                need.append("end vs guard")
            for k in need:
                if r[k] > SEAM_DEG:
                    problems.append(f"{name} {k} {r[k]} deg (pops: add / raise a chain op)")
        if c.get("loop"):
            r["loop seam"] = round(pose_dist(frame(c, 0), frame(c, -1)), 1)
            if r["loop seam"] > SEAM_DEG:
                problems.append(f"{name} loop seam {r['loop seam']} deg")
        for w in c.get("compose_warn") or []:
            problems.append(f"{name}: {w}")
        report[name] = r
    seams = []
    for chain in ms.get("chains") or []:
        for a, b in zip(chain, chain[1:]):
            d = round(pose_dist(frame(clips[a], -1), frame(clips[b], 0)), 1)
            seams.append({"from": a, "to": b, "deg": d})
            if d > SEAM_DEG:
                problems.append(f"chain {a} -> {b} pops ({d} deg)")
    previews = []
    for k, chain in enumerate(chains, 1):
        # the chain as the player sees it: each move after the other (the derived clips, back to back)
        pname = f"{ms['name']}Chain{k}"
        pc = D.copy.deepcopy(clips[chain[0]])
        for m in chain[1:]:
            D.op_concat(pc, clips[m])
        pc["name"] = pname
        with open(os.path.join(build, "animations", f"{pname}.src.clip.json"), "w", encoding="utf-8") as fh:
            json.dump(pc, fh, indent=1)
        previews.append((pname, pc))
    sheet_path = argv[argv.index("--sheet") + 1] if "--sheet" in argv else os.path.join(build, "animations", f"{ms['name']}.moveset.png")
    sheet(clips, sheet_path)
    rigged = []
    if "--no-rig" not in argv:
        for name, c in [(n, c) for n, c in clips.items() if n not in authored] + previews:
            spec = PF.pose_from(c, name, 1, ms.get("reduce", 2))
            with open(os.path.join(anims, f"{name}.pose.json"), "w", encoding="utf-8", newline="") as fh:
                json.dump(spec, fh, indent=1)
                fh.write(chr(10))
            rigged.append(name)
    tempo = "; ".join(f"{n} {r.get('startup_s', '-')}/{r.get('active_s', '-')}/{r.get('recovery_s', '-')} s" for n, r in report.items() if r.get("kind") == "action")
    with open(os.path.join(build, "animations", f"{ms['name']}.moveset.json"), "w", encoding="utf-8") as fh:
        json.dump({"moves": report, "seams": seams, "problems": problems}, fh, indent=1)
    status = "pass" if not problems else "fail"
    return emit(status, f"moveset {ms['name']}: {len(clips)} moves; chain seams " + ", ".join(f"{s['from']}->{s['to']} {s['deg']}" for s in seams)
                + (f"; tempo (startup/active/recovery) {tempo}" if tempo else "") + f"; sheet {sheet_path}"
                + (f"; PROBLEMS: {'; '.join(problems)}" if problems else ""),
                ("LOOK at the sheet, then build each move on the rig: " + " && ".join(f"lune run kit anim {n}" for n in rigged[:3]) + (" ..." if len(rigged) > 3 else ""))
                if not problems else "fix the recipes (chain ops / holds), then run the moveset again",
                moves=report, seams=seams, problems=problems)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
