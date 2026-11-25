"""movesheet.py — the MOVE SHEET: a moveset as something to LOOK at (the systems twin of the anim strip).

Usage: python kit/systems/movesheet.py build/moves/<Set>.json      (normally: lune run kit move [<Set>])
One PNG (build/moves/<Set>.png):
  1 frame data per move: startup (grey) · active (red) · recovery (blue) bars on one frame axis, hitbox frames as
    ticks, the cancel window as a green bracket, VFX / SFX cues as markers, the anim's measured action (white)
    when the frames came from the animation
  2 the combo: each hit's damage with scaling, cumulative, the time-to-kill line
  3 a table: total frames, on-block advantage (+ = attacker's turn, - = punishable), damage, block type
"""

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BG, FG, DIM = "#14161b", "#e8e6e1", "#8a8f99"
COL = {"startup": "#6b7280", "active": "#ef4444", "recovery": "#3b82f6", "cancel": "#22c55e", "anim": "#ffffff"}


def main(path):
    with open(path, encoding="utf-8") as fh:
        s = json.load(fh)
    moves = s["moves"]
    if not moves:
        print(json.dumps({"status": "fail", "summary": "no moves", "next_action": "list moves in the set"}))
        return 1
    fig = plt.figure(figsize=(14, 3 + 0.55 * len(moves) + 4), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[0.55 * len(moves) + 1.2, 4], width_ratios=[1.6, 1], hspace=0.35, wspace=0.18)
    ax = fig.add_subplot(gs[0, :])
    ax.set_facecolor(BG)
    for i, m in enumerate(moves):
        y = len(moves) - 1 - i
        tl = m["timeline"]
        x = 0
        for phase in ("startup", "active", "recovery"):
            w = tl[phase]
            ax.barh(y, w, left=x, height=0.55, color=COL[phase], edgecolor=BG)
            x += w
        for hb in m.get("hitboxes") or []:
            f0, f1 = hb["frames"]
            ax.plot([f0, f1 + 1], [y + 0.36, y + 0.36], color="#fbbf24", lw=3, solid_capstyle="butt")
        c = m.get("cancel")
        if c:
            ax.plot([c["from"], c["to"]], [y - 0.38, y - 0.38], color=COL["cancel"], lw=2.5)
            ax.text(c["to"] + 0.5, y - 0.45, "-> " + ", ".join(c.get("into", [])), color=COL["cancel"], fontsize=7, va="center")
        fa = m.get("from_anim")
        if fa:
            ax.plot([fa["action"][0], fa["action"][1] + 0.001], [y, y], color=COL["anim"], lw=6, alpha=0.8)
        for cue in (m.get("vfx") or []) + (m.get("sfx") or []):
            if "frame" in cue:
                ax.plot(cue["frame"], y + 0.36, marker="v", color="#c084fc", ms=7)
        ax.text(-1, y, f"{m['name']}  ({m['timeline']['fps']:.0f} fps)", color=FG, ha="right", va="center", fontsize=9)
    ax.set_yticks([])
    ax.set_xlabel("frame", color=DIM)
    ax.tick_params(colors=DIM)
    ax.set_xlim(-0.5, max(m["timeline"]["total"] for m in moves) + 12)
    ax.set_title(f"{s['name']} — frame data: startup · ACTIVE · recovery · hitboxes (yellow) · cancel window (green) · "
                 "anim's measured action (white) · cues (purple)", color=FG, fontsize=10, loc="left")
    for sp in ax.spines.values():
        sp.set_color("#30343c")
    # combo
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(BG)
    sim = s.get("combo_sim") or {}
    hits = sim.get("hits") or []
    if hits:
        cum, tot = [], 0
        for h in hits:
            tot += h["damage"]
            cum.append(tot)
        ax.bar(range(len(hits)), [h["damage"] for h in hits], color="#ef4444")
        ax.plot(range(len(hits)), cum, color="#fbbf24", marker="o")
        ax.axhline(s.get("health", 100), color=DIM, ls="--", lw=1)
        ax.set_xticks(range(len(hits)))
        ax.set_xticklabels([h["move"] for h in hits], rotation=20, color=FG, fontsize=8)
        ax.set_title(f"combo: {sim['damage']} damage in {sim['seconds']} s (with scaling) — {sim.get('combos_to_kill')} combo(s) to kill {s.get('health', 100)} HP",
                     color=FG, fontsize=10, loc="left")
    ax.tick_params(colors=DIM)
    for sp in ax.spines.values():
        sp.set_color("#30343c")
    # table
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    lines = [f"{'move':<14}{'frames':>7}{'onBlock':>9}{'dmg':>6}  block"]
    for m in moves:
        ob = m["on_block"]
        lines.append(f"{m['name']:<14}{m['timeline']['total']:>7}{ob:>+9}{m['damage']:>6}  {m['block']}")
    lines += ["", "onBlock: + = attacker keeps the turn,", "  -  = punishable by a faster move"]
    ax.text(0, 1, "\n".join(lines), color=FG, family="monospace", fontsize=8.5, va="top")
    out = os.path.splitext(path)[0] + ".png"
    fig.savefig(out, dpi=85, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    worst = min(moves, key=lambda m: m["on_block"])
    print(json.dumps({"status": "pass", "summary": f"{s['name']}: {len(moves)} move(s); most punishable on block: {worst['name']} ({worst['on_block']:+d} frames)",
                      "next_action": f"look at {out.replace(os.sep, '/')}", "sheet": out.replace(os.sep, "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
