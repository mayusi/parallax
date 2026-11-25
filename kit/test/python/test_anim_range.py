"""kit/anim/proc_candidates.py - the EFFORTS MAPPING 2 (anim-range, 2026-11-09): each effort moves the whole body as far
as the move's own dossier checks allow, so a round's candidates differ (the owner's "cousins", 2026-11-04). Zero
efforts stay the dossier's own build under every mapping, a round records its mapping (and a blade's / reaction's
probed reach), a bred round keeps its parents', the taste model only learns from rounds of the same mapping, and a
pick rebuilds with the mapping its round used. Stubs stand in for the slow builders.
Run: python kit/test/python/run.py -k test_anim_range"""

import json
import math
import os
import re
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, HERE)
import anim_gallery as AG  # noqa: E402
import proc_candidates as PC  # noqa: E402
from test_anim_gallery import clip, manifest, s4  # noqa: E402

ZERO = {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0}


def roundhouse():
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        d = PC.DS.require("roundhouse_kick")
    finally:
        os.chdir(cwd)
    return d, PC.PK.carry(d["build"]["keys"])


_ROUNDHOUSE = os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")


class MappingTest(unittest.TestCase):
    def test_zero_efforts_are_the_dossiers_own_build_under_every_mapping(self):
        if not os.path.isfile(_ROUNDHOUSE):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        d, base = roundhouse()
        self.assertEqual(PC.apply_sliders(base, ZERO, 1), base)
        self.assertEqual(PC.apply_sliders(base, ZERO, 2), base)
        self.assertIs(PC.kick_dossier(d, ZERO, 2), d)
        self.assertEqual(PC.follow_of(ZERO, 1), PC.follow_of(ZERO, 2))
        reach = {k: [2.5, 2.5] for k in PC.SLIDERS}
        self.assertEqual(PC.scaled({**ZERO, "arms": "habit:0:out"}, reach), {**ZERO, "arms": "habit:0:out"})
        hook = {"build": {"hit": {"part": "Head", "dir": [-1, 0, 0.2], "speed": 14, "dur": 0.12, "w_joint": 20.0},
                          "body_hit": {"part": "Torso", "speed": 10, "dir": [0, 0.3, 1]}, "sim": {"root_rot_give": 0.4}}}
        h1, b1, s1 = PC.react_genome(hook, ZERO, 1)
        h2, b2, s2 = PC.react_genome(hook, ZERO, 2, reach)
        self.assertEqual({**hook["build"]["hit"], **h1}, {**hook["build"]["hit"], **h2})   # the dossier's own hit
        self.assertEqual(({**hook["build"]["body_hit"], **b1}, s1), ({**hook["build"]["body_hit"], **b2}, s2))

    def test_the_second_mapping_moves_the_whole_body_further(self):
        if not os.path.isfile(_ROUNDHOUSE):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        d, base = roundhouse()
        strong, light = {**ZERO, "weight": 1.0}, {**ZERO, "weight": -1.0}

        def at(keys, name):
            return next(k for k in keys if k["name"] == name)
        gap = {v: at(PC.apply_sliders(base, strong, v), "contact")["kick"][0] - at(PC.apply_sliders(base, light, v), "contact")["kick"][0]
               for v in (1, 2)}
        self.assertGreater(gap[2], 1.5 * gap[1])                   # a head kick vs a body kick, not 12 deg apart
        wide = PC.apply_sliders(base, {**ZERO, "space": 1.0}, 2)
        self.assertGreater(at(wide, "contact")["head"][1], 15)     # indirect: the head turns with the body
        self.assertGreater(at(wide, "land")["yaw"], at(base, "land")["yaw"] + 10)   # carried round into the landing
        self.assertEqual(at(PC.apply_sliders(base, {**ZERO, "space": 1.0}, 1), "land")["yaw"], at(base, "land")["yaw"])
        self.assertGreater(PC.kick_dossier(d, {**ZERO, "space": 1.0}, 2)["build"]["pivot_share"], d["build"]["pivot_share"])
        rs = np.random.default_rng(3)
        for _ in range(40):                                         # every setting keeps the keys in time order
            ts = [k["t"] for k in PC.apply_sliders(base, {k: float(rs.uniform(-1, 1)) for k in PC.SLIDERS}, 2)]
            self.assertTrue(all(b > a for a, b in zip(ts, ts[1:])))
        free1, free2 = PC.follow_of({**ZERO, "flow": 1.0}, 1), PC.follow_of({**ZERO, "flow": 1.0}, 2)
        self.assertGreater(free2["Torso"], free1["Torso"])


class ReachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = PC.CLIPS
        PC.CLIPS = self.tmp.name

    def tearDown(self):
        PC.CLIPS = self.saved
        self.tmp.cleanup()

    def test_reach_goes_as_far_as_every_gate_passes_and_is_cached(self):
        calls = []

        def probe(s):
            calls.append(dict(s))
            moved = [k for k in PC.SLIDERS if s[k]]
            self.assertEqual(len(moved), 1)                         # one effort at a time, from the dossier's own build
            k, x = moved[0], s[moved[0]]
            return abs(x) <= {"weight": 2.0, "time": 2.5 if x < 0 else 1.0}.get(k, 1.4)
        src = os.path.join(self.tmp.name, "gesture.json")
        with open(src, "w") as f:
            f.write("{}")
        r = PC.reach_of("Probe", {"build": {"x": 1}}, probe, [src])
        self.assertEqual(r, {"time": [2.5, 1.0], "weight": [2.0, 2.0], "space": [1.0, 1.0], "flow": [1.0, 1.0]})
        n = len(calls)
        self.assertEqual(PC.reach_of("Probe", {"build": {"x": 1}}, probe, [src]), r)
        self.assertEqual(len(calls), n)                             # cached: no probe the second time
        with open(src, "w") as f:
            f.write('{"changed": 1}')
        PC.reach_of("Probe", {"build": {"x": 1}}, probe, [src])
        self.assertGreater(len(calls), n)                           # a source changed: probed again
        self.assertEqual(PC.scaled({**ZERO, "time": -1.0, "weight": 0.5}, r)["time"], -2.5)
        self.assertEqual(PC.scaled({**ZERO, "time": 1.0, "weight": 0.5}, r)["weight"], 1.0)

    def test_the_cache_key_covers_engine_gates_calibrations_and_the_moves_own_inputs(self):
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            blade = PC.range_sources({"build": {"gestures": {"A*": "g_one", "B*": "g_two"}}}, "blade")
            react = PC.range_sources({"build": {"base": "BrawlerIdle"}}, "react")
        finally:
            os.chdir(cwd)
        names = {os.path.basename(f) for f in blade}
        for f in ("proc_r6.py", "proc_gates.py", "proc_dossier.py", "proc_physics.py", "clip.py", "proc_blade.py",
                  "proc_candidates.py", "r6_vocab.json", "proc_calib.json", "direction.py", "g_one.json", "g_two.json"):
            self.assertIn(f, names)
        self.assertIn(os.path.join("build", "animations", "BrawlerIdle.clip.json"), react)


class RoundTest(unittest.TestCase):
    """make() on the keyed-block route with stub builders (as test_anim_gallery.MakeTest)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(PC, k) for k in ("MANIFESTS", "CLIPS", "gate", "EFFORTS")}
        self.saved_mod = (PC.DS.require, PC.PK.slide_ranges, PC.PST.build, PC.PST.variant_count)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        PC.MANIFESTS = os.path.join(self.tmp.name, "manifests")
        PC.CLIPS = os.path.join(self.tmp.name, "clips")
        PC.DS.require = lambda name: {"build": {"builder": "strike"}, "category": "combat"}
        PC.PK.slide_ranges = lambda: None
        PC.PST.variant_count = lambda d, name: 1
        PC.gate = lambda c, d, b, arms="technique": (True, [], [])
        PC.EFFORTS = {"proc_strike": 3}                            # a builder on its third mapping
        PC.PST.build = lambda d, s, name: (clip(0.5 + 0.1 * s["weight"]), {})

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(PC, k, v)
        PC.DS.require, PC.PK.slide_ranges, PC.PST.build, PC.PST.variant_count = self.saved_mod
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_a_round_records_its_mapping_and_children_keep_their_parents(self):
        self.assertEqual(PC.make("Probe", "probe", n=4, rnd=0)["efforts"], 3)        # a new spread: the newest
        reach = {k: [1.5, 1.0] for k in PC.SLIDERS}
        manifest(PC.MANIFESTS, "Probe", 1, [s4(0.2), s4(0.4)], efforts=1, reach=reach)
        man = PC.make("Probe", "probe", n=4, rnd=2, parents=["Probe/r1/c1"])
        self.assertEqual((man["efforts"], man["reach"]), (1, reach))                # the owner picked what mapping 1 made
        self.assertEqual(PC.make("Probe", "probe", n=4, rnd=3, fresh=True, change="new spread")["efforts"], 3)

    def test_the_taste_model_learns_only_from_rounds_of_the_same_mapping(self):
        manifest(PC.MANIFESTS, "Probe", 0, [s4(-0.5), s4(0.5)], builder="proc_strike")              # mapping 1
        manifest(PC.MANIFESTS, "Probe", 1, [s4(-0.4), s4(0.4)], builder="proc_strike", efforts=3)   # a fresh spread
        manifest(PC.MANIFESTS, "Probe", 2, [s4(-0.3), s4(0.3)], builder="proc_strike", efforts=3, parents=["Probe/r1/c0"])
        c3 = AG.evidence("Probe", PC.MANIFESTS, self.tmp.name, builder="proc_strike", efforts=3)["counts"]
        self.assertEqual((c3["rounds"], c3["picks"], c3["other_generator"]), (2, 1, 1))
        c1 = AG.evidence("Probe", PC.MANIFESTS, self.tmp.name, builder="proc_strike", efforts=1)["counts"]
        self.assertEqual((c1["rounds"], c1["picks"], c1["other_generator"]), (1, 0, 2))
        man = PC.make("Probe", "probe", n=4, rnd=3, fresh=True, change="x")
        self.assertEqual(man["gallery"]["evidence"]["other_generator"], 1)

    def test_evidence_needs_the_same_reach_and_lines_too(self):
        r1 = {k: [1.0, 2.5] for k in PC.SLIDERS}
        lines = [{"kind": None, "deg": 0}, {"kind": "roll", "deg": -30}]
        manifest(PC.MANIFESTS, "Probe", 0, [s4(-0.5), s4(0.5)], builder="proc_blade", efforts=2, reach=r1, lines=lines)
        manifest(PC.MANIFESTS, "Probe", 1, [s4(-0.4), s4(0.4)], builder="proc_blade", efforts=2, reach=r1,
                 lines=lines + [{"kind": "yaw", "deg": 25}])                           # another line set
        manifest(PC.MANIFESTS, "Probe", 2, [s4(-0.3), s4(0.3)], builder="proc_blade", efforts=2,
                 reach={**r1, "weight": [1.0, 1.0]}, lines=lines)                     # another reach
        same = AG.evidence("Probe", PC.MANIFESTS, self.tmp.name, builder="proc_blade", efforts=2,
                           setup=AG.setup_of({"reach": r1, "lines": lines}))["counts"]
        self.assertEqual((same["rounds"], same["other_generator"]), (1, 2))
        self.assertEqual(AG.setup_of({"lines": lines[:1]}), {"reach": None, "lines": None})   # one line = none

    def test_a_pick_rebuilds_with_the_mapping_its_round_used(self):
        reach = {k: [2.0, 2.5] for k in PC.SLIDERS}
        nums = {k: 0.2 for k in PC.SLIDERS}
        manifest(PC.MANIFESTS, "Probe", 3, [s4(0.2)], efforts=2, reach=reach)
        manifest(PC.MANIFESTS, "Probe", 4, [s4(0.2)])                                     # before the field
        s, eff, r, line, arms = PC.pick_setup({"from_candidate": "Probe/r3/c0", "sliders": nums})
        self.assertEqual((eff, r, line, arms), (2, reach, None, "technique"))             # arms from the candidate
        self.assertEqual(PC.pick_setup({"from_candidate": "Probe/r4/c0", "sliders": nums})[1:3], (1, None))
        self.assertEqual(PC.pick_setup({"from_candidate": "Probe/r3/c0", "sliders": nums, "efforts": 2})[2], reach)
        self.assertEqual(PC.pick_setup({"sliders": {}})[1:3], (1, None))                  # the dossier's own build
        self.assertEqual(PC.pick_setup({"sliders": nums, "efforts": 2, "reach": reach})[1:3], (2, reach))
        for bad in ({"from_candidate": "Probe/r9/c0", "sliders": nums},                   # its round is gone
                    {"from_candidate": "Probe/r9/c0", "sliders": {}},                     # - even at zero efforts
                    {"from_candidate": "Probe/r3/c7", "sliders": nums},                   # not a candidate of it
                    {"from_candidate": "Probe/r3/c0", "sliders": {**nums, "weight": 0.5}},  # not that pick's efforts
                    {"from_candidate": "Probe/r3/c0", "sliders": nums, "arms": "habit:2:up"},
                    {"sliders": nums}):                                                    # efforts, no mapping named
            with self.assertRaises(SystemExit):
                PC.pick_setup(bad)
        self.assertEqual(PC.pick_setup({"from_candidate": "Probe/r9/c0", "sliders": nums}, strike=True)[1], 1)


CUT = {"name": "probe_cut", "beats": [
    {"name": "hang", "t": 0.0, "phase": "rest", "sword": {"reach": [0.3, -0.9, -0.1], "blade": [0.7, 0.1, 0.7]}},
    {"name": "load", "t": 0.2, "phase": "windup", "sword": {"reach": [0.4, 0.4, 0.8], "blade": [0.4, 0.7, -0.5]}},
    {"name": "cut", "t": 0.3, "phase": "strike", "sword": {"reach": [0.0, 0.4, -0.9], "blade": [-0.8, 0.5, -0.2]}},
    {"name": "hold", "t": 0.5, "phase": "after", "sword": {"reach": [-0.8, 0.0, -0.6], "blade": [-0.6, 0.0, 0.8]}},
    {"name": "rest", "t": 0.9, "phase": "rest", "sword": {"reach": [0.5, 0.5, -0.7], "blade": [0.5, 0.4, 0.7]}}]}


class LineTest(unittest.TestCase):
    """blade LINES: the cut in another plane, probed per move, each line its share of the sheet. Stub blade builds: a
    line's blade tip sits `deg` / 10 studs off along its own axis (roll x, yaw y, tilt z); every tilt fails the gates"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(PC, k) for k in ("MANIFESTS", "CLIPS", "gate")}
        self.saved_mod = (PC.DS.require, PC.PK.slide_ranges, PC.PB.build, PC.PB.gesture_for)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        PC.MANIFESTS = os.path.join(self.tmp.name, "manifests")
        PC.CLIPS = os.path.join(self.tmp.name, "clips")
        PC.DS.require = lambda name: {"name": "probe", "build": {"builder": "proc_blade", "gestures": {"Probe*": "probe_cut"}}, "category": "combat"}
        PC.PK.slide_ranges = lambda: None
        PC.PB.gesture_for = lambda d, name: json.loads(json.dumps(CUT))
        self.built = []

        def build(d, s, name, rng=None):
            tag = os.path.basename(str((d["build"].get("gestures") or {}).get("*", "probe_cut")))
            m = re.match(r".*__([a-z]+)([+-]\d+)$", tag)
            kind, deg = (m.group(1), int(m.group(2))) if m else (None, 0)
            off = {"roll": (1, 0, 0), "yaw": (0, 1, 0), "tilt": (0, 0, 1)}.get(kind, (0, 0, 0))
            self.built.append((kind, deg))
            c = clip(0.5 + 0.05 * float(s.get("weight") or 0) + 0.01 * deg)
            c["sword"] = {"tip": [[off[0] * deg / 10, off[1] * deg / 10 + 0.01 * i, off[2] * deg / 10] for i in range(30)]}
            return c, {"gesture": tag}
        PC.PB.build = build
        PC.gate = lambda c, d, b, arms="technique": ("__tilt" not in b.get("gesture", ""), [], [])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(PC, k, v)
        PC.DS.require, PC.PK.slide_ranges, PC.PB.build, PC.PB.gesture_for = self.saved_mod
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_a_line_turns_the_cut_and_leaves_the_rest(self):
        self.assertIs(PC.line_gesture(CUT, None), CUT)
        self.assertIs(PC.line_gesture(CUT, {"kind": "roll", "deg": 0}), CUT)
        g = PC.line_gesture(CUT, {"kind": "roll", "deg": 30})
        self.assertEqual(g["name"], "probe_cut__roll+30")
        self.assertEqual(CUT["beats"][1]["sword"]["reach"], [0.4, 0.4, 0.8])                  # the design is untouched
        for i in (0, 4):                                                                     # the hang and the settle
            self.assertEqual(g["beats"][i]["sword"], CUT["beats"][i]["sword"])
        for i in (1, 2, 3):                                                                  # wind-up .. finish turned
            for f in ("reach", "blade"):
                a, b = CUT["beats"][i]["sword"][f], g["beats"][i]["sword"][f]
                self.assertAlmostEqual(a[2], b[2], places=3)                                 # about the forward axis
                turn = math.degrees(math.atan2(b[1], b[0]) - math.atan2(a[1], a[0]))
                self.assertAlmostEqual(abs((turn + 180) % 360 - 180), 30.0, delta=0.2)

    def test_lines_keep_the_design_first_and_only_lines_that_pass_spread_apart(self):
        d = PC.DS.require("probe")
        lines = PC.lines_of("Probe", d, 0, None, [])
        self.assertEqual(lines[0], {"kind": None, "deg": 0})
        self.assertNotIn("tilt", [ln["kind"] for ln in lines])                              # a failing line never
        self.assertEqual([(ln["kind"], ln["deg"]) for ln in lines[1:]], [("roll", -30), ("roll", 30), ("yaw", -25)])
        n = len(self.built)
        self.assertEqual(PC.lines_of("Probe", d, 0, None, []), lines)
        self.assertEqual(len(self.built), n)                                                 # cached
        self.assertIs(PC.line_dossier(d, CUT, None, "x"), d)                                 # no line: the dossier itself
        dl = PC.line_dossier(d, CUT, lines[1], os.path.join(self.tmp.name, "lines"))
        ref = dl["build"]["gestures"]["*"]
        with open(os.path.join(PC.PB.GESTURES, f"{ref}.json"), encoding="utf-8") as f:      # proc_blade's own lookup
            self.assertEqual(json.load(f)["name"], "probe_cut__roll-30")

    def test_a_blade_round_gives_each_line_its_share_and_children_keep_them(self):
        man = PC.make("Probe", "probe", n=8, rnd=0)
        self.assertEqual(len(man["lines"]), 4)
        per = [sum(1 for c in man["candidates"] if c["sliders"]["variant"] == v) for v in range(4)]
        self.assertEqual(per, [2, 2, 2, 2])
        built = {k for k in self.built}
        self.assertIn(("roll", -30), built)
        kid = PC.make("Probe", "probe", n=8, rnd=1, parents=[man["candidates"][0]["id"]])
        self.assertEqual((kid["lines"], kid["efforts"], kid["reach"]), (man["lines"], man["efforts"], man["reach"]))

    def test_a_pick_rebuilds_on_its_line(self):
        lines = [{"kind": None, "deg": 0}, {"kind": "roll", "deg": -30}, {"kind": "yaw", "deg": 25}]
        nums = {k: 0.1 for k in PC.SLIDERS}
        manifest(PC.MANIFESTS, "Probe", 0, [{**s4(0.1), "variant": 2}], efforts=2, lines=lines)
        manifest(PC.MANIFESTS, "Probe", 1, [s4(0.1)], efforts=2)
        s, _, _, line, _ = PC.pick_setup({"from_candidate": "Probe/r0/c0", "sliders": nums})   # no variant copied
        self.assertEqual((s["variant"], line), (2, lines[2]))                             # the candidate's own line
        self.assertEqual(PC.pick_setup({"from_candidate": "Probe/r0/c0", "sliders": nums, "line": lines[1]})[3], lines[1])
        with self.assertRaises(SystemExit):                                               # another line: not that pick
            PC.pick_setup({"from_candidate": "Probe/r0/c0", "sliders": {**nums, "variant": 1}})
        self.assertIsNone(PC.pick_setup({"from_candidate": "Probe/r1/c0", "sliders": nums})[3])   # a round with no lines


class RealBuildTest(unittest.TestCase):
    """the real kick builder and gates (no stubs; the reach probe skipped): a mapping-2 round, then its pick rebuilt by
    emit frame for frame"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {k: getattr(PC, k) for k in ("MANIFESTS", "CLIPS", "reach_of")}
        self.cwd = os.getcwd()
        os.chdir(ROOT)
        PC.MANIFESTS = os.path.join(self.tmp.name, "manifests")
        PC.CLIPS = os.path.join(self.tmp.name, "clips")
        PC.reach_of = lambda name, d, probe, files=(): {"time": [1.0, 1.0], "weight": [1.5, 1.0], "space": [1.0, 1.0],
                                                         "flow": [2.5, 1.5]}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(PC, k, v)
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_a_kick_pick_rebuilds_frame_for_frame(self):
        if not os.path.isfile(_ROUNDHOUSE):
            self.skipTest("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
        man = PC.make("Roundhouse", "roundhouse_kick", n=2, rnd=0, fresh=True, change="test", max_tries=8)
        self.assertEqual((man["efforts"], man["reach"]["flow"]), (2, [2.5, 1.5]))
        self.assertGreaterEqual(len(man["candidates"]), 1)
        cand = man["candidates"][0]
        spec = {"name": "Roundhouse", "dossier": "roundhouse_kick", "from_candidate": cand["id"],
                "sliders": {k: cand["sliders"][k] for k in PC.SLIDERS}}
        sp, out = os.path.join(self.tmp.name, "Roundhouse.dossier.json"), os.path.join(self.tmp.name, "Roundhouse.clip.json")
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(spec, f)
        PC.emit(sp, out)
        with open(cand["clip"], encoding="utf-8") as f:
            a = json.load(f)
        with open(out, encoding="utf-8") as f:
            b = json.load(f)
        for j in a["joints"]:
            self.assertTrue(np.allclose(a["joints"][j]["frames"], b["joints"][j]["frames"], atol=1e-9), j)
        self.assertEqual(b["source"]["efforts"], 2)


class ReactionLengthTest(unittest.TestCase):
    def test_mapping_two_keeps_a_dossiers_own_short_push(self):
        light = {"build": {"hit": {"part": "Head", "dir": [-1, 0, 0.2], "speed": 9, "dur": 0.05}, "sim": {"root_rot_give": 0.4}}}
        self.assertEqual(PC.react_genome(light, ZERO, 1)[0]["dur"], 0.06)             # the first mapping's floor, kept
        self.assertEqual(PC.react_genome(light, ZERO, 2, {})[0]["dur"], 0.05)         # mapping 2: the dossier's own
        self.assertLess(PC.react_genome(light, {**ZERO, "time": 1.0}, 2, {})[0]["dur"], 0.05 + 1e-9)


if __name__ == "__main__":
    unittest.main()
