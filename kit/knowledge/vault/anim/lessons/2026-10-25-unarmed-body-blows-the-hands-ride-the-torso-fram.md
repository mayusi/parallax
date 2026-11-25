---
kind: lesson
area: anim
date: 2026-10-25
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Unarmed body blows: the hands ride the TORSO frame (key rhand/lhand as torso offsets placed by the body's pos/yaw/pitch) or the guard drifts off the body as it turns; steps, lifts, root motion and hip_shift live in the move's FEET track (strike.py ignores *_lift on arm keys); a forward-pointing R6 arm's top clips the chest corner when the torso turns side-on - the lead fist in front of its own shoulder (x ~ -0.85) clears it (17-18 %), a fist pulled toward the midline sank 22 %; R6 legs need leg_twist_follow ~0.6 under a side-on torso or they read crossed
