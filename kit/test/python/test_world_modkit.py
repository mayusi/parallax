"""test_world_modkit.py - W3: THE MODULAR GOTHIC KIT, ITS SHARED TRIM SHEETS AND THE FACADE GRAMMAR (kit/world/modkit.py,
trims.py, facade_grammar.py; LIMITATIONS_FIXES_V4 5.1 / 5.4 step 2 / 13.5: "a 15-20 piece modular PBR MeshPart kit +
<= 3 shared 1024 trims (35-70 px/stud, <= 15 maps) + facade_grammar"). Before: GothicCourtyard's houses were 1,094
plain Parts under three whole-house skins, each skin its own 1024 colour atlas, every house of one type the same house.
Held here: 18 modules on 2 sheets (6 maps: colour, normal, roughness), every face at 35..70 px/stud and every uv inside
its strip; the courses of two modules side by side line up (v from the floor on one grid) and every 4-stud module edge
falls on a joint of the coursed strips; the kit's gate refuses a squeezed bay, a doorway the R6 rig cannot pass, a
bay off the grid, a uv bleeding out of its strip; the grammar puts the court's nine houses together with every rule
held (each bay of each storey once, window columns, the doorway on the ground only, no stretch past the density bar)
and its check refuses a missing bay, a doorway upstairs, a broken column, a squeezed module.
Not claimed: how the kit reads in Roblox (an upload of each part is the owner's), LOD or collision meshes."""
import copy
import json
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)
import facade_grammar as G  # noqa: E402
import modkit as M  # noqa: E402
import trims as T  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
KIT = M.build_kit()


def court_houses():
    bp = json.load(open(os.path.join(ROOT, "assets", "worlds", "GothicCourtyard.json"), encoding="utf-8"))
    out = []
    for st in bp["build"]:
        b = st.get("building")
        if b:
            out.append(b)
    return out


class Kit(unittest.TestCase):
    def test_eighteen_modules_two_sheets_six_maps_all_faces_at_the_bar(self):
        errors, stats = M.check(KIT)
        self.assertEqual(errors, [])
        self.assertEqual(stats["modules"], 18)
        self.assertEqual(stats["sheets"], ["roof", "stone"])
        self.assertEqual(stats["maps"], 6)
        self.assertGreaterEqual(stats["density"][0], 35)
        self.assertLessEqual(stats["density"][1], 70)
        for name in ("wall_4", "lancet_4", "twin_lancet_8", "portal_8", "plinth_4", "string_4", "cornice_4", "parapet_4",
                     "quoin", "pilaster", "buttress", "roof_4", "ridge_4", "gable_16", "dormer", "chimney", "cobble_4", "wall_8"):
            self.assertIn(name, KIT)

    def test_the_doorway_fits_the_rig(self):
        op = KIT["portal_8"]["opening"]
        self.assertGreaterEqual(op["width"], 4.5)
        self.assertGreaterEqual(op["apex"], 8.5)
        # a pointed (equilateral) arch: the apex stands half-width x sqrt(3) over the spring
        self.assertAlmostEqual(op["apex"] - 5.3, 2.5 * 3 ** 0.5, places=2)

    def test_courses_line_up_across_modules(self):
        # every front-face vertex of the ashlar on a wall, a lancet, a twin lancet and a portal lies on ONE mapping of
        # height to v: the band grid from the floor (6 studs: three 2-stud courses), the same row for the same height
        top, hpx = T.STRIPS["ashlar"][1:]
        band = 6.0

        def row_of(y, k):
            return top + hpx - M.INSET_PX - (y - k * band) * T.PX

        seen = 0
        for name in ("wall_4", "wall_8", "lancet_4", "twin_lancet_8", "portal_8"):
            for part in KIT[name]["parts"]:
                for (x, y, z), (u, v) in zip(part["verts"], part["uvs"]):
                    row = (1 - v) * T.SHEET
                    if abs(z) > 1e-6 or not (top <= row <= top + hpx):
                        continue
                    k = int(y // band)
                    ok = abs(row - row_of(y, k)) < 1e-3 or (abs(y - k * band) < 1e-6 and abs(row - row_of(y, k - 1)) < 1e-3)
                    self.assertTrue(ok, (name, y, row, row_of(y, k)))
                    seen += 1
        self.assertGreater(seen, 100)

    def test_every_four_studs_a_joint_in_the_coursed_strips(self):
        sheet = T.make_sheet("stone")
        h = np.asarray(sheet["normal"])
        for strip in ("ashlar", "plinth"):
            top, hpx = T.STRIPS[strip][1:]
            hf = sheet["height"][top:top + hpx]
            for c in range(0, T.SHEET, T.CELL):
                # the column at a cell's edge is a joint on every course: recessed, low in the height field
                self.assertLess(float(np.max(hf[:, c])), 0.5, (strip, c))
            # (and a column in the middle of a block is not)
            self.assertGreater(float(np.mean(hf[:, 64:192] > 0.5)), 0.5)
        self.assertEqual(h.shape, (T.SHEET, T.SHEET, 3))
        n = h * 2 - 1
        self.assertTrue(np.allclose(np.linalg.norm(n, axis=-1), 1.0, atol=1e-3))

    def test_the_gate_refuses_what_breaks_the_bar(self):
        bad = copy.deepcopy(KIT)
        # a uv squeezed: the wall's front at twice the texels
        part = bad["wall_4"]["parts"][0]
        part["uvs"] = [(u * 2, v) for u, v in part["uvs"]]
        e, _ = M.check(bad)
        self.assertTrue(any("wall_4" in x and "px/stud" in x for x in e), e)
        bad = copy.deepcopy(KIT)
        bad["wall_8"]["size"][0] = 7.0
        e, _ = M.check(bad)
        self.assertTrue(any("not a whole number" in x for x in e), e)
        bad = copy.deepcopy(KIT)
        bad["portal_8"]["opening"]["width"] = 4.0
        e, _ = M.check(bad)
        self.assertTrue(any("R6 rig" in x for x in e), e)
        bad = copy.deepcopy(KIT)
        p = bad["cobble_4"]["parts"][0]
        p["uvs"] = [(u, v - 0.2) for u, v in p["uvs"]]
        e, _ = M.check(bad)
        self.assertTrue(any("leave its strip" in x for x in e), e)

    def test_obj_and_registry_are_written(self):
        import tempfile

        d = tempfile.mkdtemp()
        path = M.write(KIT, d)
        reg = json.load(open(path))
        self.assertEqual(len(reg["modules"]), 18)
        objs = [f for f in os.listdir(d) if f.endswith(".obj")]
        self.assertEqual(len(objs), sum(len(m["parts"]) for m in KIT.values()))


class Grammar(unittest.TestCase):
    def test_the_court_s_nine_houses_hold_every_rule(self):
        if not os.path.isfile(os.path.join(ROOT, "assets", "worlds", "GothicCourtyard.json")):
            self.skipTest("the author's assets/worlds/GothicCourtyard.json is not shipped with the kit")
        houses = court_houses()
        self.assertEqual(len(houses), 9)
        used = set()
        for b in houses:
            pl, f = G.house(b["size"][0], b["size"][1], b["floors"], b["door"]["side"], seed=len(b["name"]) * 7 + ord(b["name"][-1]))
            self.assertEqual(G.check(pl, f, b["floors"], KIT), [], b["name"])
            used |= {p["module"] for p in pl}
            # one doorway, on its door side, on the ground
            doors = [p for p in pl if p["module"] == "portal_8"]
            self.assertEqual(len(doors), 1)
            self.assertEqual(doors[0]["facade"], b["door"]["side"])
            self.assertEqual(doors[0]["pos"][1], 0.0)
            # windows on every facade
            for side in "NESW":
                self.assertIn("window", f[side]["columns"] + (["window"] if f[side]["door"] is not None else []))
        self.assertGreaterEqual(len(used), 14)
        self.assertTrue(used <= set(KIT))

    def test_a_22_stud_facade_is_five_bays_stretched_never_squeezed(self):
        self.assertEqual(G.bays_of(22), (5, 4.4))
        self.assertEqual(G.bays_of(24), (6, 4.0))
        self.assertEqual(G.bays_of(20), (5, 4.0))

    def test_the_check_refuses_broken_houses(self):
        pl, f = G.house(24, 22, 4, "S", seed=3)
        self.assertEqual(G.check(pl, f, 4, KIT), [])
        # a bay left empty
        gone = [p for p in pl if not (p["facade"] == "E" and p["module"] in ("wall_4", "wall_8") and p["role"][2] == 2)]
        self.assertTrue(any("covered 0 times" in e for e in G.check(gone, f, 4, KIT)))
        # the doorway carried up a storey
        up = copy.deepcopy(pl)
        for p in up:
            if p["module"] == "portal_8":
                p["role"] = ("door", p["role"][1], 1)
        self.assertTrue(any("doorway on storey 2" in e for e in G.check(up, f, 4, KIT)))
        # a window column broken: one window turned to wall on storey 3
        broken = copy.deepcopy(pl)
        for p in broken:
            if p["module"] == "lancet_4" and p["role"][2] == 2:
                p["module"] = "wall_4"
                p["role"] = ("wall", p["role"][1], 2)
                break
        self.assertTrue(any("keep its column" in e for e in G.check(broken, f, 4, KIT)))
        # a module squeezed past the bar
        sq = copy.deepcopy(pl)
        sq[0]["scale"] = [0.7, 1, 1]
        self.assertTrue(any("px/stud" in e or "stretched" in e for e in G.check(sq, f, 4, KIT)))

    def test_no_two_single_windows_side_by_side(self):
        for n in range(3, 12):
            col = G.columns(n, None, seed=n)
            for a, b in zip(col, col[1:]):
                self.assertFalse(a == "window" and b == "window", col)
            self.assertEqual(col[0], "wall")
            self.assertEqual(col[-1], "wall")


if __name__ == "__main__":
    unittest.main()
