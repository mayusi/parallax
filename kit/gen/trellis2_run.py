"""trellis2_run.py — a cut-out picture -> a textured, high-detail mesh (GLB) with TRELLIS.2, on this PC, offline.

TRELLIS.2-4B (Microsoft, MIT) runs in its own environment: ~/.cache/roblox-kit/envs/trellis2 (torch 2.10 + CUDA 13,
xformers, and CuMesh / FlexGEMM / o-voxel built from source on this machine — kit/gen/README.md). The kit calls it
(`lune run kit gen`); by hand:

    <envs/trellis2>/Scripts/python.exe kit/gen/trellis2_run.py <cutout_rgba.png> <out.glb> [--seed N] [--faces N]
        [--texture N] [--res 512|1024]

--res 1024: the 1024 cascade (the 512 flow, then the 1024 flow refines it) - finer shape and colour, slower; needs
the 1024 networks (kit/gen/fetch.py --1024, the owner approved them 2026-11-19).

What it guards:
- offline: every socket connection raises; Hugging Face runs in offline mode. Weights come from the verified local
  copies (~/.cache/roblox-kit/models/trellis2, each file's size checked against pins.json, written at download with
  the Hub's sha256).
- licences: the picture must already be cut out (RGBA) by the kit's BiRefNet (MIT) — TRELLIS.2's default remover,
  RMBG-2.0 (CC BY-NC), never loads; nvdiffrast (NVIDIA, non-commercial) is replaced by kit/gen/uvraster.py.
- 12 GB: the 512^3 pipeline in TRELLIS.2's low-VRAM mode (each network on the GPU only while it runs).
- RTX 50-series: attention runs on PyTorch (kit/gen/xops_sdpa.py answers TRELLIS.2's xformers calls; the xformers
  wheel has no kernel for compute capability 12.0).
The GLB keeps TRELLIS.2's own PBR maps (base colour, metallic, roughness, alpha); `<out>.json` records how it was
made (engine, weights, seed, the picture's sha256, time, peak memory).
"""

import hashlib
import json
import os
import socket
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".cache", "roblox-kit")
MODELS = os.environ.get("KIT_MODELS") or os.path.join(CACHE, "models")
WEIGHTS = os.path.join(MODELS, "trellis2")
SRC = os.environ.get("KIT_TRELLIS2_SRC") or os.path.join(CACHE, "src", "TRELLIS.2")
DINOV3 = os.environ.get("KIT_DINOV3") or os.path.join(WEIGHTS, "dinov3-vitl16-pretrain-lvd1689m")

os.environ.update(
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    HF_HUB_DISABLE_TELEMETRY="1",
    ATTN_BACKEND="sdpa",  # dense attention: PyTorch's own (xformers' Windows wheel has no compute-12.0 kernel)
    SPARSE_ATTN_BACKEND="xformers",  # sparse: the xformers API, answered by kit/gen/xops_sdpa.py on PyTorch
    SPARSE_CONV_BACKEND="flex_gemm",
    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True",
    OPENCV_IO_ENABLE_OPENEXR="1",
)


def _no_network(*_a, **_k):
    raise RuntimeError("kit gen runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

sys.path.insert(0, HERE)
sys.path.insert(0, SRC)
import uvraster  # noqa: E402
import xops_sdpa  # noqa: E402

_nv = types.ModuleType("nvdiffrast")
_nv.torch = uvraster
sys.modules["nvdiffrast"] = _nv
sys.modules["nvdiffrast.torch"] = uvraster
_xf = types.ModuleType("xformers")
_xf.ops = xops_sdpa
sys.modules["xformers"] = _xf
sys.modules["xformers.ops"] = xops_sdpa


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def check_weights():
    """every pinned weight file is there at its pinned size -> list of problems"""
    pins_path = os.path.join(WEIGHTS, "pins.json")
    if not os.path.isfile(pins_path):
        return [f"no {pins_path} — the TRELLIS.2 weights were never fetched"]
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
    return problems


# --res -> TRELLIS.2's pipeline_type. 1024 is the CASCADE: the 512 flow lays the shape, the 1024 flow refines it (its
# own README's default); "1024" alone (no 512 pass first) is not offered - the cascade is the release's own route.
PIPELINES = {"512": "512", "1024": "1024_cascade"}
HI_RES = ("slat_flow_img2shape_dit_1_3B_1024_bf16", "slat_flow_imgshape2tex_dit_1_3B_1024_bf16")


def hi_res_ready(weights=None):
    """the 1024 networks are on this PC (kit/gen/fetch.py --1024; their sizes then checked with the rest: pins.json)"""
    ck = os.path.join(weights or WEIGHTS, "TRELLIS.2-4B", "ckpts")
    return all(os.path.isfile(os.path.join(ck, f"{n}.{e}")) for n in HI_RES for e in ("json", "safetensors"))


def pipeline_config(source="pipeline.json", name="kit_pipeline.json"):
    """TRELLIS.2's pipeline.json (or texturing_pipeline.json: kit/gen/trellis2_texture.py) with every model at its
    local path (the 1024 networks dropped: not fetched), the image encoder at the local DINOv3 and no background
    remover -> (the weights folder, the config's file name)"""
    base = os.path.join(WEIGHTS, "TRELLIS.2-4B")
    with open(os.path.join(base, source), encoding="utf-8") as fh:
        cfg = json.load(fh)
    args = cfg["args"]
    local = {}
    for k, v in args["models"].items():
        if v.startswith("ckpts/"):
            p = os.path.join(base, v)
        else:  # "microsoft/TRELLIS-image-large/ckpts/..." — another repo's file, fetched beside it
            p = os.path.join(WEIGHTS, v.split("/", 1)[1])
        if os.path.isfile(p + ".json") and os.path.isfile(p + ".safetensors"):
            local[k] = p.replace("\\", "/")
        elif "1024" not in k:
            raise FileNotFoundError(f"TRELLIS.2 model {k} is not in {WEIGHTS}")
    args["models"] = local
    args["image_cond_model"]["args"]["model_name"] = DINOV3.replace("\\", "/")
    args["rembg_model"] = {"name": "KitCutoutDone", "args": {}}
    with open(os.path.join(base, name), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)
    return base, name


def install_compat():
    """transformers 5 moved DINOv3's transformer blocks from model.layer to model.model.layer; TRELLIS.2 (written for
    transformers 4) loops over model.layer. Same blocks, same weights (checked: 0 missing / unexpected keys) — this
    finds them wherever the installed version keeps them."""
    import torch.nn.functional as F  # noqa: PLC0415
    from trellis2.modules import image_feature_extractor as ife  # noqa: PLC0415

    def extract_features(self, image):
        m = self.model
        image = image.to(m.embeddings.patch_embeddings.weight.dtype)
        hidden = m.embeddings(image, bool_masked_pos=None)
        pos = m.rope_embeddings(image)
        for layer in (m.layer if hasattr(m, "layer") else m.model.layer):
            out = layer(hidden, position_embeddings=pos)
            hidden = out[0] if isinstance(out, tuple) else out
        return F.layer_norm(hidden, hidden.shape[-1:])

    ife.DinoV3FeatureExtractor.extract_features = extract_features


def watch_tuning():
    """FlexGEMM tunes its GPU kernels the first time it meets a problem size (and caches the choice in ~/.flex_gemm).
    On a 12 GB RTX 5070 (2026-10-06) every model generated WHILE kernels were being tuned came out with stray
    strands to the edge of the box; the same pictures and seeds after tuning came out clean (4 of 4). -> a counter of
    tunings during a run, so a run that tuned is generated again with the tuned kernels."""
    from flex_gemm.utils import autotuner as AT  # noqa: PLC0415

    state = {"tuned": 0}

    def wrap(cls, name):
        orig = getattr(cls, name)

        def counted(self, *a, **k):
            before = len(self.cache)
            out = orig(self, *a, **k)
            if len(self.cache) > before:
                state["tuned"] += 1
            return out

        setattr(cls, name, counted)

    wrap(AT.TritonPersistentCacheAutotuner, "run")
    wrap(AT.PersistentCacheAutoTuner, "__call__")
    return state


def extents(v):
    """the three side lengths of a vertex set's box, sorted (axes differ between the raw mesh and the GLB)"""
    import numpy as np  # noqa: PLC0415

    v = np.asarray(v, dtype=np.float64)
    return sorted((v.max(0) - v.min(0)).tolist())


class KitCutoutDone:
    """the picture comes cut out (kit vision cutout --rgba, BiRefNet MIT): TRELLIS.2's RMBG-2.0 never loads"""

    def __init__(self, **_):
        pass

    def to(self, *_a, **_k):
        return self

    def cpu(self):
        return self

    def cuda(self):
        return self

    def __call__(self, image):
        raise RuntimeError("kit gen: the picture must be an RGBA cut-out (lune run kit vision cutout <img> --rgba)")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) < 2 or not os.path.isfile(argv[0]):
        return emit("fail", "trellis2: usage: trellis2_run.py <cutout_rgba.png> <out.glb> [--seed N] [--faces N] "
                            "[--texture N] [--res 512|1024]", "cut the picture out first: lune run kit vision cutout <img> --rgba")
    src, out = argv[0], argv[1]
    seed, faces, tex = _opt(argv, "--seed", 1), _opt(argv, "--faces", 300000), _opt(argv, "--texture", 2048)
    res = _opt(argv, "--res", "512")
    if res not in PIPELINES:
        return emit("fail", f"trellis2: --res {res} - one of {', '.join(PIPELINES)}", "--res 512 (default) or --res 1024")
    if res != "512" and not hi_res_ready():
        return emit("fail", "trellis2: --res 1024 needs the 1024 networks, not fetched on this PC",
                    "<envs/trellis2>/Scripts/python.exe kit/gen/fetch.py --1024 (5.16 GB, the owner approved it)")
    from PIL import Image  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    img = Image.open(src)
    if img.mode != "RGBA" or np.all(np.asarray(img)[:, :, 3] == 255):
        return emit("fail", f"trellis2: {src} has no cut-out (no transparent background)",
                    f"lune run kit vision cutout {src} --rgba, then pass its _rgba.png")
    problems = check_weights()
    if problems:
        return emit("fail", f"trellis2: weights not ready — {problems[0]}", "fetch them: see kit/gen/README.md")
    if not os.path.isfile(os.path.join(DINOV3, "model.safetensors")):
        return emit("fail", f"trellis2: the DINOv3 image encoder is not in {DINOV3} (gated: Meta approves access)",
                    "the owner requests access to facebook/dinov3-vitl16-pretrain-lvd1689m on huggingface.co and "
                    "sets HF_TOKEN; then fetch it (kit/gen/README.md)")
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return emit("fail", "trellis2: no CUDA GPU visible", "check the NVIDIA driver (nvidia-smi)")
    t0 = time.time()
    from trellis2.pipelines import Trellis2ImageTo3DPipeline  # noqa: PLC0415
    from trellis2.pipelines import rembg  # noqa: PLC0415

    rembg.KitCutoutDone = KitCutoutDone
    install_compat()
    base, cfg_name = pipeline_config()
    pipe = Trellis2ImageTo3DPipeline.from_pretrained(base, config_file=cfg_name)
    pipe.low_vram = True
    pipe.cuda()
    tuning = watch_tuning()
    reruns = 0
    for _attempt in range(3):  # a run that tuned kernels is generated again, with them tuned (watch_tuning)
        tuning["tuned"] = 0
        torch.cuda.reset_peak_memory_stats()
        mesh = pipe.run(img, seed=seed, pipeline_type=PIPELINES[res])[0]
        if not tuning["tuned"]:
            break
        reruns += 1
        print(f"trellis2: {tuning['tuned']} GPU kernel(s) were tuned during this run (first use of these sizes) — "
              "generating again with them tuned", file=sys.stderr, flush=True)
    t_gen = time.time() - t0
    import o_voxel  # noqa: PLC0415

    raw = extents(mesh.vertices.float().cpu().numpy())
    for _attempt in range(2):  # the export must stay inside the generated shape (a few voxels of remeshing)
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices,
            faces=mesh.faces,
            attr_volume=mesh.attrs,
            coords=mesh.coords,
            attr_layout=mesh.layout,
            voxel_size=mesh.voxel_size,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=faces,
            texture_size=tex,
            remesh=True,
            remesh_band=1,
            remesh_project=0,
            verbose=False,
        )
        grown = max(abs(a - b) for a, b in zip(extents(glb.vertices), raw))
        if grown <= 0.02:
            break
    else:
        return emit("fail", f"trellis2: the export grew {grown:.3f} beyond the generated shape twice (stray geometry)",
                    "run it again; if it repeats, report it (kit/gen/README.md: known Windows issues)")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    glb.export(out, extension_webp=False)
    peak = torch.cuda.max_memory_allocated() / 2**30
    with open(os.path.join(WEIGHTS, "pins.json"), encoding="utf-8") as fh:
        pins = json.load(fh)
    record = {
        "engine": "trellis2", "model": "microsoft/TRELLIS.2-4B", "licence": "MIT",
        "image_encoder": "facebook/dinov3-vitl16-pretrain-lvd1689m (DINOv3 License; owner's decision 2026-10-06: all assets)",
        "pipeline_type": PIPELINES[res], "seed": seed, "faces": faces, "texture": tex, "reruns_after_tuning": reruns,
        "input": os.path.basename(src), "input_sha256": sha256(src),
        "weights": {k: v["sha256"][:16] for k, v in pins.items() if k.endswith(".safetensors")},
        "seconds": round(time.time() - t0, 1), "seconds_generate": round(t_gen, 1), "peak_vram_gb": round(peak, 2),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    base = os.path.splitext(out)[0]  # <name>.gen.glb -> <name>.gen.json (never <name>.gen.gen.json)
    with open((base[:-4] if base.endswith(".gen") else base) + ".gen.json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    return emit("pass", f"trellis2: {out} in {record['seconds']} s (peak {record['peak_vram_gb']} GB on the GPU)",
                f"import it: a.import_mesh(...) in the build script, then lune run kit asset <name>", out=out,
                record=record)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
