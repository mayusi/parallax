---
kind: lesson
area: kit
date: 2026-11-22
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Before adding a function to a src/kit module, grep the module for the name AND for the feature (2026-11-22, Ui.luau): a new Ui.track (an analytics funnel hook) silently REDEFINED the existing Ui.track (the world marker), and the feature already existed as Ui.funnel + kit.UiAnalytics. Specs and the storybook stayed green (Ui.waypoint had captured the original); only luau-lsp's DuplicateFunction in kit prove's types step caught it, an hour later. Run the types step (luau-lsp analyze src) before committing any src/kit change.
