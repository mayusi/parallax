"""ab_picks.py - BLIND A/B (AAA gaps v2 F3; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md): two versions of a move (v3 vs v4,
ours vs a rework) rendered on the OWNER'S rig exactly like the pick sheet (kit/anim/proc_picks.py: look_r6, the fidelity
line, real-time gifs with the Hit held) but shown as X and Y in a random order with every name hidden - the gif labels,
the file names, the page. The names come back only AFTER a pick (press X / Y or click), with the verdict lines to send.
A pick made knowing which one is "the new one" leans toward it; blind, it is the motion alone.
    python kit/anim/ab_picks.py <A> <B> [--seed n]
      -> build/ab/<A>__<B>/ab.html (+ x.gif, y.gif, ab.standalone.html)
"""
import html
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_picks as PP  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def order(a, b, seed):
    """-> (x, y): the two names in a random (seeded) order"""
    pair = [a, b]
    random.Random(seed).shuffle(pair)
    return pair[0], pair[1]


def page(x, y, out):
    """the blind page: only X and Y show until a pick; then the names and the verdict lines"""
    names = json.dumps({"X": x, "Y": y})
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blind A/B</title><style>
:root{{--bg:#f4f4f6;--fg:#1c1c20;--card:#fff;--muted:#6a6a74;--acc:#2f6fd6;--pick:#e8a317}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#ececf1;--card:#212127;--muted:#9a9aa6;--acc:#6aa0ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1500px;margin:0 auto;padding:16px}} h1{{margin:.2em 0}} .muted{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px;margin-top:14px}}
.card{{margin:0;background:var(--card);border-radius:10px;padding:8px;position:relative;cursor:pointer;border:3px solid transparent}}
.card.picked{{border-color:var(--pick)}} .card img{{width:100%;border-radius:6px;display:block}}
.num{{position:absolute;top:12px;left:12px;background:var(--acc);color:#fff;border-radius:6px;padding:0 10px;font-weight:700;font-size:20px}}
.name{{font-weight:700;min-height:1.4em}}
textarea{{width:100%;min-height:70px;font:inherit;border-radius:8px;padding:8px;box-sizing:border-box;background:var(--card);color:var(--fg)}}
pre{{white-space:pre-wrap;background:var(--card);padding:10px;border-radius:8px;font-size:13px}}
</style></head><body><main>
<h1>Blind A/B: which one moves better?</h1>
<p class="muted">Two versions of one move on your R6 rig (three-quarter | game camera | side), real time, the Hit held. The names stay hidden until you pick: press <b>X</b> or <b>Y</b>, or click one.</p>
<div class="grid">
<figure class="card" data-k="X"><div class="num">X</div><img src="x.gif" alt="version X"><figcaption class="name" id="nX"></figcaption></figure>
<figure class="card" data-k="Y"><div class="num">Y</div><img src="y.gif" alt="version Y"><figcaption class="name" id="nY"></figcaption></figure>
</div>
<h3>Your words</h3><textarea id="words" placeholder="what is better about it"></textarea>
<h3>Send this</h3><pre id="out">pick X or Y</pre>
</main><script>
const N={names};let pick=null;
function draw(){{document.querySelectorAll('.card').forEach(c=>c.classList.toggle('picked',c.dataset.k===pick));
if(!pick)return;
for(const k of ['X','Y'])document.getElementById('n'+k).textContent=N[k]+(k===pick?'  (your pick)':'');
const other=pick==='X'?'Y':'X';const w=document.getElementById('words').value.trim().replace(/"/g,"'");
document.getElementById('out').textContent=`BLIND A/B: ${{N[pick]}} over ${{N[other]}} — ${{w||'(words)'}}\\n\\n`+
`lune run kit verdict anim ${{N[pick]}} <0-10> "${{w||'...'}}" --vs ${{N[other]}} --tag ab`;}}
document.querySelectorAll('.card').forEach(c=>c.addEventListener('click',()=>{{pick=c.dataset.k;draw();}}));
document.addEventListener('keydown',e=>{{if(e.target.tagName==='TEXTAREA')return;const k=e.key.toUpperCase();if(k==='X'||k==='Y'){{pick=k;draw();}}}});
document.getElementById('words').addEventListener('input',draw);
</script></body></html>"""
    open(out, "w", encoding="utf-8", newline="").write(doc)


def main(argv):
    if len(argv) < 2 or argv[0].startswith("--"):
        return emit("fail", "ab: needs <A> <B>", "lune run kit anim ab Katana4Kiriage Katana4KiriageV2")
    a, b = argv[0], argv[1]
    if a == b:
        return emit("fail", "ab: A and B are the same clip", "name two versions")
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else random.SystemRandom().randrange(1 << 30)
    build = os.environ.get("KIT_BUILD", "build")
    clips = {n: os.path.join(build, "animations", f"{n}.clip.json") for n in (a, b)}
    for n, p in clips.items():
        if not os.path.exists(p):
            return emit("fail", f"ab: no clip {p}", f"build it first: lune run kit anim {n}")
    x, y = order(a, b, seed)
    out_dir = os.path.join(build, "ab", f"{a}__{b}")
    look_dir = os.path.join(out_dir, "look")
    os.makedirs(look_dir, exist_ok=True)
    for key, n in (("x", x), ("y", y)):
        frames_dir, fid = PP.render({"id": f"ab_{key}", "clip": clips[n]}, look_dir)   # (the tag hides the name)
        if frames_dir is None:
            return emit("fail", f"ab: the render of version {key.upper()} is not faithful to its clip: {str(fid)[:160]}",
                        "fix the clip / rig mapping first (kit anim look --rig R6)")
        clip = json.load(open(clips[n], encoding="utf-8"))
        PP.gif(frames_dir, clip, key.upper(), os.path.join(out_dir, f"{key}.gif"))
    out = os.path.join(out_dir, "ab.html")
    page(x, y, out)
    PP.standalone(out)
    json.dump({"x": x, "y": y, "seed": seed}, open(os.path.join(out_dir, "key.json"), "w", encoding="utf-8"), indent=1)
    rel = out.replace(os.sep, "/")
    return emit("pass", f"ab {a} vs {b}: blind page {rel} (X and Y in a random order; names revealed after the pick)",
                f"the owner opens {rel}, picks X or Y, sends the line it shows", page=rel)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
