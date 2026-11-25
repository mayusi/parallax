"""A build gives the same bytes every time (card nrey; his limitations review V3: "guarantee identical byte/hash
output across 3 consecutive builds"): the zone fixture (a sphere split along planes past its poles) built three times
with the bake cache off - its mesh (vertices, faces, materials, UVs, in order) and every baked map identical. It was
not: Blender 5.2's create_uvsphere lists its faces in another order every run (rbx._faces_in_order fixes the order),
and a set of mesh edges handed to a dissolve was ordered by memory address."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PROBE = os.path.join(ROOT, "kit", "selftest", "blender", "probe_same_twice.py")


def run(fixture):
    env = dict(os.environ, KIT_BAKE_CACHE="0")
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", PROBE, "--",
                          os.path.join(ROOT, "kit", "selftest", "blender", fixture)],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200,
                         env=env)
    i = out.stdout.rfind("SAME ")
    return out.returncode, (json.JSONDecoder().raw_decode(out.stdout[i + 5:])[0] if i >= 0 else None), \
        out.stdout[-1500:] + out.stderr[-1500:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class SameEveryTime(unittest.TestCase):
    def test_the_zone_fixture_three_times(self):
        runs = [run("build_zone_split.py") for _ in range(3)]
        for code, got, log in runs:
            self.assertEqual(code, 0, log)
            self.assertTrue(got and all(v["maps"] for v in got.values()), log)
        self.assertEqual(runs[0][1], runs[1][1])
        self.assertEqual(runs[0][1], runs[2][1])


if __name__ == "__main__":
    unittest.main()
