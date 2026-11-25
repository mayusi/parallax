---
area: ui
kind: boot
date: 2026-10-18
links: ["[[ui/index]]"]
---

# UI lane — start here

## Boot line (paste this into any harness to start a UI session)
You are the UI lane of this project: screens (identities, UI art, HUDs, menus). Run `lune run kit start ui` first and act on its
`next_action`. Work only on this department; leave every other department's files alone.

## How this lane works
- Direction before identity: an original look starts as `lune run kit ui direct new <name> --ask "<the owner's
  words>" --game <G>`, 3-5 checked directions, `kit ui direct board` (sketch frames), and the OWNER's pick.
- Identity first: `assets/ui/identities/<name>.json` (tokens from references, an Enum.Font trio, shape language,
  motion, bans), then `kit new screen <Pascal> --from RpgHud`, then edit `assets/ui/<Name>.json` (`"identity"`,
  `"quality": "hero"`). Icons: `kit vision concept`, then `kit vision cutout`, into `assets/ui/art/<identity>/`.
- Check: `kit ui --motion`, then LOOK at `build/ui/<Name>.png` (real fonts, phone / tablet / desktop) and
  `<Name>.motion.png` (animated: `kit ui reel <Name>`); hero: `kit ui judge <Name>` (two FRESH judges, then
  `--record`); the owner's verdict: `--owner <score> "<words>"`. Start from the owner-rated examples (`kit ui vault list`).
- The full recipe: the `parallax-ui` skill (`kit/skills/parallax-ui/SKILL.md`).

## This lane's rules
- **The UI library rule (owner, 2026-10-12, a MUST).** Everything the UI pipeline makes is saved, packaged by part
  and named properly, in `library/ui/` (every screen with its parts, previews, reel and verdicts; every identity's
  pieces; owner-rated versions kept when a screen changes; nothing is ever deleted). `kit ui` and every piece command
  save it for you; `kit verify` FAILS when anything made is missing or stale (`lune run kit ui vault` fixes it). Reuse
  before making: `kit ui vault find "<words>"`, `kit ui find`, `kit ui vault get <Screen> --as <New>`.
