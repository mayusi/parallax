---
kind: lesson
area: anim
date: 2026-11-14
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Motor6D.Transform does not replicate: each machine's Animator writes its own. Any kit layer that writes joint poses (a blend, foot placement, a look-at) is SEEN only on the machine that runs it - write it on each client for every character it shows; a server-side write only moves what the server's hit checks read.
