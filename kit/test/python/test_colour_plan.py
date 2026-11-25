"""kit/tools/colour_plan.py: the model sheet's colour plan - where the object is (its traced outline, a cut-out, or
off a plain ground - and said when that ground is not plain), each palette colour's share of it as it is in a LIT
picture (a shade of a colour is that colour), the role that gives it, the object's three value families, and the
notes the numbers earn. Pictures are drawn here: known areas in, the same shares out."""

import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import colour_plan as C  # noqa: E402

GROUND = (200, 200, 205)
BODY, STEEL, CYAN, BLACK, RED = (46, 48, 56), (150, 155, 162), (27, 199, 236), (14, 14, 16), (200, 30, 30)


def picture(blocks, size=(200, 100), ground=GROUND, alpha=False):
    """blocks: [(x0, y0, x1, y1, rgb)] on a plain ground (or a cut-out) -> a saved PNG's path"""
    a = np.empty((size[1], size[0], 4), np.uint8)
    a[..., :3] = ground
    a[..., 3] = 0 if alpha else 255
    for x0, y0, x1, y1, rgb in blocks:
        a[y0:y1, x0:x1, :3] = rgb
        a[y0:y1, x0:x1, 3] = 255
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.fromarray(a, "RGBA").convert("RGBA" if alpha else "RGB").save(path)
    return path


def gun(alpha=False, body=BODY, steel=STEEL, strip=CYAN, ground=GROUND):
    """an object 100 x 50 px: 60% body, 30% steel, 10% a strip"""
    return picture([(50, 25, 110, 75, body), (110, 25, 140, 75, steel), (140, 25, 150, 75, strip)], alpha=alpha,
                   ground=ground)


def shaded(rgb, k):
    """a colour with k of its light (in linear light, as a shadow is)"""
    c = np.asarray(rgb, np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) * k
    out = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return tuple(int(round(v * 255)) for v in out)


PAL = [{"name": "body", "rgb": list(BODY)}, {"name": "steel", "rgb": list(STEEL)}, {"name": "strip", "rgb": list(CYAN)}]
OUTLINE = [(50, 25), (150, 25), (150, 75), (50, 75)]


class Pixels(unittest.TestCase):
    def test_the_object_is_what_is_away_from_a_plain_ground(self):
        a = C.read(gun())
        self.assertEqual((int(a["mask"].sum()), a["by"], a["unsure"]), (100 * 50, "ground", None))
        self.assertEqual((a["px"].shape, a["rgb"].shape), ((5000, 3), (100, 200, 3)))

    def test_a_cut_out_is_where_it_is_opaque(self):
        a = C.read(gun(alpha=True))
        self.assertEqual((int(a["mask"].sum()), a["by"]), (5000, "cut-out"))

    def test_the_traced_outline_is_the_object_whatever_the_ground(self):
        # a ground of two colours with the object's own colour in a corner: only the outline knows the object
        path = picture([(0, 0, 200, 50, (90, 120, 90)), (0, 0, 30, 30, BODY), (50, 25, 110, 75, BODY),
                        (110, 25, 140, 75, STEEL), (140, 25, 150, 75, CYAN)])
        a = C.read(path, polygon=OUTLINE)
        self.assertEqual((int(a["mask"].sum()), a["by"], a["unsure"]), (5000, "outline", None))
        got = {r["name"]: r["share"] for r in C.plan(path, PAL, polygon=OUTLINE)["rows"]}
        self.assertAlmostEqual(got["body"], 0.6, delta=0.01)
        blind = C.plan(path, PAL)                                   # without it: wrong, and it SAYS it is unsure
        self.assertTrue(any("ground is not plain" in n for n in blind["notes"]), blind["notes"])
        self.assertIn("unsure", C.said(blind))

    def test_a_hole_in_the_outline_is_not_the_object(self):
        a = C.read(gun(), polygon=OUTLINE, holes=[[(60, 35), (100, 35), (100, 65), (60, 65)]])
        self.assertAlmostEqual(int(a["mask"].sum()), 5000 - 40 * 30, delta=80)

    def test_a_ground_that_is_not_plain_is_said(self):
        grad = np.linspace(60, 230, 200).astype(np.uint8)
        arr = np.repeat(np.repeat(grad[None, :, None], 100, axis=0), 3, axis=2).copy()
        arr[25:75, 50:150] = BODY
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        Image.fromarray(arr, "RGB").save(path)
        self.assertIn("ground is not plain", C.read(path)["unsure"])
        self.assertIsNone(C.read(gun())["unsure"])

    def test_only_inside_the_traced_box(self):
        self.assertEqual(int(C.read(gun(), box=(50, 25, 110, 75))["mask"].sum()), 60 * 50)     # the body alone
        got = C.plan(gun(), PAL, box=(50, 25, 110, 75))             # ... and the PLAN reads only there
        self.assertEqual({r["name"]: r["share"] for r in got["rows"]}["body"], 1.0)

    def test_a_large_picture_is_measured_small(self):
        big = picture([(1000, 500, 2200, 1500, BODY), (2200, 500, 2800, 1500, STEEL), (2800, 500, 3000, 1500, CYAN)],
                      size=(4000, 2000))
        a = C.read(big)
        self.assertEqual(max(a["rgb"].shape[:2]), C.LONGEST)
        got = {r["name"]: r["share"] for r in C.plan(big, PAL)["rows"]}
        self.assertAlmostEqual(got["body"], 0.6, delta=0.01)
        self.assertAlmostEqual(got["strip"], 0.1, delta=0.01)
        boxed = C.read(big, box=(1000, 500, 2200, 1500), polygon=[(1000, 500), (3000, 500), (3000, 1500), (1000, 1500)])
        self.assertAlmostEqual(float(boxed["mask"].sum()) / float(a["mask"].sum()), 0.6, delta=0.02)   # scaled with it


class Shares(unittest.TestCase):
    def test_known_areas_in_the_same_shares_out(self):
        p = C.plan(gun(), PAL)
        got = {r["name"]: r["share"] for r in p["rows"]}
        self.assertAlmostEqual(got["body"], 0.6, places=3)
        self.assertAlmostEqual(got["steel"], 0.3, places=3)
        self.assertAlmostEqual(got["strip"], 0.1, places=3)
        self.assertEqual((p["other"], p["pixels"], p["measured"]), (0.0, 5000, True))

    def test_a_shade_of_a_colour_is_that_colour_saturated_ones_too(self):
        # half of every part in shadow, at 0.4 and at 0.25 of its light: a neutral, a cyan, a red, a yellow
        for k in (0.4, 0.25):
            for name, rgb in (("grey", STEEL), ("cyan", CYAN), ("red", RED), ("yellow", (230, 200, 30))):
                path = picture([(50, 25, 150, 50, rgb), (50, 50, 150, 75, shaded(rgb, k))])
                p = C.plan(path, [{"name": name, "rgb": list(rgb)}, {"name": "body", "rgb": list(BODY)}])
                got = {r["name"]: r["share"] for r in p["rows"]}
                self.assertAlmostEqual(got[name], 1.0, delta=0.02, msg=(name, k, p["other"]))

    def test_between_a_black_part_and_the_shadow_of_a_grey_one_the_black_part_wins(self):
        path = picture([(50, 25, 100, 75, BODY), (100, 25, 150, 75, BLACK)])
        got = {r["name"]: r["share"] for r in C.plan(path, [{"name": "body", "rgb": list(BODY)},
                                                            {"name": "grip", "rgb": list(BLACK)}])["rows"]}
        self.assertAlmostEqual(got["body"], 0.5, delta=0.01)
        self.assertAlmostEqual(got["grip"], 0.5, delta=0.01)

    def test_what_is_near_no_palette_colour_is_other(self):
        path = picture([(50, 25, 110, 75, BODY), (110, 25, 150, 75, (220, 30, 30))])      # 40% a red nobody listed
        p = C.plan(path, PAL)
        self.assertAlmostEqual(p["other"], 0.4, places=3)
        self.assertTrue(any("near none of the palette" in n for n in p["notes"]))

    def test_no_pixels_no_palette(self):
        empty = C.plan(picture([]), PAL)
        self.assertEqual((empty["rows"], empty["leads"]), ([], None))
        self.assertIn("no object pixels", empty["notes"][0])
        sh, other = C.shares(np.zeros((0, 3)), [[1, 2, 3], [4, 5, 6]])
        self.assertEqual((sh.tolist(), other), ([0.0, 0.0], 0.0))

    def test_every_palette_colour_is_a_row_the_absent_and_the_twin_too(self):
        # the owner approves the whole palette: a colour that is not in this view (a top-only part) and a colour
        # that is another's twin keep their rows
        pal = PAL + [{"name": "inner", "rgb": [200, 60, 200]}, {"name": "body again", "rgb": [47, 48, 56]}]
        rows = C.plan(gun(), pal)["rows"]
        self.assertEqual(sorted(r["name"] for r in rows), sorted(p["name"] for p in pal))
        by = {r["name"]: r for r in rows}
        self.assertEqual((by["inner"]["share"], by["inner"]["role"]), (0.0, "minor"))
        self.assertEqual((by["body again"]["same_as"], by["body again"]["role"], by["body again"]["share"]),
                         ("body", "same", 0.0))
        self.assertAlmostEqual(by["body"]["share"], 0.6, places=3)   # the twin took none of it


class Roles(unittest.TestCase):
    def test_main_second_accent(self):
        rows = C.plan(gun(), PAL)["rows"]
        self.assertEqual([(r["name"], r["role"]) for r in rows],
                         [("body", "main"), ("steel", "second"), ("strip", "accent")])

    def test_a_small_colour_close_to_the_main_is_no_accent(self):
        rows = C.roles([{"name": "a", "rgb": [46, 48, 56], "share": 0.7}, {"name": "b", "rgb": [150, 155, 162], "share": 0.25},
                        {"name": "c", "rgb": [52, 54, 60], "share": 0.05}])
        self.assertEqual([r["role"] for r in rows], ["main", "second", "minor"])

    def test_every_large_colour_after_the_main_is_a_second(self):
        rows = C.roles([{"name": "a", "rgb": [46, 48, 56], "share": 0.35}, {"name": "b", "rgb": [150, 155, 162], "share": 0.35},
                        {"name": "c", "rgb": [200, 60, 40], "share": 0.3}, {"name": "d", "rgb": [27, 199, 236], "share": 0.0}])
        self.assertEqual([(r["name"], r["role"]) for r in rows],
                         [("a", "main"), ("b", "second"), ("c", "second"), ("d", "minor")])   # (ties: by name)
        self.assertEqual(C.roles([]), [])
        self.assertEqual([r["role"] for r in C.roles([{"name": "a", "rgb": [1, 1, 1], "share": 0.0}])], ["minor"])

    def test_largest_first(self):
        rows = C.roles([{"name": "s", "rgb": list(CYAN), "share": 0.1}, {"name": "b", "rgb": list(BODY), "share": 0.6}])
        self.assertEqual([r["name"] for r in rows], ["b", "s"])

    def test_sampled_colours_get_no_roles(self):
        p = C.plan(gun(), None)                                      # no palette: sampled off the object
        self.assertFalse(p["measured"])
        self.assertTrue(p["rows"] and all(r["role"] is None for r in p["rows"]))
        self.assertTrue(any("SAMPLED" in n and "kit pack" in n for n in p["notes"]))
        self.assertFalse(any("no accent" in n or "no colour leads" in n for n in p["notes"]))
        self.assertTrue(C.said(p).startswith("colours: sampled (no roles); values: "))
        self.assertAlmostEqual(sum(r["share"] for r in p["rows"]) + p["other"], 1.0, delta=0.01)

    def test_sampled_colours_are_the_objects_own(self):
        # a loud ground: none of the sampled colours is the ground's
        p = C.plan(gun(ground=(255, 0, 255)), None)
        for r in p["rows"]:
            self.assertGreater(float(np.abs(np.asarray(r["rgb"]) - np.array([255, 0, 255])).sum()), 100, r)

    def test_a_share_at_the_line_between_accent_and_second_is_said(self):
        path = picture([(50, 25, 138, 75, BODY), (138, 25, 150, 75, CYAN)])               # 12% a strip
        notes = C.plan(path, PAL)["notes"]
        self.assertTrue(any("at the line between an accent and a second" in n and "strip" in n for n in notes), notes)
        self.assertFalse(any("at the line" in n for n in C.plan(gun(), PAL)["notes"]))    # 10% and 30%: not said


class Values(unittest.TestCase):
    def test_three_families_of_three_known_greys(self):
        L = np.concatenate([np.full(600, 15.0), np.full(300, 50.0), np.full(100, 85.0)])
        f = C.families(L)
        self.assertEqual((f["dark"]["share"], f["mid"]["share"], f["light"]["share"]), (0.6, 0.3, 0.1))
        self.assertEqual((f["dark"]["L"], f["mid"]["L"], f["light"]["L"]), (15.0, 50.0, 85.0))
        self.assertTrue(15.0 < f["cuts"][0] < 50.0 < f["cuts"][1] < 85.0)

    def test_the_families_are_the_objects_own(self):
        rng = np.random.default_rng(1)
        L = np.concatenate([rng.normal(8, 1, 500), rng.normal(16, 1, 300), rng.normal(26, 1, 200)])   # a black gun
        f = C.families(L)
        self.assertAlmostEqual(f["dark"]["share"], 0.5, delta=0.02)
        self.assertAlmostEqual(f["light"]["L"], 26.0, delta=0.5)
        self.assertEqual(C.families(L), C.families(L))                # the same every time

    def test_an_object_of_one_flat_value_is_that_value_never_light_by_default(self):
        self.assertEqual({k: C.families(np.full(500, 4.0))[k]["share"] for k in ("dark", "mid", "light")},
                         {"dark": 1.0, "mid": 0.0, "light": 0.0})    # a black silhouette is DARK
        self.assertEqual(C.families(np.full(500, 50.0))["mid"]["share"], 1.0)
        self.assertEqual(C.families(np.full(500, 90.0))["light"]["share"], 1.0)
        self.assertIsNone(C.families(np.full(500, 4.0))["light"]["L"])
        flat = picture([(50, 25, 150, 75, BLACK)])
        self.assertEqual(C.plan(flat, [{"name": "all", "rgb": list(BLACK)}])["leads"], "dark")

    def test_no_pixels(self):
        f = C.families([])
        self.assertEqual((f["dark"]["share"], f["dark"]["L"]), (0.0, None))

    def test_the_three_grey_picture(self):
        path = gun(steel=(110, 112, 118), strip=(225, 226, 230))      # a dark, a middle and a light part
        px, mask, rgb = C.object_pixels(path)
        fam = C.families(C.lab(px)[:, 0])
        g = C.three_grey(rgb, mask, fam)
        self.assertEqual(g.shape, rgb.shape)
        self.assertEqual(tuple(g[0, 0]), (38, 40, 45))                # the ground
        inside = g[mask]
        self.assertTrue((inside[:, 0] == inside[:, 1]).all() and (inside[:, 1] == inside[:, 2]).all())   # greys
        self.assertEqual(len(np.unique(inside[:, 0])), 3)             # three of them
        self.assertLess(int(g[50, 60, 0]), int(g[50, 120, 0]))        # the body darker than the steel
        self.assertLess(int(g[50, 120, 0]), int(g[50, 145, 0]))       # ... the steel darker than the strip
        self.assertEqual(tuple(C.three_grey(rgb, mask, fam, (24, 62, 78))[0, 0]), (24, 62, 78))
        self.assertAlmostEqual(float(C.lab([C._grey_of(50.0)] * 3)[0]), 50.0, delta=0.6)   # a grey of that lightness

    def test_an_object_of_two_values_has_an_empty_family_and_says_none(self):
        # the gun: a dark body, and a steel and a strip only 10 L* apart - they are ONE light family; the middle
        # one is empty (nothing is invented to fill a third)
        px, mask, rgb = C.object_pixels(gun())
        fam = C.families(C.lab(px)[:, 0])
        self.assertEqual((fam["dark"]["share"], fam["mid"]["share"], fam["light"]["share"]), (0.6, 0.0, 0.4))
        self.assertIsNone(fam["mid"]["L"])
        self.assertEqual(len(np.unique(C.three_grey(rgb, mask, fam)[mask][:, 0])), 2)

    def test_a_palette_colour_knows_its_family(self):
        rows = {r["name"]: r for r in C.plan(gun(), PAL)["rows"]}
        self.assertEqual((rows["body"]["value"], rows["strip"]["value"]), ("dark", "light"))
        self.assertLess(rows["body"]["L"], rows["steel"]["L"])


class Notes(unittest.TestCase):
    def test_a_sound_plan_earns_none(self):
        self.assertEqual(C.plan(gun(strip=RED), [PAL[0], PAL[1], {"name": "strip", "rgb": list(RED)}])["notes"], [])

    def test_two_large_parts_of_one_grey_are_said_whichever_they_are(self):
        # a body and a grip 8 L* apart are one dark shape in the three-grey read - the FIXTURE's own case, which a
        # note on main-against-second alone did not catch
        grip = (30, 30, 33)
        path = picture([(50, 25, 110, 75, BODY), (110, 25, 130, 75, STEEL), (130, 25, 150, 75, grip)])
        notes = C.plan(path, [PAL[0], PAL[1], {"name": "grip", "rgb": list(grip)}])["notes"]
        self.assertTrue(any("body and grip are ONE grey" in n for n in notes), notes)
        self.assertFalse(any("steel" in n and "ONE grey" in n for n in notes), notes)

    def test_hue_alone(self):
        # a red and a green of the same lightness, half and half: one value, and said twice over
        red, green = (190, 60, 60), (52, 131, 52)
        self.assertLess(abs(float(C.lab(red)[0] - C.lab(green)[0])), 4.0)
        path = picture([(50, 25, 100, 75, red), (100, 25, 150, 75, green)])
        notes = C.plan(path, [{"name": "red", "rgb": list(red)}, {"name": "green", "rgb": list(green)}])["notes"]
        self.assertTrue(any("it is ONE value" in n for n in notes), notes)
        self.assertTrue(any("green and red are ONE grey" in n or "red and green are ONE grey" in n for n in notes), notes)

    def test_no_colour_leads_and_no_accent_and_no_family_leads(self):
        a, b, c = (60, 60, 70), (140, 140, 150), (220, 220, 225)
        path = picture([(50, 25, 84, 75, a), (84, 25, 117, 75, b), (117, 25, 150, 75, c)], ground=(0, 80, 0))
        notes = C.plan(path, [{"name": n, "rgb": list(v)} for n, v in (("a", a), ("b", b), ("c", c))])["notes"]
        self.assertTrue(any("no colour leads" in n for n in notes), notes)
        self.assertTrue(any("no accent" in n for n in notes), notes)
        self.assertTrue(any("no value family leads (dark 3" in n for n in notes), notes)

    def test_said(self):
        self.assertEqual(C.said(C.plan(gun(), PAL)),
                         "colours: main body 60%, second steel 30%, accent strip 10%; values: dark leads 60%")
        self.assertEqual(C.said({}), "colours: none measured")
        self.assertEqual(C.said(C.plan(picture([]), PAL)), "colours: none measured")


if __name__ == "__main__":
    unittest.main()
