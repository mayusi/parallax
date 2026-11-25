"""a.reach's solved poses honour a chain joint's after= (card ver5: "after= sequences are not looked at by a.reach"):
an arm that may only lift once a cover has slid out of its way. The travel check stages the cover first and finds
the lift clear; the reach check posed the arm with the cover still shut over it and called it driven in. With the
cover where after= puts it, the pose is clear - and without after= the arm really does lift into the cover."""

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
class ReachAfter(unittest.TestCase):
    def build(self, after):
        src = textwrap.dedent(f"""
            import sys, json, os
            sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
            import rbx
            a = rbx.Asset('_selftest_reach_after', tex=64, size=(3.4, 2.2, 1.0), bevel=0,
                          allow_floating=('Arm', 'Cover'))
            a.material('body', color=(0.5, 0.52, 0.56))
            a.box('Base', (3.4, 0.5, 1.0), (1.0, 0.25, 0), 'body', bevel=0)
            a.box('Arm', (1.0, 0.1, 0.1), (0.5, 1.0, 0), 'body', bevel=0, group='arm')
            a.box('Cover', (0.2, 0.6, 0.6), (0.5, 1.5, 0), 'body', bevel=0, group='cover')
            a.joint('Cover', 'cover', 'slide', (1, 0, 0), min=0, max=2.0)
            a.joint('Shoulder', 'arm', 'hinge', (0, 0, 1), pivot=(0, 1.0, 0), min=0, max=90,
                    after={after!r})
            a.reach('Lift', ['Shoulder'], tip=(1.0, 1.0, 0), poses={{'up': (0.0, 2.0, 0)}})
            a.build()
            """)
        path = os.path.join(tempfile.mkdtemp(), "reach_after.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        env = dict(os.environ, KIT_BUILD=tempfile.mkdtemp(), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path, "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=900, env=env)
        text = out.stdout + out.stderr
        self.assertIn('"schema"', text, text[-2000:])
        status = json.JSONDecoder().raw_decode(text[text.find('{"schema"'):])[0]
        return status

    @staticmethod
    def check(status, name):
        for c in status.get("design") or []:
            if c.get("name") == name:
                return c
        return None

    def test_the_cover_slid_away_first_leaves_the_lift_clear(self):
        st = self.build({"Cover": "max"})
        rc = self.check(st, "reach_clear")   # (a check that holds is not listed among the design's findings)
        self.assertTrue(rc is None or rc["ok"], rc)
        self.assertIn("chains: Lift", st["summary"])
        self.assertIn("1 of 1 poses met", st["summary"])

    def test_with_no_sequence_the_lift_runs_into_the_cover(self):
        st = self.build(None)
        rc = self.check(st, "reach_clear")
        self.assertIsNotNone(rc)
        self.assertFalse(rc["ok"], rc)


if __name__ == "__main__":
    unittest.main()
