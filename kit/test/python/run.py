"""run.py — the kit's Python unit tests (pure functions: the CMA-ES optimiser, the wood grain axis, ...), run by
`lune run kit verify`. Needs numpy; a python without it is told so and skipped (never a silent pass).

Every test FILE runs in its own interpreter. The lanes' modules share names (kit/ui/plan.py and kit/tools/plan.py,
judge.py, trace.py, library.py, ...) and each test puts its lane's folder on sys.path: in one process the first
import wins and the next lane's tests error (8 did in a fresh install, 2026-10-13). Isolation costs ~1 s per file.

THE SCHEDULE (PARALLAX_FINAL_CLOSURE_SPEC Track A1, 2026-11-22): every file still runs, each in its own interpreter,
through _proc.run_tree (a timeout stops its whole process tree). What changed is the order and the slots:
  - a file is a GPU, a BLENDER or a PLAIN file (read from its source): at most PARALLAX_PY_GPU_JOBS (1) GPU files and
    PARALLAX_PY_BLENDER_JOBS (5) Blender files at once, PARALLAX_PY_TEST_JOBS / KIT_PY_TEST_JOBS workers in all
    (default cores - 2, at most 14; 1 = one at a time, in name order);
  - longest first: each file's last time is kept in .verify/py_test_timings.json and the slowest start at t = 0
    (an unknown file counts 10 s); the report stays in name order;
  - every child gets its own TEMP / TMP / TMPDIR (two Blenders never share %TEMP%);
  - a file's time limit: its own KIT_PY_FILE_TIMEOUT if it declares one (_proc.file_timeout), else - once it has a
    history - three times its SLOWEST of its last 5 times (at least 120 s, never past KIT_PY_TEST_TIMEOUT, default
    1200; _proc.limit_from), else the default: a wedged quick file stops in minutes, a known slow one keeps its room,
    and one lucky fast run no longer sets a limit its normal runs blow (a time-out goes in the history: 2026-11-23);
  - a file that fails beside the others runs again after the pool, in a SECOND pass a third of the pool wide (a pass
    there is a pass); one that fails again is run ALONE, and only that run counts (a crash with no test summary gets
    one more try there); inside the pool it is not retried at once (2026-11-23: one-by-one lone runs of ~30 files
    that failed beside four open Studio windows took 35 min).
   python kit/test/python/run.py [-k <substring>] [--changed]
     -k        only the files whose name contains it
     --changed only the test files changed in the working tree or naming a changed kit module (a quick local loop:
               verify and prove never pass it - they run every file)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

try:
    import numpy  # noqa: F401
except ImportError:
    print("python tests: SKIPPED — numpy is not installed in this python (pip install numpy, or set PYTHON)")
    sys.exit(0)

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import _proc  # noqa: E402  (the process-tree runner)

# each file from the PROJECT ROOT (kit modules default their paths to the root: kit/anim/clip.py's rigs, the
# asset folders), with the tests folder on the import path so `-m unittest test_x` still finds it
root = os.path.abspath(os.path.join(here, "..", "..", ".."))

only = None
if "-k" in sys.argv:
    only = sys.argv[sys.argv.index("-k") + 1]
files = sorted(f for f in os.listdir(here) if f.startswith("test_") and f.endswith(".py") and (not only or only in f))


def changed_only(names):
    """--changed: the test files changed in the working tree, and those whose source names a changed kit module"""
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    except OSError:
        return names
    paths = [ln[3:].strip().strip('"').replace("\\", "/") for ln in out.splitlines() if len(ln) > 3]
    stems = {os.path.splitext(os.path.basename(p))[0] for p in paths if p.startswith("kit/") and p.endswith(".py")}
    keep = []
    for f in names:
        if f"kit/test/python/{f}" in paths:
            keep.append(f)
            continue
        text = open(os.path.join(here, f), encoding="utf-8", errors="replace").read()
        if any(re.search(r"\b" + re.escape(s) + r"\b", text) for s in stems if not s.startswith("test_")):
            keep.append(f)
    return keep


if "--changed" in sys.argv:
    files = changed_only(files)

RAN = re.compile(r"^Ran (\d+) tests?", re.M)
BAD = re.compile(r"^FAILED \((.*)\)", re.M)
PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|error)")
FUNCTION_TEST = re.compile(r"^def test_", re.M)
# what a file drives, read from its source: the GPU (generators, COLMAP's dense stereo, the vision server) or Blender
GPU_FILE = re.compile(r"torch|cuda|trellis|flux|colmap|photoscan|vision[/\\]serve", re.I)
BLENDER_FILE = re.compile(r"blender|\bbpy\b|\brbx\b|cad_check|run_blender", re.I)
run = failed = errors = 0
broken = []
try:
    import pytest  # noqa: F401

    HAVE_PYTEST = True
except ImportError:
    HAVE_PYTEST = False


def source(path):
    return open(path, encoding="utf-8", errors="replace").read()


def is_function_style(path):
    """pytest-style files (top-level `def test_...`, no unittest.TestCase): unittest collects NOTHING from them and
    reports `Ran 0 tests` — 84 anim tests were silently green that way (2026-10-16). They run through pytest."""
    text = source(path)
    return bool(FUNCTION_TEST.search(text)) and "unittest" not in text


DOCS = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|#[^\n]*')


def kind_of(path):
    """gpu / blender / plain, read from the file's CODE (its docstrings and comments left out: a test that only
    tells the story of the photoscan is not a GPU job)"""
    text = DOCS.sub("", source(path))
    if GPU_FILE.search(text):
        return "gpu"
    if BLENDER_FILE.search(text):
        return "blender"
    return "plain"


env = dict(os.environ)
env["PYTHONPATH"] = here + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
# (tells test_anim_pytest_suite that every pytest-style file is run here, each on its own: it does not run them again)
env["KIT_PY_RUN_EACH"] = "1"
# a file that hangs (a server waited on, a Blender that never returns) is an ERROR after this many seconds, never
# a verify that sits for an hour (2026-10-16: a 50-minute timeout killed verify with no name to blame)
FILE_TIMEOUT = int(os.environ.get("KIT_PY_TEST_TIMEOUT", "1200"))
QUICK_FLOOR = 120  # the least a file with a history is given (three times its last time, at least this)
TIMINGS = os.path.join(root, ".verify", "py_test_timings.json")


def load_timings():
    try:
        with open(TIMINGS, encoding="utf-8") as fh:
            t = json.load(fh)
        return t if isinstance(t, dict) else {}
    except (OSError, ValueError):
        return {}


timings = load_timings()


def limit_for(f):
    """the seconds file f may run: its declared budget, else 3x its SLOWEST recent time (QUICK_FLOOR..FILE_TIMEOUT:
    _proc.limit_from), else the default"""
    path = os.path.join(here, f)
    declared = _proc.file_timeout(path, FILE_TIMEOUT)
    if declared != FILE_TIMEOUT:
        return declared
    limit = _proc.limit_from(_proc.history(timings.get(f)), QUICK_FLOOR, FILE_TIMEOUT)
    return FILE_TIMEOUT if limit is None else limit


SLOW = 60  # a file past this many seconds is named at the end (a gate that creeps is a gate that gets skipped)
slow = []
took_by_file = {}

SUMMARY = re.compile(r"^Ran \d+ tests?|\d+ (passed|failed|error)", re.M)
retried = []

lock = threading.Lock()
TEMP_ROOT = tempfile.mkdtemp(prefix="kit_pytest_")


def child_env(f):
    """the child's environment: the runner's, with a TEMP of its own (two Blenders never share %TEMP%)"""
    d = os.path.join(TEMP_ROOT, f[:-3])
    os.makedirs(d, exist_ok=True)
    e = dict(env)
    e["TEMP"] = e["TMP"] = e["TMPDIR"] = d
    return e


def run_file(f, argv, limit, attempts):
    """(completed process or None, output); None = timed out. With attempts=2 (the lone run), a run that dies with NO
    test summary at all (a Blender or GPU crash beside another lane's build, 2026-10-16: test_sculpt errored with
    empty output, then passed) is run ONCE more, and so is a timeout; a real failure fails twice."""
    started = time.time()
    p, out = None, ""
    for attempt in range(1, attempts + 1):
        try:
            # (a timeout stops the file's whole process tree: a tool it drove - COLMAP, Blender - left running
            #  beside the retry wrote into the same build folder; 2026-11-20, test_photoscan_build)
            p = _proc.run_tree(argv, limit, cwd=root, env=child_env(f))
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            p = None
            if attempt == attempts:
                break
            with lock:
                retried.append(f)
            continue
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0 or SUMMARY.search(out) or attempt == attempts:
            break
        with lock:
            retried.append(f)
    took = time.time() - started
    with lock:
        took_by_file[f] = took
        if took > SLOW:
            slow.append(f"{f} {took:.0f} s")
    return p, out


def test_file(f, attempts=1):
    """one test file in its own interpreter -> (tests run, failed, errors, the report to print or None)"""
    path = os.path.join(here, f)
    limit = limit_for(f)
    if is_function_style(path):
        if not HAVE_PYTEST:
            return 0, 0, 1, f"--- {f}: pytest-style tests and no pytest in this python (pip install pytest) — NOT run"
        p, out = run_file(f, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", path], limit, attempts)
        if p is None:
            return 0, 0, 1, f"--- {f} (pytest): TIMED OUT after {limit} s (KIT_PY_TEST_TIMEOUT / its KIT_PY_FILE_TIMEOUT / 3x its last time)"
        counts = {k: int(v) for v, k in PYTEST_COUNT.findall(out)}
        n = counts.get("passed", 0) + counts.get("failed", 0)
        if p.returncode == 0:
            return n, 0, 0, None
        fails, errs = counts.get("failed", 0), counts.get("error", 0)
        if fails == 0 and errs == 0:
            errs = 1  # a collection error, or nothing collected (exit 5)
        tail = "\n".join(out.strip().splitlines()[-25:])
        return n, fails, errs, f"--- {f} (pytest): {fails} failed, {errs} errors\n{tail}"
    p, out = run_file(f, [sys.executable, "-m", "unittest", "-q", f[:-3]], limit, attempts)
    if p is None:
        return 0, 0, 1, f"--- {f}: TIMED OUT after {limit} s (KIT_PY_TEST_TIMEOUT / its KIT_PY_FILE_TIMEOUT / 3x its last time)"
    m = RAN.search(out)
    n = int(m.group(1)) if m else 0
    if p.returncode == 0:
        return n, 0, 0, None
    detail = BAD.search(out)
    fails = errs = 0
    if detail:
        for part in detail.group(1).split(","):
            k, _, v = part.strip().partition("=")
            if k == "failures":
                fails = int(v)
            elif k == "errors":
                errs = int(v)
    if fails == 0 and errs == 0:
        errs = 1  # a crash before the summary (an import error, a syntax error)
    # the tail of the output names the failing test and its assertion / traceback
    tail = "\n".join(out.strip().splitlines()[-25:])
    return n, fails, errs, f"--- {f}: {fails} failed, {errs} errors\n{tail}"


def env_int(*names, default):
    for n in names:
        v = os.environ.get(n)
        if v and v.strip().isdigit() and int(v) > 0:
            return int(v)
    return default


JOBS = env_int("PARALLAX_PY_TEST_JOBS", "KIT_PY_TEST_JOBS", default=min(14, max(1, (os.cpu_count() or 4) - 2)))
SLOTS = {"gpu": env_int("PARALLAX_PY_GPU_JOBS", default=1), "blender": env_int("PARALLAX_PY_BLENDER_JOBS", default=5)}
kinds = {f: kind_of(os.path.join(here, f)) for f in files}


class Queue:
    """longest-first; a worker takes the first file whose kind has a free slot (GPU / Blender), else waits"""

    def __init__(self, names):
        self.todo = sorted(names, key=lambda f: (-float((timings.get(f) or {}).get("s") or 10.0), f))
        self.free = dict(SLOTS)
        self.cv = threading.Condition()

    def take(self):
        with self.cv:
            while self.todo:
                for i, f in enumerate(self.todo):
                    k = kinds[f]
                    if k in self.free and self.free[k] <= 0:
                        continue
                    self.todo.pop(i)
                    if k in self.free:
                        self.free[k] -= 1
                    return f
                self.cv.wait()
            return None

    def done(self, f):
        with self.cv:
            if kinds[f] in self.free:
                self.free[kinds[f]] += 1
            self.cv.notify_all()


results = {}
collided = []
started_at = time.time()


def run_pool(names, jobs):
    """names through `jobs` workers (longest first, GPU / Blender slots kept) -> {file: result}"""
    out = {}
    q = Queue(names)

    def worker():
        while True:
            f = q.take()
            if f is None:
                return
            try:
                r = test_file(f)
            except Exception as e:  # (the runner must name the file, never die silently)
                r = (0, 0, 1, f"--- {f}: the runner failed on it: {e!r}")
            with lock:
                out[f] = r
            q.done(f)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, min(jobs, len(names))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def failed_beside(r):
    return r[3] is not None and "NOT run" not in r[3]


# the second pass: files that failed beside the others, a third of the pool at a time (2026-11-23, the owner: "speed
# it up with more cores" - ~30 files failed beside four open Studio windows and their one-by-one lone runs took
# 35 min). A pass there is a pass; a file that fails AGAIN runs alone, and only that lone run counts.
RETRY_JOBS = max(1, JOBS // 3)
try:
    if JOBS > 1 and len(files) > 1:
        results.update(run_pool(files, JOBS))
        again = [f for f in files if failed_beside(results[f])]
        second = run_pool(again, RETRY_JOBS) if len(again) > 1 and RETRY_JOBS > 1 else {}
        # the lone runs: a file that failed beside the others (twice, when there was a second pass), again on its
        # own (the retry), and only that run counts
        for f in again:
            if f in second and not failed_beside(second[f]):
                collided.append(f)
                results[f] = second[f]
                continue
            alone = test_file(f, attempts=2)
            if alone[3] is None:
                collided.append(f)
            results[f] = alone
    else:
        for f in files:
            results[f] = test_file(f, attempts=2)
finally:
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)
wall = time.time() - started_at

# the times, for the next run's order and limits: each file's last time and its recent history (_proc.remember: a
# timed-out file's limit goes in its history, so its next limit grows - still capped at FILE_TIMEOUT)
keep = load_timings()
for f, s in took_by_file.items():
    r = results.get(f)
    if r is not None:
        keep[f] = _proc.remember(keep.get(f), s, "TIMED OUT" in (r[3] or ""), limit_for(f), kinds.get(f))
try:
    os.makedirs(os.path.dirname(TIMINGS), exist_ok=True)
    with open(TIMINGS, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(keep.items())), fh, indent=1)
except OSError:
    pass

for f in files:  # (in name order, whatever order they finished in)
    n, fails, errs, report = results[f]
    run += n
    failed += fails
    errors += errs
    if report is not None:
        broken.append(f)
        print(report)

count = {k: sum(1 for f in files if kinds[f] == k) for k in ("plain", "blender", "gpu")}
print(
    f"python tests: {run} run, {failed} failed, {errors} errors ({len(files)} files, each in its own interpreter,"
    f" {JOBS} at a time: {count['plain']} plain, {count['blender']} Blender (<= {SLOTS['blender']}),"
    f" {count['gpu']} GPU (<= {SLOTS['gpu']}); {wall:.0f} s)"
)
if slow:
    print("slow files (> %d s): " % SLOW + ", ".join(sorted(slow)))
if retried:
    print("retried once after a crash or a timeout with no test summary: " + ", ".join(sorted(retried)))
if collided:
    print("failed beside the others, passed when run again (a collision, not a failure): " + ", ".join(collided))
if broken:
    print("broken files: " + ", ".join(broken))
sys.exit(0 if not broken else 1)
