"""evolve.py — the OWNER PICKS (mission 02-vfx 5.6): four variants that differ in things the eye sees, side by side.

    lune run kit vfx evolve <name>                    round N: four overlays -> build/vfx/evolve/<name>/round_N/v1..v4.json
                                                      + the PLAYER commands that record each (kit vfx play --evolve)
    lune run kit vfx evolve <name> --sheet [--round N] [--view hero]   the four captures on ONE contact sheet
                                                      -> build/vfx/evolve/<name>/round_N.png (look at it, show the owner)
    lune run kit vfx evolve <name> --pick K [--round N] "<the owner's words>"
                                                      the owner's pick becomes the next round's BASE (assets/effects/
                                                      evolve/<name>.json); record it: kit verdict vfx ... --vs

Five blind parameter rounds burned trust; the owner picks instead. A variant is an OVERLAY played by the PLAYER (kit vfx play --evolve) on top of
the preset (`time` x every time, `scale` x every size, `saturate` +- colour saturation, `mute` layer-name prefixes) —
the preset file, and above all a LOVED preset, is never edited. Each round changes four different things the eye
sees (tempo, size, colour intensity, one layer group off), each round the other way. Two rounds at most without the
owner (AUTONOMY): a third round refuses until a pick is recorded.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import glob
import json
import math
import os
import re
import sys
from collections import Counter

from PIL import Image, ImageDraw, ImageFont

EFFECTS = os.path.join("assets", "effects")
BASES = os.path.join(EFFECTS, "evolve")
OUT = os.path.join("build", "vfx", "evolve")
# GALLERY TUNING (research proposal 10, kit/tools/gallery.py): the OWNER's own picks of earlier rounds steer each axis
# - the way likelier better, or else the way it knows least (mean + KAPPA x std). An agent's pick (made under a blanket
# approval) is never the owner's taste: with no pick of the owner's the alternating rule below stays as it was
KAPPA = 1.0
AXES = (("tempo", "time", 0.8, 1.25, "snappier: every time x0.8", "slower, longer holds"),
        ("size", "scale", 1.25, 0.85, "bigger: every size x1.25", "smaller, tighter"),
        ("colour", "saturate", 0.3, -0.25, "more saturated colours", "calmer colours"))


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status in ("pass", "warn") else 1


def load_base(name):
    p = os.path.join(BASES, f"{name}.json")
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8"))
    return {"effect": name, "base": {}, "rounds": []}


def compose(base, delta):
    """the base overlay with one delta on top: times / scales multiply, saturation adds, mutes join"""
    o = dict(base)
    if "time" in delta:
        o["time"] = round(o.get("time", 1.0) * delta["time"], 3)
    if "scale" in delta:
        o["scale"] = round(o.get("scale", 1.0) * delta["scale"], 3)
    if "saturate" in delta:
        o["saturate"] = round(max(-1.0, min(1.0, o.get("saturate", 0.0) + delta["saturate"])), 3)
    if "mute" in delta:
        o["mute"] = sorted(set(o.get("mute", [])) | set(delta["mute"]))
    return o


def _point(o):
    return {"time": o.get("time", 1.0), "scale": o.get("scale", 1.0), "saturate": o.get("saturate", 0.0),
            "mute": ",".join(sorted(o.get("mute", [])))}


def taste(state):
    """the owner's taste over the overlays -> (gallery.Model, the owner's picks): each round the OWNER picked from
    says its pick beat the other three variants ("none beat the base", pick 0: the base beat all four). A round's base
    is its recorded one, else the replay of the picks before it"""
    tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import gallery as G  # noqa: PLC0415

    space = G.Space(("time", "scale", "saturate"), ("mute",),
                    transform={"time": lambda v: 2 * math.log2(max(v, 1e-3)), "scale": lambda v: 2 * math.log2(max(v, 1e-3)),
                               "saturate": lambda v: 2 * v})
    points, prefs, base, owner = [], [], {}, 0
    for r in state.get("rounds", []):
        rb = r.get("base", base)
        over = {v["k"]: compose(rb, v.get("delta", {})) for v in r.get("variants", [])}
        pick = r.get("pick") or {}
        if pick.get("by") == "owner" and over:
            owner += 1
            at = {k: len(points) + i for i, k in enumerate(sorted(over))}
            points += [_point(over[k]) for k in sorted(over)]
            if pick.get("k", 0) in over:
                prefs += [(at[pick["k"]], at[k]) for k in over if k != pick["k"]]
            else:
                points.append(_point(rb))
                prefs += [(len(points) - 1, at[k]) for k in over]
        if pick.get("k", 0) in over:
            base = over[pick["k"]]
    return G.Model(space, points, prefs), owner


def groups(preset, already):
    """the layer groups by name prefix (ki_flame_3 -> ki_flame), biggest first, not muted yet. Only the secondary bits
    (sprites, lights) are candidates: a mesh layer is the effect's SHAPE (the flame_arc arc) - dropping it is not a
    'layer mix', it is another effect"""
    c = Counter()
    for el in preset.get("layers", []):
        if el.get("kind") not in ("sprite", "light"):
            continue
        n = str(el.get("name", ""))
        g = re.sub(r"[_-]?\d+$", "", n)
        if g and not any(g.startswith(m.rstrip("*")) for m in already):
            c[g] += 1
    return [g for g, _ in c.most_common()]


def cmd_make(name, opts):
    path = os.path.join(EFFECTS, f"{name}.json")
    if not os.path.isfile(path):
        return out("fail", f"evolve: no preset {path}", "lune run kit vfx evolve <existing preset>")
    preset = json.load(open(path, encoding="utf-8"))
    state = load_base(name)
    unpicked = [r for r in state["rounds"] if r.get("pick") is None]
    if len(unpicked) >= 2:
        return out("fail", f"evolve {name}: {len(unpicked)} rounds wait for the owner's pick - a third round needs the owner first",
                   f"show build/vfx/evolve/{name}/round_{unpicked[-1]['round']}.png; then: lune run kit vfx evolve {name} --pick K \"<words>\"")
    n = len(state["rounds"]) + 1
    flip = n % 2 == 0  # each round the other way ...
    last = next((r for r in reversed(state["rounds"]) if r.get("pick")), None)
    won = None  # ... except the axis the last pick chose: it goes FURTHER the same way, a half step
    if last:
        won = next((v for v in last["variants"] if v["k"] == last["pick"]["k"]), {}).get("axis")
    gs = groups(preset, state["base"].get("mute", []))
    mute_group = gs[1 if flip and len(gs) > 1 else 0] if len(gs) > 1 else None  # never drop the ONLY group

    def way(axis, up, down, step_up, step_down):
        if axis == won:  # the picked direction, half again
            dv = next(v for v in last["variants"] if v["k"] == last["pick"]["k"]).get("delta", {})
            # "up" = the first-round direction: snappier (time < 1), bigger (scale > 1), more saturated (saturate > 0)
            went_up = dv.get("time", 1) < 1 or dv.get("scale", 1) > 1 or dv.get("saturate", 0) > 0
            return (step_up if went_up else step_down), (up if went_up else down) + " (further, half a step)"
        return (step_down, down) if flip else (step_up, up)

    t, tw = way("tempo", "snappier: every time x0.8", "slower, longer holds", 0.8, 1.25)
    s, sw = way("size", "bigger: every size x1.25", "smaller, tighter", 1.25, 0.85)
    c, cw = way("colour", "more saturated colours", "calmer colours", 0.3, -0.25)
    if won == "tempo":
        t = 1 + (t - 1) / 2
    if won == "size":
        s = 1 + (s - 1) / 2
    if won == "colour":
        c = c / 2
    # the OWNER's picks steer: each axis the way likelier better, or the way it knows least about (an agent's pick
    # never counts); where they do not separate the two ways, the rule above stays
    model, owner_picks = taste(state)
    steered = []
    if model.evidence():
        vals = {"tempo": [t, tw], "size": [s, sw], "colour": [c, cw]}
        for axis, key, up, down, w_up, w_down in AXES:
            mean, std = model.predict([_point(compose(state["base"], {key: up})), _point(compose(state["base"], {key: down}))])
            ucb = mean + KAPPA * std
            if abs(float(ucb[0] - ucb[1])) < 1e-6:
                continue
            go_up = bool(ucb[0] > ucb[1])
            v = vals[axis][0]
            now_up = v < 1 if key == "time" else v > 1 if key == "scale" else v > 0
            if go_up != now_up:  # the rule went the other way: the owner's picks win, a full step
                vals[axis] = [up if go_up else down, w_up if go_up else w_down]
            lean = (mean[0] > mean[1]) == go_up and abs(float(mean[0] - mean[1])) > 1e-3
            vals[axis][1] += " (your picks lean this way)" if lean else " (to learn)"
            steered.append(axis)
        (t, tw), (s, sw), (c, cw) = vals["tempo"], vals["size"], vals["colour"]
    note = (f"steered by {owner_picks} pick(s) of the owner's on {', '.join(steered)}" if steered
            else "no pick of the owner's yet - the alternating rule (an agent's pick never counts as the owner's taste)"
            if not owner_picks else "the owner's picks do not separate the two ways yet - the alternating rule")
    deltas = [
        ("tempo", {"time": t}, tw),
        ("size", {"scale": s}, sw),
        ("colour", {"saturate": c}, cw),
        ("layer mix", {"mute": [f"{mute_group}*"]} if mute_group else {"time": 1.0}, f"without the '{mute_group}' layers" if mute_group else "the base again (no group to drop)"),
    ]
    d = os.path.join(OUT, name, f"round_{n}")
    os.makedirs(d, exist_ok=True)
    variants = []
    for k, (axis, delta, words) in enumerate(deltas, 1):
        overlay = compose(state["base"], delta)
        overlay["about"] = f"{name} evolve round {n} variant {k}: {words}"
        p = os.path.join(d, f"v{k}.json")
        json.dump(overlay, open(p, "w", encoding="utf-8", newline="\n"), indent=1)
        variants.append({"k": k, "axis": axis, "words": words, "delta": delta, "overlay": p.replace(os.sep, "/")})
    state["rounds"].append({"round": n, "base": dict(state["base"]), "variants": variants, "pick": None})
    os.makedirs(BASES, exist_ok=True)
    json.dump(state, open(os.path.join(BASES, f"{name}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    view = opts.get("--view", "hero")
    cmds = [f"lune run kit vfx play {name} --evolve {n}/{v['k']} --record --views {view}" for v in variants]
    return out("pass", f"evolve {name} round {n} ({note}): " + " | ".join(f"{v['k']} {v['words']}" for v in variants),
               "capture each (Studio open): " + " ; ".join(cmds) + f" ; then lune run kit vfx evolve {name} --sheet",
               round=n, variants=variants, commands=cmds, steered=steered, owner_picks=owner_picks)


def font(size):
    for f in ("segoeuib.ttf", "arial.ttf", "DejaVuSans.ttf"):
        for dd in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu"):
            try:
                return ImageFont.truetype(os.path.join(dd, f), size)
            except OSError:
                continue
    return ImageFont.load_default()


def player_frames(name, n, k, view):
    """the PLAYER recording's frames of one variant (kit vfx play --evolve n/k --record): build/vfx/booth/
    <name>_evo<n>v<k>_play/<view>_NNN.png"""
    return sorted(glob.glob(os.path.join("build", "vfx", "booth", f"{name}_evo{n}v{k}_play", f"{view}_*.*")))


def cmd_sheet(name, opts):
    state = load_base(name)
    if not state["rounds"]:
        return out("fail", f"evolve {name}: no round yet", f"lune run kit vfx evolve {name}")
    n = int(opts.get("--round", state["rounds"][-1]["round"]))
    rnd = next((r for r in state["rounds"] if r["round"] == n), None)
    view = opts.get("--view", "hero")
    rows, missing = [], []
    for v in rnd["variants"]:
        frames = player_frames(name, n, v["k"], view)
        if frames:  # six evenly spaced frames of the PLAYER recording (mission 02-vfx v2: the player is the studio)
            pick = [frames[int(i * (len(frames) - 1) / 5)] for i in range(6)]
            cells = [Image.open(f).convert("RGB") for f in pick]
            cw = 320
            cells = [c.resize((cw, round(c.height * cw / c.width))) for c in cells]
            row = Image.new("RGB", (cw * 6, cells[0].height), (10, 10, 12))
            for i, c in enumerate(cells):
                row.paste(c, (i * cw, 0))
            rows.append((v, row))
        else:
            missing.append(v["k"])
    if missing:
        return out("fail", f"evolve {name} round {n}: no player recording for variant(s) {missing}",
                   " ; ".join(f"lune run kit vfx play {name} --evolve {n}/{k} --record --views {view}" for k in missing))
    w = max(im.width for _, im in rows)
    label_h, f = 30, font(20)
    sheet = Image.new("RGB", (w, sum(im.height + label_h for _, im in rows)), (16, 16, 20))
    dr = ImageDraw.Draw(sheet)
    y = 0
    for v, im in rows:
        dr.text((8, y + 4), f"{v['k']}  —  {v['words']}", font=f, fill=(255, 215, 80))
        sheet.paste(im, (0, y + label_h))
        y += im.height + label_h
    dest = os.path.join(OUT, name, f"round_{n}.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    sheet.save(dest)
    return out("pass", f"evolve {name} round {n}: the four variants on one sheet -> {dest.replace(os.sep, '/')}",
               f"LOOK at it, then the owner picks: lune run kit vfx evolve {name} --pick K \"<words>\"", sheet=dest.replace(os.sep, "/"))


def cmd_rank(name, opts):
    """the round's variants ranked by how close each one's fullest frame (the climax) comes to the bar's climax:
    luma, saturation and hue of the effect pixels (kit/vfx/bar.py's reading). A pointer for a pick made under the
    owner's blanket approval - the owner's eye still outranks it."""
    import numpy as np

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bar as B

    style = opts["--rank-by-bar"]
    entries = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(B.BARS, style, "*.json")))]
    if not entries:
        return out("fail", f"evolve: no bar clips for style {style}", f"lune run kit vfx bar {style} <clip>")
    clim = B.median_bar(entries)["phases"]["climax"]
    state = load_base(name)
    n = int(opts.get("--round", state["rounds"][-1]["round"]))
    rnd = next((r for r in state["rounds"] if r["round"] == n), None)
    view = opts.get("--view", "hero")
    ranked = []
    for v in rnd["variants"]:
        frames = player_frames(name, n, v["k"], view)[::3]
        if not frames:
            return out("fail", f"evolve {name} round {n}: no player recording for variant {v['k']}",
                       f"lune run kit vfx play {name} --evolve {n}/{v['k']} --record --views {view}")
        best = None
        for f in frames:
            a, lum, sat, mask = B.read_frame(f)
            if best is None or mask.mean() > best[0]:
                hp = a[mask & (sat >= 0.2)] / 255.0
                hue = np.zeros(B.HUE_BINS)
                if len(hp):
                    import colorsys

                    hs = [colorsys.rgb_to_hsv(*c)[0] for c in hp[:: max(1, len(hp) // 3000)]]
                    hue = np.histogram(hs, bins=B.HUE_BINS, range=(0, 1))[0].astype(float)
                    hue /= max(hue.sum(), 1)
                best = (float(mask.mean()), float(lum[mask].mean()) if mask.any() else 0.0,
                        float(sat[mask].mean()) if mask.any() else 0.0, hue, os.path.basename(f))
        _, l, s_, h, fr = best
        gaps = {"luma": abs(l - clim["lum"]) / 60.0, "saturation": abs(s_ - clim["sat"]) / 0.25,
                "hue": 0.5 * float(np.abs(h - np.array(clim["hue"])).sum()) * 2.0}
        ranked.append((sum(gaps.values()), v, gaps, l, s_, fr))
    ranked.sort(key=lambda x: x[0])
    lines = [f"{v['k']} {v['words']}: luma {l:.0f} (bar {clim['lum']:.0f}), sat {s_:.2f} (bar {clim['sat']:.2f}), biggest gap {max(g, key=g.get)}"
             for _, v, g, l, s_, _ in ranked]
    return out("pass", f"evolve {name} round {n} vs bar {style}, closest first: " + " | ".join(lines),
               f"closest: {ranked[0][1]['k']} - the owner's eye outranks this; a pick under blanket approval: "
               f"lune run kit vfx evolve {name} --pick {ranked[0][1]['k']} --by agent \"<why>\"",
               ranked=[{"k": v["k"], "words": v["words"], "gaps": g} for _, v, g, _, _, _ in ranked])


def cmd_pick(name, args, opts):
    state = load_base(name)
    if not state["rounds"]:
        return out("fail", f"evolve {name}: no round to pick from", f"lune run kit vfx evolve {name}")
    n = int(opts.get("--round", state["rounds"][-1]["round"]))
    rnd = next((r for r in state["rounds"] if r["round"] == n), None)
    k = int(opts["--pick"])
    v = next((x for x in rnd["variants"] if x["k"] == k), None)
    if k == 0:  # none beat the base (a round inside the noise band): the base stays, the round is closed
        words = " ".join(args).strip() or "no variant beat the base"
        rnd["pick"] = {"k": 0, "words": words, "by": opts.get("--by", "owner")}
        json.dump(state, open(os.path.join(BASES, f"{name}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
        return out("pass", f"evolve {name} round {n}: none picked - the base stays {state['base']}",
                   "a plateau: change STRUCTURE next (a missing part, the reference), not a third parameter round", base=state["base"])
    if v is None:
        return out("fail", f"evolve {name} round {n}: no variant {k}", "pick 0 (keep the base) or 1-4")
    words = " ".join(args).strip()
    if not words:
        return out("fail", "evolve --pick: the owner's words are the record", f"lune run kit vfx evolve {name} --pick {k} \"<the owner's words>\"")
    overlay = json.load(open(v["overlay"], encoding="utf-8"))
    overlay.pop("about", None)
    by = opts.get("--by", "owner")  # "agent" = picked under the owner's blanket approval, never passed off as the owner's eye
    rnd["pick"] = {"k": k, "words": words, "by": by}
    state["base"] = overlay
    json.dump(state, open(os.path.join(BASES, f"{name}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    others = ",".join(f"{name}_evo{n}v{x['k']}" for x in rnd["variants"] if x["k"] != k)
    return out("pass", f"evolve {name} round {n}: {'the owner' if by == 'owner' else by} picked {k} ({v['words']}) - it is the base of the next round",
               f"record it: lune run kit verdict vfx {name}_evo{n}v{k} <0-10> \"{words}\" --vs {others}; next round: lune run kit vfx evolve {name}",
               base=overlay)


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "evolve: needs a preset name", "lune run kit vfx evolve <name> [--sheet | --pick K \"<words>\"]")
    name, rest = argv[0], argv[1:]
    opts, args, i = {}, [], 0
    while i < len(rest):
        if rest[i] == "--sheet":
            opts["--sheet"] = True
            i += 1
        elif rest[i].startswith("--") and i + 1 < len(rest):
            opts[rest[i]] = rest[i + 1]
            i += 2
        else:
            args.append(rest[i])
            i += 1
    if "--pick" in opts:
        return cmd_pick(name, args, opts)
    if "--rank-by-bar" in opts:
        return cmd_rank(name, opts)
    if opts.get("--sheet"):
        return cmd_sheet(name, opts)
    return cmd_make(name, opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
