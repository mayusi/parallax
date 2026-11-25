"""kit/vfx/autorec.py blank_frames (2026-10-25): a recording is blank only when no pixel ever changes - a small unlit
effect on a bright sky (senbazuru's paper cranes) barely moves the frame's MEAN but moves many pixels."""
import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def load():
    spec = importlib.util.spec_from_file_location("vfx_autorec", os.path.join(ROOT, "kit", "vfx", "autorec.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Blank(unittest.TestCase):
    def test_a_still_booth_is_blank_and_a_small_mover_is_not(self):
        a = load()
        w, h = 16, 9
        still = bytes([112] * (w * h)) * 10
        self.assertTrue(a.blank_frames(still, w, h))
        frames = bytearray()
        for i in range(10):  # a 2x2 dark shape crossing a bright sky: the mean moves < 3 levels, pixels move a lot
            f = bytearray([112] * (w * h))
            for dy in range(2):
                for dx in range(2):
                    f[(3 + dy) * w + i + dx] = 30
            frames += f
        means = [sum(frames[i * w * h:(i + 1) * w * h]) / (w * h) for i in range(10)]
        self.assertLess(max(means) - min(means), 3)  # the old mean test would have called this blank
        self.assertFalse(a.blank_frames(bytes(frames), w, h))


class Dailies(unittest.TestCase):
    """a recorded play ends with LOOK: <folder> (its dailies); the no-hands recorder passes that on (V0, 2026-11-12)"""

    LOG = "\n".join([
        "player: http://127.0.0.1:47813/lib/index.html?name=ember&view=hero&record=1&views=hero&fps=30",
        "serving (Ctrl-C to stop; exits by itself when the page has recorded)",
        "[ok] vfx play server: ember_play: 1 view(s) recorded",
        "[ok] vfx dailies: dailies ember: 2 beat(s), 12 strip(s) at 640 px a frame. 1 key: it stays: the scene 0.50 s, ours 0.20 s. LOOK: build/vfx/dailies/ember/",
        "summary: vfx play: ember recorded. dailies ember: 2 beat(s), 12 strip(s) at 640 px a frame. 1 key: it stays: "
        "the scene 0.50 s, ours 0.20 s. LOOK: build/vfx/dailies/ember/",
        "next_action: open build/vfx/dailies/ember/beat1_01.png onward at full size",
    ])

    def test_the_plays_dailies_are_read_from_its_summary_line(self):
        a = load()
        said = a.dailies_of(self.LOG)
        self.assertTrue(said.startswith("dailies ember: 2 beat(s)"), said)
        self.assertTrue(said.endswith("LOOK: build/vfx/dailies/ember/"), said)

    def test_a_play_that_named_no_folder_passes_nothing_on(self):
        a = load()
        self.assertEqual(a.dailies_of("summary: vfx play: ember recorded\nnext_action: LOOK at the mp4"), "")
        self.assertEqual(a.dailies_of("summary: vfx play: ember served (no recording)"), "")
        self.assertEqual(a.dailies_of(""), "")


if __name__ == "__main__":
    unittest.main()
