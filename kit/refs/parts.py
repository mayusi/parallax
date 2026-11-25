"""parts.py — which parts of an asset have NO reference picture yet, and the searches that would find one.

    python kit/refs/parts.py <asset> [--similar "<a similar object>"]

Reads assets/models/<asset>.parts.md (the part review) and the brief's `what:` line. Every part family whose answer
does not cite a picture on disk (kit/blender/review_refs.py — the rule a hero build fails on) is listed with two
searches: the object's own part, then the closest SIMILAR object's part (--similar, else the brief's `similar:` line,
else the part alone). A similar part is a real reference: another make's trigger guard, a target pistol's rear sight,
an exploded diagram's sear (the owner, 2026-10-07). One JSON verdict line after the list.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "blender"))
import review_refs  # noqa: E402

ENTRY = re.compile(r"^- (?P<fam>[A-Za-z_][\w*]*) \[(?P<fp>[0-9a-f]{8})\]:\s*(?P<body>.*)$")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def brief_line(asset, key):
    p = os.path.join(REPO, "assets", "models", f"{asset}.brief.md")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(rf"^- {key}:\s*(.+)$", line.strip())
            if m:
                return m.group(1).strip()
    return None


def short_name(what):
    """the brief's `what:` -> the object's short name for a search: up to the first ' (', ' —', ',' or ' -'"""
    return re.split(r"\s\(|\s—|,|\s-\s", what or "")[0].strip()


def main(argv):
    if not argv:
        return emit("fail", "refs parts: give the asset", "lune run kit refs parts <asset> [--similar \"<object>\"]")
    asset = argv[0]
    review = os.path.join(REPO, "assets", "models", f"{asset}.parts.md")
    if not os.path.isfile(review):
        return emit("fail", f"refs parts: no assets/models/{asset}.parts.md yet", f"lune run kit asset {asset} --geo")
    similar = argv[argv.index("--similar") + 1] if "--similar" in argv and argv.index("--similar") + 1 < len(argv) \
        else brief_line(asset, "similar")
    obj = re.sub(r"^(the|a|an) ", "", short_name(brief_line(asset, "what")) or asset, flags=re.I)
    missing, total = [], 0
    with open(review, encoding="utf-8") as fh:
        for line in fh:
            m = ENTRY.match(line.rstrip("\n"))
            if not m:
                continue
            total += 1
            body = m["body"].strip()
            _ok, probs = review_refs.ref_problems(body, REPO) if not body.startswith("TODO") else ([], ["unanswered"])
            if probs:
                missing.append((m["fam"], probs[0]))
    seen, rows = set(), []
    for fam, why in missing:
        words = review_refs.part_words(fam)
        if words in seen:
            continue
        seen.add(words)
        alt = f"{similar} {words}" if similar else f"{words} closeup"
        rows.append(f"  {fam}: {why} -> kit refs find \"{obj} {words}\"  |  kit refs find \"{alt}\"")
    if not missing:
        return emit("pass", f"refs parts {asset}: all {total} part families cite a reference picture", "none — proceed")
    return emit("fail", f"refs parts {asset}: {len(missing)} of {total} part families have no reference picture",
                f"run the searches above (the part on the real object first, then the closest similar part), look at "
                f"what comes back, and cite the picture in each answer's ref: field ({review})",
                missing=[f for f, _w in missing], rows=rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
