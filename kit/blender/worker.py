"""worker.py — a PERSISTENT Blender: builds on request without paying Blender's start-up every time (measured: 2.2 s
of every build is Blender starting and the kit importing; a --geo check of a small prop is ~4 s in all).

    blender -b --factory-startup --python-exit-code 2 -P kit/blender/worker.py -- [--idle 1800]

Run from the project root (lune run kit watch / kit fit start it). It listens on 127.0.0.1 only, on a random port,
and writes build/worker.json {port, token, pid, kit_build}: a request must carry the token. Every build runs exactly
as a fresh `blender -b --factory-startup -P <script> -- <args>` would:
  - the scene is reset to factory settings first (nothing from the last build survives),
  - sys.argv is the script's own, the request's environment variables apply for that build only,
  - the GPU device is selected again (a factory reset forgets it).
It answers with the build's whole printed output (the JSON verdict line is in it) and the exit code a fresh Blender
would have returned (2 = the script raised). When a kit file changes (kit/blender/*.py) or a request needs another
KIT_BUILD, it answers {"restart": true} and exits: the client starts a fresh worker (modules are never reloaded
in place — a half-reloaded kit would build with stale code). Exits after --idle seconds without a request, or on
POST /quit.
"""

import contextlib
import glob
import io
import json
import os
import queue
import runpy
import secrets
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rbx  # noqa: E402  (imported once: what a fresh process would import on every build)

ROOT = os.getcwd()
KIT_BUILD = os.environ.get("KIT_BUILD", "build")
STATE = os.path.join(ROOT, KIT_BUILD, "worker.json")
TOKEN = secrets.token_hex(16)
JOBS = queue.Queue()
RESULTS = {}
STATUS = {"last": time.time(), "quit": False, "busy": None}


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return float(argv[argv.index("--idle") + 1]) if "--idle" in argv else 1800.0


def _kit_stamp():
    """the newest change to what the kit imports once (its Blender code, the fitted weights): newer = stale modules"""
    files = glob.glob(os.path.join(HERE, "*.py")) + [os.path.join(os.path.dirname(HERE), "weights.json")]
    return max((os.path.getmtime(p) for p in files if os.path.isfile(p)), default=0.0)


def _same_dir(build_dir):
    """is a request's KIT_BUILD this worker's (rbx fixed its folders at import)? Paths compare resolved, any slashes"""
    norm = lambda p: os.path.normcase(os.path.abspath(os.path.join(ROOT, p)))  # noqa: E731
    return norm(build_dir) == norm(KIT_BUILD)


STAMP = _kit_stamp()
BLENDER = bpy.app.binary_path


def build(script, args, env):
    """one build, as a fresh process would run it -> (exit code, printed output). MAIN THREAD only (bpy)."""
    bpy.ops.wm.read_factory_settings()  # the same start as `blender -b --factory-startup`
    rbx._DEVICE = None  # (the factory reset forgot the GPU: select it again)
    saved_env = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    saved_argv = sys.argv
    sys.argv = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", *args]
    out = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out):
            runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except BaseException:  # noqa: BLE001 — a failing build is an answer, never the worker's end
        out.write(chr(10) + traceback.format_exc())
        code = 2
    finally:
        sys.argv = saved_argv
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return code, out.getvalue()


def _retire():
    """stop being FOUND before stopping to work: our state file goes first (kit/lib/worker.luau finds a worker through
    it) and every request is refused from now on — a client must never be handed a worker that is on its way out"""
    STATUS["quit"] = True
    STATUS["closing"] = True
    try:
        with open(STATE, encoding="utf-8") as fh:
            ours = json.load(fh).get("pid") == os.getpid()  # (only our own record: a newer worker may have written its own)
        if ours:
            os.remove(STATE)  # (after the file is closed: Windows never deletes an open file)
    except (OSError, ValueError):
        pass


class Handler(BaseHTTPRequestHandler):
    """(a server THREAD: it only queues work and reads results — every bpy call stays on the main thread)"""
    server_version = "kit-worker/1"

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):  # (quiet: the client prints what matters)
        pass

    def _authorised(self):
        if self.headers.get("X-Kit-Token") != TOKEN:
            self._send(403, {"error": "bad token"})
            return False
        STATUS["last"] = time.time()
        return True

    def _route(self):
        """the request's path alone (some clients send an absolute URL as the request target)"""
        return urlsplit(self.path).path.rstrip("/") or "/"

    def do_GET(self):  # noqa: N802
        path = self._route()
        if path == "/ping":
            if STATUS.get("closing"):
                return self._send(503, {"ok": False, "closing": True})
            return self._send(200, {"ok": True, "pid": os.getpid(), "kit_build": KIT_BUILD, "busy": STATUS["busy"]})
        if path.startswith("/result/") and self._authorised():
            job = path.split("/")[-1]
            if job in RESULTS:
                return self._send(200, {"done": True, **RESULTS.pop(job)})
            return self._send(200, {"done": False, "busy": STATUS["busy"]})
        if not path.startswith("/result/"):
            return self._send(404, {"error": f"unknown path {path}"})
        return None

    def do_POST(self):  # noqa: N802
        if not self._authorised():
            return None
        path = self._route()
        if path == "/quit":
            _retire()
            return self._send(200, {"ok": True})
        if path != "/build":
            return self._send(404, {"error": f"unknown path {path}"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        env = {str(k): str(v) for k, v in (req.get("env") or {}).items()}
        if STATUS.get("closing") or _kit_stamp() != STAMP or _same_dir(env.get("KIT_BUILD", KIT_BUILD)) is False:
            _retire()  # stale modules / another build folder: retire FIRST, then a fresh worker answers instead
            return self._send(200, {"restart": True})
        script = str(req.get("script") or "")
        if not os.path.isfile(script):
            return self._send(400, {"error": f"no script {script}"})
        job = secrets.token_hex(6)
        JOBS.put((job, script, [str(a) for a in req.get("args") or []], env))
        return self._send(200, {"job": job})


def _quiet():
    """the process's own stdout / stderr (Blender's C-level prints too) go to <build>/worker.log: whoever started this
    worker may never read its pipe, and a full pipe would freeze every build (measured: Lune's process.create pipes
    a child's output and ignores stdio="none")"""
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    log = open(os.path.join(os.path.dirname(STATE), "worker.log"), "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    sys.stdout, sys.stderr = log, log
    return log


def main():
    idle = _args()
    _quiet()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # local only, a free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"port": server.server_address[1], "token": TOKEN, "pid": os.getpid(), "kit_build": KIT_BUILD,
                   "started": time.time()}, fh)
    print(f"kit worker: 127.0.0.1:{server.server_address[1]} (pid {os.getpid()})", flush=True)
    try:
        while not STATUS["quit"] and time.time() - STATUS["last"] < idle:
            try:
                job, script, args, env = JOBS.get(timeout=0.5)
            except queue.Empty:
                continue
            STATUS["busy"] = os.path.basename(script)
            t = time.time()
            code, out = build(script, args, env)
            RESULTS[job] = {"exit": code, "output": out, "seconds": round(time.time() - t, 2)}
            STATUS["busy"], STATUS["last"] = None, time.time()
    finally:
        _retire()  # (no longer found or handed out ...)
        time.sleep(1.0)  # (... while a client collects the last result)
        server.shutdown()


main()
