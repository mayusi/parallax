"""dense.py — a beat's TIMING read frame by frame: the arithmetic of `kit vfx breakdown --dense` (the reference scene)
and of `kit vfx dailies` (the scene beside our effect). Pure numpy: frames in, three curves and the beat's timing out.

Why: a scene breakdown samples its clip at 2 frames a second, and anime effects are timed frame by frame - a hit
that holds two frames, a flash on ones, a smear on threes. So the scene's MOTION was never read; a session typed
the timing from a contact sheet (the VFX studio-route plan, V0, 2026-11-11).

What is measured, per frame of a window round one beat (all inside one shot):
    cover   the share of the screen the effect covers. The effect is, when the set's colours are measured (`hue`),
            what the kit's key read calls the effect (kit/vfx/keyread.py): pixels in the set's hue band that are
            coloured and lit, or white-hot. With no hue it is every pixel at least `floor` brighter than the QUIET
            picture (per pixel, the dimmest it gets in the window: what is there without the effect);
    bright  how bright what it covers is (0..1; 0 when it covers nothing);
    change  how much of the covered shape is new since the frame before (0 = the same drawing held, 1 = all new).
From them (timing), the beat's light read the way an eye reads it:
    ARRIVES  frames from the first light until MOST of the beat's light is on screen (0 = nothing was lit the frame
             before: it snaps in); the frame it arrives on is the HIT - the moment two timings are laid on each other
    STAYS    frames it keeps most of its light
    GOES     frames from there until under a fifth of it
    FREEZE   the longest a single drawing is held while it stays, when that is longer than the rhythm itself
             holds a drawing (a hit-stop). A film on ones uploaded at 30 a second doubles every fourth frame:
             that doubled frame is the upload's, not a freeze, and is not called one
    ON       how long a drawing usually stays: on ones, twos, threes - in 24ths of a second, whatever the clip's
             frame rate. Read from the drawings seen WHOLE (one the window or the lit span cut in two says nothing
             about how long it was held), and only from two or more of them.

Limits, said plainly: it reads LIGHT and COLOUR. A dark effect (black smoke, ink) covers nothing here; a camera
that moves inside the window counts as change; skin or scenery in the set's hue band counts as cover (what is
there through the whole window is taken off as the window's floor). A shot that opens on the effect already lit
has no arrival to read, one that ends while it is lit has only "at least this long": both are flagged (cut_in,
stay_cut, cut_away), neither is guessed.
"""

import numpy as np

FLOOR = 0.12       # no hue: a pixel this much brighter than the quiet picture is the effect's
HELD = 0.035       # two frames whose covered shapes differ by less than this share are ONE drawing, held
ONSET = 0.10       # the effect "has started" at this share of the beat's light (over the window's floor)
MOST = 0.70        # ... "has arrived" at this share: most of its light is on screen
FADED = 0.20       # ... and "has gone" under this share
STEADY = 0.20      # a window whose light never rises this share of its peak over its own floor has no beat shape
BASE = 24.0        # drawings are counted in 24ths of a second (film frames), whatever the clip plays at
TOL = 0.045        # two times closer than this (about one film frame) are the same time
SAT, VAL, HOT_V, HOT_S = 0.25, 0.35, 0.88, 0.35    # kit/vfx/keyread.py's effect: coloured + lit in the hue band, or white-hot
CHUNK = 48         # frames converted at a time (a long shot at 320 px must not need gigabytes)


def luma(frames):
    """(N, H, W, 3) sRGB bytes -> (N, H, W) brightness 0..1 (Rec. 709 weights on the encoded values: a picture's
    light as the eye orders it, which is what a timing read needs)"""
    f = np.asarray(frames, dtype=np.float32) / 255.0
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def quiet(y, low=15.0):
    """the picture WITHOUT the effect: per pixel, about the dimmest it gets in the window (the 15th percentile:
    one dark flicker frame does not set it)"""
    return np.percentile(y, low, axis=0)


def hsv(frames):
    """(N, H, W, 3) sRGB bytes -> hue in degrees (0..360), saturation and value (0..1), each (N, H, W)"""
    f = np.asarray(frames, dtype=np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    v = f.max(axis=-1)
    span = v - f.min(axis=-1)
    safe = np.maximum(span, 1e-6)
    s = np.where(v > 0, span / np.maximum(v, 1e-6), 0.0)
    h = np.where(v == r, ((g - b) / safe) % 6.0, np.where(v == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0))
    return np.where(span > 0, h * 60.0, 0.0), s, v


def effect_mask(frames, hue):
    """the effect by its measured colour (keyread's definition): in the hue band, coloured and lit - or white-hot.
    -> (mask (N, H, W) bool, light (N, H, W) 0..1: the value channel)"""
    h, s, v = hsv(frames)
    lo, hi = float(hue[0]), float(hue[1])
    inband = ((h >= lo) & (h <= hi)) if lo <= hi else ((h >= lo) | (h <= hi))
    return (inband & (s > SAT) & (v > VAL)) | ((v > HOT_V) & (s < HOT_S)), v


TWO_TONE = 0.75    # a frame this much of which is near black or near white (luma < 0.15 or > 0.85) is TWO-TONE
MONO_SAT = 0.15    # ... and MONO when its mean saturation is under this (else tinted: a pink / red negative)
SILHOUETTE_MOST = 2  # a run of two-tone frames this short, between frames that are not, is a SILHOUETTE BEAT


def two_tone(frames):
    """(N, H, W, 3) sRGB bytes -> (flat, sat): per frame the share that is near black or near white, and its mean
    saturation - an anime impact frame turns the whole picture into ink and paper (or a pink negative) for a frame"""
    y = luma(frames)
    flat = ((y < 0.15) | (y > 0.85)).reshape(len(y), -1).mean(axis=1)
    _, sat, _ = hsv(frames)
    return flat.astype(np.float64), sat.reshape(len(sat), -1).mean(axis=1).astype(np.float64)


def silhouettes(c, lo=0, hi=None):
    """the SILHOUETTE BEATS between frames lo..hi (the V3 doc, VFX stage G.1: "explicit 1-frame inverted silhouette
    beats (pink / mono)"): runs of at most SILHOUETTE_MOST two-tone frames with a frame that is not on each side ->
    [(first frame, frames, "mono" | "tinted")]. [] when the curves carry no two-tone read (an older read)"""
    flat, sat = c.get("flat"), c.get("sat")
    if flat is None or sat is None:
        return []
    flat, sat = np.asarray(flat), np.asarray(sat)
    n = len(flat)
    hi = n - 1 if hi is None else min(hi, n - 1)
    out, i = [], max(lo, 0)
    while i <= hi:
        if flat[i] >= TWO_TONE:
            j = i
            while j + 1 < n and flat[j + 1] >= TWO_TONE:
                j += 1
            run = j - i + 1
            closed = (i > 0 and flat[i - 1] < TWO_TONE) and (j < n - 1 and flat[j + 1] < TWO_TONE)
            if run <= SILHOUETTE_MOST and closed:
                out.append((i, run, "mono" if float(np.mean(sat[i:j + 1])) < MONO_SAT else "tinted"))
            i = j + 1
        else:
            i += 1
    return out


def curves(frames, hue=None, floor=FLOOR):
    """(N, H, W, 3) frames of ONE shot -> {"cover", "bright", "change", "flat", "sat"}: arrays of N numbers (see the
    head; flat / sat: two_tone). hue = (low, high) degrees: the set's measured hue band; None reads light over the
    quiet picture"""
    frames = np.asarray(frames)
    n = len(frames)
    cover, bright, change = np.zeros(n), np.zeros(n), np.zeros(n)
    flat, sat = np.zeros(n), np.zeros(n)
    if n == 0:
        return {"cover": cover, "bright": bright, "change": change, "flat": flat, "sat": sat}
    if hue is None:
        # brightness kept as BYTES, made a few frames at a time: a whole recording as floats is gigabytes
        y = np.empty(frames.shape[:3], dtype=np.uint8)
        for a in range(0, n, CHUNK):
            y[a:a + CHUNK] = np.clip(np.rint(luma(frames[a:a + CHUNK]) * 255.0), 0, 255)
        still = (quiet(y) / 255.0).astype(np.float32)
    before = None
    for a in range(0, n, CHUNK):
        b = min(n, a + CHUNK)
        if hue is None:
            light = np.clip(y[a:b].astype(np.float32) / 255.0 - still[None], 0.0, None)
            mask = light > floor
        else:
            mask, light = effect_mask(frames[a:b], hue)
        area = mask.reshape(b - a, -1).sum(axis=1).astype(np.float64)
        cover[a:b] = area / float(mask[0].size)
        flat[a:b], sat[a:b] = two_tone(frames[a:b])
        total = (light * mask).reshape(b - a, -1).sum(axis=1)
        bright[a:b] = np.where(area > 0, total / np.maximum(area, 1.0), 0.0)
        for i in range(a, b):
            now = mask[i - a]
            if before is not None:
                union = np.logical_or(now, before).sum()
                if union:
                    change[i] = 1.0 - np.logical_and(now, before).sum() / float(union)
            before = now
    return {"cover": cover, "bright": bright, "change": change, "flat": flat, "sat": sat}


def energy(c):
    """the light on screen, frame by frame: how much is covered times how bright it is"""
    return np.asarray(c["cover"], dtype=np.float64) * np.asarray(c["bright"], dtype=np.float64)


def timing(c, fps, held=HELD, before=None):
    """the three curves of one beat -> its timing, in frames of the clip and in seconds, or None when the window
    never lights up. before: the light of the frame just BEFORE the window, when the caller knows it (our own
    recording is read whole and timed stretch by stretch); None for a scene's shot (a cut precedes it):
      hit        the frame the light ARRIVES on: the first frame of the stretch at MOST of the beat's light that
                 holds the brightest frame
      arrive     frames from the first light to the hit           cut_in    the window OPENS on it already lit
      stay       frames at most of its light                      stay_cut  the window ENDS while it stays
      go         frames from there until under a fifth            cut_away  the window ENDS before it has gone
      freeze     the longest one drawing is held while it stays (frames);  frozen = that, when it is longer
                 than the rhythm's own hold at this frame rate (on ones at 30 a second: over 2 frames; with no
                 rhythm read, over threes' own), else 0;  frozen_open = the window cut the stay: it ENDED while
                 it stayed, or OPENED on it at most of its light (and nothing says the frame before was dark). The
                 drawing at that edge may have been held longer, so the freeze is "at least", and "none" is "none
                 seen"
      holds      how many frames each drawing in the span stays;  held = the usual one, in the clip's frames
      on         the usual hold in 24ths of a second: 1 = on ones, 2 = on twos ... (a 30 fps upload of a film
                 drawn on twos shows 2 and 3 frame holds; both are "on twos"). Read from the drawings seen WHOLE
                 only - the span's first and last are whole when a new drawing starts / follows there; None with
                 under 2 of them (one held drawing is not a rhythm)
      steady     the light never rises over the window's own floor: no beat shape to read
      brightest (frame), span [first lit, last lit], peak, base (the window's floor),
      seconds {hit, arrive, stay, go, freeze, frozen, span}"""
    e = energy(c)
    n = len(e)
    if n == 0 or float(e.max()) <= 0.0:
        return None
    change = np.asarray(c["change"], dtype=np.float64)
    top = int(np.argmax(e))
    peak = float(e[top])
    base = float(np.percentile(e, 15))           # what is lit through the whole window: not the beat
    # (ONE rule for a scene's shot and for our own stretch, or their differences are the rule's. A beat's own short
    # lead-in can be taken for the floor - "arrives in one frame" of a shape that grew for two; lowering the floor
    # to the frame before the stretch was tried and taken out the same day, 2026-11-12: a glow that starts WITH the
    # stretch then counts as the beat arriving, and a snap on it read as a third of a second)
    steady = (peak - base) < STEADY * peak
    if steady:
        base = 0.0
    rise = peak - base
    started, most, gone = base + ONSET * rise, base + MOST * rise, base + FADED * rise
    hit = top
    while hit > 0 and e[hit - 1] >= most:
        hit -= 1
    first = hit
    while first > 0 and e[first - 1] >= started:
        first -= 1
    end = top
    while end < n - 1 and e[end + 1] >= most:
        end += 1
    last = end
    while last < n - 1 and e[last + 1] >= gone:
        last += 1
    holds, run = [], 1
    for i in range(first + 1, last + 1):
        if change[i] < held:
            run += 1
        else:
            holds.append(run)
            run = 1
    holds.append(run)
    # the frame before the window, when the caller knows it: lit there = the window opens on light that was already on
    lit_before = before is None or float(before) >= started
    most_before = before is None or float(before) >= most
    # a drawing the span (or the window) cut in two says nothing about how long it was held
    starts_whole = (first > 0 or not lit_before) and change[first] >= held
    ends_whole = last < n - 1 and change[last + 1] >= held
    whole = holds[(0 if starts_whole else 1):(len(holds) if ends_whole else len(holds) - 1)]
    freeze, run = 1, 1
    for i in range(hit + 1, end + 1):
        run = run + 1 if change[i] < held else 1
        freeze = max(freeze, run)
    f = float(fps)
    usual = float(np.median(whole)) if whole else float(np.median(holds))
    on = max(1, int(round(usual / f * BASE))) if len(whole) >= 2 else None
    # the longest run the rhythm itself shows at this frame rate; with no rhythm read, the slowest common one's
    # (threes): a run is called a freeze only when no rhythm explains it
    own = int(np.ceil((on or 3) * f / BASE - 1e-9))
    frozen = freeze if freeze > own else 0
    frozen_open = bool(end == n - 1 or (hit == 0 and most_before))
    # the silhouette beats in the span, each by its frames from the hit (a cut-in one is the shot's own first frame)
    sil = [{"at": i - hit, "frames": run, "kind": kind} for i, run, kind in silhouettes(c, first, last)]
    return {"silhouettes": sil, "hit": hit, "arrive": hit - first, "stay": end - hit + 1, "go": last - end, "freeze": freeze,
            "frozen": frozen, "frozen_open": frozen_open, "brightest": top, "drawings": len(holds), "holds": holds,
            "held": usual,
            "on": on, "span": [first, last],
            "cut_in": bool(first == 0 and e[0] >= started and lit_before), "stay_cut": bool(end == n - 1),
            "cut_away": bool(last == n - 1 and e[n - 1] >= gone),
            "steady": bool(steady), "peak": round(peak, 5), "base": round(base, 5),
            "seconds": {"hit": round(hit / f, 3), "arrive": round((hit - first) / f, 3),
                        "stay": round((end - hit + 1) / f, 3), "go": round((last - end) / f, 3),
                        "freeze": round(freeze / f, 3), "frozen": round(frozen / f, 3),
                        "span": round((last - first + 1) / f, 3)}}


def on_what(on):
    """1 -> 'on ones' ... the way a timing is said"""
    return {1: "on ones", 2: "on twos", 3: "on threes", 4: "on fours"}.get(int(on), f"on {int(on)}s (a drawing every {int(on)} film frames)")


def describe(t, zero=0.0, window="shot"):
    """a timing in one sentence. zero: the clip second the window starts at (the arrival is then said in the clip's
    own seconds); window: what the read window is called - a scene's "shot", our own "stretch" of the clock"""
    if t is None:
        return "nothing lit up"
    s = t["seconds"]
    if t["cut_in"]:
        arrive = f"the {window} opens on it already lit (no arrival to read)"
    elif t["arrive"] == 0:
        arrive = "arrives in one frame (nothing lit the frame before)"
    else:
        arrive = f"arrives over {t['arrive']} frame(s) = {s['arrive']:.2f} s"
    stay = f"stays {t['stay']} frame(s) = {s['stay']:.2f} s at most of its light"
    if t["stay_cut"]:
        go = f"the {window} ends while it is still there (at least that long, no going to read)"
    elif t["cut_away"]:
        go = f"going for {t['go']} frame(s) = {s['go']:.2f} s when the {window} ends"
    else:
        go = f"goes in {t['go']} frame(s) = {s['go']:.2f} s"
    if t["frozen"]:
        freeze = f"; a freeze of {'at least ' if t['frozen_open'] else ''}{t['frozen']} frame(s) = {s['frozen']:.2f} s"
    else:
        freeze = f"; no freeze in what the {window} shows" if t["frozen_open"] else "; no freeze"
    drawn = f"drawn {on_what(t['on'])}" if t["on"] else \
        f"{t['drawings']} drawing(s) in it, the longest on screen {max(t['holds'])} frame(s)"
    return f"the light arrives at {zero + s['hit']:.2f} s: {arrive}; {stay}; {go}{freeze}; {drawn}"


def words(t, zero=0.0, window="shot"):
    """a timing as the short cells of a table: {"arrives", "stays", "goes", "freeze", "drawn"}"""
    if t is None:
        return {k: "-" for k in ("arrives", "stays", "goes", "freeze", "drawn")}
    s = t["seconds"]
    at = f"at {zero + s['hit']:.2f} s"

    def n(count):
        return f"{count} frame" + ("" if count == 1 else "s")

    if t["cut_in"]:
        arrives = f"the {window} opens on it lit"
    elif t["arrive"] == 0:
        arrives = f"in one frame, {at}"
    else:
        arrives = f"over {s['arrive']:.2f} s ({n(t['arrive'])}), {at}"
    stays = ("at least " if t["stay_cut"] else "") + f"{s['stay']:.2f} s ({n(t['stay'])})"
    if t["stay_cut"]:
        goes = f"not seen (the {window} ends while it is lit)"
    elif t["cut_away"]:
        goes = f"over {s['go']:.2f} s and still going when the {window} ends"
    elif t["go"] == 0:
        goes = "at once (gone the next frame)"
    else:
        goes = f"in {s['go']:.2f} s ({n(t['go'])})"
    return {"arrives": arrives, "stays": stays, "goes": goes,
            "freeze": f"{s['frozen']:.2f} s ({n(t['frozen'])})" if t["frozen"] else "none",
            "drawn": on_what(t["on"]) if t["on"] else f"too few drawings for a rhythm ({t['drawings']})"}


def verdict(c, t):
    """what the read could NOT see, as words for the summary ('' when nothing): a window that never lights up (a
    dark effect, or the wrong window), one that is lit and changing from its first frame to its last (a moving
    camera, or the beat runs past the window), one lit at a steady level throughout (no beat shape)"""
    if t is None:
        return "nothing lit up in this window: a dark effect is not read (it reads light), or the beat is elsewhere"
    n = len(c["cover"])
    if t["span"][0] == 0 and t["span"][1] == n - 1 and float(np.mean(np.asarray(c["change"])[1:] > HELD)) > 0.9:
        return "lit and changing on every frame of the window: a moving camera, or the beat runs past the window"
    if t["steady"]:
        return "lit at a steady level through the whole window: no arrival, stay or going to read here"
    return ""


def resample(values, fps_from, fps_to, count=None):
    """a curve measured at one frame rate, read at another's frame times (nearest earlier frame: a held drawing
    stays held) - so the scene at 24 and our capture at 60 can be laid over each other"""
    values = np.asarray(values, dtype=np.float64)
    n = int(count if count is not None else round(len(values) * float(fps_to) / float(fps_from)))
    idx = np.minimum((np.arange(n) * float(fps_from) / float(fps_to)).astype(int), len(values) - 1)
    return values[idx]


def compare(scene, ours):
    """two timings (timing() of the scene's beat and of ours) -> the differences a session acts on, in seconds and
    in words; [] when they agree within a film frame. What a cut hid on one side is not compared, or is compared as
    "at least"."""
    if scene is None or ours is None:
        return ["one of the two never lights up: nothing to compare"]
    said = []
    a, b = scene["seconds"], ours["seconds"]
    if scene["cut_in"]:
        if not ours["cut_in"] and b["arrive"] > TOL:
            said.append(f"it arrives: the scene's shot opens on it already lit, ours takes {b['arrive']:.2f} s")
    elif not ours["cut_in"] and abs(a["arrive"] - b["arrive"]) > TOL:
        how = [f"{'the scene' if k == 0 else 'ours'} " + ("in one frame" if t["arrive"] == 0 else f"over {t['seconds']['arrive']:.2f} s")
               for k, t in enumerate((scene, ours))]
        said.append(f"it arrives: {how[0]}, {how[1]}")
    if scene["stay_cut"] and not ours["stay_cut"]:
        if b["stay"] < a["stay"] - TOL:
            said.append(f"it stays: the scene at least {a['stay']:.2f} s (its shot ends while it is lit), ours {b['stay']:.2f} s")
    elif ours["stay_cut"] and not scene["stay_cut"]:
        if a["stay"] < b["stay"] - TOL:
            said.append(f"it stays: the scene {a['stay']:.2f} s, ours at least {b['stay']:.2f} s (our stretch ends while it is lit)")
    elif not scene["stay_cut"] and abs(a["stay"] - b["stay"]) > TOL:
        said.append(f"it stays: the scene {a['stay']:.2f} s, ours {b['stay']:.2f} s")
    whole = not (scene["stay_cut"] or scene["cut_away"] or ours["stay_cut"] or ours["cut_away"])
    if whole and abs(a["go"] - b["go"]) > TOL:
        said.append(f"it goes: the scene in {a['go']:.2f} s, ours in {b['go']:.2f} s")
    # a side whose window ended while it stayed shows only part of its stay: its freeze is "at least that long",
    # and its "none" is "none in what was seen" - said against the other side only where that still tells them apart
    def hidden(cut, whole):
        if cut["frozen"] > 0:                    # at least this long: the other must be SHORTER to differ
            return whole["seconds"]["frozen"] < cut["seconds"]["frozen"] - TOL
        # none seen over the cut side's stay: the other differs when it froze within a stay no longer than that
        return whole["seconds"]["frozen"] > TOL and whole["seconds"]["stay"] <= cut["seconds"]["stay"] + TOL

    if scene["frozen_open"] and ours["frozen_open"]:
        frozen_differs = False
    elif scene["frozen_open"]:
        frozen_differs = hidden(scene, ours)
    elif ours["frozen_open"]:
        frozen_differs = hidden(ours, scene)
    else:
        frozen_differs = abs(a["frozen"] - b["frozen"]) > TOL
    if frozen_differs:
        how = []
        for who, t, shows in (("the scene", scene, "its shot shows"), ("ours", ours, "our stretch shows")):
            if t["frozen"]:
                how.append(f"{who} " + ("at least " if t["frozen_open"] else "")
                           + f"{t['seconds']['frozen']:.2f} s ({t['frozen']} of its frames)")
            elif t["frozen_open"]:
                how.append(f"{who} none in the {t['seconds']['stay']:.2f} s {shows}")
            else:
                how.append(f"{who} has none")
        said.append(f"a freeze while it stays: {how[0]}, {how[1]}")
    if scene["on"] and ours["on"] and scene["on"] != ours["on"]:
        said.append(f"the scene is drawn {on_what(scene['on'])}, ours {on_what(ours['on'])}")
    # the silhouette beats (G.1): a frame of ink and paper (or a pink negative) the scene flashes and ours does not,
    # or of another kind (only when both reads carry the two-tone measure)
    if "silhouettes" in scene and "silhouettes" in ours:
        sk = [x["kind"] for x in scene["silhouettes"]]
        ok = [x["kind"] for x in ours["silhouettes"]]
        if sk and not ok:
            x = scene["silhouettes"][0]
            said.append(f"a silhouette frame: the scene flashes {len(sk)} ({x['kind']}, {x['frames']} frame(s), {x['at']:+d} from the hit), ours none")
        elif ok and not sk:
            said.append(f"a silhouette frame: ours flashes {len(ok)} ({ok[0]}), the scene none")
        elif sk and ok and sk[0] != ok[0]:
            said.append(f"a silhouette frame: the scene's is {sk[0]}, ours {ok[0]}")
    return said
