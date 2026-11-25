"""The mechanism gate's travel through REAL builds (kit/selftest/blender/build_travel_pin.py and its clear twin; the
owner's limitations page D-R05): a pin standing between the old five stops is found, the five stops alone read
clear (what the old check saw), and the same travel with nothing in the way passes."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()


def build(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_travel_build"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview", "--geo"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin, cls.clear = build("build_travel_pin.py"), build("build_travel_clear.py")
        cls.seated = build("build_travel_seated.py")

    def test_a_runner_that_left_its_seats_and_meets_a_pin_of_the_same_body_is_found(self):
        # (fewer colliding pairs than at rest while it cuts the pin: found by the depth test between the stops,
        # which runs where two PARTS newly touch - never by the group's total)
        self.assertEqual(self.seated["status"], "fail")
        said = next(c for c in self.seated["design"] if c["name"] == "mechanism")
        self.assertEqual(len(said["value"]), 1)
        self.assertIn("surface points inside it", said["value"][0])
        self.assertIn("Runner in Pin", said["value"][0])
        m = self.seated["facts"]["mechanism"]
        for stop in ("0", "1", "2", "3", "4"):
            self.assertEqual(m[f"Runner@{stop}"], "clear", stop)

    def test_a_pin_between_the_five_stops_is_found_and_named(self):
        self.assertEqual(self.pin["status"], "fail")
        said = next(c for c in self.pin["design"] if c["name"] == "mechanism")
        text = " ".join(said["value"]) if isinstance(said["value"], list) else str(said["value"])
        self.assertIn("drives into 'main'", text)
        self.assertIn("Runner into Pin", text)
        self.assertIn("and on to", text)                                  # (one line for the stretch, not one a stop)
        self.assertEqual(len(said["value"]), 1)

    def test_the_old_five_stops_alone_read_clear(self):
        m = self.pin["facts"]["mechanism"]
        for stop in ("0", "1", "2", "3", "4"):                           # the quarter stops of a 4-stud travel
            self.assertEqual(m[f"Runner@{stop}"], "clear", stop)
        hits = sorted(float(k.split("@")[1]) for k, v in m.items() if v == "drives in")
        self.assertTrue(hits and all(1.0 < h < 2.0 for h in hits), hits)  # between the second stop and the third

    def test_the_stops_follow_the_travel(self):
        self.assertGreater(self.pin["facts"]["mechanism"]["Runner@stops"], 20)
        self.assertNotIn("Runner@coarse", self.pin["facts"]["mechanism"])

    def test_the_same_travel_with_the_pin_beside_the_path_passes(self):
        m = self.clear["facts"]["mechanism"]
        self.assertFalse(any(c["name"] == "mechanism" for c in self.clear["design"]))
        self.assertFalse(any(v == "drives in" for v in m.values()))
        self.assertEqual(m["Runner@stops"], self.pin["facts"]["mechanism"]["Runner@stops"])


if __name__ == "__main__":
    unittest.main()
