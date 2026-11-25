"""Unit tests of the node graph in kit vfx comp (kit/vfx/comp.py "graph"): each node does what its name says, a graph
that is broken is said so in words, and a node that does nothing is refused.
Run: python -m pytest kit/test/python/test_vfx_graph.py -q"""
import copy
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import comp as C  # noqa: E402
import methods as M  # noqa: E402

DISC = {"op": "shape", "sdf": "disc", "radius": 0.2, "soft": 0.0}
RING = {"op": "shape", "sdf": "ring", "radius": 0.35, "width": 0.05, "soft": 0.0}
NOISE = {"op": "noise", "scale": 4, "octaves": 2, "pan": [1, 0], "seed": 3, "contrast": 1.5}


def spec(nodes, value, alpha=None, frames=4, grid=2, cell=64, **comp):
    g = {"nodes": nodes, "value": value}
    if alpha:
        g["alpha"] = alpha
    return {"engine": "fx", "recipe": "comp", "frames": frames, "grid": grid, "cell": cell, "comp": dict({"loop": True, "graph": g}, **comp), "post": dict(C.POST)}


def value_of(nodes, value, t=0.0, **kw):
    o = C.checked(spec(nodes, value, **kw))
    return C.graph_at(o, C.graph_fields(o), t)


def alone(nodes, value, name, t=0.0, **kw):
    """one node's own field, in a graph whose value is `value`"""
    o = C.checked(spec(nodes, value, **kw))
    return C._node_alone(o, C.graph_fields(o), t, name)


def said(nodes, value, alpha=None, **kw):
    try:
        C.checked(spec(nodes, value, alpha, **kw))
    except ValueError as e:
        return str(e)
    return ""


class TheNodes(unittest.TestCase):
    def test_joins_are_what_their_names_say(self):
        base = {"d": DISC, "r": RING, "n": NOISE}
        d = value_of(dict(base, out={"op": "max", "a": "d", "b": "r"}, m={"op": "mul", "a": "out", "b": "n"}), "m")
        # the three sources alone, read through a join that leaves them be
        o = C.checked(spec(dict(base, j={"op": "max", "a": "d", "b": "r"}, k={"op": "mul", "a": "j", "b": "n"}), "k"))
        f = C.graph_fields(o)
        one = lambda name: C._node_alone(o, f, 0.0, name)  # noqa: E731
        dd, rr, nn = one("d"), one("r"), one("n")
        self.assertTrue(np.allclose(one("j"), np.maximum(dd, rr)))
        self.assertTrue(np.allclose(one("k"), np.maximum(dd, rr) * nn))
        self.assertTrue(np.allclose(d[0], np.maximum(dd, rr) * nn))
        for op, want in (("add", np.clip(dd + nn, 0, 1)), ("sub", np.clip(dd - nn, 0, 1)), ("min", np.minimum(dd, nn)), ("screen", 1 - (1 - dd) * (1 - nn))):
            got = value_of({"d": DISC, "n": NOISE, "r": RING, "j": {"op": op, "a": "d", "b": "n"}, "k": {"op": "max", "a": "j", "b": "r"}}, "k")[0]
            self.assertTrue(np.allclose(got, np.maximum(want, rr)), op)

    def test_a_shape_is_inside_its_distance_and_a_noise_pans_whole_patterns(self):
        v = alone({"d": DISC, "r": RING, "n": NOISE, "j": {"op": "max", "a": "d", "b": "r"}, "k": {"op": "mul", "a": "j", "b": "n"}}, "k", "j")
        self.assertEqual(float(v[32, 32]), 1.0)                                             # the disc's middle
        self.assertEqual(float(v[32, 49]), 0.0)                                             # between the disc and the ring
        self.assertEqual(float(v[32, 54]), 1.0)                                             # on the ring (0.35 of 64 from the middle)
        nodes = {"d": DISC, "r": RING, "n": NOISE, "j": {"op": "max", "a": "d", "b": "r"}, "k": {"op": "mul", "a": "j", "b": "n"}}
        a, b, c = value_of(nodes, "k", 0.0)[0], value_of(nodes, "k", 0.5)[0], value_of(nodes, "k", 1.0)[0]
        self.assertFalse(np.allclose(a, b))
        self.assertTrue(np.allclose(a, c, atol=1e-9))                                        # one whole pattern on: the first frame again

    def test_mix_invert_levels_and_numbers(self):
        base = {"d": DISC, "r": RING, "n": NOISE}
        o = C.checked(spec(dict(base, m={"op": "mix", "a": "d", "b": "r", "by": "n"}), "m"))
        f = C.graph_fields(o)
        dd, rr, nn = (C._node_alone(o, f, 0.0, k) for k in ("d", "r", "n"))
        self.assertTrue(np.allclose(C.graph_at(o, f, 0.0)[0], dd * (1 - nn) + rr * nn))
        got = value_of(dict(base, i={"op": "invert", "of": "n"}, j={"op": "max", "a": "d", "b": "r"}, k={"op": "mul", "a": "j", "b": "i"}), "k")[0]
        self.assertTrue(np.allclose(got, np.maximum(dd, rr) * (1 - nn)))
        got = value_of(dict(base, l={"op": "levels", "of": "n", "low": 0.4, "high": 0.6, "gamma": 2.0}, j={"op": "max", "a": "d", "b": "r"},
                            k={"op": "mul", "a": "j", "b": "l"}), "k")[0]
        self.assertTrue(np.allclose(got, np.maximum(dd, rr) * np.clip((nn - 0.4) / 0.2, 0, 1) ** 2))
        got = value_of(dict(base, h={"op": "mul", "a": "n", "b": 0.5}, j={"op": "max", "a": "d", "b": "r"}, k={"op": "mul", "a": "j", "b": "h"}), "k")[0]
        self.assertTrue(np.allclose(got, np.maximum(dd, rr) * nn * 0.5))

    def test_a_warp_bends_what_it_reads_by_what_bends_it(self):
        base = {"d": DISC, "r": RING, "n": NOISE}
        plain = alone(dict(base, j={"op": "max", "a": "d", "b": "r"}, k={"op": "mul", "a": "j", "b": "n"}), "k", "j")
        for amount, least, most in ((0.02, 0.005, 0.2), (0.1, 0.03, 0.6)):
            bent = alone(dict(base, j={"op": "max", "a": "d", "b": "r"}, w={"op": "warp", "of": "j", "by": "n", "amount": amount},
                              k={"op": "mul", "a": "w", "b": "n"}), "k", "w")
            moved = float(np.abs(bent - plain).mean())
            self.assertGreater(moved, least, amount)                                         # it IS bent, more for more
            self.assertLess(moved, most, amount)
            self.assertAlmostEqual(float(bent.mean()), float(plain.mean()), delta=0.06)      # and the shape is not lost
        o = C.checked(spec(dict(base, j={"op": "max", "a": "d", "b": "r"}, w={"op": "warp", "of": "j", "by": "n", "amount": 0.1}, k={"op": "mul", "a": "w", "b": "n"}), "k"))
        o["graph"]["nodes"]["n2"] = {"op": "value", "is": 0.5}                             # (bent by a flat grey: not at all)
        o["graph"]["nodes"]["w"] = dict(o["graph"]["nodes"]["w"], by="n2")
        self.assertTrue(np.allclose(C._node_alone(o, C.graph_fields(o), 0.0, "w"), plain))

    def test_a_warp_by_a_mask_bends_where_the_mask_is_and_does_not_slide_the_picture(self):
        nodes = {"d": DISC, "r": RING, "n": NOISE, "m": dict(DISC, radius=0.08), "j": {"op": "max", "a": "d", "b": "r"},
                 "w": {"op": "warp", "of": "j", "by": "m", "amount": 0.2}, "k": {"op": "mul", "a": "w", "b": "n"}}
        plain, bent = alone(nodes, "k", "j"), alone(nodes, "k", "w")
        yy, xx = np.mgrid[0:64, 0:64]
        for f in (plain, bent):
            self.assertAlmostEqual(float((xx * f).sum() / f.sum()), 31.5, delta=1.5)        # its middle stays in the middle
            self.assertAlmostEqual(float((yy * f).sum() / f.sum()), 31.5, delta=1.5)
        self.assertGreater(float(np.abs(bent - plain).mean()), 0.003)                        # and it IS bent

    def test_warps_bent_by_warps_cost_what_their_count_says(self):
        import time

        nodes = {"d": DISC, "r": RING, "n": NOISE, "j": {"op": "max", "a": "d", "b": "r"}, "w0": {"op": "warp", "of": "n", "by": "j", "amount": 0.05}}
        for k in range(1, 12):
            nodes[f"w{k}"] = {"op": "warp", "of": "n", "by": f"w{k - 1}", "amount": 0.05}
        nodes["k"] = {"op": "mul", "a": "j", "b": "w11"}
        t0 = time.perf_counter()
        said(nodes, "k", cell=128)                                                           # (taken or refused: what it COSTS is the test)
        g = C.graph_checked(spec(nodes, "k", cell=128)["comp"]["graph"], spec(nodes, "k", cell=128), False, True)
        o = {"cell": 128, "tile": False, "graph": g}
        C.graph_at(o, C.graph_fields(o), 0.3)
        self.assertLess(time.perf_counter() - t0, 20)                                        # (twelve deep took 94 s a FRAME before)

    def test_the_alpha_can_be_another_node(self):
        nodes = {"d": DISC, "r": RING, "n": NOISE, "j": {"op": "max", "a": "d", "b": "r"}, "k": {"op": "mul", "a": "j", "b": "n"}}
        grey = [[0, [0, 0, 0]], [1, [255, 255, 255]]]
        value, alpha = value_of(nodes, "k", alpha="j", ramp=grey)
        self.assertTrue(np.allclose(alpha, alone(nodes, "k", "j")))
        frames = C.frames_of(C.checked(spec(nodes, "k", "j", ramp=[[0, [0, 0, 0]], [1, [255, 255, 255]]])))
        self.assertTrue(np.allclose(frames[0][..., 3], alpha))                               # the sheet's alpha is the node's
        self.assertTrue(np.allclose(frames[0][..., 0], value))                               # its colour the value through the ramp
        frames = C.frames_of(C.checked(spec(nodes, "k")))
        self.assertTrue(np.allclose(frames[0][..., 3], value))                               # no alpha node: the value is the alpha


class TheGraph(unittest.TestCase):
    def setUp(self):
        self.nodes = {"d": DISC, "r": RING, "n": NOISE, "j": {"op": "max", "a": "d", "b": "r"}, "k": {"op": "mul", "a": "j", "b": "n"}}

    def test_a_good_graph_is_taken(self):
        self.assertEqual(said(self.nodes, "k"), "")

    def test_what_is_wrong_is_said_in_words(self):
        n = self.nodes
        for nodes, value, word in (
                (dict(n, k={"op": "mul", "a": "j", "b": "clouds"}), "k", 'names no node ("clouds")'),
                (dict(n, k={"op": "blend", "a": "j", "b": "n"}), "k", '"op" is one of'),
                (dict(n, k={"op": "mul", "a": "j", "b": "n", "amount": 1}), "k", "does not read amount"),
                (dict(n, n=dict(NOISE, mix=0.5)), "k", "does not read mix"),
                (dict(n, d=dict(DISC, radius=7)), "k", 'node "d"'),
                (dict(n, j={"op": "max", "a": "d", "b": "k"}), "k", "goes round in a ring"),
                (dict(n, extra=dict(RING, radius=0.1)), "k", "extra feed nothing"),
                (n, "nothing", '"value" names no node'),
                ({"d": DISC, "i": {"op": "invert", "of": "d"}, "l": {"op": "levels", "of": "i"}}, "l", "no node joins two others"),
                ({"d": DISC, "r": RING}, "d", "3 to 24 nodes"),
                (dict(n, k={"op": "mul", "a": 0.5, "b": 0.5}), "k", "no input of it is a node"),
                (dict(n, k={"op": "warp", "of": "j", "by": 0.5, "amount": 0.1}), "k", '"by" is a node'),
                (dict(n, Big=DISC), "k", "lowercase"),
                (dict(n, l={"op": "levels", "of": "k", "low": 0.6, "high": 0.4}), "l", '"high" must be above "low"')):
            self.assertIn(word, said(nodes, value), word)
        self.assertIn('"value" names the node', said(n, None) if False else self._no_value())
        self.assertIn("stands in place of", self._mixed())
        self.assertIn('a "tile" has no shape', said(n, "k", tile=True))

    def _no_value(self):
        s = spec(self.nodes, "k")
        del s["comp"]["graph"]["value"]
        try:
            C.checked(s)
        except ValueError as e:
            return str(e)
        return ""

    def _mixed(self):
        s = spec(self.nodes, "k")
        s["comp"]["noise"] = {"scale": 4, "pan": [1, 0]}
        try:
            C.checked(s)
        except ValueError as e:
            return str(e)
        return ""

    def test_a_node_that_does_nothing_is_refused(self):
        n = self.nodes
        cases = ((dict(n, z={"op": "value", "is": 0.0}, q={"op": "max", "a": "k", "b": "z"}), "q", "z"),                              # joined with nothing
                 (dict(n, z={"op": "mul", "a": "r", "b": 0.0}, q={"op": "add", "a": "k", "b": "z"}), "q", "z"),                       # a ring times nothing
                 (dict(n, s=dict(DISC, radius=0.05), q={"op": "max", "a": "j", "b": "s"}, k={"op": "mul", "a": "q", "b": "n"}), "k", "s"))   # a small disc under a larger one
        for nodes, value, idle in cases:
            got = said(nodes, value)
            self.assertIn("do nothing", got, idle)
            self.assertIn(f'"{idle}"', got, idle)
        got = said(dict(n, s=dict(DISC, radius=0.3), q={"op": "max", "a": "j", "b": "s"}, k={"op": "mul", "a": "q", "b": "n"}), "k")
        self.assertIn('"d"', got)                                                           # a LARGER one: now the first disc is the hidden one
        self.assertNotIn('"s"', got)
        self.assertEqual(said(dict(n, s=dict(DISC, radius=0.1, soft=0.0), q={"op": "sub", "a": "j", "b": "s"}, k={"op": "mul", "a": "q", "b": "n"}), "k"), "")   # cut OUT of it: it shows

    def test_a_value_no_colour_reads_shows_nothing(self):
        n = dict(self.nodes, a2={"op": "noise", "scale": 3, "octaves": 2, "pan": [0, 1], "seed": 9, "contrast": 1.2},
                 v={"op": "screen", "a": "n", "b": "a2"})
        got = said(n, "v", "k")                                                              # alpha = k; the value branch (v, a2) colours nothing: no ramp
        self.assertIn("do nothing", got)
        self.assertIn('"a2"', got)
        self.assertIn("do nothing", said(n, "v", "k", ramp=[[0, [255, 255, 255]], [1, [255, 255, 255]]]))   # nor through a ramp of one colour
        self.assertEqual(said(n, "v", "k", ramp=[[0, [20, 0, 0]], [1, [255, 240, 200]]]), "")                # a ramp that varies shows it

    def test_a_small_strong_part_is_not_nothing(self):
        n = dict(self.nodes, spark=dict(DISC, radius=0.03), q={"op": "max", "a": "k", "b": "spark"})
        n["d"] = dict(DISC, radius=0.2, falloff=0.2)                                         # (a core that fades to its rim: the spark shows on it)
        n["spark"] = {"op": "shape", "sdf": "disc", "radius": 0.03, "soft": 0.0}
        self.assertEqual(said(dict(n, k={"op": "mul", "a": "j", "b": "n"}), "q"), "")

    def test_one_source_and_numbers_is_the_stack(self):
        self.assertIn("under two shapes or noises", said({"d": DISC, "v": {"op": "value", "is": 0.8}, "m": {"op": "mul", "a": "d", "b": "v"}}, "m"))
        self.assertIn("no node joins two others", said({"d": DISC, "l": {"op": "levels", "of": "d"}, "a": {"op": "add", "a": "l", "b": "l"}}, "a"))

    def test_the_checks_of_a_sheet_still_hold(self):
        still = dict(self.nodes, n=dict(NOISE, pan=[0, 0]))
        o = C.checked(spec(still, "k"))
        named = {c["name"]: c for c in C.check(C.frames_of(o), o)}
        self.assertFalse(named["moves"]["ok"])                                               # nothing pans: every frame the same
        o = C.checked(spec(self.nodes, "k"))
        self.assertTrue(all(c["ok"] for c in C.check(C.frames_of(o), o)))

    def test_the_starter_is_a_graph_that_bakes(self):
        s = C.new_spec("graph")
        o = C.checked(s)
        self.assertEqual(len(o["graph"]["nodes"]), 7)
        self.assertTrue(all(c["ok"] for c in C.check(C.frames_of(o), o)))


class TheRegister(unittest.TestCase):
    def test_node_compositing_is_a_comp_sheet_with_a_graph(self):
        m = M.load()[1]["node_compositing"]
        self.assertEqual(m["state"], "has")
        want = m["proof"][0]["texture"]
        good = C.new_spec("graph")
        self.assertTrue(M.texture_proves(want, good))
        stack = C.new_spec("ring")
        self.assertFalse(M.texture_proves(want, stack))
        other = copy.deepcopy(good)
        other["recipe"] = "flame"
        self.assertFalse(M.texture_proves(want, other))


if __name__ == "__main__":
    unittest.main()
