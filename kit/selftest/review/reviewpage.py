"""reviewpage.py — a running `kit review` on the kit's own fixture piece, and the calls a browser makes to it: shared
by the selftest cases (run.py) and kit/test/python/test_review_page.py.

The piece is "sheetgun" of kit/selftest/sheet, copied to build/selftest/review_page_<this run>/ (git-ignored) with
its model sheet drawn there and a locks file of its OWN - a click's record lands in the copy, never in the project's
board/locks.json. The folder is this run's alone (two sessions running the selftest or the tests at once shared one
folder and deleted each other's files, 2026-11-12); whoever made it removes it (done()).

The EFFECT (the VFX side of the page: a beat chart and a style sheet) is the made project of kit/selftest/vfx/
stylesheet/madeproject.py under names of this run's own, in build/selftest/review_vfx_<this run>/ with a locks file
of its own. The page reads an effect's recording, chart picture and style sheet in the project's build folder, so
those few files stand there (build/vfx/..., git-ignored) under the run's names and are removed by vfx_done().
make_animatic() adds the set's timing animatic (its recording made from its own plan: no browser).
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vfx", "stylesheet"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vfx", "animatic"))
import madeanimatic  # noqa: E402
import madeproject  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJ = os.path.join("build", "selftest", f"review_page_{os.getpid()}")
MODELS = PROJ.replace(os.sep, "/") + "/assets/models"
LOCKS = PROJ.replace(os.sep, "/") + "/locks.json"
EMPTY = {"approvals": {}, "waivers": {}, "stages": {}}

# the effect (names of this run's own: its recording and its sheet stand in the project's build folder)
VFX = os.path.join("build", "selftest", f"review_vfx_{os.getpid()}")
FX, FXSET = f"rvfx{os.getpid()}", f"rvset{os.getpid()}"
EFFECTS = VFX.replace(os.sep, "/") + "/assets/effects"
MEASURED = EFFECTS + "/refs_measured"
VFXLOCKS = VFX.replace(os.sep, "/") + "/locks.json"
CHART = MEASURED + f"/{FXSET}.chart.json"
DRAWN = os.path.join("build", "vfx", "charts", f"{FXSET}.drawn.json")       # what the chart's picture shows
BOOTH = os.path.join("build", "vfx", "booth")


def lune():
    found = shutil.which("lune")
    if found:
        return found
    for ext in ("", ".exe"):
        p = os.path.join(os.path.expanduser("~"), ".rokit", "bin", "lune" + ext)
        if os.path.isfile(p):
            return p
    return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fixture():
    """a fresh copy of the fixture project with its sheet drawn and an empty locks file -> what the sheet tool said
    (run from the project root)"""
    shutil.rmtree(PROJ, ignore_errors=True)
    shutil.copytree(os.path.join("kit", "selftest", "sheet"), PROJ)
    drawn = subprocess.run([sys.executable, os.path.join("kit", "tools", "sheet.py"), "sheetgun", "--root", PROJ],
                           capture_output=True, text=True)
    forget(LOCKS)
    return drawn.stdout[-400:] + drawn.stderr[-400:]


def forget(locks):
    """the fixture's own record back to empty (the page reads it again at every look)"""
    with open(locks, "w", encoding="utf-8") as f:
        json.dump(EMPTY, f)


def done():
    """remove this run's copy of the fixture project"""
    shutil.rmtree(PROJ, ignore_errors=True)


def tool(script, *args):
    """one of the kit's VFX tools, run from the project root -> its last line as JSON"""
    r = subprocess.run([sys.executable, os.path.join("kit", "vfx", script), *args], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        return {"status": "fail", "summary": (r.stdout[-300:] + r.stderr[-300:]).strip()}


def record(brighter=False):
    """our recording of the effect (brighter: the same effect recorded again with another look - a texture changed,
    the preset's own file did not)"""
    frames = madeproject.clips.our_frames()
    if brighter:
        frames = frames.copy()
        frames[frames[..., 0] > 200] = (255, 235, 90)
    return madeproject.clips.write(os.path.join(BOOTH, f"{FX}_play_hero.mp4"), frames, 30)


def draw_chart():
    """kit vfx chart, in the fixture's own measured folder -> what it said"""
    return tool("chart.py", FXSET, "--measured", MEASURED)


def draw_sheet():
    """kit vfx stylesheet, of the fixture's effect -> what it said"""
    return tool("stylesheet.py", FX, "--effects", EFFECTS, "--tile", "640")


def vfx_fixture():
    """the made effect with its chart and its style sheet DRAWN, and an empty locks file of its own -> what the two
    drawings said (run from the project root)"""
    vfx_done()
    os.makedirs(VFX)
    madeproject.project(VFX, madeproject.clips.our_frames(), FX, FXSET, BOOTH)
    forget(VFXLOCKS)
    return draw_chart(), draw_sheet()


def make_animatic():
    """the set's timing animatic (kit vfx animatic), with no browser: its recording is made from its own plan as it
    is NOW, with the mark of what it is a recording OF (kit/selftest/vfx/animatic/madeanimatic.py) -> what the tool
    said"""
    madeanimatic.record_animatic(FXSET, EFFECTS, BOOTH)
    return tool("animatic.py", FXSET, "--no-record", "--effects", EFFECTS)


def vfx_done():
    """remove this run's effect: its made project and the few files of it in the project's build folder"""
    shutil.rmtree(VFX, ignore_errors=True)
    shutil.rmtree(os.path.join("build", "vfx", "dailies", f"{FXSET}_animatic"), ignore_errors=True)
    for name in (f"{FXSET}.json", f"{FXSET}.plan.json", f"{FXSET}.recorded.json", f"{FXSET}_side.mp4"):
        if os.path.isfile(os.path.join("build", "vfx", "animatic", name)):
            os.remove(os.path.join("build", "vfx", "animatic", name))
    if os.path.isfile(os.path.join(BOOTH, f"{FXSET}_animatic_play_hero.mp4")):
        os.remove(os.path.join(BOOTH, f"{FXSET}_animatic_play_hero.mp4"))
    for folder, names in ((BOOTH, (f"{FX}_play_hero.mp4", f"{FX}_play_hero.metrics.json")),
                          (os.path.join("build", "vfx", "charts"), (f"{FXSET}.png", f"{FXSET}.drawn.json")),
                          (os.path.join("build", "vfx", "stylesheet"), (f"{FX}.png", f"{FX}.json"))):
        for name in names:
            if os.path.isfile(os.path.join(folder, name)):
                os.remove(os.path.join(folder, name))
    shutil.rmtree(os.path.join("build", "vfx", "stylesheet", FX), ignore_errors=True)


class Page:
    """one running `kit review` (started from the project root) and the calls a browser would make to it. Every call
    but the page itself carries the page's token, as the page's own script does; `token=False` leaves it out."""

    def __init__(self, args):
        self.port = free_port()
        env = dict(os.environ, KIT_GAME="none", KIT_NO_BOARD="1")
        self.proc = subprocess.Popen([lune(), "run", "kit", "review", *args, "--port", str(self.port), "--no-open", "--game", "none"],
                                     cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.base = f"http://127.0.0.1:{self.port}"
        self.token, self.page = "", b""
        deadline = time.time() + 60
        while time.time() < deadline and self.proc.poll() is None:
            try:
                status, page = self.call("/", token=False)[:2]
            except OSError:
                time.sleep(0.2)
                continue
            found = re.search(rb'const TOKEN = "([0-9a-f]+)"', page)
            self.token = found.group(1).decode() if status == 200 and found else ""
            self.page = page
            break

    def call(self, path, method="GET", body=None, headers=None, token=True):
        headers = dict(headers or {})
        if token:
            headers.setdefault("X-Review-Token", self.token if token is True else token)
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}

    def review(self):
        return json.loads(self.call("/api/review")[1])

    def stage(self, key):
        return next(s for s in self.review()["stages"] if s["key"] == key)

    def file(self, path, key=True, headers=None):
        """a picture as the page's <img> asks for it (key=False: without the page's token; headers: e.g. the Range a
        <video> asks a part of its file with)"""
        k = f"&k={self.token}" if key else ""
        return self.call("/file?p=" + urllib.parse.quote(path) + k, headers=headers, token=False)

    def act(self, body, token=True, origin=None):
        """a click. The body's "seen" is what the page showed for that stage (filled in when the body has none)"""
        body = dict(body)
        if "seen" not in body:
            shown = [s for s in self.review()["stages"] if s["key"] == body.get("stage")]
            body["seen"] = shown[0].get("seen") if shown else None
        headers = {"Content-Type": "application/json", "Origin": origin or self.base}
        status, raw, _ = self.call("/api/act", "POST", body, headers, token=token)
        return status, json.loads(raw)

    def stop(self):
        self.proc.kill()
        self.proc.wait(timeout=20)


def sheetgun(*more):
    """the page for the fixture piece (more: extra flags, e.g. "--dry")"""
    return Page(["sheetgun", "--lane", "3d", "--models", MODELS, "--locks", LOCKS, *more])


def effect(*more):
    """the page for the fixture's effect"""
    return Page([FX, "--lane", "vfx", "--effects", EFFECTS, "--locks", VFXLOCKS, *more])


def kit(*args):
    """one kit command typed in a terminal, from the project root -> what it printed"""
    env = dict(os.environ, KIT_GAME="none", KIT_NO_BOARD="1")
    r = subprocess.run([lune(), "run", "kit", *args, "--game", "none"], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=300)
    return r.stdout + r.stderr
