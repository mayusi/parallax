"""kit ui refs: any MediaWiki host is a source; game FRAMES rank before icons"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_refs", os.path.join(HERE, "..", "..", "ui", "refs.py"))
refs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refs)


class TestRefs(unittest.TestCase):
    def test_frames_rank_first_and_icons_are_dropped(self):
        self.assertEqual(refs.is_frame([1920, 1080]), 2)
        self.assertEqual(refs.is_frame([2560, 1600]), 2)       # 16:10
        self.assertEqual(refs.is_frame([1000, 800]), 1)        # a big picture, not a frame
        self.assertIsNone(refs.is_frame([256, 256]))           # an icon: no HUD to read in it
        self.assertEqual(refs.is_frame(None), 1)               # unknown size: kept, unranked

    def test_a_fandom_subdomain_needs_no_lookup(self):
        self.assertEqual(refs.wiki_base("megamitensei"), ("https://megamitensei.fandom.com/api.php", "https://megamitensei.fandom.com/wiki/"))


if __name__ == "__main__":
    unittest.main()
