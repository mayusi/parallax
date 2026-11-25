"""docs.py — the Roblox Engine API reference, searched locally (2026-11-08, sprint 5: proposal 11 of
board/plans/archive/2026-11-08-pipeline-rag-learning-research.md - the code lane had no API docs at all).

The source is the reference Roblox Studio ships on this machine (<Studio>/content/api_docs/en-us.json: every class
member, global and enum item with its description) - nothing is downloaded, nothing of Roblox's text is copied into
the repo. The declared type of a member comes from the kit's own type file (kit/types/globalTypes.d.luau, MIT, the
types gate's). An exact name ("Players.PlayerAdded", "task.wait") comes first; words rank names above descriptions.

  python kit/tools/docs.py <words | Class.member> [--k 6] [--source <en-us.json>] [--types <file.d.luau>]
Prints one JSON line ({"status", "summary", "next_action", "lines": [...], "rows": [...]})."""

import glob
import html
import json
import math
import os
import re
import sys

TYPES = os.path.join("kit", "types", "globalTypes.d.luau")
ENUM_DAMP = 0.7


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def find_source():
    """the newest Studio's reference: KIT_API_DOCS, else %LOCALAPPDATA%/Roblox/Versions/*/content/api_docs/en-us.json"""
    env = os.environ.get("KIT_API_DOCS")
    if env and os.path.isfile(env):
        return env
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    found = glob.glob(os.path.join(base, "Roblox", "Versions", "*", "content", "api_docs", "en-us.json"))
    return max(found, key=os.path.getmtime) if found else None


def words(text):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "").replace("_", " ").replace(".", " ")
    return [w for w in re.findall(r"[a-z][a-z0-9]+", spaced.lower()) if len(w) >= 2]


def entries(source):
    """{name: (kind, documentation)} - class members ("Players.PlayerAdded"), globals ("task.wait"), enum items; an
    event's own methods (".Connect") and parameter / return notes are left out"""
    with open(source, encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for key, v in data.items():
        m = re.match(r"^@roblox/(global|globaltype|enum)/(.+)$", key)
        if not m or "/" in m.group(2) or not isinstance(v, dict):
            continue
        name = m.group(2)
        if m.group(1) == "globaltype" and name.count(".") > 1:
            continue
        doc = " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(v.get("documentation") or ""))).split())
        kind = {"global": "global", "globaltype": "member" if "." in name else "class", "enum": "enum"}[m.group(1)]
        out[name] = (kind, doc)
    return out


PARENTS = {}  # "Workspace" -> "WorldRoot": filled by type_lines (an inherited member is documented on its parent)


def type_lines(path):
    """{"Class.member": its declaration line} from the type file's `declare extern type X extends Y with ... end`
    blocks (and each type's parent into PARENTS)"""
    out = {}
    if not os.path.isfile(path):
        return out
    cls = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^declare (?:class|extern type) (\w+)(?:\s+extends\s+(\w+))?", line)  # (luau-lsp 1.70 syntax)
            if m:
                cls = m.group(1)
                if m.group(2):
                    PARENTS[cls] = m.group(2)
                continue
            if line.startswith("end"):
                cls = None
                continue
            if cls:
                s = line.strip()
                mm = re.match(r"^(?:function\s+)?(\w+)\s*[:(]", s)
                if mm and f"{cls}.{mm.group(1)}" not in out:
                    out[f"{cls}.{mm.group(1)}"] = s[:160]
    return out


DEPRECATED_DAMP = 0.3  # a deprecated member is never the answer to look up first
# the engine's own words for what a session asks in plain words (a small, curated map - never a guess per query)
SYNONYMS = {"join": ["added", "enter"], "joined": ["added", "enter"], "joins": ["added", "enter"],
            "leave": ["removing"], "leaves": ["removing"],  # (not "left": the left arm)
            "die": ["died"], "dies": ["died"], "death": ["died"], "spawn": ["characteradded", "respawn"],
            "spawned": ["characteradded", "respawn"], "save": ["setasync", "updateasync"]}


def exact_name(index, query):
    """an exact name, its case aside - or the same member on a parent type (Workspace.Raycast is WorldRoot's)"""
    names = {n.lower(): n for n in index}
    q = query.strip()
    if q.lower() in names:
        return names[q.lower()], None
    m = re.match(r"^(\w+)\.(\w+)$", q)
    cls = m and next((c for c in PARENTS if c.lower() == m.group(1).lower()), None)
    seen = set()
    while cls and cls not in seen:
        seen.add(cls)
        cls = PARENTS.get(cls)
        if cls and f"{cls}.{m.group(2)}".lower() in names:
            return names[f"{cls}.{m.group(2)}".lower()], cls
    return None, None


def search(index, query, k=6):
    """an exact name first (or the member on a parent type), then by words: a name word counts 3 (a word inside a
    joined name too - "datastore" in DataStoreService), a description word 1, rarer words more; an enum item and a
    deprecated member count less"""
    qw = words(query)
    qw += [s for w in qw for s in SYNONYMS.get(w, []) if s not in qw]
    rows = []
    hit, _via = exact_name(index, query)
    if hit:
        rows.append((1e9, hit))
    if qw:
        df = {}
        for name, (_kind, doc) in index.items():
            for w in set(words(name)) | set(words(doc)):
                df[w] = df.get(w, 0) + 1
        n = len(index)
        idf = {w: math.log(1 + n / (1 + df.get(w, 0))) for w in qw}
        for name, (_kind, doc) in index.items():
            if name == hit:
                continue
            nw, dw = set(words(name)), set(words(doc))
            segs = name.lower().split(".")
            s = 0.0
            for w in qw:
                if w in nw or any(seg.startswith(w) for seg in segs if len(w) >= 5):
                    s += idf[w] * 3  # a name word, or a long word a name segment starts with ("datastore")
                elif len(w) >= 5 and any(w in seg for seg in segs):
                    s += idf[w] * 2  # a long word inside a joined name
                elif w in dw:
                    s += idf[w]
            if index[name][0] == "enum":
                s *= ENUM_DAMP  # an enum item matches plain words often; a member or a global is what is looked up
            if doc.lower().startswith("deprecated"):
                s *= DEPRECATED_DAMP
            if s > 0:
                rows.append((s, name))
    rows.sort(key=lambda r: (-r[0], len(r[1])))
    return [name for _s, name in rows[:k]]


def _opt(argv, key, default=None):
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


def main(argv):
    flags = {"--k", "--source", "--types"}
    query = " ".join(a for i, a in enumerate(argv) if a not in flags and (i == 0 or argv[i - 1] not in flags))
    if not query.strip():
        return emit("fail", "docs: which words or Class.member?", "lune run kit docs \"raycast exclude list\"")
    source = _opt(argv, "--source") or find_source()
    if not source or not os.path.isfile(source):
        return emit("fail", "docs: no API reference on this machine (Roblox Studio ships it: content/api_docs/en-us.json)",
                    "install / open Roblox Studio once, or point KIT_API_DOCS at an en-us.json")
    index = entries(source)
    types = type_lines(_opt(argv, "--types") or TYPES)
    names = search(index, query, int(_opt(argv, "--k", "6")))
    rows, lines = [], []
    for name in names:
        kind, doc = index[name]
        t = types.get(name)
        rows.append({"name": name, "kind": kind, "doc": doc[:400], "type": t})
        lines.append(f"{name} ({kind}): {doc[:220]}{'...' if len(doc) > 220 else ''}" + (f"  [{t}]" if t else ""))
    return emit("pass", f"docs \"{query}\": {len(rows)} of {len(index)} API entries (Studio's own reference, local)",
                "use the member as documented; a name the type gate does not know is not in the engine"
                if rows else "try other words, or Class.member", lines=lines, rows=rows, source=source)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
