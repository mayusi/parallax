"""synth.py — procedural SFX from JSON recipes (numpy + scipy, ffmpeg for OGG). No samples, no licenses.

Usage: python kit/audio/synth.py [--recipes DIR] [--out DIR] <recipe-name ...|all>   (normally: lune run kit sfx <name|all>)
Recipes: assets/sounds/<name>.json  ->  build/sounds/<name>.ogg (+ <name>_2.ogg ... when "variations" > 1)

RECIPE SHAPE (all keys optional except layers):
{
  "duration": 1.0,                 seconds
  "variations": 1,                 >1 renders N takes with new noise + small pitch drift (avoid repetition)
  "pitch_spread": 0.06,            the takes' pitch drift (+-6 %); seeded noise layers vary by this alone
  "loop": false,                   true = seamless loop (tail crossfaded into head)
  "layers": [{
      "source": "sine|square|saw|triangle|noise|fm|click|sample|karplus|modal",
      "role": "transient|body|sub|mechanical|tail|sweetener|air",  what the layer is FOR (gated by kit sfx set)
      "sample": "path.ogg" | ["a.ogg", "b.ogg"],  sample only (a list = round-robin per take; "lib:<id>" = library)
      "trim": [start_s, end_s], "rate": 1.0, "reverse": false, "align": "peak"   sample only (align: the
                                   sample's peak lands on the layer's delay, so layers line up on their hits)
      "decay": 1.5, "bright": 0.5  karplus only (a string / chain / wire ring; decay = seconds to -60 dB)
      "modes": [[hz, decay_s, amp], ...] | "modes_file": "x.modes.json", "strike": 0..1   modal only (a struck
                                   body: metal, glass, wood; the strike point moves per take = natural variation)
      "transient": {"attack": dB, "sustain": dB}  transient shaper (+attack = sharper hit, -sustain = drier)
      "min_weight": 0.0, "weight_gain": 0.0      layer only above this weight / dB louder per unit of weight
      "freq": 440 | [start, end],  Hz, glides exponentially start->end over the layer
      "color": "white|pink|brown", noise only
      "ratio": 2.0, "index": 3.0,  fm only: modulator = freq*ratio, depth = index
      "gain": 1.0, "delay": 0.0,   start offset in seconds
      "mod": {"rate": 0.2, "depth": 0.6, "seed": 7}   slow level gusts (beds: wind, water); whole cycles per loop
      "length": null,              seconds (default: rest of the sound)
      "repeat": [count, interval], e.g. [3, 0.15] = beep-beep-beep
      "env": {"attack": 0.005, "hold": 0, "decay": 0.2, "sustain": 0.0, "release": 0.1, "curve": "exp|lin"},
      "filter": {"type": "lowpass|highpass|bandpass", "cutoff": 2000 | [start, end], "q": 0.7},
      "drive": 0.0                 per-layer tanh saturation 0..1
  }],
  "fx": {"drive": 0, "crush": 0, "echo": [delay_s, feedback], "reverb": 0..1, "convolve": ["ir.wav", mix],
         "transient": {"attack": dB, "sustain": dB}, "normalize": -2.0 (dBFS, default) | null,
         "loudness": -16 (a LUFS target instead of peak-normalize; the peak stays under -1 dBFS)}
  "weight": 0.5                    0 light .. 1 heavy: heavier = lower pitch, more sub, longer tail (sets render 3)
  -2 dBFS leaves headroom: lossy OGG encoding overshoots transients by ~1-2 dB.
}
Prints one JSON line per run: {status, summary, next_action, sounds:[{name, file, seconds}]}.
"""

import json
import os
import shutil
import subprocess
import sys

import numpy as np
from scipy import signal

RECIPES = os.path.join("assets", "sounds")  # project recipes (kit passes --recipes from kit.config.json)
OUT = os.path.join("build", "sounds")
SR = 44100
BLOCK = 256


# ------------------------------------------------------------------ building blocks
def glide(spec, n):
    """Exponential frequency glide [start, end] (or constant) across n samples."""
    if isinstance(spec, (list, tuple)):
        start, end = float(spec[0]), float(spec[1])
        return start * (end / start) ** np.linspace(0, 1, n)
    return np.full(n, float(spec))


def oscillator(kind, freq, n, rng, layer):
    phase = 2 * np.pi * np.cumsum(freq) / SR
    if kind == "sine":
        return np.sin(phase)
    if kind == "square":
        return np.sign(np.sin(phase))
    if kind == "saw":
        return 2 * ((phase / (2 * np.pi)) % 1.0) - 1
    if kind == "triangle":
        return 2 * np.abs(2 * ((phase / (2 * np.pi)) % 1.0) - 1) - 1
    if kind == "fm":
        mod = np.sin(2 * np.pi * np.cumsum(freq * layer.get("ratio", 2.0)) / SR)
        return np.sin(phase + layer.get("index", 3.0) * mod)
    if kind == "click":
        out = np.zeros(n)
        out[: min(n, 64)] = np.hanning(128)[64 : 64 + min(n, 64)]
        return out
    if kind == "noise":
        white = rng.standard_normal(n)
        color = layer.get("color", "white")
        if color == "pink":
            b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
            white = signal.lfilter(b, a, white) * 8
        elif color == "brown":
            white = np.cumsum(white)
            white = signal.lfilter([1, -1], [1, -0.995], white) * 0.08
        return np.clip(white / 3.0, -1, 1)
    raise ValueError(f'unknown source "{kind}" (sine|square|saw|triangle|noise|fm|click|sample|karplus|modal)')


# ------------------------------------------------------------------ recorded + physical sources
_SAMPLES = {}


def load_sample(ref):
    """A recording as mono float at SR: a path, or lib:<id> from the local library (kit/audio/sfxlib.py)."""
    if ref.startswith("lib:"):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import sfxlib as library  # noqa: E402

        lib_id, ref = ref[4:], library.path_of(ref[4:])
        if ref not in _SAMPLES and not os.path.isfile(ref):
            # recorded packs stay out of git (library/sfx/index.json keeps only the paths): a fresh checkout must fetch them
            src = library.load()["entries"].get(lib_id, {}).get("source", "?")
            raise ValueError(f"library recording missing: {ref} (lib:{lib_id}, pack {src}): download the pack again "
                             f"from its VETLOG.md row into the same folder (big packs are not in git)")
    if ref not in _SAMPLES:
        if not os.path.isfile(ref):
            raise ValueError(f"sample not found: {ref}")
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        raw = subprocess.run(
            [ffmpeg, "-v", "error", "-i", ref, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
            capture_output=True,
            check=True,
        ).stdout
        _SAMPLES[ref] = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    return _SAMPLES[ref]


def sample_source(layer, n, take, pitch):
    refs = layer["sample"] if isinstance(layer["sample"], list) else [layer["sample"]]
    x = load_sample(refs[take % len(refs)])
    if "trim" in layer:
        a, b = layer["trim"]
        x = x[int(a * SR) : int(b * SR) if b else None]
    if layer.get("align") == "peak" and len(x) and np.max(np.abs(x)) > 0:
        x = x[int(np.argmax(np.abs(x))) :]
    rate = float(layer.get("rate", 1.0)) * pitch
    if abs(rate - 1.0) > 1e-4 and len(x) > 1:
        x = np.interp(np.arange(0, len(x) - 1, rate), np.arange(len(x)), x)
    if layer.get("reverse"):
        x = x[::-1]
    out = np.zeros(n)
    m = min(n, len(x))
    out[:m] = x[:m]
    # a recording cut mid-tail (a short file, a trim, the layer's end) stops on a hard edge = a click: fade its last
    # 4 ms (Kenney's 0.1 s concrete steps end at -38 dB, louder once normalised)
    f = min(m, int(0.004 * SR))
    if f > 1:
        out[m - f : m] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, f)))
    return out


def karplus(freq, n, rng, layer):
    """Karplus-Strong: a noise burst in a delay line with a lowpassing feedback loop (string, chain, wire)."""
    f0 = float(freq[0])
    period = max(2, int(round(SR / max(f0, 20))))
    decay = float(layer.get("decay", 1.5))
    fb = 10 ** (-3 / max(decay * f0, 1e-3))  # -60 dB after `decay` seconds
    bright = float(np.clip(layer.get("bright", 0.5), 0, 1))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    prev = 0.0
    for i in range(n):
        v = buf[i % period]
        out[i] = v
        buf[i % period] = fb * (bright * v + (1 - bright) * 0.5 * (v + prev))
        prev = v
    return out


def modal(n, rng, layer, take, pitch):
    """A struck resonant body: a sum of decaying sines (modes). `strike` (0..1, moved per take) re-weights the modes
    the way hitting a bar at another spot does: endless natural variation from one measured body."""
    modes = layer.get("modes")
    if modes is None and "modes_file" in layer:
        with open(layer["modes_file"], encoding="utf-8") as fh:
            modes = json.load(fh)["modes"]
    if not modes:
        raise ValueError("modal layer needs modes [[hz, decay_s, amp], ...] or modes_file")
    strike = float(layer.get("strike", 0.3)) + (0.0 if take == 0 else float(rng.uniform(-0.12, 0.12)))
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, (hz, dec, amp) in enumerate(modes):
        hz = float(hz) * pitch
        if hz >= SR / 2:
            continue
        w = abs(np.sin(np.pi * (k + 1) * float(np.clip(strike, 0.02, 0.98)))) ** 0.7
        phase = float(rng.uniform(0, 2 * np.pi))
        out += float(amp) * w * np.sin(2 * np.pi * hz * t + phase) * np.exp(-t * 6.9 / max(float(dec), 1e-3))
    # a strike starts at zero displacement: a 1 ms fade-in avoids a click that is not the body's
    ramp = min(n, int(0.001 * SR))
    out[:ramp] *= np.linspace(0, 1, ramp)
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out


def transient_shape(x, spec):
    """Transient shaper: a fast vs a slow envelope follower; attack dB boosts the hit, sustain dB scales the rest."""
    att, sus = float(spec.get("attack", 0)), float(spec.get("sustain", 0))
    if (att == 0 and sus == 0) or len(x) < 8:
        return x
    a = np.abs(x)
    kf, ks = np.exp(-1 / (0.001 * SR)), np.exp(-1 / (0.03 * SR))
    fast = signal.lfilter([1 - kf], [1, -kf], a)
    slow = signal.lfilter([1 - ks], [1, -ks], a)
    hit = np.clip((fast - slow) / np.maximum(fast, 1e-9), 0, 1)
    return x * 10 ** ((hit * att + (1 - hit) * sus) / 20)


def convolve(x, spec):
    ir = load_sample(spec[0])
    mix = float(spec[1]) if len(spec) > 1 else 0.3
    wet = signal.fftconvolve(x, ir)[: len(x)]
    wet *= np.max(np.abs(x)) / max(np.max(np.abs(wet)), 1e-9)
    return x * (1 - mix) + wet * mix


def limit(x, ceiling, look_ms=1.5, release_ms=60.0):
    """Peak limiter: the gain each sample needs to stay under `ceiling`, held over a short look-ahead window
    (the gain is already down when the peak arrives) and released smoothly (no pumping clicks)."""
    from scipy.ndimage import minimum_filter1d

    need = np.minimum(1.0, ceiling / np.maximum(np.abs(x), 1e-12))
    if need.min() >= 1.0:
        return x
    look = max(1, int(look_ms * SR / 1000))
    held = minimum_filter1d(need, size=2 * look + 1, mode="nearest")
    rel = 1 - np.exp(-1 / (release_ms * SR / 1000))
    g = np.empty_like(held)
    cur = 1.0
    for i, h in enumerate(held):
        cur = h if h < cur else cur + (h - cur) * rel
        g[i] = cur
    return np.clip(x * g, -ceiling, ceiling)


def k_lufs(x):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ears  # noqa: E402

    return ears.lufs(x, SR)


def envelope(env, n):
    a = int(env.get("attack", 0.005) * SR)
    h = int(env.get("hold", 0.0) * SR)
    d = int(env.get("decay", 0.2) * SR)
    s = float(env.get("sustain", 0.0))
    r = int(env.get("release", 0.1) * SR)
    expo = env.get("curve", "exp") == "exp"
    body = max(0, n - a - h - d - r)

    def seg(start, end, count):
        if count <= 0:
            return np.zeros(0)
        t = np.linspace(0, 1, count, endpoint=False)
        if expo and start > end:
            k = 5.0
            shape = (np.exp(-k * t) - np.exp(-k)) / (1 - np.exp(-k))
            return end + (start - end) * shape
        return start + (end - start) * t

    out = np.concatenate([seg(0, 1, a), np.ones(h), seg(1, s, d), np.full(body, s), seg(s, 0, r)])
    if len(out) < n:
        out = np.concatenate([out, np.zeros(n - len(out))])
    return out[:n]


def biquad(kind, fc, q):
    fc = float(np.clip(fc, 20, SR * 0.45))
    w = 2 * np.pi * fc / SR
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    if kind == "lowpass":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
    elif kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
    elif kind == "bandpass":
        b = [alpha, 0, -alpha]
    else:
        raise ValueError(f'unknown filter "{kind}" (lowpass|highpass|bandpass)')
    a = [1 + alpha, -2 * cw, 1 - alpha]
    return np.array(b) / a[0], np.array(a) / a[0]


def sweep_filter(x, spec):
    kind, q = spec.get("type", "lowpass"), float(spec.get("q", 0.707))
    cut = glide(spec.get("cutoff", 2000), len(x))
    out = np.empty_like(x)
    zi = np.zeros(2)
    for i in range(0, len(x), BLOCK):
        b, a = biquad(kind, cut[i], q)
        out[i : i + BLOCK], zi = signal.lfilter(b, a, x[i : i + BLOCK], zi=zi)
    return out


def reverb(x, amount, rng):
    if amount <= 0:
        return x
    length = int(SR * (0.4 + 1.6 * amount))
    t = np.arange(length) / SR
    ir = rng.standard_normal(length) * np.exp(-t * (6.0 / (0.4 + 1.6 * amount)))
    ir[0] = 0
    ir = signal.lfilter([0.3], [1, -0.7], ir)  # real rooms absorb highs: one-pole lowpass (~2.5 kHz) on the tail
    wet = signal.fftconvolve(x, ir)[: len(x)]
    wet /= max(1e-9, np.max(np.abs(wet))) / max(1e-9, np.max(np.abs(x)))
    return x * (1 - 0.5 * amount) + wet * 0.6 * amount


# ------------------------------------------------------------------ render
def gusts(spec, t, period, rng):
    """slow level movement for beds (wind gusts, lapping water): 1 - depth * (0..1) from four smooth sines whose
    cycles fit WHOLE into `period` (a loop's own length), so a modulated loop still joins without a seam"""
    depth = min(1.0, max(0.0, float(spec.get("depth", 0.5))))
    rate = max(0.01, float(spec.get("rate", 0.2)))
    g = np.random.default_rng(int(spec.get("seed", 7)))
    parts = [(max(1, round(rate * r * period)), g.uniform(0, 2 * np.pi), r) for r in (1.0, 1.7, 2.9, 4.3)]

    def curve(tt):
        tt = np.asarray(tt, dtype=float)
        return sum(np.sin(2 * np.pi * k * tt / period + ph) / r for k, ph, r in parts)

    # scaled by its range over one whole period (a pure function of time: any window reads the same curve)
    ref = curve(np.linspace(0, period, 4096, endpoint=False))
    s = (curve(t) - ref.min()) / max(ref.max() - ref.min(), 1e-9)
    return 1 - depth * np.clip(s, 0, 1)


def render_layer(layer, total, rng, pitch, take=0, period=None):
    delay = int(layer.get("delay", 0.0) * SR)
    length = layer.get("length")
    n = max(1, (int(length * SR) if length else total - delay))
    count, interval = layer.get("repeat", [1, 0.0])
    out = np.zeros(total)
    freq_spec = layer.get("freq", 440)
    if isinstance(freq_spec, (list, tuple)):
        freq_spec = [f * pitch for f in freq_spec]
    else:
        freq_spec = freq_spec * pitch
    if "seed" in layer:
        # a fixed seed = the SAME noise every take (takes then differ by pitch / strike only): short noise bursts
        # otherwise roll new dice per take (a 90 ms brown thud swung 8 % -> 38 % sub between takes)
        rng = np.random.default_rng(int(layer["seed"]))
    for k in range(int(count)):
        start = delay + int(k * interval * SR)
        if start >= total:
            break
        m = min(n, total - start)
        kind = "sample" if "sample" in layer else layer.get("source", "sine")
        if kind == "sample":
            x = sample_source(layer, m, take, pitch)
        elif kind == "karplus":
            x = karplus(glide(freq_spec, m), m, rng, layer)
        elif kind == "modal":
            x = modal(m, rng, layer, take, pitch)
        else:
            x = oscillator(kind, glide(freq_spec, m), m, rng, layer)
        if "filter" in layer:
            spec = layer["filter"]
            if pitch != 1.0:  # a take's pitch moves its filters too (a sampler's pitch moves everything)
                cut = spec.get("cutoff", 2000)
                spec = dict(spec, cutoff=[c * pitch for c in cut] if isinstance(cut, (list, tuple)) else cut * pitch)
            x = sweep_filter(x, spec)
        # recorded / physical sources carry their own decay: an envelope only when the recipe asks for one
        if "env" in layer or kind not in ("sample", "karplus", "modal"):
            x = x * envelope(layer.get("env", {}), m)
        if "transient" in layer:
            x = transient_shape(x, layer["transient"])
        if layer.get("drive", 0) > 0:
            dr = 1 + 20 * layer["drive"]
            x = np.tanh(x * dr) / np.tanh(dr)
        if "mod" in layer:
            x = x * gusts(layer["mod"], (start + np.arange(m)) / SR, (period or total) / SR, rng)
        out[start : start + m] += x * float(layer.get("gain", 1.0))
    return out


def apply_weight(recipe):
    """weight 0 (light) .. 1 (heavy), 0.5 = as written: heavier = lower pitch, more sub, longer body/tail, louder
    weight_gain layers, and layers whose min_weight is above the weight dropped. Returns (layers, pitch factor)."""
    w = float(recipe.get("weight", 0.5))
    k = w - 0.5
    layers = []
    for layer in recipe["layers"]:
        if w < float(layer.get("min_weight", 0.0)):
            continue
        layer = dict(layer)
        role = layer.get("role")
        g = float(layer.get("gain", 1.0)) * 10 ** (float(layer.get("weight_gain", 0.0)) * k / 20)
        if role == "sub":
            g *= 1 + 1.2 * k
        elif role in ("air", "sweetener"):
            g *= 1 - 0.6 * k
        layer["gain"] = max(0.0, g)
        if role in ("tail", "body") and isinstance(layer.get("env"), dict):
            env = dict(layer["env"])
            for key in ("decay", "release"):
                if key in env:
                    env[key] = float(env[key]) * (1 + 0.8 * k)
            layer["env"] = env
        layers.append(layer)
    return layers, 2 ** (-0.35 * k)


def render(recipe, seed, pitch, take=0):
    rng = np.random.default_rng(seed)
    total = int(float(recipe.get("duration", 1.0)) * SR)
    mix = np.zeros(total)
    layers, wpitch = apply_weight(recipe)
    xf_loop = min(int(0.05 * SR), total // 4) if recipe.get("loop") else 0
    for layer in layers:
        mix += render_layer(layer, total, rng, pitch * wpitch, take, period=total - xf_loop)
    fx = recipe.get("fx", {})
    if fx.get("drive", 0) > 0:
        dr = 1 + 20 * fx["drive"]
        mix = np.tanh(mix * dr) / np.tanh(dr)
    if fx.get("crush", 0) > 0:
        levels = 2 ** max(2, int(16 - 13 * fx["crush"]))
        mix = np.round(mix * levels) / levels
    if "echo" in fx:
        d, fb = fx["echo"]
        step = int(d * SR)
        for k in range(1, 6):
            if step * k >= total:
                break
            mix[step * k :] += mix[: total - step * k] * (fb**k)
    if "transient" in fx:
        mix = transient_shape(mix, fx["transient"])
    mix = reverb(mix, fx.get("reverb", 0), rng)
    if "convolve" in fx:
        mix = convolve(mix, fx["convolve"])
    if recipe.get("loop"):
        xf = min(int(0.05 * SR), total // 4)
        fade = np.linspace(0, 1, xf)
        head = mix[:xf].copy()
        mix[:xf] = head * fade + mix[-xf:] * (1 - fade)
        mix = mix[:-xf]
    else:
        tail = min(int(0.01 * SR), len(mix))
        mix[-tail:] *= np.linspace(1, 0, tail)
    mix -= np.mean(mix)
    # subsonic filter (20 Hz, 2nd order): brown noise and reverb tails carry rumble no speaker plays but that
    # eats headroom and the limiter's budget (the sword hits' tails measured a 5 Hz centroid)
    sb, sa = signal.butter(2, 20 / (SR / 2), "high")
    if recipe.get("loop"):
        # a loop is filtered as the circle it is: run two laps, keep the second (a filter starting from silence made
        # the head differ from the tail: a click at every seam)
        mix = signal.lfilter(sb, sa, np.concatenate([mix, mix]))[len(mix) :]
    else:
        mix = signal.lfilter(sb, sa, mix)
    norm = fx.get("normalize", -2.0)
    if "loudness" in fx and np.max(np.abs(mix)) > 0:
        # gain to the LUFS target, then a peak limiter at -1 dBFS (OGG overshoots transients); limiting lowers the
        # loudness a little, so converge in a few rounds. A plain peak-normalize could not reach -16 LUFS on a
        # punchy hit (crest 25 dB -> it landed at -25).
        for _ in range(10):
            miss = float(fx["loudness"]) - k_lufs(mix)
            if abs(miss) < 0.2:
                break
            mix *= 10 ** (min(miss, 6.0) / 20)
            mix = limit(mix, 10 ** (-1 / 20))
        norm = None
    if norm is not None:
        peak = np.max(np.abs(mix))
        if peak > 0:
            mix *= (10 ** (norm / 20)) / peak
    return mix


def write_ogg(samples, path):
    import wave

    wav_path = path[:-4] + ".wav"
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    # ffmpeg argument list (no shell); quality 6 Vorbis is transparent for SFX
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", wav_path, "-c:a", "libvorbis", "-q:a", "6", path], check=True)
    os.remove(wav_path)


def main(names, recipes_dir=RECIPES, out_dir=OUT):
    os.makedirs(out_dir, exist_ok=True)
    if names == ["all"]:
        # recipes only: not the events catalog (_events.json), verdicts, matched / pre-match copies (<name>.<x>.json)
        names = sorted(f[:-5] for f in os.listdir(recipes_dir) if f.endswith(".json") and not f.startswith("_") and "." not in f[:-5])
    made, errors = [], []
    for name in names:
        path = os.path.join(recipes_dir, f"{name}.json")
        try:
            with open(path, encoding="utf-8") as fh:
                recipe = json.load(fh)
            takes = int(recipe.get("variations", 1))
            for i in range(takes):
                spread = float(recipe.get("pitch_spread", 0.06))
                pitch = 1.0 if i == 0 else float(np.random.default_rng(i).uniform(1 - spread, 1 + spread))
                out_name = name if i == 0 else f"{name}_{i + 1}"
                file = os.path.join(out_dir, f"{out_name}.ogg")
                samples = render(recipe, seed=1000 + i, pitch=pitch, take=i)
                write_ogg(samples, file)
                made.append({"name": out_name, "file": os.path.relpath(file).replace("\\", "/"), "seconds": round(len(samples) / SR, 3)})
        except FileNotFoundError:
            errors.append(f"{name}: no recipe at {recipes_dir}/{name}.json")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    status = "fail" if errors else "pass"
    print(
        json.dumps(
            {
                "schema": 1,
                "status": status,
                "summary": "; ".join(errors) if errors else f"rendered {len(made)} sound(s)",
                "next_action": f"fix the recipe: {errors[0]} (shape documented at the top of kit/audio/synth.py)" if errors else "none — proceed",
                "sounds": made,
            }
        )
    )
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    opts = {"--recipes": RECIPES, "--out": OUT}
    while args and args[0] in opts:
        opts[args[0]], args = args[1], args[2:]
    sys.exit(main(args or ["all"], opts["--recipes"], opts["--out"]))
