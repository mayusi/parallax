"""kit/vfx/vault.py check: an untouched kit starter (as `kit init` seeded it: kit/starter/vfx effects and meshes,
kit/starter/textures, an example's packed parts and textures with their pictures pointed into <textures>/_library/)
is the kit's piece, so a new project's verify is green; from its first edit it is the project's and must be saved; a
piece saved here is checked like any other (stale when it changes); a new piece is always required. What decides is
the kit's record (kit/vfx/starters.json, kit/vfx/starters.py), never the project's kit/starter/ copy: bending that
copy to match a piece recognises nothing."""
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))

import starters  # noqa: E402
import vault  # noqa: E402

SPARK = {"version": 3, "duration": 1, "layers": [{"kind": "sprite", "at": 0, "count": 4, "texture": "glow"}]}
PART = {"version": 3, "layers": [{"kind": "sprite", "at": 0, "count": 2, "texture": "t"}]}
TEX_DEPS = '{\n "recipe": "import",\n "source": "__DEPS__/textures/t.png"\n}\n'


class Starters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit", "starter")
        self.write(os.path.join(self.kit, "vfx", "spark.json"), json.dumps(SPARK, indent=1))
        self.write(os.path.join(self.kit, "vfx", "_textures.json"), "{}")
        self.write(os.path.join(self.kit, "vfx", "meshes", "ring.json"), '{"shape": "ring"}')
        self.write(os.path.join(self.kit, "vfx", "_deps", "ex", "parts", "p.json"), json.dumps(PART))
        self.write(os.path.join(self.kit, "vfx", "_deps", "ex", "textures", "t.json"), TEX_DEPS)
        self.write(os.path.join(self.kit, "textures", "glow.json"), '{"recipe": "glow"}')
        self.proj = os.path.join(self.tmp, "game")
        os.makedirs(self.proj)
        self.old = os.getcwd()
        os.chdir(self.proj)
        # what kit init writes (kit/cmd/setup.luau + kit/lib/library.luau installVfx)
        self.copy("vfx/spark.json", "assets/effects/spark.json")
        self.copy("vfx/_textures.json", "assets/effects/_textures.json")
        self.copy("vfx/meshes/ring.json", "assets/effects/meshes/ring.json")
        self.copy("vfx/_deps/ex/parts/p.json", "assets/effects/parts/p.json")
        self.copy("textures/glow.json", "assets/textures/glow.json")
        self.write("assets/textures/t.json", TEX_DEPS.replace("__DEPS__/textures/", "assets/textures/_library/"))
        # the kit's record of those starters, as the kit's home writes it (kit/vfx/starters.py --write)
        self.record = os.path.join(self.tmp, "kit", "vfx", "starters.json")
        os.makedirs(os.path.dirname(self.record))
        starters.write(os.path.join(self.tmp, "kit"), self.record)
        self.saved_record = vault.RECORD
        vault.RECORD = self.record

    def tearDown(self):
        vault.RECORD = self.saved_record
        os.chdir(self.old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, text, newline="\n"):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)

    def copy(self, rel, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(self.kit, rel), dst)

    def args(self):
        return argparse.Namespace(effects="assets/effects", textures="assets/textures", build="build", out="library/vfx")

    def run_cmd(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(self.args())
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_a_new_project_with_only_untouched_starters_passes(self):
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["kit_starters"], 5)  # spark, ring, p, glow, t (the packed texture with its picture path moved)
        self.assertIn("untouched kit starter", out["summary"])

    def test_a_starter_with_windows_line_endings_is_still_untouched(self):
        with open("assets/effects/spark.json", encoding="utf-8") as fh:
            text = fh.read()
        self.write("assets/effects/spark.json", text, newline="\r\n")
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 0, out)

    def test_an_edited_starter_must_be_saved(self):
        edited = dict(SPARK, duration=2)
        self.write("assets/effects/spark.json", json.dumps(edited, indent=1))
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        self.assertIn("effect spark: effect.json", out["missing"])
        self.assertIn("effect spark: README.md", out["missing"])
        self.assertEqual(out["kit_starters"], 4)

    def test_an_edited_packed_texture_or_part_or_mesh_must_be_saved(self):
        self.write("assets/textures/t.json", TEX_DEPS.replace("__DEPS__/textures/", "elsewhere/"))
        self.write("assets/effects/parts/p.json", json.dumps(dict(PART, version=4)))
        self.write("assets/effects/meshes/ring.json", '{"shape": "ring", "segments": 64}')
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        for want in ("texture t: spec.json", "part p: part.json", "mesh ring: spec.json"):
            self.assertIn(want, out["missing"])

    def test_a_new_effect_is_always_required(self):
        self.write("assets/effects/mine.json", json.dumps(SPARK))  # (a starter's bytes under a new name: a new piece)
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        self.assertIn("effect mine: effect.json", out["missing"])
        self.assertNotIn("effect spark: effect.json", out["missing"])

    def test_a_project_piece_named_like_a_starter_is_the_projects(self):
        self.write("assets/effects/spark.json", json.dumps({"version": 3, "duration": 5, "layers": []}))
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        self.assertIn("effect spark: effect.json", out["missing"])

    def test_a_starter_saved_here_is_checked_like_any_other(self):
        code, _ = self.run_cmd(vault.cmd_save)
        self.assertEqual(code, 0)
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["kit_starters"], 0)  # (saved: no longer left to the kit)
        self.write("assets/effects/spark.json", json.dumps(dict(SPARK, duration=3), indent=1))
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        self.assertIn("effect spark: effect.json", out["stale"])

    def test_no_record_or_a_broken_one_exempts_nothing(self):
        for bad in (os.path.join(self.tmp, "nowhere.json"), self.record):
            if bad == self.record:
                self.write(self.record, "{ not json")
            vault.RECORD = bad
            code, out = self.run_cmd(vault.cmd_check)
            self.assertEqual(code, 1)
            self.assertIn("effect spark: effect.json", out["missing"])

    def test_bending_the_projects_starter_copy_recognises_nothing(self):
        # (an agent copies its own new piece into kit/starter/: the kit's record does not know that text)
        mine = {"version": 3, "duration": 9, "layers": []}
        self.write("assets/effects/mine.json", json.dumps(mine))
        self.write(os.path.join(self.kit, "vfx", "mine.json"), json.dumps(mine))
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 1)
        self.assertIn("effect mine: effect.json", out["missing"])

    def test_the_record_keeps_every_text_a_starter_shipped_with(self):
        # (a project from an older release keeps its untouched copy: after the kit's starter changes, both count)
        old = json.dumps(SPARK, indent=1)
        self.write(os.path.join(self.kit, "vfx", "spark.json"), json.dumps(dict(SPARK, duration=4), indent=1))
        starters.write(os.path.join(self.tmp, "kit"), self.record)
        with open(self.record, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["pieces"]["effect/spark"]), 2)
        self.write("assets/effects/spark.json", old)
        code, out = self.run_cmd(vault.cmd_check)
        self.assertEqual(code, 0, out)


class TheKitsOwnStarters(unittest.TestCase):
    """the REAL kit/starter seeded the way `kit init` seeds it (kit/cmd/setup.luau: the starter effects, meshes and
    textures as they are; kit/lib/library.luau unpackVfx/installVfx: each example's packed parts and textures, a
    texture spec's `__DEPS__/textures/` pointed into assets/textures/_library/, only what the project lacks), checked
    against the kit's REAL record (kit/vfx/starters.json): a starter the record lacks fails here"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.getcwd()
        os.chdir(self.tmp)
        starter = os.path.normpath(os.path.join(HERE, "..", "..", "starter"))
        vfx = os.path.join(starter, "vfx")
        for name in os.listdir(vfx):
            if name == "_deps":
                continue
            src = os.path.join(vfx, name)
            dst = os.path.join("assets", "effects", name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
        shutil.copytree(os.path.join(starter, "textures"), os.path.join("assets", "textures"))
        deps = os.path.join(vfx, "_deps")
        for ex in sorted(os.listdir(deps)) if os.path.isdir(deps) else []:
            for sub, home in (("parts", os.path.join("assets", "effects", "parts")),
                              ("textures", os.path.join("assets", "textures")),
                              ("seq", os.path.join("assets", "effects", "seq"))):
                d = os.path.join(deps, ex, sub)
                for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                    to = os.path.join(home, "_library", f) if (sub == "textures" and f.endswith(".png")) else os.path.join(home, f)
                    if os.path.isfile(to):
                        continue
                    os.makedirs(os.path.dirname(to), exist_ok=True)
                    with open(os.path.join(d, f), "rb") as fh:
                        body = fh.read()
                    if f.endswith(".json"):
                        body = body.replace(b"__DEPS__/textures/", b"assets/textures/_library/")
                    with open(to, "wb") as fh:
                        fh.write(body)

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = vault.cmd_check(argparse.Namespace(effects="assets/effects", textures="assets/textures",
                                                      build="build", out="library/vfx"))
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_a_new_project_passes_with_every_seeded_piece_left_to_the_kit(self):
        items, meta = vault.plan(argparse.Namespace(effects="assets/effects", textures="assets/textures",
                                                    build="build", out="library/vfx"))
        pieces = sum(len(meta[k]) for k in ("effects", "parts", "textures", "meshes"))
        self.assertGreater(len(meta["effects"]), 0)  # (kit/starter/vfx ships starter effects)
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertEqual(out["kit_starters"], pieces)

    def test_editing_a_real_starter_makes_it_the_projects(self):
        name = sorted(f for f in os.listdir(os.path.join("assets", "effects"))
                      if f.endswith(".json") and not f.startswith("_"))[0]
        path = os.path.join("assets", "effects", name)
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        d["duration"] = (d.get("duration") or 1) + 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn(f"effect {name[:-5]}: effect.json", out["missing"])


if __name__ == "__main__":
    unittest.main()
