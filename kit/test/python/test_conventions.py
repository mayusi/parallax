"""The conventions a model is held to on its way into the engine (kit/blender/rbx_conventions.py; the owner's method
lists: naming conventions, pivot placement, normal map convention, import settings): names, the origin, the normal
map's convention, the exported file read back."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_conventions as C  # noqa: E402


class Names(unittest.TestCase):
    def test_a_name_the_game_can_index_passes(self):
        for name in ("main", "glass", "wheel_2", "a", "x" * 32):
            self.assertIsNone(C.name_problem("group", name), name)

    def test_capitals_spaces_a_leading_digit_and_a_long_name_are_named(self):
        self.assertIn("no capitals", C.name_problem("group", "Main Body"))
        self.assertIn("no capitals", C.name_problem("material", "dark-steel"))
        self.assertIn("starts with a letter", C.name_problem("group", "2nd"))
        self.assertIn("no capitals", C.name_problem("group", "Main"))
        self.assertIn("starts with a letter", C.name_problem("group", "_main"))

    def test_the_kits_own_r6_outfit_groups_are_the_convention(self):
        for name in ("Torso", "LeftArm", "RightArm", "LeftLeg", "RightLeg", "Head"):
            self.assertIsNone(C.name_problem("group", name), name)       # (Models.wear looks them up by name)
        self.assertIsNotNone(C.name_problem("material", "Torso"))        # a material is no limb
        self.assertIsNotNone(C.name_problem("group", "Leftarm"))
        self.assertIn("32 characters", C.name_problem("material", "x" * 33))
        self.assertIn('material "x', C.name_problem("material", "x" * 33))


class Pivot(unittest.TestCase):
    def test_an_origin_on_or_in_the_model_passes(self):
        self.assertIsNone(C.pivot_problem((-1, 0, -2), (1, 3, 2)))          # standing on the origin
        self.assertIsNone(C.pivot_problem((-1, -1, -1), (1, 1, 1)))         # round it
        self.assertIsNone(C.pivot_problem((0.2, 0, 0), (4, 1, 1)))          # a hair outside: within a tenth
        # the bar itself: a box 3 x 4 x 0 (diagonal 5) lets the origin lie half a stud out, no further
        self.assertIsNone(C.pivot_problem((0.49, 0, 0), (3.49, 4, 0)))
        self.assertIsNotNone(C.pivot_problem((0.51, 0, 0), (3.51, 4, 0)))

    def test_a_model_built_away_from_the_origin_says_how_far(self):
        said = C.pivot_problem((10, 0, 0), (12, 1, 1))
        self.assertIn("10.00 studs outside", said)
        self.assertIn("(10, 0, 0) to (12, 1, 1)", said)


class Normal(unittest.TestCase):
    def test_a_tangent_map_is_mostly_blue_where_it_is_not_flat(self):
        self.assertIsNone(C.normal_problem((0.5, 0.5, 0.98)))
        self.assertIsNone(C.normal_problem((0.47, 0.53, 0.85)))
        self.assertIsNone(C.normal_problem((0.40, 0.51, 0.9)))             # leaning: a real one-sided bevel

    def test_an_object_space_map_or_swapped_channels_are_named(self):
        self.assertIn("mean blue is 0.50", C.normal_problem((0.5, 0.5, 0.5)))
        self.assertIn("mean blue is 0.50", C.normal_problem((0.98, 0.5, 0.5)))   # red and blue swapped
        self.assertIsNone(C.normal_problem((0.5, 0.5, 0.71)))              # the bar
        self.assertIsNotNone(C.normal_problem((0.5, 0.5, 0.69)))

    def test_a_map_that_is_all_flat_fill_has_nothing_to_judge(self):
        self.assertIsNone(C.normal_problem((0.9, 0.1, 0.2), judged=0.005))
        self.assertIsNotNone(C.normal_problem((0.9, 0.1, 0.2), judged=0.02))
        self.assertIn("over the 2% of it", C.normal_problem((0.9, 0.1, 0.2), judged=0.02))


def _map_of(height, green=1.0):
    """an OpenGL normal map (rows with v) of a height field; green=-1: the DirectX map of it"""
    import numpy as np  # noqa: PLC0415

    dv, du = np.gradient(height)
    n = np.stack([-du, -dv * green, np.ones_like(height)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.round((n * 0.5 + 0.5) * 255) / 255   # (8 bits, as a PNG keeps it)


class Green(unittest.TestCase):
    """which way the green points, read from the map's own slopes (they add up round a loop only the right way)"""

    @classmethod
    def setUpClass(cls):
        import numpy as np  # noqa: PLC0415

        y, x = np.mgrid[0:128, 0:128] / 127.0
        # rivets and a slanted ridge: relief that is not lined up with the map's axes
        h = sum(np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / 0.004) for cx, cy in ((0.3, 0.3), (0.7, 0.4), (0.5, 0.75)))
        cls.relief = 6.0 * (h + 0.5 * np.exp(-((x + y - 1.0) ** 2) / 0.01))
        # straight bevels along u and along v only: they show no way at all
        cls.bevels = 6.0 * (np.clip((x - 0.4) * 8, 0, 1) + np.clip((y - 0.6) * 8, 0, 1))

    def test_an_opengl_map_reads_opengl(self):
        r = C.green_reading(_map_of(self.relief))
        self.assertEqual(r["reads"], "opengl", r)
        self.assertIsNone(C.green_problem(_map_of(self.relief)))

    def test_a_directx_map_is_named(self):
        r = C.green_reading(_map_of(self.relief, green=-1.0))
        self.assertEqual(r["reads"], "directx", r)
        self.assertIn("DirectX", C.green_problem(_map_of(self.relief, green=-1.0)))

    def test_straight_bevels_claim_nothing_either_way(self):
        for g in (1.0, -1.0):
            r = C.green_reading(_map_of(self.bevels, green=g))
            self.assertIsNone(r["reads"], r)
            self.assertIsNone(C.green_problem(_map_of(self.bevels, green=g)))

    def test_a_flat_map_has_nothing_to_judge(self):
        import numpy as np  # noqa: PLC0415

        flat = np.zeros((64, 64, 3)) + (0.5, 0.5, 1.0)
        self.assertIsNone(C.green_reading(flat)["reads"])


class RoundTrip(unittest.TestCase):
    MEANT = {"tris": 12, "size": (2.0, 1.0, 4.0), "centre": (0.0, 0.5, 0.0)}

    def test_the_same_mesh_read_back_passes(self):
        read = {"tris": 12, "size": (2.0005, 1.0, 3.9995), "centre": (0.0, 0.5003, 0.0)}
        self.assertIsNone(C.roundtrip_problem(self.MEANT, read))

    def test_a_hundred_times_too_large_is_the_unit_scale(self):
        read = {"tris": 12, "size": (200.0, 100.0, 400.0), "centre": (0.0, 50.0, 0.0)}
        self.assertIn("100x the size", C.roundtrip_problem(self.MEANT, read))

    def test_lying_on_its_side_is_the_axes(self):
        read = {"tris": 12, "size": (2.0, 4.0, 1.0), "centre": (0.0, 0.5, 0.0)}
        self.assertIn("read back turned", C.roundtrip_problem(self.MEANT, read))

    def test_moved_or_mirrored_and_a_lost_triangle(self):
        read = {"tris": 12, "size": (2.0, 1.0, 4.0), "centre": (0.0, -0.5, 0.0)}
        self.assertIn("moved or mirrored", C.roundtrip_problem(self.MEANT, read))
        read = {"tris": 10, "size": (2.0, 1.0, 4.0), "centre": (0.0, 0.5, 0.0)}
        self.assertEqual(C.roundtrip_problem(self.MEANT, read), "10 triangles read back, 12 exported")

    def test_the_size_bar_is_two_thousandths_of_the_diagonal(self):
        d = (2 ** 2 + 1 ** 2 + 4 ** 2) ** 0.5                              # 4.58 studs: the bar is 0.0092
        near = {"tris": 12, "size": (2.008, 1.0, 4.0), "centre": (0.0, 0.5, 0.0)}
        far = {"tris": 12, "size": (2.011, 1.0, 4.0), "centre": (0.0, 0.5, 0.0)}
        self.assertIsNone(C.roundtrip_problem(self.MEANT, near))
        self.assertIn("1.0055x the size", C.roundtrip_problem(self.MEANT, far))
        self.assertLess(0.008, 0.002 * d)

    def test_a_half_turn_in_the_same_box_and_a_mesh_inside_out_are_seen(self):
        same = dict(self.MEANT)
        self.assertIsNone(C.roundtrip_problem(self.MEANT, same, far=0.001))
        self.assertIn("turned half round or mirrored", C.roundtrip_problem(self.MEANT, same, far=1.4))
        self.assertIn("inside out", C.roundtrip_problem(self.MEANT, same, far=0.0, inside_out=True))


if __name__ == "__main__":
    unittest.main()
