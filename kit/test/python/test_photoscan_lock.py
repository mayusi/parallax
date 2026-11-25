"""Two photoscan runs in one work folder (kit/tools/photoscan.py hold_work; 2026-11-20, V4 Phase 3: two runs of
test_photoscan_build at once - the second cleared the folder while the first's COLMAP held its database open, Windows
refused the delete, and the thin scan died with a bare traceback: exit 1, nothing on stdout, read as a crash).
Now the second run waits for the first, refuses by name when it waits too long, and a file held open by any other
program is said by name. Fast: no COLMAP run."""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import photoscan as P  # noqa: E402


def write(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(text)


class Hold(unittest.TestCase):
    def test_a_second_run_waits_then_refuses_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            first = P.hold_work(d)
            try:
                t = time.time()
                with self.assertRaises(RuntimeError) as e:
                    P.hold_work(d, wait=0.4)
                self.assertGreaterEqual(time.time() - t, 0.35)            # (it waited)
                self.assertIn("another photoscan run is using the work folder", str(e.exception))
            finally:
                first.close()

    def test_a_waiting_run_goes_on_when_the_first_lets_go(self):
        with tempfile.TemporaryDirectory() as d:
            first = P.hold_work(d)
            threading.Timer(0.5, first.close).start()
            second = P.hold_work(d, wait=20)
            second.close()

    def test_a_run_that_ended_never_blocks_the_next(self):
        with tempfile.TemporaryDirectory() as d:
            P.hold_work(d).close()
            P.hold_work(d, wait=0).close()

    def test_the_clear_never_takes_the_lock_or_the_mark(self):
        with tempfile.TemporaryDirectory() as d:
            held = P.hold_work(d)
            try:
                write(d, P.MARK, "")
                write(d, "colmap.log", "x")
                P.clear_work(d)
                self.assertEqual(sorted(os.listdir(d)), sorted([P.MARK, P.LOCK]))
            finally:
                held.close()


@unittest.skipUnless(os.path.isfile(P.COLMAP), "COLMAP not found (VETLOG.md 2026-11-16): scan stops before the clear")
class Refused(unittest.TestCase):
    def test_a_file_another_program_holds_is_said_by_name_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work")
            write(work, P.MARK, "")
            write(work, "database.db", "x")
            real = P.os.remove

            def held(path):
                if path.endswith("database.db"):
                    raise PermissionError(32, "in use by another process", path)
                return real(path)

            P.os.remove = held
            try:
                with self.assertRaises(RuntimeError) as e:
                    P.scan(os.path.join(d, "photos"), "x", work=work)
            finally:
                P.os.remove = real
            self.assertIn("database.db is held open by another program", str(e.exception))

    @unittest.skipUnless(os.name == "nt", "an open file blocks its delete on Windows only")
    def test_the_tool_prints_a_summary_for_it(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work")
            write(work, P.MARK, "")
            with open(os.path.join(work, "database.db"), "w") as fh:   # (another run's COLMAP holding it)
                fh.write("x")
                fh.flush()
                r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "photoscan.py"),
                                    os.path.join(d, "photos"), "x", "--work", work, "--out", d],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertEqual(r.returncode, 1, r.stderr[-400:])
            self.assertIn("summary: photoscan failed", r.stdout)
            self.assertIn("held open by another program", r.stdout)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
