"""parts_code.py - the code lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A code part is a MODULE by kind (validation, rate limit, the skeleton, saved
data, remotes, combat, a runtime ...) and each function it exports. P0 files, each card with its kinds:
  - every runtime module of the kit (src/kit/**) and of each game (games/*/src/**, not the synced games/*/src/kit/):
    its header comment (what it does, its API) and its exported functions with the comment above each;
  - the system template's files (kit/templates/system/): recipes for a new system.
Code has no look: everything is mechanics.
"""

import glob
import os
import re

LANE = "code"
FN = re.compile(r"^function\s+([\w.:]+)\s*\(([^)]*)\)")
SKIP = re.compile(r"[\\/](kit|Packages|DevPackages|node_modules)[\\/]")


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def module_files(root):
    files = glob.glob(os.path.join(root, "src", "**", "*.luau"), recursive=True)
    for g in glob.glob(os.path.join(root, "games", "*", "src")):
        files += [p for p in glob.glob(os.path.join(g, "**", "*.luau"), recursive=True)
                  if not SKIP.search(os.sep + os.path.relpath(p, g))]  # (games/*/src/kit/ = synced copies)
    return sorted(p for p in files if not p.endswith(".spec.luau"))


def sources(root):
    return [os.path.join(root, "src", "**", "*.luau"), os.path.join(root, "games", "*", "src", "**", "*.luau"),
            os.path.join(root, "kit", "templates", "system", "*")]


def _header(lines):
    out = []
    for line in lines[:40]:
        s = line.strip()
        if s.startswith("--!"):
            continue
        if s.startswith("--"):
            out.append(s.lstrip("-").strip())
        elif s and out:
            break
    return " ".join(out)


def collect(root):
    pieces, docs = [], []
    for p in module_files(root):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        rel = _rel(root, p)
        name = os.path.splitext(os.path.basename(p))[0]
        if name == "init":
            name = os.path.basename(os.path.dirname(p))
        head = _header(lines)
        fns = []
        for i, line in enumerate(lines):
            m = FN.match(line)
            if not m or "." not in m.group(1) and ":" not in m.group(1):
                continue
            above = []
            j = i - 1
            while j >= 0 and lines[j].strip().startswith("--") and len(above) < 6:
                above.insert(0, lines[j].strip().lstrip("-").strip())
                j -= 1
            fns.append((i + 1, m.group(1), m.group(2), " ".join(above)))
        piece = f"{rel.split('/')[1]}:{name}" if rel.startswith("games/") else name
        pieces.append({"name": piece, "functions": len(fns), "lines": len(lines)})
        layer = ("service" if "/server/" in rel or rel.endswith(".server.luau") else
                 "controller" if "/client/" in rel or rel.endswith(".client.luau") else "")
        docs.append({"id": f"code/module/{rel}", "type": "module", "piece": piece, "whole": True,
                     "title": f"{piece}: {head[:90]}", "text": f"{head} Exports: {', '.join(f[1] for f in fns[:30])}",
                     "src": rel, "kinds": {layer: 1.0} if layer else {},
                     "mech": {"functions": len(fns), "lines": len(lines)}})
        for ln, fname, args, note in fns:
            docs.append({"id": f"code/fn/{rel}/{fname}", "type": "part", "piece": piece,
                         "title": f"{fname}({args.strip()[:50]})", "text": f"{fname} {args} {note}",
                         "src": f"{rel}:{ln}", "kinds": {layer: 1.0} if layer else {}})
    for p in sorted(glob.glob(os.path.join(root, "kit", "templates", "system", "*"))):
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        rel = _rel(root, p)
        docs.append({"id": f"code/recipe/{os.path.basename(p)}", "type": "recipe", "piece": "template:system",
                     "title": f"system template: {os.path.basename(p)}", "text": _header(lines) or os.path.basename(p),
                     "src": rel})
    return {"pieces": pieces, "docs": docs}
