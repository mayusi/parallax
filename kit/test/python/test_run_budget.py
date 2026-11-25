"""A test file's own time budget in the Python runner (kit/test/python/_proc.py file_timeout, used by run.py).

The owner, 2026-11-22 ("Per-file budget 3600 s"): test_photoscan_build runs ~27 minutes of GPU dense stereo and the
runner's 1200 s per-file default killed it every run. A file may declare `KIT_PY_FILE_TIMEOUT = <s>`; the runner is
still a hang detector - no file asks past the cap, none drops below the default, a file that says nothing keeps it."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _proc  # noqa: E402


def budget(text, default=1200):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(text)
    try:
        return _proc.file_timeout(fh.name, default)
    finally:
        os.remove(fh.name)


class FileBudget(unittest.TestCase):
    def test_a_file_that_declares_nothing_keeps_the_default(self):
        self.assertEqual(budget("import os\n"), 1200)

    def test_a_declared_budget_is_used(self):
        self.assertEqual(budget("import os\nKIT_PY_FILE_TIMEOUT = 2400  # why\n"), 2400)

    def test_no_file_asks_past_the_cap(self):
        self.assertEqual(budget("KIT_PY_FILE_TIMEOUT = 999999\n"), _proc.BUDGET_CAP)

    def test_no_file_drops_below_the_default(self):
        self.assertEqual(budget("KIT_PY_FILE_TIMEOUT = 5\n"), 1200)

    def test_only_a_line_of_its_own_counts(self):
        # (a mention in a comment or a string is not a declaration)
        self.assertEqual(budget("# KIT_PY_FILE_TIMEOUT = 3600\nx = 'KIT_PY_FILE_TIMEOUT = 3600'\n"), 1200)

    def test_a_missing_file_keeps_the_default(self):
        self.assertEqual(_proc.file_timeout(os.path.join(HERE, "no_such_test_file.py"), 1200), 1200)

    def test_the_photoscan_build_declares_the_owners_budget(self):
        self.assertEqual(_proc.file_timeout(os.path.join(HERE, "test_photoscan_build.py"), 1200), 3600)


class HistoryLimit(unittest.TestCase):
    """a file with no declared budget gets 3x its SLOWEST recent time (2026-11-23: test_low_mixed's one 21 s run set a
    120 s limit and it TIMED OUT on every run after it, 177 s alone; a timed-out run kept the old entry for ever)"""

    def test_the_slowest_recent_run_sets_the_limit_not_the_last(self):
        self.assertEqual(_proc.limit_from([62.0, 80.0, 21.1], 120, 1200), 240)

    def test_the_floor_and_the_cap_still_hold(self):
        self.assertEqual(_proc.limit_from([5.0], 120, 1200), 120)
        self.assertEqual(_proc.limit_from([900.0], 120, 1200), 1200)  # (a hang is still stopped)
        self.assertIsNone(_proc.limit_from([], 120, 1200))

    def test_an_entry_from_before_the_history_counts_its_last_time(self):
        self.assertEqual(_proc.history({"s": 21.1, "kind": "blender"}), [21.1])
        self.assertEqual(_proc.history({"s": 30.0, "recent": [40.0, 50.0]}), [40.0, 50.0])
        self.assertEqual(_proc.history(None), [])

    def test_a_timed_out_run_raises_the_next_limit(self):
        e = _proc.remember({"s": 21.1, "kind": "blender"}, 240.0, True, 120, "blender")
        self.assertEqual(e["s"], 21.1)  # (its last time stays for the order)
        self.assertEqual(_proc.history(e), [21.1, 120.0])
        self.assertEqual(_proc.limit_from(_proc.history(e), 120, 1200), 360)  # (177 s alone now fits)

    def test_a_run_joins_the_history_and_only_the_last_five_are_kept(self):
        e = {"s": 10.0, "recent": [10.0, 11.0, 12.0, 13.0, 14.0]}
        e = _proc.remember(e, 15.04, False, 120, "plain")
        self.assertEqual(e["s"], 15.0)
        self.assertEqual(e["recent"], [11.0, 12.0, 13.0, 14.0, 15.0])
        self.assertEqual(e["kind"], "plain")


if __name__ == "__main__":
    unittest.main()
