"""sheet.py — the SOUND SHEET: a picture of a sound for a model that cannot hear it (the audio twin of the anim strip).

Usage: python kit/audio/sheet.py <sound.ogg|name ...> [--ref <file>] [--out DIR] [--sounds DIR] [--loop]
       (normally: lune run kit sfx sheet <name|all> [--ref <file|name>])
A name resolves to build/sounds/<name>.ogg plus its variations <name>_2.ogg ...
Per sound, one PNG (build/sounds/sheets/<name>.png):
  1 waveforms of every variation stacked (do they differ? does one clip?), markers: start, peak, -40 dB tail
  2 log-mel spectrogram 30 Hz - 16 kHz (the ref's beside it with --ref) — where the energy is, how it decays
  3 momentary loudness (LUFS) over time + the spectral centroid over time (does it darken as it dies?)
  4 the ears table (kit/audio/ears.py) and, with --ref, the differences in words, largest first
JSON verdict: {status, summary, next_action, sounds:[{name, file, sheet, ears, variations, ref_delta, words}]}.
"""

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ears as E  # noqa: E402

BG, FG, DIM, ACC, REF = "#14161b", "#e8e6e1", "#8a8f99", "#ff9e3d", "#5ec8ff"


def resolve(target, sounds_dir):
    """A file, or a name -> [main, variations...]."""
    if os.path.isfile(target):
        return os.path.splitext(os.path.basename(target))[0], [target]
    main = os.path.join(sounds_dir, f"{target}.ogg")
    if not os.path.isfile(main):
        return target, []
    takes = [main]
    i = 2
    while os.path.isfile(os.path.join(sounds_dir, f"{target}_{i}.ogg")):
        takes.append(os.path.join(sounds_dir, f"{target}_{i}.ogg"))
        i += 1
    return target, takes


def _style(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=DIM, labelsize=7)
    for s in ax.spines.values():
        s.set_color("#30343c")


def _spec(ax, x, sr, title, color):
    m, frame_s, centres = E.mel(x, sr)
    top = m.max()
    ax.imshow(np.clip(m, top - 80, top), aspect="auto", origin="lower", cmap="magma",
              extent=[0, m.shape[1] * frame_s, 0, len(centres)])
    ticks = [100, 300, 1000, 3000, 10000]
    pos = [int(np.argmin(np.abs(centres - t))) for t in ticks]
    ax.set_yticks(pos)
    ax.set_yticklabels(["100", "300", "1k", "3k", "10k"])
    ax.set_title(title, color=color, fontsize=8, loc="left")
    _style(ax)


def draw(name, takes, out_dir, ref=None, loop=False):
    xs = [E.decode(t)[0] for t in takes]
    sr = E.SR
    x = xs[0]
    ears = E.measure(x, sr, loop=loop)
    var = [E.measure(v, sr, loop=loop) for v in xs[1:]]
    rx = rears = None
    if ref:
        rx = E.decode(ref)[0]
        rears = E.measure(rx, sr, loop=loop)
    rows = 4
    fig = plt.figure(figsize=(12, 8.2), facecolor=BG)
    gs = fig.add_gridspec(rows, 2 if ref else 1, height_ratios=[1.1, 1.6, 1.0, 0.8], hspace=0.45, wspace=0.12)
    # 1 waveforms
    ax = fig.add_subplot(gs[0, :])
    for i, v in enumerate(xs):
        t = np.arange(len(v)) / sr
        off = -2.1 * i
        ax.plot(t, v + off, lw=0.5, color=ACC if i == 0 else FG, alpha=1 if i == 0 else 0.7)
        ax.text(0, off + 0.75, "take 1" if i == 0 else f"_{i + 1}", color=DIM, fontsize=7)
    if rx is not None:
        off = -2.1 * len(xs)
        ax.plot(np.arange(len(rx)) / sr, rx / max(np.abs(rx).max(), 1e-9) + off, lw=0.5, color=REF)
        ax.text(0, off + 0.75, "ref", color=REF, fontsize=7)
    a = np.abs(x)
    ip = int(np.argmax(a))
    loud = np.nonzero(a > a.max() * 0.01)[0]
    for tt, lab in ((ip / sr, "peak"), ((loud[-1] if len(loud) else 0) / sr, "-40 dB")):
        ax.axvline(tt, color=ACC, lw=0.6, ls="--")
        ax.text(tt, 1.05, lab, color=ACC, fontsize=7)
    for o in E.onsets(x, sr):
        ax.axvline(o, color="#9be564", lw=0.5, alpha=0.6)
    ax.set_yticks([])
    ax.set_title(f"{name}  —  {len(xs)} take(s), green = onsets", color=FG, fontsize=10, loc="left")
    _style(ax)
    # 2 spectrograms
    _spec(fig.add_subplot(gs[1, 0]), x, sr, "log-mel spectrogram (80 dB range)", FG)
    if rx is not None:
        _spec(fig.add_subplot(gs[1, 1]), rx, sr, "reference", REF)
    # 3 loudness + centroid over time
    ax = fig.add_subplot(gs[2, 0])
    lm, hop = E.lufs_momentary(x, sr, hop=0.01, window=0.05)
    ax.plot(np.arange(len(lm)) * hop, lm, color=ACC, lw=1.2, label="loudness (50 ms, LUFS)")
    if rx is not None:
        rl, _ = E.lufs_momentary(rx, sr, hop=0.01, window=0.05)
        ax.plot(np.arange(len(rl)) * hop, rl, color=REF, lw=1, label="ref")
    ax.set_ylim(-60, 0)
    ax.legend(fontsize=7, facecolor=BG, labelcolor=FG, edgecolor="#30343c")
    ax.set_title("loudness over time", color=FG, fontsize=8, loc="left")
    _style(ax)
    ax2 = fig.add_subplot(gs[2, 1]) if ref else ax.twinx()
    p, freqs, fs = E.stft_power(x, sr)
    cent, en = E._centroid(p, freqs)
    live = en > en.max() * 1e-4
    t = np.arange(len(cent)) * fs
    ax2.plot(t[live], cent[live], color="#c39bff", lw=1, label="centroid Hz")
    if rx is not None:
        rp, _, _ = E.stft_power(rx, sr)
        rc, ren = E._centroid(rp, freqs)
        rl2 = ren > ren.max() * 1e-4
        ax2.plot((np.arange(len(rc)) * fs)[rl2], rc[rl2], color=REF, lw=1)
    ax2.set_yscale("log")
    ax2.set_ylabel("centroid Hz", color="#c39bff", fontsize=7)
    if ref:
        ax2.set_title("brightness over time (centroid)", color=FG, fontsize=8, loc="left")
    _style(ax2)
    # 4 numbers
    ax = fig.add_subplot(gs[3, :])
    ax.axis("off")
    keys = ["lufs", "true_peak_dbfs", "crest_db", "attack_ms", "transient_ms", "tail_ms", "duration_s",
            "brightness_hz", "centroid_start_hz", "centroid_end_hz", "flux", "onsets", "sub_share", "low_share",
            "mid_share", "high_share"]
    if "seam_db" in ears:
        keys.append("seam_db")
    cols = 4
    lines = []
    for i in range(0, len(keys), cols):
        row = []
        for k in keys[i : i + cols]:
            cell = f"{k:<18}{ears[k]:>8}"
            if rears:
                cell += f" ({rears[k]})"
            row.append(cell)
        lines.append("   ".join(row))
    words = []
    if rears:
        _, words = E.delta(ears, rears)
        lines.append("")
        lines.append("vs ref: " + ("; ".join(words) if words else "no difference that matters"))
    if var:
        spread = {k: round(float(np.std([ears[k]] + [v[k] for v in var])), 2) for k in ("brightness_hz", "tail_ms", "lufs")}
        lines.append(f"variation spread (std): brightness {spread['brightness_hz']} Hz · tail {spread['tail_ms']} ms · loudness {spread['lufs']} LU")
    ax.text(0, 1, "\n".join(lines), color=FG, family="monospace", fontsize=7.6, va="top")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.png")
    fig.savefig(path, dpi=90, facecolor=BG)
    plt.close(fig)
    rec = {"name": name, "file": takes[0].replace("\\", "/"), "sheet": path.replace("\\", "/"), "ears": ears,
           "variations": var}
    if rears:
        d, _ = E.delta(ears, rears)
        rec.update({"ref": ref.replace("\\", "/"), "ref_ears": rears, "ref_delta": d, "words": words,
                    "distance": round(E.distance(ears, rears), 2)})
    return rec


def main(argv):
    out_dir, sounds_dir, ref, loop = os.path.join("build", "sounds", "sheets"), os.path.join("build", "sounds"), None, False
    names = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "--sounds", "--ref"):
            val = argv[i + 1]
            if a == "--out":
                out_dir = val
            elif a == "--sounds":
                sounds_dir = val
            else:
                ref = val
            i += 2
            continue
        if a == "--loop":
            loop = True
        else:
            names.append(a)
        i += 1
    if ref and not os.path.isfile(ref):
        _, rt = resolve(ref, sounds_dir)
        ref = rt[0] if rt else None
        if not ref:
            print(json.dumps({"status": "fail", "summary": f"no reference {argv}", "next_action": "pass --ref <file> or a rendered sound name"}))
            return 1
    if names == ["all"] or not names:
        names = sorted({f[:-4] for f in os.listdir(sounds_dir) if f.endswith(".ogg") and not _is_take(f[:-4], sounds_dir)})
    made, missing = [], []
    for n in names:
        name, takes = resolve(n, sounds_dir)
        if not takes:
            missing.append(n)
            continue
        made.append(draw(name, takes, out_dir, ref, loop))
    if missing and not made:
        print(json.dumps({"status": "fail", "summary": f"not rendered: {', '.join(missing)}",
                          "next_action": f"render first: lune run kit sfx {missing[0]}"}))
        return 1
    hint = "look at " + (made[0]["sheet"] if len(made) == 1 else out_dir + "/<name>.png")
    if ref and made:
        hint = f"improve {made[0]['name']} toward the ref: " + ("; ".join(made[0]["words"][:3]) or "close already — listen: lune run kit sfx listen " + made[0]["name"])
    print(json.dumps({"status": "pass", "summary": f"{len(made)} sheet(s) in {out_dir}" + (f"; missing {missing}" if missing else ""),
                      "next_action": hint, "sounds": made}))
    return 0


def _is_take(stem, d):
    base, _, num = stem.rpartition("_")
    return bool(base) and num.isdigit() and os.path.isfile(os.path.join(d, f"{base}.ogg"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
