---
kind: lesson
area: kit
date: 2026-10-16
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

Lune's serde YAML round-trips plain frontmatter (quoted strings with escaped quotes, flow lists); write the YAML by hand in a fixed key order so notes diff cleanly, parse with serde.decode('yaml'); a link to a FOLDER ([[3d/lessons|folder]]) must resolve by fs.isDir or the health check cries wolf; a note's body starts after ONE blank line (strip the leading newline or every lesson line ends with a space and never dedupes against the old one-line files).
