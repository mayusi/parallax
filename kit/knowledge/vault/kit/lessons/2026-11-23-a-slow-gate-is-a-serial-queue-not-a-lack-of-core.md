---
kind: lesson
area: kit
date: 2026-11-23
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A slow gate is a SERIAL QUEUE, not a lack of cores - measure each step before guessing (kit verify 2026-11-23: 1h35m then red). The Luau specs ran in ONE process on one core (~38 min); every content gate queued behind the Python lane's join; the GPU pair (photoscan + delight, a ~34 min floor on the one card) ran 2x slow beside four open Studio windows; 38 files that failed beside the pool were re-run one at a time (~35 min); and test_low_mixed's limit came from ONE lucky 21 s run (normal 60-220 s) -> 120 s -> TIMED OUT for ever, because a timed-out file kept its old time. Fixed: specs one process each across cores, the Python lane joined LAST, a second-pass retry a third of the pool wide, limits from the slowest of the last 5 runs (a time-out joins the history), and every step's time on its [ok] line + a time: line.
