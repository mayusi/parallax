---
kind: lesson
area: anim
date: 2026-10-28
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

A CORE MOVEMENT CLIP UNDER A WEAPON HOLD SHOWS NONE OF ITS ARMS (Sample Game slide, 2026-10-28): the slide played at Core while Greatsword's hold (an arms-only Idle-priority layer) covered both arms, so the owner judged the sword hold's arms as the slide's ('the right hand ... grabbing onto the ground'). For a movement state that must show its own arms with a weapon out, key a weapon VARIANT (SwordSlide: both arms + the weapon block, here Greatsword trailing back and up) and load it at MOVEMENT priority (above Idle holds, below Action attacks); Locomotion._loadExtra loads extra loops at Core, so the variant needs its own load. Ask which weapon was out before reading an arm complaint.
