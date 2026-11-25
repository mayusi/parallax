"""vault_migrate.py — fill the knowledge vault (kit/knowledge/vault) from everything the kit already recorded.

Idempotent: a note is written once (deterministic file names; an existing note with the same body is left alone).
Run from the project root:  python kit/scripts/vault_migrate.py [--dry-run | --check]
(--check: a dry run that exits 1 when the vault is behind - anything it would file - for CI; every run prints `pending`,
the same count, which verify's "vault in step" and upgrade read)

Sources (all read-only):
  kit/lessons/<area>.md                      one note per "- date (by, project): text" line
  kit/lessons/anim_r6_translation.md         a reference page (anim/refs)
  assets/ui/<Screen>.judge.json  .owner       UI verdicts (0-100 -> /10)
  library/vfx/verdicts.json                   VFX verdicts (0-100 or null -> /10 or no number)
  assets/animations/verdicts.json             anim verdicts (word -> inferred score) + the pairwise page's absolute scores
  assets/sounds/<name>.verdict.json           booth scores (1-10)
  kit/anchors/anchors.json (+ private/)       3D grades (0-100 -> /10)
  the owner's words recorded in notes and on the board (curated below; every row says where from)
Plus the GRAVEYARD and GOLDEN seeds per department (routes the record rejected / loved, with the feature that decided it).
"""

import glob
import json
import os
import re
import sys
import time as _time

# KIT_VAULT_ROOT: another vault folder (the sync test fills a COPY and proves the second pass writes nothing)
ROOT = os.environ.get("KIT_VAULT_ROOT") or "kit/knowledge/vault"
CHECK = "--check" in sys.argv
DRY = "--dry-run" in sys.argv or CHECK
WORD_SCORE = {"loved": 9.0, "good": 7.0, "ok": 5.0, "bad": 2.0, "horrible": 1.0}
GRAVE_HEADER = (
    "# Graveyard — routes that failed; do not retry without the owner's words\n\n"
    "| tried | when | result | the owner's words | do not retry because | link |\n|---|---|---|---|---|---|\n"
)
GOLD_HEADER = (
    "# Golden set — what the owner loved (≥ 7) and what decided it\n\n"
    "| piece | score | when | the owner's words | the measurable feature that decided it | link |\n|---|---|---|---|---|---|\n"
)
counts = {"lessons": 0, "verdicts": 0, "rows": 0, "skipped": 0, "refs": 0}


def slug(text):
    s = re.sub(r"[^0-9a-z]+", "-", text.lower()).strip("-")
    return (s or "note")[:48]


def scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if re.fullmatch(r"[\w\-.]+", s):
        return s
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


ORDER = ["kind", "area", "name", "score", "date", "build", "by", "source", "quoted_from", "vs", "tags", "links"]


def frontmatter(front):
    lines = ["---"]
    done = set()
    for k in ORDER + sorted(k for k in front if k not in ORDER):
        if k in done or front.get(k) is None:
            continue
        v = front[k]
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(scalar(x) for x in v)}]")
        else:
            lines.append(f"{k}: {scalar(v)}")
        done.add(k)
    lines.append("---")
    return "\n".join(lines)


def write(path, front, body):
    text = frontmatter(front) + "\n\n" + body.strip() + "\n"
    if os.path.isfile(path):
        with open(path, "rb") as f:
            # line-ending-blind: a fresh git worktree (core.autocrlf) holds the same note with CRLF
            if f.read().replace(b"\r\n", b"\n") == text.encode("utf-8"):
                counts["skipped"] += 1
                return False
    if not DRY:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return True


def row(dept, file, header, cells):
    path = f"{ROOT}/{dept}/{file}"
    safe = [str(c).replace("|", "/").replace("\n", " ") for c in cells]
    line = "| " + " | ".join(safe) + " |\n"
    text = open(path, encoding="utf-8").read() if os.path.isfile(path) else header
    if line in text:
        counts["skipped"] += 1
        return
    if not text.endswith("\n"):
        text += "\n"
    if not DRY:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + line)
    counts["rows"] += 1


def norm(text):
    return " ".join(str(text).split())


def split_note(raw):
    """(frontmatter text, body) of a note, CRLF or LF; ("", raw) when it has none."""
    raw = raw.replace("\r\n", "\n")
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end >= 0:
            return raw[4:end], raw[end + 5:]
    return "", raw


def field(front_text, key):
    """One scalar property, however it was written: the kit's own quoting or Obsidian's property editor."""
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", front_text, re.M)
    if not m:
        return None
    v = m.group(1)
    if len(v) >= 2 and v[0] == v[-1] == '"':
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    elif len(v) >= 2 and v[0] == v[-1] == "'":
        v = v[1:-1].replace("''", "'")
    return v


# every verdict note of a department, read once: (name, date, body words, path). A note is recognised by WHAT it
# says, never by its file name or the exact bytes of its frontmatter - the owner may rename it, tag it or retype its
# properties in Obsidian (which rewrites the whole block) or add a remark under it, and the sync must not file it twice
_verdict_notes = {}


def verdict_notes(dept):
    if dept not in _verdict_notes:
        found = []
        for p in glob.glob(f"{ROOT}/{dept}/verdicts/*.md"):
            front, body = split_note(open(p, encoding="utf-8").read())
            found.append((field(front, "name"), (field(front, "date") or "")[:10], norm(body), p))
        _verdict_notes[dept] = found
    return _verdict_notes[dept]


def verdict(dept, name, score, date, words, by="owner", source="owner", quoted_from=None, build=None, tags=None, feature=None, extra=None):
    date = (date or "")[:10] or "undated"
    front = {
        "kind": "verdict",
        "area": dept,
        "name": name,
        "score": None if score is None else round(float(score), 1),
        "date": date,
        "build": build,
        "by": by,
        "source": source,
        "quoted_from": quoted_from,
        "tags": tags or None,
        "links": [f"[[{dept}/index]]", f"[[{dept}/golden]]", f"[[{dept}/graveyard]]"],
    }
    if extra:
        front.update(extra)
    body = words.strip() or "(a score only — the owner gave no words)"
    if feature:
        body += f"\n\nWhat decided it: {feature}"
    want = norm(body)
    for n_name, n_date, n_body, n_path in verdict_notes(dept):
        if n_name == str(name) and n_date == date and want in n_body:
            counts["skipped"] += 1
            return n_path
    path = f"{ROOT}/{dept}/verdicts/{slug(name)}--{date}.md"
    n = 2
    while os.path.isfile(path):
        path = f"{ROOT}/{dept}/verdicts/{slug(name)}--{date}-{n}.md"
        n += 1
    front["time"] = int(_time.time())  # orders verdicts within one day (a file time moves on edits and checkouts)
    if write(path, front, body):
        verdict_notes(dept).append((str(name), date, want, path))
        counts["verdicts"] += 1
        link = f"[[{dept}/verdicts/{os.path.basename(path)[:-3]}]]"
        if score is not None and score >= 7:
            row(dept, "golden.md", GOLD_HEADER, [name, round(float(score), 1), date, words, feature or "", link])
        elif score is not None and score <= 3:
            row(dept, "graveyard.md", GRAVE_HEADER, [name, date, f"rejected ({round(float(score), 1)}/10)", words, feature or "the owner's words above", link])
    return path


# ------------------------------------------------------------------ lessons
AREAS = ["3d", "vfx", "sfx", "ui", "world", "anim", "code", "qa", "kit"]
LESSON = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \(([^,()]+), ([^)]+)\): (.*)$")


def lessons():
    for area in AREAS:
        path = f"kit/lessons/{area}.md"
        if not os.path.isfile(path):
            continue
        seen = {}
        # a lesson `kit lesson` already wrote to the vault (its own frontmatter, its own slug) is the same lesson:
        # match on the body, never on the file name
        # (a remark the owner typed under a lesson in Obsidian keeps it the same lesson: the text is CONTAINED)
        bodies = []
        ldir = f"{ROOT}/{area}/lessons"
        if os.path.isdir(ldir):
            for fn in os.listdir(ldir):
                if fn.endswith(".md"):
                    bodies.append(norm(split_note(open(os.path.join(ldir, fn), encoding="utf-8").read())[1]))
        for line in open(path, encoding="utf-8"):
            m = LESSON.match(line.rstrip("\n"))
            if not m:
                continue
            date, by, project, text = m.groups()
            if any(norm(text) in b for b in bodies):
                counts["skipped"] += 1
                continue
            base = f"{date}-{slug(text)}"
            n = seen.get(base, 0) + 1
            seen[base] = n
            name = base if n == 1 else f"{base}-{n}"
            front = {"kind": "lesson", "area": area, "date": date, "by": by, "project": project,
                     "source": f"kit/lessons/{area}.md", "links": [f"[[{area}/index]]"]}
            if write(f"{ROOT}/{area}/lessons/{name}.md", front, text):
                counts["lessons"] += 1
    spec = "kit/lessons/anim_r6_translation.md"
    if os.path.isfile(spec):
        body = open(spec, encoding="utf-8").read()
        front = {"kind": "reference", "area": "anim", "date": "2026-10-13", "source": spec,
                 "links": ["[[anim/index]]", "[[anim/graveyard]]"]}
        ref = f"{ROOT}/anim/refs/kimodo-to-r6-translation.md"
        # a page that still holds the whole source text is current: what the owner added to it in Obsidian (a remark,
        # a retyped property) is kept, never overwritten
        if os.path.isfile(ref) and norm(body) in norm(split_note(open(ref, encoding="utf-8").read())[1]):
            counts["skipped"] += 1
        elif write(ref, front, body):
            counts["refs"] += 1


# ------------------------------------------------------------------ the stores
def ui_judges():
    for p in sorted(glob.glob("assets/ui/*.judge.json")):
        d = json.load(open(p, encoding="utf-8"))
        o = d.get("owner")
        if not o or o.get("score") is None:
            continue
        screen = os.path.basename(p)[: -len(".judge.json")]
        verdict("ui", screen, float(o["score"]) / 10.0, str(o.get("when") or ""), o.get("words") or "",
                build=o.get("model_sha256") or d.get("model_sha256"), quoted_from=os.path.basename(p), source="owner")


def vfx_library():
    p = "library/vfx/verdicts.json"
    if not os.path.isfile(p):
        return
    for effect, entries in json.load(open(p, encoding="utf-8")).items():
        for e in entries:
            s = e.get("score")
            verdict("vfx", effect, None if s is None else float(s) / 10.0 if float(s) > 10 else float(s), e.get("date"),
                    e.get("words") or "", build=e.get("effect_sha"), quoted_from="library/vfx/verdicts.json")


def anim_store():
    p = "assets/animations/verdicts.json"
    if not os.path.isfile(p):
        return
    d = json.load(open(p, encoding="utf-8"))
    for name, entries in d.get("verdicts", {}).items():
        for e in entries:
            word = e.get("verdict")
            verdict("anim", name, WORD_SCORE.get(word), e.get("date"), e.get("note") or f"'{word}'",
                    source="inferred" if word in WORD_SCORE else "owner", quoted_from="assets/animations/verdicts.json",
                    tags=[word] if word else None, extra={"word": word})
    # the pairwise page's absolute scores (1 horrible .. 5 love) per clip + translator version, averaged
    agg = {}
    for a in d.get("absolute", []):
        key = (a.get("clip"), a.get("version"))
        agg.setdefault(key, []).append(float(a.get("score") or 0))
    for (clip, version), scores in sorted(agg.items()):
        mean = sum(scores) / len(scores)
        verdict("anim", f"{clip} / {version}", mean * 2.0, "2026-10-13",
                f"the owner's pairwise-page score on the Kimodo->R6 translator '{version}' for the '{clip}' test clip: mean {mean:.2f}/5 over {len(scores)} rating(s) (1 horrible .. 5 love)",
                source="owner", quoted_from="assets/animations/verdicts.json absolute", tags=["translator", "pairwise-page"])


def sounds():
    for p in sorted(glob.glob("assets/sounds/*.verdict.json")):
        d = json.load(open(p, encoding="utf-8"))
        name = d.get("name") or os.path.basename(p).split(".")[0]
        for h in d.get("history", []):
            if h.get("score") is None:
                continue
            verdict("sfx", name, float(h["score"]), str(h.get("date") or h.get("when") or h.get("at") or ""), h.get("words") or "",
                    quoted_from=os.path.basename(p), tags=["booth"] + (["blind"] if h.get("blind") else []))


def anchors():
    for p in ["kit/anchors/anchors.json", "kit/anchors/private/anchors.json"]:
        if not os.path.isfile(p):
            continue
        for a in json.load(open(p, encoding="utf-8")):
            if a.get("owner") is None:
                continue
            verdict("3d", a["asset"], float(a["owner"]) / 10.0, str(a.get("at") or "2026-10-05"), a.get("note") or "",
                    quoted_from=p, tags=["grade", "anchor"] + (["private"] if a.get("private") else []))


# ------------------------------------------------------------------ the owner's words from the memory notes / board
# (dept, name, score /10 or None, date, words, source, quoted_from, feature)
MEMORY = []


def memory():
    for dept, name, score, date, words, source, quoted, feature in MEMORY:
        verdict(dept, name, score, date, words, source=source, quoted_from=quoted, feature=feature)


# ------------------------------------------------------------------ graveyard ROUTES (not pieces) per department
GRAVE = {dept: [] for dept in ("3d", "vfx", "sfx", "ui", "world", "anim", "code", "qa", "kit")}


def graveyard():
    for dept, rows in GRAVE.items():
        for tried, when, result, words_, why, link in rows:
            row(dept, "graveyard.md", GRAVE_HEADER, [tried, when, result, words_, why, link])


# ------------------------------------------------------------------ GOLDEN seeds with the feature that decided it
GOLD = {dept: [] for dept in ("3d", "vfx", "sfx", "ui", "world", "anim", "code", "qa", "kit")}


def golden():
    for dept, rows in GOLD.items():
        for piece, score, when, words_, feature, link in rows:
            row(dept, "golden.md", GOLD_HEADER, [piece, "" if score is None else score, when, words_, feature, link])


# ------------------------------------------------------------------ the owner's inbox (written in Obsidian)
# kit/knowledge/vault/inbox.md: the owner types one line per verdict under "## New" —
#   - ui FieldHud 8 loved the dial
#   - asset "glock 17" 85 the slide finally reads as steel     (0-10 or 0-100; quotes for names with spaces)
# a sync files each line as a verdict note (+ its golden / graveyard row) and moves it under "## Filed" with a link.
INBOX = "inbox.md"
KIND_DEPT = {"asset": "3d", "model": "3d", "3d": "3d", "vfx": "vfx", "effect": "vfx", "ui": "ui", "screen": "ui",
             "sound": "sfx", "sfx": "sfx", "world": "world", "map": "world", "level": "world", "anim": "anim",
             "animation": "anim", "system": "code", "code": "code", "playtest": "qa", "qa": "qa", "kit": "kit"}
INBOX_LINE = re.compile(r'^-\s+(\w+)\s+(?:"([^"]+)"|(\S+))\s+(\d+(?:\.\d+)?)(?:/(?:10|100))?\s+(.+?)\s*$')
INBOX_HEADER = (
    "# Verdict inbox\n\n"
    "Write your verdicts here in Obsidian, one line each under **New**: `- <kind> <name> <score> <your words>`.\n"
    "Kinds: asset, vfx, ui, sound, world, anim, system, playtest, kit. Scores 0-10 or 0-100. Put quotes around a\n"
    "name with spaces. The next `lune run kit vault sync` (or `kit status`) files each line as a verdict note and\n"
    "moves it to **Filed** with a link. A line it cannot read stays under New with a note saying why.\n"
    "Three more kinds of line: `- rule <dept> <words>` (a standing order every session of that lane obeys),\n"
    "`- never <dept> <words>` (a graveyard row: a route never to try again), `- retire <words of a lesson>` (that\n"
    "lesson stops being shown; it must match exactly one lesson).\n\n"
)
# the owner's three steering lines (the plan's B2): a standing order, a graveyard route, a retired lesson
STEER_LINE = re.compile(r"^-\s+(rule|never)\s+(\S+)\s+(.+?)\s*$", re.I)
RETIRE_LINE = re.compile(r"^-\s+retire\s+(.+?)\s*$", re.I)
DEPTS = {"3d", "vfx", "sfx", "ui", "world", "anim", "code", "qa", "kit", "shared"}


def order_add(dept, words, today):
    """append one standing order to <dept>/orders.md (made on first use); the same words are never added twice"""
    path = f"{ROOT}/{dept}/orders.md"
    if os.path.isfile(path):
        text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    else:
        front = {"kind": "orders", "area": dept, "date": today, "links": [f"[[{dept}/index]]"]}
        text = (frontmatter(front) + f"\n\n# {dept} — standing orders\n\n"
                "The owner's standing orders for this lane: `kit start` prints them first and every session obeys "
                "them. Add one here in Obsidian (one `- ` line), or in inbox.md: `- rule " + dept + " <words>`. "
                "Strike one through (`~~...~~`) to withdraw it.\n\n")
    # the same order already listed (compared with the order lines only, never the page's header text)
    listed = {norm(re.sub(r"\s*\(the owner, [^)]*\)\s*$", "", line[2:])).lower()
              for line in text.splitlines() if line.startswith("- ")}
    if norm(words).lower() in listed:
        counts["skipped"] += 1
        return path
    if not DRY:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text.rstrip("\n") + f"\n- {words} (the owner, {today})\n")
    counts["orders"] = counts.get("orders", 0) + 1
    return path


def lesson_retire(words, today):
    """mark the ONE lesson whose text holds every word as superseded by the owner; (path, None) or (None, why)"""
    want = [w for w in norm(words).lower().split() if w]
    hits = []
    for p in glob.glob(f"{ROOT}/*/lessons/*.md"):
        front, body = split_note(open(p, encoding="utf-8").read())
        if field(front, "superseded_by"):
            continue
        hay = norm(body).lower()
        if all(w in hay for w in want):
            hits.append((p, front, body))
    if len(hits) != 1:
        return None, ("no lesson holds all those words" if not hits else f"{len(hits)} lessons match - add words")
    p, front, body = hits[0]
    if not DRY:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("---\n" + front.rstrip("\n") + f'\nsuperseded_by: "the owner (inbox.md, {today})"\n---\n' + body)
    counts["retired"] = counts.get("retired", 0) + 1
    return p, None


def inbox(today=None):
    path = os.path.join(ROOT, INBOX)
    if not os.path.isfile(path):
        if not DRY and os.path.isdir(ROOT):
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(INBOX_HEADER + "## New\n\n## Filed\n")
        return
    import time as _t
    today = today or _t.strftime("%Y-%m-%d")
    # the owner may be typing in it right now: with Obsidian open on this vault (it keeps .obsidian/workspace.json
    # fresh) and inbox.md saved in the last KIT_VAULT_INBOX_SETTLE seconds (20), leave it for the next sync so a
    # half-typed line is never filed
    settle = float(os.environ.get("KIT_VAULT_INBOX_SETTLE", "20"))
    ws = os.path.join(ROOT, ".obsidian", "workspace.json")
    now = _t.time()
    if (not DRY and settle > 0 and os.path.isfile(ws) and now - os.path.getmtime(ws) < 600
            and now - os.path.getmtime(path) < settle):
        counts["inbox_waiting"] = 1
        return
    text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    head, sep, rest = text.partition("## New")
    if not sep:
        return
    new_part, _, filed_part = rest.partition("## Filed")
    keep, filed = [], []
    for line in new_part.splitlines():
        if not line.strip().startswith("- "):
            continue
        clean = re.sub(r"\s+<- not filed:.*$", "", line.strip())
        steer, retire = STEER_LINE.match(clean), RETIRE_LINE.match(clean)
        if steer:
            kind, dept, words = steer.group(1).lower(), steer.group(2).lower(), steer.group(3)
            dept = KIND_DEPT.get(dept, dept)
            if dept not in DEPTS:
                keep.append(f"{clean}  <- not filed: unknown department (3d vfx sfx ui world anim code qa kit)")
                continue
            counts["inbox"] = counts.get("inbox", 0) + 1
            if DRY:
                continue
            if kind == "rule":
                p = order_add(dept, words, today)
                where = "a standing order"
            else:
                row(dept, "graveyard.md", GRAVE_HEADER, [words, today, "the owner: never", words, "the owner's words (inbox.md)", ""])
                p, where = f"{ROOT}/{dept}/graveyard.md", "a graveyard row"
            link = "[[" + os.path.relpath(p, ROOT).replace(os.sep, "/")[:-3] + "]]"
            filed.append(f"- {today} {dept} {kind}: {words} — {where} {link}")
            continue
        if retire:
            if DRY:
                # (a line a real run already marked "not filed" needs the owner, not another sync: not pending)
                if "<- not filed:" not in line:
                    counts["inbox"] = counts.get("inbox", 0) + 1
                continue
            p, why = lesson_retire(retire.group(1), today)
            if not p:
                keep.append(f"{clean}  <- not filed: {why}")
                continue
            counts["inbox"] = counts.get("inbox", 0) + 1
            link = "[[" + os.path.relpath(p, ROOT).replace(os.sep, "/")[:-3] + "]]"
            filed.append(f"- {today} retired the lesson {link}")
            continue
        m = INBOX_LINE.match(clean)
        dept = KIND_DEPT.get(m.group(1).lower()) if m else None
        if not m or not dept:
            why = "unknown kind" if m else "write it as: - <kind> <name> <score> <words>"
            keep.append(f"{clean}  <- not filed: {why}")
            continue
        score = float(m.group(4))
        if score > 10:
            score = score / 10.0
        if not 0 <= score <= 10:
            keep.append(f"{clean}  <- not filed: score must be 0-10 or 0-100")
            continue
        name, words = m.group(2) or m.group(3), m.group(5)
        counts["inbox"] = counts.get("inbox", 0) + 1
        if DRY:
            continue
        note = verdict(dept, name, score, today, words, quoted_from="inbox.md (the owner, in Obsidian)", tags=["inbox"])
        link = "[[" + os.path.relpath(note, ROOT).replace(os.sep, "/")[:-3] + "]]" if note else ""
        filed.append(f"- {today} {dept} {name} {round(score, 1)}/10 — {words} {link}".rstrip())
    if DRY:
        return
    out = head + "## New\n" + ("\n".join(keep) + "\n" if keep else "\n") + "\n## Filed\n"
    old_filed = filed_part.strip("\n")
    out += "\n".join(filed + ([old_filed] if old_filed else [])) + "\n"
    if out != text:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)


# ------------------------------------------------------------------ board decisions
# board/decisions/<stamp>-<slug>.md ("# Title", "- date:", "- by:", ## Decision / ## Why / ## Rejected) -> one vault
# note under the department the decision is about (keywords in the title + decision), else kit. kit decide writes
# both places since 2026-10-17; this files the older ones and any written by hand.
DECISION_DEPT = [
    ("anim", ["anim", "locomotion", "r6", "rig", "motion", "pose", "clip"]),
    ("vfx", ["vfx", "effect", "particle", "aura", "beam"]),
    ("ui", ["ui ", "screen", "hud", "font", "identity"]),
    ("world", ["world", "terrain", "level", "map"]),
    ("sfx", ["sound", "sfx", "audio"]),
    ("3d", ["3d", "asset", "model", "mesh", "cad", "kenney", "quaternius", "mpfb", "prop", "sculpt"]),
    ("code", ["remote", "service", "system", "net ", "moveset"]),
]


def decisions():
    # a decision kit decide already wrote to the vault names its board file in its frontmatter: never filed twice
    known = set()
    for q in glob.glob(f"{ROOT}/*/decisions/*.md"):
        with open(q, encoding="utf-8") as f:
            m = re.search(r"board/decisions/[^\s\"']+\.md", f.read())
        if m:
            known.add(os.path.basename(m.group(0)))
    for p in sorted(glob.glob("board/decisions/*.md")):
        if os.path.basename(p) in known:
            counts["skipped"] += 1
            continue
        with open(p, encoding="utf-8") as f:
            text = f.read().replace("\r\n", "\n")
        title = (re.search(r"^#\s+(.+)$", text, re.M) or re.search(r"(.+)", text)).group(1).strip()
        date = (re.search(r"^- date:\s*(\S+)", text, re.M) or re.search(r"^(\d{4}-\d{2}-\d{2})", os.path.basename(p))).group(1)
        by = (re.search(r"^- by:\s*(.+)$", text, re.M).group(1).strip() if re.search(r"^- by:", text, re.M) else "unknown")
        body = text.split("\n", 1)[1] if "\n" in text else ""
        body = re.sub(r"^- (date|by):.*\n", "", body, flags=re.M).strip()
        hay = (title + " " + body).lower()
        dept = next((d for d, words in DECISION_DEPT if any(w in hay for w in words)), "kit")
        front = {"kind": "decision", "area": dept, "name": title, "date": date[:10], "by": by,
                 "source": "board/decisions/" + os.path.basename(p), "links": [f"[[{dept}/index]]"]}
        if write(f"{ROOT}/{dept}/decisions/{date[:10]}-{slug(title)}.md", front, body):
            counts["decisions"] = counts.get("decisions", 0) + 1


# every store in the order a full sync runs them; --only <a,b> runs just those (a lane command syncs its own store
# the moment it records a verdict). Each run stamps .verify/vault_sync.json so `kit status` can tell when a store
# changed after its last sync.
STORES = {"lessons": lessons, "ui": ui_judges, "vfx": vfx_library, "anim": anim_store, "sfx": sounds,
          "inbox": inbox, "decisions": decisions, "anchors": anchors, "memory": memory, "graveyard": graveyard, "golden": golden}


def _lock():
    """one writing sync per vault at a time: several lane sessions run `kit status` (which files the inbox) at once,
    and two passes over the same inbox line must never both file it. A lock older than 5 minutes is a crashed run's."""
    import hashlib
    import tempfile
    import time as _t
    key = hashlib.sha1(os.path.abspath(ROOT).lower().encode("utf-8")).hexdigest()[:12]
    path = os.path.join(tempfile.gettempdir(), f"kit-vault-sync-{key}.lock")
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                if _t.time() - os.path.getmtime(path) > 300:
                    os.remove(path)
                    continue
            except OSError:
                continue
            return None
    return None


def run(only=None):
    names = [n for n in STORES if not only or n in only]
    lock = None if DRY else _lock()
    if not DRY and lock is None:
        counts["locked"] = True  # another session is syncing this vault right now: it files everything
        return []
    _verdict_notes.clear()  # a long-lived caller (the sound booth) syncs many times: read the notes afresh each run
    try:
        for n in names:
            STORES[n]()
    finally:
        if lock:
            try:
                os.remove(lock)
            except OSError:
                pass
    if not DRY:
        import time as _t
        stamp_path = os.path.join(".verify", "vault_sync.json")
        stamps = {}
        if os.path.isfile(stamp_path):
            try:
                with open(stamp_path, encoding="utf-8") as f:
                    stamps = json.load(f)
            except ValueError:
                stamps = {}
        now = _t.time()
        for n in names:
            stamps[n] = now
        os.makedirs(".verify", exist_ok=True)
        with open(stamp_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(stamps, f, indent=1)
    return names


def sync_store(name):
    """for a lane's own python code: sync one store right after it records a verdict; never raises (a verdict is
    already safe in the lane's store; the vault catches up on the next full sync)"""
    try:
        run({name})
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
        unknown = only - set(STORES)
        if unknown:
            print(json.dumps({"status": "fail", "summary": f"vault sync: unknown store(s) {sorted(unknown)}",
                              "next_action": "stores: " + ", ".join(STORES)}))
            sys.exit(2)
    before = sum(len(files) for _, _, files in os.walk(ROOT)) if os.path.isdir(ROOT) else 0
    ran = run(only)
    after = sum(len(files) for _, _, files in os.walk(ROOT)) if os.path.isdir(ROOT) else 0
    # `pending` (dry runs): everything a sync would file - every count but `skipped`, numbers only (a flag such as
    # `locked` is no count) - the ONE number --check, verify's "vault in step" and upgrade read, so they never
    # disagree on whether the vault is behind. (A real run files them: it reports what it filed in its counts.)
    behind = {k: v for k, v in counts.items() if k != "skipped" and type(v) is int and v > 0}
    out = {"dry_run": DRY, "files_before": before, "files_after": after, "stores": ran, **counts}
    if DRY:
        out["pending"] = sum(behind.values())
    print(json.dumps(out))
    if CHECK and behind:
        print(json.dumps({"status": "fail", "summary": f"vault: behind the kit's records ({behind})",
                          "next_action": "python kit/scripts/vault_migrate.py   (then commit kit/knowledge/vault)"}))
        sys.exit(1)
