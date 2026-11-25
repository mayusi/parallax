"""review_refs.py — the part review's REFERENCE rule (pure Python: the build and the tests both use it).

Every part family's answer in assets/models/<asset>.parts.md cites the picture(s) it was modelled from:
    - Hammer [1a2b3c4d]: real: ... | attaches: ... | works: ... | ref: refs/private/x/hammer_side.jpg | verdict: ok
A picture of THIS part on the real object, or — when the exact object has none — of the closest SIMILAR part (another
1911's trigger guard, a target pistol's rear sight, an exploded diagram's sear): `lune run kit refs find "<object>
<part>"`, then "<similar object> <part>". Each cited file must exist (under the repo or absolute); prose alone is not
a reference. The owner, 2026-10-07: "you're still not being forced to get more references and do more data on every
point ... finding something similar but to a specific point or part in the gun".
A part answered by a MEASUREMENT may cite a dimension row instead of (or with) a picture: `ref: dims:4eb2b52b` — a
row of kit/real_specs (`lune run kit refs dims find "<object> <part>"`), which must exist.
"""

import json
import os
import re

REF_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".svg", ".tif", ".tiff", ".bmp")
_PATH = re.compile(r"[\w./\\:-]+\.(?:" + "|".join(e[1:] for e in REF_EXT) + r")\b", re.IGNORECASE)
_DIMS = re.compile(r"\bdims:([0-9a-f]{8})\b")


def dims_ids(repo):
    """every dimension row's id (kit/real_specs/*.json)"""
    out, folder = set(), os.path.join(repo, "kit", "real_specs")
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if f.endswith(".json"):
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                out |= {r.get("id") for r in json.load(fh)}
    return out


def ref_field(body):
    """the text of an answer's `ref:` field (up to the next ` | `), or None"""
    m = re.search(r"\bref:\s*(.*?)(?:\s\|\s|$)", body)
    return m.group(1).strip() if m else None


def withdrawn_rows(repo):
    """{row id: why} — every dimension row a dossier withdrew (added wrong): kit/knowledge and the private store"""
    out = {}
    for folder in (os.path.join(repo, "kit", "knowledge"),
                   os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "knowledge")):
        for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            for rid, w in ((d.get("withdrawn_rows") or {}) if isinstance(d, dict) else {}).items():
                out[rid] = (w or {}).get("why") or "withdrawn"
    return out


def ref_problems(body, repo):
    """-> (the cited pictures / dimension rows that exist, problems). A problem: no ref: field, no picture path and
    no dims row in it, or a cited picture not on disk / a dims row not in kit/real_specs."""
    field = ref_field(body)
    if field is None:
        return [], ["no ref: (cite the picture this part was modelled from, or a dimension row: dims:<id>)"]
    paths, rows = _PATH.findall(field), _DIMS.findall(field)
    if not paths and not rows:
        return [], [f"ref: '{field[:60]}' names no picture file and no dims row"]
    ok, bad = [], []
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(repo, p)
        (ok if os.path.isfile(full) else bad).append(p)
    gone = {}
    if rows:
        known, withdrawn = dims_ids(repo), withdrawn_rows(repo)
        for r in rows:
            if r in withdrawn:
                gone[f"dims:{r}"] = withdrawn[r]
            else:
                (ok if r in known else bad).append(f"dims:{r}")
    probs = [f"ref {p} not found" for p in bad] + [f"ref {p} was withdrawn from its dossier ({why})"
                                                  for p, why in gone.items()]
    if not ok and not probs:
        probs.append("no cited picture exists")
    return ok, probs


def part_words(family):
    """'SlideStopPlunger' -> 'slide stop plunger'; 'Round1Case' -> 'round case'"""
    w = re.sub(r"\d+", " ", family)
    w = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", w)
    return " ".join(w.lower().split())
