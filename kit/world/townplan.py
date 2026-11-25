"""townplan.py - a TOWN'S PLAN from above, one labelled page a town: what `kit world town <Name>` shows.

The town-plan generator (kit/lib/worldtown.luau, a "town" step in a blueprint) lays out a square entered at its
corners, streets by rank, blocks, terraced lots and one landmark; the compiled world keeps each town's record
("towns" in build/worlds/<Name>.json). This draws it so a session - and the owner - can READ the layout before anything
is dressed: every street with its name and width, every lot shaded by its storeys with its door marked, the square,
the gates with the walk to the square in seconds, the landmark and the line of sight from the main gate that ends on
it, T-junctions / crossings / dead ends, and beside the plan the numbers and the kit of house types the town needs.

    python kit/world/townplan.py <compiled world.json> [--out build/worlds/town]

One JSON line: {status, summary, next_action, pages: [...]}. The numbers are for reading a layout, never a score.
"""

import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

PAGE = (1920, 1200)
PLAN_BOX = (40, 90, 1240, 1160)  # where the plan sits on the page (x0, y0, x1, y1)
BG = (22, 24, 29)
STREET = {"main": (78, 74, 66), "lane": (62, 62, 62), "alley": (50, 52, 56)}
BLOCK = (36, 38, 44)
SQUARE = (104, 96, 78)
# a lot is lighter the taller it stands (2, 3, 4+ storeys); the landmark is the one warm colour on the page
FLOORS = {1: (92, 98, 110), 2: (112, 118, 132), 3: (146, 152, 168), 4: (184, 190, 206)}
LANDMARK = (222, 166, 64)
INK = (232, 232, 236)
DIM = (150, 152, 160)
GATE = (96, 214, 130)
TEE = (236, 236, 240)
CROSSING = (240, 150, 60)
DEADEND = (232, 72, 72)
VIEW = (250, 214, 90)
STALL = (196, 176, 140)  # a market stall on the square
LAMP = (255, 190, 120)  # a lamp the town set itself
SPEED = 16.0  # the R6 walk, studs a second (kit/world/worldcheck.py PLAYER)


def font(size, bold=False):
    for f in (BOLD if bold else FONTS):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(area, box=PLAN_BOX):
    """the scale (pixels a stud) and offset that put the town's area inside the box, centred, north (-Z) up"""
    w, d = area["x1"] - area["x0"], area["z1"] - area["z0"]
    k = min((box[2] - box[0]) / w, (box[3] - box[1]) / d)
    ox = box[0] + ((box[2] - box[0]) - w * k) / 2 - area["x0"] * k
    oy = box[1] + ((box[3] - box[1]) - d * k) / 2 - area["z0"] * k
    return k, ox, oy


def to_px(k, ox, oy, x, z):
    return (x * k + ox, z * k + oy)


def strip(s):
    """a street's strip on the ground: (x0, z0, x1, z1)"""
    h = s["width"] / 2
    if s["axis"] == "z":
        return (s["at"] - h, s["from"], s["at"] + h, s["to"])
    return (s["from"], s["at"] - h, s["to"], s["at"] + h)


def lot_colour(lot):
    if lot.get("landmark"):
        return LANDMARK
    return FLOORS[max(1, min(4, int(lot.get("floors") or 2)))]


# a BENT town (the town step's "bend"): a lot and a block carry their four corners as they stand ("quad": NW, NE, SE,
# SW of the rect they were planned as), a street its middle line ("line"); a straight town has none of these and is
# drawn from its rects, as before
_FRONT_EDGE = {"N": (0, 1), "E": (1, 2), "S": (2, 3), "W": (3, 0)}


def lot_quad(lot):
    """a lot's corners on the ground, NW NE SE SW: as it stands when the town is bent, else its rect's"""
    if lot.get("quad"):
        return [tuple(c) for c in lot["quad"]]
    r = lot["rect"]
    return [(r["x0"], r["z0"]), (r["x1"], r["z0"]), (r["x1"], r["z1"]), (r["x0"], r["z1"])]


def quad_centre(q):
    return (sum(c[0] for c in q) / 4, sum(c[1] for c in q) / 4)


def door_mark(lot, k, ox, oy):
    """the short line on a lot's front that says where its door is: ((x0, y0), (x1, y1)) in pixels"""
    if lot.get("quad"):
        q = lot_quad(lot)
        i, j = _FRONT_EDGE.get(lot["front"], (2, 3))
        (ax, az), (bx, bz) = q[i], q[j]
        length = math.hypot(bx - ax, bz - az) or 1.0
        ux, uz = (bx - ax) / length, (bz - az) / length
        mx, mz = (ax + bx) / 2, (az + bz) / 2
        return to_px(k, ox, oy, mx - ux * 2.5, mz - uz * 2.5), to_px(k, ox, oy, mx + ux * 2.5, mz + uz * 2.5)
    r = lot["rect"]
    cx, cz = (r["x0"] + r["x1"]) / 2, (r["z0"] + r["z1"]) / 2
    f = lot["front"]
    if f == "N":
        a, b = (cx - 2.5, r["z0"]), (cx + 2.5, r["z0"])
    elif f == "S":
        a, b = (cx - 2.5, r["z1"]), (cx + 2.5, r["z1"])
    elif f == "W":
        a, b = (r["x0"], cz - 2.5), (r["x0"], cz + 2.5)
    else:
        a, b = (r["x1"], cz - 2.5), (r["x1"], cz + 2.5)
    return to_px(k, ox, oy, *a), to_px(k, ox, oy, *b)


def rows(town):
    """the page's text beside the plan: [(text, kind)] with kind "h" (a heading), "t" (a line), "d" (a dim note)"""
    m = town.get("measures") or {}
    out = [("The layout, in numbers", "h")]
    out.append((f'{m.get("lots", 0)} houses in {m.get("blocks", 0)} blocks, {len(town.get("streets") or [])} streets', "t"))
    for rank in ("main", "lane", "alley"):
        s = (m.get("streets") or {}).get(rank)
        if s:
            out.append((f'   {rank}: {s["count"]} - {round(s["length"])} studs in all', "t"))
    out.append((f'loops a walker can make: {m.get("loops", 0)}; dead ends: {m.get("deadEnds", 0)}', "t"))
    out.append((f'T-junctions (a house front ends the view): {m.get("tees", 0)}; crossings: {m.get("crossings", 0)}', "t"))
    out.append((f'the square is walled along {round(100 * (m.get("squareClosed") or 0))}% of its edge', "t"))
    for w in m.get("walks") or []:
        out.append((f'{w["gate"]} to the square: {round(w["seconds"])} s on foot ({round(w["studs"])} studs)', "t"))
    out.append((f'the farthest corner from the square: {round(m.get("farthestSeconds") or 0)} s', "t"))
    v = m.get("vista") or {}
    if v:
        end = "ends inside the town" if v.get("closed") else "runs out of a gate"
        out.append((f'longest straight view: {round(v.get("length") or 0)} studs ({v.get("street")}, {end})', "t"))
    out.append((f'{round(100 * (m.get("frontageBuilt") or 0))}% of the street fronts are built', "t"))
    seen = m.get("landmarkSeen")
    if isinstance(seen, dict):
        gate = "seen from the main gate" if seen.get("fromGate") else "NOT seen from the main gate"
        out.append((f'the landmark is {gate}, and from {round(100 * (seen.get("share") or 0))}% of its street', "t"))
    if (m.get("bend") or 0) > 0:
        w = m.get("wider") or {}
        out.append((f'streets bent {round(m["bend"], 1):g} degrees: each block turned as one piece', "t"))
        out.append((f'a street at its narrowest: as planned +{w.get("mean", 0):.1f} studs on average, +{w.get("most", 0):.1f} at most', "d"))
    if town.get("slope"):
        sl = town["slope"]
        side = {"N": "north", "E": "east", "S": "south", "W": "west"}.get(sl.get("toward"), "?")
        out.append((f'on a hillside: {sl.get("rise"):g} studs up in 100 toward the {side}, {sl.get("drop", 0):.0f} from edge to edge', "t"))
    if town.get("yardThings"):
        piles = sum(1 for th in town["yardThings"] if th.get("kind") == "pile")
        lines = len(town["yardThings"]) - piles
        out.append((f"in the yards with a gate: {piles} woodpiles, {lines} wash lines", "t"))
    if town.get("yardWays"):
        n = len(town["yardWays"])
        out.append((f'{n} shut yard{"" if n == 1 else "s"} opened: a court and a gate in place of one house', "t"))
    if town.get("stalls"):
        out.append((f'a market of {len(town["stalls"])} stalls on the square (the gate view kept clear)', "t"))
    if town.get("lamps"):
        why = {}
        for lamp in town["lamps"]:
            reason = str(lamp.get("why") or "place")  # (a record with no reason typed still draws)
            why[reason] = why.get(reason, 0) + 1
        said = ", ".join(f'{n} at a {k}' if n == 1 else f'{n} at {k}s' for k, n in sorted(why.items()))
        out.append((f'{len(town["lamps"])} lamps, each with a reason: {said}', "t"))
    if m.get("cutOff"):
        out.append((f'{m["cutOff"]} junction(s) no street joins to the square', "t"))
    types = town.get("types") or []
    out.append(("", "t"))
    if town.get("modules"):
        out.append((f'Made of {town["modules"]} modules by a facade grammar (in place of {len(types)} whole-house meshes)', "h"))
    out.append((f'The kit of houses: {len(types)} types', "h"))
    out.append(("front x depth _ storeys f storey height (_e / _w: a corner's windowed flank; _t: a through house)", "d"))
    shown = types[:max(4, 30 - len(out))]  # (what the page has room for above its legend)
    for t in shown:
        out.append((f'   {t["count"]:>2} x  {t["type"]}', "t"))
    if len(types) > len(shown):
        rest = sum(t["count"] for t in types[len(shown):])
        out.append((f'   ... and {len(types) - len(shown)} more types ({rest} houses)', "d"))
    return out


def draw(town, world_name, path):
    """the page -> path; returns {"lots", "streets", "scale"} (what was drawn, for the report and the tests)"""
    img = Image.new("RGB", PAGE, BG)
    d = ImageDraw.Draw(img)
    area = town["area"]
    k, ox, oy = fit(area)

    def P(x, z):
        return to_px(k, ox, oy, x, z)

    def R(x0, z0, x1, z1):
        a, b = P(x0, z0), P(x1, z1)
        return [a[0], a[1], b[0], b[1]]

    # the ground is street; streets by rank over it, blocks and the square on top
    d.rectangle(R(area["x0"], area["z0"], area["x1"], area["z1"]), fill=STREET["alley"])
    for s in town["streets"]:
        if s.get("line"):  # (bent: the street as a band along its middle line)
            d.line([P(x, z) for x, z in s["line"]], fill=STREET.get(s["rank"], STREET["lane"]), width=max(1, int(round(s["width"] * k))), joint="curve")
        else:
            d.rectangle(R(*strip(s)), fill=STREET.get(s["rank"], STREET["lane"]))
    sq = town["square"]
    d.rectangle(R(sq["x0"], sq["z0"], sq["x1"], sq["z1"]), fill=SQUARE)
    for b in town["blocks"]:
        if b.get("quad"):
            d.polygon([P(x, z) for x, z in b["quad"]], fill=BLOCK)
        else:
            d.rectangle(R(b["x0"], b["z0"], b["x1"], b["z1"]), fill=BLOCK)
    for lot in town["lots"]:
        if lot.get("quad"):
            corners = [P(x, z) for x, z in lot_quad(lot)]
            d.polygon(corners, fill=lot_colour(lot))
            d.line(corners + [corners[0]], fill=BG, width=2)
        else:
            r = lot["rect"]
            d.rectangle(R(r["x0"], r["z0"], r["x1"], r["z1"]), fill=lot_colour(lot), outline=BG, width=2)
        a, b = door_mark(lot, k, ox, oy)
        d.line([a, b], fill=BG, width=5)
        d.line([a, b], fill=(255, 255, 255) if not lot.get("landmark") else (60, 40, 10), width=2)

    # the line of sight from the main gate, to where it lands on the square's wall
    view = town.get("view") or {}
    gate_node = next((n for n in town.get("nodes") or [] if n.get("kind") == "gate" and str(n.get("name", "")).startswith(str(view.get("from")))), None)
    if gate_node and view.get("at"):
        a, b = P(gate_node["x"], gate_node["z"]), P(view["at"][0], view["at"][1])
        steps = 40
        for i in range(0, steps, 2):
            p0 = (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
            p1 = (a[0] + (b[0] - a[0]) * (i + 1) / steps, a[1] + (b[1] - a[1]) * (i + 1) / steps)
            d.line([p0, p1], fill=VIEW, width=3)

    # street names along their middles (a north-south street's name is turned)
    small, tiny = font(17), font(14)
    for s in town["streets"]:
        x0, z0, x1, z1 = strip(s)
        label = f'{s["name"]}  {round(s["width"])}'
        cx, cy = P((x0 + x1) / 2, (z0 + z1) / 2)
        if s.get("line"):  # (bent: the name sits on the street's own middle point)
            cx, cy = P(*s["line"][len(s["line"]) // 2])
        tw = d.textlength(label, font=tiny)
        if s["axis"] == "x":
            if tw < (x1 - x0) * k - 8:
                d.text((cx - tw / 2, cy - 9), label, font=tiny, fill=DIM)
        elif tw < (z1 - z0) * k - 8:
            tag = Image.new("RGBA", (int(tw) + 4, 20), (0, 0, 0, 0))
            ImageDraw.Draw(tag).text((2, 1), label, font=tiny, fill=DIM + (255,))
            tag = tag.rotate(90, expand=True)
            img.paste(tag, (int(cx - tag.width / 2), int(cy - tag.height / 2)), tag)
    d = ImageDraw.Draw(img)
    c = P((sq["x0"] + sq["x1"]) / 2, (sq["z0"] + sq["z1"]) / 2)
    d.text((c[0] - d.textlength("Square", font=small) / 2, c[1] - 11), "Square", font=small, fill=INK)

    # junctions: a T is a closed view, a crossing the start of a grid, a dead end a fault to look at
    walks = {w["gate"]: w for w in (town.get("measures") or {}).get("walks") or []}
    for n in town.get("nodes") or []:
        x, y = P(n["x"], n["z"])
        kind, deg = n.get("kind"), n.get("degree") or 0
        if kind == "gate":
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=GATE, outline=BG, width=2)
            w = walks.get(n.get("name"))
            text = f'{n.get("name")}' + (f' - {round(w["seconds"])} s to the square' if w else "")
            tw = d.textlength(text, font=small)
            tx = min(max(x - tw / 2, PLAN_BOX[0]), PLAN_BOX[2] - tw)
            ty = y - 34 if y > (PLAN_BOX[1] + PLAN_BOX[3]) / 2 else y + 14
            d.rectangle([tx - 4, ty - 2, tx + tw + 4, ty + 22], fill=BG)
            d.text((tx, ty), text, font=small, fill=GATE)
        elif kind == "deadend":
            d.rectangle([x - 6, y - 6, x + 6, y + 6], fill=DEADEND, outline=BG)
        elif kind == "junction" and deg >= 4:
            d.polygon([(x, y - 7), (x + 7, y), (x, y + 7), (x - 7, y)], fill=CROSSING, outline=BG)
        elif kind == "junction" and deg == 3:
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=TEE)
    # the market: each stall a small light box, turned as it stands
    # a shut yard's way in: its gate on the street, a small green mark
    for way in town.get("yardWays") or []:
        gx, gy = P(way["gate"]["x"], way["gate"]["z"])
        d.rectangle([gx - 3, gy - 3, gx + 3, gy + 3], fill=GATE, outline=BG)
    # the yards' things: a woodpile a small box against its wall, a wash line a thin line from wall to wall
    for th in town.get("yardThings") or []:
        a = math.radians(th.get("turn") or 0.0)
        ca, sa = math.cos(a), math.sin(a)
        if th.get("kind") == "pile":
            half = (2.5, 1.0) if th.get("alongX") else (1.0, 2.5)
        else:
            span = (th.get("span") or 0.0) / 2
            half = (0.0, span) if th.get("alongX") else (span, 0.0)
        pts = []
        for dx, dz in ((-half[0], -half[1]), (half[0], -half[1]), (half[0], half[1]), (-half[0], half[1])):
            pts.append(P(th["x"] + ca * dx + sa * dz, th["z"] - sa * dx + ca * dz))
        if th.get("kind") == "pile":
            d.polygon(pts, fill=STALL, outline=BG)
        else:
            d.line([pts[0], pts[2]], fill=STALL, width=1)
    for stall in town.get("stalls") or []:
        a = math.radians(stall.get("turn") or 0.0)
        ca, sa = math.cos(a), math.sin(a)
        corners = []
        for dx, dz in ((-4, -2.5), (4, -2.5), (4, 2.5), (-4, 2.5)):
            corners.append(P(stall["x"] + ca * dx + sa * dz, stall["z"] - sa * dx + ca * dz))
        d.polygon(corners, fill=STALL, outline=BG)
    # the town's own lamps: a small warm ring each (a gate, a mouth of the square, a crossing - never a row)
    for lamp in town.get("lamps") or []:
        x, y = P(lamp["x"], lamp["z"])
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=LAMP, width=3)
    lm = next((lot for lot in town["lots"] if lot.get("landmark")), None)
    if lm:
        x, y = P(*quad_centre(lot_quad(lm)))
        text = f'{lm["name"]} ({lm["floors"]} storeys)'
        tw = d.textlength(text, font=small)
        d.rectangle([x - tw / 2 - 4, y - 13, x + tw / 2 + 4, y + 11], fill=BG)
        d.text((x - tw / 2, y - 12), text, font=small, fill=LANDMARK)

    # the heading, a scale bar, the legend, the numbers
    d.text((40, 24), f'{world_name} - {town.get("name") or "Town"}: the town plan from above (north up, seed {town.get("seed")})', font=font(30, True), fill=INK)
    bar = 64
    bx, by = PLAN_BOX[0], PAGE[1] - 28
    d.line([(bx, by), (bx + bar * k, by)], fill=INK, width=3)
    d.text((bx + bar * k + 10, by - 11), f'{bar} studs = {round(bar / SPEED)} s on foot (an R6 walks {round(SPEED)} studs a second)', font=tiny, fill=DIM)
    x, y = 1290, 96
    for text, kind in rows(town):
        if kind == "h":
            d.text((x, y), text, font=font(24, True), fill=INK)
            y += 36
        elif kind == "d":
            d.text((x, y), text, font=tiny, fill=DIM)
            y += 22
        else:
            d.text((x, y), text, font=font(19), fill=INK)
            y += 27
    y = max(y + 16, 960)
    d.text((x, y), "How to read the plan", font=font(24, True), fill=INK)
    y += 38
    legend = [
        (FLOORS[2], "a house, 2 storeys"), (FLOORS[3], "3 storeys"), (FLOORS[4], "4 or more"),
        (LANDMARK, "the landmark"), (SQUARE, "the square"), (STREET["main"], "a main street"),
        (STREET["lane"], "a lane"), (STREET["alley"], "an alley / open ground"), (BLOCK, "a block's yard and pavement"), (STALL, "a stall / a woodpile (a thin line: washing)"),
    ]
    for i, (colour, text) in enumerate(legend):
        lx, ly = x + (i % 2) * 300, y + (i // 2) * 28
        d.rectangle([lx, ly + 3, lx + 22, ly + 21], fill=colour, outline=DIM)
        d.text((lx + 32, ly), text, font=tiny, fill=INK)
    y += ((len(legend) + 1) // 2) * 28 + 6
    d.text((x, y), "white tick = a door   green = a gate   yellow dashes = the view from the main gate", font=tiny, fill=DIM)
    d.text((x, y + 22), "white dot = T-junction   orange diamond = crossing   red square = dead end   warm ring = a lamp", font=tiny, fill=DIM)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    return {"lots": len(town["lots"]), "streets": len(town["streets"]), "scale": k}


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(json.dumps({"status": "fail", "summary": "usage: townplan.py <compiled world.json> [--out DIR]",
                          "next_action": "lune run kit world town <Name>"}))
        return 2
    world_path = argv[0]
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(os.path.dirname(os.path.abspath(world_path)), "town")
    with open(world_path, encoding="utf-8") as fh:
        w = json.load(fh)
    towns = w.get("towns") or []
    if not towns:
        print(json.dumps({"status": "fail", "summary": f'{w.get("name")}: no "town" step in this world',
                          "next_action": 'add a { "town": { ... } } step (kit/skills/parallax-world/reference/05-town-plan.md)'}))
        return 1
    pages, lines, used = [], [], {}
    for t in towns:
        # (two towns of one name - or of none - each keep their own page)
        label = t.get("name") or "Town"
        used[label] = used.get(label, 0) + 1
        if used[label] > 1:
            label = f"{label}_{used[label]}"
        page = os.path.join(out_dir, f'{w.get("name")}_{label}.png').replace("\\", "/")
        draw(t, w.get("name") or "?", page)
        pages.append(page)
        lines.append(t.get("summary") or "")
    print(json.dumps({
        "status": "pass",
        "summary": f'{w.get("name")}: {"; ".join(lines)}',
        "next_action": f"LOOK: {pages[0]} - the plan from above: streets by name and width, every lot and its door, the gates' walk to the square, the view from the main gate; open it before dressing anything",
        "pages": pages,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
