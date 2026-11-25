"""A hair card bent along a flow (kit/blender/rbx_card.py, rbx.Asset.card; the 3D methods audit, H: "a card bent
along a flow line is not built"): the ribbon's geometry, and its strand picture read in the card's OWN coordinates -
the same picture cuts the same share of a straight card and of one bent round a head, where a picture laid flat in
one plane smears."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_card  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FLOW = [(0.0, 2.0, 0.0), (0.0, 2.3, -0.5), (0.0, 1.9, -1.1), (0.0, 1.2, -1.3)]   # (over a head and down its back)
U = [(0.0, 2.0, 0.0), (0.0, 1.0, -0.2), (0.0, 0.8, -0.8), (0.0, 1.2, -1.4), (0.0, 2.0, -1.5)]   # (down and back up)


class Ribbon(unittest.TestCase):
    def test_root_to_tip_and_the_taper(self):
        v, card, faces, length = rbx_card.ribbon(FLOW, 0.3, taper=0.4, across=2)
        self.assertEqual(card[0].tolist(), [0.0, 0.0])
        self.assertEqual(card[-1].tolist(), [1.0, 1.0])
        self.assertAlmostEqual(float(np.linalg.norm(v[0] - v[2])), 0.3, places=6)
        self.assertAlmostEqual(float(np.linalg.norm(v[-3] - v[-1])), 0.12, places=6)
        self.assertGreater(length, 2.0)
        self.assertEqual(len(faces), (len(card) // 3 - 1) * 2)

    def test_it_follows_the_flow(self):
        v, card, _f, _l = rbx_card.ribbon(FLOW, 0.3, across=2)
        mid = v[1::3]                       # (the middle column: on the flow's smooth line)
        self.assertLess(float(np.linalg.norm(mid[0] - FLOW[0])), 1e-9)
        self.assertLess(float(np.linalg.norm(mid[-1] - FLOW[-1])), 1e-9)

    def test_a_flow_that_doubles_back_is_refused(self):
        with self.assertRaises(ValueError):
            rbx_card.ribbon([(0, 0, 0), (0, 1, 0), (0, 0.001, 0.0001)], 0.2, segments=2)

    def test_its_picture_fills_the_card_top_at_the_root(self):
        pts = rbx_card.card_points(np.array([[0.0, 0.0], [1.0, 1.0]]))
        self.assertEqual(pts[0].tolist(), [0.0, 1.0, 0.0])    # (the root: the picture's top)
        self.assertEqual(pts[1].tolist(), [1.0, 0.0, 0.0])


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class CardBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image

        cls.tmp = tempfile.mkdtemp()
        h, w = 256, 256
        y, x = np.mgrid[0:h, 0:w]
        # strands: 12 running down the picture, thinning toward the tip (its bottom); the last tenth clear
        width = 0.45 * (1.0 - 0.8 * y / h)
        alpha = (np.abs(((x / w * 12) % 1.0) - 0.5) < width / 2 + 0.05) & (y < 0.9 * h)
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., :3] = 40
        rgba[..., 3] = np.where(alpha, 255, 0)
        cls.pic = os.path.join(cls.tmp, "strands.png")
        Image.fromarray(rgba, "RGBA").save(cls.pic)
        cls.alpha = alpha
        half = np.zeros((h, w, 4), np.uint8)
        half[: h // 2, :, 3] = 255                    # (solid in its top half only: the root half of a card)
        cls.half = os.path.join(cls.tmp, "half.png")
        Image.fromarray(half, "RGBA").save(cls.half)
        cls.runs = {k: cls.build(k) for k in ("straight", "bent", "u")}

    @classmethod
    def build(cls, how):
        flow = [(0.0, 2.0, 0.0), (0.0, 0.7, 0.0)] if how == "straight" else U if how == "u" else FLOW
        pic, twist = (cls.half, 0) if how == "u" else (cls.pic, 25)
        src = textwrap.dedent(f"""
            import sys, json
            sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
            import rbx
            a = rbx.Asset('_selftest_card_{how}', tex=256, size=(0.6, 2.6, 1.8), allow_floating=('Lock',))
            a.material('hair', color=(0.25, 0.16, 0.1), rough=0.5)
            a.card('Lock', {flow!r}, 0.3, 'hair', picture={pic!r}, taper=0.4, twist={twist}, segments=16)
            a.build()
            print('CARD ' + json.dumps(a.design.get('cards')))
            """)
        path = os.path.join(cls.tmp, f"card_{how}.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        env = dict(os.environ, KIT_BUILD=os.path.join(cls.tmp, "build"), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path, "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=900, env=env)
        text = out.stdout + out.stderr
        got = None
        if '{"schema"' in text:
            got = json.JSONDecoder().raw_decode(text[text.find('{"schema"'):])[0]
        return out.returncode, got, text

    def cut_share(self, how):
        code, st, text = self.runs[how]
        self.assertEqual(code, 0, text[-3000:])
        cuts = (st.get("facts") or {}).get("cutouts")
        self.assertTrue(cuts, list((st.get("facts") or {}).keys()))
        row = [c for rows in cuts.values() for c in rows if str(c.get("part", "")).startswith("Lock")]
        self.assertTrue(row, cuts)
        return float(row[0]["cut"])

    def test_the_picture_bends_with_the_card(self):
        # the share the picture clears, weighted by the card's width along it (0.4 at the tip)
        rows = self.alpha.shape[0]
        along = (np.arange(rows) + 0.5) / rows
        weight = 1.0 - 0.6 * along
        want = float(((1.0 - self.alpha.mean(axis=1)) * weight).sum() / weight.sum())
        straight, bent = self.cut_share("straight"), self.cut_share("bent")
        self.assertAlmostEqual(straight, want, delta=0.04)
        self.assertAlmostEqual(bent, want, delta=0.04)          # (laid flat in one plane it smeared: not this)

    def test_a_lock_that_turns_back_up_keeps_its_root_half(self):
        # the picture solid in its top half: the card keeps its ROOT half, whichever way it runs - the share cut is
        # the tip half's, weighted by the width (0.393). Laid flat in one plane, both arms of the U sit in the
        # picture's top: 0.625 was cut (measured on the same ribbon)
        self.assertAlmostEqual(self.cut_share("u"), 0.393, delta=0.04)


if __name__ == "__main__":
    unittest.main()
