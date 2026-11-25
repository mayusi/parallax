"""rbx_sculpt_parts — teeth by their TYPE, not beads (two fresh judges called a skull's ellipsoid teeth "a string of
pearls"): an incisor is a chisel as wide as its type, a canine a cone that narrows to its tip, a molar's biting face
rises in cusps, and an arch's biting ends meet at the occlusal height (plain numpy over rbx_sculpt fields)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_sculpt as S  # noqa: E402
import rbx_sculpt_parts as SP  # noqa: E402


def top_y(node, x, z, lo=-40.0, hi=40.0, step=0.05):
    """the highest y where a vertical line through (x, z) is inside the field (or None)"""
    ys = np.arange(lo, hi, step)
    p = np.stack([np.full_like(ys, x), ys, np.full_like(ys, z)], axis=1)
    inside = np.nonzero(node.d(p) < 0)[0]
    return float(ys[inside[-1]]) if len(inside) else None


class Crowns(unittest.TestCase):
    def test_an_incisor_is_a_chisel_its_types_width(self):
        t = SP.crown("incisor", (0, 0, 0), yaw=0.0, down=-1)   # (yaw 0: its width along x)
        w, h, d = SP.CROWN["incisor"]
        self.assertAlmostEqual(SP.width_along(t, (0, 0, 0), (1, 0, 0)), w, delta=w * 0.15)
        self.assertLess(SP.width_along(t, (0, -2, 0), (0, 0, 1)), w)   # (thin front to back: a chisel)

    def test_a_canine_narrows_to_its_tip(self):
        t = SP.crown("canine", (0, 0, 0), yaw=0.0, down=-1)   # (an upper canine: its tip toward -y)
        _w, h, _d = SP.CROWN["canine"]
        near_tip = SP.width_along(t, (0, -h * 0.35, 0), (1, 0, 0))
        at_base = SP.width_along(t, (0, h * 0.1, 0), (1, 0, 0))
        self.assertLess(near_tip, at_base * 0.6)

    def test_a_molars_biting_face_rises_in_cusps(self):
        t = SP.crown("molar", (0, 0, 0), yaw=0.0, down=1)   # (a lower molar: its biting face toward +y)
        w, _h, d = SP.CROWN["molar"]
        cusp = top_y(t, w * 0.24, d * 0.24)
        middle = top_y(t, 0.0, 0.0)
        self.assertGreater(cusp, middle + 0.5)

    def test_the_arch_bites_at_the_occlusal_height(self):
        up = SP.dental_arch(SP.ADULT_UPPER, y_occlusal=59.0, upper=True)
        lo = SP.dental_arch(SP.ADULT_LOWER, y_occlusal=59.0, upper=False)
        x, _y, z = SP.ADULT_UPPER[0][1], 0, SP.ADULT_UPPER[0][2]
        # (the upper incisor's lowest point and the lower incisor's highest near the occlusal plane)
        ys = np.arange(40, 80, 0.05)
        p = np.stack([np.full_like(ys, x), ys, np.full_like(ys, z)], axis=1)
        low_up = ys[np.nonzero(up.d(p) < 0)[0][0]]
        self.assertAlmostEqual(float(low_up), 59.0, delta=1.5)
        lx, lz = SP.ADULT_LOWER[0][1], SP.ADULT_LOWER[0][2]
        self.assertAlmostEqual(top_y(lo, lx, lz, 30, 80), 59.0, delta=1.5)


class Contacts(unittest.TestCase):
    def test_a_negative_gap_fills_the_slot_between_neighbours(self):
        # between the central and lateral incisors, just inside the arch at mid-crown: a dark slot apart, bone-white
        # filled when they are filleted together
        x, z = (SP.ADULT_UPPER[0][1] + SP.ADULT_UPPER[1][1]) / 2, (SP.ADULT_UPPER[0][2] + SP.ADULT_UPPER[1][2]) / 2
        apart = SP.dental_arch(SP.ADULT_UPPER, y_occlusal=59.0, upper=True)
        touch = SP.dental_arch(SP.ADULT_UPPER, y_occlusal=59.0, upper=True, gap=-1.0)
        p = np.array([[x, 64.0, z + 1.5]])                    # (the slot just behind their contact)
        self.assertLess(float(touch.d(p)[0]), float(apart.d(p)[0]) - 0.1)
        far = np.array([[x, 64.0, z + 6.0]])                   # (well behind the teeth: untouched)
        self.assertAlmostEqual(float(touch.d(far)[0]), float(apart.d(far)[0]), delta=0.05)


class FaceParts(unittest.TestCase):
    def test_an_orbit_opens_its_size_and_sinks_deep(self):
        s = S.Canvas(voxel=0.5).box((0, 120, -60), (120, 80, 60))   # (a face block, its front at z -90)
        SP.orbit(s, (30, 124, -90), width=40, height=34, depth=45)
        inside = lambda x, y, z: float(s.d(np.array([[x, y, z]]))[0]) < 0  # noqa: E731
        self.assertFalse(inside(30, 124, -85))                       # (the opening)
        self.assertFalse(inside(30 + 17, 124, -86))                 # (near its outer edge: still open)
        self.assertTrue(inside(30 + 24, 124, -86))                  # (past its width: the rim)
        self.assertFalse(inside(30, 124, -65))                      # (deep: 25 mm in, still the socket)
        self.assertEqual(s.brushes[-1]["kind"], "pinch")            # (its upper rim pinched crisp)

    def test_a_nasal_aperture_is_deep_with_its_septum_inside(self):
        s = S.Canvas(voxel=0.5).box((0, 95, -60), (80, 60, 60))     # (front at -90)
        SP.nasal_aperture(s, floor_y=81, top_y=104, width=25, front_z=-90)
        inside = lambda x, y, z: float(s.d(np.array([[x, y, z]]))[0]) < 0  # noqa: E731
        self.assertFalse(inside(8, 90, -80))                        # (the opening, beside the septum)
        self.assertFalse(inside(8, 90, -65))                        # (deep: no 10 mm dish)
        self.assertTrue(inside(0, 92, -80))                         # (the septum, recessed inside)
        self.assertFalse(inside(0, 92, -88))                        # (...but not up to the rim)

    def test_a_mandible_forks_with_its_notch(self):
        s = S.Canvas(voxel=0.5, mirror="x").ball((0, 150, 0), 10)   # (a seed of clay elsewhere; mirrored, as used)
        SP.mandible(s, chin=(0, 8, -83), gonion=(50, 37, -5), condyle=(50, 95, -1), coronoid=(45, 88, -21))
        inside = lambda x, y, z: float(s.d(np.array([[x, y, z]]))[0]) < 0  # noqa: E731
        self.assertTrue(inside(50, 92, -1))                         # (the condyle)
        self.assertTrue(inside(45, 86, -20))                        # (the coronoid)
        self.assertFalse(inside(48, 86, -11))                       # (the notch between them)
        self.assertTrue(inside(0, 15, -80))                         # (the chin's body)


if __name__ == "__main__":
    unittest.main()
