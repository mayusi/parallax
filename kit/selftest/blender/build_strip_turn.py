"""build_strip_turn.py — POSITIVE fixture for TURNS in the take-apart gate (a.disassembly path {"turn": ...}): a flap
lying on a box with its right end held under a keeper (a pistol's barrel, its muzzle in the slide's front ring). Tipped
about its right end's lower edge, lifted a hair and drawn out to the left, it comes out clear: must NOT be named:
disassembly. Its twin (KIT_STRIP_TURN=straight: lifted straight up) runs into the keeper and must be named. Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

variant = os.environ.get("KIT_STRIP_TURN", "ok")
a = rbx.Asset(f"_selftest_strip_turn_{variant}", tex=64, size=(2.0, 0.7, 1.0), ground=False)
a.material("steel", (0.6, 0.6, 0.62), metal=1.0, rough=0.4)
a.box("Body", (2.0, 0.4, 1.0), (0, 0.2, 0), "steel", bevel=0)
a.box("Post", (0.1, 0.3, 1.0), (0.95, 0.55, 0), "steel", bevel=0)     # (x 0.9..1.0, on the body)
a.box("Keeper", (0.3, 0.1, 1.0), (0.85, 0.65, 0), "steel", bevel=0)  # (x 0.7..1.0, y 0.6..0.7: over the flap's end)
a.box("Flap", (1.6, 0.1, 0.8), (0.0, 0.45, 0), "steel", bevel=0)     # (x -0.8..0.8, y 0.4..0.5: its end under the keeper)
TURN_OUT = {"name": "flap tipped out", "parts": ["Flap"],
            "path": [{"turn": -30, "axis": (0, 0, 1), "pivot": (0.8, 0.4, 0)}, (0, 0.05, 0), (-2.4, 0, 0)]}
LIFT = {"name": "flap lifted straight", "parts": ["Flap"], "move": (0, 0.8, 0)}
a.disassembly([{"ok": TURN_OUT, "straight": LIFT}[variant]], base=["Body", "Post", "Keeper"])
a.build()
