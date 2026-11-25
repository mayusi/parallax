"""modal.py — the RESONANT MODES of a recorded hit (the Crackdown 2 method): one real clang becomes a "modal" layer
that re-strikes the same body with endless natural variation (the strike point moves per take).

Usage: python kit/audio/modal.py <file|name> [--modes 16] [--as <name>]   (normally: lune run kit sfx modal <file>)
-> assets/sounds/modes/<as>.modes.json  {source, modes: [[hz, decay_s, amp], ...]} + a resynthesis check: the modal
   layer struck once vs the recording (ears distance + the mode list), so a bad extraction shows before it is used.
Use it: { "role": "tail", "source": "modal", "modes_file": "assets/sounds/modes/<as>.modes.json", "strike": 0.3 }
How: the decay part (from the peak on) -> a long FFT -> the strongest well-separated spectral peaks (parabolic
interpolation for the exact frequency) -> each peak's own decay from its STFT band (a line fit to log magnitude:
the time to -60 dB) -> amplitude relative to the strongest. Noise-like sounds (no clear peaks) are refused.
"""

import json
import os
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402

SR = E.SR


def extract(x, sr, n_modes=16, fmin=60.0, fmax=16000.0):
    a = np.abs(x)
    ip = int(np.argmax(a))
    tail = x[ip:]
    if len(tail) < sr * 0.05:
        raise ValueError("under 50 ms after the peak: too short to hear any ringing")
    n = 1 << int(np.ceil(np.log2(len(tail))))
    # the ring already decays (it is its own window): only fade the last 10 % — a full Hann window zeroed the LOUD
    # start of the ring and smeared each mode into ghost peaks 5-20 % away
    win = np.ones(len(tail))
    k = max(1, len(tail) // 10)
    win[-k:] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, k)))
    spec = np.abs(np.fft.rfft(tail * win, n))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = (freqs >= fmin) & (freqs <= fmax)
    mag = np.where(band, spec, 0)
    # tonality first: noise is spectrally FLAT, a ringing body is not (geometric / arithmetic mean of the power)
    pw = mag[band] ** 2 + 1e-20
    flatness = float(np.exp(np.mean(np.log(pw))) / np.mean(pw))
    if flatness > 0.05:
        raise ValueError(f"spectral flatness {flatness:.2f}: a noise-like sound has no modes (use a sample layer instead)")
    # peaks on a LOG scale standing 15 dB above their surroundings (a decaying ring has broad skirts whose ripples
    # look like peaks on a linear scale), at least ~15 Hz apart
    db = 20 * np.log10(mag + 1e-12)
    min_dist = max(1, int(round(15.0 / freqs[1])))
    peaks, props = signal.find_peaks(db, prominence=15, distance=min_dist)
    peaks = peaks[band[peaks]]
    if len(peaks) == 0:
        raise ValueError("no clear resonant peaks: a noise-like sound has no modes (use a sample layer instead)")
    # strongest first; a peak within 5 % of a stronger one is that one's leakage, not a mode
    kept = []
    for p in peaks[np.argsort(-db[peaks])]:
        if all(abs(freqs[p] - freqs[q]) > 0.05 * freqs[q] for q in kept):
            kept.append(p)
        if len(kept) >= n_modes:
            break
    peaks = np.sort(np.array(kept))
    # exact frequency: parabolic interpolation on log magnitude
    out = []
    f_stft, t_stft, z = signal.stft(tail, fs=sr, nperseg=2048, noverlap=1536)
    z = np.abs(z)
    for p in peaks:
        if 0 < p < len(mag) - 1:
            l, c, r = np.log(mag[p - 1] + 1e-12), np.log(mag[p] + 1e-12), np.log(mag[p + 1] + 1e-12)
            shift = 0.5 * (l - r) / (l - 2 * c + r) if (l - 2 * c + r) != 0 else 0.0
        else:
            shift = 0.0
        hz = float((p + shift) * sr / n)
        b = int(np.argmin(np.abs(f_stft - hz)))
        env = z[max(0, b - 1) : b + 2].max(axis=0)
        envdb = 20 * np.log10(env + 1e-12)
        top = envdb.max()
        use = envdb > top - 40  # fit the part above the noise
        if use.sum() < 3:
            decay = 0.05
        else:
            slope = np.polyfit(t_stft[use], envdb[use], 1)[0]  # dB per second (negative)
            decay = float(np.clip(-60.0 / slope if slope < -1e-3 else 5.0, 0.01, 8.0))
        out.append([round(hz, 2), round(decay, 3), float(mag[p])])
    amax = max(m[2] for m in out)
    for m in out:
        m[2] = round(m[2] / amax, 3)
    return out


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: modal.py <file|name> [--modes 16] [--as <name>]", "next_action": "lune run kit sfx modal <recording>"}))
        return 1
    src = argv[0]
    n_modes = int(argv[argv.index("--modes") + 1]) if "--modes" in argv else 16
    path = src if os.path.isfile(src) else os.path.join("build", "sounds", f"{src}.ogg")
    if not os.path.isfile(path):
        print(json.dumps({"status": "fail", "summary": f"no recording {src}", "next_action": "pass a file, or a rendered sound name"}))
        return 1
    name = argv[argv.index("--as") + 1] if "--as" in argv else os.path.splitext(os.path.basename(path))[0]
    x, sr = E.decode(path)
    try:
        modes = extract(x, sr, n_modes)
    except ValueError as exc:
        print(json.dumps({"status": "fail", "summary": f"{os.path.basename(path)}: {exc}", "next_action": "pick a recording that RINGS (metal, glass, wood struck once)"}))
        return 1
    out = os.path.join("assets", "sounds", "modes", f"{name}.modes.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"source": path.replace(os.sep, "/"), "made_by": "kit/audio/modal.py", "modes": modes}, fh, indent=1)
    # resynthesis check: the modal layer struck once vs the recording's ringing part
    import synth

    ip = int(np.argmax(np.abs(x)))
    ring = x[ip:]
    y = synth.modal(len(ring), np.random.default_rng(1), {"modes": modes, "strike": 0.5}, 0, 1.0)
    ea, eb = E.measure(y, sr), E.measure(ring, sr)
    d = E.distance(ea, eb)
    _, words = E.delta(ea, eb)
    print(json.dumps({"status": "pass",
                      "summary": f"{len(modes)} mode(s) from {os.path.basename(path)}: " + ", ".join(f"{m[0]:.0f} Hz/{m[1]:.2f}s" for m in modes[:6]) + f"; resynthesis distance {d:.2f}",
                      "next_action": f"use it: {{\"role\": \"tail\", \"source\": \"modal\", \"modes_file\": \"{out.replace(os.sep, '/')}\"}}" + (f" — the ring differs: {'; '.join(words[:2])}" if words else ""),
                      "file": out.replace(os.sep, "/"), "modes": modes, "distance": round(d, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
