---
kind: lesson
area: kit
date: 2026-10-06
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Vetting an install: read a package's pyproject.toml dependencies as well as setup.py — FlexGEMM's setup.py lists only torch, its pyproject pulls triton-windows on Windows (caught after the download; the owner approved keeping it). And check every component's licence, not just the headline model's: TRELLIS.2 is MIT, but its default helpers nvdiffrast (NVIDIA, non-commercial) and RMBG-2.0 (CC BY-NC) are not.
