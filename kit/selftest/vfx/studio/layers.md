# Five layer features PLAYED in Roblox: one Studio play client, made presets (2026-11-15)

A slab broken into its own pieces, an authored vector field, mesh stones, a point cloud, a forced size: each a made
preset of the kit's own, the same file the browser player plays in `kit/selftest/vfx/player/made.py`. Nothing is in a
project's assets, nothing is saved or uploaded; the place is the kit's scratch place.

## Setup

1. `python kit/selftest/vfx/player/made.py --keep` (it writes `build/vfx/animatic/kitfx_<name>.json` and the kept
   files under `build/vfx/kitfixture/kept/`).
2. In `build/vfx/studio/scratch.project.json`, under `ReplicatedStorage.VfxPresets`: `kitfx_break`, `kitfx_field`,
   `kitfx_forced`, `kitfx_stones`, `kitfx_cloud` = `../animatic/kitfx_<name>.json`; `fields` =
   `../kitfixture/kept/fields`; `points` = `../kitfixture/kept/points`; copy `kept/fractures/kitfx_slab.json` into
   the place's `fractures` folder. `rojo build` it, open it as its own Studio window.
3. Put the LocalScript below into `StarterPlayer.StarterPlayerScripts` (in Edit), start play, and read
   `workspace:GetAttribute("KitProbe3Out")` on the CLIENT after about a minute.

A module required through the Studio tools is not the one a LocalScript required: measure from a LocalScript.
Studio's own camera script moves the camera back: a test that moves the camera sets it Scriptable EVERY frame.

```lua
local RS = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Vfx = require(RS:WaitForChild("kit"):WaitForChild("Vfx"))
local out = {}
local function all()
	local set = {}
	for _, d in workspace:GetDescendants() do set[d] = true end
	return set
end
local function read(before) -- the effect's own parts: how many, how many are meshes, their middle, spread and box
	local list, meshes, sum = {}, 0, Vector3.zero
	local lo, hi = Vector3.new(1e9, 1e9, 1e9), Vector3.new(-1e9, -1e9, -1e9)
	for _, d in workspace:GetDescendants() do
		if d:IsA("BasePart") and not before[d] and d.Transparency < 0.99 then
			table.insert(list, d); sum += d.Position; lo = lo:Min(d.Position); hi = hi:Max(d.Position)
			if d:IsA("MeshPart") then meshes += 1 end
		end
	end
	if #list == 0 then return { n = 0 } end
	local c, spread = sum / #list, 0
	for _, d in list do spread += (d.Position - c).Magnitude end
	local box = hi - lo
	return { n = #list, meshes = meshes, y = c.Y, spread = spread / #list, box = { box.X, box.Y, box.Z } }
end
task.wait(8)
local cam = workspace.CurrentCamera
local want = CFrame.lookAt(Vector3.new(0, 8, 28), Vector3.new(0, 6, 0))
RunService:BindToRenderStep("KitProbeCam", Enum.RenderPriority.Camera.Value + 1, function()
	cam.CameraType = Enum.CameraType.Scriptable
	cam.CFrame = want
end)
for _, name in { "break", "field", "stones", "cloud" } do
	local full = "kitfx_" .. name
	local r = { has = Vfx.has(full) }
	if r.has then
		pcall(Vfx.prewarm, full)
		task.wait(name == "break" and 5 or (name == "stones" and 12 or 0.5))
		local before = all()
		Vfx.play(full, CFrame.new(0, 0, 0))
		task.wait(0.7); r.early = read(before)
		task.wait(1.5); r.late = read(before)
		task.wait(1.6); r.after = read(before)
	end
	out[name] = r
end
do -- forced: the ring's size as the camera goes away and comes near (ref 28)
	local before = all()
	Vfx.play("kitfx_forced", CFrame.new(0, 0, 0))
	task.wait(0.6)
	local rows = {}
	for _, dist in { 28, 56, 14, 3, 400 } do
		want = CFrame.lookAt(Vector3.new(0, 11, dist), Vector3.new(0, 11, 0))
		task.wait(0.33)
		local s = { cam = dist }
		for _, d in workspace:GetDescendants() do
			if d:IsA("BasePart") and not before[d] and (d.Name == "plain" or d.Name == "forced") then s[d.Name] = d.Size.X end
		end
		table.insert(rows, s)
	end
	out.forced = rows
end
workspace:SetAttribute("KitProbe3Out", game:GetService("HttpService"):JSONEncode(out))
```

## What must come back (and what came back)

- **break**: 14 parts, all 14 MeshParts, lying on the floor early and late (their middle half a stud up, about 7.5
  studs from it), `after.n = 0`. As measured.
- **field**: 80 specks early; they rise and spread (middle 4.5 -> 6.3 studs up, spread 2.4 -> 4.4); a speck moves
  about 4.9 studs a second. `after.n = 0`.
- **stones**: 24 parts; 8 of them MeshParts 0.2 s into the layer (the others blocks), all 24 at 2.2 s. `after.n = 0`.
- **cloud**: a scatter about 16 studs wide and deep at 0.25 s becomes the flat figure by 2.2 s: about 11.3 x 12
  studs, 0.13 deep (the cloud's own box at `size` 6: 11.4 x 10.9 x 0).
- **forced** (`ref` 28, `min` 0.25, `max` 4): the forced ring 7.8 studs at 28, 15.6 at 56, 3.9 at 14, 1.95 at 3,
  31.2 at 400; the plain ring 7.8 at every distance.
- The flare preset (`kitfx_flare`) is refused by the kit's rules until its three pictures are registered (page 23).

Seen once and not again in two tries: an effect played four seconds into a session, as its first, drew no mesh for
its whole 2.6 seconds (no refusal was counted that time: the count was not read). In every other run a mesh showed
0.06 to 0.4 s after the play, half a second into a client's life included.

## The miss, reproduced and bounded (ten cold sessions, 2026-11-16)

Studio can run a play session from a script and hand back what the server gives `StudioTestService:EndTest(...)`:
`StudioTestService:ExecutePlayModeAsync(args)` in the Edit datamodel - so ten cold sessions are one loop. Each
played `kitfx_forced` (two mesh layers, a life of 2.6 s) once, 2 to 5 seconds into the client's life, and logged the
time to each mesh, `VfxMesh.stats()` and when the player's character arrived.

- A mesh showed in **2 of 10** (0.36 s after the play, with the character already there; and 2.19 s after a play
  made at 2.3 s - the moment the character arrived). In **8 of 10 no mesh showed within 2.9 s**: the layers were
  over before their meshes were built.
- In all ten: refused 0, engine full 0, learned ceiling 0. It is NOT a refusal, and nothing counts it.
- Five more sessions timed the engine's own calls on one triangle: `CreateEditableMesh`, filling it and the
  fixed-size copy took under a millisecond; **`AssetService:CreateMeshPartAsync` took 1.15 to 1.65 s when it ran
  while the avatar was arriving (4 of 4 such calls) and 0.15 to 0.22 s otherwise** (this client ran in the
  background at about 24 frames a second: a focused client is quicker). A warm-up call made at the client's start
  did not prevent it: the next call that met the avatar's loading still took 1.15 s.

So: in a client's first seconds - while its avatar loads - the ENGINE's call that turns a mesh into a part takes
over a second, and the kit builds an effect's meshes one after another. An effect of a few meshes played then can
be over before they exist. What a game does about it: do not play a mesh effect at a player before that player's
character has loaded, or call `Vfx.prewarm(name)` after it has; meshes built once come back from the pool at once.
The kit's answer (2026-11-16): `Vfx.prewarmAtSpawn({ names })` waits for the avatar and makes the meshes ahead;
`Vfx.coldPlays()` counts every play of a preset whose meshes were not made, and warns of the ones made before
the avatar had loaded (12-runtime).

### The answer, proven the same way (twenty cold sessions, 2026-11-16)

The client script either plays `kitfx_forced` straight away (2 to 6 s in), or calls
`Vfx.prewarmAtSpawn({ "kitfx_forced" }, done)` and plays when `done` is called, or waits 5 s after its character
appeared and plays (not warm). It reports the time to each mesh, `Vfx.isWarm`, `Vfx.coldPlays()` and how many times the
kit warned.

- Straight away: **5 of 5 counted cold AND early, 5 of 5 warned of**; a mesh showed in 1 of the 5.
- After the spawn warm-up: **7 of 7 showed their meshes at once** (the first 0.02 to 0.08 s after the play, the second
  0.10 to 0.28 s), `isWarm` true, nothing counted. The warm-up ended 0.8 to 1.9 s after the character appeared.
- Not warm, 5 s after the character: 2 of 2 showed both meshes 0.17 s after the play; counted cold, not early, no
  warning. 1.5 s after the character: shown at 0.16 s and still called early (the 3 seconds are on the safe side).
- Found between the two runs and fixed: "early" ended the moment the avatar had loaded, and three plays made 0.02 to
  0.41 s after it showed no mesh with no warning. A play is early until `Vfx.SPAWN_QUIET` (3 s) after.

### Again on 24 meshes, after the review (ten cold sessions, 2026-11-16)

The first proof's effect built 2 meshes, and the pool then kept 8 in all: a warm-up of a bigger effect was thrown away
and still called warm. After the fix (the warm-up raises what the pool keeps; `isWarm` checks what it holds), the same
loop with `kitfx_stones` (a swarm of 24 stones), measuring the stage's parts as the layer plays:

- After `Vfx.prewarmAtSpawn`: 5 of 5 held 24 meshes in the pool at the play (`VfxMesh.stats().idle`), `isWarm` true,
  `done(cold)` named none; all 24 stones were meshes 0.01 s after the play - none made late. Nothing counted, no warning.
- Straight away (2 to 5 s in): 5 of 5 counted cold and early, 5 warned of; 8 of the 24 were meshes as the layer began
  (0.55 s), 10 at 0.8 s, all 24 at 2.0 s in four; in the fifth, played as the character appeared, none of the 24.
- Refused 0 in all ten.

### Stand-ins, and the clock that jumped (twenty-one cold sessions, 2026-11-16)

The client logs, every frame, the stage's clock (`stage.time`), its parts, meshes and parts seen (transparency < 1).
- A 2-mesh effect played straight away (10) and as the character arrived (5): not one frame of the layer's life with
  fewer than its 2 parts seen - the stand-in balls first, the meshes 0.15 to 0.37 s later; `VfxStage.standIns()` 2.
- A 24-stone swarm played as the character arrived (6): all 24 seen every frame of their life (blocks, then meshes one
  after another, all 24 by 2.1 to 2.7 s). Nothing removed them early.
- The clock: before the fix, a play made inside a long frame had `stage.time` 1.35 at its first frame 0.02 s after
  the play (and 0.80 at 0.66, 0.60 at 0.08): the stage's step took the Heartbeat's dt, the whole previous frame. After
  it, 8 of 8: the first frame's time is the wall time since the play (0.02 to 0.58 at 0.07 to 0.59).
