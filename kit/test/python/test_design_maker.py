"""kit design maker (kit/tools/design.py): a maker's design language is a checked doc - two makers that differ on
2+ of primary shape / edge rule / materials / motif are both READY, a third that copies one of them is refused as
too close; the template starts with every section; a build that declares a.maker() records the language in its
facts. The owner, 2026-10-25: originality + a creative director in the pipeline."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "tools"))
import cad_check  # noqa: E402
import design  # noqa: E402

BRIGHTWIND = """# Brightwind — design language

## Identity
A coastal clockmaker family that builds duelling pistols as music boxes for the harbour nobility.

## Shape family
- primary: round
- secondary: blade

## Motif
- a whiplash curve running from the grip to the muzzle

## Edges
- rule: round
- radius_mm: 1.5

## Materials
- brass — polished
- lacquer — deep green

## Detail
- share: 30

## Bans
- no skulls
- no glowing lines
- no tactical rails
"""
IRONHALL = """# Ironhall — design language

## Identity
A mountain forge guild that makes blunt, heavy guns for wardens of the high passes.

## Shape family
- primary: square
- secondary: tube

## Motif
- stepped buttress ribs like a fortress wall

## Edges
- rule: chamfer
- radius_mm: 3

## Materials
- blackened iron — hammered
- oak — oiled

## Detail
- share: 20

## Bans
- no gold
- no curves longer than a hand
- no gems
"""


def run(*args):
    r = subprocess.run([sys.executable, os.path.join(REPO, "kit", "tools", "design.py"), *args], capture_output=True,
                       text=True)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


class Maker(unittest.TestCase):
    def test_two_distinct_makers_are_ready_and_a_copy_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Brightwind.md"), "w", encoding="utf-8").write(BRIGHTWIND)
            open(os.path.join(tmp, "Ironhall.md"), "w", encoding="utf-8").write(IRONHALL)
            for name in ("Brightwind", "Ironhall"):
                code, out = run("maker", name, "--dir", tmp)
                self.assertEqual((code, out["maker"]), (0, "ready"), out)
            copy = BRIGHTWIND.replace("# Brightwind", "# Copycat").replace("brass — polished", "brass — brushed")
            open(os.path.join(tmp, "Copycat.md"), "w", encoding="utf-8").write(copy)
            code, out = run("maker", "Copycat", "--dir", tmp)
            self.assertEqual(code, 1)
            self.assertTrue(any("too close to Brightwind" in p for p in out["problems"]), out)

    def test_parse_and_differences(self):
        with tempfile.TemporaryDirectory() as tmp:
            pa, pb = os.path.join(tmp, "Brightwind.md"), os.path.join(tmp, "Ironhall.md")
            open(pa, "w", encoding="utf-8").write(BRIGHTWIND)
            open(pb, "w", encoding="utf-8").write(IRONHALL)
            a, b = design.parse_maker(pa), design.parse_maker(pb)
            self.assertEqual((a["primary"], a["edge_rule"], a["radius_mm"], a["detail_share"]), ("round", "round", 1.5, 30.0))
            self.assertEqual(sorted(design.differences(a, b)), ["edge rule", "materials", "motif", "primary shape"])

    def test_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run("maker", "Newco", "--new", "--dir", tmp)
            text = open(os.path.join(tmp, "Newco.md"), encoding="utf-8").read()
            self.assertEqual(code, 0)
            for s in design.MAKER_SECTIONS:
                self.assertIn(f"## {s}", text)
            code, out = run("maker", "Newco", "--dir", tmp)
            self.assertEqual((code, out["maker"]), (1, "draft"))

    @unittest.skipUnless(cad_check.blender() and os.path.isfile(cad_check.blender()), "Blender not found")
    def test_a_build_records_its_maker(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Brightwind.md"), "w", encoding="utf-8").write(BRIGHTWIND)
            manifest = os.path.join(REPO, "build", "models", "_selftest_maker.manifest.json")
            if os.path.isfile(manifest):
                os.remove(manifest)
            r = subprocess.run([cad_check.blender(), "-b", "--factory-startup", "-P",
                                os.path.join(REPO, "kit", "selftest", "blender", "build_maker.py"), "--", "--no-preview"],
                               cwd=REPO, capture_output=True, text=True, timeout=900,
                               env=dict(os.environ, KIT_MAKER_DIR=tmp))
            self.assertTrue(os.path.isfile(manifest), (r.stderr or r.stdout)[-600:])
            facts = json.load(open(manifest, encoding="utf-8"))["facts"]
            self.assertEqual(facts["maker"]["name"], "Brightwind")
            self.assertEqual(facts["maker"]["edge_rule"], "round")


if __name__ == "__main__":
    unittest.main()
