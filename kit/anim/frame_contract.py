"""frame_contract.py — ONE FRAME CONVENTION, PROVEN (the owner's older list, AN-03: "a canonical contract and
calibration fixtures for handedness, forward axes, units and pivots ... deliberate mirror / axis / unit mistakes
fail before baking; every route reproduces the same calibration motion").

THE CONTRACT (what every route of the kit must agree on):
  SPACE     the character's own: +X is its RIGHT, +Y is UP, -Z is AHEAD; studs; the origin is the Torso's centre at
            rest (the R6: Torso 2 x 2 x 1, arms and legs 1 x 2 x 1, Head 2 x 1 x 1)
  A FRAME   [qx, qy, qz, qw, px, py, pz] for a joint: the turn and the slide of the part AT ITS JOINT, in the
            axes of the part it hangs from (the Torso's for a limb or the head, the character's for the Torso) -
            not the joint's own: the kit turns it into Motor6D.Transform with the joint's C0
  A TURN    right-handed: a positive turn about +X lifts a hanging arm AHEAD; about +Y turns the face to the LEFT;
            about +Z lifts the RIGHT arm out to the side (a negative one lifts the LEFT arm out to its side)
  PIVOTS    a limb turns about its joint (shoulder, hip, neck), not its centre

THE CALIBRATION MOTION: six poses, one a frame, whose places can be said by hand:
  0  rest
  1  the right arm lifted 90 degrees ahead          its end: (1.5, 0.5, -1.5)
  2  the left arm lifted 90 degrees out to the left its end: (-2.5, 1.0, 0)
  3  the head turned 90 degrees to the left         its face: (-0.5, 1.5, 0)
  4  the body 1 stud up, the right leg 45 degrees ahead   its sole: (0.5, -sqrt(2), -sqrt(2))
  5  the body turned 90 degrees to the left AND slid 1 stud ahead, the left leg 45 degrees ahead of the turned
     body, the head tipped 45 degrees back - a turn of the parent, a slide with a turn, two turns in a row, the left
     leg (the one review: without it a route that ignored the parent's turn, slid in the turned axes or turned the
     left leg the wrong way passed)
`EXPECTED` holds those places (written by hand from the block sizes, NOT computed by the kit's own code).

    python kit/anim/frame_contract.py                 the Python route (kit/anim/clip.py fk) against the contract
    python kit/anim/frame_contract.py write <file>    the calibration clip and the expected places, as JSON (for the
                                                      Luau routes' spec and for Studio)
    python kit/anim/frame_contract.py check <points.json>   places read off another route (Studio) against it

THE WEAPON'S OWN JOINT (the Handle joint under the Right Arm: kit/anim/grip.py, src/kit/AnimGrip.luau): the weapon's
frame has its origin at the grip, +Y along the blade to the tip; the joint's Transform is in the frame of Roblox's
RightGrip (1 stud down the arm, turned so its +Y points AHEAD and its +Z up the arm). The calibration carries a
`grip` track: at rest a 3-stud blade points straight ahead from the hand, its edge to the body's left - grip
(1.5, -1, 0), tip (1.5, -1, -3). In poses 1 and 3 the Transform slides it 1 along the grip frame's Y and turns it a
quarter about Z: with the arm at rest (pose 3) the blade points to the body's LEFT, a stud ahead - grip
(1.5, -1, -1), tip (-1.5, -1, -1); with the arm lifted ahead (pose 1) the same Transform rides the arm - grip
(1.5, 1.5, -1.5), tip (-1.5, 1.5, -1.5). The EDGE is checked too (a point a stud off the grip on the edge's side):
a blade rolled about its own length, or a mirrored weapon, is a different weapon. By hand (`WEAPON_EXPECTED`).

THE WRONG COPIES (`wrong()`): left-handed turns, the right on -X, the up and ahead axes swapped, ahead on +Z,
slides in metres, half turns. Each must FAIL the check - a check that passes them proves nothing.
THE ENGINE'S OWN NUMBERS (`ENGINE_POSES`): what Motor6D.Transform must hold for three of the poses, written from
Roblox's R6 joints (the Right Shoulder's own Z points along the character's X; the RootJoint's own Z points up) and
read back in Studio. The Python and Luau routes share one rig file, and a rig's C0 turn cancels out of a place
(c0 . T . c0^T): a wrong rig would pass every place and fail these.
WHERE IT RUNS: the test suite (kit test, pytest) - not each build: a route is held when its code changes.
ROUTES HELD TO IT: kit/anim/clip.py (this file's own command, kit/test/python/test_anim_frame_contract.py);
kit/lib/anim.luau modelFromClip -> the KeyframeSequence's Poses, and kit/anim/kfs_import.py back (the same test and
kit/test/spec/animframes.spec.luau); the derive recipe's mirror; the R15 -> R6 fold; the engine itself (Studio: the
sequence played on a rig, the parts read - see the audit page);
the export out of Roblox (kit/anim/export_clip.py: the .glb's nodes, read by the glTF layout alone); the IMPORT
into the kit (kit/anim/retarget.py, in Blender): see THE IMPORT ROUTE below.

THE IMPORT ROUTE (`python kit/anim/frame_contract.py import`): a small skeleton with a known family's bone names,
in Blender's own axes (Z up, facing -Y), five poses (kit/anim/import_calibration_blend.py), exported as a .glb and
brought in by retarget.py as a mover would bring a mocap. Its R15 clip must turn each part as said by hand, in
ROBLOX's axes - the R15's own rest direction, turned:
  pose 1  the right arm 90 degrees about +X (hanging -> ahead)
  pose 2  the left arm 90 degrees about -Z (hanging -> out to its LEFT, -X)
  pose 3  the face 90 degrees about +Y (looking ahead -> looking left, -X)
  pose 4  the right leg 45 degrees about +X (ahead), the pelvis up 0.2 of the source's height (in the R15's)
within IMPORT_TOL degrees and 0.01 studs - EVERY part's whole turn (all three axes: a twist about an arm's own
line, a head rolled about its look, a leg that should hang are wrong too), every pose. Must PASS: in centimetres,
turned to face another way in its file, standing toe-out (12 degrees), T-posed with the route's own "auto" arms
(a T-posed body at rest IS arms out: there the arms are held to point out to its sides, then ahead, within 17.5
degrees - the R15's own slant - and the legs, the look and the rise as above). Must FAIL: its left and right labels
swapped - and the route must SAY its hands and toes disagree.
NOT HELD TO IT: a left-hand weapon (`grip_left`); the Blender routes (kit/anim/export_clip.py, retarget.py, the look renders) - they need the owner's
rig file open in Blender; kit/anim/rig_model_check.py checks that rig against the kit's model on 300 random poses."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

TOL = 0.01           # studs
R2 = math.sqrt(2.0)
S, Cq = math.sin(math.pi / 4), math.cos(math.pi / 4)        # a 90 degree turn's quaternion parts
S8, C8 = math.sin(math.pi / 8), math.cos(math.pi / 8)       # a 45 degree turn's
REST = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")
# a named point: (part, the point in the part's own box, from its centre)
POINTS = {
    "torso": ("Torso", (0.0, 0.0, 0.0)),
    "right_hand": ("Right Arm", (0.0, -1.0, 0.0)),
    "left_hand": ("Left Arm", (0.0, -1.0, 0.0)),
    "face": ("Head", (0.0, 0.0, -0.5)),
    "right_sole": ("Right Leg", (0.0, -1.0, 0.0)),
    "left_sole": ("Left Leg", (0.0, -1.0, 0.0)),
}
_REST = {"torso": (0.0, 0.0, 0.0), "right_hand": (1.5, -1.0, 0.0), "left_hand": (-1.5, -1.0, 0.0),
         "face": (0.0, 1.5, -0.5), "right_sole": (0.5, -3.0, 0.0), "left_sole": (-0.5, -3.0, 0.0)}


def _with(**moved):
    d = dict(_REST)
    d.update(moved)
    return d


def _up(d, by):
    return {k: (v[0], v[1] + by, v[2]) for k, v in d.items()}


# BY HAND (the block sizes and the joints' places only):
EXPECTED = [
    _with(),
    _with(right_hand=(1.5, 0.5, -1.5)),                     # shoulder (1, 0.5, 0); the end 0.5 out and 1.5 down of it
    _with(left_hand=(-2.5, 1.0, 0.0)),                      # shoulder (-1, 0.5, 0)
    _with(face=(-0.5, 1.5, 0.0)),                           # neck (0, 1, 0); the face 0.5 up and 0.5 ahead of it
    _with(**{**_up(_REST, 1.0), "right_sole": (0.5, -R2, -R2)}),   # hip (1, -1, 0) + 1 up; the sole 0.5 in, 2 down
    # the body turned a quarter left (x, y, z) -> (z, y, -x), then 1 ahead (-Z). In the body's own axes first: the
    # face 0.5 up and 0.5 ahead of the neck tipped 45 back -> straight up, sqrt(0.5) above the neck; the left sole
    # 0.5 out and 2 below its hip swung 45 ahead -> sqrt(2) down and sqrt(2) ahead of the hip
    {"torso": (0.0, 0.0, -1.0), "right_hand": (0.0, -1.0, -2.5), "left_hand": (0.0, -1.0, 0.5),
     "face": (0.0, 1.0 + R2 / 2, -1.0), "right_sole": (0.0, -3.0, -1.5), "left_sole": (-R2, -1.0 - R2, -0.5)},
]
POSES = [
    {},
    {"Right Arm": [S, 0.0, 0.0, Cq, 0.0, 0.0, 0.0]},
    {"Left Arm": [0.0, 0.0, -S, Cq, 0.0, 0.0, 0.0]},
    {"Head": [0.0, S, 0.0, Cq, 0.0, 0.0, 0.0]},
    {"Torso": [0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0], "Right Leg": [S8, 0.0, 0.0, C8, 0.0, 0.0, 0.0]},
    {"Torso": [0.0, S, 0.0, Cq, 0.0, 0.0, -1.0], "Left Leg": [S8, 0.0, 0.0, C8, 0.0, 0.0, 0.0],
     "Head": [S8, 0.0, 0.0, C8, 0.0, 0.0, 0.0]},
]
# what the ENGINE's joint must hold (Motor6D.Transform: x y z, then the rotation's rows), by pose and part
ENGINE_POSES = {
    (1, "Right Arm"): [0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0],      # CFrame.Angles(0, 0, pi / 2)
    (4, "Torso"): [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],           # a stud up is the RootJoint's +Z
    # (the RootJoint's C0 rows are (-1 0 0) (0 0 1) (0 1 0): its own Y points BEHIND the character, its Z up)
    (5, "Torso"): [0.0, -1.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0],         # ahead is its -Y; a left turn its +Z
}


BLADE = 3.0          # studs: the calibration's blade, grip to tip
_TURNED = [0.0, 0.0, S, Cq, 0.0, 1.0, 0.0]
GRIP_POSES = {1: _TURNED, 3: _TURNED}                        # the Handle joint's Transform, pose by pose (unsaid: none)
WEAPON_EXPECTED = {                                          # BY HAND (the edge: a stud from the grip, on the edge's side)
    0: {"weapon_grip": (1.5, -1.0, 0.0), "weapon_tip": (1.5, -1.0, -BLADE), "weapon_edge": (0.5, -1.0, 0.0)},
    # the arm lifted 90 degrees ahead: the hand is at (1.5, 0.5, -1.5), the grip frame's "ahead" now points UP
    1: {"weapon_grip": (1.5, 1.5, -1.5), "weapon_tip": (1.5 - BLADE, 1.5, -1.5), "weapon_edge": (1.5, 0.5, -1.5)},
    3: {"weapon_grip": (1.5, -1.0, -1.0), "weapon_tip": (1.5 - BLADE, -1.0, -1.0), "weapon_edge": (1.5, -1.0, 0.0)},
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def calibration(fps=30):
    """the calibration clip (R6, one pose a frame)"""
    n = len(POSES)
    return {"schema": 1, "name": "FrameContract", "rig": "R6", "fps": fps, "loop": False, "priority": "Action",
            "times": [round(i / fps, 6) for i in range(n)], "duration": round((n - 1) / fps, 6), "events": [],
            "joints": {p: {"frames": [list(POSES[i].get(p, REST)) for i in range(n)]} for p in PARTS},
            "grip": [list(GRIP_POSES.get(i, REST)) for i in range(n)]}


def weapon_route(clip=None):
    """kit/anim/grip.py's convention: the Right Arm's frame x RightGrip's C0 x the grip track's Transform -> the
    weapon's grip and tip, pose by pose ({pose: {weapon_grip, weapon_tip}} for the poses WEAPON_EXPECTED names)"""
    import clip as C
    import grip as GR
    c = clip or calibration()
    rig = C.load_rig("r6")
    out = {}
    for i in WEAPON_EXPECTED:
        A = C.fk(rig, C.character_transforms(c, rig, i))["Right Arm"]
        f = c["grip"][i]
        T = np.eye(4)
        T[:3, :3], T[:3, 3] = C.quat_mat(f[:4]), f[4:7]
        H = A @ GR.GRIP_C0 @ T
        out[i] = {"weapon_grip": tuple(float(v) for v in H[:3, 3]),
                  "weapon_tip": tuple(float(v) for v in (H @ np.array([0.0, BLADE, 0.0, 1.0]))[:3]),
                  "weapon_edge": tuple(float(v) for v in (H @ np.array([-1.0, 0.0, 0.0, 1.0]))[:3])}
    return out


def check_weapon(got, tol=TOL):
    """-> [what is off, in words]"""
    off = []
    for i, e in WEAPON_EXPECTED.items():
        for name, want in e.items():
            g = (got.get(i) or got.get(str(i)) or {}).get(name)
            if g is None:
                off.append(f"pose {i}: no {name}")
                continue
            d = float(np.linalg.norm(np.asarray(g, float) - np.asarray(want, float)))
            if not d <= tol:
                off.append(f"pose {i}: the {name.replace('_', ' ')} is at ({g[0]:.3f}, {g[1]:.3f}, {g[2]:.3f}), the contract "
                           f"has it at ({want[0]:.3f}, {want[1]:.3f}, {want[2]:.3f}) - {d:.3f} studs off")
    return off


def points(world):
    """every frame's named points off a route's part frames ([{part: 4x4}] in the character's space)"""
    out = []
    for Wf in world:
        row = {}
        for name, (part, at) in POINTS.items():
            M = np.asarray(Wf[part], float)
            row[name] = tuple(float(v) for v in (M[:3, :3] @ np.asarray(at, float) + M[:3, 3]))
        out.append(row)
    return out


def check(got, expected=None, tol=TOL):
    """-> [what is off, in words] (empty: the route keeps the contract)"""
    expected = EXPECTED if expected is None else expected
    off = []
    if len(got) != len(expected):
        return [f"it has {len(got)} poses, the calibration has {len(expected)}"]
    for i, (g, e) in enumerate(zip(got, expected)):
        for name, want in e.items():
            if name not in g:
                off.append(f"pose {i}: no {name}")
                continue
            d = float(np.linalg.norm(np.asarray(g[name], float) - np.asarray(want, float)))
            if not d <= tol:
                off.append(f"pose {i}: the {name.replace('_', ' ')} is at ({g[name][0]:.3f}, {g[name][1]:.3f}, {g[name][2]:.3f}), "
                           f"the contract has it at ({want[0]:.3f}, {want[1]:.3f}, {want[2]:.3f}) - {d:.3f} studs off")
    return off


def python_route(clip=None):
    """kit/anim/clip.py: the clip's frames -> part frames -> the named points"""
    import clip as C
    c = clip or calibration()
    return points(C.world_frames(c, C.load_rig("r6")))


def gltf_route(glb_path):
    """kit/anim/export_clip.py's .glb (the clip OUT of Roblox: each part a node, its world place and turn a frame) ->
    the named points, pose by pose. Read with nothing but the glTF 2.0 layout: a JSON chunk, a binary chunk,
    accessors of 32-bit floats; a rotation is (x, y, z, w)"""
    import struct
    with open(glb_path, "rb") as fh:
        blob = fh.read()
    if blob[:4] != b"glTF":
        raise ValueError("it is not a .glb")
    n0 = struct.unpack("<I", blob[12:16])[0]
    doc = json.loads(blob[20:20 + n0])
    binary = blob[20 + n0 + 8:]

    def floats(index):
        acc = doc["accessors"][index]
        view = doc["bufferViews"][acc["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        vals = struct.unpack("<" + "f" * (acc["count"] * width), binary[start:start + 4 * acc["count"] * width])
        return [vals[i * width:(i + 1) * width] for i in range(acc["count"])]

    anim = doc["animations"][0]
    tracks = {}
    for ch in anim["channels"]:
        name = doc["nodes"][ch["target"]["node"]]["name"]
        tracks.setdefault(name, {})[ch["target"]["path"]] = floats(anim["samplers"][ch["sampler"]]["output"])
    frames = max(len(t["translation"]) for t in tracks.values())
    import clip as C
    out = []
    for i in range(frames):
        Wf = {}
        for name, t in tracks.items():
            M = np.eye(4)
            M[:3, :3] = C.quat_mat(list(t["rotation"][i]))
            M[:3, 3] = t["translation"][i]
            Wf[name] = M
        out.append(Wf)
    return points(out)


IMPORT_TOL = 1.0     # degrees
IMPORT_TURNS = {     # pose -> (the R15 chain: from, to), the turn about a Roblox axis, degrees - BY HAND
    1: ("RightUpperArm", "RightHand", (1.0, 0.0, 0.0), 90.0),
    2: ("LeftUpperArm", "LeftHand", (0.0, 0.0, -1.0), 90.0),
    4: ("RightUpperLeg", "RightFoot", (1.0, 0.0, 0.0), 45.0),
}
IMPORT_LOOK = {3: (-1.0, 0.0, 0.0)}                          # pose -> where the face looks (rest: ahead, -Z)
IMPORT_RISE = {4: 0.2}                                       # pose -> the pelvis's rise, metres of the source
SRC_HEIGHT = 1.75 - 0.02                                     # the calibration skeleton: its head's top over its toes


def _turned(axis, deg, v):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    t = math.radians(deg)
    v = np.asarray(v, float)
    return v * math.cos(t) + np.cross(a, v) * math.sin(t) + a * float(a @ v) * (1 - math.cos(t))


def _turn_matrix(axis, deg):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    t = math.radians(deg)
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * (K @ K)


def _chain(rig, Wf, a, b):
    M, N = np.asarray(Wf[a], float), np.asarray(Wf[b], float)
    start = M[:3, :3] @ np.asarray(rig["joints"][a]["c1"][:3], float) + M[:3, 3]
    v = N[:3, 3] - start
    return v / max(np.linalg.norm(v), 1e-12)


def _deg(u, w):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.asarray(u) @ np.asarray(w))))))


def _rot_deg(A, B):
    R = np.asarray(A, float)[:3, :3].T @ np.asarray(B, float)[:3, :3]
    return math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(R)) - 1) / 2))))


T_LINES = {"RightUpperArm": {0: (1.0, 0.0, 0.0), 1: (0.0, 0.0, -1.0)}, "LeftUpperArm": {0: (-1.0, 0.0, 0.0)}}
T_TOL = 17.5         # degrees: the R15's shoulder-to-hand line leans 16.3 off its arm's own length

CHAINS = {"RightUpperArm": ("RightUpperArm", "RightLowerArm", "RightHand"), "LeftUpperArm": ("LeftUpperArm", "LeftLowerArm", "LeftHand"),
          "RightUpperLeg": ("RightUpperLeg", "RightLowerLeg", "RightFoot")}


def check_import(clip, whole=True):
    """an R15 clip the import route made of the calibration skeleton -> [what is off, in words]. whole: every part's
    whole turn is checked too (all three axes); off for a T-posed source, whose arms aimed ahead take their own twist"""
    import clip as C
    if not isinstance(clip, dict) or clip.get("rig") != "R15" or len(clip.get("times") or []) != 5:
        return ["it is not the calibration's import (an R15 clip of 5 poses)"]
    rig = C.load_rig("r15")
    W = C.world_frames({k: v for k, v in clip.items() if k != "root"}, rig)
    rest = C.fk(rig)
    off = []
    for i in range(5):
        for pose, (a, b, axis, deg) in IMPORT_TURNS.items():
            base = _chain(rig, rest, a, b)
            want = _turned(axis, deg, base) if i == pose else base
            tol = IMPORT_TOL
            if not whole and a in T_LINES:
                # (a T-posed source: its arms are OUT at rest, and aimed ahead / left they take their own twist - the
                # line is held to its direction within the R15 arm's own slant off its length)
                want, tol = np.asarray(T_LINES[a].get(i, T_LINES[a][0]), float), T_TOL
            got = _chain(rig, W[i], a, b)
            d = _deg(got, want)
            if not d <= tol:
                off.append(f"pose {i}: the {a} -> {b} line points ({got[0]:.2f}, {got[1]:.2f}, {got[2]:.2f}), the contract "
                           f"has ({want[0]:.2f}, {want[1]:.2f}, {want[2]:.2f}) - {d:.1f} degrees off")
        look = np.asarray(W[i]["Head"], float)[:3, :3] @ np.array([0.0, 0.0, -1.0])
        want = np.asarray(IMPORT_LOOK.get(i, (0.0, 0.0, -1.0)), float)
        d = _deg(look, want)
        if not d <= IMPORT_TOL:
            off.append(f"pose {i}: the face looks ({look[0]:.2f}, {look[1]:.2f}, {look[2]:.2f}), the contract has "
                       f"({want[0]:.2f}, {want[1]:.2f}, {want[2]:.2f}) - {d:.1f} degrees off")
    if whole:
        for i in range(5):
            for part in rig["order"]:
                if part not in W[i]:
                    continue
                want = np.eye(3)
                for pose, (a, _b, axis, deg) in IMPORT_TURNS.items():
                    if i == pose and part in CHAINS[a]:
                        want = _turn_matrix(axis, deg)
                if i == 3 and part == "Head":
                    want = _turn_matrix((0.0, 1.0, 0.0), 90.0)
                got = np.asarray(W[i][part], float)[:3, :3] @ np.asarray(rest[part], float)[:3, :3].T
                d = math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(want.T @ got)) - 1) / 2))))
                if not d <= IMPORT_TOL:
                    off.append(f"pose {i}: {part} is turned {d:.1f} degrees from the contract's whole turn")
    r15_height = ((rig["rest"]["Head"][1] + rig["sizes"]["Head"][1] / 2)
                  - (rig["rest"]["RightFoot"][1] - rig["sizes"]["RightFoot"][1] / 2))
    y0 = float(np.asarray(W[0]["LowerTorso"])[1, 3])
    for i in range(5):
        rise = float(np.asarray(W[i]["LowerTorso"])[1, 3]) - y0
        want = IMPORT_RISE.get(i, 0.0) * r15_height / SRC_HEIGHT
        if abs(rise - want) > TOL:
            off.append(f"pose {i}: the pelvis rises {rise:.3f} studs, the contract has {want:.3f}")
    return off


def import_run(folder, mirror=False, scale=1.0, turn=0.0, splay=0.0, tpose=False, blender=None):
    """the calibration skeleton built in Blender and brought in by kit/anim/retarget.py -> the R15 clip (dict), with
    the route's own verdict under "_route" (its summary, `axes_disagree`)"""
    import subprocess
    exe = blender or find_blender() or "blender"
    if not os.path.isfile(exe):
        raise FileNotFoundError(f"Blender is not at {exe} (set KIT_BLENDER or BLENDER)")
    os.makedirs(folder, exist_ok=True)
    glb, spec, out = (os.path.join(folder, n) for n in ("cal.glb", "cal.import.json", "cal.clip.json"))
    extra = (["--mirror"] if mirror else []) + (["--tpose"] if tpose else []) + ["--scale", str(scale), "--turn", str(turn),
                                                                                   "--splay", str(splay)]
    r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(HERE, "import_calibration_blend.py"), "--", glb] + extra, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(glb):
        raise RuntimeError(f"the calibration skeleton was not built: {(r.stdout + r.stderr)[-300:]}")
    with open(spec, "w", encoding="utf-8") as fh:
        # (no "arms": the route's own "auto", as `kit anim import` writes it)
        json.dump({"file": glb, "clip": "Calibration", "fps": 30, "loop": False, "priority": "Action", "hit": None}, fh)
    r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P", os.path.join(HERE, "retarget.py"),
                        "--", spec, "--out", out], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(f"the import route failed: {(r.stdout + r.stderr)[-300:]}")
    with open(out, encoding="utf-8") as fh:
        clip = json.load(fh)
    verdict = [line for line in r.stdout.splitlines() if line.startswith("{") and '"status"' in line]
    clip["_route"] = json.loads(verdict[-1]) if verdict else {}
    return clip


def import_all(folder):
    """the calibration through the import route four ways -> [what is off]: as it is, in centimetres, facing another
    way (all three must keep the contract), and with its labels mirrored (that one must NOT)"""
    off = list(check_import(import_run(os.path.join(folder, "ok"))))
    for name, kw, whole in (("centimetres", {"scale": 100.0}, True), ("facing another way", {"turn": 90.0}, True),
                            ("toe-out", {"splay": 12.0}, True), ("T-posed", {"tpose": True}, False)):
        clip = import_run(os.path.join(folder, name.split()[0]), **kw)
        off += [f"{name}: {o}" for o in check_import(clip, whole=whole)]
        if clip["_route"].get("axes_disagree"):
            off.append(f"{name}: the route says its hands and toes disagree")
    mirror = import_run(os.path.join(folder, "mirror"), mirror=True)
    if not check_import(mirror):
        off.append("a skeleton with its left and right labels swapped PASSES: the check does not see it")
    if not mirror["_route"].get("axes_disagree"):
        off.append("a skeleton with its left and right labels swapped is not SAID by the route")
    return off


def wrong():
    """the calibration with one deliberate mistake each -> {name: clip}; every one must fail the check"""
    import copy
    base = calibration()

    def each(fn):
        c = copy.deepcopy(base)
        for j in c["joints"].values():
            j["frames"] = [fn(list(f)) for f in j["frames"]]
        return c

    return {
        "mirrored: left-handed turns": each(lambda f: [-f[0], -f[1], -f[2], f[3]] + f[4:]),
        "mirrored: the right is on -X": each(lambda f: [f[0], -f[1], -f[2], f[3], -f[4], f[5], f[6]]),
        "the up and ahead axes swapped": each(lambda f: [f[0], f[2], f[1], f[3], f[4], f[6], f[5]]),
        "ahead is +Z": each(lambda f: [-f[0], f[1], -f[2], f[3], f[4], f[5], -f[6]]),
        "slides in metres": each(lambda f: f[:4] + [v * 0.28 for v in f[4:]]),
        "half turns (degrees read as half)": each(lambda f: _half(f)),
    }


def _half(f):
    a = 2 * math.acos(max(-1.0, min(1.0, f[3])))
    s = math.sin(a / 2)
    if s < 1e-9:
        return f
    ax = [v / s for v in f[:3]]
    return [ax[0] * math.sin(a / 4), ax[1] * math.sin(a / 4), ax[2] * math.sin(a / 4), math.cos(a / 4)] + f[4:]


def mirrored_expected():
    """the contract's places for the MIRRORED move (left and right swapped): what a correct mirror must give"""
    swap = {"right_hand": "left_hand", "left_hand": "right_hand", "right_sole": "left_sole", "left_sole": "right_sole"}
    return [{swap.get(k, k): (-v[0], v[1], v[2]) for k, v in e.items()} for e in EXPECTED]


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if argv and argv[0] == "write":
            with open(argv[1], "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"clip": calibration(), "points": {k: [v[0], list(v[1])] for k, v in POINTS.items()},
                           "expected": [{k: list(v) for k, v in e.items()} for e in EXPECTED], "tol": TOL, "blade": BLADE,
                           "weapon": {str(i): {k: list(v) for k, v in e.items()} for i, e in WEAPON_EXPECTED.items()}},
                          fh, indent=1)
                fh.write("\n")
            return emit("pass", f"anim frames: the calibration clip and its {len(EXPECTED)} poses' places written to {argv[1]}", "none")
        if argv and argv[0] == "import":
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                off = import_all(tmp)
            if off:
                return emit("fail", f"anim frames (import): {off[0]}" + (f" (+{len(off) - 1} more)" if len(off) > 1 else ""),
                            "the import route's axes or turns differ from the contract: fix the route", off=off)
            return emit("pass", "anim frames (import): retarget.py keeps the contract - every part's whole turn and a "
                        "rise by hand; in centimetres, facing another way, toe-out, T-posed too; a mirrored skeleton fails "
                        "and the route says so", "none")
        if argv and argv[0] == "check":
            with open(argv[1], encoding="utf-8") as fh:
                got = json.load(fh)
            off = check([{k: tuple(v) for k, v in row.items()} for row in got])
        else:
            off = check(python_route()) + check_weapon(weapon_route())
            for name, c in wrong().items():
                if not check(python_route(c)):
                    off.append(f"the wrong copy \"{name}\" PASSES: the check does not see that mistake")
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, RuntimeError) as e:
        return emit("fail", f"anim frames: it could not be read ({type(e).__name__}: {e})", "python kit/anim/frame_contract.py")
    if off:
        return emit("fail", f"anim frames: {off[0]}" + (f" (+{len(off) - 1} more)" if len(off) > 1 else ""),
                    "a route's axes, handedness, units or pivots differ from the contract: fix the route, not the contract", off=off)
    return emit("pass", f"anim frames: the route keeps the contract - {len(EXPECTED)} poses, six places each, within "
                f"{TOL:g} studs; every wrong copy fails", "none")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
