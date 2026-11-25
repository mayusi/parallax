"""taste.py — a taste model per lane, learned from the owner's OWN scores on our own pieces (2026-11-08, sprint 5:
proposal 9 of board/plans/archive/2026-11-08-pipeline-rag-learning-research.md).

What it is: the nearest pieces the owner scored, by look (the SigLIP 2 vectors of the look index, kit/vision/alike.py),
weighted by how alike they are - "it looks like the ones you gave 9". Never a guessed number (`source: inferred`),
never the library's picks (the originality rule: our look is never pulled toward the library's).
How far to trust it: every scored piece is predicted from the OTHERS (leave-one-out), and the model reports how often
it orders two pieces the way the owner did (pairwise agreement; chance = 50%) and the rank correlation. It is ON only
when the lane has MIN_N scored pieces with a picture and orders pairs the owner's way at least MIN_PAIRWISE of the
time - and the owner can switch it off (`kit taste off <lane>`). It only ORDERS candidates: a report, never a gate.

  python kit/vision/run.py taste train <lane>
  python kit/vision/run.py taste order <lane> <Move/rK | picture | piece ...>
  python kit/vision/run.py taste off|on <lane>
  (--root R, --vault V, --index I: other folders, for tests)
The record (kit/knowledge/vault/<lane>/taste.json) keeps the agreement, the switch and the pieces it learned from."""

import glob
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import alike as A  # noqa: E402  (the look index, the owner's verdicts, the candidates of a round)

MIN_N = 20  # scored pieces with a picture before the model may order anything
MIN_PAIRWISE = 0.6  # and it must order pairs the owner's way this often (chance is 0.5)
K = 5  # the nearest scored pieces a prediction weighs
SHARP = 8.0  # weight = similarity ** SHARP: the nearest count most


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def labelled(meta, vecs, vault, lane):
    """the lane's pieces the owner scored THEMSELVES (a number; their newest own note) that have a picture ->
    [(piece, score, unit vector: the mean of its pictures)]"""
    vd = A.verdicts(vault, A.moves_of(meta), owner_only=True)
    rows = {}
    for e in meta["entries"]:
        if e["lane"] == lane and e["kind"] in A.OURS:
            rows.setdefault(e["piece"], set()).add(meta["rows"][e["sha"]])
    out = []
    for piece, rs in sorted(rows.items()):
        v = A.verdict_of(vd, lane, piece, move_level=False)
        try:
            score = float(v["score"]) if v and v.get("score") not in (None, "") else None
        except ValueError:
            score = None
        if score is None:
            continue
        m = vecs[sorted(rs)].astype(np.float32).mean(axis=0)
        out.append((piece, score, m / max(float(np.linalg.norm(m)), 1e-9)))
    return out


def predict(q, X, y, k=K):
    """the score the nearest scored pieces give a picture -> (score, their indexes, nearest first)"""
    sims = X @ q
    idx = np.argsort(-sims)[:k]
    w = np.maximum(sims[idx], 0.0) ** SHARP + 1e-9
    return float((w * y[idx]).sum() / w.sum()), idx


def _ranks(a):
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a), dtype=np.float64)
    r[order] = np.arange(len(a), dtype=np.float64)
    for v in np.unique(a):  # ties share their mean rank
        m = a == v
        r[m] = r[m].mean()
    return r


LOOKS_SAME = 0.95  # two pictures this alike (frames of one shot sit 0.95+: kit/vision/alike.py) - no look tells them apart
MIN_PAIRS = 10  # pairs of different looks before an agreement means anything


def agreement(y, pred, X=None):
    """(pairwise: how often two pieces of different scores are ordered the owner's way - a predicted tie counts half;
    spearman: the rank correlation). With X (their unit vectors), only pairs whose pictures DIFFER count: between two
    near-identical looks a leave-one-out average orders backwards by construction (each is predicted from the other),
    and no look can tell them apart - a pick round's candidates of one move are mostly such pairs"""
    good = total = 0.0
    for i in range(len(y)):
        for j in range(i + 1, len(y)):
            if y[i] == y[j] or (X is not None and float(X[i] @ X[j]) >= LOOKS_SAME):
                continue
            total += 1
            d = (pred[i] - pred[j]) * (y[i] - y[j])
            good += 1.0 if d > 0 else (0.5 if d == 0 else 0.0)
    ry, rp = _ranks(np.asarray(y, dtype=np.float64)), _ranks(np.asarray(pred, dtype=np.float64))
    sd = float(np.std(ry) * np.std(rp))
    spearman = float(np.mean((ry - ry.mean()) * (rp - rp.mean())) / sd) if sd > 0 else 0.0
    return (good / total if total else 0.5), spearman, int(total)


PERMUTATIONS = 200  # shuffles of the owner's scores the real agreement must beat
MAX_P = 0.05  # at most this share of shuffles may do as well


def loo_structure(X, k=K):
    """each piece's k nearest OTHER scored pieces and their weights (the prediction without itself)"""
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    kk = max(1, min(k, len(X) - 1))
    idx = np.argsort(-S, axis=1)[:, :kk]
    w = np.maximum(np.take_along_axis(S, idx, axis=1), 0.0) ** SHARP + 1e-9
    return idx, w


def loo_predict(idx, w, y):
    return (w * y[idx]).sum(axis=1) / w.sum(axis=1)


def _fast_pairwise(y, pred, differ):
    """agreement()'s pairwise on the pairs `differ` marks (upper triangle), as arrays: for the shuffle test"""
    dy = y[:, None] - y[None, :]
    prod = (pred[:, None] - pred[None, :]) * dy
    m = differ & (dy != 0)
    total = int(m.sum())
    if not total:
        return 0.5
    return float(((prod > 0) & m).sum() + 0.5 * ((prod == 0) & m).sum()) / total


def train(meta, vecs, vault, lane, k=K):
    """leave-one-out over the owner's scored pieces -> the record (never written here)"""
    data = labelled(meta, vecs, vault, lane)
    n = len(data)
    rec = {"lane": lane, "n": n, "k": k, "min_n": MIN_N, "min_pairwise": MIN_PAIRWISE,
           "pieces": [p for p, _s, _v in data]}
    if n < 3:
        rec.update(pairwise=None, spearman=None, enabled=False,
                   why=f"{n} piece(s) the owner scored with a picture - too few to test (needs {MIN_N})")
        return rec
    X = np.stack([v for _p, _s, v in data])
    y = np.array([s for _p, s, _v in data], dtype=np.float64)
    idx, w = loo_structure(X, k)
    pred = loo_predict(idx, w, y)
    pairwise, spearman, pairs = agreement(y, pred, X)
    every, _sp, _all = agreement(y, pred)
    # could shuffled scores do as well? the same pictures, the owner's scores dealt at random PERMUTATIONS times (a
    # fixed seed: the same record on the same data) - noise alone passes the 60% bar about one time in twenty
    differ = np.triu(X @ X.T < LOOKS_SAME, 1)
    rng = np.random.default_rng(1000 + n)
    beat = sum(1 for _ in range(PERMUTATIONS)
               if _fast_pairwise(yp := rng.permutation(y), loo_predict(idx, w, yp), differ) >= pairwise)
    p_value = (1 + beat) / (1 + PERMUTATIONS)
    rec.update(pairwise=round(pairwise, 3), spearman=round(spearman, 3), pairs=pairs, pairwise_all=round(every, 3),
               p_value=round(p_value, 3))
    if n < MIN_N:
        rec.update(enabled=False, why=f"{n} piece(s) the owner scored with a picture (needs {MIN_N})")
    elif pairs < MIN_PAIRS:
        rec.update(enabled=False, why=f"{pairs} pair(s) of different looks to test on (needs {MIN_PAIRS})")
    elif pairwise < MIN_PAIRWISE:
        rec.update(enabled=False, why=f"orders pairs the owner's way {pairwise:.0%} of the time (needs {MIN_PAIRWISE:.0%})")
    elif p_value > MAX_P:
        rec.update(enabled=False, why=f"orders pairs the owner's way {pairwise:.0%}, but shuffled scores do as well "
                                      f"(p {p_value:.2f}, needs {MAX_P})")
    else:
        rec.update(enabled=True, why=f"orders pairs the owner's way {pairwise:.0%} of the time on {n} pieces "
                                     f"(shuffled scores: p {p_value:.3f})")
    return rec


def record_path(vault, lane):
    return os.path.join(vault, lane, "taste.json")


def load_record(vault, lane):
    try:
        with open(record_path(vault, lane), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_record(vault, lane, rec):
    """written only when something but the date changed (no churn line in git after every run)"""
    old = load_record(vault, lane) or {}
    keep_off = bool(old.get("off"))
    rec = {**rec, "off": keep_off}
    same = {k: v for k, v in old.items() if k != "trained"} == {k: v for k, v in rec.items() if k != "trained"}
    if same:
        return False
    os.makedirs(os.path.dirname(record_path(vault, lane)), exist_ok=True)
    with open(record_path(vault, lane), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return True


def status_line(rec):
    if not rec:
        return None
    if rec.get("off"):
        return f"taste model: switched off by the owner (kit taste on {rec['lane']})"
    if rec.get("enabled"):
        return (f"taste model: orders candidates - agrees with the owner on {rec['pairwise']:.0%} of pairs "
                f"(leave-one-out, {rec['n']} scored pieces; kit taste off {rec['lane']})")
    return f"taste model: off - {rec.get('why')}"


def _targets(meta, vecs, embed, root, target):
    """what to order -> [(label, vector)]: the candidates of a round "<Move>/rK" (a bare move with pick rounds: its
    newest round), else a picture, else a piece"""
    m = re.match(r"^(.+?)/r(\d+)$", target)
    if not m:
        ks = [int(mm.group(1)) for prefix, _g in A._prefixes(root)
              for d in glob.glob(os.path.join(root, prefix, "build", "candidates", target, "round_*"))
              for mm in [re.search(r"round_(\d+)$", d)] if mm]
        if ks:
            m = re.match(r"^(.+?)/r(\d+)$", f"{target}/r{max(ks)}")
    if m:
        files = []
        for prefix, _g in A._prefixes(root):
            files += glob.glob(os.path.join(root, prefix, "build", "candidates", m.group(1), f"round_{m.group(2)}", "c*.gif"))
        out = []
        for p in sorted(files, key=lambda f: int(re.sub(r"\D", "", os.path.basename(f)) or 0)):
            sha = A._sha(p)
            if sha in meta["rows"]:
                v = vecs[meta["rows"][sha]].astype(np.float32)
            elif embed is not None:
                v = np.asarray(embed([A._picture(p)]), dtype=np.float32)[0]
            else:
                continue
            out.append((f"{m.group(1)}/r{m.group(2)}/{os.path.splitext(os.path.basename(p))[0]}", v))
        return out
    q, piece, _what, _own = A._query_vectors(target, meta, vecs, embed, root, False)
    if q is None:
        return []
    v = q.mean(axis=0)
    # (a picture of a scored piece is that piece: it never predicts itself)
    return [(piece or target, v / max(float(np.linalg.norm(v)), 1e-9))]


def order(meta, vecs, vault, lane, items, rec):
    """[(label, vector)] -> rows by predicted score, each with the scored pieces it leans on"""
    data = labelled(meta, vecs, vault, lane)
    if not data:
        return []
    X = np.stack([v for _p, _s, v in data])
    y = np.array([s for _p, s, _v in data], dtype=np.float64)
    rows = []
    for label, q in items:
        keep = np.array([p.lower() != label.lower() for p, _s, _v in data])  # a scored piece never predicts itself
        if not keep.any():
            continue
        score, idx = predict(q, X[keep], y[keep], rec.get("k") or K)
        names = [p for (p, _s, _v), k_ in zip(data, keep) if k_]
        ys = y[keep]
        near = [f"{names[i]} {ys[i]:g}" for i in idx[:2]]
        rows.append({"item": label, "predicted": round(score, 2), "nearest": near})
    rows.sort(key=lambda r: -r["predicted"])
    return rows


def _opt(argv, key, default=None):
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


def main(argv, embed=None):
    sub = argv[0] if argv else ""
    lane = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None
    root = _opt(argv, "--root", ".")
    vault = _opt(argv, "--vault", os.environ.get("KIT_VAULT_ROOT") or "kit/knowledge/vault")
    index_dir = _opt(argv, "--index", os.environ.get("KIT_LOOK_INDEX") or "build/look")
    if sub not in ("train", "order", "off", "on") or not lane:
        return emit("fail", "taste: train <lane> | order <lane> <Move/rK | picture | piece ...> | off <lane> | on <lane>",
                    "lune run kit taste train anim")
    if sub in ("off", "on"):
        rec = load_record(vault, lane) or {"lane": lane, "enabled": False, "why": "never trained"}
        rec["off"] = sub == "off"
        os.makedirs(os.path.dirname(record_path(vault, lane)), exist_ok=True)
        with open(record_path(vault, lane), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        return emit("pass", f"taste {lane}: switched {sub} by the owner", "none - proceed", line=status_line(rec))
    meta, vecs = A.load(index_dir)
    if meta is None:
        return emit("fail", "taste: no look index yet", "lune run kit alike index")
    if sub == "train":
        rec = train(meta, vecs, vault, lane)
        import datetime  # noqa: PLC0415

        rec["trained"] = datetime.date.today().isoformat()
        written = save_record(vault, lane, rec)
        rec = load_record(vault, lane) or rec
        agree = (f"leave-one-out: orders {rec['pairs']} pairs of different looks the owner's way {rec['pairwise']:.0%} "
                 f"(chance 50%; all pairs {rec['pairwise_all']:.0%}), rank correlation {rec['spearman']:+.2f}"
                 if rec.get("pairwise") is not None else "not testable yet")
        return emit("pass", f"taste {lane}: {rec['n']} piece(s) the owner scored with a picture; {agree}; "
                    f"{'ON' if rec.get('enabled') and not rec.get('off') else 'OFF'} - {rec.get('why')}",
                    "lune run kit taste order " + lane + " <Move/rK>" if rec.get("enabled") else "none - it stays off",
                    record=rec, written=written, line=status_line(rec))
    rec = load_record(vault, lane)
    if not rec:
        return emit("pass", f"taste {lane}: not trained yet", f"lune run kit taste train {lane}", lines=[], rows=[])
    if rec.get("off") or not rec.get("enabled"):
        return emit("pass", f"taste {lane}: {status_line(rec)}", "none - proceed", lines=[], rows=[], line=status_line(rec))
    items = []
    for t in [a for a in argv[2:] if not a.startswith("--") and a not in (root, vault, index_dir)]:
        items += _targets(meta, vecs, embed, root, t)
    rows = order(meta, vecs, vault, lane, items, rec)
    spread = (rows[0]["predicted"] - rows[-1]["predicted"]) if len(rows) > 1 else 0.0
    lines = [f"{r['item']}: {r['predicted']:g} (looks like {', '.join(r['nearest'])})" for r in rows]
    tell = "" if spread >= 0.5 or len(rows) < 2 else f" - they barely differ (spread {spread:.2f}): the model cannot tell them apart"
    return emit("pass", f"taste {lane}: {len(rows)} ordered by the taste model ({rec['pairwise']:.0%} pairwise agreement "
                f"with the owner, {rec['n']} pieces){tell}", "the owner picks - the order is a suggestion, never a gate",
                lines=lines, rows=rows, line=status_line(rec))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
