"""What stage K's review left (card upjv): a kitbash lender rebuilt since the owner's verdict lends nothing (his verdict
is on a build, not a name); a blob's metaball never melts into another of its base name."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import parts  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


class JudgedThisBuild(unittest.TestCase):
    V = {"date": "2026-11-10", "time": 1794288034, "build": "S1 (aaee5d81)"}

    def test_rebuilt_after_the_verdict_is_refused(self):
        ok, why = parts.judged_this_build(self.V, "29929f358d69", 1794306546)
        self.assertFalse(ok)
        self.assertIn("rebuilt", why)
        self.assertIn("29929f358d69", why)

    def test_the_build_he_named_lends(self):
        self.assertTrue(parts.judged_this_build(self.V, "aaee5d81", 1794306546)[0])

    def test_built_before_the_verdict_lends(self):
        self.assertTrue(parts.judged_this_build(self.V, "29929f358d69", 1794288000)[0])

    def test_an_old_note_with_no_time_is_read_to_the_end_of_its_day(self):
        v = {"date": "2026-11-10"}
        self.assertTrue(parts.judged_this_build(v, None, 1794288034)[0])   # (the same day)
        self.assertFalse(parts.judged_this_build(v, None, 1794288034 + 3 * 86400)[0])


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Blob(unittest.TestCase):
    def run_script(self, body):
        src = ("import sys, bpy\n"
               f"sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})\n"
               "import rbx\n"
               "a = rbx.Asset('_selftest_blob_names', tex=64, size=(2, 2, 2))\n"
               "a.material('smoke', (0.8, 0.8, 0.8))\n" + body)
        path = os.path.join(tempfile.mkdtemp(), "blob.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)

    def test_a_dotted_name_builds(self):
        out = self.run_script("a.blob('Puff.1', [(0, 0, 0, 0.5)], 'smoke', resolution=0.1)\nprint('BLOB OK')\n")
        self.assertIn("BLOB OK", out.stdout, out.stderr[-800:])

    def test_a_metaball_of_its_name_is_refused(self):
        out = self.run_script("mb = bpy.data.metaballs.new('x')\nmb.elements.new()\n"
                              "bpy.context.scene.collection.objects.link(bpy.data.objects.new('KitBlob0xPuff.007', mb))\n"
                              "a.blob('Puff', [(0, 0, 0, 0.5)], 'smoke', resolution=0.1)\nprint('BLOB OK')\n")
        self.assertNotIn("BLOB OK", out.stdout)
        self.assertIn("would melt into this one", out.stdout + out.stderr)


sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import numpy as np  # noqa: E402
import rbx_nurbs  # noqa: E402

CONE = [[(0, 1, 0)] * 4, [(-1, 0, -1), (-0.3, 0, -1), (0.3, 0, -1), (1, 0, -1)],
        [(-1, 0, 1), (-0.3, 0, 1), (0.3, 0, 1), (1, 0, 1)]]


def ring(rows, radius=1.0, n=8):
    out = []
    for y, r in rows:
        row = [(r * np.cos(2 * np.pi * k / n), y, r * np.sin(2 * np.pi * k / n)) for k in range(n)]
        out.append(row + [row[0]])
    return out


class Joins(unittest.TestCase):
    def test_a_pole_faces_and_has_a_wall(self):
        g = rbx_nurbs.surface(CONE, 12, 8)
        j = rbx_nurbs.seams(g)
        self.assertTrue(j["pole_v0"])
        self.assertFalse(j["ring_u"])
        n = rbx_nurbs.normals(g, j)
        self.assertAlmostEqual(float(np.linalg.norm(n[0, 0])), 1.0, places=5)   # (it was nothing: no wall)
        self.assertTrue(np.allclose(n[0], n[0, 0]))

    def test_a_ring_faces_alike_across_its_seam(self):
        g = rbx_nurbs.surface(ring([(0, 1.0), (0.5, 1.0), (1, 1.0)]), 24, 6)
        j = rbx_nurbs.seams(g)
        self.assertTrue(j["ring_u"])
        n = rbx_nurbs.normals(g, j)
        self.assertTrue(np.allclose(n[:, 0], n[:, -1], atol=1e-9))

    def test_the_old_call_is_unchanged(self):
        g = rbx_nurbs.surface(CONE, 6, 6)
        self.assertTrue(np.allclose(rbx_nurbs.normals(g)[1:], rbx_nurbs.normals(g, rbx_nurbs.seams(g))[1:]))


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class PatchJoins(unittest.TestCase):
    def test_a_cone_a_tube_and_a_dome_close_with_one_wall(self):
        body = f"CONE = {CONE!r}\n" + textwrap.dedent("""
            import bmesh, json, math
            def ring(rows, n=8):
                out = []
                for y, r in rows:
                    row = [(r * math.cos(2 * math.pi * k / n), y, r * math.sin(2 * math.pi * k / n)) for k in range(n)]
                    out.append(row + [row[0]])
                return out
            a.patch('Cone', CONE, 'smoke', steps=(12, 8), thick_mm=30)
            a.patch('Tube', ring([(0, 1.0), (0.5, 1.1), (1, 1.0)]), 'smoke', steps=(24, 6), thick_mm=30)
            a.patch('Dome', ring([(1, 0.0), (0.8, 0.7), (0.3, 1.0), (0, 1.0)]), 'smoke', steps=(24, 8), thick_mm=30)
            out = {}
            for o, _ in a.parts:
                bm = bmesh.new(); bm.from_mesh(o.data)
                out[o.name] = {'open': sum(1 for e in bm.edges if not e.is_manifold),
                               'tiny': sum(1 for f in bm.faces if f.calc_area() < 1e-9), 'verts': len(bm.verts)}
            print('JOINS ' + json.dumps(out))
            print('SAID ' + json.dumps(a.design['surfaces']))
            """)
        out = Blob.run_script(self, body)
        line = [x for x in out.stdout.splitlines() if x.startswith("JOINS ")]
        self.assertTrue(line, out.stdout[-800:] + out.stderr[-1500:])
        import json
        got = json.loads(line[0][6:])
        for name in ("Cone", "Tube", "Dome"):
            self.assertEqual(got[name]["open"], 0, (name, got))
            self.assertEqual(got[name]["tiny"], 0, (name, got))
        # the tube's seam is welded: 24 points round each row, not 25 (two walls on each other there before)
        self.assertEqual(got["Tube"]["verts"], 2 * 24 * 7)
        # the dome: a ring with a pole on top (one point per skin) and an open rim
        self.assertEqual(got["Dome"]["verts"], 2 * (24 * 8 + 1))
        said = {s["name"]: s.get("joins") for s in json.loads([x for x in out.stdout.splitlines() if x.startswith("SAID ")][0][5:])}
        self.assertEqual(said["Tube"], ["ring_u"])
        self.assertIn("pole_v0", said["Dome"])


if __name__ == "__main__":
    unittest.main()
