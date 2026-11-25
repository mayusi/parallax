<!-- reference for the parallax-systems route card; verbatim from the skill page (2026-10-16) -->

## Every game is a folder (FIRST, always)
The owner says "we are making <game>"? `lune run kit game new <Pascal>` before anything else (`kit game use <Name>`
to continue one; `--game <Name>` on a single command). It makes `games/<Name>/` — `GAME.md` (the brief: ASK THE OWNER
its questions first; `kit game check` lists the open ones), `src/{server,client,shared}`, `assets/`, `tests/`, its own
`board/` (tasks + handoffs), `docs/`, a Rojo project and a synced copy of the kit runtime — and makes it ACTIVE: every
kit command then reads and writes inside it (`kit status` says which game). The layout is in `games/<Name>/README.md`.
Gameplay code never lands at the project root: `kit new system` refuses without a game, and `kit verify` fails on new
root files (`games/legacy-root.json` = the scratch that was there before). Prove a game: `kit game check`,
`kit verify --game <Name>`; serve it: `rojo serve games/<Name>/default.project.json`.
