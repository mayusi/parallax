"""build_rig.py — fixtures for A MODEL'S OWN RIG, SOLVED (a.reach, a.couple, rbx_ik; the 3D methods audit, stage R).
By the word after `--`:
  (none)   an arm on a base: a boom on a shoulder hinge, a forearm on an elbow hinge, a hand on a wrist that
           follows the elbow backwards (a.couple) - with two named places for its tip, both within reach. The
           build must solve both (`reach` holds), say the chain, and write the poses and the wrist's `follows` to
           the manifest. After the build `RIG {json}`.
  far      the same arm asked to put its tip 9 studs away: `reach` must FAIL and say the chain is too short
           (build_rig_far.py).
  order    the chain's joints listed tip first: the build must STOP and say which carries which
           (build_rig_order.py).
  fold     a bollard beside the base and a pose that swings the arm out and folds the forearm down: each joint's
           own travel is clear of it, but posed together the forearm comes down through the bollard -
           `reach_clear` must FAIL by the chain's and the pose's name (build_rig_fold.py; stage P).
Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("far", "order", "fold") if w in ARGS), "good")
Z = 0.35 if HOW == "fold" else 0.7   # (fold: the forearm in the upper arm's plane)

a = rbx.Asset("_selftest_rig_" + HOW, tex=64, size=(2.8, 5.45, 1.45) if HOW == "fold" else (1.2, 5.45, 1.8),
              ground=True, allow_floating=("Base", "Post", "Boom", "Fore", "Hand", "Bollard"))   # (an arm's links hang on their joints, clear
#                                                             of each other and of the base: held by the joints)
a.material("steel", color=(0.5, 0.52, 0.55), metal=1.0, rough=0.4)
a.box("Base", (1.2, 0.9, 1.2), (0, 0.45, 0), "steel", bevel=0)
a.box("Post", (0.3, 0.5, 0.3), (0, 1.1, 0), "steel", bevel=0)
a.box("Boom", (0.3, 2.0, 0.3), (0, 2.3, 0.35), "steel", bevel=0, group="boom")
a.box("Fore", (0.3, 2.0, 0.3), (0, 4.3, Z), "steel", bevel=0, group="fore")
a.box("Hand", (0.5, 0.3, 0.3), (0, 5.3, Z + 0.35), "steel", bevel=0, group="hand")
a.joint("Shoulder", "boom", "hinge", axis=(0, 0, 1), pivot=(0, 1.3, 0.35), min=-100, max=100)
a.joint("Elbow", "fore", "hinge", axis=(0, 0, 1), pivot=(0, 3.3, Z), min=-140, max=140, parent="boom")
a.joint("Wrist", "hand", "hinge", axis=(0, 0, 1), pivot=(0, 5.3, Z + 0.35), min=-140, max=140, parent="fore")
a.couple("Wrist", drives="Elbow", ratio=-1.0)
chain = ["Elbow", "Shoulder"] if HOW == "order" else ["Shoulder", "Elbow"]
if HOW == "fold":   # (a bollard beside the base: each joint alone swings clear of it, the two together do not)
    a.box("Bollard", (0.6, 0.6, 0.6), (-1.9, 0.3, Z), "steel", bevel=0)   # (its top under the boom at its limit)
    a.reach("Arm", chain, tip=(0, 5.3, Z), poses={"out": (3.0, 2.5, Z), "down": (-2.0, -0.2, Z)})
else:
    a.reach("Arm", chain, tip=(0, 5.3, 0.7),
            poses={"out": (9.0, 1.0, 0.7) if HOW == "far" else (3.0, 2.5, 0.7), "stowed": (0.8, 2.6, 0.7)})
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
print("RIG " + json.dumps({"chains": manifest.get("chains"),
                           "wrist": manifest.get("joints", {}).get("Wrist", {}).get("follows")}))
