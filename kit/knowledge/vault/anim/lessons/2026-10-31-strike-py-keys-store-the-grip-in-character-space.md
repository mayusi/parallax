---
kind: lesson
area: anim
date: 2026-10-31
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

strike.py keys store the GRIP in character space and interpolate it in a straight line: a full-body spin keyed every ~100 deg of yaw cut the chord through the torso (arm 40 % in the body). Key a turn every <= 30 deg (gen_swift.py spin_keys) - and a foot-track key that sets right_h/left_h (a hop) CARRIES them to every later key: reset right_h=left_h=0 on the landing key or the feet stay 'in the air' (legs tucked 0.78 at the end, a 16-20 deg leg pop at the next step)
