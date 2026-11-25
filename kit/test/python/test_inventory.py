"""kit refs inventory (kit/refs/inventory.py + kit/vision/vlm.py) — the detail shot list: the model's 0-1000 boxes
land on the picture's pixels, a cut-off answer still parses, the whole-object box is dropped, each detail is graded
by the pixels the picture gives it, and over several pictures each detail keeps its BEST one (no GPU: --boxes)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vision"))
import inventory as I  # noqa: E402
import vlm as V  # noqa: E402


class Parse(unittest.TestCase):
    def test_boxes_map_from_the_0_1000_scale(self):
        text = '```json\n[{"label": "screw", "kind": "fastener", "bbox_2d": [100, 200, 150, 260], "note": "slot"}]\n```'
        d = V.parse_details(text, 2000, 1000)
        self.assertEqual(d[0]["box"], [200.0, 200.0, 300.0, 260.0])
        self.assertEqual(d[0]["kind"], "fastener")

    def test_a_cut_off_answer_keeps_the_whole_items(self):
        text = ('[{"label": "gem", "kind": "gem", "bbox_2d": [10, 10, 60, 60]}, '
                '{"label": "hammer", "kind": "control", "bbox_2d": [70, 10, 90, 4')
        d = V.parse_details(text, 1000, 1000)
        self.assertEqual([x["label"] for x in d], ["gem"])

    def test_the_whole_object_and_repeats_are_dropped(self):
        text = json.dumps([{"label": "gun", "bbox_2d": [0, 0, 1000, 990]},
                           {"label": "Screw", "kind": "bolt??", "bbox_2d": [100, 100, 200, 200]},
                           {"label": "screw", "bbox_2d": [101, 100, 200, 201]}])
        d = V.parse_details(text, 500, 500)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["kind"], "other")          # (an unknown kind is never invented into the list)


    def test_a_bracket_in_the_preamble_is_not_the_list(self):
        text = 'Here are [up to 30] items: [{"label": "gem", "bbox_2d": [10, 10, 60, 60]}]'
        self.assertEqual([d["label"] for d in V.parse_details(text, 1000, 1000)], ["gem"])


class Whole(unittest.TestCase):
    def test_the_whole_object_is_not_a_detail(self):
        obj = [100, 300, 1900, 1200]                                          # (a side-view gun: wide, not tall)
        self.assertTrue(I.whole({"label": "pistol", "box": [90, 290, 1910, 1210]}, obj))
        self.assertTrue(I.whole({"label": "the pistol", "box": [300, 300, 1500, 1100]}, obj, {"pistol"}))
        self.assertFalse(I.whole({"label": "screw", "box": [500, 500, 560, 560]}, obj, {"pistol"}))

    def test_object_box_on_a_plain_backdrop(self):
        from PIL import Image  # noqa: PLC0415

        im = Image.new("RGB", (400, 200), (10, 10, 10))
        im.paste((200, 40, 60), (50, 40, 350, 150))
        self.assertEqual(I.object_box(im), [50.0, 40.0, 350.0, 150.0])


class Grade(unittest.TestCase):
    def test_status_by_pixels_and_px_per_mm(self):
        self.assertEqual(I.grade([0, 0, 60, 80])["status"], "ok")
        self.assertEqual(I.grade([0, 0, 30, 80])["status"], "upscale")
        self.assertEqual(I.grade([0, 0, 10, 80])["status"], "close-up")
        r = I.grade([0, 0, 60, 80], mm_per_px=0.7)            # (1.43 px/mm: under the 2 px/mm bar)
        self.assertEqual(r["status"], "close-up")
        self.assertEqual(r["size_mm"], [42.0, 56.0])

    def test_merge_keeps_each_details_best_picture(self):
        shot = I.merge({}, "side.png", [{"label": "Screws", "kind": "fastener", "box": [0, 0, 9, 9],
                                         **I.grade([0, 0, 9, 9])}])
        shot = I.merge(shot, "closeup.png", [{"label": "screw", "kind": "fastener", "box": [0, 0, 90, 90],
                                              **I.grade([0, 0, 90, 90])}])
        self.assertEqual(list(shot), ["screw"])
        self.assertEqual(shot["screw"]["best"], "closeup.png")
        self.assertEqual(shot["screw"]["status"], "ok")
        self.assertEqual(shot["screw"]["seen_in"], ["closeup.png", "side.png"])


class Cli(unittest.TestCase):
    def test_a_hand_list_writes_the_shot_list_and_sheet(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as t:
            pic = os.path.join(t, "pic.png")
            Image.new("RGB", (400, 200), (200, 200, 200)).save(pic)
            boxes = os.path.join(t, "b.json")
            with open(boxes, "w") as fh:
                json.dump([{"label": "gem", "kind": "gem", "box": [20, 20, 90, 90]},
                           {"label": "pin", "kind": "fastener", "box": [200, 50, 210, 60]}], fh)
            out = os.path.join(t, "x.details.json")
            p = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "refs", "inventory.py"), pic, "--name",
                                "x", "--boxes", boxes, "--out", out, "--mm-per-px", "0.25"],
                               capture_output=True, text=True, env={**os.environ, "KIT_BUILD": t})
            res = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual(res["status"], "pass", p.stdout + p.stderr)
            self.assertEqual(res["counts"], {"ok": 1, "upscale": 0, "close-up": 1})
            doc = json.load(open(out))
            self.assertIn("trace_cmd", doc["pictures"][pic.replace(os.sep, "/")]["details"][0])
            self.assertTrue(os.path.isfile(os.path.join(t, "refs", "x_inventory.png")))

    def test_sam3s_tighter_box_wins_a_duplicate(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as t:
            pic = os.path.join(t, "pic.png")
            Image.new("RGB", (400, 200), (200, 200, 200)).save(pic)
            boxes = os.path.join(t, "b.json")
            with open(boxes, "w") as fh:
                json.dump([{"label": "screw", "kind": "fastener", "box": [100, 50, 170, 120]},
                           {"label": "screw", "kind": "fastener", "box": [104, 54, 166, 116], "pass": "sam3"}], fh)
            out = os.path.join(t, "x.details.json")
            subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "refs", "inventory.py"), pic, "--name", "x",
                            "--boxes", boxes, "--out", out], capture_output=True, text=True,
                           env={**os.environ, "KIT_BUILD": t})
            rows = json.load(open(out))["pictures"][pic.replace(os.sep, "/")]["details"]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["box"], rows[0]["pass"]), ([104, 54, 166, 116], "vlm+sam3"))


if __name__ == "__main__":
    unittest.main()
