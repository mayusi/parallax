"""autorec.py — record effects with NO hands: starts the kit's record server (`kit vfx play <name> --record`), opens the
player page in a HEADLESS local browser (Edge / Chrome, WebGL on the GPU), waits until the page has recorded every view
and the server has saved the videos (and the library copy), then closes the browser. Batch many effects in one call.

    python kit/vfx/autorec.py <effect> [<effect> ...] [--views hero,cine,player] [--fps 30] [--port 47813] [--timeout 900]
                              [--game <Name>]   (a game's preset: games/<Name>/assets/effects; default the project root)
                              [--compare <refs set>] [--times 0.9,1.2]   (then score each recording: kit vfx refs compare)

Prints one JSON line {status, summary, next_action, results:[{effect, ok, seconds, dailies?, compare?}]}.
Every recorded play makes its DAILIES (kit/vfx/dailies.py: the recording beside its scene frame by frame, every frame
large); what they said is passed through, so this summary too ends with `LOOK: <folder>` for each effect recorded.
Why: every recording used to need a person (or the agent) to navigate a browser to the player URL; with this, a
build -> record -> compare -> adjust loop runs unattended (see refs compare and the reference loop in the skill).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def browser():
    for b in BROWSERS:
        if os.path.isfile(b):
            return b
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def kill_browser(br, prof):
    """the launcher exits at once and hands off to child processes, so killing its pid is not enough (474 headless Edges
    once piled up and starved the GPU): tree-kill it AND every process whose command line carries this run's profile"""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(br.pid)], capture_output=True)
        else:
            br.kill()
    except Exception:  # noqa: BLE001
        pass
    tag = os.path.basename(prof)
    if os.name == "nt":
        ps = (f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{tag}*' -and $_.ProcessId -ne $PID }} | "
              "ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null }")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", tag], capture_output=True)


def lune():
    return shutil.which("lune") or "lune"


def dailies_of(text):
    """what the play said about its dailies: the part of its `summary:` line after "recorded. " when that names a
    folder to LOOK at ('' when the play said none - an older kit, or the play failed)"""
    for ln in reversed(text.splitlines()):
        if ln.startswith("summary: ") and " recorded. " in ln and "LOOK: " in ln:
            return ln.split(" recorded. ", 1)[1].strip()
    return ""


def record(effect, views, fps, port, timeout, game_none=True, game=None, extra=None, name=None):
    """extra: more flags for the play (kit vfx animatic: --animatic); name: the run's own name when the play gives it
    one of its own (the bundle the page asks for: <set>_animatic)"""
    t0 = time.time()
    log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False, encoding="utf-8")
    cmd = [lune(), "run", "kit", "vfx", "play", effect, "--record", "--views", views, "--fps", str(fps), "--port", str(port)]
    cmd += list(extra or [])
    if game:  # (2026-11-10: a game's presets could not be recorded hands-free - the server always ran in the root)
        cmd += ["--game", game]
    elif game_none:
        cmd += ["--game", "none"]
    srv = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    # wait until the server listens
    url = f"http://127.0.0.1:{port}/lib/index.html?name={name or effect}&view={views.split(',')[0]}&record=1&views={views}&fps={fps}"
    deadline = time.time() + 120
    while time.time() < deadline:
        log.flush()
        if "serving" in open(log.name, encoding="utf-8", errors="replace").read() or srv.poll() is not None:
            break
        time.sleep(0.5)
    if srv.poll() is not None:
        return {"effect": effect, "ok": False, "why": "the record server stopped: " + open(log.name, encoding="utf-8", errors="replace").read()[-300:]}
    prof = tempfile.mkdtemp(prefix="autorec_")
    b = browser()
    if not b:
        srv.kill()
        return {"effect": effect, "ok": False, "why": "no Edge / Chrome found"}
    br = subprocess.Popen([b, "--headless=new", "--ignore-gpu-blocklist", "--enable-webgl", "--use-angle=d3d11", "--enable-unsafe-swiftshader",
                           "--window-size=1280,720", "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--no-first-run",
                           "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
                           f"--user-data-dir={prof}", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        srv.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":  # the server and anything it started
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(srv.pid)], capture_output=True)
        else:
            srv.kill()
        try:
            srv.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
    finally:
        kill_browser(br, prof)
        time.sleep(1.0)
        shutil.rmtree(prof, ignore_errors=True)
    log.close()
    text = open(log.name, encoding="utf-8", errors="replace").read()
    try:
        os.remove(log.name)
    except OSError:
        pass
    ok = "recorded" in text and srv.returncode == 0
    return {"effect": effect, "ok": ok, "seconds": round(time.time() - t0, 1), "why": "" if ok else text[-300:],
            "dailies": dailies_of(text) if ok else ""}


def blank_frames(data, w, h, swing=12, pixels=4):
    """True when no pixel changes: under `pixels` of the w x h grey frames ever swing by `swing` levels. A lost WebGL
    context renders only the static booth (every pixel still). The old test - the range of the whole frame's MEAN under
    3 - called a small unlit effect on a bright sky blank (senbazuru 2026-10-25: paper cranes on overcast, means
    111.2-114.0, hundreds of pixels moving)"""
    n = len(data) // (w * h)
    if n < 2:
        return True
    lo, hi = list(data[:w * h]), list(data[:w * h])
    for i in range(1, n):
        f = data[i * w * h:(i + 1) * w * h]
        for k in range(w * h):
            v = f[k]
            if v < lo[k]:
                lo[k] = v
            elif v > hi[k]:
                hi[k] = v
    return sum(1 for k in range(w * h) if hi[k] - lo[k] >= swing) < pixels


def is_blank(effect, view, game=None):
    """a recording whose frames never change (a lost WebGL context under GPU pressure renders only the empty booth:
    seen 2026-10-14 while a big download ran)"""
    vid = os.path.join("build", "vfx", "booth", f"{effect}_play_{view}.mp4")  # (a game's recordings land here too)
    if not os.path.isfile(vid):
        return True
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vf", "fps=15,scale=64:36,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    if not r.stdout:
        return True
    return blank_frames(r.stdout, 64, 36)


def main(argv):
    effects, opts, i = [], {"--views": "hero,cine,player", "--fps": "30", "--port": "47813", "--timeout": "900"}, 0
    while i < len(argv):
        if argv[i].startswith("--"):
            if i + 1 >= len(argv):
                print(json.dumps({"schema": 1, "status": "fail", "summary": f"autorec: {argv[i]} needs a value", "next_action": "see the usage line"}))
                return 2
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            effects.append(argv[i])
            i += 1
    if not effects:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "autorec: name at least one effect", "next_action": "python kit/vfx/autorec.py <effect>..."}))
        return 2
    results = []
    for e in effects:
        r = record(e, opts["--views"], int(opts["--fps"]), int(opts["--port"]), int(opts["--timeout"]), game=opts.get("--game"))
        first = opts["--views"].split(",")[0]
        if r["ok"] and is_blank(e, first, opts.get("--game")):  # rendered nothing: record once more, then fail loudly
            r = record(e, opts["--views"], int(opts["--fps"]), int(opts["--port"]), int(opts["--timeout"]), game=opts.get("--game"))
            if r["ok"] and is_blank(e, first, opts.get("--game")):
                r = {"effect": e, "ok": False, "why": "the recording is BLANK twice (no frame changes): a lost WebGL context? close GPU-heavy work and retry"}
        if r["ok"] and "--compare" in opts:
            here = os.path.dirname(os.path.abspath(__file__))
            cmd = [sys.executable, "-I", os.path.join(here, "refkit.py"), "compare", opts["--compare"], "--effect", e, "--views", opts["--views"]]
            if "--times" in opts:  # the moments to judge (a short effect: when the effect is ON screen)
                cmd += ["--times", opts["--times"]]
            c = subprocess.run(cmd,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            line = next((ln for ln in c.stdout.splitlines() if ln.startswith("{")), "{}")
            try:
                d = json.loads(line)
                r["compare"] = {"score": d.get("score"), "shape": d.get("shape"), "ref_shape": d.get("ref_shape")}
            except json.JSONDecodeError:
                r["compare"] = None
        results.append(r)
    ok = sum(r["ok"] for r in results)
    looks = [r["dailies"] for r in results if r.get("dailies")]      # each ends with its own LOOK: <folder>
    print(json.dumps({"schema": 1, "status": "pass" if ok == len(results) else "fail",
                      "summary": f"autorec: {ok}/{len(results)} recorded (" + ", ".join(f"{r['effect']} {r.get('seconds', '?')}s" + (f" match {r['compare']['score']}" if r.get('compare') else "") for r in results) + ")"
                      + ("." if looks else "") + "".join(f" {d}" for d in looks),
                      "next_action": ("open each LOOK folder's beat<k>_01.png onward at full size (two consecutive frames a picture, the scene "
                                      "above ours), the key beat's at least" if looks else
                                      "LOOK at build/vfx/booth/<effect>_play_<view>.mp4") if ok else "read results[].why", "results": results}))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
