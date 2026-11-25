"""rbx_pillow.self_crossings — a redraw that crosses itself is refused by a.pillow (it tore Scarborough Fair's thin
gold arc: 186 open edges): a bow-tie crosses once, a square and a thin curved band never."""

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
CODE = r"""
import sys, json, math
sys.path.insert(0, r"%s")
import rbx_pillow as R
band = ([(15 * math.cos(0.2 + 2.4 * k / 39), 15 * math.sin(0.2 + 2.4 * k / 39)) for k in range(40)]
        + [(14 * math.cos(2.6 - 2.4 * k / 39), 14 * math.sin(2.6 - 2.4 * k / 39)) for k in range(40)])
print("CROSS " + json.dumps({"bowtie": R.self_crossings([(0, 0), (10, 10), (10, 0), (0, 10)]),
                             "square": R.self_crossings([(0, 0), (10, 0), (10, 10), (0, 10)]),
                             "band": R.self_crossings(band)}))
""" % os.path.join(REPO, "kit", "blender").replace("\\", "/")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Crossings(unittest.TestCase):
    def test_counts(self):
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", CODE], capture_output=True, text=True,
                           timeout=300)
        line = next(ln for ln in r.stdout.splitlines() if ln.startswith("CROSS "))
        got = json.loads(line[6:])
        self.assertEqual(got, {"bowtie": 1, "square": 0, "band": 0})


if __name__ == "__main__":
    unittest.main()
