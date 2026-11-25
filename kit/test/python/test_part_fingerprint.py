"""A part family's review fingerprint must not flip on float noise: a boolean re-run moves a volume by ~1e-7, and a
number sitting on a 4-digit rounding edge flipped the hash — the Gjallarhorn's unchanged feathers went back to TODO
every other build (2026-10-06). rbx_inspect accepts the answered fingerprint when it is one of the variants the
numbers can round to within 1e-5 of an edge; a real reshape is never one of them."""

import ast
import os
import types
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender", "rbx_inspect.py")
_fns = [n for n in ast.parse(open(SRC, encoding="utf-8").read()).body
        if isinstance(n, ast.FunctionDef) and n.name in ("_edge_options", "_sig_variants")]
_ns = {}
# (rbx_inspect imports bpy: lift the two pure functions out — run their definitions as a function body in _ns)
types.FunctionType(compile(ast.Module(_fns, []), "fingerprint", "exec"), _ns)()
sig_variants = _ns["_sig_variants"]

LO, HI, MATS = [0.1, -0.2, 0.3], [0.4, 0.5, 0.6], "bronze"


def own(vol, area=0.5, lo=LO, hi=HI):
    """what rbx_inspect._fingerprint writes for one object (the same formatting)"""
    return f"Feather|{[round(v, 3) for v in lo]}|{[round(v, 3) for v in hi]}|{MATS}|{vol:.4g}|{area:.4g}"


class TestFingerprintNoise(unittest.TestCase):
    def test_the_first_variant_is_the_objects_own_signature(self):
        self.assertEqual(sig_variants("Feather", LO, HI, MATS, 0.2222, 0.5)[0], own(0.2222))

    def test_a_volume_on_a_rounding_edge_matches_from_either_side(self):
        below, above = 0.12345 - 3e-9, 0.12345 + 3e-9
        self.assertNotEqual(own(below), own(above))  # the flip that sent unchanged parts back to TODO
        self.assertIn(own(above), sig_variants("Feather", LO, HI, MATS, below, 0.5))
        self.assertIn(own(below), sig_variants("Feather", LO, HI, MATS, above, 0.5))

    def test_a_box_corner_on_a_rounding_edge_matches_too(self):
        lo_a, lo_b = [0.0125 - 3e-9, -0.2, 0.3], [0.0125 + 3e-9, -0.2, 0.3]
        self.assertNotEqual(own(0.2222, lo=lo_a), own(0.2222, lo=lo_b))
        self.assertIn(own(0.2222, lo=lo_b), sig_variants("Feather", lo_a, HI, MATS, 0.2222, 0.5))

    def test_a_real_reshape_is_never_a_variant(self):
        # a chamfer or a hole moves the volume by far more than noise: 0.1234 -> 0.1240
        self.assertNotIn(own(0.1240), sig_variants("Feather", LO, HI, MATS, 0.1234, 0.5))
        # a moved part: its box by a millimetre (0.0036 studs at 280 mm a stud)
        moved = [0.1036, -0.2, 0.3]
        self.assertNotIn(own(0.1234, lo=moved), sig_variants("Feather", LO, HI, MATS, 0.1234, 0.5))

    def test_a_number_far_from_an_edge_has_one_signature(self):
        self.assertEqual(len(sig_variants("Feather", LO, HI, MATS, 0.12341, 0.51234)), 1)


if __name__ == "__main__":
    unittest.main()
