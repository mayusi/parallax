# Parallax beyond Roblox: Godot, Unreal Engine and Unity

Parallax ships for Roblox today. This page is the plan for the other engines: what already carries over, the seam a
second engine plugs into, and the order the work happens in. It is a roadmap, not a promise of dates.

## What already carries over

Most of Parallax is not about Roblox at all. The engine-agnostic core is roughly 70% of `kit/`:

- **Governance:** the work board, lane sessions, PROMPT-X, the cases, the quality locks, verdicts and the knowledge
  vault, the CLI and MCP gates, the git hooks.
- **Content tools:** Blender modelling, UVs, bakes, sculpt and CAD; the vision and audio tools; reference finding;
  the effect player and texture baking; animation authoring and its gates.
- **Engine-neutral outputs:** FBX and glTF models with PBR maps, animated glTF clips (`kit/anim/export_clip.py`), OGG
  sound, world blueprints as JSON, interface specs as JSON.
- **Pure runtime rules:** the `*Rules` modules, rate limiting, move data, effect budgets and validation in `src/kit/`
  hold no engine calls.

What is Roblox-specific is a thin layer: the emitters that turn the neutral data into Rojo models and places, the Luau
runtime wrappers around the DataModel, the Studio MCP bridge for playtests, and the Open Cloud uploads.

## The seam

A project names its engine in `kit.config.json` (or `parallax.config.json`):

```json
{ "engine": "roblox" }
```

`roblox` is the default and the only engine with emitters today; `godot`, `unreal` and `unity` are recognised and
answered with this roadmap. The planned layout separates the core from one emitter set per engine:

```text
kit/
  core/        engine-agnostic: governance, PROMPT-X, vault, board, DCC, vision, audio DSP
  engines/
    roblox/    Rojo .model.json / .rbxlx, Luau remotes, the Studio MCP bridge, Open Cloud
    godot/     .tscn / .tres text compiler, glTF animation libraries, the Godot CLI / MCP, GDScript or C# runtime
    unreal/    Unreal Python AssetImportTask, .umap / .uasset, Niagara / MetaSounds, Remote Control
    unity/     C# AssetPostprocessor and .meta, Prefab / UXML / USS, Unity MCP, a runtime package
runtime/
  core/        pure rules and state machines
  roblox/      today's src/kit/ wrappers
  godot/       addons/parallax/
  unreal/      Plugins/Parallax/
  unity/       Packages/com.parallax.runtime/
```

## The nine drivers

Each engine implements the same nine drivers over the same neutral inputs:

| Driver | Neutral input | Roblox (today) | Godot 4 | Unreal Engine 5 | Unity |
|---|---|---|---|---|---|
| Asset | model manifests, `.glb` / `.fbx`, PBR maps, `.ogg` | `.model.json` + uploaded ids | `.glb` / `.tscn` with import settings | `AssetImportTask` → StaticMesh, Texture2D | `AssetPostprocessor` + `.meta` |
| Scene | world blueprint JSON, interface JSON | Rojo models + places | plain-text `.tscn` scenes | Python → `.umap` actors, UMG | prefabs / scenes, UXML + USS |
| Animation | clip JSON + rig + beat markers | KeyframeSequence | glTF → AnimationLibrary + method tracks | FBX / GLB → AnimSequence + notifies | AnimationClip + events |
| Material | PBR maps + the VFX layer stack | SurfaceAppearance, emitters, beams | StandardMaterial3D, GPUParticles3D | material instances, Niagara | URP / HDRP Lit, VFX Graph |
| Audio | the sound event catalog | the Sfx runtime on the Audio API | AudioServer buses | MetaSounds + modulation buses | AudioMixer snapshots |
| Engine bridge | playtest scenario + performance probe | the Studio MCP | `godot --headless` / Godot MCP + GUT | Remote Control / Unreal MCP | Unity MCP / `-executeMethod` |
| Code | remote schemas + gameplay scripts | Luau remotes, StyLua, Selene, luau-lsp | validated `@rpc` wrappers, gdlint | `UFUNCTION(Server, WithValidation)` | server RPCs, Roslyn |
| Publish | the upload jobs + the moderation gate | Open Cloud through the Studio MCP | `--export-release` → itch.io / Steam | RunUAT → Steam / Fab | Addressables → Steam |
| Runtime SDK | neutral JSON (moves, effects, sounds, UI) | `src/kit/` (Luau) | `addons/parallax/` | `UParallaxSubsystem` | `com.parallax.runtime` |

## Why Godot first

Godot's scenes and resources are plain text, just like Rojo's model files, so the kit can compile them offline and
check them in CI; Godot imports glTF natively, and the kit already exports glTF models and animation and OGG sound;
and `godot --headless` runs playtests with no editor daemon. Unreal Engine and Unity follow, behind the same MCP
server and the same gates.

## How to help

Each driver is its own piece of work with a clear input and a clear output. Ideas, prototypes and pull requests are
welcome - see [CONTRIBUTING.md](../CONTRIBUTING.md).
