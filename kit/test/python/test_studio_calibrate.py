"""The Roblox-look rig FITTED to Studio (kit/tools/studio_calibrate.py, kit/blender/rbx_lookdev.calibrated_rig): the
rules a grey sphere shot in Studio showed (2026-11-18) held in the rig - the ambient is ONE even colour, the larger of
Ambient and OutdoorAmbient (either alone lit it the same, both together no more); ColorShift_Top changes nothing (black
and white alike); exposure doubles; the sun is white, Brightness x the fitted number - light_rig takes the fitted rig
whenever roblox_looks.json has one; the looks file keeps its hand-written layout; a fit too far off is never written.
The Studio side (the shots) is run by a session through the Studio tools; it cannot run here."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402
import studio_calibrate as sc  # noqa: E402

BLENDER = cad_check.blender()

PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
import bpy, rbx_lookdev as L
cal = L.calibration()
out = {"calibrated": bool(cal)}
def world(p):
    sc = bpy.data.scenes.new("t")
    made, label = L.light_rig(sc, "t", p, "as_read")
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    sun = next(o for o in made if getattr(o, "type", "") == "LIGHT")
    return {"bg": list(bg.inputs["Color"].default_value)[:3], "sun": sun.data.energy, "colour": list(sun.data.color),
            "label": label}
base = {"Brightness": 2, "SunDirection": [-0.47, 0.82, 0.31]}
out["amb"] = world({**base, "Ambient": [128, 128, 128], "OutdoorAmbient": [0, 0, 0]})
out["out"] = world({**base, "Ambient": [0, 0, 0], "OutdoorAmbient": [128, 128, 128]})
out["both"] = world({**base, "Ambient": [128, 128, 128], "OutdoorAmbient": [128, 128, 128]})
out["more"] = world({**base, "Ambient": [64, 64, 64], "OutdoorAmbient": [200, 200, 200]})
out["black"] = world({**base, "ColorShift_Top": [0, 0, 0]})
out["white"] = world({**base, "ColorShift_Top": [255, 255, 255]})
out["ev1"] = world({**base, "ExposureCompensation": 1})
night = {"Brightness": 4.5, "ExposureCompensation": 0.1, "EnvironmentDiffuseScale": 0.6, "SunDirection": [0.5, -0.8, 0.3],
         "MoonDirection": [-0.5, 0.8, 0.3], "OutdoorAmbient": [118, 130, 166], "Ambient": [64, 66, 84]}
out["night"] = world(night)
out["night_no_sky"] = world({**night, "EnvironmentDiffuseScale": 0.0})
out["underground"] = world({**night, "MoonDirection": [-0.5, -0.8, 0.3]})
out["day_night_sky"] = world({**base, "EnvironmentDiffuseScale": 0.6})
sc = bpy.data.scenes.new("v")
L.roblox_view(sc)
out["view"] = sc.view_settings.view_transform
out["cal"] = cal
print("PROBE " + json.dumps(out))
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TheFittedRig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
            fh.write(PROBE)
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", fh.name, "--",
                            os.path.join(ROOT, "kit", "blender")], capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
        os.unlink(fh.name)
        line = next((x for x in r.stdout.splitlines() if x.startswith("PROBE ")), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.p = json.loads(line[6:])

    def test_the_looks_file_carries_a_fit_and_the_rig_takes_it(self):
        self.assertTrue(self.p["calibrated"])
        self.assertIn("fitted to Studio", self.p["amb"]["label"])
        self.assertEqual(self.p["view"], self.p["cal"]["view_transform"])

    def test_either_ambient_alone_lights_the_same_and_both_no_more(self):
        a, o, b = self.p["amb"]["bg"], self.p["out"]["bg"], self.p["both"]["bg"]
        for x, y in ((a, o), (a, b)):
            for u, v in zip(x, y):
                self.assertAlmostEqual(u, v, places=6)
        self.assertGreater(min(a), 0.0)

    def test_the_larger_ambient_counts(self):
        m, o = self.p["more"]["bg"], self.p["out"]["bg"]
        self.assertGreater(m[0], o[0])                  # (200 outdoor > 128 outdoor; the 64 indoor adds nothing)

    def test_colour_shift_changes_nothing_and_the_sun_is_white(self):
        self.assertEqual(self.p["black"]["sun"], self.p["white"]["sun"])
        self.assertEqual(self.p["black"]["colour"], [1.0, 1.0, 1.0])
        self.assertAlmostEqual(self.p["black"]["sun"], 2 * self.p["cal"]["sun_per_brightness"], places=4)

    def test_the_night_moon_and_its_sky(self):
        # (moon_share of the sun's number, plus the night sky's light along the moon: EnvironmentDiffuseScale x
        #  night_sky_key, whatever the Brightness - both x 2^Exposure; the sky's even glow at night_sky of the day's)
        c, gain = self.p["cal"], 2 ** 0.1
        want = (4.5 * c["sun_per_brightness"] * c["moon_share"] + 0.6 * c["night_sky_key"]) * gain
        self.assertAlmostEqual(self.p["night"]["sun"], want, places=4)
        self.assertAlmostEqual(self.p["night"]["sun"] - self.p["night_no_sky"]["sun"], 0.6 * c["night_sky_key"] * gain,
                               places=4)
        self.assertIn("moon", self.p["night"]["label"])
        night_glow = self.p["night"]["bg"][2] - self.p["night_no_sky"]["bg"][2]
        day_glow = self.p["day_night_sky"]["bg"][2] - self.p["black"]["bg"][2]
        self.assertAlmostEqual(night_glow / day_glow / gain, c["night_sky"], places=3)   # (the night is at +0.1 EV)

    def test_no_key_light_when_the_moon_is_below_the_ground_too(self):
        self.assertEqual(self.p["underground"]["sun"], 0.0)

    def test_exposure_doubles(self):
        self.assertAlmostEqual(self.p["ev1"]["sun"], 2 * self.p["black"]["sun"], places=4)


class Decide(unittest.TestCase):
    """the fit is written only within the bars (review 2026-11-18: a mean hid one realistic state far off)"""

    def fit(self, mean=3.0, worst=5.0, bound=()):
        return {"best": "K", "results": {"K": {"mean_error": mean, "worst": {"name": "s", "error": worst},
                                                "at_bound": list(bound), "states": []}}}

    def test_within_the_bars_it_is_written(self):
        self.assertTrue(sc.decide(self.fit())[0])

    def test_a_mean_over_the_bar_is_refused(self):
        self.assertFalse(sc.decide(self.fit(mean=sc.FIT_BAR + 0.1))[0])

    def test_one_state_far_off_is_refused_though_the_mean_is_fine(self):
        ok, why = sc.decide(self.fit(mean=2.0, worst=sc.STATE_BAR + 1))
        self.assertFalse(ok)
        self.assertIn("one state", why)

    def test_a_number_stuck_at_the_end_of_its_search_is_refused(self):
        self.assertFalse(sc.decide(self.fit(bound=["moon_share"]))[0])


class Writer(unittest.TestCase):
    def test_lists_of_numbers_stay_on_one_line(self):
        text = sc.compact(json.dumps({"Ambient": [64, 66, 84], "names": ["a", "b"], "d": [0.2903, -0.4344]}, indent=1))
        self.assertIn('"Ambient": [64, 66, 84]', text)
        self.assertIn('"d": [0.2903, -0.4344]', text)
        self.assertEqual(json.loads(text)["names"], ["a", "b"])

    def test_a_fit_too_far_off_is_never_written(self):
        self.assertLessEqual(sc.FIT_BAR, 10.0)
        looks = json.load(open(sc.LOOKS, encoding="utf-8"))
        cal = looks.get("_calibration")
        self.assertIsNotNone(cal)
        self.assertLessEqual(cal["mean_error_grey_levels"], sc.FIT_BAR)
        self.assertLessEqual(cal["worst_state"]["error"], sc.STATE_BAR)


if __name__ == "__main__":
    unittest.main()
