---
kind: lesson
area: anim
date: 2026-11-22
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

kit/anim/clip.py metrics() breaks a Hit's striker tie by SET order (for e in set(strikers) | {lead}): the same clip named Right Arm / Left Arm / Blade as peak_of for PYTHONHASHSEED 1..8. The kit now pins PYTHONHASHSEED=0 for its Python children (Run.spawn, 2026-11-22); at clip.py's next tool change iterate dict.fromkeys(list(strikers) + [lead]) so a hand run is stable too (clip.py is in every clip's tool hash: changing it re-bakes all clips)
