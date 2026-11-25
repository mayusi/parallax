"""pairs.py — "A or B?" grading rounds: the owner picks the better of two builds instead of scoring each 0-100.

People judge a PAIR far more reliably than an absolute number (GPTEval3D ranks 3D generators by pairwise votes + Elo;
the owner's own re-grades moved 5 points on average). A pairwise round says where the kit's score agrees with the
owner and where it does not — without asking them for a number.

    python kit/grading/pairs.py page <list.json> [out.html]   a local page: each pair side by side, sides shuffled,
                                                               authorship hidden; the owner clicks and downloads the
                                                               round file (kit/grading/README.md: "A or B?" rounds)
    python kit/grading/pairs.py agree <pairs.json> [scores.json]   how often a scorer picks the owner's winner (by
                                                               default the kit's own score, stored with each pick)
    python kit/grading/pairs.py strengths <pairs.json>          Bradley-Terry strengths: the owner's own ranking

list.json: {"title": "...", "pairs": [{"a": {"asset", "project", "render", "script_sha", "tris"}, "b": {...}}]}
pairs.json (kit/pairs.json, written by `kit grades --import-pairs`): [{"a": {...}, "b": {...}, "winner": "a"|"b"|"tie",
"margin": 1|2, "note", "source", "at"}]. Plain Python (the page embeds the renders as base64: no server, no network).
"""

import base64
import datetime
import json
import os
import random
import sys


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def key(side):
    return f"{side.get('project') or ''}/{side['asset']}"


def strengths(pairs, iters=200):
    """Bradley-Terry by minorise-maximise (Hunter 2004): {build: strength}, the strengths summing to the build count.
    A tie counts as half a win each way; a margin of 2 ("clearly better") counts twice."""
    names = sorted({key(p["a"]) for p in pairs} | {key(p["b"]) for p in pairs})
    w = {n: 0.0 for n in names}
    games = {}
    for p in pairs:
        a, b, m = key(p["a"]), key(p["b"]), float(p.get("margin") or 1)
        if p["winner"] == "a":
            w[a] += m
        elif p["winner"] == "b":
            w[b] += m
        else:
            w[a] += 0.5 * m
            w[b] += 0.5 * m
        games[(a, b)] = games.get((a, b), 0.0) + m
    s = {n: 1.0 for n in names}
    for _ in range(iters):
        new = {}
        for n in names:
            den = sum(g / (s[a] + s[b]) for (a, b), g in games.items() if n in (a, b))
            new[n] = (w[n] + 0.1) / (den + 0.2 / (s[n] + 1.0))  # (a weak prior: a build that never won stays finite)
        total = sum(new.values())
        s = {n: v * len(names) / total for n, v in new.items()}
    return s


def agreement(pairs, scores):
    """the share of the owner's decided pairs where the higher score is the owner's winner, and the pairs it got
    wrong. scores: {build key or asset: score}"""
    right, wrong, skipped = 0, [], 0
    for p in pairs:
        if p["winner"] == "tie":
            skipped += 1
            continue
        sa = scores.get(key(p["a"]), scores.get(p["a"]["asset"]))
        sb = scores.get(key(p["b"]), scores.get(p["b"]["asset"]))
        if sa is None or sb is None or sa == sb:
            skipped += 1
            continue
        if (sa > sb) == (p["winner"] == "a"):
            right += 1
        else:
            wrong.append(f"{p['a']['asset']} vs {p['b']['asset']}: owner chose {p['winner']}, the score {sa:.1f} vs {sb:.1f}")
    decided = right + len(wrong)
    return (right / decided if decided else None), right, decided, wrong, skipped


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>A or B?</title><style>
:root{--bg:#121316;--fg:#e8e6e1;--mute:#9a978f;--card:#1c1e22;--accent:#e8c478}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1200px;margin:0 auto;padding:16px}h1{font-size:20px;margin:8px 0}
.pair{background:var(--card);border-radius:10px;padding:12px;margin:16px 0}
.imgs{display:grid;grid-template-columns:1fr 1fr;gap:10px}.imgs img{width:100%;border-radius:6px;background:#000}
figure{margin:0}.lab{font-weight:700;color:var(--accent)}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
button{background:#2a2d33;color:var(--fg);border:1px solid #3a3e46;border-radius:6px;padding:8px 14px;cursor:pointer}
button.on{background:var(--accent);color:#111;border-color:var(--accent)}input{flex:1;min-width:200px;background:#0d0e10;
color:var(--fg);border:1px solid #3a3e46;border-radius:6px;padding:8px}.mute{color:var(--mute)}
@media(max-width:700px){.imgs{grid-template-columns:1fr}}
</style></head><body><main><h1 id="title"></h1>
<p class="mute">Each pair is the same kind of object, built two ways. Which looks better — more real, more finished?
Pick A, B or "same"; "clearly" if the gap is big. Then download the results at the bottom and import them:
<code>lune run kit grades --import-pairs &lt;file&gt;</code></p><div id="pairs"></div>
<div class="row"><button id="dl">Download results</button><span id="left" class="mute"></span></div></main>
<script>
const P=__PAIRS__;const SRC=__SOURCE__;const ans={};
document.getElementById('title').textContent='A or B? \\u2014 '+__TITLE__;
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function figure(src,cap){const f=el('figure');const i=el('img');i.src=src;i.alt=cap;f.appendChild(i);f.appendChild(el('figcaption','',cap));return f;}
function render(){const box=document.getElementById('pairs');box.replaceChildren();
P.forEach((p,i)=>{const d=el('div','pair');d.appendChild(el('div','lab','Pair '+(i+1)));
const imgs=el('div','imgs');imgs.appendChild(figure(p.left.img,'A'));imgs.appendChild(figure(p.right.img,'B'));d.appendChild(imgs);
const row=el('div','row');[['A','left',1],['A clearly','left',2],['same','tie',1],['B clearly','right',2],['B','right',1]]
.forEach(([t,w,m])=>{const b=el('button',(ans[i]&&ans[i].pick===w&&ans[i].margin===m)?'on':'',t);
b.onclick=()=>{ans[i]=Object.assign(ans[i]||{},{pick:w,margin:m});render();};row.appendChild(b);});
const n=document.createElement('input');n.placeholder='why (optional)';n.value=(ans[i]&&ans[i].note)||'';
n.oninput=()=>{ans[i]=Object.assign(ans[i]||{},{note:n.value});};row.appendChild(n);d.appendChild(row);box.appendChild(d);});
document.getElementById('left').textContent=Object.values(ans).filter(a=>a.pick).length+' of '+P.length+' answered';}
document.getElementById('dl').onclick=()=>{const pairs=[];P.forEach((p,i)=>{const a=ans[i];if(!a||!a.pick)return;
const winner=a.pick==='tie'?'tie':(a.pick==='left'?p.left.side:p.right.side);
pairs.push({a:p.a,b:p.b,winner:winner,margin:a.margin||1,note:a.note||''});});
const blob=new Blob([JSON.stringify({source:SRC,pairs:pairs},null,1)],{type:'application/json'});
const l=document.createElement('a');l.href=URL.createObjectURL(blob);l.download='pairs_round.json';l.click();};
render();</script></body></html>"""


def _embed(path, width=1280):
    """a render as a data URI — shrunk to a JPEG `width` wide when Pillow is there (a page of 2 MB sheets is too heavy
    to open), else as it is"""
    try:
        import io  # noqa: PLC0415

        from PIL import Image  # noqa: PLC0415

        im = Image.open(path).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except ImportError:
        with open(path, "rb") as fh:
            mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
            return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"


def page(list_file, out=None, seed=None):
    with open(list_file, encoding="utf-8") as fh:
        spec = json.load(fh)
    rng = random.Random(seed)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    base = os.path.dirname(os.path.abspath(list_file))
    items, missing = [], []
    for p in spec["pairs"]:
        sides = {}
        for k in ("a", "b"):
            img = p[k]["render"]
            path = img if os.path.isabs(img) else os.path.join(base, img)
            if not os.path.isfile(path):
                path = os.path.join(os.getcwd(), img)
            if not os.path.isfile(path):
                missing.append(img)
                continue
            sides[k] = _embed(path)
        if len(sides) < 2:
            continue
        ident = {k: {f: p[k].get(f) for f in ("asset", "project", "script_sha", "tris")} for k in ("a", "b")}
        flip = rng.random() < 0.5  # (the owner never knows which build is which, nor which side is the newer)
        left, right = ("b", "a") if flip else ("a", "b")
        items.append({"a": ident["a"], "b": ident["b"], "left": {"side": left, "img": sides[left]},
                      "right": {"side": right, "img": sides[right]}})
    rng.shuffle(items)
    out = out or os.path.join("build", "grading", f"pairs_{datetime.date.today().isoformat()}.html")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    source = f"local A-or-B page {os.path.basename(out)} made {stamp} ({len(items)} pairs)"
    html = (PAGE.replace("__TITLE__", json.dumps(spec.get("title", "a blind round")))
            .replace("__PAIRS__", json.dumps(items)).replace("__SOURCE__", json.dumps(source)))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out, len(items), missing


def main(argv):
    if not argv or argv[0] not in ("page", "agree", "strengths"):
        return emit("fail", "pairs: page <list.json> | agree <pairs.json> <scores.json> | strengths <pairs.json>",
                    "kit/grading/README.md: \"A or B?\" rounds")
    if argv[0] == "page":
        out, n, missing = page(argv[1], argv[2] if len(argv) > 2 else None)
        if not n:
            return emit("fail", f"pairs page: no pair had both renders ({', '.join(missing[:3])})", "build the pairs first")
        return emit("pass", f"pairs page: {n} pair(s) in {out}" + (f" ({len(missing)} render(s) missing)" if missing else ""),
                    f"the OWNER opens {out}, picks, downloads pairs_round.json, then runs: lune run kit grades "
                    "--import-pairs <that file>", page=out)
    with open(argv[1], encoding="utf-8") as fh:
        pairs = json.load(fh)
    if argv[0] == "strengths":
        st = strengths(pairs)
        order = sorted(st, key=lambda n: -st[n])
        return emit("pass", "owner's ranking (Bradley-Terry): " + ", ".join(f"{n.split('/')[-1]} {st[n]:.2f}" for n in order),
                    "compare it with the kit's scores: python kit/grading/pairs.py agree", strengths=st)
    if len(argv) > 2:
        with open(argv[2], encoding="utf-8") as fh:
            scores = json.load(fh)
    else:  # (no scorer given: the kit's own score of each build, stored when the pick was imported)
        scores = {}
        for p in pairs:
            for k in ("a", "b"):
                if isinstance(p[k].get("raw"), (int, float)):
                    scores[key(p[k])] = float(p[k]["raw"])
    share, right, decided, wrong, skipped = agreement(pairs, scores)
    if share is None:
        return emit("pass", f"pairs: nothing to compare ({skipped} tie / unscored)", "grade more pairs")
    return emit("pass", f"the score agrees with the owner on {right}/{decided} pair(s) ({share:.0%})"
                + (f"; disagrees: {'; '.join(wrong[:3])}" if wrong else ""),
                "where it disagrees, the measures miss what the owner sees", agreement=share, wrong=wrong)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
