"""kit/vision/serve.py — the WARM vision worker (kit/vision/run.py's models loaded once): one call in-process gives the
exit code and the stdout verdict line a fresh python would (stderr apart, as a cold run's); a call that CRASHES is
answered and flagged so the worker retires and the client runs it cold (an exception can leave CUDA broken); /free
drops the models and says which; the model pins count as code (a changed pin retires it); --detach starts the worker
as its own process with argument lists only (no shell), breaking away from the caller's job on Windows. Measured on
a test PC (2026-10-08): 10 calls 99.8 s cold -> 13.8 s warm, outputs pixel-identical. Fakes only: no model loads."""

import io
import json
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vision"))
import serve as S  # noqa: E402


def fake_run(code=0, boom=None):
    """a stand-in for kit/vision/run.py: main(argv) prints its verdict line (stdout) and a warning (stderr)"""
    def main(argv):
        if boom:
            raise boom
        print("a library's warning", file=sys.stderr)
        print(json.dumps({"schema": 1, "status": "pass" if code == 0 else "fail", "summary": " ".join(argv),
                          "next_action": "none"}))
        return code
    return types.SimpleNamespace(main=main, _MODELS={"birefnet": object(), "sam": object()})


class TestWorker(unittest.TestCase):
    def test_a_call_gives_the_code_and_the_verdict_line_a_cold_run_would(self):
        code, out, err, crashed = S.call(fake_run(), ["cutout", "x.png", "-o", "y.png"])
        self.assertEqual((code, crashed), (0, False))
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["summary"], "cutout x.png -o y.png")
        self.assertNotIn("warning", out)  # (stderr apart: the verdict is stdout's, as a cold run's)
        self.assertIn("warning", err)
        code, *_ = S.call(fake_run(code=1), ["view", "x.png"])
        self.assertEqual(code, 1)

    def test_a_crashing_call_is_answered_and_flagged(self):
        code, out, err, crashed = S.call(fake_run(boom=RuntimeError("CUDA error: an illegal memory access")),
                                         ["depth", "x.png"])
        self.assertEqual((code, crashed), (1, True))
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["status"], "fail")
        self.assertIn("illegal memory access", err)  # (the traceback, for whoever reads the log)

    def test_a_plain_failure_keeps_the_worker_only_cuda_trouble_retires_it(self):
        for boom in (ValueError("--point lands outside the picture"), FileNotFoundError("no such picture")):
            code, out, err, crashed = S.call(fake_run(boom=boom), ["mask", "x.png"])
            self.assertEqual((code, crashed), (1, False), boom)  # (answered; it fails cold the same way)
        for boom in (RuntimeError("CUDA error: device-side assert triggered"), MemoryError("CUDA out of memory")):
            self.assertTrue(S.call(fake_run(boom=boom), ["depth", "x.png"])[3], boom)

    def test_free_drops_every_model_and_says_which(self):
        run = fake_run()
        self.assertEqual(S.free(run), ["birefnet", "sam"])
        self.assertEqual(run._MODELS, {})

    def test_the_model_pins_count_as_code(self):
        with mock.patch("glob.glob", side_effect=lambda pat: [pat.replace("*", "x")]), \
                mock.patch("os.path.getmtime", side_effect=lambda p: 2.0 if p.endswith(".json") else 1.0):
            self.assertEqual(S._kit_stamp(), 2.0)

    def test_detach_starts_its_own_process_with_argument_lists_only(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            popen.return_value = types.SimpleNamespace(pid=4242)
            self.assertEqual(S.detach(["--detach", "--idle", "300"]), 0)
        cmd = popen.call_args.args[0]
        self.assertIsInstance(cmd, list)  # (never a shell string)
        self.assertEqual(cmd[1:], [os.path.abspath(S.__file__), "--idle", "300"])
        kw = popen.call_args.kwargs
        self.assertNotIn("shell", kw)
        if os.name == "nt":
            self.assertTrue(kw["creationflags"] & 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB first
        self.assertEqual(json.loads(out.getvalue())["pid"], 4242)

    def test_a_job_that_forbids_breaking_away_still_starts_the_worker(self):
        if os.name != "nt":
            self.skipTest("Windows job objects only")
        calls = []

        def popen(cmd, **kw):
            calls.append(kw["creationflags"])
            if kw["creationflags"] & 0x01000000:
                raise PermissionError("access denied")
            return types.SimpleNamespace(pid=7)
        with mock.patch("subprocess.Popen", side_effect=popen), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(S.detach(["--detach"]), 0)
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[1] & 0x01000000)


if __name__ == "__main__":
    unittest.main()
