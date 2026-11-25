"""kit/tools/make.py (`kit make <name> "<object>"`): the pieces that decide without running a generator — the object's
category and real-size kind from its words, a silhouette compared shape-to-shape (a candidate against a photo), a
colour photo told from a black-and-white one, the single photo chosen by how surely it shows the object, a reference
model's quality verdict (a raw scan, debris, proportions), a generated mesh told torn from sound (its open edges once
welded), and the module coverage rule (a module neither run nor skipped with a reason fails the run)."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import make as MK  # noqa: E402


def _run(tmp, name="zz_test_make"):
    r = MK.Run.__new__(MK.Run)
    r.name, r.obj, r.tier, r.private, r.fresh = name, "a thing", "prop", False, False
    r.budget, r.t0 = 600, __import__("time").time()
    r.dir = tmp
    r.stages, r.facts = {}, {}
    r.log = open(os.path.join(tmp, "make.log"), "w", encoding="utf-8")
    return r


class Know(unittest.TestCase):
    def test_category_from_words(self):
        self.assertEqual(MK.category_of("Glock 17 Gen 5"), "pistol")
        self.assertEqual(MK.category_of("Barrett M107"), "rifle")
        self.assertEqual(MK.category_of("wooden chair"), "generic")

    def test_real_size_kind(self):
        kind, rng = MK.kind_of("a wooden dining chair")
        self.assertEqual(kind, "chair")
        self.assertTrue(0.8 < sum(rng["height"]) / 2 < 1.0)
        self.assertEqual(MK.kind_of("a spaceship"), (None, None))


class Life(unittest.TestCase):
    """kit make wears the generated body as its words say: a factory-fresh surface was what judges marked down"""

    def test_the_words_choose_the_life(self):
        self.assertEqual(MK.life_of("an old wooden chest"), "heavy")
        self.assertEqual(MK.life_of("a rusty fire hydrant"), "heavy")
        self.assertEqual(MK.life_of("a brand-new office chair"), "new")
        self.assertEqual(MK.life_of("a polished brass lamp"), "new")
        self.assertEqual(MK.life_of("a wooden chair"), "light")   # (in use, not abused)
        self.assertEqual(MK.life_of("a golden goblet"), "light")   # ("old" inside "golden" is no word)

    def test_the_surface_carries_it(self):
        class R:
            obj, facts = "an old wooden chest", {}
        surf = MK.surface_of(R)
        self.assertEqual((surf["scan"], surf["life"]), ("Wood096", "heavy"))
        R.obj = "a statue"   # (no word, no category: the scan the roughness check would prescribe, never one flat value)
        surf = MK.surface_of(R)
        self.assertEqual((surf["rough"], surf["life"]), (0.6, "light"))
        sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
        import rbx_pbr  # noqa: PLC0415

        self.assertEqual(surf.get("scan"), rbx_pbr.scan_for("a statue", 0.0))


class Brief(unittest.TestCase):
    """kit make writes the brief from the owner's REQUEST (the object, the tier, private or not; a prop is static) so
    kit plan's stage-0 gate passes on the make route — and never over a brief the owner wrote or edited"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "assets", "models"))
        self._repo, MK.REPO = MK.REPO, self.tmp.name
        self.r = _run(self.tmp.name, "barrel")
        self.r.obj, self.r.route, self.r.no_gen = "a wooden barrel", None, False
        self.path = os.path.join(self.tmp.name, "assets", "models", "barrel.brief.md")

    def tearDown(self):
        MK.REPO = self._repo
        self.r.log.close()
        self.tmp.cleanup()

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def test_a_props_brief_passes_kit_plans_stage_zero(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        import plan as PL  # noqa: PLC0415

        MK.write_brief(self.r)
        with open(os.path.join(self.tmp.name, "assets", "models", "build_barrel.py"), "w") as fh:
            fh.write('import rbx\na = rbx.Asset("barrel")\na.build()\n')
        st = {x["key"]: x for x in PL.assess(PL.facts("barrel", self.tmp.name))}
        # every answer passes; only its ROUTE is refused — the generated + colour-regions prop route is graveyarded since
        # 2026-10-17 (G8: three batches 0-3.5/10, batch 3 "ye hhorrible"): kit make's props need a new route
        missing = st["brief"]["missing"]
        self.assertTrue(missing and all(m.startswith("graveyarded route") and "G8" in m for m in missing), missing)
        self.assertIn("- function: static", self.read())
        self.assertIn("- ownership: a generic / public object", self.read())

    def test_private_and_complex_say_so_and_leave_function_to_the_owner(self):
        self.r.private, self.r.tier = True, "complex"
        MK.write_brief(self.r)
        text = self.read()
        self.assertIn("private=True", text)
        self.assertIn("- quality: complex", text)
        self.assertIn("- function: <answer>", text)   # (what moves is the owner's to say, never made up)

    def test_never_over_the_owners_brief_and_never_over_an_edited_one(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("# barrel — the owner's own brief\n- what: an oak barrel with a tap\n")
        MK.write_brief(self.r)
        self.assertIn("an oak barrel with a tap", self.read())
        os.remove(self.path)
        MK.write_brief(self.r)                      # (its own, unedited: rewritten on the next run)
        self.r.obj = "a wooden barrel, iron hoops"
        MK.write_brief(self.r)
        self.assertIn("- what: a wooden barrel, iron hoops", self.read())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("- note: keep the tap\n")      # (the owner edited it: theirs now)
        self.r.obj = "something else"
        MK.write_brief(self.r)
        self.assertIn("keep the tap", self.read())
        self.assertNotIn("something else", self.read())


class SizesToThePack(unittest.TestCase):
    """kit make writes every graded size into the asset's pack WITH its source (kit plan's gather gate needs a sourced
    size; the made props had one in the run and none in the pack)"""

    def test_each_graded_size_is_packed_with_the_key_it_came_from(self):
        from unittest import mock  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp, "chair_t")
            r.obj, r.route, r.no_gen = "a wooden chair", None, False
            calls = []
            r.kit = lambda args, timeout=0: (calls.append(args) or (True, {}, ""))
            with mock.patch.object(MK, "write_brief"), mock.patch.object(MK, "write_build"):
                MK.stage_know(r)   # (the files it writes are another test's: only the pack calls here)
            r.log.close()
        sizes = [c for c in calls if c[:3] == ["pack", "chair_t", "size"]]
        self.assertTrue(sizes, calls)
        for c in sizes:
            self.assertIn("--source", c)
            self.assertTrue(c[c.index("--source") + 1].startswith("real_sizes."), c)


class SizesFromDims(unittest.TestCase):
    """no dossier, no real_sizes range: kit make takes SOURCED rows (kit refs dims) for the object's words — the made
    extinguisher was 1000 mm tall while two shops said 387 mm"""

    ROWS = [{"id": "a", "object": "fire extinguisher 5 lb abc", "part": "overall", "dim": "height", "value": 387.4,
             "unit": "mm", "source": "shop1"},
            {"id": "b", "object": "fire extinguisher 5 lb abc", "part": "overall", "dim": "height", "value": 387.4,
             "unit": "mm", "source": "shop2"},
            {"id": "c", "object": "fire extinguisher 5 lb abc", "part": "body", "dim": "diameter", "value": 108,
             "unit": "mm", "source": "shop1"},
            {"id": "d", "object": "m4 carbine", "part": "barrel", "dim": "length", "value": 368, "unit": "mm",
             "source": "x"}]

    def sizes(self, obj):
        from unittest import mock  # noqa: PLC0415

        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        import dims  # noqa: PLC0415

        with mock.patch.object(dims, "load_all", return_value=self.ROWS):
            return MK.sizes_from_dims(obj)

    def test_the_head_noun_and_the_most_shared_words_pick_the_rows(self):
        s = self.sizes("a red fire extinguisher")
        self.assertEqual((s["height"]["mm"], s["height"]["grade"]), (387.4, "B"))   # (two sources agree)
        self.assertEqual((s["width"]["mm"], s["length"]["mm"], s["width"]["grade"]), (108, 108, "C"))   # (round)

    def test_a_word_shared_by_chance_is_not_enough(self):
        self.assertEqual(self.sizes("a wooden wine barrel"), {})   # (the carbine's barrel is not a wine barrel)
        self.assertEqual(self.sizes("a chair"), {})


class NoGenerators(unittest.TestCase):
    """--no-gen (the owner's pure-sculpt / code model): no 3D generator runs, no concept picture is drawn — the real
    photos are gathered, and every skipped module says why"""

    def test_a_generator_is_skipped_and_said(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp)
            r.no_gen = True
            called = []
            out = MK.gen(r, "candidates", "gen_single", "tr", lambda c: called.append(c) or ["gen", c], 300)
            r.log.close()
        self.assertIsNone(out)
        self.assertEqual(called, [])   # (its command was never even built)
        said = r.stages["candidates"]["modules"]["gen_single"]
        self.assertFalse(said["ran"])
        self.assertIn("--no-gen", str(said))

    def test_a_generic_object_takes_real_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp)
            r.obj, r.route = "a human skull", None
            r.no_gen = False
            self.assertFalse(MK.is_named_object(r))   # (by default: a concept agrees one design)
            r.no_gen = True
            self.assertTrue(MK.is_named_object(r))    # (no generator: the real photos)
            r.log.close()

    def test_no_gen_with_concept_is_refused(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = MK.main(["zz_test_nogen", "a human skull", "--no-gen", "--concept"])
        self.assertNotEqual(code, 0)
        self.assertIn("contradict", buf.getvalue())


class Pictures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _pic(self, name, rgb, box=(20, 30, 80, 70), mode="RGB"):
        a = np.full((100, 100, 3), 255, np.uint8)
        x0, y0, x1, y1 = box
        a[y0:y1, x0:x1] = rgb
        p = os.path.join(self.tmp, name)
        Image.fromarray(a).save(p)
        return p

    def test_silhouette_shape_compare(self):
        # the same rectangle at another scale and place: the same SHAPE (iou 1); a square against it: not
        a, asp_a = MK.norm_mask(self._pic("a.png", (40, 40, 40)))
        b, asp_b = MK.norm_mask(self._pic("b.png", (40, 40, 40), box=(10, 40, 40, 60)))
        c, asp_c = MK.norm_mask(self._pic("c.png", (40, 40, 40), box=(30, 30, 70, 70)))
        self.assertAlmostEqual(asp_a, asp_b, places=1)
        self.assertGreater(float((a & b).sum() / (a | b).sum()), 0.95)
        self.assertLess(min(asp_a, asp_c) / max(asp_a, asp_c), 0.8)

    def test_a_mislabelled_side_photo_is_caught(self):
        # an L (a pistol's slide and grip): the rig's right frame; a photo of the same, mirrored, is the OTHER side
        a = np.full((100, 160, 3), 255, np.uint8)
        a[20:45, 10:150] = 40     # (the slide, long)
        a[45:90, 100:140] = 40    # (the grip, at one end)
        rig = os.path.join(self.tmp, "rig.png")
        Image.fromarray(a).save(rig)
        same = os.path.join(self.tmp, "same.png")
        Image.fromarray(a).resize((320, 200)).save(same)
        other = os.path.join(self.tmp, "other.png")
        Image.fromarray(a[:, ::-1].copy()).save(other)
        self.assertEqual(MK.side_check(same, rig), "same")
        self.assertEqual(MK.side_check(other, rig), "other")
        self.assertEqual(MK.side_check(other, None), "same")   # (no rig frame to check against: the label stands)

    def test_colour_or_black_and_white(self):
        self.assertTrue(MK.is_colour(self._pic("brown.png", (150, 100, 40))))
        self.assertFalse(MK.is_colour(self._pic("grey.png", (120, 120, 120))))

    def test_best_photo_follows_the_rank(self):
        # found photos: the most-surely-the-object photo wins; a colour one only if it is nearly as sure
        with contextlib.redirect_stdout(io.StringIO()):
            r = _run(self.tmp)
        r.facts["cutouts"] = {"three_quarter": self._pic("bw.png", (90, 90, 90)),
                              "left": self._pic("col.png", (160, 90, 30))}
        r.facts["ranked_views"] = [["three_quarter", 0.18], ["left", 0.0002]]   # (the colour one: a chair PART)
        self.assertEqual(MK.best_photo(r)[0], "three_quarter")
        r.facts["ranked_views"] = [["three_quarter", 0.18], ["left", 0.15]]
        self.assertEqual(MK.best_photo(r)[0], "left")


def _glb(path, pts, tris):
    """a minimal GLB: one mesh, POSITION + indices"""
    import json
    import struct

    p = np.asarray(pts, np.float32).tobytes()
    i = np.asarray(tris, np.uint32).ravel().tobytes()
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(p) + len(i)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(p)},
                           {"buffer": 0, "byteOffset": len(p), "byteLength": len(i)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pts), "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5125, "count": len(i) // 4, "type": "SCALAR"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = p + i
    out = (struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(body)) + struct.pack("<II", len(js), 0x4E4F534A)
           + js + struct.pack("<II", len(body), 0x004E4942) + body)
    with open(path, "wb") as fh:
        fh.write(out)
    return path


class Topology(unittest.TestCase):
    def test_a_torn_mesh_is_told_from_a_sound_one(self):
        # a closed tetrahedron written as a triangle soup (every corner its own vertex, as a flat-shaded glTF export
        # writes it): welded, it is sound; the same faces each shrunk toward their centre (decimated alone): torn
        tmp = tempfile.mkdtemp()
        v = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], float)
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        soup = np.array([v[k] for f in faces for k in f])
        tris = np.arange(len(soup)).reshape(-1, 3)
        sound = MK.glb_topology(_glb(os.path.join(tmp, "sound.glb"), soup, tris))
        self.assertEqual((sound["faces"], sound["verts"], sound["open_share"]), (4, 4, 0.0))
        shrunk = soup.reshape(-1, 3, 3)
        shrunk = (shrunk - shrunk.mean(1, keepdims=True)) * 0.9 + shrunk.mean(1, keepdims=True)
        torn = MK.glb_topology(_glb(os.path.join(tmp, "torn.glb"), shrunk.reshape(-1, 3), tris))
        self.assertEqual(torn["open_share"], 1.0)
        self.assertGreater(torn["open_share"], MK.SHREDDED)


class Coverage(unittest.TestCase):
    def test_a_module_neither_run_nor_explained_fails(self):
        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            r = _run(tmp)
            for st in MK.STAGES:
                for m in MK.MODULES[st]:
                    r.mod(st, m, False, "not needed here")
            rep = r.write(True, "all said")
            self.assertTrue(rep["ok"], rep["uncovered"])
            del r.stages["look"]["modules"]["compare"]
            r.stages["surface"]["modules"]["paint"]["reason"] = ""
            rep = r.write(True, "two unsaid")
        self.assertFalse(rep["ok"])
        self.assertIn("look.compare", rep["uncovered"])
        self.assertTrue(any(u.startswith("surface.paint") for u in rep["uncovered"]))


class ColourBands(unittest.TestCase):
    """a ROUND body's colour bands from the view's rows (owner 2026-10-16 batch 2: the barrel's hoops in patches, the
    extinguisher's dome chrome): only the round slices take a band; a run of one region merges"""

    def test_hoops_become_bands_only_on_round_slices(self):
        with tempfile.TemporaryDirectory() as d:
            img = np.zeros((120, 80, 4), np.uint8)
            img[10:110, 10:70, 3] = 255
            img[10:110, 10:70, :3] = (150, 115, 75)          # wood
            img[95:110, 10:70, :3] = (120, 120, 120)         # a hoop at the bottom (rows 95-109: slices 0-2 of 20)
            Image.fromarray(img).save(os.path.join(d, "view_front_rgba.png"))

            class R:
                pass
            r = R()
            r.dir = d
            n = 20
            r.facts = {"round": {"slices": n, "profile": [[(k + 0.5) / n, 0.3] for k in range(n - 4)]}}   # top 4: not round
            regions = [{"name": "wood", "srgb": [150, 115, 75], "shades": [[150, 115, 75], [90, 70, 50]]},
                       {"name": "steel", "srgb": [125, 122, 115], "shades": [[125, 122, 115]]}]
            got = MK.colour_bands(r, regions)
            self.assertEqual(got[0][2], "steel")
            self.assertEqual(got[0][0], 0.0)
            self.assertEqual(got[1][2], "wood")
            self.assertLessEqual(max(b for _a, b, _n in got), (n - 4) / n + 1e-9)   # (the non-round top: no band)
            r.facts = {}
            self.assertEqual(MK.colour_bands(r, regions), [])


if __name__ == "__main__":
    unittest.main()


class TwoStops(unittest.TestCase):
    """kit make's two stops (his limitations review, 2026-11-17): a complex / hero piece goes past the model sheet and
    past the blockout only with the owner's approval of each as it is now (kit make-gate); a prop never stops"""

    def _faked(self, tmp, tier, approved):
        r = _run(tmp)
        r.tier, r.stopped = tier, None
        calls = []

        def kit(args, timeout=None):
            calls.append(args[0])
            if args[0] == "make-gate":
                return approved, [], 0.1
            return True, [], 0.1
        r.kit = kit
        return r, calls

    def test_a_prop_never_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, calls = self._faked(tmp, "prop", False)
            self.assertTrue(MK.stage_stop(r, "sheet"))
            r.log.close()
        self.assertEqual(calls, [])

    def test_a_complex_piece_stops_at_the_sheet_until_it_is_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, calls = self._faked(tmp, "complex", False)
            self.assertFalse(MK.stage_stop(r, "sheet"))
            r.log.close()
        self.assertEqual(calls, ["sheet", "make-gate"])   # (the sheet drawn, then the owner's question)
        self.assertIn("STOPPED for the owner at the model sheet", r.stopped)
        self.assertEqual(r.stop_step, "sheet")

    def test_an_approved_sheet_goes_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, _calls = self._faked(tmp, "hero", True)
            self.assertTrue(MK.stage_stop(r, "sheet"))
            r.log.close()
        self.assertIsNone(r.stopped)

    def test_the_blockout_stop_writes_the_build_and_never_the_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, calls = self._faked(tmp, "complex", False)
            r.facts = {"clean_mesh": os.path.join(tmp, "shape.glb")}
            wrote = []
            saved = (MK.write_build, MK.write_brief)
            MK.write_build = lambda rr, mesh: wrote.append(("build", mesh))
            MK.write_brief = lambda rr, mesh=None: wrote.append(("brief", mesh))
            try:
                self.assertFalse(MK.stage_stop(r, "blockout"))
            finally:
                MK.write_build, MK.write_brief = saved
            r.log.close()
        self.assertEqual([w[0] for w in wrote], ["build"])   # (a rewritten brief would stale the approved sheet)
        self.assertEqual(calls, ["blockout", "make-gate"])
        self.assertIn("blockout", r.stopped)

    def test_nothing_shaped_is_not_a_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, calls = self._faked(tmp, "hero", False)
            self.assertTrue(MK.stage_stop(r, "blockout"))
            r.log.close()
        self.assertEqual(calls, [])
