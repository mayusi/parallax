---
kind: lesson
area: kit
date: 2026-10-04
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: sample_game
---

VERIFY-BLOCKER: serde pretty-vs-compact float instability makes ui/world drift checks ALWAYS stale once models contain non-exact-binary floats. Proof: ScopeOverlay accent 231/255 encodes ...764 in the written file vs ...765 fresh; OrbitalRange ring pos 28.0737202661892 vs ...202. kit ui/kit world write pretty (encode json, true) but verify compares compact encodings, so 1-ulp diffs fail forever. Until kit normalizes (write compact, or tolerance compare), verify can never go green on real content. Do NOT edit kit/ or generated files to fake it.
