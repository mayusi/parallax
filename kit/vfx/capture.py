"""capture.py — the kit's real eyes for VFX (and the UI booth): Roblox Studio's own view while an effect is held still,
and the local server of the BROWSER player.

    python kit/vfx/capture.py studio --name <run> --job <build/.../<run>.job.json> --match <the scratch place>
                                     [--out build/vfx/booth] [--crop l,t,r,b] [--clip] [--wait 900] [--result-wait 600]
    python kit/vfx/capture.py serve --name <run> [--preset <effect>] [--job ...] [--port 47811] [--out build/vfx/booth]

studio  the booths in Studio, through the shared capture bridge (kit/tools/studio_capture.py, card 4s96: no network
        - a script the Studio tools run cannot call a local server). `lune run kit vfx booth <name>` / `kit ui booth
        <Screen>` write the run's script (<run>.studio.luau); start this FIRST (in the background), then run that script
        through the Studio tools (execute_luau, Edit) in the scratch place. It brings the place's window to the front
        (maximised when its 3D view could not be 1600 px wide otherwise) and reads it: every picture the script signals
        with a colour over the 3D view (a HELD walk: the VFX booth, the UI booth's reel mode), or, with --clip, the
        moving arrival of a UI screen timed from the frame it starts (the read closest to each of the job's moments).
        Each picture is cut to the 3D view, then by --crop (fractions of each side: Studio's view cube, tool strip).
        The script's own answer (each picture's view, moment and clock) is its execute_luau RETURN value: save that
        JSON line as <out>/<run>.result.json (a long run answers "started": run its .collect.luau when it is over, and
        save THAT line) - this command waits for the file, then names the pictures and makes the sheets.
serve   the browser player's server on 127.0.0.1 (kit vfx play: the page, its bundles, the frames it records, the
        preset hot reload). Studio never calls it.
Outputs: <out>/<name>/<view>_<n>.png, <out>/<name>_<view>.png (contact sheet, times labelled), <out>/<name>_<view>.mp4
when the frames are evenly spaced (video mode). Prints one JSON line on exit: {status, summary, next_action, sheets}.
"""

import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gameroot import active_game, game_root  # noqa: E402  (one rule for every kit/vfx tool: card t6rx)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import studio_capture  # noqa: E402  (the shared Studio capture bridge, card 4s96)


def play_dir():
    """where `kit vfx play` writes the bundles the page plays (Config.build("vfx") .. "/play")"""
    return os.path.join(game_root(), "build", "vfx", "play")


class Session:
    def __init__(self, name, out, crop, fps, focus=True):
        self.name, self.out, self.crop, self.fps = name, out, crop, fps
        self.focus = focus
        self.frames = {}  # view -> [(i, t, path)]
        self.thumb = 340
        self.metrics = None
        self.lock = threading.Lock()
        self.done = threading.Event()
        os.makedirs(os.path.join(out, name), exist_ok=True)

    def frame_png(self, view, i, t, raw, ext="png", tag=None):
        """a frame the browser player rendered itself (record mode), same numbering as grabbed frames; a `tag`
        (a layer name) names the file <view>__<tag>.<ext> instead (the bake of impact frames) and keeps the rest"""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", view):
            raise ValueError(f"view name {view!r}: letters, digits, _ and - only")
        if tag is not None:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", tag):
                raise ValueError(f"tag {tag!r}: letters, digits, _ . - only")
            d = os.path.join(self.out, self.name)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, f"{view}__{tag}.{ext}")
            with open(path, "wb") as fh:
                fh.write(raw)
            with self.lock:
                self.tagged = getattr(self, "tagged", 0) + 1
            return path
        with self.lock:
            if view not in self.frames:
                d = os.path.join(self.out, self.name)
                mine = re.compile(rf"^{re.escape(view)}_\d{{3}}\.(png|jpg)$")
                for f in os.listdir(d):
                    if mine.match(f):
                        os.remove(os.path.join(d, f))
                self.frames[view] = []
            path = os.path.join(self.out, self.name, f"{view}_{i:03d}.{ext}")
            with open(path, "wb") as fh:
                fh.write(raw)
            self.frames[view].append((i, t, path))
        return path

    def keep(self, view, i, t, img):
        """a picture of Studio's 3D view (the capture bridge's), cut by --crop and saved as <view>_<i>.png"""
        img = img.crop(studio_capture.crop_box(img.size, self.crop))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", view):
            raise ValueError(f"view name {view!r}: letters, digits, _ and - only")
        if view not in self.frames:  # first frame of this view in this run: drop the view's frames from older runs
            d = os.path.join(self.out, self.name)
            mine = re.compile(rf"^{re.escape(view)}_\d{{3}}\.png$")
            for f in os.listdir(d):
                if mine.match(f):
                    os.remove(os.path.join(d, f))
        path = os.path.join(self.out, self.name, f"{view}_{i:03d}.png")
        img.save(path)
        self.frames.setdefault(view, []).append((i, t, path))
        return path

    def stages(self):
        """The preset's clock: its hits (hitstop at + the effect time each spans) and its duration - the LIFECYCLE sheet
        stages every frame by it. Read from the EXPANDED bundle the page plays (build/vfx/play/<name>.json: parts' hitstops
        and beat expressions resolved, the variant applied - review 2026-10-23), else the raw preset; None without either.
        A Studio booth run of a preset is staged the same way (its frames carry the effect clock too)."""
        job = getattr(self, "job", None) or {}
        run = re.sub(r"_play$", "", self.name or "")  # the run's own bundle first: evolve / variant / blockout / --with runs
        p = None
        for key in [k for k in (run, job.get("name"), job.get("preset")) if k]:
            path = os.path.join(play_dir(), key + ".json")
            try:
                d = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get("preset"), dict):
                p = d["preset"]
                break
        if p is None:  # no bundle: the raw preset (its own clock, unexpanded)
            for key in [k for k in (job.get("preset"), job.get("name")) if k]:
                try:
                    d = json.load(open(os.path.join("assets", "effects", re.sub(r"@.*$", "", key) + ".json"), encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(d, dict):
                    p = d
                    break
        if not p:
            return None
        beats, hits = p.get("beats") or {}, []
        for h in p.get("hitstop") or []:
            at = h.get("at")
            at = beats.get(at) if isinstance(at, str) else at
            if isinstance(at, (int, float)):
                hits.append((float(at), float(h.get("span") or h.get("hold") or 0.08)))
        return {"duration": float(p.get("duration") or 0), "hits": sorted(hits)}

    @staticmethod
    def stage_of(t, st):
        """anticipation (before the first hit) | impact (inside a hit's window) | follow-through | dissipation (the
        last 30% of the time after the last hit, on the clock the recording really ran: st["end"] when known)"""
        hits, dur = st["hits"], min(st["duration"], st.get("end") or st["duration"])
        if any(at - 0.02 <= t <= at + span + 0.02 for at, span in hits):
            return "impact"
        if hits and t < hits[0][0]:
            return "anticipation"
        end = hits[-1][0] + hits[-1][1] if hits else 0.0
        return "dissipation" if t >= end + 0.7 * max(dur - end, 0.0) else "follow-through"

    def finish(self):
        sheets = []
        st = self.stages()
        for view, frames in self.frames.items():
            frames.sort()
            if st:
                # the LIFECYCLE sheet (2026-10-23, the owner: "evaluate effects at multiple stages ... not only at peak"):
                # row block 1 = the whole life sampled by EFFECT time (a held hit-stop no longer eats the samples), each
                # frame named by its stage; row block 2 = the impact window frame by frame (the impact frames are one or
                # two recorded frames each: an even sampling skipped them)
                uniq = [f for k, f in enumerate(frames) if k == 0 or abs(f[1] - frames[k - 1][1]) > 1e-4]
                t_end = max(f[1] for f in frames)
                st = dict(st, end=t_end)
                life = []
                for k in range(12):
                    want = t_end * k / 11
                    pick = min(uniq, key=lambda f: abs(f[1] - want))
                    if pick not in life:
                        life.append(pick)
                imp = [f for f in frames if self.stage_of(f[1], st) == "impact"]
                if len(imp) > 12:
                    imp = [imp[round(k * (len(imp) - 1) / 11)] for k in range(12)]
                blocks = [("whole life (by effect time)", life)] + ([("impact window, frame by frame", imp)] if imp else [])
            else:
                blocks = [("", frames if len(frames) <= 30 else [frames[round(k * (len(frames) - 1) / 19)] for k in range(20)])]
            rendered = []
            for title, shown in blocks:
                thumbs = []
                for _i, t, path in shown:
                    im = Image.open(path)
                    im.thumbnail((self.thumb, self.thumb))
                    d = ImageDraw.Draw(im)
                    label = f"t={t:.2f}" + (f" {self.stage_of(t, st)}" if st else "")
                    d.rectangle((0, 0, 8 + 6 * len(label), 16), fill=(0, 0, 0))
                    d.text((4, 2), label, fill=(255, 255, 255))
                    thumbs.append(im)
                rendered.append((title, thumbs))
            cols = 6 if st else min(5, len(rendered[0][1]))
            tw, th = rendered[0][1][0].size
            heights = [(18 if title else 0) + ((len(th_) + cols - 1) // cols) * (th + 3) + 3 for title, th_ in rendered]
            sheet = Image.new("RGB", (cols * tw + (cols + 1) * 3, sum(heights)), (12, 12, 14))
            y = 0
            for (title, thumbs), hgt in zip(rendered, heights):
                if title:
                    ImageDraw.Draw(sheet).text((4, y + 3), title, fill=(255, 220, 140))
                    y += 18
                for k, im in enumerate(thumbs):
                    r, c = divmod(k, cols)
                    sheet.paste(im, (3 + c * (tw + 3), y + 3 + r * (th + 3)))
                y += hgt - (18 if title else 0)
            sp = os.path.join(self.out, f"{self.name}_{view}.png")
            sheet.save(sp)
            entry = {"view": view, "sheet": sp.replace("\\", "/"), "frames": len(frames)}
            times = [t for _i, t, _p in frames]
            steps = [round(b - a, 3) for a, b in zip(times, times[1:])]
            steps_sorted = sorted(steps)
            median = steps_sorted[len(steps_sorted) // 2] if steps_sorted else 0
            # a video when the frames are a steady beat (a hit-stop frame may shorten ONE step: use the median)
            even = steps and sum(1 for x in steps if abs(x - median) < 0.02) >= 0.9 * len(steps)
            # the page's fps rules when it is given (held frames of a hit-stop break the beat, and a slow window around a
            # hit is mostly held: its median step is 0); without it, a steady beat is required
            if len(frames) >= 12 and (getattr(self, "video_fps", None) or (even and median > 0)):
                mp4 = os.path.join(self.out, f"{self.name}_{view}.mp4")
                fps = getattr(self, "video_fps", None) or round(1 / median)
                ext = os.path.splitext(frames[0][2])[1]
                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-start_number", str(frames[0][0]), "-i",
                       os.path.join(self.out, self.name, f"{view}_%03d{ext}"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", mp4]
                try:
                    subprocess.run(cmd, check=True, timeout=300)
                    entry["video"] = mp4.replace("\\", "/")
                except (OSError, subprocess.SubprocessError) as e:
                    entry["video_error"] = str(e)
            sheets.append(entry)
        if len(sheets) > 1:  # every view in one picture: one look covers the whole run
            ims = [Image.open(e["sheet"]) for e in sheets]
            W = max(i.width for i in ims)
            allv = Image.new("RGB", (W, sum(i.height + 16 for i in ims)), (12, 12, 14))
            y = 0
            for e, im in zip(sheets, ims):
                ImageDraw.Draw(allv).text((4, y + 2), e["view"], fill=(255, 220, 140))
                allv.paste(im, (0, y + 16))
                y += im.height + 16
            ap = os.path.join(self.out, f"{self.name}_all.png")
            allv.save(ap)
            sheets.insert(0, {"view": "all", "sheet": ap.replace("\\", "/"), "frames": sum(e["frames"] for e in sheets)})
        return sheets


_PRESET_LOCK = threading.Lock()  # two saves at once (threaded server) must not lose a field


def save_layer_field(req):
    with _PRESET_LOCK:
        return _save_layer_field(req)


def _save_layer_field(req):
    """{preset, layer, field, value} -> the layer named `layer` in assets/effects/<preset>.json, or, for a part layer
    ("<as>.<name>" placed by a `use`), the part file it came from; `value` replaces the field (null deletes it).
    Only layer fields change; nothing else in the file moves (the JSON is re-indented the kit's way)."""
    preset = re.sub(r"@.*$", "", str(req.get("preset", "")))
    layer, field = str(req.get("layer", "")), str(req.get("field", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", preset) or not field or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", field):
        return {"ok": False, "error": "bad preset / field name"}
    if field in ("name", "kind"):
        return {"ok": False, "error": "name and kind are not editable here"}
    path = os.path.join("assets", "effects", preset + ".json")
    if not os.path.isfile(path):
        return {"ok": False, "error": f"no preset {path}"}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    target_path, target_layer = None, None
    for l in doc.get("layers", []):
        if l.get("name") == layer:
            target_path, target_layer = path, l
    if target_layer is None and "." in layer:  # a part layer: "<as>.<name>" -> the part named by the use with that `as`
        prefix, inner = layer.split(".", 1)
        for i, u in enumerate(doc.get("use", [])):
            as_ = u.get("as") or f"{u.get('part')}{i + 1}"
            if as_ == prefix:
                ppath = os.path.join("assets", "effects", "parts", str(u.get("part")) + ".json")
                if os.path.isfile(ppath):
                    with open(ppath, encoding="utf-8") as fh:
                        pdoc = json.load(fh)
                    for l in pdoc.get("layers", []):
                        if str(l.get("name")) == inner:
                            doc, target_path, target_layer = pdoc, ppath, l
    if target_layer is None:
        return {"ok": False, "error": f"no layer {layer} in {preset} or its parts"}
    value = req.get("value")
    if value is None:
        target_layer.pop(field, None)
    else:
        old = target_layer.get(field)
        if old is not None and isinstance(old, (int, float, str, bool)) and isinstance(value, (dict, list)):
            return {"ok": False, "error": f"{field} is a {type(old).__name__}, not a {type(value).__name__}"}
        target_layer[field] = value
    with open(target_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    return {"ok": True, "file": target_path.replace(os.sep, "/"), "layer": layer, "field": field}


KEPT = (("fractures", "debris", lambda el: el.get("pieces")),
        ("fields", "swarm", lambda el: (el.get("field") or {}).get("name") if isinstance(el.get("field"), dict) else None),
        ("points", "swarm", lambda el: (el.get("cloud") or {}).get("name") if isinstance(el.get("cloud"), dict) else None))


def kept_files(preset, effects):
    """the kept files a preset's layers name (a fracture plan, an authored field, a point cloud), read again from the
    effects folder -> ({"fractures": {name: data}, "fields": {...}, "points": {...}}, [what could not be read]).
    The hot reload's: a plan cut again while the player is open used to stay the OLD one until `kit vfx play` was run
    again (the bundle's preset was rewritten, its kept files never). A file that is not what it should be is left
    out and said - the bundle then keeps the one it had."""
    out, bad = {"fractures": {}, "fields": {}, "points": {}}, []
    for el in (preset or {}).get("layers") or []:
        if not isinstance(el, dict):
            continue
        for folder, kind, named in KEPT:
            name = named(el) if el.get("kind") == kind else None
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in out[folder]:
                continue
            path = os.path.join(effects, folder, name + ".json")
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                bad.append(f"{folder}/{name}.json cannot be read")
                continue
            ok = isinstance(data, dict)
            if ok and folder == "fields":
                ok = isinstance(data.get("elements"), list) and len(data["elements"]) > 0
            if ok and folder == "points":
                pts = data.get("points")
                ok = (isinstance(pts, list) and 8 <= len(pts) <= 150 and all(
                    isinstance(p, list) and len(p) >= 3 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in p[:3]) for p in pts))
            if not ok:
                bad.append(f"{folder}/{name}.json is not a {folder[:-1]}")
                continue
            out[folder][name] = data
    return out, bad


def watch_preset(s, preset, variant, kept_root=None):
    """hot reload: when assets/effects/<preset>.json or any part changes, re-expand it through the kit
    (`lune run kit vfx expand`, so beats / parts / variants apply exactly as the game sees them) and rewrite the
    bundle's preset; the page polls /version and swaps the preset in place, keeping its clock"""
    import subprocess
    if "@" in preset and not variant:  # `kit vfx play <name> --variant v` passes "<name>@v" as the preset
        preset, variant = preset.split("@", 1)
    name = preset + ("@" + variant if variant else "")
    bundle = os.path.join(play_dir(), name + ".json")
    effects = os.path.join(game_root(), "assets", "effects")
    watched = [os.path.join(effects, preset + ".json")]
    parts = os.path.join("assets", "effects", "parts")
    kept_root = kept_root or effects     # (kit vfx play --kept: a made preset's kept files are not in the effects folder)
    named = {"files": None}             # the kept files THIS preset names (another session's plan is not ours to reload for)

    def kept_paths():
        if named["files"] is None:
            try:
                with open(bundle, encoding="utf-8") as fh:
                    b = json.load(fh)
                named["files"] = [os.path.join(kept_root, folder, name + ".json") for folder, _, _ in KEPT for name in (b.get(folder) or {})]
            except (OSError, ValueError, AttributeError):
                return []
        return named["files"]

    def stamp():
        files = list(watched) + ([os.path.join(parts, f) for f in os.listdir(parts)] if os.path.isdir(parts) else [])
        files += kept_paths()
        return tuple((f, os.path.getmtime(f)) for f in files if os.path.isfile(f))

    last = stamp()
    while not s.done.is_set():
        time.sleep(0.5)
        try:
            now = stamp()
        except OSError:
            continue
        if now == last:
            continue
        last = now
        try:
            with open(bundle, encoding="utf-8") as fh:
                b = json.load(fh)
            if os.path.isfile(watched[0]):
                args = ["lune", "run", "kit", "vfx", "expand", preset] + (["--variant", variant] if variant else [])
                r = subprocess.run(args, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
                if r.returncode != 0 or not r.stdout.strip().startswith("{"):
                    s.watch_state["error"] = (r.stderr or r.stdout or "expand failed").strip()[:300]
                    continue
                expanded = json.loads(r.stdout)
                b["preset"] = expanded
            else:
                # a preset that is not in the effects folder (an animatic, a made preset played from build/): there
                # is nothing to expand again - what changed is a kept file it names, read again below
                expanded = b.get("preset")
            fresh, bad = kept_files(expanded, kept_root)
            for folder, files in fresh.items():
                if files:
                    b[folder] = dict(b.get(folder) or {}, **files)
            with open(bundle, "w", encoding="utf-8") as fh:
                json.dump(b, fh)
            named["files"] = None       # (the preset may name other kept files now)
            last = stamp()
            s.watch_state["reloads"] += 1
            s.watch_state["error"] = ("kept files not reloaded: " + "; ".join(bad))[:300] if bad else None
        except Exception as e:  # noqa: BLE001
            s.watch_state["error"] = f"{type(e).__name__}: {e}"[:300]


def serve(name, port, out, crop, fps, job, focus=True):
    s = Session(name, out, crop, fps, focus)
    s.job = job
    s.watch_state = {"preset": job.get("preset"), "reloads": 0, "error": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, text):
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(text.encode())

        # the browser player: /lib/* = kit/vfx/player (+ vendor), /play/* /textures/* /sounds/* = build/vfx/play, build/textures, build/sounds
        STATIC = {"/lib/": "kit/vfx/player", "/play/": play_dir(), "/textures/": "build/textures", "/sounds/": "build/sounds",
                  "/refs/": "assets/effects/refs", "/booth/": "build/vfx/booth"}

        def static(self, path):
            for prefix, root in self.STATIC.items():
                if path.startswith(prefix):
                    rel = os.path.normpath(path[len(prefix):]).replace("\\", "/")
                    if rel.startswith("..") or os.path.isabs(rel):
                        return self.reply(404, "nope")
                    if ":" in rel:  # (a drive-relative "C:x" passes normpath / isabs and escapes the root - review 2026-11-10)
                        return self.reply(404, "nope")
                    full = os.path.join(root, rel)
                    if not os.path.isfile(full) and prefix in ("/textures/", "/sounds/") and game_root():
                        full = os.path.join(game_root(), root, rel)  # a game's own build (Config.build), after the project's
                    if not os.path.isfile(full):
                        return self.reply(404, f"no {path}")
                    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                    if full.endswith(".js"):
                        ctype = "text/javascript"
                    with open(full, "rb") as fh:
                        data = fh.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return None
            return self.reply(404, "?")

        def do_POST(self):  # noqa: N802
            u = urlparse(self.path)
            # only the kit's own page may POST (it writes preset files): a page on another origin gets 403 — the
            # browser sends Origin on every cross-site POST, and a same-origin fetch sends 127.0.0.1 / localhost
            origin = self.headers.get("Origin") or ""
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost") or (origin and not re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origin)):
                self.reply(403, "cross-origin POST refused")
                return
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            try:
                if u.path == "/preset":
                    # the viewer's inspector writes ONE field of ONE layer back to the file it came from (the preset,
                    # or a part under assets/effects/parts); the watcher then re-expands and the page reloads
                    req = json.loads(body.decode("utf-8"))
                    self.reply(200, json.dumps(save_layer_field(req)))
                    return
                if u.path == "/frame":
                    q = {k: v[0] for k, v in parse_qs(u.query).items()}
                    data = body.decode("ascii", "ignore")
                    ext = "jpg" if data.startswith("data:image/jpeg") else "png"
                    if "," in data[:40]:
                        data = data.split(",", 1)[1]
                    raw = base64.b64decode(data)
                    if q.get("fps"):
                        s.video_fps = int(float(q["fps"]))  # the page's video rate (a slow pass keeps it: the clock steps slower, the video does not)
                    path = s.frame_png(q.get("view", "main"), int(q.get("i", 0)), float(q.get("t", 0)), raw, ext, q.get("tag"))
                    self.reply(200, path)
                elif u.path == "/metrics":
                    incoming = json.loads(body.decode("utf-8"))
                    with s.lock:  # one POST per view: merge them
                        if s.metrics is None:
                            s.metrics = incoming
                        else:
                            s.metrics.setdefault("views", {}).update(incoming.get("views", {}))
                    with open(os.path.join(s.out, f"{s.name}.metrics.json"), "w", encoding="utf-8") as fh:
                        json.dump(s.metrics, fh, indent=1)
                    self.reply(200, "ok")
                else:
                    self.reply(404, "?")
            except Exception as e:  # noqa: BLE001
                self.reply(500, f"{type(e).__name__}: {e}")

        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/ping":
                    self.reply(200, "pong")
                elif u.path.startswith(("/lib/", "/play/", "/textures/", "/sounds/", "/refs/", "/booth/")):
                    self.static(u.path)
                elif u.path == "/bundles":
                    base = re.sub(r"@.*$", "", q.get("name", ""))
                    d = play_dir()
                    names = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json") and (f[:-5] == base or f.startswith(base + "@"))) if os.path.isdir(d) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", base) else []
                    self.reply(200, json.dumps(names))
                elif u.path == "/version":
                    # the bundle's mtime: the page polls it and reloads the preset when the watcher rewrote the bundle
                    nm = q.get("name", "")
                    b = os.path.join(play_dir(), nm + ".json") if re.fullmatch(r"[A-Za-z0-9_@-]{1,80}", nm) else None
                    self.reply(200, json.dumps({"mtime": os.path.getmtime(b) if b and os.path.isfile(b) else 0, "watch": s.watch_state}))
                elif u.path == "/list":
                    # files under one of the static roots (the reference panel, the booth's frames); names only
                    rel = os.path.normpath(q.get("dir", "")).replace(chr(92), "/")
                    root = {"refs": "assets/effects/refs", "booth": "build/vfx/booth"}.get(rel.split("/")[0])
                    sub = "/".join(rel.split("/")[1:])
                    full = os.path.join(root, sub) if root and ".." not in rel else None
                    if not full or not os.path.isdir(full):
                        self.reply(200, json.dumps([]))
                    else:
                        self.reply(200, json.dumps(sorted(f for f in os.listdir(full) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")))))
                elif u.path == "/done":
                    self.reply(200, "bye")
                    s.done.set()
                else:
                    self.reply(404, "?")
            except Exception as e:  # noqa: BLE001
                self.reply(500, f"{type(e).__name__}: {e}")

    # threaded + a deep listen queue: the browser player posts frames in bursts; the single-threaded server with the
    # default backlog of 5 dropped connects (measured: ERR_CONNECTION_TIMED_OUT after ~275 frames)
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer.daemon_threads = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    if job.get("preset"):
        threading.Thread(target=watch_preset, args=(s, job["preset"], job.get("variant"), job.get("kept")), daemon=True).start()
    print(f"capture server on 127.0.0.1:{port} for {name}", file=sys.stderr, flush=True)
    # serve until the page says /done. A plain viewer session never times out (the owner keeps it open for hours);
    # once a recording or a bake has started, 30 minutes without /done is a failure (a stalled page).
    started = None
    while True:
        if s.done.wait(timeout=20):
            finished = True
            break
        active = bool(s.frames) or getattr(s, "tagged", 0) > 0
        if active and started is None:
            started = time.time()
        if started is not None and time.time() - started > 1800:
            finished = False
            break
    httpd.shutdown()
    sheets = s.finish()
    tagged = getattr(s, "tagged", 0)  # the bake of impact frames posts tagged stills, no sheet, no metrics
    ok = finished and (bool(sheets) or s.metrics is not None or tagged > 0)
    print(json.dumps({
        "schema": 1,
        "status": "pass" if ok else "fail",
        "summary": (f"{tagged} impact frame(s) baked" if tagged and not sheets else f"{sum(x['frames'] for x in sheets if x['view'] != 'all')} frame(s) captured in {len([x for x in sheets if x['view'] != 'all'])} view(s)") if ok else "no /done within 15 min (did the booth bundle run in Studio?)",
        "next_action": f"LOOK at {', '.join(x['sheet'] for x in sheets)}" if ok else "run the booth bundle in Studio (Studio MCP execute_luau, Edit)",
        "sheets": sheets,
        "metrics": os.path.join(out, f"{name}.metrics.json").replace("\\", "/") if s.metrics is not None else None,
    }))
    return 0 if ok else 1


def _answer(path, wait):
    """the script's answer the session saved at `path` (one JSON line) -> (answer or None, why). A "started" /
    "running" line is not the answer yet (the run was still going): it keeps waiting for the collected one"""
    deadline, last = time.time() + wait, None
    while time.time() < deadline:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    got = json.loads(fh.read().strip() or "null")
            except (OSError, ValueError) as e:
                got, last = None, f"{path} is not one JSON line ({e})"
            if isinstance(got, dict) and got.get("status") not in ("started", "running", None):
                return got, None
            if isinstance(got, dict):
                last = f"{path} says the run is {got.get('status')}: run its .collect.luau again when it is over and save that line"
        time.sleep(1.0)
    return None, last or f"no answer saved as {path} within {int(wait)} s"


def studio(argv):
    """`capture.py studio`: a booth's pictures through the shared capture bridge (see the head of this file)"""
    opts = {"--out": "build/vfx/booth", "--crop": "0,0,0,0", "--wait": "900", "--result-wait": "600", "--fps": "30"}
    flags = {a for a in argv if a in ("--clip", "--held")}
    rest = [a for a in argv if a not in flags]
    for i in range(0, len(rest) - 1, 2):
        opts[rest[i]] = rest[i + 1]
    name, match, job_path = opts.get("--name"), opts.get("--match"), opts.get("--job")
    if not (name and match and job_path and os.path.isfile(job_path)):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "capture studio: --name, --match and an existing --job are needed",
                          "next_action": "lune run kit vfx booth <name> (or kit ui booth <Screen>) prints the command"}))
        return 2
    with open(job_path, encoding="utf-8") as fh:
        job = json.load(fh)
    out = opts["--out"]
    s = Session(name, out, studio_capture.parse_crop(opts["--crop"]), int(opts["--fps"]))
    s.job = job
    clip = "--clip" in flags or ("--held" not in flags and bool(job.get("screen")) and not job.get("states"))
    result_path = os.path.join(out, f"{name}.result.json")
    if os.path.isfile(result_path):
        os.remove(result_path)  # (a last run's answer: this run's own is waited for)
    print(f"capture studio {name}: watching {match} ({'a moving walk' if clip else 'a held walk'}); run the script now, "
          f"then save its answer line as {result_path.replace(chr(92), '/')}", file=sys.stderr, flush=True)
    wait = float(opts["--wait"])
    notes, pics = [], {}
    if clip:
        moments = sorted(float(m) for m in (job.get("moments") or [0, 0.15, 0.4, 1, 2]))
        got = studio_capture.watch_clip(match, moments, wait)
        walk = got["clip"]
        if walk.t0 is not None:
            for i, m, _rel, img in walk.frames():
                s.keep("engine", i + 1, m, img)
            notes.append(f"timed within {round(walk.worst() * 1000)} ms ({got['reads']} reads)")
        seen = walk.t0 is not None
    else:
        views = job.get("views") or ["player", "side", "hero", "cine"]
        n = len((job.get("states") or {}).get("moments") or []) or len(views) * len(job.get("moments") or [0] * 18)
        got = studio_capture.watch_walk(match, [str(k) for k in range(1, n + 2)], wait,
                                        lambda st, img, ok, _h: pics.__setitem__(int(st), (img, ok)), front=True)
        walk = got["walk"]
        seen = walk.started
    box = got["box"]
    width = (box[2] - box[0]) if box else 0
    why = got["why"] or (None if seen and walk.over else
                         ("no walk was seen: the script was not run in the scratch place (or its 3D view is not on screen)"
                          if not seen else "the walk did not end in time"))
    answer, answer_why = _answer(result_path, float(opts["--result-wait"]))
    missing, unsettled = [], []
    if not clip:
        grabs = (answer or {}).get("grabs") or []
        for g in grabs:
            k = int(g.get("k", 0))
            if k in pics:
                s.keep(str(g.get("view", "main")), int(g.get("i", k)), float(g.get("t", 0)), pics[k][0])
                if not pics[k][1]:
                    unsettled.append(f"{g.get('view')}#{g.get('i')}")
            else:
                missing.append(f"{g.get('view')}#{g.get('i')}")
        if answer is None and pics:  # (no answer to name them by: kept as they came, nothing lost)
            os.makedirs(os.path.join(out, name), exist_ok=True)
            for k, (img, _ok) in sorted(pics.items()):
                img.save(os.path.join(out, name, f"raw_{k:03d}.png"))
            notes.append(f"{len(pics)} unnamed picture(s) kept as {out}/{name}/raw_*.png")
    sheets = s.finish() if s.frames else []
    frames = sum(x["frames"] for x in sheets if x["view"] != "all")
    if answer and answer.get("stale_words"):
        notes.append(answer["stale_words"])
    if unsettled:
        notes.append("not held still for two reads: " + ", ".join(unsettled))
    ok = bool(frames) and not why and answer is not None and answer.get("status") == "pass" and not missing
    problems = [p for p in (why, answer_why, (answer or {}).get("error"),
                            ("not captured: " + ", ".join(missing)) if missing else None) if p]
    meta = {"place": got["place"], "box": list(box) if box else None, "front": got["front"], "answer": answer,
            "missing": missing, "unsettled": unsettled}
    with open(os.path.join(out, f"{name}.capture.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(json.dumps({
        "schema": 1,
        "status": "pass" if ok else "fail",
        "summary": f"{frames} frame(s) captured in Studio in {len([x for x in sheets if x['view'] != 'all'])} view(s), "
                   f"the 3D view {width} px wide"
                   + (f" (under {studio_capture.WANT_WIDTH}: the window and screen allow no more)"
                      if width and width < studio_capture.WANT_WIDTH else "")
                   + "".join(f"; {x}" for x in problems + notes),
        "next_action": f"LOOK at {', '.join(x['sheet'] for x in sheets)}" if ok else
        ("start this first, then run the run's .studio.luau through the Studio tools in the scratch place and save its "
         f"answer line as {result_path.replace(chr(92), '/')}"),
        "sheets": sheets,
        "capture": os.path.join(out, f"{name}.capture.json").replace("\\", "/"),
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "studio":
        sys.exit(studio(argv[1:]))
    if not argv or argv[0] != "serve":
        print(__doc__)
        sys.exit(2)
    opts = {"--name": "effect", "--port": "47811", "--out": "build/vfx/booth", "--fps": "30", "--crop": "0,0.05,0,0", "--focus": "1"}
    i = 1
    while i < len(argv):
        opts[argv[i]] = argv[i + 1]
        i += 2
    # --name names the run's outputs; --preset (default: the same) is the effect the booth plays
    job = {"name": opts.get("--preset", opts["--name"]), "port": int(opts["--port"])}
    if opts.get("--variant"):
        job["variant"] = opts["--variant"]
    if opts.get("--preset"):
        job["preset"] = opts["--preset"]  # the watcher re-expands this preset into the bundle on save (hot reload)
    if opts.get("--kept"):
        job["kept"] = opts["--kept"]
    views_path = "kit/vfx/views.json"
    if os.path.isfile(views_path):  # the shared camera views (the booth and the player read the same ones)
        with open(views_path, encoding="utf-8") as fh:
            job["viewDefs"] = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    if opts.get("--job") and os.path.isfile(opts["--job"]):
        with open(opts["--job"], encoding="utf-8") as fh:
            extra = json.load(fh)
        shared = job.get("viewDefs", {})
        shared.update(extra.pop("viewDefs", {}) or {})  # a preset's / a job's views override the shared ones
        job.update(extra)
        job["viewDefs"] = shared
    sys.exit(serve(opts["--name"], int(opts["--port"]), opts["--out"], [float(x) for x in opts["--crop"].split(",")], int(opts["--fps"]), job, opts["--focus"] != "0"))
