"""kit/vision/alike.py - search by look: the index covers our pieces' pictures and the references, embeds only what is
new (by content), finds the past pieces that look closest with the owner's verdict on each (never the piece itself or
its own round; guessed numbers marked), and groups the same reference filed twice. A stub embedder (a picture's mean
colour) stands in for SigLIP 2, so no model is loaded. Run: python kit/test/python/run.py -k test_alike"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
import alike as L  # noqa: E402

CALLS = []


def stub_embed(images):
    """a picture's mean colour as a unit vector: same colour = cosine 1"""
    CALLS.append(len(images))
    out = []
    for img in images:
        a = np.asarray(img.convert("RGB"), dtype=np.float32).reshape(-1, 3).mean(axis=0) / 255.0
        v = np.array([a[0], a[1], a[2], 0.05], dtype=np.float32)
        out.append(v / np.linalg.norm(v))
    return np.stack(out)


class LookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.vault = os.path.join(self.root, "vault")
        self.index = os.path.join(self.root, "build", "look")
        CALLS.clear()
        self.png("library/vfx/effects/fire_a/previews/hero.png", (250, 20, 10))
        self.png("library/vfx/effects/fire_b/previews/hero.png", (240, 30, 20))
        self.png("library/vfx/effects/ice/previews/hero.png", (10, 40, 250))
        self.gif("build/candidates/Kick/round_1/c0.gif", [(200, 200, 0), (210, 200, 0)])
        self.gif("build/candidates/Kick/round_1/c1.gif", [(205, 200, 0), (205, 200, 0)])
        self.gif("build/candidates/Kick/round_0/c3.gif", [(190, 190, 0), (200, 195, 0)])
        self.png("assets/ui/refs/a.png", (90, 90, 90))
        self.png("assets/ui/refs/sub/a_copy.png", (90, 90, 90))
        self.png("assets/ui/refs/b.png", (10, 200, 10))
        self.png("games/G1/build/worlds/Town.png", (120, 80, 40))
        self.png("build/renders/chair_front.png", (60, 40, 20))
        self.png("build/renders/chair_side.png", (62, 40, 20))
        self.png("build/renders/_selftest_x.png", (1, 2, 3))
        self.png("build/renders/chair_ref_front.png", (5, 5, 5))
        self.png("vault/ui/judged/abcd1234abcd1234.png", (240, 200, 40))
        self.note("vfx", "fire_b.md", "fire_b", "score: 9\nsource: owner\n", "love the flame shape")
        self.note("vfx", "ice.md", "ice", "score: 2\nsource: inferred\n", "too cold, guessed")
        self.note("anim", "kick.md", "Kick/r0", "score: 3\nsource: owner\n", "stilts, legs too long")
        self.note("ui", "gauge.md", "Gauge", "direction: keep\nsource: owner\njudged: ui/judged/abcd1234abcd1234.png\n",
                  "keep the gold")

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, rel):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def png(self, rel, colour):
        Image.new("RGB", (16, 16), colour).save(self.path(rel))

    def gif(self, rel, colours):
        frames = [Image.new("RGB", (8, 8), c) for c in colours]
        frames[0].save(self.path(rel), save_all=True, append_images=frames[1:])

    def note(self, lane, file, name, extra, body):
        with open(self.path(f"vault/{lane}/verdicts/{file}"), "w", encoding="utf-8") as f:
            f.write(f"---\nkind: verdict\nname: {name}\ndate: 2026-11-0{len(file) % 9}\n{extra}---\n\n{body}\n")

    def build(self):
        return L.build(stub_embed, self.root, self.vault, self.index)

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            L.main([*argv, "--root", self.root, "--vault", self.vault, "--index", self.index], embed=stub_embed)
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_collect_names_each_picture_by_its_piece(self):
        got = {(e["lane"], e["kind"], e["piece"]) for e in L.collect(self.root, self.vault)}
        for want in [("vfx", "library", "fire_a"), ("anim", "candidate", "Kick/r1/c0"), ("world", "render", "Town"),
                     ("3d", "render", "chair"), ("ui", "judged", "Gauge"), ("ui", "ref", "assets/ui/refs/a.png")]:
            self.assertIn(want, got)
        self.assertNotIn(("3d", "render", "chair_ref"), got)  # a traced reference beside the render is no picture of it
        self.assertFalse(any("_selftest" in p for _l, _k, p in got))
        self.assertEqual([e["game"] for e in L.collect(self.root, self.vault) if e["piece"] == "Town"], ["G1"])

    def test_only_new_pictures_are_embedded(self):
        first = self.build()
        self.assertEqual(first["embedded"], first["unique"])
        self.assertLess(first["unique"], first["pictures"])  # a.png and its copy share one row
        self.assertEqual(self.build()["embedded"], 0)
        self.png("library/vfx/effects/ice/previews/hero.png", (12, 60, 240))
        self.assertEqual(self.build()["embedded"], 1)
        os.remove(os.path.join(self.root, "assets/ui/refs/b.png"))
        self.assertEqual(self.build()["pictures"], first["pictures"] - 1)

    def test_a_piece_finds_the_pieces_that_look_like_it_with_the_owners_verdict(self):
        self.build()
        r = self.cli("near", "fire_a", "--lane", "vfx")
        self.assertEqual(r["rows"][0]["piece"], "fire_b")
        self.assertIn("owner 9/10", r["rows"][0]["line"])
        self.assertNotIn("fire_a", [x["piece"] for x in r["rows"]])
        ice = next(x for x in r["rows"] if x["piece"] == "ice")
        self.assertIn("guessed 2/10", ice["line"])
        self.assertLess(ice["similarity"], r["rows"][0]["similarity"])

    def test_a_candidate_skips_its_own_round_and_meets_the_rejected_round(self):
        self.build()
        r = self.cli("near", "Kick/r1/c0", "--lane", "anim")
        pieces = [x["piece"] for x in r["rows"]]
        self.assertNotIn("Kick/r1/c1", pieces)
        self.assertEqual(pieces[0], "Kick/r0/c3")
        self.assertIn("owner 3/10", r["rows"][0]["line"])  # the round's verdict stands for its candidate
        self.assertIn("stilts", r["rows"][0]["line"])

    def test_a_new_picture_is_embedded_unless_only_cached_vectors_may_be_used(self):
        self.build()
        self.png("elsewhere/new.png", (245, 25, 15))
        self.assertFalse(self.cli("near", "elsewhere/new.png", "--cached")["indexed"])
        r = self.cli("near", "elsewhere/new.png")
        self.assertIn(r["rows"][0]["piece"], ("fire_a", "fire_b"))

    def test_the_same_reference_filed_twice_is_one_group(self):
        self.build()
        r = self.cli("dupes")
        self.assertEqual(len(r["groups"]), 1)
        self.assertEqual(sorted(r["groups"][0]["paths"]), ["assets/ui/refs/a.png", "assets/ui/refs/sub/a_copy.png"])

    def test_an_unreadable_picture_is_counted_never_fatal(self):
        with open(self.path("library/vfx/effects/broken/previews/hero.png"), "wb") as f:
            f.write(b"not a png")
        st = self.build()
        self.assertEqual(st["failed"], 1)
        self.assertNotIn("broken", [e["piece"] for e in L.load(self.index)[0]["entries"]])

    def test_the_closest_judged_pieces_always_join_the_list(self):
        self.build()
        r = self.cli("near", "fire_a", "--lane", "vfx", "--k", "1")
        self.assertEqual(r["rows"][0]["piece"], "fire_b")
        extra = [x for x in r["rows"] if x.get("judged_extra")]
        self.assertEqual([x["piece"] for x in extra], ["ice"])
        self.assertTrue(extra[0]["line"].startswith("nearest judged: "))

    def test_a_fresh_picture_of_a_known_piece_leaves_its_own_pictures_out(self):
        self.build()
        self.png("elsewhere/fire_a_new.png", (250, 21, 10))
        r = self.cli("near", "elsewhere/fire_a_new.png", "--as", "fire_a", "--lane", "vfx")
        self.assertNotIn("fire_a", [x["piece"] for x in r["rows"]])
        self.assertEqual(r["rows"][0]["piece"], "fire_b")

    def test_a_round_meets_the_owners_own_loved_and_rejected_pieces(self):
        self.gif("build/animations/Spin.r6.look.gif", [(10, 10, 200), (12, 10, 200)])
        self.note("anim", "spin.md", "Spin", "score: 9\nsource: owner\n", "love the spin")
        self.build()
        r = self.cli("round", "Kick", "--round", "1")
        self.assertEqual([x["candidate"] for x in r["rows"]], ["c0", "c1"])
        self.assertTrue(all(x["closer_to_rejected"] for x in r["rows"]))
        self.assertIn("nearest rejected Kick/r0/c3", r["lines"][0])
        self.assertIn("nearest loved Spin", r["lines"][0])
        self.assertIn("CLOSER TO A REJECTED PIECE", r["lines"][0])

    def test_a_tie_between_rejected_and_loved_is_no_flag(self):
        self.gif("build/animations/Twin.r6.look.gif", [(190, 190, 0), (200, 195, 0)])  # Kick/r0/c3's very look
        self.note("anim", "twin.md", "Twin", "score: 8\nsource: owner\n", "loved")
        self.build()
        r = self.cli("round", "Kick", "--round", "1")
        self.assertFalse(any(x["closer_to_rejected"] for x in r["rows"]))

    def test_a_guessed_rejection_never_counts_in_a_round(self):
        self.note("anim", "kick.md", "Kick/r0", "score: 2\nsource: inferred\n", "guessed stilts")
        self.build()
        r = self.cli("round", "Kick", "--round", "1")
        self.assertFalse(any(x["closer_to_rejected"] for x in r["rows"]))

    def test_the_later_note_of_one_day_is_the_newest(self):
        for file, t, score in (("ice--2026-11-08.md", "1700000900", "6"), ("ice--2026-11-08-2.md", "1700000100", "1")):
            with open(self.path(f"vault/vfx/verdicts/{file}"), "w", encoding="utf-8") as f:
                f.write(f"---\nkind: verdict\nname: ice\ndate: 2026-11-08\ntime: {t}\nscore: {score}\nsource: owner\n---\n\nx\n")
        v = L.verdicts(self.vault)[("vfx", "ice")]
        self.assertEqual(v["score"], "6")  # 900 s after the other note, though its file sorts first

    def test_two_notes_of_one_day_without_a_time_the_later_file_wins(self):
        for file, score in (("ice--2026-11-09.md", "2"), ("ice--2026-11-09-2.md", "9")):
            with open(self.path(f"vault/vfx/verdicts/{file}"), "w", encoding="utf-8") as f:
                f.write(f"---\nkind: verdict\nname: ice\ndate: 2026-11-09\nscore: {score}\nsource: owner\n---\n\nx\n")
        self.assertEqual(L.verdicts(self.vault)[("vfx", "ice")]["score"], "9")  # "-2" is the day's second note

    def test_a_move_note_naming_candidates_judges_only_those(self):
        self.note("anim", "kick.md", "Kick", "score: 2\nsource: owner\n", "round 0: c3 has stilts")
        self.build()
        vd = L.verdicts(self.vault, L.moves_of(L.load(self.index)[0]))
        self.assertIsNotNone(L.verdict_of(vd, "anim", "Kick/r0/c3", move_level=False))
        self.assertIsNone(L.verdict_of(vd, "anim", "Kick/r0/c4", move_level=False))  # not named, not "every one"

    def test_a_move_note_counts_for_the_rounds_it_names_and_is_shown_for_the_rest(self):
        self.gif("build/candidates/Kick/round_2/c0.gif", [(201, 199, 0), (201, 199, 0)])
        # the only note is on the MOVE, and its words name round 0 (the setUp's "Kick/r0" note is replaced)
        self.note("anim", "kick.md", "Kick", "score: 2\nsource: owner\n", "round 0 has stilts again")
        self.build()
        r = self.cli("round", "Kick", "--round", "1")
        self.assertIn("nearest rejected Kick/r0/c3", r["lines"][0])  # the move's note named round 0
        self.assertIn("on Kick", r["lines"][0])
        meta = L.load(self.index)[0]
        vd = L.verdicts(self.vault, L.moves_of(meta))
        self.assertIsNone(L.verdict_of(vd, "anim", "Kick/r2/c0", move_level=False))  # round 2 was never named
        shown = L.verdict_of(vd, "anim", "Kick/r2/c0")
        self.assertIn("on Kick", L.verdict_text(shown, "Kick/r2/c0"))

    def test_render_variants_are_one_piece(self):
        for name in ("chair_game.clean.png", "chair.judge.png", "chair_compare.png"):
            self.png(f"build/renders/{name}", (61, 40, 20))
        pieces = {e["piece"] for e in L.collect(self.root, self.vault) if e["lane"] == "3d" and e["kind"] == "render"}
        self.assertEqual(pieces, {"chair"})

    def test_a_reference_never_matches_itself(self):
        self.build()
        r = self.cli("near", "assets/ui/refs/b.png", "--refs", "--k", "20")
        self.assertNotIn("assets/ui/refs/b.png", [x["piece"] for x in r["rows"]])

    def test_scratch_renders_are_no_past_piece(self):
        self.png("build/vfx/_fit_fire_a.png", (250, 20, 10))
        self.assertNotIn("_fit_fire_a", [e["piece"] for e in L.collect(self.root, self.vault)])

    def test_no_index_says_how_to_make_one(self):
        r = self.cli("near", "fire_a")
        self.assertEqual(r["status"], "fail")
        self.assertIn("kit alike index", r["next_action"])


if __name__ == "__main__":
    unittest.main()
