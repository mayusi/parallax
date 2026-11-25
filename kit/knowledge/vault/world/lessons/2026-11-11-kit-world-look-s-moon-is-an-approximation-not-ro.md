---
kind: lesson
area: world
date: 2026-11-11
by: mayusi
source: "kit/lessons/world.md"
links: ["[[world/index]]"]
project: Parallax
---

kit world look's moon is an approximation, not Roblox's: at a night clockTime it shines from the opposite azimuth to the look's fixed day sun (Blender 215 deg - from the north-west, travelling toward Roblox +z) at a height from the clock ((clock + 12) mod 24 on the sun's curve: clockTime 2.5 = about 55 deg). A facade meant to be moonlit in the look must face NORTH (-z): GothicCourtyard's cathedral was moved to the court's south side for this. Roblox's real moon (Lighting:GetMoonDirection) follows ClockTime and GeographicLatitude; check the facade in Studio before trusting the look's shadows.
