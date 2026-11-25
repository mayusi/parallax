"""direction.py — the DIRECTION step before anything original is built (the owner, 2026-10-24: "the craft is not the
weak link, the creative direction is"). A creative director decides WHAT a piece is and why before anyone builds it;
this makes that a document with a fixed shape the kit can check, per lane (world and sound decide their own
direction: the departments stay separate).

    python kit/direction.py check <doc.md> --lane <world|sfx>       (one JSON line: draft / ready / picked)
    python kit/direction.py new <doc.md> --lane <world|sfx> --name <Piece>   (writes the template)

A doc: # <Piece> — direction, then these sections (## headings):
  Intent       what the player should FEEL and why (>= 40 words)
  The one idea one sentence: what makes this piece this piece and no other (<= 45 words)
  References   >= 6 lines "- <source> — take: ... — leave: ..." from more than one medium (not only the game it riffs on)
  Pillars      exactly 3 rules everything must serve
  Bans         >= 3 things it must never be
  Directions   >= 3 "### <letter> — <name>" options, each with its feeling, its risk, an "Axes: state=..; light=..;
               palette=..; mood=.." line (every pair must differ on >= 2 axes: real divergence, not one idea in three
               grades), and a Frame: (world) or Sketch: (sfx) path to a real render / audio file that exists
  (references must span >= 3 media, each named in brackets: (photography), (painting), (game) ...)
  Pick         "pending ..." until the owner chooses, then "picked: <letter or mix> by owner — \"<their words>\""
Status: draft (something missing) -> ready (show the owner the frames / sketches) -> picked (build to it).
"""

import json
import os
import re
import sys

SECTIONS = ["Intent", "The one idea", "References", "Pillars", "Bans", "Directions", "Pick"]
MEDIA = {"world": "Frame", "sfx": "Sketch", "anim": "Frame", "3d": "Sheet"}  # anim: a key-pose sheet / gif on the owner's
# R6 rig; 3d: a CONCEPT SHEET per direction (side silhouette + the hero view: what the build will be traced from)
# the Axes line a new doc starts with: the lane's core axes (checked below) + one more
AXES_HINT = {"world": "state=...; light=...; palette=...; mood=...", "sfx": "space=...; source=...; density=...; mood=...",
             "anim": "rhythm=...; read=...; effort=...; mood=...",
             "3d": "maker=...; era=...; shape=...; material=...; mood=..."}
PLURAL = {"Frame": "frames", "Sketch": "sketches", "Sheet": "concept sheets"}

TEMPLATE = """# {name} — direction

Lane: {lane}. Piece: {name}. Decide WHAT this is before building it; show the owner the {media_p}, then build to the pick.

## Intent
TODO: what the player should feel here, in what order, and why (at least 40 words).

## Brainstorm
(optional, not checked - think wide BEFORE choosing; write 8+ raw ideas, then pick the one idea below)
Lenses that found real ideas here: TIME (what happened to it, what is still happening: the lake keeps a record) ·
the WORLD's own hero (tie it to the setting's unique thing: the Erdtree's root inside the castle) · FUNCTION
inverted (a fortress built to worship what it now fights) · a SECRET the player discovers (the bell under the
water) · a RITUAL of the people who lived here (lanterns for the drowned) · SCALE shift (one huge thing, or a
thousand small) · a SENSE other than sight leads (it sings in the wind) · a MATERIAL with a story (tide rings,
scorch, repairs) · what it would look like if it were ALIVE · the opposite of the obvious genre take.
- TODO

## The one idea
TODO: one sentence - what makes this piece this piece and no other.

## References
- TODO <source (medium)> — take: <what we take> — leave: <what we leave>
(at least 6, from more than one medium: photography, architecture / field recordings, film, painting, other games)

## Pillars
- TODO
- TODO
- TODO

## Bans
- TODO
- TODO
- TODO

## Directions
### A — TODO
Feeling: ... Risk: ...
Axes: {axes}
{media}: direction/{name}_A.{ext}

### B — TODO
Feeling: ... Risk: ...
Axes: {axes}
{media}: direction/{name}_B.{ext}

### C — TODO
Feeling: ... Risk: ...
Axes: {axes}
{media}: direction/{name}_C.{ext}

## Pick
pending
"""


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return out


def bullets(lines):
    return [ln[2:].strip() for ln in lines if ln.startswith("- ")]


def check(path, lane):
    """(status, problems, info)"""
    text = open(path, encoding="utf-8").read()
    sec = sections(text)
    probs = []
    for s in SECTIONS:
        if s not in sec:
            probs.append(f'no "## {s}" section')
    if "TODO" in text:
        probs.append("TODO left in the doc")
    words = lambda name: len(" ".join(sec.get(name, [])).split())
    if "Intent" in sec and words("Intent") < 40:
        probs.append(f"Intent is {words('Intent')} words (>= 40: what the player feels, in what order, why)")
    if "The one idea" in sec:
        w = words("The one idea")
        if w == 0 or w > 45:
            probs.append(f"The one idea is {w} words (one sentence, <= 45)")
    refs = bullets(sec.get("References", []))
    good = [r for r in refs if "take:" in r and "leave:" in r]
    if len(good) < 6:
        probs.append(f"{len(good)} reference(s) with take: / leave: (>= 6)")
    # the medium is the LAST bracket before take: and must be words (a year in brackets is not a medium)
    ref_media = set()
    for r in good:
        brackets = re.findall(r"\(([^)]+)\)", r.split("take:")[0])
        if brackets and re.search(r"[A-Za-z]{3,}", brackets[-1]) and not re.fullmatch(r"[\d\s.,\-–]+", brackets[-1]):
            ref_media.add(brackets[-1].strip().lower())
    if good and len(ref_media) < 3:
        probs.append(f"references from {len(ref_media)} medium/media ({', '.join(sorted(ref_media)) or 'none named'}): >= 3 (photography, architecture, painting, film, field recordings, games ...) - name each in brackets")
    if "Pillars" in sec and len(bullets(sec["Pillars"])) != 3:
        probs.append(f"{len(bullets(sec['Pillars']))} pillars (exactly 3)")
    if "Bans" in sec and len(bullets(sec["Bans"])) < 3:
        probs.append(f"{len(bullets(sec['Bans']))} bans (>= 3)")
    media = MEDIA[lane]
    dirs = re.findall(r"^###\s+(\w+)\s+[—-]", "\n".join(sec.get("Directions", [])), re.M)
    files = re.findall(rf"^{media}:\s*(\S+)", "\n".join(sec.get("Directions", [])), re.M)
    base = os.path.dirname(os.path.dirname(os.path.abspath(path)))  # (paths are relative to the lane's asset folder)
    missing = [f for f in files if not os.path.isfile(os.path.join(base, f)) and not os.path.isfile(f)]
    if len(dirs) < 3:
        probs.append(f"{len(dirs)} direction(s) (>= 3 distinct options)")
    if len(files) < len(dirs) or len(files) < 3:
        probs.append(f"{len(files)} {media}: line(s) for {len(dirs)} direction(s) (each option needs a real {media.lower()})")
    for f in missing:
        probs.append(f"{media.lower()} not found: {f}")
    # divergence: three options that are one idea in three grades are not three directions (Stormhold round 1)
    blocks = re.split(r"^###\s+", "\n".join(sec.get("Directions", [])), flags=re.M)[1:]
    axes = []
    for blk in blocks:
        m = re.search(r"^Axes:\s*(.+)$", blk, re.M)
        axes.append(dict((k.strip().lower(), v.strip().lower()) for k, v in (kv.split("=", 1) for kv in m.group(1).split(";") if "=" in kv)) if m else None)
    core = {"world": ("light", "palette", "mood"), "sfx": ("space", "source", "mood"),
            "anim": ("rhythm", "read", "mood"),
            "3d": ("shape", "material", "mood")}[lane]  # anim: the beat pattern, the shape it reads as, the feeling;
    # 3d: the shape family (round / square / blade-like ...), what it is made of, the feeling it gives its holder
    for d_, ax in zip(dirs, axes):
        if ax is not None and not all(k in ax for k in core):
            probs.append(f"direction {d_}'s Axes must name {', '.join(core)} (it names {', '.join(ax) or 'nothing'})")
    if blocks and any(a is None for a in axes):
        probs.append(f"{sum(a is None for a in axes)} direction(s) without an Axes: line (state=...; light=...; palette=...; mood=...)")
    else:
        for i in range(len(axes)):
            for j in range(i + 1, len(axes)):
                keys = set(axes[i]) & set(axes[j])
                diff = [k for k in keys if axes[i][k] != axes[j][k]]
                if len(diff) < 2:
                    probs.append(f"directions {dirs[i] if i < len(dirs) else i + 1} and {dirs[j] if j < len(dirs) else j + 1} differ on {len(diff)} axis/axes ({', '.join(diff) or 'none'}): >= 2 - they are one direction in two grades")
    pick = " ".join(sec.get("Pick", [])).strip()
    picked = re.match(r"^picked:\s*(.+?)\s+by owner", pick) is not None
    status = "draft" if probs else ("picked" if picked else "ready")
    return status, probs, {"directions": dirs, "files": files, "references": len(good), "pick": pick[:160]}


def main(argv):
    if len(argv) < 2 or argv[0] not in ("check", "new") or "--lane" not in argv:
        print(json.dumps({"status": "fail", "summary": "usage: direction.py check|new <doc.md> --lane world|sfx|anim|3d [--name Piece]",
                          "next_action": "lune run kit world direction <Piece> / lune run kit sfx direction <Piece>"}))
        return 2
    cmd, path, lane = argv[0], argv[1], argv[argv.index("--lane") + 1]
    if lane not in MEDIA:
        print(json.dumps({"status": "fail", "summary": f"lane {lane!r}: world, sfx, anim or 3d",
                          "next_action": "--lane world|sfx|anim|3d"}))
        return 2
    if cmd == "new":
        name = argv[argv.index("--name") + 1] if "--name" in argv else os.path.splitext(os.path.basename(path))[0]
        if os.path.isfile(path):
            print(json.dumps({"status": "fail", "summary": f"{path} exists (never overwritten)", "next_action": f"edit {path}"}))
            return 1
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        media = MEDIA[lane]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(TEMPLATE.format(name=name, lane=lane, media=media, media_p=PLURAL[media], ext="ogg" if lane == "sfx" else "png",
                                     axes=AXES_HINT[lane]))
        print(json.dumps({"status": "pass", "summary": f"direction template written: {path}",
                          "next_action": f"write it (intent, one idea, >= 6 references, 3 pillars, bans, 3 directions with {media.lower()}s), then check it"}))
        return 0
    if not os.path.isfile(path):
        print(json.dumps({"status": "fail", "summary": f"no direction doc {path}", "next_action": "create it: --new"}))
        return 1
    status, probs, info = check(path, lane)
    nxt = {"draft": f"finish it: {probs[0]}" if probs else "",
           "ready": f"SHOW the owner the {PLURAL[MEDIA[lane]]} ({', '.join(info['files'])}); record their pick in ## Pick: picked: <letter> by owner — \"<their words>\"",
           "picked": "build to the pick: every later decision is checked against the pillars and bans"}[status]
    print(json.dumps({"status": "pass" if status != "draft" else "fail",
                      "summary": f"{os.path.basename(path)}: {status}" + (f" ({len(probs)} problem(s))" if probs else f" - {len(info['directions'])} directions, {info['references']} references"),
                      "next_action": nxt, "direction": status, "problems": probs, **info}))
    return 0 if status != "draft" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
