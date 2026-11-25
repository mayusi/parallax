"""kit/anim/pose_sheet.py + its parts in thumbs.py / proc_dossier.py / look_r6.py (the animation studio route's A0): a
move's key poses large beside their reference, its strips, and the LOOK line a build ends with. The pictures are
drawn from a FAKE render here (flat panes + the same cameras), so the layout, the cameras and what is drawn on them
are proven without Blender; one smoke case at the end renders the real rig when Blender and the owner's rig exist."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import clip as C            # noqa: E402
import pose_appeal as PA    # noqa: E402
import pose_sheet as PS     # noqa: E402
import proc_dossier as PD   # noqa: E402
import strike as S          # noqa: E402
import thumbs as T          # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "SheetProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.2, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.4, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8])]}
PHASES = [{"name": "guard", "game_s": [0.0, 0.0], "body": "a guard, the blade raised"},
          {"name": "wind", "game_s": [0.0, 0.2], "body": "the blade cocked back at the right side"},
          {"name": "cut", "game_s": [0.2, 0.4], "body": "the hands sweep across the front"}]
FLAT = (120, 124, 130)
ORIGIN = [0.0, 0.0, 3.0]


def clip_of():
    return S.generate(json.loads(json.dumps(MOVE)))[0]


def body_points(W, rig):
    return PS.to_blender(np.concatenate([C.corners(rig, p, W[p]) for p in PA.MASS]), ORIGIN)


def fake_render(folder, pl, clip, fk_error=0.0):
    """what kit/anim/look_r6.py --sheet leaves: a flat picture per key x view and per strip frame x view, and the
    camera of every one (the same pose_sheet.camera_fit the renderer uses)"""
    from PIL import Image
    rig = C.load_rig("r6")
    frames = C.world_frames(clip, rig)
    fdir = os.path.join(folder, "frames")
    os.makedirs(fdir, exist_ok=True)
    kh = pl["key_height"]
    clouds = [body_points(frames[key["frame"]], rig) for key in pl["keys"]]
    key_size = {v: PS.pane_size(PS.VIEW_DIRS[v], clouds, kh, PS.KEY_ASPECT) for v in pl["key_views"]}
    key_cams = {v: {} for v in pl["key_views"]}
    for key in pl["keys"]:
        i = key["frame"]
        for view in pl["key_views"]:
            kw = key_size[view][0]
            key_cams[view][str(i)] = PS.camera_fit(PS.VIEW_DIRS[view], body_points(frames[i], rig), kw / kh,
                                                   ortho=view in PS.VIEW_ORTHO)
            Image.new("RGB", (kw, kh), FLAT).save(os.path.join(fdir, f"key_{view}_{i:04d}.png"))
    strip = None
    if pl["strip_frames"]:
        body = np.concatenate([body_points(frames[i], rig) for i in pl["strip_frames"]])
        pth = PS.paths(clip, frames)
        drawn = np.concatenate([PS.to_blender(pth[k], ORIGIN) for k in PS.PATH_COLOUR if k in pth])
        strip = {"size": {}, "cams": {}, "follow": False}
        for view in pl["strip_views"]:
            held = PS.strip_points(PS.VIEW_DIRS[view], body, drawn)
            sw, sh = PS.strip_size(PS.VIEW_DIRS[view], held, pl["strip_height"])
            cam = PS.camera_fit(PS.VIEW_DIRS[view], held, sw / sh, margin=1.08)
            strip["size"][view], strip["cams"][view] = [sw, sh], {str(i): cam for i in pl["strip_frames"]}
            for i in pl["strip_frames"]:
                Image.new("RGB", (sw, sh), FLAT).save(os.path.join(fdir, f"strip_{view}_{i:04d}.png"))
    json.dump({"schema": 1, "name": pl["name"], "origin": ORIGIN, "f0": 1, "posed": False, "fidelity": None,
               "overlay_error_studs": fk_error, "projection_error_px": 0.0,
               "key": {"size": key_size, "cams": key_cams}, "strip": strip, "seconds": 0.0},
              open(os.path.join(folder, "render.json"), "w"))
    return frames, rig, key_cams


def planned(tmp_path, reference=True, strips=True, view=None):
    from PIL import Image
    clip = clip_of()
    clip_path = str(tmp_path / "SheetProbe.clip.json")
    json.dump(clip, open(clip_path, "w"))
    still = str(tmp_path / "wind.png")
    Image.new("RGB", (200, 100), (200, 30, 30)).save(still)
    ref = {"phase": "wind", "image": still, "game_t": 0.2, "note": "the blade back, level", "source": "probe_footage"}
    if view:
        ref["view"] = view
    dossier = {"phases": PHASES, "reference_frames": [ref] if reference else []}
    pl = PS.plan("SheetProbe", clip, MOVE, "sheet_probe", dossier, strips=strips, clip_path=clip_path, inputs=[clip_path])
    folder = str(tmp_path / "SheetProbe.sheet")
    os.makedirs(folder)
    json.dump(pl, open(os.path.join(folder, "plan.json"), "w"))
    return clip, pl, folder


# ---------------------------------------------------------------- the dossier's reference frames
def test_a_key_pose_belongs_to_the_phase_it_arrives_at():
    d = {"phases": PHASES + [{"name": "hold", "game_s": [0.4, 0.9]}]}
    assert PD.phase_at(d, 0.0) == "guard"                       # the still start, not the wind that begins there
    assert PD.phase_at(d, 0.1) == "wind"
    assert PD.phase_at(d, 0.2) == "wind"                        # the cocked blade is the END of the wind
    assert PD.phase_at(d, 0.21) == "cut"
    assert PD.phase_at(d, 0.4) == "cut"
    assert PD.phase_at(d, 0.9) == "hold"
    assert PD.phase_at(d, 1.5) is None                          # past every phase
    assert PD.phase_at({"phases": [{"name": "wind", "game_s": [0.0, 0.3]}]}, 0.0) == "wind"   # no still phase before it
    assert PD.phase_at({"phases": [{"name": "todo", "game_s": "TODO"}]}, 0.1) is None        # a scaffold's placeholder


def test_reference_frames_say_why_a_frame_cannot_be_shown(tmp_path):
    from PIL import Image
    still = str(tmp_path / "cut.png")
    Image.new("RGB", (8, 8)).save(still)
    d = {"phases": PHASES, "reference_frames": [
        {"phase": "cut", "image": still, "game_t": 0.4},
        {"phase": "wind", "video": str(tmp_path / "gone.mp4"), "t": 1.5, "game_t": 0.2},
        {"phase": "wind", "video": still},
        {"phase": "lunge", "image": still},
        {"phase": "cut", "image": still, "view": "below"},
        {"phase": "cut"}, "not a frame"]}
    refs = PD.reference_frames(d)
    assert len(refs) == 6
    assert refs[0]["missing"] is None and refs[0]["path"] == still
    assert "not on this machine" in refs[1]["missing"]
    assert "needs t" in refs[2]["missing"]
    assert "no phase named 'lunge'" in refs[3]["missing"]
    assert "view is one of" in refs[4]["missing"]
    assert "no video and no image" in refs[5]["missing"]


def test_reference_for_a_key_is_its_phases_nearest_frame(tmp_path):
    from PIL import Image
    a, b = str(tmp_path / "a.png"), str(tmp_path / "b.png")
    for p in (a, b):
        Image.new("RGB", (8, 8)).save(p)
    d = {"phases": PHASES, "reference_frames": [{"phase": "cut", "image": a, "game_t": 0.25},
                                                {"phase": "cut", "image": b, "game_t": 0.4}]}
    phase, ref, why = PD.reference_for(d, 0.4)
    assert (phase, ref["image"], why) == ("cut", b, None)
    assert PD.reference_for(d, 0.26)[1]["image"] == a
    phase, ref, why = PD.reference_for(d, 0.2)                  # the wind has no frame: the gap is said
    assert phase == "wind" and ref is None and "no reference frame for its phase 'wind'" in why
    assert "no reference frames at all" in PD.reference_for({"phases": PHASES}, 0.2)[2]
    assert "no phase of the dossier covers" in PD.reference_for(d, 3.0)[2]


KESA = {"phases": [{"name": "kamae", "game_s": [0.0, 0.0]}, {"name": "furikaburi", "game_s": [0.0, 0.15]},
                   {"name": "cut", "game_s": [0.15, 0.31]}, {"name": "zanshin", "game_s": [0.31, 0.62]}]}


def test_a_clip_not_timed_like_its_dossier_gets_its_phases_in_order_round_the_hit():
    assert PD.hit_phase(KESA) == "cut"
    names, how, why = PD.phases_for(KESA, [0.0, 0.15, 0.3, 0.6], 0.3)         # the dossier's own build: by its timing
    assert (names, how, why) == (["kamae", "furikaburi", "cut", "zanshin"], "time", None)
    # the same dossier's calm procedural candidate hits at 0.53 s: by time its wind and its Hit both read 'zanshin'
    moments = [0.0, 0.35, 0.5333, 0.75, 1.0833]
    assert [PD.phase_at(KESA, t) for t in moments] == ["kamae", "zanshin", "zanshin", None, None]
    names, how, why = PD.phases_for(KESA, moments, 0.5333)
    assert how == "order" and names == ["kamae", "furikaburi", "cut", "zanshin", "zanshin"]
    assert "its Hit at 0.53 s falls in the dossier's 'zanshin', not its 'cut'" in why
    # more poses before the Hit than phases: counted back from the Hit, the earliest are the first phase
    assert PD.phases_for(KESA, [0.0, 0.2, 0.3, 0.45, 0.6], 0.6)[0] == ["kamae", "kamae", "kamae", "furikaburi", "cut"]
    # a dossier with its own 'contact' moment (a kick): that is the hit phase, whatever the swing is called
    kick = {"phases": [{"name": "guard", "game_s": [0.0, 0.1]}, {"name": "swing (chamber + extension)", "game_s": [0.1, 0.42]},
                       {"name": "contact", "game_s": [0.42, 0.42]}, {"name": "recoil", "game_s": [0.42, 0.8]}]}
    assert PD.hit_phase(kick) == "contact"
    assert PD.phases_for(kick, [0.0, 0.18, 0.48, 0.9], 0.48)[0] == ["guard", "swing (chamber + extension)", "contact", "recoil"]
    # no Hit, or a dossier that names no blow (a walk): by time, nothing guessed
    walk = {"phases": [{"name": "left step", "game_s": [0.0, 0.4]}, {"name": "right step", "game_s": [0.4, 0.8]}]}
    assert PD.hit_phase(walk) is None and PD.phases_for(walk, [0.0, 0.4], 0.2)[1] == "time"
    assert PD.phases_for(KESA, moments, None)[1] == "time"


def test_a_phase_named_in_order_gets_the_frame_that_phase_arrives_at(tmp_path):
    from PIL import Image
    a, b = str(tmp_path / "early.png"), str(tmp_path / "late.png")
    for p in (a, b):
        Image.new("RGB", (8, 8)).save(p)
    d = dict(KESA, reference_frames=[{"phase": "cut", "image": a, "game_t": 0.2}, {"phase": "cut", "image": b, "game_t": 0.31}])
    assert PD.reference_for(d, 0.5333, phase="cut")[1]["image"] == b     # (0.53 s is not in the dossier's cut: its end)
    assert PD.reference_for(d, 0.2, phase="cut")[1]["image"] == a        # (inside it: the nearest, as by time)
    phase, ref, why = PD.reference_for(d, 0.35, phase="furikaburi")
    assert phase == "furikaburi" and ref is None and "phase 'furikaburi'" in why
    assert PD.reference_for(d, 0.35, phase=None)[2].startswith("no phase of the dossier covers")


def test_plan_says_when_phases_were_counted_in_order(tmp_path):
    clip = clip_of()                                            # its Hit at 0.33 s
    late = {"phases": [{"name": "guard", "game_s": [0.0, 0.0]}, {"name": "wind", "game_s": [0.0, 0.1]},
                       {"name": "cut", "game_s": [0.1, 0.2]}, {"name": "hold", "game_s": [0.2, 0.4]}]}
    pl = PS.plan("SheetProbe", clip, None, "late", late)        # no authored keys: the clip's own marks
    assert pl["phase_by"] == "order" and "not its 'cut'" in pl["phase_note"]
    hit = next(k for k in pl["keys"] if abs(k["t"] - 0.3333) < 0.01)
    assert hit["phase"] == "cut" and pl["keys"][0]["phase"] == "guard" and pl["keys"][-1]["phase"] == "hold"
    timed = PS.plan("SheetProbe", clip, MOVE, "probe", {"phases": PHASES})
    assert timed["phase_by"] == "time" and timed["phase_note"] is None
    m = {"folder": "f", "keys": [1], "key_views": ["player"], "key_size": 768, "dossier": "late", "strips": [],
         "reference": {"have": 0, "gaps": []}, "phase_by": "order"}
    assert "counted in order round the Hit" in PS.look_line(m)
    assert PS.dossier_of("Any", None, str(tmp_path), None, {"dossier": "from_the_clip"}) == (None, None)   # named, not there


# ---------------------------------------------------------------- which frames
def test_key_times_are_the_moves_keys_then_the_clips_own_marks():
    clip = clip_of()
    assert T.key_times(clip, MOVE) == [0.0, 0.2, 0.4]
    own = T.key_times(clip, None)                               # its events: Swing, ActiveStart 0.3167, Hit 0.3333, ActiveEnd
    assert 0.3333 in own and 0.3167 not in own                   # of two marks a frame apart, the Hit is the pose
    marked = dict(clip, events=[{"name": "Hit", "t": 0.3}], beats={"anticipation": [0.0, 0.2], "strike": [0.2, 0.4]})
    assert T.key_times(marked, None) == [0.0, 0.2, 0.3, 0.4]    # start, the beats' borders, the Hit, the end
    bare = dict(clip, events=[], beats=None)
    assert T.key_times(bare, None) == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])
    close = {"keys": [{"t": 0.0}, {"t": 0.2}, {"t": 0.21}, {"t": 0.4}]}
    assert T.key_times(clip, close) == [0.0, 0.2, 0.4]          # two keys a frame apart are one pose
    many = {"keys": [{"t": round(k * 0.02, 2)} for k in range(21)]}
    thin = T.key_times(clip, many, limit=6)
    assert len(thin) == 6 and thin[0] == 0.0 and thin[-1] == 0.4


def test_a_move_without_authored_keys_is_looked_at_where_it_stops():
    slow = json.loads(json.dumps(MOVE))                         # the same cut over 1.2 s: wind, cut, back to the guard
    slow["keys"] = [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.4, yaw=30, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                    dict(KEY, t=0.8, yaw=-30, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8]), dict(KEY, t=1.2, yaw=0)]
    clip = S.generate(slow)[0]
    assert PS.key_moments(clip, slow) == [0.0, 0.4, 0.8, 1.2]    # authored keys: those, nothing added
    hit_only = dict(clip, events=[{"name": "Hit", "t": 0.7}], beats=None)     # what a procedural candidate carries
    stops = PS.extremes(hit_only)
    assert len(stops) == 2 and abs(stops[0] - 0.4) < 0.06 and abs(stops[1] - 0.8) < 0.06     # the wind's top, the cut's end
    moments = PS.key_moments(hit_only, None)
    assert moments[0] == 0.0 and moments[-1] == pytest.approx(1.2) and 0.7 in moments and len(moments) == 5
    assert moments == sorted(moments)
    near = dict(clip, events=[{"name": "Hit", "t": stops[0] + 0.05}], beats=None)
    assert stops[0] not in PS.key_moments(near, None)           # an extreme beside a mark is that mark's pose
    still = dict(clip, joints={j: {"frames": [v["frames"][0]] * len(v["frames"])} for j, v in clip["joints"].items()})
    still.pop("sword")
    assert PS.extremes(still) == []                             # nothing moves: no extremes, never a crash


def test_strip_frames_are_twelve_a_second():
    clip = clip_of()                                            # 60 fps, 0.4 s -> 25 frames
    assert PS.strip_frames(clip) == [0, 5, 10, 15, 20]
    assert PS.strip_frames(clip, rate=60) == list(range(25))
    assert PS.frame_of(clip, 0.2) == 12 and PS.frame_of(clip, 9.0) == 24


# ---------------------------------------------------------------- cameras
def test_camera_fit_fills_the_picture_with_what_it_is_given():
    rig = C.load_rig("r6")
    pts = body_points(C.fk(rig), rig)
    for view in ("player", "side", "front", "top"):
        for size in ((768, 768), (820, 512), (410, 512)):
            cam = PS.camera_fit(PS.VIEW_DIRS[view], pts, size[0] / size[1], ortho=view in PS.VIEW_ORTHO)
            pix, depth = PS.project(cam, pts, size)
            assert (depth > 0).all()
            assert pix[:, 0].min() >= 0 and pix[:, 0].max() <= size[0] and pix[:, 1].min() >= 0 and pix[:, 1].max() <= size[1]
            fill = max(np.ptp(pix[:, 0]) / size[0], np.ptp(pix[:, 1]) / size[1])
            assert 0.86 <= fill <= 0.90, (view, size, fill)     # 1 / 1.12: the body as large as the margin allows
            centre = (pix.min(0) + pix.max(0)) / 2
            assert abs(centre[0] - size[0] / 2) < 1.0 and abs(centre[1] - size[1] / 2) < 1.0
            assert cam["tan"][0] / cam["tan"][1] == pytest.approx(size[0] / size[1])


def test_views_look_the_way_their_titles_say():
    here = np.array([[0.0, 0.0, 0.0]])
    for view, right, up in (("player", [1, 0, 0], [0, 0, 1]), ("side", [0, 1, 0], [0, 0, 1]),
                            ("top", [1, 0, 0], [0, 1, 0]), ("front", [-1, 0, 0], [0, 0, 1])):
        cam = PS.camera_fit(PS.VIEW_DIRS[view], np.array([[-1, -1, -1], [1, 1, 1]], float), ortho=view in PS.VIEW_ORTHO)
        o = PS.project(cam, here, (100, 100))[0][0]
        assert PS.project(cam, here + np.array(right, float), (100, 100))[0][0][0] > o[0] + 5, view    # the picture's right
        assert PS.project(cam, here + np.array(up, float), (100, 100))[0][0][1] < o[1] - 5, view       # the picture's top
    # the rig faces +y in its file: from the side it faces right, from above it faces up the picture (the titles)


def test_the_plan_view_has_no_parallax_and_the_others_do():
    pts = np.array([[-2, -2, 0], [2, 2, 6]], float)
    com, floor = np.array([[0.7, 0.3, 3.0]]), np.array([[0.7, 0.3, 0.0]])
    top = PS.camera_fit(PS.VIEW_DIRS["top"], pts, ortho=True)
    assert np.allclose(PS.project(top, com, (768, 768))[0], PS.project(top, floor, (768, 768))[0], atol=1e-6)
    persp = PS.camera_fit(PS.VIEW_DIRS["top"], pts, ortho=False)
    assert np.linalg.norm(PS.project(persp, com, (768, 768))[0] - PS.project(persp, floor, (768, 768))[0]) > 5
    assert PS.lens_of({"tan": [0.36, 0.2]}) == pytest.approx(50.0)     # Blender's default lens on its 36 mm sensor
    behind = PS.project(persp, np.array(persp["loc"]) + np.array(persp["back"]) * 2.0, (10, 10))[1]
    assert behind[0] < 0                                        # behind the camera: never drawn


def test_a_strip_keeps_the_body_large_under_a_long_blade():
    rig = C.load_rig("r6")
    body = body_points(C.fk(rig), rig)
    sweep = np.array([[x, -6.0, 3.0] for x in np.linspace(-30, 30, 13)])     # a path 60 studs wide
    held = PS.strip_points(PS.VIEW_DIRS["player"], body, sweep)
    r, u, _ = PS.camera_basis(PS.VIEW_DIRS["player"])
    tall = max(np.ptp(body @ r), np.ptp(body @ u))
    assert np.ptp(held @ r) == pytest.approx(tall * PS.STRIP_HOLD[0])      # pulled onto the border, not dropped
    assert len(held) == len(body) + len(sweep)
    w, h = PS.strip_size(PS.VIEW_DIRS["player"], held)
    assert [w, h] == [820, 512]                                 # as wide as a strip frame gets, never taller
    assert PS.strip_size(PS.VIEW_DIRS["player"], body) == [420, 512]        # a body alone, as the player sees it
    assert PS.strip_size(PS.VIEW_DIRS["side"], body) == [410, 512]          # ... and from the side: the narrowest
    ahead = np.array([[0.0, y, 3.0] for y in np.linspace(-30, 30, 13)])     # a sweep fore and aft, seen from the side
    assert PS.strip_size(PS.VIEW_DIRS["side"], PS.strip_points(PS.VIEW_DIRS["side"], body, ahead)) == [820, 512]
    cam = PS.camera_fit(PS.VIEW_DIRS["player"], held, w / h, margin=1.08)
    tall = np.ptp(PS.project(cam, body, (w, h))[0][:, 1])
    whole = PS.camera_fit(PS.VIEW_DIRS["player"], np.concatenate([body, sweep]), w / h, margin=1.08)
    assert tall > 2.5 * np.ptp(PS.project(whole, body, (w, h))[0][:, 1])       # (the whole sweep: a speck of a body)
    assert np.array_equal(PS.strip_points(PS.VIEW_DIRS["side"], body, np.zeros((0, 3))), body)


# ---------------------------------------------------------------- what is drawn
def test_weight_is_over_the_feet_outside_them_or_airborne():
    rig = C.load_rig("r6")
    W = C.fk(rig)
    w = PS.weight(W, rig)
    assert w["down"] == ["Right", "Left"] and w["outside"] == 0.0 and len(w["support"]) == 4
    assert PS.weight_words(w) == "weight: over the right + left feet"
    assert all(abs(p[1] - PA.GROUND) < 1e-9 for p in w["support"])
    lean = {k: v.copy() for k, v in W.items()}
    for part in ("Torso", "Head", "Right Arm", "Left Arm"):
        lean[part][2, 3] -= 2.5                                 # the upper body 2.5 studs forward of planted feet
    w2 = PS.weight(lean, rig)
    assert w2["outside"] > 1.0 and "OUTSIDE the right + left feet" in PS.weight_words(w2)
    one = {k: v.copy() for k, v in W.items()}
    one["Left Leg"][1, 3] += 1.0                                # the left foot lifted: the support is one sole
    w3 = PS.weight(one, rig)
    assert w3["down"] == ["Right"] and len(w3["support"]) == 4
    assert w3["outside"] == 0.0 and PS.weight_words(w3) == "weight: over the right foot"   # (on that sole's inner edge)
    for part in ("Torso", "Head", "Right Arm", "Left Arm"):
        one[part][0, 3] -= 1.5                                  # ... and the upper body leaning away from it
    w3 = PS.weight(one, rig)
    assert w3["outside"] > 0.5 and "OUTSIDE the right foot" in PS.weight_words(w3)
    air = {k: v.copy() for k, v in W.items()}
    for part in air:
        air[part][1, 3] += 2.0
    w4 = PS.weight(air, rig)
    assert w4["outside"] is None and w4["support"] == [] and "airborne" in PS.weight_words(w4)


def test_hull_gap_inside_outside_and_on_one_segment():
    square = [[0, 0], [2, 0], [2, 1], [0, 1]]
    assert PS.hull_gap([1, 0.5], square) == 0.0
    assert PS.hull_gap([3, 0.5], square) == pytest.approx(1.0)
    assert PS.hull_gap([1, 3], square[::-1]) == pytest.approx(2.0)     # either winding
    assert PS.hull_gap([1, 1], [[0, 0], [2, 0]]) == pytest.approx(1.0)
    assert PS.hull_gap([1, 1], []) is None


def test_paths_carry_the_blade_and_name_the_striker():
    clip = clip_of()
    frames = C.world_frames(clip, C.load_rig("r6"))
    pth = PS.paths(clip, frames)
    assert set(pth) == {"RightHand", "LeftHand", "RightFoot", "LeftFoot", "Grip", "BladeTip"}
    assert all(v.shape == (len(frames), 3) for v in pth.values())
    assert np.allclose(np.linalg.norm(pth["BladeTip"] - pth["Grip"], axis=1), np.linalg.norm(pth["BladeTip"][0] - pth["Grip"][0]), atol=0.2)
    assert PS.striker(pth, 60) == "BladeTip"
    bare = dict(clip)
    bare.pop("sword")
    unarmed = PS.paths(bare, frames)
    assert "BladeTip" not in unarmed and PS.striker(unarmed, 60) in ("RightHand", "LeftHand")   # the hands swing the cut
    g, t, _ = T.blade_line(clip, 3)
    assert np.allclose(t, pth["BladeTip"][3]) and T.blade_line(bare, 3) is None


# ---------------------------------------------------------------- the plan
def test_plan_gives_every_key_its_phase_and_its_reference_or_its_gap(tmp_path):
    clip, pl, _ = planned(tmp_path)
    assert [k["frame"] for k in pl["keys"]] == [0, 12, 24] and [k["k"] for k in pl["keys"]] == [1, 2, 3]
    assert [k["phase"] for k in pl["keys"]] == ["guard", "wind", "cut"]
    assert pl["keys"][1]["reference"]["source"] == "probe_footage" and pl["keys"][1]["reference_gap"] is None
    assert pl["keys"][1]["phase_body"] == "the blade cocked back at the right side"
    assert pl["keys"][0]["reference"] is None and "phase 'guard'" in pl["keys"][0]["reference_gap"]
    assert pl["key_views"] == ["player", "side", "top"] and pl["key_height"] == 768
    assert pl["strip_frames"] == [0, 5, 10, 15, 20] and pl["strip_views"] == ["player", "side"] and pl["strip_height"] == 512
    assert pl["dossier"] == "sheet_probe" and pl["inputs"] and pl["rig"] == "R6"
    none = PS.plan("SheetProbe", clip, MOVE, None, None, strips=False)
    assert none["dossier"] is None and none["strip_frames"] == [] and "no move dossier" in none["keys"][0]["reference_gap"]
    unknown = PS.plan("SheetProbe", clip, MOVE, "nowhere", None)
    assert "no dossier named nowhere" in unknown["keys"][0]["reference_gap"]
    front = PS.plan("SheetProbe", clip, MOVE, "d", {"phases": PHASES, "reference_frames": [
        dict(pl["keys"][1]["reference"], view="front")]})
    assert front["key_views"] == ["player", "side", "top", "front"]      # footage filmed from the front gets our front


def test_dossier_of_a_clip_named_or_from_its_move_or_its_own_name(tmp_path):
    anims = tmp_path / "animations"
    (anims / "dossiers").mkdir(parents=True)
    json.dump({"phases": PHASES}, open(anims / "dossiers" / "sheet_probe.json", "w"))
    json.dump({"phases": []}, open(anims / "dossiers" / "side_cut.json", "w"))
    assert PS.dossier_of("SheetProbe", None, str(anims))[0] == "sheet_probe"               # its own name, snake case
    assert PS.dossier_of("Other", {"dossier": "side_cut"}, str(anims))[0] == "side_cut"     # its move says
    json.dump({"dossier": "side_cut"}, open(anims / "Game.dossier.json", "w"))
    assert PS.dossier_of("Game", None, str(anims))[0] == "side_cut"                         # a game clip's spec says
    assert PS.dossier_of("Library", None, str(anims)) == (None, None)                        # a clip with none
    assert PS.dossier_of("Library", None, str(anims), "missing") == ("missing", None)        # asked for, not there


# ---------------------------------------------------------------- the pages
def test_pages_lay_the_move_out_and_say_what_is_missing(tmp_path):
    from PIL import Image
    clip, pl, folder = planned(tmp_path)
    frames, rig, key_cams = fake_render(folder, pl, clip)
    m = PS.pages(folder)
    sheet = Image.open(os.path.join(folder, "pose_sheet.png"))
    wide = m["key_panes"]                                        # a view's pane: 768 high, as wide as its widest pose
    assert all(wide[v][1] == 768 and 768 <= wide[v][0] <= 1228 for v in ("player", "side", "top"))
    assert sheet.width == 768 + sum(wide[v][0] for v in ("player", "side", "top")) + 3 * 4   # reference | player | side | above
    assert m["sheet_size"] == list(sheet.size) and sheet.height > 3 * 768
    assert [k["reference"] for k in m["keys"]] == [False, True, False] and m["reference"]["have"] == 1
    assert len(m["reference"]["gaps"]) == 2 and m["reference"]["gaps"][0].startswith("key 1 (guard)")
    assert len(m["pages"]) == 6 and all(os.path.isfile(os.path.join(folder, p["file"])) for p in m["pages"])
    for p in m["pages"]:                                         # two panes a page: opened at full size
        pair = (768 + wide["player"][0]) if "reference" in p["file"] else (wide["side"][0] + wide["top"][0])
        page = Image.open(os.path.join(folder, p["file"]))
        assert page.width == pair + 4 and page.height - 768 in (46, 70)     # its title: one line, or wrapped onto two
    assert m["pages"][2]["file"] == "keys/key_02_0p20s_reference_player.png"
    ref_page = Image.open(os.path.join(folder, m["pages"][2]["file"])).convert("RGB")
    assert ref_page.getpixel((384, ref_page.height - 384)) == (200, 30, 30)   # the dossier's frame, in the middle of its pane
    gap_page = Image.open(os.path.join(folder, m["pages"][0]["file"])).convert("RGB")
    assert gap_page.getpixel((384, gap_page.height - 40)) == (24, 25, 30)    # no frame: the gap is said, nothing is invented
    # drawn ON the render: the centre of mass, in the plan view, where the kit's own FK and camera put it
    top = Image.open(os.path.join(folder, "keys/key_02_0p20s_side_top.png")).convert("RGB")
    com = PS.to_blender(PA.com(frames[12]), ORIGIN)
    left = wide["side"][0] + 4                                   # (the plan view is the page's second pane)
    px, py = PS.project(key_cams["top"]["12"], com, wide["top"])[0][0]
    head = top.height - 768                                      # (the page's title bar above the panes)
    assert top.getpixel((int(round(left + px + 5)), int(round(head + py)))) == (255, 255, 255)   # (its white ring)
    pane = np.asarray(top.crop((left, head, left + wide["top"][0], head + 768)), int)
    assert 0.5 < float((pane == np.array(FLAT)).all(axis=2).mean()) < 0.999      # drawn ON the render, not over it
    # the strips: 12 a second, 512 px high, a page holds the frames that stay full size
    assert [s["file"] for s in m["strips"]] == ["strip_player.png", "strip_side.png"]
    for s in m["strips"]:
        assert s["frames"] == 5 and s["frame_size"][1] == 512 and 410 <= s["frame_size"][0] <= 820
        assert len(s["pages"]) == -(-5 // max(1, PS.PAGE_WIDTH // (s["frame_size"][0] + 4)))
        assert all(Image.open(os.path.join(folder, p)).width <= PS.PAGE_WIDTH for p in s["pages"])
    assert m["striker"] == "BladeTip" and m["overlays"] is True
    assert m["inputs"] == pl["inputs"] and len(m["inputs_sha256"]) == 64
    assert m["reference_files"] == {pl["keys"][1]["reference_file"]: True}
    assert json.load(open(os.path.join(folder, "look.json")))["look"] == m["look"]
    line = m["look"]
    assert line.startswith(f"LOOK: {folder.replace(os.sep, '/')}/ - pose_sheet.png (3 key pose(s) from player, side, top, 768 px each")
    assert "beside 1 of 3 reference frame(s) of dossier sheet_probe" in line
    assert "strip_player.png, strip_side.png (12 frames a second, 512 px a frame" in line
    assert "NO reference frame beside 2 key pose(s): key 1 (guard)" in line and "open keys/key_*.png" in line


def test_every_sheet_carries_its_timing_chart_and_its_reading(tmp_path):
    from PIL import Image
    clip, pl, folder = planned(tmp_path)
    fake_render(folder, pl, clip)
    m = PS.pages(folder)
    tm = m["timing"]
    assert tm["file"] == "timing.png" and Image.open(os.path.join(folder, "timing.png")).width > 900
    assert tm["words"].startswith("the blade tip gathers ") and "mismatch" not in tm["reading"]
    assert tm["reading"]["keys"] == len(pl["keys"]) and tm["reading"]["frames"] == len(clip["times"])
    assert f"; timing.png = the timing chart ({tm['words']})" in m["look"]
    assert json.load(open(os.path.join(folder, "look.json")))["timing"]["file"] == "timing.png"


def test_a_chart_that_cannot_be_drawn_is_said_and_leaves_no_old_picture(tmp_path, monkeypatch):
    import timing_chart as TC
    clip, pl, folder = planned(tmp_path)
    fake_render(folder, pl, clip)
    assert PS.pages(folder)["timing"]["file"] == "timing.png" and os.path.isfile(os.path.join(folder, "timing.png"))

    def broken(*a, **k):
        raise ValueError("no reading today")
    monkeypatch.setattr(TC, "read", broken)
    m = PS.pages(folder)                                         # the sheet is still made: the chart is a page of it
    assert m["timing"]["file"] is None and "could not be drawn (ValueError: no reading today)" in m["timing"]["words"]
    assert not os.path.isfile(os.path.join(folder, "timing.png")) and "; NO timing chart: " in m["look"]


def test_a_sheet_without_its_timing_chart_says_why():
    m = {"folder": "build/animations/X.sheet", "keys": [1], "key_views": ["player"], "key_size": 768, "dossier": None,
         "strips": [], "reference": {"have": 0, "gaps": []}, "overlays": True,
         "timing": {"file": None, "words": "the clip does not move: there is no spacing to chart"}}
    assert "; NO timing chart: the clip does not move" in PS.look_line(m)


def test_nothing_is_drawn_when_the_rig_is_not_where_the_fk_says(tmp_path):
    from PIL import Image
    clip, pl, folder = planned(tmp_path, strips=False)
    frames, rig, key_cams = fake_render(folder, pl, clip, fk_error=0.6)     # a hand-posed file: the FK would lie
    m = PS.pages(folder)
    assert m["overlays"] is False and "differ by 0.6 studs" in m["overlays_why"] and m["strips"] == []
    top = Image.open(os.path.join(folder, "keys/key_02_0p20s_side_top.png")).convert("RGB")
    px, py = PS.project(key_cams["top"]["12"], PS.to_blender(PA.com(frames[12]), ORIGIN), m["key_panes"]["top"])[0][0]
    assert top.getpixel((int(round(m["key_panes"]["side"][0] + 4 + px + 5)), int(round(top.height - 768 + py)))) == FLAT
    assert "nothing is drawn on the renders" in m["look"] and "strip_" not in m["look"]


def test_a_reference_pairs_with_the_view_it_was_filmed_like(tmp_path):
    clip, pl, folder = planned(tmp_path, strips=False, view="side")
    fake_render(folder, pl, clip)
    m = PS.pages(folder)
    files = [p["file"] for p in m["pages"]]
    assert "keys/key_02_0p20s_reference_side.png" in files and "keys/key_02_0p20s_player_top.png" in files
    assert "keys/key_01_0p00s_reference_player.png" in files      # a key with no frame: beside the player's camera


def test_a_reference_frame_is_read_from_a_video_cropped_and_mirrored(tmp_path):
    import cv2
    vid = str(tmp_path / "v.mp4")
    w = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for i in range(20):
        frame = np.zeros((48, 64, 3), np.uint8)
        frame[:, :32] = (0, 0, 250)                              # BGR: the left half red
        w.write(frame)
    w.release()
    im = PS.reference_image({"video": vid, "t": 1.0})
    assert im.size == (64, 48) and im.getpixel((8, 24))[0] > 200 and im.getpixel((56, 24))[0] < 50
    assert PS.reference_image({"video": vid, "t": 1.0, "flip": True}).getpixel((56, 24))[0] > 200
    assert PS.reference_image({"video": vid, "t": 1.0, "crop": [0.5, 0.0, 1.0, 1.0]}).size == (32, 48)
    assert PS.reference_image({"image": str(tmp_path / "none.png")}) is None
    pane, shown = PS.reference_pane({"reference": {"video": vid, "t": 1.0, "note": "n"}, "phase": "cut"}, "d", 768)
    assert shown and pane.size == (768, 768)
    pane, shown = PS.reference_pane({"reference": None, "reference_gap": "none named", "phase": "cut"}, "d", 768)
    assert not shown and pane.size == (768, 768)


def test_look_line_names_the_folder_the_sheet_and_the_gaps():
    m = {"folder": "build/animations/X.sheet", "keys": [1, 2], "key_views": ["player", "side", "top"], "key_size": 768,
         "dossier": None, "strips": [], "reference": {"have": 0, "gaps": []}, "overlays": True}
    assert PS.look_line(m) == ("LOOK: build/animations/X.sheet/ - pose_sheet.png (2 key pose(s) from player, side, top, "
                               "768 px each; no move dossier, so nothing to look at them beside); open keys/key_*.png "
                               "for every pose at full size")
    assert PS.look_line(None) == ""


def test_the_sheet_says_how_faithful_the_rig_drawn_is_to_the_clip():
    """the fidelity line (the owner's V3 list, anim stage A.3; card 6wyz): the measured distance between the kit's FK
    and the rig's meshes is said on the build's LOOK line and in the strip's legend, not only kept in look.json"""
    m = {"folder": "build/animations/X.sheet", "keys": [1, 2], "key_views": ["player"], "key_size": 768, "dossier": None,
         "strips": [], "reference": {"have": 0, "gaps": []}, "overlays": True, "overlay_error_studs": 0.0123}
    assert PS.look_line(m).endswith("; the rig drawn = the clip within 0.012 studs")
    assert "not measured" in PS.fidelity_words(None)
    off = dict(m, overlays=False, overlays_why="0.4 studs apart")
    assert "within" not in PS.look_line(off) and "nothing is drawn on the renders (0.4 studs apart)" in PS.look_line(off)
    seen = []
    import PIL.ImageDraw as D
    real = D.ImageDraw.text
    def spy(self, xy, text, *a, **k):
        seen.append(text)
        return real(self, xy, text, *a, **k)
    D.ImageDraw.text = spy
    try:
        PS._legend(2000, list(PS.PATH_COLOUR)[:1], True, None, 0.0123)
    finally:
        D.ImageDraw.text = real
    assert any("the rig drawn = the clip within 0.012 studs" in t for t in seen)


def test_plan_and_pages_as_commands(tmp_path, capsys, monkeypatch):
    clip = clip_of()
    build = tmp_path / "build"
    (build / "animations").mkdir(parents=True)
    json.dump(clip, open(build / "animations" / "SheetProbe.clip.json", "w"))
    monkeypatch.setenv("KIT_BUILD", str(build))
    out = str(tmp_path / "sheet")
    assert PS.main(["plan", "SheetProbe", "--out", out, "--anims", str(tmp_path / "anims")]) == 0
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert said["status"] == "pass" and "no move dossier" in said["summary"]
    pl = json.load(open(os.path.join(out, "plan.json")))
    assert len(pl["keys"]) >= 3 and "kit/anim/pose_sheet.py" in pl["inputs"]       # no move file: the clip's own marks
    assert PS.main(["pages", out]) == 1                          # not rendered yet: it says so
    assert "no render.json" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert PS.main(["plan", "Nothing", "--out", out]) == 1
    assert "no built clip" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    r15 = dict(clip, rig="R15")
    json.dump(r15, open(build / "animations" / "Fifteen.clip.json", "w"))
    assert PS.main(["plan", "Fifteen", "--out", out]) == 1
    assert "rendered on the owner's R6 rig" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    fake_render(out, pl, clip)
    assert PS.main(["pages", out]) == 0
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert said["status"] == "pass" and said["look"].startswith("LOOK: ") and said["next_action"].startswith("look at ")
    # a clip with no dossier at all: no empty reference column, no list of gaps - only that there is none
    m = json.load(open(os.path.join(out, "look.json")))
    assert m["dossier"] is None and m["reference"] == {"have": 0, "of": len(m["keys"]), "gaps": []}
    assert not any("reference" in p["file"] for p in m["pages"]) and "NO reference frame" not in m["look"]
    assert m["sheet_size"][0] == sum(m["key_panes"][v][0] for v in m["key_views"]) + 4 * (len(m["key_views"]) - 1)


# ---------------------------------------------------------------- the real rig (a smoke case: Blender + the owner's rig)
def _blender():
    try:
        import cad_check
        return cad_check.blender()
    except Exception:
        return None


RIG = os.path.join(ROOT, "assets", "rigs", "R6_IK.blend")


@pytest.mark.skipif(not (_blender() and os.path.isfile(str(_blender())) and os.path.isfile(RIG)),
                    reason="Blender or the owner's R6 rig (assets/rigs/R6_IK.blend) not found")
def test_the_rig_is_rendered_where_the_kit_draws(tmp_path):
    from PIL import Image
    clip, pl, folder = planned(tmp_path)
    r = subprocess.run([_blender(), "-b", RIG, "--disable-autoexec", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "anim", "look_r6.py"), "--", "SheetProbe.r6", "--clip", pl["clip"],
                        "--out", folder, "--sheet", os.path.join(folder, "plan.json")],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout or r.stderr)[-1500:]
    rn = json.load(open(os.path.join(folder, "render.json")))
    assert rn["projection_error_px"] < 1.0                       # the kit's camera maths = Blender's own
    assert rn["overlay_error_studs"] < 0.02                      # the kit's FK = where the rig's meshes are
    assert rn["key"]["cams"]["top"]["12"]["ortho"] is True and rn["key"]["cams"]["player"]["12"]["ortho"] is False
    for view in pl["key_views"]:                                 # a view's pane: 768 px high, as wide as its widest pose
        w, h = rn["key"]["size"][view]
        assert h == 768 and 768 <= w <= 1228 and w % 2 == 0
        for key in pl["keys"]:
            assert Image.open(os.path.join(folder, "frames", f"key_{view}_{key['frame']:04d}.png")).size == (w, h)
    for view in pl["strip_views"]:
        w, h = rn["strip"]["size"][view]
        assert h == 512 and 410 <= w <= 820
        assert Image.open(os.path.join(folder, "frames", f"strip_{view}_0010.png")).size == (w, h)
    # the body is LARGE in a key pose: from the side the figure spans most of the pane's height (it was a third)
    side = np.asarray(Image.open(os.path.join(folder, "frames", "key_side_0012.png")).convert("RGB"), int)
    rows = np.where((np.abs(side - side[4, 4]).sum(axis=2) > 60).sum(axis=1) > 12)[0]
    m = PS.pages(folder)
    assert m["overlays"] is True and os.path.getsize(os.path.join(folder, "pose_sheet.png")) > 100_000
    assert len(rows) and (rows.max() - rows.min()) > 0.55 * 768
