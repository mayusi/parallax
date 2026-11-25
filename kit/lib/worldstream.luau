--!strict
-- worldstream.luau (kit) - LOADING INTENT for a world that streams (the owner's limitations list, W-R03: "cell
-- packaging does not express encounter-aware loading intent ... speed, teleports, vertical approach or
-- critical-object priority").
--
-- "streaming": { "cell": 256 } cuts a world into cells by PLACE alone. Roblox then streams each cell in by its
-- distance from the player, and that is right for a walk. It is wrong in four cases the cells cannot know of, and
-- each is a word in the blueprint now:
--   * SPEED. What lies within StreamingMinRadius of a player (64 studs unless the game says more) streams in at
--     the highest priority and never streams out; past it, up to StreamingTargetRadius (1,024), a region arrives
--     when it arrives. A walker covers 64 studs in 4 seconds. A player on a horse, a cart or a dash covers it in
--     one: the ground may not be there yet. "streaming": { "speed": <the fastest a player moves, studs a second> }
--     and the lock holds the game to LEAD seconds of that way as its StreamingMinRadius, twice that as its
--     StreamingTargetRadius (Roblox's page: equal radii leave no buffer), and - for players faster than a walk -
--     StreamingIntegrityMode PauseOutsideLoadedArea, the engine's own guard against ground that is not there.
--     LEAD is the kit's choice, not Roblox's: its page gives no number. Its page also says a large minimum radius
--     costs every player memory and recommends 64: the lock's line says so when it asks for more.
--   * A FALL (the vertical approach). A drop is crossed faster than any road, and its landing is as far away as
--     the drop is high. "fall": <the highest drop a player takes, studs>: where that is past the game's
--     StreamingMinRadius, the landing must be asked for ahead - a named arrival and WorldStream.ahead(player,
--     name) from the top - or the lock says so. (A radius as large as the drop would load that far in EVERY
--     direction round every player: the first cut did that.)
--   * WHAT MUST NEVER BE MISSING. A landmark you steer by from across the map, the floor of an arena: a step says
--     "stream": "always" (never streams out: Roblox's Persistent) or "whole" (arrives and leaves as ONE piece,
--     never half a bridge: Atomic) or "area" (with its place, meant). "always" is for a few things: Roblox's own
--     page says overuse hurts, so a world's "always" parts are counted and capped. A town says it of its
--     landmark house: "landmark": { "stream": ... }.
--   * A TELEPORT. Nothing near the place a player is sent to is loaded. "arrivals": [ { "name", "pos" } ] names
--     the places; the runtime (src/kit/WorldStream.luau) asks Roblox for the ground there BEFORE it moves the
--     player (Player:RequestStreamAroundAsync - which, by its own page, promises nothing: see the runtime).
-- (Roblox's streaming page and the Player / Workspace API pages, read 2026-11-15.)
-- Pure: no requires, no files. The game's project file is read by kit/lib/lanelocks.luau, never written.
local Stream = {}

Stream.LEAD = 4 -- seconds of ground ahead of a moving player that must already be loaded
Stream.MIN_RADIUS = 64 -- Roblox's own StreamingMinRadius when a game says nothing
Stream.WALK = 16 -- studs a second: a Roblox character on foot
Stream.SPEED_MOST = 2000 -- studs a second: past this it is no player's speed
Stream.ALWAYS_MOST = 400 -- parts a world may keep loaded for every player, always
Stream.ARRIVAL_DROP = 30 -- studs: an arrival stands this far over a floor at most
Stream.WORDS = { always = "Persistent", whole = "Atomic", area = "" }

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- what a "streaming" block says of how its players move -> { speed, fall }, and what is wrong with it
function Stream.intent(streaming: any): (any, { string })
	local problems = {}
	local out = { speed = nil :: number?, fall = 0 }
	if type(streaming) ~= "table" then
		return out, problems
	end
	if streaming.speed ~= nil then
		-- (never under a walk: a Roblox character on foot does 16, and a world that said 1 would ask nothing)
		if not number(streaming.speed) or streaming.speed < Stream.WALK or streaming.speed > Stream.SPEED_MOST then
			table.insert(
				problems,
				`"streaming.speed" is the fastest a player moves, in studs a second: {Stream.WALK} (on foot) to {Stream.SPEED_MOST} (got {tostring(
					streaming.speed
				)})`
			)
		else
			out.speed = streaming.speed
		end
	end
	if streaming.fall ~= nil then
		if not number(streaming.fall) or streaming.fall < 0 then
			table.insert(
				problems,
				`"streaming.fall" is the highest drop a player takes, in studs: 0 or more (got {tostring(streaming.fall)})`
			)
		else
			out.fall = streaming.fall
		end
	end
	return out, problems
end

-- the StreamingMinRadius a world's players need: LEAD seconds of their fastest way (the drop is asked for ahead,
-- never by a radius)
function Stream.need(intent: any): number
	local speed = if number(intent.speed) then intent.speed else Stream.WALK
	return math.max(Stream.MIN_RADIUS, math.ceil(speed * Stream.LEAD))
end

-- ... and the StreamingTargetRadius: twice that (a target equal to the minimum leaves no buffer)
function Stream.target(intent: any): number
	return 2 * Stream.need(intent)
end

-- a step's "stream" word -> Roblox's ModelStreamingMode ("" = by its place), or what is wrong with the word
function Stream.mode(word: any): (string?, string?)
	if word == nil then
		return "", nil
	end
	local mode = if type(word) == "string" then Stream.WORDS[word] else nil
	if mode == nil then
		return nil,
			`"stream" is "always" (never streams out: a landmark steered by from afar), "whole" (arrives and leaves as one piece: a bridge, an arena's floor) or "area" (with its place) (got {tostring(
				word
			)})`
	end
	return mode, nil
end

-- the places a player is sent to -> { { name, pos } }, and what is wrong with the list
function Stream.arrivals(streaming: any): ({ any }, { string })
	local out, problems = {}, {}
	local list = if type(streaming) == "table" then streaming.arrivals else nil
	if list == nil then
		return out, problems
	end
	if type(list) ~= "table" then
		return out, { '"streaming.arrivals" is a list: [ { "name": "Keep gate", "pos": [x, y, z] } ]' }
	end
	local seen: { [string]: boolean } = {}
	for i, a in list do
		local pos = if type(a) == "table" then a.pos else nil
		if type(a) ~= "table" or type(a.name) ~= "string" or a.name == "" then
			table.insert(problems, `arrivals[{i}] needs a "name" (what the game calls the place)`)
		elseif seen[a.name] then
			table.insert(problems, `two arrivals are named "{a.name}": the game could not say which`)
		elseif type(pos) ~= "table" or not (number(pos[1]) and number(pos[2]) and number(pos[3])) then
			table.insert(problems, `arrival "{a.name}" needs "pos": [x, y, z] (where the player's feet stand)`)
		else
			seen[a.name] = true
			table.insert(out, { name = a.name, pos = { pos[1], pos[2], pos[3] } })
		end
	end
	return out, problems
end

return Stream
