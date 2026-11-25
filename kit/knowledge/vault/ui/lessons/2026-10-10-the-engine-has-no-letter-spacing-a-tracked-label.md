---
kind: lesson
area: ui
date: 2026-10-10
by: mayusi
source: "kit/lessons/ui.md"
links: ["[[ui/index]]"]
project: Parallax
---

The engine has no letter-spacing: a tracked label (tracking 0.3) compiles to one AutomaticSize-X label per glyph in a centred horizontal list and Ui.text rebuilds the glyphs. A plain TextButton keeps the engine's grey background unless a colour is set, so the compiler makes colourless buttons transparent; a plate-backed button carries its text in a child Label.
