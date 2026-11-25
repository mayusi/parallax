"""kit ui verify: pairs drafted from read stills respect P1 / P2, the packet cuts both crops at one scale, and the
record refuses a score, a missing pair, an empty edit and a changed build"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_verify", os.path.join(HERE, "..", "..", "ui", "verify.py"))
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj))


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        r = self.root
        self.specs, self.refs, self.ui = f"{r}/ui", f"{r}/ui/refs", f"{r}/build"
        self.models, self.out = f"{r}/models", f"{r}/judge"
        write(f"{self.specs}/identities/fx.json", {"name": "fx"})
        os.makedirs(f"{self.refs}/fx", exist_ok=True)
        Image.new("RGB", (1920, 1080), (200, 30, 30)).save(f"{self.refs}/fx/fight.png")
        write(f"{self.refs}/fx/refs.json", {"schema": 1, "stills": [{"file": "fight.png", "size": [1920, 1080], "kind": "hud", "typed": "tag"}]})
        write(f"{self.refs}/fx/fight.read.json", {"elements": [
            {"label": "P2 super / tension gauge", "box_1080": [1000, 980, 1600, 1060]},
            {"label": "round timer / centre", "box_1080": [900, 40, 1020, 160]}]})
        self.spec = {"name": "Duel", "identity": "fx", "kind": "hud", "root": {"name": "Hud", "children": [
            {"name": "T1", "children": [{"name": "Gauge"}]}, {"name": "T2", "children": [{"name": "Gauge"}]}, {"name": "Timer"}]}}
        write(f"{self.specs}/Duel.json", self.spec)
        os.makedirs(self.ui, exist_ok=True)
        Image.new("RGB", (1920, 1080), (20, 20, 20)).save(f"{self.ui}/Duel.desktop.png")
        write(f"{self.ui}/Duel.boxes.json", {"boxes": {"Hud.T2.Gauge": [1000, 990, 600, 60], "Hud.Timer": [890, 30, 140, 140], "Hud.T1.Gauge": [300, 990, 600, 60]}})
        write(f"{self.models}/Duel.model.json", "{}")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def args(self, **kw):
        base = dict(screen="Duel", specs=self.specs, refs=self.refs, ui=self.ui, models=self.models, out=self.out)
        base.update(kw)
        return Args(**base)

    def test_pairs_keep_the_side(self):
        self.assertEqual(verify.cmd_pairs(self.args()), 0)
        pairs = json.load(open(f"{self.specs}/Duel.pairs.json", encoding="utf-8"))
        by = {p["piece"]: p["node"] for p in pairs}
        self.assertEqual(by["P2 super / tension gauge"], "T2.Gauge")   # never P1's T1
        self.assertEqual(by["round timer / centre"], "Timer")
        self.assertTrue(all(p["check"] for p in pairs))

    def test_packet_then_record_refuses_scores_gaps_and_changed_builds(self):
        verify.cmd_pairs(self.args())
        self.assertEqual(verify.cmd_packet(self.args()), 0)
        self.assertTrue(os.path.isfile(f"{self.out}/Duel/verify/pairs.png"))
        good = {"by": "fresh", "pairs": [{"piece": "P2 super / tension gauge", "difference": "ours is twice as tall", "edit": "cut the gauge to 40 px tall"},
                                         {"piece": "round timer / centre", "difference": "the disc is too large", "edit": "shrink the disc to 120 px"}],
                "bugs": []}
        vf = f"{self.root}/v.json"
        write(vf, dict(good, score=80))
        self.assertEqual(verify.cmd_record(self.args(verdict=vf)), 1)
        write(vf, dict(good, pairs=good["pairs"][:1]))
        self.assertEqual(verify.cmd_record(self.args(verdict=vf)), 1)
        write(vf, dict(good, pairs=[dict(good["pairs"][0], edit=""), good["pairs"][1]]))
        self.assertEqual(verify.cmd_record(self.args(verdict=vf)), 1)
        write(vf, good)
        self.assertEqual(verify.cmd_record(self.args(verdict=vf)), 0)
        rec = json.load(open(f"{self.specs}/Duel.verify.json", encoding="utf-8"))
        self.assertEqual(len(rec["pairs"]), 2)
        write(f"{self.models}/Duel.model.json", '{"changed": true}')
        self.assertEqual(verify.cmd_record(self.args(verdict=vf)), 1)


class TestGroupPairs(TestVerify):
    def test_a_pair_may_name_a_group_and_crops_their_union(self):
        # (a status strip kept as sibling nodes: the crop must hold all of them — 2026-10-16 InkModes)
        write(f"{self.specs}/Duel.pairs.json", [{"piece": "both gauges", "node": ["T1.Gauge", "T2.Gauge"],
                                                 "still": f"{self.refs}/fx/fight.png", "box": [300, 980, 1600, 1060]}])
        self.assertEqual(verify.cmd_packet(self.args()), 0)
        with Image.open(f"{self.out}/Duel/verify/pairs.png") as im:
            self.assertGreater(im.width, 1000)                   # the union of x 300..900 and 1000..1600 is wide
        write(f"{self.specs}/Duel.pairs.json", [{"piece": "a missing one", "node": ["T1.Gauge", "Nope"],
                                                 "still": f"{self.refs}/fx/fight.png", "box": [300, 980, 900, 1060]}])
        self.assertEqual(verify.cmd_packet(self.args()), 1)     # a group with a missing member is not cut


if __name__ == "__main__":
    unittest.main()
