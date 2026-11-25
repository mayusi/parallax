Two presets the METHOD gate must refuse, each built from its own copy of a MADE scene (a glint, a ring of light
that breaks up, embers; no real footage). Their twin that passes is kit/selftest/vfx/dissolve_gate_good.

| Preset | What is wrong | The gate says |
|---|---|---|
| preset_dissolve_erode | the ring mesh dissolves by `erode`: per-vertex alpha, which Roblox ignores on a runtime mesh | `a mesh's "erode" shows in the browser player only` |
| preset_dissolve_unbaked | beat 1 plans "Dissolve effects"; the ring plays a sheet through a surface, but the sheet (textures/m_ring_dz.json) is an import, not a baked break-up | `beat 1 plans "Dissolve effects" and nothing that plays in that beat uses it` |

Written once by a script; plain files now. Never edit them to make the gate pass.
