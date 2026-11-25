"""judge.py — an animation judged by a FRESH reviewer (another session, another model), like `kit judge` for models:
    python kit/anim/judge.py packet <Name>                  build/judge/anim/<Name>/: strip.png, motion.png, PROMPT.md
    python kit/anim/judge.py record <Name> <verdict.json>   validate the reviewer's verdict and keep it (verdict.json)

The packet is everything a judge needs and nothing that steers them: the time strip (keys, arcs, beats, events), a
motion grid (every frame, front + side), the brief (what the clip is for, its beats and events) and the measured
motion line — then the rubric: the animation principles scored 1-10 each, and three LOCATED gaps (time + joint +
what is wrong), so the verdict is actionable. The score is the mean x 10 (0-100), the bar the owner sets.
"""

import json
import os
import shutil
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402
import strip as S  # noqa: E402

RUBRIC = [
    ("timing", "Timing and spacing: fast things fast, slow things slow; holds where they belong; nothing floats"),
    ("anticipation", "Anticipation: the wind-up reads and is longer than the action it prepares"),
    ("follow_through", "Follow-through and overlap: parts keep going past the impact and settle in order, not all at once"),
    ("arcs", "Arcs: hands and feet travel on curves, not straight lines or corners"),
    ("weight", "Weight and balance: the body stays over its feet; mass is felt in the strike and the recovery"),
    ("readability", "Readability: every key pose has a clear silhouette; the action reads in the first frame of it"),
    ("impact", "Impact: the Hit sits on the fastest, most extended frame; the pose at the Hit says 'hit'"),
    ("exaggeration", "Exaggeration: pushed where it sells the action, not uniform"),
    ("secondary", "Secondary motion: head, off-hand, torso respond to the main action instead of riding along stiff"),
    ("appeal", "Appeal: the poses look intended, not like a rig that was rotated"),
    ("loop", "Loop / settle: a loop is seamless; a one-shot settles without a pop into the next idle"),
    ("engine_fit", "Engine fit: nothing a Roblox avatar cannot do (no part interpenetration, no joint past its range)"),
]


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _paths(name):
    build = os.environ.get("KIT_BUILD", "build")
    folder = os.path.join(build, "judge", "anim", name)
    clip_path = os.path.join(build, "animations", f"{name}.clip.json")
    return build, folder, clip_path


def motion_grid(clip, rig, frames, cy, tracks, path, per_row=8, max_frames=32):
    """every frame (up to max_frames, evenly thinned), front over side, in rows: the motion itself, not just keys"""
    n = len(frames)
    idx = list(range(n)) if n <= max_frames else [round(i * (n - 1) / (max_frames - 1)) for i in range(max_frames)]
    cell = int(S.CELL * 0.75)
    rows = (len(idx) + per_row - 1) // per_row
    img = Image.new("RGB", (cell * per_row, (cell * 2 + 18) * rows), S.BG)
    draw = ImageDraw.Draw(img, "RGBA")
    scale_back = S.SCALE
    S.SCALE = int(S.SCALE * 0.75)
    try:
        for k, i in enumerate(idx):
            r, c = divmod(k, per_row)
            ox, oy = c * cell, r * (cell * 2 + 18)
            for v, view in enumerate(("front", "side")):
                # draw at full CELL geometry then the smaller scale keeps the figure inside the smaller cell
                S.draw_arcs(draw, ox - (S.CELL - cell) // 2, oy + v * cell - (S.CELL - cell) // 2, cy, tracks, view, i)
                S.draw_pose(draw, ox - (S.CELL - cell) // 2, oy + v * cell - (S.CELL - cell) // 2, cy, rig, frames[i], view)
            draw.text((ox + 4, oy + cell * 2 + 2), f"{i}  t={float(clip['times'][i]):.2f}s", fill=S.DIM)
            draw.line([ox, oy, ox, oy + cell * 2], fill=S.GRID)
    finally:
        S.SCALE = scale_back
    img.save(path)
    return len(idx)


def prompt_text(name, clip, m):
    beats = clip.get("beats") or {}
    events = clip.get("events") or []
    lines = [
        f"# Judge: animation `{name}`",
        "",
        "You are a senior game animator reviewing a Roblox character animation you have never seen. Nobody who made it",
        "is in the room. Look at BOTH pictures first — strip.png (the keys and events on a timeline, with the hands' and",
        "feet's arcs over the whole clip) and motion.png (every frame, front over side) — then read the numbers.",
        "",
        *([
            "## The medium (R6)",
            "- R6 limbs are RIGID 2-stud boxes: no elbows, no knees, no wrists. A bent arm or a chambered fist does not exist;",
            "  R6 animators fake a bend by SLIDING a limb (an arm pulled back along the body, a leg slid up for a knee). Judge",
            "  every pose by what an R6 character can do - never dock it for lacking an elbow or a knee.",
            "- R6 has NO WAIST: one Torso part is both the hips and the chest, so a hips-then-chest stagger cannot exist - the",
            "  drive is staged across torso -> arm -> head (and the legs pivot with the torso). Do not ask for a waist.",
            "- The head you see is a mesh about 1.25 studs a side (the part's box is wider); the face points along the head.",
            "",
        ] if clip.get("rig") == "R6" else []),
        "## The brief",
        f"- Clip: {name}, {clip.get('duration')} s at {clip.get('fps')} fps, priority {clip.get('priority')}, "
        f"{'looping' if clip.get('loop') else 'one-shot'}, rig {clip.get('rig')}.",
        f"- Source: {json.dumps(clip.get('source') or {})}",
        f"- Beats: " + (", ".join(f"{k} {v[0]}-{v[1]} s" for k, v in beats.items()) if beats else "(none declared)"),
        f"- Events: " + (", ".join(f"{e['name']} at {e['t']} s" for e in events) if events else "(none)"),
        f"- Feel: {json.dumps(clip.get('feel') or {})}",
        "",
        "## Measured motion (kit/anim/metrics.py)",
        f"- {C.summary(m)}",
    ]
    if m.get("phases"):
        p = m["phases"]
        lines.append(f"- Phases from the fastest hand: anticipation {p['anticipation_s']} s, action {p['action_s']} s, recovery {p['recovery_s']} s")
    lines.append("- Joint speeds RELATIVE TO THE PARENT (a head that holds still in the world while the torso turns shows the torso's speed here):")
    for jn, jm in sorted(m.get("joints", {}).items()):
        lines.append(f"  - {jn}: peak {jm['peak_deg_s']} deg/s at {jm['peak_t']} s, {jm['total_deg']} deg travelled" + (f", {len(jm['pops'])} pop(s)" if jm["pops"] else ""))
    lines.append("- Part speeds IN THE WORLD (what the eye sees):")
    for pn, (pk, pt, tot, rng) in sorted(world_speeds(clip).items()):
        lines.append(f"  - {pn}: peak {pk} deg/s at {pt} s; its widest pose is {rng} deg from the start pose "
                     f"({tot} deg travelled in all - out AND back, not one turn)")
    if m.get("problems"):
        lines.append("- Gate problems: " + " | ".join(m["problems"]))
    lines += [
        "",
        "## Score it (1-10 each; 10 = shippable in a top-tier action game, 5 = a competent placeholder, 1 = broken)",
    ]
    for key, text in RUBRIC:
        lines.append(f"- `{key}`: {text}")
    lines += [
        "",
        "Then name THREE located gaps: the time (s), the joint or body part, and what is wrong / what to do — the",
        "most damaging first. Be specific (\"0.30 s RightUpperArm: the strike decelerates before the Hit, so the hit",
        "lands on a slowing arm\"), never general (\"timing could be better\").",
        "",
        "## Answer with ONLY this JSON (save it, then: lune run kit anim judge " + name + " --record <file>)",
        "```json",
        json.dumps({"judge": "<model>@<harness>", "scores": {k: 0 for k, _ in RUBRIC}, "overall": 0,
                    "gaps": [{"t": 0.0, "joint": "", "what": ""}, {"t": 0.0, "joint": "", "what": ""}, {"t": 0.0, "joint": "", "what": ""}],
                    "verdict": "two sentences: what works, what does not"}, indent=1),
        "```",
    ]
    return "\n".join(lines) + "\n"


def packet(name):
    build, folder, clip_path = _paths(name)
    if not os.path.isfile(clip_path):
        return _out("fail", f"judge: no clip for {name}", f"lune run kit anim {name}")
    clip = C.load_clip(clip_path)
    rig = C.load_rig(clip["rig"])
    m = C.metrics(clip, rig)
    os.makedirs(folder, exist_ok=True)
    strip_src = os.path.join(build, "animations", f"{name}.png")
    if not os.path.isfile(strip_src):
        return _out("fail", f"judge: no strip for {name}", f"lune run kit anim {name}")
    shutil.copyfile(strip_src, os.path.join(folder, "strip.png"))
    frames = C.world_frames(clip, rig)
    cy = S.vertical_center(rig, frames)
    tracks = {e: [frames[i][e][:3, 3] for i in range(len(frames))] for e in C.EFFECTORS.get(rig["rig"], []) if e in rig["joints"] and "Head" not in e}
    shown = motion_grid(clip, rig, frames, cy, tracks, os.path.join(folder, "motion.png"))
    with open(os.path.join(folder, "PROMPT.md"), "w", encoding="utf-8") as fh:
        fh.write(prompt_text(name, clip, m))
    with open(os.path.join(folder, "packet.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": name, "clip": clip_path, "frames": shown, "metrics": {k: v for k, v in m.items() if k != "effectors"}}, fh, indent=1)
    return _out("pass", f"judge packet {folder}/: strip.png, motion.png ({shown} frames), PROMPT.md",
                f"hand build/judge/anim/{name}/PROMPT.md + the two pictures to a FRESH reviewer (another session or model); record its JSON with: lune run kit anim judge {name} --record <file>",
                folder=folder.replace(chr(92), "/"))


def world_speeds(clip):
    """each part's WORLD rotation speed (deg/s): peak, its time, total degrees"""
    import math as _m
    import numpy as _np
    try:
        rig = C.load_rig(str(clip.get("rig") or "R6").lower())
        frames = C.world_frames(clip, rig)
    except (ValueError, OSError, KeyError):
        return {}
    fps = float(clip.get("fps") or 30)
    out = {}
    for part in frames[0]:
        if part == "HumanoidRootPart":
            continue
        d = []
        for a, b in zip(frames, frames[1:]):
            r = a[part][:3, :3].T @ b[part][:3, :3]
            d.append(_m.degrees(_m.acos(max(-1.0, min(1.0, (float(_np.trace(r)) - 1) / 2)))))
        if d:
            k = int(_np.argmax(d))
            r0 = frames[0][part][:3, :3]
            rng = max(_m.degrees(_m.acos(max(-1.0, min(1.0, (float(_np.trace(r0.T @ f[part][:3, :3])) - 1) / 2)))) for f in frames)
            out[part] = (round(d[k] * fps, 1), round(float(clip["times"][k + 1]), 4), round(float(sum(d)), 1), round(rng, 1))
    return out


def record(name, verdict_path):
    build, folder, clip_path = _paths(name)
    if not os.path.isfile(verdict_path):
        return _out("fail", f"judge: no verdict file {verdict_path}", "save the reviewer's JSON answer to a file first")
    with open(verdict_path, encoding="utf-8") as fh:
        raw = fh.read().strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.index("{"):raw.rindex("}") + 1]
    try:
        v = json.loads(raw)
    except ValueError as e:
        return _out("fail", f"judge: the verdict is not JSON ({e})", "the reviewer must answer with the JSON block alone")
    scores = v.get("scores") or {}
    bad = [k for k, _ in RUBRIC if not isinstance(scores.get(k), (int, float)) or not 1 <= scores[k] <= 10]
    if bad:
        return _out("fail", f"judge: scores missing or out of 1-10: {', '.join(bad)}", "every rubric key needs a 1-10 score")
    gaps = v.get("gaps") or []
    located = [g for g in gaps if isinstance(g, dict) and isinstance(g.get("t"), (int, float)) and g.get("joint") and g.get("what")]
    if len(located) < 3:
        return _out("fail", f"judge: {len(located)} located gap(s), need 3 (t + joint + what)", "ask the reviewer for three located gaps")
    score = round(sum(scores[k] for k, _ in RUBRIC) / len(RUBRIC) * 10, 1)
    low = sorted(RUBRIC, key=lambda r: scores[r[0]])[:3]
    kept = {"name": name, "judge": v.get("judge", "?"), "score": score, "scores": scores, "gaps": located,
            "verdict": v.get("verdict", ""), "clip": clip_path}
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "verdict.json"), "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=1)
    lows = ", ".join(f"{k} {scores[k]}" for k, _ in low)
    g = located[0]
    return _out("pass", f"{name} judged {score}/100 by {kept['judge']} (lowest: {lows}); first gap: {g['t']} s {g['joint']}: {g['what']}",
                f"improve {low[0][0]} first — {g['t']} s {g['joint']}: {g['what']}", score=score, verdict=os.path.join(folder, "verdict.json").replace(chr(92), "/"))


def main(argv):
    if len(argv) < 2:
        return _out("fail", "judge: packet <Name> | record <Name> <verdict.json>", "python kit/anim/judge.py packet Slash")
    if argv[0] == "packet":
        return packet(argv[1])
    if argv[0] == "record" and len(argv) >= 3:
        return record(argv[1], argv[2])
    return _out("fail", f"judge: unknown mode {argv[0]}", "packet <Name> | record <Name> <verdict.json>")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
