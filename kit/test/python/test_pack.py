"""kit/tools/pack.py (`kit pack <asset>`) + kit/blender/rbx_pack.py (`a.pack()` in a build): the asset's PACK — what it
HAS found by scanning (traces + mm profiles, reference models, generated drafts, colour pictures, fitted proportions),
what was CHOSEN kept (the object and its real length, sizes with their sources, each part's measured colour, stage
times), and a build reading sizes, profiles, colours, slices and drafts from it with every value's source on record.
On a temporary project; colours on a synthetic lighting-free picture with two parts of known colour."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import pack as PK  # noqa: E402
import rbx_pack as RP  # noqa: E402

# a 200 x 100 px picture; the trace frame: x0 20, y1 80, 160 px long, front on the right -> px = 20 + 160 u,
# py = 80 - 160 v. Part "slide" (u 0.1..0.4, v 0.05..0.3) = px 36..84, py 32..72 (red); "frame" (u 0.5..0.9) = px
# 100..164 (blue).
SLIDE = [[0.1, 0.05], [0.4, 0.05], [0.4, 0.3], [0.1, 0.3]]
FRAME = [[0.5, 0.05], [0.9, 0.05], [0.9, 0.3], [0.5, 0.3]]


class Project:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("assets/models", "refs/private/x", "kit/real_specs", "build/vision"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)

    def write(self, rel, obj):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(obj if isinstance(obj, str) else json.dumps(obj))
        return path

    def picture_and_albedo(self, source="refs/x_side.png", front=None):
        self.write("assets/models/x_photo_side.trace.json",
                   {"source": source, "frame": {"x0": 20, "y1": 80, "length_px": 160}, "outline": SLIDE + FRAME,
                    "parts": {"slide": SLIDE, "frame": FRAME}, **({"front": front} if front else {})})
        alb = np.full((100, 200, 3), 0.5, np.float32)
        alb[32:72, 36:84] = (0.8, 0.1, 0.1)
        alb[32:72, 100:164] = (0.1, 0.2, 0.9)
        rough = np.full((100, 200), 0.3, np.float32)
        rough[32:72, 100:164] = 0.7
        metal = np.zeros((100, 200), np.float32)
        metal[32:72, 36:84] = 1.0
        path = os.path.join(self.root, "assets/models/x.albedo.npz")
        np.savez_compressed(path, albedo=alb.astype(np.float16), rough=rough.astype(np.float16),
                            metal=metal.astype(np.float16), meta=json.dumps({"source": source}))
        return path

    def close(self):
        self.tmp.cleanup()


class TestPack(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.write("assets/models/build_x.py", 'a = rbx.Asset("x", quality="hero")\n'
                     'L = rbx_trace.measure("other_pistol")\n')

    def tearDown(self):
        self.p.close()

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = PK.main(["x", *args, "--root", self.p.root])
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_sizes_resolve_from_a_sourced_row_a_unit_or_plain_mm(self):
        self.p.write("kit/real_specs/pistol.json", [
            {"id": "ab12", "object": "pistol", "part": "slide", "dim": "length", "value": 186, "unit": "mm",
             "kind": "manual", "source": "https://example.org/manual", "trust": "high"},
            {"id": "kg01", "object": "pistol", "part": "overall", "dim": "weight", "value": 0.7, "unit": "kg"}])
        s = PK.resolve_size("dims:ab12", self.p.root)
        self.assertEqual((s["mm"], s["source"], s["trust"]), (186.0, "dims:ab12", "high"))
        self.assertEqual(PK.resolve_size("7.32 in", self.p.root)["mm"], 185.928)
        self.assertEqual(PK.resolve_size("186", self.p.root)["trust"], "unsourced")
        with self.assertRaisesRegex(ValueError, "not a length"):
            PK.resolve_size("dims:kg01", self.p.root)
        with self.assertRaisesRegex(ValueError, "no kit/real_specs row"):
            PK.resolve_size("dims:nope", self.p.root)
        with self.assertRaisesRegex(ValueError, "not a size"):
            PK.resolve_size("long", self.p.root)

    def test_part_colours_are_the_median_inside_each_parts_own_mask(self):
        alb = self.p.picture_and_albedo()
        got, note = PK.part_colours(os.path.join(self.p.root, "assets/models/x_photo_side.trace.json"), alb)
        self.assertIsNone(note)
        self.assertEqual(got["slide"]["srgb"], [0.8, 0.1, 0.1])
        self.assertEqual(got["frame"]["srgb"], [0.1, 0.2, 0.9])
        self.assertEqual((got["slide"]["metal"], got["frame"]["rough"]), (1.0, 0.7))

    def test_a_front_left_trace_mirrors_onto_the_picture(self):
        alb = self.p.picture_and_albedo(front="left")  # u = 0 is now the picture's RIGHT end: the parts swap places
        got, _ = PK.part_colours(os.path.join(self.p.root, "assets/models/x_photo_side.trace.json"), alb)
        self.assertNotEqual(got["slide"]["srgb"], [0.8, 0.1, 0.1])

    def test_colours_of_another_picture_are_refused(self):
        alb = self.p.picture_and_albedo()
        self.p.write("assets/models/x_photo_side.trace.json", {"source": "refs/other.png", "frame": {
            "x0": 20, "y1": 80, "length_px": 160}, "parts": {"slide": SLIDE}})
        got, note = PK.part_colours(os.path.join(self.p.root, "assets/models/x_photo_side.trace.json"), alb)
        self.assertEqual(got, {})
        self.assertIn("not of the traced picture", note)

    def test_scan_finds_what_the_asset_has(self):
        self.p.picture_and_albedo()
        self.p.write("assets/models/x_photo_side.profiles.json", {"parts": {"slide": [[0, 0], [186, 0], [186, 30]]},
                                                                  "outline": [], "extents": {}})
        self.p.write("assets/models/x_scan_top.trace.json", {"source": "build/refs/x_scan_top_mask.png", "parts": {}})
        self.p.write("refs/private/x/x_scan.measure.json", {"levels": [{"h": 0.1, "width_mm": 30}]})
        self.p.write("refs/other_pistol.measure.json", {"levels": []})
        self.p.write("refs/private/x_build.inspect.json", {})
        self.p.write("assets/models/x_draft.gen.json", {"engine": "pixal3d", "silhouette_iou": {"side": 0.9}})
        self.p.write("assets/models/x_draft.gen.glb", "glb")
        self.p.write("assets/models/x.params.json", {})
        f = PK.scan("x", self.p.root)
        self.assertEqual(f["traces"]["x_photo_side"]["view"], "side")
        self.assertEqual(f["traces"]["x_photo_side"]["profiles"], "assets/models/x_photo_side.profiles.json")
        self.assertEqual(f["traces"]["x_scan_top"]["source"], "model")
        self.assertEqual(sorted(f["models"]), ["other_pistol", "x_scan"])  # (its own build's inspection is no model)
        self.assertEqual(f["drafts"]["x_draft"]["glb"], "assets/models/x_draft.gen.glb")
        self.assertEqual(f["albedo"], ["assets/models/x.albedo.npz"])
        self.assertEqual(f["params"], "assets/models/x.params.json")

    def test_the_command_keeps_choices_across_refreshes(self):
        self.p.write("kit/real_specs/pistol.json", [{"id": "len1", "object": "pistol", "part": "overall",
                                                     "dim": "length", "value": 202, "unit": "mm", "trust": "high"}])
        self.p.picture_and_albedo()
        code, v = self.run_cli("object", "Example 17", "--length", "dims:len1", "--category", "firearm")
        self.assertEqual(code, 0, v)
        code, v = self.run_cli("size", "slide.length", "186", "--source", "https://example.org/manual")
        self.assertEqual(code, 0, v)
        code, v = self.run_cli("colours", "--trace", "x_photo_side")  # its albedo found by its source picture
        self.assertEqual(code, 0, v)
        self.assertIn("2 part colour(s)", v["summary"])
        code, v = self.run_cli("time", "gather", "1260", "--what", "kit gather")
        code, v = self.run_cli()  # a plain refresh keeps every choice
        d = PK.load("x", self.p.root)
        self.assertEqual(d["object"]["length_mm"], 202.0)
        self.assertEqual(d["sizes"]["slide.length"]["trust"], "medium")  # (a stated source: the giver's word)
        self.assertEqual(d["colours"]["frame"]["srgb"], [0.1, 0.2, 0.9])
        self.assertEqual(d["timings"][0]["stage"], "gather")
        self.assertIn("Example 17, 202 mm", v["summary"])

    def test_the_command_says_what_to_do_when_it_cannot(self):
        code, v = self.run_cli("colours", "--trace", "x_photo_side")
        self.assertEqual(code, 1)
        code, v = self.run_cli("size", "slide.length", "dims:missing")
        self.assertEqual(code, 1)
        self.assertIn("refs dims find", v["summary"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = PK.main(["nothing_here", "--root", self.p.root])
        self.assertEqual(code, 1)
        self.assertIn("kit new asset nothing_here", out.getvalue())


class TestBuildReadsThePack(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.write("assets/models/build_x.py", 'a = rbx.Asset("x")\n')
        self.p.picture_and_albedo()
        self.p.write("assets/models/x_photo_side.profiles.json", {
            "outline": [[0, 0], [190, 0], [190, -120], [0, -120]], "holes": [[[60, -50], [80, -50], [70, -70]]],
            "parts": {"slide": [[0, 0], [186, 0], [186, -30], [0, -30]]}, "extents": {"slide": [0, 186, -30, 0]}})
        self.p.write("refs/private/x/x_scan.measure.json", {"levels": [{"h": 0.1, "width_mm": 30, "squareness": 2.4}]})
        self.p.write("assets/models/x_draft.gen.json", {"engine": "trellis2"})
        self.p.write("assets/models/x_draft.gen.glb", "glb")
        self.p.write("kit/real_specs/pistol.json", [{"id": "len1", "value": 202, "unit": "mm", "trust": "high"}])
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "object", "Example 17", "--length", "dims:len1", "--root", self.p.root])
            PK.main(["x", "size", "slide.length", "186", "--source", "manual p.4", "--root", self.p.root])
            PK.main(["x", "colours", "--trace", "x_photo_side", "--root", self.p.root])
        self.pk = RP.Pack("x", self.p.root)

    def tearDown(self):
        self.p.close()

    def test_a_build_reads_sizes_profiles_colours_slices_and_the_draft(self):
        pk = self.pk
        self.assertEqual(pk.length_mm, 202.0)
        self.assertEqual(pk.size("slide.length"), 186.0)
        self.assertEqual(pk.profile("slide")[1], (186, 0))
        self.assertEqual(pk.extents("slide"), [0.0, 186.0, -30.0, 0.0])
        self.assertEqual(len(pk.outline()), 4)
        self.assertEqual(len(pk.holes()), 1)
        self.assertEqual(pk.colour_srgb("slide"), (0.8, 0.1, 0.1))
        self.assertEqual(pk.colour("slide"), (0.6038, 0.01, 0.01))  # linear: what a.material(color=) takes
        self.assertEqual((pk.rough("frame"), pk.metal("slide")), (0.7, 1.0))
        self.assertEqual(pk.levels("x_scan")[0]["squareness"], 2.4)
        self.assertEqual(pk.draft(), "assets/models/x_draft.gen.glb")
        facts = pk.facts()
        self.assertEqual(facts["read"], 12)
        self.assertEqual(facts["unsourced"], [])
        self.assertIn("colour", facts["kinds"])

    def test_a_missing_value_names_the_command_that_fills_it(self):
        with self.assertRaises(RP.PackMissing) as cm:
            self.pk.size("barrel.length")
        self.assertIn("lune run kit pack x size barrel.length dims:<id>", str(cm.exception))
        with self.assertRaises(RP.PackMissing) as cm:
            self.pk.colour("trigger")
        self.assertIn("kit vision albedo", str(cm.exception))
        with self.assertRaises(RP.PackMissing) as cm:
            self.pk.profile("trigger")
        self.assertIn("kit refs profiles", str(cm.exception))

    def test_a_default_is_used_but_said_unsourced(self):
        self.assertEqual(self.pk.size("barrel.length", default=114), 114.0)
        self.assertEqual(self.pk.facts()["unsourced"], ["barrel.length"])

    def test_profiles_come_from_the_side_view_unless_asked(self):
        self.p.write("assets/models/x_photo_front.trace.json", {"source": "refs/x_front.png", "parts": {"slide": SLIDE}})
        self.p.write("assets/models/x_photo_front.profiles.json", {"outline": [], "parts": {
            "slide": [[0, 0], [30, 0], [30, -30], [0, -30]]}, "extents": {"slide": [0, 30, -30, 0]}})
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "--root", self.p.root])  # (a refresh finds the front trace)
        pk = RP.Pack("x", self.p.root)
        self.assertEqual(pk.extents("slide"), [0.0, 186.0, -30.0, 0.0])  # the side's LENGTH, never the front's width
        self.assertEqual(pk.extents("slide", view="front"), [0.0, 30.0, -30.0, 0.0])

    def test_a_profile_made_after_the_last_pack_run_is_still_read(self):
        self.assertNotIn("x_close_side", PK.load("x", self.p.root)["found"]["traces"])
        self.p.write("assets/models/x_close_side.trace.json", {"source": "refs/x_close.png",
                                                               "parts": {"trigger": SLIDE}})
        self.p.write("assets/models/x_close_side.profiles.json", {"outline": [], "parts": {
            "trigger": [[10, -20], [30, -20], [30, -40]]}, "extents": {}})
        pk = RP.Pack("x", self.p.root)  # (no `kit pack` since: the build's own scan finds the new trace's profile)
        self.assertEqual(pk.profile("trigger")[0], (10, -20))

    def test_a_plain_number_is_said_unsourced(self):
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "size", "barrel.length", "114", "--root", self.p.root])
        pk = RP.Pack("x", self.p.root)
        self.assertEqual(pk.size("barrel.length"), 114.0)
        self.assertEqual(pk.facts()["unsourced"], ["barrel.length"])
        with self.assertRaisesRegex(ValueError, "over 0"):
            PK.resolve_size("0", self.p.root)

    def test_the_inputs_checksum_follows_chosen_values_only(self):
        d = PK.load("x", self.p.root)
        before = d["inputs_sha"]
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "--root", self.p.root])                       # a refresh (a rescan, a new clock)
            PK.main(["x", "time", "gather", "60", "--root", self.p.root])  # a timing
        self.assertEqual(PK.load("x", self.p.root)["inputs_sha"], before)
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "size", "slide.length", "187", "--source", "manual p.4", "--root", self.p.root])
        self.assertNotEqual(PK.load("x", self.p.root)["inputs_sha"], before)

    def test_a_builds_identity_folds_in_the_pack_values(self):
        import rbx_score  # noqa: PLC0415

        script = os.path.join(self.p.root, "assets/models/build_x.py")
        first = rbx_score.build_identity(script)
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "--root", self.p.root])
        self.assertEqual(rbx_score.build_identity(script), first)  # a refresh is the same model
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "size", "slide.length", "190", "--source", "manual p.4", "--root", self.p.root])
        self.assertNotEqual(rbx_score.build_identity(script), first)  # another size: another model
        os.remove(os.path.join(self.p.root, "assets/models/x.pack.json"))
        with open(script, "rb") as fh:
            import hashlib  # noqa: PLC0415
            self.assertEqual(rbx_score.build_identity(script),
                             hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()[:16])  # no pack: as ever

    def test_showing_or_timing_a_pack_with_nothing_chosen_keeps_the_builds_identity(self):
        import rbx_score  # noqa: PLC0415

        p = Project()
        try:
            p.write("assets/models/build_y.py", 'a = rbx.Asset("y")\n')
            script = os.path.join(p.root, "assets/models/build_y.py")
            first = rbx_score.build_identity(script)
            with contextlib.redirect_stdout(io.StringIO()):
                PK.main(["y", "--root", p.root])                        # a plain show
                PK.main(["y", "time", "gather", "60", "--root", p.root])  # a timing
            self.assertNotIn("inputs_sha", PK.load("y", p.root))
            self.assertEqual(rbx_score.build_identity(script), first)
        finally:
            p.close()

    def test_a_downloaded_photo_is_a_photo_a_library_render_and_a_measure_mask_are_models(self):
        for name, src in (("x_rifle_side", "build/refs/glock_17_side/Glock_17.jpg"),
                          ("x_lib_top", "build/library/arp_lib/part_3_top.png"),
                          ("x_scan_front", "build/refs/x_scan_front_mask.png")):
            self.p.write(f"assets/models/{name}.trace.json", {"source": src, "parts": {}})
        t = PK.scan("x", self.p.root)["traces"]
        self.assertEqual((t["x_rifle_side"]["source"], t["x_lib_top"]["source"], t["x_scan_front"]["source"]),
                         ("photo", "model", "model"))

    def test_a_bare_length_is_unsourced_everywhere(self):
        with contextlib.redirect_stdout(io.StringIO()):
            PK.main(["x", "object", "Example 17", "--length-mm", "186", "--root", self.p.root])
        self.assertEqual(PK.load("x", self.p.root)["object"]["trust"], "unsourced")
        pk = RP.Pack("x", self.p.root)
        self.assertEqual(pk.length_mm, 186.0)
        self.assertEqual(pk.facts()["unsourced"], ["length_mm"])

    def test_broken_packs_and_traces_never_crash(self):
        self.p.write("assets/models/x.pack.json", [1, 2])  # a pack that is a list
        self.assertFalse(RP.Pack("x", self.p.root).data.get("sizes"))
        self.p.write("assets/models/x.pack.json", {"found": [1, 2]})  # a 'found' that is a list
        RP.Pack("x", self.p.root)
        self.p.write("assets/models/x.pack.json", {"found": {"traces": {"x_gone_side": {
            "view": "side", "source": "photo", "profiles": "assets/models/x_gone_side.profiles.json"}}}})
        with self.assertRaises(RP.PackMissing):  # a stale entry (deleted since): the scan is the truth, never a traceback
            RP.Pack("x", self.p.root).profile("slide", trace="x_gone_side")
        self.assertEqual(RP.Pack("x", self.p.root).profile("slide")[1], (186, 0))  # ... and the valid trace still reads
        self.p.write("assets/models/x_photo_side.profiles.json", "{ not json")  # a real trace, its profiles broken
        with self.assertRaises(RP.PackMissing) as cm:
            RP.Pack("x", self.p.root).profile("slide")
        self.assertIn("gone or broken: assets/models/x_photo_side.profiles.json", str(cm.exception))
        self.p.write("assets/models/x_photo_side.profiles.json", {"parts": [1, 2], "outline": []})  # parts: a list
        with self.assertRaises(RP.PackMissing) as cm:
            RP.Pack("x", self.p.root).profile("slide")
        self.assertIn("make it again: lune run kit refs profiles", str(cm.exception))
        self.p.write("refs/private/x/x_scan.measure.json", "{ not json")
        with self.assertRaises(RP.PackMissing):  # a broken measure file: said, never a traceback
            RP.Pack("x", self.p.root).levels("x_scan")
        self.p.write("assets/models/x_photo_side.trace.json", {"source": "refs/x_side.png", "parts": [1, 2],
                                                               "frame": {"x0": 0, "y1": 0, "length_px": 1}})
        self.assertEqual(PK.scan("x", self.p.root)["traces"]["x_photo_side"]["parts"], [])
        alb = os.path.join(self.p.root, "assets/models/x.albedo.npz")
        np.savez_compressed(alb, albedo=np.zeros((4, 4, 3), np.float16), meta=json.dumps({"source": "refs/x_side.png"}))
        self.assertEqual(PK.part_colours(os.path.join(self.p.root, "assets/models/x_photo_side.trace.json"), alb)[0], {})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(PK.main(["x", "--root"]), 1)  # --root without a folder: refused, never the real repo
        self.assertIn("--root needs a folder", out.getvalue())

    def test_a_hand_edited_pack_is_said_stale(self):
        self.assertFalse(self.pk.facts()["inputs_stale"])  # (saved by kit pack: in step)
        path = os.path.join(self.p.root, "assets/models/x.pack.json")
        d = json.load(open(path, encoding="utf-8"))
        d["sizes"]["slide.length"]["mm"] = 190  # by hand, no `kit pack`
        self.p.write("assets/models/x.pack.json", d)
        self.assertTrue(RP.Pack("x", self.p.root).facts()["inputs_stale"])

    def test_a_time_that_is_no_number_is_refused(self):
        for bad in ("nan", "inf", "-5"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(PK.main(["x", "time", "gather", bad, "--root", self.p.root]), 1, bad)
        self.assertEqual(PK.load("x", self.p.root)["timings"], [])

    def test_malformed_profiles_and_no_outline_are_said(self):
        self.p.write("assets/models/x_photo_side.profiles.json", {"outline": "nope", "parts": {"slide": [[0], "x"]},
                                                                   "extents": {"slide": "bad"}})
        pk = RP.Pack("x", self.p.root)
        for call in (lambda: pk.profile("slide"), lambda: pk.extents("slide"), lambda: pk.outline()):
            with self.assertRaises(RP.PackMissing) as cm:
                call()
            self.assertIn("holds no usable", str(cm.exception))
        with self.assertRaises(RP.PackMissing) as cm:
            RP.Pack("x", self.p.root).outline(view="top")
        self.assertIn("no mm outline in a top trace", str(cm.exception))

    def test_a_length_written_as_text_is_shown_never_a_crash(self):
        d = PK.load("x", self.p.root)
        d["object"] = {"name": "Example 17", "length_mm": "186 mm"}
        self.assertIn("'186 mm' (no number)", PK.summary_of(d))
        self.p.write("assets/models/x.pack.json", d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(PK.main(["x", "--root", self.p.root]), 0)

    def test_no_pack_at_all(self):
        pk = RP.Pack("nothing", self.p.root)
        self.assertFalse(pk.exists)
        with self.assertRaises(RP.PackMissing):
            pk.length_mm  # noqa: B018



class TestDossierSizes(unittest.TestCase):
    """`--length dossier` / `size <part.dim> dossier`: the object's GRADED fact (kit dossier) — A or B only"""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        import dossier  # noqa: PLC0415

        self.dossier = dossier
        self.facts = {"overall.length": {"value": 202.0, "unit": "mm", "grade": "A", "why": "the maker"},
                      "slide.width": {"value": 25.5, "unit": "mm", "grade": "C", "why": "one source"},
                      "overall.mass": {"value": 0.63, "unit": "kg", "grade": "A", "why": "the maker"}}

    def fake(self, name, offline=True):
        if name != "glock 17 gen5":
            return None
        return {"slug": "glock_17_gen5", "facts": self.facts,
                "frame": {"length": {"mm": 202.0, "grade": "A", "key": "overall.length"}}}

    def test_a_graded_fact_sizes_the_pack_and_a_weak_one_is_refused(self):
        from unittest import mock  # noqa: PLC0415

        with mock.patch.object(self.dossier, "summary_for", side_effect=self.fake):
            length = PK.resolve_size("dossier", obj="glock 17 gen5")
            self.assertEqual((length["mm"], length["trust"], length["source"]),
                             (202.0, "high", "dossier:glock_17_gen5:overall.length"))
            with self.assertRaisesRegex(ValueError, "grade C"):
                PK.resolve_size("dossier", obj="glock 17 gen5", key="slide.width")
            with self.assertRaisesRegex(ValueError, "not a length"):
                PK.resolve_size("dossier", obj="glock 17 gen5", key="overall.mass")
            with self.assertRaisesRegex(ValueError, "has no barrel.length"):
                PK.resolve_size("dossier", obj="glock 17 gen5", key="barrel.length")
            with self.assertRaisesRegex(ValueError, "no dossier for 'colt m1911'"):
                PK.resolve_size("dossier", obj="colt m1911")
            with self.assertRaisesRegex(ValueError, "no object chosen"):
                PK.resolve_size("dossier", key="slide.length")

    def test_a_row_its_dossier_withdrew_sizes_nothing(self):
        from unittest import mock  # noqa: PLC0415

        p = Project()
        try:
            p.write("kit/real_specs/pistol.json", [
                {"id": "len1", "object": "glock 17 gen5", "value": 202, "unit": "mm", "trust": "high"},
                {"id": "wid1", "object": "glock 17 gen5", "value": 32.2, "unit": "mm", "trust": "low"}])
            d = {"withdrawn_rows": {"wid1": {"why": "its box holds a lever"}}}
            with mock.patch.object(self.dossier, "load", return_value=d):
                self.assertEqual(PK.resolve_size("dims:len1", root=p.root)["mm"], 202.0)
                with self.assertRaisesRegex(ValueError, "withdrawn from the dossier.*lever"):
                    PK.resolve_size("dims:wid1", root=p.root)
            with mock.patch.object(self.dossier, "load", side_effect=self.dossier.Broken("bad json")):
                with self.assertRaisesRegex(ValueError, "cannot be read"):  # (a broken dossier vouches for nothing)
                    PK.resolve_size("dims:wid1", root=p.root)
            with mock.patch.object(self.dossier, "load", side_effect=self.dossier.Missing("no dossier")):
                self.assertEqual(PK.resolve_size("dims:wid1", root=p.root)["mm"], 32.2)  # (no dossier withdrew it)
        finally:
            p.close()


if __name__ == "__main__":
    unittest.main()
