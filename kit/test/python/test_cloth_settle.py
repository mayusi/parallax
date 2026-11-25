"""A cloth at rest lies ON what it rests on (card maah; his limitations review V3: "cloth ... contacts host surfaces
flush (0 air gap)"): the simulation stops a hair off its collider; a.cloth settles every point within that margin
onto the surface and no longer exempts the cloth and its support from the floating check. A cloth inside a.mirror /
a.repeat is refused (its copies would never fall)."""

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Settle(unittest.TestCase):
    def test_flush_and_held_by_the_floating_check(self):
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "probe_cloth_gap.py"), "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=1200)
        i = out.stdout.rfind("GAP ")
        self.assertGreaterEqual(i, 0, out.stdout[-1500:] + out.stderr[-1500:])
        got = json.JSONDecoder().raw_decode(out.stdout[i + 4:])[0]
        self.assertLess(got["p10_mm"], 1.0, got)          # (the simulation's margin was ~7 mm)
        self.assertGreater(got["settled"], 0)
        self.assertEqual(got["exempt"], [])
        k = out.stdout.find('{"schema"')
        st = json.JSONDecoder().raw_decode(out.stdout[k:])[0]
        self.assertEqual(st["facts"]["floating"], [])

    def test_inside_a_mirror_is_refused(self):
        src = (
            "import sys, os\n"
            f"sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})\n"
            "import rbx\n"
            "a = rbx.Asset('_selftest_cloth_mirror', tex=64, size=(2, 1, 2), ground=True)\n"
            "a.material('wood', color=(0.4, 0.3, 0.2)); a.material('linen', color=(0.8, 0.8, 0.7))\n"
            "a.box('Table', (1, 1, 1), (0.8, 0.5, 0), 'wood')\n"
            "with a.mirror('X'):\n"
            "    a.cloth('Cover', (1.4, 1.4), (0.8, 1.3, 0), 'linen', over=['Table'])\n")
        d = tempfile.mkdtemp()
        path = os.path.join(d, "cloth_mirror.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("cloth: not inside a.mirror", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
