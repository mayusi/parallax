---
name: parallax-vet
description: Use before installing ANY package, binary, extension, model, or MCP server. Double-source verification with malware checks.
---

# vet — nothing installs without two independent sources + a VETLOG entry

## The law
Every install needs **two independent source checks** (e.g. GitHub API + PyPI/winget
metadata, or vendor page + hash match) AND a row in `VETLOG.md` BEFORE running the
installer. No VETLOG row = no install. Ever.

## Checklist per candidate
1. **Exists officially:** repo/package page from the real publisher (watch typosquats:
   `blender-mcp` vs `mcp-for-blender`, lookalike Unicode, fresh forks with stars).
2. **Maintained:** releases or commits within ~12 months; not archived; open issues
   not screaming abandonment.
3. **License clean:** SPDX present, commercial-safe (no NC/research-only/Territory
   traps). Weights AND code licensed separately — check both.
4. **Install surface:** read the installer/script FIRST (`install.ps1`, `setup.py`,
   postinstall hooks, `pip install` deps). No `curl|sh` blind runs; prefer winget /
   pinned release zips with hash verification.
5. **Provenance:** hash from release metadata matches download (byte count at minimum);
   publisher == source domain (e.g. `download.blender.org`); no login-gated blobs.
6. **Behavior:** telemetry defaults? (must be off/opt-in), network calls at runtime,
   auth/socket exposure (bind localhost only), what it writes outside its folder.
7. **Red flags (any one = stop and report):** no license file, single-maintainer +
   sudden ownership change, obfuscated code, requests admin/elevation without reason,
   bundled binaries without sources, Discord-only distribution.

## Record (VETLOG.md row)
Date | What + version | Source 1 | Source 2 | Hash match | License | Decision + initials.
Backfill honestly — if something was installed before this law, vet it retroactively
or mark `UNVETTED (installed <date>)` and schedule it.
