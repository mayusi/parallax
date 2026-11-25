"""rbx_refmesh — a reference model read as NUMBERS (plain numpy): a GLB with its node transforms, welded seams, the
pieces of a slice (a holey scan's open chains included), its exact outline, and landmarks found by rules."""

import json
import os
import struct
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_refmesh as R  # noqa: E402


def box_mesh(lo, hi):
    """a closed box's 8 corners and 12 triangles"""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=float)
    q = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    t = [[a, b, c] for a, b, c, d in q] + [[a, c, d] for a, b, c, d in q]
    return v, np.array(t)


def two_boxes():
    """two separate blocks side by side (a slice through them: two pieces)"""
    v1, t1 = box_mesh((-30, 0, -10), (-10, 40, 10))
    v2, t2 = box_mesh((10, 0, -10), (30, 20, 10))
    return R.Ref(np.concatenate([v1, v2]), np.concatenate([t1, t2 + len(v1)]))


def write_glb(path, verts, tris, node):
    vb = np.asarray(verts, dtype=np.float32).tobytes()
    ib = np.asarray(tris, dtype=np.uint32).tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [dict(node, mesh=0)],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "buffers": [{"byteLength": len(vb) + len(ib)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(vb)},
                           {"buffer": 0, "byteOffset": len(vb), "byteLength": len(ib)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(verts), "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5125, "count": int(np.size(tris)), "type": "SCALAR"}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    bin_ = vb + ib
    with open(path, "wb") as fh:
        fh.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(bin_)))
        fh.write(struct.pack("<I", len(js)) + b"JSON" + js)
        fh.write(struct.pack("<I", len(bin_)) + b"BIN\x00" + bin_)


class Read(unittest.TestCase):
    def test_a_glbs_node_transform_is_applied_and_placed(self):
        v, t = box_mesh((0, 0, 0), (2, 1, 4))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "box.glb")
            write_glb(p, v, t, {"scale": [10, 10, 10]})            # (a node scale, as Sketchfab exports carry)
            gv, gt = R.glb_mesh(p)
            self.assertAlmostEqual(float(gv[:, 2].max()), 40.0, places=4)
            ref = R.load(p, height=100)                            # (100 mm tall, base on y 0, centred)
        self.assertTrue(np.allclose(ref.hi - ref.lo, [200, 100, 400], atol=1e-6))
        self.assertAlmostEqual(float(ref.lo[1]), 0.0)
        self.assertAlmostEqual(float(ref.lo[0] + ref.hi[0]), 0.0)

    def test_seams_are_welded(self):
        v, t = box_mesh((0, 0, 0), (1, 1, 1))
        v2 = np.concatenate([v, v + 1e-5])                         # (every vertex split, as along texture seams)
        t2 = np.concatenate([t[:6], t[6:] + 8])
        wv, wt = R.weld(v2, t2)
        self.assertEqual(len(wv), 8)
        self.assertEqual(len(wt), 12)


class Slices(unittest.TestCase):
    def test_every_piece_of_a_slice(self):
        ref = two_boxes()
        low = R.slice_pieces(ref, 10)
        self.assertEqual(len(low), 2)                               # (both blocks)
        self.assertAlmostEqual(low[0]["width"], 20.0, delta=1.0)
        self.assertAlmostEqual(low[0]["depth"], 20.0, delta=1.0)
        self.assertEqual(sorted(round(p["centre"][0]) for p in low), [-20, 20])
        self.assertEqual(len(R.slice_pieces(ref, 30)), 1)           # (above the short one: one piece)

    def test_a_holey_shell_still_slices_into_its_solid(self):
        # four 2 mm walls with 1 mm gaps at the corners: a shell full of small holes, as a scan is
        walls = [((-20, 0, -20), (19, 40, -18)), ((20, 0, -20), (18, 40, 19)), ((-19, 0, 20), (20, 40, 18)),
                 ((-20, 0, -19), (-18, 40, 20))]
        parts = [box_mesh(np.minimum(a, b), np.maximum(a, b)) for a, b in walls]
        v = np.concatenate([p_[0] for p_ in parts])
        t = np.concatenate([p_[1] + 8 * i for i, p_ in enumerate(parts)])
        p = R.slice_pieces(R.Ref(v, t), 20)
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(p[0]["area"], 1600.0, delta=160.0)


class Outline(unittest.TestCase):
    def test_the_exact_side_outline(self):
        o = R.outline(two_boxes(), "side", res=0.5)
        self.assertAlmostEqual(o["mask"].sum() * 0.25, 20 * 40, delta=40)   # (seen from the side: the tall block)


class Sculpting(unittest.TestCase):
    """the reference's numbers INTO a sculpt: a loft through its sections, a trim to its exact outline"""

    def test_a_loft_through_measured_sections(self):
        import rbx_sculpt as S

        def square(half, res=0.5):
            n = int(60 / res)
            g = (np.arange(n) * res) - 30
            X, Z = np.meshgrid(g, g, indexing="ij")
            return (np.abs(X) <= half) & (np.abs(Z) <= half), (-30.0, -30.0), res

        m0, lo0, r0 = square(10)
        m1, lo1, r1 = square(5)
        c = S.Canvas(voxel=0.5).loft_slices([(0.0, m0, lo0, r0), (40.0, m1, lo1, r1)])
        x = np.arange(0, 20, 0.05)
        mid = c.d(np.stack([x, np.full_like(x, 20.0), np.zeros_like(x)], axis=1))
        half = float(x[np.nonzero(mid < 0)[0][-1]])
        self.assertAlmostEqual(half, 7.5, delta=0.7)                 # (half way between 10 and 5)
        self.assertGreater(float(c.d(np.array([[0.0, 45.0, 0.0]]))[0]), 4.0)   # (capped above the top section)

    def test_a_raster_outline_has_no_staircase(self):
        import rbx_sculpt as S

        res = 0.5
        g = np.arange(-30, 30, res)
        X, Y = np.meshgrid(g, g, indexing="ij")
        mask = np.hypot(X, Y) <= 20.0

        def radii(v):
            sil = S.Silhouette.__new__(S.Silhouette)
            sil.plane, sil.res, sil.lo2 = "front", res, np.array([-30.0, -30.0])
            sil.v = v
            sil.hi2 = sil.lo2 + (np.array(v.shape) - 1) * res
            out = []
            for a in np.linspace(0, 2 * np.pi, 360, endpoint=False):
                r = np.linspace(15, 25, 2001)
                p = np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(r)], axis=1)
                d = sil.d(p)
                out.append(r[np.nonzero(d > 0)[0][0]])
            return np.array(out)

        stepped = radii(S.sdf_from_mask(mask, res))
        smooth = radii(S.smooth_grid(S.sdf_from_mask(mask, res), passes=4))
        rough = lambda r: float(np.abs(np.diff(r)).mean())  # noqa: E731   (how much the edge jumps angle to angle)
        self.assertLess(rough(smooth), rough(stepped) * 0.6)
        self.assertAlmostEqual(float(np.median(smooth)), 20.0, delta=0.4)   # (and still where it was)

    def test_trimmed_to_the_exact_outline_of_the_mesh(self):
        import rbx_sculpt as S

        ref = two_boxes()
        sil = R.outline(ref, "front", res=0.5)          # (front: x across, y up — both blocks, 40 and 20 tall)
        c = S.Canvas(voxel=0.5).box((0, 20, 0), (80, 60, 10)).trim_to(sil, "front")
        self.assertLess(float(c.d(np.array([[-20.0, 35.0, 0.0]]))[0]), 0)   # (inside the tall block's outline)
        self.assertGreater(float(c.d(np.array([[20.0, 30.0, 0.0]]))[0]), 0)  # (above the short block: trimmed)
        self.assertGreater(float(c.d(np.array([[0.0, 10.0, 0.0]]))[0]), 0)   # (between them: trimmed)


class OutlineHoles(unittest.TestCase):
    def test_a_scans_holes_are_closed_a_real_opening_is_kept(self):
        # a plate 60 x 60 seen from the front with a 4 x 4 mm hole (a scan's) and a 30 x 30 mm window (a real opening)
        def quad(x0, y0, x1, y1):
            v = np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], dtype=float)
            return v, np.array([[0, 1, 2], [0, 2, 3]])
        parts = [quad(-30, 0, -20, 60), quad(20, 0, 30, 60), quad(-20, 0, 20, 10), quad(-20, 50, 20, 60),
                 quad(-20, 10, -15, 50), quad(15, 10, 20, 50), quad(-15, 10, 15, 15), quad(-15, 45, 15, 50),
                 quad(-15, 15, -2, 45), quad(2, 15, 15, 45), quad(-2, 15, 2, 20), quad(-2, 24, 2, 45)]
        v = np.concatenate([p_[0] for p_ in parts])
        t = np.concatenate([p_[1] + 4 * i for i, p_ in enumerate(parts)])
        o = R.outline(R.Ref(v, t), "front", res=0.5)
        m, lo = o["mask"], np.array(o["lo"])
        at = lambda x, y: bool(m[int((x - lo[0]) / 0.5), int((y - lo[1]) / 0.5)])  # noqa: E731
        self.assertTrue(at(0, 22))      # (the 4 x 4 mm scan hole: closed)
        self.assertTrue(at(-25, 30))    # (the plate)
        big = R.outline(R.Ref(v[: 4 * 8], t[: 2 * 8]), "front", res=0.5)   # (the frame alone: a 30 x 30 window)
        mb, lob = big["mask"], np.array(big["lo"])
        self.assertFalse(bool(mb[int((0 - lob[0]) / 0.5), int((30 - lob[1]) / 0.5)]))   # (a real opening: kept)


class Landmarks(unittest.TestCase):
    def test_landmarks_by_rule(self):
        # a profile: a chin forward low, a recess (a nasion) in the middle, a brow forward above
        v1, t1 = box_mesh((-5, 0, -30), (5, 20, 0))      # chin: front at z -30
        v2, t2 = box_mesh((-5, 20, -20), (5, 40, 0))     # recess: front at -20
        v3, t3 = box_mesh((-5, 40, -28), (5, 60, 0))     # brow: front at -28
        ref = R.Ref(np.concatenate([v1, v2, v3]), np.concatenate([t1, t2 + 8, t3 + 16]))
        L = R.landmarks(ref, {"chin": ("front_max", 0, 20), "nasion": ("front_min", 15, 45),
                              "top": ("top", 0, 60), "wide": ("side_max", 0, 60)})
        self.assertAlmostEqual(L["chin"][2], -30.0, delta=0.5)
        self.assertAlmostEqual(L["nasion"][2], -20.0, delta=0.5)
        self.assertTrue(20 <= L["nasion"][1] <= 40)
        self.assertAlmostEqual(L["top"][1], 60.0)
        self.assertAlmostEqual(L["wide"][0], 5.0)
        with self.assertRaises(ValueError):
            R.landmarks(ref, {"x": ("guess", 0, 1)})


if __name__ == "__main__":
    unittest.main()
