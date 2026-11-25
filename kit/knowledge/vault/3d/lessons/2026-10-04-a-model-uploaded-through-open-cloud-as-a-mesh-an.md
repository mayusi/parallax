---
kind: lesson
area: 3d
date: 2026-10-04
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: sample_game
---

A model uploaded through Open Cloud as a Mesh and shown via SpecialMesh faced +Z (backwards) in Studio — measure barrel-vs-camera direction in a probe and fix with Tool.Grip * CFrame.Angles(0, pi, 0); first-person tools: lock the grip to the camera each frame (R6 arms do not pitch).
