"""library.py — the local library of REAL recordings: index a folder once, then find sounds by words or by ear.

Usage:
  python kit/audio/sfxlib.py index <dir> --licence <CC0|royalty-free|own|measure-only> [--source <name>] [--split]
  python kit/audio/sfxlib.py find "<words>" [--n 12] [--like <file|name>] [--licence CC0,own]
  (normally: lune run kit sfx index <dir> --licence CC0 / lune run kit sfx find "heavy metal clang")
index: every audio file under <dir> (wav/ogg/flac/mp3) is measured (kit/audio/ears.py) and described in words
  from its path ("Kenney/impact/metal_heavy_003.ogg" -> impact, metal, heavy) and its ears (short / long, bright /
  dark, punchy, sub, airy, a hit / a rattle / a texture). --split cuts long files into single events at silences
  (each event an entry with its own trim). The licence is REQUIRED and recorded per entry: "measure-only" entries
  (ripped references: SAM Audio separations, game clips) can be found and matched against but never used as
  layers in a shipped sound (synth refuses a lib:<id> sample whose licence is measure-only).
find: words score against each entry's words; --like ranks by ears distance to a sound instead.
  Each result: id (use as "sample": "lib:<id>" in a recipe), file, trim, licence, words, the main numbers.
Index: library/sfx/index.json (paths are as given: the recordings stay where they are; big packs stay out of git).
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402

INDEX = os.environ.get("KIT_SFX_INDEX") or os.path.join("library", "sfx", "index.json")  # (env: tests use a scratch index)
EXTS = (".wav", ".ogg", ".flac", ".mp3")
LICENCES = ("CC0", "royalty-free", "own", "measure-only")
STOP = {"sfx", "sound", "sounds", "audio", "the", "and", "of", "a", "an", "fx", "wav", "ogg", "mp3", "flac", "v", "var"}


def load():
    if os.path.isfile(INDEX):
        with open(INDEX, encoding="utf-8") as fh:
            return json.load(fh)
    return {"entries": {}, "sources": {}}


def save(idx):
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    with open(INDEX, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(idx, fh, indent=1)


def path_of(entry_id):
    """lib:<id> -> a playable file (for synth). Measure-only entries are refused: they are references, not parts."""
    e = load()["entries"].get(entry_id)
    if not e:
        raise ValueError(f"lib:{entry_id} is not in {INDEX} (find one: lune run kit sfx find \"<words>\")")
    if e["licence"] == "measure-only":
        raise ValueError(f"lib:{entry_id} is measure-only ({e.get('source')}): match against it, never ship it as a layer")
    if e.get("trim"):
        return _trimmed(e)
    return e["file"]


def _trimmed(e):
    """An event cut from a longer file: rendered once to build/sounds/lib/<id>.wav."""
    out = os.path.join("build", "sounds", "lib", f"{e['id']}.wav")
    if not os.path.isfile(out):
        import shutil
        import subprocess

        os.makedirs(os.path.dirname(out), exist_ok=True)
        a, b = e["trim"]
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", str(a), "-to", str(b), "-i", e["file"], "-ac", "1", out], check=True)
    return out


def path_words(path):
    stem = os.path.splitext(path.replace("\\", "/"))[0]
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)  # camelCase packs (Kenney: impactMetal_heavy) -> impact metal
    toks = re.split(r"[^a-zA-Z]+", stem.lower())
    return sorted({t for t in toks if len(t) > 2 and t not in STOP})


def ear_words(e):
    w = []
    w.append("short" if e["duration_s"] < 0.4 else "long" if e["duration_s"] > 2.0 else "medium")
    w.append("bright" if e["brightness_hz"] > 3000 else "dark" if e["brightness_hz"] < 400 else "mid")
    if e["crest_db"] >= 16:
        w.append("punchy")
    if e["sub_share"] >= 0.3:
        w += ["sub", "boomy"]
    if e["high_share"] >= 0.4:
        w += ["airy", "hiss"]
    if e["onsets"] == 1 and e["transient_ms"] <= 5:
        w += ["hit", "impact"]
    elif e["onsets"] >= 4:
        w += ["rattle", "burst"]
    if e["tail_ms"] >= 1200:
        w += ["ring", "tail"]
    if e["onsets"] <= 1 and e["transient_ms"] > 40:
        w += ["swell", "whoosh"]
    return w


def split_events(x, sr, min_gap=0.12, floor_db=-45):
    """Cut a long recording into events at silences of min_gap or more below floor_db (under its own peak)."""
    import numpy as np

    hop = int(0.01 * sr)
    n = len(x) // hop
    if n < 2:
        return [(0.0, len(x) / sr)]
    env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    edb = 20 * np.log10(env + 1e-9)
    on = edb > edb.max() + floor_db
    events, start, quiet = [], None, 0
    for i, v in enumerate(on):
        if v:
            if start is None:
                start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet * hop / sr >= min_gap:
                events.append((start, i - quiet + 1))
                start, quiet = None, 0
    if start is not None:
        events.append((start, n))
    return [(max(0, a - 1) * hop / sr, min(n, b + 2) * hop / sr) for a, b in events if (b - a) * hop / sr >= 0.03]


def index(folder, licence, source, split):
    if licence not in LICENCES:
        return {"status": "fail", "summary": f"licence {licence!r} unknown", "next_action": f"--licence one of {', '.join(LICENCES)} (vet the pack first: kit-vet + VETLOG.md)"}
    idx = load()
    files = []
    for root, _, names in os.walk(folder):
        for f in sorted(names):
            if f.lower().endswith(EXTS):
                files.append(os.path.join(root, f).replace("\\", "/"))
    added = 0
    for f in files:
        try:
            x, sr = E.decode(f)
        except Exception:  # noqa: BLE001 — one broken file never stops an index
            continue
        spans = split_events(x, sr) if split and len(x) / sr > 2.5 else [None]
        for k, span in enumerate(spans):
            seg = x if span is None else x[int(span[0] * sr) : int(span[1] * sr)]
            if len(seg) < sr * 0.02:
                continue
            e = E.measure(seg, sr)
            base = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.relpath(f, folder))[0].lower()).strip("_")
            eid = f"{(source or os.path.basename(os.path.normpath(folder))).lower()}.{base}" + (f".{k + 1}" if span else "")
            idx["entries"][eid] = {
                "id": eid, "file": f, "trim": [round(span[0], 3), round(span[1], 3)] if span else None,
                "licence": licence, "source": source or os.path.basename(os.path.normpath(folder)),
                "words": sorted(set(path_words(os.path.relpath(f, folder)) + ear_words(e))), "ears": e,
            }
            added += 1
    idx["sources"][source or os.path.basename(os.path.normpath(folder))] = {"folder": folder.replace("\\", "/"), "licence": licence, "indexed": time.strftime("%Y-%m-%d"), "entries": added}
    save(idx)
    return {"status": "pass", "summary": f"indexed {added} sound(s) from {len(files)} file(s) in {folder} ({licence}); library has {len(idx['entries'])}",
            "next_action": 'find: lune run kit sfx find "<words>"', "added": added}


SWITCHES = {"--describe", "--split"}  # flags that never take a value
WORD_BONUS = 0.15  # --describe: each point a description scores on a sound's NAME (2 = a name word) lifts CLAP's similarity
# (`lune run kit sfx clap eval`, 2026-11-08, over all 603 library sounds, heard since the lost files were restored. 8
#  descriptions the word search answers: a right sound first for words alone 6, CLAP alone 3, lifted +0.05 4, +0.1 5,
#  +0.15 6, +0.25 6; top five 7, 5, and 7 at every lift. Every first place of a lift is a first place of the words too;
#  from +0.15 they are the same six. All miss "footsteps on a wooden floor": shell-casing takes that "roll on Wooden
#  Floor" win on the name, CLAP alone picks other footsteps. 4 descriptions the word search cannot answer: CLAP puts a
#  right sound first 2 times at every lift, top five 3. +0.15 is the smallest lift with the most first places here; 12
#  descriptions is a thin measure - add a description that missed in real use to kit/audio/clap_eval.json)


def terms(words):
    """a query's words as the searches read them (lower case, the stop words out)"""
    return [t for t in re.split(r"[^a-z]+", (words or "").lower()) if t and t not in STOP]


def _hits(ws, q):
    """2 per query word that is one of the words, 1 per one sharing a start with one longer than 3 letters"""
    return sum(2.0 if t in ws else (1.0 if any(w.startswith(t) or t.startswith(w) for w in ws if len(w) > 3) else 0.0)
               for t in q)


def word_score(e, q):
    """the plain word search's score: all of a sound's words - its name's and the ear's descriptors (long, dark...)"""
    return _hits(set(e["words"]), q)


def name_words(e, sources):
    """the words a sound's own file name (and its folders inside its pack) give it, as `index` made them - its words
    without the ear's descriptors"""
    folder = ((sources or {}).get(e.get("source")) or {}).get("folder")
    try:
        rel = os.path.relpath(e["file"], folder) if folder else os.path.basename(e["file"])
    except ValueError:  # (another drive)
        rel = os.path.basename(e["file"])
    own = set(e["words"])
    return [w for w in path_words(rel) if w in own]


def word_rank(words, entries):
    """`sfx find "<words>"`'s order: the sounds a word hits, best first -> [(score, entry)]"""
    q = terms(words)
    scored = [(s, e) for s, e in ((word_score(e, q), e) for e in entries) if s > 0]
    scored.sort(key=lambda p: (-p[0], p[1]["id"]))
    return scored


def describe_rank(words, entries, bonus=None, got=None, sources=None):
    """`sfx find "<a description>" --describe`'s order: CLAP's closeness of each sound to the words (kit/audio/clap.py),
    lifted by `bonus` (WORD_BONUS) per point the description scores on the sound's NAME -> [(score, entry)] over the
    sounds CLAP has heard, None with no CLAP index. Only the name lifts: the ear's descriptors (long, dark, whoosh,
    impact) are what CLAP hears itself, and lifting them lifted every long or dark sound. `got`: CLAP's own
    [(similarity, entry)] when already searched; `sources`: the index's sources (their folders give the names)"""
    import clap as C  # noqa: PLC0415

    got = C.search(words, entries, len(entries)) if got is None else got
    if got is None:
        return None
    if sources is None:
        sources = load().get("sources", {})
    q, b = terms(words), (WORD_BONUS if bonus is None else bonus)
    return sorted(((round(sim + b * _hits(set(name_words(e, sources)), q), 3), e) for sim, e in got),
                  key=lambda p: (-p[0], p[1]["id"]))


def find(words, n, like, licences, describe=False):
    idx = load()
    entries = list(idx["entries"].values())
    if licences:
        entries = [e for e in entries if e["licence"] in licences]
    if not entries:
        return {"status": "fail", "summary": f"the library is empty ({INDEX})", "next_action": "index recordings first: lune run kit sfx index <dir> --licence CC0 --source <pack>"}
    unheard = ""
    if describe:
        # by DESCRIPTION (kit/audio/clap.py: LAION CLAP, the owner's yes 2026-11-08): the sound's closeness to the words,
        # lifted a little by the words of its own name ("explosion" names magic_explosion; CLAP alone put a
        # sheltered-wind gust first)
        ranked = describe_rank(words, entries, sources=idx.get("sources", {}))
        if ranked is None:
            return {"status": "fail", "summary": "sfx find --describe: no CLAP index yet",
                    "next_action": "lune run kit vision setup clap-general (once), then: lune run kit sfx clap index"}
        if len(entries) > len(ranked):  # a sound whose file is gone (or added since the index) is never offered
            unheard = (f"; {len(entries) - len(ranked)} sound(s) CLAP has not heard (file gone, or new since: "
                       "lune run kit sfx clap index)")
        scored = ranked[:n]
    elif like:
        f = like if os.path.isfile(like) else os.path.join("build", "sounds", f"{like}.ogg")
        target = E.measure(E.decode(f)[0])
        ranked = sorted(entries, key=lambda e: E.distance(e["ears"], target))
        scored = [(round(E.distance(e["ears"], target), 2), e) for e in ranked[:n]]
    else:
        scored = word_rank(words, entries)[:n]
    hits = [{"id": e["id"], "score": s, "file": e["file"], "trim": e["trim"], "licence": e["licence"], "words": e["words"],
             "lufs": e["ears"]["lufs"], "brightness_hz": e["ears"]["brightness_hz"], "tail_ms": e["ears"]["tail_ms"]} for s, e in scored]
    for h in hits:
        print(f"  {h['id']:<48} {h['licence']:<13} {h['lufs']:>6} LUFS {h['brightness_hz']:>6} Hz tail {h['tail_ms']:>5} ms  {' '.join(h['words'][:8])}")
    if not hits:
        return {"status": "pass", "summary": f'nothing matches "{words}" in {len(entries)} sound(s){unheard}', "next_action": "try other words, or --like <a sound> to rank by ear", "hits": []}
    return {"status": "pass", "summary": f"{len(hits)} match(es) of {len(entries)}{unheard}", "hits": hits,
            "next_action": f'use one as a layer: {{"role": "body", "sample": "lib:{hits[0]["id"]}"}} (or audition: lune run kit sfx sheet {hits[0]["file"]})'}


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage", "next_action": __doc__.splitlines()[2].strip()}))
        return 1
    cmd, rest = argv[0], argv[1:]
    opts, pos = {}, []
    i = 0
    while i < len(rest):
        if rest[i] in SWITCHES:  # a switch never takes the next word ("find --describe a distant explosion" keeps its order)
            opts[rest[i][2:]] = True
            i += 1
        elif rest[i].startswith("--"):
            key = rest[i][2:]
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                opts[key] = rest[i + 1]
                i += 2
            else:
                opts[key] = True
                i += 1
        else:
            pos.append(rest[i])
            i += 1
    if cmd == "index":
        if not pos or not os.path.isdir(pos[0]):
            r = {"status": "fail", "summary": f"no folder {pos[:1]}", "next_action": "lune run kit sfx index <dir> --licence CC0 --source <pack>"}
        elif "licence" not in opts:
            r = {"status": "fail", "summary": "--licence is required", "next_action": f"--licence one of {', '.join(LICENCES)}"}
        else:
            r = index(pos[0], opts["licence"], opts.get("source"), bool(opts.get("split")))
    elif cmd == "find":
        lic = opts.get("licence")
        if opts.get("describe") and not " ".join(pos).strip():
            print(json.dumps({"status": "fail", "summary": "sfx find --describe: describe the sound in words",
                              "next_action": 'lune run kit sfx find "a distant explosion rolling off" --describe'}))
            return 1
        if opts.get("describe") and opts.get("like"):
            print(json.dumps({"status": "fail", "summary": "sfx find: --describe (by words) or --like (by a sound), not both",
                              "next_action": 'lune run kit sfx find "<a description>" --describe'}))
            return 1
        r = find(" ".join(pos), int(opts.get("n", 12)), opts.get("like"), lic.split(",") if isinstance(lic, str) else None,
                 describe=bool(opts.get("describe")))
    else:
        r = {"status": "fail", "summary": f"unknown {cmd}", "next_action": "index | find"}
    print(json.dumps(r))
    return 0 if r["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
