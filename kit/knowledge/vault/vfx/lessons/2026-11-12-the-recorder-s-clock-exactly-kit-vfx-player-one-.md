---
kind: lesson
area: vfx
date: 2026-11-12
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

The recorder's clock, exactly (kit/vfx/player: one player.step(1/fps) a frame, the frame taken AFTER the step): frame 0 shows 1/fps, not 0; a hit-stop is the frame that stops ON it plus the WHOLE frames of its hold (0.12 s at 30 a second: three held frames; what was left of the step that crossed it is lost); of two hit-stops on one moment only the first holds. Use denseclip.frame_times / clock_of(preset, fps) to find a chart moment in a recording - never a sum of the holds (it was up to a frame and a half off). The recorder posts every frame's clock (build/vfx/booth/<run>_play.metrics.json keeps them): that is the golden to test any clock model against.
