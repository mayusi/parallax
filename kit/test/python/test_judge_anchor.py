"""The owner's graded anchors: a PRIVATE asset's render never reaches the shared (committed) anchors — it stays in this
project's anchors/private, a folder that ignores itself in git — and a packet shows the owner's grade of the asset
itself before anyone else's (the Glock: judged 64 where the owner said 85, 2026-10-10)."""

import json
import os
import shutil
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import judge as J  # noqa: E402


class Anchors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_anchor_")
        self.repo = os.path.join(self.tmp, "repo")
        self.kit = os.path.join(self.repo, "kit")
        os.makedirs(os.path.join(self.repo, "build", "renders"))
        os.makedirs(os.path.join(self.repo, "build", "models"))
        os.makedirs(os.path.join(self.kit, "anchors"))
        self.shared = os.path.join(self.kit, "anchors", "anchors.json")
        with open(self.shared, "w", encoding="utf-8") as fh:
            json.dump([{"asset": "crate", "owner": 70.0, "image": "anchors/crate_70.png", "note": "shared"}], fh)
        self._old = (J.REPO, J.KIT, os.environ.pop("KIT_ANCHORS", None), os.environ.pop("KIT_PROJECT", None))
        J.REPO, J.KIT = self.repo, self.kit

    def tearDown(self):
        J.REPO, J.KIT = self._old[0], self._old[1]
        for k, v in (("KIT_ANCHORS", self._old[2]), ("KIT_PROJECT", self._old[3])):
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _asset(self, name, private):
        Image.new("RGB", (300, 200), (90, 90, 90)).save(os.path.join(self.repo, "build", "renders", f"{name}.png"))
        with open(os.path.join(self.repo, "build", "models", f"{name}.manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"asset": name, **({"private": True} if private else {})}, fh)

    def test_a_private_asset_stays_out_of_the_shared_index(self):
        self._asset("pistol", private=True)
        self.assertEqual(J.anchor("pistol", "85", "owner: the best yet"), 0)
        with open(self.shared, encoding="utf-8") as fh:
            self.assertEqual([a["asset"] for a in json.load(fh)], ["crate"])   # (the committed index untouched)
        folder = os.path.join(self.kit, "anchors", "private")
        self.assertTrue(os.path.isfile(os.path.join(folder, "pistol_85.png")))
        self.assertFalse(os.path.isfile(os.path.join(self.kit, "anchors", "pistol_85.png")))
        with open(os.path.join(folder, ".gitignore"), encoding="utf-8") as fh:
            self.assertIn("*", fh.read().split())   # (the folder ignores itself: safe in any project's git)
        mine = [a for a in J._anchors() if a["asset"] == "pistol"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["image"], "anchors/private/pistol_85.png")
        self.assertTrue(mine[0]["private"])
        self.assertEqual([a["asset"] for a in J._anchors(private=False)], ["crate"])

    def test_a_public_asset_joins_the_shared_index(self):
        self._asset("lamp", private=False)
        self.assertEqual(J.anchor("lamp", "65"), 0)
        with open(self.shared, encoding="utf-8") as fh:
            self.assertEqual([a["asset"] for a in json.load(fh)], ["crate", "lamp"])
        self.assertFalse(os.path.isdir(os.path.join(self.kit, "anchors", "private")))

    def test_anchors_come_oldest_first_by_when_they_were_graded(self):
        self._asset("pistol", private=True)
        J.anchor("pistol", "85")
        with open(self.shared, "w", encoding="utf-8") as fh:   # (a shared grade made AFTER the private one)
            json.dump([{"asset": "crate", "owner": 70.0, "image": "anchors/crate_70.png", "at": "2999-01-01 00:00"}], fh)
        self.assertEqual([a["asset"] for a in J._anchors()], ["pistol", "crate"])
        self.assertEqual(J.pick_anchor("chair", J._anchors())[0]["asset"], "crate")   # (the latest, not the private)

    def test_the_owners_grade_of_the_asset_itself_is_shown_first(self):
        known = [{"asset": "pistol", "owner": 85.0}, {"asset": "sniper", "owner": 80.0}, {"asset": "crate", "owner": 70.0}]
        self.assertEqual(J.pick_anchor("pistol", known), [known[0]])
        self.assertEqual(J.pick_anchor("chair", known), [known[-1]])   # (none of its own: the latest grade)
        self.assertEqual(J.pick_anchor("chair", []), [])


if __name__ == "__main__":
    unittest.main()
