---
kind: lesson
area: ui
date: 2026-10-27
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

kit ui render fits EVERY text item to its own frame, so a word set (PLAY / SETTINGS / QUIT) comes out at different scales: measure each word's cap height by script from columns with no descender (QUIT's Q tail made its 'cap' 109 instead of 81 -> drawn 26% small) and size each ImageLabel as cap_target / (cap_px / 128). Also: the spec's 'exposure' multiplies the lights (0 = lights off), it is not an EV stop.
