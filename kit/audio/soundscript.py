"""soundscript.py — `kit sfx soundscript <Game>`: the world's SOUND SCRIPT (the audio director's colour script): each
place's chosen sound direction in journey order with its loudness, density, brightness and how long its space rings,
so the journey's DYNAMICS can be seen - quiet after loud, close after open, never one level for an hour.

    python kit/audio/soundscript.py <Game> [--order FirstGrace,DrownedTower,Catacomb,Stormhold] [--out <png>]

Takes each piece's PICKED sketch (games/<Game>/assets/sounds/direction/<Piece>.md), or the recommended one while the
pick is pending; neighbours within 2 LU, 25 % density and 20 % brightness of each other are named (no change of
dynamics there). One JSON line.
"""

import json
import os
import re
import sys

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import direction as D  # noqa: E402
import ears as E  # noqa: E402
import synth  # noqa: E402


def chosen_sketch(doc_path):
    text = open(doc_path, encoding="utf-8").read()
    sec = D.sections(text)
    pick = " ".join(sec.get("Pick", []))
    m = re.match(r"^\s*picked:\s*([A-Z])", pick)
    picked = bool(m)
    if not m:
        m = re.search(r"recommendation:\s*([A-Z])\b", pick)
    letter = m.group(1) if m else "A"
    sk = re.search(rf"^###\s+{letter}\s+[—-].*?^Sketch:\s*(\S+)", "\n".join(sec.get("Directions", [])), re.M | re.S)
    base = os.path.dirname(os.path.dirname(doc_path))
    return (os.path.join(base, sk.group(1)) if sk else None), letter, picked


def measure(path):
    import shutil
    import subprocess

    SR = synth.SR
    # both channels decoded and averaged (ffmpeg's -ac 1 downmix uses its own pan law: ~2.5 LU off the sketch tool)
    raw = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", path, "-ar", str(SR), "-ac", "2", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(np.float64).mean(1)
    lufs = float(E.lufs(x, SR))
    hp = signal.lfilter(*signal.butter(2, 300, "high", fs=SR), x)
    env = np.convolve(np.abs(hp), np.ones(int(0.02 * SR)) / int(0.02 * SR), "same")
    floor = np.percentile(env, 50)
    peaks = signal.find_peaks(env, height=floor * 3 + 1e-9, distance=int(0.12 * SR))[0]
    density = len(peaks) / (len(x) / SR) * 60
    spec = np.abs(np.fft.rfft(x[: min(len(x), SR * 20)]))
    f = np.fft.rfftfreq(min(len(x), SR * 20), 1 / SR)
    bright = float((spec * f).sum() / (spec.sum() + 1e-12))
    # how long the space rings: the median time for a loud event's envelope to fall 20 dB
    rings = []
    for p in peaks[:40]:
        seg = env[p:p + int(2.5 * SR)]
        below = np.nonzero(seg < seg[0] * 0.1)[0]
        if len(below):
            rings.append(below[0] / SR)
    ring = float(np.median(rings)) if rings else 0.0
    return lufs, density, bright, ring, x


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: soundscript.py <Game> [--order a,b,c]", "next_action": "lune run kit sfx soundscript --game <Name>"}))
        return 2
    game = argv[0]
    ddir = os.path.join("games", game, "assets", "sounds", "direction")
    docs = {os.path.splitext(f)[0]: os.path.join(ddir, f) for f in os.listdir(ddir) if f.endswith(".md")} if os.path.isdir(ddir) else {}
    order = argv[argv.index("--order") + 1].split(",") if "--order" in argv else sorted(docs)
    order = [p for p in order if p in docs]
    if len(order) < 2:
        print(json.dumps({"status": "fail", "summary": f"{len(order)} sound direction doc(s): a sound script needs >= 2", "next_action": "lune run kit sfx direction <Piece> --new"}))
        return 1
    rows = []
    for p in order:
        path, letter, picked = chosen_sketch(docs[p])
        if path and os.path.isfile(path):
            lufs, dens, bright, ring, x = measure(path)
            rows.append({"piece": p, "letter": letter, "picked": picked, "lufs": lufs, "density": dens, "bright": bright, "ring": ring, "x": x})
    flat = [f"{a['piece']} -> {b['piece']}" for a, b in zip(rows, rows[1:])
            if abs(a["lufs"] - b["lufs"]) < 2 and abs(a["density"] - b["density"]) <= 0.25 * max(a["density"], b["density"], 1)
            and abs(a["bright"] - b["bright"]) <= 0.2 * max(a["bright"], b["bright"])]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("games", game, "build", "direction", f"{game}_soundscript.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(rows)
    fig = plt.figure(figsize=(3.2 * n, 5.2), dpi=110, facecolor="#15110d")
    for i, r in enumerate(rows):
        ax = fig.add_axes([i / n + 0.01, 0.5, 1 / n - 0.02, 0.38], facecolor="#1f1914")
        ax.specgram(r["x"][: synth.SR * 24], NFFT=1024, Fs=synth.SR, noverlap=512, cmap="magma", vmin=-130)
        ax.set_ylim(40, 12000)
        ax.set_yscale("log")
        ax.axis("off")
        ax.set_title(f"{r['piece']} {r['letter']}" + ("" if r["picked"] else " (rec.)"), color="#ece2d0", fontsize=10)
    cx = fig.add_axes([0.06, 0.08, 0.9, 0.32], facecolor="#1f1914")
    xs = np.arange(n)
    norm = lambda v, lo, hi: [(min(max(t, lo), hi) - lo) / (hi - lo) for t in v]
    cx.plot(xs, norm([r["lufs"] for r in rows], -36, -14), "-o", color="#ece2d0", label="loudness")
    cx.plot(xs, norm([r["density"] for r in rows], 0, 160), "-o", color="#e3a94a", label="density")
    cx.plot(xs, norm([r["bright"] for r in rows], 200, 8000), "-o", color="#8fb3d9", label="brightness")
    cx.plot(xs, norm([r["ring"] for r in rows], 0, 1.5), "-o", color="#b8573a", label="space rings")
    cx.set_xticks(xs, [r["piece"] for r in rows], color="#b3a48c", fontsize=8)
    cx.tick_params(colors="#b3a48c", labelsize=8)
    cx.set_ylim(-0.05, 1.05)
    cx.legend(loc="lower left", fontsize=7, facecolor="#1f1914", labelcolor="#ece2d0", edgecolor="#3a2f24", ncol=4)
    for s in cx.spines.values():
        s.set_color("#3a2f24")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    summary = " -> ".join(f"{r['piece']} {r['letter']}{'' if r['picked'] else '*'} ({r['lufs']:.0f} LUFS, {r['density']:.0f}/min, {r['bright']:.0f} Hz, rings {r['ring']:.2f} s)" for r in rows)
    print(json.dumps({"status": "pass",
                      "summary": f"sound script of {len(rows)} place(s): {summary}" + (f"; NO CHANGE OF DYNAMICS: {', '.join(flat)}" if flat else "; every step changes the dynamics"),
                      "next_action": f"LOOK at {out.replace(os.sep, '/')} (* = recommended, not yet picked)", "flat": flat, "out": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
