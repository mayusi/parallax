"""glance.py — the FIVE-SECOND TEST as a judge packet (v7.16): a HUD is read in a glance mid-fight, a menu in the
first second. A fresh reviewer gets the screen ONCE at glance size and answers from memory: what is it for, what did
you see first, what was the key number or word, where would you press. The answers are checked against the answer
key the kit knows (the spec's focus, its texts, the squint ranking) — a screen whose focus is not the first thing seen
fails, however good it looks up close.

    python kit/ui/glance.py <Screen> [--ui build/ui] [--models src/ui] [--out build/judge/ui]
    python kit/ui/glance.py <Screen> --check <answers.json>      {"for": "...", "first": "...", "key": "...", "press": "..."}

-> build/judge/ui/<Screen>/glance/ glance.png (the desktop frame at 640 px: the glance) + brief.md + key.json
   (key.json is for the CHECK: never give it to the reviewer).
"""
import argparse
import json
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GLANCE_W = 640
QUESTIONS = (
    ("for", "What is this screen for? (one line)"),
    ("first", "What did you see FIRST? (name the thing)"),
    ("key", "What was the most important number or word on it?"),
    ("press", "Where would you look or press next?"),
)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", str(s)).lower()) if len(w) > 1}


def texts_under(model, prefix, ui_dir="assets/ui"):
    """[(path, text)] of every word a player can read at or under a node path: typed text, bitmap-glyph text
    (Kit_GText) and the words of a lettered picture (its .letter.json)"""
    out = []

    def walk(inst, path):
        p = inst.get("Properties") or {}
        a = (p.get("Attributes") or {}).get("Attributes") or {}
        inside = not prefix or path == prefix or path.startswith(prefix + ".")
        said = None
        if inst.get("ClassName") in ("TextLabel", "TextButton") and isinstance(p.get("Text"), str) and p["Text"].strip():
            said = p["Text"].strip()
        elif (a.get("Kit_GText") or {}).get("String"):
            said = a["Kit_GText"]["String"]
        elif (a.get("KitArt") or {}).get("String"):
            side = os.path.join(ui_dir, "art", f"{a['KitArt']['String']}.letter.json")
            if os.path.isfile(side):
                with open(side, encoding="utf-8") as fh:
                    said = str(json.load(fh).get("text") or "") or None
        if said and inside and not str(inst.get("Name") or "").startswith("Fx_"):
            out.append((path, said))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def answer_key(model, boxes, frame, focus, kind):
    import hier
    # the focus's own name and its parent's ("Rank.Letter": a glance says "the rank" or "the letter")
    key = {"kind": kind, "focus": focus, "focus_words": sorted(set().union(*(words(n) for n in focus.split(".")[-2:])) if focus else [])}
    if focus:
        key["focus_texts"] = [t for _, t in texts_under(model, focus)][:6]
        for t in key["focus_texts"]:
            key["focus_words"] = sorted(set(key["focus_words"]) | words(t))
    if frame is not None and boxes:
        rank, scores = hier.squint(frame, boxes, focus or "")
        key["squint_rank"] = rank
        key["squint_top"] = [p for _, p in scores[:3]]
    # the biggest texts are what a glance can read at all
    sized = []
    for path, t in texts_under(model, ""):
        b = boxes.get(path)
        if b:
            sized.append((b[3], t))
    key["big_texts"] = [t for _, t in sorted(sized, reverse=True)[:5]]
    return key


def check(key, answers):
    """-> [(question, ok, why)]: 'first' must name the focus; 'key' must be one of its texts or a big text"""
    out = []
    first = words(answers.get("first", ""))
    fw = set(key.get("focus_words") or [])
    ok = bool(fw & first)
    out.append(("first", ok, "names the focus" if ok else f"saw {answers.get('first')!r} first, the focus is {key.get('focus')}"))
    kw = words(answers.get("key", ""))
    want = set()
    for t in (key.get("focus_texts") or []) + (key.get("big_texts") or []):
        want |= words(t)
    ok2 = bool(kw & want)
    out.append(("key", ok2, "read a real key text" if ok2 else f"{answers.get('key')!r} is none of {(key.get('focus_texts') or key.get('big_texts') or [])[:3]}"))
    fr = words(answers.get("for", ""))
    ok3 = bool(fr & words(key.get("kind") or "")) or len(fr) >= 2
    out.append(("for", ok3, "said what it is for" if ok3 else "could not say what the screen is for"))
    return out


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--ui", default="build/ui")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--out", default="build/judge/ui")
    ap.add_argument("--check", default=None)
    a = ap.parse_args(argv)
    S = a.screen
    out = os.path.join(a.out, S, "glance")
    if a.check:
        kp = os.path.join(out, "key.json")
        if not os.path.isfile(kp):
            return emit("fail", f"glance {S}: no packet yet", f"lune run kit ui glance {S}")
        with open(kp, encoding="utf-8") as fh:
            key = json.load(fh)
        with open(a.check, encoding="utf-8") as fh:
            answers = json.load(fh)
        res = check(key, answers)
        miss = [r for r in res if not r[1]]
        with open(os.path.join(out, "result.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"answers": answers, "checks": [{"q": q, "ok": ok, "why": w} for q, ok, w in res]}, fh, indent=1, ensure_ascii=False)
        if miss:
            return emit("fail", f"glance {S}: {len(res) - len(miss)}/{len(res)} - {miss[0][2]}",
                        f"make {key.get('focus')} win the glance: bigger, brighter or set apart (kit ui {S} shows the squint rank)")
        return emit("pass", f"glance {S}: {len(res)}/{len(res)} - the focus is what a glance takes away", "none - proceed")
    frame_p = next((p for p in (os.path.join(a.ui, f"{S}.desktop.png"), os.path.join(a.ui, f"{S}.png")) if os.path.isfile(p)), None)
    mp = os.path.join(a.models, f"{S}.model.json")
    if not frame_p or not os.path.isfile(mp):
        return emit("fail", f"glance {S}: no preview frame or compiled model", f"lune run kit ui {S}")
    with open(mp, encoding="utf-8") as fh:
        model = json.load(fh)
    spec = {}
    sp = os.path.join(a.specs, f"{S}.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as fh:
            spec = json.load(fh)
    frame = Image.open(frame_p).convert("RGB")
    boxes = {}
    bp = os.path.join(a.ui, f"{S}.boxes.json")
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as fh:
            bj = json.load(fh)
        vw = (bj.get("viewport") or [frame.width])[0] or frame.width
        k = frame.width / vw
        boxes = {p: tuple(v * k for v in b) for p, b in (bj.get("boxes") or {}).items()}
    key = answer_key(model, boxes, frame, spec.get("focus"), spec.get("kind"))
    os.makedirs(out, exist_ok=True)
    g = frame.resize((GLANCE_W, max(1, round(frame.height * GLANCE_W / frame.width))), Image.LANCZOS)
    g.save(os.path.join(out, "glance.png"))
    with open(os.path.join(out, "key.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(key, fh, indent=1, ensure_ascii=False)
    qs = "\n".join(f'- "{k}": {q}' for k, q in QUESTIONS)
    brief = f"""# Five-second test: one screen of a Roblox game

Open `glance.png` ONCE (it is the size a player takes in at a glance). Look at it for a moment, then close it and
answer from memory — do not open it again, do not zoom, do not read any other file in this folder.

Answer as JSON in `answers.json` beside this brief:
{qs}

Say what you actually remember, even if it is vague. "I don't know" is a real answer.
Then the kit checks it: `lune run kit ui glance {S} --check build/judge/ui/{S}/glance/answers.json`.
"""
    with open(os.path.join(out, "brief.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(brief)
    rank = key.get("squint_rank")
    note = f" (squint rank of the focus: #{rank})" if rank else ""
    return emit("pass", f"glance {S}: packet -> {out.replace(chr(92), '/')}{note}",
                f"give brief.md + glance.png (NOT key.json) to a fresh reviewer, then kit ui glance {S} --check <answers.json>",
                packet=out.replace(chr(92), "/"), focus=key.get("focus"), squint_rank=rank)


if __name__ == "__main__":
    sys.exit(main())
