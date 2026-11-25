"""ambience.py — `kit sfx ambience <World>`: a world's AMBIENCE from its own blueprint (sound mission ladder 2).

    python kit/audio/ambience.py <World>          (cwd = the repo; KIT_GAME / games/.active name the game)

Input  assets/sounds/ambience/<World>.json (hand-made, small):
  { "set": "sampleregion_ambience",                     the sound set the beds and scatter come from
    "beds": { "open": "bed_meadow", "forest": "bed_forest", "water": "bed_lake", "stone": "bed_castle" },
    "volume": { "open": 0.8 },                          per kind (default 1)
    "fade": 30,                                         studs over which a zone fades out past its edge
    "scatter": [ { "sound": "bird_chirp", "kinds": ["open", "forest"], "every": [3, 9], "distance": [20, 70],
                   "height": [6, 18], "volume": 0.6 } ],
  "voices": { "set": "stormhold_voice", "sound": "stormhold_voice", "on": ["tower", "wall"], "every": 28,
              "tower_points": 3, "volume": 0.55, "calm": 3, "full": 14, "max": 6, "range": 260 } }   (optional: the
              castle's voice - tonal wind loops on wall tops and tower tops, played by kit WindVoice)
  "gusts": [ { "sound": "distant_bell", "x": 300, "z": 260, "h": -2, "rise": 1.3, "floor": 6, "cooldown": 120,
               "chance": 0.5, "muffle": true, "pitch": 0.8 } ]   (optional: rare moments a real gust causes - kit GustEvents)
  "echoes": [ { "x": 400, "z": -120, "r": 30, "y0": -20, "y1": 40, "deep": [430, -6, -150], "delay": 0.6, "gain_db": -9,
                "pitch": 0.94, "phantom": 0.35, "min_steps": 4 } ]   (optional: places that answer - kit EchoZones)
Zones come from the BLUEPRINT (assets/worlds/<World>.json), never typed by hand: every terrain water op -> "water",
every forest step -> "forest", walls / towers / buildings / ruins / arches / rooms within 90 studs of each other ->
one "stone" zone; everywhere else is "open". Writes src/shared/<World>Ambience.json (the runtime's data:
src/kit/Ambience + AmbienceRules) and build/sounds/ambience/<World>.png (the zones on the map: LOOK at it).
Fails when a bed or a scatter sound is not a member of the set. One JSON verdict line.
"""

import json
import math
import os
import sys

STONE = ("wall", "tower", "building", "ruin", "arch", "room", "ziggurat")
KINDS = ("open", "forest", "water", "stone")


def game_root():
    g = os.environ.get("KIT_GAME")
    if g == "none":
        return "."  # (the project root, as every kit command means it: never games/.active)
    if not g:
        p = os.path.join("games", ".active")
        g = open(p, encoding="utf-8").read().strip() if os.path.isfile(p) else ""
    return os.path.join("games", g) if g and g != "none" and os.path.isdir(os.path.join("games", g)) else "."


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def step_points(kind, v):
    """the ground points a stone step covers (centre + extent, or a wall's two ends)"""
    if kind == "wall" and v.get("from") and v.get("to"):
        return [tuple(v["from"][:2]), tuple(v["to"][:2])]
    c = v.get("center") or v.get("pos")
    if not c:
        return []
    x, z = (c[0], c[2]) if len(c) >= 3 else (c[0], c[1])
    size = v.get("size") or v.get("base")
    if isinstance(size, list) and len(size) >= 2:
        hw, hd = size[0] / 2, size[-1] / 2
        return [(x - hw, z - hd), (x + hw, z + hd)]
    r = v.get("radius") or 4
    return [(x - r, z - r), (x + r, z + r)]


def zones(bp):
    out = []
    for t in bp.get("terrain") or []:
        w = t.get("water") if isinstance(t, dict) else None
        if isinstance(w, dict) and w.get("center") and w.get("size") and not w.get("backdrop"):
            c, s = w["center"], w["size"]
            out.append({"kind": "water", "name": "water", "x": c[0], "z": c[2], "r": round(max(s[0], s[-1]) / 2, 1)})
    pts = []
    for st in bp.get("build") or []:
        for k, v in st.items():
            if not isinstance(v, dict):
                continue
            if k == "forest" and v.get("center") and v.get("area"):
                c = v["center"]
                out.append({"kind": "forest", "name": v.get("name", "forest"), "x": c[0], "z": c[2], "r": round(max(v["area"]) / 2, 1)})
            elif k in STONE:
                for p in step_points(k, v):
                    pts.append((p, v.get("name", k), STONE.index(k)))
    # stone: single-linkage clusters of the stone steps' points (within 90 studs)
    groups = []
    for p, name, rank in pts:
        hit = [g for g in groups if any(math.dist(p, q) <= 90 for q, _, _ in g)]
        merged = [(p, name, rank)]
        for g in hit:
            merged += g
            groups.remove(g)
        groups.append(merged)
    for g in groups:
        xs, zs = [q[0] for q, _, _ in g], [q[1] for q, _, _ in g]
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        r = max(25.0, math.dist((min(xs), min(zs)), (max(xs), max(zs))) / 2 + 10)
        # named after its main piece: a building before a ruin before a tower before walls / arches
        order = {"building": 0, "ruin": 1, "room": 2, "ziggurat": 2, "tower": 3, "arch": 4, "wall": 5}
        names = sorted({(order.get(STONE[r], 9), n) for _, n, r in g})
        main = names[0][1]
        out.append({"kind": "stone", "name": main if len(names) == 1 else f"{main}+{len(names) - 1}",
                    "x": round(cx, 1), "z": round(cz, 1), "r": round(r, 1)})
    return out


def voice_points(bp, vs):
    """the castle's voice points from the blueprint: along every wall's top (every `every` studs, facing across the
    wall) and round every tower's top (`tower_points` of them, facing out); heights above the ground"""
    on = set(vs.get("on") or ["tower", "wall"])
    every = float(vs.get("every", 28))
    k = int(vs.get("tower_points", 3))
    pts = []
    for st in bp.get("build") or []:
        for kind, v in st.items():
            if not isinstance(v, dict) or kind not in on:
                continue
            if kind == "wall" and v.get("from") and v.get("to"):
                (x0, z0), (x1, z1) = v["from"][:2], v["to"][:2]
                L = math.dist((x0, z0), (x1, z1))
                if L < 1:
                    continue
                n = max(1, int(L // every))
                nx, nz = -(z1 - z0) / L, (x1 - x0) / L
                for i in range(n):
                    t = (i + 0.5) / n
                    pts.append({"x": round(x0 + (x1 - x0) * t, 1), "z": round(z0 + (z1 - z0) * t, 1),
                                "h": round(float(v.get("height", 18)) + 1.5, 1), "nx": round(nx, 4), "nz": round(nz, 4), "on": v.get("name", "wall")})
            elif kind == "tower" and v.get("center"):
                c = v["center"]
                cx, cz = c[0], c[2] if len(c) >= 3 else c[1]
                r = float(v.get("radius", 6))
                for i in range(k):
                    a = 2 * math.pi * i / k + 0.4
                    pts.append({"x": round(cx + r * math.cos(a), 1), "z": round(cz + r * math.sin(a), 1),
                                "h": round(float(v.get("height", 24)) - 1.0, 1), "nx": round(math.cos(a), 4), "nz": round(math.sin(a), 4),
                                "on": v.get("name", "tower")})
    return pts


def draw(world, zs, png, bounds):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    col = {"forest": "#3f7d3a", "water": "#2f6db3", "stone": "#8a8178", "open": "#c9b458"}
    fig, ax = plt.subplots(figsize=(7, 7), dpi=110)
    ax.set_facecolor("#e9e2c8")
    for z in zs:
        ax.add_patch(Circle((z["x"], z["z"]), z["r"], color=col[z["kind"]], alpha=0.45))
        ax.add_patch(Circle((z["x"], z["z"]), z["r"] + z.get("fade", 0), fill=False, ls="--", color=col[z["kind"]]))
        dy = {"water": -22, "forest": 0, "stone": 22, "open": 0}[z["kind"]]  # (zones sharing a centre stay readable)
        ax.text(z["x"], z["z"] + dy, f'{z["kind"]}: {z["name"]}', ha="center", va="center", fontsize=7)
    ax.set_xlim(bounds[0], bounds[1])
    ax.set_ylim(bounds[3], bounds[2])  # (+Z down the page: north up, as the world sheets draw it)
    ax.set_aspect("equal")
    ax.set_title(f"{world} ambience zones (open = everywhere else; dashed = the fade)", fontsize=9)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: ambience.py <World>", "next_action": "lune run kit sfx ambience <World>"}))
        return 2
    world = argv[0]
    root = game_root()
    spec_path = os.path.join(root, "assets", "sounds", "ambience", f"{world}.json")
    spec = load(spec_path)
    if not spec:
        print(json.dumps({"status": "fail", "summary": f"no ambience spec {spec_path}",
                          "next_action": f"write {spec_path} (shape: top of kit/audio/ambience.py)"}))
        return 1
    bp = load(os.path.join(root, "assets", "worlds", f"{world}.json"))
    if not bp:
        print(json.dumps({"status": "fail", "summary": f"no blueprint for {world} in {root}", "next_action": f"lune run kit new world {world}"}))
        return 1
    errors = []
    set_spec = load(os.path.join(root, "assets", "sounds", "sets", f"{spec.get('set')}.json")) or load(
        os.path.join("assets", "sounds", "sets", f"{spec.get('set')}.json"))
    members = set((set_spec or {}).get("members", {}))
    if not set_spec:
        errors.append(f'no sound set "{spec.get("set")}" (assets/sounds/sets/)')
    beds = spec.get("beds") or {}
    for kind in KINDS:
        if kind not in beds:
            errors.append(f'no bed for the "{kind}" kind')
    for kind, bed in beds.items():
        if kind not in KINDS:
            errors.append(f'unknown kind "{kind}" (one of {", ".join(KINDS)})')
        if set_spec and bed not in members:
            errors.append(f'bed "{bed}" is not a member of the set "{spec.get("set")}"')
    for i, s in enumerate(spec.get("scatter") or []):
        if set_spec and s.get("sound") not in members:
            errors.append(f'scatter {i + 1}: "{s.get("sound")}" is not a member of the set')
        for key in ("every", "distance", "height"):
            v = s.get(key)
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(n, (int, float)) for n in v) and 0 <= v[0] <= v[1]):
                errors.append(f"scatter {i + 1}: {key} must be [low, high] with 0 <= low <= high")
        if not set(s.get("kinds") or []) <= set(KINDS):
            errors.append(f"scatter {i + 1}: kinds must be among {', '.join(KINDS)}")
    voices = None
    vs = spec.get("voices")
    if isinstance(vs, dict):
        vset = load(os.path.join(root, "assets", "sounds", "sets", f"{vs.get('set')}.json")) or load(
            os.path.join("assets", "sounds", "sets", f"{vs.get('set')}.json"))
        if not vset or vs.get("sound") not in (vset.get("members") or {}):
            errors.append(f'voices: "{vs.get("sound")}" is not a member of the set "{vs.get("set")}"')
        pts = voice_points(bp, vs)
        if not pts:
            errors.append("voices: no tower or wall in the blueprint to sing")
        voices = {k: vs[k] for k in ("sound", "volume", "calm", "full", "floor", "max", "range", "near") if k in vs}
        voices["points"] = pts
    gusts = spec.get("gusts") or []
    for i, g in enumerate(gusts):
        gset = load(os.path.join(root, "assets", "sounds", "sets", f"{g.get('set', spec.get('set'))}.json")) or load(
            os.path.join("assets", "sounds", "sets", f"{g.get('set', spec.get('set'))}.json"))
        if not gset or g.get("sound") not in (gset.get("members") or {}):
            errors.append(f'gust {i + 1}: "{g.get("sound")}" is not a member of its set')
        if not all(isinstance(g.get(k), (int, float)) for k in ("x", "z")):
            errors.append(f"gust {i + 1}: needs a place (x, z)")
    echoes = spec.get("echoes") or []
    for i, e in enumerate(echoes):
        if not all(isinstance(e.get(k), (int, float)) for k in ("x", "z", "r")) or not (isinstance(e.get("deep"), list) and len(e["deep"]) == 3):
            errors.append(f"echo {i + 1}: needs x, z, r and a deep point [x, y, z]")
    zs = zones(bp)
    fade = float(spec.get("fade", 30))
    for z in zs:
        z["fade"] = fade
    out = {
        "_generated": f"kit sfx ambience {world} from assets/worlds/{world}.json + assets/sounds/ambience/{world}.json — do not edit",
        "set": spec.get("set"),
        "beds": beds,
        "volume": spec.get("volume") or {},
        "fade": fade,
        "zones": zs,
        "scatter": spec.get("scatter") or [],
        # the colour grade per zone kind (kit ZoneMood: { "forest": { "tint": [r, g, b], "saturation", "contrast",
        # "brightness" } }) - the same zones carry the look and the sound
        "moods": spec.get("moods") or {},
    }
    if echoes:
        # places that answer the player (kit EchoZones): late, dark repeats of their own sounds from deep in
        out["echoes"] = echoes
    if gusts:
        # rare moments the wind causes (kit GustEvents): a sound at a place on a real gust, cooldown, chance, muffle
        out["gusts"] = [{k: v for k, v in g.items() if k != "set"} for g in gusts]
    if voices:
        # the castle's voice (kit WindVoice): tonal wind loops on the walls and tower tops, swelling with the wind
        out["voices"] = voices
    if errors:
        print(json.dumps({"status": "fail", "summary": f"ambience {world}: {len(errors)} problem(s): {errors[0]}",
                          "next_action": f"fix {spec_path}", "errors": errors}))
        return 1
    dst = os.path.join(root, "src", "shared", f"{world}Ambience.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    hm = [t.get("heightmap") for t in bp.get("terrain") or [] if isinstance(t, dict) and isinstance(t.get("heightmap"), dict) and not t["heightmap"].get("backdrop")]
    if hm:
        c, s = hm[0]["center"], hm[0]["size"]
        bounds = (c[0] - s[0] / 2, c[0] + s[0] / 2, c[2] - s[-1] / 2, c[2] + s[-1] / 2)
    else:
        xs = [z["x"] for z in zs] or [0]
        zz = [z["z"] for z in zs] or [0]
        bounds = (min(xs) - 200, max(xs) + 200, min(zz) - 200, max(zz) + 200)
    png = os.path.join(root, "build", "sounds", "ambience", f"{world}.png")
    draw(world, zs, png, bounds)
    missing = [b for b in list(beds.values()) + [s["sound"] for s in spec.get("scatter") or []]
               if not os.path.isfile(os.path.join(root, "build", "sounds", f"{b}.ogg"))]
    counts = {k: sum(1 for z in zs if z["kind"] == k) for k in KINDS if k != "open"}
    print(json.dumps({
        "status": "pass",
        "summary": f"ambience {world}: {len(zs)} zone(s) from the blueprint ({', '.join(f'{n} {k}' for k, n in counts.items())}), "
                   f"{len(beds)} beds, {len(out['scatter'])} scatter rule(s)" + (f", {len(voices['points'])} voice point(s)" if voices else "") + f" -> {dst.replace(os.sep, '/')}",
        "next_action": (f"render the set first: lune run kit sfx set {spec.get('set')} ({len(missing)} sound(s) not rendered)" if missing
                        else f"LOOK at {png.replace(os.sep, '/')}; in game: the Ambience runtime plays it (kit.Ambience.start)"),
        "zones": zs,
        "sheet": png.replace(os.sep, "/"),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
