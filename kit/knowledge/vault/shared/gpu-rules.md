---
kind: reference
area: shared
date: 2026-10-16
source: kit lessons 3d (2026-10-06), ui (2026-10-14), a build profile measured on a 12 GB RTX 5070
links: ["[[shared/vision-stack]]", "[[shared/images]]"]
---

# GPU rules (RTX 5070, 12 GB; Windows WDDM)

- ONE GPU job at a time. Windows never says "out of memory": a job that outgrows the card spills into shared system
  memory and runs 4-20x slower (Pixal3D's 1024 shape stage: 22 min instead of 2). Start generators only on an idle
  card; never beside SAM tracing or a Blender bake.
- Peaks that matter are PyTorch's RESERVED memory, not allocated: `torch.cuda.empty_cache()` between a generator's
  stages (kit/gen/pixal3d_run.py does).
- Driver fault (2026-10-14): `torch.cuda.is_available()` segfaulted the whole process while nvidia-smi still
  answered. Owner fix: Win+Ctrl+Shift+B or a reboot. Session fix: `KIT_FORCE_CPU=1` runs the vision stack on the CPU
  (SigLIP rank 234 s for 26 stills; depth relief OK) and Blender falls back to CPU Cycles (216 s for 2 small frames).
- Cycles: OpenImageDenoise on the GPU gives the same picture 5x faster (4.8 -> 1.0 s per presentation shot);
  Freestyle line art stays on the CPU (1.5-5.6 s per view, set by geometry).
- Bake cost is per PASS, not per pixel: pack one-number channels three to a bake (R, G, B); a 1-sample emission
  pass is faster on the CPU than the GPU.
- Qwen-Image-Edit needs ~22 GB free RAM; something outside the sessions once held ~26 GB — check before planning on it.
- Kimodo on 12 GB needs `TEXT_ENCODER_DEVICE=cpu` (and Kimodo is not the animation route).
- Blender build profile (M107): 508 s -> 145.9 s cold / 21.6 s cached / 15.6 s `--geo`; builds are not
  bit-reproducible (tolerance caches, never exact mesh hashes).
