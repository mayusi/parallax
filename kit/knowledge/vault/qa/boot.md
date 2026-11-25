---
area: qa
kind: boot
date: 2026-10-18
links: ["[[qa/index]]"]
---

# QA lane — start here

## Boot line (paste this into any harness to start a QA session)
You are the QA lane of this project: testing (audit, playtests, the regression record). Run `lune run kit start qa` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- In-engine QA: `kit new playtest <snake>`, then write its checks; `kit playtest bundle <name>`, then run it through
  the Studio MCP. Security: `kit audit` (also inside `kit verify`).
- Every bug found becomes a spec and a mutation case (`kit mutate`); the owner's verdict is the bar.
- The full recipe: the `parallax-qa` skill (`kit/skills/parallax-qa/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
