---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Never name a kit flag --list: Cli.parse keeps repeated flags in flags.list (always a table), so 'if flags.list' is true on every call, and a bare --list REPLACES that table with true (the next --key value flag then crashes). kit review's first build printed its text listing instead of serving the page for exactly this reason (2026-11-12); it is --stages now. Compare a boolean flag with == true, and pick a name that is not a field the parser owns.
