--!strict
-- ZoneMood.luau — a colour grade per zone on the client (AAA gap W1: art direction per area): each zone KIND (open,
-- forest, water, stone - the world's ambience zones, derived from its blueprint) has a mood { tint = {r, g, b},
-- saturation, contrast, brightness }; where the player stands the moods blend by how present each kind is
-- (AmbienceRules.presence) and drive ONE local ColorCorrectionEffect (the server's WorldClock owns the sky and the
-- Atmosphere; this grade is the player's own, layered over it). Pure blend: ZoneMood.blend (spec-tested).
--
--   require(ReplicatedStorage.kit.ZoneMood).start(require(ReplicatedStorage.Shared.SampleRegionAmbience))  -- spec.moods
local ZoneMood = {}

ZoneMood.KINDS = { "open", "forest", "water", "stone" }
ZoneMood.TICK = 0.25
ZoneMood.EASE = 2 -- seconds to settle into a new zone's grade

local NEUTRAL = { tint = { 255, 255, 255 }, saturation = 0, contrast = 0, brightness = 0 }

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- the grade where these kinds are this present: a presence-weighted average of the kinds' moods (a kind without a
-- mood counts as neutral; nothing present = neutral)
function ZoneMood.blend(moods: any, presence: { [string]: number }): any
	local tint, sat, con, bri, total = { 0, 0, 0 }, 0, 0, 0, 0
	for _, kind in ZoneMood.KINDS do
		local w = presence[kind]
		if finite(w) and (w :: number) > 0 then
			local m = if type(moods) == "table" and type(moods[kind]) == "table" then moods[kind] else NEUTRAL
			local t = if type(m.tint) == "table" then m.tint else NEUTRAL.tint
			for i = 1, 3 do
				tint[i] += (if finite(t[i]) then t[i] else 255) * (w :: number)
			end
			sat += (if finite(m.saturation) then m.saturation else 0) * (w :: number)
			con += (if finite(m.contrast) then m.contrast else 0) * (w :: number)
			bri += (if finite(m.brightness) then m.brightness else 0) * (w :: number)
			total += w :: number
		end
	end
	if total <= 0 then
		return NEUTRAL
	end
	return {
		tint = { tint[1] / total, tint[2] / total, tint[3] / total },
		saturation = sat / total,
		contrast = con / total,
		brightness = bri / total,
	}
end

function ZoneMood.start(spec: any): () -> ()
	local Lighting = game:GetService("Lighting")
	local Players = game:GetService("Players")
	local RunService = game:GetService("RunService")
	local Workspace = game:GetService("Workspace")
	local AmbienceRules = require(script.Parent:WaitForChild("AmbienceRules"))
	assert(RunService:IsClient(), "ZoneMood.start is client-only (a grade is the player's own)")
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "KitZoneMood"
	cc.Parent = Lighting
	local moods = if type(spec) == "table" then spec.moods else nil
	local acc = 0
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		acc += dt
		if acc < ZoneMood.TICK then
			return
		end
		local step = acc
		acc = 0
		local ch = Players.LocalPlayer.Character
		local root = ch and ch:FindFirstChild("HumanoidRootPart") :: BasePart?
		local cam = Workspace.CurrentCamera
		local at = if root then root.Position elseif cam then cam.Focus.Position else nil
		if not at then
			return
		end
		local g = ZoneMood.blend(moods, AmbienceRules.presence(spec, at.X, at.Z))
		local k = math.clamp(step / ZoneMood.EASE, 0, 1)
		local c = cc.TintColor
		cc.TintColor = Color3.fromRGB(
			c.R * 255 + (g.tint[1] - c.R * 255) * k,
			c.G * 255 + (g.tint[2] - c.G * 255) * k,
			c.B * 255 + (g.tint[3] - c.B * 255) * k
		)
		cc.Saturation += (g.saturation - cc.Saturation) * k
		cc.Contrast += (g.contrast - cc.Contrast) * k
		cc.Brightness += (g.brightness - cc.Brightness) * k
	end)
	return function()
		conn:Disconnect()
		cc:Destroy()
	end
end

return ZoneMood
