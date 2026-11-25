---
kind: lesson
area: qa
date: 2026-10-29
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

Studio MCP input for combat proofs: user_keyboard_input's 'MouseLeftButton' key does NOT register as a click, VirtualInputManager is not callable from execute_luau (lacks RobloxScript), and separate mouse/keyboard calls land ~1 s apart in unfocused Studio (7 fps) - a mixed click+key string (air combos) can't be driven at game speed; prove keys-only moves by input, and get Studio focused (or the owner's playtest) for click+key strings. A training map's dummies' HumanoidRootPart is ANCHORED (launches can't move them) - unanchor one for a juggle test
