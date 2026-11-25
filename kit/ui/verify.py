"""verify.py — the VERIFIER: the judge as a per-piece comparison, not a score (mission 03, 5.7). The same piece cut
from a real reference still and from the screen's own desktop frame, side by side at ONE scale (both are 1080p
frames), and a fresh model answers per pair with ONE visible difference and ONE concrete edit — plus the BUGS it
sees (a wrong state, an empty flip face, "1 HITS", art filtered out). The owner's words come first as the anchor;
there is no score anywhere (judges underrated the owner by 30-45 points and flipped on scale: VIGA, Jan 2026 —
a verifier, one difference + one edit per region, beats a scorer whose numbers plateau in noise).

    python kit/ui/verify.py pairs  <Screen> [--specs assets/ui] [--refs assets/ui/refs]   draft <Screen>.pairs.json
    python kit/ui/verify.py packet <Screen> [--specs assets/ui] [--ui build/ui] [--models src/ui] [--out build/judge/ui]
    python kit/ui/verify.py record <Screen> --verdict <file.json> [--specs assets/ui] [--models src/ui] [--out build/judge/ui]

<Screen>.pairs.json (assets/ui): [{"piece": "health bar", "node": "Hud.P1", "still": "<path>", "box": [x0, y0, x1, y1]}]
— the box in the still's own 1080p pixels (a `kit ui read` element's box_1080). `pairs` drafts it from the stills'
.read.json elements by matching words to node names; every drafted row says "check": true until a person keeps it.
The verdict: {"by": "<model>", "pairs": [{"piece", "difference", "edit"}], "bugs": [{"where", "what"}]} — one row
per pair, no "score" key. Recorded as assets/ui/<Screen>.verify.json, tied to the build's model sha256.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refsdb  # noqa: E402

ROW_H = 180  # each pair row's height on the sheet (both crops at one scale, fitted to this)
SYNONYMS = {
    "health": {"hp", "health", "life", "vitals", "bar", "frame", "fill"},
    "tension": {"tension", "super", "meter", "gauge", "burst"},
    "timer": {"timer", "clock", "time", "round"},
    "combo": {"combo", "counter", "hits", "call"},
    "minimap": {"minimap", "map", "radar", "compass"},
    "ammo": {"ammo", "magazine", "mag", "weapon"},
    "title": {"title", "logo", "heading", "name"},
    "menu": {"menu", "list", "row", "rows", "items", "options"},
    "portrait": {"portrait", "face", "medal", "avatar", "emblem"},
    "speed": {"speed", "speedo", "dial", "tach", "rpm"},
    "soul": {"soul", "vessel", "mask", "masks"},
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def load(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def words(text):
    return set(re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "").lower()))


def expand(ws):
    out = set(ws)
    for key, syn in SYNONYMS.items():
        if ws & (syn | {key}):
            out |= syn | {key}
    return out


def side_of_label(text):
    """1 / 2 for a P1 / P2 (left / right) piece, else None"""
    m = re.search(r"\b[pP]([12])\b", text or "")
    return m.group(1) if m else None


def side_of_node(path):
    m = re.search(r"(?:^|\.)[A-Za-z]*?([12])(?=\.|$)", path.split(".", 1)[-1] if "." in path else path)
    return m.group(1) if m else None


def node_names(spec):
    out = []

    def walk(n, path):
        if not isinstance(n, dict):
            return
        p = f"{path}.{n.get('name')}" if path else str(n.get("name"))
        out.append(p)
        for c in n.get("children") or []:
            walk(c, p)
    walk(spec.get("root"), "")
    return out


def draft_pairs(spec, specs, refs_root):
    """pairs from the identity's read stills: each element whose label words meet a node's name words"""
    ident = load(os.path.join(specs, "identities", f"{spec.get('identity')}.json")) or {}
    kind = spec.get("kind") or "menu"
    nodes = node_names(spec)[1:]
    pairs, used = [], set()
    for s in refsdb.stills(spec.get("identity") or "", refs_root, ident):
        if s.get("kind") not in (kind, None):
            continue
        read = load(os.path.splitext(s["path"])[0] + ".read.json")
        if not read:
            continue
        for el in read.get("elements") or []:
            box = el.get("box_1080")
            lw = expand(words(el.get("label")))
            if not box or not lw:
                continue
            best, score = None, 0
            side = side_of_label(el.get("label"))
            for n in nodes:
                nw = words(n.split(".", 1)[-1])
                sc = len(lw & expand(nw))
                ns = side_of_node(n)
                if side and ns and side != ns:
                    continue  # (P2's gauge is never P1's node)
                if side and ns == side and sc:
                    sc += 2
                if sc > score or (sc == score and best and n.count(".") < best.count(".")):
                    best, score = n, sc
            if best and score and (el["label"], best) not in used:
                used.add((el["label"], best))
                pairs.append({"piece": el["label"], "node": best.split(".", 1)[-1] if "." in best else best,
                              "still": s["path"], "box": box, "check": True})
    return pairs


def cmd_pairs(a):
    spec = load(os.path.join(a.specs, f"{a.screen}.json"))
    if not spec:
        return emit("fail", f"verify pairs: no {a.specs}/{a.screen}.json", "name a screen in assets/ui")
    out = os.path.join(a.specs, f"{a.screen}.pairs.json")
    have = load(out) or []
    pairs = draft_pairs(spec, a.specs, a.refs)
    if not pairs:
        return emit("fail", f"verify pairs {a.screen}: no read still of its identity names a piece that matches a node",
                    f"read the stills first: lune run kit ui read <{a.refs}/{spec.get('identity')}/still> (its elements carry 1080p boxes), "
                    f"or write {out} by hand: [{{\"piece\", \"node\", \"still\", \"box\": [x0, y0, x1, y1]}}]")
    kept = [p for p in have if not p.get("check")]
    keys = {(p["piece"], json.dumps(p["node"])) for p in kept}  # (a node may be a list: a group)
    merged = kept + [p for p in pairs if (p["piece"], json.dumps(p["node"])) not in keys]
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(merged, fh, indent=1)
        fh.write("\n")
    return emit("pass", f"verify pairs {a.screen}: {len(pairs)} drafted from the read stills ({len(kept)} kept by a person) -> {out}",
                f"check each drafted row (the node really is that piece), drop \"check\" on the good ones, then: lune run kit ui verify {a.screen}",
                pairs=len(merged))


def label_font(size):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


CONTEXT = 48  # px of 1080p context around each piece: a cut at the crop's edge is the crop, not the screen


def crop(im, box, pad=CONTEXT):
    """the piece with CONTEXT px around it and its own box outlined (thin cyan), so the verifier sees what lies past
    the piece and never reads the crop's edge as clipping (a first verifier called a name cut by the crop 'clipped')"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
    c = im.crop((cx0, cy0, min(im.width, x1 + pad), min(im.height, y1 + pad))).copy()
    ImageDraw.Draw(c).rectangle([x0 - cx0, y0 - cy0, x1 - cx0 - 1, y1 - cy0 - 1], outline=(0, 230, 255), width=1)
    return c


def owner_anchor(specs, screen, identity):
    """the owner's words first: this screen's own verdict, else the identity's owner-rated screens"""
    lines = []
    j = load(os.path.join(specs, f"{screen}.judge.json")) or {}
    o = j.get("owner") or {}
    if o.get("score") is not None:
        lines.append(f"- {screen} (an earlier build): {o['score']}/100 — \"{o.get('words', '')}\"")
    for f in sorted(os.listdir(specs)):
        if f.endswith(".judge.json") and f != f"{screen}.judge.json":
            jj = load(os.path.join(specs, f)) or {}
            oo = jj.get("owner") or {}
            sp = load(os.path.join(specs, f[:-11] + ".json")) or {}
            if oo.get("score") is not None and sp.get("identity") == identity:
                lines.append(f"- {f[:-11]}: {oo['score']}/100 — \"{oo.get('words', '')}\"")
    return lines


def cmd_packet(a):
    spec = load(os.path.join(a.specs, f"{a.screen}.json"))
    pairs = load(os.path.join(a.specs, f"{a.screen}.pairs.json"))
    frame = os.path.join(a.ui, f"{a.screen}.desktop.png")
    boxes = (load(os.path.join(a.ui, f"{a.screen}.boxes.json")) or {}).get("boxes") or {}
    model = os.path.join(a.models, f"{a.screen}.model.json")
    if not spec:
        return emit("fail", f"verify: no {a.specs}/{a.screen}.json", "name a screen in assets/ui")
    if not pairs:
        return emit("fail", f"verify {a.screen}: no {a.specs}/{a.screen}.pairs.json (which reference piece is which node)",
                    f"lune run kit ui verify {a.screen} --pairs   (drafts them from the read stills)")
    if not os.path.isfile(frame) or not boxes:
        return emit("fail", f"verify {a.screen}: no full desktop frame / node boxes in {a.ui}", f"lune run kit ui {a.screen}")
    shot = Image.open(frame).convert("RGB")
    rows, missing = [], []
    for i, p in enumerate(pairs, 1):
        # a node, or a LIST of nodes (a group the screen keeps as siblings — level + XP + money): their union box
        names = p.get("node") if isinstance(p.get("node"), list) else [p.get("node")]
        found = [b for path, b in boxes.items() if any(path.split(".", 1)[-1] == nm or path == nm for nm in names)]
        nb = None
        if found and len(found) >= len(names):
            x0 = min(b[0] for b in found)
            y0 = min(b[1] for b in found)
            x1 = max(b[0] + b[2] for b in found)
            y1 = max(b[1] + b[3] for b in found)
            nb = (x0, y0, x1 - x0, y1 - y0)
        if not nb or not os.path.isfile(p.get("still", "")):
            missing.append(p.get("piece", f"#{i}"))
            continue
        ref = Image.open(p["still"]).convert("RGB")
        if ref.size != (1920, 1080):  # (the box is in 1080p pixels: bring the still to that frame)
            k = 1080 / ref.height
            ref = ref.resize((max(1, round(ref.width * k)), 1080), Image.LANCZOS)
        x, y, w, h = nb
        rows.append((i, p, crop(ref, p["box"]), crop(shot, (x, y, x + w, y + h))))
    if not rows:
        return emit("fail", f"verify {a.screen}: no pair could be cut (nodes or stills missing: {', '.join(missing[:4])})",
                    f"fix {a.specs}/{a.screen}.pairs.json: each node a path below the root (Hud.P1), each still a file")
    # one scale for the whole sheet: the tallest crop fits ROW_H, so sizes compare across the pair AND down the rows
    # (a packet of one or two big pieces gets taller rows: a 490 px vessel crop at 180 px read at 0.33x)
    row_h = max(ROW_H, min(360, 720 // max(1, len(rows))))
    k = min(1.0, row_h / max(max(r[2].height, r[3].height) for r in rows))
    colw = max(max(r[2].width, r[3].width) for r in rows) * k
    W = int(colw * 2 + 60)
    H = int(sum(max(r[2].height, r[3].height) * k + 34 for r in rows) + 30)
    sheet = Image.new("RGB", (min(W, 2400), H), (28, 28, 32))
    d = ImageDraw.Draw(sheet)
    f = label_font(15)
    d.text((10, 6), f"{a.screen} — REFERENCE (left) vs THIS BUILD (right), one scale: {k:.2f}x of 1080p", fill=(255, 220, 120), font=f)
    yy = 30
    for i, p, rc, sc in rows:
        d.text((10, yy), f"{i}. {p['piece']}  (node {p['node']})", fill=(230, 230, 230), font=f)
        yy += 20
        r2 = rc.resize((max(1, int(rc.width * k)), max(1, int(rc.height * k))), Image.LANCZOS)
        s2 = sc.resize((max(1, int(sc.width * k)), max(1, int(sc.height * k))), Image.LANCZOS)
        sheet.paste(r2, (10, yy))
        sheet.paste(s2, (int(colw) + 40, yy))
        yy += int(max(r2.height, s2.height)) + 14
    out = os.path.join(a.out, a.screen, "verify")
    os.makedirs(out, exist_ok=True)
    sheet.save(os.path.join(out, "pairs.png"))
    anchor = owner_anchor(a.specs, a.screen, spec.get("identity"))
    lines = [f"# Verify {a.screen} — one difference + one edit per piece (no score)", "",
             "You are a FRESH verifier: you did not make this. `pairs.png` shows each piece twice at ONE scale: the REAL",
             "game's piece (left, cut from a 1080p still) and this build's (right, cut from its 1920x1080 frame). Sizes",
             "compare directly. Do NOT score. For every pair name the ONE biggest visible difference and ONE concrete edit",
             "(which property, which way, by how much in 1080p pixels or colour), then list the BUGS you see anywhere: a",
             "wrong state, an empty face, a wrong plural (\"1 HITS\"), art missing, text clipped or overlapping.",
             f"Each crop shows the piece inside a thin CYAN box with {CONTEXT} px of the screen around it: something cut at the",
             "crop's outer edge is the CROP, not a bug — only call clipping you see INSIDE the picture.", "",
             "## The owner's words (the anchor: the owner's eye outranks any judge)", ""]
    lines += anchor or ["- (no owner verdict on this identity yet)"]
    lines += ["", "## Pairs", ""] + [f"{i}. {p['piece']} — node `{p['node']}`, still `{os.path.basename(p['still'])}` box {p['box']}" for i, p, _, _ in rows]
    lines += ["", "## Answer with exactly this JSON (verdict.json)", "", "```json",
              json.dumps({"by": "<your model>", "pairs": [{"piece": p["piece"], "difference": "...", "edit": "..."} for _, p, _, _ in rows],
                          "bugs": [{"where": "<node or area>", "what": "..."}]}, indent=1), "```"]
    with open(os.path.join(out, "PROMPT.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    pk = {"schema": 1, "screen": a.screen, "pairs": [p["piece"] for _, p, _, _ in rows], "skipped": missing,
          "model_sha256": sha256_file(model) if os.path.isfile(model) else None, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out, "packet.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pk, fh, indent=1)
    return emit("pass", f"verify {a.screen}: {len(rows)} pair(s) at {k:.2f}x" + (f", {len(missing)} skipped ({', '.join(missing[:3])})" if missing else "")
                + f" -> {out}/pairs.png + PROMPT.md", f"give {out}/PROMPT.md + pairs.png to a FRESH model, then: lune run kit ui verify {a.screen} --record <verdict.json>",
                pairs=len(rows))


def cmd_record(a):
    pk = load(os.path.join(a.out, a.screen, "verify", "packet.json"))
    v = load(a.verdict)
    model = os.path.join(a.models, f"{a.screen}.model.json")
    if not pk:
        return emit("fail", f"verify record: no packet for {a.screen}", f"lune run kit ui verify {a.screen}")
    if not isinstance(v, dict):
        return emit("fail", "verify record: the verdict is not a JSON object", "answer with the JSON in PROMPT.md")
    problems = []
    if "score" in v or any(isinstance(r, dict) and "score" in r for r in v.get("pairs") or []):
        problems.append("a verifier gives no score (one difference + one edit per piece)")
    if not str(v.get("by", "")).strip():
        problems.append('"by" names the model that verified')
    rows = v.get("pairs") if isinstance(v.get("pairs"), list) else []
    got = {r.get("piece") for r in rows if isinstance(r, dict)}
    for piece in pk["pairs"]:
        if piece not in got:
            problems.append(f"no answer for the pair \"{piece}\"")
    for r in rows:
        if not isinstance(r, dict) or len(str(r.get("difference", "")).strip()) < 8 or len(str(r.get("edit", "")).strip()) < 8:
            problems.append(f"pair \"{(r or {}).get('piece')}\": a difference AND an edit, each in words")
    if not isinstance(v.get("bugs"), list):
        problems.append('"bugs": a list (empty when there are none)')
    sha = sha256_file(model) if os.path.isfile(model) else None
    if pk.get("model_sha256") and sha != pk["model_sha256"]:
        problems.append("the build changed since the packet was made: make a new packet")
    if problems:
        return emit("fail", f"verify record {a.screen}: refused — " + "; ".join(problems[:4]), "fix the verdict and record again")
    rec = {"schema": 1, "screen": a.screen, "by": v["by"], "model_sha256": sha, "pairs": rows, "bugs": v["bugs"],
           "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(a.specs, f"{a.screen}.verify.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
        fh.write("\n")
    first = rows[0] if rows else {}
    return emit("pass", f"verify {a.screen}: recorded {len(rows)} difference(s) + {len(v['bugs'])} bug(s) by {v['by']}",
                (f"fix the bugs first: {v['bugs'][0].get('where')}: {v['bugs'][0].get('what')}" if v["bugs"]
                 else f"make ONE edit, the first pair's: {first.get('piece')}: {first.get('edit')}"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pairs", "packet", "record"):
        p = sub.add_parser(name)
        p.add_argument("screen")
        p.add_argument("--specs", default="assets/ui")
        p.add_argument("--refs", default="assets/ui/refs")
        p.add_argument("--ui", default="build/ui")
        p.add_argument("--models", default="src/ui")
        p.add_argument("--out", default="build/judge/ui")
        if name == "record":
            p.add_argument("--verdict", required=True)
    a = ap.parse_args()
    return {"pairs": cmd_pairs, "packet": cmd_packet, "record": cmd_record}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
