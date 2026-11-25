"""The Python test runner stops a timed-out file's WHOLE process tree (kit/test/python/_proc.py, used by run.py).

2026-11-20 (V4 Phase 3): test_photoscan_build ran past the runner's per-file timeout; only pytest was stopped, its
photoscan / COLMAP / Blender children ran on, and the runner's retry of the file scanned into the same build folder
beside them - the thin scan died with a bare traceback. Here a child starts a grandchild that writes a heartbeat;
after the timeout the heartbeat must stop."""

import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _proc  # noqa: E402

GRANDCHILD = r'''
import sys, time
path = sys.argv[1]
for _ in range(600):
    with open(path, "a") as fh:
        fh.write("x")
    time.sleep(0.1)
'''

CHILD = r'''
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]])
time.sleep(60)
'''


def size(path):
    return os.path.getsize(path) if os.path.isfile(path) else 0


class TreeKill(unittest.TestCase):
    def test_a_timed_out_file_takes_what_it_started_with_it(self):
        with tempfile.TemporaryDirectory() as d:
            beat = os.path.join(d, "beat.txt")
            t = time.time()
            with self.assertRaises(subprocess.TimeoutExpired):
                _proc.run_tree([sys.executable, "-c", CHILD, GRANDCHILD, beat], 3)
            self.assertLess(time.time() - t, 30)                     # (it did not wait for the grandchild)
            self.assertGreater(size(beat), 0, "the grandchild never started")
            time.sleep(0.5)
            before = size(beat)
            time.sleep(1.5)
            self.assertEqual(size(beat), before, "the grandchild still runs after the timeout")

    def test_a_file_that_ends_in_time_gives_its_output_and_code(self):
        r = _proc.run_tree([sys.executable, "-c", "import sys; print('ok'); sys.exit(3)"], 30)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "ok"))


if __name__ == "__main__":
    unittest.main()
