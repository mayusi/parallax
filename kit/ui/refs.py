"""refs.py — reference gathering as ONE command: real stills of a game's screen type, from sources that answer
without a bot check, into assets/ui/refs/<identity>/candidates/ with a contact sheet and every source recorded.

    python kit/ui/refs.py <identity> "<game>" "<screen words>" [--wiki <fandom-subdomain | mediawiki host>] [--steam <appid>]
        [--drop <folder>] [--max 12] [--refs assets/ui/refs]

Sources (all public APIs, no scraping, no gated pages):
  - Steam store: storesearch → appdetails (the game's own screenshots, 1920x1080) — no age gate on the API
  - a Fandom wiki's MediaWiki API: a file search for the screen words, each File's real URL + size
  - the owner's drop folder (`--drop`): anything the owner saved by hand (the best source of all)
The human picks: `--keep <n,n,...>` copies chosen candidates up one level as the identity's references and
writes their REFS.md lines (source, size, the screen words) AND their rows in refs.json (size + screen type: `--type
hud|menu[:<screen>]`, else read from the words). A site behind a bot check is never bypassed.

    python kit/ui/refs.py <identity> --index                  every still's size + type into refs.json (kit/ui/refsdb.py)
    python kit/ui/refs.py <identity> --tag <file>=hud[:<screen>]   a person says what a still shows
    python kit/ui/refs.py <identity> --waive "<the owner's words>"   the owner waives the >= 1080p rule (quoted, dated)
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refsdb  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (roblox-kit refs; local, non-commercial reference gathering)"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_bytes(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def steam_candidates(game, appid=None, limit=12):
    """the Steam store's own screenshots for the game (appdetails has no age gate)"""
    out = []
    try:
        if not appid:
            q = urllib.parse.quote(game)
            hits = fetch_json(f"https://store.steampowered.com/api/storesearch/?term={q}&cc=us&l=en").get("items") or []
            if not hits:
                return out, "steam: no store match"
            appid = hits[0]["id"]
        d = fetch_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&l=en").get(str(appid), {}).get("data") or {}
        for i, s in enumerate((d.get("screenshots") or [])[:limit]):
            out.append({"source": "steam", "title": f"{d.get('name', game)} screenshot {i + 1}", "url": s["path_full"], "thumb": s["path_thumbnail"],
                        "page": f"https://store.steampowered.com/app/{appid}/"})
        return out, f"steam: app {appid} ({d.get('name', '?')}), {len(out)} screenshot(s)"
    except Exception as e:  # noqa: BLE001
        return out, f"steam: {e}"


def wiki_base(sub):
    """(api url, page url prefix): a Fandom subdomain ('megamitensei') or ANY MediaWiki host ('splatoonwiki.org' —
    a game's best wiki is often its own: Inkipedia, Bulbapedia, zeldawiki.wiki), whose api sits at /w/api.php or /api.php"""
    if "." not in sub:
        return f"https://{sub}.fandom.com/api.php", f"https://{sub}.fandom.com/wiki/"
    host = sub.split("://")[-1].strip("/").split("/")[0]  # (a host given with a path, x.org/wiki/, is the host)
    for path, pages in (("/w/api.php", "/wiki/"), ("/api.php", "/wiki/")):
        try:
            res = fetch_json(f"https://{host}{path}?action=query&meta=siteinfo&format=json")
            art = (res.get("query", {}).get("general") or {}).get("articlepath", "")
            return f"https://{host}{path}", f"https://{host}{art.replace('$1', '')}" if art else f"https://{host}{pages}"
        except Exception:  # noqa: BLE001  (try the next layout)
            continue
    return f"https://{host}/w/api.php", f"https://{host}/wiki/"


def is_frame(size):
    """2 = a full game frame (16:9 or 16:10, >= 1280 wide), 1 = a big picture, None = too small to read a HUD in (an icon)"""
    try:
        w, h = int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        return 1  # (unknown size: keep it, unranked)
    if w < 640 or h < 360:
        return None
    return 2 if w >= 1280 and (abs(w / h - 16 / 9) < 0.05 or abs(w / h - 1.6) < 0.03) else 1


def wiki_candidates(sub, words, limit=12):
    """a wiki's files that match the screen words (the MediaWiki API: real URLs, real sizes) — Fandom or any host"""
    out = []
    try:
        base, page_at = wiki_base(sub)
        q = urllib.parse.quote(words)
        # (ask for 4x: icons, logos and portraits are dropped below, full game FRAMES ranked first)
        res = fetch_json(f"{base}?action=query&list=search&srsearch={q}&srnamespace=6&srlimit={min(50, 4 * limit)}&format=json")
        titles = [h["title"] for h in (res.get("query", {}).get("search") or [])]
        if not titles:
            return out, f"wiki {sub}: no file matches"
        t = urllib.parse.quote("|".join(titles))
        info = fetch_json(f"{base}?action=query&titles={t}&prop=imageinfo&iiprop=url|size|mime&format=json")
        for p in (info.get("query", {}).get("pages") or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("url") or not str(ii.get("mime", "")).startswith("image/"):
                continue
            out.append({"source": f"wiki:{sub}", "title": p["title"], "url": ii["url"], "size": [ii.get("width"), ii.get("height")],
                        "page": f"{page_at}{urllib.parse.quote(p['title'].replace(' ', '_'))}"})
        n = len(out)
        out = [c for c in out if is_frame(c.get("size")) is not None]
        out.sort(key=lambda c: -is_frame(c["size"]))
        out = out[:limit]
        frames = sum(1 for c in out if is_frame(c["size"]) == 2)
        return out, f"wiki {sub}: {len(out)} file(s) for '{words}' ({frames} full frame(s); {n - len(out)} small / left over)"
    except Exception as e:  # noqa: BLE001
        return out, f"wiki {sub}: {e}"


def drop_candidates(folder):
    out = []
    if folder and os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                out.append({"source": "owner", "title": f, "url": os.path.join(folder, f), "page": "the owner's drop folder"})
    return out


def load_identity(a):
    p = os.path.join(a.identities, f"{a.identity}.json")
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None


def parse_type(t):
    kind, _, screen = (t or "").partition(":")
    if kind not in refsdb.KINDS:
        raise SystemExit(f"refs: a type is {' | '.join(refsdb.KINDS)}[:<screen>], not {t!r}")
    return kind, (screen or None)


def manifest_cmd(a):
    """--index / --tag / --waive: the identity's stills as data (refs.json in each of its reference folders)"""
    ident = load_identity(a)
    dirs = refsdb.folders(a.identity, a.refs, ident)
    if not dirs:
        return emit("fail", f"refs: {a.identity} has no reference folder ({a.refs}/{a.identity}) and no listed reference picture",
                    f'gather stills first: lune run kit ui refs {a.identity} "<the game>" "<screen words>" --rank "<what it shows>"')
    tagged, unknown = [], []
    for d in dirs:
        man = refsdb.index(d, ident)
        for t in a.tag:
            f, _, ty = t.partition("=")
            kind, screen = parse_type(ty)
            s = next((s for s in man["stills"] if s["file"] == f), None)
            if s:
                s.update({"kind": kind, "screen": screen, "typed": "tag"})
                tagged.append(f)
        if a.waive and d == dirs[0]:
            man["waiver"] = {"by": "owner", "words": a.waive, "date": time.strftime("%Y-%m-%d", time.gmtime())}
        refsdb.save_manifest(d, man)
    missing = [t.partition("=")[0] for t in a.tag if t.partition("=")[0] not in tagged]
    if missing:
        unknown = missing
    all_ = refsdb.stills(a.identity, a.refs, ident)
    big = [s for s in all_ if refsdb.is_1080(s.get("size"))]
    kinds = {}
    for s in big:
        kinds[s.get("kind") or "untyped"] = kinds.get(s.get("kind") or "untyped", 0) + 1
    untyped = [s["file"] for s in big if not s.get("kind")]
    summary = (f"refs {a.identity}: {len(all_)} still(s) in {', '.join(dirs)}; {len(big)} at >= 1080p — "
               + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
               + (f"; tagged {len(tagged)}" if tagged else "") + (f"; waiver recorded" if a.waive else ""))
    if unknown:
        return emit("fail", summary + f"; no still named {', '.join(unknown)}", "tag a file that is in the folder (the names are in refs.json)")
    return emit("pass", summary,
                (f"say what the untyped ones show: lune run kit ui refs {a.identity} --tag {untyped[0]}=hud   (or =menu:<screen>)" if untyped
                 else f"lune run kit ui plan <Screen>   (the refs lock reads these)"), stills=len(all_), at_1080=len(big))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("identity")
    ap.add_argument("game", nargs="?")
    ap.add_argument("words", nargs="?")
    ap.add_argument("--index", action="store_true", help="record every still's size and screen type in refs.json")
    ap.add_argument("--tag", action="append", default=[], help="<file>=hud|menu[:<screen>] (a person says what a still shows)")
    ap.add_argument("--waive", default=None, help="the owner's words waiving the >= 1080p rule for this identity")
    ap.add_argument("--type", default=None, help="--keep: what the kept stills show, hud | menu[:<screen>]")
    ap.add_argument("--identities", default="assets/ui/identities")
    ap.add_argument("--wiki", default=None, help="the game's wiki: a fandom subdomain (megamitensei) or any MediaWiki host (splatoonwiki.org)")
    ap.add_argument("--steam", default=None, help="a Steam app id (else the store search picks the first match)")
    ap.add_argument("--drop", default=None, help="the owner's folder of hand-saved pictures")
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--keep", default=None, help="candidate numbers to promote to references: 1,4,7")
    ap.add_argument("--refs", default="assets/ui/refs")
    ap.add_argument("--rank", default=None, help="what you need, in words: the candidates come back RANKED by it (SigLIP, kit/ui/read.py rank)")
    a = ap.parse_args()
    if a.index or a.tag or a.waive:
        return manifest_cmd(a)
    if not a.game or not a.words:
        return emit("fail", "refs: <identity> \"<game>\" \"<screen words>\" (or --index / --tag / --waive)",
                    f'lune run kit ui refs {a.identity} "<the game>" "<screen words>" --rank "<what the screen shows>"')
    folder = os.path.join(a.refs, a.identity)
    cand_dir = os.path.join(folder, "candidates")
    os.makedirs(cand_dir, exist_ok=True)
    index_path = os.path.join(cand_dir, "candidates.json")
    if a.keep:
        if not os.path.isfile(index_path):
            return emit("fail", "refs --keep: no candidates gathered yet", f"run without --keep first")
        index = json.load(open(index_path, encoding="utf-8"))
        kept = []
        lines = []
        for n in [int(x) for x in a.keep.split(",") if x.strip()]:
            c = next((c for c in index["candidates"] if c["n"] == n), None)
            if not c or not os.path.isfile(c["file"]):
                continue
            name = f"{a.identity}_{c['source'].split(':')[0]}_{n:02d}{os.path.splitext(c['file'])[1]}"
            shutil.copyfile(c["file"], os.path.join(folder, name))
            kept.append(name)
            lines.append(f"- {name} — {c['title']} ({c.get('size') or '?'}); source: {c['page']} ({c['url']}); gathered by kit ui refs for \"{index['words']}\" — measure-only unless the owner says otherwise")
        md = os.path.join(folder, "REFS.md")
        with open(md, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n" + "\n".join(lines) + "\n")
        # the manifest: each kept still's size and the screen type it shows (the plan's refs lock reads it)
        man = refsdb.index(folder, load_identity(a))
        kind, screen = parse_type(a.type) if a.type else (refsdb.kind_from_words(index["words"]), None)
        for s in man["stills"]:
            if s["file"] in kept and kind:
                s.update({"kind": kind, "screen": screen, "typed": "tag" if a.type else "words"})
        refsdb.save_manifest(folder, man)
        return emit("pass", f"refs: kept {len(kept)} reference(s) in {folder}: {', '.join(kept)}", f"measure them: lune run kit ui measure {folder}/{kept[0] if kept else '<file>'}", kept=kept)
    cands = []
    notes = []
    st, note = steam_candidates(a.game, a.steam, a.max)
    cands += st
    notes.append(note)
    if a.wiki:
        wk, note = wiki_candidates(a.wiki, f"{a.game} {a.words}", a.max)
        if not wk:  # (a wiki that names its files its own way — Inkipedia's 'S3 ...' — matches the words alone)
            wk, note2 = wiki_candidates(a.wiki, a.words, a.max)
            note = f"{note}; then the words alone: {note2}"
        cands += wk
        notes.append(note)
    dr = drop_candidates(a.drop)
    cands += dr
    if dr:
        notes.append(f"owner drop: {len(dr)}")
    if not cands:
        return emit("fail", "refs: nothing found — " + "; ".join(notes), "pass --wiki <fandom subdomain> or --drop <folder with the owner's pictures>")
    # download thumbnails / small copies for the contact sheet, keep the full-size file paths
    from PIL import Image, ImageDraw
    got = []
    for i, c in enumerate(cands[: a.max * 2], 1):
        ext = ".png" if c["url"].lower().endswith(".png") else ".jpg"
        dst = os.path.join(cand_dir, f"c{i:02d}{ext}")
        try:
            if c["source"] == "owner":
                shutil.copyfile(c["url"], dst)
            else:
                open(dst, "wb").write(fetch_bytes(c["url"]))
            im = Image.open(dst)
            c.update({"n": i, "file": dst, "size": list(im.size)})
            got.append(c)
        except Exception as e:  # noqa: BLE001
            notes.append(f"c{i:02d}: {e}")
    if not got:
        return emit("fail", "refs: downloads failed — " + "; ".join(notes[-3:]), "check the network; or --drop a folder")
    cols = 3
    w, h = 400, 225
    sheet = Image.new("RGB", (cols * w, h * ((len(got) + cols - 1) // cols)), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for j, c in enumerate(got):
        im = Image.open(c["file"]).convert("RGB")
        im.thumbnail((w, h))
        sheet.paste(im, ((j % cols) * w, (j // cols) * h))
        d.rectangle([(j % cols) * w, (j // cols) * h, (j % cols) * w + 150, (j // cols) * h + 18], fill=(0, 0, 0))
        d.text(((j % cols) * w + 4, (j // cols) * h + 3), f"{c['n']}: {c['source']} {c['size'][0]}x{c['size'][1]}", fill=(255, 255, 0))
    sheet_path = os.path.join(cand_dir, "contact.png")
    sheet.save(sheet_path)
    json.dump({"schema": 1, "identity": a.identity, "game": a.game, "words": a.words, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "candidates": got}, open(index_path, "w", encoding="utf-8", newline="\n"), indent=1)
    if a.rank:
        # understand before looking: rank the candidates by what is needed, so the owner's / the model's look starts
        # at the best (a store page's marketing shots sink, gameplay stills with the interface rise)
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "read.py"), "rank", cand_dir, a.rank],
                           capture_output=True, text=True)
        line = (r.stdout.strip().splitlines() or ["{}"])[-1]
        try:
            ranked = json.loads(line)
        except Exception:  # noqa: BLE001
            ranked = {}
        order = ranked.get("ranked") or []
        best = [next((c["n"] for c in got if os.path.basename(c["file"]) == f), None) for f in order[:4]]
        return emit("pass", f"refs: {len(got)} candidate(s), RANKED for \"{a.rank}\": best {', '.join(str(b) for b in best if b)} — " + "; ".join(notes),
                    f"LOOK at {os.path.join(cand_dir, 'ranked.png')} (best first), keep: lune run kit ui refs {a.identity} \"{a.game}\" \"{a.words}\" --keep {','.join(str(b) for b in best[:2] if b)}",
                    candidates=len(got), ranked=order)
    return emit("pass", f"refs: {len(got)} candidate(s) for {a.game} / {a.words} in {cand_dir} — " + "; ".join(notes),
                f"LOOK at {sheet_path}, then keep the ones that show the screen: lune run kit ui refs {a.identity} \"{a.game}\" \"{a.words}\" --keep 1,4", candidates=len(got))


if __name__ == "__main__":
    raise SystemExit(main())
