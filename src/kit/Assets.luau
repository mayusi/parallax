-- Assets (ReplicatedStorage.kit.Assets) — uploaded asset ids by LOGICAL NAME, so code never hardcodes numbers.
-- Source: assets/ids.json (written by `lune run kit asset-id <built file> <id>`), synced as ReplicatedStorage.AssetIds.
--   Assets.id("sounds", "explosion_big")    -> "rbxassetid://123" | nil
--   Assets.play("explosion_big", where?, props?) -> AudioPlayer | nil   where: Vector3 (3D at a point) | Instance
--       (attached) | nil (2D). ON THE AUDIO API (PARALLAX_FINAL_CLOSURE_SPEC Step 6): it plays through kit Sfx's graph
--       (Sfx.voice: the "sfx" bus unless props.Bus says), so its fader, snapshots and the master compressor apply.
--       props keep their old Sound names: Volume, PlaybackSpeed, RollOffMinDistance, RollOffMaxDistance, Looped
--       (+ Bus, Eq = { high, mid, low }); SoundGroup is ignored (the bus is the group)
--   Assets.sound("ui_click")                -> an unparented AudioPlayer (its Asset set) you wire yourself
--   Assets.missing()                        -> names requested but not uploaded yet (QA reads this)
-- Variations: if "explosion_big_2", "_3"... are uploaded too, play() picks one at random each time.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Assets = {}

local registry: any = {}
local module = ReplicatedStorage:FindFirstChild("AssetIds")
if module and module:IsA("ModuleScript") then
	local ok, data = pcall(require, module)
	if ok and type(data) == "table" then
		registry = data
	end
end

local missing: { [string]: boolean } = {}
local rng = Random.new()

function Assets.id(kind: string, name: string): string?
	local section = registry[kind]
	local id = section and section[name]
	if type(id) == "string" and id ~= "" then
		return id
	end
	local key = kind .. "." .. name
	if not missing[key] then
		missing[key] = true
		warn(`[Assets] {key} has no uploaded id yet — upload build/{kind}/{name}.* then: lune run kit asset-id`)
	end
	return nil
end

local function pickTake(name: string): string?
	local sounds = registry.sounds or {}
	local takes = {}
	if sounds[name] then
		table.insert(takes, sounds[name])
	end
	local n = 2
	while sounds[`{name}_{n}`] do
		table.insert(takes, sounds[`{name}_{n}`])
		n += 1
	end
	if #takes == 0 then
		return Assets.id("sounds", name)
	end
	return takes[rng:NextInteger(1, #takes)]
end

function Assets.sound(name: string): AudioPlayer?
	local id = pickTake(name)
	if not id then
		return nil
	end
	local p = Instance.new("AudioPlayer")
	p.Name = name
	p.Asset = id
	return p
end

-- kit Sfx, found when first needed (Assets is required by modules Sfx itself never loads)
local sfx: any = nil
local function Sfx(): any
	if sfx == nil then
		local m = script.Parent:FindFirstChild("Sfx")
		local ok, mod = false, nil
		if m then
			ok, mod = pcall(require, m)
		end
		sfx = if ok then mod else false
	end
	return sfx or nil
end

function Assets.play(name: string, where: (Vector3 | Instance)?, props: { [string]: any }?): AudioPlayer?
	local id = pickTake(name)
	if not id then
		return nil
	end
	local s = Sfx()
	if not s then
		warn("[Assets] no kit Sfx module beside Assets: nothing plays")
		return nil
	end
	local p: { [string]: any } = props or {}
	local handle = s.voice(id, {
		bus = if type(p.Bus) == "string" then p.Bus else "sfx",
		at = where,
		volume = tonumber(p.Volume),
		pitch = tonumber(p.PlaybackSpeed),
		near = tonumber(p.RollOffMinDistance),
		range = tonumber(p.RollOffMaxDistance),
		looped = p.Looped == true,
		eq = p.Eq,
	})
	return if handle then handle.player else nil
end

function Assets.missing(): { string }
	local out = {}
	for key in missing do
		table.insert(out, key)
	end
	table.sort(out)
	return out
end

return Assets
