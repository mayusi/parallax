"""test_lane_fence.py — the lane fence: a path maps to one lane (or none), a commit that touches two lanes' own
files is refused unless the message says `cross`, and a golden/graveyard row may not link a verdict note that is
neither in the commit nor in the tree. Uses the real kit/knowledge/lanes.json.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "scripts"))

import lane_fence  # noqa: E402

LANES = lane_fence.load_lanes(os.path.join(ROOT, "kit", "knowledge", "lanes.json"))


class TestLaneFence(unittest.TestCase):
    def test_lane_of_exclusive_shared_and_game_paths(self):
        self.assertEqual(lane_fence.lane_of("assets/effects/x.json", LANES), "vfx")
        self.assertEqual(lane_fence.lane_of("games/SampleDojo/assets/effects/x.json", LANES), "vfx")
        # (PARALLAX spec §5.1 step 6: kit/cmd/ is the parallax lane's own now; kit/knowledge/ stays shared)
        self.assertEqual(lane_fence.lane_of("kit/cmd/content.luau", LANES), "parallax")
        self.assertIsNone(lane_fence.lane_of("kit/knowledge/routes.json", LANES))
        self.assertEqual(lane_fence.lane_of("kit\\ui\\plates.py", LANES), "ui")

    def test_lane_of_gitkeep_is_none(self):
        self.assertIsNone(lane_fence.lane_of("games/SampleDojo/assets/ui/.gitkeep", LANES))

    def test_check_one_lane_and_shared_files_is_ok(self):
        ok, reasons = lane_fence.check(
            ["assets/effects/x.json", "kit/knowledge/routes.json", "board/journal/x.md"],
            "feat(vfx): a new effect",
            LANES,
        )
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_check_code_and_qa_together_is_ok(self):
        # a gameplay system commits with its tests/playtest script (PARALLAX spec §5.1 step 6: never falsely blocked)
        ok, reasons = lane_fence.check(["src/server/X.server.luau", "tests/playtest/x.luau"], "feat: a system", LANES)
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_check_sfx_and_world_together_is_ok(self):
        ok, reasons = lane_fence.check(
            ["assets/sounds/x.json", "assets/worlds/y.json"],
            "feat: one session owns sound and world",
            LANES,
        )
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_check_sfx_and_vfx_is_refused(self):
        ok, reasons = lane_fence.check(
            ["assets/sounds/x.json", "assets/effects/y.json"],
            "feat: touch sound and vfx",
            LANES,
        )
        self.assertFalse(ok)
        self.assertEqual(
            reasons,
            [
                "touches the own files of 2 lanes (sfx+world, vfx) - split the commit, or put the word cross in "
                "the message if it is meant"
            ],
        )

    def test_check_two_lanes_is_refused(self):
        ok, reasons = lane_fence.check(
            ["assets/effects/x.json", "assets/ui/y.json"],
            "feat: touch two lanes",
            LANES,
        )
        self.assertFalse(ok)
        self.assertEqual(
            reasons,
            [
                "touches the own files of 2 lanes (ui, vfx) - split the commit, or put the word cross in the "
                "message if it is meant"
            ],
        )

    def test_check_two_lanes_with_cross_is_ok(self):
        ok, reasons = lane_fence.check(
            ["assets/effects/x.json", "assets/ui/y.json"],
            "cross: move the effect and the UI together",
            LANES,
        )
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_check_crossing_does_not_count(self):
        ok, reasons = lane_fence.check(
            ["assets/effects/x.json", "assets/ui/y.json"],
            "crossing the lanes",
            LANES,
        )
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 1)

    def test_check_rows_missing_verdict(self):
        rows = ["+| barrel | 8 | [[3d/verdicts/barrel--2026-10-17]] |"]
        self.assertEqual(
            lane_fence.check_rows(rows, lambda path: False),
            [
                "a golden/graveyard row links 3d/verdicts/barrel--2026-10-17, which is not in the commit or the "
                "tree - commit the verdict note with it"
            ],
        )

    def test_check_rows_present_verdict(self):
        seen = []

        def present(path):
            seen.append(path)
            return True

        rows = ["+| barrel | 8 | [[3d/verdicts/barrel--2026-10-17]] |"]
        self.assertEqual(lane_fence.check_rows(rows, present), [])
        self.assertEqual(seen, ["kit/knowledge/vault/3d/verdicts/barrel--2026-10-17.md"])

    def test_check_rows_without_a_link(self):
        self.assertEqual(lane_fence.check_rows(["+| barrel | 8 | no verdict link |"], lambda path: False), [])


if __name__ == "__main__":
    unittest.main()
