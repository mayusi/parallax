"""parts_ui.py - the UI lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A UI part is a COMPONENT (a bar, a button, a gauge, a counter, a plate...)
inside a game's identity. P0 files, each card with its kinds:
  - every library screen (library/ui/<identity>/screens/<Screen>/: manifest.json + screen.json): the whole screen
    (the owner's verdict on it lands in full), each component of its spec (the node's type, place, size, anchor and
    motion are the MECHANICS) and each part record (the art crop and the route that made it);
  - the look - the identity, the art itself, fonts, palette - stays hidden: inside one game the identity is shared by
    design, across games it is look reuse and needs the owner's word (look-allow).
`today_lib` is today's library search (kit/ui/vault.py cmd_find), ported as it is: the baseline P4 must beat.
"""

import glob
import json
import os
import re

LANE = "ui"
TYPES = {"bar": "bar", "button": "button", "imagebutton": "button", "stat": "counter", "number": "counter",
         "counter": "counter", "label": "label", "panel": "panel", "plate": "panel", "scroll": "list",
         "keyhint": "keyhint", "divider": "ornament", "path": "ornament", "vignette": "overlay", "input": "input",
         "image": None, "texture": None}
ROUTES = {"render": "route_render", "ink": "route_ink", "smear": "route_ink", "trace": "route_trace",
          "letter": "route_letter", "lettering": "route_letter"}
SCREENS = {"hud": "hud", "menu": "menu"}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def manifests(root):
    return sorted(glob.glob(os.path.join(root, "library", "ui", "*", "screens", "*", "manifest.json")))


def sources(root):
    return [os.path.join(root, "library", "ui", "*", "screens", "*", "manifest.json"),
            os.path.join(root, "library", "ui", "*", "screens", "*", "screen.json"),
            os.path.join(root, "assets", "ui", "directions", "*.json")]


def homes(root):
    return [os.path.join(root, "assets", "ui", "directions")]


def home(root, piece):
    return os.path.join(root, "assets", "ui", "directions")


def _nodes(node, path=""):
    """every node of a screen spec with its dotted path (Hud.Vitals.Health)"""
    if not isinstance(node, dict):
        return
    name = str(node.get("name") or node.get("type") or "?")
    here = f"{path}.{name}" if path else name
    yield here, node
    for c in node.get("children") or []:
        yield from _nodes(c, here)


def _motion(node):
    m = node.get("motion")
    if not isinstance(m, dict):
        return None
    return ", ".join(f"{k} {v.get('type') if isinstance(v, dict) else v}" for k, v in m.items())[:60]


def collect(root):
    pieces, docs = [], []
    for mp in manifests(root):
        m = _load(mp)
        if not isinstance(m, dict):
            continue
        folder = os.path.dirname(mp)
        screen = str(m.get("screen") or os.path.basename(folder))
        identity = str(m.get("identity") or "")
        skind = str(m.get("kind") or "")
        spec = _load(os.path.join(folder, "screen.json")) or {}
        nodes = list(_nodes(spec.get("root"))) if isinstance(spec, dict) else []
        pieces.append({"name": screen, "identity": identity, "kind": skind})
        sk = {SCREENS[skind]: 1.0} if skind in SCREENS else {}
        names = ", ".join(f"{p.split('.')[-1]} ({n.get('type')})" for p, n in nodes[:40])
        docs.append({"id": f"ui/screen/{screen}", "type": "screen", "piece": screen, "whole": True,
                     "title": f"{screen} ({skind}, {identity}): {str(m.get('focus') or '')[:70]}",
                     "text": f"{m.get('focus') or ''} {m.get('hero') or ''} Components: {names}",
                     "src": _rel(root, folder), "kinds": sk, "style": identity,
                     "mech": {"kind": skind, "components": len(nodes), "quality": m.get("quality")},
                     "look": {"identity": identity}})
        for path, n in nodes:
            typ = str(n.get("type") or "")
            kind = TYPES.get(typ)
            if typ in ("panel", "image") and not n.get("children") and not n.get("motion"):
                continue  # (a bare picture or a plain container: its art is a part record below)
            kinds = dict(sk)
            if kind:
                kinds[kind] = 1.0
            label = n.get("text") if isinstance(n.get("text"), str) else ""
            docs.append({"id": f"ui/node/{screen}/{path}", "type": "component", "piece": screen,
                         "title": f"{screen}: {path} ({typ})",
                         "text": f"{typ} {re.sub(r'[._]', ' ', path)} {label}".strip(),
                         "src": f"{_rel(root, folder)}/screen.json", "kinds": kinds, "style": identity,
                         "mech": {k: n[k] for k in ("pos", "size", "anchor", "fit") if k in n} |
                                 ({"motion": _motion(n)} if _motion(n) else {}),
                         "look": {"identity": identity, "image": n.get("image")} if n.get("image") else
                                 {"identity": identity}})
        for p in m.get("parts") or []:
            if not isinstance(p, dict) or not p.get("part"):
                continue
            source = str(p.get("source") or "")
            route = source.split(":", 1)[0].strip().lower()
            kinds = dict(sk)
            if route in ROUTES:
                kinds[ROUTES[route]] = 1.0
            docs.append({"id": f"ui/part/{screen}/{p['part']}", "type": "part", "piece": screen,
                         "title": f"{screen}: {p['part']} ({p.get('kind', '')}, {p.get('piece', '')})",
                         "text": f"{re.sub(r'[._]', ' ', p['part'])} {p.get('piece', '')} {p.get('kind', '')} "
                                 f"{source[:160]}",
                         "src": f"{_rel(root, folder)}/manifest.json", "kinds": kinds, "style": identity,
                         "media": [f"{_rel(root, folder)}/{p.get('file', '')}"],
                         "mech": {"kind": p.get("kind"), "route": route or None},
                         "look": {"identity": identity, "art": p.get("file")}})
    return {"pieces": pieces, "docs": docs}


def today_lib(root, words, k):
    """today's library search, as kit/ui/vault.py cmd_find scores it (a word in the part or piece 2, elsewhere 1)"""
    ws = [w for w in re.split(r"[\s,]+", (words or "").lower()) if w]
    hits = []
    for mp in glob.glob(os.path.join(root, "library", "ui", "*", "screens", "*", "manifest.json")):
        m = _load(mp) or {}
        for p in m.get("parts") or []:
            if not isinstance(p, dict) or "part" not in p or "piece" not in p:
                continue
            hay = f"{m.get('screen')} {p['part']} {p['piece']} {p.get('source', '')}".lower()
            sc = sum(2 if w in p["part"].lower() or w in p["piece"].lower() else (1 if w in hay else 0) for w in ws)
            if sc:
                hits.append((sc, m.get("screen"), p["part"]))
    hits.sort(key=lambda h: -h[0])
    return [f"ui/part/{s}/{part}" for _sc, s, part in hits[:k]]


def _direction(root, piece):
    key = re.sub(r"[^a-z0-9]", "", piece.lower())
    for p in sorted(glob.glob(os.path.join(root, "assets", "ui", "directions", "*.json")) +
                    glob.glob(os.path.join(root, "games", "*", "assets", "ui", "directions", "*.json"))):
        if key and key in re.sub(r"[^a-z0-9]", "", os.path.basename(p).lower()):
            return _load(p)
    return None


def brief(root, piece):
    d = _direction(root, piece)
    if isinstance(d, dict):
        ctx = d.get("context") if isinstance(d.get("context"), dict) else {}
        return f"{piece}: {d.get('ask', '')}. {ctx.get('pitch', '')}"
    return None
