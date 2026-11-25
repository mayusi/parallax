"""The seam check read along seam LINES, through cut-outs and on the normal map (card 7cka; rbx_seams.measure): a
dense mesh's seam is many edges under 3 texels each - judged one by one each was skipped (a sculpted ball's 1,228
seam edges: none judged); now they are chained end to end and read in windows along the line. A cut-out texel on
either side is not read. A normal map is compared by WORLD direction (each side's tangent frame), so an island
turned in the map is not a step."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_seams as S  # noqa: E402

N = 64


def strip_seams(k=40, step_px=1.5, left=(0.1, 0.5), right=(0.6, 0.5), du=0.0):
    """k short seam edges end to end (each step_px texels long) - a seam line in two places of an N x N map: on the
    left island at x = left, on the right island at x = right, the third corners inside each island"""
    a, b, verts = [], [], []
    for i in range(k):
        y0, y1 = (i * step_px + 4) / N, ((i + 1) * step_px + 4) / N
        a.append([[left[0], y0], [left[0], y1], [left[0] - 0.05, y0]])
        b.append([[right[0], y0], [right[0], y1], [right[0] + 0.05, y0]])
        verts.append([i, i + 1])
    return {"a": np.array(a), "b": np.array(b), "verts": np.array(verts), "tris": np.zeros((k, 2), int), "crowded": 0}


def two_tone(lval, rval):
    img = np.zeros((N, N, 4))
    img[:, : N // 2, :3] = lval
    img[:, N // 2:, :3] = rval
    img[..., 3] = 1.0
    return img


class Lines(unittest.TestCase):
    def test_short_edges_chained_into_one_line(self):
        seams = strip_seams()
        line, order = S.chains(seams["verts"])
        self.assertEqual(len(order), 1)
        self.assertTrue((line == 0).all())

    def test_a_line_of_short_edges_is_judged_and_its_step_seen(self):
        seams = strip_seams()
        m = S.measure(two_tone(0.2, 0.6), seams)
        self.assertEqual(m["edges"], 40)                    # (each edge 1.5 texels: once all skipped)
        self.assertGreater(m["share"], 0.9)
        m0 = S.measure(two_tone(0.4, 0.4), seams)
        self.assertEqual(m0["share"], 0.0)

    def test_a_line_shorter_than_three_texels_is_not_judged(self):
        m = S.measure(two_tone(0.2, 0.6), strip_seams(k=1, step_px=1.5))
        self.assertEqual(m["edges"], 0)

    def test_cut_out_texels_are_not_read(self):
        seams = strip_seams()
        alpha = np.ones((N, N))
        alpha[:, : N // 2] = 0.0                              # (the left island cut out)
        m = S.measure(two_tone(0.2, 0.6), seams, alpha=alpha)
        self.assertEqual(m["share"], 0.0)


class Thin(unittest.TestCase):
    def test_a_strip_too_thin_to_read_is_not_misread(self):
        """a narrow ring of a turned lip: its triangles reach 1.5 texels in from the seam, and just past them lies
        another ring of another tone - the deeper readings would land there (a 160-level "step" on the car rim's
        lip that was no seam). Read only inside their own triangle, nothing is judged there"""
        k = 40
        a, b, verts = [], [], []
        for i in range(k):
            y0, y1 = (i * 1.5 + 4) / N, ((i + 1) * 1.5 + 4) / N
            a.append([[0.40, y0], [0.40, y1], [0.40 - 1.5 / N, y0]])     # (its third corner 1.5 texels in)
            b.append([[0.60, y0], [0.60, y1], [0.60 + 1.5 / N, y0]])
            verts.append([i, i + 1])
        seams = {"a": np.array(a), "b": np.array(b), "verts": np.array(verts), "tris": np.zeros((k, 2), int),
                 "crowded": 0}
        img = np.full((N, N, 4), 0.5)
        img[:, :int(0.40 * N) - 2, :3] = 0.05                             # (the next ring, past the strip: dark)
        img[..., 3] = 1.0
        m = S.measure(img, seams)
        self.assertEqual(m["share"], 0.0)


class Normals(unittest.TestCase):
    def test_an_island_turned_in_the_map_is_not_a_step(self):
        """the same world normal (tilted toward +x) encoded in two tangent frames: the left island's tangent is +x,
        the right island's is -x (turned 180 degrees in the map) - the raw colours differ, the world does not"""
        seams = strip_seams()
        tilt = np.array([0.3, 0.0, 0.954])
        img = np.zeros((N, N, 4))
        img[:, : N // 2, :3] = tilt * 0.5 + 0.5
        img[:, N // 2:, :3] = tilt * np.array([-1, 1, 1]) * 0.5 + 0.5   # (encoded in the turned frame)
        frames = {"a": (np.array([1.0, 0, 0]), np.array([0, 1.0, 0])), "b": (np.array([-1.0, 0, 0]), np.array([0, 1.0, 0]))}

        def world(values, side, edges, _t):
            t, b = frames[side]
            v = values * 2 - 1
            out = v[:, :1] * t + v[:, 1:2] * b + v[:, 2:3] * np.array([0, 0, 1.0])
            return out / np.linalg.norm(out, axis=1, keepdims=True)
        raw = S.measure(img, seams, seen=S.SEEN_NORMAL)
        turned = S.measure(img, seams, seen=S.SEEN_NORMAL, to_world=world)
        self.assertGreater(raw["share"], 0.9)                # (read raw: a step at every window)
        self.assertEqual(turned["share"], 0.0)               # (read by world direction: none)


if __name__ == "__main__":
    unittest.main()
