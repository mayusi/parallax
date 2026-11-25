"""partcrafter_run.py — a cut-out picture -> the object as SEPARATE part meshes (PartCrafter), on this PC, offline.

PartCrafter (wgsxm/PartCrafter, MIT; built on TripoSG, MIT) generates 1-16 parts of one object in a single pass — a
sword's blade, guard, grip and pommel as four meshes that fit together. It runs in its own environment:
~/.cache/roblox-kit/envs/partcrafter (kit/gen/README.md). The kit calls it (`lune run kit gen parts`); by hand:

    <envs/partcrafter>/Scripts/python.exe kit/gen/partcrafter_run.py <cutout_rgba.png> <out_stem> --parts N
        [--seed S] [--tokens 1024] [--steps 50] [--guidance 7.0]

writes <out_stem>.parts.glb (every part, one node each: part1..partN), <out_stem>.part<k>.glb (one mesh per file:
a.import_mesh takes one) and <out_stem>.parts.json (how it was made + each part's box and triangles + the
import lines that put the parts back together).

Frame (every file): Roblox space — +Y up, the side the picture was taken from faces -Z (the object's front, its
LookVector), the object's own right is +X (so the picture's right-hand side lands at -X). Blender's glTF import plus
the kit's BL_FROM_RBX make that the identity: a.import_mesh sees these coordinates as they are. PartCrafter generates
upright (+Y) but not always facing its picture (a side-on sword came out pointing at the camera): the runner turns the
object about Y — 0, 90, 180 or 270 degrees, a turn, never a mirror — to the one whose silhouette from -Z matches the
picture best (`turned_y` in the record; a tie keeps PartCrafter's own facing, glTF's: its camera at +Z).
Specks (pieces under 1% of the object's size, marching-cubes crumbs that would stretch a part's box) are dropped.

What it guards:
- offline: every socket connection raises; Hugging Face runs offline. Weights come from the verified local copies
  (~/.cache/roblox-kit/models/partcrafter, each file's size checked against pins.json — the Hub's sha256 at download).
- licences: briaai/RMBG-1.4 (PartCrafter's background remover, non-commercial) is never fetched or loaded — the
  picture comes cut out by the kit's BiRefNet (MIT). PartCrafter's optional Gemini features (part count / style
  transfer, a cloud service) are stubbed out: importing them raises, and google-genai is not installed.
- torch-cluster (only used to train: farthest point sampling) is not installed; a torch fallback answers it.
"""

import hashlib
import json
import math
import os
import socket
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".cache", "roblox-kit")
MODELS = os.environ.get("KIT_MODELS") or os.path.join(CACHE, "models")
WEIGHTS = os.path.join(MODELS, "partcrafter")
SRC = os.environ.get("KIT_PARTCRAFTER_SRC") or os.path.join(CACHE, "src", "PartCrafter")
MAX_PARTS = 16  # what the released weights were trained for (the transformer holds 32 part embeddings)
PART_COLOURS = [(0.85, 0.33, 0.25), (0.25, 0.55, 0.85), (0.35, 0.7, 0.35), (0.9, 0.75, 0.25), (0.6, 0.4, 0.8),
                (0.3, 0.75, 0.75), (0.85, 0.5, 0.7), (0.55, 0.55, 0.55)]

os.environ.update(
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    HF_HUB_DISABLE_TELEMETRY="1",
    DIFFUSERS_DISABLE_TELEMETRY="1",
    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True",
)


def _no_network(*_a, **_k):
    raise RuntimeError("kit gen parts runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network


class _Unreachable(types.ModuleType):
    """a module the kit keeps out: any use raises (PartCrafter's cloud features, its non-commercial remover)"""

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        raise RuntimeError(f"kit gen parts: {self.__name__} is switched off (offline-only kit / licence) — "
                           "cut the picture out with lune run kit vision cutout and give the part count")


for _mod in ("google", "google.genai", "src.utils.providers", "src.utils.providers.gemini_provider",
             "src.utils.vlm_utils", "src.utils.style_transfer_utils", "src.models.briarmbg"):
    sys.modules[_mod] = _Unreachable(_mod)


def _fps(src, batch=None, ratio=0.5, random_start=True, batch_size=None, ptr=None):
    """torch_cluster.fps in plain torch (farthest point sampling: indices into src, ceil(n * ratio) per batch).
    PartCrafter only calls it when ENCODING a mesh (training); generation never does."""
    import torch  # noqa: PLC0415

    if batch is None:
        batch = torch.zeros(src.shape[0], dtype=torch.long, device=src.device)
    picked = []
    for b in torch.unique(batch):
        idx = torch.nonzero(batch == b).flatten()
        pts = src[idx].float()
        n = pts.shape[0]
        k = max(1, math.ceil(n * float(ratio)))
        sel = torch.empty(k, dtype=torch.long, device=src.device)
        far = int(torch.randint(n, (1,))) if random_start else 0
        dist = torch.full((n,), float("inf"), device=src.device)
        for i in range(k):
            sel[i] = far
            dist = torch.minimum(dist, ((pts - pts[far]) ** 2).sum(-1))
            far = int(torch.argmax(dist))
        picked.append(idx[sel])
    return torch.cat(picked)


try:
    import torch_cluster  # noqa: F401
except ImportError:
    _tc = types.ModuleType("torch_cluster")
    _tc.fps = _fps
    sys.modules["torch_cluster"] = _tc

sys.path.insert(0, SRC)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_weights():
    """every pinned weight file is there at its pinned size -> (pins, problems)"""
    pins_path = os.path.join(WEIGHTS, "pins.json")
    if not os.path.isfile(pins_path):
        return {}, [f"no {pins_path} — the PartCrafter weights were never fetched"]
    with open(pins_path, encoding="utf-8") as fh:
        pins = json.load(fh)
    problems = []
    for key, pin in pins.items():
        repo, rel = key.split("/", 2)[1], key.split("/", 2)[2]
        path = os.path.join(WEIGHTS, repo, rel)
        if not os.path.isfile(path):
            problems.append(f"missing {path}")
        elif os.path.getsize(path) != pin["size"]:
            problems.append(f"{path} is {os.path.getsize(path)} bytes, pinned {pin['size']}")
    return pins, problems


def cut_out_ok(alpha):
    """PartCrafter's own test for a usable alpha (src/utils/image_utils.py): >= 1% fully clear and >= 1% fully solid.
    Without it, its loader would call the background remover the kit never loads."""
    import numpy as np  # noqa: PLC0415

    n = alpha.size * 0.01
    return int(np.count_nonzero(alpha < 12.8)) >= n and int(np.count_nonzero(alpha >= 242.25)) >= n


def to_roblox(vertices):
    """PartCrafter (glTF: picture's camera at +Z) -> Roblox (front -Z): 180 degrees about Y. A turn: winding kept."""
    import numpy as np  # noqa: PLC0415

    v = np.asarray(vertices, dtype=np.float64).copy()
    v[:, 0] *= -1.0
    v[:, 2] *= -1.0
    return v


def turn_y(v, degrees):
    """a turn about +Y (right-handed, as Roblox's CFrame.Angles(0, a, 0)): x' = x cos + z sin, z' = -x sin + z cos"""
    import numpy as np  # noqa: PLC0415

    a = math.radians(degrees)
    c, s = round(math.cos(a)), round(math.sin(a))  # quarter turns: exact
    out = np.asarray(v, dtype=np.float64).copy()
    out[:, 0], out[:, 2] = v[:, 0] * c + v[:, 2] * s, -v[:, 0] * s + v[:, 2] * c
    return out


def drop_specks(meshes):
    """pieces of a part smaller than 1% of the whole object's box diagonal (marching-cubes crumbs) -> removed;
    a part is never emptied (its largest piece stays). -> (meshes, dropped piece count per part)"""
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    allv = np.concatenate([np.asarray(m.vertices) for m in meshes])
    limit = 0.01 * float(np.linalg.norm(allv.max(0) - allv.min(0)))
    kept, dropped = [], []
    for m in meshes:
        pieces = trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces)), min_len=1)
        pieces = sorted(pieces, key=len, reverse=True)
        keep = [p for i, p in enumerate(pieces)
                if i == 0 or np.linalg.norm(np.ptp(m.vertices[np.unique(m.faces[p])], axis=0)) >= limit]
        dropped.append(len(pieces) - len(keep))
        kept.append(m if len(keep) == len(pieces) else m.submesh([np.concatenate(keep)], append=True))
    return kept, dropped


def silhouettes(alpha, verts, grid=160):
    """the parts seen from the front (-Z) against the picture's cut-out: IoU of the two masks, each squared around its
    own box (scale-free), and the same with the parts mirrored (a mirrored frame would score higher there)"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    from scipy import ndimage  # noqa: PLC0415

    def square(mask):
        ys, xs = np.nonzero(mask)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        side = max(y1 - y0, x1 - x0)
        out = np.zeros((side, side), bool)
        oy, ox = (side - (y1 - y0)) // 2, (side - (x1 - x0)) // 2
        out[oy:oy + y1 - y0, ox:ox + x1 - x0] = mask[y0:y1, x0:x1]
        img = Image.fromarray(out.astype(np.uint8) * 255).resize((grid, grid), Image.NEAREST)
        return np.asarray(img) > 127

    def splat(u, v):
        lo_u, lo_v = u.min(), v.min()
        side = max(u.max() - lo_u, v.max() - lo_v, 1e-9)
        cu, cv = (u.max() + lo_u) / 2, (v.max() + lo_v) / 2
        iu = np.clip(((u - cu) / side + 0.5) * (grid - 1), 0, grid - 1).round().astype(int)
        iv = np.clip((0.5 - (v - cv) / side) * (grid - 1), 0, grid - 1).round().astype(int)  # image rows go down
        m = np.zeros((grid, grid), bool)
        m[iv, iu] = True
        return ndimage.binary_fill_holes(ndimage.binary_closing(m, iterations=2))

    pic = square(alpha > 127)
    front = splat(-verts[:, 0], verts[:, 1])  # from -Z: the picture's right is -X
    mirror = splat(verts[:, 0], verts[:, 1])

    def iou(a, b):
        return float(np.logical_and(a, b).sum() / max(np.logical_or(a, b).sum(), 1))

    return round(iou(pic, front), 3), round(iou(pic, mirror), 3)


def part_facts(meshes, verts):
    """each part's box (Roblox frame, generated units), triangles, pieces, watertightness; boxes that coincide"""
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    allv = np.concatenate(verts)
    lo, hi = allv.min(0), allv.max(0)
    longest = max(float((hi - lo).max()), 1e-9)
    facts = []
    for k, (m, v) in enumerate(zip(meshes, verts), start=1):
        plo, phi = v.min(0), v.max(0)
        pieces = sorted(trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces)),
                                                           min_len=1), key=len, reverse=True)
        main = v[np.unique(m.faces[pieces[0]])]
        facts.append({
            "part": f"part{k}", "triangles": int(len(m.faces)), "vertices": int(len(m.vertices)),
            "pieces": len(pieces), "watertight": bool(m.is_watertight),
            "box_min": [round(float(x), 4) for x in plo], "box_max": [round(float(x), 4) for x in phi],
            # the largest piece alone: which piece of the object this part IS (stray shards stretch the whole box)
            "main_share": round(len(pieces[0]) / max(len(m.faces), 1), 3),
            "main_box_min": [round(float(x), 4) for x in main.min(0)],
            "main_box_max": [round(float(x), 4) for x in main.max(0)],
            # fractions of the whole object's LONGEST side: what a.import_mesh needs (height= its Y size, pos= its
            # base centre, the whole object's base centre at 0)
            "height_frac": round(float((phi[1] - plo[1]) / longest), 5),
            "base_frac": [round(float(((phi[0] + plo[0]) / 2 - (hi[0] + lo[0]) / 2) / longest), 5),
                          round(float((plo[1] - lo[1]) / longest), 5),
                          round(float(((phi[2] + plo[2]) / 2 - (hi[2] + lo[2]) / 2) / longest), 5)],
        })
    dupes = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a0, a1, b0, b1 = (np.array(facts[i]["box_min"]), np.array(facts[i]["box_max"]),
                              np.array(facts[j]["box_min"]), np.array(facts[j]["box_max"]))
            inter = np.prod(np.clip(np.minimum(a1, b1) - np.maximum(a0, b0), 0, None))
            union = np.prod(a1 - a0) + np.prod(b1 - b0) - inter
            if union > 0 and inter / union > 0.85:
                dupes.append([facts[i]["part"], facts[j]["part"], round(float(inter / union), 3)])
    whole = {"box_min": [round(float(x), 4) for x in lo], "box_max": [round(float(x), 4) for x in hi],
             "size": [round(float(x), 4) for x in hi - lo]}
    return facts, whole, dupes


def export(meshes, verts, stem):
    """one GLB per part (a flat colour each, so a.import_mesh takes it without mat=) + all parts in one GLB"""
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415

    scene = trimesh.Scene()
    files = []
    for k, (m, v) in enumerate(zip(meshes, verts), start=1):
        r, g, b = PART_COLOURS[(k - 1) % len(PART_COLOURS)]
        mat = trimesh.visual.material.PBRMaterial(name=f"part{k}", baseColorFactor=[r, g, b, 1.0],
                                                  metallicFactor=0.0, roughnessFactor=0.8)
        part = trimesh.Trimesh(vertices=v.astype(np.float32), faces=np.asarray(m.faces), process=False,
                               visual=trimesh.visual.TextureVisuals(material=mat))
        path = f"{stem}.part{k}.glb"
        part.export(path)
        files.append(path.replace("\\", "/"))
        scene.add_geometry(part, node_name=f"part{k}", geom_name=f"part{k}")
    scene.export(f"{stem}.parts.glb")
    return files


def shape_up(raw, alpha, stem):
    """PartCrafter's meshes -> the kit's files: specks dropped, Roblox frame, turned to face the picture, one GLB per
    part + all in one, each part's facts and its import line -> the record's fields"""
    import numpy as np  # noqa: PLC0415

    meshes, specks = drop_specks(raw)
    verts = [to_roblox(m.vertices) for m in meshes]
    # face the picture: the quarter turn about Y whose front silhouette matches it best (ties keep PartCrafter's own)
    facing = {d: silhouettes(alpha, turn_y(np.concatenate(verts), d)) for d in (0, 90, 180, 270)}
    best = max(facing, key=lambda d: facing[d][0])
    turned = 0 if facing[0][0] >= facing[best][0] - 0.02 else best
    verts = [turn_y(v, turned) for v in verts]
    facts, whole, dupes = part_facts(meshes, verts)
    os.makedirs(os.path.dirname(os.path.abspath(stem)) or ".", exist_ok=True)
    files = export(meshes, verts, stem)
    for f, n, path in zip(facts, specks, files):
        f["specks_dropped"], f["file"] = n, path
    imports = ["L = 4.0  # the whole object's LONGEST side in studs (the parts keep their places relative to it)"] + [
        f'a.import_mesh("{f["part"].capitalize()}", "{f["file"]}", height={f["height_frac"]} * L, '
        f'pos=({f["base_frac"][0]} * L, {f["base_frac"][1]} * L, {f["base_frac"][2]} * L), mat="...")'
        for f in facts]
    return {"whole": whole, "part_facts": facts, "same_box_pairs": dupes, "turned_y": turned,
            "facing_iou": {str(d): v[0] for d, v in facing.items()},
            "silhouette_iou": facing[turned][0], "silhouette_iou_mirrored": facing[turned][1],
            "files": {"all": f"{stem}.parts.glb".replace("\\", "/"), "parts": files}, "import": imports}


def main(argv):
    if len(argv) < 2 or not os.path.isfile(argv[0]) or "--parts" not in argv:
        return emit("fail", "partcrafter: usage: partcrafter_run.py <cutout_rgba.png> <out_stem> --parts N [--seed S] "
                            "[--tokens 1024] [--steps 50] [--guidance 7.0]",
                    "lune run kit gen parts <name> --image <picture> --parts <n>")
    src, stem = argv[0], argv[1]
    n_parts, seed = _opt(argv, "--parts", 0), _opt(argv, "--seed", 0)
    tokens, steps, guidance = _opt(argv, "--tokens", 1024), _opt(argv, "--steps", 50), _opt(argv, "--guidance", 7.0)
    if not 1 <= n_parts <= MAX_PARTS:
        return emit("fail", f"partcrafter: --parts {n_parts} — PartCrafter makes 1 to {MAX_PARTS} parts",
                    "count the pieces you want as separate meshes (a sword: blade, guard, grip, pommel = 4)")
    if tokens not in (256, 512, 1024, 2048):
        return emit("fail", f"partcrafter: --tokens {tokens} — 256, 512, 1024 (default) or 2048 per part",
                    "leave --tokens out")
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    img = Image.open(src)
    if img.mode != "RGBA" or not cut_out_ok(np.asarray(img)[:, :, 3]):
        return emit("fail", f"partcrafter: {src} is not a cut-out (needs a transparent background around the object)",
                    f"lune run kit vision cutout {src} --rgba, then pass its _rgba.png")
    alpha = np.asarray(img)[:, :, 3]
    pins, problems = check_weights()
    if problems:
        return emit("fail", f"partcrafter: weights not ready — {problems[0]}",
                    "fetch them: python kit/gen/fetch.py --partcrafter (kit/gen/README.md)")
    if not os.path.isdir(os.path.join(SRC, "src", "pipelines")):
        return emit("fail", f"partcrafter: its code is not in {SRC}", "install it: kit/gen/README.md (PartCrafter)")
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return emit("fail", "partcrafter: no CUDA GPU visible", "check the NVIDIA driver (nvidia-smi)")
    free_gb = torch.cuda.mem_get_info()[0] / 2**30
    if free_gb < 6.0:
        return emit("fail", f"partcrafter: only {free_gb:.1f} GB of the GPU is free (it needs about 6)",
                    "close what holds the GPU (nvidia-smi), then run it again")
    t0 = time.time()
    from src.pipelines.pipeline_partcrafter import PartCrafterPipeline  # noqa: PLC0415
    from src.utils.image_utils import prepare_image  # noqa: PLC0415

    torch.manual_seed(seed)
    np.random.seed(seed % 2**32)
    pipe = PartCrafterPipeline.from_pretrained(os.path.join(WEIGHTS, "PartCrafter")).to("cuda", torch.float16)
    pipe.set_progress_bar_config(disable=True)
    t_load = time.time() - t0
    # the cut-out's own alpha: composited on white, cropped to the object, padded square (PartCrafter's preparation)
    picture = prepare_image(src, bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=None)
    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    out = pipe(
        image=[picture] * n_parts,
        attention_kwargs={"num_parts": n_parts},
        num_tokens=tokens,
        generator=torch.Generator(device="cuda").manual_seed(seed),
        num_inference_steps=steps,
        guidance_scale=guidance,
        max_num_expanded_coords=int(1e9),
    )
    t_gen = time.time() - t1
    peak = torch.cuda.max_memory_allocated() / 2**30
    empty = [k for k, m in enumerate(out.meshes, start=1) if m is None or len(m.faces) == 0]
    if empty:
        return emit("fail", f"partcrafter: part(s) {empty} came out empty (nothing to mesh)",
                    "another --seed, or fewer --parts")
    shaped = shape_up(list(out.meshes), alpha, stem)
    facts, sil, sil_mirror = shaped["part_facts"], shaped["silhouette_iou"], shaped["silhouette_iou_mirrored"]
    dupes = shaped["same_box_pairs"]
    record = {
        "engine": "partcrafter", "model": "wgsxm/PartCrafter", "licence": "MIT (code + weights); the DiT block code "
        "carries a Tencent Hunyuan Community License notice (VETLOG.md: the owner's call before shipping)",
        "private_only": True,  # (the owner's rule, 2026-10-07: Tencent-licensed generators -> private assets only)
        "parts": n_parts, "seed": seed, "tokens": tokens, "steps": steps, "guidance": guidance,
        "input": os.path.basename(src), "input_sha256": sha256(src),
        "weights": {k: v["sha256"][:16] for k, v in pins.items() if k.endswith(".safetensors")},
        "frame": "Roblox: +Y up, front (the picture's side) -Z, the object's own right +X; generated units "
                 "(the whole fits a 2-unit box); a.import_mesh reads it as is",
        **shaped,
        "seconds": round(time.time() - t0, 1), "seconds_load": round(t_load, 1), "seconds_generate": round(t_gen, 1),
        "peak_vram_gb": round(peak, 2), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(f"{stem}.parts.json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    tris = sum(f["triangles"] for f in facts)
    summary = (f"partcrafter: {n_parts} parts ({tris:,} triangles) in {record['seconds']} s, peak "
               f"{record['peak_vram_gb']} GB — front silhouette vs the picture IoU {sil}")
    warn = []
    if sil_mirror > sil + 0.05:
        warn.append(f"the mirrored parts match the picture better ({sil_mirror} > {sil}): check the frame")
    if dupes:
        warn.append(f"parts with the same box (a doubled part?): {dupes}")
    if sil < 0.6:
        warn.append(f"the front silhouette matches the picture poorly ({sil}): another --seed or a cleaner picture")
    split = [f"{f['part']} ({f['pieces']} pieces, largest {round(100 * f['main_share'])}%)" for f in facts
             if f["pieces"] > 1]
    if split:
        warn.append(f"parts in several pieces — {', '.join(split)}: compare main_box with box in the record "
                    "(a stray shard: a.import_mesh(..., crop=...) keeps a box of it) or another --seed")
    nxt = (f"improve: {'; '.join(warn)}" if warn else
           f"look at the parts ({stem}.parts.glb), then import each one in a MASTER build script — the lines are in "
           f"{stem}.parts.json (\"import\")")
    return emit("pass", summary, nxt, out=f"{stem}.parts.glb", record=f"{stem}.parts.json", parts=facts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
