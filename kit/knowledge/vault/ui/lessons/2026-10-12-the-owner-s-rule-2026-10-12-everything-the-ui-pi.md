---
kind: lesson
area: ui
date: 2026-10-12
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

The owner's rule (2026-10-12): everything the UI pipeline makes is SAVED, packaged by part and named properly — library/ui via kit/ui/vault.py. It is enforced, not advised: kit ui and every piece command run the save, kit verify runs the check and fails on anything unsaved or stale, the vault never deletes and keeps owner-rated versions when a screen changes, and it names every piece without a source. Reuse before making: kit ui vault find / kit ui find / kit ui vault get.
