"""Tests for the procedural R6 animator (kit/anim/proc_r6, proc_gait, proc_gates, proc_calib, proc_director) - each pins a
bug found 2026-10-13/14: the cubic bulging past its keys, the pacing gait, the statue gate that never fired, shake that
exploded on still clips, a gesture that did not reach its hand target."""
import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import proc_r6 as P  # noqa: E402

J = P.JOINTS


def pose_turned(joint=None, rv=(0.0, 0.0, 0.0)):
    p = {j: [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for j in J}
    if joint:
        p[joint][:4] = list(map(float, P.q_exp(np.asarray(rv, float))))
    return p


def clip_of(q):
    """q [T, 6, 4] -> a clip (no slides)"""
    return {"schema": 1, "name": "t", "rig": "R6", "fps": 60, "loop": False, "times": [i / 60 for i in range(len(q))], "events": [],
            "joints": {j: {"frames": [list(map(float, q[t, k])) + [0.0, 0.0, 0.0] for t in range(len(q))]} for k, j in enumerate(J)}}


class KeyCurve(unittest.TestCase):
    def test_fast_rise_into_long_hold_does_not_bulge(self):
        """Fritsch-Carlson limit: a key reached in 0.2 s then HELD to 2.0 s must not swing past it (it bulged above the
        head before the fix)"""
        up = pose_turned("Left Arm", (math.radians(60), 0.0, 0.0))
        K = [{"q": np.array([k["pose"][j][:4] for j in J]), "p": np.zeros((6, 3)), "t": k["t"], "stiff": 1.0}
             for k in ({"pose": pose_turned(), "t": 0.0}, {"pose": up, "t": 0.2}, {"pose": up, "t": 2.0})]
        curve = P.key_curve(K, False, None)
        worst = 0.0
        for t in np.linspace(0.2, 2.0, 90):
            q = curve(t)[0][J.index("Left Arm")]
            worst = max(worst, math.degrees(2 * math.acos(min(1.0, abs(q[3])))))
        self.assertLess(worst, 61.0)


class Tracking(unittest.TestCase):
    def test_follow_zero_tracks_the_curve(self):
        """interp='hermite' with follow 0 lands on the keys (the springs only smooth switches)"""
        a, b = pose_turned("Right Leg", (math.radians(30), 0, 0)), pose_turned("Right Leg", (math.radians(-30), 0, 0))
        keys = [{"pose": a, "t": 0.0}, {"pose": b, "t": 0.5}, {"pose": a, "t": 1.0}]
        c = P.sim(keys, 1.0, {"follow": {j: 0.0 for j in J}}, loop=True, plant=False, settle=2.0, interp="hermite")
        fr = np.array([f[:4] for f in c["joints"]["Right Leg"]["frames"]])
        ang = np.degrees(2 * np.arccos(np.clip(np.abs(fr[:, 3]), -1, 1)))
        self.assertGreater(ang.max(), 28.0)                  # reaches the +-30 keys (the step mode reached ~74 %)


class Gait(unittest.TestCase):
    def test_arms_swing_against_their_own_leg(self):
        import proc_director as DR
        import proc_gait as PG
        for kind in PG.GAITS:                                # every gait profile, incl. jog / sprint / sneak
            ks, _ = PG.keys(kind)
            pr = next(k["pose"] for k in ks if k.get("name") == "contactR")
            pl = next(k["pose"] for k in ks if k.get("name") == "contactL")
            # RELATIVE to the other contact (a sneak carries both arms forward): at the right contact the right leg is
            # further forward and the right arm further BACK than at the left contact (a pacing gait failed this)
            self.assertLess(DR.end(pr, "Right Leg")[2], DR.end(pl, "Right Leg")[2] - 0.3, kind)
            self.assertGreater(DR.end(pr, "Right Arm")[2], DR.end(pl, "Right Arm")[2] + 0.2, kind)
            ts = [k["t"] for k in ks]
            self.assertEqual(ts, sorted(ts))
            self.assertTrue(all(np.allclose(ks[0]["pose"][j], ks[-1]["pose"][j]) for j in J))   # the loop closes


class Gates(unittest.TestCase):
    def test_statue_and_shake(self):
        import proc_calib as PC
        import proc_gates as G
        n = 120
        still = np.tile(np.array([0, 0, 0, 1.0]), (n, 6, 1))
        self.assertFalse(G.check(clip_of(still), "idle")["statue"]["pass"])
        swing = still.copy()
        for t in range(n):
            swing[t, 2] = P.q_exp(np.array([math.radians(25) * math.sin(2 * math.pi * t / 60), 0, 0]))
        self.assertTrue(G.check(clip_of(swing), "idle")["statue"]["pass"])
        smooth = still.copy()
        noisy = still.copy()
        rs = np.random.default_rng(0)
        for t in range(n):
            smooth[t, 1] = P.q_exp(np.array([0, math.radians(20) * math.sin(2 * math.pi * t / 90), 0]))
            noisy[t, 1] = P.q_exp(np.array([0, math.radians(20) * math.sin(2 * math.pi * t / 90) + math.radians(3) * rs.standard_normal(), 0]))
        self.assertLess(PC.shake(smooth), 0.3)
        self.assertGreater(PC.shake(noisy), PC.shake(smooth) * 3)


class Director(unittest.TestCase):
    def test_pose_from_reaches_the_hand_target(self):
        import proc_director as DR
        base = DR.stance(+1)
        target = np.array([0.1, 0.15, -1.6])
        p = DR.pose_from(base, {"targets": {"Left Arm": list(target), "Right Arm": "rest"}})
        c0, _ = DR.geom()["Left Arm"]
        got = DR.end(p, "Left Arm") - c0 - np.array(p["Left Arm"][4:7])
        want = target - c0 - np.array(p["Left Arm"][4:7])
        cosang = got @ want / np.linalg.norm(got) / np.linalg.norm(want)
        self.assertGreater(cosang, math.cos(math.radians(2)))


class FootLock(unittest.TestCase):
    def test_inplace_lock_plants_feet_and_keeps_the_seam(self):
        """lock_feet_inplace + re-closing the loop: a walk's planted feet move at the ground speed (skate < 0.02
        studs/frame vs 0.046 free) and the loop still joins (< 0.5 deg)"""
        import clip as C
        import proc_director as DR
        import proc_gait as PG
        ks, g = PG.keys("walk")
        c = P.sim(ks, g["period"], {"follow": {j: 0.5 for j in J}}, loop=True, plant=False, settle=2.0, interp="hermite")
        for j in J:
            c["joints"][j]["frames"] = c["joints"][j]["frames"][:-1]
        c["times"] = c["times"][:-1]
        q, p = DR.arrays(c)
        n = len(q)
        rv = [P.q_log(P.q_mul(q[0, k], P.q_inv(q[-1, k]))) / n for k in range(6)]
        for f in range(n):                                   # closed BEFORE the lock (as the builders do) - the seam is
            for k in range(6):                               # then measured on the lock's own output, never re-smoothed
                q[f, k] = P.q_mul(P.q_exp(rv[k] * f), q[f, k])
        c = DR.set_arrays(c, q, p)
        c["loop"] = True
        # the loved R6 slide ranges the kit's gaits are pinned within (2026-10-16: the walk now SLIDES its legs like
        # loved R6 - up to ~1.2 studs - so the old arbitrary +-0.6 fixture range could not hold a planted foot; the
        # assertion below is unchanged)
        import proc_kick as PK
        rng = PK.slide_ranges()
        c, speed = DR.lock_feet_inplace(c, rng, [0, 0, -1])
        c["locomotion"] = {"speed": round(speed, 3), "direction": [0, 0, -1]}
        m = C.metrics(c, C.load_rig("r6"))
        self.assertGreater(speed, 1.0)
        self.assertLess(m["feet"]["skate_max_studs_frame"], 0.02)
        self.assertIn("loop_seam_deg", m)
        self.assertLess(m["loop_seam_deg"], 0.5)


class Physics(unittest.TestCase):
    def test_mujoco_model_matches_the_engine_skeleton(self):
        """the 6-box MuJoCo R6 (proc_physics) puts every part exactly where kit/anim/clip.py fk does - incl. limb slides
        (ignoring them was 0.54 studs off on a run)"""
        try:
            import mujoco
        except ImportError:
            self.skipTest("mujoco not installed")
        import clip as C
        import proc_physics as PH
        n = 20
        q = np.tile(np.array([0, 0, 0, 1.0]), (n, 6, 1))
        for t in range(n):
            q[t, 2] = P.q_exp(np.array([math.radians(40) * math.sin(t / 3), 0, 0.2]))
            q[t, 5] = P.q_exp(np.array([0.3, 0.1 * t / n, 0]))
        c = clip_of(q)
        for t in range(n):
            c["joints"]["Right Leg"]["frames"][t][4:7] = [0.0, 0.3 * t / n, 0.0]   # a limb slide
        m, rig = PH.model()
        d = mujoco.MjData(m)
        Q, W = PH.qpos_frames(c)
        err = 0.0
        for t in range(n):
            d.qpos[:] = Q[t]
            mujoco.mj_kinematics(m, d)
            for part in PH.PARTS:
                g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, part)
                err = max(err, float(np.linalg.norm(d.geom_xpos[g] - np.asarray(W[t][part])[:3, 3])))
        self.assertLess(err, 1e-6)


class HitReaction(unittest.TestCase):
    def test_react_is_identity_without_hits_and_moves_with_one(self):
        """proc_physics.react layers the with-hit minus without-hit difference on the clip: no hit = the clip itself
        (the PD tracking lag cancels); a chest push shoves the body back"""
        try:
            import mujoco  # noqa: F401
        except ImportError:
            self.skipTest("mujoco not installed")
        import proc_physics as PH
        n = 90
        q = np.tile(np.array([0, 0, 0, 1.0]), (n, 6, 1))
        for t in range(n):
            q[t, 2] = P.q_exp(np.array([0.3 * math.sin(t / 10), 0, 0.1]))
        c = clip_of(q)
        same, _ = PH.react(c, [])
        a = np.array([f[:4] for j in J for f in c["joints"][j]["frames"]])
        b = np.array([f[:4] for j in J for f in same["joints"][j]["frames"]])
        self.assertLess(float(np.abs(np.abs(np.einsum("fi,fi->f", a, b)) - 1).max()), 1e-5)
        hit, disp = PH.react(c, [{"t": 0.5, "part": "Torso", "dir": [0, 0, 1], "speed": 12.0}])
        self.assertGreater(disp, 0.3)


class Dossier(unittest.TestCase):
    def test_a_move_is_not_built_without_its_research(self):
        """owner 2026-10-14: research the move before building it - proc_dossier.require refuses a missing or thin
        dossier, and the roundhouse dossier is complete and measurable"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        import json
        import tempfile
        import proc_dossier as DS
        with self.assertRaises(SystemExit):
            DS.require("no_such_move_ever")
        d = DS.require("roundhouse_kick")
        thin = dict(d, sources=d["sources"][:1])
        old = DS.DIR
        with tempfile.TemporaryDirectory() as tmp:
            json.dump(thin, open(os.path.join(tmp, "thin.json"), "w", encoding="utf-8"))
            DS.DIR = tmp
            try:
                with self.assertRaises(SystemExit):
                    DS.require("thin")
            finally:
                DS.DIR = old
        self.assertTrue(all(c["measure"] in DS.MEASURES for c in d["checks"]))


class StyleBand(unittest.TestCase):
    def test_a_sluggish_walk_fails_and_a_real_one_passes(self):
        """style_band: the whole-body motion inside the loved category's band (loved min x 0.8 .. max x 1.25, >= 30
        loved clips). Our walk passes; the same walk shrunk to 10 % of its motion fails as 'sluggish'; idle (10 loved
        clips) is report-only"""
        import proc_gait as PG
        import proc_gates as G
        ks, g = PG.keys("walk")
        c = P.sim(ks, g["period"], {"follow": {j: 0.5 for j in J}}, loop=True, plant=False, settle=2.0, interp="hermite")
        ok = G.check(c, "locomotion")["style_band"]
        self.assertTrue(ok["pass"], ok)
        q = np.array([[f[:4] for f in c["joints"][j]["frames"]] for j in J]).transpose(1, 0, 2)
        small = np.array([[P.q_exp(0.1 * P.q_log(q[t, k])) for k in range(6)] for t in range(len(q))])
        slow = G.check(clip_of(small), "locomotion")["style_band"]
        self.assertFalse(slow["pass"], slow)
        self.assertEqual(slow["why"], "sluggish")
        self.assertIn("report_only", G.check(clip_of(small), "idle")["style_band"])


class Candidates(unittest.TestCase):
    def test_sliders_keep_keys_ordered_and_lineage_is_ours_only(self):
        """kit anim candidates (proc_candidates): every slider setting keeps the keys in time order; a candidate's
        lineage holds ONLY the dossier and our own candidate ids - never a catalog clip (mission 04-anim 5.6); a round
        breeds only from picks of the round before"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        import json
        import re
        import proc_candidates as PCA
        import proc_dossier as DS
        import proc_kick as PK
        base = PK.carry(DS.require("roundhouse_kick")["build"]["keys"])
        rs = np.random.default_rng(1)
        for _ in range(40):
            s = {k: float(rs.uniform(-1, 1)) for k in PCA.SLIDERS}
            ts = [k["t"] for k in PCA.apply_sliders(base, s)]
            self.assertTrue(all(b > a for a, b in zip(ts, ts[1:])), s)
        strong = {k["name"]: k for k in PCA.apply_sliders(base, {"time": 0, "weight": 1, "space": 0, "flow": 0})}
        light = {k["name"]: k for k in PCA.apply_sliders(base, {"time": 0, "weight": -1, "space": 0, "flow": 0})}
        self.assertGreater(strong["contact"]["kick"][0], light["contact"]["kick"][0])
        path = os.path.join("assets", "animations", "candidates", "Roundhouse", "round_0.json")
        if os.path.exists(path):
            man = json.load(open(path, encoding="utf-8"))
            self.assertGreaterEqual(len(man["candidates"]), 4)
            for c in man["candidates"]:
                for item in c["lineage"]:
                    self.assertRegex(item, r"^(dossier:[a-z0-9_]+|Roundhouse/r\d+/c\d+)$")
        with self.assertRaises(SystemExit) as e:                      # overwrite: reach the parent check (it refuses first)
            PCA.make("Roundhouse", "roundhouse_kick", n=1, rnd=1, parents=["s12177921457_3"], overwrite=True)  # a catalog id
        self.assertIn("breed only from picks", str(e.exception))

    def test_a_round_the_owner_picked_from_is_never_overwritten(self):
        """2026-10-16: `--fresh` with no --round rebuilt round 0 - the round the owner had picked from - in place"""
        import proc_candidates as PCA
        if not os.path.isfile(os.path.join("assets", "animations", "candidates", "Roundhouse", "round_0.json")):
            self.skipTest("no Roundhouse round 0 in this checkout")
        with self.assertRaises(SystemExit) as e:
            PCA.make("Roundhouse", "roundhouse_kick", n=1, rnd=0, fresh=True, change="x")
        self.assertIn("already exists", str(e.exception))
        self.assertGreater(PCA.next_round("Roundhouse"), 0)


class R6Vocabulary(unittest.TestCase):
    def test_slide_keeping_ik_and_the_vocab_gate(self):
        """the R6 vocabulary (owner 2026-10-16: 'the left leg doesnt just stay there ... the arms awkward'): limbs SLIDE
        (the knee / elbow R6 lacks). leg_ik_keep is exactly leg_ik on an unslid leg and keeps a slid leg's slide; the
        vocab gate fails a kick whose limbs never slide (round 1)"""
        import proc_director as DR
        import r6_vocab as RV
        qt, pt = np.array([0, 0, 0, 1.0]), np.zeros(3)
        ql = P.q_exp(np.array([0.3, 0.0, 0.1]))
        goal = np.array([0.6, -3.0, -0.4])
        rng = (np.full(3, -1.5), np.full(3, 1.5))
        a = P.leg_ik(qt, pt, ql, np.zeros(3), "Right Leg", goal, *rng)
        b = DR.leg_ik_keep(qt, pt, ql, np.zeros(3), "Right Leg", goal, *rng)
        self.assertTrue(np.allclose(a[0], b[0]) and np.allclose(a[1], b[1]))
        slid = np.array([0.0, 0.4, -0.4])
        q2, p2 = DR.leg_ik_keep(qt, pt, ql, slid, "Right Leg", goal, *rng)
        self.assertGreater(float(p2 @ slid) / float(slid @ slid), 0.5)        # the slide survives the pin
        # a kick-like clip whose limbs never slide (round 1's fault) is flagged below the loved p10 - built here, so the
        # check runs on a clean checkout (review 2026-10-16: it read a gitignored build file and skipped itself)
        n = 60
        q = np.tile(np.array([0, 0, 0, 1.0]), (n, 6, 1))
        for t in range(n):
            q[t, 4] = P.q_exp(np.array([math.radians(80) * math.sin(math.pi * t / n), 0, 0]))
            q[t, 2] = P.q_exp(np.array([math.radians(30) * math.sin(math.pi * t / n), 0, 0]))
        rows = RV.compare(clip_of(q))
        self.assertTrue(any(m == "slide_p95" and where == "below loved p10" for _, m, _, _, _, _, where in rows))


class FootageMeasure(unittest.TestCase):
    def test_a_synthetic_kick_reads_back_its_timings(self):
        """footage_measure (dossier numbers from MediaPipe world landmarks): a synthetic right kick - toe-off at 0.30 s,
        the foot out to the side and up by 0.45 s, back down by 0.80 s, the hips turning 90 deg - is read back"""
        import footage_measure as FM
        fps, T = 30, 36
        lm = np.zeros((T, 33, 3))
        for t in range(T):
            s = t / fps
            turn = math.radians(90) * min(max((s - 0.25) / 0.25, 0.0), 1.0) * (1.0 if s < 0.6 else max(0.0, 1 - (s - 0.6) / 0.3))
            lm[t, 23] = [-0.15 * math.cos(turn), 1.0, -0.15 * math.sin(turn)]
            lm[t, 24] = [0.15 * math.cos(turn), 1.0, 0.15 * math.sin(turn)]
            lm[t, 27] = [-0.15, 0.05, 0.0]
            lift = 0.0 if s < 0.3 or s > 0.8 else math.sin(math.pi * (s - 0.3) / 0.5)
            lm[t, 28] = [0.15 + 0.9 * lift, 0.05 + 1.0 * lift, 0.0]
        m = FM.measure(lm, fps)
        self.assertEqual(m["kick_leg"], "right")
        self.assertAlmostEqual(m["toe_off_s"], 0.333, delta=0.05)
        self.assertAlmostEqual(m["extend_s"], 0.55, delta=0.05)
        self.assertGreater(m["hip_turn_at_extend_deg"], 80)
        self.assertGreater(m["land_s"], m["extend_s"])

    def test_hip_centred_landmarks_find_the_extension(self):
        """MediaPipe's world landmarks are centred on the HIPS: a standing straight leg is as far from the hip centre
        as the extended one (~0.9 m), so 'furthest from the hips' found the extension at a standing frame on real
        footage (swing 1.3 s, recoil 0). The same synthetic kick, hip-centred, must still read back its extension"""
        import footage_measure as FM
        fps, T = 30, 36
        lm = np.zeros((T, 33, 3))
        for t in range(T):
            s = t / fps
            lm[t, 23], lm[t, 24] = [-0.15, 0.0, 0.0], [0.15, 0.0, 0.0]
            lm[t, 27] = [-0.12, -0.9, 0.0]
            lift = 0.0 if s < 0.3 or s > 0.8 else math.sin(math.pi * (s - 0.3) / 0.5)
            ang = math.radians(90) * lift                   # the leg swings up and out about the hip, the knee a little
            rad = 0.9 * (1 - 0.15 * lift)                   # bent at contact (as on real footage): shorter than standing
            lm[t, 28] = [0.12 + rad * math.sin(ang), -rad * math.cos(ang), 0.0]
        m = FM.measure(lm, fps)
        self.assertTrue(0.45 <= m["extend_s"] <= 0.65, m["extend_s"])  # the bent knee peaks OUT just before the apex;
        self.assertGreater(m["recoil_s"], 0.1)                          # the old 3D reach said 0.367 (mid-chamber)

    def test_arm_direction_measure_reads_the_keyed_arm(self):
        """arm_dir_off_deg (the footage arm checks): the base kick's lead arm at toe-off is near its own keyed direction
        and far from the opposite one (a raised-forward arm); the verifier's 'to' edit names the direction"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        import json

        import dossier_verify as DV
        import proc_dossier as DS
        import proc_kick as PK
        d = DS.require("roundhouse_kick")
        c, _ = PK.build(d, name="t")
        m, _ = DS.measures(c, d)
        key = next(k for k in d["build"]["keys"] if k["name"] == "toe_off")["lead_arm"]
        near = m["arm_dir_off_deg"]({"arm": "lead", "at": "toe_off", "dir": key})
        far = m["arm_dir_off_deg"]({"arm": "lead", "at": "toe_off", "dir": [150, 30]})
        self.assertLess(near, 45)
        self.assertGreater(far, near + 60)
        d2 = json.loads(json.dumps(d))
        lc = next(ck for ck in d2["checks"] if ck["id"] == "lead_counter")
        lc["range"] = [0, 1]                                         # force it to be the reported difference
        out = DV.verify(c, d2)
        self.assertEqual(out["check"], "lead_counter")
        self.assertIn("toward [38, -68]", out["edit"])

    def test_the_hit_sits_on_its_strike_for_every_timing(self):
        """2026-10-16: the Hit was clamped 'peak + 3/60' from a 4-decimal peak on a 6-decimal time grid (3.002 frames,
        over the engine's 3) and dragged to the leg's GLOBAL speed peak (toe-off) - every slow / clamped variant failed.
        The roundhouse at any time slider: the Hit lands where the BODY has turned and the foot meets the target (the
        global-peak clamp put it at toe-off + 3 frames: 67-80 deg turned, the foot 21-44 deg short), on its strike, and
        the kick ends back in the guard (the recovery step)"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        import clip as C
        import proc_candidates as PCA
        import proc_dossier as DS
        import proc_kick as PK
        d = DS.require("roundhouse_kick")
        base = PK.carry(d["build"]["keys"])
        for t in (-0.7, 0.0, 0.6):
            s = {"time": t, "weight": 0, "space": 0, "flow": 0}
            c, b = PK.build(d, keys=PCA.apply_sliders(base, s), follow=PCA.follow_of(s), name="t")
            r = DS.check(c, {**d, "build": b})["checks"]
            self.assertGreater(r["hips_over"]["value"], 85, t)              # turned at the Hit (the old clamp: 67-80)
            self.assertLess(abs(r["on_target"]["value"]), 15, t)            # the foot meets the target (was 21-44 short)
            self.assertLess(r["back_in_guard"]["value"], 0.4, t)
            m = C.metrics(c, C.load_rig("r6"))
            self.assertEqual([p for p in m["problems"] if "nearest strike" in p], [], t)

    def test_tracks_keep_two_people_apart(self):
        """footage_landmarks.track (a fight: --poses 2): two bodies walking past each other keep their own tracks"""
        import footage_landmarks as FL
        w = [[0.0, 0.0, 0.0]] * 33
        dets = [[((0.2 + 0.004 * f, 0.5), w, [1.0] * 33), ((0.8 - 0.004 * f, 0.5), w, [1.0] * 33)] for f in range(60)]
        tr = FL.track(dets)
        self.assertEqual(len(tr), 2)
        self.assertTrue(all(len(t["frames"]) == 60 for t in tr))

    def test_react_measure_reads_a_snap_from_its_onset(self):
        """react_measure: an idle head that drifts 10 deg, then snaps 30 deg in 5 frames at 0.5 s - read from the
        ONSET (not frame 0, not the drift)"""
        import react_measure as RM
        fps, n = 60, 90
        frames_head, frames_rest = [], [[0, 0, 0, 1, 0, 0, 0]]
        for i in range(n):
            drift = math.radians(10) * i / n
            snap = math.radians(30) * min(max((i - 30) / 5, 0), 1)
            a = drift + snap
            frames_head.append([0.0, math.sin(a / 2), 0.0, math.cos(a / 2), 0.0, 0.0, 0.0])
        c = {"fps": fps, "times": [i / fps for i in range(n)],
             "joints": {j: {"frames": frames_head if j == "Head" else frames_rest * n} for j in P.JOINTS}}
        m = RM.measure(c)
        self.assertAlmostEqual(m["head_peak_deg"], 30, delta=4)
        self.assertLess(m["head_to_peak_s"], 0.15)
        self.assertAlmostEqual(m["torso_peak_deg"], 0, delta=0.5)

    def test_the_neck_is_restored_after_a_reaction(self):
        """proc_physics.simulate's neck (a head cone + no head-arm contact) holds only for the run - inverse dynamics
        (the physics gate's calibration) must never see it"""
        try:
            import mujoco
        except ImportError:
            self.skipTest("mujoco not installed")
        import proc_physics as PH
        m, _ = PH.model()
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "Head")
        def state():
            return (int(m.jnt_limited[jid]), m.jnt_range[jid].tolist(), m.geom_contype.tolist(), m.geom_conaffinity.tolist(),
                    float(m.opt.timestep), int(m.opt.integrator), m.dof_damping.tolist(), m.dof_armature.tolist())
        before = state()
        c = clip_of(np.tile(np.array([0, 0, 0, 1.0]), (20, 6, 1)))
        PH.simulate(c, hits=[{"t": 0.05, "part": "Head", "dir": [-1, 0, 0], "speed": 10}], neck_deg=20)
        self.assertEqual(before, state())                         # the neck AND _simulate's damping / timestep
        PH.simulate(c, hits=[{"t": 0.05, "part": "Head", "dir": [-1, 0, 0], "speed": 10}])
        self.assertEqual(before, state())                         # the default (no neck) leaves it untouched too

    def test_the_head_hook_dossier_builds_a_clean_reaction(self):
        """head_hook_reaction (the owner's 'yes do the head hook'): built from its dossier, every check passes and the
        motion gates + physics are clean (needs the built BrawlerIdle)"""
        import os as _os
        if not _os.path.isfile(_os.path.join("build", "animations", "BrawlerIdle.clip.json")):
            self.skipTest("BrawlerIdle not built (lune run kit anim BrawlerIdle)")
        try:
            import mujoco  # noqa: F401
        except ImportError:
            self.skipTest("mujoco not installed")
        import clip as C
        import proc_dossier as DS
        import proc_gates as G
        import proc_physics as PH
        import proc_react as PR
        d = DS.require("head_hook_reaction")
        c, b = PR.build(d)
        r = DS.check(c, {**d, "build": b})
        self.assertTrue(r["pass"], [k for k, v in r["checks"].items() if not v["pass"]])
        self.assertEqual(C.metrics(c, C.load_rig("r6")).get("problems") or [], [])
        g = G.check(c, "combat")
        self.assertEqual([k for k, v in g.items() if isinstance(v, dict) and not v.get("pass", True)], [])
        self.assertTrue(PH.check(c, "combat")["pass"])

    def test_reaction_efforts_move_the_hit_physics(self):
        """proc_candidates.react_genome: the four efforts spread a REACTION's hit (harder / more sudden / another
        angle / a freer body), never past the clamps; no effort = the dossier's own hit"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "head_hook_reaction.json")):
            self.skipTest("the author's assets/animations/dossiers/head_hook_reaction.json is not shipped with the kit")
        import proc_candidates as PCA
        import proc_dossier as DS
        d = DS.require("head_hook_reaction")
        h0, b0, s0 = PCA.react_genome(d, {"time": 0, "weight": 0, "space": 0, "flow": 0})
        self.assertEqual(h0["speed"], d["build"]["hit"]["speed"])
        self.assertAlmostEqual(h0["dir"][0], d["build"]["hit"]["dir"][0], places=3)
        hi, bi, si = PCA.react_genome(d, {"time": 1, "weight": 1, "space": 1, "flow": 1})
        self.assertGreater(hi["speed"], h0["speed"])
        self.assertLess(hi["dur"], h0["dur"])
        self.assertNotAlmostEqual(hi["dir"][2], h0["dir"][2], places=2)
        self.assertGreater(si["root_rot_give"], s0["root_rot_give"])
        self.assertLessEqual(si["root_rot_give"], 0.7)
        if b0:
            self.assertGreater(bi["speed"], b0["speed"])

    def test_greatsword_cuts_in_the_loved_r6_style(self):
        """strike.py (2026-10-17, the owner's greatsword moveset): the arms SLIDE to reach (loved R6 slashes 1.24-3.21
        studs; the rejected greatswords 0.0), the legs turn WITH the body (loved 0 deg; the rejected stepped, 22-73 deg
        twist) and the Hit sits on CONTACT - the side cut's blade moves LEFT there, not forward - every dossier check passes"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "GreatswordSideCut.move.json")):
            self.skipTest("the author's assets/animations/GreatswordSideCut.move.json is not shipped with the kit")
        import json

        import proc_dossier as DS
        import strike as ST
        for name, dossier in (("GreatswordSideCut", "greatsword_side_cut"), ("GreatswordRising", "greatsword_rising")):
            m = json.load(open(os.path.join("assets", "animations", f"{name}.move.json"), encoding="utf-8"))
            c, _ = ST.generate(m)
            r = DS.check(c, DS.require(dossier))
            self.assertTrue(r["pass"], [k for k, v in r["checks"].items() if not v["pass"]])
            self.assertGreater(r["checks"]["arms_slide"]["value"], 1.1)
            self.assertLess(r["checks"]["legs"]["value"], 15)       # (the check was 'legs_with_body' until 2026-10-18)
            m0 = dict(m, arm_slide=0.0, contact_dir=None)
            m0["keys"] = [dict(k, legs=None) for k in m["keys"]]
            c0, _ = ST.generate(m0)                                   # the old behaviour: no slide, planted legs
            r0 = DS.check(c0, DS.require(dossier))
            self.assertLess(r0["checks"]["arms_slide"]["value"], 0.1)
            self.assertGreater(r0["checks"]["legs"]["value"], 30)

    def test_katana_combo_travels_vanishes_and_joins_cleanly(self):
        """the katana combo (owner 2026-10-18): strike.py's `root` key travels the character (a stamp per cut, an 8-stud
        teleport) into the clip's root track; the flash step carries Vanish / Appear events; each move starts with the
        arms facing where the last one left them (arm_facing_start), so the GAME clips joined end to end have no snap"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "Katana1Kesa.move.json")):
            self.skipTest("the author's assets/animations/Katana1Kesa.move.json is not shipped with the kit")
        import json

        import snaps as SN
        import strike as ST
        clips = []
        for name in ("Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko", "Katana4Kiriage", "Katana5Shunpo"):
            m = json.load(open(os.path.join("assets", "animations", f"{name}.move.json"), encoding="utf-8"))
            c, _ = ST.generate(m)
            clips.append(c)
        kesa, shunpo = clips[0], clips[-1]
        # v2 (owner 2026-10-18: v1's stamps + compressed cuts 'shotdown 10 folds'): the cuts stand where the loved
        # greatsword cuts stood - no root travel - and only the teleport travels
        self.assertNotIn("root", kesa)
        self.assertGreater(-shunpo["root"][-1][6], 8.0)                    # the teleport crossed 8 studs
        names = [e["name"] for e in shunpo["events"]]
        self.assertEqual(names.count("Vanish"), 1)
        self.assertEqual(names.count("Appear"), 1)
        joined = {"fps": 60, "loop": False, "joints": {j: {"frames": list(v["frames"])} for j, v in kesa["joints"].items()}}
        seams = []
        for c in clips[1:]:
            seams.append(len(joined["joints"]["Torso"]["frames"]) - 1)
            for j, v in c["joints"].items():
                joined["joints"][j]["frames"] += v["frames"][1:]
        arms = {j: [s for s in x if any(abs(s[0] - k) <= 3 for k in seams)] for j, x in SN.find(joined).items() if "Arm" in j}
        self.assertEqual({j: x for j, x in arms.items() if x}, {})         # no arm spins at a seam

    def test_planted_legs_slide_instead_of_sinking(self):
        """strike.py leg_slide + pelvis_drop_max (2026-10-18, the owner: legs 'that fit'): with the hips turned over a
        planted split stance, the loved HQ R6 Combat pack sinks the body 0.24-0.33 studs and SLIDES the legs to the
        feet; without the options the body sank 1.3 studs. The feet stay planted either way"""
        if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "GsCombo1SideLeft.move.json")):
            self.skipTest("the author's assets/animations/GsCombo1SideLeft.move.json is not shipped with the kit")
        import json

        import numpy as np
        import proc_dossier as DS
        import strike as ST
        m = json.load(open(os.path.join("assets", "animations", "GsCombo1SideLeft.move.json"), encoding="utf-8"))
        # the strike.py rule alone: feet fixed in a split stance (the combo's own keys pivot them), standing height
        m["keys"] = [dict(k, right=[0.6, 0, 1.3], left=[-0.6, 0, -0.9], pos=[0, 0, 0]) for k in m["keys"]]

        def drop_and_feet(move):
            c, _ = ST.generate(move)
            q, p = DS._world(c)
            feet = [np.array([DS._limb_end_world(q, p, t, lg) for t in range(len(q))]) for lg in ("Right Leg", "Left Leg")]
            soles = max(float(np.abs(f[:, 1] + 3.0).max()) for f in feet)          # the floor at y = -3
            slide = max(float(np.linalg.norm(np.diff(f[:, [0, 2]], axis=0), axis=1).max()) for f in feet)
            return float(p[:, 0, 1].max() - p[:, 0, 1].min()), soles, slide
        drop, soles, slide = drop_and_feet(m)
        self.assertLess(drop, 0.36)
        self.assertLess(soles, 0.35)                 # the soles near the floor (a foot's toe lifts ~0.3 at a turn)
        self.assertLess(slide, 0.02)                 # planted
        old, _, _ = drop_and_feet(dict(m, leg_slide=0.0, pelvis_drop_max=None))
        self.assertGreater(old, 1.0)
        # a CROUCH holds (the owner 2026-10-18: 'the legs tho are the issue' - they stood tall on legs slid OUT of the
        # hips): keyed 0.6 low, the pelvis never rises above it and the legs slide INTO the torso, as the loved HQ legs
        crouch = dict(m, keys=[dict(k, pos=[0, -0.6, 0]) for k in m["keys"]])
        c, _ = ST.generate(crouch)
        q, p = DS._world(c)
        self.assertLessEqual(float(p[:, 0, 1].max()), -0.6 + 1e-6)
        along = [float(p[t, DS.J.index(lg)] @ DS.P.q_rot(q[t, DS.J.index(lg)], np.array([0.0, -1.0, 0.0])))
                 for t in range(len(q)) for lg in ("Right Leg", "Left Leg")]
        self.assertLess(min(along), -0.4)                # bent-knee R6 legs: slid in

    def test_kicks_skip_held_poses(self):
        """an instructional clip holds the extension to show it: that window's timing is not the move's"""
        import footage_measure as FM
        fps = 30
        stand = [[0.0, 0.0, 0.0]] * 33
        def frame(r):
            f = [list(p) for p in stand]
            f[27], f[28] = [-0.12, -0.9, 0.0], [0.5, r, 0.0]
            return f
        clip = [frame(-0.9)] * 30 + [frame(0.0)] * 8 + [frame(-0.9)] * 40 + [frame(0.0)] * 60 + [frame(-0.9)] * 30
        w = FM.kicks(clip, fps)
        self.assertEqual(len(w), 1)
        self.assertLess(w[0][0], 30)


if __name__ == "__main__":
    unittest.main()
