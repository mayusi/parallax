"""trellis2_texture.py — paint an EXISTING mesh from one picture with TRELLIS.2's texturing pipeline, here, offline.

The kit's code-built models are exact in shape and imitations on the surface; TRELLIS.2-4B's shape-conditioned
texturing (Trellis2TexturingPipeline, Microsoft, MIT) paints PBR maps — base colour, roughness, metallic — onto a GIVEN
mesh from a picture. The kit calls it (`lune run kit gen texture <asset> --image <picture>`); by hand:

    <envs/trellis2>/Scripts/python.exe kit/gen/trellis2_texture.py <mesh.ply|.obj|.glb> <picture> <out.glb>
        [--cutout <rgba.png>] [--seed N] [--texture N] [--turn DEG] [--steps N]

The guards are trellis2_run.py's (imported before anything heavy): offline (sockets blocked, HF offline), every
weight at its pinned size, no background remover but the kit's (a picture without a transparent background needs
--cutout: BiRefNet's, kit vision cutout — RMBG-2.0 never loads), nvdiffrast answered by uvraster.py,
attention on PyTorch, and a run during which FlexGEMM tuned kernels is done again (those runs come out corrupt).
512 only: the 1024 texture network is not fetched — kit_texturing.json leaves it out; low-VRAM mode (each network on
the GPU only while it runs).
The FRAME is kept: TRELLIS.2 works in a unit box (centred, longest side 1, Z up); the painted mesh is put back in the
input's own frame and size — checked to the float — so the kit's export (Roblox studs, Y up: glTF's frame) comes back
exactly where it was built, and a.texture_from(...) bakes it onto the asset.
--turn DEG turns the picture counter-clockwise first, so the object stands in it as the mesh stands (a sword
photographed lying down, for a model standing up; a reference trace's "rotate" is the same number).
The GLB has its own UVs (CuMesh + xatlas) and the maps; <out>.json records how it was made (seed, weights, the inputs'
sha256, time, peak GPU memory) and what came out (the texture's mean colour over the surface beside the picture's).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def unit_frame(vertices):
    """the frame TRELLIS.2's preprocess_mesh puts a mesh in -> (centre, scale): v_unit = (v - centre) * scale, the
    box centre and 0.99999 / the box's longest side (the same arithmetic, so the result can be put back exactly)"""
    import numpy as np  # noqa: PLC0415

    v = np.asarray(vertices, dtype=np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    return (lo + hi) / 2, 0.99999 / float((hi - lo).max())


def restore(vertices, centre, scale):
    """unit-box vertices (in the input's axes) -> the input's own frame and size"""
    import numpy as np  # noqa: PLC0415

    return np.asarray(vertices, dtype=np.float64) / scale + np.asarray(centre, dtype=np.float64)


def surface_mean(vertices, faces, uv, texture, samples=20000, seed=0):
    """the texture's mean over the SURFACE (area-weighted points, each read at its UV; texture rows top-down, UV v up as
    glTF/trimesh keep it) -> the mean of each channel (0..255)"""
    import numpy as np  # noqa: PLC0415

    v, f, t = np.asarray(vertices, np.float64), np.asarray(faces, np.int64), np.asarray(texture)
    uv = np.asarray(uv, np.float64)
    area = 0.5 * np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1)
    if area.sum() <= 0:
        return [0.0] * t.shape[-1]
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(f), size=samples, p=area / area.sum())
    r1, r2 = np.sqrt(rng.random(samples)), rng.random(samples)
    w = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], axis=1)
    p = (uv[f[pick]] * w[..., None]).sum(axis=1)
    h, wd = t.shape[:2]
    x = np.clip((p[:, 0] % 1.0) * wd, 0, wd - 1).astype(np.int64)
    y = np.clip((1 - p[:, 1] % 1.0) * h, 0, h - 1).astype(np.int64)
    return [round(float(c), 1) for c in t[y, x].reshape(samples, -1).mean(axis=0)]


def main(argv):
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    import trellis2_run as T  # noqa: PLC0415 — the offline guard and the shims, before torch / trellis2 load

    if len(pos) < 3 or not os.path.isfile(pos[0]) or not os.path.isfile(pos[1]):
        return T.emit("fail", "trellis2 texture: usage: trellis2_texture.py <mesh.ply|.obj|.glb> <picture> <out.glb> "
                              "[--cutout <rgba.png>] [--seed N] [--texture N] [--turn DEG] [--steps N]",
                      "lune run kit gen texture <asset> --image <picture>   (it exports the mesh and cuts the picture)")
    mesh_path, pic, out = pos[0], pos[1], pos[2]
    seed, tex, turn, steps = _opt(argv, "--seed", 1), _opt(argv, "--texture", 2048), _opt(argv, "--turn", 0.0), \
        _opt(argv, "--steps", 0)
    import numpy as np  # noqa: PLC0415
    import trimesh  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    def cut_out(path):  # an RGBA picture with a transparent background, or None
        im = Image.open(path)
        im = im.convert("RGBA") if im.mode in ("LA", "P") else im
        return im if im.mode == "RGBA" and not np.all(np.asarray(im)[:, :, 3] == 255) else None

    cutout = argv[argv.index("--cutout") + 1] if "--cutout" in argv else None
    img, cut_by = cut_out(pic), "its own transparency"
    if img is None and cutout and os.path.isfile(cutout):  # a background: BiRefNet's cut-out (kit vision cutout)
        img, cut_by = cut_out(cutout), "BiRefNet (kit vision cutout)"
    if img is None:
        return T.emit("fail", f"trellis2 texture: {pic} has a background and no cut-out was given",
                      f"lune run kit vision cutout {pic} --rgba, then pass --cutout <its _rgba.png>")
    mesh = trimesh.load(mesh_path, force="mesh", process=False)
    if not len(getattr(mesh, "faces", ())):
        return T.emit("fail", f"trellis2 texture: {mesh_path} holds no triangles", "export the asset again")
    problems = T.check_weights()
    if problems:
        return T.emit("fail", f"trellis2 texture: weights not ready — {problems[0]}",
                      "fetch them: see kit/gen/README.md")
    if not os.path.isfile(os.path.join(T.DINOV3, "model.safetensors")):
        return T.emit("fail", f"trellis2 texture: the DINOv3 image encoder is not in {T.DINOV3}",
                      "fetch it (kit/gen/README.md: fetch.py --dinov3)")
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return T.emit("fail", "trellis2 texture: no CUDA GPU visible", "check the NVIDIA driver (nvidia-smi)")
    t0 = time.time()
    from trellis2.pipelines import Trellis2TexturingPipeline  # noqa: PLC0415
    from trellis2.pipelines import rembg  # noqa: PLC0415

    rembg.KitCutoutDone = T.KitCutoutDone
    T.install_compat()
    base, cfg_name = T.pipeline_config("texturing_pipeline.json", "kit_texturing.json")
    pipe = Trellis2TexturingPipeline.from_pretrained(base, config_file=cfg_name)
    pipe.low_vram = True
    pipe.cuda()
    t_load = time.time() - t0
    if turn % 360:
        img = img.rotate(turn, resample=Image.BICUBIC, expand=True)  # (RGBA: the new corners come in transparent)
    image = pipe.preprocess_image(img)  # cropped square round the object, premultiplied (TRELLIS.2's own step)
    centre, scale = unit_frame(mesh.vertices)
    unit = pipe.preprocess_mesh(mesh)  # unit box, Y up -> TRELLIS.2's Z up
    params = {"steps": steps} if steps > 0 else {}
    tuning = T.watch_tuning()
    reruns, peak = 0, 0.0
    t1 = time.time()
    for _attempt in range(3):  # a run that tuned kernels is done again, with them tuned (trellis2_run.watch_tuning)
        tuning["tuned"] = 0
        torch.cuda.reset_peak_memory_stats()
        with torch.no_grad():
            torch.manual_seed(seed)
            cond = pipe.get_cond([image], 512)
            shape_slat = pipe.encode_shape_slat(unit, 512)
            slat = pipe.sample_tex_slat(cond, pipe.models["tex_slat_flow_model_512"], shape_slat, params)
            pbr = pipe.decode_tex_slat(slat)
            painted = pipe.postprocess_mesh(unit, pbr, 512, tex)  # its own UVs + the maps, back in the input's axes
        peak = max(peak, torch.cuda.max_memory_allocated() / 2**30)
        if not tuning["tuned"]:
            break
        reruns += 1
        print(f"trellis2 texture: {tuning['tuned']} GPU kernel(s) were tuned during this run (first use of these "
              "sizes) — painting again with them tuned", file=sys.stderr, flush=True)
    t_paint = time.time() - t1
    v = restore(painted.vertices, centre, scale)
    span = float((mesh.vertices.max(0) - mesh.vertices.min(0)).max())
    moved = float(max(np.abs(v.min(0) - mesh.vertices.min(0)).max(), np.abs(v.max(0) - mesh.vertices.max(0)).max()))
    if moved > 1e-4 * span:
        return T.emit("fail", f"trellis2 texture: the painted mesh's box moved {moved:.6f} from the input's (its frame "
                              "could not be put back)", "report it with the input mesh (kit/gen/README.md)")
    painted.vertices = v
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    painted.export(out, extension_webp=False)
    mat = painted.visual.material
    col = np.asarray(mat.baseColorTexture.convert("RGB"))
    mr = np.asarray(mat.metallicRoughnessTexture.convert("RGB"))  # glTF: G = roughness, B = metallic
    uv = painted.visual.uv
    pic_rgba = np.asarray(img.convert("RGBA")).reshape(-1, 4)
    seen = pic_rgba[pic_rgba[:, 3] > 127, :3]
    with open(os.path.join(T.WEIGHTS, "pins.json"), encoding="utf-8") as fh:
        pins = json.load(fh)
    wanted = ("shape_enc_next_dc", "tex_dec_next_dc", "slat_flow_imgshape2tex_dit_1_3B_512", "dinov3")
    record = {
        "engine": "trellis2-texturing", "model": "microsoft/TRELLIS.2-4B", "licence": "MIT",
        "image_encoder": "facebook/dinov3-vitl16-pretrain-lvd1689m (DINOv3 License; owner's decision 2026-10-06: "
                         "all assets)",
        "resolution": 512, "seed": seed, "steps": steps or pipe.tex_slat_sampler_params.get("steps"), "texture": tex,
        "turn": turn, "reruns_after_tuning": reruns,
        "mesh": os.path.basename(mesh_path), "mesh_sha256": T.sha256(mesh_path),
        "mesh_triangles": int(len(mesh.faces)), "painted_triangles": int(len(painted.faces)),
        "input": os.path.basename(pic), "input_sha256": T.sha256(pic), "cut_out_by": cut_by,
        **({"cutout_sha256": T.sha256(cutout)} if cut_by.startswith("BiRefNet") else {}),
        "weights": {k: v["sha256"][:16] for k, v in pins.items()
                    if k.endswith(".safetensors") and any(w in k for w in wanted)},
        "picture_mean_rgb": [round(float(c), 1) for c in seen.mean(axis=0)] if len(seen) else None,
        "texture_mean_rgb": surface_mean(v, painted.faces, uv, col),
        "texture_mean_rough_metal": [round(c / 255, 3) for c in surface_mean(v, painted.faces, uv, mr)[1:]],
        "frame_error": moved,
        "seconds": round(time.time() - t0, 1), "seconds_load": round(t_load, 1), "seconds_paint": round(t_paint, 1),
        "peak_vram_gb": round(peak, 2), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    source = os.path.splitext(mesh_path)[0] + ".json"  # what the kit's export wrote beside the mesh (texture_export.py)
    if os.path.isfile(source):
        with open(source, encoding="utf-8") as fh:
            record["source"] = json.load(fh)
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    return T.emit("pass", f"trellis2 texture: {out} in {record['seconds']} s (painting {record['seconds_paint']} s, "
                          f"peak {record['peak_vram_gb']} GB on the GPU; surface colour {record['texture_mean_rgb']}, "
                          f"the picture's {record['picture_mean_rgb']})",
                  "bake it onto the asset: a.texture_from(\"<asset>.tex.glb\") in its build script, then lune run kit "
                  "asset <asset>", out=out, record=record)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main(sys.argv[1:]))
