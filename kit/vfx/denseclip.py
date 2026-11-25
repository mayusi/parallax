"""denseclip.py — a clip's frames for the frame-by-frame timing read (kit/vfx/dense.py does the arithmetic): the
ffmpeg side of `kit vfx breakdown <set> --dense` and `kit vfx dailies <name>`.

A beat's scene time covers one or more SHOTS (the breakdown's hard cuts bound them). Each shot is read on its own
at the clip's full frame rate - a quiet picture or a floor taken across a cut means nothing - and the beat's MAIN
shot is the one whose light rises the most over its own floor. Our own recording has no cuts: its beat is one
window on the effect's clock.

Frames are read straight from ffmpeg's pipe (no files): small (MEASURE px wide) for the numbers, large only for
the frames a picture shows.
"""

import json
import os
import re
import subprocess

import numpy as np

import dense
import gameroot

MEASURE = 320      # px wide for the numbers (kit/vfx/keyread.py reads a still at this size too)
EFFECTS = os.path.join("assets", "effects")
BOOTH = gameroot.build("vfx", "booth")   # the ACTIVE game's, where `kit vfx play` records (card t6rx)
PLAY = gameroot.build("vfx", "play")     # the bundles `kit vfx play` gives the player: <run>.json
RECORDS_IN = 900.0  # a recording is written within this many seconds of its bundle (the recorder's own time limit)
LONGEST = 12.0     # a shot longer than this many seconds is read where its beat is, not whole
MARGIN = 1.0       # ... with this many seconds either side


def probe(clip):
    """-> (frames a second, seconds long, width, height) of a clip's picture"""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate,avg_frame_rate,width,height:format=duration", "-of", "json", clip],
                       capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    return (steady_rate(st.get("r_frame_rate"), st.get("avg_frame_rate")), float((d.get("format") or {}).get("duration") or 0),
            int(st.get("width") or 0), int(st.get("height") or 0))


def steady_rate(r_frame_rate, avg_frame_rate=None):
    """the frame rate to read a clip at. A recording with no steady rate says 1000 or 90000 a second as its "real"
    rate: reading every frame at that rate would ask ffmpeg for thousands of copies - its average rate then, else 30"""
    def rate(text):
        num, _, den = str(text or "0/1").partition("/")
        try:
            return float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            return 0.0

    fps = rate(r_frame_rate)
    if not 1.0 <= fps <= 120.0:
        avg = rate(avg_frame_rate)
        fps = avg if 1.0 <= avg <= 120.0 else 30.0
    return fps


def frames(clip, start, end, width, info=None, lo=None, hi=None):
    """the clip's frames from `start` to `end` seconds, every one of them (its own frame rate), `width` px wide
    -> (N, H, W, 3) bytes. Frame i is the picture at start + i / fps. With lo / hi only frames lo..hi of that same
    count come back (a picture's large frames are the very frames the numbers were read from: counted from the
    same start, never found again by their time)."""
    fps, _, sw, sh = info or probe(clip)
    if sw <= 0 or sh <= 0 or end - start <= 0:
        return np.zeros((0, 2, 2, 3), dtype=np.uint8)
    height = max(2, int(round(sh * width / float(sw) / 2.0)) * 2)
    part = f"trim=start_frame={int(lo)}:end_frame={int(hi) + 1}," if lo is not None and hi is not None else ""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.4f}", "-to", f"{end:.4f}", "-i", clip,
                        "-vf", f"fps={fps:.6f},{part}scale={width}:{height}:flags=area", "-f", "rawvideo", "-pix_fmt",
                        "rgb24", "-"], capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {clip}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    size = width * height * 3
    count = len(r.stdout) // size
    return np.frombuffer(r.stdout[:count * size], dtype=np.uint8).reshape(count, height, width, 3)


def shots_of(t0, t1, cuts, fps, length):
    """the cut-bounded shots a beat's scene time [t0, t1] covers -> [(from, to)] in clip seconds, each pulled one
    frame in from its cuts (a cut's own frame belongs to nobody). A shot counts when the beat covers 0.3 s of it,
    or half of it, or it holds half of the BEAT (a hit of 0.2 s inside a long shot is that shot's); a very long shot
    is read round the beat only."""
    bounds = [0.0] + sorted(float(c) for c in cuts if 0.0 < float(c) < length) + [float(length)]
    found = []
    for a, b in zip(bounds, bounds[1:]):
        share = min(b, t1) - max(a, t0)
        if b - a < 3.0 / fps or share < min(0.3, 0.5 * (b - a), 0.5 * (t1 - t0)) - 1e-9:
            continue
        if b - a > LONGEST:
            a, b = max(a, t0 - MARGIN), min(b, t1 + MARGIN)
        found.append((round(a + 1.0 / fps, 4), round(b - 1.0 / fps, 4)))
    return found


def steady(f, hue=None):
    """a window's frames with the CAMERA taken out (kit/vfx/track.py) -> (frames, what the camera did, in words, or
    None). A camera that moves makes every frame differ from the last, and the read then says the effect changes on
    every frame: a window whose camera is followed and moves is read from its stabilised frames, inside the window
    every frame covers. A camera that stands, or one that cannot be followed, leaves the frames as they are"""
    if len(f) < 3:
        return f, None
    try:
        import track
        camera = track.track(f, hue)
        if not (camera["known"] and camera["moves"]):
            return f, None
        # NOT cropped: the frames stay whole (what no frame covers is black, which is no effect), so "cover" is still
        # a share of the frame and compares with a read that was not stabilised
        laid, win = track.stabilise(f, camera, crop=False)
        if laid is None or (win[2] - win[0]) < 0.3 * camera["size"][0] or (win[3] - win[1]) < 0.3 * camera["size"][1]:
            return f, track.says(camera) + " - too far to stabilise: read as it is"
        return laid, track.says(camera) + ": read from the stabilised frames"
    except Exception as e:  # noqa: BLE001 - a read never fails on its camera: it is then read as it always was
        return f, f"the camera was not read ({type(e).__name__})"


def read(clip, start, end, hue=None, info=None):
    """one window of a clip (one shot, or one beat of our own recording) read frame by frame ->
    {"from", "to", "fps", "frames", "curves", "timing", "note", "camera"} or None when it holds under 3 frames"""
    info = info or probe(clip)
    f = frames(clip, start, end, MEASURE, info)
    if len(f) < 3:
        return None
    f, camera = steady(f, hue)
    c = dense.curves(f, hue)
    t = dense.timing(c, info[0])
    note = dense.verdict(c, t)
    return {"from": round(start, 4), "to": round(end, 4), "fps": info[0], "frames": len(f), "curves": c, "timing": t,
            "note": "; ".join(x for x in (camera, note) if x), "camera": camera}


def rise(shot):
    """how far a read's light rises over its own floor (0 when it never lights up or is steady): what makes a shot
    the beat's main one"""
    t = shot and shot["timing"]
    return 0.0 if not t or t["steady"] else t["peak"] - t["base"]


def read_beat(clip, t0, t1, cuts, hue=None, info=None):
    """a beat of the scene: every shot it covers read on its own -> {"shots": [...], "main": index or None}.
    The main shot: the one whose light rises the most over its own floor; with none rising, the brightest."""
    info = info or probe(clip)
    shots = [s for s in (read(clip, a, b, hue, info) for a, b in shots_of(t0, t1, cuts, info[0], info[1])) if s]
    if not shots:
        return {"shots": [], "main": None}
    best = max(range(len(shots)), key=lambda i: rise(shots[i]))
    if rise(shots[best]) <= 0.0:
        lit = [i for i in range(len(shots)) if shots[i]["timing"]]
        best = max(lit, key=lambda i: shots[i]["timing"]["peak"]) if lit else None
    return {"shots": shots, "main": best}


def within(shot, a, b):
    """a read of a WHOLE recording, timed over the stretch a..b seconds of it only (one beat of our own clock).
    The frames keep their numbers in the whole recording, so a picture can show the moments just outside the
    stretch, and "stretch" says which frames were timed. None when the stretch holds under 3 frames."""
    fps = shot["fps"]
    ia = max(0, int(round((a - shot["from"]) * fps)))
    ib = min(shot["frames"], int(round((b - shot["from"]) * fps)) + 1)
    if ib - ia < 3:
        return None
    part = {k: np.asarray(v)[ia:ib] for k, v in shot["curves"].items()}
    # the frame before the stretch is KNOWN here (the recording is read whole; before its first frame nothing is
    # lit): light that was already on is "opens on it", a dark frame before is an arrival in one frame
    before = float(dense.energy(shot["curves"])[ia - 1]) if ia > 0 else 0.0
    t = dense.timing(part, fps, before=before)
    note = dense.verdict(part, t)
    if t:
        t = dict(t, hit=t["hit"] + ia, brightest=t["brightest"] + ia, span=[t["span"][0] + ia, t["span"][1] + ia],
                 seconds=dict(t["seconds"], hit=round((t["hit"] + ia) / fps, 3)))
    return dict(shot, timing=t, note=note, stretch=[ia, ib - 1])


def says(shot):
    """a read's timing in one sentence: a scene's shot in the clip's own seconds, our stretch on our own clock"""
    ours = "stretch" in shot
    return dense.describe(shot["timing"], 0.0 if ours else shot["from"], "stretch" if ours else "shot")


def numbers(shot):
    """a read without its curves' arrays (what is written beside the beat sheet): its window, its timing, the light
    where it arrives, and what the read could not see"""
    c, t = shot["curves"], shot["timing"]
    lo, hi = shot.get("stretch") or (0, shot["frames"] - 1)
    out = {"from": round(shot["from"] + lo / shot["fps"], 3), "to": round(shot["from"] + (hi + 1) / shot["fps"], 3),
           "fps": round(shot["fps"], 3), "frames": hi - lo + 1, "timing": t, "says": says(shot)}
    if t:
        out["hit_at"] = round(shot["from"] + t["hit"] / shot["fps"], 3)
        out["at_hit"] = {"cover": round(float(c["cover"][t["hit"]]), 4), "bright": round(float(c["bright"][t["hit"]]), 4)}
    if shot["note"]:
        out["note"] = shot["note"]
    return out


def shown(shot, cap):
    """which frames of a read a picture shows: `cap` consecutive frames round the frame the light ARRIVES on, a
    third of them before it (what was there before, the arrival, the first of its stay). The rest of the stay and
    the going are on the light curve; ask for more frames to see them. -> (first index, last index)"""
    t = shot["timing"]
    lo0, hi0 = shot.get("stretch") or (0, shot["frames"] - 1)
    if not t:
        return lo0, min(hi0, lo0 + cap - 1)
    lo = max(0, t["hit"] - cap // 3)
    hi = min(shot["frames"] - 1, lo + cap - 1)
    return max(0, hi - cap + 1), hi


def dump(data, path):
    """the numbers as JSON a person can read and a diff can show: one key a line, a list of numbers on ONE line (a
    long shot's holds are a hundred numbers)"""
    text = json.dumps(data, indent=1)
    text = re.sub(r"\[\s+((?:-?[\d.]+,\s+)*-?[\d.]+)\s+\]", lambda m: "[" + " ".join(m.group(1).split()) + "]", text)
    open(path, "w", encoding="utf-8", newline="\n").write(text + "\n")


def measured_hue(measured_dir, *names):
    """the hue band of the first measured colours file that exists (refs_measured/<name>.json's "hue") or None"""
    for n in names:
        p = os.path.join(measured_dir, f"{n}.json") if n else None
        if p and os.path.isfile(p):
            try:
                hue = json.load(open(p, encoding="utf-8")).get("hue")
            except (OSError, ValueError):
                hue = None
            if isinstance(hue, list) and len(hue) == 2:
                return (float(hue[0]), float(hue[1]))
    return None


def set_piece(set_name, effects=None, colours=None):
    """a scene SET's measured things, found in one place -> {"set", "effects", "measured", "chart", "breakdown",
    "scene_clip", "cuts", "hue", "beats"}. Its folder as kit/vfx/chart.py picks it: the effects folder's own when the
    set is there (its beat sheet or its chart), else the project's - so the chart read here is the chart `kit vfx
    chart --approve` writes. colours: the measured colours file an effect names, tried first for the hue band."""
    effects = effects or EFFECTS
    measured = os.path.join(effects, "refs_measured")
    root = os.path.join(EFFECTS, "refs_measured")
    if set_name and not any(os.path.isfile(os.path.join(measured, f"{set_name}{ext}")) for ext in (".beats.md", ".chart.json")):
        measured = root
    chart = breakdown = None
    if set_name:
        for kind in ("chart", "breakdown"):
            data = None
            # (the breakdown names the scene's clip: one a game did not copy is still the project's)
            for folder in ((measured,) if kind == "chart" else (measured, root)):
                try:
                    data = json.load(open(os.path.join(folder, f"{set_name}.{kind}.json"), encoding="utf-8"))
                    if isinstance(data, dict):              # (a file that is not a chart / a breakdown is none)
                        break
                    data = None
                except (OSError, ValueError):
                    data = None
            if kind == "chart":
                chart = data
            else:
                breakdown = data
    clip = breakdown.get("clip") if breakdown and os.path.isfile(str(breakdown.get("clip"))) else None
    return {"set": set_name, "effects": effects, "measured": measured, "chart": chart, "breakdown": breakdown,
            "scene_clip": clip, "cuts": [c["t"] for c in (breakdown or {}).get("cuts", [])],
            "hue": measured_hue(measured, colours, f"{set_name}_scene" if set_name else None, set_name),
            "beats": (chart or {}).get("beats") or [{"beat": "the whole effect", "t": 0.0}]}


def piece(name, effects=None, view=None, run=None):
    """an effect and everything it is read against, found in one place (kit vfx dailies, kit vfx stylesheet) -> a
    dict, or a string saying what is missing. effects: the folder its preset is in (a game's, else the project's);
    its measured set (chart, breakdown, colours) is looked for there first, then in the project's (the scene gate's
    rule); run: the recording's name when it is not the preset's (a variant, a blockout)."""
    effects = effects or EFFECTS
    measured = os.path.join(effects, "refs_measured")
    path = os.path.join(effects, f"{name}.json")
    try:
        preset = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return f"no preset {path.replace(os.sep, '/')}"
    views = (preset.get("booth") or {}).get("views") or ["hero"]
    view, run = view or views[0], run or name
    decl = preset.get("scene") if isinstance(preset.get("scene"), dict) else {}
    found = set_piece(decl.get("set"), effects, decl.get("colours"))
    if not decl.get("set"):                                 # (no set declared: nothing measured is this effect's)
        found["measured"] = measured
    found.update(name=name, preset=preset, preset_path=path, view=view, run=run,
                 recording=os.path.join(BOOTH, f"{run}_play_{view}.mp4"))
    found["played"], found["clock_exact"] = played(run, found["recording"], preset, path)
    return found


def caution(found):
    """what a tool says when the clock it read a recording on is not surely the one it was recorded on, else ''"""
    if found.get("clock_exact", True):
        return ""
    return ("CAUTION: the clock this recording is read on may not be the one it was recorded on - no bundle of the play "
            "that made it is beside it, and the preset's file cannot say (it is composed, names a moment by a beat, or "
            "was edited since): record it again to be sure")


def numbers_only(preset):
    """a preset's clock - its length, hit-stops and slow motion - with only what can be read as numbers (a hit-stop
    "at" a beat's NAME is resolved when the preset is expanded: its file alone cannot say when it is) ->
    ({"duration", "hitstop", "timewarp"}, how many entries were left out)"""
    preset = preset if isinstance(preset, dict) else {}
    left, clock = 0, {}

    def number(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if np.isfinite(v) else None

    stops = []
    for h in preset.get("hitstop") or []:
        at_ = number(h.get("at")) if isinstance(h, dict) else None
        hold = 0.08 if not (isinstance(h, dict) and h.get("hold")) else number(h.get("hold"))
        if at_ is None or hold is None:
            left += 1
        else:
            stops.append({"at": at_, "hold": hold})
    warp = []
    for k in preset.get("timewarp") or []:
        # (the player reads a key's first two numbers, whatever follows them)
        pair = [number(k[0]), number(k[1])] if isinstance(k, (list, tuple)) and len(k) >= 2 else [None, None]
        if None in pair:
            left += 1
        else:
            warp.append(pair)
    duration = number(preset.get("duration"))
    if duration is not None and duration > 0:
        clock["duration"] = duration
    if stops:
        clock["hitstop"] = stops
    if warp:
        clock["timewarp"] = warp
    return clock, left


def played(run, recording, preset=None, preset_path=None):
    """the preset AS IT WAS PLAYED for a recording -> (its clock: {"duration", "hitstop", "timewarp"}, exact).
    `kit vfx play` writes the bundle it gives the player just before it records (<the folder beside the recording's
    booth>/play/<run>.json): the preset EXPANDED - its beats' names resolved to seconds, its parts' and variants'
    layers and hit-stops in. The recording ran on THAT clock; the preset's file can say something else (starblade's
    file has a hit-stop "at": "blast", which is 5.66 s only once expanded - read from the file, the clock crashed,
    and with it the dailies of every recorded play of such an effect: a review, 2026-11-12).
    Which clock, in this order:
      1. the bundle, when it IS this recording's: written before the recording and within the recorder's own time
         limit of it (a bundle of the same name from last week, or from another play, is not - a third review found
         a stale one taken as exact) - exact when nothing of it had to be left out;
      2. the preset's own file, when it is not composed (no `use`, `beats`, `variants`, `overlay`) and all of its clock is
         numbers: there is nothing an expansion could add - exact, unless the file was edited after the recording;
      3. else a bundle that is not surely this recording's (it still knows what the file cannot), else the file's
         numbers: NOT exact, and the tools say so (caution())."""
    bundle = os.path.join(os.path.dirname(os.path.dirname(recording)), "play", f"{run}.json")
    try:
        was = json.load(open(bundle, encoding="utf-8")).get("preset")
    except (OSError, ValueError, AttributeError):
        was = None
    theirs = numbers_only(was) if isinstance(was, dict) else None
    try:
        made_at = os.path.getmtime(recording)
    except OSError:
        made_at = None
    if theirs and made_at is not None:
        try:
            ahead = made_at - os.path.getmtime(bundle)
        except OSError:
            ahead = None
        if ahead is not None and -2.0 <= ahead <= RECORDS_IN:
            return theirs[0], theirs[1] == 0
    own, left = numbers_only(preset)
    # (an `overlay` too: its `time` stretches the length and every hit-stop when the preset is expanded)
    composed = isinstance(preset, dict) and any(preset.get(k) for k in ("use", "beats", "variants", "overlay"))
    if left == 0 and not composed:
        try:
            edited = made_at is not None and preset_path is not None and os.path.getmtime(preset_path) > made_at + 1.0
        except OSError:
            edited = False
        return own, not edited
    return (theirs[0] if theirs else own), False


def frame_times(preset, fps, limit=40.0):
    """the EFFECT time each frame of a recording shows, frame by frame - the recorder's own loop (kit/vfx/player/
    index.html record(): one player.step(1 / fps) a frame, the frame taken after it) and the player's own clock
    (player.js step() and warpAt(), mirrored line for line, in the same arithmetic):
      * the clock moves 1 / fps a frame, times its speed there (preset "timewarp": [[t, rate], ...]);
      * a step that would cross a hit-stop (preset "hitstop": [{at, hold}], the first one in the list it crosses)
        stops ON it, and the frames that follow show that same moment until `hold` seconds of frames are spent -
        whole frames, so a hold of 0.12 s at 30 a second is 3 held frames, and the part of the step that crossed
        is lost;
      * two hit-stops at one time: only the first holds.
    Frame 0 shows the clock after its first step (1 / fps), not 0. Held to the times two real recordings posted
    (kit/test/python/test_vfx_dailies.py: the FlameArc animatic's 107 frames, starblade's 569 with slow motion).
    preset: the preset AS PLAYED (played(): the bundle's, never the file's when the two differ). What is not a
    number in it is left out, never crashed on. A preset with no length plays 5 s, as in the player.
    Not modelled: an impact frame inside a hit-stop's `span` is DRAWN during the held frames (the player runs those
    on the held clock) - a beat that is only such a frame shows up to the hold's length before this clock has it."""
    clock, _ = numbers_only(preset)
    stops = [(h["at"], h["hold"]) for h in clock.get("hitstop", [])]
    warp = [(k[0], k[1]) for k in clock.get("timewarp", [])]
    duration = min(clock.get("duration", 5.0), limit)

    def rate(t):
        if not warp:
            return 1.0
        if t <= warp[0][0]:
            return 1.0 if warp[0][0] > 0 and t < warp[0][0] else warp[0][1]
        for a, b in zip(warp, warp[1:]):
            if t <= b[0]:
                return a[1] + (b[1] - a[1]) * ((t - a[0]) / max(1e-6, b[0] - a[0]))
        return 1.0 if t > warp[-1][0] else warp[-1][1]

    dt = 1.0 / float(fps)
    time, hold_left, shown = 0.0, 0.0, []
    while time < duration - 1e-6 and len(shown) < 100000:
        if hold_left > 0:
            hold_left -= dt
            if hold_left > 0:
                shown.append(time)                          # a held frame: the same moment again
                continue
        t = time + dt * rate(time)
        for at_, hold in stops:
            if time < at_ <= t:
                t, hold_left = at_, hold
                break
        time = t
        shown.append(time)
    return shown


def clock_of(preset, fps=30.0):
    """effect seconds -> seconds of the effect's RECORDING at `fps`: the first frame that shows that moment or a
    later one (a layer that starts at 0.30 s is first seen in the frame whose clock has reached 0.30 s). The chart's
    times are the effect's clock; a recording is real time, and every hit-stop before a beat moves it (a beat the
    chart puts at 1.90 s, after hit-stops of 0.12 and 0.06 s, starts about 0.13 s later in a 30-a-second recording:
    four held frames). Read by its chart time, a late beat's stretch showed the beat BEFORE it (found by the timing
    animatic's own check, 2026-11-12). Exact to the frame: see frame_times."""
    shown = frame_times(preset, fps)

    def real(t):
        t = float(t)
        lo, hi = 0, len(shown)
        while lo < hi:                                      # the first frame whose clock has reached t
            mid = (lo + hi) // 2
            if shown[mid] >= t:
                hi = mid
            else:
                lo = mid + 1
        return lo / float(fps)

    return real


def stretch(beats, k, fps, length, clock=None):
    """our stretch of the RECORDING for beat k (clock: clock_of the preset that was recorded - the chart's times are
    the effect's clock, the recording is real time; None = a recording with no hit-stop and no slow motion):
    from its own start to two frames before the next beat IN TIME starts (a
    chart's rows are not always in time order: katana_water_set runs 0, .05, .08, .9, .45), and three frames at
    least - a flash of one frame is a beat too, and three frames is the least a read needs (it then runs into the
    next beat's first frames, which is said nowhere else: a pad either side once let the next beat's flash be read
    as this one's light, flame_arc_v2's ribbon, 2026-11-12). Never past the recording's end: a beat within
    three frames of it gets what is left, and the read says the recording holds too little of it -> (from, to) s"""
    def at(row):
        try:
            return float(row.get("t") or 0.0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    real = clock or (lambda t: t)
    a = max(0.0, at(beats[k]))
    later = [at(r) for r in beats if at(r) > a + 1e-9]
    # (two frames before the next beat: a recording's frames are not cut on the effect's clock, and the next beat's
    # first light was found in this one's last frame - flame_arc_v2's ribbon read the clash's flash as its peak)
    b = (real(min(later)) - 2.0 / fps) if later else length
    a = real(a)
    return a, min(length, max(b, a + 3.0 / fps))
