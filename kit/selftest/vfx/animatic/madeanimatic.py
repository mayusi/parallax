"""madeanimatic.py — the timing animatic's proof WITHOUT a browser (kit selftest + kit/test/python/
test_vfx_animatic.py): the made project of kit/selftest/vfx/stylesheet/madeproject.py (one set "fire" with a chart
of two beats and a scene clip, one effect "fx" built from it), and RECORDINGS made here from the animatic's own
plan - every beat a fire disc of the plan's share of the frame, from the plan's hit to its going, on a dark frame.

The recordings are made the way the player's recorder makes them: one frame a step of the player's clock
(player_clock below - a port of the page's record loop and the player's step(), written here on its own: the tool's
reading of a recording, denseclip.frame_times, is held against it and against a real recording's posted times in
kit/test/python/test_vfx_dailies.py, never only against itself). A hit-stop is held frames; the frame taken after the
first step shows 1/fps, not 0.

The real recording is the player's (kit vfx animatic records it through a headless browser); what is proven here is
everything round it: the plan, the preset, the read of a recording against the plan, the pages, the side-by-side
video, the check, what a recording is OF (--no-record), and the drift of a built effect from the animatic. The tool
is run from the folder its build/ is in.
"""

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dailies"))
sys.path.insert(0, os.path.join(HERE, "..", "stylesheet"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import animatic  # noqa: E402
import clips  # noqa: E402
import denseclip as DC  # noqa: E402
import madeproject  # noqa: E402


def player_clock(preset, fps):
    """the effect time each frame of a recording shows. kit/vfx/player/index.html record():
        for (; player.time < d - 1e-6 && !player.finished; ) { player.step(1 / fps); <the frame is taken> }
    and kit/vfx/player/player.js step(dt): inside a hit-stop `holdLeft -= dt`, and while it is still above 0 the
    frame shows the same moment; else the clock moves dt times its speed there (warpAt), and a move that crosses a
    hit-stop (`time < at && t >= at`, the first in the list) stops ON it and starts its hold."""
    stops = [(float(h["at"]), float(h.get("hold") or 0.08)) for h in preset.get("hitstop") or []]
    warp = preset.get("timewarp") or []

    def warp_at(t):
        if not warp:
            return 1.0
        if t <= warp[0][0]:
            return 1.0 if (warp[0][0] > 0 and t < warp[0][0]) else warp[0][1]
        for i in range(len(warp) - 1):
            a, b = warp[i], warp[i + 1]
            if t <= b[0]:
                return a[1] + (b[1] - a[1]) * ((t - a[0]) / max(1e-6, b[0] - a[0]))
        return 1.0 if t > warp[-1][0] else warp[-1][1]

    duration, dt = float(preset.get("duration") or 5), 1.0 / fps
    time, hold_left, finished, taken = 0.0, 0.0, False, []
    while time < duration - 1e-6 and not finished and len(taken) < 100000:
        moves = True
        if hold_left > 0:
            hold_left -= dt
            moves = not hold_left > 0
        if moves:
            t = time + dt * warp_at(time)
            for stop, hold in stops:
                if time < stop and t >= stop:
                    t, hold_left = stop, hold
                    break
            time = t
            finished = t >= duration
        taken.append(time)
    return taken


def rows_of(set_name, effects=None):
    """the animatic's plan rows for a set, by the tool's own functions -> (what the set holds, rows)"""
    found = DC.set_piece(set_name, effects)
    return found, animatic.plan_rows(found["beats"], animatic.scene_reads(found), float(found["chart"]["duration"]))


def blocking_of(found, rows, gains=None):
    """the blocking preset the tool makes of these rows (the hero view)"""
    return animatic.preset_of(found["set"], rows, "hero", animatic.view_of("hero"), float(found["chart"]["duration"]),
                              found["hue"], gains)


def recording(rows, preset, fps=30, late=None, ramp=None, linger=(), spark=None, dim=None):
    """the plan as a recording's frames on `preset`'s clock (its length, hit-stops and slow motion): each beat a fire
    disc covering the plan's share of the frame, from its hit to its going - lit as the player lights a layer
    (`t >= at`, nothing allowed for). What a built effect can do differently from the motion that was watched:
      late    {beat index: FRAMES} - that beat's light starts that many frames of the recording after the frame the
              plan has its hit in (before it, when negative);
      ramp    {beat index: FRAMES} - ... and grows evenly in area over that many frames, instead of being there at once;
      linger  the beats whose light does NOT go before the next beat starts (it stays on until then);
      spark   {beat index: share of its light} - a small light of that share from the frame the plan has its hit in
              until its own (late) light comes: an effect that "starts" on time and snaps late;
      dim     {beat index: share of its light} - the beat covers only that share of what the plan gives it."""
    late, ramp, spark, dim = late or {}, ramp or {}, spark or {}, dim or {}
    times = player_clock(preset, fps)
    first = {r["index"]: next((i for i, t in enumerate(times) if t >= r["t"] + r["arrive"]), len(times)) for r in rows}
    frames = []
    for i, t in enumerate(times):
        area = 0.0
        for r in rows:
            k = r["index"]
            on = first[k] + late.get(k, 0)
            if i >= on and t < r["t"] + r["life"] - (0.0 if k in linger else r["go"]):
                area = r["share"] * dim.get(k, 1.0) * (min(1.0, (i - on + 1) / ramp[k]) if ramp.get(k) else 1.0)
            elif first[k] <= i < on and spark.get(k):
                area = r["share"] * spark[k]
        frames.append(clips.frame(int(round(math.sqrt(area * clips.W * clips.H / math.pi)))))
    return np.stack(frames)


def curve(keys, u):
    """a preset curve [[u, value], ...] at u: a straight line between its keys (the player's numAt); a value that is
    a list is read by its first number"""
    first = lambda v: float(v[0] if isinstance(v, (list, tuple)) else v)  # noqa: E731
    for (ua, va), (ub, vb) in zip(keys, keys[1:]):
        if u <= ub:
            f = 0.0 if ub <= ua else max(0.0, min(1.0, (u - ua) / (ub - ua)))
            return first(va) + (first(vb) - first(va)) * f
    return first(keys[-1][1])


def lit(el, t):
    """how much of its whole light a mesh layer of a preset shows at clock time t, as the player draws it
    (kit/vfx/player/player.js, the mesh layer): alive while `t >= at` and its UNSTEPPED age is within its life
    (`(t - at) / life <= 1`); its curves are read at its stepped age (`floor((t - at) * step) / step`), in a straight
    line between their keys; its light is the square of its scale against its largest - times, for an arc, the part
    its sweep shows (head - tail). 0 when it is not alive."""
    if t < el["at"] or (t - el["at"]) / el["life"] > 1:
        return 0.0
    step = el.get("step")
    u = (math.floor((t - el["at"]) * step) / step if step else t - el["at"]) / el["life"]
    size = (curve(el["scale"], u) / max(float(k[1][0]) for k in el["scale"])) ** 2
    if "sweep" in el:
        size *= max(0.0, curve(el["sweep"]["head"], u) - curve(el["sweep"]["tail"], u))
    return size


def drawn_recording(rows, preset, fps=30):
    """the ANIMATIC as the player draws it, read from the PRESET the tool made (never from the plan): every frame of
    the recorder's clock (player_clock), every mesh layer by the player's own rules (lit), as a fire disc of that
    share of the frame the plan gives the beat. One disc a frame: the larger light where two layers overlap. A key
    that is not ON its drawing, or a light that sits on a line the timing read draws, shows here as it shows in the
    real recording."""
    live = [r for r in rows if not r.get("problem")]
    frames = []
    for t in player_clock(preset, fps):
        area = max([row["share"] * lit(el, t) for row, el in zip(live, preset["layers"])] or [0.0])
        frames.append(clips.frame(int(round(math.sqrt(area * clips.W * clips.H / math.pi)))))
    return np.stack(frames)


def shown_frame(preset, k, n=0, fps=30):
    """the first frame of the preset's recording in which its layer k is on its drawing n or a later one - by the
    player's own rule, on the fixture's own port of the recorder's clock: the TRUTH a read of the recording is held
    to (never the tool's own answer). None when no frame shows it."""
    el = preset["layers"][k]
    for i, t in enumerate(player_clock(preset, fps)):
        if t >= el["at"] and (t - el["at"]) / el["life"] <= 1 and math.floor((t - el["at"]) * el["step"]) >= n:
            return i
    return None


def record_animatic(set_name, effects=None, booth=None, drawn=False, **how):
    """the set's animatic "recorded" with no browser, as it is planned NOW: its recording on the blocking preset's
    own clock, and beside it what the tool's recorder leaves the moment it records - what the recording is OF (the
    plan's id, no size corrections, the file's stamp) -> (what the set holds, rows, the recording). drawn: drawn as
    the player draws the blocking preset, drawing by drawing (drawn_recording), instead of a light that is there at
    once; how: recording()'s own (linger: an animatic whose beats run into each other)"""
    found, rows = rows_of(set_name, effects)
    booth = booth or os.path.join("build", "vfx", "booth")
    blocking = blocking_of(found, rows)
    made = clips.write(os.path.join(booth, f"{set_name}_animatic_play_hero.mp4"),
                       drawn_recording(rows, blocking) if drawn else recording(rows, blocking, **how), 30)
    plan = animatic.plan_id(set_name, rows, "hero", float(found["chart"]["duration"]), found["hue"], animatic.source_of(found),
                            animatic.view_of("hero"))
    animatic.mark_recorded(set_name, "hero", plan, {}, made)
    return found, rows, made


def project(root, set_name="fire", name="fx", booth=None, late=None, holds=None, stops=None, drawn=False):
    """the made project with its set's ANIMATIC recording and its effect's recording in place (both from the plan)
    -> (rows, the animatic's recording, the effect's recording). Run from the folder the tool will run in (its paths
    are relative to it).
      late    {beat index: frames}: the EFFECT's drift;
      holds   {beat index: seconds}: the chart holds those beats (hit-stops on their hits, in the animatic);
      stops   the built effect's own hit-stops ([{at, hold}]): its recording runs on that clock;
      drawn   the animatic's recording is drawn as the player draws its preset (drawn_recording)."""
    madeproject.project(root, clips.our_frames(), name, set_name, booth)
    effects = os.path.join(root, "assets", "effects")
    if holds:
        path = os.path.join(effects, "refs_measured", f"{set_name}.chart.json")
        chart = json.load(open(path))
        for k, hold in holds.items():
            chart["beats"][k]["hold"] = hold
        json.dump(chart, open(path, "w"))
    booth = booth or os.path.join(root, "build", "vfx", "booth")
    _, rows, made = record_animatic(set_name, effects, booth, drawn=drawn)
    path = os.path.join(effects, f"{name}.json")
    effect = json.load(open(path))
    if stops:
        effect["hitstop"] = stops
        json.dump(effect, open(path, "w"))
    built = clips.write(os.path.join(booth, f"{name}_play_hero.mp4"), recording(rows, effect, late=late), 30)
    return rows, made, built
