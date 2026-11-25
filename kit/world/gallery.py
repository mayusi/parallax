"""kit world gallery — every world in one page: a card per world (its hero shot, its pitch, its numbers) opening its
web viewer, the contact sheet one click away.

    python kit/world/gallery.py <out_dir>

Scans games/*/ (each game's build/worlds/web/<World>.html + build/worlds/shots/<World>/ + GAME.md) and the project's
own build/worlds/. Writes <out_dir>/index.html (an Artifact-ready fragment), <out_dir>/<World>.html (each viewer, a
whole document) and <out_dir>/img/*.jpg. One JSON verdict line.
"""

import html
import json
import os
import re
import shutil
import sys

from PIL import Image


def pitch_of(game_dir):
    p = os.path.join(game_dir, "GAME.md")
    if not os.path.isfile(p):
        return "", ""
    text = open(p, encoding="utf-8").read()
    def section(name):
        m = re.search(r"## " + re.escape(name) + r"\n(.*?)(?:\n## |\Z)", text, re.S)
        v = (m.group(1).strip() if m else "")
        return "" if v.startswith("TODO") else v
    return section("Pitch"), section("Genre and source")


def worlds():
    out = []
    roots = [("", ".")] + [(g, os.path.join("games", g)) for g in sorted(os.listdir("games")) if os.path.isdir(os.path.join("games", g))] if os.path.isdir("games") else [("", ".")]
    for game, root in roots:
        web = os.path.join(root, "build", "worlds", "web")
        if not os.path.isdir(web):
            continue
        for f in sorted(os.listdir(web)):
            if not f.endswith(".html") or f.endswith(".artifact.html"):
                continue
            name = f[:-5]
            shots = os.path.join(root, "build", "worlds", "shots", name)
            flat = os.path.join(root, "build", "worlds", name + ".json")
            parts = 0
            if os.path.isfile(flat):
                try:
                    parts = len(json.load(open(flat, encoding="utf-8")).get("parts", []))
                except (OSError, ValueError):
                    pass
            pitch, source = pitch_of(root) if game else ("", "")
            out.append({"name": name, "game": game, "page": os.path.join(web, f), "shots": shots,
                        "sheet": os.path.join(root, "build", "worlds", "shots", name + ".png"),
                        "pitch": pitch, "source": source, "parts": parts})
    # a world that lives in a game wins over a stale copy of the same name at the project root
    in_games = {w["name"] for w in out if w["game"]}
    return [w for w in out if w["game"] or w["name"] not in in_games]


def jpg(src, dst, width):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)))
    im.save(dst, quality=84)


def main(argv):
    out = argv[1] if len(argv) > 1 else "build/worlds/gallery"
    ws = worlds()
    if not ws:
        print(json.dumps({"status": "fail", "summary": "no world pages found", "next_action": "lune run kit world shots <Name> (it builds the page and the shots)"}))
        return 1
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "img"))
    cards = []
    names = [w["name"] for w in ws]
    for w in ws:
        # two games with a world of the same name: keep both (the game in the file names)
        w["slug"] = re.sub(r"[^A-Za-z0-9_-]", "", (w["game"] + "-" if names.count(w["name"]) > 1 else "") + w["name"])
        shutil.copyfile(w["page"], os.path.join(out, w["slug"] + ".html"))
        hero, views = "", []
        if os.path.isdir(w["shots"]):
            shots = sorted(f for f in os.listdir(w["shots"]) if f.endswith(".jpg"))
            # the hero: an eye-level shot at a grace / landmark (a spawn pad in the foreground is no cover), else the overview
            eyes = [f for f in shots if f.startswith("eye") and not f.startswith("eye_spawn")]
            pick = (eyes[:1] or ["overview.jpg"]) + [f for f in ["overview.jpg"] if eyes] + [f for f in shots if f.startswith("near")][:2]
            pick = [f for f in pick if f in shots]  # (a tour that stopped early has fewer views)
            for k, f in enumerate(pick[:4]):
                dst = f"img/{w['slug']}_{k}.jpg"
                jpg(os.path.join(w["shots"], f), os.path.join(out, dst), 960 if k == 0 else 480)
                views.append(dst)
        if os.path.isfile(w["sheet"]):
            jpg(w["sheet"], os.path.join(out, f"img/{w['slug']}_sheet.jpg"), 1600)
        cards.append((w, views))
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gallery_template.html"), encoding="utf-8").read()
    items = []
    for w, views in cards:
        e = html.escape
        title = re.sub(r"([a-z])([A-Z])", r"\1 \2", w["name"])
        thumbs = "".join(f'<img src="{v}" alt="" loading="lazy">' for v in views[1:])
        hero = f'<img class="hero" src="{views[0]}" alt="{e(w["name"])} at eye level">' if views else '<div class="hero none"></div>'
        sheet = f'<a class="ghost" href="img/{e(w["slug"])}_sheet.jpg">Contact sheet</a>' if os.path.isfile(w["sheet"]) else ""
        items.append(f'''<article class="world">
  <a class="frame" href="{e(w["slug"])}.html">{hero}</a>
  <div class="body">
    <p class="kicker">{e(w["game"] and "games/" + w["game"] or "kit example")} · {w["parts"]:,} parts</p>
    <h2>{e(title)}</h2>
    <p class="pitch">{e(w["pitch"])}</p>
    <p class="source">{e(w["source"])}</p>
    <div class="thumbs">{thumbs}</div>
    <div class="actions"><a class="go" href="{e(w["slug"])}.html">Enter the world</a>{sheet}</div>
  </div>
</article>''')
    page = tpl.replace("<!--WORLDS-->", "\n".join(items)).replace("__COUNT__", str(len(cards)))
    open(os.path.join(out, "index.html"), "w", encoding="utf-8", newline="\n").write(page)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(out) for f in fs)
    print(json.dumps({"status": "pass", "summary": f"{len(cards)} world(s), {size / 1048576:.1f} MB -> {out}/index.html",
                      "next_action": f"publish {out}/index.html as an Artifact with its files (the viewers + img/)", "out": out,
                      "files": sorted(os.path.relpath(os.path.join(dp, f), out).replace(os.sep, "/") for dp, _, fs in os.walk(out) for f in fs if f != "index.html")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
