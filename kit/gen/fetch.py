"""fetch.py — fetch and verify the weights kit gen runs on (the owner approved these exact files, 2026-10-06).

    python kit/gen/fetch.py            # TRELLIS.2-4B's 512 set + TRELLIS-image-large's structure decoder (10.5 GB)
    python kit/gen/fetch.py --1024     # + the 1024 shape and texture flows (5.16 GB; the owner approved 2026-11-19)
    python kit/gen/fetch.py --dinov3   # + the DINOv3 image encoder (1.21 GB, gated: needs the owner's HF_TOKEN)
    python kit/gen/fetch.py --omni     # Hunyuan3D-Omni (kit gen omni): the DiT + the shape VAE + configs (13.5 GB)
    python kit/gen/fetch.py --omni-encoders   # + the two encoders its control needs (1.22 GB) — the owner approved
                                              #   them (VETLOG.md: the Omni encoders row — fetched, sha256 matched)
    python kit/gen/fetch.py --partcrafter   # PartCrafter alone (3.97 GB, at its vetted commit) -> models/partcrafter

Every file is checked against the Hugging Face Hub's own sha256 and size, at the repository's current (or pinned)
commit, and recorded in ~/.cache/roblox-kit/models/<set>/pins.json (the runners check sizes against it before every
run). A token is read from the HF_TOKEN environment variable only — never pass it on the command line or paste it.
"""

import hashlib
import json
import os
import sys

MODELS = os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models")
ROOT = os.path.join(MODELS, "trellis2")
OMNI_ROOT = os.path.join(MODELS, "hunyuan3d-omni")
_TRELLIS2 = ["ss_flow_img_dit_1_3B_64_bf16", "slat_flow_img2shape_dit_1_3B_512_bf16",
             "slat_flow_imgshape2tex_dit_1_3B_512_bf16", "shape_dec_next_dc_f16c32_fp16",
             "tex_dec_next_dc_f16c32_fp16", "shape_enc_next_dc_f16c32_fp16"]
FILES = {
    "microsoft/TRELLIS.2-4B": ["pipeline.json", "texturing_pipeline.json"]
    + [f"ckpts/{n}.{e}" for n in _TRELLIS2 for e in ("json", "safetensors")],
    "microsoft/TRELLIS-image-large": [f"ckpts/ss_dec_conv3d_16l8_fp16.{e}" for e in ("json", "safetensors")],
}
# The 1024 networks (the owner: "Yes, download it", 2026-11-19 - the 5.16 GB set held back on 2026-10-06): the shape
# and texture flows at 1024, at the commit the 512 set was fetched from (pins.json). The 1024 cascade runs the 512 flow
# first and refines it at 1024 (TRELLIS.2's pipeline_type "1024_cascade").
TRELLIS2_COMMIT = "af44b45f2e35a493886929c6d786e563ec68364d"
HI_RES = {"microsoft/TRELLIS.2-4B": [f"ckpts/{n}.{e}" for n in ("slat_flow_img2shape_dit_1_3B_1024_bf16",
                                                                 "slat_flow_imgshape2tex_dit_1_3B_1024_bf16")
                                     for e in ("json", "safetensors")]}
DINOV3 = {"facebook/dinov3-vitl16-pretrain-lvd1689m": ["config.json", "model.safetensors"]}
# Hunyuan3D-Omni (Tencent Hunyuan 3D Omni Community License, accepted by the owner 2026-10-06), at a pinned commit.
# The DiT comes as two 12.2 GB fp32 .bin files: pytorch_model.bin is the one its inference.py loads (no --use_ema).
OMNI_COMMIT = "70e803bfb4e127d534049d8ab8c8cb511780d485"
OMNI = {"tencent/Hunyuan3D-Omni": ["config.json", "License.txt", "Notice.txt", "model/config.json",
                                   "model/pytorch_model.bin", "vae/config.json", "vae/pytorch_model.bin",
                                   "cond_encoder/config.json", "scheduler/config.json", "image_processor/config.json"]}
# What the control needs on top (found reading the code, 2026-10-06; NOT in the owner's first approval): the control
# encoder's own weights (465 KB, same repo) and the image encoder its config names, facebook/dinov2-large — the DiT
# file holds neither (752 keys: t_embedder, x_embedder, blocks, final_layer).
OMNI_ENCODERS = {"tencent/Hunyuan3D-Omni": ["cond_encoder/pytorch_model.bin"]}
DINOV2_COMMIT = "47b73eefe95e8d44ec3623f8890bd894b6ea2d6c"
DINOV2 = {"facebook/dinov2-large": ["config.json", "model.safetensors"]}
# PartCrafter (MIT): its diffusers folder. Its README's background remover (briaai/RMBG-1.4, non-commercial) is not
# fetched — the kit's BiRefNet cuts the picture out.
PARTCRAFTER = {"wgsxm/PartCrafter": ["model_index.json", "scheduler/scheduler_config.json",
                                     "feature_extractor_dinov2/preprocessor_config.json",
                                     "image_encoder_dinov2/config.json", "image_encoder_dinov2/model.safetensors",
                                     "transformer/config.json", "transformer/diffusion_pytorch_model.safetensors",
                                     "vae/config.json", "vae/diffusion_pytorch_model.safetensors"]}
PARTCRAFTER_COMMIT = "69a0ffc1dad5e48e7e5ed91c0609f2b1276eb31f"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(files, token=None, root=ROOT, revision=None, flat=False):
    """root: where the set lives; revision: a pinned commit (default: the repo's current one); flat: the files go
    straight into root (one repo per set) instead of root/<repo name>"""
    from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415

    pins_path = os.path.join(root, "pins.json")
    pins = json.load(open(pins_path, encoding="utf-8")) if os.path.isfile(pins_path) else {}
    api, bad = HfApi(token=token), 0
    for repo, names in files.items():
        info = api.model_info(repo, files_metadata=True, revision=revision)
        meta = {s.rfilename: s for s in info.siblings}
        for name in names:
            s = meta[name]
            local = hf_hub_download(repo, name, revision=info.sha, token=token,
                                    local_dir=root if flat else os.path.join(root, repo.split("/")[1]))
            size, digest = os.path.getsize(local), sha256(local)
            ok = (s.lfs is None or (digest == s.lfs.sha256 and size == s.lfs.size))
            bad += not ok
            pins[f"{repo}/{name}"] = {"commit": info.sha, "size": size, "sha256": digest}
            print(("OK  " if ok else "BAD ") + f"{repo}/{name} {size} bytes", flush=True)
    os.makedirs(root, exist_ok=True)
    with open(pins_path, "w", encoding="utf-8") as fh:
        json.dump(pins, fh, indent=1)
    return bad


def main(argv):
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    files = dict(FILES)
    token = None
    if "--omni-encoders" in argv:
        bad = fetch(OMNI_ENCODERS, root=OMNI_ROOT, revision=OMNI_COMMIT, flat=True)
        bad += fetch(DINOV2, root=OMNI_ROOT, revision=DINOV2_COMMIT)  # -> <root>/dinov2-large
        print(json.dumps({"schema": 1, "status": "pass" if not bad else "fail",
                          "summary": f"fetch: Omni's encoders {'verified' if not bad else f'{bad} file(s) FAILED'}",
                          "next_action": "lune run kit gen omni <name> --image <picture> --from-asset <asset>"}))
        return 0 if not bad else 1
    if "--omni" in argv:
        bad = fetch(OMNI, root=OMNI_ROOT, revision=OMNI_COMMIT, flat=True)
        print(json.dumps({"schema": 1, "status": "pass" if not bad else "fail",
                          "summary": f"fetch: Hunyuan3D-Omni {'verified' if not bad else f'{bad} file(s) FAILED'} "
                                     f"({OMNI_ROOT})",
                          "next_action": "lune run kit gen omni <name> --image <picture> --from-asset <asset>"}))
        return 0 if not bad else 1
    if "--1024" in argv:   # public, MIT: no token; the 512 set's own commit, so the two sets are one release
        bad = fetch(HI_RES, None, ROOT, TRELLIS2_COMMIT)
        print(json.dumps({"schema": 1, "status": "pass" if not bad else "fail",
                          "summary": f"fetch: TRELLIS.2's 1024 networks {'verified' if not bad else f'{bad} file(s) FAILED'}"
                                     f" ({ROOT})",
                          "next_action": "lune run kit gen <name> --image <picture> --res 1024"}))
        return 0 if not bad else 1
    if "--partcrafter" in argv:  # public, MIT: no token
        root = os.path.join(MODELS, "partcrafter")
        bad = fetch(PARTCRAFTER, None, root, PARTCRAFTER_COMMIT)
        print(json.dumps({"schema": 1, "status": "pass" if not bad else "fail",
                          "summary": f"fetch: PartCrafter {'verified' if not bad else f'{bad} file(s) failed'}"
                                     f" ({root})",
                          "next_action": "lune run kit gen parts <name> --image <picture> --parts <n>"}))
        return 0 if not bad else 1
    if "--dinov3" in argv:
        token = os.environ.get("HF_TOKEN")
        if not token:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "fetch: --dinov3 needs HF_TOKEN in the "
                              "environment (DINOv3 is gated: request access on huggingface.co first)",
                              "next_action": "the owner sets HF_TOKEN (a read token) — never paste it into a chat"}))
            return 1
        files = DINOV3 if "--only-dinov3" in argv else {**files, **DINOV3}
    bad = fetch(files, token)
    status = "pass" if not bad else "fail"
    print(json.dumps({"schema": 1, "status": status,
                      "summary": f"fetch: {'every file verified' if not bad else f'{bad} file(s) failed the check'}"
                                 f" ({ROOT})", "next_action": "lune run kit gen <name> --image <picture>"}))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
