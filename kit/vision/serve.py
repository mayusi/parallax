"""serve.py — a WARM vision worker: kit/vision/run.py's models (TEED, BiRefNet, SAM 2.1, Depth Anything, SigLIP 2,
DINOv2) loaded ONCE and kept, every `kit vision` / cut-out / rank call answered in-process instead of a fresh Python
that loads its model again (kit/lib/run.luau routes `kit/vision/run.py` steps here whenever this worker answers).

    python kit/vision/serve.py [--idle 1200]

Like the Blender worker (kit/blender/worker.py): 127.0.0.1 on a free port, a token, the state in <build>/vision_worker.json;
every call runs on THIS process's main thread, one at a time (the GPU is one card). /free drops the models and empties
CUDA's cache — a big generator (kit gen ...) asks for the whole card first; the next call loads again. It retires when
idle for --idle seconds, on /quit, when kit/vision's code or its model pins (models.json) changed, or after a call
CRASHED (an exception can leave CUDA broken: the client runs that call cold) — every such call runs cold; start a
fresh worker with `kit vision serve`.
"""

import contextlib
import glob
import io
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.getcwd()
KIT_BUILD = os.environ.get("KIT_BUILD", "build")
STATE = os.path.join(ROOT, KIT_BUILD, "vision_worker.json")
TOKEN = secrets.token_hex(16)
JOBS = queue.Queue()
RESULTS = {}
STATUS = {"last": time.time(), "quit": False, "busy": None, "calls": 0, "loaded": []}
sys.path.insert(0, HERE)


def _kit_stamp():
    """the newest change to the vision code this worker imported once, or to its model pins: newer = stale"""
    files = glob.glob(os.path.join(HERE, "*.py")) + glob.glob(os.path.join(HERE, "*.json"))
    return max((os.path.getmtime(p) for p in files), default=0.0)


STAMP = _kit_stamp()


def _args(argv):
    return float(argv[argv.index("--idle") + 1]) if "--idle" in argv else 1200.0


def call(run, argv):
    """one `kit/vision/run.py <argv>` in-process -> (exit code, its stdout, its stderr, crashed) — stdout holds the
    verdict line exactly as a cold run's; crashed = an exception escaped (CUDA may be broken: the worker retires and
    the client runs this call cold)"""
    out, err = io.StringIO(), io.StringIO()
    crashed = False
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = run.main([str(a) for a in argv])
        except SystemExit as e:  # (argparse-style exits)
            code = int(e.code or 0)
        except Exception as e:  # noqa: BLE001 — answered; the worker retires only when CUDA may be broken
            import traceback  # noqa: PLC0415

            traceback.print_exc()
            code = 1
            # (a missing model, a corrupt picture, a bad --point fail cold the same way: answered, the worker stays;
            #  a CUDA / out-of-memory error can leave the device unusable: the worker retires, the call runs cold)
            crashed = bool(re.search(r"cuda|cudnn|cublas|out of memory|outofmemory|device-side",
                                     f"{type(e).__name__} {e}", re.IGNORECASE))
            print(json.dumps({"schema": 1, "status": "fail", "summary": f"vision worker: {type(e).__name__}: {e}",
                              "next_action": "the call runs cold now; the worker retired"}))
    return code, out.getvalue(), err.getvalue(), crashed


def free(run):
    """drop every loaded model and give the card back (a generator needs all of it) -> the models dropped"""
    import gc  # noqa: PLC0415

    dropped = sorted(run._MODELS)
    run._MODELS.clear()
    if "vlm" in sys.modules and sys.modules["vlm"]._M:  # (the re-ranker's language model keeps its own cache)
        dropped.append(sys.modules["vlm"].NAME)
        sys.modules["vlm"].free()
    gc.collect()
    try:
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    return dropped


def _retire():
    STATUS["quit"] = True
    STATUS["closing"] = True
    try:
        with open(STATE, encoding="utf-8") as fh:
            ours = json.load(fh).get("pid") == os.getpid()
        if ours:
            os.remove(STATE)
    except (OSError, ValueError):
        pass


class Handler(BaseHTTPRequestHandler):
    """(a server THREAD: it only queues work and reads results — every model call stays on the main thread)"""
    server_version = "kit-vision-worker/1"

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass

    def _authorised(self):
        if self.headers.get("X-Kit-Token") != TOKEN:
            self._send(403, {"error": "bad token"})
            return False
        STATUS["last"] = time.time()
        return True

    def _route(self):
        return urlsplit(self.path).path.rstrip("/") or "/"

    def do_GET(self):  # noqa: N802
        path = self._route()
        if path == "/ping":
            if STATUS.get("closing"):
                return self._send(503, {"ok": False, "closing": True})
            return self._send(200, {"ok": True, "kind": "vision", "pid": os.getpid(), "busy": STATUS["busy"],
                                    "calls": STATUS["calls"], "loaded": STATUS["loaded"]})
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
        if path not in ("/run", "/free"):
            return self._send(404, {"error": f"unknown path {path}"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        if STATUS.get("closing") or _kit_stamp() != STAMP:
            _retire()  # stale modules: retire FIRST; the client runs this call cold
            return self._send(200, {"restart": True})
        job = secrets.token_hex(6)
        JOBS.put((job, path[1:], [str(a) for a in req.get("argv") or []]))
        return self._send(200, {"job": job})


def _quiet():
    """our own stdout / stderr go to <build>/vision_worker.log (a full pipe nobody reads would freeze every call)"""
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    log = open(os.path.join(os.path.dirname(STATE), "vision_worker.log"), "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    sys.stdout, sys.stderr = log, log
    return log


def detach(argv):
    """start a worker that OUTLIVES its caller and return at once: the same script, its own process — no console, no
    inherited pipes (a Lune child ends with its command; a pipe it holds open would keep the caller waiting). Argument
    lists only, no shell."""
    import subprocess  # noqa: PLC0415

    args = [a for a in argv if a != "--detach"]
    kw = {"cwd": ROOT, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "close_fds": True}
    cmd = [sys.executable, os.path.abspath(__file__), *args]
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:
            # (Lune runs its children in a Windows job that ends every process inside when the command exits —
            #  measured: a detached worker died with `kit vision serve`; breaking away from the job keeps it)
            proc = subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:  # (a job that forbids breaking away: the worker lives as long as its command)
            proc = subprocess.Popen(cmd, creationflags=flags, **kw)
    else:
        proc = subprocess.Popen(cmd, start_new_session=True, **kw)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"vision worker starting (pid {proc.pid})",
                      "next_action": "none", "pid": proc.pid}))
    return 0


def main(argv):
    if "--detach" in argv:
        return detach(argv)
    idle = _args(argv)
    _quiet()
    import run  # noqa: PLC0415  (the models load on first use, then stay)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"port": server.server_address[1], "token": TOKEN, "pid": os.getpid(), "kit_build": KIT_BUILD,
                   "started": time.time()}, fh)
    print(f"kit vision worker: 127.0.0.1:{server.server_address[1]} (pid {os.getpid()})", flush=True)
    try:
        while not STATUS["quit"] and time.time() - STATUS["last"] < idle:
            try:
                job, kind, args = JOBS.get(timeout=0.5)
            except queue.Empty:
                continue
            STATUS["busy"] = " ".join(args[:1]) or kind
            t = time.time()
            crashed, err = False, ""
            if kind == "free":
                dropped = free(run)
                code, out = 0, json.dumps({"schema": 1, "status": "pass", "next_action": "none",
                                           "summary": f"vision worker: freed {', '.join(dropped) or 'nothing'}"})
            else:
                code, out, err, crashed = call(run, args)
                STATUS["calls"] += 1
            vlm_ = sys.modules.get("vlm")  # (the re-ranker's language model keeps its own cache: report it too)
            STATUS["loaded"] = sorted(run._MODELS) + ([vlm_.NAME] if vlm_ is not None and vlm_._M else [])
            RESULTS[job] = {"exit": code, "output": out, "stderr": err, "crashed": crashed,
                            "seconds": round(time.time() - t, 3)}
            STATUS["busy"], STATUS["last"] = None, time.time()
            if crashed:
                time.sleep(1.0)  # (the client collects this answer — it runs the call cold — then we are gone)
                break
    finally:
        _retire()
        time.sleep(1.0)
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
