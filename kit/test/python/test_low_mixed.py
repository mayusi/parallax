"""The high-and-low route with CAD and non-CAD parts in ONE group (LIMITATIONS_FIXES_V4 Phase 1, 3D-X): a box and a
post beside a CAD plate have no high of their own - their own surface is their high, as the exploded bake already
baked them. The group's bake source (rbx.Asset._low_source) carries them now, so bake_misses reads the surface the bake
did: before, 76% (box) and 89% (post) of their rays were counted as misses the bake never had (18% of the group)."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_low_mixed.py")
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender not found")
class MixedLowGroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_low_mixed"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", FIXTURE, "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1200, env=env,
                           encoding="utf-8", errors="replace")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.report = json.loads(line)

    def test_the_parts_with_no_high_are_not_read_as_misses(self):
        import rbx_bakecage  # noqa: PLC0415  (numpy only)

        g = self.report["facts"]["low"]["groups"]["g"]
        misses = g["bake_misses"]
        self.assertLessEqual(misses["missed"], 0.002, misses)    # (V4: < 0.2%; the kit's own bar is MISSES)
        self.assertLess(misses["missed"], rbx_bakecage.MISSES)
        self.assertNotIn("Block", misses.get("parts", {}))
        self.assertNotIn("Post", misses.get("parts", {}))
        self.assertEqual(self.report["status"], "pass", self.report["summary"])

    def test_the_silhouette_and_the_cage_are_the_cad_parts_own(self):
        g = self.report["facts"]["low"]["groups"]["g"]
        self.assertLess(g["silhouette_mm"]["max_mm"], 1.0)     # (the box and the post: their own surface, 0 mm)
        self.assertLessEqual(g["cage_mm"], 2.0)


if __name__ == "__main__":
    unittest.main()
