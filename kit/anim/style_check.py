"""style_check.py - a game's ANIMATION STYLE GUIDE checked on its sets (board nmtn + wuef + d2en; AAA gaps v2 A6, C1, C2;
board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md). Pros lock one bible per game; a move that breaks it is caught here:
  guard     the set's OPENER starts in the game's guard pose (every joint within tol_deg)
  link      each cut starts on the pose the cut before it ENDED in (within link_tol_deg) - a combo that flows in game,
            not only in a chained preview (C2: link poses)
  startup   clip start -> its first Hit within the budget of its feel tier (C1: responsiveness - a combo cut starts
            where the last one cancelled, so its Hit time IS its in-game startup)
  return    how far each cut's last pose is from the guard (reported: the recovery a game needs if the combo stops there)
The style lives with the game: games/<Game>/anim_style.json (anim lane only - departments stay separate).

    python kit/anim/style_check.py <Set> [--game SampleDojo] [--build build]
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def pose(clip, i):
    return {j: np.array(C.quat_mat(v["frames"][i][:4])) for j, v in clip["joints"].items() if v.get("frames")}


def angle(A, B):
    return float(np.degrees(np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1.0, 1.0))))


def worst(a, b):
    """the joint furthest apart between two poses -> (degrees, joint)"""
    best = (0.0, None)
    for j in a:
        if j in b:
            d = angle(a[j], b[j])
            if d > best[0]:
                best = (d, j)
    return best


def check(style, set_name, build="build"):
    names = style["sets"].get(set_name)
    if not names:
        raise KeyError(f"no set {set_name} in the style ({', '.join(style['sets'])})")
    load = lambda n: json.load(open(os.path.join(build, "animations", f"{n}.clip.json"), encoding="utf-8"))  # noqa: E731
    g = style["guard"]
    guard = pose(load(g["clip"]), g.get("frame", 0))
    rows, problems = [], []
    prev = None
    moves_by_anim = {}
    mdir = os.path.join("games", style.get("game", "SampleDojo"), "assets", "moves")
    if os.path.isdir(mdir):
        for fn in os.listdir(mdir):
            if fn.endswith(".json"):
                try:
                    mv = json.load(open(os.path.join(mdir, fn), encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(mv, dict) and mv.get("anim"):
                    moves_by_anim[mv["anim"]] = mv
    for k, n in enumerate(names):
        c = load(n)
        start, end = pose(c, 0), pose(c, -1)
        row = {"move": n}
        if k == 0:
            d, j = worst(guard, start)
            row["guard_deg"] = round(d, 1)
            if d > g.get("tol_deg", 10):
                problems.append(f"{n} opens {d:.0f} deg off the guard pose ({j})")
        if prev is not None:
            d, j = worst(prev[1], start)
            row["link_deg"] = round(d, 1)
            if d > style.get("link_tol_deg", 3):
                problems.append(f"{n} does not start where {prev[0]} ended: {d:.0f} deg ({j})")
        hits = [e["t"] for e in c.get("events") or [] if e.get("name") == "Hit"]
        tier = (c.get("feel") or {}).get("tier", "medium")
        budget = style.get("startup_s", {}).get(tier)
        if hits and budget is not None:
            row["startup_s"], row["tier"], row["budget_s"] = round(hits[0], 3), tier, budget
            if hits[0] > budget + 1e-6:
                problems.append(f"{n} ({tier}) hits at {hits[0]:.2f} s, over the {tier} budget {budget} s")
        row["return_deg"] = round(worst(guard, end)[0], 1)
        # C2: a player who cancels at the EARLIEST frame starts the next cut from THIS pose, not the end pose - the
        # seam he sees (games/<Game>/assets/moves: the move that plays this clip, its cancel `from` frame)
        mv = moves_by_anim.get(n)
        if mv and isinstance(mv.get("cancel"), dict) and k + 1 < len(names):
            f = int(mv["cancel"].get("from", 0))
            fps_c = round(1.0 / (c["times"][1] - c["times"][0]))
            fr = mv.get("frames")
            mfps = float(fr.get("fps", 60)) if isinstance(fr, dict) else 60.0   # "from_anim": the kit move default
            i = min(len(c["times"]) - 1, int(round(f / mfps * fps_c)))
            row["cancel_pose"] = pose(c, i)
        if prev is not None and prev[2] is not None:
            d, j = worst(prev[2], start)
            row["cancel_link_deg"] = round(d, 1)
            if d > style.get("cancel_tol_deg", 60):
                problems.append(f"{n} starts {d:.0f} deg from {prev[0]}'s earliest cancel pose ({j}) - an early cancel snaps")
        cancel_pose = row.pop("cancel_pose", None)
        rows.append(row)
        prev = (n, end, cancel_pose)
    return rows, problems


def main(argv):
    if not argv:
        return emit("fail", "style: needs <Set>", "lune run kit anim style KatanaSet")
    set_name = argv[0]
    game = argv[argv.index("--game") + 1] if "--game" in argv else "SampleDojo"
    build = argv[argv.index("--build") + 1] if "--build" in argv else os.environ.get("KIT_BUILD", "build")
    path = os.path.join("games", game, "anim_style.json")
    if not os.path.isfile(path):
        return emit("fail", f"style: no {path}", f"write the game's animation style guide: {path} (guard, link_tol_deg, startup_s, sets)")
    style = json.load(open(path, encoding="utf-8"))
    try:
        rows, problems = check(style, set_name, build)
    except (KeyError, FileNotFoundError) as exc:
        return emit("fail", f"style {set_name}: {exc}", "build the set's clips first: lune run kit anim <Name>")
    tag = " (the style is a PROPOSAL until the owner approves it)" if style.get("status") == "proposal" else ""
    if problems:
        return emit("fail", f"style {set_name}: {len(problems)} break(s) of {path}{tag}: {problems[0]}",
                    "fix the move (or, if the owner says the style is wrong, the style file)", rows=rows, problems=problems)
    return emit("pass", f"style {set_name}: {len(rows)} moves keep {path}{tag} - opener on guard, every cut linked, startups in budget",
                "none - proceed", rows=rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
