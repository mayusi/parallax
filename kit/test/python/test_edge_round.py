"""The rounded-edge highlight the normal bake adds (card 3aan). Unasked, it follows the model's size - except on the
high-and-low route (low=), where the high's own fillets and rounds are the shape: there the bake adds none (a crisp
CAD high's game version showed a ~1 mm band at every rim the high does not have; the car rim and the karambit had
each turned it off by hand). An asked edge_radius is taken as asked on either route."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class EdgeRound(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        script = os.path.join(tmp, "edge_round_probe.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(f"""
                import json, sys
                sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
                import rbx
                got = {{}}
                for key, kw in (("plain", {{}}), ("low", {{"low": True}}), ("low_budget", {{"low": 15000}}),
                                ("plain_asked", {{"edge_radius": 0.01}}), ("low_asked", {{"low": True, "edge_radius": 0.01}}),
                                ("low_zero", {{"low": True, "edge_radius": 0.0}})):
                    a = rbx.Asset("_selftest_edge_round_" + key, tex=64, size=(1.6, 0.4, 0.4), **kw)
                    got[key] = a._edge_round()
                print("ROUND " + json.dumps(got))
                """))
        env = dict(os.environ, KIT_BUILD=os.path.join(tmp, "build"), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
        text = out.stdout + out.stderr
        line = next((ln for ln in text.splitlines() if ln.startswith("ROUND ")), None)
        cls.text = text
        cls.got = json.loads(line[6:]) if line else None

    def test_the_probe_ran(self):
        self.assertIsNotNone(self.got, self.text[-2000:])

    def test_unasked_it_follows_the_models_size(self):
        self.assertAlmostEqual(self.got["plain"], 0.0055 * 1.6, places=6)

    def test_unasked_on_the_high_and_low_route_the_bake_adds_none(self):
        self.assertEqual(self.got["low"], 0.0)
        self.assertEqual(self.got["low_budget"], 0.0)

    def test_an_asked_round_is_taken_as_asked_on_either_route(self):
        self.assertEqual(self.got["plain_asked"], 0.01)
        self.assertEqual(self.got["low_asked"], 0.01)
        self.assertEqual(self.got["low_zero"], 0.0)


if __name__ == "__main__":
    unittest.main()
