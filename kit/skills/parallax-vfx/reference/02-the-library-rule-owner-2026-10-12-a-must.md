<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## The library rule (owner, 2026-10-12 — a MUST, enforced by `kit verify`)
EVERYTHING the VFX pipeline makes is saved in `library/vfx/`, packaged by part and named properly: every effect
(source, the expanded version that plays, previews, recordings at 640 px, the owner's verdicts, every earlier
version), every part, every texture (spec + finished sheet), every mesh — each with a README (what it is, who uses it,
how to reuse it). `kit vfx` and `kit vfx play --record` save it; `kit verify` fails on anything missing or stale.
- **Reuse before making**: `kit vfx vault find "<words>"` → read `library/vfx/<kind>/<name>/README.md` →
  `kit vfx vault get <effect> --as <new>` (the effect + its parts + textures + uploaded ids), or `"use"` a part.
- **The owner's words are data**: `kit vfx vault verdict <effect> "<words>" [--score N]` the moment they judge — the
  verdict stays tied to that exact version, and that version is never lost.
- Saving by hand (after editing outside `kit vfx`): `lune run kit vfx vault`. Never delete from `library/vfx/`.
