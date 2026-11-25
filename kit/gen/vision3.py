"""vision3.py — the kit's diffusion models (owner-approved 2026-10-06), run in the diffusers environment
(~/.cache/roblox-kit/envs/diffusers: torch 2.10 + CUDA 13 for the RTX 50s, diffusers 0.41). `lune run kit vision
<command> ...` routes here:

    light <picture> [-o out.exr] [--seed 200] [--height 256]
        the picture's lighting as an HDR environment map: DiffusionLight-Turbo paints a chrome ball into it (SDXL +
        depth ControlNet + its two LoRAs, at EV 0, -2.5 and -5), the balls are unwrapped and merged into one
        equirectangular EXR; + facts (where the key light comes from, key-to-fill ratio, colour temperature) and a
        preview in build/vision/. The maths: kit/gen/diffusionlight.py (vendored, MIT)
    concept "<description>" [--sheet turnaround|views|single|three_quarter] [--from <front.png>] [--seed N] [-o out]
        a CONCEPT picture from words (FLUX.2 [klein] 4B): `single` = one three-quarter view, `turnaround` (default) =
        front, side, back and top on plain grey, drawn together in one picture (one design), cut into views and
        checked (four objects found, no view a copy of the front, the upright views equally tall); `views` = front,
        side (its front facing left: the object's LEFT side) and back, three to a row (bigger, and no top view — the
        top the model draws most often repeats the front) — what `kit make` feeds its generators for a name-only
        object: ONE design from three sides (2026-10-09: asked for a three-quarter view as well, the model drew the
        views out of order); `three_quarter --from <its front view>` = that SAME design from the front-left and above
        (drawn with the front as a reference: a top or a 3/4 for the painter and single-photo generators — asked for
        straight down it still draws it from above the front). A concept agrees a look for a name-only request; it
        is never a measurement

Offline: every socket connection raises, Hugging Face is offline, and each weight file is checked against its pin in
kit/vision/models.json (size) before use. The models load in stages, each straight onto the GPU (text encoders, then
the denoiser), so the peak is the same as diffusers' model CPU offload with half the RAM and no copying back and forth.
"""

import gc
import json
import os
import re
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(ROOT, "kit", "vision", "models.json")
BUILD = os.path.join(ROOT, os.environ.get("KIT_BUILD", "build"))
CACHE = os.environ.get("KIT_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "models")
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                  DIFFUSERS_VERBOSITY="error", TRANSFORMERS_VERBOSITY="error")


def _no_network(*_a, **_k):
    raise RuntimeError("kit vision runs offline: a network connection was attempted and blocked")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.socket.sendto = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import diffusionlight as dl  # noqa: E402

# GPU memory a command needs free before it starts (measured on the RTX 5070, 2026-10-06; see kit/gen/README.md)
NEED_GB = {"light": 9.5, "concept": 9.5, "plate": 9.5}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def model_dir(name):
    """the model's folder, every pinned file present at its pinned size (else a clear error)"""
    with open(MANIFEST, encoding="utf-8") as fh:
        m = json.load(fh)["models"][name]
    folder = os.path.join(CACHE, name)
    for f in m["files"]:
        p = os.path.join(folder, f["path"])
        if not os.path.isfile(p) or os.path.getsize(p) != f["size"]:
            raise FileNotFoundError(f"{name}/{f['path']} missing or not its pinned size — "
                                    f"lune run kit vision setup {name}")
    return folder


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _free(*models):
    """release models' GPU memory NOW (their tensors emptied, whatever still refers to them), then the cache.
    (A plain `del` left the SDXL UNet + ControlNet on the GPU through the VAE decode: 11.8 GB, it crawled.)"""
    import torch  # noqa: PLC0415

    for m in models:
        if m is not None:
            for t in list(m.parameters()) + list(m.buffers()):
                t.data = torch.empty(0, dtype=t.dtype)
    gc.collect()
    torch.cuda.empty_cache()


def _peak():
    """the most GPU memory PyTorch held since the last call (GB), then a fresh count"""
    import torch  # noqa: PLC0415

    p = round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)
    torch.cuda.reset_peak_memory_stats()
    return p


def _gpu_check(cmd):
    """None if the GPU has room for `cmd`, else the failing verdict's arguments"""
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        return (f"vision {cmd}: needs an NVIDIA GPU (CUDA) — none found", "run it on the PC with the RTX card")
    free, total = (v / 2 ** 30 for v in torch.cuda.mem_get_info())
    if free < NEED_GB[cmd]:
        return (f"vision {cmd}: the GPU has {free:.1f} GB free, {cmd} needs about {NEED_GB[cmd]} GB",
                "close other GPU programs (or wait for a running kit gen / vision job) and run it again")
    # never ask for more than is free: past it Windows pages GPU memory to RAM — 10x slower, and a contended run
    # once came back as pure noise. Over the cap PyTorch empties its cache and retries, else stops with an error.
    torch.cuda.set_per_process_memory_fraction(min(1.0, (free - 0.3) / total))
    return None


def _to_gpu(model):
    import torch  # noqa: PLC0415

    return model.to("cuda", torch.float16) if hasattr(model, "dtype") else model.to("cuda")


# ---------------------------------------------------------------------------------------------------------- light
def light_facts(hdr):
    """facts about an equirectangular HDR map (middle column = where the camera looks, left half = its left)"""
    H, W = hdr.shape[:2]
    az = ((np.arange(W) + 0.5) / W - 0.5) * 2 * np.pi  # 0 = ahead (into the scene), + = to the camera's right
    el = np.pi / 2 - (np.arange(H) + 0.5) / H * np.pi  # + = above the horizon
    AZ, EL = np.meshgrid(az, el)
    dirs = np.stack([np.cos(EL) * np.sin(AZ), np.sin(EL), np.cos(EL) * np.cos(AZ)], -1)  # (right, up, ahead)
    solid = np.cos(EL) * (2 * np.pi / W) * (np.pi / H)
    rgb = np.maximum(hdr.astype(np.float64), 0)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    w = lum * solid
    d = (w[..., None] * dirs).sum((0, 1))
    key = d / (np.linalg.norm(d) + 1e-12)
    cos_k = dirs @ key
    e_key = (rgb * (solid * np.clip(cos_k, 0, None))[..., None]).sum((0, 1))  # irradiance facing the key
    e_fill = (rgb * (solid * np.clip(-cos_k, 0, None))[..., None]).sum((0, 1))  # ... facing away from it
    y_key, y_fill = float(e_key @ [0.2126, 0.7152, 0.0722]), float(e_fill @ [0.2126, 0.7152, 0.0722])
    # the brightest spot (a 3 x 3 box blur against single hot pixels)
    pad = np.pad(lum, 1, mode="edge")
    blur = sum(pad[i:i + H, j:j + W] for i in range(3) for j in range(3)) / 9
    r, c = np.unravel_index(int(np.argmax(blur)), blur.shape)
    key_az, key_el = float(np.degrees(np.arctan2(key[0], key[2]))), float(np.degrees(np.arcsin(np.clip(key[1], -1, 1))))
    return {
        "key_light": {"azimuth_deg": round(key_az, 1), "elevation_deg": round(key_el, 1),
                      "from": describe(key_az, key_el),
                      "camera_vector": [round(float(v), 3) for v in key],
                      "blender_vector": [round(float(key[2]), 3), round(float(-key[0]), 3), round(float(key[1]), 3)]},
        "brightest_spot": {"azimuth_deg": round(float(np.degrees(az[c])), 1),
                           "elevation_deg": round(float(np.degrees(el[r])), 1),
                           "times_the_average": round(float(blur[r, c] / (lum.mean() + 1e-12)), 1)},
        "directional": round(float(np.linalg.norm(d) / (w.sum() + 1e-12)), 3),
        "key_to_fill": round(y_key / max(y_fill, 1e-9), 2),
        "key_colour_temperature_k": cct(e_key),
        "fill_colour_temperature_k": cct(e_fill),
        "key_colour_srgb": srgb8(e_key),
        "fill_colour_srgb": srgb8(e_fill),
    }


def describe(az, el):
    """plain words for a light's direction (az: 0 = ahead of the camera, + = right; el: + = up)"""
    side = "right" if az > 0 else "left"
    a = abs(az)
    where = ("behind the subject (a back light, facing the camera)" if a < 30 else
             f"behind the subject, from the {side}" if a < 75 else
             f"from the {side} side" if a < 105 else
             f"from the front {side}" if a < 150 else "from behind the camera (a front light)")
    height = ("high above" if el > 55 else "above" if el > 20 else "about level" if el > -10 else "below")
    return f"{height}, {where}"


def cct(rgb):
    """correlated colour temperature (K) of a linear sRGB colour (McCamy; good from ~2,000 to ~12,000 K)"""
    r, g, b = (float(v) for v in rgb)
    X = 0.4124 * r + 0.3576 * g + 0.1805 * b
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = 0.0193 * r + 0.1192 * g + 0.9505 * b
    s = X + Y + Z
    if s <= 0:
        return None
    x, y = X / s, Y / s
    n = (x - 0.3320) / (0.1858 - y)
    return int(round(min(max(449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33, 1000), 25000), -1))


def srgb8(rgb):
    """a linear colour scaled so its brightest channel is 1, as 8-bit sRGB (a light's colour, not its strength)"""
    v = np.maximum(np.asarray(rgb, dtype=np.float64), 0)
    v = v / (v.max() + 1e-12)
    v = np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.power(v, 1 / 2.4) - 0.055)
    return [int(round(float(c) * 255)) for c in v]


def paint_balls(square, seed, log):
    """DiffusionLight-Turbo: the picture (SIZE x SIZE) -> {EV: the painted SIZE x SIZE picture}"""
    import torch  # noqa: PLC0415
    from transformers import pipeline as hf_pipeline  # noqa: PLC0415

    t = time.time()
    depth_model = hf_pipeline("depth-estimation", model=model_dir("dpt-large"), device=0, dtype=torch.float16)
    depth = depth_model(Image.fromarray(square))["depth"]
    _free(depth_model.model)
    del depth_model
    if depth.size != (dl.SIZE, dl.SIZE):
        depth = depth.resize((dl.SIZE, dl.SIZE), Image.BICUBIC)
    control, mask = dl.control_and_mask(np.asarray(depth.convert("L")))
    log["depth_s"] = round(time.time() - t, 1)
    log["depth_peak_gb"] = _peak()

    from diffusers import (AutoencoderKL, ControlNetModel, StableDiffusionXLControlNetInpaintPipeline,  # noqa: PLC0415
                           StableDiffusionXLPipeline, UNet2DConditionModel, UniPCMultistepScheduler)

    sdxl = model_dir("sdxl-base-1.0")
    t = time.time()
    enc = StableDiffusionXLPipeline.from_pretrained(sdxl, unet=None, vae=None, variant="fp16",
                                                    torch_dtype=torch.float16).to("cuda")
    with torch.no_grad():
        white, negative, white_pooled, negative_pooled = enc.encode_prompt(
            dl.PROMPT, device="cuda", do_classifier_free_guidance=True, negative_prompt=dl.NEGATIVE)
        black, _, black_pooled, _ = enc.encode_prompt(dl.PROMPT_BLACK, device="cuda", do_classifier_free_guidance=True,
                                                      negative_prompt=dl.NEGATIVE)
    _free(enc.text_encoder, enc.text_encoder_2)
    del enc
    log["prompts_s"] = round(time.time() - t, 1)
    log["prompts_peak_gb"] = _peak()

    t = time.time()
    unet =UNet2DConditionModel.from_pretrained(sdxl, subfolder="unet", variant="fp16", torch_dtype=torch.float16)
    unet = _to_gpu(unet)
    controlnet = _to_gpu(ControlNetModel.from_pretrained(model_dir("controlnet-depth-sdxl"), variant="fp16",
                                                         torch_dtype=torch.float16))
    vae = _to_gpu(AutoencoderKL.from_pretrained(model_dir("sdxl-vae-fp16-fix"), torch_dtype=torch.float16))
    pipe = StableDiffusionXLControlNetInpaintPipeline.from_pretrained(
        sdxl, unet=unet, controlnet=controlnet, vae=vae, text_encoder=None, text_encoder_2=None, tokenizer=None,
        tokenizer_2=None, add_watermarker=False, torch_dtype=torch.float16)
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)  # (the authors: ~30 steps, better)
    pipe.set_progress_bar_config(disable=True)
    from safetensors.torch import load_file  # noqa: PLC0415

    for name, model in (("turbo", "diffusionlight-turbo-lora"), ("exposure", "diffusionlight-exposure-lora")):
        sd = load_file(os.path.join(model_dir(model), "pytorch_lora_weights.safetensors"))
        # saved as "unet.unet.<layer>" (an older diffusers' training wrapper): diffusers 0.41 strips one "unet."
        sd = {("unet." + k[len("unet.unet."):] if k.startswith("unet.unet.") else k): v for k, v in sd.items()}
        pipe.load_lora_weights(sd, adapter_name=name)
    lora_layers = sum(1 for m in pipe.unet.modules() if hasattr(m, "lora_A") and "exposure" in getattr(m, "lora_A", {}))
    if lora_layers == 0:
        raise RuntimeError("the DiffusionLight LoRAs did not attach to the UNet (0 layers): the ball would be guessed")
    log["lora_layers"] = lora_layers

    # the authors' bilinear mask downscale (diffusers uses nearest): a cleaner ball edge
    original, scale = pipe.prepare_mask_latents, pipe.vae_scale_factor

    def bilinear_mask(mask_t, *args, **kwargs):
        h, w = args[2], args[3]  # (masked_image, batch_size, height, width, ...)
        mask_t = torch.nn.functional.interpolate(mask_t, size=(h // scale, w // scale), mode="bilinear",
                                                 align_corners=False)
        return original(mask_t, *args, **kwargs)

    pipe.prepare_mask_latents = bilinear_mask
    log["load_s"] = round(time.time() - t, 1)
    print(f"loaded ({lora_layers} LoRA layers, GPU {torch.cuda.memory_allocated() / 2 ** 30:.1f} GB)", file=sys.stderr,
          flush=True)

    out = {}
    t = time.time()
    for ev in dl.EVS:
        r = dl.prompt_mix(ev)
        pipe.set_adapters(["turbo"], adapter_weights=[1.0])
        switched = []

        def switch(p, i, step_t, kw):
            if not switched and step_t <= dl.SWITCH_T:
                p.set_adapters(["exposure"], adapter_weights=[dl.EXPOSURE_LORA_SCALE])
                switched.append(i)
            return kw

        with torch.no_grad():
            res = pipe(prompt_embeds=white * r + black * (1 - r),
                       pooled_prompt_embeds=white_pooled * r + black_pooled * (1 - r),
                       negative_prompt_embeds=negative, negative_pooled_prompt_embeds=negative_pooled,
                       num_inference_steps=dl.STEPS, image=Image.fromarray(square), mask_image=Image.fromarray(mask),
                       control_image=Image.fromarray(control), controlnet_conditioning_scale=dl.CONTROL_SCALE,
                       height=dl.SIZE, width=dl.SIZE, callback_on_step_end=switch, output_type="latent",
                       generator=torch.Generator("cuda").manual_seed(seed))
        out[ev] = res.images  # (latents: decoded below, once the UNet and ControlNet are off the GPU)
        gb = torch.cuda.max_memory_allocated() / 2 ** 30
        print(f"painted EV {ev:g} ({time.time() - t:.0f} s, GPU peak {gb:.1f} GB)", file=sys.stderr, flush=True)
    log["paint_peak_gb"] = _peak()
    processor = pipe.image_processor
    _free(unet, controlnet)
    del pipe, unet, controlnet
    print(f"denoisers off the GPU ({torch.cuda.memory_allocated() / 2 ** 30:.1f} GB still allocated)", file=sys.stderr,
          flush=True)
    with torch.no_grad():
        for ev, lat in out.items():
            img = vae.decode(lat / vae.config.scaling_factor, return_dict=False)[0]
            out[ev] = (processor.postprocess(img, output_type="np")[0] * 255).round().astype(np.uint8)
    log["paint_s"] = round(time.time() - t, 1)
    log["decode_peak_gb"] = _peak()
    _free(vae)
    del vae
    return out, control


def light_preview(path, painted, box, balls, hdr, facts):
    """the painted picture + the three balls over the tone-mapped map, the key light marked"""
    W = 960
    canvas = Image.new("RGB", (W, 384 + 480 + 56), (24, 24, 26))
    d = ImageDraw.Draw(canvas)
    x0, y0, nw, nh = box
    pic = Image.fromarray(painted[y0:y0 + nh, x0:x0 + nw])
    pic.thumbnail((384, 384))
    canvas.paste(pic, ((384 - pic.width) // 2, (384 - pic.height) // 2))
    for k, (ev, ball) in enumerate(balls):
        canvas.paste(Image.fromarray(ball).resize((184, 184), Image.LANCZOS), (392 + k * 190, 90))
        d.text((392 + k * 190 + 70, 280), f"EV {ev:g}", fill=(220, 220, 220))
    pano = Image.fromarray((dl.tonemap(hdr) * 255).astype(np.uint8)).resize((W, 480), Image.LANCZOS)
    canvas.paste(pano, (0, 384 + 28))
    pd = ImageDraw.Draw(canvas)
    for frac, label in ((0.0, "behind"), (0.25, "left"), (0.5, "ahead"), (0.75, "right")):
        x = int(frac * W)
        pd.line([(x, 412), (x, 412 + 480)], fill=(90, 90, 90))
        pd.text((x + 4, 392), label, fill=(200, 200, 200))
    pd.line([(0, 412 + 240), (W, 412 + 240)], fill=(90, 90, 90))  # the horizon
    k = facts["key_light"]
    kx = int((k["azimuth_deg"] / 360 + 0.5) * W)
    ky = int(412 + (0.5 - k["elevation_deg"] / 180) * 480)
    pd.ellipse([kx - 14, ky - 14, kx + 14, ky + 14], outline=(255, 60, 40), width=3)
    pd.text((8, 384 + 480 + 34), f"key light: {k['from']} (az {k['azimuth_deg']:g}, el {k['elevation_deg']:g}); "
            f"key:fill {facts['key_to_fill']:g}; key ~{facts['key_colour_temperature_k']} K", fill=(235, 235, 235))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    canvas.save(path)


def cmd_light(argv):
    import torch  # noqa: PLC0415

    src = argv[0]
    busy = _gpu_check("light")
    if busy:
        return emit("fail", *busy)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.join(BUILD, "vision", stem + ".light.exr")
    seed, height = _opt(argv, "--seed", dl.SEED), _opt(argv, "--height", 256)
    square, box = dl.fit_square(np.asarray(Image.open(src).convert("RGB")))
    t0, log = time.time(), {}
    torch.cuda.reset_peak_memory_stats()
    painted, _control = paint_balls(square, seed, log)
    balls = [(ev, dl.crop_ball(painted[ev])) for ev in dl.EVS]
    maps = [dl.ball_to_envmap(b.astype(np.float32) / 255, height=height) for _, b in balls]
    hdr = dl.merge_exposures(maps, dl.EVS)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    dl.write_exr(out, hdr)
    facts = light_facts(hdr)
    peak = max(v for k, v in log.items() if k.endswith("_peak_gb"))
    preview =os.path.join(BUILD, "vision", os.path.splitext(os.path.basename(out))[0] + "_preview.png")
    light_preview(preview, painted[0.0], box, balls, hdr, facts)
    record = {"source": src.replace("\\", "/"), "exr": out.replace("\\", "/"), "preview": preview.replace("\\", "/"),
              "map": {"width": int(hdr.shape[1]), "height": int(hdr.shape[0]), "projection": "equirectangular",
                      "middle": "where the camera looks", "left_half": "the camera's left", "top": "up",
                      "blender": "as a world texture it matches a camera looking along +X (Z up)"},
              "facts": facts, "seed": seed, "time_s": round(time.time() - t0, 1), "stages": log,
              "peak_gpu_gb": round(peak, 2),
              "models": ["sdxl-base-1.0", "sdxl-vae-fp16-fix", "controlnet-depth-sdxl", "diffusionlight-turbo-lora",
                         "diffusionlight-exposure-lora", "dpt-large"],
              "note": "an ESTIMATE painted by a diffusion model: right about where the light comes from and its "
                      "colour, approximate about its strength; what the picture cannot see (behind the camera) is "
                      "a plausible guess"}
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    k = facts["key_light"]
    return emit("pass", f"vision light: {out} ({hdr.shape[1]} x {hdr.shape[0]} HDR, {time.time() - t0:.0f} s, peak "
                        f"{peak:.1f} GB) — key light {k['from']} (azimuth {k['azimuth_deg']:g}, elevation "
                        f"{k['elevation_deg']:g}), key:fill {facts['key_to_fill']:g}, key ~"
                        f"{facts['key_colour_temperature_k']} K, fill ~{facts['fill_colour_temperature_k']} K — LOOK "
                        f"at {preview} (the painted ball, the three exposures, the map with the key light ringed)",
                "use it: the .exr as a world light in a showcase / Blender (camera along +X); the facts (+ .json) to "
                "set a key light", out=out.replace("\\", "/"), preview=preview.replace("\\", "/"), facts=facts)


# -------------------------------------------------------------------------------------------------------- concept
ORDER = ("front", "side", "back", "top")
VIEWS_ORDER = ("front", "side", "back")  # (--sheet views: the side drawn with its front facing left)
SHEET_W, SHEET_H = 2048, 640  # one generation, four views in a row (each ~512 px wide)


def concept_prompts(desc, sheet):
    """the words for one picture. A turnaround is ONE generation of all four views side by side: drawn together they
    show one design (drawing each view from the front as a reference picture gave four copies of the front)"""
    if sheet == "three_quarter":   # (drawn FROM the design's front view: the same object, not another one)
        return (f"A photorealistic studio product photograph of the same {desc} as in the reference image, the exact "
                f"same object, materials and details, seen from the front-left at three-quarters and a little above, "
                f"the whole object visible with a margin, plain flat mid-grey background, soft even studio lighting, "
                f"no shadows, no text")
    if sheet == "views":
        # (photographs, not drawings: a drawn sheet's black outlines and flat fills reached the painted model — a
        # treasure chest came out plain brown, its planks and brass latch lost)
        return (f"Three photorealistic studio product photographs of {desc}, the same single real object in one row, "
                f"evenly spaced and at the same scale, from left to right: front view, side view in profile with its "
                f"front facing left, back view. Orthographic views without perspective, real materials and textures, "
                f"each view fully visible with a margin, on a plain flat mid-grey background, soft even studio "
                f"lighting, no cast shadows, no outlines, no line art, no text, no labels")
    if sheet == "single":
        return (f"Concept art of {desc}, a three-quarter view, the whole object centred and fully visible, on a plain "
                f"flat mid-grey background, soft even studio lighting, no text")
    return (f"A product-design turnaround sheet of {desc}: the same object drawn four times in one row, evenly spaced "
            f"and at the same scale, from left to right: front view, side view in profile, back view, top view from "
            f"directly above. Orthographic views without perspective, each view fully visible with a margin, on a "
            f"plain flat mid-grey background, soft even studio lighting, no cast shadows, no text, no labels")


def _background(a):
    border = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3),
                             a[:, -8:].reshape(-1, 3)])
    return np.median(border, axis=0)


def object_box(rgb, bg=None):
    """the object's box [x, y, w, h] on a plain background: pixels that differ from the border's median colour"""
    a = np.asarray(rgb, dtype=np.float32)
    diff = np.abs(a - (_background(a) if bg is None else bg)).max(axis=2) > 24
    ys, xs = np.nonzero(diff)
    if len(xs) < 50:
        return None
    x0, x1, y0, y1 = np.percentile(xs, 0.5), np.percentile(xs, 99.5), np.percentile(ys, 0.5), np.percentile(ys, 99.5)
    return [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def split_views(sheet_im, n=4):
    """the sheet's views: cut between the objects where there are n of them in a row (else n equal cells)"""
    a = np.asarray(sheet_im, dtype=np.float32)
    bg = _background(a)
    fg = (np.abs(a - bg).max(axis=2) > 24).mean(axis=0) > 0.004  # columns with some object in them
    runs, start = [], None
    for x, f in enumerate(list(fg) + [False]):
        if f and start is None:
            start = x
        elif not f and start is not None:
            if runs and start - runs[-1][1] < 12:  # (a gap of a few px inside one object)
                runs[-1] = (runs[-1][0], x)
            else:
                runs.append((start, x))
            start = None
    runs = [r for r in runs if r[1] - r[0] >= 24]
    W = a.shape[1]
    if len(runs) == n:
        cuts = [0] + [(runs[i][1] + runs[i + 1][0]) // 2 for i in range(n - 1)] + [W]
    else:
        cuts = [round(W * i / n) for i in range(n + 1)]
    cells = [sheet_im.crop((cuts[i], 0, cuts[i + 1], sheet_im.height)) for i in range(n)]
    return cells, len(runs), bg


def square_on(im, bg):
    """a cell centred on a square of the background colour (a view the size of the sheet's height)"""
    s = max(im.size)
    out = Image.new("RGB", (s, s), tuple(int(v) for v in bg))
    out.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out


def cmd_concept(argv):
    desc = argv[0].strip()
    sheet = _opt(argv, "--sheet", "turnaround")
    if sheet not in ("turnaround", "views", "single", "three_quarter") or not desc or desc.startswith("--"):
        return emit("fail", f"vision concept: needs a description first and --sheet turnaround|views|single|"
                            f"three_quarter (got {sheet})",
                    'lune run kit vision concept "<description>" --sheet turnaround')
    ref = _opt(argv, "--from", "")
    if sheet == "three_quarter" and not os.path.isfile(ref):
        return emit("fail", "vision concept --sheet three_quarter: needs --from <the design's front view>",
                    'lune run kit vision concept "<description>" --sheet three_quarter --from <x>.front.png')
    import torch  # noqa: PLC0415
    from diffusers import Flux2KleinPipeline  # noqa: PLC0415

    busy = _gpu_check("concept")
    if busy:
        return emit("fail", *busy)
    seed, steps = _opt(argv, "--seed", 1), _opt(argv, "--steps", 4)
    width, height = (1024, 1024) if sheet in ("single", "three_quarter") else (SHEET_W, SHEET_H)
    slug = re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")[:48] or "concept"
    name = slug + ("" if sheet == "turnaround" else f".{sheet}")  # (one sheet never overwrites another)
    out = argv[argv.index("-o") + 1] if "-o" in argv else os.path.join(BUILD, "vision", "concepts", name + ".png")
    prompt = concept_prompts(desc, sheet)
    folder = model_dir("flux2-klein-4b")
    t0, log = time.time(), {}
    torch.cuda.reset_peak_memory_stats()

    t = time.time()  # stage 1: the text encoder (Qwen3 4B) alone, straight onto the GPU
    enc = Flux2KleinPipeline.from_pretrained(folder, transformer=None, vae=None, torch_dtype=torch.bfloat16,
                                             device_map="cuda")
    with torch.no_grad():
        embeds = enc.encode_prompt(prompt, device="cuda")[0]
    _free(enc.text_encoder)
    del enc
    log["prompts_s"] = round(time.time() - t, 1)
    log["prompts_peak_gb"] = _peak()

    t = time.time()  # stage 2: the transformer + VAE
    pipe = Flux2KleinPipeline.from_pretrained(folder, text_encoder=None, tokenizer=None, torch_dtype=torch.bfloat16,
                                              device_map="cuda")
    pipe.set_progress_bar_config(disable=True)
    log["load_s"] = round(time.time() - t, 1)
    t = time.time()
    with torch.no_grad():
        lat = pipe(prompt_embeds=embeds, height=height, width=width, num_inference_steps=steps, guidance_scale=1.0,
                   output_type="latent", generator=torch.Generator("cuda").manual_seed(seed),
                   **({"image": [Image.open(ref).convert("RGB")]} if sheet == "three_quarter" else {})).images
    log["draw_s"] = round(time.time() - t, 1)
    log["draw_peak_gb"] = _peak()
    vae, processor = pipe.vae, pipe.image_processor
    _free(pipe.transformer)  # (the decode runs with the transformer gone: a whole sheet at once, no tiles)
    del pipe
    with torch.no_grad():
        picture = processor.postprocess(vae.decode(lat.to(vae.dtype), return_dict=False)[0], output_type="pil")[0]
    log["decode_peak_gb"] = _peak()
    _free(vae)
    peak = max(v for k, v in log.items() if k.endswith("_peak_gb"))
    picture = picture.convert("RGB")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    base = os.path.splitext(out)[0]
    views, checks, found = {}, {}, None
    if sheet in ("single", "three_quarter"):
        picture.save(out)
        views[sheet] = {"object_box_px": object_box(picture), "file": out.replace("\\", "/")}
    else:
        order = VIEWS_ORDER if sheet == "views" else ORDER
        cells, found, bg = split_views(picture, len(order))
        cell = 512
        canvas = Image.new("RGB", (cell * len(order), cell + 64), (128, 128, 128))
        d = ImageDraw.Draw(canvas)
        small = {}
        for k, (v, im) in enumerate(zip(order, cells)):
            sq = square_on(im, bg)
            path = f"{base}.{v}.png"
            sq.save(path)
            views[v] = {"object_box_px": object_box(sq, bg), "file": path.replace("\\", "/")}
            canvas.paste(sq.resize((cell, cell), Image.LANCZOS), (k * cell, 0))
            d.text((k * cell + 10, cell + 8), v.upper(), fill=(20, 20, 20))
            small[v] = np.asarray(sq.convert("L").resize((128, 128)), dtype=np.float32)
        d.text((10, cell + 36), f"CONCEPT (FLUX.2 klein 4B, seed {seed}) - not a measurement: {desc}"[:250],
               fill=(30, 30, 30))
        canvas.save(out)
        picture.save(f"{base}.raw.png")
        checks["objects_found"] = found
        # a copy of the front (mean difference in grey levels at 128 px): copies measured 2.8-4.8, a chest's turned
        # views 7.8-9.3. The side and top only: a back can look like the front for real
        turned = ("side",) if sheet == "views" else ("side", "top")
        checks["least_different_from_front"] = round(min(float(np.abs(small[v] - small["front"]).mean())
                                                         for v in turned), 1)
        b = {v: views[v]["object_box_px"] for v in order}
        if b["front"] and b["side"] and b["back"]:  # one object, one scale: the upright views stand as tall
            checks["side_height_vs_front"] = round(b["side"][3] / max(b["front"][3], 1), 2)
            checks["back_height_vs_front"] = round(b["back"][3] / max(b["front"][3], 1), 2)
            checks["back_width_vs_front"] = round(b["back"][2] / max(b["front"][2], 1), 2)
    problems = []
    if sheet not in ("single", "three_quarter"):
        if found != len(VIEWS_ORDER if sheet == "views" else ORDER):
            problems.append(f"{found} objects in a row, not {len(VIEWS_ORDER if sheet == 'views' else ORDER)} (cut "
                            "into equal cells)")
        if checks["least_different_from_front"] < 6:
            problems.append(f"the {' or '.join(turned)} view repeats the front")
        problems += [f"{k} {r}" for k, r in checks.items() if k.endswith("_vs_front") and abs(r - 1) > 0.15]
    record = {"kind": "concept", "reference_measurement": False,
              "note": "a CONCEPT generated from words to agree a look; never a measurement — sizes come from real "
                      "references (kit refs) or kit/real_sizes.json",
              "description": desc, "sheet": sheet, "seed": seed, "steps": steps, "size": [width, height],
              "prompt": prompt, "views": views, "checks": checks, "problems": problems,
              "model": "flux2-klein-4b @ e7b7dc2 (Apache-2.0)", "time_s": round(time.time() - t0, 1),
              "stages": log, "peak_gpu_gb": round(peak, 2)}
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    warn = f"; check: {'; '.join(problems)}" if problems else ""
    return emit("pass", f"vision concept: {out} ({sheet}, {time.time() - t0:.0f} s, peak {peak:.1f} GB){warn} — "
                        f"LOOK at it: a concept, not a measurement",
                (f"improve: {'; '.join(problems)} — another --seed (or more words about the views)" if problems else
                 "look at it with the owner; agreed -> the brief (and kit gen <name> --image <its .front.png>)"),
                out=out.replace("\\", "/"), concept=True, views=views, checks=checks)



def cmd_plate(argv):
    """plate "<prompt>" [--from frame.png] [--seed 1] [--n 4] [--steps 4] [--size 1024] [-o build/vision/plates/<slug>]:
    drawn full-screen plates (anime impact frames: ink illustrations shown for a few frames) from a free prompt, `n`
    seeds in one model load; a contact sheet + a json record beside them. The prompt is used as written (no
    product-photo framing). `--from <frame>`: the plate is a REDRAW of that picture (the effect's own frame at the
    beat — same camera, figure and light; FLUX.2 klein image conditioning), at the frame's own size (<= 1 MP)."""
    prompt = argv[0]
    src = argv[argv.index("--from") + 1] if "--from" in argv else None
    ref = None
    if src:
        ref = Image.open(src).convert("RGB")
        if ref.width * ref.height > 1024 * 1024:
            k = (1024 * 1024 / (ref.width * ref.height)) ** 0.5
            ref = ref.resize((int(ref.width * k) // 16 * 16, int(ref.height * k) // 16 * 16), Image.LANCZOS)
    import torch  # noqa: PLC0415
    from diffusers import Flux2KleinPipeline  # noqa: PLC0415

    busy = _gpu_check("plate")
    if busy:
        return emit("fail", *busy)
    seed, n, steps, size = _opt(argv, "--seed", 1), _opt(argv, "--n", 4), _opt(argv, "--steps", 4), _opt(argv, "--size", 1024)
    slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:40] or "plate"
    out_dir = argv[argv.index("-o") + 1] if "-o" in argv else os.path.join(BUILD, "vision", "plates", slug)
    os.makedirs(out_dir, exist_ok=True)
    folder = model_dir("flux2-klein-4b")
    t0 = time.time()
    torch.cuda.reset_peak_memory_stats()
    enc = Flux2KleinPipeline.from_pretrained(folder, transformer=None, vae=None, torch_dtype=torch.bfloat16, device_map="cuda")
    with torch.no_grad():
        embeds = enc.encode_prompt(prompt, device="cuda")[0]
    _free(enc.text_encoder)
    del enc
    pipe = Flux2KleinPipeline.from_pretrained(folder, text_encoder=None, tokenizer=None, torch_dtype=torch.bfloat16, device_map="cuda")
    pipe.set_progress_bar_config(disable=True)
    lats = []
    with torch.no_grad():
        for k in range(n):
            kw = {"image": [ref], "height": ref.height // 16 * 16, "width": ref.width // 16 * 16} if ref is not None else {"height": size, "width": size}
            lats.append(pipe(prompt_embeds=embeds, num_inference_steps=steps, guidance_scale=1.0, output_type="latent",
                             generator=torch.Generator("cuda").manual_seed(seed + k), **kw).images)
    vae, processor = pipe.vae, pipe.image_processor
    _free(pipe.transformer)
    del pipe
    files = []
    with torch.no_grad():
        for k, lat in enumerate(lats):
            pic = processor.postprocess(vae.decode(lat.to(vae.dtype), return_dict=False)[0], output_type="pil")[0].convert("RGB")
            path = os.path.join(out_dir, f"plate_{seed + k:03d}.png")
            pic.save(path)
            files.append(path.replace("\\", "/"))
    _free(vae)
    peak = _peak()
    th = 320 if ref is None else int(320 * ref.height / ref.width)
    thumbs = [Image.open(f).convert("RGB").resize((320, th), Image.LANCZOS) for f in files]
    cols = min(4, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 320, rows * th + 20), (20, 20, 24))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * 320, (i // cols) * th))
    ImageDraw.Draw(sheet).text((6, rows * th + 4), f"PLATES (FLUX.2 klein 4B, seeds {seed}..{seed + n - 1}{', from ' + os.path.basename(src) if src else ''}): {prompt}"[:200], fill=(220, 220, 220))
    sheet_path = os.path.join(out_dir, "_sheet.png")
    sheet.save(sheet_path)
    with open(os.path.join(out_dir, "plates.json"), "w", encoding="utf-8") as fh:
        json.dump({"kind": "plate", "prompt": prompt, "from": src, "seed": seed, "n": n, "steps": steps, "size": size, "files": files,
                   "model": "flux2-klein-4b @ e7b7dc2 (Apache-2.0)", "time_s": round(time.time() - t0, 1), "peak_gpu_gb": round(peak, 2)}, fh, indent=1)
    return emit("pass", f"vision plate: {n} plate(s) in {out_dir} ({time.time() - t0:.0f} s, peak {peak:.1f} GB) — LOOK at _sheet.png",
                "pick the plates that read; register them: lune run kit vfx import <dir> --prefix plate --pack \"kit generated plates\"",
                out=out_dir.replace("\\", "/"), files=files, sheet=sheet_path.replace("\\", "/"))


def main(argv):
    cmds = {"light": cmd_light, "concept": cmd_concept, "plate": cmd_plate}
    if not argv or argv[0] not in cmds or len(argv) < 2:
        return emit("fail", "vision3: usage: light <picture> [-o out.exr] | concept \"<description>\" "
                            "[--sheet turnaround|views|single] [--seed N]", 'lune run kit vision concept "a wooden crate"')
    if argv[0] == "light" and not os.path.isfile(argv[1]):
        return emit("fail", f"vision light: no picture at {argv[1]}", "lune run kit vision light refs/<picture>")
    try:
        return cmds[argv[0]](argv[1:])
    except FileNotFoundError as e:
        return emit("fail", f"vision {argv[0]}: {e}", "lune run kit vision setup   (fetches the pinned models)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
