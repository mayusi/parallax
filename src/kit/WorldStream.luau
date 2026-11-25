-- WorldStream.luau (kit, server) — SENDING A PLAYER TO A PLACE in a world that streams (the owner's limitations list,
-- W-R03). With streaming on, nothing near the place a player is teleported to is loaded on their machine: moved
-- at once they stand in nothing, fall, or are paused by Roblox until the ground arrives. A world's blueprint names
-- its arrivals ("streaming": { "arrivals": [ { "name", "pos" } ] }: kit/lib/worldstream.luau) and the compiler
-- leaves each as a small unseen part in KitWorld.KitArrivals (a model that never streams out). This asks Roblox
-- for the ground round an arrival FIRST (Player:RequestStreamAroundAsync), then moves the character.
--   local WorldStream = require(ReplicatedStorage.kit.WorldStream)
--   local ok, why = WorldStream.arrive(player, "Keep gate")   -- yields until Roblox answers (TIMEOUT at most)
--   WorldStream.ahead(player, "Under the cliff")              -- the ground only: at the top of a long drop
-- -> true, nil | true, "late" | false, why
-- WHAT ROBLOX PROMISES (its Player API page, read 2026-11-15): the request yields until the region is sent or the
-- timeout passes, then returns NOTHING either way - no error on a timeout - and "no guarantees of what will be
-- streamed". So "late" is told by the clock: a request that took the whole TIMEOUT was given up by the engine
-- and the ground may not be there. The player is moved all the same (the game asked for the teleport); a game
-- that must not show bare ground sets StreamingIntegrityMode PauseOutsideLoadedArea, which the world lane's lock
-- asks of any world whose players move faster than a walk.
-- `deps` (optional, last) stands in for the engine in the kit's own spec, which runs this file as it is:
--   { root(), request(player, pos, timeout), place(character, pos), now(), warn(text) }
local WorldStream = {}

WorldStream.TIMEOUT = 5 -- seconds Roblox is given to bring the ground in before the player is moved all the same
WorldStream.LIFT = 3 -- studs: the character's middle stands this far over the arrival's point (an R6 rig's hip)

local function engine(): any
	local Workspace = game:GetService("Workspace")
	return {
		root = function()
			return Workspace:FindFirstChild("KitWorld")
		end,
		request = function(player: any, pos: any, timeout: number)
			player:RequestStreamAroundAsync(pos, timeout)
		end,
		place = function(character: any, pos: any)
			character:PivotTo(CFrame.new(pos + Vector3.new(0, WorldStream.LIFT, 0)))
		end,
		now = os.clock,
		warn = warn,
	}
end

-- the ground round an arrival asked for, nobody moved -> (found, late, why)
local function ask(deps: any, player: any, name: string): (any, boolean, string?)
	local part = WorldStream.arrivals(deps)[name]
	if not part then
		return nil, false, `no arrival "{name}" in this world (its blueprint's "streaming.arrivals" names them)`
	end
	local began = deps.now()
	local ok, err = pcall(deps.request, player, part.Position, WorldStream.TIMEOUT)
	local late = not ok or deps.now() - began >= WorldStream.TIMEOUT - 0.05
	if late then
		deps.warn(
			`[WorldStream] arrival "{name}": Roblox did not send the ground in {WorldStream.TIMEOUT} s{if ok
				then ""
				else ` ({tostring(err)})`}`
		)
	end
	return part, late, nil
end

-- the arrivals this world names -> { [name] = its part }
function WorldStream.arrivals(given: any?): { [string]: any }
	local deps = given or engine()
	local out = {}
	local root = deps.root()
	local folder = root and root:FindFirstChild("KitArrivals")
	if folder then
		for _, part in folder:GetChildren() do
			local name = part:GetAttribute("KitArrival")
			if type(name) == "string" then
				out[name] = part
			end
		end
	end
	return out
end

function WorldStream.arrive(player: any, name: string, given: any?): (boolean, string?)
	local deps = given or engine()
	local part, late, why = ask(deps, player, name)
	if not part then
		return false, why
	end
	-- (the player may have left, died or respawned while that yielded: the character is read NOW)
	local character = player.Character
	if player.Parent == nil or character == nil or character.Parent == nil then
		return false, "the player left, or has no character, before the place was loaded"
	end
	deps.place(character, part.Position)
	return true, if late then "late" else nil
end

-- the ground only (at the top of a drop, before a cutscene ends): nobody is moved
function WorldStream.ahead(player: any, name: string, given: any?): (boolean, string?)
	local deps = given or engine()
	local part, late, why = ask(deps, player, name)
	if not part then
		return false, why
	end
	return true, if late then "late" else nil
end

return WorldStream
