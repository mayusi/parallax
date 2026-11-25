"""alike.py — search by LOOK (2026-11-08, sprint 4: proposal 8 of board/plans/archive/2026-11-08-pipeline-rag-learning-research.md).

Every picture of our past pieces (the owner's judged copies, the VFX / UI library previews, renders, animation looks
and pick-sheet candidates) and every reference picture, embedded once with the pinned SigLIP 2 (kit/vision/run.py
embed, the perceptual judge's eye), in a local index keyed by content (build/look/, git-ignored, rebuilt by
`kit alike index`). Then:
  near <picture | piece>  the past pieces that LOOK closest, one line each with the owner's newest verdict on it
                          (their own numbers apart from guessed ones) - never the piece itself, never its own round
  dupes                   the same picture filed twice among the references (resized / recompressed copies too)
Run through kit/vision/run.py (`run.py alike ...`), so the warm vision worker answers it with the model loaded.

  python kit/vision/run.py alike index [--lane L]
  python kit/vision/run.py alike near <picture | piece> [--lane L] [--k N] [--cached] [--refs]
  python kit/vision/run.py alike dupes [--lane L] [--min 0.985] [--kind ref|all]
  (--root R, --vault V, --index I: other folders, for tests)
Each prints one JSON line last ({"status", "summary", "next_action", "lines": [...], ...})."""

import glob
import hashlib
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "anim"))
import vault_migrate as VM  # noqa: E402  (split_note / field: the vault's own note reader)
import check_validate as CV  # noqa: E402  (verdict_targets: the rounds an animation note judges - sprint 2's mapping)

SCHEMA = 1
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
OURS = ("judged", "library", "render", "candidate")  # pictures of our own pieces (refs are other people's)
# measured 2026-11-08 on the 4,804 reference pictures (a 64-bit dhash as the pixel truth; re-measured by the review on
# all 899 pairs): of the pairs at cosine >= 0.995, 97% are within 4 of 64 dhash bits (70% identical) - a picture filed
# twice; between 0.985 and 0.995 about 65% are within 4 bits, mostly neighbouring frames of one shot (--min 0.985)
DUP_MIN = 0.995
BATCH = 32

# a 3D render's aids (traced references, line / shade passes, labels) are no picture of the piece
AID = re.compile(r"(^_selftest)|(_(lines|shaded|labels|mask|edges|depth\d*)$)|(_ref(_|$))|(_colours(_|$))", re.I)
VIEW = re.compile(r"_(front|side|top|back|left|right|hero|game|iso|persp|ortho|compare|clean|parts(_\d+)?|closeup.*|\d+)$",
                  re.I)


def _stem(p):
    return os.path.splitext(os.path.basename(p))[0]


def render_piece(p):
    # a dotted suffix is a variant of the same render ("town_barrel_game.clean", "<asset>.judge"): the piece is before it
    s = _stem(p).split(".")[0]
    if AID.search(s):
        return None
    prev = None
    while prev != s:
        prev, s = s, VIEW.sub("", s)
    return s or None


def ui_piece(p):
    s = _stem(p)
    return None if "." in s else s  # <Screen>.png; .cvd / .desktop / .phone are views of the same screen


def candidate_piece(p):
    m = re.search(r"([^/]+)/round_(\d+)/c(\d+)\.gif$", p.replace("\\", "/"))
    return f"{m.group(1)}/r{m.group(2)}/c{m.group(3)}" if m else None


# (lane, kind, pattern under a root, the piece a file shows) - every root is the project and each game folder
SOURCES = [
    ("vfx", "library", "library/vfx/effects/*/previews/hero.png", lambda p: p.replace("\\", "/").split("/")[-3]),
    ("vfx", "render", "build/vfx/booth/*_play_hero.png", lambda p: _stem(p)[: -len("_play_hero")]),
    ("vfx", "render", "build/vfx/*.png", _stem),
    ("ui", "library", "library/ui/*/screens/*/previews/sheet.png", lambda p: p.replace("\\", "/").split("/")[-3]),
    ("ui", "render", "build/ui/*.png", ui_piece),
    ("world", "render", "build/worlds/*.png", _stem),
    ("3d", "render", "build/renders/*.png", render_piece),
    ("anim", "render", "build/animations/*.r6.look.gif", lambda p: os.path.basename(p)[: -len(".r6.look.gif")]),
    ("anim", "candidate", "build/candidates/*/round_*/c*.gif", candidate_piece),
    ("ui", "ref", "assets/ui/refs/**/*", None),
    ("3d", "ref", "assets/models/refs/**/*", None),
    ("world", "ref", "assets/worlds/refs/**/*", None),
    ("vfx", "ref", "assets/effects/refs/**/*", None),
]


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _rel(p, root):
    return os.path.relpath(p, root).replace(os.sep, "/")


def _prefixes(root):
    """the folders every source sits under: the project, then each game ([(prefix, game)])"""
    out = [("", None)]
    games_dir = os.path.join(root, "games")
    if os.path.isdir(games_dir):
        out += [(f"games/{g}/", g) for g in sorted(os.listdir(games_dir)) if os.path.isdir(os.path.join(games_dir, g))]
    return out


def collect(root=".", vault="kit/knowledge/vault", lane=None):
    """every picture the index covers -> [{path, lane, kind, piece, game}] (paths relative to root)"""
    out, seen = [], set()
    prefixes = _prefixes(root)
    for ln, kind, pattern, piece_of in SOURCES:
        if lane and ln != lane:
            continue
        for prefix, game in prefixes:
            for p in sorted(glob.glob(os.path.join(root, prefix + pattern), recursive=True)):
                if not os.path.isfile(p) or not p.lower().endswith(IMAGE_EXT):
                    continue
                rel = _rel(p, root)
                piece = rel if piece_of is None else piece_of(rel)
                if not piece or rel in seen or (piece_of is not None and piece.startswith("_")):
                    continue  # (a "_fit_..." / "_selftest..." render is a scratch run, no past piece)
                seen.add(rel)
                out.append({"path": rel, "lane": ln, "kind": kind, "piece": piece, "game": game})
    # the owner's judged copies: the verdict note that keeps one names its piece
    for front, rel_note in _notes(vault):
        judged = VM.field(front, "judged")
        name = VM.field(front, "name")
        dept = rel_note.split("/")[0]
        if not judged or not name or (lane and dept != lane):
            continue
        p = os.path.join(vault, judged)
        rel = _rel(p, root)
        if os.path.isfile(p) and p.lower().endswith(IMAGE_EXT) and rel not in seen:
            seen.add(rel)
            out.append({"path": rel, "lane": dept, "kind": "judged", "piece": name, "game": None})
    return out


def _notes(vault):
    for p in sorted(glob.glob(os.path.join(vault, "*", "verdicts", "*.md"))):
        try:
            front, _body = VM.split_note(open(p, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            continue
        yield front, _rel(p, vault)


EVERY = ("all bad", "every one", "every candidate", "all of them", "all 8")  # check_validate.owner_rejections' words


def _when(front, path):
    """a note's moment: its date, its time (epoch seconds), then its file's day counter ("<piece>--<date>-2.md" is the
    day's second note) - most notes carry no time, and their files sort the base name after "-2" ("." > "-")"""
    t = VM.field(front, "time") or ""
    m = re.search(r"--\d{4}-\d{2}-\d{2}-(\d+)$", os.path.splitext(os.path.basename(path))[0])
    return ((VM.field(front, "date") or "")[:10], int(t) if t.isdigit() else 0, int(m.group(1)) if m else 1)


def verdicts(vault="kit/knowledge/vault", moves=None, owner_only=False):
    """(lane, piece lower-case) -> the newest verdict note on it (date, then time): {name, date, score, direction,
    source, words}. An animation note also stands for each round it judges (check_validate.verdict_targets: a note
    named "<Move>/rK" or "<Move>/rK/cN", or "<Move>" whose words name "round K"), keyed "<Move>/rK" ["/cN"]; `moves`
    maps a lower-case move name to its own (the candidates the index knows)"""
    out = {}

    def keep(key, rec):
        if key not in out or rec["when"] >= out[key]["when"]:
            out[key] = rec

    for p in sorted(glob.glob(os.path.join(vault, "*", "verdicts", "*.md"))):
        try:
            front, body = VM.split_note(open(p, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            continue
        name = VM.field(front, "name")
        if not name:
            continue
        lane = _rel(p, vault).split("/")[0]
        words = VM.norm(re.sub(r"^#.*$", "", body, flags=re.M))
        rec = {"name": name, "date": (VM.field(front, "date") or "")[:10], "when": _when(front, p),
               "score": VM.field(front, "score"), "direction": VM.field(front, "direction"),
               "source": VM.field(front, "source") or "owner", "words": words[:160]}
        if owner_only and rec["source"] == "inferred":
            continue  # (the taste model learns the owner's own numbers only: a guess never)
        keep((lane, name.strip().lower()), rec)
        if lane == "anim" and moves:
            low = body.lower()
            for move, k, cand in CV.verdict_targets(name, body, moves):
                # a move note naming candidates ("round 2: c3 and c5 are stilts") judges those, unless it says all
                # (check_validate.owner_rejections' reading - sprint 2)
                ids = [] if cand else sorted(set(re.findall(r"\bc(\d+)\b", low)), key=int)
                if cand:
                    keep((lane, f"{move}/r{k}/{cand}".lower()), rec)
                elif ids and not any(w in low for w in EVERY):
                    for i in ids:
                        keep((lane, f"{move}/r{k}/c{i}".lower()), rec)
                else:
                    keep((lane, f"{move}/r{k}".lower()), rec)
    return out


def moves_of(meta):
    """the animation moves the index has candidates of: lower-case name -> its own"""
    out = {}
    for e in meta.get("entries", []):
        if e["kind"] == "candidate":
            m = e["piece"].split("/")[0]
            out[m.lower()] = m
    return out


def verdict_of(vd, lane, piece, move_level=True):
    """the newest verdict on a piece; an animation candidate falls back to its round's, then (move_level, for what
    is shown - never for the round report's loved / rejected) to its move's newest note"""
    v = vd.get((lane, piece.lower()))
    if v is None and lane == "anim":
        m = re.match(r"^((.+?)/r\d+)/c\d+$", piece)
        if m:
            v = vd.get((lane, m.group(1).lower()))
            if v is None and move_level:
                v = vd.get((lane, m.group(2).lower()))
    return v


def verdict_text(v, about=None):
    """the verdict as a line; `about`: the piece shown - a note on another name (its round, its move) says so"""
    if not v:
        return "no verdict yet"
    who = "guessed" if v["source"] == "inferred" else "owner"
    if v["score"] not in (None, ""):
        head = f"{who} {v['score']}/10"
    elif v["direction"]:
        head = f"{who} {v['direction'].capitalize()}"
    else:
        head = who
    on = f" on {v['name']}" if about and v["name"].strip().lower() != about.strip().lower() else ""
    words = v["words"][:90] + ("..." if len(v["words"]) > 90 else "")
    return f"{head}{on} {v['date']}: \"{words}\""


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _picture(path):
    """a still to embed: a GIF's middle frame, else the picture itself"""
    from PIL import Image  # noqa: PLC0415

    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        if n > 1:
            img.seek(n // 2)
        return img.convert("RGB")


def load(index_dir):
    meta_p, vec_p = os.path.join(index_dir, "index.json"), os.path.join(index_dir, "vectors.npy")
    if not (os.path.isfile(meta_p) and os.path.isfile(vec_p)):
        return None, None
    try:
        with open(meta_p, encoding="utf-8") as fh:
            meta = json.load(fh)
        vecs = np.load(vec_p)
    except (OSError, ValueError):
        return None, None
    if meta.get("schema") != SCHEMA or len(meta.get("rows", {})) != len(vecs):
        return None, None
    return meta, vecs


def build(embed, root=".", vault="kit/knowledge/vault", index_dir="build/look", lane=None):
    """embed what is new (by content), keep what is known, drop what is gone -> stats"""
    meta, vecs = load(index_dir)
    old_entries = {e["path"]: e for e in (meta or {}).get("entries", [])}
    old_rows = (meta or {}).get("rows", {})
    files = collect(root, vault, lane)
    if lane and meta:  # an index of one lane keeps the other lanes' pictures as they were
        files += [e for e in meta["entries"] if e["lane"] != lane]
    entries, need, failed = [], [], 0
    for f in files:
        p = os.path.join(root, f["path"])
        if "sha" in f:  # carried over from another lane
            entries.append(f)
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        o = old_entries.get(f["path"])
        # (nanosecond times: a picture rewritten in the same second at the same size is still a new picture)
        sha = o["sha"] if o and o.get("size") == st.st_size and o.get("mtime_ns") == st.st_mtime_ns else _sha(p)
        entries.append({**f, "size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha": sha})
        if sha not in old_rows:
            need.append((sha, p))
    # unique new pictures, embedded in batches; a picture that cannot be read is left out (counted)
    new_vecs, todo = {}, list({sha: p for sha, p in need}.items())
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        imgs, keep = [], []
        for sha, p in chunk:
            try:
                imgs.append(_picture(p))
                keep.append(sha)
            except Exception:  # noqa: BLE001 - a broken picture is skipped, never fatal
                failed += 1
        if imgs:
            e = np.asarray(embed(imgs), dtype=np.float32)
            for sha, v in zip(keep, e):
                new_vecs[sha] = v
    used, have = [], set()
    for e in entries:
        if e["sha"] not in have and (e["sha"] in old_rows or e["sha"] in new_vecs):
            have.add(e["sha"])
            used.append(e["sha"])
    entries = [e for e in entries if e["sha"] in old_rows or e["sha"] in new_vecs]
    dim = (vecs.shape[1] if vecs is not None and len(vecs) else
           (len(next(iter(new_vecs.values()))) if new_vecs else 0))
    out = np.zeros((len(used), dim), dtype=np.float16)
    rows = {}
    for i, sha in enumerate(used):
        out[i] = new_vecs[sha] if sha in new_vecs else vecs[old_rows[sha]]
        rows[sha] = i
    os.makedirs(index_dir, exist_ok=True)
    tmp_m, tmp_v = os.path.join(index_dir, "index.json.tmp"), os.path.join(index_dir, "vectors.tmp.npy")
    np.save(tmp_v, out)
    with open(tmp_m, "w", encoding="utf-8") as fh:
        json.dump({"schema": SCHEMA, "model": "siglip2-base", "entries": entries, "rows": rows}, fh)
    os.replace(tmp_v, os.path.join(index_dir, "vectors.npy"))
    os.replace(tmp_m, os.path.join(index_dir, "index.json"))
    by = {}
    for e in entries:
        k = f"{e['lane']} {e['kind']}"
        by[k] = by.get(k, 0) + 1
    return {"pictures": len(entries), "unique": len(used), "embedded": len(new_vecs), "failed": failed,
            "by": dict(sorted(by.items()))}


def _query_vectors(target, meta, vecs, embed, root, cached):
    """(vectors to search with, the piece they show or None, what was searched, the picture's own content - never a
    match of itself): a picture file or a piece name"""
    p = os.path.join(root, target) if not os.path.isabs(target) else target
    if os.path.isfile(p):
        sha = _sha(p)
        if sha in meta["rows"]:
            piece = next((e["piece"] for e in meta["entries"] if e["sha"] == sha and e["kind"] in OURS), None)
            return vecs[[meta["rows"][sha]]].astype(np.float32), piece, target, {sha}
        if cached or embed is None:
            return None, None, target, {sha}
        return np.asarray(embed([_picture(p)]), dtype=np.float32), None, target, {sha}
    rows = sorted({meta["rows"][e["sha"]] for e in meta["entries"]
                   if e["kind"] in OURS and e["piece"].lower() == target.lower()})
    if not rows:
        return None, target, target, set()
    return vecs[rows].astype(np.float32), target, target, set()


JUDGED_EXTRA = 2  # beyond the top k, the nearest pieces with a verdict (the owner's or a guess, marked) are always added


def near(meta, vecs, qvecs, piece=None, lane=None, k=5, kinds=OURS, vd=None, judged_extra=JUDGED_EXTRA, skip_shas=()):
    """the past pieces that look closest to qvecs (best cosine over each piece's pictures), the piece itself, its own
    round and the very picture asked about left out; then the nearest judged pieces beyond them, so what was loved or
    rejected nearby always shows"""
    sims = (vecs.astype(np.float32) @ qvecs.T).max(axis=1)
    skip = (piece or "").lower()
    rnd = re.match(r"^(.+?/r\d+)(/c\d+)?$", piece or "")
    skip_round = (rnd.group(1).lower() + "/") if rnd else None
    best = {}
    for e in meta["entries"]:
        if e["kind"] not in kinds or (lane and e["lane"] != lane):
            continue
        name = e["piece"].lower()
        if name == skip or (skip_round and (name + "/").startswith(skip_round)) or e["sha"] in skip_shas:
            continue
        s = float(sims[meta["rows"][e["sha"]]])
        key = (e["lane"], e["piece"])
        if key not in best or s > best[key]["similarity"]:
            best[key] = {"lane": e["lane"], "piece": e["piece"], "kind": e["kind"], "path": e["path"],
                         "game": e.get("game"), "similarity": round(s, 4)}
    order = sorted(best.values(), key=lambda r: -r["similarity"])
    ranked = order[:k]
    extra = [r for r in order[k:] if r["kind"] != "ref" and verdict_of(vd or {}, r["lane"], r["piece"])][:judged_extra]
    for r in extra:
        r["judged_extra"] = True
    ranked += extra
    for r in ranked:
        v = verdict_of(vd or {}, r["lane"], r["piece"]) if r["kind"] != "ref" else None
        r["verdict"] = v
        r["line"] = (("nearest judged: " if r.get("judged_extra") else "")
                     + f"looks {r['similarity']:.2f} like {r['piece']} ({r['lane']} {r['kind']}"
                     + (f", {r['game']}" if r.get("game") else "")
                     + f"): {verdict_text(v, r['piece']) if r['kind'] != 'ref' else r['path']}")
    return ranked


def _polarity(v):
    """+1 loved (7+ or Keep), -1 rejected (3 or less, or Redo), 0 neither - the owner's own verdicts only"""
    if not v or v["source"] == "inferred":
        return 0
    try:
        sc = float(v["score"]) if v["score"] not in (None, "") else None
    except ValueError:
        sc = None
    if sc is not None:
        return 1 if sc >= 7 else (-1 if sc <= 3 else 0)
    d = (v["direction"] or "").lower()
    return 1 if d == "keep" else (-1 if d == "redo" else 0)


CLOSER_BY = 0.01  # a tie is no signal: the rejected piece must look closer by this much (a report, not validated)


def round_lines(meta, vecs, embed, root, move, rnd, vd, lane="anim"):
    """each candidate of a pick round against the owner's own loved and rejected pieces of the lane (its own round
    left out): the nearest of each by look, and whether it sits closer to a rejected one -> (lines, rows)"""
    found = []
    for prefix, _game in _prefixes(root):
        found += glob.glob(os.path.join(root, prefix, "build", "candidates", move, f"round_{rnd}", "c*.gif"))
    files = sorted(found, key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0))
    if not files:
        return [], []
    qv, have = [], []
    for p in files:
        sha = _sha(p)
        if sha in meta["rows"]:
            qv.append(vecs[meta["rows"][sha]].astype(np.float32))
            have.append(p)
        elif embed is not None:
            qv.append(np.asarray(embed([_picture(p)]), dtype=np.float32)[0])
            have.append(p)
    own = f"{move}/r{rnd}/".lower()
    pools = {1: [], -1: []}
    for e in meta["entries"]:
        if e["lane"] != lane or e["kind"] not in OURS or (e["piece"].lower() + "/").startswith(own):
            continue
        v = verdict_of(vd, lane, e["piece"], move_level=False)  # a move's note counts only for the rounds it names
        pol = _polarity(v)
        if pol:
            pools[pol].append((meta["rows"][e["sha"]], e["piece"], v))
    lines, rows = [], []
    for p, q in zip(have, qv):
        cand = os.path.splitext(os.path.basename(p))[0]
        near_of = {}
        for pol, pool in pools.items():
            if pool:
                sims = vecs[[r for r, _n, _v in pool]].astype(np.float32) @ q
                i = int(np.argmax(sims))
                near_of[pol] = (float(sims[i]), pool[i][1], pool[i][2])
        rej, lov = near_of.get(-1), near_of.get(1)
        closer = bool(rej and (not lov or rej[0] >= lov[0] + CLOSER_BY))
        parts = []
        if rej:
            parts.append(f"nearest rejected {rej[1]} {rej[0]:.2f} ({verdict_text(rej[2], rej[1])})")
        if lov:
            parts.append(f"nearest loved {lov[1]} {lov[0]:.2f}")
        lines.append(f"{cand}: " + ("; ".join(parts) if parts else "no loved or rejected piece of this lane to compare")
                     + (f" - CLOSER TO A REJECTED PIECE (by {rej[0] - lov[0]:.2f})" if closer and lov else
                        " - CLOSER TO A REJECTED PIECE" if closer else ""))
        rows.append({"candidate": cand, "rejected": rej and {"piece": rej[1], "similarity": round(rej[0], 4)},
                     "loved": lov and {"piece": lov[1], "similarity": round(lov[0], 4)}, "closer_to_rejected": closer})
    return lines, rows


def dupes(meta, vecs, lane=None, kinds=("ref",), min_sim=DUP_MIN):
    """groups of the same picture filed more than once (identical files, or cosine >= min_sim)"""
    items = [e for e in meta["entries"] if e["kind"] in kinds and (not lane or e["lane"] == lane)]
    if len(items) < 2:
        return []
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    m = vecs[[meta["rows"][e["sha"]] for e in items]].astype(np.float32)
    best = {}
    for i0 in range(0, len(items), 512):
        block = m[i0:i0 + 512] @ m.T
        for bi, j in zip(*np.nonzero(block >= min_sim)):
            i = i0 + int(bi)
            j = int(j)
            if j <= i:
                continue
            a, b = find(i), find(j)
            if a != b:
                parent[b] = a
            best[(i, j)] = float(block[bi, j])
    groups, low = {}, {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    for (i, _j), s in best.items():
        r = find(i)
        low[r] = min(low.get(r, 1.0), s)
    out = []
    for r, g in groups.items():
        if len(g) < 2:
            continue
        paths = [items[i]["path"] for i in g]
        out.append({"lane": items[g[0]]["lane"], "paths": paths, "lowest": round(low.get(r, 1.0), 4),
                    "folders": len({os.path.dirname(x) for x in paths})})
    # copies in different folders first: one picture filed under two pieces (frames of one shot share a folder)
    return sorted(out, key=lambda d: (d["folders"] < 2, -len(d["paths"]), d["paths"][0]))


def _opt(argv, key, default=None):
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


def main(argv, embed=None):
    sub = argv[0] if argv else ""
    root = _opt(argv, "--root", ".")
    vault = _opt(argv, "--vault", os.environ.get("KIT_VAULT_ROOT") or "kit/knowledge/vault")
    index_dir = _opt(argv, "--index", os.environ.get("KIT_LOOK_INDEX") or "build/look")
    lane = _opt(argv, "--lane")
    if sub == "index":
        st = build(embed, root, vault, index_dir, lane)
        by = ", ".join(f"{k} {n}" for k, n in st["by"].items())
        bad = f", {st['failed']} unreadable" if st["failed"] else ""
        return emit("pass", f"alike index: {st['pictures']} picture(s), {st['unique']} unique, {st['embedded']} newly "
                    f"embedded{bad} ({by})", "lune run kit alike <picture | piece>  /  lune run kit alike dupes", **st)
    meta, vecs = load(index_dir)
    if meta is None:
        return emit("fail", "alike: no index yet", "lune run kit alike index")
    if sub == "near":
        target = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None
        if not target:
            return emit("fail", "alike: which picture or piece?", "lune run kit alike <picture | piece>")
        q, piece, what, own = _query_vectors(target, meta, vecs, embed, root, "--cached" in argv)
        piece = _opt(argv, "--as", piece)  # a fresh picture of a known piece: its own older pictures stay out
        if q is None:
            return emit("pass", f"alike {what}: no picture of it in the index yet", "lune run kit alike index",
                        lines=[], rows=[], indexed=False)
        kinds = OURS + (("ref",) if "--refs" in argv else ())
        rows = near(meta, vecs, q, piece, lane, int(_opt(argv, "--k", "5")), kinds, verdicts(vault, moves_of(meta)),
                    skip_shas=own)
        lines = [r["line"] for r in rows]
        top = "; ".join(lines[:2]) if lines else "nothing to compare with"
        return emit("pass", f"alike {what}: {len(rows)} past piece(s) look closest - {top}",
                    "open the closest ones: copy what was loved (never its look: the originality rule), avoid what failed",
                    lines=lines, rows=rows, indexed=True)
    if sub == "round":
        move = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None
        if not move:
            return emit("fail", "alike round: which move?", "lune run kit anim picks <Move>")
        rnd = _opt(argv, "--round")
        if rnd is None:
            ks = [int(m.group(1)) for prefix, _g in _prefixes(root)
                  for d in glob.glob(os.path.join(root, prefix, "build", "candidates", move, "round_*"))
                  for m in [re.search(r"round_(\d+)$", d)] if m]
            rnd = str(max(ks)) if ks else "0"
        lines, rows = round_lines(meta, vecs, embed, root, move, rnd, verdicts(vault, moves_of(meta)))
        closer = sum(1 for r in rows if r["closer_to_rejected"])
        return emit("pass", f"alike round {move}/r{rnd}: {closer} of {len(rows)} candidate(s) look closer to a piece the "
                    "owner rejected than to one they loved (by look: a report, never a gate)",
                    "look at those candidates first - is it the rejected look again?" if closer else "none - proceed",
                    lines=lines, rows=rows)
    if sub == "dupes":
        kinds = OURS + ("ref",) if _opt(argv, "--kind", "ref") == "all" else ("ref",)
        groups = dupes(meta, vecs, lane, kinds, float(_opt(argv, "--min", str(DUP_MIN))))
        extra = sum(len(g["paths"]) - 1 for g in groups)
        across = sum(1 for g in groups if g["folders"] > 1)
        lines = [f"{g['lane']}: {len(g['paths'])} copies{' in ' + str(g['folders']) + ' folders' if g['folders'] > 1 else ''}"
                 f" (cosine >= {g['lowest']:.3f}): " + ", ".join(g["paths"][:4]) + (" ..." if len(g["paths"]) > 4 else "")
                 for g in groups]
        return emit("pass", f"alike dupes: {len(groups)} picture(s) filed more than once ({extra} extra file(s); "
                    f"{across} across folders)",
                    "keep one copy of each (the one the brief or dossier names) - none: proceed",
                    lines=lines[:50], groups=groups)
    return emit("fail", "alike: index | near <picture | piece> | dupes", "lune run kit alike index")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
