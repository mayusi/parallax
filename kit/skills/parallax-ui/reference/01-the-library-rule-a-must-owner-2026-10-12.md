<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## The library rule — a MUST (owner, 2026-10-12)
Everything the UI pipeline makes is saved, packaged by part and named properly, in `library/ui/`:
`<identity>/screens/<Screen>/` (README with the owner's verdict and a parts table, manifest, the spec, every picture
as `parts/<Node.Path>.png`, previews + reel), `<identity>/pieces/` (every piece the identity ever made, with
PIECES.md and its source), owner-rated versions kept under `versions/` when a screen changes; nothing is deleted.
`kit ui` and every piece command (ink, letter, render, trace, gauge, reel) save automatically; **`kit verify` fails**
when anything made is not saved or is stale, or `lune run kit ui vault` fixes it. Every piece needs a source (a sidecar
or a PROVENANCE.md row): the vault names the ones that do not. Reuse BEFORE making: `kit ui vault find "<words>"`,
`kit ui find "<words>"`, `kit ui vault get <Screen> --as <New>`; the index: `library/ui/INDEX.md`.
