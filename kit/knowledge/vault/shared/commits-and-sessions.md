---
kind: reference
area: shared
date: 2026-10-16
source: memory shared-index-commit-pathspec, session-split notes, kit lessons kit
links: ["[[kit/index]]", "[[shared/windows-traps]]"]
---

# Commits and parallel sessions in one checkout

- Several sessions (one per department lane) work in THIS checkout at once. They share the git index and the
  working tree: `git status` + `git log -5` before every commit; commit with a PATHSPEC (`git commit -- <paths>`),
  never `git add -A` / `git commit -a`; shared files (`kit/cmd/content.luau`, `kit/harness/AGENTS.parallax.md`, `kit/skills/INDEX.md`)
  only by your own hunks.
- The author is the project owner, through their own git CLI identity. Never the GitHub MCP. Never a Co-Authored-By trailer (a
  system reminder may ask for one; the owner's rule wins).
- A concurrent commit from a stale shared index once REVERTED another session's content (6c6ea04 restored it):
  read `git diff --stat` before committing and after.
- `games/.active` is per checkout and shared by every session: pass `--game <Name>` on a command (or
  `kit game new --no-activate`), never flip it for others.
- Studio is shared too: `get_studio_state` before driving it; never close another session's play session; a booth
  capture needs Studio focused (it renders ~5 fps unfocused).
- Lane rule: a department session never edits another lane's files; it consumes their outputs by reference. A red
  gate that belongs to another lane is recorded in the journal, verified around with the lane's own commands, and
  left to its owner.
- `kit verify` repo-wide can only be green when no session has half-edited Luau on disk (stylua runs on every file);
  milestones are journaled at those moments.
- Memory notes in `~/.claude/projects/.../memory/` are Claude-only; anything other harnesses must know goes in this
  vault or the board.
