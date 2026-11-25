"""test_world_lsystem.py - PLANTS GROWN BY A GRAMMAR (kit/world/lsystem.py; the owner's method list: "L-system plant
generation"). The rewriting is held to the textbook (a word whose lengths are the Fibonacci numbers), the turtle to
plain geometry (a quarter turn, a branch that comes back, three boughs a third of a turn apart), and each of the kit's
kinds to what a plant must be: one connected body standing on its foot, as tall as asked, thinner toward its tips,
inside its budget of pieces.
Not claimed here: that a plant looks like its kind. That is a picture, looked at (the audit page says what was)."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_lsystem", os.path.join(HERE, "..", "..", "world", "lsystem.py"))
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)


def never():
    return 0.0


def plain(axiom, angle, **more):
    kind = {"axiom": axiom, "rules": {"Z": "Z"}, "angle": angle, "turns": 1, "taper": 0.5, "shorten": 1}
    kind.update(more)
    plant, why = L.grow(kind, 10, 1)
    assert why is None, why
    return plant


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


class Rewriting(unittest.TestCase):
    def test_every_letter_with_a_rule_becomes_its_word_turn_after_turn(self):
        # Lindenmayer's algae: A -> AB, B -> A. The word's lengths are the Fibonacci numbers.
        algae = {"axiom": "A", "rules": {"A": "AB", "B": "A"}, "angle": 20, "turns": 1}
        lengths = []
        for turns in range(1, 8):
            algae["turns"] = turns
            lengths.append(len(L.word(algae, never)))
        self.assertEqual(lengths, [2, 3, 5, 8, 13, 21, 34])
        algae["turns"] = 4
        self.assertEqual(L.word(algae, never), "ABAABABA")
        # letters with no rule stay; the turtle's own letters are never rewritten
        self.assertEqual(L.word({"axiom": "F[+X]", "rules": {"X": "FX"}, "angle": 20, "turns": 2}, never), "F[+FFX]")

    def test_a_rule_with_several_ways_is_chosen_by_weight(self):
        ways = {"axiom": "X" * 40, "rules": {"X": [[3, "F"], [1, "L"]]}, "angle": 20, "turns": 1}
        k = [0]

        def steps():
            k[0] += 1
            return (k[0] % 40) / 40

        text = L.word(ways, steps)
        self.assertEqual(len(text), 40)
        self.assertEqual(text.count("F"), 30)  # (three in four)

    def test_a_word_that_multiplies_for_ever_is_stopped(self):
        self.assertIsNone(L.word({"axiom": "A", "rules": {"A": "AAAAA"}, "angle": 20, "turns": 7}, never))


class Turtle(unittest.TestCase):
    def test_forward_and_a_straight_run_is_one_piece(self):
        up = plain("FFFF", 90)
        self.assertEqual(len(up["wood"]), 1)
        self.assertAlmostEqual(dist(up["wood"][0]["from"], [0, 0, 0]), 0)
        self.assertAlmostEqual(dist(up["wood"][0]["to"], [0, 10, 0]), 0)

    def test_a_quarter_turn_runs_level_and_turns_undo_each_other(self):
        turned = plain("F+F", 90)
        self.assertEqual(len(turned["wood"]), 2)
        a, b = turned["wood"][1]["from"], turned["wood"][1]["to"]
        self.assertAlmostEqual(a[1], 10)
        self.assertAlmostEqual(b[1], 10)
        self.assertAlmostEqual(dist(a, b), 10)
        for pair in ("+-", "&^", "\\/"):
            back = plain("F" + pair + "F", 37)
            self.assertEqual(len(back["wood"]), 2)  # (a turn ends the run, even one that is undone)
            self.assertAlmostEqual(dist(back["wood"][1]["to"], [0, 10, 0]), 0, places=9)
        # + then - are opposite ways; & pitches in the other plane
        left, right, pitch = plain("F+F", 90)["wood"][1]["to"], plain("F-F", 90)["wood"][1]["to"], plain("F&F", 90)["wood"][1]["to"]
        self.assertAlmostEqual(left[0], -right[0])
        self.assertAlmostEqual(abs(left[0]), 10)
        self.assertAlmostEqual(abs(pitch[2]), 10)
        self.assertAlmostEqual(pitch[0], 0)

    def test_a_branch_comes_back_to_its_fork_thinner_inside(self):
        forked = plain("F[+F]F", 90)
        self.assertEqual(len(forked["wood"]), 3)
        fork = forked["wood"][0]["to"]
        self.assertAlmostEqual(dist(forked["wood"][1]["from"], fork), 0)
        self.assertAlmostEqual(dist(forked["wood"][2]["from"], fork), 0)
        self.assertAlmostEqual(dist(forked["wood"][2]["to"], [0, 10, 0]), 0)  # (the leader goes on up)
        self.assertEqual([w["depth"] for w in forked["wood"]], [0, 1, 0])
        # thinner by the taper inside a branch, at the same height
        self.assertAlmostEqual(forked["wood"][1]["radius"], forked["wood"][2]["radius"] * 0.5)
        # ... and thinner toward the top along one piece
        self.assertLess(forked["wood"][2]["tip"], forked["wood"][2]["radius"])
        self.assertLess(forked["wood"][0]["tip"], forked["wood"][0]["radius"])

    def test_three_boughs_rolled_a_third_of_a_turn_apart_stand_evenly_round_the_trunk(self):
        whorl = plain("F[&F][////&F][////////&F]", 30)
        self.assertEqual(len(whorl["wood"]), 4)
        sx = sum(w["to"][0] - w["from"][0] for w in whorl["wood"][1:])
        sz = sum(w["to"][2] - w["from"][2] for w in whorl["wood"][1:])
        self.assertAlmostEqual(sx, 0, places=9)
        self.assertAlmostEqual(sz, 0, places=9)
        for w in whorl["wood"][1:]:
            self.assertGreater(w["to"][1], w["from"][1])  # (pitched out, still rising)

    def test_a_leaf_mass_sits_where_the_word_says(self):
        leafy = plain("F[+FL]", 90)
        self.assertEqual(len(leafy["leaves"]), 1)
        self.assertAlmostEqual(dist(leafy["leaves"][0]["pos"], leafy["wood"][1]["to"]), 0)
        self.assertEqual(sorted(leafy["leaves"][0]), ["pos"])  # (a leaf mass is a place; its cards are the mesh's)

    def test_wood_is_thinner_and_shorter_at_every_level_and_toward_the_top(self):
        # three levels, each a quarter turn off the last: lengths and radii by the level, to the digit
        kind = {"axiom": "F[+F[+F[+F]]]", "rules": {"Z": "Z"}, "angle": 90, "turns": 1, "taper": 0.5, "shorten": 0.5}
        plant, why = L.grow(kind, 10, 1, 1.0)
        self.assertIsNone(why)
        wood = plant["wood"]
        self.assertEqual([w["depth"] for w in wood], [0, 1, 2, 3])
        lengths = [dist(w["from"], w["to"]) for w in wood]
        for k in range(1, 4):
            self.assertAlmostEqual(lengths[k] / lengths[k - 1], 0.5)
        # radius = trunk x taper ^ level x (1 - 0.6 x height share), the trunk's own as asked
        self.assertAlmostEqual(wood[0]["radius"], 1.0)
        self.assertAlmostEqual(wood[0]["tip"], 1.0 * (1 - 0.6 * wood[0]["to"][1] / 10))
        for k in range(1, 4):
            y = wood[k]["from"][1]
            self.assertAlmostEqual(wood[k]["radius"], max(0.12, 0.5 ** k * (1 - 0.6 * y / 10)))
        # a straight stem to the top: its tip is 0.4 of its foot
        straight = L.grow({"axiom": "FF", "rules": {"Z": "Z"}, "angle": 20, "turns": 1}, 10, 1, 1.0)[0]
        self.assertAlmostEqual(straight["wood"][0]["tip"], 0.4)
        # the trunk unsaid: 0.035 of the height
        self.assertAlmostEqual(L.grow("dead", 40, 1)[0]["wood"][0]["radius"], 1.4)
        self.assertAlmostEqual(L.grow("dead", 40, 1, 2.5)[0]["wood"][0]["radius"], 2.5)
        # a thin trunk is not made thicker by the twig's floor
        thin = L.grow("broadleaf", 10, 1, 0.05)[0]
        self.assertTrue(all(abs(w["radius"] - 0.05) < 1e-12 and abs(w["tip"] - 0.05) < 1e-12 for w in thin["wood"]))
        # a bough that droops is no thicker at its tip
        droop = L.grow({"axiom": "F[&&F]", "rules": {"Z": "Z"}, "angle": 60, "turns": 1, "shorten": 0.5}, 10, 1, 1.0)[0]
        self.assertLess(droop["wood"][1]["to"][1], droop["wood"][1]["from"][1])
        self.assertEqual(droop["wood"][1]["tip"], droop["wood"][1]["radius"])

    def test_the_stem_is_first_whatever_the_word_starts_with(self):
        # a side branch written before the stem: the stem (not inside a branch) is still wood[0]
        plant, why = L.grow({"axiom": "[&F]FF", "rules": {"Z": "Z"}, "angle": 40, "turns": 1}, 10, 1, 1.0)
        self.assertIsNone(why)
        self.assertEqual(plant["wood"][0]["depth"], 0)
        self.assertAlmostEqual(dist(plant["wood"][0]["to"], [0, 10, 0]), 0)
        self.assertEqual([w["foot"] for w in plant["wood"]], [True, True])  # (both start on the ground)
        self.assertGreater(plant["wood"][0]["radius"], plant["wood"][1]["radius"])
        # a shrub's stems all start on the ground, and say so; nothing above the ground does
        shrub = L.grow("shrub", 8, 3)[0]
        feet = [w for w in shrub["wood"] if w["foot"]]
        self.assertEqual(len(feet), 3)
        for w in shrub["wood"]:
            self.assertEqual(w["foot"], dist(w["from"], [0, 0, 0]) < 1e-9)
        tree = L.grow("conifer", 30, 3)[0]
        self.assertEqual([w["foot"] for w in tree["wood"]].count(True), 1)
        self.assertTrue(tree["wood"][0]["foot"])

    def test_the_wobble_is_the_seeds_and_bounded(self):
        ruler = {"axiom": "F+F", "rules": {"Z": "Z"}, "angle": 60, "turns": 1, "shorten": 1}
        loose = dict(ruler, wobble=0.2)
        exact = L.grow(ruler, 10, 1)[0]
        self.assertEqual(exact["wood"], L.grow(ruler, 10, 2)[0]["wood"])  # (no wobble: the seed changes nothing here)
        angles = set()
        for seed in range(40):
            w = L.grow(loose, 10, seed)[0]["wood"][1]
            v = [w["to"][k] - w["from"][k] for k in range(3)]
            angle = math.degrees(math.acos(v[1] / dist(w["from"], w["to"])))
            self.assertTrue(60 * 0.8 - 1e-9 <= angle <= 60 * 1.2 + 1e-9, angle)
            angles.add(round(angle, 6))
        self.assertGreaterEqual(len(angles), 35)
        self.assertTrue(min(angles) < 54 and max(angles) > 66)  # (it uses its range)
        self.assertEqual(L.grow(loose, 10, 7)[0]["wood"], L.grow(loose, 10, 7)[0]["wood"])
        # the wobble has numbers of its own: a kind's forks are the same with it and without it
        stiff = dict(L.KINDS["broadleaf"], wobble=0)
        for seed in range(30):
            a, b = L.grow(stiff, 24, seed)[0], L.grow("broadleaf", 24, seed)[0]
            self.assertEqual([w["depth"] for w in a["wood"]], [w["depth"] for w in b["wood"]], seed)
            self.assertEqual(len(a["leaves"]), len(b["leaves"]))
            self.assertNotEqual(a["wood"], b["wood"])
        # seed 0 and seed 1 draw different numbers
        zero, one = L._lcg(0), L._lcg(1)
        self.assertNotEqual([zero() for _ in range(4)], [one() for _ in range(4)])


class Kinds(unittest.TestCase):
    def test_each_kind_is_one_plant_on_its_foot_as_tall_as_asked_in_budget(self):
        self.assertEqual(sorted(L.KINDS), ["broadleaf", "conifer", "dead", "shrub"])
        for name in L.KINDS:
            self.assertEqual(L.problems(L.KINDS[name]), [])
            for seed in range(1, 26):
                for height in (6, 24, 60):
                    plant, why = L.grow(name, height, seed)
                    self.assertIsNone(why)
                    wood = plant["wood"]
                    self.assertTrue(3 <= plant["pieces"] <= L.BUDGET)
                    self.assertEqual(len(wood), plant["pieces"])
                    self.assertAlmostEqual(dist(wood[0]["from"], [0, 0, 0]), 0)
                    top = max([max(w["from"][1], w["to"][1]) for w in wood] + [leaf["pos"][1] for leaf in plant["leaves"]])
                    self.assertAlmostEqual(top, height, places=6)
                    for w in wood:
                        self.assertGreaterEqual(min(w["from"][1], w["to"][1]), -1e-6)  # (nothing grows into the ground)
                        self.assertLessEqual(w["radius"], wood[0]["radius"] + 1e-9)  # (no piece thicker than the trunk)
                        self.assertLessEqual(w["tip"], w["radius"] + 1e-9)
                        self.assertGreaterEqual(w["tip"], 0.12 - 1e-9)
                    # one body: every piece starts ON an earlier piece (at its end, or along a straight run)
                    for i in range(1, len(wood)):
                        a = wood[i]["from"]
                        joined = False
                        for q in wood[:i]:
                            v = [q["to"][k] - q["from"][k] for k in range(3)]
                            t = sum((a[k] - q["from"][k]) * v[k] for k in range(3)) / sum(c * c for c in v)
                            t = min(1.0, max(0.0, t))
                            joined = joined or dist([q["from"][k] + v[k] * t for k in range(3)], a) < 1e-6
                        self.assertTrue(joined, (name, seed, i))
                    for leaf in plant["leaves"]:
                        self.assertTrue(any(dist(w["to"], leaf["pos"]) < 1e-6 for w in wood))
                    self.assertLessEqual(len(plant["leaves"]), L.LEAVES)
                    self.assertTrue(wood[0]["foot"])
                    self.assertEqual(wood[0]["depth"], min(w["depth"] for w in wood if w["foot"]))
        self.assertEqual(len(L.grow("dead", 24, 1)[0]["leaves"]), 0)  # (a dead tree has none)
        self.assertGreaterEqual(len(L.grow("broadleaf", 24, 1)[0]["leaves"]), 10)

    def test_a_kinds_shape_is_its_own(self):
        def reach(plant):
            return max(math.hypot(w["to"][0], w["to"][2]) for w in plant["wood"])

        conifer = L.grow("conifer", 30, 1)[0]
        boughs = [w for w in conifer["wood"] if w["depth"] == 1]
        lowest = min(boughs, key=lambda w: w["from"][1])
        widest = max(boughs, key=lambda w: math.hypot(w["to"][0], w["to"][2]))
        self.assertAlmostEqual(widest["from"][1], lowest["from"][1])  # (a cone: its widest whorl is its lowest)
        self.assertTrue(30 * 0.2 < reach(conifer) < 30 * 0.5)
        for w in boughs:  # (nearly level: a bough rises or falls under a fifth of its length)
            self.assertLess(abs(w["to"][1] - w["from"][1]), 0.2 * dist(w["from"], w["to"]))
        broad = L.grow("broadleaf", 30, 1)[0]
        # a broadleaf's crown stands round its trunk: its leaves' middle is near the trunk's line (it leaned to one
        # side when two of its three boughs pointed nearly the same way)
        cx = sum(leaf["pos"][0] for leaf in broad["leaves"]) / len(broad["leaves"])
        cz = sum(leaf["pos"][2] for leaf in broad["leaves"]) / len(broad["leaves"])
        self.assertLess(math.hypot(cx, cz), 0.12 * 30)
        dead = L.grow("dead", 30, 1)[0]
        ends = [w["to"] for w in dead["wood"] if w["depth"] >= 1]
        self.assertLess(math.hypot(sum(e[0] for e in ends) / len(ends), sum(e[2] for e in ends) / len(ends)), 0.12 * 30)

    def test_the_same_seed_the_same_plant_another_seed_another(self):
        a, b = L.grow("broadleaf", 24, 5)[0], L.grow("broadleaf", 24, 5)[0]
        self.assertEqual(a["wood"], b["wood"])
        self.assertGreaterEqual(len({L.grow("broadleaf", 24, seed)[0]["pieces"] for seed in range(1, 31)}), 3)
        # every kind of the kit's: 30 seeds, 30 plants (a stand of one kind is not one plant set down 30 times)
        for name in L.KINDS:
            plants = set()
            for seed in range(30):
                plant = L.grow(name, 24, seed)[0]
                plants.add(tuple(round(v, 4) for w in plant["wood"] for v in w["to"]))
            self.assertEqual(len(plants), 30, name)
        # the seed's ends are plants of their own
        self.assertNotEqual(L.grow("broadleaf", 24, 0)[0]["wood"], L.grow("broadleaf", 24, 1)[0]["wood"])
        self.assertNotEqual(L.grow("broadleaf", 24, 65534)[0]["wood"], L.grow("broadleaf", 24, 65535)[0]["wood"])


class Refused(unittest.TestCase):
    def test_what_cannot_be_grown_is_said(self):
        ok = {"axiom": "A", "rules": {"A": "FA"}, "angle": 20, "turns": 2}
        for kind, text, height in (
            ("palm", 'no plant kind "palm": the kit\'s are broadleaf, conifer, dead, shrub', 20),
            (5, "a plant's kind is", 20),
            ({"rules": {"A": "F"}, "angle": 20, "turns": 2}, "kind.axiom", 20),
            ({"axiom": "A", "rules": {}, "angle": 20, "turns": 2}, "kind.rules is", 20),
            (dict(ok, rules={"F": "FF"}), "a rule rewrites ONE letter", 20),
            (dict(ok, rules={"AB": "F"}), "a rule rewrites ONE letter", 20),
            (dict(ok, rules={"A": "F[+A"}), 'a "[" that is never closed', 20),
            (dict(ok, rules={"A": "F]+A"}), 'a "]" with no "["', 20),
            (dict(ok, rules={"A": "FQ"}), 'the letter "Q"', 20),
            (dict(ok, rules={"A": [[0, "F"]]}), "[weight over 0, word]", 20),
            (dict(ok, rules={"A": []}), "a word, or a list", 20),
            (dict(ok, angle=120), "kind.angle", 20),
            (dict(ok, turns=2.5), "kind.turns", 20),
            (dict(ok, taper=2), "kind.taper", 20),
            (dict(ok, leaf=0.3), "kind.leaf", 20),  # (a leaf's size is the mesh recipe's, not the kind's)
            (dict(ok, wobble=0.4), "kind.wobble", 20),
            (dict(ok, wobble=-0.1), "kind.wobble", 20),
            (dict(ok, shorten=0.29), "kind.shorten", 20),
            (dict(ok, shorten=1.01), "kind.shorten", 20),
            (dict(ok, taper=0.29), "kind.taper", 20),
            (dict(ok, turns=8), "kind.turns", 20),
            (dict(ok, turns=0), "kind.turns", 20),
            (dict(ok, angle=0.5), "kind.angle", 20),
            (dict(ok, angle=float("inf")), "kind.angle", 20),
            (dict(ok, rules={"A": [[float("nan"), "F"]]}), "[weight over 0, word]", 20),
            (dict(ok, rules={"A": [[float("inf"), "F"]]}), "[weight over 0, word]", 20),
            (dict(ok, rules={"A": [[True, "F"]]}), "[weight over 0, word]", 20),
            ({"axiom": "F" + "[F" * 13 + "]" * 13, "rules": {"Z": "Z"}, "angle": 20, "turns": 1}, "over 12 deep", 20),
            ({"axiom": "F[" + "L" * 61 + "]", "rules": {"Z": "Z"}, "angle": 20, "turns": 1}, "over 60 leaf masses", 20),
            ({"axiom": "LFF", "rules": {"Z": "Z"}, "angle": 20, "turns": 1}, "a leaf mass at its foot", 20),
            ({"axiom": "F&&&" + "F" * 9, "rules": {"Z": "Z"}, "angle": 29, "turns": 1, "shorten": 1}, "times its height sideways", 20),
            # (a dip of a tenth of the plant's height under its foot is into the ground too)
            ({"axiom": "[&&&&F]FFFFF", "rules": {"Z": "Z"}, "angle": 30, "turns": 1, "shorten": 1}, "into the ground", 20),
            ("broadleaf", "height is 2 to 400", 401),
            (dict(ok, tapre=0.5), "kind.tapre", 20),
            (dict(ok, rules={"A": "A"}), "grows no wood", 20),
            (dict(ok, rules={"A": "AAAAA"}, turns=7), "grows past", 20),
            (dict(ok, rules={"A": "F[+A][-A][&A][^A]"}, turns=5), "over 90 pieces", 20),
            ({"axiom": "F[&&&&&&FF]", "rules": {"A": "F"}, "angle": 30, "turns": 1}, "into the ground", 20),
            ({"axiom": "&&&F", "rules": {"A": "F"}, "angle": 30, "turns": 1}, "does not grow upward", 20),
            ("broadleaf", "height is 2 to 400", 1),
            ("broadleaf", "height is 2 to 400", float("nan")),
        ):
            plant, why = L.grow(kind, height, 1)
            self.assertIsNone(plant, (kind, text))
            self.assertIn(text, why)
        self.assertIsNotNone(L.grow("broadleaf", 400, 1)[0])
        self.assertIsNotNone(L.grow("broadleaf", 2, 1)[0])
        self.assertIsNotNone(L.grow({"axiom": "F" + "[F" * 12 + "]" * 12, "rules": {"Z": "Z"}, "angle": 20, "turns": 1, "shorten": 1}, 20, 1)[0])
        self.assertIsNotNone(L.grow({"axiom": "F[" + "L" * 60 + "]", "rules": {"Z": "Z"}, "angle": 20, "turns": 1}, 20, 1)[0])

    def test_a_seed_or_a_trunk_that_is_no_number_is_said_not_a_crash(self):
        for seed in (float("inf"), float("nan"), "abc", [1], None, True, 1.7, -1, 65536):
            plant, why = L.grow("broadleaf", 20, seed)
            self.assertIsNone(plant, seed)
            self.assertIn("seed is a whole number 0 to 65535", why)
        for seed in (0, 65535, 3.0):
            self.assertIsNotNone(L.grow("broadleaf", 20, seed)[0], seed)
        for trunk in (0, -1, float("inf"), float("nan"), "abc", True, 5.01):
            plant, why = L.grow("broadleaf", 20, 1, trunk)
            self.assertIsNone(plant, trunk)
            self.assertIn("trunk is its radius at the foot", why)
        self.assertIsNotNone(L.grow("broadleaf", 20, 1, 5)[0])  # (a quarter of its height)


class Budget(unittest.TestCase):
    def test_the_budget_is_held_to_the_piece(self):
        def zigzag(pieces):  # (a stem that leans one way and back: every F its own piece)
            return {"axiom": "".join("F" + ("+" if k % 2 == 0 else "-") for k in range(pieces))[:-1], "rules": {"Z": "Z"},
                    "angle": 20, "turns": 1, "shorten": 1}

        plant, why = L.grow(zigzag(L.BUDGET), 40, 1)
        self.assertIsNone(why)
        self.assertEqual(plant["pieces"], L.BUDGET)
        plant, why = L.grow(zigzag(L.BUDGET + 1), 40, 1)  # (the last piece is only closed at the word's end)
        self.assertIsNone(plant)
        self.assertIn("over 90 pieces", why)


class Asked(unittest.TestCase):
    def test_a_new_tree_says_how_its_wood_grows(self):
        line = L.unsaid({"name": "oak_c", "kind": "tree", "height": 30}, set())
        self.assertIn("oak_c: a new tree says how its wood grows", line)
        self.assertIn('"grammar": false', line)
        self.assertIn("broadleaf | conifer | dead | shrub", line)
        self.assertIsNone(L.unsaid({"name": "oak_c", "kind": "tree", "grammar": "broadleaf"}, {}))
        self.assertIsNone(L.unsaid({"name": "oak_c", "kind": "tree", "grammar": False}, {}))  # (the older way, meant)
        # a tree already uploaded into a game is not asked; one that is only named like something else is
        self.assertIsNone(L.unsaid({"name": "oak_a", "kind": "tree"}, {"oak_a", "crag"}))
        self.assertIsNone(L.unsaid({"name": "oak_a"}, ["oak_a"]))
        self.assertIsNotNone(L.unsaid({"name": "oak_c", "kind": "tree"}, {"oak_a", "crag"}))
        self.assertIsNotNone(L.unsaid({"name": "oak_c", "kind": "tree"}, None))
        # null, "", 0, true are no word: asked again - an uploaded tree too, once it writes the key
        for none in (None, "", 0, True, 5, []):
            self.assertIsNotNone(L.unsaid({"name": "oak_c", "kind": "tree", "grammar": none}, set()), repr(none))
            self.assertIsNotNone(L.unsaid({"name": "oak_a", "kind": "tree", "grammar": none}, {"oak_a"}), repr(none))
        self.assertIsNone(L.unsaid({"name": "oak_c", "kind": "tree", "grammar": {"axiom": "F"}}, set()))
        self.assertIsNotNone(L.unsaid({"name": "oak_c"}, {"oak_a": {}}))  # (a recipe with no kind is a tree)
        self.assertIsNone(L.unsaid({"name": "crag", "kind": "rock"}, {}))
        self.assertIsNone(L.unsaid(None, {}))

    def test_what_grammar_a_recipe_wants(self):
        self.assertEqual(L.wanted({"grammar": "conifer"}), "conifer")
        self.assertEqual(L.wanted({"grammar": {"axiom": "F"}}), {"axiom": "F"})
        self.assertIsNone(L.wanted({"grammar": False}))
        self.assertIsNone(L.wanted({"height": 30}))
        for none in (None, "", 0, True, 5, []):
            self.assertIsNone(L.wanted({"grammar": none}), repr(none))
        self.assertIsNone(L.wanted(None))


if __name__ == "__main__":
    unittest.main()
