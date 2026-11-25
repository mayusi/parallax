"""studio_model.py - a built model seen in ROBLOX STUDIO with no upload (the 3D methods audit's "not seen: no uploaded
mesh" rows: soft transparency, the engine's own light, run-time cost).

    python kit/tools/studio_model.py pack <asset> [--build <dir>] [--out <dir>] [--port 8766] [--tag <name>]
                                         [--at x,y,z] [--transparency <t>]
    python kit/tools/studio_model.py grab --match <place name> <out.png>

  pack  the asset's meshes (kit/blender/studio_pack.py: every group's triangles in Roblox's axes, out of its .blend)
        and its maps as raw RGBA (an EditableImage takes 1024 px a side at most: a larger map is shrunk, and said),
        with model.json (every group set the way the game sets it: kit/lib/models.luau) and load.luau (the loader,
        kit/studio/model_load.luau, its settings filled in) -> <out> (default <build>/studio/<asset>). Then:
        `python -m http.server <port> --bind 127.0.0.1 --directory <out>` and run load.luau ONCE through the Studio
        tools (execute_luau, Edit) in a kit scratch place; never save it.
  grab  the Studio window whose place is --match, as it is on screen now (PrintWindow, kit/world/studio_shots.py:
        also when other windows cover it) -> <out.png>.
Prints one JSON line: {status, summary, next_action, ...}."""

import json
import math
import os
import shutil
import subprocess
import sys
import time

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import cad_check  # noqa: E402

MAX_SIDE = 1024           # an EditableImage's largest side (AssetService:CreateEditableImage)
SHOT_FOV = 30.0           # the shot's vertical field of view, degrees (a portrait lens: little perspective)
SHOT_FROM = (0.45, 0.25, -1.0)   # the shot looks from the model's FRONT (Roblox's -Z), a little right and above
SHOT_ROOM = 1.15          # the model's bounding sphere fills the view's height / this
HOLD, FLASH = 3.0, 1.0    # s: each view held (two agreeing reads are needed), each signal up (model_shot.luau)
SIGNALS = {"start": (255, 0, 255), "behind": (0, 255, 255), "end": (255, 255, 0)}
EDGE = 6                  # grey levels: a pixel that changed more than this when the model went away is the model's
IOU_BAR = 0.95
# where a model stands by default: high in open air, the sky alone behind it (review 2026-11-18: a model on a
# baseplate casts a shadow there, and the shadow would be taken for the model's own pixels)
OPEN_AIR = (0.0, 200.0, 0.0)            # the twin's silhouette must cover Studio's this well, or its camera / axes / place differ
MAPS = {"color": "ColorMap", "normal": "NormalMap", "rough": "RoughnessMap", "metal": "MetalnessMap",
        "emissive": "EmissiveMask"}   # (kit/lib/models.luau's MAPS + the emissive mask)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def resolve(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def raw_map(src, dest):
    """a PNG -> raw RGBA rows, top row first (an EditableImage's WritePixelsBuffer); -> (size, shrunk from or None)"""
    img = Image.open(src).convert("RGBA")
    was = img.size
    if max(was) > MAX_SIDE:
        k = MAX_SIDE / max(was)
        img = img.resize((max(1, round(was[0] * k)), max(1, round(was[1] * k))), Image.LANCZOS)
    with open(dest, "wb") as fh:
        fh.write(img.tobytes())
    return list(img.size), (list(was) if img.size != was else None)


def group_entry(group, entry, shrunk, out):
    """one group as the game sets it (kit/lib/models.luau) + its mesh file and its maps"""
    maps = {}
    for key, prop in MAPS.items():
        src = (entry.get("textures") or {}).get(key)
        if not src:
            continue
        file = f"{group}_{key}.rgba"
        size, was = raw_map(resolve(src), os.path.join(out, file))
        maps[prop] = {"file": file, "size": size}
        if was:
            shrunk.append(f"{group}.{key} {was[0]}x{was[1]} -> {size[0]}x{size[1]}")
    g = {"group": group, "mesh": f"mesh_{group}.json", "maps": maps,
         "size": entry.get("size_studs") or [1, 1, 1], "center": entry.get("center") or [0, 0, 0],
         "transparency": entry.get("transparency") or 0, "alpha_mode": entry.get("alpha_mode"),
         "alpha_soft": bool(entry.get("alpha_soft")), "collision_fidelity": entry.get("collision_fidelity"),
         "render_fidelity": entry.get("render_fidelity")}
    if "EmissiveMask" in maps:
        g["emissive_strength"] = entry.get("emissiveStrength") or 4
    return g


def lua_value(v):
    return "nil" if v is None else repr(float(v))


def framing(groups, fov=SHOT_FOV):
    """the shot's camera from the model's own boxes (the manifest's center +- size/2, model space, studs) -> (eye,
    target), both from the model's origin: the whole bounding sphere in the view's height, seen from SHOT_FROM"""
    lo = [min(g["center"][i] - g["size"][i] / 2.0 for g in groups) for i in range(3)]
    hi = [max(g["center"][i] + g["size"][i] / 2.0 for g in groups) for i in range(3)]
    mid = [(a + b) / 2.0 for a, b in zip(lo, hi)]
    radius = max(1e-3, math.dist(lo, hi) / 2.0)
    far = radius / math.sin(math.radians(fov) / 2.0) * SHOT_ROOM
    k = math.hypot(*SHOT_FROM)
    eye = [round(m + far * d / k, 4) for m, d in zip(mid, SHOT_FROM)]
    return eye, [round(m, 4) for m in mid]


class Watch:
    """the watcher of model_shot.luau's steps, fed one picture of the window at a time (pure: the test feeds it made
    pictures). MAGENTA gives the 3D view's box; after it, the first view two reads agree on is the MODEL; after CYAN
    the first agreed view is what is BEHIND it; YELLOW ends. -> .state ("start", "model", "behind", "end", "done")"""

    def __init__(self, flash_box, differ, agree=0.5):
        self.flash_box, self.differ, self.agree = flash_box, differ, agree
        self.state, self.box, self.last, self.views = "start", None, None, {}

    def _signal(self, img, name):
        return self.flash_box(img, SIGNALS[name], min_size=(300, 200), fill=0.8)

    def feed(self, img):
        if self.state == "start":
            box = self._signal(img, "start")
            if box:
                self.box, self.state = box, "model"
            return self.state
        if self.state in ("model", "behind"):
            if self._signal(img, "start" if self.state == "model" else "behind"):
                self.last = None                         # (the signal is still up)
                return self.state
            later = "behind" if self.state == "model" else "end"
            if self._signal(img, later):                 # (the next signal came before two reads agreed: the
                self.state = "lost"                      #  hold was too short - nothing is taken from a signal)
                return self.state
            view = img.crop(self.box)
            if self.last is not None and self.differ(self.last, view) < self.agree:
                self.views[self.state] = view
                self.state = "end" if self.state == "behind" else "after_model"
            self.last = view
            return self.state
        if self.state == "after_model":
            if self._signal(img, "behind"):
                self.state, self.last = "behind", None
            return self.state
        if self.state == "end" and self._signal(img, "end"):
            self.state = "done"
        return self.state


def model_mask(view, behind):
    """the model's own pixels: where the view changed by more than EDGE grey levels when it was taken away"""
    from PIL import ImageChops  # noqa: PLC0415

    return ImageChops.difference(view.convert("RGB"), behind.convert("RGB")).convert("L").point(
        lambda v: 255 if v > EDGE else 0)


def compare(studio, mask, twin):
    """Studio's view + its model mask beside the Blender twin (RGBA, its alpha the model) -> {iou, studio_mean,
    twin_mean, lum_ratio (twin / Studio, over the pixels both call the model), studio_spread / twin_spread (the
    model's 90th - 10th luminance percentile: how hard its light and shade differ)}"""
    import numpy as np  # noqa: PLC0415

    s = np.asarray(studio.convert("RGB"), float)
    m = np.asarray(mask.convert("L")) > 127
    t = np.asarray(twin.convert("RGBA"), float)
    tm = t[..., 3] > 127
    both = m & tm
    union = (m | tm).sum()
    out = {"iou": round(float(both.sum() / union), 4) if union else 0.0, "studio_px": int(m.sum()),
           "twin_px": int(tm.sum())}
    if both.sum() == 0:
        return out
    lum = np.array([0.2126, 0.7152, 0.0722])
    sl, tl = s[both] @ lum, t[..., :3][both] @ lum
    out.update({"studio_mean": [round(float(v), 1) for v in s[both].mean(0)],
                "twin_mean": [round(float(v), 1) for v in t[..., :3][both].mean(0)],
                "lum_ratio": round(float(tl.mean() / max(sl.mean(), 1e-6)), 3),
                "studio_spread": round(float(np.percentile(sl, 90) - np.percentile(sl, 10)), 1),
                "twin_spread": round(float(np.percentile(tl, 90) - np.percentile(tl, 10)), 1)})
    return out


def _studio_shots():
    sys.path.insert(0, os.path.join(ROOT, "kit", "world"))
    import studio_shots  # noqa: PLC0415  (the world lane's window reader, used as it is)

    return studio_shots


def shot(argv):
    """watch model_shot.luau's steps in the scratch place's window -> <dir>/model.png, behind.png, mask.png, shot.json"""
    ss = _studio_shots()
    match, dest = flag(argv, "--match"), argv[-1]
    wait = float(flag(argv, "--wait", "60"))
    if not match:
        return emit("fail", "studio_model shot: --match <the scratch place's name>", "name the place")
    handle, why = ss.pick_window(ss.top_windows(), match)
    if not handle:
        return emit("fail", f"studio_model shot: {why}", "open the scratch place in its own Studio window")
    w = Watch(ss.flash_box, ss.differ)
    t0 = time.time()
    while w.state not in ("done", "lost") and time.time() - t0 < wait:
        w.feed(ss.grab(handle))
        time.sleep(0.15)
    if w.state != "done" or "model" not in w.views or "behind" not in w.views:
        return emit("fail", f"studio_model shot: the walk stopped at '{w.state}' after {wait:g} s",
                    "start this watcher first, then run the model's shot.luau through the Studio tools within "
                    f"{wait:g} s; keep the scratch place's window maximised")
    os.makedirs(dest, exist_ok=True)
    w.views["model"].save(os.path.join(dest, "model.png"))
    w.views["behind"].save(os.path.join(dest, "behind.png"))
    mask = model_mask(w.views["model"], w.views["behind"])
    mask.save(os.path.join(dest, "mask.png"))
    box = mask.getbbox()
    vw, vh = w.views["model"].size
    cut = bool(box) and (box[0] == 0 or box[1] == 0 or box[2] == vw or box[3] == vh)
    info = {"view": [vw, vh], "window_box": list(w.box), "model_box": list(box) if box else None, "cut_off": cut}
    with open(os.path.join(dest, "shot.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    if not box:
        return emit("fail", "studio_model shot: nothing changed when the model was taken away - it was not in view",
                    "frame it (pack --fov, or eye/target given to shot.luau) and shoot again", **info)
    return emit("pass", f"studio_model shot: {vw}x{vh} view, the model {box[2] - box[0]}x{box[3] - box[1]} px"
                + (" - CUT OFF by the view's edge" if cut else ""),
                f"save shot.luau's returned line as {dest}/look.json, then: python kit/tools/studio_model.py twin "
                f"<asset> {dest}", **info)


def twin(argv):
    """the Blender twin of a shot (kit/blender/studio_twin.py) and the comparison -> <dir>/twin.png, pair.png,
    twin.json; fails when the twin's silhouette misses Studio's (IOU_BAR)"""
    from PIL import Image  # noqa: PLC0415

    asset, dest = argv[0], resolve(argv[1])
    build = resolve(flag(argv, "--build") or os.environ.get("KIT_BUILD") or "build")
    need = [os.path.join(dest, f) for f in ("look.json", "model.png", "mask.png")]
    need += [os.path.join(build, "models", f"{asset}{x}") for x in (".manifest.json", ".blend")]
    gone = [os.path.relpath(p, ROOT) for p in need if not os.path.isfile(p)]
    if gone:
        return emit("fail", f"studio_model twin: missing {', '.join(gone)}",
                    "shoot it first (shot.luau + studio_model.py shot) and save shot.luau's line as look.json")
    blender = cad_check.blender()
    out = os.path.join(dest, "twin.png")
    # the twin is drawn at the size the shot's view came out on the screen (a scaled display gives the window more
    # pixels than Roblox's ViewportSize says; the vertical field of view holds either way)
    with open(need[0], encoding="utf-8") as fh:
        look = json.load(fh)
    shot_info = os.path.join(dest, "shot.json")
    if os.path.isfile(shot_info):
        with open(shot_info, encoding="utf-8") as fh:
            look["camera"]["viewport"] = json.load(fh)["view"]
    render_look = os.path.join(dest, "look_render.json")
    with open(render_look, "w", encoding="utf-8") as fh:
        json.dump(look, fh)
    r = subprocess.run([blender, "-b", need[4], "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "blender", "studio_twin.py"), "--", need[3], render_look, out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    line = next((x for x in r.stdout.splitlines() if x.startswith("TWIN ")), None)
    if r.returncode != 0 or not line or not os.path.isfile(out):
        return emit("fail", f"studio_model twin: the Blender twin failed: {(r.stderr or r.stdout)[-400:]}",
                    "read the error; the asset's .blend and manifest must be the same build")
    rendered = json.loads(line[5:])
    studio, mask, tw = (Image.open(os.path.join(dest, f)) for f in ("model.png", "mask.png", "twin.png"))
    if tw.size != studio.size:
        return emit("fail", f"studio_model twin: the twin is {tw.size}, the shot {studio.size}",
                    "the look.json's viewport must be the shot's view")
    c = compare(studio, mask, tw)
    box = mask.getbbox() or (0, 0, studio.size[0], studio.size[1])
    pad = 24
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(studio.size[0], box[2] + pad), min(studio.size[1], box[3] + pad))
    flat = Image.new("RGB", tw.size, (255, 255, 255))
    flat.paste(tw, mask=tw.convert("RGBA").split()[3])
    a, b = studio.convert("RGB").crop(box), flat.crop(box)
    pair = Image.new("RGB", (a.size[0] * 2 + 12, a.size[1]), (255, 255, 255))
    pair.paste(a, (0, 0))
    pair.paste(b, (a.size[0] + 12, 0))
    pair.save(os.path.join(dest, "pair.png"))
    record = {"asset": asset, **c, "light": rendered.get("light"), "view_transform": rendered.get("view_transform")}
    with open(os.path.join(dest, "twin.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    rel = os.path.relpath(dest, ROOT).replace("\\", "/")
    if c["iou"] < IOU_BAR:
        return emit("fail", f"studio_model twin {asset}: the twin's silhouette covers Studio's {c['iou']:.0%} (under "
                    f"{IOU_BAR:.0%}): its camera, axes or place differ from the shot's", f"look at {rel}/pair.png", **record)
    return emit("pass", f"studio_model twin {asset}: silhouettes agree ({c['iou']:.1%}); Blender's light is "
                f"{c.get('lum_ratio', 0):.2f} x Studio's brightness on the model, its light-to-shade spread "
                f"{c.get('twin_spread')} against Studio's {c.get('studio_spread')}",
                f"look at {rel}/pair.png (Studio left, the Blender twin right)", **record)


def pack(argv):
    asset = argv[0]
    build = resolve(flag(argv, "--build") or os.environ.get("KIT_BUILD") or "build")
    manifest = os.path.join(build, "models", f"{asset}.manifest.json")
    blend = os.path.join(build, "models", f"{asset}.blend")
    for need in (manifest, blend):
        if not os.path.isfile(need):
            return emit("fail", f"studio_model pack: {os.path.relpath(need, ROOT)} not found",
                        f"build {asset} first (lune run kit asset {asset})")
    out = resolve(flag(argv, "--out") or os.path.join(build, "studio", asset))
    # (only a folder this command made is emptied: --out . or --out build must never delete the checkout or the build)
    if os.path.isdir(out) and os.listdir(out) and not os.path.isfile(os.path.join(out, "model.json")):
        return emit("fail", f"studio_model pack: {os.path.relpath(out, ROOT)} holds files this command did not write",
                    "name an empty folder (or leave --out out: build/studio/<asset>)")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    blender = cad_check.blender()
    if not blender or not os.path.isfile(blender):
        return emit("fail", "studio_model pack: Blender not found", "install Blender (VETLOG.md)")
    r = subprocess.run([blender, "-b", blend, "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "blender", "studio_pack.py"), "--", manifest, out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    line = next((x for x in r.stdout.splitlines() if x.startswith("PACK ")), None)
    packed = json.loads(line[5:]) if line else None
    if r.returncode != 0 or not packed:
        why = f"groups with no object in the .blend: {packed['missing']}" if packed else (r.stderr or r.stdout)[-400:]
        return emit("fail", f"studio_model pack: {asset}: {why}", "rebuild the asset; its .blend and manifest differ")
    with open(manifest, encoding="utf-8") as fh:
        m = json.load(fh)
    shrunk = []
    groups = [group_entry(g, e, shrunk, out) for g, e in sorted(m["groups"].items(), key=lambda kv: kv[0] != "main")]
    with open(os.path.join(out, "model.json"), "w", encoding="utf-8") as fh:
        json.dump({"asset": asset, "build_id": m.get("build_id"), "groups": groups}, fh, indent=1)
    port = int(flag(argv, "--port", "8766"))
    at = [float(x) for x in (flag(argv, "--at") or ",".join(str(v) for v in OPEN_AIR)).split(",")]
    t = flag(argv, "--transparency")
    with open(os.path.join(ROOT, "kit", "studio", "model_load.luau"), encoding="utf-8") as fh:
        src = fh.read()
    for key, value in {"BASE": f"http://127.0.0.1:{port}", "NAME": asset, "TAG": flag(argv, "--tag") or
                       f"KitStudio_{asset}", "AT": ",".join(repr(x) for x in at),
                       "TRANSPARENCY": lua_value(t)}.items():
        src = src.replace("{{" + key + "}}", value)
    with open(os.path.join(out, "load.luau"), "w", encoding="utf-8") as fh:
        fh.write(src)
    fov = float(flag(argv, "--fov", str(SHOT_FOV)))
    eye, target = framing(groups, fov)
    with open(os.path.join(ROOT, "kit", "studio", "model_shot.luau"), encoding="utf-8") as fh:
        shot = fh.read()
    for key, value in {"TAG": flag(argv, "--tag") or f"KitStudio_{asset}", "EYE": ",".join(repr(x) for x in eye),
                       "TARGET": ",".join(repr(x) for x in target), "FOV": repr(fov), "HOLD": repr(HOLD),
                       "FLASH": repr(FLASH)}.items():
        shot = shot.replace("{{" + key + "}}", value)
    with open(os.path.join(out, "shot.luau"), "w", encoding="utf-8") as fh:
        fh.write(shot)
    with open(os.path.join(ROOT, "kit", "studio", "model_cost.luau"), encoding="utf-8") as fh:
        cost = fh.read().replace("{{TAG}}", flag(argv, "--tag") or f"KitStudio_{asset}")
    with open(os.path.join(out, "cost.luau"), "w", encoding="utf-8") as fh:
        fh.write(cost)
    tris = sum(g["tris"] for g in packed["groups"].values())
    rel = os.path.relpath(out, ROOT).replace("\\", "/")
    return emit("pass", f"studio_model pack {asset}: {len(groups)} groups, {tris:,} triangles"
                + (f"; maps shrunk to {MAX_SIDE}: {', '.join(shrunk)}" if shrunk else ""),
                f"python -m http.server {port} --bind 127.0.0.1 --directory {rel} (in the background), then run "
                f"{rel}/load.luau ONCE through the Studio tools (execute_luau, Edit) in a kit scratch place; never save",
                out=rel, groups=packed["groups"], shrunk=shrunk)


def grab(argv):
    studio_shots = _studio_shots()
    match, dest = flag(argv, "--match"), argv[-1]
    if not match:
        return emit("fail", "studio_model grab: --match <the scratch place's name>", "name the place")
    handle, why = studio_shots.pick_window(studio_shots.top_windows(), match)
    if not handle:
        return emit("fail", f"studio_model grab: {why}", "open the scratch place in its own Studio window")
    # Roblox's light lands over a few frames: kept once two reads 0.4 s apart agree (the world's capture does the same)
    img, tries = studio_shots.grab(handle), 0
    while tries < 20:
        time.sleep(0.4)
        again = studio_shots.grab(handle)
        tries += 1
        if studio_shots.differ(img, again) < 0.5:
            img = again
            break
        img = again
    if studio_shots.blank(img) or min(img.size) < 200:
        return emit("fail", f"studio_model grab: the window gave a {img.size[0]}x{img.size[1]} picture with nothing in "
                    "it (minimised?)", "maximise the scratch place's window (ShowWindow 3), then grab again")
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    img.save(dest)
    return emit("pass", f"studio_model grab: {img.size[0]}x{img.size[1]} -> {dest}", "look at it, beside the build's own look")


COMMANDS = {"pack": pack, "grab": grab, "shot": shot, "twin": twin}


def main(argv):
    if not argv or argv[0] not in COMMANDS or len(argv) < 2:
        return emit("fail", "studio_model: pack <asset> | shot --match <place> <dir> | twin <asset> <dir> | grab "
                    "--match <place> <out.png>", "see this file's header")
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
