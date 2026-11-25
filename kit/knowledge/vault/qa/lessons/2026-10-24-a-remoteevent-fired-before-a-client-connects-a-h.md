---
kind: lesson
area: qa
date: 2026-10-24
by: mayusi
source: "kit/lessons/qa.md"
links: ["[[qa/index]]"]
project: Parallax
---

A RemoteEvent fired before a client connects a handler is QUEUED and handed to the FIRST OnClientEvent handler that connects - a second handler connected later never sees it (the networked cutscene test missed its own broadcast). A broadcast that must reach late listeners also stamps its state on the remote (attributes) for them to read; a test reads the stamp, not a second handler
