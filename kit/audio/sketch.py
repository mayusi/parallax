"""sketch.py — `kit sfx sketch <scene.json>`: a SONIC DIRECTION sketch - a short stereo scene of one place's sound.

    python kit/audio/sketch.py <scene.json> [--out <file.ogg>]

A direction is decided by LISTENING to a place, not to one sound at a time: a scene puts beds, one-shots and
recurring events on a timeline, places each in the stereo field and at a distance, and plays the whole in ONE space
(a convolution reverb whose impulse response is generated from the space's size / decay / brightness: the stone hall
rings, the open vale does not). Three scenes = three directions the owner can hear side by side.

scene: {"duration": 24, "space": {"size": 0.7, "decay": 2.2, "bright": 0.45, "predelay": 0.02} | {"ir": "<vetted IR .wav>", "mix": 1},
        "lufs": -20,
        "events": [{"file": "<.ogg|.wav>" | "lib": "<library id>" | "recipe": {synth recipe},
                    "at": 0 | [t, ...] | "every": [min_s, max_s] (+ "start", "until"), "loop": false,
                    "gain_db": 0, "pan": -1..1 | "random", "dist": 0..1 (far = quieter, darker, wetter),
                    "pitch": [lo, hi] (random per hit), "lowpass" / "highpass": hz, "seed": 1,
                    "walk": {"dist": [0.1, 0.95], "pan": [0, 0.3]} (the source moves over its hits)}]}
Writes <out>.ogg (stereo), <out>.png (a spectrogram of the mix) and one JSON line (what played, LUFS, peak).
"""

import json
import os
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402
import synth  # noqa: E402

SR = synth.SR


def space_ir(space, seed=1):
    """a stereo impulse response from a space's numbers: early reflections (size), an exponential noise tail
    (decay = RT60 seconds), darker as it decays (bright 0..1: air + soft walls absorb the highs first)"""
    rng = np.random.default_rng(seed)
    size = float(space.get("size", 0.5))
    rt60 = max(0.05, float(space.get("decay", 1.5)))
    bright = float(np.clip(space.get("bright", 0.5), 0, 1))
    pre = int(float(space.get("predelay", 0.01 + 0.03 * size)) * SR)
    n = pre + int(rt60 * 1.1 * SR)
    t = np.arange(n - pre) / SR
    env = 10 ** (-3 * t / rt60)  # -60 dB at rt60
    out = np.zeros((2, n))
    for ch in range(2):
        tail = rng.normal(0, 1, n - pre) * env
        # darken over time: crossfade a bright and a dark copy of the tail
        dark = signal.lfilter(*signal.butter(2, 600 + 6000 * bright, "low", fs=SR), tail)
        brite = signal.lfilter(*signal.butter(2, 2500 + 12000 * bright, "low", fs=SR), tail)
        w = np.clip(t / max(rt60 * 0.35, 1e-3), 0, 1)
        out[ch, pre:] = brite * (1 - w) + dark * w
        for k in range(int(6 + 10 * size)):  # early reflections: discrete taps, wider apart in a bigger room
            d = pre + int(rng.uniform(0.003, 0.012 + 0.07 * size) * SR)
            if d < n:
                out[ch, d] += rng.uniform(0.3, 0.9) * (1 if rng.random() < 0.5 else -1)
    out /= np.max(np.abs(out)) + 1e-12
    return out


def load_ir(path):
    """a RECORDED impulse response (wav / flac / ogg, any channel count) -> stereo at SR: stereo files as they are,
    B-format / multichannel use their first two channels, mono is spread with a tiny decorrelating delay"""
    import shutil
    import subprocess

    probe = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=channels", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    ch = int(probe or 1)
    raw = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", path, "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype="<f4").astype(np.float64).reshape(-1, ch).T
    if ch == 1:
        d = int(0.0007 * SR)
        x = np.stack([x[0], np.concatenate([np.zeros(d), x[0][:-d]])])
    out = x[:2]
    return out / (np.max(np.abs(out)) + 1e-12)


def load_event_audio(ev, rng):
    pick = lambda v: v[int(rng.integers(0, len(v)))] if isinstance(v, list) else v  # (a list = round-robin per hit)
    if "file" in ev:
        return synth.load_sample(pick(ev["file"]))
    if "lib" in ev:
        return synth.load_sample("lib:" + pick(ev["lib"]))
    rec = dict(ev["recipe"])
    return synth.render(rec, int(ev.get("seed", 1)) + int(rng.integers(0, 1 << 16)), 1.0)


def pan_gains(p):
    a = (float(p) + 1) * np.pi / 4  # equal power
    return np.cos(a), np.sin(a)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: sketch.py <scene.json> [--out file.ogg]", "next_action": "lune run kit sfx sketch <scene.json>"}))
        return 2
    scene_path = argv[0]
    scene = json.load(open(scene_path, encoding="utf-8"))
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.splitext(scene_path)[0] + ".ogg"
    dur = float(scene.get("duration", 20))
    total = int(dur * SR)
    dry = np.zeros((2, total))
    wet_in = np.zeros((2, total))
    rng = np.random.default_rng(int(scene.get("seed", 7)))
    played = []
    for i, ev in enumerate(scene.get("events", [])):
        times = []
        if "every" in ev:
            lo, hi = ev["every"]
            t = float(ev.get("start", rng.uniform(0, hi)))
            while t < min(dur, float(ev.get("until", dur))):
                times.append(t)
                t += max(0.01, rng.uniform(lo, hi))  # (every: [0, 0] would never end)
        else:
            at = ev.get("at", 0)
            times = at if isinstance(at, list) else [at]
        cache = None
        for t in times:
            x = load_event_audio(ev, rng) if (cache is None or isinstance(ev.get("file", ev.get("lib")), list) or "recipe" in ev) else cache
            cache = x
            if "pitch" in ev:
                r = rng.uniform(*ev["pitch"])
                x = np.interp(np.arange(0, len(x) - 1, r), np.arange(len(x)), x)
            start = int(t * SR)
            if ev.get("loop"):
                reps = int(np.ceil((total - start) / max(len(x), 1)))
                x = np.tile(x, max(reps, 1))
            m = min(len(x), total - start)
            if m <= 0:
                continue
            seg = x[:m] * 10 ** (float(ev.get("gain_db", 0)) / 20)
            if ev.get("lowpass"):  # (e.g. underwater: everything above ~500 Hz gone)
                seg = signal.lfilter(*signal.butter(2, float(ev["lowpass"]), "low", fs=SR), seg)
            if ev.get("highpass"):
                seg = signal.lfilter(*signal.butter(2, float(ev["highpass"]), "high", fs=SR), seg)
            dist = float(ev.get("dist", 0.0))
            walk = ev.get("walk")  # a source that MOVES: distance and pan travel over the event's span (someone walking away)
            if walk and len(times) > 1:
                frac = (t - times[0]) / max(times[-1] - times[0], 1e-6)
                wd = walk.get("dist", [dist, dist])
                dist = wd[0] + (wd[1] - wd[0]) * frac
                ev = dict(ev, pan=walk["pan"][0] + (walk["pan"][1] - walk["pan"][0]) * frac) if "pan" in walk else ev
            if dist > 0:  # dist is a LOG distance (0 = at arm's length, 1 = 16x further): -6 dB per doubling = -24 dB at 1, the highs gone (air)
                seg = signal.lfilter(*signal.butter(2, 16000 * (1 - dist) + 900, "low", fs=SR), seg) * 10 ** (-24 * dist / 20)
            p = rng.uniform(-0.9, 0.9) if ev.get("pan") == "random" else float(ev.get("pan", 0))
            gl, gr = pan_gains(p)
            send = float(ev.get("send", 0.25 + 0.6 * dist))
            for ch, g in ((0, gl), (1, gr)):
                dry[ch, start : start + m] += seg * g * (1 - 0.5 * send)
                wet_in[ch, start : start + m] += seg * g * send
        played.append(f"{ev.get('name', i)} x{len(times)}")
    space = scene.get("space")
    mix = dry
    if space:
        ir = load_ir(space["ir"]) if space.get("ir") else space_ir(space)  # (a real room's recording when we have one)
        wet = np.stack([signal.fftconvolve(wet_in[ch], ir[ch])[:total] for ch in range(2)])
        wet *= np.sqrt(np.sum(wet_in**2) / max(np.sum(wet**2), 1e-12))  # (the space as loud as what goes in)
        mix = dry + wet * float(space.get("mix", 1.0))
    mono = mix.mean(0)
    target = float(scene.get("lufs", -20))
    if np.max(np.abs(mono)) > 0:
        # gain toward the target, but the limiter may take at most MAX_GR dB off the peaks: pushed harder, a sparse
        # scene's every event is clamped to the ceiling and its dynamics die (five walkers leaving measured FLAT).
        # A sparse scene lands under its target instead, and says so. The ceiling leaves room for the encoder:
        # Vorbis overshoots transients by ~2 dB.
        ceiling = 10 ** (-3.5 / 20)
        max_gr = 4.0
        gain_db = target - E.lufs(mix.mean(0), SR)
        peak_after = np.max(np.abs(mix)) * 10 ** (gain_db / 20)
        room = 20 * np.log10(ceiling / max(peak_after, 1e-12)) + max_gr  # (< 0: the target needs more limiting than allowed)
        if room < 0:
            gain_db += room
        mix *= 10 ** (gain_db / 20)
        if np.max(np.abs(mix)) > ceiling:
            mix = np.stack([synth.limit(mix[ch], ceiling) for ch in range(2)])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wav = os.path.splitext(out)[0] + ".wav"
    import wave

    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        inter = np.clip(mix.T, -1, 1)
        w.writeframes((inter * 32767).astype("<i2").tobytes())
    import shutil
    import subprocess

    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libvorbis", "-q:a", "6", out], check=True)
    os.remove(wav)
    png = os.path.splitext(out)[0] + ".png"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 3), dpi=100)
        ax.specgram(mix.mean(0), NFFT=2048, Fs=SR, noverlap=1024, cmap="magma", vmin=-120)
        ax.set_ylim(20, 16000)
        ax.set_yscale("log")
        ax.set_title(os.path.basename(out), fontsize=9)
        fig.savefig(png, bbox_inches="tight")
        plt.close(fig)
    except Exception:
        png = None
    lufs = round(float(E.lufs(mix.mean(0), SR)), 1)
    under = target - lufs
    note = f" ({under:.1f} LU under the target: sparse - its dynamics kept, not limited away)" if under > 1.0 else ""
    print(json.dumps({"status": "pass", "summary": f"{os.path.basename(out)}: {dur:.0f} s, {lufs} LUFS{note}, {len(played)} event kinds ({', '.join(played)})",
                      "next_action": f"LISTEN to {out.replace(os.sep, '/')} beside the other directions", "lufs": lufs, "out": out, "png": png}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
