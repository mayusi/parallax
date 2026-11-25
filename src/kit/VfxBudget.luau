-- VfxBudget (kit) - what the VFX runtime may spend, as rules: pure, no services, numbers and tables only.
-- The owner's limitations file (2026-11-15):
--   F-R04  "Idle-pool caps do not bound active cross-effect demand": the mesh pool capped what it KEPT, nothing capped
--          what every effect together had IN USE. ADMISSION: one count of built meshes in use across all effects
--          (always kept), and - when a GAME sets a budget - a ceiling, a share of it kept back for cues marked
--          critical, and a limit on fresh builds started a second. No budget is set by the kit itself.
--   F-R06  "Impact quality tiers chiefly change concurrency and culling": a detail level set how many impacts play and
--          how far away - not what each one is made of. TIERS: a layer says the lowest level it plays at (`tier`) and
--          how much of its emission each level keeps (`tierCount`); a level then really drops layers and particles.
local VfxBudget = {}

-- ---------------------------------------------------------------------------------------------- detail tiers (F-R06)
VfxBudget.LEVELS = { "Low", "Medium", "High" }
local RANK = { Low = 1, Medium = 2, High = 3 }

-- a level's place (1 = Low .. 3 = High); nil for what is not a level
function VfxBudget.rank(level: any): number?
	return if type(level) == "string" then RANK[level] else nil
end

-- does a layer play at this level: `tier` is the LOWEST level it plays at (nil: it plays at every level - a core
-- layer); a level that is not one (nil: nobody set a detail) plays everything
function VfxBudget.plays(tier: any, level: any): boolean
	local need, have = VfxBudget.rank(tier), VfxBudget.rank(level)
	if need == nil or have == nil then
		return true
	end
	return have >= need
end

-- how much of a layer's emission a level keeps: tierCount = { Low = 0.4, Medium = 0.7 } (a level not named: all of it)
function VfxBudget.factor(tierCount: any, level: any): number
	if type(tierCount) ~= "table" or VfxBudget.rank(level) == nil then
		return 1
	end
	local f = tierCount[level]
	if type(f) ~= "number" or f ~= f then
		return 1
	end
	return math.clamp(f, 0, 1)
end

local function scaled(v: any, f: number): any
	if type(v) == "number" then
		if v <= 0 then
			return v -- (a layer written to emit nothing emits nothing at every level)
		end
		return math.max(1, math.floor(v * f + 0.5)) -- (a layer that plays keeps one particle at least)
	end
	if type(v) == "table" and #v == 2 and type(v[1]) == "number" and type(v[2]) == "number" then
		return { math.max(1, math.floor(v[1] * f + 0.5)), math.max(1, math.floor(v[2] * f + 0.5)) }
	end
	return v -- (a curve, or nothing: left as it is)
end

-- one layer as a level plays it: nil when the level drops it; else the layer (the SAME table when nothing changes, a
-- copy with its `count` and `rate` cut when its tierCount says so). given: what the kit's own rule gives this layer
-- (VfxBudget.auto) - read only where the layer says nothing of its own
function VfxBudget.layerAt(el: any, level: any, given: any?): any?
	if type(el) ~= "table" then
		return el
	end
	local tier = if el.tier ~= nil then el.tier elseif given then given.tier else nil
	local share = if el.tierCount ~= nil then el.tierCount elseif given then given.tierCount else nil
	if not VfxBudget.plays(tier, level) then
		return nil
	end
	local f = VfxBudget.factor(share, level)
	if f >= 1 then
		return el
	end
	local c = table.clone(el)
	c.count = scaled(el.count, f)
	c.rate = scaled(el.rate, f)
	if type(el.twin) == "table" and el.twin.count ~= nil then -- (a twin emitter's own count is cut with its layer's)
		c.twin = table.clone(el.twin)
		c.twin.count = scaled(el.twin.count, f)
	end
	return c
end

-- a preset's layers as a level plays them -> (the layers kept, the names of the ones dropped). auto: true = with the
-- kit's own tiers for the layers that say none (as the stage plays them)
function VfxBudget.tiered(layers: any, level: any, auto: boolean?): ({ any }, { string })
	local kept, dropped = {}, {}
	local plan = if auto then VfxBudget.auto(layers) else {}
	for i, el in if type(layers) == "table" then layers else {} do
		local got = VfxBudget.layerAt(el, level, plan[i])
		if got == nil then
			table.insert(dropped, if type(el.name) == "string" then el.name else `layers[{i}]`)
		else
			table.insert(kept, got)
		end
	end
	return kept, dropped
end

-- ------------------------------------------------------------------------------------------- the kit's own tiers
-- EVERY effect is tiered, not only the ones an author marked (the owner, 2026-11-15: "tier the kit's own presets for
-- real"): a layer that says no "tier" / "tierCount" of its own gets one from this rule, read off what the layer IS.
--   never touched   what carries the beat and the feel: sound, shake, screen, fov, impact, world, lens, highlight,
--                   glow, crater, decal, beam, trail
--   emission        a sprite, a swarm or debris of 6 or more (count, or rate a second) keeps 0.4 of it at Low and 0.7
--                   at Medium; of 3 to 5, 0.6 at Low
--   lights          of the lights that start at one moment, the strongest (range x brightness) stays; the others
--                   play from Medium
--   meshes          by ELEMENT - the meshes that start at one moment, at one place, of one shape, aimed one way: the
--                   shells of one thing (a beam's core, body and haze). Of an element's shells, ranked by how solid
--                   each is (its least transparency: the core before the haze), then by how much there is of it (its
--                   life x its largest size): the top 0.4 (one at least) play at every level, down to 0.75 from
--                   Medium, the rest at High only. So NO element is ever dropped whole - a level thins a thing's
--                   shells, it never takes the thing away. A layer marked "critical" is never tiered
-- "One moment": the same "at" (a named moment, or the same tenth of a second). An author's own tier always wins.
-- (begin of the tier rule - kit/vfx/player/player.js `autoTiers` is the same arithmetic; a spec runs both on every preset)
local CORE_KINDS = {
	sound = true,
	shake = true,
	screen = true,
	fov = true,
	impact = true,
	world = true,
	lens = true,
	highlight = true,
	glow = true,
	crater = true,
	decal = true,
	beam = true,
	trail = true,
}
local EMITS = { sprite = true, swarm = true, debris = true }

local function momentOf(el: any): string
	local at = el.at
	if type(at) == "string" then
		return at
	end
	if type(at) ~= "number" or at ~= at then
		return "0"
	end
	return tostring(math.floor(at * 10 + 0.5))
end

-- the largest a layer's "scale" gets: a number, [x, y, z], keys [[u, number | [x, y, z]], ...], or { from, to }
local function sizeOf(scale: any): number
	if type(scale) == "number" then
		return math.abs(scale)
	end
	if type(scale) ~= "table" then
		return 1
	end
	local most = 0
	if scale.from ~= nil or scale.to ~= nil then -- an ease written out: { from, to, ease, keys }
		for _, key in { "from", "to" } do
			local v = scale[key]
			if type(v) == "number" then
				most = math.max(most, math.abs(v))
			elseif type(v) == "table" then
				for i = 1, #v do
					if type(v[i]) == "number" then
						most = math.max(most, math.abs(v[i]))
					end
				end
			end
		end
		return if most > 0 then most else 1
	end
	for i = 1, #scale do
		local v = scale[i]
		if type(v) == "number" then
			most = math.max(most, math.abs(v))
		elseif type(v) == "table" then
			local inner = v[2]
			if type(inner) == "number" then
				most = math.max(most, math.abs(inner))
			elseif type(inner) == "table" then
				for _, x in inner do
					if type(x) == "number" then
						most = math.max(most, math.abs(x))
					end
				end
			else
				for _, x in v do
					if type(x) == "number" then
						most = math.max(most, math.abs(x))
					end
				end
			end
		end
	end
	return if most > 0 then most else 1
end

local function amount(v: any): number
	if type(v) == "number" then
		return v
	end
	if type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" then
		return math.max(v[1], v[2])
	end
	return 0
end

-- the least / the most a keyed number gets: a number, or keys [[u, value], ...]
local function leastOf(v: any, default: number): number
	if type(v) == "number" then
		return v
	end
	if type(v) ~= "table" then
		return default
	end
	local least: number? = nil
	for _, k in v do
		local x = if type(k) == "table" then k[2] else k
		if type(x) == "number" and (least == nil or x < least) then
			least = x
		end
	end
	return least or default
end

local function mostOf(v: any, default: number): number
	if type(v) == "number" then
		return v
	end
	if type(v) ~= "table" then
		return default
	end
	local most: number? = nil
	for _, k in v do
		local x = if type(k) == "table" then k[2] else k
		if type(x) == "number" and (most == nil or x > most) then
			most = x
		end
	end
	return most or default
end

-- a point as a key (hundredths of a stud): two layers at one place give the same text
local function vecKey(v: any): string
	if type(v) ~= "table" then
		return ""
	end
	local out = {}
	for i = 1, 3 do
		local x = v[i]
		local n = if type(x) == "number" and x == x then math.floor(x * 100 + 0.5) else 0
		n = math.clamp(n, -1e9, 1e9)
		if n == 0 then
			n = 0
		end
		out[i] = string.format("%d", n)
	end
	return table.concat(out, ",")
end

-- the ELEMENT a mesh layer is a shell of: the meshes that start at one moment, at one place, of one shape, aimed one
-- way (a beam's core, body and haze; a ball's skin and core). A baked sequence is its own element by its name
local function elementOf(el: any): string
	local seq = if type(el.params) == "table" and type(el.params.seq) == "string" then el.params.seq else ""
	return table.concat({
		momentOf(el),
		if type(el.shape) == "string" then el.shape else "",
		vecKey(el.point),
		vecKey(el.aim),
		seq,
	}, "|")
end

-- a preset's layers -> for each layer (by its place in the list) what the rule gives it: { tier = ?, tierCount = ? },
-- or nothing for a layer it leaves alone or that says its own
function VfxBudget.auto(layers: any): { [number]: { tier: string?, tierCount: { [string]: number }? } }
	local plan: { [number]: { tier: string?, tierCount: { [string]: number }? } } = {}
	if type(layers) ~= "table" then
		return plan
	end
	type Ranked = { i: number, own: boolean, solid: number, much: number }
	local lights: { [string]: { Ranked } } = {}
	local lightOrder: { string } = {}
	local elements: { [string]: { Ranked } } = {}
	local order: { string } = {}
	for i, el in layers do
		if type(el) ~= "table" or CORE_KINDS[el.kind] then
			continue
		end
		-- a layer that says its own tier, or is a cue that must not be lost, keeps its PLACE in its group (so naming one
		-- never moves another) but is given nothing
		local own = el.tier ~= nil or el.tierCount ~= nil or el.critical == true
		if EMITS[el.kind] then
			if own then
				continue
			end
			local n = math.max(amount(el.count), amount(el.rate))
			if n >= 6 then
				plan[i] = { tierCount = { Low = 0.4, Medium = 0.7 } }
			elseif n >= 3 then
				plan[i] = { tierCount = { Low = 0.6 } }
			end
		elseif el.kind == "light" then
			local m = momentOf(el)
			if lights[m] == nil then
				lights[m] = {}
				table.insert(lightOrder, m)
			end
			table.insert(
				lights[m],
				{ i = i, own = own, solid = 0, much = mostOf(el.range, 0) * mostOf(el.brightness, 0) }
			)
		elseif el.kind == "mesh" then
			local key = elementOf(el)
			if elements[key] == nil then
				elements[key] = {}
				table.insert(order, key)
			end
			local life = if type(el.life) == "number" and el.life > 0 then el.life else 1
			table.insert(elements[key], {
				i = i,
				own = own,
				solid = 1 - math.clamp(leastOf(el.transparency, 0), 0, 1),
				much = life * sizeOf(el.scale),
			})
		end
	end
	local function ranked(group: { Ranked })
		table.sort(group, function(a, b)
			if a.solid ~= b.solid then
				return a.solid > b.solid
			end
			if a.much ~= b.much then
				return a.much > b.much
			end
			return a.i < b.i
		end)
	end
	for _, m in lightOrder do
		local group = lights[m]
		ranked(group)
		for r, g in group do
			if r > 1 and not g.own then
				plan[g.i] = { tier = "Medium" }
			end
		end
	end
	for _, key in order do
		local group = elements[key]
		ranked(group)
		local n = #group
		local core = math.max(1, math.floor(n * 0.4 + 0.5))
		local mid = math.max(core, math.ceil(n * 0.75))
		for r, g in group do
			if g.own then
				continue
			end
			if r > mid then
				plan[g.i] = { tier = "High" }
			elseif r > core then
				plan[g.i] = { tier = "Medium" }
			end
		end
	end
	return plan
end
-- (end of the tier rule)

-- what is wrong with a preset's tiers, in words ({} = nothing): a tier that is not a level, a tierCount that names no
-- level or is not a share, and a preset of which NOTHING is left at Low (an effect a low device would not see at all)
function VfxBudget.problems(layers: any): { string }
	local out = {}
	local any, core = false, false
	for i, el in if type(layers) == "table" then layers else {} do
		if type(el) ~= "table" then
			continue
		end
		local where = `layers[{i}]{if type(el.name) == "string" then "(" .. el.name .. ")" else ""}`
		if el.tier ~= nil then
			any = true
			if VfxBudget.rank(el.tier) == nil then
				table.insert(out, `{where}.tier: tier is the lowest level the layer plays at - Low | Medium | High`)
			end
		end
		if el.tierCount ~= nil then
			any = true
			if type(el.tierCount) ~= "table" then
				table.insert(
					out,
					`{where}.tierCount: tierCount is \{ Low = 0.4, Medium = 0.7 \}: the share of its count each level keeps`
				)
			else
				for k, v in el.tierCount do
					if VfxBudget.rank(k) == nil then
						table.insert(out, `{where}.tierCount: "{tostring(k)}" is not a level (Low | Medium | High)`)
					elseif type(v) ~= "number" or v ~= v or v <= 0 or v > 1 then
						table.insert(
							out,
							`{where}.tierCount.{k}: a share above 0 and at most 1 (to drop the layer at a level, give it a "tier")`
						)
					end
				end
			end
		end
		if VfxBudget.plays(el.tier, "Low") then
			core = true
		end
	end
	if any and not core then
		table.insert(
			out,
			`no layer plays at Low: every layer has a "tier" above it - a low device would see nothing of this effect (leave its core layers without a tier)`
		)
	end
	return out
end

-- ------------------------------------------------------------------------------------------------- admission (F-R04)
-- A BUDGET is { max, reserve, perSecond }: built meshes in use at once over every effect; of those, the last `reserve`
-- only for layers marked critical (a cue that must not be lost); fresh builds STARTED in any one second (a build
-- yields a quarter of a second: a burst stalls). There is NO budget unless a game sets one (VfxMesh.setBudget):
-- the kit does not know what a client can hold - Sample Game's logs say "about eight EditableMeshes", most of the kit's
-- own effects ask for more than that at once, and a fixed ceiling cut 86 of 102 presets down to their first six mesh
-- layers (a review, 2026-11-15). The COUNT is always kept (VfxMesh.stats()); the ceiling is the game's to set, from
-- a measurement in Studio.

-- a budget as the rules take it -> (the budget, nil) or (nil, what is wrong with it)
function VfxBudget.budget(o: any): ({ max: number, reserve: number, perSecond: number }?, string?)
	if type(o) ~= "table" then
		return nil, "a budget is { max = 8, reserve = 2, perSecond = 6 }"
	end
	local function whole(v: any, lo: number, hi: number): boolean
		return type(v) == "number" and v == v and v == math.floor(v) and v >= lo and v <= hi
	end
	local max, reserve, perSecond = o.max, o.reserve or 0, o.perSecond or 1000
	if not whole(max, 1, 100000) then
		return nil, "max is a whole number of meshes, 1 or more"
	end
	if not whole(reserve, 0, max - 1) then
		return nil, "reserve is a whole number from 0 to max - 1 (the share kept for critical layers)"
	end
	if not whole(perSecond, 1, 100000) then
		return nil, "perSecond is a whole number of fresh builds, 1 or more"
	end
	return { max = max, reserve = reserve, perSecond = perSecond }, nil
end

-- the budget an ask is held to: the set one (nil = none), cut to the ceiling the engine showed this client (learned:
-- the meshes that were in use when it refused one; nil = it refused nothing yet). With no budget set, a learned
-- ceiling is one by itself, with nothing kept back. Of a cut budget a quarter at most is kept for critical cues
function VfxBudget.ceiling(budget: any, learned: number?): { max: number, reserve: number, perSecond: number }?
	if learned == nil or (budget ~= nil and budget.max <= learned) then
		return budget
	end
	local max = math.max(1, math.floor(learned))
	local reserve = if budget then budget.reserve else 0
	return {
		max = max,
		reserve = math.min(reserve, math.floor(max / 4)),
		perSecond = if budget then budget.perSecond else 1000,
	}
end

-- may one more mesh be IN USE now (a fresh build or one handed out of the pool). active: meshes in use now;
-- critical: the layer is a cue that must not be lost; budget: nil = none set, everything is admitted
function VfxBudget.admit(active: number, critical: boolean, budget: any): (boolean, string?)
	if budget == nil then
		return true, nil
	end
	local ceiling = if critical then budget.max else budget.max - budget.reserve
	if active >= ceiling then
		return false,
			if critical
				then `{active} meshes are in use, the most there may be`
				else `{active} meshes are in use: the last {budget.reserve} are kept for critical cues`
	end
	return true, nil
end

-- may one more FRESH build be started now (a mesh out of the pool costs no build: it is never asked this). recent:
-- the clock times of the fresh builds started lately; a critical one is not held by the rate
function VfxBudget.mayStart(recent: { number }, now: number, critical: boolean, budget: any): (boolean, string?)
	if budget == nil or critical then
		return true, nil
	end
	local lately = 0
	for _, t in recent do
		if now - t < 1 and now - t >= 0 then
			lately += 1
		end
	end
	if lately >= budget.perSecond then
		return false, `{lately} meshes were started in the last second, the most there may be`
	end
	return true, nil
end

-- the list of recent build times with the old ones (over a second) dropped and `now` added: what `mayStart` reads next
function VfxBudget.started(recent: { number }, now: number): { number }
	local out = {}
	for _, t in recent do
		if now - t < 1 and now - t >= 0 then
			table.insert(out, t)
		end
	end
	table.insert(out, now)
	return out
end

-- HOW MANY RUNTIME MESHES A PRESET BUILDS (kit/vfx/cost.py `built_meshes` is the same rule, held to this one by
-- kit/test/python/test_vfx_cost.py): every mesh layer, a debris layer's thrown rocks (40 at most) or its fracture's
-- pieces (`pieces(name)` says how many its plan cuts; 64 at most; none when it is not known), a swarm's stones (40
-- at most), a trail drawn as a ribbon, a mark draped over the ground. Each is an engine call that YIELDS
-- (AssetService:CreateMeshPartAsync: 0.15 to 0.22 s in a background Studio client, 1.15 to 1.65 s while the player's
-- avatar is loading - ten cold sessions, 2026-11-16): an effect that builds any, played before they were made, shows
-- them late or - when it is over first - not at all. Vfx counts such plays (Vfx.coldPlays) from this number
function VfxBudget.builds(layers: any, pieces: ((string) -> number?)?): number
	local n = 0
	if type(layers) ~= "table" then
		return n
	end
	local function count(v: any, default: number, most: number): number
		return math.min(if type(v) == "number" and v == v then math.max(0, math.floor(v)) else default, most)
	end
	for _, el in layers do
		if type(el) ~= "table" then
			continue
		end
		local one = el.kind == "mesh"
			or (el.kind == "trail" and el.mesh == true)
			or (el.kind == "decal" and (el.wrap == true or type(el.wrap) == "number"))
		if one then
			n += 1
		elseif el.kind == "debris" and type(el.pieces) == "string" then
			n += count(if pieces then pieces(el.pieces) else nil, 0, 64)
		elseif el.kind == "debris" and el.shape == "rock" then
			n += count(el.count, 6, 40)
		elseif el.kind == "swarm" and el.shape == "Rock" then
			n += math.max(1, count(el.count, 40, 40)) -- (the stage clamps a swarm of stones to 1 .. 40)
		end
	end
	return n
end

-- A SWARM'S FRAME (the V3 doc, VFX stage F.1: "cap CPU curl3 updates <= 0.5 ms/frame + cull > 300 studs"): a swarm
-- layer moves every one of its parts in Luau every frame (curl noise, attractors, a field, a floor, a cloud), so a
-- big one can take the frame. Its updater times itself; past SWARM_MS the next frames move only every k-th part (in
-- turn, each by the time since IT last moved: the paths stay the same, only coarser), and back down to every part
-- once the work is well under. Past SWARM_CULL studs from the camera a swarm is a few pixels: it is not moved.
VfxBudget.SWARM_MS = 0.5
VfxBudget.SWARM_CULL = 300
VfxBudget.SWARM_STRIDE_MOST = 4 -- (on fours at most: more reads as stepping)

-- the stride for the next frame from what this one took (ms) and the stride it ran at
function VfxBudget.swarmStride(spentMs: number, stride: number): number
	local s = math.clamp(math.floor(stride), 1, VfxBudget.SWARM_STRIDE_MOST)
	if spentMs > VfxBudget.SWARM_MS and s < VfxBudget.SWARM_STRIDE_MOST then
		return s + 1
	elseif spentMs < VfxBudget.SWARM_MS * 0.5 and s > 1 then
		return s - 1
	end
	return s
end

-- does part i move on this frame (n counts the swarm's frames)?
function VfxBudget.swarmMoves(i: number, n: number, stride: number): boolean
	return stride <= 1 or (i + n) % stride == 0
end

-- is a swarm this far from the camera (studs) left where it is this frame?
function VfxBudget.swarmCulled(distance: number): boolean
	return distance > VfxBudget.SWARM_CULL
end

return VfxBudget
