"""studio_capture.py - the kit's ONE way to see and hear from Roblox Studio without a network (the shared capture
bridge, card 4s96). A script run through the Studio tools (execute_luau, the Edit datamodel) cannot call a local
server (measured 2026-11-12: "HttpService request denied: domain 127.0.0.1:<port> is not in the Assistant HTTP
allowlist"), so the two sides agree by what is ON SCREEN and by what the call RETURNS:

  * the Studio side (kit/studio/capture_bridge.luau) covers the 3D view with one plain colour for a moment:
    magenta = a walk starts (and where the 3D view sits in the window), one of six colours = a picture is coming
    (which one: its number, in sixes), cyan = over;
  * this side reads the place's OWN window (PrintWindow: also while other windows cover it; only the one Studio
    window whose place is --match, so another session's Studio is never read), brought to the front first (an
    unfocused Studio draws ~6 frames a second) and maximised when its 3D view could not be 1600 px wide otherwise;
    each picture is cut to the 3D view (the start colour's box);
  * the script's own answer (what it did, the times of its pictures) is the execute_luau call's RETURN value: a JSON
    line, from the run itself when it is short, else from a second call (<run>.collect.luau) once it is over.

    python kit/tools/studio_capture.py snippet <harness> --out <base> [--job <job.json>] [--set key=value ...]
        writes <base>.studio.luau (run it), <base>.install.luau (run it ONCE when the run answers status "install":
        it puts the kit's Studio harnesses into ServerStorage.KitStudioBridge) and <base>.collect.luau (the answer of
        a long run). Harnesses: vfx_booth, ui_booth, ui_playtest, ui_proof_v6 (see HARNESSES).
    python kit/tools/studio_capture.py watch <out_dir> --match <place> --count <n> [--wait 300] [--crop l,t,r,b]
        the pictures of one held walk -> <out_dir>/<k>.png (k = 1..) + capture.json
    python kit/tools/studio_capture.py windows [--match <place>]
Every command prints one JSON line: {status, summary, next_action, ...}. kit/world/studio_shots.py (kit world studio)
and kit/vfx/capture.py studio (kit vfx booth, kit ui booth) use the functions below in-process.
"""

import ctypes
import datetime
import json
import os
import re
import sys
import time

from PIL import ImageChops, ImageStat

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# the signals: one plain colour over the whole 3D view
START, END = (255, 0, 255), (0, 255, 255)
# "a picture is coming", and which: picture i (0-based) shows NEXTS[i % 6] (every pair differs by 127+ in a channel)
NEXTS = ((255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 128, 0), (128, 0, 255), (0, 128, 255))
WANT_WIDTH = 1600  # px: the 3D view a booth picture is cut from, when the window and the screen allow it (card 896p)
FLASH, HOLD = 0.6, 1.0  # s: a booth's signal up, a booth's picture held still (>= 3 reads at PAUSE)
PAUSE = 0.1  # s between two reads of the window (a held walk)

try:  # (Windows only: the tests of the pure parts import this file anywhere)
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.SetProcessDPIAware()
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
except (AttributeError, ImportError, OSError):
    user32 = gdi32 = PROC = wt = None


# ---------------------------------------------------------------- the pure parts
def place_of(title):
    """the place a Roblox Studio window shows, from its title ("<path or name>[.rbxlx] - Roblox Studio") -> its bare
    name, or None for a window that is not a Studio window with a place"""
    if not title.endswith(" - Roblox Studio"):
        return None
    stem = re.split(r"[\\/]", title[:-len(" - Roblox Studio")])[-1]
    return re.sub(r"\.rbxlx?$", "", stem, flags=re.I)


def pick_window(windows, match):
    """the ONE Roblox Studio window whose place IS `match` (its file's name; KitWorldScratch_Court is not
    KitWorldScratch_Courtyard) -> (handle, None), or (None, why): no Studio open, Studio open on other places only
    (they are named, never touched), or the place open twice"""
    studios = [(h, t) for h, t in windows if t.endswith("Roblox Studio")]
    hits = [(h, t) for h, t in studios if (place_of(t) or "").lower() == match.lower()]
    if len(hits) == 1:
        return hits[0][0], None
    if len(hits) > 1:
        return None, f"{len(hits)} Roblox Studio windows show the place {match}: close all but one"
    named = [place_of(t) for _, t in studios if place_of(t)]
    if not named:
        return None, "Roblox Studio is not open" if not studios else "Roblox Studio is open with no place"
    return None, (f"Roblox Studio is open on another place ({'; '.join(named)}), which is never touched; the scratch "
                  f"place ({match}) is not open")


def flash_box(img, colour, tol=14, min_size=(300, 200), fill=0.9):
    """where a picture is covered by one of the plain signal colours -> the box (left, top, right, bottom) of the
    pixels within `tol` of the colour, when it is at least min_size and at least `fill` of it is that colour (a
    plugin's own notice may sit over a corner); else None"""
    bands = img.convert("RGB").split()
    mask = None
    for band, want in zip(bands, colour):
        m = band.point(lambda v, want=want: 255 if abs(v - want) <= tol else 0)
        mask = m if mask is None else ImageChops.multiply(mask, m)
    box = mask.getbbox()
    if not box:
        return None
    w, h = box[2] - box[0], box[3] - box[1]
    if w < min_size[0] or h < min_size[1]:
        return None
    return box if ImageStat.Stat(mask.crop(box)).mean[0] / 255.0 >= fill else None


def signal(img):
    """which signal covers this picture of the 3D view -> ("start", None) | ("next", its colour's place in NEXTS) |
    ("end", None) | None"""
    w, h = img.size
    small = (max(1, min(300, w // 3)), max(1, min(200, h // 3)))
    for kind, colours in (("start", (START,)), ("end", (END,)), ("next", NEXTS)):
        for i, colour in enumerate(colours):
            if flash_box(img, colour, min_size=small, fill=0.8):
                return (kind, i if kind == "next" else None)
    return None


def differ(a, b):
    """how far two pictures are apart: the mean absolute difference of their small grey copies (0..255)"""
    if a.size != b.size:
        return 255.0
    small = (160, 90)
    return ImageStat.Stat(ImageChops.difference(a.convert("L").resize(small), b.convert("L").resize(small))).mean[0]


def blank(img):
    """a picture with nothing in it (a window that was minimised, a grab that failed): one flat colour"""
    lo, hi = img.convert("L").resize((160, 90)).getextrema()
    return hi - lo <= 2


def crop_box(size, frac):
    """the box a picture of the 3D view keeps when `frac` = (left, top, right, bottom) fractions of its sides are cut
    away (Studio's own view cube / tool strip) -> (left, top, right, bottom) in px; never empty"""
    w, h = size
    left, top, right, bottom = (max(0.0, min(0.49, float(f))) for f in frac)
    box = (int(w * left), int(h * top), int(round(w * (1 - right))), int(round(h * (1 - bottom))))
    return (box[0], box[1], max(box[0] + 1, box[2]), max(box[1] + 1, box[3]))


def parse_crop(text):
    """'l,t,r,b' -> four fractions (a missing or bad one is 0)"""
    out = []
    for part in (text or "").split(",")[:4]:
        try:
            out.append(float(part))
        except ValueError:
            out.append(0.0)
    return tuple(out + [0.0] * (4 - len(out)))


def needs_maximise(window_w, monitor_w, zoomed, want=WANT_WIDTH, chrome=420):
    """should the window be maximised so its 3D view can be `want` px wide? Studio's panels (Explorer, Properties,
    the tool strip) take ~`chrome` px beside the 3D view. Not when it is maximised already, nor when it already has
    the room, nor when the screen itself is no wider than the window (nothing to gain)"""
    if zoomed or window_w >= want + chrome:
        return False
    return monitor_w > window_w


def fingerprint(text):
    """FNV-1a (32 bit) of a text's UTF-8 bytes, carriage returns left out -> 8 hex digits. capture_bridge.luau's
    Bridge.fingerprint gives the same for a ModuleScript's Source: a place's copy of a module that differs from the
    repo's file is named (a place built before the module changed)"""
    h = 2166136261
    for b in text.encode("utf-8"):
        if b == 13:
            continue
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return "%08x" % h


def tree_print(model):
    """a compiled model's (Rojo .model.json) shape -> "<instances>:<fingerprint of every Class:Name, sorted>" (the root
    counts by its class alone: Rojo names it after its file). Bridge.treePrint gives the same for the instance tree a
    place built from it: a screen in the place that is not the file's is named"""
    names = []

    def walk(node, root):
        names.append(f"{node.get('ClassName', '')}:" + ("" if root else str(node.get("Name") or node.get("ClassName", ""))))
        for child in node.get("Children") or []:
            walk(child, False)

    walk(model, True)
    return f"{len(names)}:{fingerprint(chr(10).join(sorted(names)))}"


def long_string(text):
    """a Luau long string that holds `text` exactly ([==[ ... ]==] with as many = as it needs; its first newline is
    the bracket's own, so a text that starts with one keeps it)"""
    n = 0
    while ("]" + "=" * n + "]") in text:
        n += 1
    eq = "=" * n
    return f"[{eq}[\n{text}]{eq}]"


def lua_str(s):
    """a Luau string literal: JSON's quoting, with its \\uXXXX escapes (which Luau does not read) written Luau's way;
    letters outside ASCII stay as they are (a Luau source file is UTF-8)"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: "\\u{%s}" % m.group(1), json.dumps(str(s), ensure_ascii=False))


class Walk:
    """a held walk, one read of the 3D view at a time (no clock, no window: the tests drive it with pictures).
    feed(img) -> a list of (station, picture, settled) to save; .over when the end signal came. A station's signal
    says which station it is (its place in the list, in sixes), so a signal no read caught loses that one picture and
    nothing else: the next signal still names its own station."""

    def __init__(self, stations, tol=0.6):
        self.stations, self.tol = list(stations), tol
        self.started = self.over = False
        self.cur = None  # the station on screen (its index) once its signal has gone, until it is saved
        self.floor = 0  # the lowest index the next signal can mean (signals only ever go forward)
        self.prev = None  # the station the last signal named
        self.last = None  # the last clean read of the station on screen
        self.sig = None  # the signal the last read showed: a signal counts ONCE, however many reads see it

    def _flush(self, out):
        if self.cur is not None and self.last is not None:
            out.append((self.stations[self.cur], self.last, False))  # (its hold ended before two reads agreed)
        self.cur, self.last = None, None

    def feed(self, img):
        out = []
        sig = signal(img)
        edge, self.sig = sig != self.sig, sig
        if sig is not None and sig[0] == "start":
            if edge:
                self.started, self.over, self.cur, self.floor, self.last = True, False, None, 0, None
                self.prev = None
        elif not self.started or self.over:
            return out
        elif sig is not None and sig[0] == "next":
            if edge and self.prev is not None and sig[1] == self.prev % len(NEXTS):
                # the SAME station's signal read again (a read in between did not see it: a plugin's notice over the
                # view): it is still coming, and what was read in between was not its view
                if self.cur is not None:
                    self.last = None
            elif edge:
                self._flush(out)
                i = self.floor + (sig[1] - self.floor) % len(NEXTS)  # the first station from the floor up it can be
                if i < len(self.stations):
                    self.cur, self.floor, self.prev = i, i + 1, i
        elif sig is not None:  # (the end)
            if edge:
                self._flush(out)
                self.over = True
        elif self.cur is not None:
            if self.last is not None and differ(self.last, img) <= self.tol:
                out.append((self.stations[self.cur], img, True))
                self.cur, self.last = None, None
            else:
                self.last = img
        return out


class Clip:
    """a MOVING walk (a screen's arrival: it cannot be held still for a picture): magenta, then the go colour
    (NEXTS[0]) over the view while the script gets ready; the go colour leaves on the very frame the motion starts.
    Every read after that is timed from the moment it left (the middle of the last read that showed it and the first
    that did not: half that gap is the timing's error); for each wanted moment the read closest to it is kept.
    feed(img, at) with `at` a clock in seconds; .over at the end signal or once the last moment is passed by 0.5 s."""

    def __init__(self, moments, after=0.5):
        self.moments, self.after = [float(m) for m in moments], after
        self.started = self.armed = self.over = False
        self.t0 = self.go_last = None
        self.err = 0.0
        self.best = {}  # moment index -> (|off|, seconds after t0, picture)

    def feed(self, img, at):
        if self.over:
            return
        # (the signal covers the whole view: a quarter-size copy tells it as well, in a fraction of the time - a
        # moving walk is timed by how many reads a second there are)
        sig = signal(img.resize((max(1, img.width // 4), max(1, img.height // 4)), 0))
        if sig is not None and sig[0] == "start":
            self.started, self.armed, self.t0, self.best = True, False, None, {}
            return
        if not self.started:
            return
        if sig is not None and sig[0] == "end":
            self.over = True
            return
        if self.t0 is None:
            if sig is not None and sig[0] == "next" and sig[1] == 0:
                self.armed, self.go_last = True, at
            elif sig is None and self.armed:
                self.t0, self.err = (self.go_last + at) / 2.0, (at - self.go_last) / 2.0
                self._keep(img, at)
            return
        if sig is None:
            self._keep(img, at)
        if self.moments and at - self.t0 > max(self.moments) + self.after:
            self.over = True

    def _keep(self, img, at):
        rel = at - self.t0
        for i, m in enumerate(self.moments):
            off = abs(rel - m)
            if i not in self.best or off < self.best[i][0]:
                self.best[i] = (off, rel, img)

    def frames(self):
        """-> [(moment index, moment, seconds after t0 the picture was read, picture)] in the moments' order"""
        return [(i, self.moments[i], self.best[i][1], self.best[i][2]) for i in sorted(self.best)]

    def worst(self):
        """the largest timing error of a kept picture (s): its distance from its moment + the start's own error"""
        return max((b[0] for b in self.best.values()), default=0.0) + self.err


# ---------------------------------------------------------------- the window
def _text(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def _size(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def top_windows():
    """every visible top-level window -> [(handle, title)]"""
    if user32 is None:
        return []
    tops = []
    user32.EnumWindows(PROC(lambda h, _l: (tops.append((h, _text(h))) if user32.IsWindowVisible(h) else None) or True), 0)
    return [(h, t) for h, t in tops if t]


def dpi_scale(h):
    """the window's display scaling (1.0 = 100 %): Studio counts its 3D view in scaled px, a picture of it is in real ones"""
    try:
        return max(1.0, user32.GetDpiForWindow(h) / 96.0)
    except (AttributeError, OSError):
        return 1.0


def _monitor_width(h):
    class MI(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    mi = MI()
    mi.cbSize = ctypes.sizeof(MI)
    mon = user32.MonitorFromWindow(h, 2)  # MONITOR_DEFAULTTONEAREST
    if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return 0
    return mi.rcWork.right - mi.rcWork.left


def bring_to_front(h, want=WANT_WIDTH):
    """the window restored when minimised, maximised when its 3D view could not be `want` px wide otherwise
    (needs_maximise), then put in FRONT (a Studio window behind others draws ~6 frames a second: particles and motion
    fall behind the clock) -> what was done, as words"""
    done = []
    if user32.IsIconic(h):
        user32.ShowWindow(h, 9)  # SW_RESTORE
        done.append("restored")
    w, _ = _size(h)
    if needs_maximise(w, _monitor_width(h), bool(user32.IsZoomed(h)), want):
        user32.ShowWindow(h, 3)  # SW_MAXIMIZE
        done.append("maximised")
    # Windows lets a background process take the foreground only on its own input's thread: join it for the call
    fg = user32.GetForegroundWindow()
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    joined = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    user32.BringWindowToTop(h)
    ok = bool(user32.SetForegroundWindow(h))
    if not ok:
        user32.SwitchToThisWindow(h, True)
    if joined:
        user32.AttachThreadInput(me, other, False)
    done.append("in front" if ok or user32.GetForegroundWindow() == h else "NOT in front (Windows refused)")
    return ", ".join(done)


def grab(h):
    """the window's own picture, also while other windows cover it (PW_RENDERFULLCONTENT)"""
    from PIL import Image  # noqa: PLC0415

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    w, hh = _size(h)
    hdc = user32.GetWindowDC(h)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(h, mdc, 2)
    bih = BIH()
    bih.biSize = ctypes.sizeof(BIH)
    bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = w, -hh, 1, 32
    buf = ctypes.create_string_buffer(w * hh * 4)
    gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(h, hdc)
    return Image.frombuffer("RGBA", (w, hh), buf, "raw", "BGRA", 0, 1).convert("RGB")


# ---------------------------------------------------------------- the watches
def watch_walk(match, stations, wait, on_frame, pause=PAUSE, front=False, want=WANT_WIDTH):
    """read the --match place's window until a held walk is over (or `wait` s pass); every picture the walk keeps goes
    to on_frame(station, picture of the 3D view, settled, window handle). front: the window is brought to the front
    (bring_to_front) when first found and again when its walk starts. -> {walk, place, box, why, front}"""
    walk = Walk(stations)
    place, box, why, fronted = None, None, None, []
    deadline = time.time() + wait
    while time.time() < deadline and not walk.over:
        top, gone = pick_window(top_windows(), match)
        if top is None:
            why = gone
            time.sleep(1.0)
            continue
        why, place = None, _text(top)
        if front and not fronted:
            fronted.append(bring_to_front(top, want))
        if user32.IsIconic(top):
            why = f"the scratch place's Studio window is minimised ({place}): restore it"
            time.sleep(1.0)
            continue
        full = grab(top)
        if box is None or not walk.started:
            found = flash_box(full, START)  # (where the 3D view sits in the window: the start signal covers it)
            if found is None:
                time.sleep(pause)
                continue
            box = found
            if front and len(fronted) == 1:
                fronted.append(bring_to_front(top, want))
        view = full.crop(box)
        for station, img, ok in walk.feed(view):
            on_frame(station, img, ok, top)
        time.sleep(pause)
    return {"walk": walk, "place": place, "box": box, "why": why, "front": fronted}


def watch_clip(match, moments, wait, front=True, want=WANT_WIDTH):
    """read the --match place's window as fast as it can be read until a moving walk (Clip) is over -> {clip, place,
    box, why, front, reads}"""
    clip = Clip(moments)
    place, box, why, fronted, reads, top = None, None, None, [], 0, None
    deadline = time.time() + wait
    while time.time() < deadline and not clip.over:
        if top is None or not user32.IsWindow(top):  # (the window is found once: reads are what times the walk)
            top, gone = pick_window(top_windows(), match)
            if top is None:
                why = gone
                time.sleep(1.0)
                continue
            why, place = None, _text(top)
        if front and not fronted:
            fronted.append(bring_to_front(top, want))
        if user32.IsIconic(top):
            why = f"the scratch place's Studio window is minimised ({place}): restore it"
            time.sleep(1.0)
            continue
        at = time.perf_counter()
        full = grab(top)
        reads += 1
        if box is None or not clip.started:
            found = flash_box(full, START)
            if found is None:
                time.sleep(0.05)
                continue
            box = found
            if front and len(fronted) == 1:  # (again as the walk starts: a call into Studio may have taken the front)
                fronted.append(bring_to_front(top, want))
        clip.feed(full.crop(box), at)
    return {"clip": clip, "place": place, "box": box, "why": why, "front": fronted, "reads": reads}


# ---------------------------------------------------------------- the snippets (what a session runs in Studio)
# the kit's Studio harnesses: installed ONCE into ServerStorage.KitStudioBridge by <base>.install.luau (each carries
# its file's fingerprint as its Version: a run whose harness differs asks for the install again)
MODULES = {
    "Bridge": "kit/studio/capture_bridge.luau",
    "VfxBooth": "kit/vfx/booth.luau",
    "UiBooth": "kit/ui/booth.luau",
    "UiPlaytest": "kit/ui/playtest.luau",
    "UiProofV6": "kit/ui/proof_v6.luau",
}
HARNESSES = {  # id -> the harness module, the place's src/kit modules it uses, the place's screens it builds
    "vfx_booth": {"module": "VfxBooth", "kit": ["VfxStage", "VfxCompose"], "screens": []},
    "ui_booth": {"module": "UiBooth", "kit": ["Ui"], "screens": ["@screen"]},
    "ui_playtest": {"module": "UiPlaytest", "kit": ["Ui"], "screens": ["@screen"]},
    "ui_proof_v6": {"module": "UiProofV6", "kit": ["Ui"],
                    "screens": ["RushHud", "SimShop", "FieldHud", "RiffDamage", "SimHud", "styles/sim"]},
}


def kit_closure(names, kit_dir):
    """the src/kit modules `names` need, with every module they require by a relative path ("./X"), transitively"""
    seen, todo = [], list(names)
    while todo:
        name = todo.pop(0)
        path = os.path.join(kit_dir, name + ".luau")
        if name in seen or not os.path.isfile(path):
            continue
        seen.append(name)
        with open(path, encoding="utf-8") as fh:
            todo += re.findall(r'require\(\s*"\./([A-Za-z0-9_]+)"\s*\)', fh.read())
    return sorted(seen)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def snippets(harness, job, base, root=ROOT):
    """the three Luau files of one run -> {install, run, collect, job}: `job` (what the harness reads) gets the run's
    key, the collect file's path, the signal timing (capture = {flash, hold}) and the repo's fingerprints of what the
    place must hold (kitPrints: the src/kit modules the harness uses, transitively; screenPrints: its screens)"""
    spec = HARNESSES[harness]
    rel = os.path.relpath(base, root).replace("\\", "/") if os.path.isabs(base) else base.replace("\\", "/")
    job = dict(job)
    job.setdefault("key", re.sub(r"[^A-Za-z0-9_]", "_", os.path.basename(rel)))
    job.setdefault("capture", {"flash": FLASH, "hold": HOLD})  # (a UI job's own "hold" is its state's settle)
    job["collect"] = rel + ".collect.luau"
    kit_dir = os.path.join(root, "src", "kit")
    job["kitPrints"] = {n: fingerprint(_read(os.path.join(kit_dir, n + ".luau"))) for n in kit_closure(spec["kit"], kit_dir)}
    prints = {}
    for s in spec["screens"]:
        name = job.get("screen") if s == "@screen" else s
        path = os.path.join(root, "src", "ui", f"{name}.model.json") if name else None
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                prints[name] = tree_print(json.load(fh))
    job["screenPrints"] = prints
    need = ["Bridge", spec["module"]]
    sources = {n: _read(os.path.join(root, MODULES[n])) for n in need}
    versions = {n: fingerprint(sources[n]) for n in need}
    head = (f"-- {harness} run {job['key']}: generated by kit/tools/studio_capture.py - do not edit. Run it through the\n"
            "-- Studio tools (execute_luau, the Edit datamodel) in the kit's SCRATCH place only; never save the place.\n")
    install = [head.replace(" run ", " install ", 1),
               "-- It puts the kit's Studio harness into ServerStorage.KitStudioBridge (nothing else is touched).",
               'local ServerStorage = game:GetService("ServerStorage")',
               'local holder = ServerStorage:FindFirstChild("KitStudioBridge") or Instance.new("Folder")',
               'holder.Name = "KitStudioBridge"',
               "local function put(name: string, version: string, source: string)",
               "\tlocal old = holder:FindFirstChild(name)",
               "\tif old then", "\t\told:Destroy()", "\tend",
               '\tlocal m = Instance.new("ModuleScript")', "\tm.Name = name;",  # (";": the next line starts with "(")
               "\t(m :: any).Source = source", '\tm:SetAttribute("Version", version)', "\tm.Parent = holder", "end"]
    for n in need:
        install.append(f"put({lua_str(n)}, {lua_str(versions[n])}, {long_string(sources[n])})")
    install += ["holder.Parent = ServerStorage",
                f'return {lua_str("installed " + ", ".join(f"{n} {versions[n]}" for n in need) + "; now run " + rel + ".studio.luau again")}']
    answer = json.dumps({"status": "install", "summary": f"the place's Studio harness is missing or older: run {rel}.install.luau ONCE, then this again",
                         "next_action": f"run {rel}.install.luau through the Studio tools, then {rel}.studio.luau", "install": rel + ".install.luau"})
    run = [head,
           "local NEED = { " + ", ".join(f"{n} = {lua_str(versions[n])}" for n in need) + " }",
           'local holder = game:GetService("ServerStorage"):FindFirstChild("KitStudioBridge")',
           "local missing = {}",
           "for name, version in NEED do",
           "\tlocal m = holder and holder:FindFirstChild(name)",
           '\tif not (m and m:GetAttribute("Version") == version) then',
           "\t\ttable.insert(missing, name)", "\tend", "end",
           "if #missing > 0 then",
           f"\treturn {lua_str(answer)}",
           "end",
           f"local JOB = {long_string(json.dumps(job, ensure_ascii=False))}",
           f"return (require :: any)((holder :: Instance):FindFirstChild({lua_str(spec['module'])})).run(JOB)", ""]
    collect = [head.replace(" run ", " collect ", 1),
               "-- It returns the run's answer (one JSON line) once the run is over: save it where the capture asked.",
               'local holder = game:GetService("ServerStorage"):FindFirstChild("KitStudioBridge")',
               'local results = holder and holder:FindFirstChild("Results")',
               f"local got = results and results:FindFirstChild({lua_str(job['key'])})",
               "if got then", "\treturn (got :: StringValue).Value", "end",
               f"return {lua_str(json.dumps({'status': 'missing', 'summary': 'no answer of run ' + job['key'] + ' in this place: was its .studio.luau run here?'}))}", ""]
    return {"install": "\n".join(install) + "\n", "run": "\n".join(run), "collect": "\n".join(collect), "job": job}


def write_snippets(harness, job, base, root=ROOT):
    """snippets() written next to each other -> (the job as sent, {kind: path})"""
    got = snippets(harness, job, base, root)
    full = base if os.path.isabs(base) else os.path.join(root, base)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    paths = {}
    for kind, ext in (("run", ".studio.luau"), ("install", ".install.luau"), ("collect", ".collect.luau")):
        paths[kind] = full + ext
        with open(paths[kind], "w", encoding="utf-8", newline="\n") as fh:
            fh.write(got[kind])
    return got["job"], paths


# ---------------------------------------------------------------- the commands
def emit(status, summary, next_action, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def cmd_snippet(argv):
    harness = argv[0] if argv else ""
    base = _opt(argv, "--out")
    if harness not in HARNESSES or not base:
        return emit("fail", f"snippet: {harness or '(none)'}: harness one of {', '.join(HARNESSES)} and --out <base>",
                    "python kit/tools/studio_capture.py snippet <harness> --out <base> [--job <job.json>] [--set k=v]")
    job = {}
    if _opt(argv, "--job"):
        with open(_opt(argv, "--job"), encoding="utf-8") as fh:
            job = json.load(fh)
    for i, a in enumerate(argv):
        if a == "--set" and i + 1 < len(argv) and "=" in argv[i + 1]:
            k, v = argv[i + 1].split("=", 1)
            job[k] = _value(v)
    sent, paths = write_snippets(harness, job, base)
    rel = {k: os.path.relpath(p, ROOT).replace("\\", "/") for k, p in paths.items()}
    return emit("pass", f"{harness}: {rel['run']} ({os.path.getsize(paths['run'])} bytes)",
                f"run {rel['run']} through the Studio tools (execute_luau, Edit) in the scratch place; if it answers "
                f"status install, run {rel['install']} once first", files=rel, key=sent["key"])


def cmd_watch(argv):
    out, match = (argv[0] if argv else None), _opt(argv, "--match")
    if not out or not match or user32 is None:
        return emit("fail", "watch: <out_dir> --match <place> --count <n> (on the PC with Roblox Studio)",
                    "python kit/tools/studio_capture.py watch <out_dir> --match KitPlaytestScratch --count 1")
    n = int(_opt(argv, "--count", "1"))
    frac = parse_crop(_opt(argv, "--crop", "0,0,0,0"))
    os.makedirs(out, exist_ok=True)
    shots = {}

    def keep(station, img, ok, _h):
        img = img.crop(crop_box(img.size, frac))
        img.save(os.path.join(out, f"{station}.png"))
        shots[station] = {"file": f"{station}.png", "size": list(img.size), "settled": bool(ok)}

    got = watch_walk(match, [str(k) for k in range(1, n + 1)], float(_opt(argv, "--wait", "300")), keep, front=True)
    walk = got["walk"]
    why = got["why"] or (None if walk.over else ("no walk was seen" if not walk.started else "the walk did not end"))
    meta = {"place": got["place"], "box": list(got["box"]) if got["box"] else None, "front": got["front"],
            "when": datetime.datetime.now().isoformat(timespec="seconds"), "frames": shots, "why": why}
    with open(os.path.join(out, "capture.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    width = (got["box"][2] - got["box"][0]) if got["box"] else 0
    ok = walk.over and len(shots) == n
    return emit("pass" if ok else "fail",
                f"{len(shots)} of {n} picture(s) from {got['place'] or match}, the 3D view {width} px wide"
                + (f" (under {WANT_WIDTH}: the screen allows no more)" if width and width < WANT_WIDTH else "")
                + (f"; {why}" if why else ""),
                f"look at {out}" if ok else "start this first, then run the script in the scratch place", **meta)


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "snippet":
        return cmd_snippet(argv[1:])
    if cmd == "watch":
        return cmd_watch(argv[1:])
    if cmd == "windows":
        tops = top_windows()
        match = _opt(argv, "--match")
        hit, why = pick_window(tops, match) if match else (None, None)
        return emit("pass", f"{len([t for _, t in tops if t.endswith('Roblox Studio')])} Roblox Studio window(s)", "none",
                    studios=[t for _, t in tops if t.endswith("Roblox Studio")], open=hit is not None, why=why)
    return emit("fail", "usage: studio_capture.py snippet|watch|windows ... (see the file's head)", "read kit/tools/studio_capture.py")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
