--!strict
-- Acoustics.luau — sound that lives in the space (AAA gap S1): Roblox's Acoustic Simulation muffles sound behind
-- walls, bends it round corners and reverbs it off what is around, all by itself, for the Advanced Audio API (kit Sfx
-- plays through it). Acoustics.start (server) turns it on and lets sound through what should not stop it: every part
-- the world compiler marked KitAudioPass (leaves, grass, flames, rugs, mist, foliage meshes) gets AudioCanCollide off,
-- now and when it appears later (WorldMeshes swaps placeholders for meshes at runtime).
--
--   require(ReplicatedStorage.kit.Acoustics).start()          -- once, on the server
local CollectionService = game:GetService("CollectionService")
local SoundService = game:GetService("SoundService")
local Workspace = game:GetService("Workspace")

local Acoustics = {}

-- set a property that may be a boolean or a RolloutState-style enum on this engine build; false when it is unknown
local function enable(inst: Instance, prop: string): boolean
	for _, v in { true, (Enum :: any).RolloutState and (Enum :: any).RolloutState.Enabled or nil } do
		if v ~= nil then
			local ok = pcall(function()
				(inst :: any)[prop] = v
			end)
			if ok then
				return true
			end
		end
	end
	return false
end

local function pass(part: Instance)
	if part:IsA("BasePart") and part:GetAttribute("KitAudioPass") == true then
		pcall(function()
			(part :: any).AudioCanCollide = false
		end)
	end
end

-- -> { simulation, characterSounds, passed }: what this engine build accepted
function Acoustics.start(): { simulation: boolean, characterSounds: boolean, passed: number }
	local out = {
		simulation = enable(SoundService, "AcousticSimulationEnabled"),
		characterSounds = enable(SoundService, "CharacterSoundsUseNewApi"),
		passed = 0,
	}
	for _, d in Workspace:GetDescendants() do
		if d:IsA("BasePart") and d:GetAttribute("KitAudioPass") == true then
			pass(d)
			out.passed += 1
		end
	end
	Workspace.DescendantAdded:Connect(pass)
	CollectionService:GetInstanceAddedSignal("KitAudioPass"):Connect(pass)
	return out
end

return Acoustics
