"""What stage L's reviews left (card 9bsn): a socket's size is MEASURED on its part - a hole's or a pin's width -
filling a size left out (a mate's fit= reads it) and saying a size given that the part does not measure."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_mate  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


class Across(unittest.TestCase):
    def test_a_round_hole_reads_its_width_off_middle_too(self):
        # (a socket 0.1 off the middle of a 1.0 hole: the opposite pairs still sum to the width)
        import math
        d = []
        for k in range(rbx_mate.RAYS):
            t = 2 * math.pi * k / rbx_mate.RAYS
            ux, uy = math.cos(t), math.sin(t)
            b = 0.1 * ux   # (the point at (0.1, 0) inside a circle of radius 0.5: the distance along (ux, uy))
            d.append(-b + math.sqrt(b * b - (0.01 - 0.25)))
        width, spread = rbx_mate.across(d)
        self.assertAlmostEqual(width, 1.0, delta=0.02)
        self.assertLess(spread, 0.05)

    def test_a_ray_that_met_nothing_reads_nothing(self):
        self.assertIsNone(rbx_mate.across([0.5] * (rbx_mate.RAYS - 1) + [None]))

    def test_a_size_said_wrong_is_said(self):
        self.assertIsNone(rbx_mate.size_problem("Bore", 0.5, 0.52, "hole"))
        self.assertIn("measures 0.8", rbx_mate.size_problem("Bore", 0.5, 0.8, "hole"))
        self.assertIsNone(rbx_mate.size_problem("Bore", None, 0.8, "hole"))


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Measured(unittest.TestCase):
    def build(self, bore_said):
        src = textwrap.dedent(f"""
            import sys, json, os
            sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
            import rbx
            a = rbx.Asset('_selftest_socket_sizes', tex=64, size=(2.0, 2.0, 2.0), bevel=0)
            a.material('body', color=(0.5, 0.52, 0.56))
            a.material('peg', color=(0.75, 0.6, 0.25), metal=1.0, rough=0.4)
            a.box('Body', (2.0, 1.0, 2.0), (0, 0.5, 0), 'body', bevel=0)
            a.cut('Body', a.cylinder('Bore', 0.3, 1.4, (0, 0.5, 0), 'body', axis='Y', segments=32))
            a.socket('Mouth', 'Body', (0, 1.0, 0), axis=(0, 1, 0), size={bore_said!r})
            a.cylinder('Peg', 0.27, 0.8, (0, 1.4, 0), 'peg', axis='Y', segments=32)
            a.socket('Foot', 'Peg', (0, 1.0, 0), axis=(0, -1, 0))
            a.mate('Peg in Mouth', 'Foot', 'Mouth', fit=(0.01, 0.05))
            a.build()
            st = json.load(open(os.path.join(rbx.BUILD, 'models', a.name + '.status.json'), encoding='utf-8')) \\
                if os.path.isfile(os.path.join(rbx.BUILD, 'models', a.name + '.status.json')) else None
            print('SOCKETS ' + json.dumps({{n: {{k: v for k, v in s.items() if k in ('size', 'size_from')}}
                                            for n, s in a.sockets.items()}}))
            print('FACTS ' + json.dumps(a._mate_facts))
            w = getattr(a, '_socket_size_warn', None)
            print('WARN ' + json.dumps(w and w.get('summary', w)))
            """)
        path = os.path.join(tempfile.mkdtemp(), "sockets.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        env = dict(os.environ, KIT_BUILD=tempfile.mkdtemp(), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path, "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=900, env=env)
        got = {}
        for line in out.stdout.splitlines():
            for key in ("SOCKETS ", "FACTS ", "WARN "):
                if line.startswith(key):
                    got[key.strip()] = json.loads(line[len(key):])
        self.assertIn("FACTS", got, out.stdout[-1500:] + out.stderr[-1500:])
        return got

    def test_a_size_left_out_is_measured_and_the_fit_reads_it(self):
        got = self.build(None)
        self.assertEqual(got["FACTS"]["measured"]["Mouth"]["kind"], "hole")
        self.assertAlmostEqual(got["FACTS"]["measured"]["Mouth"]["across"], 0.6, delta=0.02)
        self.assertEqual(got["FACTS"]["measured"]["Foot"]["kind"], "pin")
        self.assertAlmostEqual(got["FACTS"]["measured"]["Foot"]["across"], 0.54, delta=0.02)
        self.assertEqual(got["SOCKETS"]["Foot"]["size_from"], "measured")
        self.assertEqual(got["FACTS"]["held"], 1)   # (0.6 - 0.54) / 2 = 0.03 each side: inside the fit asked
        self.assertIsNone(got["WARN"])

    def test_a_size_said_that_the_part_does_not_measure_is_said(self):
        got = self.build(0.9)
        self.assertIn("Mouth", json.dumps(got["WARN"]))
        self.assertIn("a hole", json.dumps(got["WARN"]))


if __name__ == "__main__":
    unittest.main()
