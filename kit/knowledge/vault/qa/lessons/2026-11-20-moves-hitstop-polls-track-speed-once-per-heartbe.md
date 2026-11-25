---
kind: lesson
area: qa
date: 2026-11-20
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

moves_hitstop polls track.Speed once per Heartbeat: in a Studio window drawn in the background (6 fps, 0.167 s frames) the move's 0.05 s hit-stop release (task.delay) can resume BEFORE the next Heartbeat the test samples, so a freshly opened window failed 'froze' / 'moved again' twice while two older windows with the same code and data passed (held 0.165 s); a live probe showed the freeze is real (the track's TimePosition held one frame at the hit). Before calling it a regression: run it in another window, or with the window in front; the measurement (event- or TimePosition-based) is the owner's call - a test is never edited to pass
