-- worlddecal.luau (kit) — DECALS LAID ON A WORLD'S WALLS AND FLOORS (the owner's method list: "Decal-based detailing").
-- A decal is a picture laid on a face: a leak under a ledge, a stain, a crack, moss in a corner, soot over a torch.
-- The picture is made by `kit world decal <Name> --kind ...` (kit/world/decals.py: by rule, border clear). A build
-- step lays it:
--   { "decal": { "name": "Leak1", "at": [x, y, z], "size": [w, h], "facing": "north" } }            one, where said
--   { "decal": { "names": ["Leak1", "Stain2"], "along": { "from": [x, z], "to": [x, z] }, "y": [lo, hi],
--                "count": 6, "size": [3, 6], "facing": "north", "seed": 4 } }                        many, along a wall
-- "at" is the decal's middle ON the face it lies on; "facing" is the side that face looks toward (north = -Z,
-- east = +X, south = +Z, west = -X, up, down). Along a wall the decals stand one after the other (none over
-- another), each a size, a height and a name of its own by the seed.
-- In the game a decal is a thin unseen part just off the face with a Decal on its outward side.
-- It is in a game only once its picture is uploaded and its id stands in the project's ids file as decals.<Name>:
-- until then the compile says so and the decal is left out (nothing half). A decal that was never made is an error,
-- and so is one that lies on nothing.
-- Pure but for Decal.read (the record and the id, from files).
local Config = require("./config")
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Decal = {}

Decal.MOST = 200 -- decals one step may lay
Decal.OFF = 0.03 -- studs a decal's part stands off its face (no flicker with the wall)
Decal.THICK = 0.05

-- the side a face looks toward -> its normal, the Decal's Face on the thin part, and which of the part's axes are the
-- decal's width and height (1 = x, 2 = y, 3 = z). SEEN in Studio (2026-11-16): a Decal shows on a part of
-- Transparency 1 that nobody can touch; on Front and Right it stands upright and not mirrored; on Top it lies with the
-- picture's top edge toward +Z (south), not mirrored. Back, Left and Bottom were not looked at
Decal.FACING = {
	north = { normal = { 0, 0, -1 }, face = "Front", wide = 1, tall = 2 },
	south = { normal = { 0, 0, 1 }, face = "Back", wide = 1, tall = 2 },
	east = { normal = { 1, 0, 0 }, face = "Right", wide = 3, tall = 2 },
	west = { normal = { -1, 0, 0 }, face = "Left", wide = 3, tall = 2 },
	up = { normal = { 0, 1, 0 }, face = "Top", wide = 1, tall = 3 },
	down = { normal = { 0, -1, 0 }, face = "Bottom", wide = 1, tall = 3 },
}

-- does a colour read as blood (r, g, b 0..255): the rule of kit/world/decals.py `bloody`, held to it by one table of
-- colours in both tests. No blood or gore in this kit (the owner, 2026-10-29)
function Decal.bloody(r: number, g: number, b: number): boolean
	local hi, lo = math.max(r, g, b), math.min(r, g, b)
	if hi < 30 or hi <= 0 or (hi - lo) / hi < 0.35 or r < hi then
		return false
	end
	local hue = 60 * (g - b) / (hi - lo)
	return hue >= -35 and hue <= 12
end

-- the side whose normal this is (whole numbers), nil when it is none of the six
function Decal.facingOf(x: number, y: number, z: number): string?
	for side, f in Decal.FACING do
		if f.normal[1] == x and f.normal[2] == y and f.normal[3] == z then
			return side
		end
	end
	return nil
end

local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	state = (state * 48271) % 2147483647
	state = (state * 48271) % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function numbers(v: any, n: number): boolean
	if type(v) ~= "table" or #v ~= n then
		return false
	end
	for i = 1, n do
		if not number(v[i]) then
			return false
		end
	end
	return true
end

local function name(v: any): boolean
	return type(v) == "string" and string.match(v, "^[%w_]+$") ~= nil
end

local KNOWN = {
	name = true,
	names = true,
	at = true,
	along = true,
	y = true,
	count = true,
	size = true,
	facing = true,
	seed = true,
	transparency = true,
	tint = true,
}

-- what is wrong with a decal step, in words ({} = nothing)
function Decal.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return {
			'decal needs { "name", "at": [x, y, z], "size": [w, h], "facing" } or { "names", "along", "y", "count", "size", "facing" }',
		}
	end
	for k in spec do
		if not KNOWN[k] then
			table.insert(out, `decal: "{tostring(k)}" is not a word it knows`)
		end
	end
	if type(spec.facing) ~= "string" or not Decal.FACING[spec.facing] then
		table.insert(out, 'decal: "facing" is the side its face looks toward: north | south | east | west | up | down')
	end
	if
		spec.transparency ~= nil
		and not (number(spec.transparency) and spec.transparency >= 0 and spec.transparency < 1)
	then
		table.insert(out, 'decal: "transparency" is 0 (as made) to under 1')
	end
	if spec.tint ~= nil then
		local ok = numbers(spec.tint, 3)
		for i = 1, 3 do
			ok = ok and spec.tint[i] >= 0 and spec.tint[i] <= 255
		end
		if not ok then
			table.insert(out, 'decal: "tint" is [r, g, b], each 0 to 255')
		elseif Decal.bloody(spec.tint[1], spec.tint[2], spec.tint[3]) then
			table.insert(out, 'decal: this "tint" reads as blood: not laid (no blood or gore in this kit)')
		end
	end
	local many = spec.along ~= nil or spec.names ~= nil or spec.count ~= nil or spec.y ~= nil
	if not many then
		if not name(spec.name) then
			table.insert(out, 'decal: "name" is the decal made by: lune run kit world decal <Name> --kind ...')
		end
		if not numbers(spec.at, 3) then
			table.insert(out, 'decal: "at" is [x, y, z], its middle on the face it lies on')
		end
		if
			not (
				numbers(spec.size, 2)
				and spec.size[1] >= 0.5
				and spec.size[1] <= 64
				and spec.size[2] >= 0.5
				and spec.size[2] <= 64
			)
		then
			table.insert(out, 'decal: "size" is [width, height] in studs, each 0.5 to 64')
		end
		if spec.seed ~= nil then
			table.insert(out, 'decal: one decal has no "seed" (it is where "at" says)')
		end
		return out
	end
	if spec.name ~= nil or spec.at ~= nil then
		table.insert(out, 'decal: either one ("name", "at") or many ("names", "along"), not both')
	end
	local ok = type(spec.names) == "table" and #spec.names >= 1 and #spec.names <= 16
	if ok then
		for _, n in spec.names do
			ok = ok and name(n)
		end
	end
	if not ok then
		table.insert(out, 'decal: "names" is 1 to 16 decals made by: lune run kit world decal <Name> --kind ...')
	end
	local along = spec.along
	if type(along) ~= "table" or not numbers(along.from, 2) or not numbers(along.to, 2) then
		table.insert(out, 'decal: "along" is { "from": [x, z], "to": [x, z] }, the foot of the wall they lie on')
	elseif spec.facing == "up" or spec.facing == "down" then
		table.insert(
			out,
			'decal: many decals lie along a WALL ("facing" north | south | east | west); a floor\'s are laid one by one'
		)
	else
		local dx, dz = along.to[1] - along.from[1], along.to[2] - along.from[2]
		local f = Decal.FACING[spec.facing]
		-- (a wall that faces north or south runs east-west, and the other way round)
		if f and ((f.wide == 1 and math.abs(dz) > 1e-6) or (f.wide == 3 and math.abs(dx) > 1e-6)) then
			table.insert(
				out,
				`decal: a wall facing {spec.facing} runs {if f.wide == 1 then "east-west" else "north-south"}: "along" must not leave that line`
			)
		elseif math.abs(dx) + math.abs(dz) < 1 then
			table.insert(out, 'decal: "along" has no length')
		end
	end
	if not (numbers(spec.y, 2) and spec.y[1] < spec.y[2]) then
		table.insert(out, 'decal: "y" is [lowest, highest] of the wall they may lie on')
	end
	if not (number(spec.count) and spec.count % 1 == 0 and spec.count >= 1 and spec.count <= Decal.MOST) then
		table.insert(out, `decal: "count" is a whole number 1 to {Decal.MOST}`)
	end
	if not (numbers(spec.size, 2) and spec.size[1] >= 0.5 and spec.size[1] <= spec.size[2] and spec.size[2] <= 64) then
		table.insert(out, 'decal: many decals\' "size" is [smallest, largest] side in studs, 0.5 to 64')
	end
	if
		spec.seed ~= nil and not (number(spec.seed) and spec.seed % 1 == 0 and spec.seed >= 0 and spec.seed <= 65535)
	then
		table.insert(out, 'decal: "seed" is a whole number 0 to 65535')
	end
	if #out == 0 then
		local length = math.abs(along.to[1] - along.from[1]) + math.abs(along.to[2] - along.from[2])
		if length / spec.count < spec.size[1] then
			table.insert(
				out,
				`decal: {spec.count} decals of {spec.size[1]} studs and more do not stand side by side on {length} studs of wall`
			)
		end
		if spec.y[2] - spec.y[1] < spec.size[1] then
			table.insert(
				out,
				`decal: the wall's "y" leaves {spec.y[2] - spec.y[1]} studs and the smallest decal is {spec.size[1]}`
			)
		end
	end
	return out
end

export type Laid = { name: string, at: { number }, size: { number }, facing: string }

-- THE DECALS OF A STEP, where each lies (a step with no problems) -> { { name, at = {x, y, z}, size = {w, h}, facing } }
function Decal.lay(spec: any): { Laid }
	if spec.along == nil then
		return {
			{
				name = spec.name,
				at = { spec.at[1], spec.at[2], spec.at[3] },
				size = { spec.size[1], spec.size[2] },
				facing = spec.facing,
			},
		}
	end
	local rand = lcg((spec.seed or 1) * 7 + 3)
	local from, to = spec.along.from, spec.along.to
	local length = math.abs(to[1] - from[1]) + math.abs(to[2] - from[2])
	local slot = length / spec.count
	local tallest = spec.y[2] - spec.y[1]
	local out: { Laid } = {}
	for i = 1, spec.count do
		-- each stands in its own stretch of the wall: no decal over another
		local side = math.min(spec.size[1] + (spec.size[2] - spec.size[1]) * rand(), slot, tallest)
		local t = ((i - 1) * slot + side / 2 + (slot - side) * rand()) / length
		local y = spec.y[1] + side / 2 + (tallest - side) * rand()
		local which = spec.names[math.min(#spec.names, 1 + math.floor(rand() * #spec.names))]
		table.insert(out, {
			name = which,
			at = { from[1] + (to[1] - from[1]) * t, y, from[2] + (to[2] - from[2]) * t },
			size = { side, side },
			facing = spec.facing,
		})
	end
	return out
end

-- the thin part a laid decal is in the game -> size {x, y, z}, pos {x, y, z}, face (the Decal's Face)
function Decal.part(d: Laid): ({ number }, { number }, string)
	local f = Decal.FACING[d.facing]
	local size = { Decal.THICK, Decal.THICK, Decal.THICK }
	size[f.wide] = d.size[1]
	size[f.tall] = d.size[2]
	local off = Decal.OFF + Decal.THICK / 2
	return size, { d.at[1] + f.normal[1] * off, d.at[2] + f.normal[2] * off, d.at[3] + f.normal[3] * off }, f.face
end

-- DOES A DECAL LIE ON SOMETHING -> nil when it does, else why not.
-- boxes = the solid, seen, SQUARE-STANDING block parts built so far, each { pos, half = {x, y, z} } (a turned or
-- round part is no face a decal can be laid on: the compiler hands none). A decal lies on a box when its middle is
-- on that box's face looking the decal's way, the WHOLE of it is on that face (none hangs off an end), and no other
-- box stands over the spot. A decal facing up may lie on the land instead (ground = its height there, nil = none):
-- within a quarter stud of it.
function Decal.lies(d: Laid, boxes: { any }, ground: number?): string?
	local f = Decal.FACING[d.facing]
	local n = f.normal
	local why: string? = nil
	local function inside(b: any, x: number, y: number, z: number): boolean
		return math.abs(x - b.pos[1]) <= b.half[1]
			and math.abs(y - b.pos[2]) <= b.half[2]
			and math.abs(z - b.pos[3]) <= b.half[3]
	end
	for _, b in boxes do
		-- (a hair behind its middle: inside the part, however thin the part is)
		if inside(b, d.at[1] - n[1] * 0.02, d.at[2] - n[2] * 0.02, d.at[3] - n[3] * 0.02) then
			local reach = (d.at[1] - b.pos[1]) * n[1] + (d.at[2] - b.pos[2]) * n[2] + (d.at[3] - b.pos[3]) * n[3]
			local half = b.half[1] * math.abs(n[1]) + b.half[2] * math.abs(n[2]) + b.half[3] * math.abs(n[3])
			if math.abs(reach - half) <= 0.25 then
				local overW = math.abs(d.at[f.wide] - b.pos[f.wide]) + d.size[1] / 2 - b.half[f.wide]
				local overT = math.abs(d.at[f.tall] - b.pos[f.tall]) + d.size[2] / 2 - b.half[f.tall]
				if overW > 0.05 or overT > 0.05 then
					why =
						`it hangs {math.floor(math.max(overW, overT) * 100 + 0.5) / 100} studs off the face it lies on (that face is {b.half[f.wide] * 2} x {b.half[f.tall] * 2} studs, the decal {d.size[1]} x {d.size[2]})`
				else
					for _, c in boxes do
						if c ~= b and inside(c, d.at[1] + n[1] * 0.1, d.at[2] + n[2] * 0.1, d.at[3] + n[3] * 0.1) then
							return "another part stands over that spot: the decal would not be seen"
						end
					end
					return nil
				end
			end
		end
	end
	if d.facing == "up" and ground ~= nil and math.abs(d.at[2] - ground) <= 0.25 then
		return nil
	end
	return why
		or `no solid, square-standing part's face stands there looking {d.facing} (its "at" is its middle ON the face; a turned or round part, one nobody can touch and an unseen one are no face for it)`
end

-- what is known of a decal by its name -> record (the .decal.json; nil = not made, false = there and unreadable),
-- id (the uploaded picture's, as "rbxassetid://n"; nil = not uploaded)
function Decal.read(which: string): (any?, string?)
	local record: any = nil
	local file = `{Config.build("decals")}/{which}.decal.json`
	if fs.isFile(file) then
		local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(file))
		record = if ok
				and type(data) == "table"
				and data.name == which
				and type(data.kind) == "string"
			then data
			else false
	end
	local id: string? = nil
	local ip = Config.path("ids")
	if ip and fs.isFile(ip) then
		local ok, all = pcall(serde.decode, "json" :: any, fs.readFile(ip))
		if ok and type(all) == "table" and type(all.decals) == "table" then
			id = Decal.id(all.decals[which])
		end
	end
	return record, id
end

-- an id is a whole number over 0, or that number as a string, bare or after rbxassetid:// : nothing else
function Decal.id(v: any): string?
	local digits: string? = nil
	if type(v) == "number" and v > 0 and v % 1 == 0 and v < 2 ^ 53 then
		digits = string.format("%d", v)
	elseif type(v) == "string" then
		digits = string.match(v, "^rbxassetid://(%d+)$") or string.match(v, "^(%d+)$")
		if digits and tonumber(digits) == 0 then
			digits = nil
		end
	end
	return if digits then `rbxassetid://{digits}` else nil
end

return Decal
