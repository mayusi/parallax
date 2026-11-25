---
kind: lesson
area: anim
date: 2026-11-04
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A strike-route clip that turns the body N full turns must END on the spin's own yaw number (e.g. -2172), never the stance's -12: the same facing mod 360, but yaw is interpolated numerically, so the last segment silently spun him all N turns again in 0.16 s - invisible in stills, it inflated the leg-angle and arm-sink numbers (DTDrillSpin, 2026-11-04). Check: torso_yaw_range_deg should equal 360 x turns
