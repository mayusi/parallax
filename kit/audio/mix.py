"""mix.py — hear a REAL FIGHT offline: a playtest's sound-event log re-rendered through the events catalog, with
distance, voice limits and ducking — then measured (density, repetition, masking, loudness).

Usage: python kit/audio/mix.py <events.log.json> [--seconds 30] [--out build/sounds/mix]
       python kit/audio/mix.py --demo [--moves src/moves/BgFists.json]   a simulated 30 s fight (2 fighters
                                                                         trading the moveset's combo + ambience)
       (normally: lune run kit sfx mix <log> | --demo)
Log: { "listener": [x, y, z], "events": [ { "t": 1.25, "event": "SwordHit", "params": { "surface": "metal",
       "weight": 0.8 }, "pos": [x, y, z] }, ... ] }   (an entry may name a "sound" directly instead of an event)
-> <out>/<log>.ogg (the mix, for the owner) + <out>/<log>.png (spectrogram + voices over time) + a verdict:
   peak simultaneous voices, sounds repeated > 20 times a minute (fatigue: raise their variations), pairs that sit in
   the same band at the same moment (masking: "the hit and the swing fight at 2-4 kHz"), the mix's loudness.
"""

import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402
import synth  # noqa: E402

SR = synth.SR
CATALOG = os.path.join("assets", "sounds", "_events.json")
SOUNDS = os.path.join("build", "sounds")


def resolve(cat, event, params, rnd):
    """The same resolution as src/kit/SfxRules.luau: switch -> case -> blend (nearest weight) -> sound."""
    e = (cat.get("events") or {}).get(event)
    if not isinstance(e, dict):
        return None
    p = params or {}

    def pick(case):
        if isinstance(case, str):
            return case
        if isinstance(case, dict):
            if isinstance(case.get("sound"), str):
                return case["sound"]
            sounds = case.get("sounds") or {}
            x = float(p.get(case.get("blend", "weight"), 0.5))
            best = min(sorted(sounds), key=lambda k: abs(float(k) - x), default=None)
            return sounds.get(best) if best is not None else None
        return None

    if e.get("switch") and isinstance(e.get("cases"), dict):
        case = e["cases"].get(str(p.get(e["switch"])))
        if case is None and "default" in e:
            case = e["cases"].get(str(e["default"]))
        sound = pick(case)
    elif isinstance(e.get("sounds"), dict):
        sound = pick(e)
    else:
        sound = e.get("sound")
    if not sound:
        return None
    pr = e.get("pitch", 1)
    pitch = rnd.uniform(*pr) if isinstance(pr, list) else float(pr)
    return {"sound": sound, "bus": e.get("bus", "sfx"), "priority": e.get("priority", 50), "voices": e.get("voices", 6),
            "rolloff": e.get("rolloff", [8, 140]), "duck": e.get("duck"), "pitch": pitch, "volume": float(p.get("volume", 1))}


_cache = {}


def take(sound, rnd):
    takes = [os.path.join(SOUNDS, f"{sound}.ogg")]
    i = 2
    while os.path.isfile(os.path.join(SOUNDS, f"{sound}_{i}.ogg")):
        takes.append(os.path.join(SOUNDS, f"{sound}_{i}.ogg"))
        i += 1
    if not os.path.isfile(takes[0]):
        return None, None
    f = rnd.choice(takes)
    if f not in _cache:
        _cache[f] = E.decode(f)[0]
    return f, _cache[f]


def demo(moves_path, seconds=30.0):
    """Two fighters 6-20 studs from the listener trading the moveset's combo, with blocks, a parry and UI clicks."""
    rnd = random.Random(7)
    combo = ["BgM1_1", "BgM1_2", "BgM1_3", "BgM1_4"]
    gaps = [0.3, 0.35, 0.35, 0.5]
    if moves_path and os.path.isfile(moves_path):
        with open(moves_path, encoding="utf-8") as fh:
            m = json.load(fh)
        combo = m.get("combo") or combo
        gaps = []
        for n in combo:
            mv = m["moves"][n]
            c = mv.get("cancel") or {}
            gaps.append((c.get("from") or sum(mv["frames"][k] for k in ("startup", "active", "recovery"))) / mv["frames"].get("fps", 60))
    ev, t = [], 0.5
    while t < seconds - 2:
        pos = [rnd.uniform(-20, 20), 0, rnd.uniform(6, 20)]
        blocked = rnd.random() < 0.25
        for i, n in enumerate(combo):
            w = 0.15 + 0.25 * i if i < 3 else 0.9
            ev.append({"t": round(t, 3), "event": "SwordSwing", "params": {"weight": w}, "pos": pos})
            ev.append({"t": round(t + 0.08, 3), "event": "SwordBlock" if blocked else "SwordHit",
                       "params": {"surface": rnd.choice(["flesh", "flesh", "metal"]), "weight": w}, "pos": pos})
            t += gaps[i % len(gaps)]
        if rnd.random() < 0.2:
            ev.append({"t": round(t + 0.1, 3), "event": "SwordParry", "params": {}, "pos": pos})
        t += rnd.uniform(0.6, 1.6)
        if rnd.random() < 0.3:
            ev.append({"t": round(t, 3), "event": "UiClick", "params": {}})
    return {"listener": [0, 0, 0], "events": ev}


def render(log, seconds, cat):
    rnd = random.Random(3)
    n = int(seconds * SR)
    buses = {b: np.zeros(n) for b in ("sfx", "ui", "music", "ambience", "voice")}
    base = {b: float((cat.get("buses") or {}).get(b, {}).get("volume", 1.0)) for b in buses}
    duck = np.ones(n)
    lis = np.array(log.get("listener", [0, 0, 0]), float)
    placed, dropped, missing = [], 0, set()
    max_voices = int(cat.get("maxVoices", 32))
    active = []
    for e in sorted(log["events"], key=lambda e: e["t"]):
        if e["t"] >= seconds:
            continue
        if "sound" in e:
            r = {"sound": e["sound"], "bus": e.get("bus", "sfx"), "priority": 50, "voices": 6, "rolloff": [8, 140], "duck": None, "pitch": 1.0, "volume": 1.0}
        else:
            r = resolve(cat, e["event"], e.get("params"), rnd)
        if not r:
            missing.add(e.get("event", "?"))
            continue
        f, x = take(r["sound"], rnd)
        if x is None:
            missing.add(r["sound"])
            continue
        if abs(r["pitch"] - 1) > 1e-3:
            x = np.interp(np.arange(0, len(x) - 1, r["pitch"]), np.arange(len(x)), x)
        start = int(e["t"] * SR)
        end = start + len(x)
        active = [a for a in active if a[1] > start]
        same = [a for a in active if a[2] == r["sound"]]
        if len(same) >= r["voices"] or len(active) >= max_voices:
            dropped += 1
            continue
        g = r["volume"]
        if e.get("pos") is not None and r["bus"] != "ui":
            d = float(np.linalg.norm(np.array(e["pos"], float) - lis))
            near, far = r["rolloff"]
            g *= 1.0 if d <= near else max(0.0, 1 - (d - near) / max(far - near, 1e-6))
        seg = x[: max(0, min(len(x), n - start))] * g
        buses[r["bus"] if r["bus"] in buses else "sfx"][start : start + len(seg)] += seg
        active.append((start, end, r["sound"]))
        placed.append({"t": e["t"], "sound": r["sound"], "start": start, "end": min(end, n), "gain": g, "file": f})
        dk = r.get("duck")
        if isinstance(dk, dict) and dk.get("bus") in buses:
            a0, a1 = start, min(n, start + int(float(dk.get("seconds", 0.35)) * SR))
            duck[a0:a1] = np.minimum(duck[a0:a1], float(dk.get("to", 0.5)))
    mix = np.zeros(n)
    for b, sig in buses.items():
        mix += sig * base[b] * (duck if b in ("ambience", "music") else 1.0)
    mix = synth.limit(mix, 10 ** (-1 / 20))
    return mix, placed, dropped, missing


def analyse(mix, placed, seconds):
    hop = int(0.05 * SR)
    frames = int(len(mix) / hop)
    voices = np.zeros(frames, int)
    for p in placed:
        voices[p["start"] // hop : max(p["start"] // hop + 1, p["end"] // hop)] += 1
    per_min = {}
    for p in placed:
        per_min[p["sound"]] = per_min.get(p["sound"], 0) + 1
    minutes = seconds / 60
    fatigue = sorted(((s, round(c / minutes)) for s, c in per_min.items() if c / minutes > 20), key=lambda x: -x[1])
    # masking: pairs that start within 60 ms whose brightness sits within a third of an octave
    cent = {}
    for p in placed:
        if p["file"] not in cent:
            cent[p["file"]] = E.measure(_cache[p["file"]])["brightness_hz"]
    clashes = {}
    ps = sorted(placed, key=lambda p: p["start"])
    for i, a in enumerate(ps):
        for b in ps[i + 1 :]:
            if b["start"] - a["start"] > 0.06 * SR:
                break
            if a["sound"] == b["sound"]:
                continue
            ca, cb = cent[a["file"]], cent[b["file"]]
            if abs(math.log2(max(ca, 1) / max(cb, 1))) < 1 / 3 and min(a["gain"], b["gain"]) > 0.3:
                key = tuple(sorted((a["sound"], b["sound"])))
                clashes[key] = clashes.get(key, 0) + 1
    return voices, fatigue, sorted(clashes.items(), key=lambda kv: -kv[1])


def main(argv):
    seconds = float(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 30.0
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(SOUNDS, "mix")
    if not os.path.isfile(CATALOG):
        print(json.dumps({"status": "fail", "summary": f"no {CATALOG}", "next_action": "write the events catalog (kit sfx catalog)"}))
        return 1
    with open(CATALOG, encoding="utf-8") as fh:
        cat = json.load(fh)
    if "--demo" in argv:
        moves = argv[argv.index("--moves") + 1] if "--moves" in argv else os.path.join("src", "moves", "BgFists.json")
        log, name = demo(moves, seconds), "demo_fight"
    else:
        path = argv[0]
        with open(path, encoding="utf-8") as fh:
            log = json.load(fh)
        name = os.path.splitext(os.path.basename(path))[0].replace(".log", "")
    mix, placed, dropped, missing = render(log, seconds, cat)
    voices, fatigue, clashes = analyse(mix, placed, seconds)
    os.makedirs(out_dir, exist_ok=True)
    ogg = os.path.join(out_dir, f"{name}.ogg")
    synth.write_ogg(mix, ogg)
    e = E.measure(mix)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 6), facecolor="#14161b", gridspec_kw={"height_ratios": [2, 1]})
    m, fs, _ = E.mel(mix, SR, bands=80)
    a1.imshow(np.clip(m, m.max() - 70, m.max()), aspect="auto", origin="lower", cmap="magma", extent=[0, m.shape[1] * fs, 0, 80])
    a1.set_title(f"{name}: {len(placed)} sounds in {seconds:.0f} s — {e['lufs']} LUFS, peak {int(voices.max())} voices", color="#e8e6e1", fontsize=10, loc="left")
    a2.plot(np.arange(len(voices)) * 0.05, voices, color="#ff9e3d")
    a2.set_ylabel("voices", color="#8a8f99")
    for ax in (a1, a2):
        ax.set_facecolor("#14161b")
        ax.tick_params(colors="#8a8f99", labelsize=7)
    png = os.path.join(out_dir, f"{name}.png")
    fig.tight_layout()
    fig.savefig(png, dpi=80, facecolor="#14161b")
    plt.close(fig)
    warns = [f"improve: {s} plays {c} times a minute — fatigue: give it more variations / round-robin samples" for s, c in fatigue]
    warns += [f"improve: {a} and {b} start together {c} time(s) in the same band — they mask each other: separate them in brightness or time" for (a, b), c in clashes[:3]]
    if missing:
        warns.append(f"improve: not rendered / unknown: {', '.join(sorted(missing))}")
    for w in warns:
        print("  warn  " + w)
    print(json.dumps({"status": "pass",
                      "summary": f"{name}: {len(placed)} sound(s) mixed over {seconds:.0f} s, {dropped} dropped by voice limits, peak {int(voices.max())} voices, {e['lufs']} LUFS, {len(fatigue)} fatiguing, {len(clashes)} masking pair(s)",
                      "next_action": warns[0] if warns else f"the owner listens: {ogg.replace(os.sep, '/')}",
                      "mix": ogg.replace(os.sep, "/"), "sheet": png.replace(os.sep, "/"), "warnings": warns}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
