"""priors.py — LAYOUT KNOWLEDGE across games: where a genre puts each piece, measured from every reference the kit has
read (`kit ui read` writes <still>.read.json with the genre and named, boxed pieces).

    python kit/ui/read.py prior <genre> [--refs assets/ui/refs] [--out assets/ui/priors]   (lune run kit ui read prior fighting)

For each named piece (the label, with a P1 / P2 side kept, list-row numbers dropped): in how many stills of how many
games it was found, its MEDIAN box at 1080p and the spread (the middle half of where it sat) -> <genre>.json. A draft or a
new screen can then start from 'a fighting game puts the health bars here, this tall' instead of a guess.
"""
import json
import os
import re
import time

import numpy as np


GENERIC = {"interface panel", "label text", "icon", "bar", "panel", "graphic lettering", "a counter", "logo / emblem / portrait"}


def piece_name(label):
    """the label without per-still detail: list rows lose their k of n, descriptive finds keep 'found'"""
    label = re.sub(r"\s*\(\w+\)$", "", label)              # (rarity suffix)
    label = re.sub(r"card / list row \d+ of \d+", "card / list row", label)
    return label  # (a 'found: <words>' keeps its words: unrelated descriptions are not one piece)


def collect(refs_dir, genre):
    """every read element of that genre: [(game folder, still, name, box_1080)]"""
    out = []
    for root, _dirs, files in os.walk(refs_dir):
        if "candidates" in root.replace("\\", "/").split("/"):
            continue
        for f in files:
            if not f.endswith(".read.json"):
                continue
            try:
                d = json.load(open(os.path.join(root, f), encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("genre") != genre:
                continue
            game = os.path.basename(root)
            for e in d.get("elements") or []:
                name = piece_name(e["label"])
                if e.get("box_1080") and name not in GENERIC:  # (a piece with no job named says nothing about layout)
                    out.append((game, f, name, e["box_1080"]))
    return out


def priors(items):
    """per piece: stills, games, the box made from the MEDIAN CENTRE and the MEDIAN SIZE (so they agree), and the
    inter-quartile spread of its centre (1080p); one sample per piece per still — the largest — so a still that repeats
    a label (DBFZ's three P1 bars) does not outvote the other games"""
    one = {}
    for game, still, name, box in items:
        area = (box[2] - box[0]) * (box[3] - box[1])
        k = (game, still, name)
        if k not in one or area > one[k][1]:
            one[k] = (box, area)
    by = {}
    for (game, still, name), (box, _a) in one.items():
        by.setdefault(name, []).append((game, still, box))
    out = {}
    for name, rows in sorted(by.items()):
        b = np.array([r[2] for r in rows], dtype=float)
        cx, cy = (b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2
        w_, h_ = float(np.median(b[:, 2] - b[:, 0])), float(np.median(b[:, 3] - b[:, 1]))
        mx, my = float(np.median(cx)), float(np.median(cy))
        out[name] = {"stills": len({(g, s) for g, s, _ in rows}), "games": len({g for g, _s, _b in rows}),
                     "box_1080": [int(round(mx - w_ / 2)), int(round(my - h_ / 2)), int(round(mx + w_ / 2)), int(round(my + h_ / 2))],
                     "size_1080": [int(round(w_)), int(round(h_))],
                     "centre_spread": [[int(np.percentile(cx, 25)), int(np.percentile(cx, 75))], [int(np.percentile(cy, 25)), int(np.percentile(cy, 75))]]}
    return out


def cmd_prior(a):
    def emit(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0 if status == "pass" else 1

    a.refs = a.refs or os.path.join(a.ui, "refs")  # (the active game's folders: the CLI passes its --ui)
    a.out = a.out or os.path.join(a.ui, "priors")
    if getattr(a, "draft", None):
        if not a.identity:
            return emit("fail", "prior --draft needs --identity <name>", f"lune run kit ui read prior {a.genre} --draft <Screen> --identity <id>")
        if os.path.exists(os.path.join(a.ui, f"{a.draft}.json")):
            return emit("fail", f"prior: {a.draft}.json exists; a draft never overwrites a screen", "pick a new --draft name")
    items = collect(a.refs, a.genre)
    if not items:
        return emit("fail", f"prior: no read references of genre '{a.genre}' under {a.refs}",
                    "read some first: lune run kit ui read <still> (the genre is decided from the frame)")
    p = priors(items)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"{a.genre}.json")
    games = sorted({g for g, *_ in items})
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "genre": a.genre, "games": games, "stills": len({(g, s) for g, s, *_ in items}), "pieces": p,
                   "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh, indent=1)
    if getattr(a, "draft", None):  # a STARTING screen laid out by the genre's measured layout
        import importlib.util
        dpath = os.path.join(a.ui, f"{a.draft}.json")
        spec_ = importlib.util.spec_from_file_location("kit_ui_read", os.path.join(os.path.dirname(os.path.abspath(__file__)), "read.py"))
        rd = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(rd)
        keep = [(n, v) for n, v in p.items() if v["games"] >= min(2, len({g for g, *_ in items})) and n != "found"]
        els = [{"label": n, "looks_like": "digits" if re.search(r"timer|counter|count|score", n) else "panel",
                "box_1080": v["box_1080"], "size_1080": v["size_1080"]} for n, v in keep]
        with open(dpath, "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump(rd.draft_spec(a.draft, a.identity, els, f"the {a.genre} prior ({len(games)} games)"), fh, indent=1)
    common = sorted(p.items(), key=lambda kv: (-kv[1]["games"], -kv[1]["stills"]))[:5]
    said = "; ".join(f"{n} in {v['games']} game(s) at {v['box_1080']}" for n, v in common)
    return emit("pass", f"prior: {a.genre} from {len(games)} game(s) ({', '.join(games)}): {said}",
                f"start a {a.genre} screen from {path} (each piece's median box at 1080p)", prior=path)
