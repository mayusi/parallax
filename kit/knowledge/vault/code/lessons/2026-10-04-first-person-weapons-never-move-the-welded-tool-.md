---
kind: lesson
area: code
date: 2026-10-04
by: mayusi
source: "kit/lessons/code.md"
links: ["[[code/index]]"]
project: sample_game
---

First-person weapons: never move the welded tool per frame (it trails the camera by a frame and rebuilds the weld 60x/s = stutter). Render a client-only copy under the camera in BindToRenderStep(Camera+1), drawn at ~0.3 scale and 0.3 distance (no wall clipping), hide the real handle with LocalTransparencyModifier, and make the real Handle Massless + CanCollide false. Keep it RIGID (camera.CFrame * offset): sway driven by per-frame camera/mouse deltas shakes because mouse input arrives unevenly — the owner called it choppy.
