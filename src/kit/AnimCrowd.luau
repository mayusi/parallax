--!strict
-- AnimCrowd (ReplicatedStorage.kit.AnimCrowd) — MANY CHARACTERS at once (the owner's method lists 2026-11-13: crowd
-- animation): how often the kit's own per-frame animation work is done for each tracked character - every frame
-- for the nearest, every 2nd, every 4th, not at all past `far` - nearest first inside two budgets, a frame's work
-- spread evenly (the rule: AnimRules.crowd / due, spec'd). Roblox throttles its OWN animation by distance already
-- (Animator.EvaluationThrottled); this is for what the kit adds after it: foot placement (Anim.feet asks here),
-- and any game loop that asks AnimCrowd.due(character).
--
--   AnimCrowd.track(character)      -- an NPC, a remote player: from now on it has a rate
--   AnimCrowd.untrack(character)
--   AnimCrowd.due(character)        -- is its kit work done on THIS frame? (a character never tracked: always)
--   AnimCrowd.rate(character)       -- 1, 2, 4 or 0 (nil: not tracked)
--   AnimCrowd.limits = { near, mid, far, full, half }   -- optional: other bands and budgets (AnimRules' defaults)
--
-- Distances are from the camera (on a server, which has none: from the origin of AnimCrowd.viewer, a Vector3 the game
-- may set). Studio-unproven (written 2026-11-14): the plan's maths is spec'd, the loop below is not.
local RunService = game:GetService("RunService")

local AnimRules = require(script.Parent.AnimRules)

local AnimCrowd = {}

AnimCrowd.limits = nil :: AnimRules.CrowdLimits?
AnimCrowd.viewer = nil :: Vector3?
AnimCrowd.REFRESH = 15 -- frames between two plans (a plan is a sort: not needed every frame)

local tracked: { [Model]: boolean } = {}
local plan: { [any]: { number } } = {}
local frame = 0
local conn: RBXScriptConnection? = nil

local function eye(): Vector3
	local cam = workspace.CurrentCamera
	if AnimCrowd.viewer then
		return AnimCrowd.viewer
	end
	return if cam then cam.CFrame.Position else Vector3.zero
end

local function refresh()
	local ids: { any }, distances: { number } = {}, {}
	local from = eye()
	for character in tracked do
		if character.Parent then
			table.insert(ids, character)
			local root = character:FindFirstChild("HumanoidRootPart")
			local at = if root and root:IsA("BasePart") then root.Position else character:GetPivot().Position
			table.insert(distances, (at - from).Magnitude)
		else
			tracked[character] = nil
		end
	end
	plan = AnimRules.crowdPlan(ids, distances, AnimCrowd.limits)
end

local function start()
	if conn then
		return
	end
	conn = RunService.Heartbeat:Connect(function()
		frame += 1
		if (frame - 1) % math.max(1, math.floor(AnimCrowd.REFRESH)) == 0 then
			refresh()
		end
		if next(tracked) == nil and conn then
			conn:Disconnect()
			conn = nil
		end
	end)
end

function AnimCrowd.track(character: Model)
	tracked[character] = true
	refresh()
	start()
end

function AnimCrowd.untrack(character: Model)
	tracked[character] = nil
	plan[character] = nil
end

function AnimCrowd.rate(character: Model): number?
	local p = plan[character]
	return if p then p[1] else nil
end

function AnimCrowd.due(character: Model): boolean
	local p = plan[character]
	if not p then
		return true
	end
	return AnimRules.due(p[1], frame, p[2])
end

return AnimCrowd
