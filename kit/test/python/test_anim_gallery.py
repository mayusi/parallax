"""kit/anim/anim_gallery.py + proc_candidates.make - gallery tuning for the animation candidates: the owner's picks and
rejections on a move's earlier rounds are the evidence (an inferred verdict never is), a round's sheet is chosen from a
bigger gate-clean pool and spaced apart by MOTION (the owner's "cousins"), and after an "All bad" the next round
steers away from what was rejected. Stub builders stand in for the real ones (fast; no Blender, no MuJoCo).
Run: python kit/test/python/run.py -k test_anim_gallery"""

import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import anim_gallery as AG  # noqa: E402

JOINTS = AG.JOINTS


def quat(angle):
    return [math.sin(angle / 2), 0.0, 0.0, math.cos(angle / 2), 0.0, 0.0, 0.0]


def clip(angle, frames=30):
    """a clip whose every joint turns from 0 to `angle` about one axis"""
    return {"times": [i / 60 for i in range(frames)], "events": [{"name": "Hit", "t": 0.2}],
            "joints": {j: {"frames": [quat(angle * i / (frames - 1)) for i in range(frames)]} for j in JOINTS}}


def note(root, name, score, words, source="owner"):
    d = os.path.join(root, "kit", "knowledge", "vault", "anim", "verdicts")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{name.lower().replace('/', '-')}--{score}-{source}.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nkind: verdict\narea: anim\nname: {name}\nscore: {score}\ndate: 2026-11-08\nsource: {source}\n---\n\n{words}\n")


def manifest(mdir, move, rnd, sliders, parents=(), **extra):
    os.makedirs(os.path.join(mdir, move), exist_ok=True)
    cands = [{"id": f"{move}/r{rnd}/c{i}", "sliders": s} for i, s in enumerate(sliders)]
    with open(os.path.join(mdir, move, f"round_{rnd}.json"), "w", encoding="utf-8") as f:
        json.dump({"round": rnd, "parents": list(parents), "candidates": cands, **extra}, f)


def s4(v, arms="technique"):
    return {"time": v, "weight": v, "space": v, "flow": v, "arms": arms}


class SignatureTest(unittest.TestCase):
    def test_motion_is_measured_on_the_joints_and_falls_back_to_settings(self):
        a, b = AG.signature(clip(1.0)), AG.signature(clip(1.6))
        self.assertEqual(a.shape, (len(JOINTS), AG.SAMPLES, 4))
        self.assertAlmostEqual(AG.motion_distance(a, a), 0.0, places=6)
        self.assertGreater(AG.motion_distance(a, b), 0.1)
        self.assertIsNone(AG.signature({"times": [0, 1], "events": []}))  # no joint tracks
        far = AG.distance({"sliders": s4(-1.0), "sig": None}, {"sliders": s4(1.0), "sig": a})
        near = AG.distance({"sliders": s4(0.9), "sig": None}, {"sliders": s4(1.0), "sig": a})
        self.assertGreater(far, near)  # spaced by settings when a clip has no joints


class EvidenceTest(unittest.TestCase):
    def test_picks_and_the_owners_own_rejections_are_the_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            mdir = os.path.join(root, "manifests")
            manifest(mdir, "Probe", 0, [s4(-0.6), s4(-0.2), s4(0.2), s4(0.6)])
            manifest(mdir, "Probe", 1, [s4(0.1), s4(0.15), s4(0.25), s4(0.3)], parents=["Probe/r0/c2"])
            note(root, "Probe/r1", 2, "All bad - every one of the 4")
            note(root, "Probe", 1, "round 0: all bad", source="inferred")  # a model's guess: never the owner's
            ev = AG.evidence("Probe", mdir, root)
            self.assertEqual(ev["counts"], {"rounds": 2, "shown": 8, "picks": 1, "pairs": 3, "rejected": 4, "all_bad_rounds": 1,
                                            "other_generator": 0})
            self.assertTrue(all(ev["ids"][i].startswith("Probe/r0/c2") for i, _ in ev["prefs"]))
            self.assertEqual(sorted(ev["ids"][i] for i in ev["bad"]), [f"Probe/r1/c{k}" for k in range(4)])
            self.assertEqual(AG.evidence("Probe", mdir, root, before=1)["counts"]["rejected"], 0)  # only earlier rounds
            self.assertIn("1 pick(s) (3 comparisons)", AG.said(ev["counts"]))

    def test_another_generators_rounds_are_left_out(self):
        with tempfile.TemporaryDirectory() as root:
            mdir = os.path.join(root, "manifests")
            manifest(mdir, "Probe", 0, [s4(-0.5), s4(0.5)])  # no builder recorded: made before proc_blade existed
            manifest(mdir, "Probe", 1, [s4(-0.4), s4(0.4)], builder="proc_strike")
            manifest(mdir, "Probe", 2, [s4(-0.3), s4(0.3)], builder="proc_blade")
            note(root, "Probe", 2, "All bad - round 0 and round 1 and round 2, every one")
            blade = AG.evidence("Probe", mdir, root, builder="proc_blade")["counts"]
            self.assertEqual((blade["rounds"], blade["rejected"], blade["other_generator"]), (1, 2, 2))
            kick = AG.evidence("Probe", mdir, root, builder="proc_kick")["counts"]
            self.assertEqual((kick["rounds"], kick["other_generator"]), (1, 2))  # only the unrecorded round
            self.assertIn("2 earlier round(s) by another generator left out", AG.said(blade))

    def test_an_agents_pick_never_counts(self):
        with tempfile.TemporaryDirectory() as root:
            mdir = os.path.join(root, "manifests")
            manifest(mdir, "Probe", 0, [s4(-0.6), s4(-0.2), s4(0.2)])
            manifest(mdir, "Probe", 1, [s4(0.1)], parents=["Probe/r0/c2"], picked_by="agent (blanket approval)")
            self.assertEqual(AG.evidence("Probe", mdir, root)["counts"]["picks"], 0)
            self.assertEqual(AG.evidence("Probe", mdir, root, parents=["Probe/r0/c1"], picked_by="agent")["counts"]["picks"], 0)
            self.assertEqual(AG.evidence("Probe", mdir, root, parents=["Probe/r0/c1"])["counts"]["picks"], 1)


class MakeTest(unittest.TestCase):
    """proc_candidates.make on the keyed-block route with stub builders: every built candidate's motion is chosen by
    the test (the first eight nearly the same - cousins)"""

    def setUp(self):
        import proc_candidates as PC  # noqa: PLC0415

        self.PC = PC
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(PC, k) for k in ("MANIFESTS", "CLIPS", "gate")}
        self.saved_mod = (PC.DS.require, PC.PK.slide_ranges, PC.PST.build, PC.PST.variant_count)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        PC.MANIFESTS = os.path.join(self.tmp.name, "manifests")
        PC.CLIPS = os.path.join(self.tmp.name, "clips")
        PC.DS.require = lambda name: {"build": {"builder": "strike"}, "category": "combat"}
        PC.PK.slide_ranges = lambda: None
        PC.PST.variant_count = lambda d, name: 1
        PC.gate = lambda c, d, b, arms="technique": (True, [], [])
        self.built = []

        def build(d, s, name):
            k = len(self.built)
            self.built.append(dict(s))
            angle = 0.5 + 0.01 * k if k < 8 else 0.5 + 0.2 * (k - 7) * (1 if k % 2 else -1)  # cousins first
            return clip(angle), {}
        PC.PST.build = build

    def tearDown(self):
        PC = self.PC
        for k, v in self.saved.items():
            setattr(PC, k, v)
        PC.DS.require, PC.PK.slide_ranges, PC.PST.build, PC.PST.variant_count = self.saved_mod
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_the_sheet_comes_from_a_bigger_pool_spaced_apart_by_motion(self):
        man = self.PC.make("Probe", "probe", n=8, rnd=0)
        g = man["gallery"]
        self.assertEqual(len(man["candidates"]), 8)
        self.assertEqual(g["pool"], math.ceil(AG.POOL * 8))
        self.assertEqual((g["measure"], g["roles"]), ("motion", {"spread": 8}))  # nothing learned yet: spread
        self.assertGreater(g["sheet"][0], g["first_built"][0] * 5)  # the closest pair is far apart now
        self.assertTrue(all(c["gallery"]["role"] == "spread" and c["gallery"]["proposed"] is False for c in man["candidates"]))
        self.assertTrue(all("sig" not in c and "proposed" not in c for c in man["candidates"]))
        self.assertEqual(g["evidence"]["shown"], 0)

    def test_after_all_bad_the_next_round_steers_away_from_what_was_rejected(self):
        # round 0: eight rejected candidates in one corner of the efforts
        manifest(self.PC.MANIFESTS, "Probe", 0, [s4(0.7 + 0.03 * k) for k in range(8)])
        note(self.tmp.name, "Probe", 2, "All bad - round 0, every one")
        man = self.PC.make("Probe", "probe", n=8, rnd=1, fresh=True, change="steer away")
        g = man["gallery"]
        self.assertEqual((g["evidence"]["rejected"], g["evidence"]["all_bad_rounds"]), (8, 1))
        self.assertEqual(g["roles"], {"likely": 4, "learn": 4})
        self.assertTrue(any(c["gallery"]["proposed"] for c in man["candidates"]))  # the model's own settings built
        rejected = np.asarray([[0.7 + 0.03 * k] * 4 for k in range(8)])

        def near_rejected(cands):
            return float(np.mean([np.min(np.linalg.norm(rejected - [c["sliders"][k] for k in ("time", "weight", "space", "flow")], axis=1))
                                  for c in cands]))
        lhs = self.PC.genomes_round0(8 * self.PC.POOL_GENOMES, man["seed"])[:8]  # the round a plain spread would show
        self.assertGreater(near_rejected(man["candidates"]), near_rejected([{"sliders": s} for s in lhs]))

    def test_a_line_that_rarely_passes_still_gets_its_share(self):
        self.PC.PST.variant_count = lambda d, name: 4
        seen = {}

        def gate(c, d, b, arms="technique"):
            v = self.built[-1]["variant"]
            seen[v] = seen.get(v, 0) + 1
            return (v != 3 or seen[v] % 6 == 0), ["x"], []  # line 3 passes one try in six
        self.PC.gate = gate
        man = self.PC.make("Probe", "probe", n=8, rnd=0)
        per = [sum(1 for c in man["candidates"] if c["sliders"]["variant"] == v) for v in range(4)]
        self.assertEqual(per, [2, 2, 2, 2])
        self.assertGreater(man["gallery"]["pool"], math.ceil(AG.POOL * 8))  # it built on until line 3 had its two


if __name__ == "__main__":
    unittest.main()
