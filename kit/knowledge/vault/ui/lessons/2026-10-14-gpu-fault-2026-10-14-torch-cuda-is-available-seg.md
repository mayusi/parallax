---
kind: lesson
area: ui
date: 2026-10-14
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

GPU fault 2026-10-14: torch.cuda.is_available() segfaulted the whole process (Blender saw no OptiX either) while nvidia-smi still answered — a driver fault (owner: Win+Ctrl+Shift+B or reboot). KIT_FORCE_CPU=1 runs the vision stack on the CPU (SigLIP rank 234 s for 26 stills; depth relief OK); Blender falls back to CPU Cycles (216 s for 2 small frames).
