"""flow.py — a FLOW of screens as one film: the way a player moves between them (pros design the flow, not single
screens): each step a trigger, a transition and — the AAA touch — a SHARED ELEMENT that flies from one screen into the
next (the shop button's cart becomes the shop's title cart).

    python kit/ui/flow.py <Flow> [--ui assets/ui] [--models src/ui] [--build build/ui] [--library library/ui]

assets/ui/flows/<Flow>.json:
{
  "name": "SimShopFlow", "start": "SimHud",
  "steps": [
    {"from": "SimHud", "to": "SimShop", "on": "Hud.Menu.Shop", "transition": "shared",          (fade | push | shared)
     "shared": {"from": "Hud.Menu.Shop.Icon", "to": "Shop.Window.Title.Icon"}, "seconds": 0.5},
    {"from": "SimShop", "to": "SimHud", "on": "Shop.Window.Close", "transition": "fade"}
  ]
}
Checks: every screen is compiled, every "on" is a button on its "from" screen, every shared piece exists on its screen,
the flow can come back to its start (a menu with no way back is a trap). -> build/ui/flows/<Flow>.gif (the film) +
<Flow>.png (a strip), saved with the flow in library/ui/flows/<Flow>/. In game: Ui.go(from, to, {shared = {a, b}}).
"""
import argparse
import json
import math
import os
import shutil
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preview as P  # noqa: E402

TRANSITIONS = ("fade", "push", "shared")
BUTTONS = ("TextButton", "ImageButton")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def classes(model):
    """{root-relative path: ClassName} of a compiled screen"""
    out = {}

    def walk(inst, path):
        out[path] = inst.get("ClassName")
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def check(flow, models):
    """every problem with a flow (an empty list: good)"""
    bad = []
    steps = flow.get("steps") or []
    if not steps:
        bad.append("a flow needs \"steps\": [{\"from\", \"to\", \"on\", \"transition\"}]")
    start = flow.get("start") or (steps[0].get("from") if steps else None)
    for i, st in enumerate(steps):
        at = f"steps[{i}]"
        for k in ("from", "to"):
            if st.get(k) not in models:
                bad.append(f"{at}.{k}: no compiled screen '{st.get(k)}' (lune run kit ui)")
        tr = st.get("transition", "fade")
        if tr not in TRANSITIONS:
            bad.append(f"{at}.transition: {tr} is not one of {', '.join(TRANSITIONS)}")
        fm, tm = models.get(st.get("from")), models.get(st.get("to"))
        if fm is not None and st.get("on") is not None:
            cls = classes(fm).get(st["on"])
            if cls is None:
                bad.append(f"{at}.on: no node '{st['on']}' on {st['from']}")
            elif cls not in BUTTONS:
                bad.append(f"{at}.on: '{st['on']}' is a {cls}, not a button the player can press")
        if tr == "shared":
            sh = st.get("shared") or {}
            if fm is not None and sh.get("from") not in classes(fm):
                bad.append(f"{at}.shared.from: no node '{sh.get('from')}' on {st.get('from')}")
            if tm is not None and sh.get("to") not in classes(tm):
                bad.append(f"{at}.shared.to: no node '{sh.get('to')}' on {st.get('to')}")
    # a way back to the start from every screen the flow reaches
    edges = {}
    for st in steps:
        edges.setdefault(st.get("from"), set()).add(st.get("to"))
    reached = {s for st in steps for s in (st.get("from"), st.get("to"))}
    for s in sorted(x for x in reached if x):
        seen, todo = set(), [s]
        while todo:
            cur = todo.pop()
            for nxt in edges.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        if s != start and start not in seen:
            bad.append(f"{s}: no way back to {start} (a screen the player cannot leave is a trap: add a back / close step)")
    return bad


def ease(k):
    return 1 - (1 - k) ** 3


def film(flow, models, scale=0.5, fps=20, hold=0.6):
    """the flow as frames: each step holds its screen, plays its transition, lands on the next"""
    frames = []
    shots = {}

    def shot(name):
        if name not in shots:
            im, _ = P.draw_viewport(models[name], 1920, 1080, "desktop")
            shots[name] = (im.convert("RGB"), dict(P.ALL_BOXES))
        return shots[name]

    def add(im, n=1):
        small = im.resize((int(1920 * scale), int(1080 * scale)), Image.LANCZOS)
        frames.extend([small] * n)

    for st in flow.get("steps") or []:
        a, abox = shot(st["from"])
        b, bbox = shot(st["to"])
        held = a.copy()
        if st.get("on") in abox:  # (the press: the trigger ringed for a beat)
            x, y, w, h = abox[st["on"]]
            ImageDraw.Draw(held).rounded_rectangle([x - 6, y - 6, x + w + 6, y + h + 6], radius=10, outline=(255, 255, 255), width=5)
        add(a, int(hold * fps * 0.6))
        add(held, int(hold * fps * 0.4))
        n = max(2, int(float(st.get("seconds", 0.5)) * fps))
        tr = st.get("transition", "fade")
        sh = st.get("shared") or {}
        piece = None
        if tr == "shared" and sh.get("from") in abox and sh.get("to") in bbox:
            fx_, fy_, fw_, fh_ = abox[sh["from"]]
            piece = a.crop((int(fx_), int(fy_), int(fx_ + fw_), int(fy_ + fh_)))
        for i in range(1, n + 1):
            k = ease(i / n)
            if tr == "push":
                im = Image.new("RGB", (1920, 1080))
                im.paste(a, (int(-1920 * k), 0))
                im.paste(b, (int(1920 * (1 - k)), 0))
            else:
                im = Image.blend(a, b, k)
            if piece is not None:
                (fx_, fy_, fw_, fh_), (tx_, ty_, tw_, th_) = abox[sh["from"]], bbox[sh["to"]]
                cx = fx_ + (tx_ - fx_) * k
                cy = fy_ + (ty_ - fy_) * k - math.sin(math.pi * k) * 120  # (an arc, not a slide: it is THROWN)
                cw = max(1, int(fw_ + (tw_ - fw_) * k))
                ch = max(1, int(fh_ + (th_ - fh_) * k))
                im.paste(piece.resize((cw, ch), Image.LANCZOS), (int(cx), int(cy)))
            add(im)
        add(b, int(hold * fps))
    return frames


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("flow")
    ap.add_argument("--ui", default="assets/ui")
    ap.add_argument("--models", default="src/ui")
    ap.add_argument("--build", default="build/ui")
    ap.add_argument("--library", default="library/ui")
    a = ap.parse_args(argv)
    path = os.path.join(a.ui, "flows", f"{a.flow}.json")
    if not os.path.isfile(path):
        return emit("fail", f"flow: no {path}", "write it (the shape: top of kit/ui/flow.py)")
    with open(path, encoding="utf-8") as fh:
        flow = json.load(fh)
    names = {s for st in flow.get("steps") or [] for s in (st.get("from"), st.get("to")) if s}
    models = {}
    for n in names:
        mp = os.path.join(a.models, f"{n}.model.json")
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                models[n] = json.load(fh)
    bad = check(flow, models)
    if bad:
        return emit("fail", f"flow: {a.flow} - {len(bad)} problem(s)", bad[0], problems=bad)
    P.ART_DIR = os.path.join(a.build, "art")
    frames = film(flow, models)
    out_dir = os.path.join(a.build, "flows")
    os.makedirs(out_dir, exist_ok=True)
    gif = os.path.join(out_dir, f"{a.flow}.gif")
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for f in frames]
    pal[0].save(gif, save_all=True, append_images=pal[1:], duration=50, loop=0, disposal=2)
    pick = [frames[round(k * (len(frames) - 1) / 7)] for k in range(8)]
    fw, fh = pick[0].size
    strip = Image.new("RGB", (fw * 4 + 24, fh * 2 + 8), (36, 36, 40))
    for k, f in enumerate(pick):
        strip.paste(f, ((k % 4) * (fw + 8), (k // 4) * (fh + 8)))
    png = os.path.join(out_dir, f"{a.flow}.png")
    strip.save(png)
    lib = os.path.join(a.library, "flows", a.flow)
    os.makedirs(lib, exist_ok=True)
    shutil.copyfile(path, os.path.join(lib, "flow.json"))
    shutil.copyfile(gif, os.path.join(lib, "film.gif"))
    shutil.copyfile(png, os.path.join(lib, "strip.png"))
    return emit("pass", f"flow: {a.flow} - {len(flow['steps'])} step(s) over {len(names)} screen(s), {len(frames)} frames -> {gif}",
                f"LOOK at {png} and play {gif}: does the shared piece read as ONE object travelling? can the player always get back?",
                gif=gif.replace(chr(92), "/"), strip=png.replace(chr(92), "/"))


if __name__ == "__main__":
    sys.exit(main())
