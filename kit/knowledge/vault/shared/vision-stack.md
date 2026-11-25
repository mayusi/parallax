---
kind: reference
area: shared
date: 2026-10-16
source: kit/vision/models.json, VETLOG.md, kit lessons
links: ["[[shared/gpu-rules]]", "[[3d/index]]", "[[ui/index]]", "[[vfx/index]]"]
---

# The vision stack (local, vetted, pinned in `kit/vision/models.json`)

| Model | Licence | What it does in the kit | Command |
|---|---|---|---|
| TEED | MIT | edges on a photo AND on a shaded render, compared in one frame (internal lines a silhouette cannot see) | `kit vision edges` |
| SAM 2.1 hiera-small | Apache-2.0 | ONE part's mask from a point or box prompt (box prompts for big parts; points / negatives for small ones) | `kit vision mask`, `kit trace --part-box` |
| SAM 3 (TRELLIS.2 env) | per its card | every match of a text prompt | `kit vision parts --text`, `kit trace --part-text` |
| BiRefNet (Swin-L fp16, vendored) | MIT | cutouts; counts an aura as foreground (cannot split golden aura from golden hair) | `kit vision cutout` |
| Depth Anything V2 Small | Apache-2.0 | depth / relief from a cut-out | `kit vision depth`, `kit vision relief` |
| SigLIP 2 base | Apache-2.0 | similarity to a REFERENCE (never a free-floating taste meter: zero-shot quality correlates ~0 with the owner); cannot find faces in ink art | `kit vision similar`, `kit ui refs --rank` |
| DINOv2 with registers (small) | Apache-2.0 | per-patch "where it differs" maps | `kit vision differ` |
| DINOv3 ViT-L (TRELLIS.2 encoder) | DINOv3 licence (owner's call: all assets) | image encoder for the generators | `kit gen` |
| Marigold-IID | per its card | albedo + roughness + metalness from one picture (colour without its lighting) | `kit vision albedo` |
| Real-ESRGAN x2 / x4 | BSD-3 | upscaling low-res design pictures before tracing (`--x 4`, then `kit trace --tolerance 1.0`) | `kit vision upscale` |
| vtracer | MIT | lines to SVG curves (UI meshes via `kit ui spin`) | `kit vision vectorize` |
| FLUX.2 klein 4B | per its card | concept pictures / turnaround sheets from words (ORIGINAL art only; never a stand-in for a known character) | `kit vision concept` |
| Qwen-Image-Edit-2511 | per its card | a picture from another camera / edited by an instruction — LOW TRUST, look never measure; needs ~22 GB free RAM | `kit vision angle / edit` |
| DiffusionLight-Turbo | per its card | a picture's lighting as an HDR map | `kit vision light` |
| RapidOCR (ONNX, CPU) | Apache-2.0 | the WORDS in a UI still | `kit ui read` |
| TRELLIS.2-4B, Pixal3D, Hunyuan3D-2mv / Omni (private only), PartCrafter | MIT / MIT / Tencent / per card | image-to-3D drafts and PARTS (never a hero's hard surface) | `kit gen` |

Rules: run ONE GPU model at a time on an idle card ([[shared/gpu-rules]]); `kit vision serve` keeps the warm models;
a model's first bad result is usually a bad TEST (check the mask / the alpha / the pixel you clicked); every new
generator's frame is checked by silhouette vs its cloud projections before a blockout is mapped into it.
