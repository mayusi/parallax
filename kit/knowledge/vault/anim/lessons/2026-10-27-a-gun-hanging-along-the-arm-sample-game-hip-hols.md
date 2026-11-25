---
kind: lesson
area: anim
date: 2026-10-27
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A GUN HANGING ALONG THE ARM (Sample Game hip holsters, 2026-10-27): with an animated grip and twist edge the RIGHT arm's roll is fitted to the barrel AND the edge; a holstered gun pointing down-back along a hanging arm makes that fit degenerate - Pearl's arm flipped 100-180 deg a frame and sank 0.3-0.47 into the torso while Onyx (hand-only arm) was fine; arm_edge null did NOT help (with a blade the solver then fits the barrel alone). Fix (kit pose_r6): a key's right_arm "arm_twist": false - the arm takes its natural swing, the gun still turns in the fist from the key's blade/edge; switch back to fitted where the two agree (measure natural vs fitted per key offline with solve_arm: the hip draw's frame 18 at 7 deg, the holster's start at 5). Also: frame_toward's vertical-barrel fallback flips the gun's top 180 deg - never key a barrel exactly vertical; Pearl's grip is held 0.25 from the fist (the pistol 'hold') - shift its holster hand targets so both grips land on the seat.
