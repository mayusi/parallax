"""booth.py — the LISTENING BOOTH: the owner's ears in the loop (the model cannot hear; the owner decides).

Usage: python kit/audio/booth.py <name ...> [--ref(s) <file|name>] [--blind] [--port 8791] [--stop] [--serve]
       (normally: lune run kit sfx listen <name ...>)
Starts (or reuses) a small server on 127.0.0.1 serving one page: every take of every named sound (+ the reference),
its sound sheet, play / loop buttons, hotkeys (1-9 play a take, space = stop, R = the reference), a 1-10 score,
a "pick" (the best take) and a few words. --blind hides the names and shuffles the order (an honest A/B).
Each verdict is appended to assets/sounds/<name>.verdict.json ({history:[{when, score, pick, words, blind, ears}]})
and folded into the owner's taste profile (kit/knowledge/sfx_taste.json: which measured traits the owner scores
up or down — the kit learns the owner's ear the way it learned UI taste). The server stops after 2 h idle, or
with --stop. Prints one JSON verdict line with the URL (the command returns at once; the server keeps running).
"""

import html
import http.server
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402

SOUNDS, RECIPES = os.path.join("build", "sounds"), os.path.join("assets", "sounds")
STATE = os.path.join("build", "sounds", "booth", "server.json")
TASTE = os.path.join("kit", "knowledge", "sfx_taste.json")
IDLE_S = 2 * 3600


def takes_of(name):
    main = os.path.join(SOUNDS, f"{name}.ogg")
    if not os.path.isfile(main):
        return []
    out, i = [main], 2
    while os.path.isfile(os.path.join(SOUNDS, f"{name}_{i}.ogg")):
        out.append(os.path.join(SOUNDS, f"{name}_{i}.ogg"))
        i += 1
    return out


# ------------------------------------------------------------------ verdicts + taste
def save_verdict(name, verdict):
    path = os.path.join(RECIPES, f"{name}.verdict.json")
    if not os.path.isdir(RECIPES):
        os.makedirs(RECIPES, exist_ok=True)
    data = {"name": name, "history": []}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    takes = takes_of(name)
    try:
        verdict["ears"] = E.measure(E.decode(takes[0])[0]) if takes else {}
    except Exception:  # noqa: BLE001 — a verdict is never lost to a measuring error
        verdict["ears"] = {}
    verdict["when"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["history"].append(verdict)
    data["latest"] = verdict
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1)
    update_taste()
    # the ONE verdict record: the knowledge vault files this score now (kit/scripts/vault_migrate.py, store "sfx");
    # a failure never loses the verdict, it is already in <name>.verdict.json
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
        import vault_migrate  # noqa: E402

        vault_migrate.sync_store("sfx")
    except Exception:  # noqa: BLE001
        pass
    return path


TRAITS = ["lufs", "crest_db", "transient_ms", "tail_ms", "brightness_hz", "sub_share", "high_share", "flux"]
WORDS = {
    "crest_db": ("punchier (more crest)", "flatter / more compressed"),
    "transient_ms": ("softer attacks", "sharper attacks"),
    "tail_ms": ("longer tails", "shorter, drier tails"),
    "brightness_hz": ("brighter sounds", "darker sounds"),
    "sub_share": ("more sub weight", "less sub"),
    "high_share": ("more air on top", "less air on top"),
    "flux": ("grainier textures", "smoother textures"),
    "lufs": ("louder sounds", "quieter sounds"),
}


def update_taste():
    """Correlate every scored verdict's measured traits with the owner's score: what the owner rewards."""
    rows = []
    for f in sorted(os.listdir(RECIPES)) if os.path.isdir(RECIPES) else []:
        if f.endswith(".verdict.json"):
            with open(os.path.join(RECIPES, f), encoding="utf-8") as fh:
                for v in json.load(fh).get("history", []):
                    if isinstance(v.get("score"), (int, float)) and v.get("ears"):
                        rows.append(v)
    taste = {"verdicts": len(rows), "updated": time.strftime("%Y-%m-%d"), "leans": [], "note": ""}
    if len(rows) < 6:
        taste["note"] = f"{len(rows)} scored verdict(s): needs 6+ before the owner's leanings mean anything"
    else:
        import numpy as np

        scores = np.array([float(v["score"]) for v in rows])
        for t in TRAITS:
            vals = np.array([float(v["ears"].get(t, 0)) for v in rows])
            if t == "brightness_hz":
                vals = np.log2(np.maximum(vals, 1))
            if np.std(vals) < 1e-9 or np.std(scores) < 1e-9:
                continue
            r = float(np.corrcoef(vals, scores)[0, 1])
            if abs(r) >= 0.3:
                up, down = WORDS[t]
                taste["leans"].append({"trait": t, "r": round(r, 2), "owner_prefers": up if r > 0 else down})
        taste["leans"].sort(key=lambda x: -abs(x["r"]))
        best = sorted(rows, key=lambda v: -v["score"])[: max(3, len(rows) // 4)]
        taste["targets"] = {t: round(float(np.median([v["ears"].get(t, 0) for v in best])), 3) for t in TRAITS}
    os.makedirs(os.path.dirname(TASTE), exist_ok=True)
    with open(TASTE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(taste, fh, indent=1)
    return taste


# ------------------------------------------------------------------ the page
PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Sound booth</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#14161b;--fg:#e8e6e1;--dim:#8a8f99;--acc:#ff9e3d;--ref:#5ec8ff;--card:#1d2027}
body{background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif;margin:0;padding:16px;max-width:1100px}
h1{font-size:20px;margin:0 0 4px} .hint{color:var(--dim);font-size:13px;margin-bottom:14px}
.sound{background:var(--card);border-radius:10px;padding:14px;margin:12px 0}
.takes{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
button{background:#2a2e37;color:var(--fg);border:1px solid #3a3f4a;border-radius:7px;padding:8px 12px;font:inherit;cursor:pointer}
button.on{background:var(--acc);color:#111} button.ref{border-color:var(--ref);color:var(--ref)}
.score{display:flex;gap:4px;flex-wrap:wrap;margin:8px 0} .score button{width:40px}
input[type=text]{width:100%;box-sizing:border-box;background:#111317;color:var(--fg);border:1px solid #3a3f4a;border-radius:7px;padding:8px}
img{max-width:100%;border-radius:6px;margin-top:8px} .saved{color:#9be564;font-size:13px;min-height:18px}
details summary{color:var(--dim);cursor:pointer;margin-top:6px}
</style></head><body>
<h1>Sound booth</h1>
<div class="hint">Keys: 1-9 play a take of the focused sound · R the reference · space stop · L loop on/off.
Score 1-10, pick the best take, a few words — Save writes the verdict the kit learns from.__BLIND__</div>
__REF__
__SOUNDS__
<script>
let audio=new Audio(), loop=false, focus=0;
function play(src,btn){audio.pause();audio=new Audio(src);audio.loop=loop;audio.play();
 document.querySelectorAll('button.on').forEach(b=>b.classList.remove('on')); if(btn) btn.classList.add('on');}
document.addEventListener('keydown',e=>{ if(e.target.tagName==='INPUT') return;
 const cards=[...document.querySelectorAll('.sound:not(.refcard)')]; const c=cards[focus]; if(!c) return;
 if(e.key>='1'&&e.key<='9'){const b=c.querySelectorAll('.take')[+e.key-1]; if(b) b.click();}
 else if(e.key===' '){audio.pause();e.preventDefault();}
 else if(e.key==='r'||e.key==='R'){const r=document.querySelector('.ref'); if(r) r.click();}
 else if(e.key==='l'||e.key==='L'){loop=!loop;audio.loop=loop;}
 else if(e.key==='ArrowDown'){focus=Math.min(cards.length-1,focus+1);cards[focus].scrollIntoView({behavior:'smooth'});}
 else if(e.key==='ArrowUp'){focus=Math.max(0,focus-1);cards[focus].scrollIntoView({behavior:'smooth'});}});
document.querySelectorAll('.sound:not(.refcard)').forEach((card,i)=>{card.addEventListener('click',()=>focus=i);
 card.querySelectorAll('.score button').forEach(b=>b.onclick=()=>{card.dataset.score=b.textContent;
  card.querySelectorAll('.score button').forEach(x=>x.classList.toggle('on',x===b));});
 card.querySelectorAll('.pick').forEach(b=>b.onclick=()=>{card.dataset.pick=b.dataset.take;
  card.querySelectorAll('.pick').forEach(x=>x.classList.toggle('on',x===b));});
 card.querySelector('.save').onclick=async()=>{const body={name:card.dataset.name,score:card.dataset.score?+card.dataset.score:null,
  pick:card.dataset.pick||null,words:card.querySelector('input').value,blind:__BLINDJS__};
  const r=await fetch('/verdict',{method:'POST',headers:{'Content-Type':'application/json','X-Booth-Token':'__TOKEN__'},body:JSON.stringify(body)});
  card.querySelector('.saved').textContent=r.ok?'saved — '+(await r.text()):'not saved: '+r.status;};});
</script></body></html>"""


def page(names, ref, blind):
    cards = []
    order = list(names)
    if blind:
        random.shuffle(order)
    for k, n in enumerate(order):
        label = f"Sound {chr(65 + k)}" if blind else html.escape(n)
        takes = takes_of(n)
        tbtn = "".join(f'<button class="take" onclick="play(\'/file?p={urllib.parse.quote(t)}\',this)">{i + 1}</button>' for i, t in enumerate(takes))
        pbtn = "".join(f'<button class="pick" data-take="{i + 1}">best: {i + 1}</button>' for i in range(len(takes)))
        sbtn = "".join(f"<button>{s}</button>" for s in range(1, 11))
        sheet = os.path.join(SOUNDS, "sheets", f"{n}.png")
        img = "" if blind or not os.path.isfile(sheet) else f'<details><summary>sound sheet</summary><img src="/file?p={urllib.parse.quote(sheet)}"></details>'
        cards.append(
            f'<div class="sound" data-name="{html.escape(n)}"><b>{label}</b> <span class="hint">{len(takes)} take(s)</span>'
            f'<div class="takes">{tbtn}</div><div class="takes">{pbtn}</div><div class="score">{sbtn}</div>'
            f'<input type="text" placeholder="a few words: what works, what is off"><div class="takes"><button class="save">Save verdict</button></div>'
            f'<div class="saved"></div>{img}</div>'
        )
    refhtml = ""
    if ref:
        refhtml = f'<div class="sound refcard"><b>Reference</b> <button class="ref" onclick="play(\'/file?p={urllib.parse.quote(ref)}\',this)">play reference (R)</button></div>'
    return (PAGE.replace("__SOUNDS__", "".join(cards)).replace("__REF__", refhtml)
            .replace("__BLIND__", " <b>Blind: names hidden, order shuffled.</b>" if blind else "")
            .replace("__BLINDJS__", "true" if blind else "false"))


# ------------------------------------------------------------------ the server
class Handler(http.server.BaseHTTPRequestHandler):
    page_html = ""
    last = time.time()
    token = ""
    port = 0

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _trusted_host(self):
        # DNS rebinding guard: only our own address answers
        return self.headers.get("Host", "") in (f"127.0.0.1:{Handler.port}", f"localhost:{Handler.port}")

    def _trusted_post(self):
        """A POST must carry the per-launch token in a custom header (a cross-site page cannot send one without a
        CORS preflight, which this server never approves), come to our own Host, and from our own Origin if any."""
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{Handler.port}", f"http://localhost:{Handler.port}"):
            return False
        import hmac

        return self._trusted_host() and hmac.compare_digest(self.headers.get("X-Booth-Token", ""), Handler.token)

    def do_OPTIONS(self):  # noqa: N802 — preflights are never approved
        return self._send(403, "no")

    def do_GET(self):  # noqa: N802
        Handler.last = time.time()
        if not self._trusted_host():
            return self._send(403, "no")
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, Handler.page_html.replace("__TOKEN__", Handler.token), "text/html; charset=utf-8")
        if u.path == "/reload":
            return self._send(200, "booth")
        if u.path == "/file":
            p = urllib.parse.parse_qs(u.query).get("p", [""])[0]
            full = os.path.abspath(p)
            root = os.path.abspath(".")
            # only files inside the project, and only sounds / pictures
            if not full.startswith(root + os.sep) or not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in (".ogg", ".wav", ".mp3", ".flac", ".png"):
                return self._send(404, "no")
            ctype = {"ogg": "audio/ogg", "wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "png": "image/png"}[full.rsplit(".", 1)[1].lower()]
            with open(full, "rb") as fh:
                return self._send(200, fh.read(), ctype)
        return self._send(404, "no")

    def do_POST(self):  # noqa: N802
        Handler.last = time.time()
        if not self._trusted_post():
            return self._send(403, "no")
        try:  # (a negative or junk length made rfile.read(-1) read without a limit)
            n = max(0, int(self.headers.get("Content-Length", 0)))
        except ValueError:
            return self._send(400, "bad length")
        if self.path == "/page":  # a new `kit sfx listen` replaces the page of a running booth
            if n > 2_000_000:
                return self._send(413, "too big")
            Handler.page_html = self.rfile.read(n).decode("utf-8")
            return self._send(200, "ok")
        if self.path != "/verdict":
            return self._send(404, "no")
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(415, "json only")
        try:
            if n > 65536:
                return self._send(413, "too big")
            v = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(v, dict):
                return self._send(400, "a verdict is a JSON object")
            name = str(v.get("name", ""))
            if not name or "/" in name or "\\" in name or ".." in name or not takes_of(name):
                return self._send(400, "unknown sound")
            score = v.get("score")
            verdict = {
                "score": int(score) if isinstance(score, (int, float)) and 1 <= score <= 10 else None,
                "pick": str(v.get("pick"))[:8] if v.get("pick") else None,
                "words": str(v.get("words", ""))[:500],
                "blind": bool(v.get("blind")),
            }
            path = save_verdict(name, verdict)
            return self._send(200, path.replace("\\", "/"))
        except (ValueError, TypeError) as exc:
            return self._send(400, f"bad verdict: {exc}")


def serve(port, page_file):
    with open(page_file, encoding="utf-8") as fh:
        Handler.page_html = fh.read()
    with open(STATE, encoding="utf-8") as fh:  # the launcher wrote the per-launch token before starting us
        Handler.token = json.load(fh)["token"]
    Handler.port = port
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def watchdog():
        while time.time() - Handler.last < IDLE_S:
            time.sleep(30)
        srv.shutdown()

    threading.Thread(target=watchdog, daemon=True).start()
    srv.serve_forever()


def running(port):
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/reload", timeout=1) as r:
            return r.status == 200 and r.read() == b"booth"  # (not some other program on the port)
    except OSError:
        return False


VALUED = {"--ref": "ref", "--refs": "ref", "--port": "port", "--page": "page"}   # (--refs: the plural people type)
SWITCHES = {"--blind": "blind", "--stop": "stop", "--serve": "serve"}


def parse(argv):
    """the booth's words -> ({names, ref, port, page, blind, stop, serve}, None), or (None, what was wrong). A flag the
    booth does not know is REFUSED: before 2026-11-19 `--refs x.wav` was taken as two sound names (the V3 list's SFX
    seam: "missing kit sfx listen --refs")."""
    out = {"names": [], "ref": None, "port": 8791, "page": None, "blind": False, "stop": False, "serve": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in VALUED:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                return None, f"{a} needs a value"
            key, val = VALUED[a], argv[i + 1]
            if key == "port":
                if not val.isdigit():
                    return None, f"--port {val}: a port number"
                val = int(val)
            out[key] = val
            i += 2
            continue
        if a in SWITCHES:
            out[SWITCHES[a]] = True
        elif a.startswith("--"):
            return None, f"{a}: not a booth option ({', '.join([*VALUED, *SWITCHES])})"
        else:
            out["names"].append(a)
        i += 1
    return out, None


def main(argv):
    got, wrong = parse(argv)
    if wrong:
        print(json.dumps({"status": "fail", "summary": wrong,
                          "next_action": "lune run kit sfx listen <name ...> [--ref <file|name>] [--blind] [--port 8791]"}))
        return 1
    names, ref, blind, port = got["names"], got["ref"], got["blind"], got["port"]
    stop, serve_mode, page_file = got["stop"], got["serve"], got["page"]
    if serve_mode:
        serve(port, page_file)
        return 0
    if stop:
        if os.path.isfile(STATE):
            with open(STATE, encoding="utf-8") as fh:
                pid = json.load(fh).get("pid")
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"] if os.name == "nt" else ["kill", str(pid)], capture_output=True)
            os.remove(STATE)
        print(json.dumps({"status": "pass", "summary": "booth stopped", "next_action": "none — proceed"}))
        return 0
    missing = [n for n in names if not takes_of(n)]
    if not names or missing:
        print(json.dumps({"status": "fail", "summary": f"not rendered: {', '.join(missing) or '(no names)'}",
                          "next_action": "render first: lune run kit sfx <name> (or kit sfx set <set>), then kit sfx listen <name ...>"}))
        return 1
    if ref and not os.path.isfile(ref):
        rt = takes_of(ref)
        ref = rt[0] if rt else None
    html_text = page(names, ref, blind)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    page_file = os.path.join(os.path.dirname(STATE), "page.html")
    with open(page_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html_text)
    url = f"http://127.0.0.1:{port}/"
    if running(port):
        import urllib.request

        with open(STATE, encoding="utf-8") as fh:
            token = json.load(fh).get("token", "")
        urllib.request.urlopen(urllib.request.Request(url + "page", data=html_text.encode("utf-8"), method="POST",
                                                      headers={"X-Booth-Token": token}), timeout=3).read()
    else:
        import secrets

        with open(STATE, "w", encoding="utf-8") as fh:  # the token first: the server reads it on start
            json.dump({"pid": 0, "port": port, "token": secrets.token_hex(16)}, fh)
        cmd = [sys.executable, os.path.abspath(__file__), "--serve", "--port", str(port), "--page", page_file]
        io = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":
            # Lune runs kit tools inside a Windows job that is killed when the command returns (and forbids
            # breakaway): the booth died the moment `kit sfx listen` printed its URL. WMI's Win32_Process.Create
            # starts it OUTSIDE any job, owned by nobody here; its pid comes back for --stop.
            line = subprocess.list2cmdline([sys.executable.replace("python.exe", "pythonw.exe") if os.path.isfile(sys.executable.replace("python.exe", "pythonw.exe")) else sys.executable] + cmd[1:])
            ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
                  f"@{{CommandLine='{line.replace(chr(39), chr(39) * 2)}'; CurrentDirectory='{os.getcwd().replace(chr(39), chr(39) * 2)}'}}; $r.ProcessId")
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, timeout=60)
            pid = int(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else 0
            proc = type("P", (), {"pid": pid})()
        else:
            proc = subprocess.Popen(cmd, cwd=os.getcwd(), start_new_session=True, **io)
        with open(STATE, encoding="utf-8") as fh:
            state = json.load(fh)
        state["pid"] = proc.pid
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        for _ in range(150):  # (python + numpy start in ~2-5 s on this machine)
            if running(port):
                break
            time.sleep(0.1)
        if not running(port):
            print(json.dumps({"status": "fail", "summary": f"booth did not start on port {port}", "next_action": f"port busy? retry with --port {port + 1}"}))
            return 1
    print(json.dumps({"status": "pass", "summary": f"booth at {url} — {len(names)} sound(s){' (blind)' if blind else ''}",
                      "next_action": f"open {url} — the owner scores each sound; verdicts land in assets/sounds/<name>.verdict.json (stop: kit sfx listen --stop)",
                      "url": url}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
