"""direction_frames.py - the FRAMES of an animation's creative direction (the owner, 2026-10-24: decide the direction
before building; kit/direction.py --lane anim wants a real frame per option). Each option is a few CONCEPT key poses in
assets/animations/direction/poses/<Piece><Letter>.pose.json (the owner-rig pose format; never a game clip: kit anim
does not scan that folder) -> compiled on the owner's R6_IK rig (kit/anim/pose_r6.py), rendered three-quarter + game
camera (kit/anim/look_r6.py) -> assets/animations/direction/<Piece>_<Letter>.png: its first, middle and last key side
by side, the frame the direction doc points at.

    python kit/anim/direction_frames.py <Piece>
"""
import glob
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_KIT = os.path.abspath(os.path.join(_HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

BLENDER = find_blender() or "blender"
RIG = os.environ.get("PARALLAX_R6_RIG") or os.path.join("assets", "rigs", "R6_IK.blend")
DIR = os.path.join("assets", "animations", "direction")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def blender(args):
    if not os.path.isfile(BLENDER):
        return {"status": "fail", "summary": f"no Blender at {BLENDER} (set KIT_BLENDER)"}
    p = subprocess.run([BLENDER, "-b", RIG, "--disable-autoexec", "--python-exit-code", "2", "-P", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    last = [ln for ln in (p.stdout or "").splitlines() if ln.startswith("{") and '"status"' in ln]
    return json.loads(last[-1]) if last else {"status": "fail", "summary": (p.stderr or p.stdout)[-400:]}


def key_frames(pose):
    """the 1-based render frames of the first, middle and last key (the guard, the moment, the follow-through)"""
    fps = float(pose.get("fps", 60))
    fs = sorted(float(k["f"]) if "f" in k else float(k["t"]) * fps for k in pose["keys"])
    picks = [fs[0], fs[len(fs) // 2], fs[-1]] if len(fs) >= 3 else (fs + fs[-1:] * 3)[:3]
    return [int(round(f)) + 1 for f in picks]


def sheet(look_dir, frames, label, out):
    from PIL import Image, ImageDraw
    tiles = []
    for f in frames:
        pair = [Image.open(os.path.join(look_dir, f"{v}_{f:04d}.png")).convert("RGB") for v in ("three-quarter", "game")]
        w, h = pair[0].size
        t = Image.new("RGB", (w * 2, h))
        t.paste(pair[0], (0, 0))
        t.paste(pair[1], (w, 0))
        tiles.append(t)
    row = Image.new("RGB", (tiles[0].width * len(tiles), tiles[0].height + 28), (240, 241, 244))
    for i, t in enumerate(tiles):
        row.paste(t, (i * t.width, 28))
    ImageDraw.Draw(row).text((8, 8), f"{label}   (first key | the moment | last key; three-quarter + game camera)", fill=(20, 20, 24))
    row.save(out)


def main(argv):
    if not argv:
        return emit("fail", "direction frames: needs <Piece>", "lune run kit anim direction KatanaKaeshi --frames")
    piece = argv[0]
    if not re.match(r"^[A-Za-z0-9_-]+$", piece):
        return emit("fail", f"direction frames: name {piece!r}: letters, digits, _ and - only", "pick a plain name")
    poses = sorted(p for p in glob.glob(os.path.join(DIR, "poses", f"{piece}?.pose.json"))
                   if os.path.basename(p)[len(piece)].isupper())       # (Windows globs ignore case: A-Z only)
    if not poses:
        return emit("fail", f"direction frames {piece}: no concept poses in {DIR}/poses/{piece}<A|B|C>.pose.json",
                    "write 2-3 key poses per option there (the owner-rig pose format: right_arm hand / blade, body, feet)")
    work = os.path.join("_artifacts", "direction", piece)
    os.makedirs(work, exist_ok=True)
    made, problems = [], []
    for path in poses:
        letter = os.path.basename(path)[len(piece)]
        pose = json.load(open(path, encoding="utf-8"))
        clip = os.path.join(work, f"{piece}{letter}.clip.json")
        r = blender(["kit/anim/pose_r6.py", "--", path, "--out", clip, "--save", os.path.join(work, f"{piece}{letter}.r6.blend")])
        if r.get("status") != "pass":
            problems.append(f"{letter}: pose {r.get('summary', '')[:160]}")
            continue
        r = blender(["kit/anim/look_r6.py", "--", f"{piece}{letter}", "--clip", clip, "--out", work, "--views", "3", "--size", "360",
                       "--mark"])
        if r.get("status") != "pass":
            problems.append(f"{letter}: render {r.get('summary', '')[:160]}")
            continue
        out = os.path.join(DIR, f"{piece}_{letter}.png")
        try:
            sheet(os.path.join(work, f"{piece}{letter}.look"), key_frames(pose), f"{letter}  {pose.get('note', '')[:90]}", out)
        except (OSError, KeyError, ValueError) as e:
            problems.append(f"{letter}: sheet {e}")
            continue
        made.append(out.replace(os.sep, "/"))
    if problems:
        return emit("fail", f"direction frames {piece}: {len(made)} made, {len(problems)} failed - {problems[0]}",
                    "fix that option's concept poses (the pose note says which key)", made=made, problems=problems)
    return emit("pass", f"direction frames {piece}: {len(made)} frames on the owner's rig -> {', '.join(made)}",
                f"LOOK at them, then point each direction's Frame: line at its file; lune run kit anim direction {piece}",
                made=made)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
