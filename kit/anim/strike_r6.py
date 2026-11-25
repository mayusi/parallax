"""strike_r6.py — AUTHORED R6 strikes on the owner's rig from the craft rules the fresh-judge loop proved.

    python kit/anim/strike_r6.py <jab|cross|hook|uppercut> --as <Name> [--out <path>]

Why (2026-10-11): a cross punch keyed from scratch climbed from 3.5 to 4.5 / 10 over seven fresh judgings (the owner-
loved sprint: 4.0 on the same prompt), while moves edited from a pack plateaued at 3.2-3.8. What moved it is written
here as structure, so every strike starts from it:
- ONE GUARD for the set (bladed stance, left foot forward, both arms raised forward) - every strike starts and ends
  there, so they chain without a pop;
- ARMS TORSO-RELATIVE (swing / out / slide): root-relative hand targets cross the chest when the torso turns;
- the beat: guard -> anticipation start -> COIL (the torso turns further AWAY than the guard, the weight back, the
  striking arm slid back - the R6 elbow) -> a HIP-LEAD breakdown (the torso already turning while the fist is still
  back) -> the HIT on the fastest frame AND at full reach -> a 2-frame OVERSHOOT -> the torso home before the arm
  -> the guard;
- the striking arm level with the shoulder at the Hit (its swing adds the lean back), lean <= ~15;
- R6 HAS NO WAIST: the torso is the hips, so the total turn stays ~45 deg (more swings both legs: a whole-body snap);
- the off-hand slides home as the strike fires; the head dips into the Hit and settles last (head offset);
- on a STRIKE the head FOLLOWS ~70% of the torso's turn (judged twice: a head holding its world facing while the torso
  turns 50 deg reads as a twisted neck) - the rig's head ignores the body's turn, so its look is keyed from the turn;
- IK feet planted.
Each kind is a table of those beats; `kit anim <Name>` bakes it on the rig, `kit anim judge` judges it."""
import json
import os
import sys

FEET = {"right_foot": {"at": [0.6, -0.6], "lift": 0, "turn": 30}, "left_foot": {"at": [-0.45, 0.7], "lift": 0, "turn": 5}}


def A(sw, out, sl=(0, 0, 0)):
    return {"swing": sw, "out": out, "twist": 0, "slide": list(sl)}


GUARD_BODY = {"pos": [0, -0.25, 0], "lean": 8, "turn": 25, "tilt": 0}
GUARD_R, GUARD_L = A(118, -4), A(105, -6, (0, 0, 0.1))
GUARD_HEAD = {"look": [0, -0.05, 1]}

# per kind: the frames of the beats, the body at each, the striking arm at each, the off-hand at the Hit, the head
KINDS = {
    "cross": {
        "arm": "right_arm", "off": "left_arm", "frames": [6, 9, 11, 13, 15, 17, 22, 30],
        "body": [((0.05, -0.3, -0.05), 5, 32, 2), ((0.08, -0.33, -0.1), 3, 38, 3), ((-0.02, -0.32, 0.06), 9, 22, 0),
                 ((-0.1, -0.33, 0.14), 13, -8, -4), ((-0.12, -0.34, 0.16), 14, -14, -5), ((-0.07, -0.34, 0.1), 12, -4, -3),
                 ((-0.03, -0.31, 0.05), 10, 10, -1), ((0, -0.23, 0), 7, 22, 0)],
        "strike": [A(98, 10, (0, 0, -0.3)), A(97, 12, (0, 0, -0.42)), A(100, 4, (0, 0, -0.1)), A(103, -14, (0, -0.02, 0.55)),
                   A(101, -17, (0, -0.03, 0.6)), A(104, -12, (0, -0.02, 0.32)), A(110, -6, (0, 0, 0.12)), A(114, -3)],
        "off_hit": A(96, 6, (0, -0.05, -0.2)),
    },
    "jab": {                                          # the lead (left) hand: quick, little turn, the rear hand guards
        "arm": "left_arm", "off": "right_arm", "frames": [3, 5, 7, 8, 10, 13, 18, 26],
        "body": [((0.02, -0.28, -0.03), 7, 18, 1), ((0.05, -0.31, -0.07), 6, 12, 2), ((0.0, -0.3, 0.04), 9, 24, 0),
                 ((-0.06, -0.31, 0.12), 12, 38, -2), ((-0.07, -0.31, 0.13), 12, 41, -2), ((-0.05, -0.3, 0.09), 11, 36, -1),
                 ((-0.02, -0.27, 0.03), 9, 28, 0), ((0, -0.24, 0), 8, 25, 0)],
        "strike": [A(92, 6, (0, -0.05, -0.25)), A(86, 8, (0, -0.1, -0.42)), A(96, 2, (0, -0.04, -0.05)), A(102, -6, (0, -0.02, 0.62)),
                   A(101, -8, (0, -0.02, 0.68)), A(103, -7, (0, -0.01, 0.3)), A(104, -6, (0, 0, 0.14)), A(105, -6, (0, 0, 0.1))],
        "off_hit": A(120, -6, (0, 0, -0.05)),
    },
    "hook": {                                         # the rear hand sweeps a horizontal arc from out wide to across
        "arm": "right_arm", "off": "left_arm", "frames": [6, 9, 11, 13, 15, 17, 22, 30],
        "body": [((0.05, -0.31, -0.05), 6, 36, 4), ((0.09, -0.36, -0.1), 4, 44, 8), ((0.0, -0.35, 0.03), 8, 30, 3),
                 ((-0.08, -0.35, 0.1), 12, -6, -8), ((-0.09, -0.36, 0.11), 13, -10, -9), ((-0.06, -0.34, 0.08), 11, 0, -5),
                 ((-0.02, -0.3, 0.03), 9, 10, -2), ((0, -0.23, 0), 7, 22, 0)],
        "strike": [A(98, 40, (0, -0.05, -0.15)), A(94, 60, (0, -0.1, -0.08)), A(98, 72, (0, 0, 0.32)), A(106, -20, (0, 0, 0.48)),
                   A(105, -30, (0, 0, 0.38)), A(103, -16, (0, 0, 0.22)), A(108, -8, (0, 0, 0.12)), A(114, -3)],
        "off_hit": A(98, 4, (0, -0.05, -0.15)),
    },
    "uppercut": {                                     # dip and load low, rise THROUGH the strike (the legs push)
        "arm": "right_arm", "off": "left_arm", "frames": [6, 9, 11, 13, 15, 17, 22, 30],
        "body": [((0.06, -0.4, -0.04), 12, 31, 6), ((0.1, -0.5, -0.06), 15, 36, 9), ((0.02, -0.42, 0.03), 13, 22, 3),
                 ((-0.06, -0.22, 0.14), 15, -6, -3), ((-0.07, -0.2, 0.15), 14, -10, -4), ((-0.04, -0.24, 0.09), 11, -2, -2),
                 ((-0.02, -0.26, 0.03), 7, 12, -1), ((0, -0.23, 0), 7, 22, 0)],
        "strike": [A(70, 10, (0, -0.1, -0.2)), A(52, 12, (0, -0.15, -0.3)), A(96, 4, (0, -0.02, 0.05)), A(158, -14, (0, 0.06, 0.38)),
                   A(164, -16, (0, 0.08, 0.4)), A(150, -12, (0, 0.05, 0.32)), A(128, -6, (0, 0, 0.1)), A(114, -3)],
        "off_hit": A(72, 10, (0, -0.1, -0.35)),
    },
    # DEFENCE / REACTION kinds on the same guard and beats (the "Hit" event is renamed by "event")
    "slip": {                                         # off the line: a counter-shift, a fast deep side-bend held, home
        "arm": "right_arm", "off": "left_arm", "frames": [3, 6, 8, 11, 13, 17, 23, 31], "event": "Dodge", "event_beat": 2,
        "head_follow": 1.0,
        "body": [((0.06, -0.3, 0.0), 8, 28, 5), ((-0.18, -0.6, 0.04), 13, 18, -18), ((-0.26, -0.74, 0.05), 15, 15, -24),
                 ((-0.27, -0.76, 0.05), 15, 15, -25), ((-0.24, -0.7, 0.05), 14, 16, -21), ((-0.12, -0.48, 0.03), 11, 20, -10),
                 ((-0.03, -0.3, 0.01), 9, 24, -2), ((0, -0.25, 0), 8, 25, 0)],
        "strike": [A(118, -4), A(122, -8, (0, 0, 0.05)), A(124, -10, (0, 0, 0.08)), A(124, -10, (0, 0, 0.08)), A(123, -9, (0, 0, 0.07)),
                   A(121, -7, (0, 0, 0.04)), A(119, -5), A(118, -4)],
        "off_hit": A(110, -10, (0, 0, 0.14)),
    },
    "block": {                                        # both forearms up ACROSS the face, held, a knock-back jolt, ease out
        "arm": "right_arm", "off": "left_arm", "frames": [2, 4, 5, 8, 10, 16, 22, 30], "event_beat": 2, "event": "Block",
        "body": [((0, -0.29, -0.03), 9, 22, 0), ((0, -0.34, -0.07), 4, 20, 0), ((0, -0.36, -0.09), 2, 19, 0),
                 ((0, -0.37, -0.13), -2, 21, 1), ((0, -0.36, -0.1), 1, 20, 0), ((0, -0.35, -0.08), 2, 19, 0),
                 ((0, -0.3, -0.03), 6, 23, 0), ((0, -0.25, 0), 8, 25, 0)],
        "strike": [A(130, -14), A(150, -30, (0, 0, 0.15)), A(154, -34, (0, 0, 0.18)), A(152, -32, (0, 0, 0.12)),
                   A(154, -34, (0, 0, 0.18)), A(152, -33, (0, 0, 0.17)), A(130, -12), A(118, -4)],
        "off_hit": A(150, -32, (0, 0, 0.22)), "off_coil": A(140, -24, (0, 0, 0.18)),
    },
    "hit_react": {                                    # hold the guard, the HEAD snaps back first (chin up), the torso follows
        "arm": "right_arm", "off": "left_arm", "frames": [5, 6, 8, 11, 15, 19, 26, 36], "event": "Impact", "event_beat": 2,
        "body": [((0, -0.25, 0), 8, 25, 0), ((0, -0.25, -0.03), 6, 26, 1), ((0.02, -0.28, -0.12), -4, 31, 5),
                 ((0.04, -0.34, -0.24), -12, 35, 9), ((0.04, -0.36, -0.26), -13, 36, 9), ((0.02, -0.33, -0.16), -6, 32, 6),
                 ((0, -0.28, -0.05), 4, 27, 2), ((0, -0.25, 0), 8, 25, 0)],
        "strike": [A(118, -4), A(116, 2), A(104, 14, (0, 0, -0.15)), A(92, 24, (0, -0.05, -0.25)), A(90, 26, (0, -0.05, -0.26)),
                   A(98, 18, (0, 0, -0.2)), A(112, 4, (0, 0, -0.05)), A(118, -4)],
        "off_hit": A(102, 12, (0, 0, -0.1)), "off_coil": A(105, -6, (0, 0, 0.1)),
        # the head: still, then thrown back and up BEFORE the torso, held through the stagger, home last
        "head": [[0, -0.05, 1], [0, 0.35, 1], [0.08, 0.7, 1], [0.1, 0.55, 1], [0.08, 0.45, 1], [0.04, 0.25, 1], [0, 0.05, 1], [0, -0.05, 1]],
    },
}


# WEAPON strikes - EXPERIMENTAL (2026-10-11): on R6 a tool is WELDED to the fist (RightGrip), so with rigid arms the
# hand's place and the blade's direction are coupled: locking the blade leaves the hand ~1 stud off its target and the
# two-handed arms cross the torso / face (gs_diagonal clipped 17+ frames); locking the hand turns the blade 20-67 deg
# off. A greatsword set that reads well needs an ANIMATABLE GRIP (the sword on its own Motor6D, keyed like a limb) -
# a game-setup decision for the owner. Kept so that work starts here.
# WEAPON strikes: the right hand + the BLADE direction (exact: the blade leaves the fist at the grip's angle) and the
# left hand on the hilt every frame (kit/anim/pose_r6.py). Same beats as the fists, a heavier tempo.
GS_SWORD = {"blade": 4.0, "grip_pitch": 60, "spacing": 0.55, "grip": "animated"}
GS_GUARD = {"body": {"pos": [0, -0.45, 0], "lean": 10, "turn": 25, "tilt": -3},
            "right_arm": {"hand": [0.35, 2.35, 1.4], "blade": [-0.05, 0.42, 0.9]}}
GS_FEET = {"right_foot": {"at": [0.85, -0.55], "lift": 0, "turn": 35}, "left_foot": {"at": [-0.55, 0.75], "lift": 0, "turn": 5}}
WEAPON_KINDS = {
    # WIP (2026-10-11): first judged 3.7; blade + hands exact via the animated grip, the cut now the fastest motion; the
    # follow-through still clips (the right arm past the face 11 f, the left arm across the torso on the return) -
    # two-handed R6 geometry under a 16 deg lean: next, place the hands torso-relative and lean less in the finish
    "gs_diagonal": {                                  # a two-handed diagonal: high over the right shoulder, down across to the
        # left hip, HELD (the weight of the blade), then a slow return - judged: the recovery must never outrun the cut
        "frames": [6, 11, 14, 19, 25, 28, 38, 52], "event_shift": 2,
        # the off-hand lets go AFTER the Hit (the sweep's judged fix): a counterweight out low behind, re-gripping for
        # the return - two hands held on the hilt through the finish folded rigid R6 arms across the chest
        "left": {4: {"swing": 5, "out": 28, "twist": 0, "slide": [0, 0, -0.05]}, 5: {"swing": -8, "out": 30, "twist": 0, "slide": [0, 0, -0.08]},
                 6: "hilt"},
        "body": [((0, -0.46, -0.08), 5, 38, -5), ((0, -0.5, -0.16), 0, 50, -8), ((0, -0.52, -0.02), 8, 32, -3),
                 ((0, -0.64, 0.22), 13, 2, 3), ((0, -0.68, 0.26), 15, -10, 5), ((0, -0.71, 0.27), 17, -15, 6),
                 ((0, -0.54, 0.1), 11, 12, 1), ((0, -0.45, 0), 10, 25, -3)],
        "hand_local": [(1.1, 0.7, 0.9), (1.4, 1.0, 0.35), (1.2, 0.85, 0.85), (-0.15, -0.25, 1.95), (-1.35, -0.95, 1.15),
                       (-1.45, -1.05, 1.0), (-1.0, -0.85, 1.35), (-0.15, -0.6, 1.5)],
        "blade": [(0.15, 0.95, -0.1), (0.25, 0.75, -0.6), (0.2, 0.95, -0.25), (-0.6, -0.25, 0.75), (-0.55, -0.83, -0.05),
                  (-0.5, -0.85, -0.15), (-0.3, 0.1, 0.95), (-0.05, 0.42, 0.9)],
        # the WEIGHT: the front foot steps into a lunge on the cut (lifted mid-step), held low, then back to the guard
        "feet": {2: {"left_foot": {"at": [-0.55, 0.95], "lift": 0.18, "turn": 5}},
                 3: {"left_foot": {"at": [-0.6, 1.3], "lift": 0, "turn": 0}},
                 6: {"left_foot": {"at": [-0.6, 1.3], "lift": 0, "turn": 0}},
                 7: {"left_foot": {"at": [-0.55, 0.75], "lift": 0, "turn": 5}}},
    },
}


WEAPON_KINDS["gs_horizontal"] = {                    # a flat sweep right -> left at chest height, the body turning through
    "frames": [8, 15, 18, 23, 29, 32, 42, 56], "event_shift": 1,
    "body": [((0, -0.5, -0.06), 6, 40, -3), ((0, -0.56, -0.14), 3, 52, -5), ((0, -0.57, -0.06), 6, 47, -4),
             ((0, -0.66, 0.22), 12, 2, 2), ((0, -0.68, 0.25), 13, -14, 3), ((0, -0.7, 0.26), 14, -20, 3),
             ((0, -0.55, 0.1), 11, 8, 0), ((0, -0.45, 0), 10, 25, -3)],
    "hand_local": [(1.2, 0.25, 0.8), (1.6, 0.2, 0.0), (1.5, 0.15, 0.7), (0.2, 0.0, 2.25), (-1.7, -0.1, 1.2),
                   (-1.55, -0.1, 1.45), (-0.9, -0.4, 1.55), (-0.15, -0.6, 1.5)],
    # the off-hand LETS GO for the wide sweep (two hands across the body fold rigid R6 arms and the hilt runs out of
    # reach): flung out behind for balance through the cut, back on the hilt for the return
    "left": {1: {"swing": 92, "out": 14, "twist": 0, "slide": [0, 0, 0.08]}, 2: {"swing": 82, "out": 26, "twist": 0, "slide": [0, 0, 0.04]},
             3: {"swing": 68, "out": 40, "twist": 0, "slide": [0, 0, 0]},
             4: {"swing": 50, "out": 52, "twist": 0, "slide": [0, 0, 0]}, 5: {"swing": 52, "out": 48, "twist": 0, "slide": [0, 0, 0]},
             6: "hilt"},
    "blade": [(0.75, 0.25, -0.6), (0.85, 0.15, -0.5), (0.6, 0.1, 0.8), (-0.3, 0.05, 0.95), (-0.95, 0.0, 0.3),
              (-0.95, -0.05, 0.25), (-0.3, 0.1, 0.95), (-0.05, 0.42, 0.9)],
    "feet": {2: {"left_foot": {"at": [-0.55, 0.95], "lift": 0.16, "turn": 5}}, 3: {"left_foot": {"at": [-0.6, 1.25], "lift": 0, "turn": 0}},
             6: {"left_foot": {"at": [-0.6, 1.25], "lift": 0, "turn": 0}}, 7: {"left_foot": {"at": [-0.55, 0.75], "lift": 0, "turn": 5}}},
}
WEAPON_KINDS["gs_overhead"] = {
    "head_pitch": [0.05, 0.18, 0.15, -0.25, -0.3, -0.28, -0.12, -0.05],                      # the heaviest: hands up BEHIND the crown, leaning back, then a chop
    # down the centre that is already below level ON the Hit, the torso pitched over a deep lunge; a drifting finish
    "frames": [7, 13, 16, 21, 27, 30, 40, 54], "event_shift": -1,
    # the off-hand lets go AFTER the Hit (the sweep's judged fix): a counterweight out low behind, re-gripping for
    # the return - two hands held on the hilt through the finish folded rigid R6 arms across the chest
    "left": {4: {"swing": 35, "out": 55, "twist": 0, "slide": [0, 0, 0]}, 5: {"swing": 30, "out": 58, "twist": 0, "slide": [0, 0, 0]},
         6: "hilt"},
    "body": [((0, -0.42, -0.1), -2, 30, -2), ((0, -0.4, -0.22), -15, 28, -2), ((0, -0.46, -0.1), -8, 26, -1),
             ((0, -0.74, 0.3), 25, 18, 1), ((0, -0.78, 0.33), 27, 16, 1), ((0, -0.8, 0.34), 29, 15, 1),
             ((0, -0.56, 0.12), 14, 22, -1), ((0, -0.45, 0), 10, 25, -3)],
    "hand_local": [(0.55, 1.2, 0.6), (0.4, 2.2, -0.2), (0.35, 2.1, 0.3), (0.1, -0.6, 1.85), (0.0, -1.05, 1.55),
                   (0.0, -1.05, 1.55), (-0.35, -0.7, 1.6), (-0.15, -0.6, 1.5)],
    "blade": [(0.05, 0.8, -0.6), (0.0, 0.2, -0.98), (0.02, 0.45, -0.89), (0.0, -0.6, 0.8), (0.0, -0.95, 0.3),
              (0.0, -0.92, 0.38), (-0.25, 0.1, 0.95), (-0.05, 0.42, 0.9)],
    "feet": {1: {"right_foot": {"at": [0.9, -0.75], "lift": 0, "turn": 35}},
             2: {"left_foot": {"at": [-0.55, 1.0], "lift": 0.2, "turn": 5}}, 3: {"left_foot": {"at": [-0.6, 1.45], "lift": 0, "turn": 0}},
             6: {"left_foot": {"at": [-0.6, 1.45], "lift": 0, "turn": 0}},
             7: {"left_foot": {"at": [-0.55, 0.75], "lift": 0, "turn": 5}, "right_foot": {"at": [0.85, -0.55], "lift": 0, "turn": 35}}},
}


# a two-handed BLOCK: the blade up FLAT across the face, the off-hand braced on the flat (on_blade - the hilt hand alone
# cannot hold a greatsword against a hit, and two hands on the hilt fold rigid R6 arms across the chest), squared to
# the attacker, the knees giving on the knock-back, held, then down to the guard. "Block" = the blade is up
WEAPON_KINDS["gs_block"] = {
    "about": "an AUTHORED R6 greatsword block (kit/anim/strike_r6.py): the blade up flat across the face, the off-hand braced on the flat, squared to the attacker, a knock-back with the knees giving, held, down to the guard",
    "frames": [3, 7, 9, 12, 15, 22, 32, 44], "event": "Block", "event_beat": 2,
    "eases": ["sine_inout", "quad_out", "sine_inout", "quad_out", "sine_inout", "sine_inout", "sine_inout", "sine_inout"],
    "head_pitch": [-0.08, -0.14, -0.15, -0.12, -0.13, -0.14, -0.08, -0.05],      # the chin tucked behind the blade
    "body": [((0, -0.5, -0.04), 8, 18, -2), ((0, -0.56, -0.08), 4, 10, 0), ((0, -0.58, -0.1), 3, 8, 0),
             ((0, -0.66, -0.2), -1, 9, 1), ((0, -0.62, -0.16), 1, 8, 0), ((0, -0.6, -0.14), 2, 8, 0),
             ((0, -0.52, -0.06), 7, 18, -2), ((0, -0.45, 0), 10, 25, -3)],
    "hand_local": [(0.4, 0.2, 1.3), (0.9, 1.3, 0.75), (0.9, 1.35, 0.75), (0.95, 1.2, 0.6), (0.9, 1.28, 0.7),
                   (0.9, 1.28, 0.7), (0.3, 0.1, 1.35), (-0.15, -0.6, 1.5)],
    "blade": [(-0.3, 0.75, 0.55), (-0.95, 0.15, 0.25), (-0.95, 0.12, 0.27), (-0.94, 0.2, 0.2), (-0.95, 0.14, 0.25),
              (-0.95, 0.14, 0.25), (-0.3, 0.6, 0.75), (-0.05, 0.42, 0.9)],
    "left": {1: {"on_blade": 1.5}, 2: {"on_blade": 1.5}, 3: {"on_blade": 1.45}, 4: {"on_blade": 1.5}, 5: {"on_blade": 1.5}, 6: "hilt"},
    # braced: the back foot pushes out wider for the knock-back
    "feet": {3: {"right_foot": {"at": [0.95, -0.7], "lift": 0, "turn": 35}}, 7: {"right_foot": {"at": [0.85, -0.55], "lift": 0, "turn": 35}}},
}


# a HIT REACTION holding the greatsword: the head snaps back FIRST (no head drag - it leads), the torso thrown back
# and turned by the blow, the hands kept on the hilt but jolted up (the blade tips back), a slow recovery to the guard
WEAPON_KINDS["gs_hit_react"] = {
    "about": "an AUTHORED R6 greatsword hit reaction (kit/anim/strike_r6.py): the head snaps back first, the torso thrown back and turned, the hands on the hilt jolted up, a slow recovery to the guard",
    "frames": [4, 6, 8, 12, 17, 22, 30, 42], "event": "Impact", "event_beat": 2, "offsets": {},
    "eases": ["sine_inout", "quad_out", "quad_out", "sine_out", "sine_inout", "sine_inout", "sine_inout", "sine_inout"],
    "head_pitch": [-0.05, 0.12, 0.32, 0.22, 0.06, -0.01, -0.04, -0.05],
    "body": [((0, -0.45, 0), 10, 25, -3), ((0, -0.43, -0.12), 4, 30, 2), ((0, -0.45, -0.24), -6, 36, 4),
             ((0, -0.52, -0.3), -8, 38, 5), ((0, -0.55, -0.25), -2, 34, 3), ((0, -0.52, -0.15), 4, 30, 0),
             ((0, -0.48, -0.05), 8, 27, -2), ((0, -0.45, 0), 10, 25, -3)],
    "hand_local": [(-0.15, -0.6, 1.5), (-0.1, -0.45, 1.4), (0.0, -0.3, 1.25), (0.05, -0.35, 1.2), (0.0, -0.5, 1.3),
                   (-0.08, -0.55, 1.4), (-0.12, -0.58, 1.47), (-0.15, -0.6, 1.5)],
    "blade": [(-0.05, 0.42, 0.9), (0.0, 0.55, 0.83), (0.1, 0.7, 0.7), (0.12, 0.72, 0.68), (0.05, 0.6, 0.8),
              (0.0, 0.5, 0.86), (-0.03, 0.45, 0.89), (-0.05, 0.42, 0.9)],
}


def torso_frame(body):
    """stage-space rotation of the torso for a body key (turn + = to the right, lean + = forward) and its centre"""
    import math
    t, l = math.radians(body.get("turn", 0)), math.radians(body.get("lean", 0))
    Ry = [[math.cos(t), 0, math.sin(t)], [0, 1, 0], [-math.sin(t), 0, math.cos(t)]]
    Rx = [[1, 0, 0], [0, math.cos(l), -math.sin(l)], [0, math.sin(l), math.cos(l)]]
    Rm = [[sum(Ry[i][k] * Rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    pos = body.get("pos", [0, 0, 0])
    return Rm, (pos[0], 3.0 + pos[1], pos[2])


def to_world(body, local):
    Rm, c = torso_frame(body)
    return [round(c[i] + sum(Rm[i][j] * local[j] for j in range(3)), 3) for i in range(3)]


def build_weapon(kind, name):
    import math
    K = WEAPON_KINDS[kind]
    f = K["frames"]
    guard_arm = dict(GS_GUARD["right_arm"])
    if K.get("hand_local"):
        guard_arm["hand"] = to_world(GS_GUARD["body"], K["hand_local"][-1])
    keys = [dict({"f": 0, "ease": "sine_inout", "body": dict(GS_GUARD["body"]), "head": {"look": [0, -0.05, 1]},
                  "right_arm": guard_arm, "left_arm": "hilt"}, **GS_FEET)]
    eases = ["sine_inout", "quad_in", "linear", "quad_out", "sine_inout", "sine_inout", "sine_inout", "sine_inout"]
    eases = K.get("eases", eases)
    for i, fr in enumerate(f):
        pos, lean, turn, tilt = K["body"][i]
        yaw = math.radians(0.5 * (turn - GS_GUARD["body"]["turn"]))
        keys.append({"f": fr, "ease": eases[i], "body": {"pos": list(pos), "lean": lean, "turn": turn, "tilt": tilt},
                     "head": {"look": [round(math.sin(yaw), 4), K["head_pitch"][i] if K.get("head_pitch") else (-0.14 if i == 3 else -0.06),
                                       round(math.cos(yaw), 4)]},
                     "right_arm": {"hand": to_world({"pos": list(pos), "lean": lean, "turn": turn}, K["hand_local"][i])
                                   if K.get("hand_local") else list(K["hand"][i]), "blade": list(K["blade"][i])}})
        keys[-1].update(K.get("feet", {}).get(i, {}))
        if i in K.get("left", {}):
            keys[-1]["left_arm"] = K["left"][i]
    keys.append(dict(keys[-1], f=f[-1] + 4))
    return {"name": name, "axes": "stage: x right, y up from the floor, z forward (the character stands at the origin facing +z)",
            "note": K.get("about") or f"an AUTHORED R6 greatsword {kind} from the judged craft rules (kit/anim/strike_r6.py): the guard, a coil over the shoulder, the torso leading while the blade is still up, the Hit on the fastest frame, a 2-frame overshoot, the torso home before the blade, R6 has no waist (turn ~50), the head follows half the turn, the left hand on the hilt",
            "fps": 60, "loop": False, "priority": "Action", "sword": dict(GS_SWORD), "events": [{"name": K.get("event", "Hit"), "f": f[K.get("event_beat", 3)] + K.get("event_shift", 0)}],
            "offsets": K.get("offsets", {"head": 3}), "strike": {"kind": kind, "tool": "kit/anim/strike_r6.py"}, "keys": keys}


def build(kind, name):
    K = KINDS[kind]
    f = K["frames"]
    keys = [dict({"f": 0, "ease": "sine_inout", "body": dict(GUARD_BODY), "head": dict(GUARD_HEAD),
                  "right_arm": GUARD_R, "left_arm": GUARD_L}, **FEET)]
    eases = ["sine_inout", "quad_in", "linear", "quad_out", "sine_inout", "sine_inout", "sine_inout", "sine_inout"]
    for i, fr in enumerate(f):
        pos, lean, turn, tilt = K["body"][i]
        k = {"f": fr, "ease": eases[i], "body": {"pos": list(pos), "lean": lean, "turn": turn, "tilt": tilt}, K["arm"]: K["strike"][i]}
        if i == 1:
            k[K["off"]] = K.get("off_coil") or (A(100, -4, (0, 0, 0.22)) if K["off"] == "left_arm" else A(118, -6, (0, 0, 0.0)))
            k["head"] = {"look": [0.03, -0.05, 1]}
        if i == 3:
            k[K["off"]] = K["off_hit"]
            k["head"] = {"look": [-0.05, -0.14, 1]}
        if i == 6:
            k[K["off"]] = GUARD_L if K["off"] == "left_arm" else GUARD_R
            k["head"] = {"look": [-0.02, -0.08, 1]}
        if i == 7:
            k["right_arm"], k["left_arm"], k["head"] = GUARD_R, GUARD_L, dict(GUARD_HEAD)
            k["body"] = dict(GUARD_BODY)
        keys.append(k)
    import math
    pitch = {0: -0.05, 1: -0.05, 3: -0.14, 4: -0.12, 6: -0.08}
    for i, k in enumerate(keys):
        if i == 0:
            continue
        if K.get("head"):                              # a reaction keys its own head (thrown back first)
            k["head"] = {"look": list(K["head"][i - 1])}
            continue
        yaw = math.radians(K.get("head_follow", 0.7) * (k["body"]["turn"] - GUARD_BODY["turn"]))
        # a full follow also takes the torso's side-bend: the head leaves the centre line with it
        side = math.radians(k["body"].get("tilt", 0)) * (K.get("head_follow", 0.7) if K.get("head_follow", 0.7) >= 1 else 0)
        k["head"] = {"look": [round(math.sin(yaw), 4), pitch.get(i - 1, -0.06), round(math.cos(yaw), 4)], "tilt": round(math.degrees(side), 1)}
    hold = dict(keys[-1], f=f[-1] + 4)
    keys.append(hold)
    return {"name": name, "axes": "stage: x right, y up from the floor, z forward (the character stands at the origin facing +z)",
            "note": f"an AUTHORED R6 {kind} from the judged craft rules (kit/anim/strike_r6.py): one guard, coil away, hip-lead breakdown, the Hit on the fastest frame at full reach, a 2-frame overshoot, the torso home before the arm, R6 has no waist (turn ~45 deg)",
            "fps": 60, "loop": False, "priority": "Action", "events": [{"name": K.get("event", "Hit"), "f": f[K.get("event_beat", 3)]}], "offsets": {"head": 3},
            "strike": {"kind": kind, "tool": "kit/anim/strike_r6.py"}, "keys": keys}


def main(argv):
    if not argv or (argv[0] not in KINDS and argv[0] not in WEAPON_KINDS) or "--as" not in argv:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"strike_r6: needs <{'|'.join(list(KINDS) + list(WEAPON_KINDS))}> --as <Name>",
                          "next_action": "lune run kit anim new CraftJab --strike jab"}))
        return 1
    kind, name = argv[0], argv[argv.index("--as") + 1]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("assets", "animations", f"{name}.pose.json")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        json.dump(build_weapon(kind, name) if kind in WEAPON_KINDS else build(kind, name), fh, indent=1)
        fh.write(chr(10))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"strike_r6 {name}: an authored {kind} -> {out}",
                      "next_action": f"lune run kit anim {name} && lune run kit anim judge {name} --rig R6"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
