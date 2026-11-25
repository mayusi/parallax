"""A MATERIAL'S OWN LAYERS in the builder (a.material(layers=), rbx_layers; 2026-11-13): a layer changed, added or
taken out reads the last bake's passes; its maps are a fresh bake's; a layer taken out changes only the texels it
lay on; a build with no layers says none; what each layer covered is in the report and survives a cache hit.
Fixture: kit/selftest/blender/build_layers.py, built in a folder of its own (real Blender builds)."""

import glob
import io
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
BUILD = os.path.join("build", "_test_layers")
SCRIPT = os.path.join(REPO, "kit", "selftest", "blender", "build_layers.py")
SAME = 0.0005     # (test_relayer.py: the room two bakes of the same thing have - a kept pass is the first bake's)


def build(*args, env=None):
    """-> (the build's report, {map name: its bytes})"""
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=BUILD, **(env or {}))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", SCRIPT, "--", "--no-preview", *args], cwd=REPO,
                       capture_output=True, text=True, timeout=900, env=e, encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    maps = {}
    for p in sorted(glob.glob(os.path.join(REPO, BUILD, "models", "textures", "_selftest_layers_*.png"))):
        with open(p, "rb") as fh:
            maps[os.path.basename(p)[len("_selftest_layers_"):-4]] = fh.read()
    return json.loads(line), maps


def cycles(report):
    return sorted(k for k in report["timing"] if k in ("bake:emit", "bake:normal", "bake:ao"))


def pixels(png):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA")).astype(int)


def changed(a, b):
    """the texels where two maps (PNG bytes) differ at all -> bool (H, W)"""
    return (abs(pixels(a) - pixels(b)).max(axis=-1) > 0)


def apart(a, b):
    return 0.0 if a == b else float(changed(a, b).mean())


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class LayerStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first, cls.first_maps = build("--rebake")                        # baked fresh: its passes are kept
        cls.more, cls.more_maps = build("--more-dirt")                       # only the layers' amounts changed
        cls.again, cls.again_maps = build("--more-dirt")                     # the same again: the bake cache
        cls.fresh, cls.fresh_maps = build("--more-dirt", "--rebake")         # the same layers, baked fresh
        cls.back, cls.back_maps = build()                                    # the first numbers again, from passes
        cls.nosoot, cls.nosoot_maps = build("--no-soot")                     # one layer taken out
        cls.none, cls.none_maps = build("--no-layers")                       # none at all
        cls.snow, cls.snow_maps = build("--snow")                            # a layer on the up faces
        cls.nowhere, cls.nowhere_maps = build("--nowhere")                   # a layer with nowhere to lie
        cls.back2, cls.back2_maps = build()                                  # the first numbers once more
        cls.nofirst, cls.nofirst_maps = build("--no-first")                  # the FIRST layer taken out
        # no material with a wear number (no chips, no grime): the group's passes hold no material coverage
        cls.plain0, _m = build("--plain", "--no-layers", "--rebake")
        cls.plain1, cls.plain1_maps = build("--plain")                       # its first layers
        cls.plain2, _m = build("--plain", "--no-layers")                     # ... taken out
        cls.plain3, cls.plain3_maps = build("--plain")                       # ... and put back
        # RELIEF: every layer a stain (thick_mm=0), the layers as they are (rust 0.4 mm), and a thick one (mud)
        cls.nol, cls.nol_maps = build("--no-layers")
        cls.flat, cls.flat_maps = build("--flat")
        cls.thick, cls.thick_maps = build()
        cls.mud, cls.mud_maps = build("--mud")
        cls.big, cls.big_maps = build("--big", "--rebake")                   # the same piece on a 2048 map

    def test_a_first_build_lays_them_and_says_what_each_covered(self):
        self.assertEqual(self.first["facts"].get("passes_kept"), None)
        paint = self.first["facts"]["layers"]["main"]["paint"]
        self.assertEqual([(r["layer"], r["where"]) for r in paint],
                         [("rust", "chipped"), ("rust", "cavities"), ("soot", "low")])
        for r in paint:                                    # the share asked OF the room its place gives
            self.assertAlmostEqual(r["covered"], r["asked"] * r["eligible"], delta=0.012)
            self.assertGreater(r["covered"], 0.01)
        self.assertEqual([r["layer"] for r in self.first["facts"]["layers"]["main"]["steel"]], ["blueing"])
        self.assertIn("layers: main paint rust where chipped 80% -> ", self.first["summary"])
        self.assertIn(" + rust in cavities 15% -> ", self.first["summary"])      # (two of a kind: told apart)
        self.assertIn("steel blueing on flats 25% -> ", self.first["summary"])

    def test_a_layer_changed_reads_the_passes_no_unwrap_no_cycles(self):
        self.assertEqual(cycles(self.more), [])
        self.assertEqual(self.more["facts"]["passes_kept"]["main"]["baked"], 0)
        self.assertGreater(self.more["facts"]["passes_kept"]["main"]["kept"], 3)
        self.assertIn("passes kept: main", self.more["summary"])
        self.assertLess(self.more["timing"]["unwrap"], 0.5)

    def test_more_was_asked_more_is_laid(self):
        a, b = self.first["facts"]["layers"]["main"], self.more["facts"]["layers"]["main"]
        for mat in ("paint", "steel"):
            for ra, rb in zip(a[mat], b[mat]):
                self.assertGreater(rb["covered"], ra["covered"], (mat, ra["layer"], ra["where"]))
                self.assertEqual(rb["eligible"], ra["eligible"])           # where it MAY lie did not move
        self.assertGreater(apart(self.first_maps["color"], self.more_maps["color"]), 0.02)

    def test_its_maps_are_a_fresh_bakes_maps(self):
        for name, fresh in self.fresh_maps.items():
            self.assertLessEqual(apart(self.more_maps[name], fresh), SAME, name)
        for name, first in self.first_maps.items():        # ... and back again: the first build's own maps
            self.assertLessEqual(apart(self.back_maps[name], first), SAME, name)

    def test_a_cache_hit_still_says_what_the_layers_covered(self):
        self.assertEqual(self.again["bakes"]["reused"], 1)
        self.assertEqual(self.again["facts"]["layers"], self.more["facts"]["layers"])
        self.assertIn("layers: main paint rust ", self.again["summary"])
        self.assertEqual(self.again_maps, self.more_maps)

    def test_a_layer_taken_out_changes_only_the_texels_it_lay_on(self):
        self.assertEqual(cycles(self.nosoot), [])
        self.assertEqual([r["layer"] for r in self.nosoot["facts"]["layers"]["main"]["paint"]], ["rust", "rust"])
        soot = next(r for r in self.back["facts"]["layers"]["main"]["paint"] if r["layer"] == "soot")
        moved = changed(self.back_maps["color"], self.nosoot_maps["color"])
        # (the soot lay on `covered` of the paint; the paint is most of the map: the texels that moved are of that
        # order - never the whole map, never nothing)
        self.assertGreater(float(moved.mean()), 0.3 * soot["covered"])
        self.assertLess(float(moved.mean()), 1.6 * soot["covered"])
        # the other layers' rows did not move: each has its own noise
        for ra, rb in zip(self.back["facts"]["layers"]["main"]["paint"], self.nosoot["facts"]["layers"]["main"]["paint"]):
            self.assertEqual(ra, rb)
        self.assertEqual(self.back["facts"]["layers"]["main"]["steel"], self.nosoot["facts"]["layers"]["main"]["steel"])
        # ... and the texels that moved are the ones the soot darkened: low on the object, nowhere on the cap's blue
        a, b = pixels(self.back_maps["color"]), pixels(self.nosoot_maps["color"])
        self.assertGreater(float(b[moved][:, :3].mean()), float(a[moved][:, :3].mean()))   # without soot: lighter

    def test_the_first_layer_taken_out_moves_no_other_layers_patches(self):
        self.assertEqual(cycles(self.nofirst), [])
        a, b = self.back2["facts"]["layers"]["main"], self.nofirst["facts"]["layers"]["main"]
        self.assertEqual([(r["layer"], r["where"]) for r in b["paint"]], [("rust", "cavities"), ("soot", "low")])
        self.assertEqual(b["paint"], a["paint"][1:])                         # to the last digit: the same masks
        self.assertEqual(b["steel"], a["steel"])
        gone = a["paint"][0]["covered"]                                      # what the rust in the chips covered
        moved = changed(self.back2_maps["color"], self.nofirst_maps["color"])
        self.assertGreater(float(moved.mean()), 0.2 * gone)
        self.assertLess(float(moved.mean()), 2.0 * gone)                     # ... and nothing else moved

    def test_where_no_material_has_a_wear_number_the_first_layers_bake_one_helper_pass(self):
        self.assertNotIn("layers", self.plain0["facts"])
        self.assertEqual(cycles(self.plain1), ["bake:emit"])                 # the materials' coverage + "low"
        self.assertEqual(self.plain1["facts"]["passes_kept"]["main"]["baked"], 1)
        self.assertGreater(self.plain1["facts"]["passes_kept"]["main"]["kept"], 2)   # ... and nothing else
        rows_ = self.plain1["facts"]["layers"]["main"]["paint"]
        self.assertEqual((rows_[0]["where"], rows_[0]["eligible"], rows_[0]["covered"]), ("chipped", 0.0, 0.0))
        self.assertIn("rust where chipped 80% -> 0% (nowhere)", self.plain1["summary"])
        self.assertGreater(rows_[1]["covered"], 0.01)

    def test_layers_taken_out_and_put_back_bake_nothing(self):
        self.assertEqual(cycles(self.plain2), [])
        self.assertNotIn("layers", self.plain2["facts"])
        self.assertEqual(cycles(self.plain3), [])                            # the helper pass was kept for it
        self.assertEqual(self.plain3["facts"]["passes_kept"]["main"]["baked"], 0)
        self.assertEqual(self.plain3["facts"]["layers"], self.plain1["facts"]["layers"])
        self.assertEqual(self.plain3_maps, self.plain1_maps)

    def test_a_layer_in_a_cavity_is_as_dark_as_the_cavity(self):
        # rust laid where the plain paint is in the occlusion's shade (round the cap's foot, in the seams) is
        # darker than the same rust in the open - not a flat patch brighter than the paint round it
        import numpy as np

        a = pixels(self.none_maps["color"])[..., :3].astype(float)           # the surface with no layers
        b = pixels(self.first_maps["color"])[..., :3].astype(float)
        paint = (a[..., 1] > a[..., 0] + 15) & (a[..., 1] > a[..., 2])       # plain green paint (no chip there)
        light = a.sum(-1)
        med = float(np.median(light[paint]))
        rusty = paint & (b[..., 0] > 1.5 * b[..., 2]) & (b[..., 0] > b[..., 1] + 20)   # ... now red-brown
        shaded, lit = rusty & (light < 0.7 * med), rusty & (light > 0.8 * med)
        self.assertGreater(int(shaded.sum()), 100)
        self.assertGreater(int(lit.sum()), 100)
        self.assertLess(float(b[shaded].sum(-1).mean()), 0.85 * float(b[lit].sum(-1).mean()))

    def test_a_stain_leaves_the_normal_map_alone(self):
        self.assertEqual(cycles(self.flat), [])
        self.assertEqual(self.flat_maps["normal"], self.nol_maps["normal"])  # to the byte: a build without layers'
        for r in self.flat["facts"]["layers"]["main"]["paint"]:
            self.assertNotIn("thick_mm", r)
            self.assertNotIn("tilt_deg", r)
        self.assertNotIn("mm thick", self.flat["summary"])

    def test_a_thickness_is_relief_in_the_normal_map_and_nothing_else(self):
        self.assertEqual(cycles(self.thick), [])                             # (a thickness changed: no render pass)
        for name in ("color", "rough", "metal"):
            self.assertEqual(self.thick_maps[name], self.flat_maps[name], name)
        moved = changed(self.thick_maps["normal"], self.flat_maps["normal"])
        rust = sum(r["covered"] for r in self.thick["facts"]["layers"]["main"]["paint"] if r["layer"] == "rust")
        # the relief is where the rust lies (its edges and its uneven top), nowhere else
        self.assertGreater(float(moved.mean()), 0.2 * rust)
        self.assertLess(float(moved.mean()), 3.0 * rust)
        import numpy as np

        col = changed(self.thick_maps["color"], self.nol_maps["color"])      # where ANY layer changed the colour
        # ... or one texel beside it: the foot of a sharp bank (a slope is between two texels) - measured
        # 2026-11-13: every normal texel moved off a layer was that one, and none further away
        p = np.pad(col, 1)
        near = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] |             p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:]
        self.assertEqual(int((moved & ~near).sum()), 0)
        self.assertGreater(float((moved & col).sum()) / float(moved.sum()), 0.8)
        rows = self.thick["facts"]["layers"]["main"]["paint"]
        self.assertEqual([r.get("thick_mm") for r in rows], [0.4, 0.4, None])
        self.assertTrue(all(r["tilt_deg"] >= 2.0 for r in rows[:2]))
        self.assertTrue(all(r["tilt_deg"] == max(r["bank_deg"], r["top_deg"]) for r in rows[:2]))

    def test_the_relief_is_raised_not_sunk(self):
        # where the mud's colour mask RISES along the map's x, the normal must lean to -x (and so along y): the
        # builder's own wiring of the sign, on the built maps
        import numpy as np

        on = changed(self.mud_maps["color"], self.thick_maps["color"]).astype(float)   # where the mud lies
        k = np.ones(9) / 9.0
        soft = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, on)
        soft = np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, soft)
        # (a PNG's rows run top-down, the map's bottom-up: the normal's green points up the picture)
        rise_y, rise_x = np.gradient(soft)
        a = pixels(self.mud_maps["normal"])[..., :2].astype(float)
        b = pixels(self.thick_maps["normal"])[..., :2].astype(float)
        dx, dy = a[..., 0] - b[..., 0], a[..., 1] - b[..., 1]
        bank = (np.hypot(rise_x, rise_y) > 0.02) & (np.hypot(dx, dy) > 2)
        self.assertGreater(int(bank.sum()), 500)
        self.assertLess(float(np.corrcoef(dx[bank], rise_x[bank])[0, 1]), -0.5)        # leans away from the rise
        self.assertGreater(float(np.corrcoef(dy[bank], rise_y[bank])[0, 1]), 0.5)      # (rows flipped: the same)

    def test_more_texels_a_millimetre_draw_a_steeper_bank(self):
        small = self.thick["facts"]["layers"]["main"]["paint"][0]            # rust in the chips, 1024
        large = self.big["facts"]["layers"]["main"]["paint"][0]              # ... the same on 2048
        self.assertEqual((small["layer"], small["where"]), (large["layer"], large["where"]))
        self.assertGreater(large["bank_deg"], 1.3 * small["bank_deg"])       # twice the texels a millimetre
        self.assertIn("rust where chipped 80% -> 5%, 0.4 mm thick + ", self.thick["summary"])

    def test_a_thicker_layer_tilts_the_surface_more(self):
        rows = self.mud["facts"]["layers"]["main"]["paint"]
        mud = next(r for r in rows if r["layer"] == "mud")
        self.assertEqual((mud["layer"], mud["where"], mud["thick_mm"]), ("mud", "low", 3.0))
        self.assertGreater(mud["top_deg"], 5.0)                              # its lumpy top
        self.assertGreater(mud["bank_deg"], 3.0 * rows[0]["bank_deg"])       # 3 mm banks against the rust's 0.4
        self.assertLess(mud["bank_deg"], 63.5)
        # 3 mm of mud over half the paint: its uneven top tilts far more of the normal map than the rust's thin
        # lines did (the same build without the mud: cls.thick)
        moved = changed(self.mud_maps["normal"], self.thick_maps["normal"])
        self.assertGreater(float(moved.mean()), 0.5 * mud["covered"] * 0.6)   # (the paint is some 60% of the map)
        rust_moved = changed(self.thick_maps["normal"], self.flat_maps["normal"])
        self.assertGreater(float(moved.mean()), 3.0 * float(rust_moved.mean()))
        self.assertIn("mud low down 50% -> ", self.mud["summary"])
        self.assertIn(", 3 mm thick", self.mud["summary"])
        # the normal map stays a unit normal map: no texel flattened to grey, none past the slope's hold
        n = pixels(self.mud_maps["normal"])[..., :3] / 255.0 * 2 - 1
        length = (n ** 2).sum(-1) ** 0.5
        self.assertGreater(float(length.min()), 0.9)
        self.assertGreater(float(n[..., 2].min()), 0.3)                      # (63 degrees at the most, and the bevels)

    def test_no_layers_none_are_named_and_the_surface_is_the_plain_one(self):
        self.assertNotIn("layers", self.none["facts"])
        self.assertNotIn("layers:", self.none["summary"])
        self.assertEqual(cycles(self.none), [])                              # (taking them all out bakes nothing)
        self.assertGreater(apart(self.none_maps["color"], self.first_maps["color"]), 0.05)

    def test_a_layer_on_the_up_faces_bakes_only_the_pass_it_reads(self):
        self.assertEqual(cycles(self.snow), ["bake:emit"])
        self.assertEqual(self.snow["facts"]["passes_kept"]["main"]["baked"], 1)
        snow = self.snow["facts"]["layers"]["main"]["steel"][-1]
        self.assertEqual((snow["layer"], snow["where"]), ("snow", "up"))
        self.assertGreater(snow["eligible"], 0.2)                            # the cap's top looks up
        self.assertLess(snow["eligible"], 0.8)                               # its side and underside do not
        self.assertGreater(snow["covered"], 0.1)

    def test_a_layer_with_nowhere_to_lie_says_so(self):
        last = self.nowhere["facts"]["layers"]["main"]["steel"][-1]
        self.assertEqual((last["layer"], last["where"], last["eligible"], last["covered"]),
                         ("rust", "chipped", 0.0, 0.0))
        self.assertIn("rust where chipped 50% -> 0% (nowhere)", self.nowhere["summary"])

    def test_the_roughness_and_the_metalness_follow(self):
        # rust on chipped paint: where the chips showed bare metal (metalness 1), rust is no metal
        self.assertGreater(apart(self.none_maps["metal"], self.first_maps["metal"]), 0.01)
        a, b = pixels(self.none_maps["metal"]), pixels(self.first_maps["metal"])
        moved = changed(self.none_maps["metal"], self.first_maps["metal"])
        self.assertLess(float(b[moved][:, 0].mean()), float(a[moved][:, 0].mean()))
        self.assertGreater(apart(self.none_maps["rough"], self.first_maps["rough"]), 0.05)


if __name__ == "__main__":
    unittest.main()
