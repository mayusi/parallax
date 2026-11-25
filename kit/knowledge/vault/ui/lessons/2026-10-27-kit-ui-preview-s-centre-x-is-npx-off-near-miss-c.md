---
kind: lesson
area: ui
date: 2026-10-27
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

kit ui preview's 'centre x is Npx off' near-miss check misfires on a LEFT-ALIGNED list (character-action-style menu): SgMenu's PLAY/QUIT centres differ 3 px but their ink left edges match within 0.8 px - for left-aligned lists compare ink left edges, not centres.
