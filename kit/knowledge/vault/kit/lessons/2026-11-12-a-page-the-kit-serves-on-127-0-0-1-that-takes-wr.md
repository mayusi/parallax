---
kind: lesson
area: kit
date: 2026-11-12
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

A page the kit serves on 127.0.0.1 that takes WRITES must forbid being framed. A token only the page knows, an exact Host and a same-origin check all pass for a page shown inside another site's frame - its requests are its own - so a site the owner has open could lay it invisibly over its own buttons and turn his typing and his click into an approval of something he cannot see. Two lines close it (Content-Security-Policy frame-ancestors 'none' and X-Frame-Options DENY: LocalPage.pageHeaders), plus refusing a request whose Sec-Fetch-Dest is a frame. Found by the third fresh review of kit review, not by the first two.
