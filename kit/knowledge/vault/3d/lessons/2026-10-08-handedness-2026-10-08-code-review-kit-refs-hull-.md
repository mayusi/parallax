---
kind: lesson
area: 3d
date: 2026-10-08
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

HANDEDNESS (2026-10-08, code review): kit refs hull wrote its OBJ MIRRORED - the carving frame (x right, y up, z INTO the side photo) is left-handed, so front +x / up +y put the object's LEFT side at +z, and every 3D tool reads an OBJ right-handed. The square ortho views were right (written knowing +z was left). Fixed at the write (occ[:, :, ::-1]) with a test that FAILS on the old code: a bump on the object's left must come out at -z and at the top of the top view, for --front right and --front left. Any tool that writes geometry from its own camera frame: test a one-sided feature, never a symmetric block.
