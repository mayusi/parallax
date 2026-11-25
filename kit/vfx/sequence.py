"""sequence.py — V5: a CHOREOGRAPHED MULTI-SHOT sequence, checked and drawn as a timeline (LIMITATIONS_FIXES_V4 §3.4 step
3, §13.3.3: "Charge -> 1f VfxMood + B4 ScreenGui impact plate + Hitstop -> V5 multi-cut reveal").

    lune run kit vfx sequence <name> --new [--force]    write assets/effects/sequences/<name>.seq.json: the V5 shape
                                                         as a template (a charge, ONE impact beat, a three-cut reveal)
    lune run kit vfx sequence <name>                     check it by the GAME's own rules (src/kit/VfxSequenceRules.luau
                                                         through kit/vfx/sequence.luau: one source of truth) and draw its
                                                         timeline: build/vfx/sequences/<name>_timeline.png - a 60 fps
                                                         ruler, one row per event kind, every beat where it falls; the
                                                         plates it names must exist (assets/effects/plates/<key>.plate.json)
    (--dir <folder>: another folder of sequences; --plates-dir <folder>; --look-dir <folder>)

A sequence's beats (frames of the 60 fps clock): camera_cut, fov_punch, shake, mood_push, impact_plate, hitstop,
vfx_layers, sfx_event, victim_reaction - see the head of src/kit/VfxSequenceRules.luau. The game plays it with
src/kit/VfxSequence.luau (VfxSequence.play(seq, { at = hitCFrame, victim = model, hitstop = ... })).
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw

DIR = os.path.join("assets", "effects", "sequences")
PLATES = os.path.join("assets", "effects", "plates")
LOOK = os.path.join("build", "vfx", "sequences")
ROWS = ["camera_cut", "mood_push", "impact_plate", "hitstop", "shake", "fov_punch", "vfx_layers", "sfx_event",
        "victim_reaction"]
COLOURS = {"camera_cut": (240, 240, 240), "mood_push": (255, 120, 200), "impact_plate": (255, 220, 90),
           "hitstop": (120, 200, 255), "shake": (255, 150, 90), "fov_punch": (170, 140, 255),
           "vfx_layers": (120, 230, 150), "sfx_event": (200, 200, 120), "victim_reaction": (255, 90, 90)}


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def template(name):
    """the V5 shape, filled with plain numbers to change: a 0.6 s charge, the impact beat, a three-cut reveal"""
    return {"schema": 1, "name": name, "fps": 60, "kind": "hero",
            "about": "Charge -> ONE impact beat (1-frame mood + plate + hitstop) -> a multi-cut reveal. Frames of 60 fps.",
            "beats": [
                {"t_frame": 0, "name": "charge", "camera_cut": {"shot": "wide"}, "vfx_layers": ["<charge preset>"],
                 "sfx_event": "<charge sound>"},
                {"t_frame": 36, "name": "impact", "mood_push": {"values": {"exposure": 2.5}, "frames": 1, "priority": 80},
                 "impact_plate": {"plate": "<plate key>", "frames": 6, "rate": 2}, "hitstop": {"frames": 6},
                 "shake": {"amp": 2.0, "frames": 14}, "fov_punch": {"delta": -10, "frames": 12},
                 "vfx_layers": ["<impact preset>"], "sfx_event": "<impact sound>", "victim_reaction": {"power": 1.0}},
                {"t_frame": 37, "name": "reveal_close", "camera_cut": {"shot": "close"}},
                {"t_frame": 49, "name": "reveal_low", "camera_cut": {"shot": "low"}},
                {"t_frame": 61, "name": "reveal_wide", "camera_cut": {"shot": "wide"}},
            ]}


def rules(path):
    """the game's own rules over the file -> their JSON answer"""
    try:
        r = subprocess.run(["lune", "run", "kit/vfx/sequence.luau", path], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "problems": [f"lune could not run the rules: {e}"]}
    lines = [ln for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.strip().startswith("{")]
    if not lines:
        return {"ok": False, "problems": ["the rules printed nothing: " + r.stderr.decode("utf-8", "replace")[-300:]]}
    return json.loads(lines[-1])


def plates_named(seq):
    return sorted({b["impact_plate"]["plate"] for b in seq.get("beats", []) if isinstance(b.get("impact_plate"), dict)
                   and isinstance(b["impact_plate"].get("plate"), str)})


def timeline_png(seq, res, path, px=8):
    """a 60 fps ruler, one row per event kind: a beat's start as a block, its duration as a bar; the impact frame
    marked; the 1-frame mood is ONE column wide - the eye checks the shape at a glance"""
    frames = int(res["frames"])
    w = 140 + frames * px + 20
    h = 30 + len(ROWS) * 22 + 20
    img = Image.new("RGB", (w, h), (24, 26, 34))
    d = ImageDraw.Draw(img)
    for f in range(0, frames + 1, 6):
        x = 140 + f * px
        d.line([(x, 20), (x, h - 10)], fill=(60, 62, 74) if f % 30 else (110, 112, 126))
        if f % 30 == 0:
            d.text((x + 2, 4), f"{f}f", fill=(170, 170, 180))
    for i, kind in enumerate(ROWS):
        y = 30 + i * 22
        d.text((6, y + 4), kind, fill=COLOURS[kind])
        for ev in res["events"]:
            if ev["kind"] != kind:
                continue
            x0 = 140 + ev["frame"] * px
            x1 = 140 + (ev.get("ends") or ev["frame"] + 1) * px
            d.rectangle([x0, y + 3, max(x1 - 1, x0 + px - 1), y + 17], fill=COLOURS[kind])
    if res.get("impact"):
        b = seq["beats"][res["impact"] - 1]
        x = 140 + b["t_frame"] * px
        d.rectangle([x, 20, x + px - 1, h - 10], outline=(255, 60, 60))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path


def main(argv):
    opts, names, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--new", "--force"):
            opts[a] = True
        elif a.startswith("--") and i + 1 < len(argv):
            opts[a] = argv[i + 1]
            i += 1
        else:
            names.append(a)
        i += 1
    usage = "lune run kit vfx sequence <name> [--new]"
    if not names or not re.fullmatch(r"[A-Za-z0-9_]{1,60}", names[0]):
        return out("fail", "sequence: name the sequence (letters, digits, _)", usage)
    name = names[0]
    folder = opts.get("--dir", DIR)
    path = os.path.join(folder, f"{name}.seq.json")
    if opts.get("--new"):
        if os.path.isfile(path) and not opts.get("--force"):
            return out("fail", f"sequence {name}: {path} exists (never overwritten without --force)", f"lune run kit vfx sequence {name}")
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(template(name), fh, indent=1)
            fh.write("\n")
        return out("pass", f"sequence {name}: the V5 template written ({path.replace(os.sep, '/')}): fill the <...> names",
                   f"lune run kit vfx sequence {name}", file=path.replace(os.sep, "/"))
    if not os.path.isfile(path):
        return out("fail", f"sequence {name}: no {path}", f"lune run kit vfx sequence {name} --new")
    res = rules(path)
    if not res.get("ok"):
        return out("fail", f"sequence {name}: " + "; ".join(res.get("problems") or ["refused"]),
                   "fix the beats named (src/kit/VfxSequenceRules.luau says what each field takes)", problems=res.get("problems"))
    with open(path, encoding="utf-8") as fh:
        seq = json.load(fh)
    plates_dir = opts.get("--plates-dir", PLATES)
    missing = [p for p in plates_named(seq) if not os.path.isfile(os.path.join(plates_dir, f"{p}.plate.json"))]
    if missing:
        return out("fail", f"sequence {name}: it names plate(s) not baked: {', '.join(missing)}",
                   f"lune run kit vfx plate {missing[0]} --kind halftone|lines|kanji")
    png = timeline_png(seq, res, os.path.join(opts.get("--look-dir", LOOK), f"{name}_timeline.png"))
    impact = f"impact at frame {seq['beats'][res['impact'] - 1]['t_frame']}" if res.get("impact") else "no impact beat (a plain sequence)"
    return out("pass", f"sequence {name} ({res['kind']}): {len(seq['beats'])} beats, {len(res['events'])} events over "
                       f"{res['frames']} frames ({res['frames'] / 60.0:.2f} s), {impact}; checked by the game's own rules",
               f"LOOK at {png.replace(os.sep, '/')}; the game plays it with VfxSequence.play",
               timeline=png.replace(os.sep, "/"), frames=res["frames"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
