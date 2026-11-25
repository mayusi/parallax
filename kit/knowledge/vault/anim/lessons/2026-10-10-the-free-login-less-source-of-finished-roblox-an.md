---
kind: lesson
area: anim
date: 2026-10-10
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

The free, login-less source of finished Roblox animations is the DevForum itself: search.json?q=<words> then /t/<id>.json; the posts' own uploads (/uploads/short-url/...rbxm|rbxl) download directly. Creator Store assets return 401 without a login (assetdelivery v1 and v2 alike); GitHub holds almost no KeyframeSequence files; Payhip/robloxanimations 'free' packs need a checkout. Crawl, dump every attachment read-only (kit/anim/kfs_dump.luau; a .rbxl is a place: deserializePlace), classify each sequence by its posed part names (Torso vs UpperTorso), keep the R6 ones with a VETLOG row. 356 topics gave 37 files with sequences and one real finished R6 attack set (Free Friday's whirlwind).
