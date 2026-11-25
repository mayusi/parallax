"""parts_qa.py - the QA lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A QA part is a TEST by kind (a spec, a fuzz run, a mutation case, a playtest
check, a gate's selftest fixture, a regression, a Python unit test) and a BUG by pattern. P0 files, each card with its
kinds:
  - every frktest spec's tests (kit/test/spec, tests/spec, games/*/tests): one card per test("...");
  - every playtest script's checks (tests/playtest, games/*/tests/playtest);
  - every regression (games/*/tests/regressions.json): the bug, the spec that now catches it, the mutation it was;
  - every gate's selftest fixture (kit/selftest/<lane>/): what that gate must catch;
  - every Python test file's purpose (its docstring) and the fuzz / mutate runners (recipes).
QA has no look: everything is mechanics.
"""

import glob
import json
import os
import re

LANE = "qa"
TEST = re.compile(r"""\btest\(\s*["'](.+?)["']\s*,""")
CHECK = re.compile(r"""\bt\.check\(\s*["'](.+?)["']""")


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _specs(root):
    pats = [os.path.join(root, "kit", "test", "spec", "*.spec.luau"), os.path.join(root, "tests", "spec", "*.spec.luau"),
            os.path.join(root, "games", "*", "tests", "*.spec.luau"), os.path.join(root, "games", "*", "tests", "**",
                                                                                   "*.spec.luau")]
    return sorted({p for pat in pats for p in glob.glob(pat, recursive=True)})


def _playtests(root):
    pats = [os.path.join(root, "tests", "playtest", "*.luau"), os.path.join(root, "games", "*", "tests", "playtest",
                                                                           "*.luau")]
    return sorted({p for pat in pats for p in glob.glob(pat)})


def sources(root):
    return [os.path.join(root, "kit", "test", "spec", "*.spec.luau"), os.path.join(root, "tests", "**", "*.luau"),
            os.path.join(root, "games", "*", "tests", "**", "*"), os.path.join(root, "kit", "selftest", "*", "*"),
            os.path.join(root, "kit", "test", "python", "test_*.py"), os.path.join(root, "kit", "test", "*.luau")]


def _doc(text):
    m = re.match(r'\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', text, re.S)
    if m:
        return " ".join(m.group(1).split())
    head = []
    for line in text.splitlines()[:30]:
        s = line.strip()
        if s.startswith("--") and not s.startswith("--!"):
            head.append(s.lstrip("-").strip())
        elif s and head:
            break
    return " ".join(head)


def collect(root):
    pieces, docs = [], []
    for p in _specs(root):
        text, rel = _read(p), _rel(root, p)
        name = os.path.basename(p)[:-len(".spec.luau")]
        tests = TEST.findall(text)
        pieces.append({"name": name, "tests": len(tests)})
        for i, t in enumerate(tests):
            docs.append({"id": f"qa/spec/{rel}/{i}", "type": "test", "piece": f"spec:{name}",
                         "title": f"{name}: {t[:100]}", "text": f"{name} spec: {t}", "src": rel,
                         "kinds": {"t_spec": 1.0}})
    for p in _playtests(root):
        text, rel = _read(p), _rel(root, p)
        name = os.path.splitext(os.path.basename(p))[0]
        checks = CHECK.findall(text)
        docs.append({"id": f"qa/playtest/{rel}", "type": "test", "piece": f"playtest:{name}",
                     "title": f"playtest {name}: {_doc(text)[:80]}",
                     "text": f"{_doc(text)} Checks: {'; '.join(checks[:20])}", "src": rel,
                     "kinds": {"t_playtest": 1.0}, "mech": {"checks": len(checks)}})
    for p in sorted(glob.glob(os.path.join(root, "games", "*", "tests", "regressions.json"))):
        try:
            data = json.loads(_read(p))
        except ValueError:
            continue
        rows = data if isinstance(data, list) else data.get("cases") or data.get("regressions") or []
        game = p.replace(os.sep, "/").split("/")[-3]
        for r in rows:
            if not isinstance(r, dict) or not r.get("id"):
                continue
            docs.append({"id": f"qa/bug/{game}/{r['id']}", "type": "bug", "piece": f"bug:{game}",
                         "title": f"{game} bug {r['id']}: {r.get('module', '')}",
                         "text": f"found by {r.get('found_by', '')}; caught by spec {r.get('spec', '')}; in "
                                 f"{r.get('module', '')} line {r.get('line', '')}: {r.get('from', '')} -> {r.get('to', '')}",
                         "src": _rel(root, p), "kinds": {"t_regression": 1.0}})
    for p in sorted(glob.glob(os.path.join(root, "kit", "selftest", "*", "*"))):
        if not os.path.isfile(p) or p.endswith(".pyc"):
            continue
        lane = p.replace(os.sep, "/").split("/")[-2]
        name = os.path.basename(p)
        words = re.sub(r"[_.-]+", " ", os.path.splitext(name)[0])
        docs.append({"id": f"qa/fixture/{lane}/{name}", "type": "fixture", "piece": f"selftest:{lane}",
                     "title": f"{lane} gate fixture: {words}", "text": f"{lane} gate must catch: {words}. {_doc(_read(p))[:200]}",
                     "src": _rel(root, p), "kinds": {"t_selftest": 1.0}})
    for p in sorted(glob.glob(os.path.join(root, "kit", "test", "python", "test_*.py"))):
        name = os.path.basename(p)[5:-3]
        docs.append({"id": f"qa/python/{name}", "type": "test", "piece": f"python:{name}",
                     "title": f"python tests {name}: {_doc(_read(p))[:80]}", "text": _doc(_read(p))[:600],
                     "src": _rel(root, p), "kinds": {"t_python": 1.0}})
    for p in (os.path.join(root, "kit", "test", "fuzz.luau"), os.path.join(root, "kit", "test", "mutate.luau")):
        if os.path.isfile(p):
            kind = "t_fuzz" if "fuzz" in p else "t_mutate"
            docs.append({"id": f"qa/recipe/{os.path.basename(p)}", "type": "recipe", "piece": "runner",
                         "title": f"{os.path.basename(p)}: {_doc(_read(p))[:80]}", "text": _doc(_read(p))[:600],
                         "src": _rel(root, p), "kinds": {kind: 1.0}})
    return {"pieces": pieces, "docs": docs}
