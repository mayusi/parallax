"""parts_rerank.py - the parts libraries' re-ranker (board/plans/archive/2026-11-09-parts-libraries-plan.md). The kit's installed,
pinned vision-language model (kit/vision/vlm.py, Qwen3-VL-4B-Instruct, offline) reads the piece being built and each
card, and the cards are ordered by the model's yes-minus-no logit for "does this card directly help build that?". Text
only; nothing is downloaded.

WARM first (P1): when the kit's warm vision worker runs (`lune run kit vision serve`: kit/vision/serve.py), the scoring
goes there as one batched `kit/vision/run.py relevance` call, with the model already loaded - a whole sheet in seconds.
With no worker, a caller may load the model in this process (`cold=True`, ~40 s: the opt-in --rerank) or get None and
keep the plain order (the default sheets: a look-up never waits on a model silently).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
VISION = os.path.join(ROOT, "kit", "vision")

PROMPT = ("You help a game artist reuse what was made before. The artist is now building:\n{query}\n\n"
          "A card from the library of past work:\n{text}\n\n"
          "Does this card directly help build that - how to make one of its parts, its size or timing, or a mistake to "
          "avoid? Answer only yes or no.")


# ------------------------------------------------------------------------------------------------------- the worker
def _state_paths():
    """where a running worker leaves its state (kit/lib/visionworker.luau: <KIT_BUILD>/vision_worker.json; KIT_BUILD is
    the active game's build folder when one is active)"""
    out = []
    if os.environ.get("KIT_BUILD"):
        out.append(os.path.join(ROOT, os.environ["KIT_BUILD"], "vision_worker.json"))
    game = os.environ.get("KIT_GAME")
    if not game:
        try:
            with open(os.path.join(ROOT, "games", ".active"), encoding="utf-8") as f:
                game = f.read().strip()
        except OSError:
            game = None
    if game:
        out.append(os.path.join(ROOT, "games", game, "build", "vision_worker.json"))
    out.append(os.path.join(ROOT, "build", "vision_worker.json"))
    return out


def _request(url, token=None, body=None, timeout=5.0):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Kit-Token"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


MODEL = "qwen3-vl-4b"  # (kit/vision/vlm.py NAME: the worker lists it as loaded once it is)
LAST = {"why": ""}  # why the last call fell back to the plain order (for the sheet's hint)


def worker():
    """the running warm vision worker's {port, token, loaded} - only when it answers /ping as that worker - else None.
    `loaded`: the re-ranker's model is already in it (a worker that is up has not necessarily loaded it)"""
    for path in _state_paths():
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            ping = _request(f"http://127.0.0.1:{int(st['port'])}/ping", timeout=2.0)
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
            continue
        if ping.get("ok") and ping.get("kind") == "vision" and ping.get("pid") == st.get("pid"):
            return {"port": int(st["port"]), "token": st["token"], "loaded": MODEL in (ping.get("loaded") or [])}
    return None


def _remote(w, prompts, deadline=300.0):
    """one batched relevance call through the worker -> scores, or None (it went away, crashed, or timed out)"""
    os.makedirs(os.path.join(ROOT, "build", "parts"), exist_ok=True)
    req = os.path.join(ROOT, "build", "parts", f"rerank-{os.getpid()}-{int(time.time() * 1000)}.json")
    with open(req, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"prompts": prompts}, f)
    try:
        base = f"http://127.0.0.1:{w['port']}"
        job = _request(f"{base}/run", w["token"], {"argv": ["relevance", req]}, timeout=10.0)
        if job.get("restart") or not job.get("job"):
            return None
        t0 = time.time()
        while time.time() - t0 < deadline:
            time.sleep(0.05)
            d = _request(f"{base}/result/{job['job']}", w["token"], timeout=10.0)
            if d.get("done"):
                if d.get("crashed") or d.get("exit"):
                    return None
                for line in reversed(str(d.get("output", "")).splitlines()):
                    if line.startswith("{"):
                        scores = json.loads(line).get("scores")
                        return scores if isinstance(scores, list) and len(scores) == len(prompts) else None
                return None
        return None
    except (OSError, ValueError, urllib.error.URLError):
        return None
    finally:
        try:
            os.remove(req)
        except OSError:
            pass


def _local(prompts):
    if VISION not in sys.path:
        sys.path.insert(0, VISION)
    import vlm  # noqa: PLC0415  (offline guard and pin check: kit/vision/run.py)

    if not vlm.installed():
        LAST["why"] = "the vision model (qwen3-vl-4b) is not installed"
        return None
    return vlm.yes_scores(prompts)


# ------------------------------------------------------------------------------------------------------- the api
def scores(query, texts, cold=False):
    """the model's usefulness score for each card text (higher = more useful); see scores_many"""
    return scores_many([(query, t) for t in texts], cold=cold)


def score(query, text):
    """one card's score (kept for callers that score one at a time)"""
    return scores(query, [text])[0]


def scores_many(pairs, cold=False):
    """[(query, card text)] -> their scores in ONE call (a whole sheet's cards at once; each card scored alone inside
    it). Warm when the worker has the model loaded. Otherwise None - the caller keeps the plain order and LAST["why"]
    says why - unless `cold`: then a worker without the model loads it (once, ~20 s, warm afterwards) and with no worker
    at all it is loaded here. A worker that fails never gets a second copy of the model loaded beside it.
    Default cold=False: a look-up never waits on a model silently (parts.py passes cold=True explicitly on --rerank)."""
    prompts = [PROMPT.format(query=q, text=t) for q, t in pairs]
    if not prompts:
        return []
    w = worker()
    if w:
        if not cold and not w["loaded"]:
            LAST["why"] = "the vision worker runs but has not loaded the re-ranker's model yet"
            return None
        got = _remote(w, prompts)
        if got is None:
            LAST["why"] = "the vision worker failed this call"
        return got
    if not cold:
        LAST["why"] = "no warm vision worker runs"
        return None
    return _local(prompts)


def rerank(query, items, cold=False):
    """items [(id, text)] -> the ids, most useful first (ties keep the engine's order); None when no worker runs and
    `cold` is off"""
    got = scores(query, [t for _i, t in items], cold=cold)
    if got is None:
        return None
    ranked = sorted(((s, -i, cid) for i, ((cid, _t), s) in enumerate(zip(items, got))), reverse=True)
    return [cid for _s, _i, cid in ranked]
