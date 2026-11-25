---
kind: lesson
area: kit
date: 2026-10-06
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Vetting a MODEL: the approved file list can miss what its code fetches at run time. Grep its configs for from_pretrained names and list the main weight file's state-dict keys (torch.load(mmap=True, weights_only=True): seconds, no RAM) BEFORE calling it installed — Hunyuan3D-Omni's 12 GB DiT file holds no image or control encoder (752 keys: t_embedder, x_embedder, blocks, final_layer); it also needs cond_encoder/pytorch_model.bin + facebook/dinov2-large
