"""kit/blender/verifier.py (`kit judge <asset>`): a VERIFIER, not a judge — per traced view the same crop of the
reference photo and the model's render side by side, the worst places at 1:1, the owner's words first, ONE difference
per image and ONE edit, never a score, ten rounds per attempt then STOP. On a temporary project."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import verifier as V  # noqa: E402

SCRIPT = 'import rbx\na = rbx.Asset("x", quality="prop")\na.trace_match("x_side", view="side")\na.build()\n'


def gun(w, h, flip=False, bg=(255, 255, 255, 255), fg=(30, 30, 30, 255)):
    """an L: a long top bar (the slide) and a grip on the RIGHT (the front is on the left), flip: grip on the left"""
    im = Image.new("RGBA", (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, int(h * 0.35)), fill=fg)
    gx = (0, int(w * 0.3)) if flip else (int(w * 0.7), w - 1)
    d.rectangle((gx[0], 0, gx[1], h - 1), fill=fg)
    return im


class Project:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("assets/models", "refs", "build/models", "build/renders"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        self._repo, V.REPO = V.REPO, self.root

    def close(self):
        V.REPO = self._repo
        self.tmp.cleanup()

    def write(self, rel, data):
        p = os.path.join(self.root, rel)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
        return p

    def asset(self, flip_render=False, mask_photo=False):
        """a photo (white page, the object in a 400 x 160 box at 50, 40), its trace (frame = that box, front left), the
        build's shaded render (transparent, the object alone), a manifest with the view's gap windows"""
        photo = Image.new("RGB", (500, 260), (255, 255, 255))
        obj = gun(400, 160).convert("RGB")
        if not mask_photo:   # (a photo has tones: a gradient across it)
            g = np.asarray(obj).astype(np.int16) + np.linspace(0, 60, 400, dtype=np.int16)[None, :, None]
            obj = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))
        photo.paste(obj, (50, 40))
        photo.save(os.path.join(self.root, "refs", "x_side.png"))
        outline = [[0, 0.4], [1, 0.4], [1, 0.26], [0.3, 0.26], [0.3, 0], [0, 0]]   # (u from the back, h in lengths)
        self.write("assets/models/x_side.trace.json", {"source": "refs/x_side.png", "front": "left", "height_ratio": 0.4,
                                                       "outline": outline, "frame": {"x0": 50, "y1": 200,
                                                                                     "length_px": 400}})
        self.write("assets/models/build_x.py", SCRIPT)
        r = gun(800, 320, flip=flip_render, bg=(0, 0, 0, 0), fg=(120, 120, 120, 255))
        canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
        canvas.paste(r, (100, 340))
        canvas.save(os.path.join(self.root, "build", "renders", "x_ref_side_shaded.png"))
        wins = [{"place": "top left", "extra": 0.4, "missing": 3.1}, {"place": "centre", "extra": 1.2, "missing": 0.0},
                {"place": "bottom right", "extra": 0.0, "missing": 0.0}]
        self.write("build/models/x.manifest.json", {"asset": "x", "build_id": "b1", "tier": "prop", "facts": {
            "references": [{"view": "side", "iou": 0.9, "gaps": {"view_size": 186.0, "windows": wins}}]}})


def run(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fn(*a)
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


class Packet(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.close()

    def test_the_same_box_of_reference_and_model_per_view_and_the_worst_places(self):
        self.p.asset()
        code, v = run(V.packet, "x")
        self.assertEqual(code, 0, v["summary"])
        names = [os.path.basename(i) for i in v["images"]]
        self.assertEqual(names, ["side.png", "side_R1.png", "side_R2.png"])   # (the two places with a gap, worst first)
        prompt = open(os.path.join(self.p.root, "build", "judge", "x", "verify", "PROMPT.md"), encoding="utf-8").read()
        self.assertIn("round 1 of 10", prompt)
        self.assertIn("never score", prompt)
        self.assertIn("top left at its own pixels — the outline is 3.1 mm missing", prompt)
        self.assertLess(prompt.index("The owner first"), prompt.index("The images"))
        self.assertNotIn("score", v["summary"])

    def test_the_crops_cover_the_same_object(self):
        self.p.asset()
        t = V._trace("x_side")
        ref = V.ref_crop(t)
        self.assertEqual(ref.size, (400, 160))                  # (the frame's box exactly)
        render, mask = V.render_crop(os.path.join(self.p.root, "build", "renders", "x_ref_side_shaded.png"))
        self.assertEqual(render.size, (800, 320))               # (the silhouette's box: the same aspect)
        self.assertAlmostEqual(ref.width / ref.height, render.width / render.height, places=3)

    def test_a_render_facing_the_other_way_is_turned_to_lie_like_the_trace(self):
        self.p.asset(flip_render=True)
        t = V._trace("x_side")
        render, mask = V.render_crop(os.path.join(self.p.root, "build", "renders", "x_ref_side_shaded.png"))
        _r, flipped, iou = V.oriented(t, render, mask)
        self.assertTrue(flipped)
        self.assertGreater(iou, 0.9)
        self.p.asset(flip_render=False)
        render, mask = V.render_crop(os.path.join(self.p.root, "build", "renders", "x_ref_side_shaded.png"))
        self.assertFalse(V.oriented(t, render, mask)[1])

    def test_a_mask_is_no_reference_a_photo_of_the_same_family_is_used(self):
        self.p.asset(mask_photo=True)
        self.assertTrue(V.is_mask(os.path.join(self.p.root, "refs", "x_side.png")))
        # (a photo trace of the same view: x_photo_side)
        g = np.linspace(40, 230, 500, dtype=np.uint8)[None, :, None].repeat(260, 0).repeat(3, 2)   # (a photo: tones)
        Image.fromarray(g).save(os.path.join(self.p.root, "refs", "x_photo.png"))
        self.p.write("assets/models/x_photo_side.trace.json", {"source": "refs/x_photo.png", "front": "left",
                                                               "height_ratio": 0.4, "outline": [[0, 0], [1, 0], [1, 0.4]],
                                                               "frame": {"x0": 50, "y1": 200, "length_px": 400}})
        name, _t = V.photo_trace("side", "x_side")
        self.assertEqual(name, "x_photo_side")

    def test_no_traced_view_falls_back_to_the_reference_beside_the_hero_and_says_it_is_not_the_same_camera(self):
        self.p.write("assets/models/build_x.py", 'import rbx\na = rbx.Asset("x")\na.build()\n')
        Image.new("RGB", (300, 200), (90, 90, 90)).save(os.path.join(self.p.root, "refs", "x.png"))
        Image.new("RGB", (1920, 960), (60, 60, 60)).save(os.path.join(self.p.root, "build", "renders", "x.png"))
        self.p.write("build/models/x.manifest.json", {"asset": "x", "build_id": "b1", "reference_image": "refs/x.png"})
        code, v = run(V.packet, "x")
        self.assertEqual(code, 0, v["summary"])
        prompt = open(os.path.join(self.p.root, "build", "judge", "x", "verify", "PROMPT.md"), encoding="utf-8").read()
        self.assertIn("NOT the same camera", prompt)


class Record(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.asset()
        run(V.packet, "x")
        self.vdir = os.path.join(self.p.root, "build", "judge", "x", "verify")

    def tearDown(self):
        self.p.close()

    def answer(self, **over):
        a = {"build": "b1", "verifier": "test",
             "differences": [{"image": n, "difference": "the grip is 4 mm too long"}
                             for n in ("side.png", "side_R1.png", "side_R2.png")],
             "edit": {"where": "the grip, both sides, its bottom", "change": "shorten it 4 mm", "why": "R1"}}
        a.update(over)
        with open(os.path.join(self.vdir, "verify_1.json"), "w", encoding="utf-8") as fh:
            json.dump(a, fh)

    def test_a_verifier_never_scores_and_gives_one_edit_and_a_difference_per_image(self):
        imgs = ["side.png", "side_R1.png", "side_R2.png"]
        good = {"build": "b1", "differences": [{"image": i, "difference": "x"} for i in imgs],
                "edit": {"where": "a", "change": "b"}}
        self.assertEqual(V.check(good, "b1", imgs), [])
        self.assertTrue(any("never scores" in p for p in V.check({**good, "score": 7}, "b1", imgs)))
        self.assertTrue(any("never scores" in p for p in V.check({**good, "criteria": {}}, "b1", imgs)))
        self.assertTrue(any("one edit, not a list" in p for p in V.check({**good, "edit": [{}, {}]}, "b1", imgs)))
        self.assertTrue(any("no difference for: side_R2.png" in p for p in
                            V.check({**good, "differences": good["differences"][:2]}, "b1", imgs)))
        self.assertTrue(any("not the current b2" in p for p in V.check(good, "b2", imgs)))

    def test_a_round_is_kept_and_the_tenth_stops_for_the_owner(self):
        self.answer()
        code, v = run(V.record, "x")
        self.assertEqual(code, 0, v["summary"])
        self.assertIn("verify round 1/10", v["summary"])
        self.assertIn("shorten it 4 mm", v["summary"])
        data = json.load(open(os.path.join(self.p.root, "assets", "models", "x.verify.json")))
        self.assertEqual(data["rounds"][0]["edit"]["change"], "shorten it 4 mm")
        self.assertFalse(os.path.isfile(os.path.join(self.vdir, "verify_1.json")))   # (an answer is used once)
        data["rounds"] = [dict(data["rounds"][0], round=i + 1) for i in range(10)]
        self.p.write("assets/models/x.verify.json", data)
        code, v = run(V.packet, "x")
        self.assertEqual(code, 1)
        self.assertIn("STOP", v["summary"])
        self.assertIn("the owner looks now", v["summary"])
        # a new attempt (kit plan --restart) counts again from round 1
        self.p.write("assets/models/x.clock.json", {"started": 0, "attempt": 2})
        code, v = run(V.packet, "x")
        self.assertEqual(code, 0, v["summary"])
        self.assertIn("round 1/10", v["summary"])

    def test_a_scored_answer_is_refused(self):
        self.answer(score=8.5)
        code, v = run(V.record, "x")
        self.assertEqual(code, 1)
        self.assertIn("never scores", v["summary"])


if __name__ == "__main__":
    unittest.main()
