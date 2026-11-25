"""audio_check.py — Roblox audio gate + "numeric ears" (so a model that can't listen can still judge a sound).

Usage: python kit/audio/check.py <file-or-dir ...>    (normally: lune run kit audio-check <path>)
Gate (errors): format mp3/ogg/wav/flac, < 20 MB, < 7 min, sample rate <= 48 kHz, 1-2 channels,
               not silent (peak > -40 dBFS), no clipping (< 10 samples at full scale), decoded peak <= 0 dBFS.
Warnings:      leading silence > 30 ms (laggy SFX), DC offset, stereo on a short SFX (3D sounds should be mono).
Ears (info):   peak/rms dBFS, attack ms (time to peak), tail ms (peak until it falls below -40 dB),
               brightness = power-weighted spectral centroid Hz:
               <300 boomy/sub (explosions, thumps) · 300-1200 warm/body (hits, engines) ·
               1200-3500 present/bright (UI, beeps, swings) · >3500 harsh/hissy (only for sizzle, shatter, static).
Prints one JSON line: {status, summary, next_action, files:[{file, ok, checks, ears}]}.
"""

import json
import os
import shutil
import subprocess
import sys

import numpy as np

FORMATS = {".mp3", ".ogg", ".wav", ".flac"}
# the owner's measured ear: kit/audio/booth.py writes it after every verdict (its leanings and the loved takes' median
# per trait, once 6+ verdicts are scored) - read here beside each take (2026-11-08, sprint 4: written, never read)
TASTE = os.path.join("kit", "knowledge", "sfx_taste.json")


def ear_notes(ears, taste):
    """each trait the owner leans on where this take sits far from the loved takes' median: a report, never a gate
    (half an octave of brightness; a quarter of the target elsewhere). [] until the booth has its targets"""
    out = []
    targets = (taste or {}).get("targets") or {}
    for lean in (taste or {}).get("leans") or []:
        t = lean.get("trait")
        if t not in targets or t not in (ears or {}):
            continue
        v, goal = float(ears[t]), float(targets[t])
        if t == "brightness_hz":
            off = abs(np.log2(max(v, 1.0)) - np.log2(max(goal, 1.0))) >= 0.5
        else:
            off = abs(v - goal) > 0.25 * max(abs(goal), 1e-6)
        if off:
            out.append(f"{t} {v:g} vs the loved takes' {goal:g} (the owner prefers {lean.get('owner_prefers', '?')})")
    return out


def load_taste(path=None):
    try:
        with open(path or TASTE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def probe(path):
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=sample_rate,channels:format=duration", "-of", "json", path],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    return int(stream["sample_rate"]), int(stream["channels"]), float(data["format"]["duration"])


def decode(path, sr):
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def db(x):
    return round(float(20 * np.log10(max(x, 1e-9))), 1)


def check_file(path):
    checks = []

    def add(name, ok, value, limit, fix, severity="error"):
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "value": value, "limit": limit, "fix": "" if ok else fix})

    ext = os.path.splitext(path)[1].lower()
    size_mb = round(os.path.getsize(path) / 1e6, 3)
    add("format", ext in FORMATS, ext, sorted(FORMATS), "export as .ogg (MP3 adds leading silence)")
    add("size_mb", size_mb < 20, size_mb, 20, "shorten it or lower the bitrate")
    try:
        sr, channels, duration = probe(path)
        x = decode(path, sr)
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError) as exc:
        add("decode", False, str(exc)[:120], "readable", "file is corrupt or not audio — re-export it")
        return {"file": path, "ok": False, "checks": checks, "ears": {}}

    add("duration_s", duration < 420, round(duration, 3), 420, "Roblox rejects audio of 7 minutes or more")
    add("sample_rate", sr <= 48000, sr, 48000, "resample to 44100 or 48000")
    add("channels", 1 <= channels <= 2, channels, "1-2", "downmix to mono or stereo")
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    rms = float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
    clipped = int(np.sum(np.abs(x) >= 0.999))
    add("not_silent", db(peak) > -40, db(peak), -40, "the sound is (nearly) silent — raise gain or check the layers")
    add("clipping", clipped < 10, clipped, "<10 samples", 'lower gain or set "fx": {"normalize": -2.0}')
    add("peak_over_0dbfs", db(peak) <= 0.0, db(peak), 0.0, 'decoded peak is above full scale — normalize lower (e.g. -2.0)')
    thresh = peak * 0.1
    above = np.nonzero(np.abs(x) > thresh)[0] if peak > 0 else np.array([0])
    lead_ms = round(1000 * above[0] / sr, 1) if len(above) else 0.0
    add("leading_silence_ms", lead_ms <= 30, lead_ms, 30, "trim the start so the sound fires on time (or remove the layer delay)", "warn")
    dc = round(float(np.mean(x)), 4) if len(x) else 0.0
    add("dc_offset", abs(dc) < 0.02, dc, 0.02, "remove DC offset (synth.py does this automatically)", "warn")
    add("mono_sfx", not (channels == 2 and duration < 5), channels, "mono for short SFX", "3D/positional SFX should be mono", "warn")

    spectrum = np.abs(np.fft.rfft(x[: sr * 5])) if len(x) else np.zeros(1)
    freqs = np.fft.rfftfreq(min(len(x), sr * 5), 1 / sr) if len(x) else np.zeros(1)
    # power-weighted: magnitude weighting lets quiet high-frequency tails dominate (lowpassed-at-500Hz noise
    # read ~1000 Hz). Power weighting tracks where the energy actually is.
    power = spectrum**2
    centroid = float(np.sum(freqs * power) / max(np.sum(power), 1e-12))
    loud = np.nonzero(np.abs(x) > peak * 0.01)[0] if peak > 0 else np.array([0])
    ears = {
        "peak_dbfs": db(peak),
        "rms_dbfs": db(rms),
        "attack_ms": round(1000 * int(np.argmax(np.abs(x))) / sr, 1) if len(x) else 0,
        "brightness_hz": round(centroid),
        "tail_ms": round(1000 * (loud[-1] - int(np.argmax(np.abs(x)))) / sr) if len(x) else 0,
        "duration_s": round(duration, 3),
        "sample_rate": sr,
        "channels": channels,
    }
    ok = all(c["ok"] for c in checks if c["severity"] == "error")
    return {"file": path, "ok": ok, "checks": checks, "ears": ears}


def main(targets):
    files = []
    for t in targets:
        if os.path.isdir(t):
            files += sorted(os.path.join(t, f) for f in os.listdir(t) if os.path.splitext(f)[1].lower() in FORMATS)
        else:
            files.append(t)
    if not files:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"no audio files in {targets}", "next_action": "render first: lune run kit sfx all", "files": []}))
        return 1
    results = [check_file(f) for f in files]
    bad = [r for r in results if not r["ok"]]
    if bad:
        first = next(c for c in bad[0]["checks"] if not c["ok"] and c["severity"] == "error")
        summary = "; ".join(
            f"{os.path.basename(r['file'])}: " + ", ".join(f"{c['name']}={c['value']}" for c in r["checks"] if not c["ok"] and c["severity"] == "error")
            for r in bad
        )
        next_action = f"{os.path.basename(bad[0]['file'])}: {first['fix']}"
    else:
        summary = " | ".join(f"{os.path.basename(r['file'])} {r['ears']['duration_s']}s {r['ears']['brightness_hz']}Hz" for r in results)
        next_action = "none — proceed (upload via Studio Asset Manager, then: lune run kit asset-id <file> <rbxassetid>)"
    taste = load_taste()
    off = 0
    for r in results:
        r["ear"] = ear_notes(r.get("ears"), taste)
        off += 1 if r["ear"] else 0
    if off:
        summary += f" · the owner's ear: {off} take(s) far from the loved takes on a trait they lean on (files[].ear)"
    print(json.dumps({"schema": 1, "status": "fail" if bad else "pass", "summary": summary, "next_action": next_action, "files": results}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or [os.path.join("build", "sounds")]))
