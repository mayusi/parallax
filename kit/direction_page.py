"""direction_page.py — the OWNER'S REVIEW BOARD for a game's directions: every direction doc (world + sound) as one
page - the one idea, the three options side by side (frames to look at, sketches to play), their axes, the pillars,
the bans, the recommendation - so the owner picks from the real thing, not from a summary.

    python kit/direction_page.py <Game> [--lane world|sfx] [--out <file.html>] [--title "..."]
    (lune run kit world board / kit sfx board: one lane's board; both lanes only for a one-off owner presentation)

Reads games/<Game>/assets/worlds/direction/*.md and games/<Game>/assets/sounds/direction/*.md (kit/direction.py's
shape); embeds frames as JPEG and sketches as MP3 (plays everywhere, iPhone included). One JSON line.
"""

import base64
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import direction as D  # noqa: E402

CSS = """
:root { --bg:#15110d; --panel:#1f1914; --line:#3a2f24; --fg:#ece2d0; --muted:#b3a48c; --gold:#e3a94a; --ember:#b8573a;
  --display:"Cinzel","Trajan Pro",Georgia,serif; --body:"Alegreya Sans","Segoe UI",system-ui,sans-serif; color-scheme:dark; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); font:17px/1.55 var(--body); margin:0; }
.wrap { max-width:1120px; margin:0 auto; padding-block:40px 72px; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }
h1,h2,h3 { font-family:var(--display); font-weight:700; letter-spacing:.04em; text-wrap:balance; margin:0; }
h1 { font-size:clamp(30px,5vw,48px); line-height:1.1; }
h2 { font-size:clamp(24px,3.4vw,34px); margin-top:72px; padding-top:28px; border-top:1px solid var(--line); }
h3 { font-size:16px; }
.lane { font:600 12px/1 var(--body); text-transform:uppercase; letter-spacing:.16em; color:var(--gold); margin:40px 0 4px; }
.eyebrow { font:600 12px/1 var(--body); text-transform:uppercase; letter-spacing:.16em; color:var(--muted); }
.idea { font-size:clamp(18px,2.3vw,22px); font-style:italic; max-width:64ch; margin:14px 0 0; }
p.lede { color:var(--muted); max-width:68ch; margin:8px 0 0; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; margin-top:16px; }
@media (max-width:860px) { .grid { grid-template-columns:1fr; } }
.card { min-width:0; display:flex; flex-direction:column; gap:8px; }
.card img { width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:6px; border:1px solid var(--line); display:block; }
.tag { display:flex; gap:8px; align-items:baseline; }
.letter { font-family:var(--display); font-size:26px; color:var(--gold); line-height:1; }
.card p { margin:0; color:var(--muted); font-size:15px; }
.axes { font-size:13px; color:var(--muted); display:flex; flex-wrap:wrap; gap:6px; }
.axes span { border:1px solid var(--line); border-radius:999px; padding:2px 9px; }
.mine { font:600 11px/1.3 var(--body); letter-spacing:.1em; text-transform:uppercase; color:var(--bg); background:var(--gold); padding:6px 9px; border-radius:3px; }
.sound { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:16px; }
.play { all:unset; cursor:pointer; display:inline-flex; align-items:center; gap:10px; font:600 15px var(--body); color:var(--fg); }
.play:focus-visible { outline:2px solid var(--gold); outline-offset:4px; border-radius:4px; }
.disc { width:42px; height:42px; border-radius:50%; border:1.5px solid var(--gold); display:grid; place-items:center; flex:none; }
.disc svg { width:16px; height:16px; fill:var(--gold); }
.bar { height:3px; background:var(--line); border-radius:2px; overflow:hidden; }
.bar i { display:block; height:100%; width:0%; background:var(--gold); }
.rules { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px; margin-top:18px; }
@media (max-width:700px) { .rules { grid-template-columns:1fr; } }
.rules ul { margin:8px 0 0; padding-left:18px; color:var(--muted); }
.rules li { margin:4px 0; }
.rules li::marker { color:var(--ember); }
.pick { margin-top:14px; color:var(--muted); font-size:15px; }
.answer { margin-top:64px; border-top:1px solid var(--line); padding-top:22px; color:var(--muted); max-width:70ch; }
.answer b { color:var(--fg); }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
"""

JS = """
(function(){var PLAY='<path d="M4 2l10 6-10 6z"/>',PAUSE='<path d="M3 2h4v12H3zM9 2h4v12H9z"/>',cur=null;
document.querySelectorAll('.sound').forEach(function(box){var btn=box.querySelector('.play'),svg=box.querySelector('svg'),fill=box.querySelector('.bar i'),a=null;
btn.addEventListener('click',function(){if(!a){a=new Audio(box.dataset.src);a.addEventListener('timeupdate',function(){fill.style.width=(100*a.currentTime/(a.duration||24))+'%';});
a.addEventListener('ended',function(){svg.innerHTML=PLAY;fill.style.width='0%';});a.addEventListener('pause',function(){svg.innerHTML=PLAY;});a.addEventListener('play',function(){svg.innerHTML=PAUSE;});}
if(cur&&cur!==a)cur.pause();if(a.paused){cur=a;a.play().catch(function(){});}else{a.pause();}});});})();
"""


def jpg_uri(path):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((1280, 720))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def mp3_uri(path):
    out = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", path, "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "-"],
                         capture_output=True, check=True).stdout
    return "data:audio/mpeg;base64," + base64.b64encode(out).decode()


def parse(path):
    text = open(path, encoding="utf-8").read()
    sec = D.sections(text)
    title = re.match(r"#\s+(.+?)\s+[—-]", text)
    blocks = re.split(r"^###\s+", "\n".join(sec.get("Directions", [])), flags=re.M)[1:]
    dirs = []
    for blk in blocks:
        head, _, body = blk.partition("\n")
        m = re.match(r"(\w+)\s+[—-]\s+(.+)", head)
        axes = re.search(r"^Axes:\s*(.+)$", body, re.M)
        media = re.search(r"^(?:Frame|Sketch):\s*(\S+)", body, re.M)
        desc = " ".join(ln for ln in body.splitlines() if ln and not re.match(r"^(Axes|Frame|Sketch):", ln))
        dirs.append({"letter": m.group(1) if m else "?", "name": m.group(2) if m else head, "desc": desc,
                     "axes": [a.strip() for a in axes.group(1).split(";")] if axes else [],
                     "file": os.path.join(os.path.dirname(os.path.dirname(path)), media.group(1)) if media else None})
    return {"title": title.group(1) if title else os.path.basename(path), "idea": " ".join(sec.get("The one idea", [])).strip(),
            "intent": " ".join(sec.get("Intent", [])).strip(), "pillars": D.bullets(sec.get("Pillars", [])),
            "bans": D.bullets(sec.get("Bans", [])), "pick": " ".join(sec.get("Pick", [])).strip(), "dirs": dirs}


def section(doc, lane):
    e = html.escape
    out = [f'<div class="lane">{"The look" if lane == "world" else "The sound"}</div>']
    if lane == "world":
        out.append(f'<p class="idea">{e(doc["idea"])}</p><p class="lede">{e(doc["intent"])}</p>')
    else:
        out.append(f'<p class="idea">{e(doc["idea"])}</p>')
    out.append('<div class="grid">')
    for d in doc["dirs"]:
        axes = "".join(f"<span>{e(a)}</span>" for a in d["axes"])
        if lane == "world":
            img = f'<img src="{jpg_uri(d["file"])}" alt="{e(d["letter"] + ": " + d["name"])}">' if d["file"] and os.path.isfile(d["file"]) else ""
            out.append(f'<div class="card">{img}<div class="tag"><span class="letter">{e(d["letter"])}</span><h3>{e(d["name"])}</h3></div>'
                       f'<p>{e(d["desc"])}</p><div class="axes">{axes}</div></div>')
        else:
            src = mp3_uri(d["file"]) if d["file"] and os.path.isfile(d["file"]) else ""
            out.append(f'<div class="card sound" data-src="{src}"><button class="play" type="button" aria-label="Play {e(d["letter"])}">'
                       f'<span class="disc"><svg viewBox="0 0 16 16"><path d="M4 2l10 6-10 6z"/></svg></span>'
                       f'<span><span class="letter">{e(d["letter"])}</span>&nbsp; {e(d["name"])}</span></button><div class="bar"><i></i></div>'
                       f'<p>{e(d["desc"])}</p><div class="axes">{axes}</div></div>')
    out.append("</div>")
    out.append('<div class="rules"><div><div class="eyebrow">Pillars</div><ul>' + "".join(f"<li>{e(p)}</li>" for p in doc["pillars"]) +
               '</ul></div><div><div class="eyebrow">Bans</div><ul>' + "".join(f"<li>{e(b)}</li>" for b in doc["bans"]) + "</ul></div></div>")
    out.append(f'<p class="pick"><b>Pick:</b> {e(doc["pick"])}</p>')
    return "\n".join(out)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: direction_page.py <Game> [--out file.html]", "next_action": "lune run kit direction page <Game>"}))
        return 2
    game = argv[0]
    root = os.path.join("games", game)
    lane_tag = argv[argv.index("--lane") + 1] + "_" if "--lane" in argv else ""
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(root, "build", "direction", f"{game}_{lane_tag}directions.html")
    wdocs = {os.path.splitext(os.path.basename(f))[0]: f for f in sorted(_md(os.path.join(root, "assets", "worlds", "direction")))}
    sdocs = {os.path.splitext(os.path.basename(f))[0]: f for f in sorted(_md(os.path.join(root, "assets", "sounds", "direction")))}
    lane_only = argv[argv.index("--lane") + 1] if "--lane" in argv else None  # (the departments stay separate: one lane's board)
    if lane_only not in (None, "world", "sfx"):
        print(json.dumps({"status": "fail", "summary": f"--lane {lane_only}: the board has world or sfx", "next_action": "--lane world | --lane sfx"}))
        return 2
    if lane_only == "world":
        sdocs = {}
    elif lane_only == "sfx":
        wdocs = {}
    pieces = sorted(set(wdocs) | set(sdocs))
    if not pieces:
        print(json.dumps({"status": "fail", "summary": f"no direction docs in {root}", "next_action": "lune run kit world direction <Piece> --new"}))
        return 1
    title = argv[argv.index("--title") + 1] if "--title" in argv else f"{game} Directions"
    body = [f'<div class="eyebrow">{html.escape(game)} · directions, before building</div><h1>{html.escape(title)}</h1>',
            '<p class="lede">Each piece below has one idea and three directions for its look and its sound, rendered from the kit\'s real pieces and pipeline. Pick one per lane, or a mix; everything after is built to the pick.</p>']
    states = []
    cs = os.path.join(root, "build", "direction", f"{game}_colorscript.png")
    if lane_only != "sfx" and os.path.isfile(cs):  # the journey's mood rhythm first (kit world colorscript)
        body.append('<h2>The journey</h2><p class="lede">The colour script: each place in the order the player meets it, its palette, its value (light) and warmth.</p>'
                    f'<img src="{jpg_uri(cs)}" alt="colour script" style="width:100%;border-radius:6px;border:1px solid var(--line);margin-top:14px">')
    ss = os.path.join(root, "build", "direction", f"{game}_soundscript.png")
    if lane_only != "world" and os.path.isfile(ss):  # the journey's dynamics (kit sfx soundscript)
        body.append('<h2>The journey, heard</h2><p class="lede">The sound script: each place in order, its loudness, density, brightness and how long its space rings.</p>'
                    f'<img src="{jpg_uri(ss)}" alt="sound script" style="width:100%;border-radius:6px;border:1px solid var(--line);margin-top:14px">')
    for p in pieces:
        body.append(f"<h2>{html.escape(p)}</h2>")
        for lane, docs in (("world", wdocs), ("sfx", sdocs)):
            if p in docs:
                st = D.check(docs[p], lane)[0]
                states.append(f"{p} {lane}: {st}")
                body.append(section(parse(docs[p]), lane))
    body.append('<div class="answer"><p><b>To answer:</b> per piece, one letter for the look and one for the sound (or a mix, e.g. "C, with B\'s lanterns at night"), plus anything that bothers you. Your words are recorded as the pick.</p></div>')
    page = (f"<title>{html.escape(title)}</title>\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n"
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Alegreya+Sans:ital,wght@0,400;0,600;1,400&display=swap">\n'
            f"<style>{CSS}</style>\n<div class=\"wrap\">\n" + "\n".join(body) + f"\n</div>\n<script>{JS}</script>\n")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    print(json.dumps({"status": "pass", "summary": f"{len(pieces)} piece(s), {len(states)} direction doc(s) -> {out.replace(os.sep, '/')} ({len(page) // 1024} KB)",
                      "next_action": "publish it for the owner (an Artifact) and record their picks in each doc's ## Pick", "states": states, "out": out}))
    return 0


def _md(d):
    return [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md")] if os.path.isdir(d) else []


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
