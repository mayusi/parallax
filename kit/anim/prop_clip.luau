-- prop_clip.luau — `lune run kit/anim/prop_clip.luau <rigs dir> <spec.json> <out dir>`: a PROP's keyframe spec the
-- whole way through the kit's own compiler (kit/lib/anim.luau): spec -> clip (clipFromSpec, sampled) -> the
-- KeyframeSequence model the game plays (modelFromClip), on a prop's rig read from <rigs dir> (a rig kit/anim/
-- prop_rig.py made: <rigs dir>/<name>.json) instead of kit/anim/rigs. Writes <out dir>/<Name>.clip.json and
-- <out dir>/<Name>.model.json and prints one JSON verdict line. It holds nothing itself: kit/anim/prop_rig.py `go`
-- runs it and holds the clip to the prop's joints BEFORE the model is kept.
-- ONE NUMBER poses a hinge or a slide by itself ({"Lid": 90}: degrees about the joint's own axis, whichever way it
-- points; {"Tray": 1.2}: studs along its runner). A hinge posed so is turned key to key in DEGREES after sampling, with
-- the key's easing (the compiler's slerp takes the short way: a wheel keyed 0 then 270 would turn back 90); its clip
-- keeps the degrees as a "turn" track, and when a key-to-key turn reaches HALF a turn the model is written frame by
-- frame (the engine, too, takes the short way between two keyframes).
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Rig = require("../lib/animrig")

local rigDir, specPath, outDir = process.args[1], process.args[2], process.args[3]
local function say(status: string, summary: string, extra: { [string]: any }?)
	local v: { [string]: any } = { schema = 1, status = status, summary = summary }
	for k, x in extra or {} do
		v[k] = x
	end
	print(serde.encode("json", v))
	process.exit(if status == "pass" then 0 else 1)
end
if not rigDir or not specPath or not outDir then
	say("fail", "usage: lune run kit/anim/prop_clip.luau <rigs dir> <spec.json> <out dir>")
end
if not fs.isDir(rigDir) or not fs.isFile(specPath) then
	say("fail", `prop clip: no rigs folder at {rigDir} or no spec at {specPath}`)
end

-- the character rigs stay known (a spec that names R6 by mistake is told so by the compiler), the prop's is added
local own = Rig.RIG_DIR
Rig.loadRigs()
local known: { [string]: any } = table.clone(Rig.RIGS)
Rig.RIG_DIR = rigDir
Rig.loadRigs()
for name, rig in known do
	if Rig.RIGS[name] == nil then
		Rig.RIGS[name] = rig
	end
end
Rig.RIG_DIR = own
local Anim = require("../lib/anim") -- (Anim.RIGS is Rig.RIGS: the same table, filled above)

local okS, spec = pcall(serde.decode, "json" :: any, fs.readFile(specPath))
if not okS or type(spec) ~= "table" then
	say("fail", `prop clip: {specPath} is not valid JSON`)
end
local rig = if type(spec.rig) == "string" then Rig.RIGS[spec.rig] else nil
if not rig or rig.kind ~= "prop" then
	say("fail", `prop clip: the spec's rig "{tostring(spec.rig)}" is not a prop's rig in {rigDir}`)
end
local HALF = 179 -- degrees key to key from which the engine's own interpolation could turn the wrong way

-- a turn of `deg` degrees about a unit-able axis -> the 3x3 rotation (columns), Rodrigues
local function axisTurn(ax: { number }, deg: number): { { number } }
	local n = math.sqrt(ax[1] * ax[1] + ax[2] * ax[2] + ax[3] * ax[3])
	local x, y, z = ax[1] / n, ax[2] / n, ax[3] / n
	local c, s = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	local t = 1 - c
	return {
		{ t * x * x + c, t * x * y - s * z, t * x * z + s * y },
		{ t * x * y + s * z, t * y * y + c, t * y * z - s * x },
		{ t * x * z - s * y, t * y * z + s * x, t * z * z + c },
	}
end

local limits: { [string]: any } = (rig :: any).limits or {}
local scalar: { [string]: { [number]: number } } = {} -- part -> key time -> degrees / studs
local shaped: { [string]: boolean } = {} -- parts posed by a triple or {rot, pos} in some key
for _, key in (if type(spec.keys) == "table" then spec.keys else {}) do
	if type(key) ~= "table" or type(key.pose) ~= "table" or type(key.t) ~= "number" then
		continue -- (the compiler says what is wrong with it)
	end
	for part, v in key.pose do
		if type(v) ~= "number" then
			shaped[part] = true
			continue
		end
		local lim = limits[part]
		if type(lim) ~= "table" or (lim.kind ~= "hinge" and lim.kind ~= "slide") then
			say(
				"fail",
				`prop clip {tostring(spec.name)}: {part} is posed by one number - only a hinge (degrees) or a slide (studs) is`
			)
		end
		if v ~= v or math.abs(v) == math.huge then
			say("fail", `prop clip {tostring(spec.name)}: {part} is posed by a number that is not one`)
		end
		scalar[part] = scalar[part] or {}
		scalar[part][key.t] = v
		local ax = lim.axis
		if lim.kind == "hinge" then
			key.pose[part] = Rig.eulerOf(axisTurn(ax, v))
		else
			key.pose[part] = { rot = { 0, 0, 0 }, pos = { ax[1] * v, ax[2] * v, ax[3] * v } }
		end
	end
end
for part in scalar do
	if shaped[part] then
		say(
			"fail",
			`prop clip {tostring(spec.name)}: {part} is posed by one number in one key and by a turn in another - one way in every key`
		)
	end
end

local function issuesOf(list: { any }): ({ string }, boolean)
	local out, bad = {}, false
	for _, i in list do
		table.insert(out, `[{i.severity}] {i.path}: {i.message}`)
		if i.severity == "error" then
			bad = true
		end
	end
	return out, bad
end
local clip, issues = Anim.clipFromSpec(spec, { source = { kind = "spec", file = specPath } })
local said, bad = issuesOf(issues)
if not clip or bad then
	say(
		"fail",
		`prop clip {tostring(spec.name)}: the spec does not compile - {said[1] or "no clip"}`,
		{ issues = said }
	)
end
local dense = Anim.sample(clip :: any)
-- a hinge posed by numbers: its frames turned in degrees, key to key with the key's easing (as the compiler eases)
local frameByFrame = false
for part, byTime in scalar do
	local lim = limits[part]
	local j = dense.joints[part]
	if lim.kind ~= "hinge" or not j or not j.keys or not j.frames then
		continue
	end
	local keys = j.keys :: { any }
	local values, prev = {}, 0 -- (every spec key time: a hold of the last value, rest before the first)
	for k, key in keys do
		local v = byTime[key.t]
		if v == nil then
			v = prev
		end
		values[k] = v
		prev = v
		if k > 1 and math.abs(v - values[k - 1]) >= HALF then
			frameByFrame = true
		end
	end
	local ax = lim.axis
	local n = math.sqrt(ax[1] * ax[1] + ax[2] * ax[2] + ax[3] * ax[3])
	local turn = {}
	for i, t in dense.times do
		local v = values[#keys]
		if t <= keys[1].t then
			v = values[1]
		else
			for k = 1, #keys - 1 do
				local a, b = keys[k], keys[k + 1]
				if t >= a.t and t < b.t then
					v = values[k] + (values[k + 1] - values[k]) * Anim.ease(a.ease, a.dir, (t - a.t) / (b.t - a.t))
					break
				end
			end
		end
		turn[i] = v
		local h = math.rad(v) / 2
		local sh = math.sin(h)
		local f = j.frames[i]
		j.frames[i] = { ax[1] / n * sh, ax[2] / n * sh, ax[3] / n * sh, math.cos(h), f[5], f[6], f[7] }
	end
	(j :: any).turn = turn
end
if frameByFrame then
	for _, j in dense.joints do
		j.keys = nil -- (modelFromClip then writes the dense frames: one keyframe a frame)
	end
end
local model, _, more = Anim.modelFromClip(dense, spec.rig)
local said2, bad2 = issuesOf(more)
if not model or bad2 then
	say("fail", `prop clip {spec.name}: no animation model - {said2[1] or "no model"}`, { issues = said2 })
end
if not fs.isDir(outDir) then
	fs.writeDir(outDir)
end
local clipOut, modelOut = `{outDir}/{spec.name}.clip.json`, `{outDir}/{spec.name}.model.json`
fs.writeFile(clipOut, serde.encode("json", dense))
fs.writeFile(modelOut, serde.encode("json", model))
say("pass", `prop clip {spec.name}: compiled on {spec.rig}`, { clip = clipOut, model = modelOut, issues = said })
