"""kit/vision/taste.py - the taste model per lane: it learns only the owner's own numbers (never a guess) on pieces with
a picture, is tested leave-one-out (how often it orders two pieces the owner's way), switches on only with enough
pieces and agreement, can be switched off by the owner, orders a pick round's candidates by the scored pieces they look
like, and never rewrites its record when nothing changed. A stub embedder (a picture's mean colour) stands in for
SigLIP 2. Run: python kit/test/python/run.py -k test_taste"""

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
import alike as A  # noqa: E402
import taste as T  # noqa: E402


def stub_embed(images):
    out = []
    for img in images:
        a = np.asarray(img.convert("RGB"), dtype=np.float32).reshape(-1, 3).mean(axis=0) / 255.0
        v = np.array([a[0], a[1], a[2], 0.05], dtype=np.float32)
        out.append(v / np.linalg.norm(v))
    return np.stack(out)


class TasteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.vault = os.path.join(self.root, "vault")
        self.index = os.path.join(self.root, "build", "look")

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, rel):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def piece(self, i, colour, score, source="owner"):
        name = f"fx{i:02d}"
        Image.new("RGB", (16, 16), colour).save(self.path(f"library/vfx/effects/{name}/previews/hero.png"))
        with open(self.path(f"vault/vfx/verdicts/{name}.md"), "w", encoding="utf-8") as f:
            f.write(f"---\nkind: verdict\nname: {name}\ndate: 2026-11-01\nscore: {score}\nsource: {source}\n---\n\nx\n")

    def warm_and_cold(self, n):
        """warm (red) pieces the owner loved, cool (blue) ones they rejected: a look that predicts the score"""
        for i in range(n):
            if i % 2:
                self.piece(i, (240 - i, 30 + i, 20), 8 + (i % 3) * 0.5)
            else:
                self.piece(i, (20, 40 + i, 240 - i), 2 + (i % 3) * 0.5)

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.main([*argv, "--root", self.root, "--vault", self.vault, "--index", self.index], embed=stub_embed)
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    def build(self):
        A.build(stub_embed, self.root, self.vault, self.index)

    def test_a_look_that_predicts_the_owner_turns_the_model_on(self):
        self.warm_and_cold(22)
        self.build()
        r = self.cli("train", "vfx")
        self.assertEqual(r["record"]["n"], 22)
        self.assertGreaterEqual(r["record"]["pairwise"], 0.9)
        self.assertTrue(r["record"]["enabled"])
        self.assertIn("orders candidates", r["line"])

    def test_too_few_pieces_stay_off_whatever_the_agreement(self):
        self.warm_and_cold(8)
        self.build()
        rec = self.cli("train", "vfx")["record"]
        self.assertFalse(rec["enabled"])
        self.assertIn("needs 20", rec["why"])

    def test_a_look_that_says_nothing_stays_off(self):
        rng = np.random.default_rng(3)
        for i in range(24):  # colours unrelated to the scores
            self.piece(i, tuple(int(c) for c in rng.integers(0, 255, 3)), float(rng.integers(0, 11)))
        self.build()
        rec = self.cli("train", "vfx")["record"]
        self.assertFalse(rec["enabled"])  # 24 pieces: past the count gate, stopped by the agreement or the shuffles
        self.assertTrue(rec["pairwise"] < T.MIN_PAIRWISE or rec["p_value"] > T.MAX_P)

    def test_noise_rarely_switches_on_the_shuffle_test_holds_it(self):
        """random scores on real-looking pictures: across 30 seeds at most a few pass 60%, and the shuffle test
        stops those"""
        on = 0
        for seed in range(30):
            rng = np.random.default_rng(seed)
            X = rng.normal(size=(24, 8))
            X /= np.linalg.norm(X, axis=1, keepdims=True)
            y = rng.integers(0, 11, 24).astype(float)
            idx, w = T.loo_structure(X)
            pred = T.loo_predict(idx, w, y)
            pairwise, _s, _p = T.agreement(y, pred, X)
            differ = np.triu(X @ X.T < T.LOOKS_SAME, 1)
            self.assertAlmostEqual(T._fast_pairwise(y, pred, differ), pairwise, places=9)  # the fast path agrees
            beat = sum(1 for _ in range(T.PERMUTATIONS)
                       if T._fast_pairwise(yp := rng.permutation(y), T.loo_predict(idx, w, yp), differ) >= pairwise)
            if pairwise >= T.MIN_PAIRWISE and (1 + beat) / (1 + T.PERMUTATIONS) <= T.MAX_P:
                on += 1
        self.assertLessEqual(on, 2)

    def test_a_scored_pieces_own_picture_never_predicts_itself(self):
        self.warm_and_cold(22)
        self.build()
        self.cli("train", "vfx")
        own = self.cli("order", "vfx", "library/vfx/effects/fx01/previews/hero.png")
        self.assertEqual(own["rows"][0]["item"], "fx01")
        self.assertNotIn("fx01 ", " ".join(own["rows"][0]["nearest"]) + " ")

    def test_a_guess_is_never_learned(self):
        self.warm_and_cold(22)
        for i in range(22, 30):
            self.piece(i, (250, 20, 20), 1, source="inferred")  # guessed numbers on red: would poison the reds
        self.build()
        rec = self.cli("train", "vfx")["record"]
        self.assertEqual(rec["n"], 22)
        self.assertTrue(all(not p.startswith(("fx22", "fx23", "fx29")) for p in rec["pieces"]))

    def test_the_owner_switches_it_off_and_order_stops(self):
        self.warm_and_cold(22)
        self.build()
        self.cli("train", "vfx")
        Image.new("RGB", (16, 16), (245, 25, 15)).save(self.path("elsewhere/new.png"))
        on = self.cli("order", "vfx", "elsewhere/new.png")
        self.assertEqual(len(on["rows"]), 1)
        self.assertGreater(on["rows"][0]["predicted"], 6)  # it looks like the loved ones
        self.cli("off", "vfx")
        off = self.cli("order", "vfx", "elsewhere/new.png")
        self.assertEqual(off["rows"], [])
        self.assertIn("switched off by the owner", off["line"])
        self.cli("train", "vfx")  # retraining keeps the owner's switch
        self.assertIn("switched off", self.cli("order", "vfx", "elsewhere/new.png")["line"])

    def test_the_record_is_not_rewritten_when_nothing_changed(self):
        self.warm_and_cold(22)
        self.build()
        self.assertTrue(self.cli("train", "vfx")["written"])
        self.assertFalse(self.cli("train", "vfx")["written"])

    def test_agreement_counts_pairs_and_ties(self):
        self.assertEqual(T.agreement([1, 2, 3], [1, 2, 3])[0], 1.0)
        self.assertEqual(T.agreement([1, 2, 3], [3, 2, 1])[0], 0.0)
        self.assertEqual(T.agreement([1, 2], [5, 5])[0], 0.5)  # a predicted tie counts half


if __name__ == "__main__":
    unittest.main()
