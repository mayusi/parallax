---
kind: lesson
area: code
date: 2026-10-10
by: mayusi
source: "kit/lessons/code.md"
links: ["[[code/index]]"]
project: Parallax
---

Patching repo files from Python on Windows: open(p, "w").write(s) turns LF files into CRLF (text mode); .luau files are eol=lf, so stylua --check fails kit verify on EVERY line while git diff looks clean (autocrlf hides it). Read and write bytes (open(p, "rb") / "wb"), check with git ls-files --eol. And a Python patch script written through a bash heredoc can lose a backslash level (a doubled backslash arrives single): write patch scripts with the editor tool, assert every old text is present before replacing.
