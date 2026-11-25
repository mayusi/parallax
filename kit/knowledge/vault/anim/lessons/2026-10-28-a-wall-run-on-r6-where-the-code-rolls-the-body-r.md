---
kind: lesson
area: anim
date: 2026-10-28
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A wall run on R6 where the CODE rolls the body (RootJoint.C0) away from the wall: author the clip upright in root space and solve each foot onto the wall plane x*cos(roll) - y*sin(roll) = D against the leg BOX corners (1 stud wide), not the sole centre. D = 3*sin(roll) buries the wall-side thigh; at 30 deg D 1.85 works. Re-solve the touch at the foot's own z every frame, and swing the air foot AWAY from the wall: on a 60-deg plane a lift alone clears it by only ~0.2 (gen_wallrun.py, play-proven 10-28: deepest corner -0.007)
