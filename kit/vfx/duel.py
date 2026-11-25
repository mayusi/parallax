"""duel.py — G2, the 2-fighter scene (LIMITATIONS_FIXES_V4 3.4 step 1 / 11 Phase 2: "the 24-stud 2-fighter arena" the
browser player is calibrated in across the four judging skies), CHECKED: the scene file both renderers build from
(kit/vfx/scenes/<name>.json: the browser player, kit/vfx/player/player.js, and the Studio booth, kit/vfx/booth.luau)
is held to what makes it that scene, and a preset that plays in it is held to the scene's anchors.

    python kit/vfx/duel.py check [<scene name> | <path.json>]     (default g2)
    python kit/vfx/duel.py preset <preset.json>                   a preset's booth.scene + its "@victim*" anchors

What a 2-fighter scene must be (each fault is named):
  - the arena 24 studs square (the doc's number), its floor at y = 0, a curb under 2 studs (a camera sees over it)
  - exactly two R6 fighters, an attacker and a victim; the attacker ON the effect's origin facing -Z (the booth's actor
    stands there: every preset's points are measured from it)
  - both whole inside the arena (an R6 is 4 studs across the arms, 1 deep, 5 tall), apart (their bodies do not meet)
    and face to face (each faces the other within 10 degrees)
  - the victim within the attacker's REACH: its front within 7.45 studs of the attacker's shoulder (the stand-in's
    blade tip, 2.75 + 4.6 + 0.1 from the shoulder pivot: player.js buildActor) - a strike that cannot land is no duel
  - every anchor named victim* on or at the victim's body (within 0.6 studs of its box)
  - every view (and every key of a moving one) sees BOTH fighters whole inside 90 % of a 16:9 frame, from in front
    of them, the camera above the floor and outside both bodies
Prints one JSON line {schema, status, summary, next_action, faults}.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENES = os.path.join(HERE, "scenes")

ARENA = 24.0            # studs (the doc: "G2 24-stud 2-fighter Studio arena")
R6 = (4.0, 5.0, 1.0)    # width across the arms, height, depth (studs)
REACH = 7.45            # the stand-in's blade tip from its shoulder pivot (player.js buildActor: 2.75 + 2.3 + 2.3 + 0.1)
SHOULDER = 3.9          # the stand-in's arm pivot height
FACE_COS = math.cos(math.radians(10))
FRAME = 0.9             # the share of the frame a fighter must stay inside
ASPECT = 16 / 9
NEAR = 0.3              # the player's camera near plane
ANCHOR_SLACK = 0.6


def load(ref="g2"):
    path = ref if ref.endswith(".json") else os.path.join(SCENES, f"{ref}.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh), path


def _v(x):
    return isinstance(x, list) and len(x) == 3 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in x)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-9 else None


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def body(f):
    """an R6 fighter's box: (centre, right axis, forward axis) on the floor plane, and its 8 corners"""
    fwd = _norm([f["face"][0], 0.0, f["face"][2]]) or [0.0, 0.0, -1.0]
    right = [-fwd[2], 0.0, fwd[0]]
    w, h, d = R6
    p = f["pos"]
    corners = []
    for sx in (-0.5, 0.5):
        for sz in (-0.5, 0.5):
            for y in (0.0, h):
                corners.append([p[0] + right[0] * sx * w + fwd[0] * sz * d, p[1] + y, p[2] + right[2] * sx * w + fwd[2] * sz * d])
    return fwd, right, corners


def inside_body(f, q, slack=0.0):
    fwd, right, _ = body(f)
    r = _sub(q, f["pos"])
    w, h, d = R6
    return abs(_dot(r, right)) <= w / 2 + slack and abs(_dot(r, fwd)) <= d / 2 + slack and -slack <= r[1] <= h + slack


def project(view, q, aspect=ASPECT):
    """a point through a view's camera -> (ndc x, ndc y, depth) - the player's camera: look-at, vertical fov"""
    pos, look = view["pos"], view["look"]
    fwd = _norm(_sub(look, pos))
    right = _norm(_cross(fwd, [0.0, 1.0, 0.0])) or [1.0, 0.0, 0.0]
    up = _cross(right, fwd)
    r = _sub(q, pos)
    z = _dot(r, fwd)
    if z <= 1e-6:
        return None, None, z
    t = math.tan(math.radians(view.get("fov", 70)) / 2)
    return _dot(r, right) / (z * t * aspect), _dot(r, up) / (z * t), z


def view_keys(name, v):
    if isinstance(v, dict) and isinstance(v.get("path"), list):
        return [(f"{name}@{k.get('t', i)}", k) for i, k in enumerate(v["path"])]
    return [(name, v)]


def check(scene):
    faults = []
    arena = scene.get("arena") or {}
    size = arena.get("size")
    if size != ARENA:
        faults.append(f"arena: {size} studs - the 2-fighter arena is {ARENA:g} studs square")
    c = arena.get("center")
    if not _v(c) or c[1] != 0:
        faults.append("arena: centre is [x, 0, z] (the floor at y = 0)")
        c = [0.0, 0.0, 0.0]
    curb = (arena.get("curb") or {}).get("height", 0)
    if not isinstance(curb, (int, float)) or curb < 0 or curb >= 2:
        faults.append(f"arena: curb {curb} studs - under 2 (a camera sees over it)")
    fs = scene.get("fighters")
    if not isinstance(fs, list) or len(fs) != 2:
        faults.append(f"fighters: {len(fs) if isinstance(fs, list) else 0} - a 2-fighter scene has exactly two")
        return faults
    for i, f in enumerate(fs):
        if not isinstance(f, dict) or not _v(f.get("pos")) or not _v(f.get("face")):
            faults.append(f"fighters[{i}]: pos and face are [x, y, z]")
            return faults
        if f.get("rig") != "R6":
            faults.append(f"fighters[{i}]: rig {f.get('rig')!r} - the kit's fighters are R6")
        if f["pos"][1] != 0:
            faults.append(f"fighters[{i}] ({f.get('role')}): stands at y {f['pos'][1]} - on the floor (y 0)")
    roles = sorted(str(f.get("role")) for f in fs)
    if roles != ["attacker", "victim"]:
        faults.append(f"fighters: roles {roles} - one attacker and one victim")
        return faults
    att = next(f for f in fs if f["role"] == "attacker")
    vic = next(f for f in fs if f["role"] == "victim")
    if att["pos"] != [0, 0, 0] or (_norm([att["face"][0], 0, att["face"][2]]) or [0, 0, 0])[2] > -0.999:
        faults.append("attacker: stands on the effect's origin [0, 0, 0] facing -Z (the booth's actor; presets measure from it)")
    half = size / 2 - (arena.get("curb") or {}).get("width", 0) if isinstance(size, (int, float)) else 0
    for f in fs:
        _, _, corners = body(f)
        out = max(max(abs(q[0] - c[0]), abs(q[2] - c[2])) for q in corners)
        if out > half + 1e-6:
            faults.append(f"{f['role']}: reaches {out:.2f} studs from the arena's centre - not whole inside its {half:g}-stud half (curb taken off)")
    d = _sub(vic["pos"], att["pos"])
    dist = math.hypot(d[0], d[2])
    to_v, to_a = _norm([d[0], 0, d[2]]), _norm([-d[0], 0, -d[2]])
    if to_v is None:
        faults.append("fighters: both stand on one spot")
        return faults
    if _dot(body(att)[0], to_v) < FACE_COS:
        faults.append("attacker: does not face the victim (more than 10 degrees off)")
    if _dot(body(vic)[0], to_a) < FACE_COS:
        faults.append("victim: does not face the attacker (more than 10 degrees off)")
    if dist < R6[2] + 0.5:
        faults.append(f"fighters: {dist:.2f} studs apart - their bodies meet")
    front = dist - R6[2] / 2  # the blade sweeps a vertical arc: at shoulder height it reaches REACH straight ahead
    if front > REACH:
        faults.append(f"victim: its front is {front:.2f} studs from the attacker - out of the strike's reach ({REACH} studs)")
    for k, a in (scene.get("anchors") or {}).items():
        if not _v(a):
            faults.append(f"anchors.{k}: [x, y, z]")
        elif k.startswith("victim") and not inside_body(vic, a, ANCHOR_SLACK):
            faults.append(f"anchors.{k}: {a} is not on the victim's body")
    views = scene.get("views") or {}
    if not views:
        faults.append("views: none - the scene names the cameras that see both fighters")
    for name, v in views.items():
        for label, key in view_keys(name, v):
            if not (isinstance(key, dict) and _v(key.get("pos")) and _v(key.get("look"))):
                faults.append(f"views.{label}: pos and look are [x, y, z]")
                continue
            if key["pos"][1] <= 0.2:
                faults.append(f"views.{label}: the camera is under the floor")
            for f in fs:
                if inside_body(f, key["pos"], 0.3):
                    faults.append(f"views.{label}: the camera is inside the {f['role']}")
                    break
                worst = 0.0
                for q in body(f)[2]:
                    x, y, z = project(key, q)
                    if x is None or z < NEAR:
                        worst = float("inf")
                        break
                    worst = max(worst, abs(x), abs(y))
                if worst > FRAME:
                    faults.append(f"views.{label}: the {f['role']} is not whole in the frame ({'behind the camera' if worst == float('inf') else f'reaches {worst:.2f} of the half-frame, over {FRAME}'})")
    return faults


def check_preset(preset):
    """a preset that plays in a scene: booth.scene names one that passes; every "@victim*" anchor it uses is the scene's"""
    faults = []
    scene_name = (preset.get("booth") or {}).get("scene")
    used = set()

    def walk(x):
        if isinstance(x, str) and x.startswith("@victim"):
            used.add(x[1:].split("^")[0])
        elif isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            for y in x.values():
                walk(y)

    walk(preset.get("layers") or [])
    if scene_name in (None, "bare"):
        if used:
            faults.append(f"booth.scene: {scene_name!r} - its layers use {sorted(used)}, the 2-fighter scene's anchors (booth.scene \"g2\")")
        return faults
    if not isinstance(scene_name, str) or not os.path.isfile(os.path.join(SCENES, f"{scene_name}.json")):
        return [f"booth.scene: {scene_name!r} - no scene kit/vfx/scenes/{scene_name}.json (\"bare\" or a scene file)"]
    scene, _ = load(scene_name)
    faults += [f"scene {scene_name}: {x}" for x in check(scene)]
    for a in sorted(used):
        if a not in (scene.get("anchors") or {}):
            faults.append(f"@{a}: not an anchor of scene {scene_name} ({', '.join(sorted(scene.get('anchors') or {}))})")
    return faults


def say(status, summary, nxt, faults):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt, "faults": faults}))
    return 0 if status == "pass" else 1


def main(argv):
    if not argv or argv[0] not in ("check", "preset"):
        print(__doc__)
        return 2
    if argv[0] == "check":
        ref = argv[1] if len(argv) > 1 else "g2"
        try:
            scene, path = load(ref)
        except (OSError, ValueError) as e:
            return say("fail", f"duel: scene {ref}: {e}", "kit/vfx/scenes/<name>.json", [str(e)])
        faults = check(scene)
        if faults:
            return say("fail", f"duel: {os.path.basename(path)} - {len(faults)} fault(s): {faults[0]}", "fix the scene file (kit/vfx/scenes/)", faults)
        return say("pass", f"duel: {os.path.basename(path)} - a {ARENA:g}-stud arena, two R6 fighters face to face in reach, every view sees both whole",
                   "none", [])
    if len(argv) < 2:
        print(__doc__)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            preset = json.load(fh)
    except (OSError, ValueError) as e:
        return say("fail", f"duel: preset {argv[1]}: {e}", "a preset JSON", [str(e)])
    faults = check_preset(preset)
    if faults:
        return say("fail", f"duel: {os.path.basename(argv[1])} - {len(faults)} fault(s): {faults[0]}", "booth.scene \"g2\" and the scene's anchors", faults)
    return say("pass", f"duel: {os.path.basename(argv[1])} - plays in scene {(preset.get('booth') or {}).get('scene')!r}, its anchors are the scene's", "none", [])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
