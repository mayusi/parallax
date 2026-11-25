"""reel.py — a screen's GAMEPLAY animation, rendered: the preview shows how a screen arrives (motion strip); a reel shows
what happens in play (a hit, the ghost trail draining, a counter rolling, a low-health pulse) as an animated GIF and a
strip of frames, drawn by the same renderer as the preview (kit/ui/preview.py), from a keyframe script.

    python kit/ui/reel.py <Screen> [--ui assets/ui] [--models src/ui] [--out build/ui/reels]

The script: assets/ui/<Screen>.reel.json
{
  "duration": 3.6, "fps": 20, "viewport": "desktop",
  "crop": [x, y, w, h],               (a 1920x1080 region to show; default the whole screen)
  "scale": 0.5,                       (output scale of the cropped region)
  "tracks": [
    {"node": "Bar.Fill", "prop": "size_x", "ease": "out", "keys": [[0, 0.82], [0.6, 0.82], [0.72, 0.54]]},
    {"node": "Hp", "prop": "text", "keys": [[0, "82"], [0.62, "54"]]},
    ...
  ]
}
"node" matches a node path by suffix ("Bar.Fill" finds "Hud.Health.Bar.Fill"). Props:
  per-instant (the preview's animation hook): alpha, scale, dx, dy, wipe, text (step)
  model (written into a copy of the compiled model per frame): size_x, size_y (the Size scale; a Fill's value),
  color (BackgroundColor3), image_color (ImageColor3), text_color (TextColor3), rotation, transparency (BackgroundTransparency),
  image_alpha (ImageTransparency), visible (step), art (step: "<identity>/<piece>" — a flipbook of pictures),
  grad_offset (the x Offset of its "Band" / "Fx_Burn" UIGradient), fx_alpha (an fx layer's own transparency),
  path_t (a "path" node drawn to that share of its length; a "draw" key adds it by itself)
Every node's runtime fx (the spec's "fx": shimmer, ping, burn_in, split, flicker -> Kit_Fx) is added as tracks by
itself (fx_tracks): the reel draws what Ui.fx plays.
Easing per track: linear | in | out | inout | step. Colours interpolate in RGB.
-> build/ui/reels/<Screen>.gif + <Screen>.reel.png (eight frames). A reel is the designer's statement of the game
code's calls (Ui.bar, Ui.punch, Ui.flash, Ui.counter...): it shows the look of the motion, it does not run the runtime.
"""
import argparse
import copy
import json
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preview as P  # noqa: E402

HOOK = {"alpha", "scale", "dx", "dy", "wipe", "text"}
MODEL = {"size_x", "size_y", "color", "image_color", "text_color", "rotation", "transparency", "image_alpha", "visible", "art",
         "grad_offset", "fx_alpha", "path_t"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def ease(kind, k):
    k = max(0.0, min(1.0, k))
    if kind == "in":
        return k * k
    if kind == "out":
        return 1 - (1 - k) * (1 - k)
    if kind == "inout":
        return 0.5 - 0.5 * math.cos(math.pi * k)
    if kind == "back":  # out-back (passes the target ~10% and settles: the Ui runtime's 'back')
        c1 = 1.70158
        return 1 + (c1 + 1) * (k - 1) ** 3 + c1 * (k - 1) ** 2
    if kind == "elastic":
        if k in (0.0, 1.0):
            return k
        return 2 ** (-10 * k) * math.sin((k * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if kind == "bounce":
        n1, d1 = 7.5625, 2.75
        if k < 1 / d1:
            return n1 * k * k
        if k < 2 / d1:
            k -= 1.5 / d1
            return n1 * k * k + 0.75
        if k < 2.5 / d1:
            k -= 2.25 / d1
            return n1 * k * k + 0.9375
        k -= 2.625 / d1
        return n1 * k * k + 0.984375
    return k


def hex_rgb(v):
    v = v.lstrip("#")
    return [int(v[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def value_at(track, t):
    keys = sorted(track["keys"], key=lambda kv: kv[0])
    kind = track.get("ease", "linear")
    if t <= keys[0][0]:
        v = keys[0][1]
        return hex_rgb(v) if isinstance(v, str) and v.startswith("#") else v
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            if kind == "step" or isinstance(v0, (str, bool)) and not (isinstance(v0, str) and v0.startswith("#") and len(v0) == 7):
                return v1 if t >= t1 else v0
            k = ease(kind, (t - t0) / max(t1 - t0, 1e-6))
            if isinstance(v0, str) and v0.startswith("#"):
                a, b = hex_rgb(v0), hex_rgb(v1)
                return [a[i] + (b[i] - a[i]) * k for i in range(3)]
            return v0 + (v1 - v0) * k
    v = keys[-1][1]
    return hex_rgb(v) if isinstance(v, str) and v.startswith("#") else v


def find_paths(model, suffix):
    out = []

    def walk(inst, path):
        if path == suffix or path.endswith("." + suffix):
            out.append((path, inst))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def apply_model(inst, prop, v):
    p = inst.setdefault("Properties", {})
    if prop in ("size_x", "size_y"):
        u = copy.deepcopy((p.get("Size") or {}).get("UDim2") or [[0, 0], [0, 0]])
        u[0 if prop == "size_x" else 1][0] = float(v)
        p["Size"] = {"UDim2": u}
    elif prop == "color":
        p["BackgroundColor3"] = {"Color3": list(v)}
    elif prop == "image_color":
        p["ImageColor3"] = {"Color3": list(v)}
    elif prop == "text_color":  # (a row that turns ink when the selection's swipe lands under it)
        p["TextColor3"] = {"Color3": list(v)}
    elif prop == "rotation":
        p["Rotation"] = float(v)
    elif prop == "transparency":
        p["BackgroundTransparency"] = float(v)
    elif prop == "image_alpha":
        p["ImageTransparency"] = float(v)
    elif prop == "visible":
        p["Visible"] = bool(v)
    elif prop == "grad_offset":  # (an fx band sweeping: the Offset of the node's Band / Fx_Burn gradient)
        for g in inst.get("Children") or []:
            if g.get("ClassName") == "UIGradient" and g.get("Name") in ("Band", "Fx_Burn"):
                g.setdefault("Properties", {})["Offset"] = {"Vector2": [float(v), 0.0]}
    elif prop == "fx_alpha":  # (an fx layer's own transparency, whatever it is: a picture, a text, a fill)
        cls = inst.get("ClassName")
        key = "ImageTransparency" if cls in ("ImageLabel", "ImageButton") else ("TextTransparency" if cls in ("TextLabel", "TextButton") else "BackgroundTransparency")
        p[key] = float(v)
    elif prop == "path_t":  # (a vector line drawn to this share of its length: a "path" node's draw-on)
        p.setdefault("Attributes", {}).setdefault("Attributes", {})["Kit_PathT"] = {"Float64": float(v)}
    elif prop == "art":
        # a FLIPBOOK: swap the picture an image shows ("<identity>/<piece>"; in game: the ImageLabel's Image)
        attrs = p.setdefault("Attributes", {}).setdefault("Attributes", {})
        attrs["KitArt"] = {"String": str(v)}


def set_number(inst, text):
    """a 'number' node (a frame carrying Kit_Digits): show `text` by swapping each cell's picture — the reel's twin of
    Ui.number; cells past the text hide. False when the node is not a number (a label's text is the hook's)"""
    attrs = ((inst.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
    digits = (attrs.get("Kit_Digits") or {}).get("String")
    if not digits:
        return False
    text = str(text)
    cells = {c.get("Name"): c for c in inst.get("Children") or []}
    cw = float((attrs.get("Kit_DigitCell") or {}).get("Float64") or (attrs.get("Kit_DigitCell") or {}).get("Int64") or 0)
    align = (attrs.get("Kit_DigitAlign") or {}).get("String") or "center"
    width = attrs.get("Kit_DigitWidth") or {}
    width = float(width.get("Float64") or width.get("Int64") or cw)
    narrow = {}
    for pair in ((attrs.get("Kit_DigitNarrow") or {}).get("String") or "").split(";"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            try:
                narrow[k] = float(v)
            except ValueError:
                pass

    def code_of(ch):
        return ch if ch.isalnum() else f"u{ord(ch)}"

    def adv_of(ch):
        return int(cw * narrow.get(code_of(ch), 1) + 0.5) if narrow else cw

    total = sum(adv_of(ch) for ch in text)  # (Kit_DigitCell is the advance: each cell centres in its slot, as in Ui.number)
    slot = 0
    for i in range(1, max(len(text), len(cells)) + 1):
        cell = cells.get(f"C{i}")
        if not cell:
            continue  # (the reel keeps the compiled cells: lay the node out for its widest text)
        p = cell.setdefault("Properties", {})
        if i <= len(text):
            ch = text[i - 1]
            code = ch if ch.isalnum() else f"u{ord(ch)}"
            p.setdefault("Attributes", {}).setdefault("Attributes", {})["KitArt"] = {"String": f"{digits}_{code}"}
            p["Visible"] = True
            if cw:  # (re-laid like Ui.number: a shorter text re-centres instead of leaving the old slots)
                a_ = adv_of(ch)
                x = slot + (a_ - width) / 2
                slot += a_
                sx, ox = (1, -(total - x)) if align == "right" else (0, x) if align == "left" else (0.5, x - total / 2)
                p["Position"] = {"UDim2": [[sx, ox], [0, 0]]}
        else:
            p["Visible"] = False
    return True


def sync_art(src, dst):
    """copy every piece in assets/ui/art that is newer than its built copy (a re-rendered flipbook, a redrawn piece):
    the reel paints from the built art, and a reel run right after `kit ui spin` showed the OLD frames -> the count copied"""
    import shutil
    n = 0
    if not os.path.isdir(src):
        return 0
    for ident in os.listdir(src):
        sd, dd = os.path.join(src, ident), os.path.join(dst, ident)
        if not os.path.isdir(sd):
            continue
        for f in os.listdir(sd):
            if not f.endswith(".png"):
                continue
            sp, dp = os.path.join(sd, f), os.path.join(dd, f)
            if os.path.isfile(dp) and os.path.getmtime(dp) >= os.path.getmtime(sp):
                continue
            if not os.path.isfile(dp) and not os.path.isdir(dd):
                continue  # (an identity the compiler has not built yet: kit ui makes it)
            if os.path.isfile(dp):
                from PIL import Image  # noqa: PLC0415
                with Image.open(sp) as a_, Image.open(dp) as b_:
                    if a_.size != b_.size:  # (a new size needs the art index too: only kit ui rebuilds it)
                        print(f"reel: {ident}/{f} changed size — run `lune run kit ui` to rebuild the art index", file=sys.stderr)
                        continue
            shutil.copy2(sp, dp)
            n += 1
    return n


MOVE = {"dx", "dy", "scale", "rotation", "size_x", "size_y"}


def nums(tr):
    """a track's numeric keys in time order (a reel file may list them out of order)"""
    return sorted((k for k in tr.get("keys") or [] if isinstance(k[1], (int, float))), key=lambda k: k[0])


def is_gameplay(tr, dur):
    """a value DRIVEN BY PLAY — a tach needle all race long: it keeps moving in 3+ of the reel's 4 quarters (an entrance
    with a spring settle and an exit key moves in two at most, however many keys it has)"""
    keys = nums(tr)
    quarters = {min(3, int(4 * k1[0] / dur)) for k1, k2 in zip(keys, keys[1:]) if k2[1] != k1[1]} if dur > 0 else set()
    return len(keys) >= 6 and len(quarters) >= 3


def is_meter(tr):
    """a size meter DRAINING (a nitro bar, a health loss): the game's timing, not an entrance — a bar that wipes IN
    (grows) is still an entrance"""
    keys = nums(tr)
    return tr.get("prop") in ("size_x", "size_y") and len(keys) >= 2 and keys[-1][1] < keys[0][1]


def entrance(tr, drift=0.8):
    """a track's ENTRANCE: the first unbroken run of moving segments — it ends at the first hold (a segment that does
    not change) or at a slow segment longer than `drift` s (ambient drift, not an entrance) -> (start, settle) or None"""
    keys = nums(tr)
    segs = list(zip(keys, keys[1:]))
    i = 0
    while i < len(segs) and segs[i][1][1] == segs[i][0][1]:
        i += 1
    if i == len(segs):
        return None
    start, settle = segs[i][0][0], segs[i][0][0]
    v_start, moved = segs[i][0][1], 0.0
    while i < len(segs):
        (t0, v0), (t1, v1) = segs[i]
        # (a slow segment AFTER the arrival is drift only when it is small next to the arrival — a big slow tail, like
        # [-600 -> -300 in 0.2 s -> 0 in 1.2 s], is still the entrance)
        # (and a slow creep of a few % of the travel — a slide held while it drifts on — is the HOLD: the piece has arrived)
        if v1 == v0 or (moved > 0 and t1 - t0 > drift and abs(v1 - v0) < 0.25 * moved) or                 (moved > 0 and t1 - t0 >= 0.3 and abs(v1 - v0) < 0.05 * moved):
            break
        settle = t1
        moved = abs(v1 - v_start)
        i += 1
    return (start, settle) if settle > start else None


def is_ambient(tr, dur):
    """an AMBIENT loop or a tiny drift (a sway that comes back, a 0.6% push-in, a slow turn): life, not an entrance"""
    keys = nums(tr)
    if len(keys) < 2:
        return False
    vals = [k[1] for k in keys]
    rng = max(vals) - min(vals)
    span = keys[-1][0] - keys[0][0]
    tiny = {"scale": 0.03, "dx": 10, "dy": 10, "rotation": 5, "alpha": 0.08}.get(tr.get("prop"), 0)
    hold = max([k2[0] - k1[0] for k1, k2 in zip(keys, keys[1:]) if k2[1] == k1[1]] or [0])
    # (a value that comes back is a loop only without a long HOLD between: enter -> hold -> leave is not ambient)
    returns = abs(vals[-1] - vals[0]) <= 0.1 * rng and len(keys) >= 3 and span >= 0.6 * dur and hold < 0.4
    return rng <= tiny + 1e-9 or returns or (tr.get("prop") == "rotation" and len(keys) <= 3 and span >= 0.8 * dur)


def is_pulse(tr):
    """a PULSE TRAIN: the value leaves its rest and comes back to it twice or more (a flare on each beat) — beats, not an
    entrance"""
    keys = nums(tr)
    if len(keys) < 4:
        return False
    vals = [k[1] for k in keys]
    rng = max(vals) - min(vals)
    near = [abs(v - vals[0]) <= 0.05 * max(rng, 1e-9) for v in vals]
    back = sum(1 for a, b in zip(near, near[1:]) if b and not a)  # (returns to the rest after being away)
    return rng > 0 and back >= 2


def is_shake(tr):
    """a shake: 3+ direction flips packed into 0.6 s, or a JOLT — 2 flips inside 0.15 s (a wobbly settle over a long slide
    is not one)"""
    keys = nums(tr)
    flips = [k2[0] for k1, k2, k3 in zip(keys, keys[1:], keys[2:]) if (k2[1] - k1[1]) * (k3[1] - k2[1]) < 0]
    rng = (max(k[1] for k in keys) - min(k[1] for k in keys)) if keys else 0
    at_rest = bool(keys) and abs(keys[-1][1] - keys[0][1]) <= 0.1 * max(rng, 1e-9)  # (a spring SETTLE starts elsewhere)
    jolt = any(flips[j + 1] - flips[j] <= 0.15 for j in range(len(flips) - 1))
    return at_rest and (jolt or any(flips[j + 2] - flips[j] <= 0.6 for j in range(len(flips) - 2)))


def hide_times(tracks):
    """when each node goes out of sight: visible -> false, alpha -> 0, transparency -> 1"""
    out = {}
    for tr in tracks:
        p, keys = tr.get("prop"), sorted(tr.get("keys") or [], key=lambda k: k[0])
        gone = {"visible": lambda v: v is False, "alpha": lambda v: v == 0, "transparency": lambda v: v == 1}.get(p)
        if gone:
            out.setdefault(tr.get("node", ""), []).extend(k2[0] for k1, k2 in zip(keys, keys[1:]) if gone(k2[1]) and not gone(k1[1]))
    return out


def critique(tracks, dur, fps, focus=()):
    """MOTION notes from the reel's own keys (research 2026-10-14: Material 3 motion tokens — entrances ~150-600 ms with
    an ease-out, exits shorter; never linear for UI movement; siblings staggered 2-5 frames; a small overshoot on the hero
    beat; a still moment to READ before the end). Advice, not a gate: a deliberate slam may break a rule"""
    notes = []
    hidden = hide_times(tracks)
    for tr in tracks:
        p, ease = tr.get("prop"), tr.get("ease", "linear")
        node = tr.get("node", "")
        if p not in MOVE or ease == "step":
            continue
        keys = nums(tr)
        if len(keys) < 2:
            continue
        loop = is_ambient(tr, dur) or is_pulse(tr)  # (a slow turn, a sway that comes back, a tiny drift, beats: not an entrance)
        shake = is_shake(tr)
        # (a value DRIVEN BY GAMEPLAY — a tach needle all race long, many keys over most of the reel — is not an entrance;
        # a meter draining at a steady rate is right to be linear)
        if is_gameplay(tr, dur) or is_meter(tr):
            continue
        if ease == "linear" and not loop and not shake:
            notes.append({"node": node, "prop": p, "note": f"{node}.{p} moves LINEAR: use ease out to enter, ease in to leave"})
        en = entrance(tr)
        # (a piece moving until it is hidden — a damage number floating up — floats AWAY: not a slow entrance)
        if en and any(abs(h - en[1]) <= 0.05 for h in hidden.get(node, [])):
            en = None
        if en and not loop and not shake:
            d = en[1] - en[0]
            if d > 0.8:
                notes.append({"node": node, "prop": p, "note": f"{node}.{p} takes {d:.2f} s to settle: entrances read best at 0.15-0.6 s"})
    # siblings that all start together: stagger them
    starts = {}
    for tr in tracks:
        # (slides and fades only: pieces PUNCHING together on one hit, or sharing one shake, are simultaneous on purpose)
        if tr.get("prop") in ("dx", "dy", "alpha") and tr.get("ease") != "step" and not is_shake(tr) and not is_ambient(tr, dur):
            en = entrance(tr)
            if en:
                parent = tr["node"].rsplit(".", 1)[0] if "." in tr["node"] else ""  # (root-level pieces share the root)
                starts.setdefault((parent, tr["prop"], round(en[0] * fps)), set()).add(tr["node"])
    for (parent, p, f), nodes in starts.items():
        if len(nodes) >= 3:
            notes.append({"node": parent, "prop": p, "note": f"{len(nodes)} pieces under {parent} start their {p} on the same frame: stagger them 2-5 frames"})
    # the hero / focus beat: an overshoot gives it weight
    for tr in tracks:
        node = tr.get("node", "")
        if focus and tr.get("prop") == "scale" and any(node == f or node.endswith("." + f) or f.endswith("." + node) for f in focus):
            vals = [k[1] for k in tr.get("keys") or [] if isinstance(k[1], (int, float))]
            rest = vals[-1] if vals else 1
            # (only a hero that ARRIVES by scale: one already on screen at rest that just punches, or a tiny push-in, has no
            # entrance to overshoot)
            # (a 'back' / 'elastic' / 'bounce' ease overshoots by itself, though no key shows it)
            arrives = vals and abs(vals[0] - rest) > 0.05 and not is_ambient(tr, dur) and tr.get("ease") not in ("back", "elastic", "bounce")
            if arrives and not any((v - rest) * (vals[0] - rest) < 0 for v in vals):
                notes.append({"node": tr["node"], "prop": "scale", "note": f"the hero {tr['node']} arrives without an overshoot: pass the rest a little (~3-8%) and settle"})
    # a still moment to read
    last = 0.0
    for tr in tracks:
        en = entrance(tr) if tr.get("prop") in MOVE | {"alpha"} else None
        # (a blink, a loop, a shake, a gameplay-driven value or a meter is not an entrance)
        loop = tr.get("ease") == "step" or is_ambient(tr, dur) or is_pulse(tr) or is_shake(tr) or is_gameplay(tr, dur) or is_meter(tr)
        if en and not loop and en[1] < dur:
            last = max(last, en[1])
    if dur - last < 0.4:
        notes.append({"node": "", "prop": "", "note": f"the last entrance settles {dur - last:.2f} s before the end: leave ~0.5 s still to READ it"})
    return notes


def frame_names(m):
    """a macro's frames: a list, or a template "<id>/<name>_{k}" with "count" (k = 0..count-1)"""
    fr = m.get("frames")
    if isinstance(fr, str):
        return [fr.replace("{k}", str(k)) for k in range(int(m.get("count", 1)))]
    return list(fr or [])


def burst_presets(base):
    """the screen's burst presets (Kit_Burst_<name> = "sprite=..;count=..;...") -> {name: {k: v}}"""
    a = ((base.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
    out = {}
    for k, v in a.items():
        if k.startswith("Kit_Burst_"):
            d = {}
            for pair in str((v or {}).get("String") or "").split(";"):
                kk, _, vv = pair.partition("=")
                if kk:
                    d[kk] = vv
            out[k[len("Kit_Burst_"):]] = d
    return out


def burst_parts(p, seed):
    """one burst's particles as Ui.burst flies them (seeded: a reel draws the same film every time)"""
    import random
    rnd = random.Random(seed)
    pair = lambda s, a, b: tuple(float(x) for x in s.split(",")) if s and "," in s else (a, b)  # noqa: E731
    s0, s1 = pair(p.get("speed"), 220, 520)
    z0, z1 = pair(p.get("size"), 12, 30)
    spread, angle, spin = float(p.get("spread", 360)), float(p.get("angle", -90)), float(p.get("spin", 180))
    cols = [c for c in (p.get("colors") or "#ffffff").split(",") if c.startswith("#")] or ["#ffffff"]
    parts = []
    for _ in range(int(float(p.get("count", 14)))):
        a = math.radians(angle + spread * (rnd.random() - 0.5))
        spd = s0 + (s1 - s0) * rnd.random()
        parts.append({"v": (math.cos(a) * spd, math.sin(a) * spd), "size": z0 + (z1 - z0) * rnd.random(),
                      "rot": rnd.random() * 360, "spin": spin * (rnd.random() * 2 - 1), "col": tuple(int(round(c * 255)) for c in hex_rgb(cols[rnd.randrange(len(cols))]))})
    return parts


def burst_frame(im, t, fires, presets):
    """draw every burst alive at time t over a frame (fires: [(t0, origin (x, y), preset name, seed)])"""
    for t0, origin, name, seed in fires:
        p = presets.get(name)
        if not p:
            continue
        life = float(p.get("life", 0.6))
        dt = t - t0
        if dt < 0 or dt > life:
            continue
        k = dt / life
        g = float(p.get("gravity", 900))
        sprite = P.art_image(p.get("art")) if p.get("art") else None
        for q in burst_parts(p, seed):
            x = origin[0] + q["v"][0] * dt
            y = origin[1] + q["v"][1] * dt + 0.5 * g * dt * dt
            sz = max(1, int(q["size"] * ((1 - 0.7 * k) if p.get("shrink", "1") != "0" else 1)))
            alpha = (1 - k) if p.get("fade", "1") != "0" else 1
            if sprite is not None:
                spr = P.tint(sprite.resize((sz, sz), Image.LANCZOS), tuple(int(c) for c in q["col"]), 1 - alpha)
            else:
                spr = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
                ImageDraw.Draw(spr).ellipse([0, 0, sz - 1, sz - 1], fill=tuple(int(c) for c in q["col"]) + (int(255 * alpha),))
            spr = spr.rotate(-(q["rot"] + q["spin"] * dt), expand=True, resample=Image.BICUBIC)
            px_, py_ = int(x - spr.width / 2), int(y - spr.height / 2)
            if 0 <= px_ < im.width - spr.width and 0 <= py_ < im.height - spr.height:
                im.alpha_composite(spr, (px_, py_))
    return im


def visible_at(model, path):
    """is a node shown in this frame's model (itself and every ancestor Visible)"""
    node, parts = None, path.split(".")
    level = model.get("Children") or []
    for name in parts:
        node = next((c for c in level if c.get("Name") == name), None)
        if node is None or (node.get("Properties") or {}).get("Visible") is False:
            return False
        level = node.get("Children") or []
    return True


def burst_nodes(base):
    """[(path, preset, delay)] for every node whose burst fires when it shows"""
    out = []

    def walk(inst, path):
        a = ((inst.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
        if (a.get("Kit_BurstOn") or {}).get("String") == "show":
            out.append((path, (a.get("Kit_BurstPreset") or {}).get("String"), float((a.get("Kit_BurstDelay") or {}).get("Float64") or 0)))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in base.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def expand_macros(tracks, dur):
    """REEL MACROS — the mechanics every reel repeats, one line each (a library of motion MECHANICS, never a look):
      {"macro": "flipbook", "node": N, "frames": [...] | "<id>/<p>_{k}", "count": n, "from": t0, "to": t1, "reverse": false}
          the frames played once, evenly from t0 to t1, holding the last (a drip running, a spin, an iris, a swipe)
      {"macro": "cycle", "node": N, "frames": ..., "fps": 12}   the frames looped all reel long (film grain, a flicker)
      {"macro": "weave", "node": N, "amp": [2, 3], "fps": 12, "seed": 7}   film gate weave: the picture jitters by whole
          pixels at the film's rate (dx and dy, step)
      {"macro": "burst", "node": N, "at": t, "preset": "smash"}   UI particles fly out of the node at t (Ui.burst);
          a node with a "burst" key fires by itself when it shows
    a plain track passes through untouched"""
    import random as _r
    out = []
    for m in tracks:
        kind = m.get("macro")
        if not kind:
            out.append(m)
            continue
        node = m.get("node", "")
        if kind == "burst":  # (UI particles: drawn over the frames by the main loop, not a track)
            continue
        if kind in ("cycle", "weave") and float(m.get("fps", 12)) <= 0:
            out.append({"node": node, "prop": f"macro {kind}: fps must be > 0", "keys": []})
            continue
        if kind == "flipbook":
            fr = frame_names(m)
            if not fr:
                out.append({"node": node, "prop": "art", "ease": "step", "keys": [], "from_macro": "flipbook"})  # (check_tracks: no keys)
                continue
            if m.get("reverse"):
                fr = fr[::-1]
            t0, t1 = float(m.get("from", 0)), float(m.get("to", dur))
            n = max(1, len(fr))
            keys = ([[0, fr[0]]] if t0 > 0 else []) + [[round(t0 + (t1 - t0) * k / n, 4), f] for k, f in enumerate(fr)]
            out.append({"node": node, "prop": "art", "ease": "step", "keys": keys, "from_macro": "flipbook"})
        elif kind == "cycle":
            fr = frame_names(m)
            step = 1.0 / float(m.get("fps", 12))
            n = int(dur / step) + 1
            out.append({"node": node, "prop": "art", "ease": "step", "from_macro": "cycle",
                        "keys": [[round(i * step, 4), fr[i % len(fr)]] for i in range(n)] if fr else []})
        elif kind == "weave":
            amp = m.get("amp", [2, 2])
            ax, ay = (amp, amp) if isinstance(amp, (int, float)) else (amp[0], amp[1])
            rnd = _r.Random(int(m.get("seed", 7)))
            step = 1.0 / float(m.get("fps", 12))
            n = int(dur / step) + 1
            for prop, a_ in (("dx", ax), ("dy", ay)):
                out.append({"node": node, "prop": prop, "ease": "step", "from_macro": "weave",
                            "keys": [[round(i * step, 4), rnd.randint(-max(1, int(round(a_))), max(1, int(round(a_))))] for i in range(n)]})
        else:
            out.append(m)  # (an unknown macro reaches check_tracks: "unknown prop")
    return out


def check_tracks(tracks, base):
    """every problem with a reel's tracks against the compiled model (an empty list: good)"""
    bad = []
    for tr in tracks:
        if tr.get("prop") not in HOOK | MODEL:
            bad.append(f"{tr.get('node')}.{tr.get('prop')}: unknown prop (hook: {', '.join(sorted(HOOK))}; model: {', '.join(sorted(MODEL))})")
        elif not find_paths(base, tr.get("node", "")):
            bad.append(f"{tr.get('node')}: no node with that path suffix")
        elif not tr.get("keys"):
            bad.append(f"{tr.get('node')}.{tr.get('prop')}: no keys")
        elif tr.get("prop") in ("size_x", "size_y") and not all(isinstance(k[1], (int, float)) for k in tr["keys"]):
            bad.append(f"{tr.get('node')}.{tr.get('prop')}: every key must be a number, a share of the parent (0..1)")
        elif tr.get("prop") in ("size_x", "size_y") and any(abs(float(k[1])) > 4 for k in tr["keys"]):
            # (size_x / size_y write the Size SCALE: a key of 694 is a clip 694 times its parent, the drop never shows)
            big = max(abs(float(k[1])) for k in tr["keys"])
            bad.append(f"{tr.get('node')}.{tr.get('prop')}: a key of {big:g} looks like PIXELS; size_x / size_y are a share of the parent "
                       "(0..1): size the node in % and key shares")
    return bad


def parse_fx(enc):
    """Kit_Fx "kind:k=v,k=v;..." -> [(kind, {k: v})]"""
    out = []
    for item in (enc or "").split(";"):
        kind, _, rest = item.partition(":")
        if not kind:
            continue
        v = {}
        for kv in rest.split(","):
            k, _, x = kv.partition("=")
            try:
                v[k] = float(x)
            except ValueError:
                pass
        out.append((kind, v))
    return out


def fx_for(path, enc, dur):
    """the tracks one node's fx play over a reel of `dur` seconds (the same timings as Ui.fx; split / flicker bursts
    from a random seeded by the node's path, so a reel draws the same film every time)"""
    import random
    rnd = random.Random(sum(ord(c) for c in path))
    tracks = []
    for kind, v in parse_fx(enc):
        if kind == "shimmer":
            per, t = v.get("period", 2.6), v.get("delay", 0.0)
            keys = [[0, -1.0]]
            while t < dur:
                keys += [[t, -1.0], [t + per * 0.45, 1.0], [t + per * 0.45 + 0.001, -1.0]]
                t += per
            tracks.append({"node": path + ".Fx_Shimmer", "prop": "grad_offset", "ease": "inout", "keys": keys})
        elif kind == "ping":
            per, t, s_, a_ = v.get("period", 1.6), v.get("delay", 0.0), v.get("scale", 1.12), v.get("alpha", 0.6)
            sk, ak = [[0, 1.0]], [[0, 1.0]]
            while t < dur:
                sk += [[t, 1.0], [t + per * 0.6, s_], [t + per - 0.001, s_]]
                ak += [[t - 0.001 if t > 0 else 0, 1.0], [t, 1 - a_], [t + per * 0.6, 1.0]]
                t += per
            tracks.append({"node": path + ".Fx_Ping", "prop": "scale", "ease": "out", "keys": sk})
            tracks.append({"node": path + ".Fx_Ping", "prop": "fx_alpha", "ease": "out", "keys": ak})
        elif kind == "burn_in":
            d0, d1 = v.get("delay", 0.0), v.get("delay", 0.0) + v.get("dur", 0.6)
            tracks.append({"node": path, "prop": "grad_offset", "ease": "inout", "keys": [[0, -1.0], [d0, -1.0], [d1, 1.0]]})
            tracks.append({"node": path + ".Fx_BurnEdge", "prop": "grad_offset", "ease": "inout", "keys": [[0, -1.0], [d0, -1.0], [d1, 1.0]]})
            tracks.append({"node": path + ".Fx_BurnEdge", "prop": "fx_alpha", "ease": "linear",
                           "keys": [[0, 1.0], [max(0.0, d0 - 0.001), 1.0], [d0, 0.0], [d1, 0.0], [d1 + 0.15, 1.0]]})
        elif kind in ("split", "flicker"):
            every, burst = v.get("every", 3.0 if kind == "split" else 3.5), v.get("dur", 0.14 if kind == "split" else 0.35)
            t = every * (0.7 + rnd.random() * 0.6)
            if kind == "split":
                ka, kb, al = [[0, 0.0]], [[0, 0.0]], [[0, 1.0]]
            else:
                fl = [[0, 1.0]]
            while t < dur:
                f = t
                while f < t + burst:
                    j = rnd.randint(-1, 1)
                    if kind == "split":
                        px = v.get("px", 4)
                        ka.append([f, px + j])
                        kb.append([f, -px - j])
                        al.append([f, 1 - v.get("alpha", 0.55)])
                    else:
                        fl.append([f, 1 - v.get("depth", 0.4) if rnd.random() < 0.5 else 1.0])
                    f += 1 / 30
                if kind == "split":
                    al.append([t + burst, 1.0])
                else:
                    fl.append([t + burst, 1.0])
                t += burst + every * (0.7 + rnd.random() * 0.6)
            if kind == "split":
                for nm, ks in (("Fx_SplitA", ka), ("Fx_SplitB", kb)):
                    tracks.append({"node": f"{path}.{nm}", "prop": "dx", "ease": "step", "keys": ks})
                    tracks.append({"node": f"{path}.{nm}", "prop": "fx_alpha", "ease": "step", "keys": al})
                # (during a burst the piece shows as its copy ON TOP of the ghosts, as Ui.fx does)
                on = [[k[0], 0.0 if k[1] < 1 else 1.0] for k in al]
                tracks.append({"node": f"{path}.Fx_SplitC", "prop": "fx_alpha", "ease": "step", "keys": on})
            else:
                tracks.append({"node": path, "prop": "alpha", "ease": "step", "keys": fl})
    return tracks


def fx_tracks(base, dur, given=()):
    """every node's runtime fx as tracks (a node + prop the reel script already keys is left to the script)"""
    out = []
    taken = {(tr.get("node"), tr.get("prop")) for tr in given}

    def walk(inst, path):
        a = ((inst.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
        enc = (a.get("Kit_Fx") or {}).get("String")
        if enc:
            out.extend(tr for tr in fx_for(path, enc, dur) if (tr["node"], tr["prop"]) not in taken)
        draw = (a.get("Kit_PathDraw") or {}).get("String")
        if draw and (path, "path_t") not in taken:  # (a vector line drawing itself on, as Ui.path does at bind)
            d_, _, w_ = draw.partition(",")
            d_, w_ = float(d_ or 0.6), float(w_ or 0)
            out.append({"node": path, "prop": "path_t", "ease": "out", "keys": [[0, 0.0], [w_, 0.0], [w_ + d_, 1.0]]})
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in base.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def frame_state(base, tracks, t):
    """the reel at time t: (the model with the tracks' model properties set, the anim hook the preview draws on top)"""
    model = copy.deepcopy(base)
    hook = {}
    for tr in tracks:
        v = value_at(tr, t)
        for path, inst in find_paths(model, tr["node"]):
            if tr["prop"] == "text" and set_number(inst, v):
                continue  # (a digit-set number: its cells' pictures change, as Ui.number does in game)
            if tr["prop"] in MODEL:
                apply_model(inst, tr["prop"], v)
            else:
                h = hook.setdefault(path, {})
                if tr["prop"] in ("dx", "dy") and tr["prop"] in h:
                    h[tr["prop"]] += v  # (offsets ADD: a gate weave rides on top of a slide, it does not replace it)
                else:
                    h[tr["prop"]] = v

    def anim(path, inst, hook=hook):
        # a node rides on its nearest animated ancestor (dx / dy / alpha / scale of a group move its children)
        st = {}
        node = path
        while node:
            if node in hook:
                for k, v in hook[node].items():
                    if k == "text" and node != path:
                        continue
                    if k in ("dx", "dy"):
                        st[k] = st.get(k, 0) + v
                        if node != path:  # (an ancestor's slide moves the clip it imposes, the node's own does not)
                            st["c" + k] = st.get("c" + k, 0) + v
                    elif k in ("alpha", "scale") and k in st:
                        st[k] *= v
                    else:
                        st.setdefault(k, v)
            node = node.rpartition(".")[0]
        if "text" in st and st["text"] is not None:
            st["text"] = str(st["text"])
        return st or None

    return model, anim


STATE_PROPS = ("Size", "Rotation", "Visible", "BackgroundTransparency", "ImageTransparency", "TextColor3", "BackgroundColor3", "ImageColor3")


def export_states(a, base, tracks, moments):
    """the reel's state at chosen moments, per animated node, as the ENGINE takes it (kit/ui/booth.luau reel mode):
    the model properties the tracks set (Size, Visible, transparencies, colours, the picture's KitArt) and the hooks
    the preview draws on top (dx / dy offsets, scale, alpha, text) — the same numbers this reel's frames are drawn from,
    so an engine capture beside the preview's frame shows only the difference in DRAWING"""
    out = {"schema": 1, "screen": a.screen, "moments": []}
    for t in moments:
        model = copy.deepcopy(base)
        nodes = {}
        for tr in tracks:
            v = value_at(tr, t)
            for path, inst in find_paths(model, tr["node"]):
                st = nodes.setdefault(path, {})
                if tr["prop"] == "text" and set_number(inst, v):
                    st["number"] = str(v)
                    continue
                if tr["prop"] in MODEL:
                    apply_model(inst, tr["prop"], v)
                    st["_model"] = inst
                elif tr["prop"] in ("dx", "dy"):
                    st[tr["prop"]] = st.get(tr["prop"], 0) + float(v)
                elif tr["prop"] == "text":
                    st["text"] = str(v)
                else:
                    st[tr["prop"]] = v
        rows = {}
        for path, st in nodes.items():
            inst = st.pop("_model", None)
            row = {k: v for k, v in st.items()}
            if inst is not None:
                p = inst.get("Properties") or {}
                for k in STATE_PROPS:
                    if k in p:
                        row[k] = p[k]
                art = (((p.get("Attributes") or {}).get("Attributes") or {}).get("KitArt") or {}).get("String")
                if art:
                    row["KitArt"] = art
            rows[path] = row
        out["moments"].append({"t": t, "nodes": rows})
    path = a.states_out or os.path.join(a.out, f"{a.screen}.states.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # the PREVIEW's own frame at each moment (full 1920x1080), to lay beside the engine's capture
    frames_dir = os.path.splitext(path)[0] + "_preview"
    os.makedirs(frames_dir, exist_ok=True)
    for i, t in enumerate(moments, 1):
        model, anim = frame_state(base, tracks, t)
        im, _ = P.draw_viewport(model, 1920, 1080, "desktop", anim)
        im.convert("RGB").save(os.path.join(frames_dir, f"preview_{i:03d}.png"))
    out["preview_frames"] = frames_dir.replace("\\", "/")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
    return emit("pass", f"reel {a.screen}: the state of {len(rows)} animated node(s) at {len(moments)} moment(s) -> {path}",
                "play them in the engine: the booth's reel mode (kit/ui/booth.luau) sets these on the built screen and grabs each moment")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--out", default="build/ui/reels")
    ap.add_argument("--art", default="build/ui/art", help="the drawn + uploaded art the preview paints (kit ui writes it)")
    ap.add_argument("--states", default=None, help="t,t,...: export the animated nodes' state at these moments (the booth's reel mode)")
    ap.add_argument("--states-out", default=None)
    a = ap.parse_args()
    P.ART_DIR = a.art  # (the preview's art lookup, set in its own main otherwise: without it every piece is a placeholder)
    synced = sync_art(os.path.join(a.ui, "art"), a.art)
    reel_path = os.path.join(a.ui, f"{a.screen}.reel.json")
    model_path = os.path.join(a.models, f"{a.screen}.model.json")
    if not os.path.isfile(reel_path):
        return emit("fail", f"reel: no script at {reel_path}", "write it (the shape: top of kit/ui/reel.py), then run again")
    if not os.path.isfile(model_path):
        return emit("fail", f"reel: no compiled model at {model_path}", "lune run kit ui")
    reel = json.load(open(reel_path, encoding="utf-8"))
    base = json.load(open(model_path, encoding="utf-8"))
    dur = float(reel.get("duration", 3.0))
    tracks = expand_macros(reel.get("tracks") or [], dur)
    tracks = tracks + fx_tracks(base, dur, tracks)  # (the screen's runtime fx, as Ui.fx plays them)
    bad = check_tracks(tracks, base)
    if bad:
        return emit("fail", f"reel: {len(bad)} bad track(s)", bad[0], problems=bad)
    fps = int(reel.get("fps", 20))
    label = reel.get("viewport", "desktop")
    sw, sh = {"desktop": (1920, 1080), "tablet": (1024, 768), "phone": (844, 390)}[label]
    crop = reel.get("crop") or [0, 0, sw, sh]
    out_scale = float(reel.get("scale", 0.5))
    if a.states:
        return export_states(a, base, tracks, [float(x) for x in a.states.split(",") if x.strip()])
    frames = []
    n = max(2, int(round(dur * fps)) + 1)
    presets = burst_presets(base)
    watch = burst_nodes(base) if presets else []
    shown = {pth: False for pth, _, _ in watch}
    fires = []  # (t0, origin, preset, seed): a node's burst fires when it shows, a "burst" macro at its time
    for m in reel.get("tracks") or []:
        if m.get("macro") == "burst":
            fires.append((float(m.get("at", 0)), m.get("node"), m.get("preset"), len(fires) + 1))
    for i in range(n):
        t = i / fps
        model, anim = frame_state(base, tracks, t)
        im, _ = P.draw_viewport(model, sw, sh, label, anim)
        if presets:
            for pth, preset, delay in watch:
                v = visible_at(model, pth)
                if v and not shown[pth]:
                    fires.append((t + delay, pth, preset, len(fires) + 1))
                shown[pth] = v
            live = []
            for t0, who, preset, seed in fires:
                bx = P.ALL_BOXES.get(who) or next((b for k, b in P.ALL_BOXES.items() if k.endswith("." + str(who))), None)
                if bx:
                    live.append((t0, (bx[0] + bx[2] / 2, bx[1] + bx[3] / 2), preset, seed))
            im = burst_frame(im.convert("RGBA"), t, live, presets)
        im = im.convert("RGB").crop((crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]))
        im = im.resize((max(1, int(crop[2] * out_scale)), max(1, int(crop[3] * out_scale))), Image.LANCZOS)
        frames.append((t, im))
    os.makedirs(a.out, exist_ok=True)
    gif = os.path.join(a.out, f"{a.screen}.gif")
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for _, f in frames]
    pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / fps), loop=0, disposal=2)
    # the strip: eight frames, each stamped with its time
    # "strip": the moments to show (an impact lasts a few frames: an even spread misses it); else eight even ones
    want = reel.get("strip")
    if isinstance(want, list) and want:
        pick = [min(frames, key=lambda f, t=t: abs(f[0] - float(t))) for t in want[:8]]
        pick += [frames[-1]] * (8 - len(pick))
    else:
        pick = [frames[round(k * (len(frames) - 1) / 7)] for k in range(8)]
    fw, fh = pick[0][1].size
    strip = Image.new("RGB", (fw * 4 + 24, fh * 2 + 8), (36, 36, 40))
    for k, (t, f) in enumerate(pick):
        f = f.copy()
        ImageDraw.Draw(f).text((6, f.height - 16), f"t = {t:.2f} s", fill=(255, 255, 255), font=P.font("GothamBold", 12))
        strip.paste(f, ((k % 4) * (fw + 8), (k // 4) * (fh + 8)))
    png = os.path.join(a.out, f"{a.screen}.reel.png")
    strip.save(png)
    focus = reel.get("focus") or []
    spec_path = os.path.join(a.ui, f"{a.screen}.json")
    if not focus and os.path.isfile(spec_path):
        spec = json.load(open(spec_path, encoding="utf-8"))
        # the spec names paths from the root (Hud.List.Boon1.Dia); tracks name a suffix (Boon1.Dia / List.Boon1)
        focus = [".".join(p.split(".")[-2:]) for p in (spec.get("hero"), spec.get("focus")) if isinstance(p, str)]
    notes = critique(tracks, dur, fps, focus)
    with open(os.path.join(a.out, f"{a.screen}.critic.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "screen": a.screen, "notes": notes}, fh, indent=1)
    said = f"; motion: {len(notes)} note(s) — " + " | ".join(n["note"] for n in notes[:3]) if notes else "; motion: no notes"
    # PHOTOSENSITIVITY (WCAG 2.3.1): no more than 3 flashes in any second over a quarter of a 10-degree field, red
    # stricter — the screen's own fx (flicker, split, ping, flashes) are counted on the film itself (kit/ui/flash.py)
    import flash as _flash
    fl = _flash.flash_report([f for _, f in frames], fps)
    with open(os.path.join(a.out, f"{a.screen}.flash.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "screen": a.screen, **fl}, fh, indent=1)
    if fl["fail"]:
        return emit("fail", f"reel: {a.screen} FLASHES — {fl['max_hz']} flashes/s (red {fl['red_max_hz']}) over "
                    f"{fl['area_share'] * 100:.1f}% of the frame (WCAG 2.3.1: at most 3 a second over a quarter of a "
                    "10-degree field)", f"slow or shrink what flashes near {fl['where']} (flicker / split every >= 0.34 s, "
                    "a smaller region, no saturated red strobe); players can also ask for Ui.setReduceFlashing(true)",
                    gif=gif.replace("\\", "/"), flash=fl)
    said += f"; flashes: {fl['max_hz']}/s max (ok)"
    return emit("pass", f"reel: {a.screen} — {len(frames)} frames over {dur:g} s at {fps} fps, {len(tracks)} track(s) -> {gif}{said}",
                (f"improve the motion ({os.path.join(a.out, a.screen + '.critic.json')}), then LOOK at {png}" if notes else
                 f"LOOK at {png} (eight frames) and play {gif}: does every hit read, does the ghost drain AFTER the hit, does the low state pulse?"),
                gif=gif.replace("\\", "/"), strip=png.replace("\\", "/"), notes=notes)


if __name__ == "__main__":
    raise SystemExit(main())
