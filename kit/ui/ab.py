"""ab.py — a BLIND A/B pick between two screens or two versions of one (v7.16): the owner sees X and Y side by side in
a random order with the names hidden, presses X or Y (or = for "same"), then a score 0-9 / 10 for the winner; the
pick goes into the vault as `kit verdict screen <winner> <score> "<words>" --vs <loser> --tag ab` (a tie records
nothing but the words). Comparing beats rating alone: people judge better side by side than on an absolute scale.

    python kit/ui/ab.py <A> <B> [--port 47814] [--ui build/ui] [--specs assets/ui]

A and B are screen names (their preview frames, build/ui/<S>.desktop.png) or PNG paths (two renders of one screen:
then --name <Screen> names whose verdict it is). The server answers only 127.0.0.1, needs the per-run token printed
here, and stops after one pick.
"""
import argparse
import hmac
import html
import json
import os
import random
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rate import data_uri, emit  # noqa: E402


def picture(x, ui):
    """a screen name -> its preview frame; a path -> itself"""
    if x.lower().endswith(".png"):
        return x if os.path.isfile(x) else None
    for p in (os.path.join(ui, f"{x}.desktop.png"), os.path.join(ui, f"{x}.png")):
        if os.path.isfile(p):
            return p
    return None


def order(a, b, rng=None):
    """X / Y in a random order -> {"X": name, "Y": name}"""
    pair = [a, b]
    (rng or random).shuffle(pair)
    return {"X": pair[0], "Y": pair[1]}


def page(sides, pics, token):
    figs = "".join(f'<figure><figcaption>{k}</figcaption><img src="{data_uri(pics[k])}"></figure>' for k in ("X", "Y"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>A/B pick</title><style>
body{{background:#111;color:#eee;font:15px system-ui;margin:16px}} .two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media (max-width:900px){{.two{{grid-template-columns:1fr}}}} img{{max-width:100%;border:1px solid #333}} figure{{margin:0}}
figcaption{{font:700 28px system-ui;color:#fc6}} .keys button{{font:20px system-ui;min-width:52px;height:52px;margin:2px}}
input{{width:60%;font:15px system-ui;padding:6px}} #step2{{display:none}}</style></head><body>
<h2>Which is better? Press X or Y (= if the same). Names stay hidden until you pick.</h2>
<form id="f" method="POST" action="/pick"><input type="hidden" name="token" value="{html.escape(token)}">
<input type="hidden" name="pick" id="pick"><input type="hidden" name="score" id="score">
<div class="keys" id="step1"><button type="button" onclick="pick('X')">X</button><button type="button" onclick="pick('Y')">Y</button>
<button type="button" onclick="pick('=')">=</button></div>
<div id="step2"><p>How good is <b id="won"></b>? Press 0-9 (or click 10). Words optional:</p><input name="words" placeholder="your words (optional)">
<div class="keys">{''.join(f'<button type="button" onclick="go({n})">{n}</button>' for n in range(11))}</div></div></form>
<div class="two">{figs}</div>
<script>let picked=null;function pick(k){{picked=k;document.getElementById('pick').value=k;
if(k==='='){{go(-1);return}}document.getElementById('won').textContent=k;document.getElementById('step1').style.display='none';
document.getElementById('step2').style.display='block'}}
function go(n){{document.getElementById('score').value=n;document.getElementById('f').submit()}}
document.addEventListener('keydown',e=>{{if(document.activeElement.name==='words'&&e.key!=='Enter')return;const k=e.key.toUpperCase();
if(!picked&&(k==='X'||k==='Y'||k==='=')){{e.preventDefault();pick(k)}}else if(picked&&/^[0-9]$/.test(e.key)){{e.preventDefault();go(parseInt(e.key))}}}});
</script></body></html>"""


def verdict_args(sides, pick, score, words, name=None):
    """the kit verdict line for a pick (None for a tie): the winner is the screen; with --name both are versions of it"""
    if pick not in ("X", "Y"):
        return None
    won, lost = sides[pick], sides["Y" if pick == "X" else "X"]
    words = (words or "").strip() or "(picked blind, no words)"
    if words.startswith("-"):
        words = "(" + words.lstrip("-").strip() + ")"
    screen = name or won
    tag = "ab" if not name else f"ab,{os.path.basename(won)}"
    return ["verdict", "screen", screen, str(score), words, "--vs", os.path.basename(lost), "--tag", tag]


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--name", default=None, help="when A and B are two renders (PNG) of ONE screen: its name")
    ap.add_argument("--port", type=int, default=47814)
    ap.add_argument("--ui", default="build/ui")
    ap.add_argument("--lune", default="lune")
    a = ap.parse_args(argv)
    pa, pb = picture(a.a, a.ui), picture(a.b, a.ui)
    if not pa or not pb:
        miss = a.a if not pa else a.b
        return emit("fail", f"ab: no picture for {miss}", f"lune run kit ui {miss} (or give a PNG path)")
    if (a.a.lower().endswith(".png") or a.b.lower().endswith(".png")) and not a.name:
        return emit("fail", "ab: two PNGs need --name <Screen> (whose verdict the pick is)", "add --name <Screen>")
    sides = order(a.a, a.b)
    pics = {k: (pa if v == a.a else pb) for k, v in sides.items()}
    token = secrets.token_urlsafe(24)
    host_ok = {f"127.0.0.1:{a.port}", f"localhost:{a.port}"}
    body = page(sides, pics, token).encode("utf-8")
    result = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _local(self):
            return self.client_address[0] in ("127.0.0.1", "::1") and (self.headers.get("Host") or "") in host_ok

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if not self._local() or not hmac.compare_digest((q.get("t") or [""])[0], token):
                return self.send_error(403)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            o = self.headers.get("Origin")
            if not self._local() or (o is not None and o not in {f"http://{h}" for h in host_ok}) or urlparse(self.path).path != "/pick":
                return self.send_error(403)
            n = min(int(self.headers.get("Content-Length") or 0), 65536)
            form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            if not hmac.compare_digest((form.get("token") or [""])[0], token):
                return self.send_error(403)
            pick = (form.get("pick") or [""])[0]
            try:
                score = int((form.get("score") or ["-1"])[0])
            except ValueError:
                score = -1
            if pick not in ("X", "Y", "=") or (pick != "=" and not 0 <= score <= 10):
                return self.send_error(400, "pick X / Y / = and a score 0-10")
            words = (form.get("words") or [""])[0]
            args = verdict_args(sides, pick, score, words, a.name)
            said = "a tie: nothing recorded"
            ok = True
            if args:
                r = subprocess.run([a.lune, "run", "kit"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
                tail = [ln for ln in r.stdout.splitlines() if ln.startswith("summary:")]
                ok, said = r.returncode == 0, (tail[-1] if tail else r.stdout[-300:])
            result.update({"ok": ok, "pick": pick, "score": score, "said": said})
            reveal = f"X was {sides['X']}, Y was {sides['Y']}."
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<body style='background:#111;color:#eee;font:18px system-ui'><p>{html.escape(reveal)}</p>"
                             f"<p>{html.escape(said)}</p><p>You can close this tab.</p></body>".encode("utf-8"))
            threading.Thread(target=srv.shutdown, daemon=True).start()

    srv = HTTPServer(("127.0.0.1", a.port), H)
    print(f"ab: open http://127.0.0.1:{a.port}/?t={token} — X or Y, then a score", flush=True)
    srv.serve_forever()
    if not result:
        return emit("fail", "ab: closed without a pick", f"lune run kit ui ab {a.a} {a.b}")
    if result["pick"] == "=":
        return emit("pass", f"ab: the owner saw no difference ({sides['X']} vs {sides['Y']})", "keep either; the change did not read")
    won = sides[result["pick"]]
    return emit("pass" if result["ok"] else "fail", f"ab: the owner picked {won} ({result['score']}/10) — {result['said']}",
                "build on the winner; the vault holds the pick (--tag ab)")


if __name__ == "__main__":
    raise SystemExit(main())
