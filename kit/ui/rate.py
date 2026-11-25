"""rate.py — the owner's ONE-KEY rating of a screen (mission 03, 5.7): a page on this machine (127.0.0.1 only) shows the
screen as the ENGINE drew it (the booth's capture) beside the preview sheet, the reference still and the verifier's
pairs; one key (0-9, or the 10 button) plus optional words records the verdict through `kit verdict screen` — the
only quality signal — and the page closes the server.

    python kit/ui/rate.py <Screen> [--port 47813] [--ui build/ui] [--specs assets/ui] [--once]

Nothing leaves the machine; the server answers only 127.0.0.1 and stops after one rating.
"""
import argparse
import base64
import html
import json
import hmac
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PICTURES = (("the engine (Studio)", "{ui}/booth/{s}_engine.png"), ("the preview", "{ui}/{s}.png"),
            ("beside the real game (verifier)", "build/judge/ui/{s}/verify/pairs.png"),
            ("the reel in the engine", "{ui}/booth/{s}_reel_compare.png"))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}), flush=True)
    return 0 if status == "pass" else 1


def data_uri(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def page(screen, ui, token=""):
    figs = []
    for label, pat in PICTURES:
        p = pat.format(ui=ui, s=screen)
        if os.path.isfile(p):
            figs.append(f'<figure><figcaption>{html.escape(label)} — {html.escape(p)}</figcaption><img src="{data_uri(p)}"></figure>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Rate {html.escape(screen)}</title>
<style>body{{background:#111;color:#eee;font:15px system-ui;margin:16px}} img{{max-width:100%;border:1px solid #333}}
figure{{margin:0 0 18px}} figcaption{{color:#9ab;margin:4px 0}} .keys button{{font:20px system-ui;width:52px;height:52px;margin:2px}}
input{{width:60%;font:15px system-ui;padding:6px}}</style></head><body>
<h2>Rate {html.escape(screen)} — press 0-9 (or click 10); words optional</h2>
<form id="f" method="POST" action="/rate"><input type="hidden" name="token" value="{html.escape(token)}"><input name="words" placeholder="your words (optional)" autofocus>
<input type="hidden" name="score" id="score"><div class="keys">{''.join(f'<button type="button" onclick="go({n})">{n}</button>' for n in range(11))}</div></form>
{''.join(figs) or '<p>No pictures yet: run kit ui ' + html.escape(screen) + ' (and kit ui booth for the engine).</p>'}
<script>function go(n){{document.getElementById('score').value=n;document.getElementById('f').submit()}}
document.addEventListener('keydown',e=>{{if(document.activeElement.name==='words'&&e.key!=='Enter')return;
if(/^[0-9]$/.test(e.key)){{e.preventDefault();go(parseInt(e.key))}}}});</script></body></html>"""


def record(screen, score, words, cmd):
    words = words.strip() or "(rated by key, no words)"
    if words.startswith("-"):  # (never read as a flag by the verdict command)
        words = "(" + words.lstrip("-").strip() + ")"
    r = subprocess.run(cmd + ["verdict", "screen", screen, str(score), words], capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [ln for ln in r.stdout.splitlines() if ln.startswith("summary:")]
    return r.returncode == 0, (tail[-1] if tail else r.stdout[-300:])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--port", type=int, default=47813)
    ap.add_argument("--ui", default="build/ui")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--lune", default="lune")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(a.specs, f"{a.screen}.json")):
        return emit("fail", f"rate: no {a.specs}/{a.screen}.json", "name a screen in assets/ui")
    result = {}
    # a per-run secret: any web page the owner has open can POST to 127.0.0.1, so a rating needs the token printed here
    # (the URL) and a Host of exactly this server (DNS rebinding) — security review 2026-10-16
    token = secrets.token_urlsafe(24)
    host_ok = {f"127.0.0.1:{a.port}", f"localhost:{a.port}"}
    body = page(a.screen, a.ui, token).encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _local(self):
            return self.client_address[0] in ("127.0.0.1", "::1") and (self.headers.get("Host") or "") in host_ok

        def _origin_ok(self):
            o = self.headers.get("Origin")
            return o is None or o in {f"http://{h}" for h in host_ok}

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if not self._local() or not hmac.compare_digest((q.get("t") or [""])[0], token):
                return self.send_error(403)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not self._local() or not self._origin_ok() or urlparse(self.path).path != "/rate":
                return self.send_error(403)
            n = min(int(self.headers.get("Content-Length") or 0), 65536)
            form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            if not hmac.compare_digest((form.get("token") or [""])[0], token):
                return self.send_error(403)
            try:
                score = int((form.get("score") or ["-1"])[0])
            except ValueError:
                score = -1
            if not 0 <= score <= 10:
                return self.send_error(400, "score 0-10")
            ok, said = record(a.screen, score, (form.get("words") or [""])[0], [a.lune, "run", "kit"])
            result.update({"ok": ok, "score": score, "said": said})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<body style='background:#111;color:#eee;font:18px system-ui'><p>{html.escape(said)}</p><p>You can close this tab.</p></body>".encode("utf-8"))
            threading.Thread(target=srv.shutdown, daemon=True).start()

    srv = HTTPServer(("127.0.0.1", a.port), H)
    print(f"rate {a.screen}: open http://127.0.0.1:{a.port}/?t={token} — one key records the verdict", flush=True)
    srv.serve_forever()
    if not result:
        return emit("fail", f"rate {a.screen}: closed without a rating", f"lune run kit ui rate {a.screen}")
    return emit("pass" if result["ok"] else "fail", f"rate {a.screen}: the owner gave {result['score']}/10 — {result['said']}",
                "the verdict is in the vault: kit status --dept ui shows it")


if __name__ == "__main__":
    raise SystemExit(main())
