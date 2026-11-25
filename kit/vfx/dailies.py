"""dailies.py — DAILIES: an effect's recording looked at the way a director looks at a shot, beside the scene it is
built from (the VFX studio-route plan, V0).

    lune run kit vfx dailies <name> [--view hero] [--beat <#>] [--frames 12] [--tile 640] [--run <recording>]
                                    [--scene-window a,b] [--effects <dir>]

For every beat of the effect's chart (refs_measured/<set>.chart.json: the scene's time and our own clock per beat):
  * the scene's MAIN shot of that beat is read frame by frame at the clip's full frame rate (kit/vfx/denseclip.py),
    our recording (build/vfx/booth/<run>_play_<view>.mp4, `kit vfx play <name> --record`) over the beat's stretch of
    our clock the same way, with the same idea of what the effect is (the set's measured hue band);
  * the two HITS are laid on one moment, and the scene's consecutive frames round its hit are shown above OUR frames
    at the same moments from our hit, every frame --tile px wide (640 or more), the hit ringed, a held drawing marked;
  * the two light curves are drawn over each other, and what differs is said in seconds and in drawings
    ("the hit: the scene holds it 0.10 s, ours 0.03 s", "the scene is drawn on twos, ours on ones").
-> build/vfx/dailies/<run>/beat<k>_page.png   the whole beat on one page (open it at full size)
   build/vfx/dailies/<run>/beat<k>_<nn>.png   the same frames two at a time: what a session reads at FULL size
   build/vfx/dailies/<run>/dailies.json       the numbers
The scene's frames are private (measure-only): they live in the git-ignored build/ and nowhere else.
An effect with no scene clip on this machine gets its own frames alone, as large.

    python kit/vfx/dailies.py <label> --ours <mp4> [--ours-window a,b] [--scene-clip <mp4>] [--scene-window a,b]
                              [--hue lo,hi] --out <dir>            (two clips named outright: tests, the selftest)

Prints one JSON line {schema, status, summary, next_action, look, ...}; the summary ends with LOOK: <folder>.
Fails when there is no recording to look at, or when ours never lights up in any beat (a blank recording).
"""

import json
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dailies_page as P  # noqa: E402
import dense  # noqa: E402
import denseclip as DC  # noqa: E402

OUT = DC.gameroot.build("vfx", "dailies")  # the active game's build/vfx (card t6rx)


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def curve_side(shot, name):
    """a read's light over time for the curve panel: seconds from its hit, its light over the window's floor"""
    t = shot and shot["timing"]
    if not t:
        return None
    lo, hi = shot.get("stretch") or (0, shot["frames"] - 1)
    e = dense.energy(shot["curves"])[lo:hi + 1]
    return {"seconds": (np.arange(lo, hi + 1) - t["hit"]) / shot["fps"], "energy": np.clip(e - t["base"], 0.0, None),
            "name": name}


def held(shot, i):
    """frame i repeats the drawing before it (and something is lit: an empty frame holds nothing)"""
    c = shot["curves"]
    return bool(i > 0 and c["cover"][i] > 0 and c["change"][i] < dense.HELD)


def tiles_of(side, indices, width, colour):
    """the frames `indices` of a read as labelled tiles (None in the list = our recording does not reach that
    moment). side: {"clip", "info", "shot", "zero"}: zero = the clip second a label counts from"""
    shot, real = side["shot"], [i for i in indices if i is not None]
    t = shot["timing"]
    if not real:
        return []
    got = DC.frames(side["clip"], shot["from"], shot["to"], width, side["info"], min(real), max(real))
    made, height = [], (got.shape[1] if len(got) else 2) + 30
    for i in indices:
        if i is None or i - min(real) >= len(got):
            made.append(P.blank(width, height, "nothing recorded at this moment"))
            continue
        label = f"{shot['from'] + i / shot['fps'] - side.get('zero', 0.0):.2f} s"
        if t:
            label += f"    {i - t['hit']:+d}" if i != t["hit"] else ""
        made.append(P.tile(got[i - min(real)], width, label, colour, hit=bool(t and i == t["hit"]), held=held(shot, i)))
    return made


def beat(title, stem, out_dir, scene, ours, width, cap):
    """one beat's pictures and numbers. scene / ours: {"clip", "info", "shot", "name", "zero"} or None (a side with
    nothing to show). -> {"files", "scene", "ours", "differences", "notes"}"""
    lines, s_tiles, o_tiles = [], [], []
    st = scene["shot"]["timing"] if scene else None
    ot = ours["shot"]["timing"] if ours else None
    lead = scene or ours                                    # whose span decides which moments are shown
    lo, hi = DC.shown(lead["shot"], cap)
    if scene:
        s_tiles = tiles_of(scene, list(range(lo, hi + 1)), width, P.SCENE)
        lines.append(f"the scene ({scene['name']}): {DC.says(scene['shot'])}")
    if ours:
        if scene:                                           # ours at the same moments from OUR hit
            origin = st["hit"] if st else lo
            start = ot["hit"] if ot else (ours["shot"].get("stretch") or [0])[0]
            wanted = [start + int(round((i - origin) / scene["shot"]["fps"] * ours["shot"]["fps"])) for i in range(lo, hi + 1)]
            wanted = [j if 0 <= j < ours["shot"]["frames"] else None for j in wanted]
        else:
            wanted = list(range(lo, hi + 1))
        o_tiles = tiles_of(ours, wanted, width, P.OURS)
        lines.append(f"ours ({ours['name']}): {DC.says(ours['shot'])}")
    differences = dense.compare(st, ot) if scene and ours else []
    lines += [f"DIFFERENT - {d}" for d in differences]
    if scene and ours and not differences:
        lines.append("the timing agrees within a film frame (lead-in, the hit's hold, the fade, the drawing rhythm)")
    notes = [f"{w['name']}: {w['shot']['note']}" for w in (scene, ours) if w and w["shot"]["note"]]
    lines += [f"NOT READ - {n}" for n in notes]
    files = []
    page = P.page(title, lines, s_tiles, o_tiles, curve_side(scene and scene["shot"], "the scene"),
                  curve_side(ours and ours["shot"], "ours"))
    page.save(os.path.join(out_dir, f"{stem}_page.png"))
    files.append(f"{stem}_page.png")
    for k, im in enumerate(P.strips(s_tiles, o_tiles), 1):
        im.save(os.path.join(out_dir, f"{stem}_{k:02d}.png"))
        files.append(f"{stem}_{k:02d}.png")
    return {"files": files, "scene": DC.numbers(scene["shot"]) if scene else None,
            "ours": DC.numbers(ours["shot"]) if ours else None, "differences": differences, "notes": notes}


def clear(out_dir, only=None):
    """our own earlier pictures of this run (never anything else's); only = one beat's, the others stay"""
    os.makedirs(out_dir, exist_ok=True)
    start = "beat" if only is None else f"beat{only}_"
    for f in os.listdir(out_dir):
        if (f == "dailies.json" and only is None) or (f.startswith(start) and f.endswith(".png")):
            os.remove(os.path.join(out_dir, f))


def pair(text):
    a, b = (float(v) for v in text.split(","))
    return a, b


def finish(label, out_dir, beats, width, key=None, alone="", kept=(), caution=""):
    """the numbers file, then the one JSON line; fails when ours never lit up. alone: why there is no scene beside
    ours (said in the summary: a reader must not take ours alone for a match)"""
    look = out_dir.replace(os.sep, "/") + "/"
    stored = sorted(list(kept) + beats, key=lambda b: b.get("index", 0))    # with the other beats of an earlier run
    DC.dump({"schema": 1, "name": label, "tile": width, "beats": stored}, os.path.join(out_dir, "dailies.json"))
    strips = sum(len(b["files"]) - 1 for b in beats)
    if not any(b["ours"] and b["ours"]["timing"] for b in beats):
        return out("fail", f"dailies {label}: ours never lights up in any beat - a blank recording, or an effect this read "
                   f"cannot see (it reads light and the set's colours). LOOK: {look}",
                   f"open {look}{beats[0]['files'][0]} and look at our frames; record again if they are empty",
                   look=look, beats=beats)
    k = key if key is not None and key < len(beats) else 0
    main = beats[k]
    said = "; ".join(main["differences"]) if main["differences"] else (
        "its timing agrees with the scene within a film frame" if main["scene"] else
        f"OURS ALONE ({alone or 'no scene beside it'}) - {main['ours']['says']}")
    if alone and main["scene"]:
        said += f" ({alone})"
    return out("pass", f"dailies {label}: {len(beats)} beat(s), {strips} strip(s) at {width} px a frame. "
               f"{main['beat']}: {said}.{' ' + caution + '.' if caution else ''} LOOK: {look}",
               f"open {look}{main['files'][1] if len(main['files']) > 1 else main['files'][0]} onward at full size (two "
               f"consecutive frames a picture, the scene above ours), then {main['files'][0]} for the curves; change the "
               f"effect's timing where it differs and play it again",
               look=look, beats=beats)


def named(label, opts):
    """two clips named outright"""
    our_clip, scene_clip, out_dir = opts.get("--ours"), opts.get("--scene-clip"), opts.get("--out")
    if not our_clip or not os.path.isfile(our_clip) or not out_dir:
        return out("fail", f"dailies {label}: needs --ours <mp4> and --out <dir>", "name the recording and the folder")
    width, cap = int(opts.get("--tile", 640)), int(opts.get("--frames", 12))
    hue = pair(opts["--hue"]) if "--hue" in opts else None
    if os.path.isdir(out_dir) and os.listdir(out_dir) and not os.path.isfile(os.path.join(out_dir, "dailies.json")):
        return out("fail", f"dailies {label}: --out {out_dir} holds other files and no dailies.json: not a dailies folder",
                   "name an empty folder, or one an earlier dailies run made")
    clear(out_dir)
    oi = DC.probe(our_clip)
    a, b = pair(opts["--ours-window"]) if "--ours-window" in opts else (0.0, oi[1])
    whole = DC.read(our_clip, 0.0, oi[1], hue, oi)
    shot = whole and DC.within(whole, a, b)
    if shot is None:
        return out("fail", f"dailies {label}: under 3 frames in {our_clip}", "name a recording with frames in it")
    ours = {"clip": our_clip, "info": oi, "shot": shot, "name": os.path.basename(our_clip)}
    scene = None
    if scene_clip and os.path.isfile(scene_clip):
        si = DC.probe(scene_clip)
        a, b = pair(opts["--scene-window"]) if "--scene-window" in opts else (0.0, si[1])
        sshot = DC.read(scene_clip, a, b, hue, si)
        scene = sshot and {"clip": scene_clip, "info": si, "shot": sshot, "name": os.path.basename(scene_clip)}
    rec = beat(f"{label} - dailies", "beat0", out_dir, scene, ours, width, cap)
    rec["beat"], rec["index"], rec["key"] = label, 0, True
    return finish(label, out_dir, [rec], width)


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "dailies: needs a preset name", "lune run kit vfx dailies <name> [--view hero] [--beat <#>]")
    name, rest = argv[0], argv[1:]
    opts = {rest[i]: rest[i + 1] for i in range(0, len(rest) - 1, 2) if rest[i].startswith("--")}
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return out("fail", "dailies: ffmpeg / ffprobe not on PATH", "install ffmpeg (vetted) or put it on PATH")
    if "--ours" in opts:
        return named(name, opts)
    found = DC.piece(name, opts.get("--effects"), opts.get("--view"), opts.get("--run"))
    if isinstance(found, str):
        return out("fail", f"dailies {name}: {found}", "name an existing preset")
    return of(name, found, opts)


def of(name, found, opts, again=None):
    """the dailies of one recording that has a set's chart beside it. found: what DC.piece gives for an effect - or
    the same for anything else played on the chart's clock (the timing animatic of a set: kit/vfx/animatic.py);
    again: the command that makes the recording, for the lines that say it is missing"""
    view, run, our_clip = found["view"], found["run"], found["recording"]
    again = again or f"lune run kit vfx play {name} --record --views {view}"
    if not os.path.isfile(our_clip):
        return out("fail", f"dailies {name}: no recording {our_clip.replace(os.sep, '/')}", again)
    width, cap = max(320, int(opts.get("--tile", 640))), max(4, int(opts.get("--frames", 12)))
    set_name, hue, scene_clip, cuts = found["set"], found["hue"], found["scene_clip"], found["cuts"]
    si = DC.probe(scene_clip) if scene_clip else None
    oi = DC.probe(our_clip)
    rows = found["beats"]
    only = int(opts["--beat"]) if "--beat" in opts else None
    if only is not None and not 0 <= only < len(rows):
        return out("fail", f"dailies {name}: no beat {only} (the chart has {len(rows)})", "name a beat of the chart, from 0")
    out_dir = os.path.join(OUT, run)
    clear(out_dir, only)
    beats, why, key = [], [], None
    whole = DC.read(our_clip, 0.0, oi[1], hue, oi)          # ours once, whole: each beat is a stretch of it
    if whole is None:
        return out("fail", f"dailies {name}: under 3 frames in {our_clip.replace(os.sep, '/')}", again)
    if not set_name:
        why.append("the preset declares no scene set")
    elif not scene_clip:
        why.append(f"the scene's clip of {set_name} is not on this machine")
    # the recording is real time: every hit-stop before a beat moves it - on the clock of the preset AS PLAYED
    clock = DC.clock_of(found["played"] if "played" in found else found.get("preset"), oi[0])
    for k, row in enumerate(rows):
        if only is not None and k != only:
            continue
        a, b = DC.stretch(rows, k, oi[0], oi[1], clock)
        oshot = DC.within(whole, a, b)
        if oshot is None:
            why.append(f"beat {k}: under 3 frames of ours between {a:.2f} and {b:.2f} s")
            continue
        ours = {"clip": our_clip, "info": oi, "shot": oshot, "name": f"{run} {view}, {a:.2f}-{b:.2f} s of its recording"}
        scene = None
        sc = row.get("scene")
        if scene_clip and isinstance(sc, list) and len(sc) == 2:
            if "--scene-window" in opts and only is not None:       # a window set by hand is read as one shot
                wa, wb = pair(opts["--scene-window"])
                sshot = DC.read(scene_clip, wa, wb, hue, si)
            else:
                read = DC.read_beat(scene_clip, float(sc[0]), float(sc[1]), cuts, hue, si)
                sshot = read["shots"][read["main"]] if read["main"] is not None else None
            if sshot:
                scene = {"clip": scene_clip, "info": si, "shot": sshot,
                         "name": f"{set_name}, shot {sshot['from']:.2f}-{sshot['to']:.2f} s at {si[0]:g} fps"}
            else:
                why.append(f"beat {k}: no shot of the scene to read between {sc[0]} and {sc[1]} s")
        rec = beat(f"{run} - dailies, beat {row.get('beat', k)}", f"beat{k}", out_dir, scene, ours, width, cap)
        rec["beat"], rec["index"], rec["key"] = str(row.get("beat", k)), k, bool(row.get("key"))
        if row.get("key"):
            key = len(beats)
        beats.append(rec)
    if not beats:
        return out("fail", f"dailies {name}: nothing to show ({'; '.join(why) or 'no beat'})", again)
    if only is None and key is None and any(r.get("key") for r in rows):
        why.append("the chart's key beat could not be read (see above): the beat named here is the first one that could")
    kept = []
    if only is not None:                                    # one beat again: the others keep their numbers
        try:
            kept = [b for b in json.load(open(os.path.join(out_dir, "dailies.json"), encoding="utf-8")).get("beats", [])
                    if b.get("index") != only]
        except (OSError, ValueError):
            kept = []
    return finish(run, out_dir, beats, width, key, "; ".join(why), kept, DC.caution(found))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
