"""Switch/weapon-swap arm-speed gate (kit/anim/clip.py).

Owner verdict (graveyard.md ~86-88, 2026-10-26):
  "the transitions are in slow motion and look dumb ... when the gun transitions the arms
   aren't doing anything to actually transition"

Gate rule: a clip whose name matches switch|swap|to(left|right)hand (case-insensitive) must
have at least one arm joint (name contains "arm") whose peak rotation speed reaches
GATES["switch_arm_deg_s"] (1200 deg/s).

"transition" is EXCLUDED: locomotion transitions (IdleToRunTransition) are legs.
Swap clips (SwapToSword, SwapToGuns, etc.) and SwordToLeftHand/SwordToRightHand are weapon switches.

Grandfathering by CONTENT HASH: only the exact committed clip data warns; a rebuilt clip with
different content must pass the floor or fail.

Calibration:
  - Rejected: GunSwitch / GunSideSwitch — arm peak 973 deg/s each (FAIL, grandfathered by hash)
  - Passing reference: GunDrawHips 1451 deg/s, GunDrawDual 2438 deg/s
  - Swap clips measured at 1310-2874 deg/s (pass)
  - Floor 1200 deg/s sits cleanly above rejected (973) and below passing references
"""

import hashlib
import json
import math
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402

FPS = 30


def qx(deg):
    a = math.radians(deg) / 2
    return [math.sin(a), 0.0, 0.0, math.cos(a)]


def _make_switch_clip(name, arm_frames, duration, fps=FPS):
    """build a minimal switch clip with just RightUpperArm keyed."""
    n = int(round(duration * fps)) + 1
    times = [i / fps for i in range(n)]
    return {
        "name": name, "rig": "R15", "fps": fps, "duration": duration,
        "loop": False, "priority": "Action", "events": [], "times": times,
        "joints": {"RightUpperArm": {"frames": [arm_frames(i, t) for i, t in enumerate(times)]}},
    }


def _make_legs_clip(name, duration, fps=FPS):
    """build a clip that only moves legs (no arm joints) — simulates IdleToRunTransition."""
    n = int(round(duration * fps)) + 1
    times = [i / fps for i in range(n)]
    def leg(i, t):
        a = math.radians(90 * t / duration) / 2
        return [math.sin(a), 0.0, 0.0, math.cos(a)] + [0, 0, 0]
    return {
        "name": name, "rig": "R6", "fps": fps, "duration": duration,
        "loop": False, "priority": "Core", "events": [], "times": times,
        "joints": {
            "Right Leg": {"frames": [leg(i, t) for i, t in enumerate(times)]},
            "Left Leg": {"frames": [leg(i, t) for i, t in enumerate(times)]},
        },
    }


class SwitchSpeedGate(unittest.TestCase):
    def setUp(self):
        self.rig = C.load_rig("r15", ROOT)
        self.rig_r6 = C.load_rig("r6", ROOT)

    def test_slow_switch_fails(self):
        """arm moves 90 deg linearly over 1 second: peak = 90 * 30 = 2700 deg ... wait, 90 deg / 1 s = 90 deg/s —
        well below 1200.  The gate must report a problem."""
        # 90 deg total over 30 steps: each step = 90/30 = 3 deg, peak speed = 3 * 30 = 90 deg/s
        clip = _make_switch_clip(
            "SlowSwitch",
            lambda i, t: qx(90 * t / 1.0) + [0, 0, 0],
            1.0,
        )
        m = C.metrics(clip, self.rig)
        self.assertIn("switch_arm_peak_deg_s", m)
        self.assertLess(m["switch_arm_peak_deg_s"], C.GATES["switch_arm_deg_s"])
        problems = " ".join(m["problems"])
        self.assertIn("switch arm speed", problems)

    def test_fast_switch_passes(self):
        """arm snaps 150 deg in 2 frames (0.067 s): peak = 150 * 30 / 2 = 2250 deg/s — well above 1200."""
        def arm(i, t):
            # 150 deg reached by frame 2, held after
            return qx(min(150, i * 75)) + [0, 0, 0]

        clip = _make_switch_clip("FastSwitch", arm, 0.5)
        m = C.metrics(clip, self.rig)
        self.assertIn("switch_arm_peak_deg_s", m)
        self.assertGreaterEqual(m["switch_arm_peak_deg_s"], C.GATES["switch_arm_deg_s"])
        self.assertFalse(
            any("switch arm speed" in p for p in m["problems"]),
            f"unexpected problem: {m['problems']}",
        )

    def test_non_switch_clip_is_not_checked(self):
        """a 'GunFire' clip whose arm barely moves must not trigger the switch gate."""
        clip = _make_switch_clip(
            "GunFire",
            lambda i, t: qx(10 * t) + [0, 0, 0],
            0.5,
        )
        m = C.metrics(clip, self.rig)
        self.assertNotIn("switch_arm_peak_deg_s", m)
        self.assertFalse(
            any("switch arm speed" in p for p in m["problems"]),
            m["problems"],
        )

    def test_swap_name_is_gated(self):
        """'Swap' in the name (e.g. SwapToSword) triggers the gate — weapon swaps are arm switches."""
        clip = _make_switch_clip(
            "SwapToSword",
            lambda i, t: qx(90 * t / 1.0) + [0, 0, 0],
            1.0,
        )
        m = C.metrics(clip, self.rig)
        self.assertIn("switch_arm_peak_deg_s", m)
        problems = " ".join(m["problems"])
        self.assertIn("switch arm speed", problems)

    def test_tolefthand_name_is_gated(self):
        """'SwordToLeftHand' matches to(left|right)hand — weapon switch to off-hand."""
        clip = _make_switch_clip(
            "SwordToLeftHand",
            lambda i, t: qx(90 * t / 1.0) + [0, 0, 0],
            1.0,
        )
        m = C.metrics(clip, self.rig)
        self.assertIn("switch_arm_peak_deg_s", m)
        problems = " ".join(m["problems"])
        self.assertIn("switch arm speed", problems)

    def test_idletorun_transition_is_not_gated(self):
        """IdleToRunTransition is a locomotion transition — legs only, NOT a weapon switch.
        Even though it contains a slow arm (none at all), the gate must not fire."""
        clip = _make_legs_clip("IdleToRunTransition", 0.5)
        m = C.metrics(clip, self.rig_r6)
        self.assertNotIn("switch_arm_peak_deg_s", m)
        self.assertFalse(
            any("switch arm speed" in p for p in m["problems"]),
            f"IdleToRunTransition must not trigger the switch gate: {m['problems']}",
        )

    def test_grandfathered_clips_warn_not_fail(self):
        """GunSwitch and GunSideSwitch existed before the gate: their CONTENT HASH is grandfathered.
        They warn but do not add a problem."""
        for clip_name in ("GunSwitch", "GunSideSwitch"):
            path = os.path.join(ROOT, "build", "animations", f"{clip_name}.clip.json")
            if not os.path.exists(path):
                self.skipTest(f"{clip_name}.clip.json not built yet")
            c = C.load_clip(path)
            rig = C.load_rig(c["rig"], ROOT)
            m = C.metrics(c, rig)
            # must NOT be a hard problem
            self.assertFalse(
                any("switch arm speed" in p for p in m["problems"]),
                f"{clip_name}: should warn, not fail — problems: {m['problems']}",
            )
            # but must appear as a warning
            warnings = " ".join(m.get("warnings", []))
            self.assertIn("switch arm speed", warnings,
                          f"{clip_name}: expected a grandfather warning")

    def test_grandfathered_name_with_different_content_fails(self):
        """A clip NAMED GunSwitch but with different content (a rebuild) must FAIL the gate —
        grandfathering is by content hash, not name."""
        path = os.path.join(ROOT, "build", "animations", "GunSwitch.clip.json")
        if not os.path.exists(path):
            self.skipTest("GunSwitch.clip.json not built yet")
        c = C.load_clip(path)
        # mutate the content: add a dummy key so the hash no longer matches
        c_modified = dict(c, _test_mutation="grandfathering_breaks_on_content_change")
        rig = C.load_rig(c["rig"], ROOT)
        m = C.metrics(c_modified, rig)
        # the modified clip (same name, different hash) must FAIL — not just warn
        self.assertTrue(
            any("switch arm speed" in p for p in m["problems"]),
            f"GunSwitch with mutated content must fail (not grandfather by name): {m}",
        )

    def test_hash_is_the_motion_not_where_it_was_made(self):
        """The same clip rebuilt in another checkout (kit prove's sandbox) has another source.owner_rig path and
        tool sha: it is the same motion and keeps its grandfathering (2026-11-18: the committed-tree proof's two
        reds). A change to the motion itself still changes the hash."""
        clip = {"name": "GunSwitch", "rig": "R6", "fps": 60, "times": [0, 1 / 60],
                "joints": {"Right Shoulder": [[0, 0, 0, 1, 0, 0, 0]] * 2},
                "source": {"owner_rig": "C:\a\R6_IK.blend", "tool_sha256": "aa", "rig_sha256": "bb"}}
        other = dict(clip, source={"owner_rig": "D:\sandbox\R6_IK.blend", "tool_sha256": "cc", "rig_sha256": "dd"})
        self.assertEqual(C._clip_hash(clip), C._clip_hash(other))
        moved = dict(clip, joints={"Right Shoulder": [[0, 0, 0, 1, 0, 0, 0], [0.1, 0, 0, 1, 0, 0, 0]]})
        self.assertNotEqual(C._clip_hash(clip), C._clip_hash(moved))

    def test_selftest_slow_fixture_fails(self):
        """The bad selftest fixture (_selftest_SwitchSlow) must trip the gate."""
        # Simulate the fixture directly — same path as kit/selftest/anim/
        spec = {
            "name": "_selftest_SwitchSlow",
            "priority": "Action",
            "keys": [
                {"t": 0, "ease": "Linear", "pose": {"Right Arm": [0, 0, 0], "Left Arm": [0, 0, 0]}},
                {"t": 1, "ease": "Linear", "pose": {"Right Arm": [90, 0, 0], "Left Arm": [45, 0, 0]}},
            ],
        }
        dur = 1.0
        n = int(round(dur * FPS)) + 1
        times = [i / FPS for i in range(n)]
        frames = C.spec_frames(spec, times)
        clip = {
            "name": spec["name"], "rig": "R15", "fps": FPS, "duration": dur, "loop": False,
            "priority": "Action", "joints": {j: {"frames": fr} for j, fr in frames.items()},
            "times": times, "events": [],
        }
        m = C.metrics(clip, self.rig)
        self.assertTrue(
            any("switch arm speed" in p for p in m["problems"]),
            f"slow fixture should fail: {m['problems']}",
        )

    def test_selftest_fast_fixture_passes(self):
        """The good control fixture (_selftest_SwitchFast) must pass."""
        spec = {
            "name": "_selftest_SwitchFast",
            "priority": "Action",
            "keys": [
                {"t": 0, "ease": "Linear", "pose": {"Right Arm": [0, 0, 0], "Left Arm": [0, 0, 0]}},
                {"t": 0.05, "ease": "Linear", "pose": {"Right Arm": [150, 0, 0], "Left Arm": [0, 0, 0]}},
                {"t": 0.1, "ease": "Linear", "pose": {"Right Arm": [150, 0, 0], "Left Arm": [120, 0, 0]}},
                {"t": 0.5, "ease": "Linear", "pose": {"Right Arm": [150, 0, 0], "Left Arm": [120, 0, 0]}},
            ],
        }
        dur = 0.5
        n = int(round(dur * FPS)) + 1
        times = [i / FPS for i in range(n)]
        frames = C.spec_frames(spec, times)
        clip = {
            "name": spec["name"], "rig": "R15", "fps": FPS, "duration": dur, "loop": False,
            "priority": "Action", "joints": {j: {"frames": fr} for j, fr in frames.items()},
            "times": times, "events": [],
        }
        m = C.metrics(clip, self.rig)
        self.assertFalse(
            any("switch arm speed" in p for p in m["problems"]),
            f"fast fixture should pass: {m['problems']}",
        )

    def test_built_switch_and_swap_clips_pass(self):
        """Scan loved/built clips that match the gate pattern and verify none hard-fail.
        Uses the same regex as clip.py: switch|swap|to(left|right)hand (case-insensitive).
        Clips whose content hash is grandfathered are skipped (they warn, not fail)."""
        import re
        anim_dir = os.path.join(ROOT, "build", "animations")
        if not os.path.isdir(anim_dir):
            return
        for fname in sorted(os.listdir(anim_dir)):
            if not fname.endswith(".clip.json"):
                continue
            clip_name = fname[: -len(".clip.json")]
            if not re.search(r"switch|swap|to(left|right)hand", clip_name, re.IGNORECASE):
                continue
            path_full = os.path.join(anim_dir, fname)
            c = C.load_clip(path_full)
            if C._clip_hash(c) in C._SWITCH_GATE_GRANDFATHERED:
                continue  # grandfathered by content hash — warns only, skip
            rig = C.load_rig(c["rig"], ROOT)
            m = C.metrics(c, rig)
            self.assertFalse(
                any("switch arm speed" in p for p in m["problems"]),
                f"{clip_name}: non-grandfathered switch/swap clip fails the gate: {m['problems']}",
            )


if __name__ == "__main__":
    unittest.main()
