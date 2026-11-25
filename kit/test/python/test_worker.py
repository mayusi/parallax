"""The persistent Blender worker's lifecycle (kit/blender/worker.py), run under plain python with stand-ins for bpy and
rbx (no build is made): it binds 127.0.0.1, refuses requests without its token, and a worker asked to RESTART (the
kit changed, another build folder) or to quit is never handed out again — its state file is gone and its ping answers
503 before the answer leaves, so kit/lib/worker.luau starts a fresh one instead of reusing a dying one."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

WORKER = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender", "worker.py"))
RUNNER = """
import runpy, sys, types
bpy = types.ModuleType("bpy")
bpy.app = types.SimpleNamespace(binary_path=sys.executable)
sys.modules["bpy"] = bpy
sys.modules["rbx"] = types.ModuleType("rbx")
sys.argv = [sys.argv[1], "--", "--idle", "60"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def setUpModule():
    """the HTTP calls here go to 127.0.0.1; if another test imported the vision code (kit/vision/run.py blocks every
    socket in its process: offline by design), the socket module is reloaded fresh for this module's calls"""
    import importlib
    import socket

    if "connect" in socket.socket.__dict__ or getattr(socket.getaddrinfo, "__name__", "") != "getaddrinfo":
        importlib.reload(socket)


def call(port, path, token=None, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Kit-Token": token or "", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except (urllib.error.URLError, ConnectionError, OSError):
        return None, {}


class TestWorkerLifecycle(unittest.TestCase):
    def _start(self, d):
        runner = os.path.join(d, "runner.py")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write(RUNNER)
        build = os.path.join(d, "build")
        proc = subprocess.Popen([sys.executable, runner, WORKER], cwd=d, env=dict(os.environ, KIT_BUILD=build),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = os.path.join(build, "worker.json")
        for _ in range(200):
            if os.path.isfile(state):
                try:
                    with open(state, encoding="utf-8") as fh:
                        return proc, state, json.load(fh)
                except ValueError:
                    pass
            time.sleep(0.05)
        proc.kill()
        self.fail("the worker never wrote its state file")

    def test_a_restarting_worker_is_never_found_again(self):
        with tempfile.TemporaryDirectory() as d:
            proc, state, st = self._start(d)
            try:
                port, token = st["port"], st["token"]
                self.assertEqual(call(port, "/ping")[0], 200)
                self.assertEqual(call(port, "/build", "wrong", {"script": "x"})[0], 403)  # no token, no work
                code, ans = call(port, "/build", token, {"script": "x", "env": {"KIT_BUILD": os.path.join(d, "other")}})
                self.assertEqual((code, ans.get("restart")), (200, True))
                # BEFORE the answer left: no state file (nobody finds it) and a ping that says it is going
                self.assertFalse(os.path.isfile(state))
                self.assertIn(call(port, "/ping")[0], (503, None))
                self.assertEqual(call(port, "/build", token, {"script": "x", "env": {}})[1].get("restart"), True)
                proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()

    def test_quit_retires_it_too(self):
        with tempfile.TemporaryDirectory() as d:
            proc, state, st = self._start(d)
            try:
                self.assertEqual(call(st["port"], "/quit", st["token"], {})[0], 200)
                self.assertFalse(os.path.isfile(state))
                self.assertIn(call(st["port"], "/ping")[0], (503, None))
                proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()


if __name__ == "__main__":
    unittest.main()
