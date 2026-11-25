---
kind: lesson
area: vfx
date: 2026-10-14
by: mayusi
source: "kit/lessons/vfx.md"
links: ["[[vfx/index]]"]
project: Parallax
---

THE DETAILS (owner 2026-10-15, Rasengan blow-out 'looks horrible'): air / energy is never a solid surface. Untextured Neon ribbons read as plastic; the fix that worked = flaring tube SHELLS carrying a dedicated streak texture (tex_wind_streaks.py: hairlines + strands + wisps, periodic along the flow; *_v variant for tubes because a tube's V runs along its height) scrolling outward, fadeIn/fadeOut soft feet and tips, an ease-out stretch, an erode dissolve; pressure rings as feathered mesh discs facing the flow (sprite rings seen edge-on = a white barcode); scattered thin streak sprites from a small volume (40 at once = one fat bar); wispy smoke (ul_wispy_smoke) not puff clouds. refs norms rule 6 now fails big untextured hard-edged opaque meshes.
