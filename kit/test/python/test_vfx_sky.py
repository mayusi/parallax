"""The judging skies on both renderers (LIMITATIONS_FIXES_V4 13.3.1: calibrate "across Daylight / Overcast / Sunset /
Night"). What is proven: the Studio booth (kit/vfx/booth.luau SKIES) has exactly the browser player's four skies
(kit/vfx/player/player.js SKIES) and kit vfx play / booth take the same names (kit/cmd/content.luau VFX_SKIES =
calibrate.SKIES); the booth's night is its original dusk arena number for number (the 2026-10-10 calibration's light);
kit vfx booth --sky writes the sky into the run's job (and else the preset's booth.sky, else night), an unknown sky is
refused by play and booth; calibrate.py --sky refuses recordings made under another sky or not saying theirs, and
writes nothing then.
Run: python -m pytest kit/test/python/test_vfx_sky.py -q"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import calibrate  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def kit(*args):
    env = dict(os.environ, KIT_GAME="none")
    p = subprocess.run(["lune", "run", "kit", *args, "--game", "none"], cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300)
    return p.returncode, p.stdout + p.stderr


class SameSkies(unittest.TestCase):
    def test_booth_player_commands_and_calibrate_name_the_same_four(self):
        js = read("kit/vfx/player/player.js")
        block = js[js.index("const SKIES = {"):]
        block = block[:block.index("\n};")]
        player = set(re.findall(r"^\s+([a-z]+): \{", block, re.M))
        booth_src = read("kit/vfx/booth.luau")
        bblock = booth_src[booth_src.index("local SKIES: {"):]
        bblock = bblock[:bblock.index("\n}\n")]
        booth = set(re.findall(r"^\t([a-z]+) = \{", bblock, re.M))
        content = read("kit/cmd/content.luau")
        cmd = set(re.findall(r'"([a-z]+)"', re.search(r"local VFX_SKIES = \{([^}]*)\}", content).group(1)))
        self.assertEqual(player, {"night", "day", "overcast", "sunset"})
        self.assertEqual(booth, player)
        self.assertEqual(cmd, player)
        self.assertEqual(set(calibrate.SKIES), player)

    def test_booth_night_is_the_original_dusk_arena(self):
        b = read("kit/vfx/booth.luau")
        night = b[b.index("\tnight = {"):b.index("\tday = {")]
        for said in ("clock = 18.55", "sun = 1.6", "exposure = -0.15", "ambient = { 34, 32, 44 }", "outdoor = { 82, 74, 92 }",
                     "density = 0.36", "offset = 0.15", "color = { 196, 156, 132 }", "decay = { 92, 72, 112 }", "glare = 0.5",
                     "haze = 1.8"):
            self.assertIn(said, night)
        self.assertIn("local K = SKIES[job.sky or \"\"] or SKIES.night", b)


class Commands(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(os.path.join(ROOT, "assets", "effects", "g2_duel.json")):
            self.skipTest("the author's g2_duel preset (assets/effects/g2_duel.json) is not shipped with the kit")

    def test_booth_writes_the_sky_into_its_job(self):
        job = os.path.join(ROOT, "build", "vfx", "booth", "g2_duel.job.json")
        code, said = kit("vfx", "booth", "g2_duel", "--sky", "overcast")
        self.assertEqual(code, 0, said[-400:])
        with open(job, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["sky"], "overcast")
        code, said = kit("vfx", "booth", "g2_duel")        # no --sky, no booth.sky in g2_duel: night
        self.assertEqual(code, 0, said[-400:])
        with open(job, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["sky"], "night")

    def test_an_unknown_sky_is_refused(self):
        for cmd in ("booth", "play"):
            code, said = kit("vfx", cmd, "g2_duel", "--sky", "dusk")
            self.assertNotEqual(code, 0)
            self.assertIn('sky "dusk" is not a judging sky', said)


class CalibrateRefusesAnotherSky(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="vfx_sky_")
        self.old = os.getcwd()
        os.chdir(self.dir)
        os.makedirs(os.path.join("build", "vfx", "booth"))

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.dir, ignore_errors=True)

    def files(self, booth_sky, play_sky):
        with open(os.path.join("build", "vfx", "booth", "fx.job.json"), "w") as fh:
            json.dump({"name": "fx"} if booth_sky is None else {"name": "fx", "sky": booth_sky}, fh)
        with open(os.path.join("build", "vfx", "booth", "fx_play.metrics.json"), "w") as fh:
            json.dump({"frames": []} if play_sky is None else {"frames": [], "sky": play_sky}, fh)

    def test_the_rule(self):
        self.files("day", "day")
        self.assertEqual(calibrate.sky_problems("fx", "day"), [])
        self.files("night", "day")
        self.assertEqual(calibrate.sky_problems("fx", "day"), ["the booth recorded under night, not day"])
        self.files("day", None)
        self.assertIn("does not say its sky", calibrate.sky_problems("fx", "day")[0])

    def test_main_refuses_and_writes_nothing(self):
        self.files("night", "night")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = calibrate.main(["fx", "--sky", "day"])
        self.assertEqual(code, 1)
        line = json.loads(said.getvalue().strip().splitlines()[-1])
        self.assertIn("recorded under night, not day", line["summary"])
        self.assertFalse(os.path.exists(os.path.join("build", "vfx", "booth", "fx_calibration_day.json")))


if __name__ == "__main__":
    unittest.main()
