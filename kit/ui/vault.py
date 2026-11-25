"""vault.py — the UI library: EVERYTHING the UI pipeline makes is saved, packaged by part, named properly, for reuse
and reference (the owner's rule, 2026-10-12: "anything ever made is to be saved"). Enforced: `kit ui` runs `save`
after every build, the piece commands (ink / letter / render / trace / gauge) save their identity's pieces, and
`kit verify` runs `check` — a screen or a piece that is not in the vault (or is stale) FAILS the gate.

    python kit/ui/vault.py save   [--ui assets/ui] [--models src/ui] [--build build/ui] [--out library/ui] [--identity <id>]
    python kit/ui/vault.py check  [same]                     -> fail when anything made is missing or stale
    python kit/ui/vault.py list   [--out library/ui]
    python kit/ui/vault.py find "<words>"
    python kit/ui/vault.py get <Screen> [--as <NewName>] [--into <project root>]   (from this project's library/ui, or --from <root>)

library/ui/
  INDEX.md, index.json                    every package and every identity's piece count, with the owner's verdicts
  <identity>/identity.json                the identity pack as built
  <identity>/pieces/<piece>.png (+ sidecars, PIECES.md, PROVENANCE.md)   every piece the identity ever made
  <identity>/screens/<Screen>/
      README.md                           what it is, the owner's verdict, the parts table, how to reuse it
      manifest.json                       parts (node path -> kind -> file -> source), texts, hashes, verdicts
      screen.json (+ reel.json, gauge.json, judge.json, look.json)
      parts/<Node.Path>.png               every picture the screen shows, NAMED BY THE PART that shows it
      previews/sheet.png, motion.png, states.png, focus.png, cvd.png, reel.gif, reel.png
Files are rewritten only when their bytes change (a rebuild with nothing new changes nothing in git).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time

SIDE_EXTS = ("render.json", "ink.json", "trace.json", "letter.json", "smear.json", "spin.json", "anchors.json")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


TEXT_EXT = (".json", ".md", ".luau", ".lua", ".txt", ".py", ".toml", ".yaml", ".yml", ".csv")


def sha(path):
    """sha256 of a file; text files are hashed with CRLF read as LF, so the same content hashes the same in a
    checkout git wrote with Windows line endings (core.autocrlf: a fresh worktree) and one tools wrote with LF"""
    with open(path, "rb") as fh:
        data = fh.read()
    if path.lower().endswith(TEXT_EXT):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def same(stored, path):
    """a manifest's recorded hash matches the file: the line-ending-blind hash, or the raw one older manifests
    recorded from a CRLF working copy"""
    if stored == sha(path):
        return True
    with open(path, "rb") as fh:
        return stored == hashlib.sha256(fh.read()).hexdigest()


def put(src, dst, written):
    """copy only when the bytes differ (keeps git quiet on rebuilds)"""
    if not os.path.isfile(src):
        return False
    if os.path.isfile(dst) and sha(dst) == sha(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    written.append(dst)
    return True


def put_text(dst, text, written):
    if os.path.isfile(dst):
        with open(dst, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    written.append(dst)
    return True


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def screens(ui):
    out = []
    for p in sorted(glob.glob(os.path.join(ui, "*.json"))):
        base = os.path.basename(p)[:-5]
        if "." in base:
            continue
        spec = load(p)
        if isinstance(spec, dict) and isinstance(spec.get("root"), dict):
            out.append((base, p, spec))
    return out


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return "w_" + (s[:40] or "word")


def expand_range(name):
    """'soul_0..soul_4' / 'figurine_cards_0..4' -> each frame's name; any other name as it is"""
    m = re.fullmatch(r"(.*?)(\d+)\.\.(?:\1)?(\d+)", name)
    if not m or int(m.group(3)) < int(m.group(2)) or int(m.group(3)) - int(m.group(2)) > 200:
        return [name]
    width = len(m.group(2)) if m.group(2).startswith("0") and len(m.group(2)) > 1 else 0  # (frame_01..frame_03 keeps its zeros)
    return [f"{m.group(1)}{str(k).zfill(width)}" for k in range(int(m.group(2)), int(m.group(3)) + 1)]


def provenance(art_dir):
    """PROVENANCE.md in either form: table rows (| piece | source |) or sections (## piece + its lines, the generated
    packs' form — a section named "bonfire" also answers for "icon_bonfire")"""
    rows = {}
    p = os.path.join(art_dir, "PROVENANCE.md")
    if not os.path.isfile(p):
        return rows
    text = open(p, encoding="utf-8", errors="replace").read()
    for line in text.splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|", line)
        if m and m.group(1).lower() not in ("file", "---", "piece") and not set(m.group(1)) <= set("- "):
            for name in re.split(r"[,/]\s*", m.group(1)):
                name = name.strip().replace("`", "")
                for one in expand_range(name):  # (a flipbook's frames in one row: soul_0..soul_4, cards_0..4)
                    rows[one] = m.group(2).strip()
    head = re.split(r"^## ", text, flags=re.M)[0]
    intro = " ".join(ln.strip() for ln in head.splitlines()[1:] if ln.strip())[:160]
    for sec in re.split(r"^## ", text, flags=re.M)[1:]:
        name, _, body = sec.partition(chr(10))
        desc = re.search(r"description:\s*(.+)", body)
        seed = re.search(r"seed:\s*(\S+)", body)
        line = (f"generated: {desc.group(1).strip()[:120]}" if desc else body.strip()[:140]) + (f" (seed {seed.group(1)})" if seed else "")
        rows[name.strip()] = line + (f" — {intro}" if intro and not desc else "")
    return rows


def source_of(ident, piece, art_root, built_art):
    d = os.path.join(art_root, ident)
    for ext in SIDE_EXTS:
        side = load(os.path.join(d, f"{piece}.{ext}"))
        if isinstance(side, dict):
            kind = side.get("kind") or ext.split(".")[0]
            what = side.get("about") or side.get("from") or ""
            mode = f" ({side['mode']})" if side.get("mode") else ""
            return f"{kind}{mode}: {what}".strip(": ")
    prov = provenance(d)
    row = prov.get(piece) or prov.get(re.sub(r"^(icon|backdrop)_", "", piece))
    if row:
        return row
    m_glyph = re.match(r"^(.+)_([A-Za-z0-9]|u\d+)$", piece)
    if m_glyph and isinstance(load(os.path.join(d, f"{m_glyph.group(1)}.glyphs.json")), dict):
        g = load(os.path.join(d, f"{m_glyph.group(1)}.glyphs.json"))
        return f"kit ui letter --glyphs: one glyph of the digit set {m_glyph.group(1)} ({g.get('about') or g.get('font', '')})"
    m_spin = re.match(r"^(.+)_spin_(?:f\d+|sheet)$", piece)
    if m_spin and os.path.isfile(os.path.join(d, f"{m_spin.group(1)}_spin.spin.json")):
        return f"kit ui spin: a frame of {m_spin.group(1)} turning as a 3D mesh (its .spin.json)"
    if piece.endswith("_figure") and os.path.isfile(os.path.join(d, f"{piece[:-7]}.smear.json")):
        return f"kit ui smear --split: the sharp figure of {piece[:-7]} alone, on the same canvas (to break a frame)"
    if piece.endswith("_cell") and os.path.isfile(os.path.join(d, f"{piece[:-5]}.trace.json")):
        return f"kit ui trace: the blank cell cut from {piece[:-5]} (the traced plate; its .trace.json)"
    if os.path.isfile(os.path.join(built_art, ident, f"{piece}.png")) and not os.path.isfile(os.path.join(d, f"{piece}.png")):
        return "drawn by kit ui plates (the identity's shape language)"
    return "unknown — add a PROVENANCE.md row or a sidecar"


def piece_file(ident, piece, art_root, built_art):
    for base in (os.path.join(art_root, ident), os.path.join(built_art, ident), built_art):
        p = os.path.join(base, f"{piece}.png")
        if os.path.isfile(p):
            return p
    return None


def walk_parts(node, path, ident, out, texts):
    if not isinstance(node, dict):
        return
    name = str(node.get("name", "?"))
    here = f"{path}.{name}" if path else name
    pieces = []
    img = node.get("image")
    if isinstance(img, str) and img.startswith("art:"):
        ref = img[4:]
        pid, _, p = ref.partition("/") if "/" in ref else (ident, "", ref)
        pieces.append(("image", pid, p))
    plate = node.get("plate")
    if isinstance(plate, str):
        pid, _, p = plate.partition("/") if "/" in plate else (ident, "", plate)
        pieces.append(("plate", pid, p))
    if node.get("lettering") not in (None, False) and isinstance(node.get("text"), str):
        lt = node["lettering"]
        p = (lt.get("name") if isinstance(lt, dict) else None) or slug(node["text"])
        pieces.append(("lettering", ident, p))
    for kind, pid, p in pieces:
        out.append({"part": here, "kind": kind, "identity": pid, "piece": p})
    if isinstance(node.get("text"), str) and node["text"] and node.get("lettering") in (None, False):
        texts.append({"part": here, "text": node["text"], "role": node.get("role"), "type": node.get("type")})
    for c in node.get("children") or []:
        walk_parts(c, here, ident, out, texts)


def owner_of(judge):
    if not isinstance(judge, dict):
        return None, None
    o = judge.get("owner") or {}
    return o.get("score"), o.get("words")


def package(a, name, spec_path, spec, written, report):
    ident = spec.get("identity") or "kit"
    pkg = os.path.join(a.out, ident, "screens", name)
    model_path = os.path.join(a.models, f"{name}.model.json")
    # an OWNER-RATED version is never lost: when the spec changes after a verdict, the rated package is kept whole
    prev = load(os.path.join(pkg, "manifest.json"))
    if isinstance(prev, dict) and prev.get("owner") and not same(prev.get("spec_sha256"), spec_path):
        stamp = re.sub(r"[^0-9T]", "", str(prev.get("made") or "")) or time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        vdir = os.path.join(pkg, "versions", f"{stamp}_owner{prev['owner'].get('score')}")
        if not os.path.isdir(vdir):
            for f in ("README.md", "manifest.json", "screen.json", "reel.json", "gauge.json", "judge.json", "look.json"):
                put(os.path.join(pkg, f), os.path.join(vdir, f), written)
            for sub in ("parts", "previews"):
                d = os.path.join(pkg, sub)
                if os.path.isdir(d):
                    for f in os.listdir(d):
                        put(os.path.join(d, f), os.path.join(vdir, sub, f), written)
    parts, texts = [], []
    walk_parts(spec.get("root"), "", ident, parts, texts)
    # one file per distinct piece, named by the FIRST part that shows it; every other part points at the same file
    by_piece = {}
    for p in parts:
        key = (p["identity"], p["piece"])
        src = piece_file(p["identity"], p["piece"], os.path.join(a.ui, "art"), os.path.join(a.build, "art"))
        p["source"] = source_of(p["identity"], p["piece"], os.path.join(a.ui, "art"), os.path.join(a.build, "art"))
        if src is None:
            p["file"] = None
            report["missing_art"].append(f"{name}: {p['part']} -> {p['identity']}/{p['piece']}")
            continue
        if key not in by_piece:
            fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", p["part"].split(".", 1)[-1] if "." in p["part"] else p["part"]) + ".png"
            by_piece[key] = f"parts/{fname}"
            put(src, os.path.join(pkg, by_piece[key]), written)
        p["file"] = by_piece[key]
    # the screen's own files
    put(spec_path, os.path.join(pkg, "screen.json"), written)
    for ext in ("reel", "gauge", "judge", "look"):
        put(os.path.join(a.ui, f"{name}.{ext}.json"), os.path.join(pkg, f"{ext}.json"), written)
    for src, dst in ((f"{name}.png", "sheet.png"), (f"{name}.motion.png", "motion.png"), (f"{name}.states.png", "states.png"), (f"{name}.focus.png", "focus.png"), (f"{name}.cvd.png", "cvd.png"),
                     (os.path.join("reels", f"{name}.gif"), "reel.gif"), (os.path.join("reels", f"{name}.reel.png"), "reel.png")):
        put(os.path.join(a.build, src), os.path.join(pkg, "previews", dst), written)
    judge = load(os.path.join(a.ui, f"{name}.judge.json"))
    oscore, owords = owner_of(judge)
    old = load(os.path.join(pkg, "manifest.json"), {}) or {}
    spec_sha = sha(spec_path)
    model_sha = sha(model_path) if os.path.isfile(model_path) else None
    made = old.get("made") if old.get("spec_sha256") == spec_sha else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest = {"schema": 1, "screen": name, "identity": ident, "kind": spec.get("kind"), "quality": spec.get("quality"),
                "focus": spec.get("focus"), "hero": spec.get("hero"), "spec_sha256": spec_sha, "model_sha256": model_sha,
                "owner": {"score": oscore, "words": owords} if oscore is not None else None,
                "judges": {"median": judge.get("score"), "count": judge.get("judges")} if isinstance(judge, dict) and judge.get("score") is not None else None,
                "parts": parts, "texts": texts,
                "reuse": f"lune run kit ui vault get {name} --as <NewName>   (or: lune run kit new screen <NewName> --from {name} if it is a promoted example)",
                "made": made}
    put_text(os.path.join(pkg, "manifest.json"), json.dumps(manifest, indent=1) + "\n", written)
    # README: the human page
    lines = [f"# {name}  ({ident})", ""]
    if oscore is not None:
        lines.append(f"**Owner: {oscore}/100** — \"{owords}\"")
    if manifest["judges"]:
        lines.append(f"Fresh judges: median {manifest['judges']['median']} ({manifest['judges']['count']} judge(s))")
    lines += ["", f"Kind {spec.get('kind')}, quality {spec.get('quality')}, focus `{spec.get('focus')}`.", "",
              "![sheet](previews/sheet.png)", ""]
    if os.path.isfile(os.path.join(pkg, "previews", "reel.gif")):
        lines += ["Gameplay motion: ![reel](previews/reel.gif)", ""]
    lines += ["## Parts", "", "| part | kind | file | source |", "| --- | --- | --- | --- |"]
    for p in parts:
        lines.append(f"| `{p['part']}` | {p['kind']} | {p['file'] or 'MISSING'} | {str(p['source'])[:110]} |")
    if texts:
        lines += ["", "## Live texts", "", "| part | text | role |", "| --- | --- | --- |"]
        lines += [f"| `{t['part']}` | {t['text'][:40]} | {t.get('role') or ''} |" for t in texts]
    lines += ["", "## Reuse", "", "```", manifest["reuse"], "```", ""]
    put_text(os.path.join(pkg, "README.md"), "\n".join(lines), written)
    # the PROCESS page (kit/ui/exemplar.py): what it was made from and how, so a copy copies the route, not the look
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import exemplar  # noqa: E402

        proc = exemplar.page(name, a.ui, os.path.join(a.ui, "refs"), with_rounds=False)
        if proc:
            put_text(os.path.join(pkg, "PROCESS.md"), proc, written)
    except Exception as e:  # noqa: BLE001  (a page that cannot be written is reported, never fatal to the save)
        report.setdefault("process_errors", []).append(f"{name}: {e}")
    return manifest


def save_pieces(a, ident, written):
    src_dir = os.path.join(a.ui, "art", ident)
    dst = os.path.join(a.out, ident, "pieces")
    n = 0
    rows = ["# pieces — " + ident, "", "| piece | size | source |", "| --- | --- | --- |"]
    if os.path.isdir(src_dir):
        for f in sorted(os.listdir(src_dir)):
            full = os.path.join(src_dir, f)
            if not os.path.isfile(full):
                continue
            put(full, os.path.join(dst, f), written)
            if f.endswith(".png"):
                n += 1
                piece = f[:-4]
                try:
                    from PIL import Image
                    size = "x".join(map(str, Image.open(full).size))
                except Exception:  # noqa: BLE001
                    size = "?"
                rows.append(f"| `{piece}` | {size} | {source_of(ident, piece, os.path.join(a.ui, 'art'), os.path.join(a.build, 'art'))[:120]} |")
    put(os.path.join(a.ui, "identities", f"{ident}.json"), os.path.join(a.out, ident, "identity.json"), written)
    put_text(os.path.join(dst, "PIECES.md"), "\n".join(rows) + "\n", written)
    return n


def identities(a):
    ids = set()
    d = os.path.join(a.ui, "identities")
    if os.path.isdir(d):
        ids |= {f[:-5] for f in os.listdir(d) if f.endswith(".json")}
    d = os.path.join(a.ui, "art")
    if os.path.isdir(d):
        ids |= {f for f in os.listdir(d) if os.path.isdir(os.path.join(d, f))}
    return sorted(ids)


def routes_page(a):
    """library/ui/ROUTES.md: every PIECE ROUTE (kit/ui/routes.json) with its standing, how to make a piece on it, the
    owner's record, and how many pieces each live screen shows by it — the golden routes first, the graveyard last"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import routes as R  # noqa: E402

    tab = R.table()
    used, per_screen = {}, []
    for name, _path, spec in screens(a.ui):
        rows = R.screen_routes(spec, os.path.join(a.ui, "art"))
        counts = {}
        for _, piece, r, _ in rows:
            counts[r] = counts.get(r, 0) + 1
            if piece:
                used.setdefault(r, set()).add(piece)
        per_screen.append((name, counts))
    order = {"golden": 0, "ok": 1, "caution": 2, "graveyard": 3}
    lines = ["# UI piece routes", "",
             "Every way the UI pipeline makes a picture, and what the owner's verdicts say about it. `kit ui plan <Screen>` names",
             "each piece's route (kit/ui/routes.py) and stops a hero piece on a graveyard route; a hero screen needs at least one",
             "piece on a golden route. The table is kit/ui/routes.json.", "",
             "| route | standing | pieces in use | for | how | the record |", "| --- | --- | --- | --- | --- | --- |"]
    for k, v in sorted(tab.items(), key=lambda kv: (order.get(kv[1].get("status"), 9), kv[0])):
        lines.append(f"| {k} | {v.get('status')} | {len(used.get(k, ()))} | {v.get('for', '')} | `{v.get('make', '')}` | {v.get('evidence', '')} |")
    lines += ["", "## Screens by route", "", "| screen | golden | routes |", "| --- | --- | --- |"]
    golden = {k for k, v in tab.items() if v.get("status") == "golden"}
    for name, counts in sorted(per_screen, key=lambda sc: (-sum(n for r, n in sc[1].items() if r in golden), sc[0])):
        g = sum(n for r, n in counts.items() if r in golden)
        lines.append(f"| {name} | {g} | " + ", ".join(f"{r} {n}" for r, n in sorted(counts.items(), key=lambda kv: -kv[1])) + " |")
    return "\n".join(lines) + "\n"


def cmd_save(a):
    written = []
    report = {"missing_art": []}
    manifests = []
    for name, path, spec in screens(a.ui):
        if a.identity and spec.get("identity") != a.identity:
            continue
        manifests.append(package(a, name, path, spec, written, report))
    pieces = {i: save_pieces(a, i, written) for i in identities(a) if not a.identity or i == a.identity}
    if not a.identity:
        live = {m["screen"] for m in manifests}
        for mp in sorted(glob.glob(os.path.join(a.out, "*", "screens", "*", "manifest.json"))):
            m = load(mp)
            if isinstance(m, dict) and m.get("screen") not in live:
                m["retired"] = True  # (its spec is gone from assets/ui; the package stays: nothing made is lost)
                manifests.append(m)
        index = {"schema": 1, "rule": "everything the UI pipeline makes is saved here, packaged by part (kit/ui/vault.py); the vault never deletes",
                 "screens": {m["screen"]: {"identity": m["identity"], "kind": m["kind"], "quality": m["quality"], "owner": m["owner"], "retired": bool(m.get("retired")),
                                           "judges": m["judges"], "parts": len(m["parts"]), "path": f"{m['identity']}/screens/{m['screen']}"}
                             for m in manifests},
                 "pieces": pieces}
        put_text(os.path.join(a.out, "index.json"), json.dumps(index, indent=1) + "\n", written)
        rows = ["# UI library", "", "Everything the UI pipeline makes is saved here, packaged by part (the owner's rule).",
                "Reuse: `lune run kit ui vault get <Screen> --as <NewName>`; search: `lune run kit ui vault find \"<words>\"`.", "",
                "| screen | identity | kind | owner | judges | parts |", "| --- | --- | --- | --- | --- | --- |"]
        for m in sorted(manifests, key=lambda m: (-(m["owner"] or {}).get("score", 0) if m["owner"] else 0, m["screen"])):
            o = f"{m['owner']['score']} \"{str(m['owner']['words'])[:40]}\"" if m["owner"] else ""
            j = m["judges"]["median"] if m["judges"] else ""
            rows.append(f"| [{m['screen']}]({m['identity']}/screens/{m['screen']}/README.md) | {m['identity']} | {m['kind']} | {o} | {j} | {len(m['parts'])} |")
        rows += ["", "## Pieces per identity", ""] + [f"- [{i}]({i}/pieces/PIECES.md): {n} piece(s)" for i, n in sorted(pieces.items())]
        rows += ["", "How every piece is made, and the owner's record on each way: [ROUTES.md](ROUTES.md)."]
        put_text(os.path.join(a.out, "INDEX.md"), "\n".join(rows) + "\n", written)
        put_text(os.path.join(a.out, "ROUTES.md"), routes_page(a), written)
    miss = report["missing_art"]
    unknown = []
    for ident in identities(a):
        d = os.path.join(a.ui, "art", ident)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".png") and f != "world.png" and source_of(ident, f[:-4], os.path.join(a.ui, "art"), os.path.join(a.build, "art")).startswith("unknown"):
                    unknown.append(f"{ident}/{f[:-4]}")
    summary = (f"vault: {len(manifests)} screen package(s), {sum(pieces.values())} piece(s) across {len(pieces)} identit(ies) in {a.out}; "
               f"{len(written)} file(s) written" + (f"; {len(miss)} part(s) point at missing art" if miss else ""))
    if unknown:
        summary += f"; {len(unknown)} piece(s) with no source"
    nxt = (f"make or fix the missing art first: {miss[0]}" if miss else
           f"name where these came from (a PROVENANCE.md row or a sidecar): {', '.join(unknown[:4])}" if unknown else
           "none — everything made is saved")
    return emit("pass", summary, nxt, written=len(written), missing_art=miss[:20], unknown_source=unknown[:40])


def cmd_check(a):
    problems = []
    for name, path, spec in screens(a.ui):
        ident = spec.get("identity") or "kit"
        man = load(os.path.join(a.out, ident, "screens", name, "manifest.json"))
        if not isinstance(man, dict):
            problems.append(f"{name}: not in the vault")
            continue
        if not same(man.get("spec_sha256"), path):
            problems.append(f"{name}: the vault holds an older spec")
        mp = os.path.join(a.models, f"{name}.model.json")
        if os.path.isfile(mp) and not same(man.get("model_sha256"), mp):
            problems.append(f"{name}: the vault holds an older build")
    for ident in identities(a):
        src_dir = os.path.join(a.ui, "art", ident)
        if not os.path.isdir(src_dir):
            continue
        for f in os.listdir(src_dir):
            full = os.path.join(src_dir, f)
            if os.path.isfile(full) and f.endswith(".png"):
                dst = os.path.join(a.out, ident, "pieces", f)
                if not os.path.isfile(dst):
                    problems.append(f"{ident}/{f[:-4]}: a piece not in the vault")
                elif sha(dst) != sha(full):
                    problems.append(f"{ident}/{f[:-4]}: the vault holds an older piece")
    if problems:
        return emit("fail", f"vault: {len(problems)} thing(s) made but not saved (the rule: everything the UI pipeline makes is saved, packaged by part)",
                    "lune run kit ui vault   (or any `lune run kit ui` build: it saves automatically)", problems=problems[:30])
    return emit("pass", "vault: everything made is saved", "none — proceed")


def cmd_list(a):
    index = load(os.path.join(a.out, "index.json"))
    if not isinstance(index, dict):
        return emit("fail", f"vault: no library at {a.out}", "lune run kit ui vault")
    for name, s in sorted(index.get("screens", {}).items()):
        o = f"owner {s['owner']['score']}" if s.get("owner") else ""
        print(f"  {name:<22} {s['identity']:<8} {str(s.get('kind')):<5} {o:<10} {s['parts']} parts")
    return emit("pass", f"vault: {len(index.get('screens', {}))} screen package(s), pieces {index.get('pieces')}", "lune run kit ui vault get <Screen> --as <NewName>")


def cmd_find(a):
    words = [w for w in re.split(r"[\s,]+", (a.words or "").lower()) if w]
    hits = []
    for man_path in glob.glob(os.path.join(a.out, "*", "screens", "*", "manifest.json")):
        m = load(man_path) or {}
        for p in m.get("parts") or []:
            hay = f"{m.get('screen')} {p['part']} {p['piece']} {p.get('source', '')}".lower()
            sc = sum(2 if w in p["part"].lower() or w in p["piece"].lower() else (1 if w in hay else 0) for w in words)
            if sc:
                hits.append((sc, m.get("screen"), p))
    hits.sort(key=lambda h: -h[0])
    for sc, screen, p in hits[:15]:
        print(f"  {screen}: {p['part']}  ({p['kind']} {p['identity']}/{p['piece']})  {p.get('file')}  — {str(p.get('source'))[:80]}")
    if not hits:
        return emit("fail", f"vault: nothing matches '{a.words}'", "lune run kit ui find \"<words>\" searches the live art; or make it by the hero route")
    return emit("pass", f"vault: {len(hits)} part(s) for '{a.words}'", "lune run kit ui vault get <Screen> --as <NewName>, or copy the part's file")


def cmd_get(a):
    src_root = os.path.join(a.from_root, "library", "ui") if a.from_root else a.out
    found = glob.glob(os.path.join(src_root, "*", "screens", a.name, "manifest.json"))
    if not found:
        return emit("fail", f"vault: no package '{a.name}' in {src_root}", "lune run kit ui vault list")
    pkg = os.path.dirname(found[0])
    man = load(found[0])
    new = a.as_name or a.name
    into = a.into or "."
    ui_dst = os.path.join(into, "assets", "ui")
    spec = load(os.path.join(pkg, "screen.json"))
    spec["name"] = new
    dst_spec = os.path.join(ui_dst, f"{new}.json")
    if os.path.isfile(dst_spec):
        return emit("fail", f"vault get: {dst_spec} exists", "pick another --as name")
    written = []
    put_text(dst_spec, json.dumps(spec, indent=1) + "\n", written)
    for ext in ("reel", "gauge"):
        put(os.path.join(pkg, f"{ext}.json"), os.path.join(ui_dst, f"{new}.{ext}.json"), written)
    ident = man["identity"]
    id_dst = os.path.join(ui_dst, "identities", f"{ident}.json")
    if not os.path.isfile(id_dst):
        put(os.path.join(os.path.dirname(os.path.dirname(pkg)), "identity.json"), id_dst, written)
    # every piece the parts use, back under its own piece name (identity plates are redrawn by kit ui plates)
    pieces_dir = os.path.join(os.path.dirname(os.path.dirname(pkg)), "pieces")
    for p in man.get("parts") or []:
        src = os.path.join(pieces_dir, f"{p['piece']}.png")
        if os.path.isfile(src):
            dst = os.path.join(ui_dst, "art", p["identity"], f"{p['piece']}.png")
            if not os.path.isfile(dst):
                put(src, dst, written)
                for ext in SIDE_EXTS:
                    put(os.path.join(pieces_dir, f"{p['piece']}.{ext}"), os.path.join(ui_dst, "art", p["identity"], f"{p['piece']}.{ext}"), written)
    return emit("pass", f"vault get: {a.name} -> {dst_spec} ({len(written)} file(s): spec, identity, pieces)",
                "lune run kit ui --motion, then edit the copy (its parts table: the package README)")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="save", choices=["save", "check", "list", "find", "get"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--build", default="build/ui")
    ap.add_argument("--out", default="library/ui")
    ap.add_argument("--identity", default=None)
    ap.add_argument("--as", dest="as_name", default=None)
    ap.add_argument("--into", default=None)
    ap.add_argument("--from", dest="from_root", default=None)
    a = ap.parse_args()
    a.words = a.name
    return {"save": cmd_save, "check": cmd_check, "list": cmd_list, "find": cmd_find, "get": cmd_get}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
