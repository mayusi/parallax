"""kit vfx timing <name> [--view hero] - does the picture land on the sound? (pros time VFX to the sound: "VFX as audio
visualization", An-Tim Nguyen, GDC 2022; board/plans/archive/aaa-vfx-research.md). Mixes the preset's sound layers into one
track (each clip decoded by ffmpeg, pitch = speed, volume = gain, placed at its `at`), finds the sound's hits (onsets:
sharp rises of the loudness envelope), finds the picture's hits in the player recording's metrics (sharp rises of the
frame's mean brightness / hot pixels: build/vfx/booth/<name>_play.metrics.json) and pairs them.

A sound hit with no picture hit within ONE frame (42 ms at the player's 24 fps; the V3 doc, VFX stage E.3: "<= +-1
frame visual peak vs SFX transient") is reported: the picture is EARLY (it flashes before the sound) or LATE, or there
is no visual beat for it at all; a big picture hit with no sound is reported too. `kit vfx play <name> --record` runs
it after every recording (the effect's own folder, the active game's build).
Prints one JSON line {status, summary, next_action, sound_hits, picture_hits, pairs}; exit 0 = in sync, or
"unchecked" (no sound layer to judge against, or none of its sounds built).
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameroot  # noqa: E402

RATE = 22050
FPS = 24.0          # the player records at 24 fps
TOL = 1.0 / FPS     # one frame (was two, 83 ms)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict(status=status, summary=summary, next_action=next_action, **extra)))
    sys.exit(0 if status in ("pass", "unchecked") else 1)


def judge(sound_hits, picture_hits, tol=TOL):
    """the sound's hits against the picture's -> (pairs, problems): every sound hit paired with the nearest picture hit,
    a problem when that is more than `tol` away (EARLY / LATE), or there is none near at all; a big picture hit
    (strength >= 0.6) with no sound within `tol` is a problem too"""
    pairs, problems, paired = [], [], set()
    ms = round(tol * 1000)
    for t, strength in sound_hits:
        near = min(picture_hits, key=lambda h: abs(h[0] - t)) if picture_hits else None
        off = round(near[0] - t, 3) if near else None
        pairs.append({"sound": t, "picture": near[0] if near else None, "offset": off})
        reach = max(2 * tol, 0.5 / max(1, len(sound_hits)))  # (how far a picture hit may be and still be this sound's)
        if near is None or abs(off) > reach:
            problems.append(f"sound hit at {t:.2f} s has no picture hit near it (within {round(reach * 1000)} ms)")
            continue
        paired.add(near[0])  # (a picture hit a sound took: told once, as early / late, never again as soundless)
        if abs(off) > tol + 1e-9:
            problems.append(f"sound hit at {t:.2f} s: the picture is {'LATE' if off > 0 else 'EARLY'} by {abs(off) * 1000:.0f} ms "
                            f"(more than one frame, {ms} ms)")
    for t, strength in picture_hits:
        if strength >= 0.6 and t not in paired and not any(abs(t - s[0]) <= tol + 1e-9 for s in sound_hits):
            problems.append(f"a big picture hit at {t:.2f} s has no sound")
    return pairs, problems


def decode(path):
    exe = shutil.which("ffmpeg")
    if not exe:
        out("fail", "vfx timing: ffmpeg is not on PATH", "install ffmpeg (vetted, VETLOG) to decode the sounds")
    r = subprocess.run([exe, "-v", "error", "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        return None
    return np.frombuffer(r.stdout, dtype=np.float32)


def onsets(times, values, min_gap=0.12, rel=0.25):
    """the rises of a curve: positive steps (frame to frame) above `rel` of the biggest rise, at least min_gap apart;
    each hit = (time, strength 0..1)"""
    v = np.asarray(values, dtype=np.float64)
    if len(v) < 3 or v.max() <= 0:
        return []
    rise = np.clip(np.diff(v), 0, None)
    if rise.max() <= 0:
        return []
    rise = rise / rise.max()
    hits = []
    for i in np.argsort(-rise):
        if rise[i] < rel:
            break
        t = float(times[i + 1])
        if all(abs(t - h[0]) >= min_gap for h in hits):
            hits.append((round(t, 3), round(float(rise[i]), 2)))
    return sorted(hits)


def main():
    args = sys.argv[1:]
    if not args:
        out("fail", "vfx timing: name the preset", "lune run kit vfx timing <name> [--view hero]")
    name = args[0]
    view = args[args.index("--view") + 1] if "--view" in args else None
    exp = subprocess.run(["lune", "run", "kit", "vfx", "expand", name], capture_output=True, text=True, encoding="utf-8")
    text = exp.stdout
    if "{" not in text:
        out("fail", f"vfx timing: could not expand {name}", (exp.stderr or "lune run kit vfx expand " + name)[:300])
    preset = json.loads(text[text.index("{"):text.rindex("}") + 1])
    dur = float(preset.get("duration") or 5)
    sounds = [l for l in preset.get("layers", []) if l.get("kind") == "sound"]
    if not sounds:
        out("unchecked", f"vfx timing: {name} has no sound layers (nothing to judge its timing against)", "none")
    track = np.zeros(int((dur + 1) * RATE), dtype=np.float32)
    missing = []
    for s in sounds:
        path = gameroot.build("sounds", f"{s.get('sound')}.ogg")
        clip = decode(path) if os.path.isfile(path) else None
        if clip is None or len(clip) == 0:
            missing.append(s.get("sound"))
            continue
        pitch = float(s.get("pitch") or 1)
        if abs(pitch - 1) > 1e-3:  # Roblox PlaybackSpeed: faster AND higher - resample
            idx = np.arange(0, len(clip), pitch)
            clip = np.interp(idx, np.arange(len(clip)), clip).astype(np.float32)
        start = int(float(s.get("at") or 0) * RATE)
        if start >= len(track):
            continue
        n = min(len(clip), len(track) - start)
        track[start:start + n] += clip[:n] * float(s.get("volume") or 0.5)
    hop = int(RATE * 0.01)
    env = np.sqrt(np.convolve(track ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    env_t = np.arange(len(env)) * 0.01
    if len(missing) == len(sounds):
        out("unchecked", f"vfx timing: {name}: none of its sounds is built ({', '.join(sorted(set(map(str, missing))))}): nothing to judge against",
            "lune run kit sfx (builds them), then record again", missing_sounds=missing)
    sound_hits = [h for h in onsets(env_t, env, rel=0.2) if h[0] <= dur]
    run = args[args.index("--run") + 1] if "--run" in args else name
    metrics = gameroot.build("vfx", "booth", f"{run}_play.metrics.json")
    if not os.path.isfile(metrics):
        out("fail", f"vfx timing: no player recording metrics for {name}",
            f"lune run kit vfx play {name} --record (then run timing again)", sound_hits=sound_hits)
    m = json.load(open(metrics, encoding="utf-8"))
    views = m.get("views", {})
    if not views:
        out("fail", "vfx timing: the metrics hold no views", f"lune run kit vfx play {name} --record")
    v = views.get(view) if view else views.get("hero") or next(iter(views.values()))
    frames = [f for f in v.get("frames", []) if "t" in f]
    seen, pic_t, pic_v = set(), [], []
    for f in frames:
        if f["t"] in seen:
            continue
        seen.add(f["t"])
        pic_t.append(f["t"])
        pic_v.append(float(f.get("mean", 0)) + 40.0 * float(f.get("hot", 0)))
    picture_hits = onsets(pic_t, pic_v, rel=0.3)
    pairs, problems = judge(sound_hits, picture_hits)
    extra = dict(sound_hits=sound_hits, picture_hits=picture_hits, pairs=pairs, missing_sounds=missing)
    if missing:
        problems.append(f"sounds not built: {', '.join(sorted(set(map(str, missing))))}")
    if problems:
        out("warn", f"vfx timing: {name}: {len(problems)} off-beat: " + "; ".join(problems[:4]),
            "move the visual beat (layer `at` / the beat table) onto the sound, or the sound onto the picture; re-record", **extra)
    out("pass", f"vfx timing: {name}: {len(pairs)} sound hit(s), every one lands on a picture hit (within one frame, {round(TOL * 1000)} ms)", "none", **extra)


if __name__ == "__main__":
    main()
