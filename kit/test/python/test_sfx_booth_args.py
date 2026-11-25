"""kit sfx listen's words (kit/audio/booth.py parse; the V3 list's SFX seam "missing kit sfx listen --refs"): --refs is
--ref's plural spelling, and a flag the booth does not know is REFUSED - before, `--refs x.wav` became two sound names
and the booth said they were "not rendered"."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "audio"))
import booth as B  # noqa: E402


class Args(unittest.TestCase):
    def test_names_and_the_reference(self):
        got, wrong = B.parse(["hit_a", "hit_b", "--ref", "refs/hit.wav", "--blind"])
        self.assertIsNone(wrong)
        self.assertEqual((got["names"], got["ref"], got["blind"], got["port"]),
                         (["hit_a", "hit_b"], "refs/hit.wav", True, 8791))

    def test_refs_is_the_same_as_ref(self):
        self.assertEqual(B.parse(["hit_a", "--refs", "refs/hit.wav"])[0]["ref"], "refs/hit.wav")
        self.assertEqual(B.parse(["hit_a", "--refs", "refs/hit.wav"])[0]["names"], ["hit_a"])

    def test_an_unknown_flag_is_refused_not_taken_as_a_name(self):
        got, wrong = B.parse(["hit_a", "--reff", "refs/hit.wav"])
        self.assertIsNone(got)
        self.assertIn("--reff: not a booth option", wrong)

    def test_a_flag_with_no_value_is_refused(self):
        self.assertEqual(B.parse(["hit_a", "--ref"])[1], "--ref needs a value")
        self.assertEqual(B.parse(["hit_a", "--ref", "--blind"])[1], "--ref needs a value")
        self.assertEqual(B.parse(["--port", "eighty"])[1], "--port eighty: a port number")

    def test_the_port_and_the_switches(self):
        got, _ = B.parse(["--stop", "--port", "8800"])
        self.assertEqual((got["stop"], got["port"], got["names"]), (True, 8800, []))
        got, _ = B.parse(["--serve", "--port", "8791", "--page", "p.html"])
        self.assertEqual((got["serve"], got["page"]), (True, "p.html"))


if __name__ == "__main__":
    unittest.main()
