---
kind: lesson
area: anim
date: 2026-10-24
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

BLADE READ from the game camera (2026-10-24): the KatanaKaeshi riposte swept in front of the chest = BEHIND the torso from the player's camera, invisible, though every number passed; kit anim appeal now reports blade_visible_pct per key. It is REPORTED, not gated: the owner's loved 9/10 cuts hide the blade near the Hit too (Katana4Kiriage 12.5 % at one key, GreatswordSideCut 31 %); it matters for poses that must READ - a parry (KatanaKaeshi 87.5 %), a guard, a held finish. The fix for a hidden cut is the camera cheat (kit anim appeal --cheat) + a wider follow-through, never a wind-up
