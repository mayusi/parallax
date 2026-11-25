"""clap.py — the sound library searched by DESCRIPTION (2026-11-08: proposal 11's SFX part, on the owner's yes - "Yes,
download it"). LAION CLAP (laion/larger_clap_general, Apache-2.0; pinned in kit/vision/models.json, fetched by
`lune run kit vision setup clap-general`) puts sounds and words in one space: every library sound is embedded once
(build/sfx_clap/, keyed by its content and trim), and a description ("a distant explosion rolling off", "wet footsteps
on stone") ranks them. The word search (kit/audio/sfxlib.py find) stays as it is; `find ... --describe` uses this.

  python kit/audio/clap.py index        embed what is new (a sound whose file is gone is left out, and counted)
  python kit/audio/clap.py find "<description>" [--n 12]
  python kit/audio/clap.py eval         the recorded descriptions (clap_eval.json): words alone vs CLAP vs --describe
Each prints one JSON line last."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.environ.get("KIT_SFX_CLAP") or os.path.join("build", "sfx_clap")
SR = 48000  # CLAP hears at 48 kHz
MAX_S = 10.0  # its window: a longer sound is heard from its start
BATCH = 16

_model = None
WEIGHTS = (".safetensors", ".bin", ".pt", ".pth", ".ckpt")


def unpinned_weights(folder, pinned):
    """weight files in the model's folder that are not among its pinned files: only the vetted weights load (a
    model.safetensors dropped in would be loaded before the checked pytorch_model.bin)"""
    return sorted(f for f in os.listdir(folder) if f.endswith(WEIGHTS) and f not in pinned)


def _load():
    """the pinned model (kit/vision/run.py ensure: every file checked against its vetted pin) on the GPU if any"""
    global _model
    if _model is None:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "vision"))
        import run as V  # noqa: PLC0415

        folder = V.ensure("clap-general")
        extra = unpinned_weights(folder, {f["path"] for f in V._manifest()["clap-general"]["files"]})
        if extra:
            raise RuntimeError(f"clap-general: unpinned weight file(s) {extra} in {folder} - remove them")
        from transformers import ClapModel, ClapProcessor  # noqa: PLC0415

        torch, dev = V._torch()
        model = ClapModel.from_pretrained(folder).to(dev).eval()
        _model = (torch, dev, model, ClapProcessor.from_pretrained(folder))
    return _model


def _unit(e):
    e = np.asarray(e, dtype=np.float32)
    return e / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)


# (the embeddings are the towers' pooled outputs through their projections, exactly as ClapModel.forward builds
#  audio_embeds / text_embeds - checked identical on 2026-11-08. CLAP itself scores some true pairs low: a carpet
#  footstep against "footsteps on a carpet" sits near 0 - see `clap.py eval` for what it finds and misses)
def embed_audio(arrays):
    """mono 48 kHz float arrays -> unit vectors (n, d) in the shared sound-text space"""
    torch, dev, model, proc = _load()
    with torch.no_grad():
        try:
            inp = proc(audio=list(arrays), sampling_rate=SR, return_tensors="pt")
        except TypeError:
            inp = proc(audios=list(arrays), sampling_rate=SR, return_tensors="pt")
        out = model.audio_model(**{k: v.to(dev) for k, v in inp.items()})
        e = model.audio_projection(out.pooler_output)
    return _unit(e.float().cpu().numpy())


def embed_text(texts):
    torch, dev, model, proc = _load()
    with torch.no_grad():
        inp = proc(text=list(texts), return_tensors="pt", padding=True)
        out = model.text_model(**{k: v.to(dev) for k, v in inp.items()})
        e = model.text_projection(out.pooler_output)
    return _unit(e.float().cpu().numpy())


def decode(path, trim=None):
    """a sound as mono 48 kHz floats, its trim [start, end] seconds applied, at most MAX_S long"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    if isinstance(trim, (list, tuple)) and len(trim) == 2:
        x = x[int(float(trim[0]) * SR): int(float(trim[1]) * SR)]
    return x[: int(MAX_S * SR)]


def _key(path, trim):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    h.update(json.dumps(trim).encode())
    return h.hexdigest()[:16]


def load(index_dir=None):
    d = index_dir or INDEX_DIR
    try:
        with open(os.path.join(d, "index.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        vecs = np.load(os.path.join(d, "vectors.npy"))
    except (OSError, ValueError):
        return None, None
    return (meta, vecs) if len(meta.get("rows", {})) == len(vecs) else (None, None)


def build(entries, index_dir=None, embed=None, decoder=None):
    """embed the library sounds that are new (by content + trim); a sound whose file is gone is left out -> stats"""
    d = index_dir or INDEX_DIR
    embed = embed or embed_audio
    decoder = decoder or decode
    meta, vecs = load(d)
    old_rows = (meta or {}).get("rows", {})
    ids, need, missing, failed = {}, [], 0, 0
    for e in entries:
        p = e.get("file") or ""
        if not os.path.isfile(p):
            missing += 1
            continue
        trim = e.get("trim") if isinstance(e.get("trim"), (list, tuple)) else None
        k = _key(p, trim)
        ids[e["id"]] = k
        if k not in old_rows:
            need.append((k, p, trim))
    new = {}
    todo = list({k: (p, t) for k, p, t in need}.items())
    for i in range(0, len(todo), BATCH):
        chunk, arrays, keys = todo[i:i + BATCH], [], []
        for k, (p, t) in chunk:
            try:
                x = decoder(p, t)
                if len(x) < SR // 20:  # under 50 ms: nothing to hear
                    raise ValueError("too short")
                arrays.append(x)
                keys.append(k)
            except Exception:  # noqa: BLE001 - an undecodable sound is left out, counted
                failed += 1
        if arrays:
            for k, v in zip(keys, embed(arrays)):
                new[k] = v
    used = sorted({k for k in ids.values() if k in old_rows or k in new})
    dim = vecs.shape[1] if vecs is not None and len(vecs) else (len(next(iter(new.values()))) if new else 0)
    out = np.zeros((len(used), dim), dtype=np.float16)
    rows = {}
    for i, k in enumerate(used):
        out[i] = new[k] if k in new else vecs[old_rows[k]]
        rows[k] = i
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "vectors.tmp.npy"), out)
    with open(os.path.join(d, "index.json.tmp"), "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "model": "clap-general", "rows": rows,
                   "ids": {i: k for i, k in ids.items() if k in rows}}, fh)
    os.replace(os.path.join(d, "vectors.tmp.npy"), os.path.join(d, "vectors.npy"))
    os.replace(os.path.join(d, "index.json.tmp"), os.path.join(d, "index.json"))
    return {"sounds": len(rows), "embedded": len(new), "missing": missing, "failed": failed}


def search(query, entries, n=12, index_dir=None, embed=None):
    """the library sounds whose sound is closest to the description -> [(similarity, entry)]"""
    meta, vecs = load(index_dir)
    if meta is None:
        return None
    q = (embed or embed_text)([query])[0]
    sims = vecs.astype(np.float32) @ q
    scored = []
    for e in entries:
        k = meta["ids"].get(e["id"])
        if k is not None and k in meta["rows"]:
            scored.append((round(float(sims[meta["rows"][k]]), 3), e))
    scored.sort(key=lambda p: (-p[0], p[1]["id"]))
    return scored[:n]


EVAL = os.path.join(HERE, "clap_eval.json")
BONUSES = (0.05, 0.1, 0.15, 0.25)  # the word lifts the eval tries beside CLAP alone (sfxlib.WORD_BONUS is the one used)


def evaluate(entries, cases, index_dir=None, embed=None, sources=None):
    """the recorded descriptions ranked by the plain word search (sfx find), by CLAP alone and by CLAP lifted by the
    sound's name at each lift in BONUSES (sfx find --describe), over the sounds CLAP has heard (a sound whose file is
    gone answers nothing). A description is `shared` when the word search finds any sound for it, else `unshared` (only
    CLAP can answer it) - measured, so a library that loses or gains sounds moves it. Right at top-1 / top-5: that many
    first sounds hold one whose id matches its `want`
    -> {"heard", "unheard", "groups": {group: {way: [top1, top5, descriptions]}}, "lines", "left_out"}, None (no index)"""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import sfxlib as L  # noqa: PLC0415

    meta, _vecs = load(index_dir)
    if meta is None:
        return None
    if sources is None:
        sources = L.load().get("sources", {})
    heard = [e for e in entries if e["id"] in meta["ids"]]
    lifts = [("clap", 0.0)] + [(f"clap+{b:g}", b) for b in sorted(set(BONUSES) | {L.WORD_BONUS})]
    ways = ["words"] + [w for w, _b in lifts]
    groups = {g: {w: [0, 0, 0] for w in ways} for g in ("shared", "unshared")}
    lines, left_out = [], []
    for c in cases:
        rx = re.compile(c["want"])
        if not any(rx.search(e["id"]) for e in heard):
            left_out.append(c["q"])  # no right sound left in the library: it measures nothing
            continue
        got = search(c["q"], heard, len(heard), index_dir, embed)
        orders = {"words": [e["id"] for _s, e in L.word_rank(c["q"], heard)]}
        for w, b in lifts:
            orders[w] = [e["id"] for _s, e in L.describe_rank(c["q"], heard, b, got, sources)]
        group = "shared" if orders["words"] else "unshared"
        marks = []
        for w in ways:
            ids = orders[w]
            t1, t5 = bool(ids and rx.search(ids[0])), any(rx.search(i) for i in ids[:5])
            groups[group][w][0] += int(t1)
            groups[group][w][1] += int(t5)
            groups[group][w][2] += 1
            marks.append(f"{w}:{'1' if t1 else ('5' if t5 else '-')}")
        pick = L.describe_rank(c["q"], heard, None, got, sources)[0][1]["id"]
        lines.append(f"{group:8} {c['q']:<30} {' '.join(marks)}  --describe's first: {pick}")
    return {"heard": len(heard), "unheard": len(entries) - len(heard), "groups": groups, "lines": lines,
            "left_out": left_out}


def main(argv):
    sys.path.insert(0, HERE)
    import sfxlib as L  # noqa: PLC0415  (the library index)

    entries = list(L.load()["entries"].values())
    sub = argv[0] if argv else ""
    if sub == "index":
        st = build(entries)
        gone = f"; {st['missing']} sound(s) whose file is gone left out" if st["missing"] else ""
        print(json.dumps({"schema": 1, "status": "pass",
                          "summary": f"sfx clap index: {st['sounds']} sound(s), {st['embedded']} newly embedded{gone}"
                                     + (f", {st['failed']} undecodable" if st["failed"] else ""),
                          "next_action": 'lune run kit sfx find "<a description>" --describe', **st}))
        return 0
    if sub == "find":
        words = " ".join(a for a in argv[1:] if not a.startswith("--"))
        hits = search(words, entries, 12)
        if hits is None:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "sfx describe: no CLAP index yet",
                              "next_action": "lune run kit sfx clap index"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"{len(hits)} sound(s) closest to \"{words}\"",
                          "next_action": "audition them", "hits": [{"id": e["id"], "score": s} for s, e in hits]}))
        return 0
    if sub == "eval":
        with open(EVAL, encoding="utf-8") as fh:
            r = evaluate(entries, json.load(fh)["cases"])
        if r is None:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "sfx clap eval: no CLAP index yet",
                              "next_action": "lune run kit sfx clap index"}))
            return 1
        for line in r["lines"]:
            print(line)
        use = f"clap+{L.WORD_BONUS:g}"

        def part(g):
            t = r["groups"][g]
            n = t["words"][2]
            return (f"{g} ({n}): top-1 words {t['words'][0]}, CLAP {t['clap'][0]}, --describe {t[use][0]}; top-5 "
                    f"words {t['words'][1]}, CLAP {t['clap'][1]}, --describe {t[use][1]}")

        print(json.dumps({"schema": 1, "status": "pass",
                          "summary": f"sfx clap eval over {r['heard']} heard sound(s) ({r['unheard']} not heard: file gone or undecodable): "
                                     + "; ".join(part(g) for g in ("shared", "unshared"))
                                     + (f"; left out (no right sound): {r['left_out']}" if r["left_out"] else ""),
                          "next_action": "a right sound is one whose id matches the query's `want` "
                                         "(kit/audio/clap_eval.json) - a proxy; listen before trusting a pick",
                          **{k: v for k, v in r.items() if k != "lines"}}))
        return 0
    print(json.dumps({"schema": 1, "status": "fail", "summary": "clap: index | find \"<description>\" | eval",
                      "next_action": "lune run kit sfx clap index"}))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
