---
area: kit
kind: boot
date: 2026-10-18
links: ["[[kit/index]]"]
---

# Kit lane — start here

## Boot line (paste this into any harness to start a Kit session)
You are the Kit lane of this project: the kit itself (kit/ commands, gates, the vault, harness files). Run `lune run kit start kit` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- Changing the kit (`kit/`, `src/kit/`): run `lune run kit selftest` and `lune run kit verify`; prove the committed
  tree with `lune run kit prove --selftest` when other sessions share the checkout.
- The vault (kit/knowledge/vault) is the one record: `kit vault check`, `kit vault sync`. No instruction files are
  written for any client: the MCP server sends the rules (kit/harness/AGENTS.parallax.md) and each lane's recipe
  (kit/skills, through parallax_skill); `kit harness` keeps the git hooks and the connected clients' configs in step.
- The full recipe: the `parallax-work` skill (`kit/skills/parallax-work/SKILL.md`).

## This lane's rules
- The shared rules (originality, safety) are in kit/harness/AGENTS.parallax.md (every client gets them from the MCP server); this lane has no rule of its own yet.
