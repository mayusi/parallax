"""kit/vfx/methods.py - the owner's VFX methods and the method plan that holds an effect to them. What is proven is
what the gate is trusted for: the register IS his list, in his order; a proof is met only by ONE layer that carries
all of it, of the beat that planned it; a plan with a hole says which; a reason for leaving a method out counts only
once he has seen it; and nothing he saw is dropped quietly. The chart draws the plan and its approval keeps it."""

import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import chart as CHART  # noqa: E402
import methods as M  # noqa: E402

GOOD = os.path.join(ROOT, "kit", "selftest", "vfx", "methods_good")
DZ_GOOD = os.path.join(ROOT, "kit", "selftest", "vfx", "dissolve_gate_good")
DZ_BAD = os.path.join(ROOT, "kit", "selftest", "vfx", "dissolve_gate")
BAD = os.path.join(ROOT, "kit", "selftest", "vfx", "methods")
HIS_LIST = os.path.join(ROOT, "board", "plans", "2026-11-13-owner-method-lists.md")
VALIDATOR = os.path.join(ROOT, "src", "kit", "VfxValidate3.luau")
WHY = "the embers are points of light, not drawn shapes"


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = M.main(argv)
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    return code, json.loads(lines[-1]), lines[:-1]


def gate_of(folder, name):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.main(["--gate", "--effects", folder, "--name", name, "--textures", os.path.join(folder, "textures")])
    return json.loads(buf.getvalue().splitlines()[-1])


class Empty:
    def get(self, key):
        return None


class Fixed:
    def __init__(self, specs):
        self.specs = specs

    def get(self, key):
        return self.specs.get(key)


class TestRegister(unittest.TestCase):
    def setUp(self):
        self.methods, self.by = M.load()

    def test_it_is_his_list_in_his_words_and_order(self):
        if not os.path.isfile(HIS_LIST):
            self.skipTest("the owner's method lists are not in this checkout")
        text = open(HIS_LIST, encoding="utf-8").read()
        body = text[text.index("## 4. VFX methods"):]
        body = body[body.index("\n") + 1:]
        body = body[:body.index("\n## ")] if "\n## " in body else body
        his = [re.sub(r"\s+", " ", x).strip() for x in body.split("·")]
        his = [x for x in his if x]
        self.assertEqual(len(his), 104)
        self.assertEqual([m["name"] for m in self.methods], his)
        self.assertEqual([m["n"] for m in self.methods], list(range(1, 105)))

    def test_every_method_says_what_the_kit_does_with_it(self):
        for m in self.methods:
            self.assertRegex(m["id"], r"^[a-z][a-z0-9_]*$")
            self.assertGreater(len(m.get("how", "")), 20, m["id"])
            if M.usable(m):
                self.assertIsInstance(m.get("proof"), list, m["id"])
                self.assertIsNone(m.get("stand_in"), m["id"])
            else:
                self.assertNotIn("proof", m, m["id"])
            if m.get("ask"):
                self.assertTrue(M.usable(m) and m.get("proof") and m.get("cues") and m.get("tools"), m["id"])

    def test_a_proof_only_names_what_a_preset_can_hold(self):
        """a proof that names a layer kind or a mesh key the runtime does not read could never be met"""
        src = open(VALIDATOR, encoding="utf-8").read()
        kinds = set(re.findall(r"^\t(\w+) = true,", src[src.index("local KINDS = {"):src.index("local KIND_LIST")], re.M))
        mesh_keys = set(re.findall(r"^\t(\w+) = true,", src[src.index("local MESH_KEYS = {"):src.index("local DEBRIS_KEYS")], re.M))
        tech = {"rim", "boil", "haze", "echo", "path", "flicker"}  # (VfxTech keys: expanded before the validator)
        self.assertIn("mesh", kinds)
        self.assertIn("uvScroll", mesh_keys)
        known = {"kind", "has", "lacks", "where", "where_not", "positive", "zero", "nonzero", "texture", "layers_min", "file", "plan", "kept", "rests", "least"}
        debris_keys = set(re.findall(r"^	(\w+) = true,", src[src.index("local DEBRIS_KEYS = {"):src.index("}", src.index("local DEBRIS_KEYS = {"))], re.M))
        tex = {"recipe", "recipe_not", "post", "post_any", "made_by", "where", "has", "positive", "varies"}
        for m in self.methods:
            for alt in m.get("proof") or []:
                self.assertTrue(set(alt) <= known and alt, (m["id"], alt))
                if "kind" in alt:
                    self.assertIn(alt["kind"], kinds, m["id"])
                if "texture" in alt:
                    self.assertTrue(set(alt["texture"]) <= tex and alt["texture"], (m["id"], alt))
                if "kept" in alt:
                    if "sim" in alt["kept"]:                             # a baked simulation: which one checks the bake
                        self.assertTrue({"key", "dir", "sim"} <= set(alt["kept"]) <= {"key", "dir", "sim", "recipes"}, m["id"])
                        if "recipes" in alt["kept"]:                     # one module, more than one method: the bake's recipe says which
                            mod = __import__(M.SIMS[alt["kept"]["sim"]])
                            self.assertTrue(alt["kept"]["recipes"] and set(alt["kept"]["recipes"]) <= set(mod.RECIPES), m["id"])
                        self.assertIn(alt["kept"]["sim"], M.SIMS, m["id"])
                        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(M.__file__), M.SIMS[alt["kept"]["sim"]] + ".py")), m["id"])
                    else:
                        self.assertEqual(set(alt["kept"]), {"key", "dir"}, m["id"])
                        self.assertIn(alt["kept"]["dir"], ("fields", "fractures", "points", "seq"), m["id"])
                if "rests" in alt:                                       # the layer's own flight is flown: the plan it names is the one it flies
                    self.assertEqual((alt["rests"], alt.get("where")), (alt.get("plan"), {"rest": [True]}), m["id"])
                if "plan" in alt:
                    self.assertEqual(alt.get("kind"), "debris", m["id"])
                    self.assertIn(alt["plan"], debris_keys, m["id"])
                if alt.get("kind") == "mesh":
                    for path in (list(alt.get("has") or []) + list(alt.get("where") or {}) + list(alt.get("nonzero") or []) + list(alt.get("positive") or [])
                                 + list(alt.get("where_not") or {}) + list(alt.get("lacks") or [])):
                        self.assertIn(path.split(".")[0], mesh_keys | tech, (m["id"], path))
                self.assertTrue(M.say(alt))

    def test_what_the_game_does_not_show_is_a_refused_rule(self):
        self.assertTrue(any(r.get("id") == "mesh_erode" and r["match"] == {"kind": "mesh", "has": ["erode"]} for r in M.REFUSED))
        self.assertTrue(any(r.get("id") == "mesh_dissolve_sheet_bare" for r in M.REFUSED))
        for mid in ("dissolve", "alpha_clip", "dither"):
            self.assertEqual(self.by[mid]["state"], "has", mid)
            self.assertTrue(self.by[mid].get("tools"), mid)
        # a mesh's own erode is NOT a proof of the dissolve method
        self.assertIsNone(M.proved(self.by["dissolve"], [{"kind": "mesh", "erode": [0.6, 1], "texture": "x"}], Empty(), ".", "s"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            json.dump({"methods": [{"id": "a", "name": "A", "state": "has"}], "refused": [{"match": {"kind": "mesh"}}]}, open(path, "w"))
            with self.assertRaises(ValueError):
                M.load(path)
        M.load()  # (the real register's rules back in place)

    def test_breaking_is_the_objects_own_pieces(self):
        for mid in ("fracture", "destruction"):
            self.assertEqual(self.by[mid]["state"], "has")
        self.assertTrue(self.by["fracture"].get("ask"))
        frac = self.by["fracture"]
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fractures"))
            with open(os.path.join(tmp, "fractures", "slab_a.json"), "w", encoding="utf-8") as fh:
                json.dump({"pieces": [{"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.0}, {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.1}, {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.4}]}, fh)
            with open(os.path.join(tmp, "fractures", "one.json"), "w", encoding="utf-8") as fh:
                json.dump({"pieces": [{"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.0}]}, fh)

            def proved(layer):
                return M.proved(frac, [dict({"kind": "debris", "life": 1.2}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"pieces": "slab_a", "speed": 30}))
            self.assertTrue(proved({"pieces": "slab_a"}))                      # the plan's own speed
            self.assertFalse(proved({"shape": "rock", "count": 8}))            # thrown rocks are not the object breaking
            self.assertFalse(proved({"pieces": "typo"}))                       # a name that names no plan
            self.assertFalse(proved({"pieces": "Slab_a"}))                     # the game finds names by their exact letters
            self.assertFalse(proved({"pieces": "slab_a", "speed": 0}))         # no piece leaves the slab
            self.assertFalse(proved({"pieces": "slab_a", "life": 0.3}))        # the break never reaches the last piece
            self.assertFalse(proved({"pieces": "one"}))                        # one piece is the slab, not a break
            self.assertTrue(M.proved(self.by["destruction"], [{"kind": "debris", "pieces": "slab_a", "life": 1}], Empty(), tmp, "s"))
        self.assertEqual(M.cue_hit(frac, "the ground slab shatters under the blow"), "shatter")
        for said in ("the window shattered", "the wall crumbled", "the pane cracked open", "the plate broke apart"):
            self.assertIsNotNone(M.cue_hit(frac, said), said)
        self.assertIsNone(M.cue_hit(frac, "the slab holds: no shatter"))
        for said in ("not a single shatter", "without any sign of a fracture", "never one shatter"):
            self.assertIsNone(M.cue_hit(frac, said), said)
        self.assertEqual(M.cue_hit(frac, "a single shatter, not a sound"), "shatter")
        self.assertIsNone(M.cue_hit(frac, "an earth-shattering roar"))        # a figure of speech breaks nothing

    def test_a_flare_is_the_lens_answering_a_light(self):
        for mid in ("lens_flare", "anamorphic"):
            self.assertEqual(self.by[mid]["state"], "has")

        def proved(mid, layer):
            return M.proved(self.by[mid], [dict({"kind": "lens", "life": 1}, **layer)], Empty(), ".", "s") is not None

        self.assertTrue(proved("lens_flare", {"flare": {"strength": 0.8}}))
        self.assertTrue(proved("lens_flare", {"flare": {"strength": [[0, 0], [0.2, 1], [1, 0]]}}))
        self.assertFalse(proved("lens_flare", {"flare": {"strength": 0}}))          # a flare nobody sees
        self.assertFalse(proved("lens_flare", {"flare": {"strength": 0.01}}))       # ... nor one too faint to see
        self.assertFalse(proved("lens_flare", {"flare": {"strength": [[0, 0], [0.5, 0.1], [1, 0]]}}))
        self.assertFalse(proved("anamorphic", {"flare": {"strength": 0.8, "streak": 0.02}}))   # a streak a hair long
        self.assertTrue(proved("anamorphic", {"flare": {"strength": 0.8, "streak": 0.6}}))
        self.assertFalse(proved("lens_flare", {"flare": {"ghosts": 5}}))            # no strength said
        self.assertFalse(proved("lens_flare", {"flare": {"strength": 0.8, "ghosts": 0}}))  # a dot with nothing that swings
        self.assertFalse(proved("lens_flare", {"streaks": 0.8}))                    # speed lines are not a flare
        self.assertTrue(proved("anamorphic", {"flare": {"strength": 0.8, "streak": 0.6}}))
        self.assertFalse(proved("anamorphic", {"flare": {"strength": 0.8, "streak": 0}}))
        self.assertFalse(proved("anamorphic", {"flare": {"strength": 0.8, "squeeze": 2}}))  # ovals alone: no streak
        self.assertFalse(proved("anamorphic", {"streaks": 0.8}))

    def test_a_vector_field_is_one_that_is_there(self):
        vf = self.by["vector_field"]
        self.assertEqual(vf["state"], "has")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fields"))
            with open(os.path.join(tmp, "fields", "whirl.json"), "w", encoding="utf-8") as fh:
                json.dump({"elements": [{"kind": "wind", "dir": [1, 0, 0], "speed": 4}]}, fh)
            for bad, text in (("empty", '{"elements": []}'), ("junk", "not json at all"), ("still", '{"bounds": 4, "elements": [{"kind": "vortex", "at": [300, 0, 0], "radius": 2, "speed": 12}]}'),
                              ("norad", '{"elements": [{"kind": "vortex", "at": [0, 0, 0], "radius": 0, "speed": 12}]}')):
                with open(os.path.join(tmp, "fields", f"{bad}.json"), "w", encoding="utf-8") as fh:
                    fh.write(text)

            def proved(layer):
                return M.proved(vf, [dict({"kind": "swarm", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            for bad in ("empty", "junk", "still", "norad"):                  # a file that is there and is no field that moves the air
                self.assertFalse(proved({"field": {"name": bad}}), bad)
            self.assertFalse(proved({"field": {"name": "whirl", "gain": [[0, 0], [1, 0]]}}))   # off all its life
            self.assertFalse(proved({"field": {"name": "whirl", "gain": 0.0001}}))             # as good as off

            self.assertTrue(proved({"field": {"name": "whirl"}}))
            self.assertTrue(proved({"field": {"name": "whirl", "gain": [[0, 0], [1, 2]]}}))
            self.assertFalse(proved({"field": {"name": "typo"}}))            # a name that names no field
            self.assertFalse(proved({"field": {"name": "Whirl"}}))           # the game finds names by their exact letters
            self.assertFalse(proved({"field": {"name": "whirl", "gain": 0}}))  # a field that is switched off
            self.assertFalse(proved({"field": "whirl"}))                     # not the block the layer reads
            self.assertTrue(proved({"curl": {"strength": 10}}))              # the generated field still counts
            self.assertFalse(proved({}))

    def test_mesh_particles_are_meshes_not_balls_or_blocks(self):
        mp = self.by["mesh_particle"]
        self.assertEqual(mp["state"], "has")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fractures"))
            with open(os.path.join(tmp, "fractures", "slab_a.json"), "w", encoding="utf-8") as fh:
                json.dump({"pieces": [{"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.0}, {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "delay": 0.1}]}, fh)

            def proved(layer):
                return M.proved(mp, [dict({"life": 2}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"kind": "swarm", "shape": "Rock", "count": 20}))
            self.assertTrue(proved({"kind": "debris", "shape": "rock", "count": 8}))
            self.assertTrue(proved({"kind": "debris", "pieces": "slab_a"}))
            self.assertFalse(proved({"kind": "swarm", "count": 60}))                     # balls
            self.assertFalse(proved({"kind": "swarm", "shape": "Block"}))
            self.assertFalse(proved({"kind": "debris", "count": 8}))                     # blocks
            self.assertFalse(proved({"kind": "swarm", "shape": "Rock", "count": 0}))     # nothing drawn
            self.assertFalse(proved({"kind": "sprite"}))                                 # flat pictures are not meshes

    def test_a_row_the_engine_cannot_do_is_closed_only_with_its_reason_and_a_held_stand_in(self):
        closed = [m for m in self.by.values() if m["state"] == "engine"]
        self.assertGreaterEqual(len(closed), 5)
        for m in closed:
            self.assertGreaterEqual(len(m["reason"]), 60, m["id"])           # the exact thing Roblox lacks, in words
            self.assertTrue(m["proof"], m["id"])                             # and a preset must SHOW the stand-in
            self.assertTrue(M.usable(m))                                     # a plan may name it
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            json.dump({"methods": [{"id": "a", "name": "A", "state": "engine", "proof": [{"kind": "mesh"}],
                                    "reason": "Roblox has no custom shader: a script cannot run one"}]}, open(path, "w"))
            methods, _ = M.load(path)
            self.assertEqual(methods[0]["state"], "engine")

    def test_a_register_that_is_not_whole_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            for doc in ({"methods": []},
                        {"methods": [{"id": "a", "name": "A", "state": "has"}, {"id": "a", "name": "B", "state": "has"}]},
                        {"methods": [{"id": "a", "name": "A", "state": "done"}]},
                        {"methods": [{"id": "a", "name": "A", "state": "not_roblox", "stand_in": "nothing"}]},
                        # a row closed as "the engine cannot, a stand-in is held" says its reason AND has a proof
                        {"methods": [{"id": "a", "name": "A", "state": "engine", "proof": [{"kind": "mesh"}]}]},
                        {"methods": [{"id": "a", "name": "A", "state": "engine", "reason": "too short", "proof": [{"kind": "mesh"}]}]},
                        {"methods": [{"id": "a", "name": "A", "state": "engine", "reason": "Roblox has no custom shader: a script cannot run one"}]}):
                json.dump(doc, open(path, "w"))
                with self.assertRaises(ValueError):
                    M.load(path)
            code, verdict, _ = run(["--register", path])
            self.assertEqual((code, verdict["status"]), (1, "fail"))


class TestProof(unittest.TestCase):
    def test_a_cue_the_words_deny_is_no_hit(self):
        m = {"cues": ["fire", "flame", "smoke"]}
        for text in ("drifting embers in the dark, the fire gone", "no flame, only a glint", "a clean cut without any smoke", "the fire is out", "never a flame"):
            self.assertIsNone(M.cue_hit(m, text), text)
        for text in ("a crescent of flame, no hold", "the fire follows the blade and is gone at the end of the swing only after it", "smoke, no sparks", "not small: a wall of fire"):
            self.assertIsNotNone(M.cue_hit(m, text), text)

    def test_a_cue_is_a_whole_word(self):
        m = {"cues": ["fire", "wave"]}
        self.assertEqual(M.cue_hit(m, "embers of the FIRE drift"), "fire")
        self.assertEqual(M.cue_hit(m, "two waves cross"), "wave")
        self.assertIsNone(M.cue_hit(m, "a fireball; a waveform; campfire"))
        self.assertIsNone(M.cue_hit({}, "fire"))

    def test_numbers_reads_curves_not_their_times(self):
        self.assertEqual(M.numbers(3), [3.0])
        self.assertEqual(M.numbers([[0, 0], [0.5, 0], [1, 0]]), [0.0, 0.0, 0.0])
        self.assertEqual(M.numbers([[0, 0.2], [1, 1]]), [0.2, 1.0])
        self.assertEqual(M.numbers(True), [])
        self.assertEqual(M.numbers(None), [])
        self.assertEqual(sorted(M.numbers({"a": 1, "b": [2, 3]})), [1.0, 2.0, 3.0])

    def test_numbers_reads_keys_with_envelopes(self):
        self.assertEqual(M.numbers([[0, 0, 0.3], [1, 0, 0.3]]), [0.0, 0.0])
        self.assertEqual(M.numbers([[0, 2, 0.5], [1, 5, 0]]), [2.0, 5.0])

    def test_every_condition_must_hold_on_the_same_layer(self):
        alt = {"kind": "mesh", "has": ["uvScroll"]}
        self.assertTrue(M.layer_proves(alt, {"kind": "mesh", "uvScroll": [0.2, 0]}, Empty()))
        self.assertFalse(M.layer_proves(alt, {"kind": "mesh"}, Empty()))
        self.assertFalse(M.layer_proves(alt, {"kind": "beam", "uvScroll": [0.2, 0]}, Empty()))
        self.assertFalse(M.layer_proves(alt, {"kind": "mesh", "uvScroll": False}, Empty()))
        m = {"proof": [alt]}
        split = [{"kind": "mesh"}, {"kind": "beam", "uvScroll": [1, 0]}]
        self.assertIsNone(M.proved(m, split, Empty(), ".", "s"))
        self.assertEqual(M.proved(m, split + [{"kind": "mesh", "uvScroll": [1, 0]}], Empty(), ".", "s"), alt)

    def test_where_positive_zero_and_dotted_paths(self):
        self.assertTrue(M.layer_proves({"kind": "mesh", "where": {"shape": ["seq"]}}, {"kind": "mesh", "shape": "seq"}, Empty()))
        self.assertFalse(M.layer_proves({"kind": "mesh", "where": {"shape": ["seq"]}}, {"kind": "mesh", "shape": "ring"}, Empty()))
        self.assertTrue(M.layer_proves({"kind": "impact", "has": ["draw.cutSmear"]}, {"kind": "impact", "draw": {"cutSmear": 0.4}}, Empty()))
        self.assertFalse(M.layer_proves({"kind": "impact", "has": ["draw.cutSmear"]}, {"kind": "impact", "draw": {}}, Empty()))
        add = {"kind": "sprite", "positive": ["lightEmission"]}
        self.assertTrue(M.layer_proves(add, {"kind": "sprite", "lightEmission": [[0, 0], [1, 0.8]]}, Empty()))
        self.assertFalse(M.layer_proves(add, {"kind": "sprite", "lightEmission": 0}, Empty()))
        self.assertFalse(M.layer_proves(add, {"kind": "sprite"}, Empty()))
        plain = {"kind": "sprite", "zero": ["lightEmission"]}
        self.assertTrue(M.layer_proves(plain, {"kind": "sprite"}, Empty()))
        self.assertTrue(M.layer_proves(plain, {"kind": "sprite", "lightEmission": 0}, Empty()))
        self.assertFalse(M.layer_proves(plain, {"kind": "sprite", "lightEmission": 1}, Empty()))
        self.assertFalse(M.layer_proves({}, {"kind": "sprite"}, Empty()))

    def test_a_texture_proof_reads_the_spec_not_the_name(self):
        specs = Fixed({"flame_ink": {"engine": "fx", "recipe": "ink"}, "pack": {"engine": "fx", "recipe": "import", "about": "x (kit/vfx/flowbake.py: loops)"},
                       "cel": {"recipe": "cel", "post": {"bands": 3, "cut": 0}}})
        ink = {"texture": {"recipe": ["ink"]}}
        self.assertTrue(M.layer_proves(ink, {"kind": "sprite", "texture": "flame_ink"}, specs))
        self.assertFalse(M.layer_proves(ink, {"kind": "sprite", "texture": "ink_but_no_spec"}, specs))
        self.assertFalse(M.layer_proves(ink, {"kind": "sprite", "texture": "pack"}, specs))
        self.assertTrue(M.layer_proves(ink, {"kind": "mesh", "boil": {"texture": "flame_ink"}}, specs))
        self.assertTrue(M.layer_proves(ink, {"kind": "sprite", "views": {"0": "pack", "90": "flame_ink"}}, specs))
        self.assertTrue(M.layer_proves({"texture": {"made_by": "flowbake.py"}}, {"kind": "mesh", "texture": "pack"}, specs))
        self.assertFalse(M.layer_proves({"texture": {"made_by": "flowbake.py"}}, {"kind": "mesh", "texture": "cel"}, specs))
        self.assertFalse(M.layer_proves({"texture": {"made_by": "flares.py"}}, {"kind": "mesh", "texture": "pack"}, specs))
        gen = {"texture": {"recipe_not": ["import", "ink"]}}
        self.assertTrue(M.layer_proves(gen, {"kind": "sprite", "texture": "cel"}, specs))
        self.assertFalse(M.layer_proves(gen, {"kind": "sprite", "texture": "pack"}, specs))
        self.assertFalse(M.layer_proves(gen, {"kind": "sprite", "texture": "ink_but_no_spec"}, specs))
        self.assertTrue(M.layer_proves({"texture": {"post": ["bands"]}}, {"kind": "sprite", "texture": "cel"}, specs))
        self.assertFalse(M.layer_proves({"texture": {"post": ["cut"]}}, {"kind": "sprite", "texture": "cel"}, specs))  # cut: 0 is off
        self.assertTrue(M.layer_proves({"texture": {"post_any": True}}, {"kind": "sprite", "texture": "cel"}, specs))
        self.assertFalse(M.layer_proves({"texture": {"post_any": True}}, {"kind": "sprite", "texture": "flame_ink"}, specs))

    def test_a_texture_proof_may_read_the_specs_own_fields(self):
        specs = Fixed({"hard": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "patches", "soft": 0.0}},
                       "soft": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "patches", "soft": 0.08}},
                       "dots": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "dither", "soft": 0}},
                       "pack": {"engine": "fx", "recipe": "import", "dissolve": {"pattern": "dither"}},
                       "typed": {"engine": "blender", "recipe": "dissolve", "dissolve": {"pattern": "dither", "soft": 0}}})
        dither = {"texture": {"recipe": ["dissolve"], "where": {"dissolve.pattern": ["dither"]}}}
        hard = {"texture": {"recipe": ["dissolve"], "where": {"dissolve.soft": [0]}}}
        self.assertTrue(M.layer_proves(dither, {"kind": "sprite", "texture": "dots"}, specs))
        self.assertFalse(M.layer_proves(dither, {"kind": "sprite", "texture": "soft"}, specs))
        self.assertFalse(M.layer_proves(dither, {"kind": "sprite", "texture": "pack"}, specs))  # an import that says so is not one
        self.assertTrue(M.layer_proves(hard, {"kind": "mesh", "texture": "hard"}, specs))
        self.assertTrue(M.layer_proves(hard, {"kind": "mesh", "texture": "dots"}, specs))
        self.assertFalse(M.layer_proves(hard, {"kind": "mesh", "texture": "soft"}, specs))

    def test_the_dissolve_methods_are_proved_by_a_sheet_that_is_played(self):
        specs = Fixed({"soft": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "patches", "soft": 0.08}},
                       "hard": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "patches", "soft": 0}},
                       "dots": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "dither", "soft": 0}},
                       "pack": {"engine": "fx", "recipe": "import"},
                       "typed": {"engine": "blender", "recipe": "dissolve", "dissolve": {"pattern": "dither", "soft": 0}}})
        _, by = M.load()
        over = {"layout": "4x4", "mode": "OneShot", "over": [0.6, 1]}
        mesh = {"kind": "mesh", "texture": "soft", "surface": 1, "flipbook": over}
        sprite = {"kind": "sprite", "texture": "soft", "flipbook": {"layout": "4x4", "mode": "OneShot"}}

        def proves(mid, layer):
            return M.proved(by[mid], [layer], specs, ".", "s") is not None

        self.assertTrue(proves("dissolve", mesh))
        self.assertTrue(proves("dissolve", sprite))
        self.assertFalse(proves("dissolve", {k: v for k, v in mesh.items() if k != "surface"}))       # the game would draw full squares
        self.assertFalse(proves("dissolve", dict(mesh, flipbook={"layout": "4x4", "mode": "OneShot"})))  # no window
        self.assertFalse(proves("dissolve", dict(mesh, texture="pack")))                               # not a baked break-up
        self.assertFalse(proves("dissolve", dict(mesh, texture="typed")))                              # a spec typed by hand for another engine
        self.assertFalse(proves("dissolve", dict(sprite, flipbook={"layout": "4x4", "mode": "Loop"})))  # a loop never ends empty
        self.assertFalse(proves("dissolve", {"kind": "sprite", "texture": "soft"}))                    # the sheet shown whole
        self.assertTrue(proves("dither", dict(mesh, texture="dots")))
        self.assertTrue(proves("dither", dict(sprite, texture="dots")))
        self.assertFalse(proves("dither", mesh))
        self.assertFalse(proves("dither", {"kind": "mesh", "texture": "dots"}))                        # not played, no surface
        self.assertTrue(proves("alpha_clip", dict(sprite, texture="hard")))
        self.assertFalse(proves("alpha_clip", {"kind": "sprite", "texture": "hard"}))                  # a static sprite moves no threshold
        self.assertFalse(proves("alpha_clip", sprite))                                                 # a soft front is not a cut-out

    def test_the_methods_a_comp_sheet_builds_are_proved_by_its_blocks(self):
        def sheet(**comp):
            return {"engine": "fx", "recipe": "comp", "comp": comp}

        ring = {"sdf": "ring", "radius": 0.3, "width": 0.1}
        white = [[0, [255, 255, 255]], [1, [255, 255, 255]]]
        specs = Fixed({"warped": sheet(shape=ring, warp={"scale": 3, "amount": 0.05}), "plain": sheet(shape=ring),
                       "mapped": sheet(source={"texture": "g"}, warp={"scale": 3, "amount": 0.05}, ramp=[[0, [0, 0, 0]], [1, [255, 255, 255]]]),
                       # blocks that are there and do nothing: a warp of no amount, a starter's white ramp
                       "idle": sheet(shape=ring, warp={"scale": 3, "amount": 0}, ramp=white), "bare": sheet(shape=ring, warp={}, ramp=white),
                       "blobs": sheet(shape={"sdf": "blobs", "radius": 0.1, "count": 5}), "tree": sheet(shape={"sdf": "branches", "length": 0.2, "width": 0.03}),
                       "dots": sheet(shape=ring, halftone={"dot": 8}), "noise": sheet(tile=True, noise={"scale": 4}),
                       "typed": {"engine": "blender", "recipe": "comp", "comp": {"shape": ring, "warp": {}, "ramp": [], "halftone": {}}},
                       "import": {"engine": "fx", "recipe": "import", "comp": {"warp": {"amount": 1}}}})
        _, by = M.load()

        def proves(mid, key):
            return M.proved(by[mid], [{"kind": "sprite", "texture": key}], specs, ".", "s") is not None

        want = {"uv_distortion": {"warped", "mapped"}, "texture_warp": {"mapped"}, "gradient_map": {"mapped"},
                "sdf": {"warped", "plain", "blobs", "tree", "dots", "idle", "bare"}, "metaball": {"blobs"}, "branching": {"tree"}, "halftone": {"dots"}}
        for mid, keys in want.items():
            self.assertEqual(by[mid]["state"], "has", mid)
            self.assertEqual({k for k in specs.specs if proves(mid, k)}, keys, mid)   # (never "typed" nor "import")

    def test_specs_are_read_from_their_folder_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "textures"))
            json.dump({"recipe": "ink"}, open(os.path.join(tmp, "secret.json"), "w"))
            json.dump({"recipe": "ink"}, open(os.path.join(tmp, "textures", "ok.json"), "w"))
            open(os.path.join(tmp, "textures", "broken.json"), "w").write("{")
            json.dump(["a list"], open(os.path.join(tmp, "textures", "list.json"), "w"))
            specs = M.Specs(os.path.join(tmp, "textures"))
            self.assertEqual(specs.get("ok"), {"recipe": "ink"})
            self.assertIsNone(specs.get("../secret"))
            self.assertIsNone(specs.get("broken"))
            self.assertIsNone(specs.get("list"))
            self.assertIsNone(specs.get("none"))

    def test_a_beats_trace_proves_that_beat(self):
        m = self.by["rotoscope"] if hasattr(self, "by") else M.load()[1]["rotoscope"]
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "refs_measured"))
            open(os.path.join(tmp, "refs_measured", "a_set.trace.beat2.json"), "w").write("{}")
            self.assertIsNone(M.proved(m, [], Empty(), tmp, "a_set", "1"))
            self.assertIsNotNone(M.proved(m, [], Empty(), tmp, "a_set", "2"))
            self.assertIsNone(M.proved(m, [], Empty(), tmp, "a_set"))

    def test_a_kept_file_proves_by_its_set(self):
        m = {"proof": [{"file": "refs_measured/{set}.trace.beat*.json"}]}
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "refs_measured"))
            self.assertIsNone(M.proved(m, [], Empty(), tmp, "a_set"))
            open(os.path.join(tmp, "refs_measured", "b_set.trace.beat1.json"), "w").write("{}")
            self.assertIsNone(M.proved(m, [], Empty(), tmp, "a_set"))
            open(os.path.join(tmp, "refs_measured", "a_set.trace.beat1.json"), "w").write("{}")
            self.assertIsNotNone(M.proved(m, [], Empty(), tmp, "a_set"))
            self.assertIsNone(M.proved(m, [], Empty(), tmp, ""))


def chart_of(plan, seen="same", approved=True, by="owner"):
    rows = [("0 glint", 0.0), ("1 crescent of flame", 0.3), ("2 embers", 0.9)]
    P = {"schema": 1, "duration": 1.6, "beats": []}
    for label, t in rows:
        row = {"beat": label, "t": t, "len": 0.3, "hold": 0.0, "slow": 1.0, "key": label.startswith("1")}
        methods, nots = plan.get(label.split()[0], ([], {}))
        if methods:
            row["methods"] = list(methods)
        if nots:
            row["not"] = dict(nots)
        P["beats"].append(row)
    if approved:
        P["approved"] = {"by": by, "words": "yes", "plan": CHART.plan_key(P)}
        if seen == "same":
            P["approved"]["methods"] = M.snapshot(P)
        elif seen is not None:
            P["approved"]["methods"] = M.snapshot(chart_of(seen, approved=False))
    return P


WORDS = {"0": "0 glint a glint runs along the blade", "1": "1 crescent of flame ONE thick crescent of flame", "2": "2 embers embers of the fire drift"}
PLAN = {"0": (["sprite"], {}), "1": (["mesh", "uv_scroll"], {"hand_drawn": WHY}), "2": (["particle"], {"hand_drawn": WHY})}
LAYERS = [{"kind": "sprite", "beat": 0}, {"kind": "mesh", "uvScroll": [1, 0], "beat": 1}, {"kind": "sprite", "beat": 2}]


class TestPlan(unittest.TestCase):
    def setUp(self):
        _, self.by = M.load()

    def problems(self, plan):
        return M.plan_problems(self.by, M.plan_of(chart_of(plan, approved=False)), WORDS)

    def test_a_whole_plan_has_nothing_open(self):
        self.assertEqual(self.problems(PLAN), [])

    def test_each_hole_is_said(self):
        p = copy.deepcopy(PLAN)
        p["0"] = ([], {})
        self.assertTrue(any("beat 0" in x and "names no method" in x for x in self.problems(p)))
        p = copy.deepcopy(PLAN)
        p["0"] = (["sprite", "sparkle_magic"], {})
        self.assertTrue(any('"sparkle_magic" is not a method of the list' in x for x in self.problems(p)))
        p = copy.deepcopy(PLAN)
        p["0"] = (["_made_missing"], {})
        self.assertTrue(any('"A made method the kit has not built" is not built in the kit yet' in x for x in self.problems(p)))
        p = copy.deepcopy(PLAN)
        p["0"] = (["gpu_particle"], {})
        got = self.problems(p)
        self.assertTrue(any("Roblox has no place" in x and "Particle effects" in x for x in got), got)
        p = copy.deepcopy(PLAN)
        p["1"] = (["mesh", "hand_drawn"], {"hand_drawn": WHY})
        self.assertTrue(any("both planned and left out" in x for x in self.problems(p)))

    def test_an_ask_method_is_used_or_left_out_with_a_reason(self):
        p = copy.deepcopy(PLAN)
        p["1"] = (["mesh"], {})
        got = self.problems(p)
        self.assertTrue(any('beat 1' in x and 'shows "flame"' in x and "hand_drawn" in x for x in got), got)
        for thin in ("", "no", "<why>", "<the reason goes here, in plain words>", "not needed", "x" * 30, "aaaa bbbb " * 1, ["a", "list", "of", "twenty", "letters"], 12345678901234567890123):
            p["1"] = (["mesh"], {"hand_drawn": thin})
            self.assertTrue(any("needs its reason" in x for x in self.problems(p)), thin)
        p["1"] = (["mesh", "hand_drawn"], {})
        self.assertEqual(self.problems(p), [])
        # a beat whose words carry no cue asks for nothing
        p = copy.deepcopy(PLAN)
        p["0"] = (["sprite"], {})
        self.assertFalse(any("beat 0" in x for x in self.problems(p)))

    def test_the_beat_sheet_gives_each_beat_its_words(self):
        words = M.beat_words(os.path.join(GOOD, "refs_measured", "ember_arc_set.beats.md"))
        self.assertEqual(sorted(words), ["0", "1", "2"])
        self.assertIn("crescent of flame", words["1"])
        self.assertNotIn("1.4-2.6", words["1"])
        # what is ON SCREEN and its shape, not the notes on motion or colour
        self.assertIn("thick crescent", words["1"])
        self.assertNotIn("a hard hit", words["1"])
        self.assertNotIn("orange", words["1"])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.beats.md")
            open(path, "w", encoding="utf-8").write("| Beat | Time | Notes |\n|---|---|---|\n| 0 a | 1-2 s | a flame |\n| 1 b | 2-3 s | dust |\n| 2 c | 3-4 s | ash |\n")
            self.assertEqual(M.beat_words(path)["0"], "0 a a flame")  # (a sheet with no such column: every cell)
        self.assertEqual(M.beat_words(os.path.join(GOOD, "no_such.md")), {})

    def test_the_snapshot_is_what_an_approval_keeps(self):
        snap = M.snapshot(chart_of(PLAN, approved=False))
        self.assertEqual(snap["1"], {"methods": ["mesh", "uv_scroll"], "not": {"hand_drawn": WHY}})
        spaced = chart_of({"1": (["mesh"], {"hand_drawn": "  the   embers are points\n of light, not drawn shapes "})}, approved=False)
        self.assertEqual(M.snapshot(spaced)["1"]["not"], {"hand_drawn": WHY})
        self.assertEqual(M.snapshot(chart_of({}, approved=False)), {})

    def test_edit_plan(self):
        P = chart_of({}, approved=False)
        self.assertIsNone(M.edit_plan(self.by, P, {"--beat": "1", "--use": "mesh, uv_scroll", "--not": [f"hand_drawn={WHY}"]}))
        self.assertEqual(M.plan_of(P)["1"]["methods"], ["mesh", "uv_scroll"])
        self.assertEqual(M.plan_of(P)["1"]["not"], {"hand_drawn": WHY})
        self.assertIsNone(M.edit_plan(self.by, P, {"--beat": "1", "--use": "hand_drawn"}))  # using it takes it out of "not"
        self.assertEqual(M.plan_of(P)["1"]["not"], {})
        self.assertIsNone(M.edit_plan(self.by, P, {"--beat": "1", "--drop": "mesh"}))
        self.assertEqual(M.plan_of(P)["1"]["methods"], ["uv_scroll", "hand_drawn"])
        self.assertIn("not a method", M.edit_plan(self.by, P, {"--beat": "1", "--use": "nonsense"}))
        self.assertIn("needs its reason", M.edit_plan(self.by, P, {"--beat": "1", "--not": ["hand_drawn=no"]}))
        self.assertIn("no beat 9", M.edit_plan(self.by, P, {"--beat": "9", "--use": "mesh"}))


class TestGate(unittest.TestCase):
    def setUp(self):
        _, self.by = M.load()

    def gate(self, plan, layers, seen="same", expanded=None, approved=True, specs=None, by="owner", raw=None):
        return M.gate(self.by, chart_of(plan, seen, approved, by), WORDS, raw or {"layers": layers}, expanded, specs or Empty(), ".", "s")

    def test_a_plan_that_is_used_passes_and_says_what_it_measured(self):
        problems, record = self.gate(PLAN, LAYERS)
        self.assertEqual(problems, [])
        self.assertEqual(record["1"]["used"], ["mesh", "uv_scroll"])

    def test_a_method_is_proved_by_a_layer_of_its_own_beat(self):
        layers = [{"kind": "sprite", "beat": 0}, {"kind": "mesh", "uvScroll": [1, 0], "beat": 0}, {"kind": "sprite", "beat": 1}, {"kind": "sprite", "beat": 2}]
        problems, _ = self.gate(PLAN, layers)
        self.assertTrue(any('beat 1 plans "UV scrolling / panning"' in x for x in problems), problems)
        self.assertTrue(any('beat 1 plans "Mesh-based effects"' in x for x in problems), problems)

    def test_a_piece_that_tags_no_beat_is_read_whole(self):
        layers = [{k: v for k, v in layer.items() if k != "beat"} for layer in LAYERS]
        problems, record = self.gate(PLAN, layers)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(record), ["0", "1", "2"])

    def test_only_the_beats_a_piece_builds_are_held(self):
        p = copy.deepcopy(PLAN)
        p["2"] = ([], {})  # beat 2 has no plan, and this piece does not build beat 2
        problems, record = self.gate(p, [layer for layer in LAYERS if layer["beat"] != 2])
        self.assertEqual(problems, [])
        self.assertEqual(sorted(record), ["0", "1"])
        problems, _ = self.gate(p, LAYERS)
        self.assertTrue(any("beat 2" in x and "names no method" in x for x in problems))

    def test_a_beat_tag_may_be_a_number_or_its_label(self):
        layers = [{"kind": "sprite", "beat": "0 glint"}, {"kind": "mesh", "uvScroll": [1, 0], "beat": 1.0}, {"kind": "sprite", "beat": "2"}]
        self.assertEqual(self.gate(PLAN, layers)[0], [])

    def test_a_parts_layers_count_by_their_uses_beat(self):
        raw = [{"kind": "sprite", "name": "a", "beat": 0}, {"kind": "sprite", "name": "b", "beat": 1}, {"kind": "sprite", "name": "c", "beat": 2}]
        self.assertTrue(self.gate(PLAN, raw)[0])
        # (VfxCompose gives a part's layers the beat of their use: "use": [{"part": ..., "beat": 1}])
        expanded = {"layers": raw + [{"kind": "mesh", "name": "ring.shell", "uvScroll": [1, 0], "beat": 1}]}
        self.assertEqual(self.gate(PLAN, raw, expanded=expanded)[0], [])
        bare = {"layers": raw + [{"kind": "mesh", "name": "ring.shell", "uvScroll": [1, 0]}]}
        problems, _ = self.gate(PLAN, raw, expanded=bare)
        self.assertTrue(any("name no beat" in x and '"beat": N' in x for x in problems), problems)
        self.assertTrue(any('beat 1 plans "UV scrolling / panning"' in x for x in problems), problems)

    def test_a_beat_the_chart_does_not_have(self):
        stray = [dict(layer, name=f"l{i}", beat=99) for i, layer in enumerate(LAYERS)]
        problems, record = self.gate(PLAN, stray)
        self.assertTrue(any("3 layer(s) name a beat the chart does not have" in x for x in problems), problems)
        self.assertTrue(any("no layer builds a beat of the chart" in x for x in problems), problems)
        self.assertEqual(record, {})
        for odd in ("1x", 1.9, -1, True, "one", [1], {"b": 1}):
            layers = [dict(LAYERS[0]), dict(LAYERS[1], beat=odd), dict(LAYERS[2])]
            problems, _ = self.gate(PLAN, layers)
            self.assertTrue(any("name a beat the chart does not have" in x for x in problems), (odd, problems))
        self.assertEqual(M.beat_tag(" 2 ", {}), "2")
        self.assertEqual(M.beat_tag("1 Crescent  of flame", {"1 crescent of flame": "1"}), "1")
        self.assertIsNone(M.beat_tag("1 crescent", {"1 crescent of flame": "1"}))

    def test_a_muted_layer_proves_nothing(self):
        raw = [dict(layer, name=f"l{i}") for i, layer in enumerate(LAYERS)]
        self.assertEqual(self.gate(PLAN, raw)[0], [])
        played = {"layers": [raw[0], raw[2]]}  # the scrolling ring is muted: it is in the file and not in what plays
        problems, _ = self.gate(PLAN, raw, expanded=played)
        self.assertTrue(any('beat 1 plans "UV scrolling / panning" and nothing that plays in that beat uses it' in x for x in problems), problems)

    def test_a_technique_key_is_read_from_before_the_expansion_only_while_its_layer_plays(self):
        plan = copy.deepcopy(PLAN)
        plan["1"] = (["mesh", "uv_scroll", "fresnel"], {"hand_drawn": WHY})
        raw = [dict(LAYERS[0], name="a"), dict(LAYERS[1], name="shell", rim={"color": [1, 1, 1]}), dict(LAYERS[2], name="c")]
        plain = [raw[0], {k: v for k, v in raw[1].items() if k != "rim"}, raw[2]]  # (VfxTech took the rim out)
        self.assertEqual(self.gate(plan, raw, expanded={"layers": plain + [{"kind": "mesh", "name": "shell_rim", "beat": 1}]})[0], [])
        gone = self.gate(plan, raw, expanded={"layers": [raw[0], raw[2]]})[0]
        self.assertTrue(any('"Fresnel / rim effects"' in x for x in gone), gone)

    def test_layers_are_not_counted_twice(self):
        self.by["__two"] = {"id": "__two", "name": "Two layers", "state": "has", "proof": [{"layers_min": 2}]}
        plan = copy.deepcopy(PLAN)
        plan["0"] = (["sprite", "__two"], {})
        raw = [dict(layer, name=f"l{i}") for i, layer in enumerate(LAYERS)]
        problems, _ = self.gate(plan, raw, expanded={"layers": raw})
        self.assertTrue(any('beat 0 plans "Two layers"' in x for x in problems), problems)

    def test_a_mesh_that_erodes_is_refused_whatever_the_plan_says(self):
        layers = [dict(LAYERS[0]), dict(LAYERS[1], name="shell", erode=[0.6, 1]), dict(LAYERS[2])]
        problems, _ = self.gate(PLAN, layers)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('1 layer(s) (shell): a mesh\'s "erode" shows in the browser player only', problems[0])
        many = [dict(LAYERS[0]), dict(LAYERS[2])] + [dict(LAYERS[1], name=f"s{i}", erode=[0.6, 1]) for i in range(5)]
        problems, _ = self.gate(PLAN, many)
        self.assertIn("5 layer(s) (s0, s1, s2 ...)", problems[0])
        # a layer the preset mutes is not held to it: it does not play
        raw = [dict(LAYERS[0], name="a"), dict(LAYERS[1], name="shell"), dict(LAYERS[1], name="old", erode=[0.6, 1]), dict(LAYERS[2], name="c")]
        self.assertEqual(self.gate(PLAN, raw, expanded={"layers": [raw[0], raw[1], raw[3]]})[0], [])

    def test_a_dissolve_sheet_on_a_mesh_without_a_surface_is_refused(self):
        specs = Fixed({"dz": {"engine": "fx", "recipe": "dissolve", "dissolve": {"pattern": "patches", "soft": 0.08}}})
        bare = [dict(LAYERS[0]), dict(LAYERS[1], name="shell", texture="dz", flipbook={"layout": "4x4", "mode": "OneShot"}), dict(LAYERS[2])]
        problems, _ = self.gate(PLAN, bare, specs=specs)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('1 layer(s) (shell): a dissolve sheet on a mesh without "surface"', problems[0])
        with_it = [bare[0], dict(bare[1], surface=1), bare[2]]
        self.assertEqual(self.gate(PLAN, with_it, specs=specs)[0], [])
        on_a_sprite = [dict(LAYERS[0], texture="dz"), dict(LAYERS[1]), dict(LAYERS[2])]   # a sprite needs no surface
        self.assertEqual(self.gate(PLAN, on_a_sprite, specs=specs)[0], [])

    def test_a_waived_plan_still_refuses_what_the_game_does_not_show(self):
        chart = chart_of({})                                    # no plan at all: the owner waived it for this piece
        eroding = [dict(LAYERS[0]), dict(LAYERS[1], name="shell", erode=[0.6, 1]), dict(LAYERS[2])]
        problems, record = M.gate(self.by, chart, WORDS, {"layers": eroding}, None, Empty(), ".", "s", refused_only=True)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('a mesh\'s "erode" shows in the browser player only', problems[0])
        self.assertEqual(record, {})
        self.assertEqual(M.gate(self.by, chart, WORDS, {"layers": LAYERS}, None, Empty(), ".", "s", refused_only=True)[0], [])
        self.assertTrue(M.gate(self.by, chart, WORDS, {"layers": LAYERS}, None, Empty(), ".", "s")[0])   # (unwaived: no plan is a problem)

    def test_a_layer_that_draws_nothing_proves_nothing(self):
        for dead in ({"transparency": 1}, {"transparency": [[0, 1], [1, 1]]}, {"scale": 0}, {"life": 0}, {"scale": [[0, [0, 0, 0]], [1, [0, 0, 0]]]}):
            layers = [dict(LAYERS[0]), dict(LAYERS[1], **dead), dict(LAYERS[2])]
            problems, _ = self.gate(PLAN, layers)
            self.assertTrue(any('beat 1 plans "Mesh-based effects"' in x for x in problems), (dead, problems))
        for alive in ({"transparency": [[0, 0.2], [1, 1]]}, {"scale": [[0, 0], [1, 2]]}, {"life": 0.4}):
            layers = [dict(LAYERS[0]), dict(LAYERS[1], **alive), dict(LAYERS[2])]
            self.assertEqual(self.gate(PLAN, layers)[0], [], alive)
        self.assertFalse(M.draws({"kind": "sprite", "count": 0}))
        self.assertTrue(M.draws({"kind": "sprite", "count": 0, "rate": 30}))
        self.assertTrue(M.draws({"kind": "shake"}))

    def test_a_key_that_does_nothing_proves_nothing(self):
        for still in ([0, 0], 0, [[0, 0], [1, 0]]):
            layers = [dict(LAYERS[0]), dict(LAYERS[1], uvScroll=still), dict(LAYERS[2])]
            problems, _ = self.gate(PLAN, layers)
            self.assertTrue(any('beat 1 plans "UV scrolling / panning"' in x for x in problems), (still, problems))
        layers = [dict(LAYERS[0]), dict(LAYERS[1], uvScroll=[-0.4, 0]), dict(LAYERS[2])]  # scrolling backwards is scrolling
        self.assertEqual(self.gate(PLAN, layers)[0], [])
        self.assertTrue(M.layer_proves({"kind": "impact", "has": ["lines"], "where_not": {"lines": ["none"]}}, {"kind": "impact", "lines": "bold"}, Empty()))
        self.assertFalse(M.layer_proves({"kind": "impact", "has": ["lines"], "where_not": {"lines": ["none"]}}, {"kind": "impact", "lines": "none"}, Empty()))

    def test_the_register_no_longer_takes_one_plain_layer_for_four_methods(self):
        plain_impact = [{"kind": "impact", "style": "frame", "lines": "none"}]
        for mid in ("halftone", "edge_detection", "speed_lines", "frame_by_frame"):
            self.assertIsNone(M.proved(self.by[mid], plain_impact, Empty(), ".", "s", "1"), mid)
        drawn = [{"kind": "impact", "lines": "bold", "draw": {"hatch": 0.4, "outline": 1}}]
        for mid in ("halftone", "edge_detection", "speed_lines", "frame_by_frame", "impact_frame"):
            self.assertIsNotNone(M.proved(self.by[mid], drawn, Empty(), ".", "s", "1"), mid)
        self.assertIsNotNone(M.proved(self.by["billboard"], [{"kind": "sprite"}], Empty(), ".", "s"))
        self.assertIsNotNone(M.proved(self.by["billboard"], [{"kind": "sprite", "orientation": "FacingCamera"}], Empty(), ".", "s"))
        self.assertIsNone(M.proved(self.by["billboard"], [{"kind": "sprite", "orientation": "VelocityParallel"}], Empty(), ".", "s"))

    def test_a_method_that_cannot_be_measured_is_said_not_refused(self):
        p = copy.deepcopy(PLAN)
        self.by["__said"] = {"id": "__said", "name": "Said only", "state": "has", "proof": []}
        p["0"] = (["sprite", "__said"], {})
        problems, record = self.gate(p, LAYERS)
        self.assertEqual(problems, [])
        self.assertEqual(record["0"], {"used": ["sprite"], "said": ["__said"]})

    def test_what_he_saw_is_not_dropped_quietly(self):
        was = copy.deepcopy(PLAN)
        was["1"] = (["mesh", "uv_scroll", "trail"], {"hand_drawn": WHY})
        problems, _ = self.gate(PLAN, LAYERS, seen=was)
        self.assertTrue(any('"Trail effects" was on the chart the owner approved and is gone' in x for x in problems), problems)
        # more than he saw is free
        more = copy.deepcopy(PLAN)
        more["1"] = (["mesh", "uv_scroll", "noise"], {"hand_drawn": WHY})
        layers = LAYERS + [{"kind": "mesh", "wobble": 1, "beat": 1}]
        self.assertEqual(self.gate(more, layers, seen=PLAN)[0], [])

    def test_a_reason_counts_once_he_has_seen_it(self):
        problems, _ = self.gate(PLAN, LAYERS, seen=None)  # an approval from before plans
        self.assertEqual(sum("is not on the chart the owner approved" in x for x in problems), 2, problems)
        without = copy.deepcopy(PLAN)
        without["1"] = (["mesh", "uv_scroll", "hand_drawn"], {})
        problems, _ = self.gate(PLAN, LAYERS, seen=without)
        self.assertTrue(any("beat 1" in x and "is not on the chart the owner approved" in x for x in problems))
        self.assertTrue(any("beat 1" in x and "is gone from the plan" in x for x in problems))
        # a chart with no approval yet: the scene gate refuses it, this one adds nothing about what he saw
        problems, _ = self.gate(PLAN, LAYERS, approved=False)
        self.assertEqual(problems, [])

    def test_only_the_owners_own_approval_holds_a_plan(self):
        for by in ("model-proposed", "owner blanket approval 2026-10-16", "", "Owner's agent"):
            problems, _ = self.gate(PLAN, LAYERS, by=by)
            self.assertEqual(sum("needs the OWNER's own approval" in x for x in problems), 2, (by, problems))
            self.assertIsNone(M.owner_saw(chart_of(PLAN, by=by)))
        self.assertEqual(self.gate(PLAN, LAYERS, by=" Owner ")[0], [])
        # a model's approval cannot clear a drop either: with no plan of the owner's, the unseen reason stands
        dropped = copy.deepcopy(PLAN)
        dropped["1"] = (["mesh"], {"hand_drawn": WHY})
        self.assertTrue(self.gate(dropped, LAYERS, by="model-proposed")[0])

    def test_the_reason_he_read_is_the_reason_that_counts(self):
        other = copy.deepcopy(PLAN)
        other["2"] = (["particle"], {"hand_drawn": "another reason entirely, written after he had read the first"})
        problems, _ = self.gate(other, LAYERS, seen=PLAN)
        self.assertTrue(any("beat 2" in x and "is not the one the owner read" in x for x in problems), problems)
        spaced = copy.deepcopy(PLAN)
        spaced["2"] = (["particle"], {"hand_drawn": "the embers  are points of light,\nnot drawn shapes"})
        self.assertEqual(self.gate(spaced, LAYERS, seen=PLAN)[0], [])

    def test_a_chart_without_numbered_beats(self):
        problems, _ = M.gate(self.by, {"beats": [{"beat": "glint"}]}, {}, {"layers": LAYERS}, None, Empty(), ".", "s")
        self.assertTrue(problems)


class TestFixtures(unittest.TestCase):
    """the selftest's fixtures through the gate's own command (kit selftest runs them through the build step)"""

    def test_the_good_one_passes(self):
        got = gate_of(GOOD, "preset_methods_whole")
        self.assertEqual(got["problems"], [])
        self.assertEqual(got["beats"]["1"]["used"], ["mesh", "uv_scroll", "hand_drawn"])

    def test_each_bad_one_is_refused_for_its_own_reason(self):
        uses = "and nothing that plays in that beat uses it"
        want = {"noplan": 'beat 0 ("glint") names no method', "unused": f'beat 1 plans "UV scrolling / panning" {uses}',
                "ask": 'beat 1 ("crescent of flame") shows "flame"', "dropped": "was on the chart the owner approved and is gone from the plan",
                "unseen": "is not on the chart the owner approved", "missing": '"A made method the kit has not built" is not built in the kit yet',
                "fakeink": f'beat 1 plans "Hand-drawn effects animation" {uses}', "stray": "4 layer(s) name a beat the chart does not have",
                "dead": f'beat 1 plans "Hand-drawn effects animation" {uses}', "model": "needs the OWNER's own approval of the chart that shows the reason",
                "rewritten": "is not the one the owner read on the chart he approved"}
        for case, needle in want.items():
            got = gate_of(BAD, f"preset_methods_{case}")
            self.assertTrue(any(needle in p for p in got["problems"]), (case, got["problems"]))

    def test_the_dissolve_fixtures(self):
        got = gate_of(DZ_GOOD, "preset_dissolve_baked")
        self.assertEqual(got["problems"], [])
        self.assertEqual(got["beats"]["1"]["used"], ["mesh", "dissolve"])
        erode = gate_of(DZ_BAD, "preset_dissolve_erode")["problems"]
        self.assertTrue(any('1 layer(s) (arc_ring): a mesh\'s "erode" shows in the browser player only' in p and "kit vfx dissolve" in p for p in erode), erode)
        unbaked = gate_of(DZ_BAD, "preset_dissolve_unbaked")["problems"]
        self.assertTrue(any('beat 1 plans "Dissolve effects" and nothing that plays in that beat uses it' in p for p in unbaked), unbaked)

    def test_the_gate_command_under_a_waiver(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            M.main(["--gate", "--refused-only", "--effects", DZ_BAD, "--name", "preset_dissolve_erode", "--textures", os.path.join(DZ_BAD, "textures")])
            M.main(["--gate", "--refused-only", "--effects", DZ_BAD, "--name", "preset_dissolve_unbaked", "--textures", os.path.join(DZ_BAD, "textures")])
            M.main(["--gate", "--refused-only", "--effects", BAD, "--name", "preset_methods_noplan", "--textures", os.path.join(BAD, "textures")])
        erode, unbaked, noplan = [json.loads(ln)["problems"] for ln in buf.getvalue().splitlines()]
        self.assertTrue(len(erode) == 1 and "erode" in erode[0], erode)
        self.assertEqual(unbaked, [])     # an unused plan is the plan's business: waived
        self.assertEqual(noplan, [])

    def test_a_variant_is_held_as_it_plays(self):
        raw = json.load(open(os.path.join(GOOD, "preset_methods_whole.json"), encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            whole, cut = os.path.join(tmp, "whole.json"), os.path.join(tmp, "cut.json")
            json.dump(raw, open(whole, "w"))
            json.dump(dict(raw, layers=[layer for layer in raw["layers"] if layer["name"] != "arc_drawn"]), open(cut, "w"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                M.main(["--gate", "--effects", GOOD, "--name", "preset_methods_whole", "--textures", os.path.join(GOOD, "textures"),
                        "--expanded", f"={whole}", "--expanded", f"night={cut}"])
            got = json.loads(buf.getvalue().splitlines()[-1])
            self.assertEqual(len(got["problems"]), 1, got["problems"])
            self.assertTrue(got["problems"][0].startswith('variant night: beat 1 plans "Hand-drawn effects animation"'))
            self.assertEqual(sorted(got["plays"]), ["night", "preset"])

    def test_the_gate_never_throws(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = gate_of(tmp, "nothing_here")
            self.assertTrue(got["problems"] and "could not read" in got["problems"][0])
            json.dump({"layers": [], "scene": {"set": "s"}}, open(os.path.join(tmp, "p.json"), "w"))
            got = gate_of(tmp, "p")
            self.assertIn("no method plan", got["problems"][0])
            json.dump({"layers": []}, open(os.path.join(tmp, "q.json"), "w"))
            self.assertEqual(gate_of(tmp, "q")["problems"], [])
            os.makedirs(os.path.join(tmp, "refs_measured"))
            open(os.path.join(tmp, "refs_measured", "s.chart.json"), "w").write("[1, 2]")
            self.assertTrue(gate_of(tmp, "p")["problems"])


class TestCommand(unittest.TestCase):
    def test_the_list_and_a_find(self):
        code, verdict, lines = run([])
        self.assertEqual((code, verdict["status"], len(lines)), (0, "pass", 104))
        self.assertEqual(sum(verdict["counts"].values()), 104)
        code, verdict, lines = run(["hand-drawn", "effects"])
        self.assertEqual(code, 0)
        self.assertIn("Hand-drawn effects animation", lines[0])
        self.assertTrue(any("kit vfx ink" in ln for ln in lines))
        code, verdict, _ = run(["zzzz"])
        self.assertEqual((code, verdict["status"]), (1, "fail"))

    def test_a_sets_plan_is_shown_and_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(BAD, "refs_measured"), os.path.join(tmp, "refs_measured"))
            code, verdict, lines = run(["--set", "m_noplan_set", "--effects", tmp])
            self.assertEqual((code, verdict["status"]), (1, "fail"))
            self.assertTrue(any('its words say "flame": ASK Hand-drawn effects animation' in ln for ln in lines), lines)
            run(["--set", "m_noplan_set", "--effects", tmp, "--beat", "0", "--use", "sprite,flipbook"])
            run(["--set", "m_noplan_set", "--effects", tmp, "--beat", "1", "--use", "mesh", "--not", f"hand_drawn={WHY}"])
            code, verdict, lines = run(["--set", "m_noplan_set", "--effects", tmp, "--beat", "2", "--use", "particle", "--not", f"hand_drawn={WHY}"])
            self.assertEqual((code, verdict["status"]), (0, "pass"), verdict)
            P = json.load(open(os.path.join(tmp, "refs_measured", "m_noplan_set.chart.json"), encoding="utf-8"))
            self.assertEqual(P["beats"][1]["methods"], ["mesh"])
            self.assertEqual(P["beats"][1]["not"], {"hand_drawn": WHY})
            self.assertEqual(P["approved"]["plan"], CHART.plan_key(P))  # the timing he approved is untouched
            code, verdict, _ = run(["--set", "m_noplan_set", "--effects", tmp, "--beat", "1", "--use", "nonsense"])
            self.assertEqual(code, 1)
            code, verdict, _ = run(["--set", "no_such_set", "--effects", tmp])
            self.assertEqual((code, verdict["status"]), (1, "fail"))
            code, verdict, _ = run(["--set"])
            self.assertEqual((code, verdict["status"]), (1, "fail"))


class TestChart(unittest.TestCase):
    """the chart draws the plan, and its approval is for the picture that shows it"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_methods_chart_")
        shutil.copytree(os.path.join(GOOD, "refs_measured"), os.path.join(self.tmp, "refs_measured"))
        self.measured = os.path.join(self.tmp, "refs_measured")
        self.keep = (CHART.OUT, CHART.MEASURED, CHART.EFFECTS)
        CHART.OUT = os.path.join(self.tmp, "charts")

    def tearDown(self):
        CHART.OUT, CHART.MEASURED, CHART.EFFECTS = self.keep
        shutil.rmtree(self.tmp, ignore_errors=True)

    def chart(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = CHART.main(["ember_arc_set", "--measured", self.measured, *argv])
        return code, json.loads(buf.getvalue().splitlines()[-1])

    def plan(self):
        return json.load(open(os.path.join(self.measured, "ember_arc_set.chart.json"), encoding="utf-8"))

    def test_the_rows_say_the_plan_in_his_words(self):
        _, by = M.load()
        rows = CHART.method_lines(self.plan(), by, 40)
        self.assertEqual(len(rows), 3)
        text = [" ".join(ln for ln, _ in row) for row in rows]
        self.assertIn("Mesh-based effects", text[1])
        self.assertIn("Hand-drawn effects animation", text[1])
        self.assertTrue(any(left for _, left in rows[2]))
        self.assertIn("NOT Hand-drawn effects animation: the embers are points", text[2])
        bare = CHART.method_lines({"beats": [{"beat": "0 x"}]}, by, 40)
        self.assertIn("NO METHOD PLANNED", bare[0][0][0])

    def test_the_picture_grows_to_hold_the_plan_and_records_it(self):
        from PIL import Image
        code, verdict = self.chart()
        self.assertEqual(code, 0, verdict)
        made = json.load(open(os.path.join(CHART.OUT, "ember_arc_set.drawn.json"), encoding="utf-8"))
        self.assertEqual(made["methods"], M.snapshot(self.plan()))
        tall = Image.open(os.path.join(CHART.OUT, "ember_arc_set.png")).size[1]
        P = self.plan()
        for row in P["beats"]:
            row.pop("methods", None)
            row.pop("not", None)
        json.dump(P, open(os.path.join(self.measured, "ember_arc_set.chart.json"), "w", encoding="utf-8"))
        code, verdict = self.chart()
        self.assertIn("method plan has", verdict["summary"])
        self.assertLess(Image.open(os.path.join(CHART.OUT, "ember_arc_set.png")).size[1], tall)

    def test_an_approval_keeps_the_plan_he_saw(self):
        P = self.plan()
        P.pop("approved")
        json.dump(P, open(os.path.join(self.measured, "ember_arc_set.chart.json"), "w", encoding="utf-8"))
        # no picture drawn on this machine: nothing he could have seen
        code, verdict = self.chart("--approve", "yes, build it", "--by", "owner")
        self.assertEqual(code, 1)
        self.assertIn("does not show this chart's method plan", verdict["summary"])
        self.assertNotIn("approved", self.plan())
        self.chart()
        code, verdict = self.chart("--approve", "yes, build it", "--by", "owner")
        self.assertEqual(code, 0, verdict)
        self.assertEqual(self.plan()["approved"]["methods"], M.snapshot(self.plan()))
        self.assertEqual(self.plan()["approved"]["by"], "owner")

    def test_a_models_approval_holds_no_plan(self):
        P = self.plan()
        P.pop("approved")
        json.dump(P, open(os.path.join(self.measured, "ember_arc_set.chart.json"), "w", encoding="utf-8"))
        self.chart()
        code, verdict = self.chart("--approve", "looks right to me")
        self.assertEqual(code, 0, verdict)
        self.assertEqual(self.plan()["approved"]["by"], "model-proposed")
        self.assertNotIn("methods", self.plan()["approved"])
        self.assertIsNone(M.owner_saw(self.plan()))

    def test_a_replan_keeps_each_beats_method_plan(self):
        before = M.plan_of(self.plan())
        code, verdict = self.chart("--replan", "1", "--duration", "3")
        after = self.plan()
        self.assertEqual(after["duration"], 3.0)
        self.assertNotIn("approved", after)
        self.assertEqual({b: (p["methods"], p["not"]) for b, p in M.plan_of(after).items()}, {b: (p["methods"], p["not"]) for b, p in before.items()})

    def test_a_plan_changed_after_the_picture_is_not_approved_from_it(self):
        self.chart()
        P = self.plan()
        P.pop("approved")
        P["beats"][2]["not"] = {"hand_drawn": "another reason, written after the picture was drawn"}
        P["beats"][1]["methods"] = ["mesh"]
        json.dump(P, open(os.path.join(self.measured, "ember_arc_set.chart.json"), "w", encoding="utf-8"))
        code, verdict = self.chart("--approve", "yes", "--by", "owner")
        self.assertEqual(code, 1)
        self.assertIn("drawn before the plan was as it is now", verdict["summary"])
        self.assertNotIn("approved", self.plan())

    def test_a_chart_with_no_plan_is_approved_as_before(self):
        P = self.plan()
        P.pop("approved")
        for row in P["beats"]:
            row.pop("methods", None)
            row.pop("not", None)
        json.dump(P, open(os.path.join(self.measured, "ember_arc_set.chart.json"), "w", encoding="utf-8"))
        code, verdict = self.chart("--approve", "yes", "--by", "owner")
        self.assertEqual(code, 0, verdict)
        self.assertNotIn("methods", self.plan()["approved"])


if __name__ == "__main__":
    unittest.main()


class TestBaked(unittest.TestCase):
    def test_a_texture_proves_its_method_only_when_it_was_baked(self):
        """a review leftover of stage 25: a texture spec written by hand and never baked proved its methods (the game
        draws its fallback) - with a registry in the effects folder, the texture must be in it"""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(M.baked(tmp, "anything"))                       # no registry: a made folder is not asked
            with open(os.path.join(tmp, "_textures.json"), "w", encoding="utf-8") as fh:
                json.dump({"sheet_a": {"id": "rbxassetid://1"}}, fh)
            self.assertTrue(M.baked(tmp, "sheet_a"))
            self.assertFalse(M.baked(tmp, "sheet_b"))                      # a spec that was never packed
            alt = {"kind": "sprite", "texture": {}}
            layer = {"kind": "sprite", "texture": "sheet_b"}
            self.assertFalse(M.layer_proves(alt, layer, {"sheet_b": {"recipe": "x"}}, tmp))
            self.assertTrue(M.layer_proves(alt, dict(layer, texture="sheet_a"), {"sheet_a": {"recipe": "x"}}, tmp))
