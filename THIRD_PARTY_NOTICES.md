# Third-party notices

Parallax is MIT-licensed (see `LICENSE`). These files carry third-party material under their own licences:

| Files | What | Licence |
| --- | --- | --- |
| `kit/vfx/player/vendor/three.*.js`, `kit/grading/page/vendor/three.*.js` (+ `addons/`) | three.js r186 | MIT, Copyright 2010-2026 Three.js Authors (`LICENSE` beside the files) |
| `kit/types/globalTypes.d.luau` | Roblox type definitions published by luau-lsp | MIT (see `kit/types/NOTICE.md`) |
| `assets/animations/calibration/style_stats.json` | per-style locomotion statistics measured from the 100STYLE dataset (Mason, Starke, Komura 2022, doi 10.1145/3522618); no motion data is included | CC BY 4.0 (attribution inside the file) |
| `kit/selftest/vfx/{chart_owner,chart_owner_good,scope,scope_good}/refs_measured/flame_arc_*.lore.json` and `flame_arc_*.brief.md` (10 files) | short quotations from an article of the Kimetsu no Yaiba Wiki on Fandom (kimetsu-no-yaiba.fandom.com), used as test fixtures for the VFX lore stage. Adapted: character and technique names were replaced, including in the page title of the URL the files record, so that URL does not resolve | CC BY-SA (Fandom's licence for wiki text); these 10 fixture files stay under CC BY-SA, not MIT |

Every tool, package and model the kit installs or calls is vetted and recorded in `VETLOG.md`, with its licence.
