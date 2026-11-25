"""colorscript.py — `kit world colorscript <Game>`: a COLOUR SCRIPT of a world (the art director's tool: Pixar's colour
scripts) - every place's mood laid out in the order the player meets them, so the journey's rhythm can be SEEN:
warm -> cold, light -> dark, open -> close, never one note for an hour.

    python kit/world/colorscript.py <Game> [--order FirstGrace,DrownedTower,Catacomb,Stormhold] [--out <png>]

For each piece with a world direction doc (games/<Game>/assets/worlds/direction/<Piece>.md) it takes the PICKED frame
(the owner's) or, while the pick is pending, the recommended one (marked as such), measures its palette (5 colours,
k-means), its value (mean luminance) and its warmth (red - blue), and draws: the frames in journey order, their
palettes, and the value / warmth curves. Neighbours that feel the same (value within 0.06 AND warmth within 0.05)
are named: the journey has no change of mood there. One JSON line.
"""

import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import direction as D  # noqa: E402


def chosen_frame(doc_path):
    """(path, letter, picked?) - the owner's pick, else the recommendation"""
    text = open(doc_path, encoding="utf-8").read()
    sec = D.sections(text)
    pick = " ".join(sec.get("Pick", []))
    m = re.match(r"^\s*picked:\s*([A-Z])", pick)
    picked = bool(m)
    if not m:
        m = re.search(r"recommendation:\s*([A-Z])\b", pick)
    letter = m.group(1) if m else "A"
    frame = re.search(rf"^###\s+{letter}\s+[—-].*?^Frame:\s*(\S+)", "\n".join(sec.get("Directions", [])), re.M | re.S)
    base = os.path.dirname(os.path.dirname(doc_path))
    return (os.path.join(base, frame.group(1)) if frame else None), letter, picked


def palette(img, k=5, seed=1):
    """k dominant colours (k-means on a 64x36 thumbnail), largest first"""
    a = np.asarray(img.convert("RGB").resize((64, 36))).reshape(-1, 3).astype(float) / 255
    rng = np.random.default_rng(seed)
    c = a[rng.choice(len(a), k, replace=False)]
    for _ in range(20):
        lab = np.argmin(((a[:, None, :] - c[None]) ** 2).sum(2), 1)
        c = np.array([a[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    counts = np.bincount(lab, minlength=k)
    order = np.argsort(-counts)
    return c[order], counts[order] / counts.sum()


def measure(path):
    from PIL import Image

    img = Image.open(path)
    a = np.asarray(img.convert("RGB")).astype(float) / 255
    value = float((0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).mean())
    warmth = float((a[..., 0] - a[..., 2]).mean())
    cols, share = palette(img)
    return img, value, warmth, cols, share


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: colorscript.py <Game> [--order a,b,c]", "next_action": "lune run kit world colorscript --game <Name>"}))
        return 2
    game = argv[0]
    ddir = os.path.join("games", game, "assets", "worlds", "direction")
    docs = {os.path.splitext(f)[0]: os.path.join(ddir, f) for f in os.listdir(ddir) if f.endswith(".md")} if os.path.isdir(ddir) else {}
    order = argv[argv.index("--order") + 1].split(",") if "--order" in argv else sorted(docs)
    order = [p for p in order if p in docs]
    if len(order) < 2:
        print(json.dumps({"status": "fail", "summary": f"{len(order)} world direction doc(s) in {ddir}: a colour script needs >= 2", "next_action": "lune run kit world direction <Piece> --new"}))
        return 1
    rows = []
    for p in order:
        path, letter, picked = chosen_frame(docs[p])
        if not path or not os.path.isfile(path):
            continue
        img, value, warmth, cols, share = measure(path)
        rows.append({"piece": p, "letter": letter, "picked": picked, "img": img, "value": value, "warmth": warmth, "cols": cols, "share": share})
    flat = []
    for a_, b_ in zip(rows, rows[1:]):
        if abs(a_["value"] - b_["value"]) < 0.06 and abs(a_["warmth"] - b_["warmth"]) < 0.05:
            flat.append(f"{a_['piece']} -> {b_['piece']}")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("games", game, "build", "direction", f"{game}_colorscript.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(rows)
    fig = plt.figure(figsize=(3.2 * n, 6.4), dpi=110, facecolor="#15110d")
    for i, r in enumerate(rows):
        ax = fig.add_axes([i / n + 0.005, 0.42, 1 / n - 0.01, 0.5])
        ax.imshow(r["img"])
        ax.axis("off")
        tag = f"{r['piece']} {r['letter']}" + ("" if r["picked"] else " (rec.)")
        ax.set_title(tag, color="#ece2d0", fontsize=10)
        pa = fig.add_axes([i / n + 0.005, 0.33, 1 / n - 0.01, 0.07])
        x0 = 0.0
        for c, s in zip(r["cols"], r["share"]):
            pa.add_patch(plt.Rectangle((x0, 0), s, 1, color=np.clip(c, 0, 1)))
            x0 += s
        pa.set_xlim(0, 1)
        pa.set_ylim(0, 1)
        pa.axis("off")
    cx = fig.add_axes([0.06, 0.07, 0.9, 0.2], facecolor="#1f1914")
    xs = np.arange(n)
    cx.plot(xs, [r["value"] for r in rows], "-o", color="#ece2d0", label="value (light)")
    cx.plot(xs, [r["warmth"] + 0.5 for r in rows], "-o", color="#e3a94a", label="warmth (+0.5)")
    cx.set_xticks(xs, [r["piece"] for r in rows], color="#b3a48c", fontsize=8)
    cx.tick_params(colors="#b3a48c", labelsize=8)
    cx.set_ylim(0, 1)
    cx.legend(loc="upper right", fontsize=7, facecolor="#1f1914", labelcolor="#ece2d0", edgecolor="#3a2f24")
    for s in cx.spines.values():
        s.set_color("#3a2f24")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    summary = " -> ".join(f"{r['piece']} {r['letter']}{'' if r['picked'] else '*'} (v {r['value']:.2f}, w {r['warmth']:+.2f})" for r in rows)
    print(json.dumps({"status": "pass",
                      "summary": f"colour script of {len(rows)} place(s): {summary}" + (f"; NO CHANGE OF MOOD: {', '.join(flat)}" if flat else "; every step changes the mood"),
                      "next_action": f"LOOK at {out.replace(os.sep, '/')} (* = recommended, not yet picked)" + ("; re-think one of each flat pair" if flat else ""),
                      "flat": flat, "out": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
