"""_proc.py - run one test file as a process TREE (kit/test/python/run.py; not a test file itself).

subprocess.run(timeout=) stops only the process it started. A test file that drives tools (photoscan.py -> COLMAP,
Blender) left those running after its timeout, and the runner's retry of the same file ran beside them in the same
build folder (2026-11-20, V4 Phase 3: test_photoscan_build's thin scan, two runs in one work folder - the second
died with a bare traceback). On a timeout the whole tree is stopped before the error is raised."""

import os
import re
import signal
import subprocess

# A test file's OWN time budget, read from its source (never imported): a line
#     KIT_PY_FILE_TIMEOUT = 3600  # why
# The owner, 2026-11-22 ("Per-file budget 3600 s"): test_photoscan_build is ~27 minutes of GPU dense stereo on a
# quiet machine and the runner's 1200 s default killed it every run. It is still a HANG detector: no file may ask
# past BUDGET_CAP, and a file that declares nothing keeps the runner's default.
BUDGET_CAP = 3600
_BUDGET = re.compile(r"^KIT_PY_FILE_TIMEOUT\s*=\s*(\d+)\b", re.M)


def file_timeout(path, default):
    """the seconds this test file may run: its declared KIT_PY_FILE_TIMEOUT (at most BUDGET_CAP, never below the
    default), else `default`"""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            m = _BUDGET.search(fh.read())
    except OSError:
        return default
    if not m:
        return default
    return max(default, min(BUDGET_CAP, int(m.group(1))))


# A file with no declared budget: three times its SLOWEST recent time (the runner keeps the last RECENT runs in
# .verify/py_test_timings.json), at least `floor`, never past `cap`. The slowest, not the last: one fast run must not
# set a limit its normal runs blow (2026-11-23: test_low_mixed ran 62, 80, 223 s, then once 21 s -> a 120 s limit ->
# TIMED OUT beside the pool AND alone - a red verify with 0 failed tests; alone it took 177 s).
RECENT = 5


def history(entry):
    """a timings entry's recent times (newest last); an entry from before the history counts its one last time"""
    entry = entry if isinstance(entry, dict) else {}
    recent = [float(x) for x in (entry.get("recent") or []) if isinstance(x, (int, float)) and x > 0]
    if not recent and isinstance(entry.get("s"), (int, float)) and entry["s"] > 0:
        recent = [float(entry["s"])]
    return recent


def limit_from(recent, floor, cap):
    """the seconds a file with this history may run, or None with no history"""
    if not recent:
        return None
    return int(min(cap, max(floor, 3 * max(recent))))


def remember(entry, seconds, timed_out, limit, kind):
    """the timings entry after a run: its last time and history; a TIMED-OUT run puts its limit in the history (it ran
    at least that long: the next limit is three times it, still capped) and keeps its last time for the order -
    before, it kept its old entry and nothing else, so a file whose one fast run set too short a limit timed out on
    every run after it, for ever"""
    entry = entry if isinstance(entry, dict) else {}
    recent = history(entry)
    if timed_out:
        return dict(entry, recent=(recent + [float(limit)])[-RECENT:], kind=kind)
    return {"s": round(seconds, 1), "recent": (recent + [round(seconds, 1)])[-RECENT:], "kind": kind}


def kill_tree(p):
    """stop `p` and everything it started (Windows: taskkill /T; elsewhere: its own process group)"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        p.kill()
    except OSError:
        pass


def run_tree(argv, timeout, **kw):
    """subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kw), but a timeout stops the whole
    process tree (then raises subprocess.TimeoutExpired with what was printed so far, like subprocess.run)"""
    if os.name != "nt":
        kw["start_new_session"] = True     # (its own process group: killpg reaches the grandchildren)
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(p)
        out, err = p.communicate()
        raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err) from None
    return subprocess.CompletedProcess(argv, p.returncode, out, err)
