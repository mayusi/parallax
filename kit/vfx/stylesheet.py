"""stylesheet.py — the STYLE SHEET of an effect: every beat's LOOK, ours beside the scene's, on one page the owner
approves before a whole version is polished (the VFX studio-route plan, V1).

    lune run kit vfx stylesheet <effect> [--view hero] [--run <recording>] [--tile 768] [--effects <dir>]
    python kit/vfx/stylesheet.py <effect> --check [--effects <dir>]

Why: the owner approved "the chart with ONE test frame" - the key beat. Every other beat's look was first seen in the
finished effect (flame_arc was redone twice over beats nobody had been shown). A studio signs a style frame per
beat before the effects are built out.

For EVERY beat of the effect's chart, a PAIR at the same size:
    the scene   its main shot's frame at that beat's peak (kit/vfx/denseclip.py: the frame with the most light)
    ours        our recording's frame at OUR peak inside that beat's stretch of the clock
and under each: the effect's five main colours with their shares, and the kit's key read of that frame (kit/vfx/
keyread.py: how much of the frame it covers, its white-hot share, its colour bands, its detail, its pieces). Under the
pair: where ours falls short of the scene on those (the same rule as `kit vfx keyread`: under 0.75 x the scene's).
-> build/vfx/stylesheet/<run>.png          the whole sheet (open it at full size)
   build/vfx/stylesheet/<run>/beat<k>.png  one pair a picture, 2 x --tile px: what a session reads at full size
   build/vfx/stylesheet/<run>.json         the numbers, and what the sheet was made from
The scene's frames are private (measure-only): everything this writes is in the git-ignored build/.

WHAT the owner's yes is recorded for (`lune run kit approve vfx <effect> "<his words>" --by owner --stage style`):
  the ID     a hash of what decides the look and can be read again on any machine - the preset's own file, the scene
             set's name and the chart's plan. A preset edited after his yes has another id: his word again (a re-timed
             beat too: the id is of the whole preset, not yet of each beat's layers - stricter than need be);
  DRAWN      a hash of the pair pictures themselves, as they were on the machine he looked at them on. A sheet drawn
             again from a NEW recording (a texture or a mesh changed, the preset's file did not) shows other pictures:
             same id, another "drawn" - his yes was for the pictures, so it is asked again (a review, 2026-11-12).
--check answers without drawing: {exists, id, drawn, stale, why, problems, files, png} ("files": the pair pictures
"drawn" is the hash of, in order - a page shows exactly these) - stale when the sheet on this machine
was drawn from another preset or another recording than the ones here now, or its pictures are not the ones its
record was written for ("drawn" is read from the pictures themselves, every time); "why" says which. While a sheet
is being drawn (or its drawing failed) there IS no sheet: its record is removed first and written last.

A sheet with a problem is not one he can approve (there is nothing true to show him): a beat where ours never lights
up, a beat with no shot of the scene to put beside it, no recording. Falling SHORT of the scene is not a problem of
the sheet: it is what the sheet is for, and it is said under the pair.
Prints one JSON line {schema, status, summary, next_action, ...}; the summary ends with LOOK: <folder>.
"""

import hashlib
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dailies_page as P  # noqa: E402
import dense  # noqa: E402
import denseclip as DC  # noqa: E402

OUT = DC.gameroot.build("vfx", "stylesheet")  # the active game's build/vfx (card t6rx)
BAND = 96          # px under each frame: the colours and the read
GAP = 12


FLAGS = {"--view", "--run", "--tile", "--effects"}


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def plan_key(chart):
    """the chart's plan as one comparable line: kit/vfx/chart.py plan_key()'s text (kept the same there, in the scene
    gate and in kit/lib/review.luau: a re-timed chart is another chart)"""
    return f"{float(chart.get('duration') or 0):.2f}|" + ";".join(
        f"{float(b.get('t') or 0):.2f},{float(b.get('len') or 0):.2f},{float(b.get('hold') or 0):.2f},{1 if b.get('key') else 0}"
        for b in chart.get("beats", []) if isinstance(b, dict))


def sheet_id(found):
    """what decides the look, readable again on any machine: the preset's file, the set, the chart's plan"""
    try:
        preset = open(found["preset_path"], "rb").read().replace(b"\r\n", b"\n")
    except OSError:
        preset = b""
    plan = plan_key(found["chart"]) if found["chart"] else ""
    return hashlib.sha1(preset + b"|" + str(found["set"]).encode() + b"|" + plan.encode()).hexdigest()[:12]


def stamp(path):
    """a file as it is now (size and time to the nanosecond: a re-recording within the same second is another file):
    the recording a sheet was drawn from"""
    try:
        st = os.stat(path)
        return [st.st_size, st.st_mtime_ns]
    except OSError:
        return None


def swatches(frame, hue, count=5):
    """the effect's main colours in one frame -> [([r, g, b], share of the effect)], most first; [] when it covers
    under 50 pixels"""
    if hue is None:
        y = dense.luma(frame[None])[0]
        mask = y > max(0.35, float(np.percentile(y, 85)))
    else:
        mask = dense.effect_mask(frame[None], hue)[0][0]
    px = frame[mask]
    if len(px) < 50:
        return []
    q = Image.fromarray(px.reshape(-1, 1, 3)).quantize(count, method=Image.MEDIANCUT)
    pal = q.getpalette()[:count * 3]
    counts = np.bincount(np.asarray(q).ravel(), minlength=count)[:count]
    order = np.argsort(-counts)
    return [([int(pal[i * 3]), int(pal[i * 3 + 1]), int(pal[i * 3 + 2])], round(float(counts[i]) / len(px), 3))
            for i in order if counts[i] > 0]


def key_read(frame, hue):
    """the kit's key read of one frame (kit/vfx/keyread.py), or None when the set has no measured hue band"""
    if hue is None:
        return None
    import keyread
    return keyread.read(Image.fromarray(frame), tuple(hue))


def said(read):
    """a key read in two short lines (they sit beside the colours, under a frame)"""
    if not read:
        return ["not read", "(no measured colours for this set)"]
    return [f"covers {read['coverage'] * 100:.0f} % of the frame   white-hot {read['light'] * 100:.0f} %",
            f"{read['layers']} colour bands   detail {read['detail']:.1f}   {read['pieces']} pieces"]


def gaps(scene, ours):
    """where ours falls short of the scene's frame, in plain words. The rule is `kit vfx keyread`'s own (kit/vfx/
    keyread.py compare: under SHORT x the scene's cover, white-hot share, detail or pieces; two colour bands fewer) -
    one sentence per gap, the same count"""
    if not scene or not ours:
        return []
    import keyread
    words = {"coverage": lambda r: f"covers {r['coverage'] * 100:.0f} % of the frame",
             "light": lambda r: f"is {r['light'] * 100:.0f} % white-hot",
             "detail": lambda r: f"has detail {r['detail']:.1f}",
             "pieces": lambda r: f"is in {r['pieces']} pieces"}
    said_ = []
    for k in ("coverage", "light", "detail", "pieces"):
        if scene[k] > 0 and ours[k] < keyread.SHORT * scene[k]:
            said_.append(f"ours {words[k](ours)}, the scene's frame {words[k](scene)}")
    if ours["layers"] <= scene["layers"] - 2:
        said_.append(f"ours has {ours['layers']} colour bands, the scene's frame {scene['layers']}")
    return said_


def side(frame, width, label, colour, colours, read):
    """one frame at `width` px with its label, its five colours and its read under it"""
    im = Image.fromarray(np.asarray(frame, dtype=np.uint8)).convert("RGB")
    height = max(1, int(round(im.height * width / float(im.width))))
    cell = Image.new("RGB", (width, 34 + height + BAND), P.PANEL)
    cell.paste(im.resize((width, height), Image.LANCZOS), (0, 34))
    d = ImageDraw.Draw(cell)
    d.text((10, 6), label, fill=colour, font=P._font(20))
    x, y = 10, 34 + height + 10
    for rgb, share in colours:
        d.rectangle([x, y, x + 44, y + 44], fill=tuple(rgb), outline=(70, 74, 84))
        d.text((x + 2, y + 48), f"{share * 100:.0f}%", fill=P.DIM, font=P._font(15))
        x += 54
    for i, line in enumerate(said(read)):
        d.text((max(x + 14, 296), y + 2 + 24 * i), line, fill=P.INK, font=P._font(18))
    return cell


def nothing(width, height, label, colour, why):
    cell = Image.new("RGB", (width, 34 + height + BAND), P.PANEL)
    d = ImageDraw.Draw(cell)
    d.text((10, 6), label, fill=colour, font=P._font(20))
    d.text((10, 34 + height // 2), why, fill=P.DIM, font=P._font(20))
    return cell


def pair(title, left, right, lines):
    """the scene's frame and ours side by side, the beat's name over them, what differs under them"""
    width = left.width + GAP + right.width
    im = Image.new("RGB", (width, 40 + max(left.height, right.height) + 10 + 26 * max(1, len(lines)) + 10), P.PAGE)
    d = ImageDraw.Draw(im)
    d.text((10, 6), title, fill=P.INK, font=P._font(24))
    im.paste(left, (0, 40))
    im.paste(right, (left.width + GAP, 40))
    y = 40 + max(left.height, right.height) + 10
    for i, line in enumerate(lines or ["holds beside the scene's frame on all five reads"]):
        d.text((10, y + 26 * i), line, fill=P.HITC if line.startswith("SHORT") else P.DIM, font=P._font(18))
    return im


def stack(title, lines, rows):
    width = max([r.width for r in rows] + [1280])
    head = 50 + 26 * len(lines)
    im = Image.new("RGB", (width, head + sum(r.height + GAP for r in rows)), P.PAGE)
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, fill=P.INK, font=P._font(28))
    for i, line in enumerate(lines):
        d.text((10, 50 + 26 * i), line, fill=P.DIM, font=P._font(18))
    y = head
    for r in rows:
        im.paste(r, (0, y))
        y += r.height + GAP
    return im


def drawn_of(look, records):
    """a hash of the pair pictures as they are on disk NOW - what he looks at - or None when one is not there"""
    h = hashlib.sha1()
    for rec in records:
        try:
            h.update(open(os.path.join(look, os.path.basename(str(rec.get("file")))), "rb").read())
        except OSError:
            return None
    return h.hexdigest()[:12] if records else None


def check(found, run):
    """--check: no drawing. "drawn" is read from the PICTURES, not from the record: pictures that are not the ones
    the record was written for (replaced, or half of another drawing) are no sheet to say yes to"""
    png, record = os.path.join(OUT, f"{run}.png"), os.path.join(OUT, f"{run}.json")
    answer = {"exists": False, "id": sheet_id(found), "drawn": None, "stale": False, "why": "", "problems": [],
              "files": [], "png": png.replace(os.sep, "/")}
    try:
        made = json.load(open(record, encoding="utf-8"))
    except (OSError, ValueError):
        made = None
    beats = made.get("beats") if isinstance(made, dict) else None
    now = drawn_of(os.path.join(OUT, run), beats) if isinstance(beats, list) else None
    if made and now and os.path.isfile(png):
        answer["exists"] = True
        answer["drawn"] = now
        # the very files "drawn" is the hash of, in order: what a page shows him is these, no more and no fewer
        answer["files"] = [os.path.basename(str(b.get("file"))) for b in beats]
        why = []                                             # each reason it is not the sheet of what is here now
        if made.get("id") != answer["id"]:
            why.append("the preset, its set or the chart's plan changed since it was drawn")
        if made.get("recording") != stamp(found["recording"]):
            why.append("the effect was recorded again since it was drawn")
        if made.get("drawn") is None:
            why.append("its record names no pictures (an older kit drew it)")
        elif made.get("drawn") != now:
            why.append("its pictures are not the ones its record was written for")
        answer["stale"], answer["why"] = bool(why), "; ".join(why)
        answer["problems"] = list(made.get("problems") or [])
    print(json.dumps(answer))
    return 0


def draw(found, run, width):
    name, hue, beats = found["name"], found["hue"], found["beats"]
    oi = DC.probe(found["recording"])
    whole = DC.read(found["recording"], 0.0, oi[1], hue, oi)
    if whole is None:
        return out("fail", f"stylesheet {name}: under 3 frames in the recording", f"lune run kit vfx play {name} --record")
    si = DC.probe(found["scene_clip"]) if found["scene_clip"] else None
    look = os.path.join(OUT, run)
    # while it is being drawn there is NO sheet: the record goes first and comes back last, so a drawing that
    # fails half way leaves nothing that --check (and the review page) would take for the finished sheet
    for old in (os.path.join(OUT, f"{run}.json"), os.path.join(OUT, f"{run}.png")):
        if os.path.isfile(old):
            os.remove(old)
    shutil.rmtree(look, ignore_errors=True)
    os.makedirs(look, exist_ok=True)
    rows, records, problems, short = [], [], [], []
    height = max(2, int(round(oi[3] * width / float(oi[2]))))
    # the recording is real time: every hit-stop before a beat moves it - on the clock of the preset AS PLAYED
    clock = DC.clock_of(found["played"] if "played" in found else found["preset"], oi[0])
    for k, row in enumerate(beats):
        label = str(row.get("beat", k))
        a, b = DC.stretch(beats, k, oi[0], oi[1], clock)
        ours = DC.within(whole, a, b)
        our_read = our_colours = our_at = None
        got = []
        if ours and ours["timing"]:
            i = ours["timing"]["brightest"]
            got = DC.frames(found["recording"], whole["from"], whole["to"], width, oi, i, i)
        if len(got):
            frame = got[0]
            our_read, our_colours, our_at = key_read(frame, hue), swatches(frame, hue), round(i / oi[0], 3)
            right = side(frame, width, f"OURS at {our_at:.2f} s of its recording", P.OURS, our_colours, our_read)
        elif ours is None:      # (not "never lights up": there is nothing of this beat in the recording to read)
            problems.append(f"beat {label}: the recording holds under 3 frames of its stretch ({a:.2f}-{b:.2f} s of "
                            f"{oi[1]:.2f} s recorded)")
            right = nothing(width, height, "OURS", P.OURS, "the recording ends before this beat's stretch")
        elif ours["timing"]:
            problems.append(f"beat {label}: our frame at {ours['timing']['brightest'] / oi[0]:.2f} s could not be read back")
            right = nothing(width, height, "OURS", P.OURS, "this frame could not be read from the recording")
        else:
            problems.append(f"beat {label}: ours never lights up in its stretch of the clock ({a:.2f}-{b:.2f} s)")
            right = nothing(width, height, "OURS", P.OURS, "nothing lit in this beat's stretch of our clock")
        scene_read = scene_colours = scene_at = None
        sc = row.get("scene")
        shot = None
        if found["scene_clip"] and isinstance(sc, list) and len(sc) == 2:
            read = DC.read_beat(found["scene_clip"], float(sc[0]), float(sc[1]), found["cuts"], hue, si)
            shot = read["shots"][read["main"]] if read["main"] is not None else None
        got = []
        if shot and shot["timing"]:
            i = shot["timing"]["brightest"]
            got = DC.frames(found["scene_clip"], shot["from"], shot["to"], width, si, i, i)
        if len(got):
            frame = got[0]
            scene_at = round(shot["from"] + i / shot["fps"], 3)
            scene_read, scene_colours = key_read(frame, hue), swatches(frame, hue)
            left = side(frame, width, f"THE SCENE at {scene_at:.2f} s", P.SCENE, scene_colours, scene_read)
        else:
            problems.append(f"beat {label}: no shot of the scene to put beside it")
            left = nothing(width, height, "THE SCENE", P.SCENE, "no frame of the scene for this beat on this machine")
        fell = gaps(scene_read, our_read)
        if len(fell) >= 2:
            short.append(label)
        lines = [f"SHORT of the scene: {g}" for g in fell]
        picture = pair(f"beat {label}" + ("   (the key beat)" if row.get("key") else ""), left, right, lines)
        picture.save(os.path.join(look, f"beat{k}.png"))
        rows.append(picture)
        records.append({"beat": label, "index": k, "key": bool(row.get("key")), "file": f"beat{k}.png",
                        "scene": {"at": scene_at, "read": scene_read, "colours": scene_colours},
                        "ours": {"at": our_at, "read": our_read, "colours": our_colours}, "short": fell})
    head = [f"{found['set'] or 'no scene set'}  -  {len(beats)} beat(s), the scene's frame left, ours right, each at its beat's peak",
            "under each frame: the effect's five main colours with their shares, and the key read of that frame",
            "the read counts everything in the set's colour band, lit skin and scenery too: a SHORT line says where to look, it is no verdict"]
    sheet = stack(f"{run} - style sheet", head, rows)
    png = os.path.join(OUT, f"{run}.png")
    sheet.save(png)
    made = {"schema": 1, "name": name, "run": run, "id": sheet_id(found), "drawn": drawn_of(look, records),
            "recording": stamp(found["recording"]), "tile": width, "beats": records, "problems": problems}
    DC.dump(made, os.path.join(OUT, f"{run}.json"))
    where = look.replace(os.sep, "/") + "/"
    falls = f"; short of the scene on two or more of the five reads: {', '.join(short)}" if short else ""
    if DC.caution(found):
        falls += ". " + DC.caution(found)
    if problems:
        return out("fail", f"stylesheet {name}: not a sheet he can approve - {'; '.join(problems)}. LOOK: {where}",
                   f"build the beat(s) named, record again (lune run kit vfx play {name} --record), draw the sheet again",
                   look=where, png=png.replace(os.sep, "/"), id=made["id"], beats=records, problems=problems)
    return out("pass", f"stylesheet {name}: {len(beats)} beat(s) as pairs at {width} px a frame{falls}. LOOK: {where}",
               f"open {where}beat0.png onward at full size (the scene | ours), then show the owner the sheet: lune run kit "
               f"review {name}; his yes: lune run kit approve vfx {name} \"<his words>\" --by owner --stage style",
               look=where, png=png.replace(os.sep, "/"), id=made["id"], beats=records, problems=[])


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "stylesheet: needs an effect's name", "lune run kit vfx stylesheet <effect> [--view hero]")
    name, rest = argv[0], argv[1:]
    bare = {a for a in rest if a == "--check"}
    rest = [a for a in rest if a not in bare]
    # every flag has a value: "--view" with none must not take the next flag for one (it swallowed an --effects the
    # kit had appended, and the sheet was drawn from another folder - a review, 2026-11-12)
    opts, wrong, i = {}, None, 0
    while i < len(rest) and not wrong:
        if rest[i] not in FLAGS:
            wrong = f"{rest[i]} is not one of {', '.join(sorted(FLAGS))}"
        elif i + 1 >= len(rest) or rest[i + 1].startswith("--"):
            wrong = f"{rest[i]} needs a value"
        else:
            opts[rest[i]] = rest[i + 1]
        i += 2
    if wrong:
        if bare:
            print(json.dumps({"exists": False, "id": None, "stale": False, "problems": [wrong], "png": None}))
            return 0
        return out("fail", f"stylesheet {name}: {wrong}", "lune run kit vfx stylesheet <effect> [--view hero] [--tile 768]")
    found = DC.piece(name, opts.get("--effects"), opts.get("--view"), opts.get("--run"))
    if isinstance(found, str):
        if bare:
            print(json.dumps({"exists": False, "id": None, "stale": False, "problems": [found], "png": None}))
            return 0
        return out("fail", f"stylesheet {name}: {found}", "name an existing preset")
    if bare:
        return check(found, found["run"])
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return out("fail", "stylesheet: ffmpeg / ffprobe not on PATH", "install ffmpeg (vetted) or put it on PATH")
    if not os.path.isfile(found["recording"]):
        return out("fail", f"stylesheet {name}: no recording {found['recording'].replace(os.sep, '/')}",
                   f"lune run kit vfx play {name} --record --views {found['view']}")
    if not found["chart"]:
        return out("fail", f"stylesheet {name}: no beat chart to take the beats from (set {found['set']})",
                   f"lune run kit vfx chart {found['set'] or '<set>'}")
    try:
        width = max(480, int(opts.get("--tile", 768)))
    except ValueError:
        return out("fail", f"stylesheet {name}: --tile is a number of pixels (768)", f"lune run kit vfx stylesheet {name}")
    return draw(found, found["run"], width)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
