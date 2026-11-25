---
kind: lesson
area: kit
date: 2026-11-13
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Two checks before work on the kit's files. (1) Before writing a NEW module, check its name is free: git ls-files and ls - kit/blender/rbx_scatter.py existed (the grip relief's maths) and a new file of that name overwrote it for a minute, mid self-test. (2) Before saying a change gives the same bytes as before, build the fixture TWICE with the old code: build_zone_split bakes differently from run to run on the committed builder, and one old-against-new comparison would have blamed the change
