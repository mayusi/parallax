---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

Roblox styling in the engine (2026-11-20): a StyleRule's value is read with inst:GetStyled(prop) - the property itself keeps the instance's own value (Rotation read 0 while styled 7); a StyleQuery turns active (q.IsActive) ONLY parented under the styled GuiObject (in the StyleSheet, under a rule or the StyleLink it never does); '@Name' selects the object the query sits under, so its nested rules need '> X' or '>> X' (a bare '.KitTitle' under '@Name' matched nothing). tests/playtest/ui_style_query holds both the kit's layout (red) and the engine's (control).
