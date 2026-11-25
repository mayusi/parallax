"""kit sharpen keeps an OPENING open through its new skin (kit/gen/sharpen_part.py keep_open, on the fixture of
kit/selftest/blender/check_sharpen_keep_open.py: a block with a bore 1.2 voxels across). A voxel remesh shuts it -
every line of sight down it stopped; --keep-open carves it again, every line clear, the skin still closed."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SharpenKeepOpen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "check_sharpen_keep_open.py")
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "--python", script],
                             cwd=REPO, capture_output=True, text=True, timeout=900)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("SHARPEN_KEEP_OPEN ")), None)
        assert line, (run.stderr or run.stdout)[-1200:]
        cls.out = json.loads(line[len("SHARPEN_KEEP_OPEN "):])

    def test_the_bore_is_open_as_made_and_the_remesh_shuts_it(self):
        self.assertEqual(self.out["as_made"], 0, self.out)
        self.assertEqual(self.out["remeshed"], self.out["lines"], self.out)   # (the fault the keep-out answers)

    def test_kept_open_every_line_of_sight_is_clear_and_the_skin_stays_closed(self):
        self.assertEqual(self.out["kept"], 0, self.out)
        self.assertEqual((self.out["open"], self.out["pinched"]), (0, 0), self.out)
        self.assertTrue(self.out["uv"], self.out)


class Parse(unittest.TestCase):
    def test_keep_open_is_read_and_checked(self):
        # (sharpen_part imports bpy: its parser is read from the file and run alone)
        src = open(os.path.join(REPO, "kit", "gen", "sharpen_part.py"), encoding="utf-8").read()
        i, j = src.index("def parse_keep_open"), src.index("KEEP_RINGS =")
        ns = {}
        exec(src[i:j], ns)  # noqa: S102
        P = ns["parse_keep_open"]
        self.assertEqual(P(["prep", "--keep-open", "0,0.5,0.5>1,0.5,0.5@0.02"]), [((0, 0.5, 0.5), (1, 0.5, 0.5), 0.02)])
        for bad in ("0,0.5>1,0.5,0.5@0.02", "0,0.5,0.5>1,0.5,0.5@0", "0,0.5,0.5@0.02"):
            with self.assertRaises(ValueError):
                P(["--keep-open", bad])


if __name__ == "__main__":
    unittest.main()
