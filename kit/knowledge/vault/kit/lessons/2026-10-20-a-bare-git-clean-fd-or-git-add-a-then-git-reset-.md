---
kind: lesson
area: kit
date: 2026-10-20
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A bare 'git clean -fd' (or 'git add -A' then 'git reset --hard') in a worktree whose shared folders are JUNCTIONS into the main checkout deletes the owner's real files through the link: on 2026-10-20 it emptied _downloads (6,150 files, 4 GB, restored from the E: copy). Every worktree script must exclude its linked folders by pathspec, dry-run first, and never git-add inside them; /_downloads/ is now in .gitignore.
