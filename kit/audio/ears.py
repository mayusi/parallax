"""ears.py — measuring sound for a model that cannot hear (shared by sheet / match / set / mix / identity).

decode(path) -> (mono float64 samples, sample rate)       any format ffmpeg reads
measure(x, sr) -> dict of numbers ("ears v2"):
  peak_dbfs, true_peak_dbfs (4x oversampled), rms_dbfs, crest_db (punch: peak over rms),
  lufs (ITU-R BS.1770-4 integrated, gated), lufs_m_max (loudest 400 ms), attack_ms (start -> peak),
  transient_ms (10 % -> 90 % of the peak: how sharp the hit is), tail_ms (peak -> last sample above -40 dB),
  duration_s, brightness_hz (power-weighted centroid), centroid_start_hz / centroid_end_hz (first vs last
  third of the sound: metal and real tails get darker as they decay), flux (spectral change per frame = texture),
  onsets (separate hits: 1 = one impact, 3+ = a rattle or a burst), sub_share (energy below 120 Hz),
  low/mid/high shares (<300, 300-3k, >3k Hz), seam_db (loop discontinuity, only meaningful for loops)
delta(a, b) -> the same keys as "a minus b" plus a plain-words list ("18 % darker", "tail 300 ms longer")
distance(a, b) -> one number for optimisers (weighted, unit-normalised differences)
mel(x, sr) -> (log-mel spectrogram [bands x frames], frame seconds, band centre Hz)
No librosa / pyloudnorm: numpy + scipy only (the formulas are short; the kit vets every dependency).
"""

import shutil
import subprocess

import numpy as np
from scipy import signal

SR = 44100


def decode(path, sr=SR):
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64), sr


def db(v):
    return float(20 * np.log10(max(float(v), 1e-9)))


# ------------------------------------------------------------------ loudness (ITU-R BS.1770-4)
def _k_weight(x, sr):
    """K-weighting with the standard's own 48 kHz coefficients (BS.1770-4 table 1/2); other rates are resampled
    to 48 kHz first. (A shelf rebuilt from its parameters gave +0.43 dB at 1 kHz instead of +0.69: a full-scale
    1 kHz sine read -3.27 LUFS, not the textbook -3.01.)"""
    if sr != 48000:
        from math import gcd

        g = gcd(48000, int(sr))
        x = signal.resample_poly(x, 48000 // g, int(sr) // g)
    b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    a1 = [1.0, -1.69065929318241, 0.73248077421585]
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, -1.99004745483398, 0.99007225036621]
    return signal.lfilter(b2, a2, signal.lfilter(b1, a1, x)), 48000


def _block_powers(y, sr, seconds, overlap):
    n = int(round(seconds * sr))
    if len(y) <= n:
        return np.array([np.mean(y**2)]) if len(y) else np.array([0.0])
    hop = max(1, int(round(n * (1 - overlap))))
    starts = list(range(0, len(y) - n + 1, hop))
    # the last block always ends at the sound's end: a 0.5 s SFX otherwise got 2 blocks as WAV but 1 as OGG
    # (128 samples shorter) and read 2.5 LU louder — short sounds sit right at the block boundaries
    if starts[-1] != len(y) - n:
        starts.append(len(y) - n)
    return np.array([np.mean(y[i : i + n] ** 2) for i in starts])


def lufs(x, sr):
    """Integrated loudness. A sound shorter than one 400 ms block is measured as one block (SFX are short)."""
    y, sr = _k_weight(x, sr)
    z = _block_powers(y, sr, 0.4, 0.75)
    loud = -0.691 + 10 * np.log10(np.maximum(z, 1e-12))
    z = z[loud > -70]
    if len(z) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(z)) - 10
    z2 = z[(-0.691 + 10 * np.log10(np.maximum(z, 1e-12))) > rel]
    return float(-0.691 + 10 * np.log10(max(np.mean(z2 if len(z2) else z), 1e-12)))


def lufs_momentary(x, sr, hop=0.05, window=0.4):
    """K-weighted loudness over a sliding window every `hop` seconds. window 0.4 = EBU momentary (lufs_m_max);
    the sheet's curve uses 50 ms (an SFX is often shorter than one 400 ms window)."""
    y, sr = _k_weight(x, sr)
    n, step = max(1, int(window * sr)), max(1, int(hop * sr))
    pad = np.concatenate([np.zeros(n // 2), y, np.zeros(n // 2)])
    vals = [np.mean(pad[i : i + n] ** 2) for i in range(0, max(1, len(pad) - n + 1), step)]
    return np.array([-0.691 + 10 * np.log10(max(v, 1e-12)) for v in vals]), hop


# ------------------------------------------------------------------ spectra
def stft_power(x, sr, n=2048, hop=256):
    if len(x) < n:
        x = np.concatenate([x, np.zeros(n - len(x))])
    _, _, z = signal.stft(x, fs=sr, nperseg=n, noverlap=n - hop, boundary=None, padded=True)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    return np.abs(z) ** 2, freqs, hop / sr


def _mel_filters(sr, n_fft, bands=96, fmin=30.0, fmax=None):
    fmax = fmax or sr / 2
    mel = lambda f: 2595 * np.log10(1 + f / 700)  # noqa: E731
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)  # noqa: E731
    pts = inv(np.linspace(mel(fmin), mel(fmax), bands + 2))
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    fb = np.zeros((bands, len(freqs)))
    for i in range(bands):
        lo, c, hi = pts[i], pts[i + 1], pts[i + 2]
        up = (freqs - lo) / max(c - lo, 1e-9)
        down = (hi - freqs) / max(hi - c, 1e-9)
        fb[i] = np.maximum(0, np.minimum(up, down))
    return fb, pts[1:-1]


def mel(x, sr, bands=96):
    p, _, frame_s = stft_power(x, sr)
    fb, centres = _mel_filters(sr, 2048, bands)
    m = fb @ p
    return 10 * np.log10(np.maximum(m, 1e-12)), frame_s, centres


def _centroid(p, freqs):
    tot = np.sum(p, axis=0)
    return np.sum(freqs[:, None] * p, axis=0) / np.maximum(tot, 1e-12), tot


# ------------------------------------------------------------------ the ears
def measure(x, sr=SR, loop=False):
    x = np.asarray(x, dtype=np.float64)
    if len(x) == 0:
        x = np.zeros(1)
    a = np.abs(x)
    peak = float(a.max())
    rms = float(np.sqrt(np.mean(x**2)))
    # "the peak" = the first moment within 10 % of the maximum: a limited sound sits flat at its ceiling for a
    # while, and argmax then picks any sample of that plateau (attack jumped 1.6 -> 98 ms between takes)
    ip = int(np.nonzero(a >= peak * 0.9)[0][0]) if peak > 0 else 0
    up = signal.resample_poly(x, 4, 1) if len(x) > 8 else x
    first = np.nonzero(a > peak * 0.1)[0]
    start = int(first[0]) if len(first) else 0
    ten = start
    ninety = np.nonzero(a[start : ip + 1] >= peak * 0.9)[0]
    loud = np.nonzero(a > peak * 0.01)[0]
    p, freqs, frame_s = stft_power(x, sr)
    cent, energy = _centroid(p, freqs)
    w = energy / max(np.sum(energy), 1e-12)
    third = max(1, len(cent) // 3)
    live = energy > energy.max() * 1e-4 if energy.max() > 0 else np.ones_like(energy, bool)
    idx = np.nonzero(live)[0]
    seg = idx if len(idx) else np.arange(len(cent))
    head, tail = seg[: max(1, len(seg) // 3)], seg[-max(1, len(seg) // 3) :]
    spec = np.sum(p, axis=1)
    tot = max(np.sum(spec), 1e-12)
    band = lambda lo, hi: float(np.sum(spec[(freqs >= lo) & (freqs < hi)]) / tot)  # noqa: E731
    # spectral flux: positive change of the (normalised) magnitude spectrum between frames
    mag = np.sqrt(p)
    mag = mag / np.maximum(np.max(mag, axis=0, keepdims=True), 1e-12)
    fl = np.sum(np.maximum(np.diff(mag, axis=1), 0), axis=0) if mag.shape[1] > 1 else np.zeros(1)
    fl_w = fl * (energy[1:] / max(energy.max(), 1e-12)) if len(fl) == len(energy) - 1 else fl
    seam = db(abs(x[-1] - x[0]) + 1e-9) - db(peak) if loop else None
    out = {
        "peak_dbfs": round(db(peak), 1),
        "true_peak_dbfs": round(db(np.abs(up).max()), 1),
        "rms_dbfs": round(db(rms), 1),
        "crest_db": round(db(peak) - db(rms), 1),
        "lufs": round(lufs(x, sr), 1),
        "lufs_m_max": round(float(np.max(lufs_momentary(x, sr)[0])), 1),
        "attack_ms": round(1000 * (ip - start) / sr, 1),
        "transient_ms": round(1000 * (int(ninety[0]) if len(ninety) else 0) / sr, 1) if ip >= ten else 0.0,
        "tail_ms": round(1000 * (int(loud[-1]) - ip) / sr) if len(loud) else 0,
        "duration_s": round(len(x) / sr, 3),
        "brightness_hz": round(float(np.sum(cent * w))),
        "centroid_start_hz": round(float(np.average(cent[head], weights=np.maximum(energy[head], 1e-12)))),
        "centroid_end_hz": round(float(np.average(cent[tail], weights=np.maximum(energy[tail], 1e-12)))),
        "flux": round(float(np.sum(fl_w) / max(1, len(fl_w)) * 100), 2),
        "onsets": len(onsets(x, sr)),
        "sub_share": round(band(0, 120), 3),
        "low_share": round(band(0, 300), 3),
        "mid_share": round(band(300, 3000), 3),
        "high_share": round(band(3000, sr / 2 + 1), 3),
    }
    if seam is not None:
        out["seam_db"] = round(seam, 1)
    _ = third, frame_s
    return out


def onsets(x, sr=SR):
    """Times (s) of separate hits: peaks of the energy-envelope rise, at least 60 ms apart, above 25 % of the
    biggest rise. Robust for SFX (a gunshot = 1, a triple beep = 3, a chain rattle = many)."""
    hop = int(0.005 * sr)
    n = len(x) // hop
    if n < 5:
        return [0.0]
    env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    env = np.convolve(env, np.ones(3) / 3, mode="same")  # 15 ms smoothing: noise grain is not a hit
    edb = 20 * np.log10(env + 1e-9)
    # floor at 60 dB under the peak: a rise out of digital silence (-180 dB) dwarfed every later hit and the
    # "30 % of the biggest rise" threshold hid them (a swing + hit on one clip read as ONE onset)
    edb = np.maximum(edb, edb.max() - 60)
    lag = 4  # rise measured over 20 ms
    rise = np.maximum(edb - np.concatenate([np.full(lag, edb[0] - 60), edb[:-lag]]), 0)
    loud = edb > edb.max() - 24  # a hit must reach within 24 dB of the loudest moment
    rise = np.where(loud, rise, 0)
    if rise.max() <= 0:
        return [0.0]
    peaks, _ = signal.find_peaks(rise, height=max(6.0, rise.max() * 0.3), distance=max(1, int(0.08 * sr / hop)))
    # one rise spreads over a few frames: keep the first frame of each rise
    return [round(float(max(0, p - lag) * hop / sr), 3) for p in peaks] or [0.0]


# ------------------------------------------------------------------ comparing
SCALE = {  # what counts as "one unit" of difference per number (perceptual-ish steps)
    "lufs": 1.0,
    "crest_db": 1.5,
    "attack_ms": 5.0,
    "transient_ms": 3.0,
    "tail_ms": 120.0,
    "brightness_hz": None,  # relative (log) below
    "centroid_start_hz": None,
    "centroid_end_hz": None,
    "flux": None,  # relative: noise and tones live on different scales
    "sub_share": 0.04,
    "low_share": 0.05,
    "mid_share": 0.05,
    "high_share": 0.05,
    "onsets": 1.0,
}
WEIGHT = {"lufs": 0.5, "brightness_hz": 2.0, "tail_ms": 1.5, "attack_ms": 1.0, "transient_ms": 1.0, "onsets": 1.0}


def distance(a, b):
    """One number: 0 = same ears. Log ratio for frequencies (an octave = 3 units), steps elsewhere."""
    tot = 0.0
    for k, unit in SCALE.items():
        if k not in a or k not in b:
            continue
        if unit is None:
            d = 3 * abs(np.log2(max(a[k], 1) / max(b[k], 1)))
        else:
            d = abs(a[k] - b[k]) / unit
        tot += WEIGHT.get(k, 0.5) * min(d, 10.0) ** 2
    return float(np.sqrt(tot))


def delta(a, b):
    """a minus b, and the differences that matter, in words (largest first)."""
    d = {k: round(a[k] - b[k], 3) for k in a if k in b and isinstance(a[k], (int, float)) and isinstance(b[k], (int, float))}
    words = []

    def pct(k):
        return 100 * (a[k] - b[k]) / max(abs(b[k]), 1e-9)

    if abs(pct("brightness_hz")) >= 10:
        words.append((abs(pct("brightness_hz")) / 10, f"{abs(pct('brightness_hz')):.0f} % {'brighter' if pct('brightness_hz') > 0 else 'darker'}"))
    if abs(d.get("tail_ms", 0)) >= 80:
        words.append((abs(d["tail_ms"]) / 80, f"tail {abs(d['tail_ms']):.0f} ms {'longer' if d['tail_ms'] > 0 else 'shorter'}"))
    if abs(d.get("attack_ms", 0)) >= 4:
        words.append((abs(d["attack_ms"]) / 4, f"peak {abs(d['attack_ms']):.0f} ms {'later' if d['attack_ms'] > 0 else 'earlier'}"))
    if abs(d.get("transient_ms", 0)) >= 3:
        words.append((abs(d["transient_ms"]) / 3, f"transient {'softer' if d['transient_ms'] > 0 else 'sharper'} ({abs(d['transient_ms']):.0f} ms)"))
    if abs(d.get("lufs", 0)) >= 1.5:
        words.append((abs(d["lufs"]) / 1.5, f"{abs(d['lufs']):.1f} LU {'louder' if d['lufs'] > 0 else 'quieter'}"))
    if abs(d.get("crest_db", 0)) >= 2:
        words.append((abs(d["crest_db"]) / 2, f"{'punchier' if d['crest_db'] > 0 else 'flatter / more compressed'} ({abs(d['crest_db']):.1f} dB crest)"))
    if abs(d.get("sub_share", 0)) >= 0.05:
        words.append((abs(d["sub_share"]) / 0.05, f"{'more' if d['sub_share'] > 0 else 'less'} sub below 120 Hz ({abs(d['sub_share']) * 100:.0f} pts)"))
    if abs(d.get("high_share", 0)) >= 0.06:
        words.append((abs(d["high_share"]) / 0.06, f"{'more' if d['high_share'] > 0 else 'less'} air above 3 kHz ({abs(d['high_share']) * 100:.0f} pts)"))
    if d.get("onsets", 0) != 0:
        words.append((abs(d["onsets"]), f"{a['onsets']} hit(s) vs {b['onsets']}"))
    if abs(d.get("flux", 0)) >= 1.5:
        words.append((abs(d["flux"]) / 1.5, f"{'busier / grainier' if d['flux'] > 0 else 'smoother'} texture"))
    words.sort(key=lambda w: -w[0])
    return d, [w for _, w in words]


# ------------------------------------------------------------------ the independent loudness cross-check
LOUDNESS_TOLERANCE_LU = 0.5


def _pyloudnorm():
    """pyloudnorm (VETLOG: 0.2.0, MIT, ITU-R BS.1770-4) when it is installed, else None: the kit never needs it, it
    only CHECKS our own meter against an independent implementation (LIMITATIONS_FIXES_V4 SFX-X: pyloudnorm in ears)"""
    try:
        import pyloudnorm  # noqa: PLC0415
    except ImportError:
        return None
    return pyloudnorm


def lufs_crosscheck(x, sr, tolerance=LOUDNESS_TOLERANCE_LU):
    """our BS.1770-4 integrated loudness beside pyloudnorm's on the same samples -> dict:
      available  pyloudnorm importable (False: nothing compared, ok None - never a fake pass)
      ours / theirs / diff_lu   LUFS, LUFS, ours minus theirs
      ok         |diff| <= tolerance (None when not compared)
      note       why it was not compared (not installed; shorter than one 400 ms block, where the two meters
                 legitimately differ: ours measures a short SFX as one block, pyloudnorm refuses it)"""
    x = np.asarray(x, dtype=np.float64)
    ours = round(float(lufs(x, sr)), 2)
    out = {"available": False, "ours": ours, "theirs": None, "diff_lu": None, "ok": None, "tolerance": tolerance, "note": ""}
    pln = _pyloudnorm()
    if pln is None:
        out["note"] = "pyloudnorm is not installed (VETLOG: vetted 0.2.0; it is optional - the kit's own meter is used)"
        return out
    out["available"] = True
    if len(x) < int(0.4 * sr) + 1:
        out["note"] = "shorter than one 400 ms block: not comparable (pyloudnorm needs a full block)"
        return out
    theirs = float(pln.Meter(int(sr)).integrated_loudness(x))
    if not np.isfinite(theirs):
        out["note"] = "pyloudnorm measured silence (below the -70 LUFS gate)"
        return out
    out["theirs"] = round(theirs, 2)
    out["diff_lu"] = round(ours - theirs, 2)
    out["ok"] = abs(ours - theirs) <= tolerance
    return out


def main(argv):
    """python kit/audio/ears.py --loudness <file ...>: each file's loudness by our meter and pyloudnorm's"""
    import json
    import sys

    if not argv or argv[0] != "--loudness" or len(argv) < 2:
        print(json.dumps({"status": "fail", "summary": "usage: ears.py --loudness <file ...>",
                          "next_action": "python kit/audio/ears.py --loudness build/sounds/<name>.ogg"}))
        return 2
    rows = []
    for f in argv[1:]:
        try:
            x, sr = decode(f)
        except (OSError, subprocess.CalledProcessError) as exc:
            rows.append({"file": f, "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append({"file": f, **lufs_crosscheck(x, sr)})
    bad = [r for r in rows if r.get("error") or r.get("ok") is False]
    compared = [r for r in rows if r.get("ok") is not None]
    if bad:
        status, summary = "fail", f"loudness: {len(bad)} of {len(rows)} file(s) disagree or failed: " + "; ".join(
            f"{r['file']}: " + (r.get("error") or f"ours {r['ours']} vs pyloudnorm {r['theirs']} LUFS ({r['diff_lu']:+} LU)") for r in bad[:3])
        nxt = "a meter disagreement is a bug in kit/audio/ears.py lufs (BS.1770-4): fix the meter, never the tolerance"
    elif not compared:
        status = "pass"
        summary = f"loudness: {len(rows)} file(s) measured by the kit's meter; NOT cross-checked ({rows[0].get('note', '')})"
        nxt = "install the vetted pyloudnorm 0.2.0 (the owner's yes) to cross-check, or ignore: the kit's meter stands alone"
    else:
        status = "pass"
        summary = f"loudness: {len(compared)} of {len(rows)} file(s) agree with pyloudnorm within {LOUDNESS_TOLERANCE_LU} LU"
        nxt = "nothing: the meter agrees"
    print(json.dumps({"status": status, "summary": summary, "next_action": nxt, "files": rows}))
    sys.stdout.flush()
    return 1 if bad else 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(main(_sys.argv[1:]))
