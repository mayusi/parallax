# Contributing to Parallax

Thanks for helping. This repository is **the kit's home**: the kit (`kit/`), its in-game runtime (`src/kit/`) and the
measured data its builders read (`assets/`). Games are made in their own folders with `lune run parallax install`.

## Getting set up

Follow [SETUP.md](SETUP.md) steps 1-5 in a clone of this repository, then:

```powershell
lune run parallax harness
lune run parallax connect <your AI client>
```

`harness` installs the kit's git hooks in your clone (the lane fence and the commit gate). `connect` adds the kit's
MCP server to your own client; what it writes is gitignored here - the repository ships no AI-client files.

## The rules

- **Prove it before you claim it.** `lune run parallax verify` must pass. A change to a gate, a builder or a fixture
  also needs `lune run parallax selftest`: every content gate must still catch its bad fixture.
- **Never weaken a check to make something pass.** Do not edit a test, a gate or a `kit/selftest` fixture so that a
  change goes green; fix the change. When a behaviour is meant to change, change its test to the new behaviour - with
  assertions at least as strong - and say so in the pull request.
- **Change the inputs, not the outputs.** Generated files (`build/`, compiled screens and models, `.verify/`) are
  rebuilt from their sources.
- **Vet everything you add.** A new package, binary, model or dataset is checked against two independent sources, its
  licence and its install script, and recorded in [VETLOG.md](VETLOG.md) before it lands.
- **One lane per change.** A commit that mixes two lanes' files is refused by the lane fence; write `cross` in the
  commit message when it is deliberate.
- **Keep the server the authority.** Gameplay code validates every remote argument (`Guard`) and rate-limits every
  handler (`RateLimit`); `kit audit` fails otherwise. Shared modules stay pure.
- **Record the why.** A decision that shapes the kit gets an entry in [DECISIONS.md](DECISIONS.md); a user-visible
  change gets a line in [CHANGELOG.md](CHANGELOG.md).

## Useful commands

| Command | What it checks |
|---|---|
| `lune run parallax test kit` | the kit's Luau specs |
| `python kit/test/python/run.py` | the kit's Python tests (`-k <words>` for some of them) |
| `lune run parallax harness --check` | git hooks and connected client configs in step |
| `lune run parallax vault check` | the knowledge vault's notes, links and indexes |
| `lune run parallax verify` | everything above plus format, lint, types, the security audit and the content gates |
| `lune run parallax selftest` | every content gate against its bad fixture |
| `lune run parallax prove --selftest` | the committed tree, in a clean sandbox |

## Pull requests

Describe what changed and why, list the commands you ran and their `summary:` lines, and include before/after evidence
for anything visual (a sheet, a render, a recording). CI runs the toolchain checks, the specs and the vault checks on
every push; `verify` and `selftest` need the full local toolchain (Blender, ffmpeg, Node.js, Roblox Studio), so run them
before you open the pull request.

## Releasing (maintainers)

1. Set the new version in `kit/VERSION` and `wally.toml`, move the CHANGELOG's "Unreleased" items under it, and run
   `verify` and `selftest` on that commit.
2. Tag it: `git tag -a vX.Y.Z -m "Parallax vX.Y.Z"`.
3. `python kit/scripts/release_archive.py vX.Y.Z` writes `parallax-vX.Y.Z.tar.gz` (one top folder,
   `parallax-X.Y.Z/`) and `parallax-vX.Y.Z.tar.gz.sha256` beside the repository - the two files
   `lune run parallax upgrade` downloads and checks.
4. Push the commit and the tag, then create the GitHub release for the tag with both files attached.
