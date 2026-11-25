"""cost.py — a preset's COST LINE (mission 02-vfx 5.9), from the measured engine facts
(kit/knowledge/vault/vfx/refs/engine-facts.md), not guesses:

    lune run kit vfx cost <name> [--variant v] [--mobile]   (or: python kit/vfx/cost.py <name>)

  * live particles at the peak: every sprite layer's burst (count, + its twin) and stream (rate x min(for, lifetime))
    alive together, sampled every 0.05 s over the effect (the validator warns at 800, caps at ~1500)
  * mesh layers alive at the peak; vertices REWRITTEN per frame (wobble deforms move every vertex every frame; scroll
    and cell rewrite every UV) and the Luau time that costs: measured 0.36 us per wobbled vertex (60 flames of 697 =
    14-17 ms a frame), ~0.25 us per rewritten UV (assumed alike; cell() measured 0.017 ms for a card)
  * lights alive at the peak, SurfaceAppearance layers (each streams its own maps; > 1 s cold)
  * the meshes the engine must hold AT ONCE: mesh layers, and - each its own runtime mesh - a fracture's PIECES (a
    debris layer's "pieces": as many as its plan cuts, read from <effects>/fractures), a debris layer's thrown ROCKS
    ("shape": "rock": its count) and a swarm's STONES ("shape": "Rock": its count, 40 at most), a trail drawn as a mesh ribbon and a mark draped over the ground (one each) -
    held FROM THE EFFECT'S START to its end (the game builds them when the effect is set up and gives them back
    when it is over: the layer's own "at" and "life" do not shorten that), a mesh layer from the start until its own
    life is over - against the kit's default ceiling (100 in use, the last 10 for critical cues: over it a
    piece flies as a block and a mesh layer draws nothing); a swarm in an authored FIELD pays every element for
    every part every frame (ESTIMATED at 1 us an element a part, not measured in Roblox)
  * MESH SEQUENCES (a mesh layer "shape": "seq", kit/vfx/meshseq.py): their triangles, read from the baked sequence
    (4 a grid square: two triangles, both faces, as VfxMesh builds every grid), against the V3 doc's budget for a baked 3D burst (stage E.2):
    at most 800 triangles a sequence, and the sequences playing at once at most 3 x 800 triangles together (many
    small ones are as heavy as three big ones) - every frame of one is a full rewrite of its vertices
  * the verdict against a 60 fps budget: <= 2 ms of the effect's own Luau per frame is comfortable, > 6 ms is not
  * --mobile: the phone tier (<= 1 / 3 ms, <= 300 / 600 particles, <= 3 lights, <= 2 surface layers; Glass and post
    effects named because they vanish on phones / low graphics) and the particle scale a mobile variant needs
Prints one JSON line {schema, status, summary, next_action, cost}.
"""

import json
import os
import subprocess
import sys

# the grid of each VfxMesh shape: (segments default, rings default) -> (cols + 1) x (rows + 1) vertices per grid
GRIDS = {"ring": (48, 2), "disc": (48, 2), "tube": (32, 8), "cone": (32, 8), "sphere": (32, 16), "dome": (32, 10),
         "spiral": (96, 1), "flame": (40, 16), "tongue": (8, 12), "arc": (48, 2), "rock": (12, 8), "bolt": (5, 12),
         "cards": (1, 1), "spikes": (2, 6), "corona": (2, 6), "torus": (48, 16), "crown": (64, 20)}
US_PER_WOBBLED_VERT = 0.36
US_PER_UV = 0.25
US_PER_FIELD_ELEMENT = 1.0      # (a part in a field, an element, a frame: ESTIMATED, not measured in Roblox)
MESH_CEILING, MESH_RESERVE = 100, 10    # (src/kit/VfxMesh.luau DEFAULT_BUDGET: measured in a Studio play client)
SEQ_TRIS, SEQ_LIVE = 800, 3             # (the V3 doc, VFX stage E.2: a hero mesh-sequence burst's budget)
EFFECTS = os.path.join("assets", "effects")


def kept(effects, folder, name):
    """a kept file a layer names (a fracture plan, a field) -> its data, or None when it is not there"""
    try:
        data = json.load(open(os.path.join(effects, folder, f"{name}.json"), encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def count_of(v):
    return len(v) if isinstance(v, list) else int(v) if isinstance(v, (int, float)) else 0


def built_meshes(el, effects, missing):
    """the runtime meshes ONE layer makes besides a mesh layer's own: a fracture's pieces, a swarm's stones"""
    if el.get("kind") == "debris" and isinstance(el.get("pieces"), str):
        plan = kept(effects, "fractures", el["pieces"])
        if plan is None:
            missing.append(f"fracture plan {el['pieces']}")
            return 0
        return min(count_of(plan.get("pieces")), 64)
    if el.get("kind") == "debris" and el.get("shape") == "rock":      # (thrown rocks: a mesh a rock, up to 40)
        c = el.get("count")
        return max(0, min(int(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else 6, 40))
    if el.get("kind") == "swarm" and el.get("shape") == "Rock":      # (the game clamps a swarm of stones to 40)
        c = el.get("count")
        return max(1, min(int(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else 40, 40))
    if el.get("kind") == "trail" and el.get("mesh") is True:           # (a ribbon)
        return 1
    w = el.get("wrap")
    if el.get("kind") == "decal" and (w is True or (isinstance(w, (int, float)) and not isinstance(w, bool))):   # (a sheet laid over the ground; wrap 0 too: the stage clamps it to 2)
        return 1
    return 0


def verts(el):
    p = el.get("params") or {}
    shape = el.get("shape") or "ring"
    seg, rings = GRIDS.get(shape, (32, 8))
    cols = int(p.get("segments", seg))
    rows = int(p.get("rings", rings))
    n = (cols + 1) * (rows + 1)
    if shape == "cards":
        n *= int(p.get("count", 3))
    if shape in ("spikes", "corona"):
        n *= int(p.get("count", 12))
    return n


def rng_max(v, default=1.0):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
        return float(max(v))
    return default


def expand(name, variant):
    """the preset as the game plays it (beats / use / variants / overlay applied) via `lune run kit vfx expand`"""
    args = ["lune", "run", "kit", "vfx", "expand", name] + (["--variant", variant] if variant else [])
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=300)
    start = r.stdout.find("{")
    try:
        return json.loads(r.stdout[start:r.stdout.rfind("}") + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None


def seq_tris(el, effects, missing):
    """the triangles ONE seq mesh layer draws (its baked sequence's grid: 4 a square - two, both faces - every strip),
    or None when its sequence is not there to read"""
    name = (el.get("params") or {}).get("seq") if isinstance(el.get("params"), dict) else None
    if not isinstance(name, str) or not name:
        return None
    d = kept(effects, "seq", name)
    if not isinstance(d, dict) or not isinstance(d.get("cols"), int) or not isinstance(d.get("rows"), int):
        missing.append(f"seq/{name}.json")
        return None
    strips = d.get("strips") if isinstance(d.get("strips"), int) and d.get("strips") > 1 else 1
    return 4 * d["cols"] * d["rows"] * strips  # (VfxMesh builds every grid square as 2 triangles, both faces)


def cost(P, effects=None):
    """effects: the folder a layer's kept files are read from (the project's effects folder unless said)"""
    effects = effects or EFFECTS
    missing = []
    dur = float(P.get("duration") or 1)
    layers = [el for el in P.get("layers", []) if isinstance(el, dict)]
    peak_p, peak_m, peak_l, peak_t = 0.0, 0, 0, 0.0
    made = {id(el): built_meshes(el, effects, missing) for el in layers}
    seqs = {id(el): seq_tris(el, effects, missing) for el in layers if el.get("kind") == "mesh" and el.get("shape") == "seq"}
    peak_built = peak_seq = peak_seq_tris = 0
    wob = uv = 0
    t = 0.0
    while t <= dur + 1e-6:
        p_alive = m_alive = l_alive = b_alive = s_alive = s_tris = 0
        for el in layers:
            at = float(el.get("at") or 0) if isinstance(el.get("at"), (int, float)) else 0.0
            if el.get("kind") == "sprite":
                life = rng_max(el.get("lifetime"), 1.0)
                n = 0.0
                if (el.get("count") or 0) > 0 and at <= t <= at + life:
                    n += el["count"] * (2 if el.get("twin") else 1)
                rate = el.get("rate") or 0
                if rate and t >= at:
                    on = min(t - at, float(el.get("for") or 0))
                    n += rate * min(on, life) * (2 if el.get("twin") else 1) if t - at <= float(el.get("for") or 0) + life else 0
                p_alive += n
            elif el.get("kind") == "mesh":
                life = float(el.get("life") or 1)
                if at <= t <= at + life:
                    m_alive += 1
                    if id(el) in seqs:
                        s_alive += 1
                        s_tris += seqs[id(el)] or 0
                if t <= at + life:      # (built when the effect is set up, held until its own life is over)
                    b_alive += 1
            elif el.get("kind") == "light":
                life = float(el.get("life") or 1)
                if at <= t <= at + life:
                    l_alive += 1
            elif made[id(el)]:      # (built when the effect is set up, given back when it is over)
                b_alive += made[id(el)]
        if p_alive > peak_p:
            peak_p, peak_t = p_alive, t
        peak_m, peak_l = max(peak_m, m_alive), max(peak_l, l_alive)
        peak_built = max(peak_built, b_alive)
        peak_seq = max(peak_seq, s_alive)
        peak_seq_tris = max(peak_seq_tris, s_tris)
        t += 0.05
    meshes = [el for el in layers if el.get("kind") == "mesh"]
    for el in meshes:
        v = verts(el)
        if el.get("wobble"):
            wob += v
        if el.get("uvScroll") or el.get("flipbook"):
            uv += v
    # swarms (scripted particles): every part moved by Luau every frame - ~2 us plain, ~15 us with curl noise (18 noise
    # lookups x 8 hashed sines; ESTIMATED, not yet measured in Roblox)
    swarm_parts = sum(min(int(el.get("count") or 40), 150) for el in layers if el.get("kind") == "swarm")
    swarm_us = sum(min(int(el.get("count") or 40), 150) * (15 if el.get("curl") else 2) for el in layers if el.get("kind") == "swarm")
    # a swarm in an authored field: every element, for every part, every frame
    field_us = 0.0
    for el in layers:
        if el.get("kind") == "swarm" and isinstance(el.get("field"), dict) and isinstance(el["field"].get("name"), str):
            field = kept(effects, "fields", el["field"]["name"])
            if field is None:
                missing.append(f"field {el['field']['name']}")
                continue
            field_us += min(int(el.get("count") or 40), 150) * count_of(field.get("elements")) * US_PER_FIELD_ELEMENT
    luau_ms = (wob * US_PER_WOBBLED_VERT + uv * US_PER_UV + swarm_us + field_us) / 1000.0
    surfaces = sum(1 for el in meshes if el.get("surface") is not None)
    glass = sorted({el.get("name") for el in layers if el.get("material") == "Glass"})
    post = sorted({el.get("name") for el in layers if el.get("kind") == "world" and (el.get("sunRays") or el.get("dof"))}
                  | {el.get("name") for el in layers if el.get("kind") == "screen" and el.get("blur")})
    return {"glass_layers": glass, "post_layers": post, "swarm_parts": swarm_parts, "duration": dur, "peak_particles": round(peak_p), "peak_at": round(peak_t, 2), "meshes_peak": peak_m,
            "mesh_layers": len(meshes), "wobbled_verts_per_frame": wob, "uv_rewrites_per_frame": uv,
            "luau_ms_per_frame": round(luau_ms, 2), "lights_peak": peak_l, "surface_layers": surfaces,
            "piece_meshes": sum(made[id(el)] for el in layers if el.get("kind") == "debris" and el.get("pieces")),
            "stone_meshes": sum(made[id(el)] for el in layers if el.get("kind") in ("debris", "swarm") and not el.get("pieces")),
            "built_meshes_peak": peak_built, "seq_peak": peak_seq, "seq_tris_peak": peak_seq_tris,
            "seq_tris_most": max([v for v in seqs.values() if v is not None], default=0), "field_ms_per_frame": round(field_us / 1000.0, 3), "missing": missing}


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "cost: needs a preset name", "next_action": "lune run kit vfx cost <name>"}))
        return 1
    name = argv[0]
    variant = argv[argv.index("--variant") + 1] if "--variant" in argv else None
    P = expand(name, variant)
    if P is None:
        path = os.path.join("assets", "effects", f"{name}.json")
        if not os.path.isfile(path):
            print(json.dumps({"schema": 1, "status": "fail", "summary": f"cost: no preset {path}", "next_action": "check the name"}))
            return 1
        P = json.load(open(path, encoding="utf-8"))  # the file as written (no expansion available)
    c = cost(P, argv[argv.index("--effects") + 1] if "--effects" in argv and argv.index("--effects") + 1 < len(argv) else None)
    mobile = "--mobile" in argv
    # mobile (the pros' platform tier): a mid phone runs ~1/3 of a PC's particle fill and Luau; Glass refraction does
    # not exist on mobile (devforum, measured by the community) and post effects drop at low graphics quality
    lim = {"ms": (1.0, 3.0), "particles": (300, 600), "lights": 3, "surfaces": 2} if mobile else {"ms": (2.0, 6.0), "particles": (800, 1500)}
    heavy = c["luau_ms_per_frame"] > lim["ms"][1] or c["peak_particles"] > lim["particles"][1]
    warm = c["luau_ms_per_frame"] > lim["ms"][0] or c["peak_particles"] > lim["particles"][0]
    mobile_notes = []
    if mobile:
        if c["glass_layers"]:
            mobile_notes.append(f"Glass does not refract on mobile ({', '.join(c['glass_layers'][:3])}): it reads as a plain shell")
        if c["post_layers"]:
            mobile_notes.append(f"sun rays / depth of field / blur drop at low graphics ({', '.join(c['post_layers'][:3])}): the effect must read without them")
        if c["lights_peak"] > lim["lights"]:
            mobile_notes.append(f"{c['lights_peak']} lights at once (mobile: <= {lim['lights']})")
            warm = True
        if c["surface_layers"] > lim["surfaces"]:
            mobile_notes.append(f"{c['surface_layers']} SurfaceAppearance layers (mobile: <= {lim['surfaces']}: each streams its maps)")
            warm = True
        if c["peak_particles"] > lim["particles"][0]:
            k = lim["particles"][0] / max(c["peak_particles"], 1)
            mobile_notes.append(f"a mobile variant at x{k:.2f} particle rate / count fits the budget")
    line = (f"cost {name}{' (mobile)' if mobile else ''}: peak {c['peak_particles']} live particles (t={c['peak_at']} s), {c['meshes_peak']} mesh(es) at once, "
            f"{c['wobbled_verts_per_frame']} wobbled + {c['uv_rewrites_per_frame']} UV-rewritten vertices a frame = ~{c['luau_ms_per_frame']} ms Luau, "
            f"{c['lights_peak']} light(s), {c['surface_layers']} surface layer(s)")
    # the meshes the engine holds at once (a piece and a stone are each a runtime mesh of their own)
    over = c["built_meshes_peak"] > MESH_CEILING - MESH_RESERVE
    if c["piece_meshes"] or c["stone_meshes"] or over:
        line += (f"; {c['built_meshes_peak']} built mesh(es) at once ({c['piece_meshes']} piece(s), {c['stone_meshes']} rock(s) / stone(s))"
                 + (f" - OVER the kit's default ceiling ({MESH_CEILING - MESH_RESERVE} in use): the last are turned away" if over else ""))
    # mesh sequences: the doc's budget for a baked 3D burst (E.2)
    seq_over = c["seq_tris_peak"] > SEQ_LIVE * SEQ_TRIS or c["seq_tris_most"] > SEQ_TRIS
    if c["seq_peak"] or c["seq_tris_most"]:
        line += (f"; {c['seq_peak']} mesh sequence(s) at once ({c['seq_tris_peak']} triangles together), the largest {c['seq_tris_most']}"
                 + (f" - OVER the budget of a baked burst ({SEQ_TRIS} triangles a sequence, {SEQ_LIVE * SEQ_TRIS} together)" if seq_over else ""))
    if c["missing"]:
        line += "; NOT COUNTED (not found): " + ", ".join(c["missing"])
    warm = warm or over or seq_over or bool(c["missing"])
    status = "fail" if heavy else ("warn" if warm else "pass")
    nxt = ("over a 60 fps budget: fewer wobbling layers / segments (0.36 us a vertex), fewer streams" if heavy else
           "comfortable for 60 fps" if not warm else
           "fewer pieces / stones / mesh layers at once, or mark the ones that must show critical" if over else
           f"a coarser sequence (kit vfx meshseq: fewer cols / rows, {SEQ_TRIS} triangles at most) or fewer at once ({SEQ_LIVE * SEQ_TRIS} together)" if seq_over else
           "make the kept file it names (kit vfx fracture / kit vfx field), then again" if c["missing"] else
           "watch it on mobile: trim wobble segments or the densest stream")
    if c["surface_layers"]:
        nxt += "; surface layers stream maps (> 1 s cold): VfxStage.preload before the first cast"
    if mobile_notes:
        line += " | mobile: " + "; ".join(mobile_notes)
    print(json.dumps({"schema": 1, "status": status, "summary": line, "next_action": nxt, "cost": c}))
    return 0 if status != "fail" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
