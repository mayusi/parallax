"""animatic.py — the TIMING ANIMATIC (the VFX studio-route plan, V2): an effect's MOTION in flat shapes, made from
the beat chart and the scene's measured timing BEFORE its look is built.

    lune run kit vfx animatic <set> [--view hero] [--fps 30] [--no-record] [--angles combat,cine]
    lune run kit vfx animatic <set> --check
    lune run kit vfx animatic <set> --drift <effect> [--view hero]

    lune run kit vfx animatic <set> --blocking [--angles combat,cine]   (the solid beats alone: worked out and DRAWN
                                                                         from every angle; no recording, no browser)

SOLID BEATS (kit/vfx/blocking.py, 2026-11-15): a chart's beat may say "solid": {"form": "ball" | "pillar" | "slab",
"size": studs, "at": [x, z], "lift": studs, "to": [x, z]} ("to": it MOVES there over its beat). It is then a real 3D shape standing in the effect's own place - not a
card near the camera - and is worked out from the animatic's own view and every gameplay angle of --angles (`combat`
unless said): how much of it is in the picture, how much of the picture it covers, what hides it, whether it touches
the ground. A solid beat an angle cannot show stops the run, in words. The record keeps what every angle sees. Only
the animatic's own view is FILMED by the player, and that film does NOT show a solid's volume or what it hides (the
player draws these shapes as flat glowing colour, one laid over the other). So the solids are also DRAWN, by rays,
from the animatic's view and every angle - lit, the nearer hiding the farther, the ground dark where they touch it:
build/vfx/animatic/<set>_blocking.png (every solid beat from every angle) and <set>_angles.mp4 (all angles at once
on the chart's clock). Both are part of what the owner is shown. A chart with a MOVING solid is checked for flow:
every solid at eleven moments of its beat, from every angle. (--blocking writes <set>_blocking_look.png and
<set>_angles_look.mp4: a look only, never the files his yes covers.) A chart with no solid beat is the plan it always was (the same id, the same record).

Why: the owner approves the chart as a still picture, and the motion is first seen when the whole effect is built -
textures, meshes and all. A studio blocks the motion first: flat shapes at the final timing, watched beside the
reference, approved, and only then is the look paid for.

What it makes (everything in the git-ignored build/: the scene's frames are private):
  build/vfx/animatic/<set>.json            the blocking PRESET (version 3, no textures, no sims): per beat ONE flat
                                           shape facing the camera - a disc, ring, arc, bar or wall, read from the
                                           beat's words, else from how much of the frame the scene's beat covers - at
                                           the chart's time and length, sized to the scene's measured share of the
                                           screen, arriving and going as the scene's main shot does, drawn on the
                                           scene's rhythm (on ones / twos), with the chart's hit-stops and slow motion.
                                           It is checked by the kit's own preset rules (validate_preset.luau) before
                                           anything is recorded or recorded over
  build/vfx/booth/<set>_animatic_play_<view>.mp4   its recording in the player (kit vfx play <set> --animatic --record)
  build/vfx/animatic/<set>.recorded.json   what that recording is OF, written the moment it is made: the plan's id,
                                           the size corrections it was made with, the recording's own stamp
  build/vfx/dailies/<set>_animatic/        the scene's consecutive frames above the animatic's, beat by beat, with
                                           what differs in seconds (the dailies' own pages: kit/vfx/dailies.py)
  build/vfx/animatic/<set>_side.mp4        the two in MOTION side by side, beat after beat, each pair laid on its hit,
                                           the two light curves under them with a cursor; then the animatic alone
                                           on its own clock. This is what the owner watches.
  build/vfx/animatic/<set>.plan.json       what it was made from, what was measured back from its recording, its id

Where the scene could not say (a shot that opens on the light, or ends while it is lit), and wherever the plan had
to settle a number itself (a beat cut short by the next one, a hold longer than the player's longest, a beat too
short for its rhythm), the beat's NOTES in the record say so: nothing is invented or capped silently. A beat that
cannot be shown at all (it starts at or after the chart's end) fails the run.

--no-record reads the recording that is on this machine instead of making one - only when <set>.recorded.json says
it IS this plan's recording (the same id, the same view, the very file). A chart re-timed after its recording is
another plan: the old recording is refused, never given a new record.
A run that is refused touches nothing of the animatic that is here - not its record, not its video, not its preset
(a new preset is checked by the kit's rules under another name first). A run that RECORDS puts its preset in place
and starts the recorder: the animatic that was here then reads out of date as soon as its preset or its recording
is another one (both are part of what its record is of), and stays as it was only if neither changed.

Each beat is READ BACK from the recording: its light must arrive in the very frame that first shows its hit drawing
(the player's own sums on the recorder's own clock: first_shown). A beat whose light cannot be told from another's
is NOT READ, and its notes say so: it has under three frames before the next beat, its hit shows only after the
next beat has started, another beat's shape is still lit when it hits, or its stretch opens on light the PLAN has
there from the beat before. The video shows such a beat; --drift cannot hold an effect to it. Light before a beat
that the plan does not have there is a fault (the recording is not this plan's). An animatic of which no beat
could be read back fails; so does one whose hit drawing no frame shows (--fps is 24 to 120).

WHAT the owner's yes is recorded for (lune run kit approve vfx <set> "<his words>" --by owner --stage animatic):
  the ID     a hash of the plan: every beat's time, length, hold, slow motion, arrival, going, rhythm, share and
             shape, the view (its name and where its camera stands), the set's colour band, and where the scene's
             numbers came from (each beat's window of the scene, the clip, its cuts). A chart re-timed, or pointed
             at another part of the scene, after his yes is another plan: his word again;
  DRAWN      a hash of what he watched and looked at - the side-by-side video and the beat pages, read from the
             files - and of the WHOLE record beside them (its beats, its clock, its frame rate: everything --drift
             holds an effect to). A number changed anywhere in the record is a changed animatic.
--check [--view <view>] answers without making anything and without reading a clip: {exists, id, drawn, stale, why,
problems, shown, png}. Stale: the plan is another now, a shown file or anything in the record was changed, or the
animatic was recorded again since (a recording that is merely gone changes nothing he was shown).

--drift <effect>: the BUILT effect's recording read beat by beat against the animatic's plan, each recording on its
own clock (a recording is real time: every hit-stop before a beat moves it - denseclip.clock_of, the recorder's own
loop frame by frame; the effect's clock is its preset AS PLAYED: denseclip.played). What is named, and fails:
  - a beat whose light ARRIVES - is first at most (0.7) of what its stretch reaches, over the timing read's own
    floor - more than ONE drawing from where the animatic's does. One drawing and a quarter frame, nothing more;
  - a beat whose light was already at its own strength before the beat started (it came early);
  - a beat with no light of its own: what is lit when it starts has been on since the beat before.
  - a beat that, on the effect's OWN clock, has under three frames before the next one where the animatic's clock
    gives it room (a hit-stop or slow motion of the chart is not in the effect).
A beat the animatic itself could not read back is LISTED as not held; a beat on time but under half the planned size
is SAID (the look is the style sheet's to judge). It answers only when there is something true to hold the effect
against: the animatic here is current and passed its own check, the effect is built from THIS set, read in the
animatic's own view, and its recording is not older than its
preset's file (a part's file edited later is not seen). The summary says whose motion it is: "its approved motion"
only when the project's board/locks.json holds the owner's yes for this very animatic.
WHAT IT IS NOT: it reads LIGHT, nothing else. A flash at most of a beat's light on time, with the beat's body coming
later, reads on time; so does any motion that puts as much light on screen at the same moments. It is a guard
against a beat's layers placed late or early - not a judge of the motion. The dailies' frames are, and the owner.

LIMIT: these tools read and write the project's own build/. With a game active the play command records into THAT
game's build folder, which they do not see (board: kit lane).

Prints one JSON line {schema, status, summary, next_action, ...}; the summary ends with LOOK: <what to open>.
"""

import colorsys
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocking as BL  # noqa: E402  (solid blocking: kit/vfx/blocking.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dailies  # noqa: E402
import dailies_page as P  # noqa: E402
import dense  # noqa: E402
import denseclip as DC  # noqa: E402

OUT = DC.gameroot.build("vfx", "animatic")  # the active game's build/vfx, where kit vfx play --animatic reads (card t6rx)
GENERATOR = 3                    # the plan's own rules (how a beat's light is drawn, where its hit-stop goes, the
#                                  colours ...): a change to them is another plan. 2: whole drawings, the light whole
#                                  ON the hit. 3: a layer starts ON its beat, the stop inside the hit drawing (stop_on)
FILM = 24.0                      # drawings are counted in 24ths of a second
FLAGS = {"--view", "--fps", "--effects", "--drift", "--port", "--angles"}
BARE = {"--check", "--no-record", "--blocking"}
RING_INNER = 0.62
ARC = {"arc": 150, "width": 0.6}   # a thick crescent: its band crosses the frame (a thin one of this share lies outside it)
WHITE_HOT = [255, 246, 228]
NEAR = 6.0                       # studs from the camera: the shapes are cards in front of the booth (see card_point)
PRIMARY, BLOOM = 0.59, 3.4       # how the player shows a flat Neon card (measured 2026-11-12: see colour_of)
SHAPES = (("ring", r"\b(ring|halo|shock ?wave|nova)\b"),       # (before the arc: a shock wave is a ring, a wave an arc)
          ("arc", r"\b(arc|crescent|slash|swing|sweep|wave)\b"),
          ("bar", r"\b(beam|streak|line|ribbon|trail|bolt|bar|lance)\b"),
          ("wall", r"\b(wall|flash|white-?out|screen)\b"))
SIDE_W, SIDE_H, STRIP_H, SIDE_FPS = 640, 360, 150, 24


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ------------------------------------------------------------------------------------------------ the plan
def view_of(name):
    """a camera view of kit/vfx/views.json (a path's first key) -> {"pos", "look", "fov"} or None"""
    try:
        v = json.load(open(os.path.join(HERE, "views.json"), encoding="utf-8")).get(name)
    except (OSError, ValueError):
        return None
    if isinstance(v, dict) and isinstance(v.get("path"), list) and v["path"]:
        v = v["path"][0]
    if not (isinstance(v, dict) and isinstance(v.get("pos"), list) and isinstance(v.get("look"), list)):
        return None
    return {"pos": [float(x) for x in v["pos"]], "look": [float(x) for x in v["look"]], "fov": float(v.get("fov", 66))}


def frame_size(view):
    """(width, height) in studs of what the camera sees NEAR studs in front of it (a 16:9 picture)"""
    h = 2.0 * NEAR * math.tan(math.radians(view["fov"]) / 2.0)
    return h * 16.0 / 9.0, h


def card_point(view):
    """where the flat shapes stand: on the camera's own line of sight, NEAR studs in front of it. At the point the
    camera looks at (the effect's place) the lower third of the frame is the booth's ground, and it cut every shape
    larger than a few studs (the second FlameArc animatic, 2026-11-12); this near, nothing of the booth is in front"""
    d = math.dist(view["pos"], view["look"]) or 1.0
    return [round(p + (q - p) * NEAR / d, 4) for p, q in zip(view["pos"], view["look"])]


def shape_of(text, share):
    """a beat's flat shape: from its words, else a wall when the scene's beat fills the frame, else a disc"""
    low = str(text).lower()
    for shape, pattern in SHAPES:
        if re.search(pattern, low):
            return shape
    return "wall" if share > 0.42 else "disc"


def unit_area(shape):
    """the flat area of a shape at size 1 (bar: 6 to 1, wall: 16 to 9, both `size` wide)"""
    return {"disc": math.pi, "ring": math.pi * (1 - RING_INNER ** 2), "bar": 1 / 6.0, "wall": 9 / 16.0,
            "arc": math.radians(ARC["arc"]) * ARC["width"] * 0.72}[shape]    # (0.72: the crescent's taper to its tips)


def size_of(shape, share, view, gain=1.0):
    """the shape's size in studs to cover `share` of the screen (gain: a correction measured back from a recording)"""
    w, h = frame_size(view)
    return math.sqrt(max(0.004, min(float(share), 0.95)) * w * h / unit_area(shape)) * gain


def at(row):
    try:
        t = row.get("t")
        t = 0.0 if isinstance(t, bool) else float(t or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return t if math.isfinite(t) else 0.0


def num(row, key, default, notes):
    """a chart row's number; one that is not a number (true / false, text, nan, inf) is read as the default, and the
    row's notes say so"""
    v = row.get(key) if isinstance(row, dict) else None
    if v is None or v == "":
        return float(default)
    try:
        got = float("nan") if isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        got = float("nan")
    if not math.isfinite(got):
        notes.append(f"the chart's \"{key}\" ({v!r}) is not a number: read as {default:g}")
        return float(default)
    return got


def plan_rows(beats, reads, duration):
    """the chart's beats + the scene's read of each -> the animatic's rows. reads[k]: {"timing": dense.timing of the
    scene's main shot, "share": the share of the screen it covers at its most} or None (not read on this machine).
    Every value that is not the chart's or the scene's own - a default, a cap, a clamp - is a NOTE on its row; a
    beat that cannot be shown at all (no room before the chart's end) carries a "problem"."""
    duration = float(duration)
    least = 2.0 / FILM                                      # the least a shape is seen for: two film frames
    rows = []
    for k, row in enumerate(beats):
        notes, problem = [], None
        name = row.get("beat", k)
        start = round(num(row, "t", 0.0, notes), 3)
        later = [at(r) for r in beats if at(r) > start + 1e-9]
        room = (min(later) if later else duration) - start
        till_end = duration - start
        length, hold, slow = (num(row, key, default, notes) for key, default in (("len", 0.0), ("hold", 0.0), ("slow", 1.0)))
        for key, value in (("len", length), ("hold", hold)):
            if value < 0:
                notes.append(f"the chart's \"{key}\" is negative ({value:g}): read as none")
        length, hold = max(0.0, length), max(0.0, hold)
        if start < 0:
            problem = f"beat {name} starts before the chart does ({start:.2f} s)"
        elif till_end <= 1e-6:
            problem = f"beat {name} starts at {start:.2f} s, at or after the chart's end ({duration:.2f} s)"
        elif till_end < least - 1e-9:
            problem = (f"beat {name} starts {till_end:.2f} s before the chart's end ({duration:.2f} s): a shape is seen "
                       f"for {least:.2f} s at least - move the beat or lengthen the chart")
        wanted = min(length, room) if length > 0 else room
        # (never past the chart's end: the player refuses a layer still running there. Rounded DOWN: a rounded start
        # plus a rounded life must not cross it)
        life = math.floor(min(max(least, wanted), max(till_end, least)) * 1000 + 1e-6) / 1000
        if length > room + 1e-6 and room >= least:
            notes.append(f"the chart gives it {length:.2f} s but {'the next beat starts' if later else 'the chart ends'} "
                         f"after {room:.2f} s: shown that long")
        if wanted < least - 1e-9 and not problem:
            notes.append(f"it has {max(wanted, 0.0):.2f} s on the chart: shown for {least:.2f} s, the least a shape is seen for"
                         + (" (it is still there when the next beat starts)" if room < least - 1e-9 else ""))
        read = reads[k] if k < len(reads) else None
        t = read.get("timing") if isinstance(read, dict) else None
        if not t:
            arrive, go, on, share = 0.0, 2.0 / FILM, 2, 0.12
            notes.append("the scene's shot of this beat was not read on this machine: a plain default (a disc, at once, on twos)")
        else:
            sec = t["seconds"]
            arrive = 0.0 if t["cut_in"] else float(sec["arrive"])
            if t["cut_in"]:
                notes.append("the scene's shot opens on it already lit: how it arrives is not known, shown at once")
            if t["stay_cut"] or t["cut_away"]:
                go = 2.0 / FILM
                notes.append("the scene's shot ends while it is lit: how it goes is not known, shown in two frames")
            else:
                go = float(sec["go"])
            on, share = int(t["on"] or 2), float(read.get("share") or t["peak"])
            if not t["on"]:
                notes.append("the scene's drawing rhythm could not be read (too few whole drawings): shown on twos")
            if on > FILM:
                notes.append(f"the scene holds a drawing {on} film frames: shown one drawing a second, the slowest rhythm here")
                on = int(FILM)
        if hold > 1.8:
            notes.append(f"the chart holds it {hold:.2f} s: the player's longest hit-stop is 1.80 s, shown as that")
            hold = 1.8
        elif 0 < hold < 0.02:
            notes.append(f"a hold of {hold:.3f} s is under the player's shortest hit-stop (0.02 s): none shown")
            hold = 0.0
        if slow <= 0:
            notes.append(f"slow {slow:g} is not a speed (it is how many times slower the clock runs: 1 or more): shown at its own")
            slow = 1.0
        elif slow < 1.0 - 1e-9:
            notes.append(f"slow {slow:g} would be FASTER than real time: the player's clock has no such speed, shown at its own")
            slow = 1.0
        elif slow > 20.0:
            notes.append(f"slow {slow:g}: the player's slowest clock is a twentieth of real time, shown as that")
            slow = 20.0
        # a beat shorter than two drawings of its rhythm cannot be drawn on it (its curve would end after its life:
        # the player refuses that preset): shown on the finest rhythm that still gives it two drawings
        rhythm = "on " + {1: "ones", 2: "twos", 3: "threes"}.get(on, f"{on}s")
        step = FILM / max(1, on)
        if life * step < 2.0 - 1e-6:
            step = min(60.0, 2.0 / life + 0.5)
            notes.append(f"it is shorter than two drawings {rhythm}: shown on a finer rhythm ({step:.0f} drawings a second)")
            rhythm = f"at {step:.0f} drawings a second"
        step = round(step, 3)
        # the shape is DRAWN on that rhythm: its light changes only ON a drawing. So its arrival and its going are
        # whole drawings - the hit, and the chart's hit-stop on it, must be a drawing that is there (the exact clock
        # showed two FlameArc beats lit two frames after their plan: their hit lay between two drawings, 2026-11-12)
        count = max(1, int(math.floor(life * step + 1e-6)))             # the drawings its life holds
        half = int(math.floor(0.5 * life * step + 1e-6))
        if arrive > 0.5 * life + 1e-6:
            notes.append(f"the scene takes {arrive:.2f} s to arrive, the chart gives the beat {life:.2f} s: shown arriving "
                         f"over half of it")
        n = max(0, min(int(round(arrive * step)), half, count - 1))
        if abs(n / step - min(arrive, 0.5 * life)) > 0.25 / FILM:
            notes.append(f"its light takes {min(arrive, 0.5 * life):.3f} s to arrive: drawn {rhythm} that is "
                         f"{'at once' if n == 0 else f'{n} drawing(s), {n / step:.3f} s'}")
        arrive = n / step
        after = max(0, count - n - 1)                       # the drawings left after the hit for it to go in
        if go > after / step + 1e-6:
            notes.append(f"the scene takes {go:.2f} s to go, the beat has {after / step:.2f} s after it arrives: shown "
                         f"going over that")
        fall = max(1 if after >= 1 else 0, min(int(round(go * step)), after))
        if abs(fall / step - min(go, after / step)) > 0.25 / FILM:
            notes.append(f"its light takes {min(go, after / step):.3f} s to go: drawn {rhythm} that is "
                         f"{'at once' if fall == 0 else f'{fall} drawing(s), {fall / step:.3f} s'}")
        go = fall / step
        rows.append({"index": k, "beat": str(name), "key": bool(row.get("key")), "t": start,
                     "life": life, "hold": round(hold, 3), "slow": round(slow, 3), "arrive": round(arrive, 3),
                     "go": round(go, 3), "on": on, "step": step, "share": round(share, 4),
                     "shape": shape_of(row.get("beat", ""), share), "hit": round(start + arrive, 3), "notes": notes})
        if row.get("solid") is not None:
            # SOLID BLOCKING (kit/vfx/blocking.py): the beat is a real 3D shape in the effect's own place, not a card
            try:
                rows[-1]["solid"] = BL.checked(row["solid"])
            except ValueError as e:
                problem = problem or f"beat {name}: {e}"
        if problem:
            rows[-1]["problem"] = problem
    return rows


def block_solids(rows, view_name, view, asked=None):
    """the chart's SOLID beats, worked out from every angle (the animatic's own view, and the gameplay angles asked:
    `combat` unless said) -> ({angle: [what it sees of each solid beat]}, the problems in words, the angles' names).
    A solid beat's "share" becomes what the animatic's own view sees of it (a card is SIZED to a share; a solid has
    its size in studs, and its share follows). A chart with no solid beat: ({}, [], [])"""
    if not any(r.get("solid") for r in rows):
        return {}, (["--angles is for a chart with a solid beat (a beat's \"solid\": {\"form\", \"size\"}): this chart has none"] if asked else []), []
    names = list(dict.fromkeys([view_name] + list(asked or ["combat"])))
    views, problems = {}, []
    for n in names:
        v = view if n == view_name else view_of(n)
        if v:
            views[n] = v
        else:
            problems.append(f"no camera view '{n}' in kit/vfx/views.json")
    if problems:
        return {}, problems, names
    report, problems = BL.angles([r for r in rows if not r.get("problem")], views)
    for r in rows:
        got = next((x for x in report[view_name] if x["index"] == r["index"]), None) if r.get("solid") else None
        if got:
            # (a solid that moves covers more of the picture as it comes nearer: its share is the MOST it covers on the
            # way - what the read-back of a recording measures - not the least)
            most = (got.get("flow") or {}).get("most", got["share"])
            r["share"] = round(max(0.004, min(most, 0.95)), 4)
            r["notes"].append(f"a solid ({r['solid']['form']}, {r['solid']['size']:g} studs): its share of the screen is what the {view_name} view sees of it, "
                              f"not the scene's measured one")
    return report, problems, names


def draw_solids(set_name, rows, view_name, view, angle_names, duration, hue, look=False):
    """the chart's solids DRAWN from the animatic's view and every angle (kit/vfx/blocking.py: volume, what hides what,
    the ground they touch - what the player's film does not show) -> ([the files written], the problems in words)"""
    views = {n: (view if n == view_name else view_of(n)) for n in angle_names}
    colours = {r["index"]: tuple(WHITE_HOT) if r["key"] else BL.PALETTE[r["index"] % len(BL.PALETTE)] for r in rows}
    os.makedirs(OUT, exist_ok=True)
    # look: a run of --blocking, to LOOK only - its files have names of their own: the animatic's own sheet and film
    # are part of what the owner's yes covers, and a look from other angles would have made his animatic read changed
    tail = "_look" if look else ""
    png, mp4 = os.path.join(OUT, f"{set_name}_blocking{tail}.png"), os.path.join(OUT, f"{set_name}_angles{tail}.mp4")
    made, problems = [], []
    try:
        if BL.sheet(rows, views, png, colours):
            made.append(png.replace(os.sep, "/"))
        if BL.film(rows, views, mp4, duration, colours):
            made.append(mp4.replace(os.sep, "/"))
        else:
            problems.append("the film of the solids from every angle could not be written (ffmpeg)")
    except Exception as e:  # noqa: BLE001  (said, never swallowed)
        problems.append(f"the solids could not be drawn ({type(e).__name__}: {str(e)[:120]})")
    return made, problems


def blocking_only(found, view_name, asked=None):
    """--blocking: the chart's solid beats worked out and DRAWN from every angle, and nothing else - no recording, no
    browser, and nothing of the animatic that is here touched: its drawings have names of their own (_look)"""
    set_name = found["set"]
    view = view_of(view_name)
    if not view:
        return out("fail", f"animatic {set_name}: no camera view '{view_name}' in kit/vfx/views.json", "name one of its views")
    duration = duration_of(found)
    rows = plan_rows(found["beats"], scene_reads(found), duration)
    unshown = [r["problem"] for r in rows if r.get("problem")]
    if unshown:   # (a solid that is not one - a form that is none - is said, not dropped)
        return out("fail", f"animatic {set_name}: the chart cannot be shown - {'; '.join(unshown)}",
                   f"fix the chart ({found['measured'].replace(os.sep, '/')}/{set_name}.chart.json), then again")
    seen_from, hidden, angle_names = block_solids(rows, view_name, view, asked)
    if not angle_names:
        return out("fail", f"animatic {set_name}: the chart has no solid beat to block (a beat's \"solid\": {{\"form\", \"size\"}})",
                   f"add one in the chart ({found['measured'].replace(os.sep, '/')}/{set_name}.chart.json)")
    if hidden:
        return out("fail", f"animatic {set_name}: the chart's solid beats cannot be shown - {'; '.join(hidden)}",
                   f"change the beat's \"solid\" in the chart ({found['measured'].replace(os.sep, '/')}/{set_name}.chart.json), or name other --angles")
    drawn, problems = draw_solids(set_name, rows, view_name, view, angle_names, duration, found["hue"], look=True)
    if problems:
        return out("fail", f"animatic {set_name}: {'; '.join(problems)}", "read the message, then again")
    n = sum(1 for r in rows if r.get("solid"))
    moving = sum(1 for r in rows if r.get("solid") and r["solid"].get("to"))
    return out("pass", f"animatic {set_name}: {n} solid beat(s) ({moving} moving) worked out and drawn from {', '.join(angle_names)}: every one "
               f"can be seen from every angle{', at eleven moments of its way' if moving else ''}. LOOK: {drawn[0]}",
               f"OPEN {drawn[0]} (every solid beat from every angle: its volume, what hides it, where it stands) and WATCH {drawn[-1]} "
               f"(all angles at once, on the chart's clock); then the animatic itself: lune run kit vfx animatic {set_name}",
               shown=drawn, angles=seen_from, angle_names=angle_names)


def source_of(found):
    """where the plan's scene numbers come from, as one short id: each beat's window of the scene, the clip's name,
    size and frame rate, its cuts (nothing of the clip is read: a check stays cheap). A chart pointed at another
    part of the scene is another plan, though no beat moved"""
    b = found.get("breakdown") if isinstance(found.get("breakdown"), dict) else {}
    clip = str(b.get("clip") or "")
    try:
        size = os.path.getsize(clip) if clip else None
    except OSError:
        size = None                                         # (the clip is not on this machine: said in the notes)
    text = json.dumps([[r.get("scene") for r in found["beats"]], os.path.basename(clip), size, b.get("clip_fps"),
                       list(found.get("cuts") or [])], sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def duration_of(found):
    """the chart's length in seconds, 0.0 when it has none that is a number"""
    try:
        d = float((found.get("chart") or {}).get("duration") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return d if math.isfinite(d) and d > 0 else 0.0


def unsound(found):
    """why this set's chart cannot be planned at all, or None"""
    chart = found.get("chart")
    if not isinstance(chart, dict):
        return f"no beat chart of {found['set']}"
    beats = chart.get("beats")
    if not isinstance(beats, list) or not beats or not all(isinstance(b, dict) for b in beats):
        return f"the chart of {found['set']} has no list of beats"
    if duration_of(found) <= 0:
        return f"the chart of {found['set']} has no duration"
    return None


def refusals(paths):
    """the kit's own preset rules on preset FILES (kit/vfx/validate_preset.luau runs src/kit/VfxValidate: what the
    player's command checks before it plays anything) -> {path: the errors, [] when the player takes it}. A check
    that could not be run is an error of every file: a preset nobody checked is not one to write a record over"""
    paths = [os.path.abspath(p) for p in paths]
    tool, lune = os.path.join(HERE, "validate_preset.luau"), shutil.which("lune")
    if not lune:
        return {p: ["the kit's preset rules could not be run on it (lune is not on PATH)"] for p in paths}
    answer = {}
    for i in range(0, len(paths), 40):                      # (a command line holds only so many paths)
        some = paths[i:i + 40]
        try:
            # (run from the folder kit/ is in: lune is found through that project's own tool manifest, wherever the
            # caller stands - a made project in a temp folder has none)
            got = subprocess.run([lune, "run", tool, *some], capture_output=True, text=True, timeout=120,
                                 cwd=os.path.abspath(os.path.join(HERE, "..", "..")))
            said = json.loads(got.stdout.strip().splitlines()[-1])
            if not isinstance(said, dict) or set(said) != set(some):
                raise ValueError("not an answer for these files")
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            answer.update({p: [f"the kit's preset rules could not be run on it ({type(e).__name__})"] for p in some})
            continue
        # (an empty list of errors comes back as {}: Lua has one empty table)
        answer.update({p: [str(e) for e in said[p]] if isinstance(said[p], list) else [] for p in some})
    return answer


def refused(path):
    """one preset file's errors by the kit's own rules, [] when the player takes it (see refusals)"""
    return refusals([path])[os.path.abspath(path)]


def plan_id(set_name, rows, view_name, duration, hue=None, source=None, view=None, angles=None):
    """the plan as one id: every beat's own fields (never what is measured back from a recording), the view - its
    name and where its camera stands (the shapes are sized and placed by it) - the set's colour band (the shapes'
    colour) and where the scene's numbers came from"""
    core = [[r["beat"], r["t"], r["life"], r["hold"], r["slow"], r["arrive"], r["go"], r["on"], r.get("step"), r["share"],
             r["shape"], r["key"]] for r in rows]
    camera = [view.get("pos"), view.get("look"), view.get("fov")] if isinstance(view, dict) else None
    parts = [GENERATOR, set_name, view_name, camera, round(float(duration), 3), core, [round(float(h), 2) for h in hue] if hue else None, source]
    if any(r.get("solid") for r in rows):   # (a chart with no solid beat is the plan it always was: the same id)
        # the solids, and every angle they are worked out from - its NAME and where its camera stands (a camera moved
        # in views.json is another check: another plan)
        cams = []
        for n in angles or []:
            v = view if n == view_name else view_of(n)
            cams.append([n, [v.get("pos"), v.get("look"), v.get("fov")] if isinstance(v, dict) else None])
        parts.append([[r.get("solid") for r in rows], cams])
    text = json.dumps(parts, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:24] or "beat"


def colour_of(hue, key):
    """the flat colour: inside the set's measured hue band AS THE PLAYER SHOWS IT (the timing read sees the animatic
    as it sees the effect); the key beat white-hot. A preset's colours are linear light - the player's last pass
    raises them to 1/2.2 - so the colour wanted on screen is written as its 2.2th power (written as it should look,
    [255, 140, 25] came out pale yellow, outside the fire band: the first FlameArc animatic, 2026-11-12)"""
    if key:
        return list(WHITE_HOT)
    mid = ((hue[0] + hue[1]) / 2.0) if hue else 28.0
    shown = colorsys.hsv_to_rgb((mid % 360.0) / 360.0, 0.85, 1.0)
    # ... and the player's bloom lifts a flat card further: measured on six cards, the strongest channel is full at
    # PRIMARY of full light and the others come out about BLOOM times what was written ([150, 22, 0] shows as
    # (254, 146, 38): hue 30, the middle of the fire band; [228, 68, 4] shows yellow, hue 56, outside it). Measured
    # for a red-led colour; make() reads the recording back and says so when a set's colour is not seen
    top = max(shown)
    return [int(round(255 * (PRIMARY if c >= top else (c ** 2.2) / BLOOM))) for c in shown]


def drawings_of(row):
    """a beat's life in drawings of its rhythm -> (drawings a second, how many its life holds, the drawing its
    light arrives ON, how many it takes to go)"""
    step = float(row.get("step") or FILM / max(1, row["on"]))
    count = max(1, int(math.floor(row["life"] * step + 1e-6)))
    n = max(0, min(int(round(row["arrive"] * step)), count - 1))
    fall = max(0, min(int(round(row["go"] * step)), count - n - 1))
    return step, count, n, fall


def first_shown(times, start, step, n=0, life=None):
    """the first frame of a recording in which a layer that starts at `start` is on its drawing n, or a later one -
    by the player's OWN sums (player.js: a layer is alive when `t >= at`, on the drawing
    `Math.floor((t - at) * step)`) on the recorder's OWN clock (times: denseclip.frame_times). Nothing is rounded
    and nothing is left to luck: a frame whose clock is a hair under a round time does not show the beat, and this
    says so. life: the layer's life, when the drawing must be shown while the layer is alive (`(t - at) / life <= 1`).
    len(times) when no frame shows it (a drawing shorter than a frame can fall between two)."""
    for i, t in enumerate(times):
        if t >= start and math.floor((t - start) * step) >= n:
            return i if life is None or (t - start) / life <= 1 else len(times)
    return len(times)


def stop_on(start, step, n, duration):
    """when the clock stops for a beat's hit: ON its hit drawing, by the player's own sum. The hit is start + n /
    step; written in thousandths (as a preset is) that can be a hair BEFORE the drawing starts - 0.083 is before
    2/24, and 0.175 - 0.05 is 0.12499999999999999 in a computer (on ones: still the drawing before the fourth) - and
    the clock, stopped there, froze the drawing before the hit. So: the first
    thousandth from the hit on at which `floor((stop - start) * step)` is the hit drawing. Never before a sixtieth
    of a second (the player has no hit-stop at 0), never in the chart's last hundredth."""
    stop = round(max(start + n / step, 1.0 / 60), 3)
    for _ in range(5):
        if math.floor((stop - start) * step) >= n:
            break
        stop = round(stop + 0.001, 3)
    return round(min(stop, float(duration) - 0.01), 3)


def light_of(row):
    """the beat's light as shares of its whole, one for each drawing 0 .. count (the last: gone).
    The timing read measures LIGHT - how much of the frame is lit - over a floor it takes from the stretch itself
    (what is lit through nearly all of it), and calls a beat ARRIVED at 0.7 of the way from that floor to its peak.
    A beat's own lead-in or going can be taken for that floor, so the line can sit anywhere from 0.70 to about 0.85
    of the whole light. The drawings are made to be read right wherever it sits: before the hit the light rises
    from 0.15 to 0.45 (never near the line), ON the hit it is WHOLE, it stays whole but a hair smaller (0.94) on
    every other drawing (a held drawing and a new one can be told apart - by the eye, and by the read), goes from
    0.6 to 0.3, and is gone. (0.7 on the hit, then 0.85, were each read as the hit or as the drawing after it by the
    luck of a blurred edge or of the floor: the FlameArc animatics, 2026-11-12.)"""
    _, count, n, fall = drawings_of(row)
    last_stay = count - fall - 1
    light = []
    for k in range(count + 1):
        if k == count:
            light.append(0.0)
        elif k < n:
            light.append(0.3 if n == 1 else 0.15 + 0.3 * k / (n - 1))
        elif k <= last_stay:
            light.append(1.0 if (k - n) % 2 == 0 else 0.94)
        else:
            light.append(0.45 if fall == 1 else 0.6 - 0.3 * (k - last_stay - 1) / (fall - 1))
    return light


def layer_of(row, view, hue, gain=1.0):
    """one beat as one mesh layer: flat, facing the camera, in front of the booth; ONE key a drawing of its rhythm,
    each ON its drawing (the layer's clock moves in drawings: a key between two is never shown as written)"""
    shape, s = row["shape"], size_of(row["shape"], row["share"], view, gain)
    full = {"bar": [s, 0.05, s / 6.0], "wall": [s, 0.05, s * 9.0 / 16.0]}.get(shape, [s, 1.0, s])
    life = row["life"]
    step, count, n, fall = drawings_of(row)
    light = light_of(row)
    # where each drawing is in the layer's life. The last one is the last the stepped clock reaches: the shape must
    # be GONE on it (a curve that ends at the life's very end is never reached: the first animatic left every shape
    # at a tenth of its size under the next beat)
    us = [round(min(1.0, k / (step * life)), 5) for k in range(count + 1)]
    el = {"name": f"beat{row['index']}_{slug(row['beat'])}", "kind": "mesh",
          "shape": {"disc": "disc", "ring": "ring", "arc": "arc"}.get(shape, "Block"), "material": "Neon",
          "point": card_point(view), "aim": list(view["pos"]), "at": row["t"], "life": life,
          "color": colour_of(hue, row["key"]), "step": step}

    def closed(keys):
        return keys if keys[-1][0] >= 1.0 else keys + [[1.0, keys[-1][1]]]

    if row.get("solid"):
        # a SOLID: a real shape standing in the effect's own place, upright, not turned to any camera. It grows and
        # goes as a card does (its sides by the root of its light: what it covers follows the light) and its
        # UNDERSIDE stays where it stands: the middle rises by half its height as it grows
        mid, whole = BL.box_of(row["solid"])
        grow = [math.sqrt(max(light[k], 0.0004)) for k in range(count + 1)]
        el.pop("aim")
        el["shape"] = {"ball": "Ball", "pillar": "Cylinder", "slab": "Block"}[row["solid"]["form"]]
        el["point"] = [round(mid[0], 4), round(row["solid"]["lift"], 4), round(mid[2], 4)]
        el["scale"] = closed([[us[k], [round(v * grow[k], 4) for v in whole]] for k in range(count + 1)])
        # ... and one that says "to" goes there evenly over its beat (the layer's own frame is the effect's: x, z)
        to = row["solid"].get("to")
        dx, dz = ((to[0] - row["solid"]["at"][0]), (to[1] - row["solid"]["at"][1])) if to else (0.0, 0.0)
        # its way is done on the LAST DRAWING THAT IS SHOWN (the layer's clock moves in drawings and the last key is
        # never reached: paced over the whole life, a 1 s beat on twos stopped 20 of its 22 studs along - short of where
        # the check had looked at its end)
        reach = us[count - 1] if count > 1 and us[count - 1] > 0 else 1.0
        way = [min(1.0, us[k] / reach) for k in range(count + 1)]
        el["move"] = [[us[k], [round(dx * way[k], 4) if to else 0, round(whole[1] * grow[k] / 2.0, 4), round(dz * way[k], 4) if to else 0]]
                      for k in range(count + 1)]
        if el["move"][-1][0] < 1.0:
            el["move"].append([1.0, list(el["move"][-1][1])])
        return el
    if shape == "ring":
        el["params"] = {"inner": RING_INNER, "outer": 1}
    if shape == "arc":
        # a slash DRAWS itself in along the swing and is wiped from its tail: the arc's own sweep, at full size - a
        # hair smaller on every other drawing, so its rhythm shows as the other shapes' does (a crescent that never
        # changed read as one long freeze, and hid the chart's own hit-stop)
        el["params"] = dict(ARC)
        el["rotate"] = [0, 50, 0]    # turned in the picture's plane: a slash coming down across the frame, not a smile
        el["scale"] = closed([[us[k], [round(v * (1.0 if k % 2 == 0 else 0.97), 3) for v in full]] for k in range(count + 1)])
        last_stay = count - fall - 1
        el["sweep"] = {"head": closed([[us[k], round(light[k], 3) if k <= n else 1.0] for k in range(count + 1)]),
                       "tail": closed([[us[k], 0.0 if k <= last_stay else round(1.0 - light[k], 3)] for k in range(count + 1)])}
        return el
    # the shape's AREA is its light: its sides move with the root of it (a width that moved evenly put the hit late
    # and made a one-second fade read as 0.4 s: the first FlameArc animatics, 2026-11-12)
    el["scale"] = closed([[us[k], [round(v * math.sqrt(max(light[k], 0.0004)), 4) for v in full]] for k in range(count + 1)])
    return el


def preset_of(set_name, rows, view_name, view, duration, hue, gains=None, angles=None):
    """the blocking preset (version 3). gains: {beat index: size correction} measured back from a recording (a card's:
    a solid's size is the chart's own); angles: the other views a plan with solid beats is to be looked at from"""
    gains = gains or {}
    rows = [r for r in rows if not r.get("problem")]
    layers = [layer_of(r, view, hue, 1.0 if r.get("solid") else gains.get(r["index"], 1.0)) for r in rows]
    # hit-stops: ON each beat's hit (never at 0: the player has none there); two beats that hit at one moment are ONE
    # stop there, the longer hold (the player honours only the first stop at a time)
    stops = {}
    for r in rows:
        if r["hold"] >= 0.02:
            step, _, n, _ = drawings_of(r)
            where = stop_on(r["t"], step, n, duration)
            stops[where] = max(stops.get(where, 0.0), round(min(r["hold"], 1.8), 3))
    made = {"version": 3, "mode": "burst", "duration": float(duration),
            "about": f"the timing animatic of {set_name}: its beats as flat shapes at the chart's timing (kit vfx animatic)",
            "booth": {"views": list(dict.fromkeys([view_name] + list(angles or [])))}, "layers": layers}
    if stops:
        made["hitstop"] = [{"at": a, "hold": stops[a]} for a in sorted(stops)]
    slow = sorted((r for r in rows if r["slow"] > 1.001), key=lambda r: r["t"])
    if slow:                                                # bullet time: the clock's speed over each slowed beat
        warp, last = [], -1.0
        for r in slow:
            a, b, rate = max(r["t"], last + 0.002), min(r["t"] + r["life"], float(duration)), max(0.05, min(1.0, 1.0 / r["slow"]))
            if b - a < 0.01:
                continue
            if a - 0.001 > last and a > 0.002:
                warp.append([round(a - 0.001, 4), 1.0])
            warp += [[round(a, 4), round(rate, 3)], [round(b, 4), round(rate, 3)]]
            last = b
            if b + 0.001 < float(duration):
                warp.append([round(b + 0.001, 4), 1.0])
                last = b + 0.001
        if len(warp) >= 2:
            made["timewarp"] = warp
    return made


# ------------------------------------------------------------------------------------------------ the reads
def scene_reads(found):
    """each beat's main shot of the scene, read as the dailies read it -> [{"shot", "timing", "share"} or None]"""
    clip, hue, cuts = found["scene_clip"], found["hue"], found["cuts"]
    si = DC.probe(clip) if clip else None
    reads = []
    for row in found["beats"]:
        sc = row.get("scene")
        shot = None
        if clip and isinstance(sc, list) and len(sc) == 2:
            got = DC.read_beat(clip, float(sc[0]), float(sc[1]), cuts, hue, si)
            shot = got["shots"][got["main"]] if got["main"] is not None else None
        t = shot and shot["timing"]
        if not t:
            reads.append(None)
            continue
        cover = np.asarray(shot["curves"]["cover"], dtype=np.float64)
        share = float(cover[t["hit"]:t["hit"] + max(1, t["stay"])].max())
        reads.append({"shot": shot, "timing": t, "share": share, "info": si})
    return reads


def our_reads(recording, rows, hue, preset=None, layers=None):
    """a recording read back, beat by beat -> (whole read or None, its probe, [per beat], the recording's clock).
    preset: the preset AS PLAYED (its hit-stops and slow motion decide which frame shows which moment).
    layers: [{"at", "step"}], one a row, when the recording is the ANIMATIC's own: where a beat starts, and where
    its hit is first shown, are then EXACT - the player's own sums on the recorder's own clock (first_shown).
    Without them (a built effect: nothing is known of its layers) a beat starts, and its plan's hit is, in the first
    frame whose clock has reached that time.
    A beat's stretch runs from its first frame to two frames before the next beat's first: three frames at least,
    and NEVER into the next beat (a small beat was read through the big one after it).
    Per beat: None when its stretch never lights up; {"unread": why, "planned"} when nothing can be read of it, and
    nothing is claimed - "short": it has under three frames of its own, or its hit drawing is first shown only after
    the next beat has started; "mixed" (the animatic's own recording, where the layers are known): another beat's
    shape is still lit, by the plan, between this beat's start and its hit - the light there is not this beat's
    alone; else
      frame, hit  where its light ARRIVES - the first frame of its stretch at most (0.7) of the light the stretch
                  reaches, over the timing read's own floor (one rule for every recording) - and that in seconds.
                  (The timing read times the run that holds the stretch's brightest frame: when the NEXT beat's
                  light came a little early that was the stretch's last frame, and this beat read thirteen late)
      planned     the frame its plan's hit is first shown in
      arrive      the frames from its first light to there;  rising: it is still growing when its stretch ends
      share       the share of the frame it covers at its most, while it stays
      opens       its stretch OPENS on light that was already at most of the beat's own strength in the frame
                  before, and that did not rise by a quarter when the stretch began: the arrival is not in the
                  stretch - it came earlier, or it is the light of the beat before
      early       ... and for how many frames before the stretch it had been that strong without a break
      since       ... True when that run goes all the way back to where the beat before starts (it never went out)
      unplanned   (the animatic's own recording) it opens on light the plan does not have there: no other beat is
                  that strong in the frame before, by the plan"""
    oi = DC.probe(recording)
    times = DC.frame_times(preset, oi[0])
    clock = DC.clock_of(preset, oi[0])
    whole = DC.read(recording, 0.0, oi[1], hue, oi)
    light = dense.energy(whole["curves"]) if whole else None
    frames = int(whole["frames"]) if whole else 0
    starts, hits = [], []
    for k, r in enumerate(rows):
        if layers:
            _, _, n, _ = drawings_of(r)
            starts.append(first_shown(times, layers[k]["at"], layers[k]["step"]))
            hits.append(first_shown(times, layers[k]["at"], layers[k]["step"], n, r["life"]))
        else:
            starts.append(int(round(clock(at(r)) * oi[0])))
            hits.append(int(round(clock(float(r["hit"])) * oi[0])))

    def lit(j, f):
        """is row j's shape lit in frame f, by the plan? (alive, and not yet on its last drawing: the one it is gone on)"""
        if not 0 <= f < len(times):
            return False
        age = times[f] - layers[j]["at"]
        return age >= 0 and age / rows[j]["life"] <= 1 and math.floor(age * layers[j]["step"]) < drawings_of(rows[j])[1]

    def planned(j, f):
        """the share of the frame row j's shape covers in frame f, by the plan (0 when it is not lit)"""
        if not lit(j, f):
            return 0.0
        return rows[j]["share"] * light_of(rows[j])[int(math.floor((times[f] - layers[j]["at"]) * layers[j]["step"]))]

    got = []
    for k, r in enumerate(rows):
        later = [f for f in starts if f > starts[k]]
        nxt = min(later) if later else frames
        if not whole or starts[k] >= frames:
            got.append(None)
            continue
        last = min(frames - 1, max(nxt - 2, starts[k] + 2) if later else frames - 1)
        if layers and hits[k] >= len(times):
            got.append({"unread": "never", "planned": hits[k]})     # (no frame shows its hit drawing: a fault, not a limit)
            continue
        if nxt - starts[k] < 3 or hits[k] > last:
            got.append({"unread": "short", "planned": hits[k]})
            continue
        if layers and any(j != k and starts[j] <= starts[k] and any(lit(j, f) for f in range(starts[k], hits[k] + 1))
                          for j in range(len(rows))):
            got.append({"unread": "mixed", "planned": hits[k]})
            continue
        shot = DC.within(whole, starts[k] / oi[0], last / oi[0])
        t = shot and shot["timing"]
        if not t:
            got.append(None)
            continue
        # (a stretch's read keeps the WHOLE recording's curves, and its timing counts in the recording's frames)
        cover = np.asarray(shot["curves"]["cover"], dtype=np.float64)
        first, last = shot["stretch"]
        rise = t["peak"] - t["base"]
        started, most = t["base"] + dense.ONSET * rise, t["base"] + dense.MOST * rise
        hit = next((i for i in range(first, last + 1) if light[i] >= most), t["hit"])
        stay = 1
        while hit + stay <= last and light[hit + stay] >= most:
            stay += 1
        begun = hit
        while begun > first and light[begun - 1] >= started:
            begun -= 1
        before = [f for f in starts if f < starts[k]]
        lowest = min(first, max(before) + 1) if before else 0
        back = first
        # (a beat that starts with a JUMP over the light of the one before has an arrival, however bright that light
        # was: the FlameArc arc comes in on the last of the ignition's going - 0.26 of the frame's light, 0.38 with
        # the arc - and was called "no arrival to read")
        if hit == first and first > 0 and light[first - 1] >= most and light[first] < 1.25 * light[first - 1]:
            while back > lowest and light[back - 1] >= most:
                back -= 1
        got.append({"frame": hit, "hit": round(hit / oi[0], 3), "planned": hits[k], "arrive": hit - begun,
                    "share": round(float(cover[hit:hit + stay].max()), 4),
                    "rising": hit + stay - 1 >= last and float(light[last]) > 1.1 * float(light[hit]), "shot": shot,
                    "opens": back < first, "early": first - back, "since": bool(before) and back < first and back == lowest,
                    # (the animatic's own recording: light at the beat's strength before it starts, where the PLAN
                    # has no other beat that strong - it can only be this beat, early: the recording is not the
                    # plan's. The plan's shares are turned into this read's light by the beat's own: peak / share)
                    "unplanned": bool(layers) and back < first and max(
                        [planned(j, first - 1) for j in range(len(rows)) if j != k] or [0.0]) * t["peak"] / max(r["share"], 1e-6)
                    < 0.85 * most})
    return whole, oi, got, clock


def stamp(path):
    """what tells one file on disk from another made later under its name: its size and its time (in nanoseconds)"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def recorded_path(set_name):
    return os.path.join(OUT, f"{set_name}.recorded.json")


def mark_recorded(set_name, view_name, plan, gains, recording):
    """what a recording is OF, written the moment it is made: the plan's id, the size corrections it was made with,
    and the recording's own stamp. --no-record takes a recording only when this says it is the current plan's (a
    review, 2026-11-12: a chart re-timed after its recording got a new record over the OLD video)"""
    os.makedirs(OUT, exist_ok=True)
    DC.dump({"id": plan, "view": view_name, "gains": {str(k): v for k, v in (gains or {}).items()},
             "recording": stamp(recording)}, recorded_path(set_name))


def record(set_name, view_name, fps, port):
    import autorec
    return autorec.record(set_name, view_name, fps, port, 900, extra=["--animatic"], name=f"{set_name}_animatic")


# ------------------------------------------------------------------------------------------------ the video
def fit(frame, w, h):
    im = Image.fromarray(frame).convert("RGB")
    im.thumbnail((w, h))
    canvas = Image.new("RGB", (w, h), (12, 13, 16))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def curve_strip(scene, ours, tau, lo, hi, width):
    """the two light curves over a beat's window (seconds from the hit), a cursor at `tau`"""
    im = Image.new("RGB", (width, STRIP_H), (18, 20, 24))
    d = ImageDraw.Draw(im)
    x_of = lambda s: int(round((s - lo) / max(hi - lo, 1e-6) * (width - 1)))  # noqa: E731
    d.line([(x_of(0.0), 0), (x_of(0.0), STRIP_H)], fill=(70, 74, 82), width=1)
    for side, colour in ((scene, P.SCENE), (ours, P.OURS)):
        if not side:
            continue
        top = float(side["energy"].max()) or 1.0
        pts = [(x_of(float(s)), int(round(STRIP_H - 12 - (STRIP_H - 30) * float(e) / top)))
               for s, e in zip(side["seconds"], side["energy"]) if lo <= s <= hi]
        if len(pts) >= 2:
            d.line(pts, fill=colour, width=3)
    x = x_of(tau)
    d.line([(x, 0), (x, STRIP_H)], fill=(240, 240, 245), width=2)
    return im


def side_video(dest, set_name, rows, scene, ours, whole, oi, recording, clock):
    """the scene's beats beside the animatic's, in motion: each pair laid on its hit; then the animatic alone ->
    whether the video was written. ffmpeg is never left running: a pipe that breaks or a wait that runs out ends it,
    and the error is the caller's to say"""
    w, h = SIDE_W * 2, 44 + SIDE_H + STRIP_H
    pipe = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r",
                             str(SIDE_FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt",
                             "yuv420p", "-movflags", "+faststart", dest], stdin=subprocess.PIPE)
    try:
        side_frames(pipe, w, h, set_name, rows, scene, ours, oi, recording, clock)
        pipe.stdin.close()
        pipe.wait(timeout=600)
    except BaseException:
        pipe.kill()
        pipe.wait()
        raise
    return pipe.returncode == 0 and os.path.isfile(dest)


def side_frames(pipe, w, h, set_name, rows, scene, ours, oi, recording, clock):
    """every frame of the side-by-side video, written to ffmpeg's pipe"""
    font, small = P._font(22), P._font(16)
    dark = np.zeros((SIDE_H, SIDE_W, 3), dtype=np.uint8)
    last = max(0, int(round(oi[1] * oi[0])) - 1)

    def window(clip, start, end, info, lo, hi):
        """frames lo..hi of a clip's window, large - only those (a long shot is hundreds of large frames)"""
        lo, hi = max(0, lo), max(0, hi)
        got = DC.frames(clip, start, end, SIDE_W, info, lo, hi) if hi >= lo else dark[None][:0]
        return lambda j: got[j - lo] if lo <= j < lo + len(got) else dark

    def write(left, right, title, strip, sub=""):
        page = Image.new("RGB", (w, h), (12, 13, 16))
        d = ImageDraw.Draw(page)
        d.text((12, 8), title, font=font, fill=(240, 240, 245))
        if sub:
            d.text((w - 12 - d.textlength(sub, font=small), 14), sub, font=small, fill=(150, 154, 162))
        if left is None:                                    # the animatic alone, in the middle
            page.paste(fit(right, SIDE_W, SIDE_H), (SIDE_W // 2, 44))
            d.text((SIDE_W // 2 + 10, 48), "THE ANIMATIC", font=small, fill=P.OURS)
        else:
            page.paste(fit(left, SIDE_W, SIDE_H), (0, 44))
            page.paste(fit(right, SIDE_W, SIDE_H), (SIDE_W, 44))
            for x, text, colour in ((6, "THE SCENE", P.SCENE), (SIDE_W + 6, "THE ANIMATIC", P.OURS)):
                d.rectangle([x, 46, x + 14 + d.textlength(text, font=small), 70], fill=(12, 13, 16))
                d.text((x + 6, 49), text, font=small, fill=colour)
            if left is dark:
                d.text((SIDE_W // 2 - 150, 44 + SIDE_H // 2 - 10), "(the scene's shot is over here: a cut)", font=small,
                       fill=(120, 124, 132))
        if strip is not None:
            page.paste(strip, (0, 44 + SIDE_H))
        pipe.stdin.write(np.asarray(page, dtype=np.uint8).tobytes())

    def beats_strip(now):
        """the whole clock as a bar: every beat a block where the RECORDING has it, a cursor at `now` seconds"""
        im = Image.new("RGB", (w, STRIP_H), (18, 20, 24))
        d = ImageDraw.Draw(im)
        x_of = lambda s: 20 + int(round(s / max(oi[1], 1e-6) * (w - 40)))  # noqa: E731
        for r in rows:
            a, b = clock(r["t"]), clock(r["t"] + r["life"])
            d.rectangle([x_of(a), 46, max(x_of(a) + 2, x_of(b) - 2), 96], fill=(255, 246, 228) if r["key"] else (214, 120, 40))
            d.text((x_of(a) + 2, 24), r["beat"][:26], font=small, fill=(200, 204, 212))
            if r["hold"] >= 0.02:
                d.text((x_of(clock(r["hit"])), 102), f"hold {r['hold']:.2f} s", font=small, fill=(150, 154, 162))
        d.line([(x_of(now), 14), (x_of(now), STRIP_H - 8)], fill=(240, 240, 245), width=2)
        return im

    for k, r in enumerate(rows):
        s, o = scene[k], ours[k]
        if not o:
            continue
        ot, oshot = o["shot"]["timing"], o["shot"]
        st = s["timing"] if s else None
        # from half a second before the hit to a little after THIS beat is over on the animatic's clock (its hold
        # too): the scene's side shows what the scene does in that same time - later the animatic is on its next beat
        lead = 0.5
        tail = min(4.0, r["life"] - r["arrive"] + r["hold"] + 0.08)
        scene_at = None
        if s:
            f = s["shot"]["fps"]
            scene_at = window(s["info_clip"], s["shot"]["from"], s["shot"]["to"], s["info"],
                              st["hit"] - int(lead * f) - 1, st["hit"] + int(tail * f) + 1)
        ours_at = window(recording, 0.0, oi[1], oi, ot["hit"] - int(lead * oi[0]) - 1, min(last, ot["hit"] + int(tail * oi[0]) + 1))
        sc, oc = dailies.curve_side(s["shot"], "the scene") if s else None, dailies.curve_side(oshot, "ours")
        title = f"beat {r['beat']}" + ("   (the key beat)" if r["key"] else "")
        steps = int(round((lead + tail) * SIDE_FPS))
        for i in range(steps):
            tau = -lead + i / SIDE_FPS
            left = scene_at(st["hit"] + int(round(tau * s["shot"]["fps"]))) if scene_at else dark
            right = ours_at(ot["hit"] + int(round(tau * oi[0])))
            write(left, right, title, curve_strip(sc, oc, tau, -lead, tail, w), f"{tau:+.2f} s from the hit")
    # the animatic alone, on its own clock: the rhythm of the whole (read two seconds at a time)
    chunk, ours_at, upto = int(2 * oi[0]), None, -1
    for i in range(int(round(oi[1] * SIDE_FPS))):
        j = int(round(i / SIDE_FPS * oi[0]))
        if j > last:
            break
        if j > upto:
            ours_at, upto = window(recording, 0.0, oi[1], oi, j, min(last, j + chunk - 1)), j + chunk - 1
        write(None, ours_at(j), f"{set_name}: the whole animatic at its own speed", beats_strip(i / SIDE_FPS), f"{i / SIDE_FPS:.2f} s")


# ------------------------------------------------------------------------------------------------ check, drift
def hash_of(paths, more=None):
    """a hash of the files as they are on disk now - and of `more`, what the record says about them - or None when
    a file is not there"""
    h = hashlib.sha1()
    for p in paths:
        try:
            h.update(open(p, "rb").read())
        except OSError:
            return None
    if more is not None:
        h.update(json.dumps(more, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:12] if paths else None


def kept(read):
    """what a scene read gives the plan, as numbers a record keeps (so a check needs no clip)"""
    if not read:
        return None
    t = read["timing"]
    return {"share": round(float(read["share"]), 4),
            "timing": {"cut_in": t["cut_in"], "stay_cut": t["stay_cut"], "cut_away": t["cut_away"], "on": t["on"],
                       "peak": t["peak"], "seconds": {"arrive": t["seconds"]["arrive"], "go": t["seconds"]["go"]}}}


def record_of(set_name):
    try:
        made = json.load(open(os.path.join(OUT, f"{set_name}.plan.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return made if isinstance(made, dict) else None


def state_of(found, made):
    """the animatic on this machine against the chart, the scene and the files as they are NOW (no clip is read: the
    scene's numbers are the ones its record keeps) -> (the plan's id now, the hash now of what he is shown or None,
    [why it is not that plan's animatic any more]). "What he is shown" is the video, the pages AND the whole record
    beside them - its beats, its clock, its frame rate, everything --drift holds an effect to: a number changed
    anywhere in the record is a changed animatic"""
    duration = duration_of(found)
    view_name = str(made.get("view") or "hero")
    shown = [str(p) for p in made["shown"]] if isinstance(made.get("shown"), list) else []
    drawn = hash_of(shown, {k: v for k, v in made.items() if k != "drawn"})
    try:
        now_rows = plan_rows(found["beats"], made.get("scene") or [], duration)
        was_asked = list(made.get("angles_asked") or []) or None   # (the very list the run was asked: with the filmed view in it, or twice the same)
        _, _, now_angles = block_solids(now_rows, view_name, view_of(view_name), was_asked)
        now_id = plan_id(found["set"], now_rows, view_name, duration, found["hue"], source_of(found), view_of(view_name), now_angles)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, drawn, ["its record on this machine cannot be read (made by another version of the tool)"]
    why = []
    if made.get("id") != now_id:
        why.append("the chart was re-timed, pointed at another part of the scene, or the set's colours or the camera "
                   "changed since it was made")
    if drawn and made.get("drawn") != drawn:
        why.append("the video, a page or a number of its record is not the one its record was written for")
    if made.get("preset") and hash_of([os.path.join(OUT, f"{found['set']}.json")]) != made["preset"]:
        why.append("its preset (what the player shows with --animatic) is not the one it was made from")
    # (a recording that is merely gone changes nothing he was shown; one made AGAIN is another recording)
    now = stamp(str(made.get("recording") or ""))
    if now is not None and made.get("recording_stamp") != now:
        why.append("it was recorded again since it was made")
    return now_id, drawn, why


def check(found, asked=None):
    """--check: nothing is made. "drawn" is read from the files he is shown, not from the record. asked: the view
    the caller named, if it named one (the animatic of a set is of ONE view)"""
    answer = {"exists": False, "id": None, "drawn": None, "stale": False, "why": "", "problems": [], "shown": [], "png": None}
    bad = unsound(found)
    if bad:
        answer["problems"].append(bad)
        print(json.dumps(answer))
        return 0
    made = record_of(found["set"])
    if made and asked and str(made.get("view") or "hero") != asked:
        answer["problems"].append(f"the animatic on this machine is of the view {made.get('view') or 'hero'}, not {asked}")
        made = None
    if made:
        answer["id"], drawn, why = state_of(found, made)
        if drawn:
            shown = [str(p) for p in made["shown"]]
            answer.update(exists=True, drawn=drawn, shown=shown, stale=bool(why), why="; ".join(why),
                          problems=list(made.get("problems") or []), png=next((p for p in shown if p.endswith(".png")), None))
    print(json.dumps(answer))
    return 0


def is_owner(rec):
    """kit/lib/locks.luau Locks.isOwner, rule for rule: a record counts only when it is the owner's. (Trimmed as
    Lua's %s trims - the six ASCII blanks, nothing else: a no-break space before "owner" is not the owner's)"""
    if not isinstance(rec, dict):
        return False
    who = rec.get("who")
    if who is not None and (not isinstance(who, str) or who.lower() != "owner"):
        return False
    by = rec.get("by") if rec.get("by") is not None else who
    return isinstance(by, str) and by.strip(" \t\n\v\f\r").lower()[:5] == "owner"


def approval_of(set_name, made):
    """the owner's own record of this animatic (board/locks.json, as kit approve writes it): "approved" when it is
    for this plan and these files (kit/lib/lanelocks.luau LaneLocks.holds), "earlier" when he approved one that was
    made again since, else "none". It words the summary only: what passes and fails never depends on it"""
    try:
        data = json.load(open(os.path.join("board", "locks.json"), encoding="utf-8"))
        rec = data["stages"]["vfx"][set_name]["animatic"]
    except (OSError, ValueError, KeyError, TypeError):
        return "none"
    if not is_owner(rec):
        return "none"
    return "approved" if rec.get("id") == made.get("id") and rec.get("drawn") == made.get("drawn") else "earlier"


def drift(found, effect, effects, view_name):
    """the built effect's recording against the animatic's plan, beat by beat"""
    set_name = found["set"]
    made = record_of(set_name)
    if not made:
        return out("fail", f"animatic {set_name}: no animatic yet to hold {effect} against", f"lune run kit vfx animatic {set_name}")
    _, drawn, why = state_of(found, made)
    if why or not drawn:
        return out("fail", f"animatic {set_name}: its animatic on this machine is out of date ({'; '.join(why) or 'a file of it is missing'}): "
                   f"nothing to hold {effect} against", f"lune run kit vfx animatic {set_name}, have the owner look at it, then again")
    if made.get("problems"):
        return out("fail", f"animatic {set_name}: its animatic failed its own check ({str(made['problems'][0])[:140]}): "
                   f"nothing to hold {effect} against", f"lune run kit vfx animatic {set_name} (fix what it names first)")
    mine_view = str(made.get("view") or "hero")
    if view_name and view_name != mine_view:
        return out("fail", f"animatic {set_name} --drift: the animatic here is of the view {mine_view}, not {view_name}",
                   f"lune run kit vfx animatic {set_name} --drift {effect} --view {mine_view}")
    piece = DC.piece(effect, effects, mine_view, None)
    if isinstance(piece, str):
        return out("fail", f"animatic {set_name} --drift: {piece}", "name an existing preset built from this set")
    if piece["set"] != set_name:
        return out("fail", f"animatic {set_name} --drift: {effect} is built from the set {piece['set'] or '(none)'}, not from "
                   f"{set_name}", f"lune run kit vfx animatic {piece['set'] or '<its set>'} --drift {effect}")
    if not os.path.isfile(piece["recording"]):
        return out("fail", f"animatic {set_name} --drift: no recording {piece['recording'].replace(os.sep, '/')}",
                   f"lune run kit vfx play {effect} --record --views {piece['view']}")
    if os.path.getmtime(piece["preset_path"]) > os.path.getmtime(piece["recording"]) + 1.0:
        return out("fail", f"animatic {set_name} --drift: {effect}'s preset was edited after its recording was made",
                   f"lune run kit vfx play {effect} --record --views {piece['view']}")
    said = {"approved": "its approved motion", "earlier": "its animatic (the owner approved an EARLIER one: not this)",
            "none": "its animatic (which the owner has not approved yet)"}[approval_of(set_name, made)]
    rows = made.get("beats") or []                          # (state_of's "drawn" is of the whole record: not edited since)
    # each recording runs on its own clock, at its own frame rate - the effect's is its preset AS PLAYED
    _, oi, got, _ = our_reads(piece["recording"], rows, found["hue"], piece["played"])
    late, lines, unseen, reasons, small = [], [], [], set(), []
    for r, g in zip(rows, got):
        measured = r.get("measured") if isinstance(r.get("measured"), dict) else {}
        blank = {"beat": r["beat"], "plan": r["hit"], "from_plan": None, "off": None}
        step, _, n, _ = drawings_of(r)
        allowed = 1.0 / step + 0.25 / oi[0]
        if measured.get("unseen"):
            # the ANIMATIC itself cannot say when this beat arrives: nothing is held to it, and that is said
            unseen.append(str(r["beat"]))
            reasons.add({"opens": "the animatic's own light is already on when they start",
                         "mixed": "another beat's shape is still lit when they hit"}.get(
                             measured["unseen"], "they have under three frames of their own before the next beat"))
            lines.append(blank)
            continue
        if not g:
            lines.append(blank)
            late.append(f"beat {r['beat']}: the effect never lights up in its stretch of the recording")
            continue
        if g.get("unread"):
            # the animatic had room for this beat, the effect's own clock leaves it none: the two clocks differ
            lines.append(blank)
            late.append(f"beat {r['beat']}: on the effect's own clock it has under three frames before the next beat, where "
                        f"the animatic's clock gives it room - a hit-stop or slow motion of the chart is not in the effect")
            continue
        if g["share"] < 0.5 * float(r.get("share") or 0.0):
            small.append(f"beat {r['beat']} covers {g['share']:.2f} of the frame, the plan {float(r['share']):.2f}")
        if g["opens"] and g["since"]:
            # at this beat's own strength from its first frame, and so all the way back to the beat before: nothing
            # ARRIVES in this beat. By its light alone two faults look the same, so both are named. (Also when the
            # plan's own gap is a single drawing and the effect closes it by a frame: the light does not go down where
            # the animatic's does. Letting that through let a beat four frames early through with it.)
            lines.append(blank)
            late.append(f"beat {r['beat']}: no light of its own arrives - what is lit when it starts has been on since the "
                        f"beat before: the beat before never goes out, or this one comes early by the whole gap between "
                        f"them (in the animatic the light goes down first)")
            continue
        # how far the effect's light is from where the PLAN has it, on the effect's own clock (the first frame whose
        # clock has reached the plan's hit). The animatic's own light is IN the frame its plan has it in - an animatic
        # that is not has failed its own check, and nothing is held to it
        off = (g["frame"] - g["planned"]) / oi[0]
        if g["opens"]:
            # the effect's light is at the beat's strength BEFORE the beat's stretch, the animatic's was not: it came
            # early, by the frames it had been on (read inside the stretch alone it is "there from the first frame",
            # which is what on time looks like)
            off -= g["early"] / oi[0]
        # what is allowed (above): ONE drawing of the beat as it is drawn, and a quarter frame for the sampling.
        # Nothing more for a light that takes its time: an allowance from the effect's own slow start let a small
        # spark at the beat's start buy a snap three frames late (a review, 2026-11-12)
        frames = int(round(abs(off) * oi[0]))
        lines.append({"beat": r["beat"], "plan": r["hit"], "from_plan": round(off, 3), "off": round(off, 3),
                      "allowed": round(allowed, 3)})
        if abs(off) > allowed:
            # (still growing in its stretch's last frame: the light had not finished arriving when the beat ended)
            least = " at least (it is still rising when the beat ends)" if off > 0 and g["rising"] else ""
            grows = f"; it grows over {g['arrive']} frame(s)" if off > 0 and g["arrive"] > 1 else ""
            late.append(f"beat {r['beat']}: the effect's light arrives {abs(off):.2f} s ({frames} of its frames){least} "
                        f"{'after' if off > 0 else 'before'} the animatic's (the plan has it at {float(r['hit']):.2f} s of the "
                        f"effect's clock{grows})")
    more = ""
    if unseen:
        more += f"; {len(unseen)} beat(s) could not be held to it - {' / '.join(sorted(reasons))}: {', '.join(unseen)}"
    if small:
        more += (f"; {len(small)} beat(s) far smaller than planned (only the timing is held here - the look is the style "
                 f"sheet's): {'; '.join(small)}")
    if DC.caution(piece):
        more += "; " + DC.caution(piece)
    if late:
        return out("fail", f"animatic {set_name}: {effect} drifts from {said} - {'; '.join(late)}{more}",
                   f"move the beat's layers to the animatic's time (or re-time the chart and have the motion approved again), "
                   f"then lune run kit vfx play {effect} --record", beats=lines, drifts=late, unseen=unseen, small=small)
    judged = len(lines) - len(unseen)
    if judged == 0:
        return out("fail", f"animatic {set_name}: no beat of {effect} could be held to {said}{more}",
                   "the animatic's beats run into each other: give the chart beats whose light goes out before the next "
                   "one, or judge the motion by eye (lune run kit vfx dailies)", beats=lines, drifts=[], unseen=unseen,
                   small=small)
    return out("pass", f"animatic {set_name}: {effect} hits where {said} does ({judged} beat(s), each within one drawing "
               f"of it){more}", "none", beats=lines, drifts=[], unseen=unseen, small=small)


# ------------------------------------------------------------------------------------------------ the whole run
def make(found, view_name, fps, port, recorded, asked=None):
    set_name = found["set"]
    view = view_of(view_name)
    if not view:
        return out("fail", f"animatic {set_name}: no camera view '{view_name}' in kit/vfx/views.json", "name one of its views")
    duration = duration_of(found)
    if duration <= 0:
        return out("fail", f"animatic {set_name}: the chart has no duration", f"lune run kit vfx chart {set_name}")
    scene = scene_reads(found)
    rows = plan_rows(found["beats"], scene, duration)
    unshown = [r["problem"] for r in rows if r.get("problem")]
    if unshown:
        return out("fail", f"animatic {set_name}: the chart cannot be shown - {'; '.join(unshown)}",
                   f"fix the chart's times ({found['measured'].replace(os.sep, '/')}/{set_name}.chart.json), then again")
    # SOLID beats are worked out from the animatic's own view and every gameplay angle asked, BEFORE anything is made:
    # one that an angle cannot show (outside the picture, a speck, hidden behind another) stops the run in words
    seen_from, hidden, angle_names = block_solids(rows, view_name, view, asked)
    if hidden:
        return out("fail", f"animatic {set_name}: the chart's solid beats cannot be shown - {'; '.join(hidden)}",
                   f"change the beat's \"solid\" in the chart ({found['measured'].replace(os.sep, '/')}/{set_name}.chart.json), or name other --angles")
    source = source_of(found)
    plan = plan_id(set_name, rows, view_name, duration, found["hue"], source, view, angle_names)
    os.makedirs(OUT, exist_ok=True)
    preset_path, record_path = os.path.join(OUT, f"{set_name}.json"), os.path.join(OUT, f"{set_name}.plan.json")
    video = os.path.join(OUT, f"{set_name}_side.mp4")
    recording = os.path.join(DC.BOOTH, f"{set_name}_animatic_play_{view_name}.mp4")
    # NOTHING of the animatic that is here is touched until this run has a recording of its own plan to read: a
    # --no-record that is refused (another view, a re-timed chart) left a set without the animatic he had approved
    # (a review, 2026-11-12). What is here stays - and reads out of date when the chart is another one
    gains = {}
    if recorded:
        # --no-record: the recording that is here is taken only when it IS this plan's, as its own mark says
        if not os.path.isfile(recording):
            return out("fail", f"animatic {set_name}: no recording {recording.replace(os.sep, '/')}",
                       f"lune run kit vfx animatic {set_name} (without --no-record)")
        try:
            was = json.load(open(recorded_path(set_name), encoding="utf-8"))
            gains = {int(k): float(v) for k, v in (was.get("gains") or {}).items()}
        except (OSError, ValueError, TypeError, AttributeError):
            was = None
        why = ("no recording of it was made by this tool" if not isinstance(was, dict) else
               "the chart or the scene's read changed since it was recorded" if was.get("id") != plan else
               "it was recorded for another view" if was.get("view") != view_name else
               "the recording was replaced since" if was.get("recording") != stamp(recording) else "")
        if why:
            return out("fail", f"animatic {set_name}: the recording on this machine is not of this plan ({why})",
                       f"lune run kit vfx animatic {set_name} (without --no-record: it records it again)")
    blocking, ours, whole, oi, clock, problems = None, [], None, None, None, []
    for attempt in range(3):
        blocking = preset_of(set_name, rows, view_name, view, duration, found["hue"], gains, angle_names)
        # checked under another name first: a preset the kit's rules refuse never replaces the one that is here
        # (before a browser is started, and with --no-record too)
        try:
            DC.dump(blocking, preset_path + ".new")
            wrong = refused(preset_path + ".new")
        except BaseException:
            if os.path.isfile(preset_path + ".new"):
                os.remove(preset_path + ".new")
            raise
        if wrong:
            os.remove(preset_path + ".new")
            return out("fail", f"animatic {set_name}: the plan makes a preset the player refuses - {'; '.join(wrong[:3])}",
                       "a beat of this chart is outside what the plan's rules cover: say which on the board (kit lane) - "
                       "kit/vfx/animatic.py plan_rows / layer_of")
        os.replace(preset_path + ".new", preset_path)
        if not recorded:
            got = record(set_name, view_name, fps, port)
            if not got.get("ok"):
                why = " ".join(str(got.get("why")).split())[-240:]
                return out("fail", f"animatic {set_name}: the player did not record it ({why})",
                           f"lune run kit vfx play {set_name} --animatic (look at it in the player), then again")
            mark_recorded(set_name, view_name, plan, gains, recording)
        if not os.path.isfile(recording):
            return out("fail", f"animatic {set_name}: no recording {recording.replace(os.sep, '/')}",
                       f"lune run kit vfx animatic {set_name} (without --no-record)")
        whole, oi, ours, clock = our_reads(recording, rows, found["hue"], blocking, blocking["layers"])
        # the shares measured back: a shape that came out a different size than the scene's is sized again, once or twice
        # (a share far from the target is not a size error: a shape cut by the frame, a colour the read does not see)
        # (a SOLID is the size its chart says: it is never sized again from a recording)
        off = {r["index"]: math.sqrt(r["share"] / o["share"]) for r, o in zip(rows, ours)
               if not r.get("solid") and o and not o.get("unread") and not o["opens"] and o["frame"] == o["planned"] and r["share"] > 0
               and 0.5 <= o["share"] / r["share"] <= 2.0 and not 0.88 <= o["share"] / r["share"] <= 1.14}
        if recorded or not off or attempt == 2:
            break
        for k, v in off.items():                            # (never far from the size the camera's geometry gave)
            gains[k] = round(max(0.7, min(1.4, gains.get(k, 1.0) * v)), 4)
    # from here until its new record is written there is NO animatic: the pages and the video are made again
    for old in (record_path, video):
        if os.path.isfile(old):
            os.remove(old)
    if ours and all(o is None or o.get("unread") or o["opens"] for o in ours) and any(o and not o.get("unread") == "never" for o in ours):
        problems.append("not one beat of it could be read back (they run into each other): the check has checked nothing")
    for r, o in zip(rows, ours):
        if not o:
            problems.append(f"beat {r['beat']}: the animatic never lights up in its stretch of the recording")
            continue
        if o.get("unread") == "never":
            problems.append(f"beat {r['beat']}: no frame of the recording shows its hit drawing (a drawing shorter than a "
                            f"frame at this frame rate)")
            continue
        if o.get("unread"):
            r["measured"] = {"hit": None, "frame": None, "planned": o["planned"], "share": None, "unseen": o["unread"]}
            r["notes"].append(("in the animatic's own recording this beat has under three frames of its own before the "
                               "next beat starts (or its hit shows only after it)" if o["unread"] == "short" else
                               "in the animatic's own recording another beat's shape is still lit when this one hits")
                              + ": nothing of it can be read back, and --drift cannot hold a built effect to it")
            continue
        r["measured"] = {"hit": o["hit"], "frame": o["frame"], "planned": o["planned"], "share": o["share"],
                         "unseen": "opens" if o["opens"] else None}
        if o["unplanned"]:
            problems.append(f"beat {r['beat']}: light as strong as its own is on {o['early']} frame(s) before it starts, "
                            f"where its plan has no beat that strong - the recording is not this plan's")
            continue
        if o["opens"]:
            r["notes"].append("in the animatic's own recording this beat opens on light that is already as strong as its "
                              "own (the beat before): when it arrives cannot be read back, and --drift cannot hold a "
                              "built effect to it")
            continue                                        # (nothing of it to check: its arrival is not in its stretch)
        # where the plan's hit drawing is first SHOWN (the player's own sums on the recorder's own clock): the light
        # must be read as arriving in that very frame (the read is exact on what the player draws: a frame off is a
        # recording that is not this plan's)
        if o["frame"] != o["planned"]:
            problems.append(f"beat {r['beat']}: the animatic's light arrives in frame {o['frame']} of its recording "
                            f"({o['hit']:.2f} s), its plan shows the hit in frame {o['planned']}")
        if not 0.5 <= o["share"] / max(r["share"], 1e-6) <= 2.0:
            problems.append(f"beat {r['beat']}: the read sees {o['share']:.0%} of the frame where the shape should cover "
                            f"{r['share']:.0%} (a colour outside the set's band as the player shows it, or a shape the "
                            f"frame cuts)")
    # the beat pages: the scene's frames above the animatic's (the dailies' own pages and words)
    look = os.path.join(dailies.OUT, f"{set_name}_animatic")
    pages = dict(found, name=set_name, view=view_name, run=f"{set_name}_animatic", recording=recording, preset=blocking)
    quiet, said = sys.stdout, None
    try:
        from io import StringIO
        sys.stdout = StringIO()
        dailies.of(set_name, pages, {"--tile": "640"}, f"lune run kit vfx animatic {set_name}")
        said = sys.stdout.getvalue().strip().splitlines()[-1]
    except Exception as e:  # noqa: BLE001  (a page that could not be drawn is said, never swallowed)
        said = json.dumps({"status": "fail", "summary": f"{type(e).__name__}: {e}"})
    finally:
        sys.stdout = quiet
    try:
        paged = json.loads(said) if said else {}
    except ValueError:
        paged = {}
    if paged.get("status") != "pass":
        problems.append(f"the beat pages were not made ({str(paged.get('summary') or 'no answer')[:160]})")
    for s in scene:                                         # (what the video needs of each side)
        if s:
            s["info_clip"] = found["scene_clip"]
    try:
        filmed = side_video(video, set_name, rows, scene, [o if o and not o.get("unread") else None for o in ours], whole, oi,
                            recording, clock)
    except Exception as e:  # noqa: BLE001  (ffmpeg's pipe can break mid-write: said, and there is then no video)
        filmed = False
        problems.append(f"the side-by-side video could not be written ({type(e).__name__}: {str(e)[:120]})")
        if os.path.isfile(video):
            os.remove(video)
    if not filmed and not any("side-by-side" in p for p in problems):
        problems.append("the side-by-side video could not be written (ffmpeg)")
    solid_shown = []
    if angle_names:   # the solids drawn from every angle: part of what he is shown (the film shows no volume)
        solid_shown, drew = draw_solids(set_name, rows, view_name, view, angle_names, duration, found["hue"])
        problems.extend(drew)
    shown = ([video.replace(os.sep, "/")] if os.path.isfile(video) else []) + solid_shown + sorted(
        (os.path.join(look, f).replace(os.sep, "/") for f in (os.listdir(look) if os.path.isdir(look) else [])
         if re.fullmatch(r"beat\d+_page\.png", f)), key=lambda p: int(re.search(r"beat(\d+)_page", p).group(1)))
    differences = {b.get("index"): b.get("differences") or [] for b in (paged.get("beats") or [])}
    for r in rows:
        r["differs"] = differences.get(r["index"], [])
    made = {"schema": 1, "set": set_name, "id": plan, "generator": GENERATOR, "view": view_name, "duration": duration,
            "source": source, "hue": list(found["hue"]) if found["hue"] else None, "fps": oi[0],
            "shown": shown, "recording": recording.replace(os.sep, "/"), "preset": hash_of([preset_path]),
            "recording_stamp": stamp(recording), "gains": {str(k): v for k, v in gains.items()}, "beats": rows,
            "clock": {k: blocking[k] for k in ("hitstop", "timewarp", "duration") if k in blocking},
            "scene": [kept(s) for s in scene], "problems": problems}
    if angle_names:   # (a chart with no solid beat keeps the record it always had)
        made["angle_names"], made["angles"], made["angles_asked"] = angle_names, seen_from, list(asked or [])
    # "drawn": the files he is shown AND this whole record as it is WRITTEN (read back from the file, so what a
    # later check reads is what was hashed) - its beats, its clock, its frame rate: all that --drift holds an effect to
    DC.dump(made, record_path)
    made = json.load(open(record_path, encoding="utf-8"))
    made["drawn"] = hash_of(shown, made)
    DC.dump(made, record_path)
    where = video.replace(os.sep, "/")
    notes = sum(len(r["notes"]) for r in rows)
    key = next((r for r in rows if r["key"]), rows[0])
    told = "; ".join(key["differs"]) if key["differs"] else "its timing agrees with the scene within a film frame"
    if problems:
        return out("fail", f"animatic {set_name}: not an animatic he can approve - {'; '.join(problems)}. LOOK: {where}",
                   f"open the player (lune run kit vfx play {set_name} --animatic), find the beat, fix the chart, make it again",
                   video=where, look=look.replace(os.sep, "/") + "/", id=made["id"], beats=rows, problems=problems)
    blind = [r["beat"] for r in rows if (r.get("measured") or {}).get("unseen")]
    read = ("each hitting where the chart says" if not blind else
            f"{len(rows) - len(blind)} of them read back and hitting where the chart says ({len(blind)} could not be read "
            f"back - they run into another beat: {', '.join(blind)} - the video shows them, --drift cannot hold an effect "
            f"to them)")
    return out("pass", f"animatic {set_name}: {len(rows)} beat(s) as flat shapes on a {duration:g} s clock, {read}; "
               f"{notes} thing(s) the plan had to settle itself (the notes in its record say which). "
               f"{key['beat']}: {told}. LOOK: {where}",
               f"WATCH {where} (the scene | the animatic, beat after beat), open {look.replace(os.sep, '/')}/beat"
               f"{key['index']}_page.png for the frames, read the notes in {record_path.replace(os.sep, '/')}, then show "
               f"the owner: lune run kit review {set_name} --lane vfx; his yes: lune run kit approve vfx {set_name} "
               f"\"<his words>\" --by owner --stage animatic",
               video=where, look=look.replace(os.sep, "/") + "/", id=made["id"], beats=rows, problems=[])


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "animatic: needs a scene set's name", "lune run kit vfx animatic <set> [--view hero]")
    set_name, rest = argv[0], argv[1:]
    bare = {a for a in rest if a in BARE}
    rest = [a for a in rest if a not in bare]
    opts, wrong, i = {}, None, 0
    while i < len(rest) and not wrong:
        if rest[i] not in FLAGS:
            wrong = f"{rest[i]} is not one of {', '.join(sorted(FLAGS | BARE))}"
        elif i + 1 >= len(rest) or rest[i + 1].startswith("--"):
            wrong = f"{rest[i]} needs a value"
        else:
            opts[rest[i]] = rest[i + 1]
        i += 2
    if not wrong and not re.fullmatch(r"[A-Za-z0-9_\-]+", set_name):
        # (its name is in every file it writes, and the review page shows no file with another character in it)
        wrong = "a set's name is letters, digits, _ and - only"
    if not wrong and "--drift" in opts and not re.fullmatch(r"[A-Za-z0-9_\-]+", opts["--drift"]):
        wrong = "an effect's name is letters, digits, _ and - only"     # (it is read as <effects>/<name>.json)
    view_name = opts.get("--view", "hero")
    if "--check" in bare:
        if wrong:
            print(json.dumps({"exists": False, "id": None, "drawn": None, "stale": False, "why": "", "problems": [wrong],
                              "shown": [], "png": None}))
            return 0
        return check(DC.set_piece(set_name, opts.get("--effects")), opts.get("--view"))
    if wrong:
        return out("fail", f"animatic {set_name}: {wrong}", "lune run kit vfx animatic <set> [--view hero]")
    found = DC.set_piece(set_name, opts.get("--effects"))
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return out("fail", "animatic: ffmpeg / ffprobe not on PATH", "install ffmpeg (vetted) or put it on PATH")
    if not found["chart"]:
        return out("fail", f"animatic {set_name}: no beat chart to take the beats from ({found['measured'].replace(os.sep, '/')}"
                   f"/{set_name}.chart.json)", f"lune run kit vfx chart {set_name}")
    bad = unsound(found)
    if bad:
        return out("fail", f"animatic {set_name}: {bad}", f"lune run kit vfx chart {set_name}")
    if "--drift" in opts:
        return drift(found, opts["--drift"], opts.get("--effects"), opts.get("--view"))
    try:
        fps, port = int(opts.get("--fps", 30)), int(opts.get("--port", 47815))
    except ValueError:
        return out("fail", f"animatic {set_name}: --fps and --port are numbers", "lune run kit vfx animatic <set>")
    if not 24 <= fps <= 120:
        # (under 24 a second a drawing on ones is shorter than a frame: a hit drawing can fall between two)
        return out("fail", f"animatic {set_name}: --fps is 24 to 120 frames a second", "lune run kit vfx animatic <set> [--fps 30]")
    asked = [a for a in opts.get("--angles", "").split(",") if a]
    if any(not re.fullmatch(r"[A-Za-z0-9_\-]+", a) for a in asked) or ("--angles" in opts and not asked):
        return out("fail", f"animatic {set_name}: --angles is camera views of kit/vfx/views.json, with commas (combat,cine)", "lune run kit vfx animatic <set> --angles combat,cine")
    if "--blocking" in bare:
        return blocking_only(found, view_name, asked or None)
    return make(found, view_name, fps, port, "--no-record" in bare, asked or None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
