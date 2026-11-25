"""av.py — a sound ON its picture: judge it where it lives (a VFX reel, an anim strip GIF, a gameplay clip).

Usage: python kit/audio/av.py <name> --video <file> [--at <seconds>] [--cue <name>@<seconds> ...] [--out DIR]
       (normally: lune run kit sfx av <name> --video build/vfx/booth/starblade_play_front.mp4 --at 0.42)
<name> plays at --at (default 0); every --cue adds another sound at its own time (a whole score on one clip:
--cue sword_swing_medium@0.10 --cue sword_hit_metal_medium@0.31). Takes 1 of each sound. The video keeps its
length; sounds past its end are cut. A GIF / image sequence is converted (H.264, even size, 30 fps).
-> build/sounds/av/<name>.mp4 + one JSON verdict line (the owner watches it; the model reads the cue list).
"""

import json
import os
import shutil
import subprocess
import sys

SOUNDS = os.path.join("build", "sounds")


def probe_duration(path):
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True)
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def main(argv):
    name, video, at, cues, out_dir = None, None, 0.0, [], os.path.join(SOUNDS, "av")
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--video", "--at", "--cue", "--out"):
            v = argv[i + 1]
            if a == "--video":
                video = v
            elif a == "--at":
                at = float(v)
            elif a == "--cue":
                n, _, t = v.rpartition("@")
                cues.append((n, float(t)))
            else:
                out_dir = v
            i += 2
            continue
        name = a
        i += 1
    if not name or not video:
        print(json.dumps({"status": "fail", "summary": "need a sound name and --video <file>", "next_action": "lune run kit sfx av <name> --video <file> [--at s] [--cue name@s ...]"}))
        return 1
    if not os.path.isfile(video):
        print(json.dumps({"status": "fail", "summary": f"no video {video}", "next_action": "record one first (kit vfx play --record, kit anim <Name> writes a GIF strip)"}))
        return 1
    cues = [(name, at)] + cues
    files = []
    for n, t in cues:
        f = n if os.path.isfile(n) else os.path.join(SOUNDS, f"{n}.ogg")
        if not os.path.isfile(f):
            print(json.dumps({"status": "fail", "summary": f"not rendered: {n}", "next_action": f"lune run kit sfx {n} (or kit sfx set <set>)"}))
            return 1
        files.append((f, t))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{os.path.splitext(os.path.basename(name))[0]}.mp4")
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ffmpeg, "-y", "-v", "error", "-i", video]
    for f, _ in files:
        cmd += ["-i", f]
    parts = []
    for k, (_, t) in enumerate(files):
        ms = max(0, int(round(t * 1000)))
        parts.append(f"[{k + 1}:a]aresample=48000,adelay={ms}|{ms},apad[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(files)))
    filt = ";".join(parts) + f";{mix}amix=inputs={len(files)}:normalize=0,alimiter=limit=0.95[aout]"
    filt += ";[0:v]fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[vout]"
    dur = probe_duration(video)
    cmd += ["-filter_complex", filt, "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd.append(out)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out):
        print(json.dumps({"status": "fail", "summary": f"ffmpeg failed: {r.stderr.strip()[-300:]}", "next_action": "check the video plays (ffprobe <file>)"}))
        return 1
    late = [f"{os.path.basename(f)}@{t}" for f, t in files if dur and t >= dur]
    print(json.dumps({
        "status": "pass",
        "summary": f"{out.replace(os.sep, '/')} — {len(files)} cue(s) on {os.path.basename(video)} ({dur and round(dur, 2)} s)",
        "next_action": ("improve the cue times: past the video's end: " + ", ".join(late)) if late else f"look at {out.replace(os.sep, '/')} (the owner watches it with sound)",
        "file": out.replace(os.sep, "/"),
        "cues": [{"sound": f.replace(os.sep, "/"), "at": t} for f, t in files],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
