"""THE PASSES KEPT (rbx.Asset._raw_open / _bake_pass, 2026-11-12): a build that changes only a material's wear
numbers reads its last bake's Cycles passes off the kept file - and its maps are, byte for byte, the maps a fresh
bake of the same numbers gives. Fixture: kit/selftest/blender/build_relayer.py, built in a folder of its own."""

import glob
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
BUILD = os.path.join("build", "_test_relayer")
SCRIPT = os.path.join(REPO, "kit", "selftest", "blender", "build_relayer.py")


def build(*args, env=None):
    """-> (the build's report, {map name: its bytes})"""
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=BUILD, **(env or {}))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", SCRIPT, "--", "--no-preview", *args], cwd=REPO,
                       capture_output=True, text=True, timeout=900, env=e, encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    maps = {}
    for p in sorted(glob.glob(os.path.join(REPO, BUILD, "models", "textures", "_selftest_relayer_*.png"))):
        with open(p, "rb") as fh:
            maps[os.path.basename(p)] = fh.read()
    return json.loads(line), maps


def cycles(report):
    return sorted(k for k in report["timing"] if k in ("bake:emit", "bake:normal", "bake:ao"))


def apart(a, b):
    """the share of texels where two maps (PNG bytes) differ at all -> float (1.0: not the same size)"""
    import io

    import numpy as np
    from PIL import Image

    if a == b:
        return 0.0
    x, y = (np.asarray(Image.open(io.BytesIO(d)).convert("RGBA")).astype(int) for d in (a, b))
    return 1.0 if x.shape != y.shape else float((np.abs(x - y).max(axis=-1) > 0).mean())


# two FRESH bakes are not always the same to the bit: Cycles' normal pass can differ by a level on a few texels of
# a million (measured by the review), and the wear reads the normal map. A kept pass is the first bake's - so "the
# same maps" is held to that room: under 5 texels in 10,000. A wrong layer or a stale number moves whole percents.
SAME = 0.0005


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class PassesKept(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first, cls.first_maps = build("--rebake")                       # baked fresh: its passes are kept
        cls.more, cls.more_maps = build("--more-dirt")                      # only the wear numbers changed
        cls.again, cls.again_maps = build("--more-dirt")                    # the same again: the bake cache
        cls.fresh, cls.fresh_maps = build("--more-dirt", "--rebake")        # the same numbers, baked fresh
        cls.shape, _m = build("--more-dirt", "--bigger-cap")                # another shape
        cls.nodust, _m = build("--no-dust", "--rebake")                     # no dust layer: no "up" pass
        cls.dust, cls.dust_maps = build()                                   # dust for the first time
        cls.dust_fresh, cls.dust_fresh_maps = build("--rebake")
        cls.off, cls.off_maps = build("--more-dirt", env={"KIT_RELAYER": "0"})
        cls.light, cls.light_maps = build("--life=light", "--rebake")       # the cap's wear from a life word
        cls.heavy, cls.heavy_maps = build("--life=heavy")                   # another word: another wear=
        cls.heavy_fresh, cls.heavy_fresh_maps = build("--life=heavy", "--rebake")
        cls.new, _m = build("--life=new", "--rebake")                       # no wear at all on the cap
        cls.used, cls.used_maps = build("--life=used")
        cls.used_fresh, cls.used_fresh_maps = build("--life=used", "--rebake")
        cls.bare, _m = build("--no-mottle", "--life=new", "--rebake")       # nothing on the piece is mottled
        cls.worn, cls.worn_maps = build("--life=used")                      # ... and now both materials are

    def test_a_fresh_bake_keeps_nothing_from_before(self):
        self.assertNotIn("passes kept", self.first["summary"])
        self.assertEqual(cycles(self.first), ["bake:ao", "bake:emit", "bake:normal"])

    def test_only_the_wear_numbers_changed_no_unwrap_no_cycles(self):
        self.assertIn("passes kept: main", self.more["summary"])
        kept = self.more["facts"]["passes_kept"]["main"]
        self.assertGreaterEqual(kept["kept"], 5)
        self.assertEqual(kept["baked"], 0)
        self.assertEqual(cycles(self.more), [])                             # not one Cycles pass
        self.assertLess(self.more["timing"]["unwrap"], 0.5)                 # the kept UVs, no unwrap
        self.assertEqual(self.more["bakes"].get("relayered"), 1)

    def test_its_maps_are_a_fresh_bakes_maps(self):
        self.assertEqual(sorted(self.more_maps), sorted(self.fresh_maps))
        for name, data in self.fresh_maps.items():
            self.assertLess(apart(self.more_maps[name], data), SAME, name)

    def test_the_wear_did_change(self):
        c = "_selftest_relayer_color.png"
        self.assertGreater(apart(self.first_maps[c], self.more_maps[c]), 0.2)       # more chips, grime, dust
        n = "_selftest_relayer_normal.png"
        self.assertEqual(self.first_maps[n], self.more_maps[n])                     # the SAME pass: to the byte

    def test_a_plain_cache_hit_reads_no_passes_and_does_not_say_it_did(self):
        self.assertEqual(self.again["bakes"]["reused"], 1)
        self.assertNotIn("passes kept", self.again["summary"])
        self.assertEqual(self.again_maps, self.more_maps)

    def test_another_shape_bakes_everything(self):
        self.assertNotIn("passes kept", self.shape["summary"])
        self.assertEqual(cycles(self.shape), ["bake:ao", "bake:emit", "bake:normal"])

    def test_a_layer_turned_on_bakes_only_the_pass_it_lacks(self):
        self.assertNotIn("passes kept", self.nodust["summary"])
        kept = self.dust["facts"]["passes_kept"]["main"]
        self.assertGreaterEqual(kept["kept"], 3)                            # colour, normal, occlusion at least
        self.assertGreaterEqual(kept["baked"], 1)                           # the pass that carries "up"
        self.assertNotIn("bake:normal", self.dust["timing"])
        self.assertNotIn("bake:ao", self.dust["timing"])
        for name, data in self.dust_fresh_maps.items():
            self.assertLess(apart(self.dust_maps[name], data), SAME, name)

    def test_switched_off_it_bakes_everything_to_the_same_maps(self):
        self.assertNotIn("passes kept", self.off["summary"])
        self.assertEqual(cycles(self.off), ["bake:ao", "bake:emit", "bake:normal"])
        for name, data in self.fresh_maps.items():
            self.assertLess(apart(self.off_maps[name], data), SAME, name)

    def test_a_changed_life_word_keeps_the_passes(self):
        # life= sets wear= (the mottle): it was a ramp in the material's nodes and baked everything again
        kept = self.heavy["facts"]["passes_kept"]["main"]
        self.assertEqual(kept["baked"], 0)
        self.assertEqual(cycles(self.heavy), [])
        for name, data in self.heavy_fresh_maps.items():
            self.assertLess(apart(self.heavy_maps[name], data), SAME, name)
        for ch in ("color", "rough"):   # light -> heavy: the cap's mottle is deeper and rougher (only its life changed)
            name = f"_selftest_relayer_{ch}.png"
            self.assertGreater(apart(self.heavy_maps[name], self.light_maps[name]), 0.02, name)

    def test_from_new_to_used_bakes_no_normal_no_occlusion(self):
        # (a "new" cap asks for no smudge layer: "used" adds one pass of masks - the rest is kept)
        self.assertNotIn("bake:normal", self.used["timing"])
        self.assertNotIn("bake:ao", self.used["timing"])
        self.assertGreaterEqual(self.used["facts"]["passes_kept"]["main"]["kept"], 4)
        for name, data in self.used_fresh_maps.items():
            self.assertLess(apart(self.used_maps[name], data), SAME, name)

    def test_the_first_mottle_on_a_piece_bakes_its_noise_and_keeps_the_rest(self):
        self.assertNotIn("passes kept", self.bare["summary"])
        kept = self.worn["facts"]["passes_kept"]["main"]
        self.assertGreaterEqual(kept["kept"], 4)                            # colour, under, normal, occlusion
        self.assertGreaterEqual(kept["baked"], 1)                           # the pass that carries the noise
        self.assertNotIn("bake:normal", self.worn["timing"])
        self.assertNotIn("bake:ao", self.worn["timing"])
        for name, data in self.used_fresh_maps.items():                     # (the same numbers, baked fresh)
            self.assertLess(apart(self.worn_maps[name], data), SAME, name)

    def test_a_record_cut_short_is_a_miss_never_a_lost_build(self):
        path = os.path.join(REPO, BUILD, "models", "bakecache", "_selftest_relayer.passes.npz")
        build("--rebake")
        with open(path, "rb") as fh:
            head = fh.read()[:2000]
        with open(path, "wb") as fh:
            fh.write(head)                                                  # a file cut short (a killed build)
        report, _maps = build("--more-dirt")
        self.assertNotIn("passes kept", report["summary"])
        self.assertIn("could not be read", report["bakes"]["why"]["main"])
        self.assertEqual(cycles(report), ["bake:ao", "bake:emit", "bake:normal"])
        again, _maps = build("--rebake")                                    # ... and the next bake writes it whole
        kept, _maps = build("--more-dirt")
        self.assertIn("passes kept: main", kept["summary"])


if __name__ == "__main__":
    unittest.main()
