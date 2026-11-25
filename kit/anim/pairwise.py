"""pairwise.py — the owner's PAIRWISE rating page (owner brief 2026-10-13): two versions of the same clip side by side,
blind (labelled A / B, the version names shown only after the vote), each with an optional ABSOLUTE score (1 horrible .. 5 love) + a short note (-> verdicts.json 'absolute'), the source reference above them; click (or press
1 / 2 / 3) A better / tie / B better. Every vote is appended to assets/animations/verdicts.json under "pairwise"
({date, clip, a, b, winner}); the least-voted pair comes next. Local only (127.0.0.1); it serves ONLY the files the
manifest lists.

    python kit/anim/pairwise.py gifs <look_dir> <out.gif>                 one version's front | side gif from a look
    python kit/anim/pairwise.py serve <manifest.json> [--port 8766]
manifest: {"title": "...", "clips": {"<clip>": {"reference": "<gif>", "versions": {"<version>": "<gif>", ...}}}}"""
import datetime
import http.server
import itertools
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERDICTS = os.path.join(ROOT, "assets", "animations", "verdicts.json")


def version_gif(look_dir, out_gif, size=300):
    from PIL import Image
    look = json.load(open(os.path.join(look_dir, "look.json"), encoding="utf-8"))
    frames = []
    for f in look["frames"][::4]:                          # every 4th 60 fps frame at 66 ms = real time
        ims = [Image.open(os.path.join(look_dir, f"{v}_{f:04d}.png")).convert("RGB").resize((size, size)) for v in ("front", "side")]
        im = Image.new("RGB", (2 * size, size))
        for i, x in enumerate(ims):
            im.paste(x, (i * size, 0))
        frames.append(im)
    frames[0].save(out_gif, save_all=True, append_images=frames[1:], duration=66, loop=0)
    return out_gif


def load_verdicts():
    if os.path.isfile(VERDICTS):
        return json.load(open(VERDICTS, encoding="utf-8"))
    return {"about": "owner verdicts", "verdicts": {}}


def votes():
    return load_verdicts().get("pairwise", [])


SCORES = {1: "horrible", 2: "bad", 3: "ok", 4: "good", 5: "love"}


def record(clip, a, b, winner, scores=None, notes=None):
    """the A/B/tie vote -> "pairwise"; each version's optional absolute 1..5 score + note -> "absolute" """
    data = load_verdicts()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    data.setdefault("pairwise", []).append({"date": now, "clip": clip, "a": a, "b": b, "winner": winner})
    for v in (a, b):
        sc, note = (scores or {}).get(v), ((notes or {}).get(v) or "").strip()[:200]
        if sc or note:
            data.setdefault("absolute", []).append({"date": now, "clip": clip, "version": v, "score": sc,
                                                    "word": SCORES.get(sc), "note": note})
    tmp = VERDICTS + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, VERDICTS)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Pairwise</title>
<style>
:root{--bg:#f6f6f8;--fg:#111;--card:#fff;--line:#ddd;--accent:#2b59c3}
@media (prefers-color-scheme:dark){:root{--bg:#16171a;--fg:#eee;--card:#202227;--line:#333;--accent:#7aa2ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
main{max-width:1320px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:0 0 4px} .sub{opacity:.7;margin-bottom:12px}
.ref{display:flex;gap:12px;align-items:center;margin-bottom:12px}
.ref img{height:180px;border:1px solid var(--line);border-radius:6px;background:#fff}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
.card img{width:100%;display:block;border-radius:4px}
.card b{font-size:16px}
.score{display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap}
.score button{padding:5px 9px;font-size:13px} .score button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.score input{flex:1;min-width:140px;font:inherit;padding:5px 8px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.btns{display:flex;gap:10px;justify-content:center;margin:14px 0}
button{font:inherit;padding:10px 22px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent)} .reveal{text-align:center;min-height:22px;opacity:.85}
table{border-collapse:collapse;margin-top:16px} td,th{border-bottom:1px solid var(--line);padding:4px 10px;text-align:left}
@media (max-width:760px){.pair{grid-template-columns:1fr}}
</style></head><body><main>
<h1 id="title"></h1><div class="sub" id="sub"></div>
<div class="ref"><img id="ref" alt="reference"><div>Reference (the source motion)</div></div>
<div class="pair">
<div class="card"><b>A</b><img id="ga" alt="A"><div class="score" data-side="a"></div></div>
<div class="card"><b>B</b><img id="gb" alt="B"><div class="score" data-side="b"></div></div></div>
<div class="btns"><button data-w="a">1 &middot; A better</button><button data-w="tie">2 &middot; Tie</button><button data-w="b">3 &middot; B better</button></div>
<div class="reveal" id="reveal"></div>
<table id="tally"></table>
</main><script>
let cur=null;
async function next(){const r=await fetch('/next');cur=await r.json();
 document.getElementById('title').textContent=cur.title;
 document.getElementById('sub').textContent='Clip: '+cur.clip+'  -  '+cur.done+' votes so far';
 document.getElementById('ref').src='/file?p='+encodeURIComponent(cur.reference);
 document.getElementById('ga').src='/file?p='+encodeURIComponent(cur.a_gif);
 document.getElementById('gb').src='/file?p='+encodeURIComponent(cur.b_gif);
 scoreRows();
 const t=cur.tally;let h='<tr><th>version</th><th>wins</th><th>ties</th><th>losses</th><th>score (1-5)</th></tr>';
 for(const k in t){const sc=t[k].n?(t[k].s/t[k].n).toFixed(1)+' ('+t[k].n+')':'-';
  h+='<tr><td>'+k+'</td><td>'+t[k].w+'</td><td>'+t[k].t+'</td><td>'+t[k].l+'</td><td>'+sc+'</td></tr>'}
 document.getElementById('tally').innerHTML=h;}
const WORDS=['horrible','bad','ok','good','love'];let picked={a:null,b:null};
function scoreRows(){document.querySelectorAll('.score').forEach(el=>{const side=el.dataset.side;picked[side]=null;
 el.innerHTML=WORDS.map((w,i)=>'<button type="button" data-s="'+(i+1)+'">'+(i+1)+' '+w+'</button>').join('')+'<input placeholder="note (optional)" maxlength="200">';
 el.querySelectorAll('button').forEach(b=>b.onclick=()=>{picked[side]=+b.dataset.s;el.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));});});}
async function vote(w){if(!cur)return;const c=cur;cur=null;
 const note=s=>document.querySelector('.score[data-side="'+s+'"] input').value;
 const scores={},notes={};scores[c.a]=picked.a;scores[c.b]=picked.b;notes[c.a]=note('a');notes[c.b]=note('b');
 await fetch('/vote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clip:c.clip,a:c.a,b:c.b,winner:w==='a'?c.a:w==='b'?c.b:'tie',scores:scores,notes:notes})});
 document.getElementById('reveal').textContent='Last: A = '+c.a+', B = '+c.b+' -> '+(w==='tie'?'tie':(w==='a'?c.a:c.b));
 next();}
document.querySelectorAll('button').forEach(b=>b.onclick=()=>vote(b.dataset.w));
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.key==='1')vote('a');if(e.key==='2')vote('tie');if(e.key==='3')vote('b');});
next();
</script></body></html>"""


def serve(manifest_path, port=8766):
    man = json.load(open(manifest_path, encoding="utf-8"))
    allowed = set()
    pairs = []
    for clip, d in man["clips"].items():
        allowed.add(os.path.normpath(os.path.join(ROOT, d["reference"])))
        for v in d["versions"].values():
            allowed.add(os.path.normpath(os.path.join(ROOT, v)))
        if d.get("pairs"):                                 # an explicit queue (e.g. every variant vs the base)
            pairs += [(clip, *sorted(p)) for p in d["pairs"]]
        else:
            pairs += [(clip, a, b) for a, b in itertools.combinations(sorted(d["versions"]), 2)]

    def tally():
        t = {}
        for v in votes():
            for side in ("a", "b"):
                t.setdefault(v[side], {"w": 0, "t": 0, "l": 0, "s": 0, "n": 0})
            if v["winner"] == "tie":
                t[v["a"]]["t"] += 1
                t[v["b"]]["t"] += 1
            else:
                loser = v["b"] if v["winner"] == v["a"] else v["a"]
                t[v["winner"]]["w"] += 1
                t[loser]["l"] += 1
        for a in load_verdicts().get("absolute", []):     # the absolute scores, shown beside the votes
            if a.get("score"):
                r = t.setdefault(a["version"], {"w": 0, "t": 0, "l": 0, "s": 0, "n": 0})
                r["s"] = r.get("s", 0) + a["score"]
                r["n"] = r.get("n", 0) + 1
        return t

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            if self.path == "/" or self.path.startswith("/?"):
                return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if self.path == "/next":
                done = votes()
                count = {}
                for v in done:
                    key = (v["clip"],) + tuple(sorted((v["a"], v["b"])))
                    count[key] = count.get(key, 0) + 1
                least = min(count.get(p, 0) for p in pairs)
                clip, a, b = random.choice([p for p in pairs if count.get(p, 0) == least])
                if random.random() < 0.5:
                    a, b = b, a
                d = man["clips"][clip]
                body = {"title": man.get("title", "Pairwise"), "clip": clip, "a": a, "b": b, "a_gif": d["versions"][a],
                        "b_gif": d["versions"][b], "reference": d["reference"], "done": len(done), "tally": tally()}
                return self._send(200, json.dumps(body).encode("utf-8"), "application/json")
            if self.path.startswith("/file?p="):
                from urllib.parse import unquote
                p = os.path.normpath(os.path.join(ROOT, unquote(self.path[len("/file?p="):])))
                if p not in allowed or not os.path.isfile(p):
                    return self._send(404, b"not listed", "text/plain")
                return self._send(200, open(p, "rb").read(), "image/gif")
            return self._send(404, b"", "text/plain")

        def _local(self):
            """only this page may talk to us: the Host must be ours (no DNS rebinding) and, on a vote, the Origin too
            with a JSON body (a cross-site form cannot send JSON without a CORS preflight, which is never answered)"""
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                return False
            if self.command == "POST":
                origin = self.headers.get("Origin")
                if origin is not None and origin not in {f"http://{h}" for h in hosts}:
                    return False
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    return False
            return True

        def do_POST(self):
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            if self.path != "/vote":
                return self._send(404, b"", "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            v = json.loads(self.rfile.read(n) or b"{}")
            ok = v.get("clip") in man["clips"] and {v.get("a"), v.get("b")} <= set(man["clips"][v["clip"]]["versions"]) \
                and v.get("winner") in (v.get("a"), v.get("b"), "tie")
            if not ok:
                return self._send(400, b"bad vote", "text/plain")
            scores = {k: int(x) for k, x in (v.get("scores") or {}).items() if k in (v["a"], v["b"]) and x in (1, 2, 3, 4, 5)}
            notes = {k: str(x) for k, x in (v.get("notes") or {}).items() if k in (v["a"], v["b"])}
            record(v["clip"], v["a"], v["b"], v["winner"], scores, notes)
            return self._send(200, b"{}", "application/json")

    print(f"pairwise: http://127.0.0.1:{port}/  ({len(pairs)} pairs, votes -> {VERDICTS})", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def main(argv):
    if argv[:1] == ["gifs"]:
        print(version_gif(argv[1], argv[2]))
        return 0
    if argv[:1] == ["serve"]:
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8766
        serve(argv[1], port)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
