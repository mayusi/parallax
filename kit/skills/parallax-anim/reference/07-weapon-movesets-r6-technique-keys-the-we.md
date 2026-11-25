<!-- reference for the parallax-anim route card; verbatim from the skill page (2026-10-16) -->

## Weapon movesets (R6, technique keys, the weapon's weight in the timing)
`assets/animations/<Name>.move.json` → `kit anim` runs kit/anim/strike.py → an R6-native clip (`rig: "R6"`, compiled,
stripped, gated like any other). The author writes what a swordsman DOES at each key, in character space (x right,
y up, -z forward): `grip` (the two hands' midpoint), `dir` (where the blade points), `yaw`/`pitch`/`roll` + `pos`
(the torso; +pitch leans BACK), `right`/`left` (where each foot stands; `right_h`/`left_h` > 0 = hovering mid-step),
`weight` (right / left / both: the leg the pelvis rides on), `look_yaw`/`look_pitch`, `ease` toward the next key
(In = a wind-up gathering speed, Strike = fastest at once then braking, Out, InOut), `overshoot` + `settle` (the
follow-through: past the key and back). `sword: {length, grip}`, `lag` (the steel trails the body). The generator
solves both one-piece arms onto the hilt (the grip moves the least amount both can reach; the arm boxes face the
hilt, turning at most ~30° a frame), the pelvis onto the weight-bearing leg (the other planted leg slides up into the
torso; a stepping foot lifts before it travels and arrives before it touches), the head against the torso, and
places the Hit one frame after the BLADE TIP is fastest (the metrics add the tip as an effector when a clip carries
`sword.tip`). The look render draws the blade. Greatsword set: GreatswordGuard (vom Tag idle), GreatswordLight1
(Zornhau, right foot passing), GreatswordLight2 (the return cut, left foot passing), GreatswordHeavy (Oberhau with a
lunge, the blade carried to the floor, a slow lift), GreatswordThrust (from Pflug). An R6 arm reaches 1.58 studs from
its shoulder pivot: a grip further than that is pulled back, so extension comes from the torso's lean and lunge.
