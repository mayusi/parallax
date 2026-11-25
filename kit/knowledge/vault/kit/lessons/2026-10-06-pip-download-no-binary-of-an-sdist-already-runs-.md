---
kind: lesson
area: kit
date: 2026-10-06
by: mayusi
source: "kit/lessons/kit.md"
links: ["[[kit/index]]"]
project: Parallax
---

pip download --no-binary of an sdist already RUNS its setup.py (the metadata step) before you can read it — vet sdists by fetching the file by URL, checking its PyPI sha256 and reading setup.py/pyproject first (natten 0.21.7, 2026-10-06).
