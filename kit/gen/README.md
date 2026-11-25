# kit gen — generated shapes and textures, on this PC

The kit's code-built models top out where sculpting starts: a wolf's head, feathers, engraving, real material
variation. `kit gen` makes that part with a generative model instead — **TRELLIS.2** (Microsoft, MIT): one picture
in, a high-detail mesh with its own PBR maps (base colour, metallic, roughness) out — and the kit does the rest
(scale, cut into moving parts, joints, every gate, `kit optimize` to Roblox's budget, the judge, the showcase).

Everything runs **locally and offline** (the owner's rule: no cloud services). The picture never leaves the PC.

## Use

```
lune run kit gen chest --image refs/chest_front.png [--seed 7] [--faces 300000] [--texture 2048]
```
1. the picture is cut out (`kit vision cutout`, BiRefNet) — one object, a plain background works best;
2. TRELLIS.2 generates it (512³, low-VRAM mode: ~2.7 GB of the GPU, ~3–4 min on an RTX 5070);
3. `assets/models/chest.gen.glb` + `chest.gen.json` (seed, weights, the picture's sha256, time, memory).

Then, in a MASTER build script (`stage="master"`: a generated mesh is 100k+ triangles):
```python
a = rbx.Asset("chest", stage="master", kind="chest", ...)
a.import_mesh("Body", "assets/models/chest.gen.glb", height=2.4)   # its own textures come along
a.cut(...)                    # split moving pieces out of it like any part (lid, drawer, trigger)
a.joint("Lid", "lid", "hinge", ...)
```
and `lune run kit optimize chest` for the game version. Not happy with a shape? Another `--seed`.

Scanned materials for what the kit still builds itself: `a.material("bronze", (0.55, 0.36, 0.2), metal=1,
rough=0.35, scan="Metal008", scan_mix=0.6)` (the 12 owner-approved ambientCG scans: rbx_scans.py).

## Paint a kit model from a picture (`kit gen texture`)

A code-built model is exact in shape and an imitation on the surface. TRELLIS.2 also ships a shape-conditioned
texturing pipeline: it paints base colour, roughness and metallic onto a GIVEN mesh from a picture. The kit uses it
on the asset's own geometry:
```
lune run kit asset arming_sword                     # a full build first: what gets painted is its last full build
lune run kit gen texture arming_sword --image refs/arming_sword_front.jpg --turn -90 [--group <g>] [--seed 7]
```
1. the picture is cut out (BiRefNet) unless it already has a transparent background;
2. the build (`build/models/<asset>.blend`, every group or `--group`) is exported in the kit's own space — Roblox
   studs, Y up, -Z front, the frame a glTF file uses (`kit/blender/texture_export.py`);
3. TRELLIS.2 paints it (`trellis2_texture.py`: 512, low-VRAM) and the result is put back in that frame to the float
   (checked) -> `assets/models/<asset>.tex.glb` (the same surface, its own UVs + the three maps) + `<asset>.tex.json`
   (seed, weights, the inputs' sha256, time, peak memory, the surface's mean colour beside the picture's).

Then in the build script, before `a.build()`:
```python
a.texture_from("arming_sword.tex.glb", mix=1.0, groups=None, channels=("color", "rough", "metal"))
```
At bake time the painted mesh is imported where the parts are and baked onto the asset's own atlas by the closest
surface (selected-to-active from the painted mesh: each texel takes the paint right over it), then mixed over the
kit's own maps by `mix` BEFORE the kit's surface pass — AO, edge wear, chips, grime, patterns and the rounded-edge
normals still ride on top. Facts per group (`facts.texture_from` in the build verdict): coverage % of the atlas's
texels the paint was found over, the mean difference it made per map, the kit's and the paint's mean colour. It is
part of the bake cache key (a new paint, mix or channel list bakes again); a coverage under 90% warns
(`texture_coverage`: the shape changed since it was painted — paint it again). `--turn` stands the object in the
picture as the model stands (counter-clockwise degrees; a reference trace's `rotate` is the same number). A game
version (`kit optimize`) takes the master's paint: its cut's deviation widens the bake's reach. The `.tex.glb` belongs
beside the build script like a `.gen.glb`: a script that calls `texture_from` needs it to build.

**Measured (RTX 5070, 2026-10-06, the arming sword: 644 triangles, 2048 texture):** painting 11–12 s once the GPU
kernels are tuned; loading the networks 46–79 s; peak **2.52 GB**; the first run ever at these sizes tuned 38
kernels and painted twice (65 s). `kit gen texture` end to end 2 min 36 s (cut-out 48 s cold). Frame error 3e-8
studs. The bake transfer: 2.0–2.3 s at 1024, **coverage 100 %** of 171,130 texels. Per part, sRGB means of the baked
atlas — picture / kit's own materials / painted: blade (224,224,224) / (204,200,194) / (246,246,246); guard
(188,188,188) / (168,165,162) / (179,180,180); grip (91,67,65) / (98,67,53) / (43,27,21); pommel (165,165,165) /
(188,184,179) / (179,180,181) — the paint takes the picture's pattern (neutral polished steel, metallic 0.92–0.98,
smooth; a dark red-brown leather grip, rough 0.91, not metal) and gives albedo, not the lit photo's values. The same
photo recoloured (gold blade, blue grip) painted a gold blade (249,169,1) and a blue grip (1,64,167): it follows the
picture, not the model's materials.

**Limits.** 512 only (the 1024 texture network is fetched since 2026-11-19 for `kit gen --res 1024`; this texturing
route still runs at 512): colour detail is about 1/512 of the model's longest
side — panels, wraps and two-tone finishes, not lettering or engraving (that is `a.relief` / `a.displace`). One
picture: the sides it does not show are guessed. TRELLIS.2 decides what is metal (the gold-painted blade came out
non-metallic): `channels=("color",)` keeps the kit's own roughness and metallic, `mix` < 1 keeps some of its colour.
Albedo, not the photo: a lit leather grip comes out darker than it looks in the picture. Shape edits after painting
leave texels uncovered (the warning) — paint again. The weapon question is the one above (DINOv3's licence; the
owner's decision covers it).

## Weapons

TRELLIS.2 reads pictures through Meta's **DINOv3** encoder, whose licence (s.1(v), a trade-controls clause) bars uses
"related to … the development or use of guns or illegal weapons". The owner weighed it and decided (2026-10-06):
**TRELLIS.2 is used for every asset, weapons included** ("we will use anything we have at our disposal"). The
decision is the owner's, recorded in VETLOG.md; TRELLIS v1 (MIT, an Apache-2.0 encoder) stays uninstalled.

## What is installed (VETLOG.md has the vetting rows)

| Where | What | Licence |
|---|---|---|
| `~/.cache/roblox-kit/envs/trellis2` | Python 3.11 env: torch 2.10.0+cu130, torchvision 0.25.0, xformers 0.0.35 (unused, see below), transformers, timm, kornia, trimesh, opencv, utils3d @9a4eb15, triton-windows 3.8 (FlexGEMM's kernels) | BSD / Apache / MIT |
| `~/.cache/roblox-kit/src` | TRELLIS.2 (code only) + o-voxel, CuMesh (+cubvh), FlexGEMM — **compiled on this PC** (nvcc 13.1 + MSVC 2022, `TORCH_CUDA_ARCH_LIST=12.0`), Eigen (o-voxel's submodule) | MIT / MPL-2.0 |
| `~/.cache/roblox-kit/models/trellis2` | TRELLIS.2-4B 512 set (10.35 GB) + TRELLIS-image-large's structure decoder (0.15 GB); DINOv3 ViT-L/16 once Meta approves (1.21 GB); `pins.json` | MIT; DINOv3 License |
| `~/.cache/roblox-kit/materials` | 12 ambientCG scans, 2K (196.9 MB); `pins.json` | CC0 |

**Not installed, on purpose:** nvdiffrast / nvdiffrec (NVIDIA Source Code License: non-commercial use only — a game
asset is commercial use) and RMBG-2.0 (CC BY-NC, TRELLIS.2's default background remover).

## Why the kit code in this folder exists

- `uvraster.py` — the two nvdiffrast calls TRELLIS.2's GLB export makes (rasterize in UV space + interpolate), in
  plain PyTorch with nvdiffrast's conventions; installed as `nvdiffrast.torch` by the runner.
- `xops_sdpa.py` — the two xformers calls TRELLIS.2's sparse attention makes, on PyTorch's own attention: the
  xformers Windows wheel has no kernel for compute capability 12.0 (RTX 50-series), PyTorch's does.
- `patch_ovoxel_msvc.py` — o-voxel is written for GCC; three MSVC fixes (compile flags as CuMesh/FlexGEMM use,
  size_t casts, GCC's `d` literal suffix). Nothing it computes changes.
- `trellis2_run.py` — the runner: offline (sockets blocked, HF offline), weights checked against `pins.json`, the
  shims installed, RMBG never loaded, 512 pipeline in low-VRAM mode, the GLB + its `.gen.json` record.
- `trellis2_texture.py` — the texturing runner (`kit gen texture`): the same guards (it imports `trellis2_run`), the
  texturing pipeline at 512 from `kit_texturing.json` (texturing_pipeline.json without the unfetched 1024 network),
  the unit box undone exactly (`unit_frame` / `restore`, tested), the `.tex.glb` + its `.tex.json` record.
- `fetch.py` — fetches and verifies the weights (`--dinov3` for the encoder: reads HF_TOKEN from the environment;
  `--partcrafter` for PartCrafter, at its vetted commit).
- `partcrafter_run.py` — `kit gen parts`' runner (the PartCrafter section below).

## Reinstall from scratch (what was run, 2026-10-06)

```
py -3.11 -m venv %USERPROFILE%\.cache\roblox-kit\envs\trellis2
<env>\Scripts\python -m pip install torch-2.10.0+cu130 torchvision-0.25.0+cu130 xformers-0.0.35   (download.pytorch.org/whl/cu130, sha256 checked)
<env>\Scripts\python -m pip install transformers timm kornia trimesh opencv-python-headless imageio zstandard easydict tqdm ninja safetensors huggingface_hub scipy git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8
git clone --depth 1 --filter=blob:none --sparse https://github.com/microsoft/TRELLIS.2  (sparse-checkout: trellis2 o-voxel; Eigen @21e4582 into o-voxel/third_party/eigen)
git clone --depth 1 --recursive https://github.com/JeffreyXiang/CuMesh ; git clone --depth 1 https://github.com/JeffreyXiang/FlexGEMM
python kit/gen/patch_ovoxel_msvc.py <src>/TRELLIS.2/o-voxel
(in a VS 2022 x64 prompt: TORCH_CUDA_ARCH_LIST=12.0, DISTUTILS_USE_SDK=1) <env>\Scripts\python -m pip install --no-build-isolation <src>\CuMesh <src>\FlexGEMM <src>\TRELLIS.2\o-voxel
python kit/gen/fetch.py            (then, after Meta approves the owner's request: set HF_TOKEN, python kit/gen/fetch.py --dinov3 --only-dinov3)
```

## Known issues on Windows + RTX 50 (handled by the runner)

- **First-time kernel tuning corrupts that run.** FlexGEMM tunes its GPU kernels the first time it meets a problem
  size (cached in `~/.flex_gemm/autotune_cache.json`). Every model generated while tuning happened came out with stray
  strands to the edge of the box; the same pictures and seeds after tuning came out clean (4 of 4, 2026-10-06). The
  runner counts tunings during a run and generates again when any happened (`reruns_after_tuning` in the record).
- **CuMesh's export without remeshing is broken here** (`remesh=False`: an `isNormalized` assertion, coordinates of
  1e38, then a CUDA "invalid argument"). The runner always remeshes, and checks the export stays within a few voxels
  of the generated shape (twice, then it fails loudly).
- **transformers 5 moved DINOv3's layers** (`model.layer` -> `model.model.layer`); `install_compat()` finds them
  (same weights: 0 missing keys).

## Tools (owner-approved 2026-10-06; VETLOG.md has the vetting rows)

Small tools beside the generators. Wheels are pinned with their sha256 in `kit/tools/pins/<env>.txt`;
`lune run kit tools setup [kit-python|mitsuba|cad]` installs exactly those (pip `--no-deps --require-hashes
--only-binary=:all:`: no dependency that is not pinned, no build script). `lune run kit tools doctor` says which are
ready or missing, with the fix; `--deep` also runs each one on a tiny test (the GPU one is skipped while the GPU is
busy).

| Tool | Licence | Where it runs | Use |
|---|---|---|---|
| vtracer 0.6.15 — lines / shapes to SVG curves | MIT | kit python | `lune run kit vision vectorize <image> [--color] [--speckle 4] [--threshold auto\|0-255] [--invert] [--polygon] [-o out.svg]` |
| Real-ESRGAN x4plus + general-x4v3 weights, read by spandrel 0.4.2 (weights-only; NOT the realesrgan / basicsr packages) | BSD-3-Clause / MIT | kit python (its torch) | `lune run kit vision upscale <image> [--x 2\|4] [--fast] [--tile 384] [--cpu] [-o out.png]` |
| Mitsuba 3.9.1 + Dr.Jit 1.5.0 — differentiable rendering | BSD-3-Clause | `~/.cache/roblox-kit/envs/mitsuba` | `Run.tool("mitsuba")`; `kit/tools/probe_mitsuba.py` is the working example |
| build123d 0.13.0 + cadquery-ocp-novtk 8.0.1.0.0 — code CAD | Apache-2.0 | `~/.cache/roblox-kit/envs/cad` | `Run.tool("cad")`; `kit/tools/probe_cad.py` |

- **vectorize**: binary (the default) reads dark ink on light paper (transparent = paper), threshold by Otsu unless
  `--threshold`; it saves `<name>_ink.png` (what it traced) beside the SVG. `--color` traces colour regions. Blender
  imports the SVG as curves for engraving, stencils, outlines.
- **upscale**: the weights are in `kit/vision/models.json` (`lune run kit vision setup realesrgan-x4plus
  realesr-general-x4v3`). Alpha is kept (it goes through the model too); big pictures go in tiles read with 16 px of
  context (no seams: the tiled result equals the whole one, `kit/test/python/test_upscale_vectorize.py`); the GPU is
  used when it has 2 GB free, else the CPU. It cleans JPEG noise and also fine grain (a brushed-metal photo came out
  smooth in a test): look before using it on a texture. spandrel's package imports einops for networks the kit never
  loads; einops is not approved for the kit python, so `upscale.py` puts a stand-in in its place while it is missing.
- **mitsuba**: measured on the RTX 5070 (driver 591.86): `cuda_ad_rgb` forward render 1.6 s and backward (the
  gradient of an image loss with respect to a texture) 0.7 s on a 64 px test; the Blackwell bugs drjit #511 (PTX on
  sm_120) and mitsuba3 #1614 (a `dr.backward` hang, Linux) did not show. The `llvm_*` variants need an LLVM install
  (not present: the CPU path is `scalar_rgb`).
- **cad**: OpenCASCADE (OCP) works — the test part (a 40 x 30 x 20 mm box, upright edges filleted r 3, a 10 mm hole
  chamfered 1 mm) measures 22257.94 mm3 against 22257.94 worked out by hand, 1536 triangles in its STL and GLB.
  build123d works too (owner-approved 2026-10-07): the same part built with build123d measures the same 22257.94 mm3
  (4.2 s). The cad env sees the kit python's own packages (`include-system-site-packages`) and pins only the 21 it
  lacks in `kit/tools/pins/cad.txt` (94.4 MB, sha256 each); `lune run kit tools setup cad` turns that on for an env
  made before. It reuses the kit python's numpy/scipy/ipython — `kit tools doctor --deep` says if an upgrade there
  ever breaks it.

## Measured on a test PC (RTX 5070 12 GB, 2026-10-06)

Real pictures (the Gjallarhorn's 3/4 render, its side view, a wolf-head crop): **14–16 s to generate** once warm
(the first run of a session also loads the weights, ~50 s), ~20 s to export, 279k–300k triangles, peak 2.65 GB.
Earlier, a full pipeline run with stand-in encoder features (DINOv3 still gated): load 50 s, generate 176 s (55,809 vertices,
119,064 faces), export 8 s, **peak 2.65 GB** of GPU memory — the 1024 pipeline (another 5.16 GB of weights) likely
fits too. `a.import_mesh` of that GLB: welded (glTF splits at seams), pinholes closed, oriented by its volume,
scaled, baked with its own textures, exported without its private UV channel.

**The 1024 cascade (`kit gen <name> --image <pic> --res 1024`; fetched 2026-11-19 with `fetch.py --1024`, the owner:
"Yes, download it").** One picture (a wooden chest with iron bands, seed 1), 512 against 1024 on the same cut-out:
512 = 179 s in all (162 s generating), peak 2.78 GB; 1024 = **847 s in all (522 s generating, ~325 s exporting),
peak 9.86 GB** - it fits the 12 GB card, nothing else may share it. What 1024 buys, seen side by side: the IRON is
sharp (band edges, the corner brackets' rivets, the latch, the front panel's frame) where 512 is soft; the WOOD is no
better - both carry the same see-through gaps and torn planks, which is the generated shape, not its resolution.
Welded by position the two exports are alike (512: 1,945 pieces, the biggest 66% of the faces; 1024: 2,057, 65%).
The export check (it must not grow past the generated shape) refused 1 of 3 runs at 1024 twice in a row (grew
0.047): run it again, as its own next step says. Use 1024 for a hero piece's fine hard detail; 512 for the rest.

---

# kit gen omni — a generated shape STEERED by a code-built blockout (Hunyuan3D-Omni)

TRELLIS.2 makes whatever the picture suggests, at whatever proportions it guesses. **Hunyuan3D-Omni** (Tencent,
Sept 2025: Hunyuan3D 2.1's 3.3B shape model plus a control encoder) makes the picture's shape **held to a control**
— a point cloud, voxels, or a box. The kit's control is the blockout a build script already is: the code fixes the
proportions, the part sizes and where everything stands; the generator brings the sculpted surface. Shape only (no
textures): the build gives it a kit material.

```
lune run kit asset chest                                   # the code-built blockout (build/models/chest.blend)
lune run kit gen omni chest_hi --image refs/chest.png --from-asset chest [--group main] [--control point|voxel|bbox]
        [--seed 1234] [--steps 50] [--guidance 4.5] [--octree 384]
lune run kit gen omni chest_hi --image refs/chest.png --points my_cloud.ply     # or --voxels <file>, --bbox 4,3,2.8
```
1. the picture is cut out (`kit vision cutout`, BiRefNet);
2. `omni_blockout.py` (Blender) exports the build's triangles in Roblox space, studs, where the asset stands — every
   group, or `--group main` / `--group <g>`;
3. `omni_run.py` samples the control from them (2,048 surface points; `voxel`: 16,384 points the encoder snaps to its
   16³ grid; `bbox`: the three side lengths), generates, and maps the mesh back;
4. `assets/models/chest_hi.gen.glb` + `chest_hi.gen.json`: seed, weights, the picture's sha256, time, peak memory,
   **how well it agrees with the blockout** (each axis's size ratio, Chamfer) and the import line.

Then, in a MASTER build script, the `import.line` from the `.gen.json` (it lands exactly on the blockout):
```python
a.import_mesh("Body", "assets/models/chest_hi.gen.glb", height=3.020, pos=(0.000, 0.000, -0.015), mat="wood")
```

**Which control.** `point` (default) holds the surface closest — the blockout's thin parts survive; `voxel` (16³
occupancy) holds the volume but lets the surface wander inside each 1/16th cell — for loose blockouts; `bbox` holds
only the proportions. If a result is >15 % off the blockout on any axis, the verdict says `improve:` — another
`--seed`, or `--control voxel`.

## The frame — how a blockout goes in and the mesh comes back (omni_run.py: to_omni / to_asset)

| | x | y | front |
|---|---|---|---|
| Roblox, a build script, `a.import_mesh` (a GLB's coordinates ARE Roblox's there) | right | up | -Z |
| Hunyuan3D-Omni (its camera on +Z; the picture = the front) | the picture's right | up | +Z |

Measured, not assumed: the repo's own point demo (`demos/point/008`) — its picture's silhouette against its cloud
seen from +Z gives IoU 0.80, from -Z (mirrored) 0.63; width/height 0.70 vs the cloud's x/y 0.68.
- **in**: Roblox -> Omni is a half turn about Y, `(x, y, z) -> (-x, y, -z)` (a rotation: no mirror); then centred on
  the blockout's box and scaled so its longest side is 2 × 0.98 (inference.py's `normalize_mesh(scale=0.98)`);
- **out**: the exact inverse (the half turn again, `/ k + centre`) — the GLB is in studs, where the asset stands
  (round trip error 4e-16 studs). `bbox` controls: the longest side matched to the box's, on the blockout's centre
  (a bare `--bbox`: standing on y = 0 at the origin);
- **import**: `height` = the result's own Y size and `pos` = (its centre x, its lowest y, its centre z), so
  `a.import_mesh`'s "scale to height, base centred on pos" puts it back 1:1. The picture must show the object's
  FRONT (its -Z side), a slightly raised front view like the repo's demos.

## Status (2026-10-07): installed, both encoders fetched

Everything is in place and checked. The **two encoder files the code needs that the owner's first approval did not
list** (found reading the code) were approved and fetched by 2026-10-07 (VETLOG.md: the Omni encoders row; both matched the
Hub's sha256 at the pinned commits): `cond_encoder/pytorch_model.bin` (465 KB, the control encoder's trained layers —
same repo, same licence) and `facebook/dinov2-large` (Apache-2.0, 1.22 GB, the image encoder
`cond_encoder/config.json` names). The DiT file holds neither (its 752 keys: t_embedder, x_embedder, blocks,
final_layer). On a fresh machine: `python kit/gen/fetch.py --omni-encoders` (sha256-checked at pinned commits), then
the smoke test below.

## Licence (Tencent Hunyuan 3D Omni Community License — License.txt beside the weights; the owner accepted it)

Territory = worldwide **except the EU, the UK and South Korea**. No military use
(the Acceptable Use Policy). More than 1M monthly active users needs Tencent's own licence. Its outputs must not
train or improve any other AI model. Tencent claims no rights in the outputs. **Open point for the owner, s.5(c):**
"You must not use, reproduce, modify, distribute, or display ... Output or results ... outside the Territory" — a
mesh from Omni in a public Roblox game is displayed to players in the EU, the UK and South Korea too. Decide before
shipping an Omni-made mesh in a public game (TRELLIS.2, MIT, has no such clause).

## VRAM

fp16, and each network on the GPU only while it runs: the image + control encoders (0.3B), then the DiT (3.05B,
6.1 GB — streamed from the memory-mapped fp32 file straight to the GPU in fp16, never a 12 GB copy in RAM), then the
shape decoder (0.33B) and marching cubes. The runner refuses to start under 7.5 GB free (other GPU jobs) and says so.

## What is installed (VETLOG.md has the rows)

| Where | What |
|---|---|
| `~/.cache/roblox-kit/envs/hunyuan3d-omni` | Python 3.11: torch 2.10.0+cu130 + torchvision 0.25.0 (the kit's verified wheel cache — NOT the repo's torch 2.5.1+cu124 pin: no RTX 50 kernels); transformers, timm, omegaconf, einops, trimesh, scipy, opencv, numpy pinned to the TRELLIS.2 env's versions; scikit-image 0.26 (marching cubes) |
| `~/.cache/roblox-kit/src/Hunyuan3D-Omni` | the code at commit 4d47c0c (its tarball; `KIT_COMMIT.txt`) — pure Python, nothing compiled |
| `~/.cache/roblox-kit/models/hunyuan3d-omni` | `model/pytorch_model.bin` (12.2 GB fp32: the one inference.py loads; the `_ema` twin not fetched), `vae/pytorch_model.bin` (1.31 GB), every config, License.txt + Notice.txt, `pins.json` |

**Not installed, on purpose:** deepspeed, cupy, open3d (never imported on this path); pytorch-lightning, diffusers,
torchdiffeq (the repo takes a base class, `randn_tensor` + the MoE's `FeedForward`, and one Euler loop from them —
rewritten exactly in `omni_run.py`: the DiT loads with 0 missing / 0 unexpected keys); pymeshlab (GPL-3.0 — floaters
and degenerate faces removed with trimesh, the same 0.5 % rule); rembg / RMBG (the kit's BiRefNet cuts the
picture); gradio, fastapi, realesrgan, onnxruntime (the demo app). The `.bin` files are read with
`torch.load(weights_only=True, mmap=True)` only.

## Reinstall from scratch (what was run, 2026-10-06)

```
py -3.11 -m venv %USERPROFILE%\.cache\roblox-kit\envs\hunyuan3d-omni
<env>\Scripts\python -m pip install --no-deps <kit wheels>\torch-2.10.0+cu130-...whl
    <kit wheels>\torchvision-0.25.0+cu130-...whl          (<kit wheels> = ~/.cache/roblox-kit/wheels, sha256 checked)
<env>\Scripts\python -m pip install -c <constraints = pip freeze of the trellis2 env> pip==26.2.1
<env>\Scripts\python -m pip install -c <same> filelock typing_extensions sympy networkx jinja2 fsspec numpy pillow
    transformers omegaconf einops timm trimesh scipy opencv-python-headless scikit-image huggingface_hub safetensors
    pyyaml tqdm
the code: codeload.github.com/Tencent-Hunyuan/Hunyuan3D-Omni/tar.gz/4d47c0c -> ~/.cache/roblox-kit/src/Hunyuan3D-Omni
python kit/gen/fetch.py --omni            (and the two encoders, approved + fetched — VETLOG.md: python kit/gen/fetch.py --omni-encoders)
```

## Smoke test (a committed kit asset against itself)

```
lune run kit asset treasure_chest
<blender> -b --factory-startup build/models/treasure_chest.blend --python-exit-code 2 -P kit/gen/omni_blockout.py --
    treasure_chest build/gen/chest_blockout.npz --picture build/gen/treasure_chest_front.png
lune run kit gen omni chest_omni --image build/gen/treasure_chest_front.png --from-asset treasure_chest
```
The picture is the build's own front render (Cycles, on white), so a good result agrees with the blockout to within
the generator's surface detail: read `agreement` in `assets/models/chest_omni.gen.json` (each axis's size ratio
~1.0; `chamfer_normalised` — the noise floor, two samplings of the same blockout, is 0.009 of its longest side).

---

## kit gen parts — one picture, the object as SEPARATE part meshes (PartCrafter)

TRELLIS.2 makes one welded surface; cutting a sword's guard out of it is guesswork. **PartCrafter** (wgsxm/PartCrafter,
MIT; built on TripoSG, MIT) generates the object as 1-16 parts in one pass — blade, guard, grip, pommel as four meshes
that fit together. Untextured shapes: each part takes a kit material (or a scan).

```
lune run kit gen parts sword --image refs/sword_front.png --parts 4 [--seed 0] [--tokens 1024] [--steps 50]
```
1. the picture is cut out (`kit vision cutout`, BiRefNet);
2. PartCrafter generates the parts (`kit/gen/partcrafter_run.py`, its own env, offline);
3. `assets/models/sword.part1.glb` … `part4.glb` (one mesh each: `a.import_mesh` takes one per file; each a flat
   colour, so they can be told apart), `sword.parts.glb` (all of them, nodes `part1`…) and `sword.parts.json`: seed,
   weights, the picture's sha256, time, peak memory, each part's box / triangles / pieces, and the import lines.

The import lines put the parts back together in a MASTER build script (`L` = the whole object's longest side, studs):
```python
L = 3.2
a.import_mesh("Part1", "assets/models/sword.part1.glb", height=0.13303 * L, pos=(-0.37991 * L, 0.0 * L, 0.0 * L),
              mat="steel")   # (rename the parts: Guard, Blade, Grip, Pommel — the record says which box is which)
```
Measured on a test PC (RTX 5070, 2026-10-06), `refs/arming_sword_front.jpg` (side-on, 2732x588), `--parts 4`,
seed 0: **108 s** (load 13 s, generate + mesh 94 s), **peak 5.16 GB**, 39,652 triangles. The four parts are the four
pieces of a sword: guard (one piece), blade (one), grip (largest piece 93%, two shards inside the blade), pommel
(largest 66%, one more piece by the guard). PartCrafter made it pointing at the camera: turned 270 degrees, its front
silhouette matches the picture at IoU 0.81 (mirrored 0.68, unturned 0.09). Imported with the record's lines in
Blender, all four parts landed within 0.0003 studs of their generated places (L = 4).

**Frame** (every file): Roblox space — +Y up, the side the picture was taken from faces **-Z** (the front), the
object's own right is +X (the picture's right-hand side lands at -X). Blender's glTF import and the kit's BL_FROM_RBX
cancel out, so `a.import_mesh` reads the coordinates as they are. glTF viewers that expect glTF's front (+Z) show the
back first. PartCrafter generates upright but NOT always facing its picture (the side-on sword came out pointing at
the camera): the runner tries the four quarter turns about Y and keeps the one whose silhouette from -Z matches the
picture best (`turned_y`, `facing_iou` in the record; a near-tie keeps PartCrafter's own facing). A turn, never a
mirror — `silhouette_iou_mirrored` shows the mirror scored lower.

**Read the record before importing.** A part is whatever PartCrafter decided: the runner cannot name it, so match the
boxes to the pieces — `main_box_min/max` is the part's largest piece alone (`main_share` of its triangles), which says
what the part IS when a stray shard stretches its `box`. Specks (crumbs under 1% of the object's size) are dropped
(`specks_dropped`); bigger shards stay (`pieces` > 1: the verdict says which; `a.import_mesh(..., crop=...)` keeps a
box of a part). It also warns when two parts share one box (a doubled part) and when the silhouette matches the
picture poorly (< 0.6); a part that came out empty fails the run. Another `--seed`.

Guards: offline (sockets blocked, Hugging Face offline); weights checked against `models/partcrafter/pins.json`;
needs ~6 GB of the GPU free (it says so and stops). Its README's background remover **briaai/RMBG-1.4 is
non-commercial: never fetched or loaded** — the picture must be a cut-out (BiRefNet does it). Its newest commit's
**Gemini features** (part count / style transfer, a cloud service) are stubbed: importing them raises, and
google-genai is not installed. **torch-cluster** (farthest point sampling, used only to train) is not installed: a
plain-torch `fps` answers the import. deepspeed, wandb, gradio, pyrender (training / demo / rendering): not installed.

**Licence note — the owner's call before shipping its output.** Code and weights are MIT, but the DiT block code
(`partcrafter_transformer.py`, inherited from TripoSG) says portions come from Tencent HunyuanDiT and "the use of this
code is subject to" the Tencent Hunyuan Community License: not valid in the EU, an acceptable-use policy (no military
use; item 12 asks that machine-generated content put in public be identified as such). VETLOG.md has the row.

Installed (2026-10-06, VETLOG.md):

| Where | What |
|---|---|
| `~/.cache/roblox-kit/envs/partcrafter` | Python 3.11: torch 2.10.0+cu130 + torchvision 0.25.0 (the kit's verified wheels in `~/.cache/roblox-kit/wheels`), diffusers 0.34.0 (the weights' version), transformers 4.53.3, accelerate 1.15.0, einops, omegaconf, trimesh, scikit-image 0.26, scipy, opencv-python-headless 4.14 |
| `~/.cache/roblox-kit/src/PartCrafter` | the code at 3d773bf (src/ + LICENSE + README; each file checked against its git blob hash) |
| `~/.cache/roblox-kit/models/partcrafter` | wgsxm/PartCrafter @ 69a0ffc: transformer 2.88 GB, vae 0.49 GB, DINOv2 encoder 0.61 GB + configs; `pins.json` |

Reinstall:
```
py -3.11 -m venv %USERPROFILE%\.cache\roblox-kit\envs\partcrafter
<env>\Scripts\python -m pip install <wheels>\torch-2.10.0+cu130-cp311-cp311-win_amd64.whl <wheels>\torchvision-0.25.0+cu130-cp311-cp311-win_amd64.whl
<env>\Scripts\python -m pip install "diffusers==0.34.0" "transformers>=4.53,<4.54" accelerate einops omegaconf trimesh scikit-image scipy "opencv-python-headless<5" safetensors huggingface_hub tqdm
PartCrafter's src/ at commit 3d773bf02fad51c7ab31a5615573fec93b287b30 -> ~/.cache/roblox-kit/src/PartCrafter
    (NOT its settings/setup.sh: that installs torch-cluster from data.pyg.org and the training stack)
python kit/gen/fetch.py --partcrafter      (any python with huggingface_hub, e.g. the trellis2 env)
```
Windows: nothing to patch — the Windows fork (JackDainzh/PartCrafter-Windows, upstream PR #24) only changes progress
bars and the README and points at prebuilt torch_cluster / deepspeed wheels of unknown origin (not used).
# Hunyuan3D-2 — a shape from up to 4 views, a texture for a mesh you already have

Tencent's Hunyuan3D-2 family, also local and offline (`kit/gen/hunyuan_run.py`, its own environment):

```
lune run kit gen mv-shape <name> --front <pic> [--left <pic>] [--back <pic>] [--right <pic>] [--seed 1] [--octree 380]
lune run kit gen paint <asset | mesh.glb> --image <picture> [--out <name>] [--faces 100000] [--seed 0] [--texture 2048]
```
- **mv-shape** (Hunyuan3D-2mv turbo): 1–4 pictures of ONE object -> `assets/models/<name>.gen.glb` + `.gen.json` —
  shape only, no texture; the views agree with each other, so the back and sides are not guessed. Import it like a
  TRELLIS.2 mesh (`a.import_mesh`, a MASTER, `kit optimize`). Each picture is cut out first (BiRefNet).
- **paint** (Hunyuan3D-2 Delight + Paint turbo): a picture of the object from the FRONT ->
  `assets/models/<name>.paint.glb` + `.paint.json`, the SAME mesh in the SAME place and frame with a fresh UV layout
  and a painted base-colour map (Delight first takes the picture's lighting and shadows out). The kit's transfer bake
  then carries the colours onto the asset's own atlas. Evidence to look at: `build/gen/<name>_paint_views.png` (the picture, delit, and the 6 views
  the network painted). An asset NAME reads its full build `build/models/<name>.blend` (never its upload FBX, which is
  pre-turned half a turn for Roblox's importer); a mesh file is read as it is.

**Views and frames.** Every GLB in and out is in Roblox space: x right, y up, the front faces -Z (a GLB's coordinates
are Roblox's, as `a.import_mesh` reads them). The pictures are OF the object, level, orthographic or close to it:

| picture | where the camera is | kit camfit yaw |
|---|---|---|
| `--front` | in front of it (Roblox -Z), looking at its front | 0 |
| `--left` | on the object's OWN left side (Roblox -X), looking toward +X | +90 |
| `--back` | behind it (+Z) | 180 |
| `--right` | on its own right side (+X), looking toward -X | -90 |

Hunyuan's own frame is glTF's (front +Z, its x = the object's left: its renderer puts the front camera on +Z and
image-right on +x); the runner turns half a turn about y on the way in and out — measured, see below. The slot order
(front, left, back, right = "front, front clockwise 90, back, front clockwise 270" in its preprocessor) is the same
camera ring its Paint renderer uses (azimuth 90 = the camera on the object's own left — the painted "left" view of
the test gun showed its muzzle end, as it should). On the test meshes the 2mv model leaned on the front and back
pictures: swapping --left and --right changed nothing measurable (Chamfer 0.0181 vs 0.0179), so give it the front
and back always; a single non-front picture is read as if it were a front.

**Licence (Tencent Hunyuan 3D 2.0 Community License — the owner accepted it, 2026-10-06).** It applies worldwide
except the EU, the UK and South Korea; no military use (Acceptable Use Policy 19) or any
other use the policy lists; a product with more than 1 million monthly active users needs Tencent's own licence; the
outputs, and the models, may not be used to improve any other AI model; Tencent claims no rights in what you generate.
Passing the weights or code on requires the licence text and its "Notice" file (`~/.cache/roblox-kit/src/Hunyuan3D-2`).

**Private experiments only (the owner's rule, 2026-10-07).** s.5(c) forbids displaying outputs outside the licence's
territory, and a public Roblox game is seen everywhere. So every record the runner writes beside its GLB —
`<name>.gen.json` for mv-shape, `<name>.paint.json` for paint — carries `"engine": "hunyuan3d-2mv"` /
`"hunyuan3d-paint"` and `"private_only": true`, and `a.import_mesh` refuses such a mesh in a public asset. Keep the
record next to the GLB; use these to try shapes and colours, then build the public version with the kit's own tools.

**Installed (VETLOG.md has the rows).**

| Where | What |
|---|---|
| `~/.cache/roblox-kit/envs/hunyuan3d2` | Python 3.11: torch 2.10.0+cu130 / torchvision 0.25.0 from `~/.cache/roblox-kit/wheels`, the same diffusers 0.41 / transformers 5.18 / trimesh / opencv / scipy versions as the trellis2 env (`--no-deps`, a pinned list), scikit-image 0.26 (marching cubes) + lazy-loader, and `custom_rasterizer` (compiled here) |
| `~/.cache/roblox-kit/src/Hunyuan3D-2` | the code at f8db630 (`hy3dgen/` + LICENSE/NOTICE only; each file checked against its git blob hash; `PINNED_COMMIT`) |
| `~/.cache/roblox-kit/models/hunyuan3d-2` | `Hunyuan3D-2mv/hunyuan3d-dit-v2-mv-turbo` (4.93 GB: the DiT, the shape decoder and its DINOv2-giant image encoder in ONE file — no separate VAE needed), `Hunyuan3D-2/hunyuan3d-paint-v2-0-turbo` (6.68 GB) and `hunyuan3d-delight-v2-0` (4.31 GB); `pins.json` (sha256 + size of all 31 files) |

Never installed: Hunyuan3D-2's demo requirements (gradio, fastapi, uvicorn, rembg/onnxruntime — the kit cuts
pictures out with BiRefNet), pymeshlab (GPL; the runner drops specks itself), xatlas (the kit unwraps in Blender),
pygltflib, accelerate (the runner moves one network at a time itself), nvdiffrast (Paint never imports it). Never
LOADED although fetched with their folder: the paint text encoder (`pytorch_model.bin`: Paint's prompt is a learned
embedding inside its unet) and image encoder. Any `.bin` that does load (the paint VAE) goes through
`torch.load(weights_only=True)` — the runner forces it.

**Reinstall from scratch (what was run, 2026-10-06).**
```
py -3.11 -m venv %USERPROFILE%\.cache\roblox-kit\envs\hunyuan3d2
<env>\Scripts\python -m pip install pip==26.2.1 setuptools==84.0.0 wheel==0.48.0
<env>\Scripts\python -m pip install --no-deps <wheels>\torch-2.10.0+cu130-cp311-cp311-win_amd64.whl <wheels>\torchvision-0.25.0+cu130-cp311-cp311-win_amd64.whl
<env>\Scripts\python -m pip install --no-deps --only-binary :all: <the trellis2 env's versions of: sympy mpmath networkx Jinja2 MarkupSafe filelock fsspec typing_extensions numpy pillow PyYAML einops tqdm colorama diffusers importlib_metadata zipp transformers tokenizers safetensors regex packaging huggingface_hub hf-xet httpx httpcore h11 anyio idna certifi requests urllib3 charset-normalizer typer click rich shellingham markdown-it-py mdurl Pygments annotated-doc trimesh scipy opencv-python-headless ImageIO ninja> scikit-image==0.26.0 lazy_loader==0.6
python <fetch the code at f8db630: hy3dgen/ + LICENSE/NOTICE/requirements/setup, each file = its git blob sha1> -> %USERPROFILE%\.cache\roblox-kit\src\Hunyuan3D-2
(in a VS 2022 x64 prompt — vcvars64.bat)
  set TORCH_CUDA_ARCH_LIST=12.0 & set DISTUTILS_USE_SDK=1 & set CUDA_HOME=<CUDA v13.1>
  set CL=/permissive- /Zc:__cplusplus
  set NVCC_APPEND_FLAGS=-Xcompiler=/permissive- -Xcompiler=/Zc:__cplusplus -allow-unsupported-compiler
  <env>\Scripts\python -m pip install --no-build-isolation --no-deps <src>\hy3dgen\texgen\custom_rasterizer
<env>\Scripts\python kit/gen/hunyuan_run.py fetch
```
The build flags are the ones CuMesh / FlexGEMM use: without `/permissive-` nvcc's front end finds `std` ambiguous in
torch's `compiled_autograd.h` (C2872); VS 2022's newest toolset is past CUDA 13.1's version check. They go in through
the `CL` / `NVCC_APPEND_FLAGS` variables, so the vetted source is not edited. The paint module's other native part
(`differentiable_renderer/mesh_processor.cpp`, pybind11) is not built: its own Python fallback runs.

**How the runner keeps 12 GB (shared) enough.** shape: the checkpoint is read network by network, built in half
precision without random init and streamed in (peak RAM ~ the networks once, not twice); the DINOv2-giant encoder,
the DiT and the decoder each move to the GPU only while they run. paint: Delight is loaded, run and freed before the
multiview network loads; that network is freed before the bake. Before either, the runner checks the GPU has room
(`NEED_GB`: 3.5 / 5.5 GB free) and says so instead of crashing.

**Handled by the runner (found 2026-10-07).**
- **transformers 5 renamed DINOv2's layers** (`attention.attention.query` -> `attention.q_proj`, ...) and split its
  SwiGLU input projection in two; Hunyuan loads a state dict directly, so the 2mv image encoder would not load. The
  runner applies transformers' own conversion rules (`dinov2_tf5`; the gate is the first half). Every DiT and encoder
  weight then loads strictly; the VAE lacks only its encoding half (`encoder.*`, `pre_kl.*`), which never runs.
- **The paint unet safetensors carries an unused image-prompt adapter** (`attn2.to_k_ip/to_v_ip`,
  `unet.image_proj_model`: 36 tensors) that neither the GitHub code nor the repo's own `unet/modules.py` (read,
  never run: functionally identical) builds; everything else loads strictly.
- **trimesh drops a GLB's UVs when it has no material**: the Blender prep writes one plain material.

**Measured on a test PC (RTX 5070 12 GB shared with other agents' jobs at ~100% load, 2026-10-07).** Test asset:
the kit's `blaster` (1,807 polygons, baked colour), rendered level and orthographic at 512 px (Workbench, studio
light) from the 4 directions; metrics after centring each mesh on its box and scaling its longest side to 2.
- **mv-shape**: peak **2.46 GB** of GPU memory; load 66–75 s (RAM: its 2.58 B half-precision weights once, ~5.2 GB); generate 180–416 s
  under that load (5 steps + the 381³ decoder + marching cubes: the decoder is most of it); 284k–310k faces,
  watertight. The as-exported frame is the best of the 8 candidate turns/mirrors (so front -Z is right).
  Blaster as built: Chamfer 0.029 (of 2), silhouette IoU front/back 0.77, sides 0.86, held-out top 0.83, 3/4 0.87.
  Blaster turned 90° (its profile in the front view): Chamfer 0.018, IoU 0.88–0.91, held-out top 0.91, 3/4 0.93.
  Through `lune run kit gen mv-shape` (BiRefNet cut-outs first): the same numbers (Chamfer 0.029).
- **paint** (the turned blaster, its lit front render as the picture; 3,752 triangles): **45 s** (Delight 16 s,
  multiview 18 s, bake + fill the rest), peak **4.26 GB**; 48% of the UV area seen by a view directly (the rest
  filled: grazing angles and depth edges are left out by design). Colour against the source's own albedo over
  6 views (4 never shown to it): ΔE 19.4 mean (one flat colour: 27.4; the lit picture itself: 22.1); luminance
  correlation 0.92. It keeps the picture's exposure (here ~30% darker than the albedo): after one global gain, ΔE 8.9
  mean / 7.3 median. The painted 6 views agree with the geometry (front profile, muzzle end on the left camera).
## Diffusion models: a picture's lighting, concept sheets (`kit vision light`, `kit vision concept`)

Two owner-approved diffusion tools (2026-10-06), in their own environment `~/.cache/roblox-kit/envs/diffusers`
(Python 3.11: torch 2.10.0+cu130 from the vetted local wheels, diffusers 0.41.0, transformers 5.18.0, accelerate
1.15.0, peft 0.21.2, OpenEXR 3.5.2). Runner: `kit/gen/vision3.py` (offline: sockets blocked, Hugging Face offline,
every weight file checked against its pin). Weights: pinned in `kit/vision/models.json`, fetched and hash-checked by
`lune run kit vision setup <model>`.

```
lune run kit vision light refs/<picture>.jpg [-o build/vision/<name>.light.exr] [--seed 200] [--height 256]
lune run kit vision concept "<name + details>" [--sheet turnaround|single] [--seed 1] [--steps 4] [-o out.png]
```

**light** — DiffusionLight-Turbo (MIT; Phongthawee, Chinchuthakun et al., VISTEC): SDXL paints a chrome ball into
the middle of the picture (depth ControlNet keeps it a sphere in the scene; the Turbo LoRA steadies it, the exposure
LoRA takes over at t = 800), at EV 0, -2.5 and -5; each ball is unwrapped to an equirectangular map and the three are
merged into one HDR map (their exposure bracketing). Out: `<name>.light.exr` (512 x 256, linear) + `<name>.light.json`
+ `build/vision/<name>.light_preview.png` (the painted picture, the three balls, the map with the key light ringed).
Facts: the key light's direction (azimuth 0 = ahead of the camera, + = its right; elevation; in words, as a camera
vector and as a Blender vector), the brightest spot, how directional the light is (0 = even all round, 1 = one
point), the key-to-fill ratio (irradiance facing the key / facing away), colour temperatures of key and fill
(McCamy) and their colours. The map's middle column is where the camera looks, its left half the camera's left; as a
Blender world texture it matches a camera looking along +X. The maths (`kit/gen/diffusionlight.py`) is vendored from
the authors' `ball2envmap.py` / `exposure2hdr.py` and checked on a synthetic ball lit from four known directions: the
key light came back within 1 degree. It is an ESTIMATE: right about where the light comes from and its colour,
approximate about its strength; what the picture cannot see (behind the camera) is a plausible guess. A studio shot
on white gives a bright, even, near-white map — use a picture with a real scene for a scene's light.

**concept** — FLUX.2 [klein] 4B (Black Forest Labs, Apache-2.0; the 9B is non-commercial and not installed).
`turnaround` (default): ONE 2048 x 640 generation of all four views in a row (front, side, back, top) — drawn
together they show one design — cut between the objects into four views; `build/vision/concepts/<slug>.png` (a
labelled sheet on grey, CONCEPT in its caption) + `<slug>.<view>.png` + the raw picture + `<slug>.json`. Drawing each
view from the front as a reference picture (klein's editing) was tried first and gave four copies of the front.
The JSON says `"kind": "concept", "reference_measurement": false` and checks the sheet: four objects found, the side
and top views not a copy of the front (mean grey difference; copies measured 2.8-4.8), the upright views as tall as
the front (within 15%); a failed check -> `improve: ... another --seed`. `single`: one 1024 px three-quarter
view (`<slug>.single.png`). Use it for name-only requests: agree the look in the brief; then
`kit gen <name> --image <slug>.front.png` can make a mesh from the front view. Never trace or measure a concept:
sizes come from real references (`kit refs`, `kit/real_sizes.json`).

**Memory.** Both load in stages, each straight onto the GPU — the text encoders first (then freed), then the
denoiser; the VAE decodes after the denoiser is freed (a 1 MP decode alone takes ~7.4 GB: SDXL's and FLUX.2's VAEs
alike). Same peak as diffusers' model CPU offload, half the RAM, no copying back and forth. Each command checks the
free GPU memory first (light and concept: 9.5 GB) and caps PyTorch at what was free: past it Windows pages GPU memory
to RAM — 10x slower, and one such run came back as pure noise. Run one big GPU job at a time.

**Measured** (RTX 5070 12 GB, 2026-10-07; other agents' GPU jobs overlapped some runs):
- `light refs/arming_sword_style_3.jpg` (a 1920 x 1440 studio photo, seed 200): **71 s** on a free GPU — depth 3 s,
  prompts 3 s, load 13 s, three exposures + decode 45 s (343 s when another agent's GPU job overlapped). Peak 9.0 GB
  (UNet + ControlNet + LoRAs 7.4 GB, painting), decode 7.5 GB alone. A convincing chrome ball in the middle of the
  picture; the facts (two runs): key light below, beyond the subject (azimuth -18.5 / -19.5, elevation -37.3: the
  white sweep's floor is the brightest thing the ball sees), key:fill 3.7 / 3.8, ~6,500 K key and fill (neutral).
- `concept "a small wooden treasure chest with iron bands and a curved lid"` (turnaround, seed 1): 22-34 s in all —
  prompt 9-16 s (7.8 GB), load 9-12 s, the sheet in 4.5 s (8.1 GB), decode 7.4 GB alone. Checks passed: four
  objects, side / back as tall as the front (1.02 / 1.00), side and top differ from the front by 8.7 (copies:
  2.8-4.8); the kit's SigLIP view check reads the top panel as a top view (0.73 vs <= 0.17 for the rest). `single`
  of the same words: 1024 px in 67 s (another job overlapped).

**Not used, on purpose:** stabilityai/sdxl-turbo (DiffusionLight's `sdxl_turbo` option: non-commercial licence), the
original DiffusionLight requirements (torch 2.0.1, xformers 0.0.20, OpenEXR 1.3.9), its training-state files
(optimizer.bin, random_states_0.pkl, scheduler.bin), SDXL's own VAE (madebyollin's fp16 fix replaces it: no NaNs in
fp16), the `.bin` copies of every repo, FLUX.2 klein 9B, and FLUX's root single-file duplicate.

**Known issues (handled):**
- DiffusionLight's two LoRAs are saved with their layer names as `unet.unet.<layer>`; diffusers 0.41 strips one
  `unet.` and then finds no layer ("No modules were targeted"). The runner renames the keys (same weights) and fails
  loudly if a LoRA attaches to 0 layers.
- Multi-GB downloads arrived short (Python's http.client stops quietly when a server closes early): `kit vision
  setup` now resumes with an HTTP Range request; the size + sha256 check is unchanged.

Reinstall (what was run, 2026-10-06):
```
py -3.11 -m venv %USERPROFILE%\.cache\roblox-kit\envs\diffusers
<env>\Scripts\python -m pip install --no-deps <wheels>\torch-2.10.0+cu130-cp311-cp311-win_amd64.whl
  <wheels>\torchvision-0.25.0+cu130-cp311-cp311-win_amd64.whl diffusers==0.41.0 transformers==5.18.0
  tokenizers==0.23.2 accelerate==1.15.0 peft==0.21.2 OpenEXR==3.5.2 huggingface_hub==1.33.0 hf-xet==1.6.0
  safetensors==0.8.0 numpy==2.4.6 pillow==12.3.0 psutil==7.2.2 filelock==4.0.12 typing_extensions==4.16.0
  sympy==1.14.0 mpmath==1.3.0 networkx==3.6.1 Jinja2==3.1.6 MarkupSafe==3.0.4 fsspec==2026.9.0
  importlib_metadata==9.0.1 zipp==4.1.1 regex==2026.9.29 requests==2.34.2 charset-normalizer==3.5.2 idna==3.20
  urllib3==2.8.0 certifi==2026.7.22 httpx==0.28.1 httpcore==1.0.9 h11==0.16.0 anyio==4.15.1 packaging==26.3
  PyYAML==6.0.3 tqdm==4.70.1 colorama==0.4.6 shellingham==1.5.4 typer==0.27.2 click==8.5.0 rich==15.0.0
  markdown-it-py==4.2.0 mdurl==0.1.2 Pygments==2.21.0 annotated-doc==0.0.5        (pip check: no broken requirements)
lune run kit vision setup sdxl-base-1.0 sdxl-vae-fp16-fix controlnet-depth-sdxl diffusionlight-turbo-lora
  diffusionlight-exposure-lora dpt-large flux2-klein-4b                          (43 files, 27.0 GB, all verified)
```
## Multi-view: `kit gen views` (Pixal3D)

One picture leaves the back, the depth and the proportions to the generator's imagination. **Pixal3D** (Tencent ARC,
MIT, SIGGRAPH 2026; built on TRELLIS.2) takes 2-4 views of the same object WITH their cameras and projects every
view's features into its voxel grid through that view's camera — the shape lines up with each view instead of being
guessed. The natural input is the reference chart the kit already measures with (`kit refs`, `kit trace`): its side,
front, back and top views.

```
lune run kit gen views chest --view side=refs/chest_side_rgba.png --view front=refs/chest_front_rgba.png \
    [--view back=refs/chest_back_rgba.png] [--view top=refs/chest_top_rgba.png] [--ortho] [--flip side] [--seed 7]
    [--faces 300000] [--texture 2048] [--remesh 512] [--fov <deg>] [--resume]
```
-> `assets/models/chest.gen.glb` (Roblox space: x right, y up, front -Z; longest side 1 — scale it with
`a.import_mesh(..., height=...)`) + `chest.gen.json` (views, their sha256, the fitted proportions, how much each view
disagrees with the others, **silhouette IoU per view** of the result, seed, time, peak memory). The framed pictures and
Pixal3D's own `transforms.json` stay in `build/gen/chest_views/` (run Pixal3D's `inference_mv.py` on them by hand to
compare).

**The views** (kit/gen/views_rig.py — the same cameras as kit/blender/rbx_precision.py VIEWS, checked against them):

| view | camera at | picture right | picture up |
|---|---|---|---|
| front | -Z | -X (the model's left) | +Y |
| side | +X | -Z: **the front on the RIGHT** (as `kit trace` and the side camera see it) | +Y |
| back | +Z | +X | +Y |
| top | +Y | +X | -Z: **the front at the TOP** |

- Every picture must be a cut-out (RGBA: `lune run kit vision cutout <img> --rgba`) of ONE object. A chart whose side
  view has the front on the left: `--flip side` (mirrors that picture).
- Crops and sizes do not matter: each picture is re-framed from its silhouette. The silhouette's box is the object's
  extent across that view (exact for an orthographic drawing); the three extents are fitted from all the views' aspect
  ratios (the disagreement per view is in the record — over 5 % means a picture is off: perspective, a different
  pose, a bad cut-out); the object is normalised to a longest side of 1 and each picture scaled to that, centred.
- `--ortho` (chart drawings): orthographic views are approximated by a 2-degree lens 31.5 units away (a +-0.5 deep
  object is drawn within +-1.6 % of orthographic). Without it (renders, photos): Pixal3D's own example rig, a
  20-degree lens 3.12 units away. `--fov <deg>` sets another lens.
- Pixal3D needs a MAIN view (frame 0) at its canonical front camera: front if given, else side, else back (never the
  top — the object must stand upright in it, as in training). The world is turned so that view lands there, and the
  GLB turned back into Roblox space afterwards.

**What is installed for it** (VETLOG.md rows 2026-10-06):

| Where | What | Licence |
|---|---|---|
| `~/.cache/roblox-kit/src/Pixal3D` | TencentARC/Pixal3D @ f7cf384, sparse checkout (pixal3d/, inference_mv.py, the example views) — on `sys.path`, NOT pip-installed (its requirements.txt pins transformers 4.57.3, gradio and MoGe: none installed; it runs in the trellis2 env on transformers 5) | MIT |
| `~/.cache/roblox-kit/models/pixal3d` | `Pixal3D/`: pipeline_mv.json + the 4 multi-view networks (22.0 GB) at revision b0cb2e1; its 3 decoders are HARD LINKS to the byte-identical TRELLIS.2 copies (same sha256, no second download); `naf/naf_release.pth` (2.7 MB); `pins.json` | MIT; Apache-2.0 |
| `~/.cache/roblox-kit/src/NAF` | valeoai/NAF @ 37f2dfc, only src/layers + src/model/naf.py vendored (its rope.py carries Meta's DINOv3 licence header: covered by the owner's DINOv3 decision) | Apache-2.0 |
| trellis2 env | NATTEN 0.21.7 **without libnatten** (NAF's code imports it; nothing compiled) | MIT |

Reinstall:
```
git clone --filter=blob:none --no-checkout https://github.com/TencentARC/Pixal3D <src>/Pixal3D
  (sparse-checkout --no-cone: /pixal3d/ /inference.py /inference_mv.py /assets/mv_images/ /requirements*.txt /LICENSE /NOTICE /README.md /app.py /configs/; git checkout f7cf38429b0bd264f1995f0f8743a88b1c728b94)
git clone --filter=blob:none --no-checkout https://github.com/valeoai/NAF <src>/NAF
  (sparse-checkout --no-cone: /src/layers/ /src/model/naf.py /src/model/base.py /LICENSE /hubconf.py; git checkout 37f2dfc180f2de53d98bd601109c0da0dd6b0f43)
(download natten-0.21.7.tar.gz from PyPI, sha256 8417236b...05ffb, unpack, read setup.py) then, with no GPU visible so
  its setup.py builds WITHOUT libnatten:  set CUDA_VISIBLE_DEVICES=-1 & <env>\Scripts\python -m pip install --no-deps --no-build-isolation --no-index <natten-0.21.7 dir>
<env>\Scripts\python kit/gen/pixal3d_fetch.py      (--check re-hashes everything against pins.json)
```

**Licence patches** (pixal3d_run.py; Pixal3D's code is not edited): its configs name `briaai/RMBG-2.0` (CC BY-NC)
through a BiRefNet remote-code wrapper — replaced by `KitCutoutDone` (views come cut out by the kit's BiRefNet);
its code loads DINOv3 from `camenduru/dinov3-vitl16-pretrain-lvd1689m` (an unofficial re-upload) — the owner's
official copy in `models/trellis2/dinov3-vitl16-pretrain-lvd1689m` is used, ONE instance for all four stages; NAF
through `torch.hub.load("valeoai/NAF")` (fetches and runs code at run time) — the vendored copy, weights loaded
weights-only and strictly; MoGe-2 (single-view camera guess) is not used: the views' cameras are known.

**Why the kit code exists** (all exact: same numbers as Pixal3D's own path, unless said):
- `naf_attn.py` — NAF's attention upsamples its keys/values to 1024 x 1024 before NATTEN runs: 4 GiB of values alone
  in the texture stage. Nearest upsampling makes every key in a dilated window the same low-resolution key, so the kit
  attends to the low-resolution windows directly, a few rows at a time. Proven: `test_naf_attn.py` (vs the definition,
  1e-10 in float64) and, at install, vs NATTEN's own Flex kernel (max difference 1.3e-6 in float32).
- `pixal3d_run.py`, beyond the licence patches: the seven networks (4 x 1.3B flow models, 3 decoders) are built with
  their weights on the "meta" device and read from disk only when their stage moves them to the GPU, then freed —
  Pixal3D's low-VRAM mode otherwise keeps ~14 GB of them in RAM; every key must match (Pixal3D loads with
  strict=False); the image features are projected only at the occupied voxels (the values Pixal3D reads out of its
  full 64^3 grid, without building the 2 GiB grid); DINOv3 leaves the GPU while NAF's big maps exist; freed GPU
  memory is handed back between stages (see Windows below). Not exact, on purpose: the export rebuilds the surface on
  a 512^3 grid (`--remesh 512`, the default; o-voxel would use 1024^3: 31.9M faces and 12.75 GB before the
  decimation to ~300k faces, against 7.0M and 3.1 GB — same final budget, textures still sampled at 1024), and
  decoded vertices outside the box (a glitch, below) are dropped with their faces.
- `pixal3d_run.py --resume` exports the shape the last run saved (`build/gen/<name>_views/generated.pt`) without
  generating again — when an export fails (out of GPU memory) or to try another `--faces` / `--texture` / `--remesh`.
- `views_rig.py` — the kit's views as cameras (table above), the re-framing and the turn back to Roblox space;
  `test_views_rig.py` checks it against Pixal3D's own projection, its canonical front camera and its export turn.
- `gen_common.py` — the offline guard, shims, pins check, FlexGEMM tuning watch and verdict line, shared by runners
  (trellis2_run.py keeps its own copies).
- `pixal3d_fetch.py` — fetches + verifies the weights at the pinned revision, hard-links the shared decoders.

**Measured on a test PC** (RTX 5070 12 GB, 2026-10-07). Ground truth: the kit's `treasure_chest` starter
(3,876 triangles, 4.75 x 3.02 x 2.87 studs) rendered by Blender from the kit's own view cameras (EEVEE, RGBA, the
same construction as rbx_precision's), generated, then measured against the chest's mesh — both normalised (box
centred, longest side 1), no other fitting. Silhouette IoU from 512 x 512 orthographic renders; "unseen" = four 3/4
views from 30 degrees above, the bottom and the left, none of them an input:

| input | IoU, input views | IoU, unseen views (mean) | Chamfer-L1 | F-score @1 % / @2 % | proportions (1 : 0.636 : 0.604) |
|---|---|---|---|---|---|
| 4 orthographic views, `--ortho` | 0.962-0.978 | 0.962-0.984 (0.978) | 0.0072 | 0.90 / 0.96 | 1 : 0.626 : 0.601 |
| side + front only, `--ortho` | 0.968-0.980 | 0.958-0.984 (0.971) | 0.0073 | 0.85 / 0.96 | 1 : 0.627 : 0.605 |
| 4 perspective renders (20 deg), default | 0.907-0.987 | 0.907-0.942 (0.932) | 0.0119 | 0.67 / 0.87 | 1 : 0.636 : 0.606 |

Looked at (one render, source beside result): planks, gold bands, corner caps, feet, side handles, the lock plate
and hasp — all there and the right way round. Two views already carry most of it; perspective pictures come out
softer (their re-framing is approximate, see above). One visible fault: the black hinge straps of the BACK were also
painted onto the front — Pixal3D averages every view's features along its rays with no occlusion, so a detail only
one view shows can leak to the opposite face.

- **Time** (kernels already tuned, GPU to itself): 388 s end to end — structure 9 s, 512 shape 14 s, 1024 shape
  145 s, texture 108 s (its NAF condition 23 s), decode 39 s, export + checks 33 s. The FIRST runs on a PC tune
  FlexGEMM's kernels for new sizes and generate again (the first chest: 3 passes, 38 + 2 tunings; the two-view chest
  later: 1 more pass for 6 new sizes).
- **GPU memory** (allocated peak per step, `seconds_stages` in the record): sampling <= 4.2 GB, the texture
  condition (NAF at 1024) 6.95 GB, **decode 10.6 GB** (the shape decoder at 1024^3: 8-10M vertices), export 3.0-3.6
  GB. So the card must be otherwise idle. RAM: ~6 GB (each network read from disk when its stage starts).

**Known issues on Windows + RTX 50 (handled by the runner):**
- **A busy GPU never fails, it crawls.** Windows lets a process outgrow the card into shared system memory: with
  other jobs on the GPU (or PyTorch's cache not handed back) a 1024 shape stage took 22 min instead of 2. The runner
  empties the cache between stages; start a run only on an idle card.
- **Stray decoded vertices.** One run (the two-view chest) decoded 4,813 of 7.9M vertices at z = 1.3e25 (every
  vertex of the dual grid lies inside its voxel, so these are a numerical glitch); the export then failed its
  growth check twice. They are dropped with their 41k faces (0.26 %) before export, counted in the record
  (`stray_*_dropped`; a warning above 1 %).
- **The export at 1024^3 runs out of memory** next to anything else (CuMesh: out of memory in simplify) — hence the
  512 remesh, and the shape is saved before export (`--resume`).
- FlexGEMM's tuning corrupting a run and transformers 5's DINOv3 layers: as for TRELLIS.2 above.
## kit vision angle / edit — clean views on demand (Qwen-Image-Edit-2511)

A reference often shows an ornament only from 3/4, or is full of reflections. `kit vision angle` asks an image-edit
model for **the same object from another camera**; `kit vision edit` applies a written instruction to a picture.
Model: **Qwen-Image-Edit-2511** (Alibaba Qwen, Apache-2.0; Q4_K_M GGUF) with its text encoder Qwen2.5-VL-7B, run by
**stable-diffusion.cpp** (MIT, a native program — no Python environment), plus fal's **Multiple-Angles LoRA** (96
camera poses) and lightx2v's **Lightning LoRA** (4 steps). Local and offline, like everything here.

```
lune run kit vision angle refs/x.png --azimuth 90 --elevation 0 [--distance near|mid|far] [-o out.png] [--fast]
lune run kit vision edit refs/x.png --prompt "remove reflections, flat even studio light, white background" [--fast]
    options: --seed 1  --steps N  --cfg 2.5  --res 1024 (pixel budget; the output keeps the input's aspect)
             --strength 0.9 (the angle LoRA, 0.8-1.0)  --wait <minutes> (for free memory or another run)
```
- **Poses** snap to the LoRA's 96: azimuth in 45° steps (0 = the object's front, 90 its right side, 180 its back, 270
  its left side), elevation -30 (from below) / 0 (eye level) / 30 / 60 (looking down), distance near / mid / far
  (close-up / medium shot / wide shot). The `.json` beside the output records what was asked and what was used.
- Output: `build/vision/<picture>.angle_<az>_<el>_<distance>.png` (or `.edit.png`; `_fast` with `--fast`) + its `.json`
  (prompt, seed, steps, time, peak memory, the source's sha256, `"trust": "low"`).
- A cut-out (transparent PNG) goes in on white.

**LOW TRUST — always.** The output is a generated picture: not a photo, not a measurement. Use it to understand a
shape you cannot see (the back of an ornament, what a 3/4 render hides) or as the picture for `kit gen`. Never trace,
measure (`kit refs views`), fit or colour-match from it: those read real pictures and real models only. Check it is
still the same object (same parts, proportions, count of features) — if not, another `--seed`.

**Speed + memory** (RTX 5070 12 GB, 32 GB RAM): not measured yet — on 2026-10-06/07 the smoke runs waited
3.5 h for 22 GB of free RAM on the shared PC (other jobs held it; free RAM peaked at 16.4 GB) and never started.
sd-cli accepted every flag above (a dry run with the model paths missing stops at loading, after parsing).

**Install** (on demand — a plain `kit vision setup` skips it): `lune run kit vision setup qwen-image-edit sd-cpp`
— 23.6 GB of weights (`~/.cache/roblox-kit/models/qwen-image-edit`, Hugging Face's own sha256 + size, pinned per
commit in kit/vision/models.json) + the sd.cpp release `master-929-3f8527a` Windows CUDA 12 build and NVIDIA's CUDA
12 runtime DLLs (`~/.cache/roblox-kit/tools/sd-cpp`, 0.9 GB, the release's sha256; zips unpacked only after every
path inside is checked). Big Hugging Face files go through `huggingface_hub` when it is installed (parallel: ~80 MB/s
here against 2–4 MB/s for one plain stream). VETLOG.md has the vetting rows.

**Flags the runner always passes** (kit/gen/qwen_edit.py): `--model-args qwen_image_zero_cond_t=true` (2511's edit
quality degrades badly without it), `--offload-to-cpu --max-vram -1` (segmented execution: the weights wait in RAM,
1 GiB of the GPU is left free), `--diffusion-fa`, euler, flow shift 3, and with a LoRA `--lora-apply-mode at_runtime`
(the `immediately` mode aborts on quantised Qwen weights, sd.cpp issue #2083). It refuses to start below 22 GB of
free RAM or 9 GB of free GPU memory, and runs one generation at a time (a lock file beside sd-cli).
**Not used:** the diffusers fallback (it needs a 16.6 GB bf16 text encoder that is not approved).

# The hybrid route — CAD where it is machined, generated where it is sculpted (LIMITATIONS_FIXES_V4 3D-X)

`python kit/gen/hybrid_fabricate.py <asset> --plate <concept.png> --part <Name>=x0,y0,x1,y1[@quads]` (or
`--image <Name>=<picture>`, `--gen-glb <Name>=<glb>`): each AI part's picture cut out (BiRefNet), generated by
TRELLIS.2 at 1024 (cached by the picture's sha256, seed, resolution), then RETOPOLOGISED by `retopo_part.py`
(Instant Meshes pure quads at the budget - built from source, VETLOG; Blender's QuadriFlow when its binary is
missing, said), its colour baked across, the generator's surface kept as one watertight skin: the part's HIGH.
Manifest: `build/hybrid/<asset>/hybrid.json`. In the build (`Asset(low=...)`): `rbx_hybrid.ai_part(a, asset, Name,
...)` = `a.import_mesh(low, high=...)`; the CAD parts are the script's own (`a.cad`, `a.cast(mode="cad")`,
`a.ornament`). After the build, `--hulls` cuts each built group into convex collision pieces (`hulls.py`: CoACD 1.0.14
in `~/.cache/roblox-kit/envs/coacd`) and measures them: surface covered >= 99%, volume over the mesh <= 35%.

Gates: `generated_topology` (an imported part's triangles pairing into good quads, rbx_quads: >= 0.8; an error on the
high-and-low route) and, for R6 clothes, `a.r6_wear(group, on=...)` (rbx_r6wear: <= 4,000 triangles, quads,
watertight, 0.022 studs clear of the block). Measured: a TRELLIS.2 crust 0.39, the same decimated 0.14, its Instant
Meshes retopology 0.93. CoACD's default search took 511 s on a 4,000-quad lobed ball; the kit's settings 108 s, the
same cover.
