---
kind: lesson
area: 3d
date: 2026-10-05
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Vetting downloaded models: vendor small model code (TEED 150 lines, BiRefNet 2100) instead of trust_remote_code; safetensors weights (or torch.load weights_only=True); pin commit + sha256 and re-hash after download; run with a socket guard (any network attempt raises). 6 local lines replaced three pip packages (timm/kornia/einops) — check how much of a dependency the code really uses.
