"""kit world shots — the world's web viewer, rendered headless, as a contact sheet of fixed views.

    python kit/world/shots.py <page.html> <out_dir> [--timeout 480]

Serves the page's folder on a free local port, opens <page>?shots=1 in headless Edge / Chrome (GPU via ANGLE), the
page flies a fixed tour (overview, from above, eye level at every Site of Grace / the spawn, close to every objective)
and POSTs each frame here. Writes <out_dir>/<view>.jpg + <out_dir>.png (the sheet). One JSON verdict line.
Fast (about a minute) and the same shaders the owner sees in the viewer — the quick look; `kit world look` (Blender)
remains the second opinion.
"""

import base64
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

EDGE = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def browser():
    for p in EDGE:
        if os.path.isfile(p):
            return p
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def kill_profile(fragment, older_than_s=None):
    """end every browser process whose profile folder contains `fragment`. msedge.exe hands the page to a child
    browser and exits, so killing the launched process leaves the real one RENDERING the 3D page forever — a few
    of those left behind took the GPU and made later tours 10x slower (measured 2026-10-14: 47 s vs 525 s)"""
    try:
        if os.name == "nt":
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' OR Name='chrome.exe'\" | "
                  f"Where-Object {{ $_.CommandLine -like '*{fragment}*' -and $_.CommandLine -notlike '*--type=*' }} | "
                  + (f"Where-Object {{ ((Get-Date) - $_.CreationDate).TotalSeconds -gt {int(older_than_s)} }} | "
                     if older_than_s else "") +
                  "ForEach-Object { $_.ProcessId }")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 timeout=30).stdout
            for pid in out.split():
                if pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, timeout=15)
        else:
            subprocess.run(["pkill", "-f", fragment], capture_output=True, timeout=15)
    except Exception:  # noqa: BLE001 — cleanup must never fail the tour
        pass


def slug(view):
    return re.sub(r"[^A-Za-z0-9]+", "_", view).strip("_").lower() or "view"


def serve(root, out_dir, state):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode("utf-8", "replace")
            if self.path.startswith("/shot"):
                m = re.search(r"view=([^&]+)", self.path)
                from urllib.parse import unquote
                view = unquote(m.group(1)) if m else f"view{len(state['views'])}"
                data = body.split(",", 1)[1] if "," in body else body
                base, k = slug(view), 2
                path = os.path.join(out_dir, base + ".jpg")
                while any(p == path for _, p in state["views"]):
                    path = os.path.join(out_dir, f"{base}_{k}.jpg")
                    k += 1
                with open(path, "wb") as f:
                    f.write(base64.b64decode(data))
                state["views"].append((view, path))
            elif self.path.startswith("/done"):
                state["done"].set()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", state["port"]), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def sheet(views, out_png, title):
    from PIL import Image, ImageDraw, ImageFont
    cols, tw, th = 3, 640, 360
    rows = (len(views) + cols - 1) // cols
    pad, head, lab = 12, 46, 26
    W = cols * tw + (cols + 1) * pad
    H = head + rows * (th + lab + pad) + pad
    img = Image.new("RGB", (W, H), (18, 15, 11))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 16)
        big = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 24)
    except OSError:
        font = big = ImageFont.load_default()
    d.text((pad, 12), title, fill=(236, 214, 160), font=big)
    for i, (view, path) in enumerate(views):
        r, c = divmod(i, cols)
        x, y = pad + c * (tw + pad), head + r * (th + lab + pad)
        try:
            im = Image.open(path).convert("RGB").resize((tw, th))
            img.paste(im, (x, y + lab))
        except OSError:
            pass
        d.text((x, y + 4), view, fill=(214, 190, 140), font=font)
    img.save(out_png)


def main(argv):
    if len(argv) < 3:
        print(json.dumps({"status": "fail", "summary": "usage: shots.py <page.html> <out_dir>", "next_action": "lune run kit world shots <Name>"}))
        return 2
    page, out_dir = os.path.abspath(argv[1]), os.path.abspath(argv[2])
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 480
    if not os.path.isfile(page):
        print(json.dumps({"status": "fail", "summary": f"no page {page}", "next_action": "lune run kit world web <Name> first"}))
        return 1
    b = browser()
    if not b:
        print(json.dumps({"status": "fail", "summary": "no Edge / Chrome found", "next_action": "install Microsoft Edge or Chrome"}))
        return 1
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    state = {"views": [], "done": threading.Event(), "port": free_port()}
    httpd = serve(os.path.dirname(page), out_dir, state)
    # (a tour that crashed before its cleanup: never share the GPU with it — only STALE ones: another session's tour
    # may be running right now)
    kill_profile("worldshots_", older_than_s=max(900, timeout + 120))
    prof = tempfile.mkdtemp(prefix="worldshots_")
    url = f"http://127.0.0.1:{state['port']}/{os.path.basename(page)}?shots=1"
    t0 = time.time()
    # a REAL window (headed), parked off screen: headless rendering differed from a normal browser's three ways
    # (stalls, no animation frames, and NaN/inf blooms on scanned meshes that a normal Chromium draws clean);
    # --headless stays available for machines without a desktop (KIT_SHOTS_HEADLESS=1)
    mode = (["--headless=new"] if os.environ.get("KIT_SHOTS_HEADLESS") else
            ["--window-position=-2600,-1600", f"--app={url}"])
    br = subprocess.Popen([b, *mode, "--ignore-gpu-blocklist", "--enable-webgl", "--use-angle=d3d11",
                           "--window-size=1280,720", "--hide-scrollbars", "--mute-audio",
                           "--no-first-run", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                           "--disable-backgrounding-occluded-windows",
                           # Windows 11 throttles a page nobody can see: efficiency mode (EcoQoS) and occlusion
                           # detection made tours stall at random (1 view in 480 s on an idle GPU, 2026-10-14)
                           "--disable-features=UseEcoQoSForBackgroundProcess,CalculateNativeWinOcclusion,"
                           "IntensiveWakeUpThrottling,msEfficiencyMode", "--disable-ipc-flooding-protection",
                           f"--user-data-dir={prof}"] + ([url] if os.environ.get("KIT_SHOTS_HEADLESS") else []),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # (not br.poll(): msedge.exe hands the page to another process and exits at once, so "the browser died"
    # cannot be told that way; a page that sends nothing before the timeout failed)
    done = state["done"].wait(timeout)
    br.kill()
    try:
        br.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass
    kill_profile(os.path.basename(prof))
    httpd.shutdown()
    shutil.rmtree(prof, ignore_errors=True)
    views = state["views"]
    if not views:
        print(json.dumps({"status": "fail", "summary": f"no frames came back in {round(time.time() - t0)} s",
                          "next_action": "open the page with ?shots=1 in a browser and read its console"}))
        return 1
    name = os.path.splitext(os.path.basename(page))[0]
    png = out_dir.rstrip("/\\") + ".png"
    sheet(views, png, f"{name} - {len(views)} views (kit world shots, the viewer's shaders)")
    ok = done
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"{len(views)} view(s) in {round(time.time() - t0)} s -> {png}" + ("" if ok else " (the tour did not finish)"),
                      "next_action": f"LOOK at {png}" if ok else "read the page console (open it with ?shots=1)",
                      "sheet": png}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
