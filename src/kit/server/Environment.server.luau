-- Environment.server.luau (kit) — builds every world's terrain + lighting when the server starts
-- (assets/worlds/*.json "lighting" / "terrain"; Rojo cannot carry them, so they are applied here).
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Environment = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Environment"))

Workspace:WaitForChild("KitWorld", 10)
local started = os.clock()
local count = Environment.applyAll()
if count > 0 then
	print(string.format("[Environment] %d world environment(s) applied in %.2fs", count, os.clock() - started))
end
-- the world's real meshes (trees, rocks, cliffs) replace their placeholders
local WorldMeshes = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("WorldMeshes"))
local made, notThere, missing = WorldMeshes.swapAll()
if made + notThere > 0 then
	-- (a mesh that is not there has its stand-in: a solid thing its box, a dressed building its own walls; a failed
	-- load is tried again in the background - KitWorld's KitMeshesReady says when all is settled)
	print(
		if notThere > 0
			then string.format(
				"[WorldMeshes] %d mesh(es) placed, %d not there (%d never uploaded): stand-ins shown",
				made,
				notThere,
				missing
			)
			else string.format("[WorldMeshes] %d mesh(es) placed", made)
	)
end
-- sound that lives in the space: Acoustic Simulation on, foliage / flames / rugs let sound through (a game opts out
-- with the Workspace attribute KitAcousticsOff)
if Workspace:GetAttribute("KitAcousticsOff") ~= true then
	local a = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Acoustics")).start()
	-- (character sounds on the new audio API are the PLACE's setting - SoundService.CharacterSoundsUseNewApi, which a
	--  script cannot always set: not a fault, and kit Foley plays the footsteps either way. The V3 list: no false
	--  character warnings at boot. Only the simulation is the kit's to say.)
	print(
		string.format(
			"[Acoustics] simulation %s%s, %d part(s) marked to let sound through",
			if a.simulation then "on" else "UNAVAILABLE on this build",
			if a.characterSounds then ", character sounds on the new audio API" else "",
			a.passed
		)
	)
end
Workspace:SetAttribute("KitEnvironmentReady", true)
