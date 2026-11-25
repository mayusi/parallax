"""pixal3d_run.py — 2 to 4 cut-out views of ONE object -> a textured mesh (GLB) with Pixal3D multi-view, offline.

Pixal3D (Tencent ARC, MIT, SIGGRAPH 2026) is built on TRELLIS.2 but projects every picture's features into its voxel
grid through that picture's camera, so the shape lines up with each view instead of being guessed from one. The kit
calls it with `lune run kit gen views`; by hand:

    <envs/trellis2>/Scripts/python.exe kit/gen/pixal3d_run.py <out.glb> --view side=<rgba.png> --view front=<rgba.png>
        [--view back=<rgba.png>] [--view top=<rgba.png>] [--ortho | --fov DEG] [--flip <view>] [--seed N]
        [--faces N] [--texture N] [--remesh 512] [--work DIR] [--resume]

--resume exports the shape the last run saved in the work folder (generated.pt) without generating again.

The views are the kit's (kit/gen/views_rig.py: side = the front on the RIGHT, top = the front at the top, ...); each
picture is re-framed from its silhouette, so crops and sizes do not matter. --ortho: chart drawings (a long lens far
away); without it: renders / photos at Pixal3D's 20-degree rig. The GLB comes out in Roblox space (y up, front -Z),
its longest side 1 unit: scale it with a.import_mesh(..., height=...).

What it guards:
- offline: every socket connection raises; weights come from the verified local copies (each file's size checked
  against ~/.cache/roblox-kit/models/pixal3d/pins.json, written at download with the Hub's sha256).
- licences: the views must already be cut out (RGBA) by the kit's BiRefNet — the BiRefNet remote code / RMBG-2.0
  (CC BY-NC) its config names never loads; DINOv3 from the owner's official copy (not the unofficial re-upload
  Pixal3D's code names); NAF from the vendored copy (kit/gen/naf_attn.py: no torch.hub); nvdiffrast never (uvraster).
- 12 GB: one network on the GPU at a time and NOT in memory otherwise (each is read from disk when its stage starts,
  every key checked); NAF's attention and the feature projection computed exactly in a fraction of the memory
  (naf_attn.py; features only at the occupied voxels); DINOv3 leaves the GPU while NAF runs.
- FlexGEMM's first kernel tuning corrupts a run (kit/gen/README.md): such a run is generated again.
- the export must stay within a few voxels of the generated shape; every view's silhouette is compared with the
  result's (silhouette IoU per view in the record).
"""

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.update(
    ATTN_BACKEND="sdpa",  # dense attention: PyTorch's own
    SPARSE_ATTN_BACKEND="xformers",  # sparse: the xformers API, answered by kit/gen/xops_sdpa.py on PyTorch
    SPARSE_CONV_BACKEND="flex_gemm",
    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True",
    OPENCV_IO_ENABLE_OPENEXR="1",
)
import gen_common as G  # noqa: E402
import views_rig as R  # noqa: E402

G.offline()
G.shims()

WEIGHTS = os.path.join(G.MODELS, "pixal3d")
PIX = os.path.join(WEIGHTS, "Pixal3D")
NAF_WEIGHTS = os.path.join(WEIGHTS, "naf", "naf_release.pth")
DINOV3 = os.environ.get("KIT_DINOV3") or os.path.join(G.MODELS, "trellis2", "dinov3-vitl16-pretrain-lvd1689m")
SRC = os.environ.get("KIT_PIXAL3D_SRC") or os.path.join(G.SRC, "Pixal3D")
PIXAL3D_COMMIT = "f7cf38429b0bd264f1995f0f8743a88b1c728b94"
CANVAS = 1024  # the framed pictures (the 1024 stages read them at full size, the 512 stages resized)
CHECK = 512  # silhouette check resolution
# Pixal3D's four condition stages (inference_mv.py IMAGE_COND_CONFIGS), the encoder at the local official copy
STAGES = {
    "ss": dict(image_size=512, grid_resolution=16),
    "shape_512": dict(image_size=512, grid_resolution=32, use_naf_upsample=True, naf_target_size=512),
    "shape_1024": dict(image_size=1024, grid_resolution=64, use_naf_upsample=True, naf_target_size=512),
    "tex_1024": dict(image_size=1024, grid_resolution=64, use_naf_upsample=True, naf_target_size=1024),
}
LOADED = []  # every network read from disk this run: (name, tensors)
PEAK = [0, 0]  # the generation's peak GPU memory, allocated / reserved (bytes): steps reset torch's counters


def _note_peak():
    import torch  # noqa: PLC0415

    PEAK[0] = max(PEAK[0], torch.cuda.max_memory_allocated())
    PEAK[1] = max(PEAK[1], torch.cuda.max_memory_reserved())
    return PEAK


def _where(key):
    if key.startswith("valeoai/"):
        return NAF_WEIGHTS
    return os.path.join(PIX, key.split("/", 2)[2])


def _head(src):
    head = os.path.join(src, ".git", "HEAD")
    return open(head, encoding="utf-8").read().strip() if os.path.isfile(head) else None


def check_ready():
    """-> (problem, fix) or None"""
    problems = G.pinned(WEIGHTS, _where)
    if problems:
        return (f"weights not ready — {problems[0]}",
                "fetch them: <envs/trellis2>/Scripts/python.exe kit/gen/pixal3d_fetch.py")
    if not os.path.isfile(os.path.join(DINOV3, "model.safetensors")):
        return (f"the DINOv3 image encoder is not in {DINOV3}",
                "fetch it: python kit/gen/fetch.py --dinov3 --only-dinov3")
    if _head(SRC) != PIXAL3D_COMMIT:
        return f"Pixal3D's code in {SRC} is not at the pinned commit {PIXAL3D_COMMIT[:7]}", "see kit/gen/README.md"
    import naf_attn  # noqa: PLC0415

    if naf_attn.vendored_commit() != naf_attn.NAF_COMMIT:
        return f"NAF's vendored copy is not at {naf_attn.NAF_COMMIT[:7]} ({naf_attn.NAF_SRC})", "see kit/gen/README.md"
    return None


# ---------------------------------------------------------------- the views: re-framed, posed, written as Pixal3D's
def prepare_views(specs, flips, fov, work):
    """{view: picture} -> the framed RGBA pictures + transforms.json in `work`, and what was measured"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageOps  # noqa: PLC0415

    cut, sizes, info = {}, {}, {}
    for view, path in specs.items():
        img = Image.open(path)
        if img.mode != "RGBA":
            img = img.convert("RGBA") if "transparency" in img.info else None
        if img is None or np.all(np.asarray(img)[:, :, 3] == 255):
            raise ValueError(f"{path} has no cut-out (no transparent background): "
                             f"lune run kit vision cutout {path} --rgba, then pass its _rgba.png")
        if view in flips:
            img = ImageOps.mirror(img)
        alpha = np.asarray(img)[:, :, 3] > 127
        ys, xs = np.nonzero(alpha)
        if len(xs) < 64:
            raise ValueError(f"{path}: the cut-out is (nearly) empty")
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        cut[view] = img.crop(box)
        sizes[view] = (box[2] - box[0], box[3] - box[1])
        info[view] = {"file": os.path.relpath(path, REPO).replace("\\", "/") if os.path.isabs(path) else path,
                      "sha256": G.sha256(path), "flipped": view in flips, "silhouette_px": list(sizes[view])}
    ext, off = R.fit_extents(sizes)
    main = R.choose_main(specs)
    os.makedirs(work, exist_ok=True)
    files = {}
    for view, img in cut.items():
        k = R.frame_scale(view, sizes[view], ext, CANVAS)
        w, h = max(1, round(sizes[view][0] * k)), max(1, round(sizes[view][1] * k))
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        canvas.paste(img.resize((w, h), Image.Resampling.LANCZOS), ((CANVAS - w) // 2, (CANVAS - h) // 2))
        files[view] = f"{view}.png"
        canvas.save(os.path.join(work, files[view]))
        info[view].update(scale=round(k, 4), disagreement_pct=off[view])
    with open(os.path.join(work, "transforms.json"), "w", encoding="utf-8") as fh:
        json.dump(R.transforms(files, main, fov), fh, indent=1)
    return main, ext, info


def load_bundle(work):
    """transforms.json + its pictures -> the bundle Pixal3D's run_mv() takes (as its inference_mv.load_views: each
    picture LANCZOS-resized to the stage size and premultiplied by its alpha, black background)"""
    import numpy as np  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    with open(os.path.join(work, "transforms.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    frames = meta["frames"]
    mats = torch.tensor([f["transform_matrix"] for f in frames], dtype=torch.float32)[None]
    fov = torch.tensor([float(f.get("camera_angle_x", meta["camera_angle_x"])) for f in frames])[None]
    rgba = [Image.open(os.path.join(work, f["file_path"])).convert("RGBA") for f in frames]

    def cond(im, size):
        im = im.resize((size, size), Image.Resampling.LANCZOS)
        a = torch.tensor(np.array(im.getchannel(3))).float() / 255.0
        rgb = torch.tensor(np.array(im.convert("RGB"))).permute(2, 0, 1).float() / 255.0
        return rgb * a[None]

    return {"images": {s: torch.stack([cond(im, s) for im in rgba])[None] for s in (512, 1024)},
            "camera_angle_x": fov, "camera_distance": torch.norm(mats[:, :, :3, 3], dim=-1),
            "transform_matrix": mats, "mesh_scale": float(meta.get("mesh_scale", 1.0)),
            "view_names": [f["name"] for f in frames]}


# ---------------------------------------------------------------- Pixal3D, adapted to this PC
def _params_on_meta():
    """a context in which every nn.Parameter is created on the meta device (no memory); buffers and plain tensors
    are created normally"""
    import contextlib  # noqa: PLC0415

    import torch.nn as nn  # noqa: PLC0415

    @contextlib.contextmanager
    def ctx():
        orig = nn.Module.register_parameter

        def register(self, name, param):
            if param is not None and param.device.type != "meta":
                param = nn.Parameter(param.to("meta"), requires_grad=param.requires_grad)
            orig(self, name, param)

        nn.Module.register_parameter = register
        try:
            yield
        finally:
            nn.Module.register_parameter = orig

    return ctx()


_LAZY = {}


def _lazy_class(cls):
    """cls, but its weights live on disk until a stage moves it to the GPU, and leave memory when it moves back:
    .to(cuda) reads the checkpoint (every key must match), .cpu() frees it"""
    if cls in _LAZY:
        return _LAZY[cls]
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    from safetensors import safe_open  # noqa: PLC0415

    def unload(self):
        if self._kit_on is not None:
            nn.Module.to_empty(self, device="meta")
            self._kit_on = None
            torch.cuda.empty_cache()

    def load(self, device):
        torch.cuda.empty_cache()  # (whatever the last stage left cached goes back first)
        nn.Module.to_empty(self, device=device)
        state = self.state_dict()
        unsaved = {n for n, _ in self.named_buffers()} - set(state)  # would stay uninitialised: refuse
        with safe_open(self._kit_file, framework="pt", device="cpu") as f:
            keys = set(f.keys())
            missing, extra = sorted(set(state) - keys) + sorted(unsaved), sorted(keys - set(state))
            if missing or extra:
                raise RuntimeError(f"{os.path.basename(self._kit_file)}: {len(missing)} missing key(s) {missing[:3]}, "
                                   f"{len(extra)} unexpected {extra[:3]}")
            for k in keys:
                state[k].copy_(f.get_tensor(k))
        LOADED.append((os.path.basename(self._kit_file), len(keys)))

    def to(self, *args, **kwargs):
        device, dtype, _nb, _fmt = torch._C._nn._parse_to(*args, **kwargs)
        if dtype is not None or device is None:
            return nn.Module.to(self, *args, **kwargs)
        if device.type == "cpu":
            unload(self)
        elif self._kit_on != device.type:
            unload(self)
            load(self, device)
            self._kit_on = device.type
        return self

    lazy = type(f"KitLazy{cls.__name__}", (cls,), {
        "to": to, "cpu": lambda self: self.to("cpu"),
        "cuda": lambda self, device=None: self.to(torch.device("cuda") if device is None else device)})
    _LAZY[cls] = lazy
    return lazy


def lazy_from_pretrained(path, **kwargs):
    """Pixal3D's models.from_pretrained, lazily (see _lazy_class) and strictly (theirs loads with strict=False)"""
    from pixal3d import models as PM  # noqa: PLC0415

    cfg_path, file = f"{path}.json", f"{path}.safetensors"
    if not (os.path.isfile(cfg_path) and os.path.isfile(file)):
        raise FileNotFoundError(f"Pixal3D network {path} is not here (kit/gen/pixal3d_fetch.py)")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cls = getattr(PM, cfg["name"])
    with _params_on_meta():
        net = cls(**cfg["args"], **kwargs)
    net.__class__ = _lazy_class(cls)
    net._kit_file, net._kit_on = file, None
    return net


def build_pipeline():
    """Pixal3D's multi-view pipeline with the kit's patches (module docstring) in low-VRAM mode"""
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from transformers import DINOv3ViTModel  # noqa: PLC0415

    import naf_attn  # noqa: PLC0415
    from pixal3d import models as PM  # noqa: PLC0415
    from pixal3d.modules.sparse import SparseTensor  # noqa: PLC0415
    from pixal3d.pipelines import rembg  # noqa: PLC0415
    from pixal3d.pipelines.pixal3d_mv_image_to_3d import Pixal3DMVImageTo3DPipeline  # noqa: PLC0415
    from pixal3d.trainers.flow_matching.mixins import image_conditioned_proj as IPC  # noqa: PLC0415

    shared = {}

    class LocalDino:
        """DINOv3 from the owner's official local copy, ONE instance shared by the four stages"""

        @staticmethod
        def from_pretrained(*_a, **_k):
            if "dino" not in shared:
                shared["dino"] = DINOv3ViTModel.from_pretrained(DINOV3, local_files_only=True)
            return shared["dino"]

    def extract_features(self, image):  # transformers 5 keeps DINOv3's blocks at model.model.layer
        m = self.model
        image = image.to(m.embeddings.patch_embeddings.weight.dtype)
        hidden = m.embeddings(image, bool_masked_pos=None)
        pos = m.rope_embeddings(image)
        for layer in G.dinov3_blocks(m):
            out = layer(hidden, position_embeddings=pos)
            hidden = out[0] if isinstance(out, tuple) else out
        return F.layer_norm(hidden, hidden.shape[-1:])

    def load_naf(self):  # the vendored NAF, one shared instance (no torch.hub)
        if self.naf_model is None:
            if "naf" not in shared:
                shared["naf"] = naf_attn.load_naf(NAF_WEIGHTS, "cpu")
            self.naf_model = shared["naf"].to(next(self.model.parameters()).device)

    def mv_forward(self, image, camera_angle_x=None, distance=None, mesh_scale=None, transform_matrix=None):
        """DinoV3ProjMultiViewFeatureExtractor.forward ("average" fusion), the same numbers; DINOv3 leaves the GPU
        before NAF's big feature maps are made"""
        B, V = image.shape[:2]
        calc = IPC.compute_relative_calc_mat(transform_matrix, distance, self.proj_grid.front_view_transform_matrix)
        flat = image.reshape(B * V, *image.shape[2:])
        with torch.no_grad():
            z = self.extract_features(self.transform(flat))
            reg = getattr(self.model.config, "num_register_tokens", 4)
            z_global = torch.cat([z[:, 0:1], z[:, 1:1 + reg]], 1)
            z_global = z_global.reshape(B, V, *z_global.shape[1:]).mean(1)
            patches = z[:, 1 + reg:].reshape(B * V, self.patch_number, self.patch_number, -1)
            del z
            if self.use_naf_upsample:
                self._load_naf()
                self.model.cpu()
                torch.cuda.empty_cache()
            fov, dist = camera_angle_x.reshape(B * V), distance.reshape(B * V)
            scale = mesh_scale[:, None].expand(B, V).reshape(B * V)
            calc = calc.reshape(B * V, 4, 4)
            acc = None
            for v in range(V):
                idx = torch.arange(v, B * V, V, device=patches.device)
                zv = self._project_single_view(patches[idx], flat[idx] if self.use_naf_upsample else None,
                                               fov[idx], dist[idx], scale[idx], calc[idx])
                acc = zv.contiguous() if acc is None else acc.add_(zv)
                del zv
        return z_global, acc.div_(V)

    IPC.DINOv3ViTModel = LocalDino
    IPC.DinoV3ProjFeatureExtractor.extract_features = extract_features
    IPC.DinoV3ProjFeatureExtractor._load_naf = load_naf
    IPC.DinoV3ProjMultiViewFeatureExtractor.forward = mv_forward
    PM.from_pretrained = lazy_from_pretrained
    rembg.KitCutoutDone = G.KitCutoutDone

    class KitMV(Pixal3DMVImageTo3DPipeline):
        @torch.no_grad()
        def get_proj_cond_shape(self, image_cond_model, image, coords, camera_angle_x=None, distance=None,
                                mesh_scale=1.0, grid_resolution_override=None):
            """the stage's condition at the occupied voxels only: the same values Pixal3D reads out of its full
            R^3 grid (index x R^2 + y R + z), without building the grid"""
            views = self._views_of(image)
            if self.low_vram:
                image_cond_model.to(self.device)
            pg = image_cond_model.proj_grid
            res = grid_resolution_override or image_cond_model.grid_resolution
            if int(coords[:, 0].max()) != 0:
                raise NotImplementedError("kit: one object at a time")
            full = IPC.ProjGridMV(grid_resolution=res, image_resolution=pg.image_resolution).grid_points
            c = coords.long().cpu()
            saved = pg.grid_points
            pg.grid_points = full[c[:, 1] * res * res + c[:, 2] * res + c[:, 3]].to(self.device)
            try:
                z_global, z_proj = self._run_extractor(image_cond_model, views, camera_angle_x, distance, mesh_scale)
            finally:
                pg.grid_points = saved
            if self.low_vram:
                image_cond_model.cpu()
            # hand NAF's freed maps back to the driver before the next network loads: on Windows a process that keeps
            # them cached pushes the GPU past its 12 GB into shared system memory (the stage then runs ~4x slower)
            torch.cuda.empty_cache()
            feats = z_proj[0]
            return {"cond": {"global": z_global, "proj": SparseTensor(feats=feats, coords=coords)},
                    "neg_cond": {"global": torch.zeros_like(z_global),
                                 "proj": SparseTensor(feats=torch.zeros_like(feats), coords=coords)}}

    with open(os.path.join(PIX, "pipeline_mv.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["args"]["rembg_model"] = {"name": "KitCutoutDone", "args": {}}  # never briaai/RMBG-2.0 (CC BY-NC)
    with open(os.path.join(PIX, "kit_pipeline_mv.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)
    pipe = KitMV.from_pretrained(PIX, "kit_pipeline_mv.json")
    for stage, args in STAGES.items():
        m = IPC.DinoV3ProjMultiViewFeatureExtractor(model_name=DINOV3, multiview_fusion="average", **args)
        m.train(False)
        setattr(pipe, f"image_cond_model_{stage}", m)
    pipe._device = torch.device("cuda")
    pipe.low_vram = True
    return pipe


PBR_LAYOUT = {"base_color": slice(0, 3), "metallic": slice(3, 4), "roughness": slice(4, 5), "alpha": slice(5, 6)}


def generate(work, seed, key):
    """the views -> the generated shape + its texture voxels (on the CPU, ready to save) and how it went"""
    import gc  # noqa: PLC0415

    import torch  # noqa: PLC0415

    t0 = time.time()
    pipe = build_pipeline()
    bundle = load_bundle(work)
    tuning = G.watch_tuning()
    stages = _time_stages(pipe)
    reruns = 0
    torch.cuda.reset_peak_memory_stats()
    for _attempt in range(3):  # a run that tuned kernels is generated again, with them tuned
        tuning["tuned"] = 0
        stages.clear()
        LOADED.clear()
        meshes, (_shape, _tex, res) = pipe.run_mv(bundle, seed=seed, pipeline_type="1024_cascade",
                                                  max_num_tokens=49152, return_latent=True)
        if not tuning["tuned"]:
            break
        reruns += 1
        print(f"pixal3d: {tuning['tuned']} GPU kernel(s) were tuned during this run (first use of these sizes) — "
              "generating again with them tuned", file=sys.stderr, flush=True)
    m = meshes[0]
    gen = {"key": key, "vertices": m.vertices.float().cpu(), "faces": m.faces.cpu(), "attrs": m.attrs.cpu(),
           "coords": m.coords.cpu(), "res": int(res), "reruns": reruns, "seconds": round(time.time() - t0, 1),
           "stages": [list(s) for s in stages], "networks_loaded": len(LOADED),
           "peak_vram_gb": round(_note_peak()[0] / 2**30, 2), "peak_vram_reserved_gb": round(PEAK[1] / 2**30, 2)}
    del pipe, bundle, meshes, m, _shape, _tex
    gc.collect()
    torch.cuda.empty_cache()
    return gen


def _time_stages(pipe):
    """[[step, seconds, its peak GPU GB], ...] in the order the pipeline runs them (its condition, sampling and
    decoding steps)"""
    import torch  # noqa: PLC0415

    stages = []

    def wrap(obj, attr, label):
        orig = getattr(obj, attr)

        def timed(*a, **k):
            torch.cuda.synchronize()
            _note_peak()  # (the run's peak so far, kept)
            torch.cuda.reset_peak_memory_stats()
            t = time.time()
            out = orig(*a, **k)
            torch.cuda.synchronize()
            peak = torch.cuda.max_memory_allocated()
            _note_peak()
            stages.append([label, round(time.time() - t, 1), round(peak / 2**30, 2)])
            return out

        setattr(obj, attr, timed)

    wrap(pipe, "get_proj_cond_ss", "condition 16^3")
    wrap(pipe, "get_proj_cond_shape", "condition (NAF)")
    wrap(pipe, "decode_latent", "decode")
    wrap(pipe.sparse_structure_sampler, "sample", "sample structure")
    wrap(pipe.shape_slat_sampler, "sample", "sample shape")
    wrap(pipe.tex_slat_sampler, "sample", "sample texture")
    return stages


def drop_strays(gen):
    """the decoded mesh without vertices outside the generator's box (measured 2026-10-07: a two-view chest came out
    with 4,813 of 7.9M vertices at z = 1.3e25 — a numerical glitch: every vertex of the dual grid lies in its voxel)
    and the faces that use them -> (vertices, faces, stray vertices, faces dropped)"""
    import torch  # noqa: PLC0415

    v, f = gen["vertices"], gen["faces"].long()
    bad = ~(torch.isfinite(v).all(1) & (v.abs() <= 0.5 + 2.0 / gen["res"]).all(1))
    n = int(bad.sum())
    if not n:
        return v, gen["faces"], 0, 0
    keep = ~bad[f].any(1)
    f = f[keep]
    used = torch.zeros(len(v), dtype=torch.bool)
    used[f.reshape(-1)] = True
    remap = torch.full((len(v),), -1, dtype=torch.long)
    remap[used] = torch.arange(int(used.sum()))
    return v[used], remap[f].to(gen["faces"].dtype), n, int((~keep).sum())


def export(gen, faces, tex, remesh_res):
    """the saved shape -> (GLB in the generator's frame, how far it grew), remeshed + textured on the GPU; (None,
    grown) when it grew past a few voxels twice.
    The surface is rebuilt (dual contouring) on a remesh_res^3 grid: o-voxel would use the generation's 1024^3 —
    measured on the chest: 31.9M faces and 12.75 GB of GPU memory before the decimation to ~300k faces, against 7.0M
    faces and 3.1 GB at 512 (the same final triangle budget). The textures are still sampled from the 1024 voxels."""
    import cumesh  # noqa: PLC0415
    import torch  # noqa: PLC0415

    import o_voxel  # noqa: PLC0415

    dc = cumesh.remeshing.remesh_narrow_band_dc

    def remesh(vertices, faces_, center, scale, resolution, band=1, **kw):
        if resolution > remesh_res:  # the same box (o-voxel pads it by 3 bands of its own grid), a coarser grid
            box = scale * resolution / (resolution + 3 * band)
            scale, resolution = (remesh_res + 3 * band) / remesh_res * box, remesh_res
        return dc(vertices, faces_, center=center, scale=scale, resolution=resolution, band=band, **kw)

    verts, tris, gen["stray_vertices"], gen["stray_faces"] = drop_strays(gen)
    raw = G.extents(verts.numpy())
    grown = 0.0
    cumesh.remeshing.remesh_narrow_band_dc = remesh
    try:
        for _attempt in range(2):  # the export must stay inside the generated shape (a few voxels of remeshing)
            glb = o_voxel.postprocess.to_glb(
                vertices=verts.cuda(), faces=tris.cuda(), attr_volume=gen["attrs"].cuda(),
                coords=gen["coords"].cuda(), attr_layout=PBR_LAYOUT, grid_size=gen["res"],
                aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]], decimation_target=faces, texture_size=tex, remesh=True,
                remesh_band=1, remesh_project=0, verbose=False)
            torch.cuda.empty_cache()
            grown = max(abs(a - b) for a, b in zip(G.extents(glb.vertices), raw))
            if grown <= 0.02:
                return glb, grown
        # the rebuilt surface strayed twice (a thin object: the Glock, 2026-10-09, 0.705 off) — the decoded surface
        # itself, only decimated, under the same check
        glb = o_voxel.postprocess.to_glb(
            vertices=verts.cuda(), faces=tris.cuda(), attr_volume=gen["attrs"].cuda(), coords=gen["coords"].cuda(),
            attr_layout=PBR_LAYOUT, grid_size=gen["res"], aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=faces, texture_size=tex, remesh=False, verbose=False)
        torch.cuda.empty_cache()
        grown = max(abs(a - b) for a, b in zip(G.extents(glb.vertices), raw))
        if grown <= 0.02:
            gen["export"] = "decoded surface, decimated (the remesh strayed)"
            return glb, grown
    finally:
        cumesh.remeshing.remesh_narrow_band_dc = dc
    return None, grown


# ---------------------------------------------------------------- the check: the result seen from every view
def silhouette_ious(vertices, faces, work, views, fov):
    """{view: IoU of the result's silhouette with the framed picture's} at CHECK x CHECK"""
    import numpy as np  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    import uvraster  # noqa: PLC0415

    tri = torch.as_tensor(np.asarray(faces), dtype=torch.int64, device="cuda")
    out = {}
    for view in views:
        px = R.project(vertices, view, fov, CHECK)
        clip = np.stack([2 * px[:, 0] / CHECK - 1, 2 * px[:, 1] / CHECK - 1, np.zeros(len(px)), np.ones(len(px))], -1)
        rast, _ = uvraster.rasterize(None, torch.as_tensor(clip, dtype=torch.float32, device="cuda")[None], tri,
                                     (CHECK, CHECK))
        mine = (rast[0, :, :, 3] > 0).cpu().numpy()
        a = Image.open(os.path.join(work, f"{view}.png")).getchannel(3).resize((CHECK, CHECK), Image.Resampling.BOX)
        ref = np.asarray(a) > 127
        out[view] = round(float((mine & ref).sum() / max(1, (mine | ref).sum())), 4)
    return out


def main(argv):
    if not argv or argv[0].startswith("--") or not G.opts(argv, "--view"):
        return G.emit("fail", "pixal3d: usage: pixal3d_run.py <out.glb> --view side=<rgba.png> --view front=<rgba.png> "
                              "[--view back=...] [--view top=...] [--ortho | --fov DEG] [--flip <view>] [--seed N]",
                      "lune run kit gen views <name> --view side=<rgba.png> --view front=<rgba.png> [--ortho]")
    out = argv[0]
    specs = {}
    for v in G.opts(argv, "--view"):
        name, _, path = v.partition("=")
        if name not in R.VIEWS or not path:
            return G.emit("fail", f"pixal3d: --view {v}: use <{'|'.join(R.ORDER)}>=<picture>",
                          "e.g. --view side=refs/x_side_rgba.png --view front=refs/x_front_rgba.png")
        if not os.path.isfile(path):
            return G.emit("fail", f"pixal3d: {path} not found", "check the path of every --view")
        specs[name] = path
    flips = set(G.opts(argv, "--flip"))
    ortho = "--ortho" in argv
    fov = G.opt(argv, "--fov", R.ORTHO_FOV if ortho else R.PERSPECTIVE_FOV)
    seed, faces, tex = G.opt(argv, "--seed", 1), G.opt(argv, "--faces", 300000), G.opt(argv, "--texture", 2048)
    remesh_res = G.opt(argv, "--remesh", 512)  # the export's surface grid (1024 needs ~13 GB: export())
    stem = os.path.splitext(os.path.basename(out))[0]
    work = G.opt(argv, "--work", os.path.join(REPO, "build", "gen", f"{stem}_views"))
    record_path = os.path.splitext(out)[0] + ".json"  # <name>.gen.glb -> <name>.gen.json
    try:
        main_view, ext, info = prepare_views(specs, flips, fov, work)
    except ValueError as e:
        return G.emit("fail", f"pixal3d: {e}", "give cut-outs of one object from the kit's views (kit/gen/README.md)")
    problem = check_ready()
    if problem:
        return G.emit("fail", f"pixal3d: {problem[0]}", problem[1])
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return G.emit("fail", "pixal3d: no CUDA GPU visible", "check the NVIDIA driver (nvidia-smi)")
    t0 = time.time()
    saved = os.path.join(work, "generated.pt")  # the shape before export: --resume exports it again, no regenerating
    key = {"views": {v: info[v]["sha256"] for v in sorted(info)}, "flips": sorted(flips), "seed": seed, "fov": fov,
           "code": PIXAL3D_COMMIT}
    gen = None
    if "--resume" in argv:
        if not os.path.isfile(saved):
            return G.emit("fail", f"pixal3d: --resume: nothing saved in {saved}", "run the command without --resume")
        gen = torch.load(saved, map_location="cpu", weights_only=True)
        if gen.get("key") != key:
            return G.emit("fail", "pixal3d: --resume: the saved shape was made from other views / seed / lens",
                          "run the command without --resume")
    if gen is None:
        gen = generate(work, seed, key)
        torch.save(gen, saved)
    import numpy as np  # noqa: PLC0415

    torch.cuda.reset_peak_memory_stats()
    try:
        glb, grown = export(gen, faces, tex, remesh_res)
    except RuntimeError as e:  # (torch's OutOfMemoryError is one; CuMesh raises a plain one)
        if "out of memory" not in str(e).lower():
            raise
        return G.emit("fail", "pixal3d: the GPU ran out of memory while exporting (the generated shape is saved)",
                      "free the GPU (other programs on it), then the same command with --resume: it exports the "
                      "saved shape without generating again")
    if glb is None:
        return G.emit("fail", f"pixal3d: the export grew {grown:.3f} beyond the generated shape twice (stray geometry)",
                      "run it again with another --seed; if it repeats, report it (kit/gen/README.md)")
    glb.apply_transform(R.glb_to_roblox(main_view))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    glb.export(out, extension_webp=False)
    peak_export = torch.cuda.max_memory_allocated() / 2**30
    peak, peak_reserved = gen["peak_vram_gb"], gen["peak_vram_reserved_gb"]
    t_gen, reruns = gen["seconds"], gen["reruns"]
    ious = silhouette_ious(glb.vertices, glb.faces, work, specs, fov)
    v = np.asarray(glb.vertices)
    size = v.max(0) - v.min(0)
    with open(os.path.join(WEIGHTS, "pins.json"), encoding="utf-8") as fh:
        pins = json.load(fh)
    record = {
        "engine": "pixal3d-mv", "model": "TencentARC/Pixal3D (multi-view)", "licence": "MIT",
        "code": f"TencentARC/Pixal3D@{PIXAL3D_COMMIT[:7]}",
        "image_encoder": "facebook/dinov3-vitl16-pretrain-lvd1689m (DINOv3 License; owner's decision 2026-10-06: "
                         "all assets)",
        "pipeline_type": "1024_cascade", "seed": seed, "faces": faces, "texture": tex, "remesh": remesh_res,
        "reruns_after_tuning": reruns, "stray_vertices_dropped": gen["stray_vertices"],
        "stray_faces_dropped": gen["stray_faces"],
        "rig": {"ortho": ortho, "fov_deg": fov, "distance": round(R.distance(fov), 4), "half_width": R.HALF,
                "main_view": main_view, "frame": "Roblox: x right, y up, front -Z; longest side 1"},
        "views": info, "extents_from_views": [round(float(e), 4) for e in ext],
        "extents_generated": [round(float(s), 4) for s in size],
        "silhouette_iou": ious, "silhouette_iou_min": min(ious.values()),
        "weights": {k: p["sha256"][:16] for k, p in pins.items() if k.endswith((".safetensors", ".pth"))},
        "networks_loaded": gen["networks_loaded"], "resumed": "--resume" in argv,
        "seconds": round(time.time() - t0 + (t_gen if "--resume" in argv else 0), 1), "seconds_generate": t_gen,
        "seconds_stages": gen["stages"], "peak_vram_gb": peak, "peak_vram_reserved_gb": peak_reserved,
        "peak_vram_export_gb": round(peak_export, 2), "triangles": len(glb.faces),
        "work": os.path.relpath(work, REPO).replace("\\", "/"), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(record_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    worst = min(ious, key=ious.get)
    warn = [f"{v} view disagrees with the others by {abs(info[v]['disagreement_pct']):.0f}% (its proportions)"
            for v in info if abs(info[v]["disagreement_pct"]) > 5]
    if ious[worst] < 0.85:
        warn.append(f"the result matches the {worst} view's silhouette only {ious[worst]:.0%}")
    if gen["stray_faces"] > 0.01 * len(gen["faces"]):
        warn.append(f"{gen['stray_faces']} decoded faces had stray vertices and were dropped (look for holes)")
    glb_path = out.replace("\\", "/")
    nxt = (f'import it: a.import_mesh("Body", "{glb_path}", height=...) in a MASTER build script, '
           "then lune run kit asset <name>")
    if warn:
        nxt = "check " + "; ".join(warn) + " (another --seed, or fix that picture) — or " + nxt
    return G.emit("pass", f"pixal3d: {out} in {record['seconds']} s (peak {record['peak_vram_gb']} GB on the GPU; "
                          f"silhouettes {', '.join(f'{k} {v:.2f}' for k, v in ious.items())})",
                  nxt, out=out, record=record_path, warnings=warn)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
