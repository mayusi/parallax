---
kind: lesson
area: vfx
date: 2026-10-15
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

SCENE BREAKDOWN beats memory (owner 2026-10-15: Hollow Purple v1 'looks really bad'). Wiki galleries had ~0 frames of the effect (65 stills, best 9 % purple); a 35 s scene clip (yt-dlp, vetted, private) studied at 2 fps showed v1 was wrong in its basics: Purple is a TINY fingertip starburst that releases a screen-filling WALL of light, Red/Blue are tiny marbles, the collision is ripple rings, there is a grey impact wash and a whiteout. Build per beat, then compare scene frame vs render frame per beat side by side (beats_compare sheets) - it catches what scores never do (a camera inside a tube sees nothing: inner faces are culled; a flood tint with +brightness turns grey-lavender, use saturation).
