"""kit/anim/frame_contract.py - one frame convention, proven (the owner's older list, AN-03): a calibration motion
whose places are written by hand goes through the kit's routes; a mirrored, axis-swapped, metre or half-turn copy
must fail. The Luau routes are held by kit/test/spec/animframes.spec.luau; the engine by a Studio reading (the
audit page)."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C                 # noqa: E402
import derive as D               # noqa: E402
import frame_contract as F       # noqa: E402
import kfs_import as K           # noqa: E402

FIX = os.path.join(ROOT, "kit", "selftest", "anim")


def test_the_expected_places_are_written_by_hand_not_computed():
    # (the block sizes and the joints only: an arm's end 0.5 out and 1.5 below its shoulder, turned by hand)
    assert F.EXPECTED[0]["right_hand"] == (1.5, -1.0, 0.0) and F.EXPECTED[0]["left_sole"] == (-0.5, -3.0, 0.0)
    assert F.EXPECTED[1]["right_hand"] == (1.5, 0.5, -1.5)            # ahead is -Z
    assert F.EXPECTED[2]["left_hand"] == (-2.5, 1.0, 0.0)             # the left is -X
    assert F.EXPECTED[3]["face"] == (-0.5, 1.5, 0.0)                  # a positive turn about +Y looks left
    assert F.EXPECTED[4]["torso"] == (0.0, 1.0, 0.0)
    assert np.allclose(F.EXPECTED[4]["right_sole"], (0.5, -math.sqrt(2), -math.sqrt(2)))
    assert F.EXPECTED[5]["torso"] == (0.0, 0.0, -1.0) and F.EXPECTED[5]["right_hand"] == (0.0, -1.0, -2.5)
    assert np.allclose(F.EXPECTED[5]["left_sole"], (-math.sqrt(2), -1 - math.sqrt(2), -0.5))
    assert np.allclose(F.EXPECTED[5]["face"], (0.0, 1 + math.sqrt(0.5), -1.0))
    assert len(F.EXPECTED) == len(F.POSES) == 6
    src = open(os.path.join(ROOT, "kit", "anim", "frame_contract.py"), encoding="utf-8").read()
    body = src[src.index("EXPECTED = ["):src.index("POSES = [")]
    assert "fk(" not in body and "world_frames" not in body


def test_the_python_route_keeps_the_contract():
    assert F.check(F.python_route()) == []
    assert F.main([]) == 0


def test_every_wrong_copy_fails_and_says_where():
    wrong = F.wrong()
    assert len(wrong) == 6
    for name, clip in wrong.items():
        off = F.check(F.python_route(clip))
        assert off, name
        assert "the contract has it at" in off[0], name
    # ... each caught on the pose that shows it: left-handed turns on the arm lifted ahead (it goes behind)
    off = F.check(F.python_route(wrong["mirrored: left-handed turns"]))
    assert any(o.startswith("pose 1: the right hand") for o in off)
    off = F.check(F.python_route(wrong["slides in metres"]))
    assert off and all(o.startswith(("pose 4", "pose 5")) for o in off)


def test_routes_the_first_five_poses_could_not_see_fail_on_the_sixth():
    # (the one review ran these against the first cut: all passed)
    rig = C.load_rig("r6")
    base = F.calibration()

    def places(fn):
        """the calibration through a route whose forward kinematics is `fn(world, part, joint, R, p)` -> 4x4"""
        out = []
        for i in range(len(base["times"])):
            world = {rig["root"]: np.eye(4)}
            tr = C.character_transforms(base, rig, i)
            for part in rig["order"]:
                j = rig["joints"][part]
                R, p = tr.get(part, (np.eye(3), np.zeros(3)))
                world[part] = fn(world, part, j, R, p)
            out.append(world)
        return F.points(out)

    def good(world, part, j, R, p):
        tj, pj = C.joint_space(rig, part, R, p)
        t4 = np.eye(4)
        t4[:3, :3], t4[:3, 3] = tj, pj
        return world[j["parent"]] @ C.cf(j["c0"]) @ t4 @ np.linalg.inv(C.cf(j["c1"]))

    assert F.check(places(good)) == []

    def no_parent_turn(world, part, j, R, p):                # a limb hung from a parent whose turn is dropped
        m = good(world, part, j, R, p)
        if j["parent"] != rig["root"]:
            par = np.eye(4)
            par[:3, 3] = world[j["parent"]][:3, 3]
            m = par @ C.cf(j["c0"]) @ np.block([[C.joint_space(rig, part, R, p)[0], np.zeros((3, 1))], [np.zeros((1, 3)), 1]]) \
                @ np.linalg.inv(C.cf(j["c1"]))
        return m

    def slide_in_turned_axes(world, part, j, R, p):
        return good(world, part, j, R, R @ p)

    def left_leg_inverted(world, part, j, R, p):
        return good(world, part, j, R.T if part == "Left Leg" else R, p)

    def torso_inverted(world, part, j, R, p):
        return good(world, part, j, R.T if part == "Torso" else R, p)

    for wrong in (no_parent_turn, slide_in_turned_axes, left_leg_inverted, torso_inverted):
        off = F.check(places(wrong))
        assert off and all(o.startswith("pose 5") for o in off), wrong.__name__


def test_the_compiled_poses_are_the_engines_own_numbers():
    # a rig file with a wrong C0 passes every PLACE (its turn cancels out of c0 . T . c0^T): the Motor6D.Transform
    # the kit compiles is held to Roblox's own joints here, by hand (and was read back in Studio)
    with open(os.path.join(FIX, "frame_contract.kfs.json"), encoding="utf-8") as fh:
        dump = json.load(fh)
    for (pose, part), want in F.ENGINE_POSES.items():
        got = dump["keyframes"][pose]["poses"][part]["cf"]
        assert np.allclose(got, want, atol=1e-4), (pose, part, got)
    # ... and Python's own joint maths gives the same from the clip's frame
    rig = C.load_rig("r6")
    for (pose, part), want in F.ENGINE_POSES.items():
        f = F.POSES[pose][part]
        tj, pj = C.joint_space(rig, part, C.quat_mat(f[:4]), np.array(f[4:7]))
        assert np.allclose(np.r_[pj, tj.reshape(-1)], want, atol=1e-6), (pose, part)


def test_a_route_a_hundredth_of_a_stud_off_fails_and_half_that_passes():
    got = F.python_route()
    near = copy.deepcopy(got)
    near[2]["left_hand"] = tuple(np.add(near[2]["left_hand"], (0.004, 0.0, 0.0)))
    assert F.check(near) == []
    far = copy.deepcopy(got)
    far[2]["left_hand"] = tuple(np.add(far[2]["left_hand"], (0.02, 0.0, 0.0)))
    assert len(F.check(far)) == 1
    assert F.check(got[:-1]) and F.check([{} for _ in got])
    nan = copy.deepcopy(got)
    nan[0]["torso"] = (float("nan"), 0.0, 0.0)
    assert F.check(nan)


def test_the_recipes_mirror_gives_the_mirrored_places():
    m = D.op_mirror(copy.deepcopy(F.calibration()))
    assert F.check(F.python_route(m), F.mirrored_expected()) == []
    assert F.check(F.python_route(m))                        # (and a mirrored move is not the move)
    assert F.mirrored_expected()[1]["left_hand"] == (-1.5, 0.5, -1.5)


def test_the_keyframe_sequence_the_kit_compiles_imports_back_onto_the_contract():
    # kit/lib/anim.luau modelFromClip's Poses (kept by kit/selftest/anim/frame_contract_write.luau; the spec holds
    # the kept file to today's compile) -> kit/anim/kfs_import.py -> a clip -> the places
    with open(os.path.join(FIX, "frame_contract.kfs.json"), encoding="utf-8") as fh:
        dump = json.load(fh)
    assert len(dump["keyframes"]) == 6
    clip = K.convert(copy.deepcopy(dump), {"fps": 30, "loop": False, "name": "FrameContract"}, C.load_rig("r6"))[0]
    assert clip["rig"] == "R6" and len(clip["times"]) == 6
    assert F.check(F.python_route(clip)) == []
    # the Poses themselves are joint-space: the arm's turn ahead is NOT a turn about X there (the shoulder's C0
    # is turned) - reading a Pose as character space is the mistake the import exists to not make
    arm = np.array(dump["keyframes"][1]["poses"]["Right Arm"]["cf"][3:]).reshape(3, 3)
    assert not np.allclose(arm, C.quat_mat(F.POSES[1]["Right Arm"][:4]), atol=1e-3)
    wrong = copy.deepcopy(dump)
    for kf in wrong["keyframes"]:
        for pose in kf["poses"].values():
            pose["cf"][:3] = [v * 0.28 for v in pose["cf"][:3]]
    assert F.check(F.python_route(K.convert(wrong, {"fps": 30, "loop": False, "name": "X"}, C.load_rig("r6"))[0]))


def test_the_fixture_is_the_contracts_own_writing(tmp_path, capsys):
    out = tmp_path / "frame_contract.json"
    assert F.main(["write", str(out)]) == 0
    capsys.readouterr()
    with open(os.path.join(FIX, "frame_contract.json"), encoding="utf-8") as fh:
        kept = json.load(fh)
    assert json.loads(out.read_text(encoding="utf-8")) == kept
    # places read off another route (Studio writes such a file) are checked the same way
    got = tmp_path / "got.json"
    got.write_text(json.dumps([{k: list(v) for k, v in row.items()} for row in F.python_route()]), encoding="utf-8")
    assert F.main(["check", str(got)]) == 0
    bad = F.python_route(F.wrong()["ahead is +Z"])
    got.write_text(json.dumps([{k: list(v) for k, v in row.items()} for row in bad]), encoding="utf-8")
    assert F.main(["check", str(got)]) == 1
    got.write_text(json.dumps({"a": 1}), encoding="utf-8")   # (not a list of poses: said, not a traceback)
    assert F.main(["check", str(got)]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "fail"


def test_the_weapons_own_joint_puts_the_blade_where_the_contract_has_it():
    # by hand: at rest the blade points straight ahead from the hand; in pose 3 it is turned to the body's left
    assert F.WEAPON_EXPECTED[0] == {"weapon_grip": (1.5, -1.0, 0.0), "weapon_tip": (1.5, -1.0, -3.0), "weapon_edge": (0.5, -1.0, 0.0)}
    assert F.WEAPON_EXPECTED[3] == {"weapon_grip": (1.5, -1.0, -1.0), "weapon_tip": (-1.5, -1.0, -1.0), "weapon_edge": (1.5, -1.0, 0.0)}
    # ... and with the ARM lifted ahead the same Transform rides the arm (the review: an arm at rest proves nothing of it)
    assert F.WEAPON_EXPECTED[1] == {"weapon_grip": (1.5, 1.5, -1.5), "weapon_tip": (-1.5, 1.5, -1.5), "weapon_edge": (1.5, 0.5, -1.5)}
    assert F.check_weapon(F.weapon_route()) == []
    # the route's own maths against the kit's function that MAKES a grip track (kit/anim/grip.py grip_track): a
    # sword path at the contract's places gives back the calibration's Transform
    import grip as GR
    c = F.calibration()
    n = len(c["times"])
    c["sword"] = {"tip": [list(F.WEAPON_EXPECTED[3]["weapon_tip"])] * n, "grip_path": [list(F.WEAPON_EXPECTED[3]["weapon_grip"])] * n,
                  "edge": [[0.0, 0.0, 1.0]] * n}               # (the edge: -X of the weapon, which in pose 3 points BACK)
    made = GR.grip_track(c)[3]                                # (pose 3: the arm at rest)
    want = F.GRIP_POSES[3]
    assert C.quat_angle(made[:4], want[:4]) < 0.05 and np.allclose(made[4:7], want[4:7], atol=1e-4)
    # wrong routes must fail: no RightGrip frame; the blade along the weapon's X; the Transform before the grip's frame
    rig = C.load_rig("r6")

    def route(fn):
        out = {}
        for i in F.WEAPON_EXPECTED:
            A = C.fk(rig, C.character_transforms(c, rig, i))["Right Arm"]
            f = c["grip"][i]
            T = np.eye(4)
            T[:3, :3], T[:3, 3] = C.quat_mat(f[:4]), f[4:7]
            H, tip = fn(A, T)
            out[i] = {"weapon_grip": tuple(H[:3, 3]), "weapon_tip": tuple((H @ np.array(tip + [1.0]))[:3]),
                      "weapon_edge": tuple((H @ np.array([-1.0, 0.0, 0.0, 1.0]))[:3])}
        return out

    # the routes the review built that passed the first cut: each must fail now
    rest_arm = C.fk(rig)["Right Arm"]

    def with_arm(change):
        out = {}
        for i in F.WEAPON_EXPECTED:
            A = change(C.fk(rig, C.character_transforms(c, rig, i))["Right Arm"])
            f = c["grip"][i]
            T = np.eye(4)
            T[:3, :3], T[:3, 3] = C.quat_mat(f[:4]), f[4:7]
            H = A @ GR.GRIP_C0 @ T
            out[i] = {"weapon_grip": tuple(H[:3, 3]), "weapon_tip": tuple((H @ np.array([0.0, 3.0, 0.0, 1.0]))[:3]),
                      "weapon_edge": tuple((H @ np.array([-1.0, 0.0, 0.0, 1.0]))[:3])}
        return out

    def transposed(A):
        B = A.copy()
        B[:3, :3] = A[:3, :3].T
        return B

    assert F.check_weapon(with_arm(lambda A: A)) == []
    assert F.check_weapon(with_arm(lambda A: rest_arm))                  # the arm's pose ignored
    assert F.check_weapon(with_arm(transposed))                          # the arm's turn the wrong way round
    rolled, mirrored = {}, {}
    for i, e in F.weapon_route().items():
        g, t, ed = (np.array(e[k]) for k in ("weapon_grip", "weapon_tip", "weapon_edge"))
        axis = (t - g) / np.linalg.norm(t - g)
        rolled[i] = dict(e, weapon_edge=tuple(g + np.cross(axis, ed - g)))       # a quarter roll about the blade
        mirrored[i] = dict(e, weapon_edge=tuple(g - (ed - g)))                   # the edge on the other side
    assert F.check_weapon(rolled) and F.check_weapon(mirrored)

    assert F.check_weapon(route(lambda A, T: (A @ GR.GRIP_C0 @ T, [0.0, 3.0, 0.0]))) == []
    assert F.check_weapon(route(lambda A, T: (A @ T, [0.0, 3.0, 0.0])))
    assert F.check_weapon(route(lambda A, T: (A @ GR.GRIP_C0 @ T, [3.0, 0.0, 0.0])))
    assert F.check_weapon(route(lambda A, T: (A @ T @ GR.GRIP_C0, [0.0, 3.0, 0.0])))
    assert F.check_weapon({}) and F.check_weapon({0: {"weapon_grip": (0, 0, 0)}})


def test_the_export_out_of_roblox_keeps_the_contract(tmp_path):
    # kit/anim/export_clip.py: the calibration as a .glb any engine loads - each part's own place and turn a frame
    import subprocess
    src, out = tmp_path / "cal.clip.json", tmp_path / "cal.glb"
    src.write_text(json.dumps(F.calibration()), encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "export_clip.py"), str(src), str(out)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and out.exists(), r.stdout + r.stderr
    got = F.gltf_route(str(out))
    assert len(got) == len(F.EXPECTED) and F.check(got) == []
    # a wrong copy exported is still wrong on the other side (the reader does not forgive)
    bad = tmp_path / "bad.clip.json"
    bad.write_text(json.dumps(F.wrong()["ahead is +Z"]), encoding="utf-8")
    subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "export_clip.py"), str(bad), str(tmp_path / "bad.glb")],
                   capture_output=True, text=True, cwd=ROOT, check=True)
    assert F.check(F.gltf_route(str(tmp_path / "bad.glb")))
    with open(tmp_path / "not.glb", "wb") as fh:
        fh.write(b"nope")
    try:
        F.gltf_route(str(tmp_path / "not.glb"))
        raise AssertionError("a file that is no .glb was read")
    except ValueError:
        pass
