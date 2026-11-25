"""A game version's vertex paint held against the paint its master's maps were baked with (card t5tr: "a paint
changed in the script after the master was built is in the file's vertex colours and not in the map, unsaid"). The
engine draws no vertex colour under a SurfaceAppearance (seen in Studio 2026-11-17), so the map's paint is the one
that shows: a game version painted otherwise than its master's bake is said (`paint_stale`), one painted the same
is not."""

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
class PaintStale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.build_dir = os.path.join(cls.tmp, "build")
        cls.script = os.path.join(cls.tmp, "build__selftest_paintstale.py")
        with open(cls.script, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(f"""
                import os, sys
                sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
                import rbx
                shade = float(os.environ.get("PAINT", "0.5"))
                a = rbx.Asset("_selftest_paintstale", tex=128, size=(1.2, 3.4, 1.2), ground=True, stage="master")
                a.material("stone", color=(0.7, 0.68, 0.62), rough=0.8)
                a.box("Post", (1.0, 3.0, 1.0), (0, 1.5, 0), "stone", bevel=0)
                a.vertex_paint((shade, shade, shade), parts=["Post"])
                a.build()
                """))
        cls.master = cls.run_build("0.5", [])

    @classmethod
    def run_build(cls, shade, extra):
        env = dict(os.environ, KIT_BUILD=cls.build_dir, KIT_GAME="none", PAINT=shade, KIT_METHODS_LOCK="0")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", cls.script, "--",
                              "--no-preview", *extra], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=1200, env=env)
        text = out.stdout + out.stderr
        st = None
        if '{"schema"' in text:
            st = json.JSONDecoder().raw_decode(text[text.rfind('{"schema"'):])[0]
        return out.returncode, st, text

    def stale(self, st):
        return [c for c in st.get("design") or [] if c.get("name") == "paint_stale"]

    def test_the_master_built(self):
        code, st, text = self.master
        self.assertEqual(code, 0, text[-2000:])
        self.assertTrue((st.get("facts") or {}).get("paint"), text[-1500:])

    def test_a_game_version_painted_as_its_master_is_not_said(self):
        code, st, text = self.run_build("0.5", ["--optimize"])
        self.assertEqual(code, 0, text[-2000:])
        self.assertEqual(self.stale(st), [], st.get("summary"))

    def test_a_game_version_painted_otherwise_is_said(self):
        code, st, text = self.run_build("0.9", ["--optimize"])
        self.assertEqual(code, 0, text[-2000:])
        got = self.stale(st)
        self.assertTrue(got, (st or {}).get("summary"))
        self.assertIn("rebuild the master", json.dumps(got))


if __name__ == "__main__":
    unittest.main()
