"""kit ui direct (v8, the creative director): the owner's loaded words are read through the lexicon; a brief is refused
when it is a wish (a wish-word big idea, two directions the same on the axes, palettes too close, a re-skin of an
identity, an owner word left unread); the board draws a sketch frame per direction; a pick without --by owner is only a
proposal; a NEW identity needs an owner-picked direction (older ones exempt, an owner waiver passes)"""
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "..", "ui")
sys.path.insert(0, UI)
_spec = importlib.util.spec_from_file_location("kit_ui_direct", os.path.join(UI, "direct.py"))
direct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(direct)


def direction(key, axes, pal, display, title):
    return {
        "key": key, "title": title,
        "big_idea": f"the HUD IS the {title.lower()} of the station: every fighter is a line on it",
        "world_object": "station signage", "axes": dict(zip(("space", "volume", "material", "voice"), axes)),
        "medium": "enamel signs and hairline rules", "verb": "slides on rails and snaps to the grid",
        "signature_moment": {"name": "Suspended", "beats": [["0.00", "every roundel drops to grey"], ["0.12", "the board flips row by row"],
                                                            ["0.35", "a red band closes across the screen"]]},
        "only_here": "the crossing sits on top of the station where the arc's fights happen",
        "type_voice": {"display": display, "body": "RobotoCondensed"},
        "palette": dict(pal, why="taken from the line colours of the metro"),
        "screens": {"hud": "a roundel and a departure board with exits"},
        "roblox": "flat frames with strokes and a glyph set", "risk": "it can read too calm for a brawler",
        "sources": [{"what": "Tokyo Metro signage", "kind": "signage"}, {"what": "JR departure boards", "kind": "signage"},
                    {"what": "JJK season 2 platform fight", "kind": "anime"}],
        "not": ["not neon cyberpunk", "not a puzzle game clone"],
        "frame": {"elements": [{"kind": "rect", "box": [10, 10, 200, 60], "fill": "accent"},
                               {"kind": "text", "at": [20, 20], "text": "F07 » A1", "font": "display", "size": 30, "color": "ink"}]},
    }


def brief():
    return {
        "name": "t", "game": None, "ask": "make a sick hud, original", "screens": ["hud"],
        "context": {"pitch": "a scramble crossing at night", "world_objects": ["video wall", "street lamps"]},
        "reading": {"fantasy": "a sorcerer on the worst night", "player": "battlegrounds players on phones and PC",
                    "moment_of_use": "glances between combos mid fight", "assumptions": [],
                    "words": [{"id": "cooler", "words": ["sick"], "here": "one signature moment in motion per direction"},
                              {"id": "original", "words": ["original"], "here": "objects of this world, no genre swap at all"}]},
        "directions": [
            direction("A", ("screen", "quiet", "signage", "system"), {"ground": "#15181d", "ink": "#f4f4f0", "accent": "#f39700", "support": "#9c5e31"}, "GothamBlack", "Wayfinding"),
            direction("B", ("screen", "loud", "paper", "character"), {"ground": "#efe6d2", "ink": "#0b0a09", "accent": "#d7261e", "support": "#6b5b45"}, "PermanentMarker", "Talisman"),
            direction("C", ("hybrid", "loud", "pixels", "observer"), {"ground": "#030304", "ink": "#ffffff", "accent": "#ffe600", "support": "#0071bc"}, "Oswald", "Broadcast"),
        ],
        "recommendation": {"key": "B", "why": "it comes straight from the arc's own world and its medium"},
    }


class InTemp(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        os.makedirs(os.path.join("assets", "ui", "identities"))

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()


class TestReading(unittest.TestCase):
    def test_loaded_words(self):
        ids = lambda s: sorted(w["id"] for w in direct.loaded_words(s))  # noqa: E731
        self.assertEqual(ids("make a sick hud like jjk"), ["cooler", "like-a-game"])
        self.assertEqual(ids("i like it, keep it realistic"), ["realistic"])
        self.assertIn("persona", ids("something like Persona 5"))
        self.assertEqual(ids("would like a menu"), [])


class TestCheck(InTemp):
    def errs(self, b):
        return direct.check_brief(b)[0]

    def test_a_design_passes(self):
        self.assertEqual(self.errs(brief()), [])

    def test_a_wish_word_is_refused(self):
        b = brief()
        b["directions"][0]["big_idea"] = "a sleek modern HUD is what it is"
        self.assertTrue(any("wish" in e for e in self.errs(b)))

    def test_the_same_idea_twice(self):
        b = brief()
        b["directions"][2]["axes"] = dict(b["directions"][1]["axes"])
        self.assertTrue(any("the same idea twice" in e for e in self.errs(b)))

    def test_palettes_too_close(self):
        b = brief()
        b["directions"][2]["palette"] = dict(b["directions"][0]["palette"])
        self.assertTrue(any("too close" in e for e in self.errs(b)))

    def test_a_reskin_of_an_identity(self):
        with open(os.path.join("assets", "ui", "identities", "old.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": "old", "tokens": {"bg": "#16191e", "accent": "#f29800"}}, fh)
        self.assertTrue(any("re-skin" in e and "old" in e for e in self.errs(brief())))

    def test_an_owner_word_left_unread(self):
        b = brief()
        b["ask"] = "make it realistic and sick, original"
        self.assertTrue(any("realistic" in e for e in self.errs(b)))

    def test_no_source_outside_games(self):
        b = brief()
        b["directions"][0]["sources"] = [{"what": "Mini Metro menus", "kind": "game"}, {"what": "Apex Legends HUD", "kind": "game"},
                                         {"what": "Valorant kill banner", "kind": "game"}]
        self.assertTrue(any("outside games" in e for e in self.errs(b)))

    def test_too_few_beats_and_unknown_font(self):
        b = brief()
        b["directions"][1]["signature_moment"]["beats"] = [["0.0", "a flash happens here"]]
        b["directions"][1]["type_voice"]["display"] = "Comic Sans"
        e = self.errs(b)
        self.assertTrue(any("timed beats" in x for x in e))
        self.assertTrue(any("not a Roblox font" in x for x in e))

    def test_two_directions_are_not_enough(self):
        b = brief()
        b["directions"] = b["directions"][:2]
        self.assertTrue(any("3-5" in e for e in self.errs(b)))


class TestBoardAndPick(InTemp):
    def write(self, b):
        p = os.path.join("assets", "ui", "directions", "t.json")
        direct.save(p, b)
        return p

    def test_board_draws_every_direction(self):
        self.write(brief())
        rc = direct.main(["board", "t"])
        self.assertEqual(rc, 0)
        for k in "ABC":
            self.assertTrue(os.path.isfile(os.path.join("build", "ui", "directions", "project", "t", f"{k}.jpg")))
        page = open(os.path.join("build", "ui", "directions", "project", "t", "board.html"), encoding="utf-8").read()
        self.assertIn("make a sick hud, original", page)
        self.assertEqual(page.count("<section"), 3)

    def test_pick_needs_the_owner(self):
        p = self.write(brief())
        direct.main(["pick", "t", "B", "nice", "--lune", ""])
        d = json.load(open(p, encoding="utf-8"))
        self.assertIsNone(d.get("pick"))
        self.assertEqual(d["proposal"]["key"], "B")
        self.assertFalse(os.path.isfile(os.path.join("assets", "ui", "identities", "talisman.json")))

    def test_owner_pick_drafts_an_identity_that_passes_the_lock(self):
        self.write(brief())
        direct.main(["pick", "t", "B", "this one", "--by", "owner", "--identity", "veil", "--lune", ""])
        ip = os.path.join("assets", "ui", "identities", "veil.json")
        ident = json.load(open(ip, encoding="utf-8"))
        self.assertEqual(ident["direction"], {"brief": "t", "key": "B", "game": None})
        self.assertEqual(ident["tokens"]["bg"], "#efe6d2")
        self.assertEqual(ident["fonts"]["titleFont"], "PermanentMarker")
        self.assertTrue(direct.direction_lock("veil", ip)[0])
        # an identity that follows a direction the owner did NOT pick is locked
        other = copy.deepcopy(ident)
        other["direction"]["key"] = "C"
        op = os.path.join("assets", "ui", "identities", "other.json")
        direct.save(op, other)
        self.assertFalse(direct.direction_lock("other", op)[0])

    def test_the_lock(self):
        ip = os.path.join("assets", "ui", "identities", "fresh.json")
        direct.save(ip, {"name": "fresh", "tokens": {}})
        ok, detail, todo = direct.direction_lock("fresh", ip)
        self.assertFalse(ok)
        self.assertIn("kit ui direct new", todo)
        field = os.path.join("assets", "ui", "identities", "field.json")
        self.assertTrue(direct.direction_lock("field", field)[0])  # (made before the director: exempt by its PATH)
        # the same name in a game folder is a NEW identity: not exempt
        g = os.path.join("games", "G", "assets", "ui", "identities", "field.json")
        direct.save(g, {"name": "field"})
        self.assertFalse(direct.direction_lock("field", g)[0])
        os.makedirs("board")
        with open(os.path.join("board", "locks.json"), "w", encoding="utf-8") as fh:
            json.dump({"waivers": {"ui": {"fresh": {"by": "owner", "words": "go", "steps": ["direction"]}}}}, fh)
        self.assertTrue(direct.direction_lock("fresh", ip)[0])


class TestReviewFindings(InTemp):
    """the fresh review of 2026-10-24: each hole it found stays closed"""

    def errs(self, b):
        return direct.check_brief(b)[0]

    def test_design_is_not_signage(self):
        b = brief()
        for x in b["directions"]:
            x["sources"] = [{"what": "a game design doc", "kind": "game design"}, {"what": "Apex Legends HUD", "kind": "game"},
                            {"what": "the template kind", "kind": "game|anime|film|print|signage|..."}]
        self.assertTrue(any("outside games" in e for e in self.errs(b)))

    def test_a_sentence_with_is_is_not_a_metaphor(self):
        b = brief()
        b["directions"][0]["big_idea"] = "This is a HUD."
        self.assertTrue(any("not a metaphor" in e for e in self.errs(b)))

    def test_the_template_only_here_is_refused(self):
        b = brief()
        b["directions"][0]["only_here"] = direct.TEMPLATE_ONLY_HERE
        self.assertTrue(any("only_here" in e for e in self.errs(b)))

    def test_repick_and_the_lock_binds_the_identity(self):
        p = os.path.join("assets", "ui", "directions", "t.json")
        direct.save(p, brief())
        direct.main(["pick", "t", "B", "this one", "--by", "owner", "--identity", "veil", "--lune", ""])
        self.assertEqual(self.errs(json.load(open(p, encoding="utf-8"))), [])  # (its own draft is no re-skin)
        direct.main(["pick", "t", "C", "no, this one", "--by", "owner", "--identity", "veil", "--lune", ""])
        ip = os.path.join("assets", "ui", "identities", "veil.json")
        self.assertEqual(json.load(open(ip, encoding="utf-8"))["direction"]["key"], "C")
        self.assertTrue(direct.direction_lock("veil", ip)[0])
        # a hand-written identity claiming the same pick is locked
        fake = os.path.join("assets", "ui", "identities", "fake.json")
        direct.save(fake, {"name": "fake", "direction": {"brief": "t", "key": "C", "game": None}})
        self.assertFalse(direct.direction_lock("fake", fake)[0])
        # a brief of the same name in a game does not open a root identity's lock
        other = os.path.join("assets", "ui", "identities", "x.json")
        direct.save(other, {"name": "x", "direction": {"brief": "t", "key": "C", "game": "G"}})
        self.assertFalse(direct.direction_lock("x", other)[0])

    def test_pick_refuses_an_unrelated_identity(self):
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), brief())
        souls = os.path.join("assets", "ui", "identities", "souls.json")
        direct.save(souls, {"name": "souls", "tokens": {"bg": "#000000"}})
        self.assertEqual(direct.main(["pick", "t", "B", "yes", "--by", "owner", "--identity", "souls", "--lune", ""]), 1)
        self.assertEqual(json.load(open(souls, encoding="utf-8"))["tokens"]["bg"], "#000000")

    def test_a_broken_element_is_skipped_not_fatal(self):
        b = brief()
        b["directions"][0]["frame"]["elements"].append({"kind": "rect"})
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), b)
        self.assertEqual(direct.main(["board", "t"]), 0)


class TestReel(InTemp):
    def test_state_in_out_wipe_pulse(self):
        import direct_reel as R
        el = {"t": [0.2, 1.0], "in": {"dur": 0.2, "from": {"alpha": 0, "dx": -100, "scale": 2}, "ease": "linear"},
              "out": {"dur": 0.2, "to": {"alpha": 0}, "ease": "linear"}}
        self.assertFalse(R.state(el, 0.1, 1.5)[0])                      # before its window
        vis, a, dx, dy, sc, rv = R.state(el, 0.3, 1.5)                   # half way in
        self.assertTrue(vis)
        self.assertAlmostEqual(a, 0.5, 2)
        self.assertAlmostEqual(dx, -50, 1)
        self.assertAlmostEqual(sc, 1.5, 2)
        self.assertAlmostEqual(R.state(el, 0.6, 1.5)[1], 1.0, 3)         # at rest
        self.assertAlmostEqual(R.state(el, 0.9, 1.5)[1], 0.5, 2)         # half way out
        self.assertFalse(R.state(el, 1.2, 1.5)[0])                      # gone
        wipe = {"t": [0, 1], "wipe": {"dur": 0.4, "ease": "linear"}}
        self.assertAlmostEqual(R.state(wipe, 0.2, 1)[5], 0.5, 2)
        self.assertGreater(R.ease(0.5, "back"), 0.5)

    def test_a_timed_moment_renders_a_reel_and_a_strip(self):
        b = brief()
        x = b["directions"][1]
        x["frame"]["elements"].append({"kind": "stamp", "center": [960, 540], "r": 120, "text": "X", "font": "display", "size": 90,
                                       "color": "accent", "t": [0.1, 0.9], "in": {"dur": 0.2, "from": {"scale": 2.0, "alpha": 0}}})
        x["frame"]["reel"] = {"duration": 0.9, "fps": 10, "events": [{"t": 0.0, "dur": 0.1, "kind": "invert"}, {"t": 0.1, "dur": 0.2, "kind": "shake"}]}
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), b)
        self.assertEqual(direct.main(["reel", "t", "B"]), 0)
        from PIL import Image
        with Image.open(os.path.join("build", "ui", "directions", "project", "t", "B.reel.gif")) as gif:
            total = 0
            for i in range(gif.n_frames):  # (identical frames merge; their durations add up: the clock holds)
                gif.seek(i)
                total += gif.info.get("duration", 0)
            self.assertGreaterEqual(gif.n_frames, 3)
            self.assertAlmostEqual(total, 900, delta=60)
        self.assertTrue(os.path.isfile(os.path.join("build", "ui", "directions", "project", "t", "B.strip.jpg")))
        # a still-only brief says so instead of rendering nothing silently
        self.assertEqual(direct.main(["reel", "t", "A"]), 1)
        self.assertTrue(any("is a still" in w for w in direct.check_brief(b)[1]))


class TestSparkCritiqueNames(InTemp):
    def test_sparks_are_grounded_varied_and_skip_used_media(self):
        import direct_spark as SP
        b = brief()
        b["directions"][0]["medium"] = "a railway departure board"
        b["context"]["world_objects"] = ["video wall", "street lamps", "car", "skyline"]
        got = SP.sparks(b, n=10, seed=1)
        self.assertEqual(len(got), 10)
        source = [g.get("medium") or g.get("craft") for g in got]
        self.assertEqual(len(set(source)), 10)                                      # no medium or craft twice
        self.assertTrue(all(g["object"] in ("video wall", "street lamps", "car", "skyline") for g in got))  # the world's own things
        self.assertFalse(any("departure board" in s_ for s_ in source))            # already used by a direction
        crafts = [g for g in got if g.get("craft")]
        self.assertTrue(crafts and all(len(g["process"].split()) >= 5 for g in crafts))  # the animation IS a real process
        self.assertTrue(0.3 <= SP.craft_share() <= 0.85)
        self.assertEqual(SP.sparks(b, 10, 1), got)                                 # a seed repeats

    def test_critique_round_trip(self):
        import direct_critique as CR
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), brief())
        self.assertEqual(direct.main(["critique", "t", "--seed", "3"]), 0)
        out = os.path.join("build", "judge", "ui", "directions", "project", "t")
        key = json.load(open(os.path.join(out, "key.json"), encoding="utf-8"))
        doc = open(os.path.join(out, "brief.md"), encoding="utf-8").read()
        for x in brief()["directions"]:
            self.assertNotIn(x["title"], doc)                                      # blind: no titles
        ans = os.path.join(out, "answers.json")
        json.dump({"ranking": [3, 1, 2], "notes": {"3": {"cliche": "a station sign", "remember": "the band", "stronger": "doors"}}},
                  open(ans, "w", encoding="utf-8"))
        self.assertEqual(direct.main(["critique", "t", "--record", ans, "--judge", "j"]), 0)
        d = json.load(open(os.path.join("assets", "ui", "directions", "t.json"), encoding="utf-8"))
        self.assertEqual(d["critiques"][0]["ranking"][0], key["3"])
        self.assertEqual(d["critiques"][0]["notes"][key["3"]]["cliche"], "a station sign")
        json.dump({"ranking": [1, 1, 2]}, open(ans, "w", encoding="utf-8"))
        self.assertEqual(direct.main(["critique", "t", "--record", ans]), 1)      # every direction once

    def test_borrowed_names_are_refused(self):
        b = brief()
        b["ask"] = "a hud like jjk, original and sick"
        b["reading"]["words"].append({"id": "like-a-game", "words": ["like jjk"], "here": "its real frames, our own shapes and names"})
        self.assertTrue(any("source_names" in e for e in direct.check_brief(b)[0]))
        b["context"]["source_names"] = ["Black Flash", "Itadori", "Journey"]
        self.assertTrue(any("source_moves" in e for e in direct.check_brief(b)[0]))   # names need the moves too
        b["context"]["source_moves"] = ["a call that ripples out in rings from your feet"]
        self.assertEqual(direct.check_brief(b)[0], [])
        b["directions"][0]["verb"] = "a call ripples out in rings from your feet"
        self.assertTrue(any("repeats the source's own move" in w for w in direct.check_brief(b)[1]))
        b["directions"][0]["big_idea"] += ", a map of your journey"                    # the word, not the game
        self.assertEqual(direct.check_brief(b)[0], [])
        b["directions"][1]["frame"]["elements"].append({"kind": "text", "at": [0, 0], "text": "BLACK FLASH"})
        self.assertTrue(any("source's own name 'Black Flash'" in e for e in direct.check_brief(b)[0]))


class TestStripAndMovement(unittest.TestCase):
    def test_the_strip_shows_each_beat_settled(self):
        import direct_reel as R
        beats = [["0.00", "a"], ["0.30", "b"], ["0.60", "c"], ["0.66", "d"], ["1.40", "e"]]
        picks = R.strip_picks(beats, 24, 58)
        self.assertEqual(len(picks), 6)
        self.assertEqual(picks[-1], 57)                    # the final rest
        self.assertIn(15, picks)                           # the short 0.60-0.66 beat (the crack) survives
        self.assertNotIn(56, picks)                        # a near-duplicate of the end goes first
        self.assertEqual(len(R.strip_picks([["0", "a"]], 10, 9)), 6)

    def test_movement_between_rounds(self):
        import direct_critique as CR
        rounds = [{"ranking": ["A", "C", "D", "B"]}, {"ranking": ["A", "B", "C", "E", "D"]}]
        m = CR.movement(rounds)
        self.assertIn("B up", m)
        self.assertIn("E new", m)
        self.assertIn("D down", m)
        self.assertIn("noisy", m)
        self.assertEqual(CR.movement(rounds[:1]), "")
        # two judges in one round are averaged: a single judge's swing is damped
        multi = [{"ranking": ["A", "B", "C"], "round": "1"}, {"ranking": ["B", "A", "C"], "round": "1"},
                 {"ranking": ["C", "A", "B"], "round": "2"}, {"ranking": ["A", "C", "B"], "round": "2"}]
        m2 = CR.movement(multi)
        self.assertIn("C up", m2)
        self.assertIn("2 vs 2 judge(s)", m2)
        self.assertNotIn("noisy", m2)


class TestMoodAndNames(unittest.TestCase):
    def test_mood_words_need_a_reading(self):
        b = brief()
        b["ask"] = "make it feel magical, journey vibes, original"
        e = direct.check_brief(b)[0]
        self.assertTrue(any("'magical'" in x for x in e))
        self.assertTrue(any("'vibes'" in x for x in e))
        b["reading"]["words"] += [{"id": "mood:magical", "here": "the world answers you, never sparkles"},
                                  {"id": "mood:vibes", "here": "the feeling of a wordless pilgrimage only"}]
        self.assertFalse(any("mood" in x or "'magical'" in x for x in direct.check_brief(b)[0]))

    def test_lexicon_synonyms(self):
        ids = sorted(w["id"] for w in direct.loaded_words("its own thing, no clutter"))
        self.assertEqual(ids, ["original", "simple"])

    def test_world_object_names(self):
        self.assertEqual(direct.split_name("GlyphA"), "glyph")
        self.assertEqual(direct.split_name("BuriedTowerB"), "buried tower")
        self.assertEqual(direct.split_name("VideoWall3"), "video wall")
        self.assertEqual(direct.split_name("Marker_3"), "marker")


class TestSwap(InTemp):
    def test_a_direction_that_fits_another_game_is_flagged(self):
        for g, pitch in (("Home", "a frozen lake and a timber hall"), ("Other", "a jungle temple with a jade relic and a cascade")):
            os.makedirs(os.path.join("games", g))
            with open(os.path.join("games", g, "GAME.md"), "w", encoding="utf-8") as fh:
                fh.write(f"# {g}\n\n## Pitch\n{pitch}\n\n## Core loop\nx\n")
        b = brief()
        b["game"] = "Home"
        x = b["directions"][0]
        x["big_idea"] = "the HUD IS the jade relic of the jungle temple: it glows"
        x["world_object"] = "the jade relic in the temple"
        x["only_here"] = "the cascade and the jade relic of the temple make it"
        self.assertEqual(direct.swappable(b, x), "Other")
        x["big_idea"] = "the HUD IS the frozen lake under the timber hall"
        x["world_object"] = "the frozen lake"
        x["only_here"] = "the frozen lake by the timber hall"
        self.assertIsNone(direct.swappable(b, x))


class TestSources(InTemp):
    def test_gather_plan(self):
        b = brief()
        b["directions"][1]["sources"] = [{"what": "Apex Legends", "kind": "game", "look_for": "the kill banner timing"},
                                         {"what": "kintsugi pottery", "kind": "craft", "look_for": "gold following a crack"}]
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), b)
        cmds = direct.gather_plan(b, b["directions"][1], "veil")
        self.assertIn('lune run kit ui refs veil "Apex Legends" "kill banner timing"', cmds[0])
        self.assertTrue(cmds[1].endswith("--wiki commons.wikimedia.org"))
        self.assertIn("gold following crack", cmds[1])
        self.assertEqual(direct.main(["sources", "t"]), 1)          # nothing picked: refused
        self.assertEqual(direct.main(["sources", "t", "B"]), 0)     # a named direction: a preview


class TestMaterials(unittest.TestCase):
    def test_chladni_and_branch_draw_real_forms(self):
        pal = {"ink": "#ffffff", "accent": "#ff8800"}
        ch = direct.draw_element({"kind": "chladni", "center": [960, 540], "r": 300, "ry": 300, "n": 3, "m": 5}, pal, {})
        px = sum(1 for v in ch.getchannel("A").getdata() if v > 0)
        self.assertGreater(px, 2000)                                   # nodal lines, not an empty layer
        a = direct.draw_element({"kind": "branch", "at": [100, 100], "dir": 30, "len": 500, "seed": 2}, pal, {})
        b = direct.draw_element({"kind": "branch", "at": [100, 100], "dir": 30, "len": 500, "seed": 2}, pal, {})
        self.assertEqual(a.tobytes(), b.tobytes())                      # a seed repeats exactly
        box = a.getbbox()
        self.assertGreater(box[2] - box[0], 250)                        # it grows along its direction


class TestIndex(InTemp):
    def test_index_lists_every_brief(self):
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), brief())
        self.assertEqual(direct.main(["index"]), 0)
        page = open(os.path.join("build", "ui", "directions", "index.html"), encoding="utf-8").read()
        self.assertIn("make a sick hud, original", page)
        self.assertEqual(page.count("class=cell"), 3)
        self.assertIn("checked - awaiting the owner", page)
        self.assertIn("project/t/board.html", page)


class TestReviewFindings2(InTemp):
    """the fresh review of v8.1-8.7 (2026-10-24): each bug it found stays fixed"""

    def test_strip_keeps_the_end_beats(self):
        import direct_reel as R
        picks = R.strip_picks([["0.1", "a"], ["1.6", "b"], ["1.9", "c"]], 24, 48)
        self.assertEqual(len(picks), 6)
        self.assertEqual(picks[-1], 47)
        self.assertTrue(any(p >= 38 for p in picks[:-1]))
        self.assertEqual(len(R.strip_picks([["0", "a"]], 10, 2)), 6)

    def test_cjk_name_inside_japanese_text(self):
        b = brief()
        b["context"]["source_names"] = ["黒閃"]
        b["context"]["source_moves"] = ["a negative flash"]
        b["directions"][0]["frame"]["elements"].append({"kind": "text", "at": [0, 0], "text": "これが黒閃だ"})
        self.assertTrue(any("黒閃" in e for e in direct.check_brief(b)[0]))

    def test_float_radius_scalar_t_zero_duration_bad_beats(self):
        import direct_reel as R
        direct.draw_element({"kind": "stamp", "center": [100, 100], "r": 52.5, "text": "X", "size": 40}, {}, {})
        direct.draw_element({"kind": "chladni", "center": [100, 100], "r": 0, "density": 1}, {}, {})
        self.assertTrue(R.state({"t": 0.4}, 0.5, 1.0)[0])
        b = brief()
        x = b["directions"][1]
        x["frame"]["elements"].append({"kind": "rect", "box": [0, 0, 10, 10], "fill": "accent", "t": 0.2})
        x["frame"]["reel"] = {"duration": 0, "fps": 10}
        x["signature_moment"]["beats"].append([1.2, "x", "sfx"])
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), b)
        self.assertEqual(direct.main(["reel", "t", "B"]), 0)
        self.assertEqual(direct.main(["board", "t"]), 0)
        self.assertEqual(direct.main(["critique", "t"]), 0)

    def test_two_games_same_brief_name_do_not_collide(self):
        a, b = brief(), brief()
        a["game"], b["game"] = "G1", "G2"
        self.assertNotEqual(direct.out_dir(dict(a, name="hud")), direct.out_dir(dict(b, name="hud")))

    def test_answers_are_never_wiped(self):
        direct.save(os.path.join("assets", "ui", "directions", "t.json"), brief())
        self.assertEqual(direct.main(["critique", "t"]), 0)
        out = os.path.join("build", "judge", "ui", "directions", "project", "t")
        json.dump({"ranking": [1, 2, 3]}, open(os.path.join(out, "answers.json"), "w", encoding="utf-8"))
        self.assertEqual(direct.main(["critique", "t", "--seed", "9"]), 1)       # refused: unrecorded answers
        self.assertTrue(os.path.isfile(os.path.join(out, "answers.json")))
        self.assertEqual(direct.main(["critique", "t", "--record", os.path.join(out, "answers.json")]), 0)
        self.assertEqual(direct.main(["critique", "t", "--seed", "9"]), 0)       # recorded: a new packet is fine


class TestVisible(unittest.TestCase):
    def test_moment_change(self):
        import direct_reel as R
        from PIL import Image
        a = Image.new("RGB", (100, 100), (20, 20, 20))
        b = a.copy()
        b.paste((250, 250, 250), (0, 0, 50, 100))                    # half the frame lights up
        self.assertAlmostEqual(R.moment_change([a, a, b, a]), 0.5, 2)
        c = a.copy()
        c.paste((250, 250, 250), (0, 0, 10, 10))                     # a corner blip
        self.assertLess(R.moment_change([a, c]), R.FAINT)


if __name__ == "__main__":
    unittest.main()
