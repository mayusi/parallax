--!strict
-- contract.luau — the CROSS-LANE CONTRACT of one hero weapon (LIMITATIONS_FIXES_V4 §10 item 1 / §13.8 item 1):
-- assets/contracts/<hero>.json binds what every lane made for it - the built model (its files' SHA-256, its sockets,
-- its length at 1 stud = 0.28 m), the move set's authored Hit / Cancel / Hitstop frames, the VFX it plays, the sound
-- events swing / hit / parry (each one with a recipe that makes it), the UI trigger and the PROMPT-X packet - so that
-- ANY hash change, a moved hit frame, a lost socket or a sound with no recipe is caught BY NAME before a downstream
-- build trusts it ("any hash change invalidates downstream builds cleanly").
--
-- Pure: no files, no services. kit/cmd/contract.luau reads the real sources into `Inputs` (below) and calls:
--   Contract.build(inputs) -> contract          every field derived from the sources; a field with no source yet is
--                                               Contract.NULL with its reason in contract.whyNull[<field>]
--   Contract.validate(contract) -> { string }   the contract's own rules (schema 1, studScale 0.28, five sockets, a
--                                               reason for every null, every sound event in the catalogue and made)
--   Contract.diff(stored, fresh) -> { string }  drift: every field that differs, named by its path
--   Contract.check(stored, fresh) -> { string } validate(stored) + validate(fresh) + diff(stored, fresh)
--   Contract.encode(contract) -> string         JSON, keys in a fixed order, nulls written as null
-- A contract decoded from JSON has no nulls (serde drops them): every function here treats an absent field and
-- Contract.NULL alike.
local Contract = {}

Contract.SCHEMA = 1
-- the scale every lane builds to (Roblox: 1 stud = 0.28 m; §10 item 1) - a contract at any other scale is refused
Contract.STUD_SCALE = 0.28
Contract.SOCKETS = { "RightGrip", "LeftGrip", "Holster", "Tip", "Muzzle" }
Contract.NULL = "<null>"
Contract.MISSING = "missing"

export type FileHash = { path: string, sha: string }
export type Inputs = {
	hero: string,
	madeWith: { [string]: any },
	model: {
		asset: string,
		manifestPath: string,
		manifest: any,
		files: { [string]: string }, -- path -> sha256 (or Contract.MISSING)
		mmPerStud: number,
		mmPerStudSource: string,
	},
	set: { path: string, sha: string, data: any },
	moveFiles: { [string]: FileHash | false }, -- move name -> its authored assets/moves/<move>.json
	clips: { [string]: { files: { [string]: string }, sword: any? } }, -- anim name -> its files, its .move.json sword
	vfx: { name: string, kind: string, path: string, sha: string } | false | nil, -- false: named but not found
	cues: { [string]: { kind: string, path: string, sha: string } | false }, -- preset -> where the moves' cue lives
	sfx: { path: string, sha: string, events: { [string]: any }, made: { [string]: boolean } } | false,
	parryEvent: { event: string, source: string }?,
	ui: { name: string, path: string, sha: string } | false | nil,
	packet: { path: string, sha256: string }?,
	packetReason: string?,
	assetId: string?,
	assetIdReason: string?,
}

local function sortedKeys(t: { [any]: any }): { string }
	local keys = {}
	for k in t do
		table.insert(keys, tostring(k))
	end
	table.sort(keys)
	return keys
end

local function isArray(t: { [any]: any }): boolean
	local n = 0
	for _ in t do
		n += 1
	end
	return n > 0 and #t == n
end

-- every sound name an event plays (its sound / sounds / cases' sounds) - kit/audio/catalog.py names_in
local function soundsOf(e: any): { string }
	local out, seen = {}, {}
	local function add(s: any)
		if type(s) == "string" and not seen[s] then
			seen[s] = true
			table.insert(out, s)
		end
	end
	local cases = { e }
	if type(e) == "table" and type(e.cases) == "table" then
		for _, k in sortedKeys(e.cases) do
			table.insert(cases, e.cases[k])
		end
	end
	for _, case in cases do
		if type(case) == "string" then
			add(case)
		elseif type(case) == "table" then
			add(case.sound)
			if type(case.sounds) == "table" then
				for _, k in sortedKeys(case.sounds) do
					add(case.sounds[k])
				end
			end
		end
	end
	table.sort(out)
	return out
end
Contract.soundsOf = soundsOf

local function round(n: number, places: number): number
	local m = 10 ^ places
	return math.floor(n * m + 0.5) / m
end

-- the model's whole-file hash: every file the manifest names (fbx, maps), sorted, "path sha" lines
function Contract.modelHash(files: { [string]: string }, hash: (string) -> string): string
	local lines = {}
	for _, p in sortedKeys(files) do
		table.insert(lines, `{p} {files[p]}\n`)
	end
	return hash(table.concat(lines))
end

-- a socket the 3D lane recorded on the model: manifest.sockets[name] (a.socket) or manifest.anchors[name] (a.anchor),
-- the name matched exactly first, then without case (§10 writes @tip / @muzzle)
local function socketOf(manifest: any, name: string): any?
	local sockets = if type(manifest.sockets) == "table" then manifest.sockets else {}
	local anchors = if type(manifest.anchors) == "table" then manifest.anchors else {}
	local function find(t: { [string]: any }): (string?, any?)
		if t[name] ~= nil then
			return name, t[name]
		end
		for k, v in t do
			if string.lower(k) == string.lower(name) then
				return k, v
			end
		end
		return nil, nil
	end
	local k, s = find(sockets)
	if k and type(s) == "table" then
		return { name = k, part = s.part, pos = s.pos, axis = s.axis, from = "sockets" }
	end
	local ka, a = find(anchors)
	if ka and type(a) == "table" then
		return { name = ka, pos = a, from = "anchors" }
	end
	return nil
end

-- the model's longest side in studs (manifest.facts.size_studs, the 3D lane's measure of the joined model)
local function lengthOf(manifest: any): (number?, string?)
	local size = type(manifest.facts) == "table" and manifest.facts.size_studs
	if type(size) ~= "table" or #size < 3 then
		return nil, nil
	end
	local axes = { "x", "y", "z" }
	local best, axis = -1, "x"
	for i = 1, 3 do
		if type(size[i]) == "number" and size[i] > best then
			best, axis = size[i], axes[i]
		end
	end
	return best, axis
end

function Contract.build(inp: Inputs, hash: (string) -> string): any
	local whyNull: { [string]: string } = {}
	local sources: { [string]: string } = {}
	local function source(path: string, sha: string)
		sources[path] = sha
	end
	local function null(field: string, why: string): string
		whyNull[field] = why
		return Contract.NULL
	end

	-- the model ------------------------------------------------------------------------------------------------
	-- (the manifest itself is not hashed: every build re-writes it; the files it names carry the hash, and its
	-- sockets and length are compared field by field)
	local manifest = inp.model.manifest or {}
	if not inp.model.manifest then
		source(inp.model.manifestPath, Contract.MISSING)
	end
	for p, sha in inp.model.files do
		source(p, sha)
	end
	local sockets = {}
	for _, name in Contract.SOCKETS do
		local s = socketOf(manifest, name)
		sockets[name] = if s
			then s
			else null(
				`sockets.{name}`,
				`{inp.model.manifestPath} records no socket or anchor named {name} (the 3D build script names none: a.socket / a.anchor)`
			)
	end
	local length, axis = lengthOf(manifest)
	local studScale = inp.model.mmPerStud / 1000
	local animSword = {}
	for anim, clip in inp.clips do
		if type(clip.sword) == "table" and type(clip.sword.length) == "number" then
			animSword[anim] = {
				length = clip.sword.length,
				kind = clip.sword.kind,
				grip = clip.sword.grip,
				-- "hand": the clip's Handle poses have their origin at the right hand (the game joint's C1 takes
				-- grip / 2 up the handle: src/kit/AnimGrip.luau handOffset)
				gripOrigin = clip.sword.grip_origin,
			}
		end
	end
	local physicalLength = if length
		then {
			studs = length,
			metres = round(length * studScale, 4),
			axis = axis,
			source = `{inp.model.manifestPath} facts.size_studs`,
			animSword = animSword,
		}
		else null("physicalLength", `{inp.model.manifestPath} has no facts.size_studs`)

	-- the move set ---------------------------------------------------------------------------------------------
	local set = inp.set.data or {}
	source(inp.set.path, inp.set.sha)
	local combo: { string } = if type(set.combo) == "table" then set.combo else {}
	local moves = if type(set.moves) == "table" then set.moves else {}
	local timeline = {}
	local clips = {}
	local cues = {}
	local swing, hit = {}, {}
	local fps = 60
	for _, name in combo do
		local m = moves[name]
		if type(m) ~= "table" then
			timeline[name] =
				null(`movesTimeline.moves.{name}`, `{inp.set.path} lists {name} in its combo but has no such move`)
			continue
		end
		local mf = inp.moveFiles[name]
		if mf then
			source(mf.path, mf.sha)
		end
		local frames = if type(m.frames) == "table" then m.frames else {}
		fps = if type(frames.fps) == "number" then frames.fps else fps
		local entry: { [string]: any } = {
			anim = m.anim,
			-- the first active frame: the clip's Hit, measured into the compiled set (frames "from_anim")
			hitFrame = if type(frames.startup) == "number"
				then frames.startup
				else null(`movesTimeline.moves.{name}.hitFrame`, `{inp.set.path} {name} has no frames.startup`),
			cancelFrame = if type(m.cancel) == "table" and type(m.cancel.from) == "number"
				then m.cancel.from
				else null(
					`movesTimeline.moves.{name}.cancelFrame`,
					`{name} cancels into nothing ({inp.set.path} gives it no cancel window)`
				),
			hitstopSeconds = m.hitstop,
			hitstopFrames = if type(m.hitstop) == "number"
				then math.floor(m.hitstop * (frames.fps or 60) + 0.5)
				else null(`movesTimeline.moves.{name}.hitstopFrames`, `{inp.set.path} {name} has no hitstop`),
		}
		timeline[name] = entry
		if type(m.anim) == "string" then
			local c = inp.clips[m.anim]
			clips[m.anim] = { move = name, files = if c then c.files else {} }
			if c then
				for p, sha in c.files do
					source(p, sha)
				end
			end
		end
		for _, s in (if type(m.sfx) == "table" then m.sfx else {}) :: { any } do
			if type(s) == "table" and type(s.event) == "string" then
				swing[s.event] = true
			end
		end
		if type(m.onHit) == "table" and type(m.onHit.sfx) == "string" then
			hit[m.onHit.sfx] = true
		end
		for _, v in (if type(m.vfx) == "table" then m.vfx else {}) :: { any } do
			if type(v) == "table" and type(v.preset) == "string" then
				table.insert(cues, { move = name, frame = v.frame, preset = v.preset })
				local where = inp.cues[v.preset]
				if where then
					source(where.path, where.sha)
				else
					source(`(vfx preset {v.preset})`, Contract.MISSING)
				end
			end
		end
	end
	local opener = combo[1]
	local first = if opener and type(timeline[opener]) == "table" then timeline[opener] else {}
	local parryAnim = if type(set.parry) == "table" and type(set.parry.anim) == "string" then set.parry.anim else nil
	if parryAnim then
		local c = inp.clips[parryAnim]
		clips[parryAnim] = { move = "(parry)", files = if c then c.files else {} }
		if c then
			for p, sha in c.files do
				source(p, sha)
			end
		end
	end
	local movesTimeline = {
		fps = fps,
		move = opener or Contract.NULL,
		hitFrame = if first.hitFrame ~= nil then first.hitFrame else Contract.NULL,
		cancelFrame = if first.cancelFrame ~= nil then first.cancelFrame else Contract.NULL,
		hitstopFrames = if first.hitstopFrames ~= nil then first.hitstopFrames else Contract.NULL,
		combo = combo,
		moves = timeline,
	}
	if not opener then
		whyNull["movesTimeline.move"] = `{inp.set.path} has no combo`
	end

	-- the VFX --------------------------------------------------------------------------------------------------
	local vfxSequence: any
	if inp.vfx then
		source(inp.vfx.path, inp.vfx.sha)
		vfxSequence = { name = inp.vfx.name, kind = inp.vfx.kind, file = inp.vfx.path, cues = cues }
	elseif inp.vfx == false then
		local named = tostring(inp.madeWith.vfx)
		source(`(vfx {named})`, Contract.MISSING)
		vfxSequence = { name = named, kind = Contract.NULL, file = Contract.NULL, cues = cues }
	elseif #cues > 0 then
		local where = inp.cues[cues[1].preset]
		vfxSequence = {
			name = cues[1].preset,
			kind = if where then where.kind else Contract.NULL,
			file = if where then where.path else Contract.NULL,
			cues = cues,
		}
	else
		vfxSequence = null("vfxSequence", `no --vfx given and no move of {inp.set.path} cues a VFX preset`)
	end

	-- the sounds -----------------------------------------------------------------------------------------------
	local sfxEvents: any
	local function role(names: { [string]: boolean }, label: string): any
		local list = sortedKeys(names)
		if #list == 0 then
			return null(`sfxEvents.{label}`, `no move of {inp.set.path} names a {label} sound event`)
		end
		local sounds, unmade, missing = {}, {}, {}
		local seen = {}
		local catalog = inp.sfx
		for _, ev in list do
			local e = if catalog then catalog.events[ev] else nil
			if e == nil then
				table.insert(missing, ev)
				continue
			end
			for _, s in soundsOf(e) do
				if not seen[s] then
					seen[s] = true
					table.insert(sounds, s)
					if not (catalog and catalog.made[s]) then
						table.insert(unmade, s)
					end
				end
			end
		end
		table.sort(sounds)
		return { events = list, sounds = sounds, unmade = unmade, notInCatalog = missing }
	end
	local parryNames = {}
	if inp.parryEvent then
		parryNames[inp.parryEvent.event] = true
	end
	if inp.sfx then
		source(inp.sfx.path, inp.sfx.sha)
	end
	sfxEvents = {
		catalog = if inp.sfx then inp.sfx.path else Contract.NULL,
		swing = role(swing, "swing"),
		hit = role(hit, "hit"),
		parry = if parryAnim == nil
			then null("sfxEvents.parry", `{inp.set.path} has no parry`)
			elseif inp.parryEvent then role(parryNames, "parry")
			else null(
				"sfxEvents.parry",
				"no parry sound event found (the set's parry.sfx, or the runtime's broadcast)"
			),
	}
	if inp.parryEvent and type(sfxEvents.parry) == "table" then
		sfxEvents.parry.source = inp.parryEvent.source
	end
	if not inp.sfx then
		whyNull["sfxEvents.catalog"] = "no sound events catalogue (assets/sounds/_events.json) beside the move set"
	end

	-- the UI trigger and the PROMPT-X packet -------------------------------------------------------------------
	local uiTrigger: any
	if inp.ui then
		source(inp.ui.path, inp.ui.sha)
		uiTrigger = { name = inp.ui.name, file = inp.ui.path }
	elseif inp.ui == false then
		source(`(ui {tostring(inp.madeWith.ui)})`, Contract.MISSING)
		uiTrigger = { name = tostring(inp.madeWith.ui), file = Contract.NULL }
	else
		uiTrigger = null(
			"uiTrigger",
			`no UI screen spec is bound to {inp.set.path} yet (UiCombat.ladder is the runtime's rule; no screen names this set): kit contract new ... --ui <screen>`
		)
	end
	local packetSha: any = if inp.packet
		then inp.packet.sha256
		else null("promptPacketSha256", inp.packetReason or "no PROMPT-X packet names this piece")
	if inp.packet then
		source(inp.packet.path, inp.packet.sha256)
	end

	local modelSha = Contract.modelHash(inp.model.files, hash)
	local assetId: any = if inp.assetId
		then inp.assetId
		else null("assetId", inp.assetIdReason or "the model is not uploaded")

	return {
		schema = Contract.SCHEMA,
		hero = inp.hero,
		about = `the cross-lane contract of {inp.hero}: model {inp.model.asset}, move set {tostring(
			set.name or inp.set.path
		)} - written by kit contract new from the sources below; kit contract check re-reads them`,
		assetId = assetId,
		studScale = studScale,
		studScaleSource = inp.model.mmPerStudSource,
		physicalLength = physicalLength,
		sockets = sockets,
		model = { asset = inp.model.asset, manifest = inp.model.manifestPath, files = inp.model.files },
		modelSha256 = modelSha,
		animSet = {
			name = set.name or Contract.NULL,
			file = inp.set.path,
			parry = parryAnim or Contract.NULL,
			clips = clips,
		},
		movesTimeline = movesTimeline,
		vfxSequence = vfxSequence,
		sfxEvents = sfxEvents,
		uiTrigger = uiTrigger,
		promptPacketSha256 = packetSha,
		promptPacket = if inp.packet then inp.packet.path else Contract.NULL,
		sources = sources,
		whyNull = whyNull,
		madeWith = inp.madeWith,
	}
end

-- a copy without Contract.NULL markers (a decoded contract has none: both read alike)
local function strip(v: any): any
	if v == Contract.NULL then
		return nil
	end
	if type(v) ~= "table" then
		return v
	end
	local out = {}
	for k, x in v do
		out[k] = strip(x)
	end
	return out
end
Contract.strip = strip

local function at(t: any, path: string): any
	local cur = t
	for part in string.gmatch(path, "[^%.]+") do
		if type(cur) ~= "table" then
			return nil
		end
		cur = cur[part]
	end
	return cur
end

-- the contract's own rules (a stored one and a freshly built one alike)
function Contract.validate(raw: any): { string }
	local c = strip(raw) or {}
	local problems = {}
	local why = if type(c.whyNull) == "table" then c.whyNull else {}
	local function bad(s: string)
		table.insert(problems, s)
	end
	if c.schema ~= Contract.SCHEMA then
		bad(`schema: {tostring(c.schema)} (must be {Contract.SCHEMA})`)
	end
	if type(c.studScale) ~= "number" or math.abs(c.studScale - Contract.STUD_SCALE) > 1e-9 then
		bad(`studScale: {tostring(c.studScale)} (must be {Contract.STUD_SCALE}: 1 stud = 0.28 m)`)
	end
	if type(c.modelSha256) ~= "string" or not string.match(c.modelSha256, "^%x+$") or #c.modelSha256 ~= 64 then
		bad(`modelSha256: {tostring(c.modelSha256)} is not a SHA-256`)
	end
	local sockets = if type(c.sockets) == "table" then c.sockets else {}
	for _, name in Contract.SOCKETS do
		local s = sockets[name]
		if s == nil and why[`sockets.{name}`] == nil then
			bad(`sockets.{name}: missing (no socket and no reason)`)
		elseif s ~= nil and (type(s) ~= "table" or type(s.pos) ~= "table") then
			bad(`sockets.{name}: has no place (pos)`)
		end
	end
	for _, field in { "assetId", "uiTrigger", "promptPacketSha256", "vfxSequence", "physicalLength" } do
		if c[field] == nil and why[field] == nil then
			bad(`{field}: null with no reason (whyNull.{field})`)
		end
	end
	local tl = if type(c.movesTimeline) == "table" then c.movesTimeline else {}
	for _, field in { "hitFrame", "hitstopFrames" } do
		if type(tl[field]) ~= "number" then
			bad(`movesTimeline.{field}: {tostring(tl[field])} (the opener's authored frame is not there)`)
		end
	end
	local sfx = if type(c.sfxEvents) == "table" then c.sfxEvents else {}
	for _, r in { "swing", "hit", "parry" } do
		local e = sfx[r]
		if e == nil then
			if why[`sfxEvents.{r}`] == nil then
				bad(`sfxEvents.{r}: missing (no event and no reason)`)
			end
			continue
		end
		if type(e) ~= "table" then
			bad(`sfxEvents.{r}: not an object`)
			continue
		end
		for _, ev in (e.notInCatalog or {}) :: { string } do
			bad(`sfxEvents.{r}: event {ev} is not in the sound catalogue {tostring(sfx.catalog)}`)
		end
		for _, s in (e.unmade or {}) :: { string } do
			bad(`sfxEvents.{r}: sound {s} ({table.concat(e.events or {}, ", ")}) has no recipe or set that makes it`)
		end
	end
	local v = c.vfxSequence
	if type(v) == "table" and v.file == nil then
		bad(
			`vfxSequence: preset {tostring(v.name)} not found (no assets/effects/{tostring(v.name)}.json or sequences/{tostring(
				v.name
			)}.seq.json)`
		)
	end
	local ui = c.uiTrigger
	if type(ui) == "table" and ui.file == nil then
		bad(`uiTrigger: screen {tostring(ui.name)} not found`)
	end
	for _, p in sortedKeys(if type(c.sources) == "table" then c.sources else {}) do
		if c.sources[p] == Contract.MISSING then
			bad(`sources: {p} is missing`)
		end
	end
	for _, p in sortedKeys(if type(c.model) == "table" and type(c.model.files) == "table" then c.model.files else {}) do
		if c.model.files[p] == Contract.MISSING then
			bad(`model: {p} is missing`)
		end
	end
	return problems
end

local IGNORED = { madeWith = true, about = true }

local function show(v: any): string
	if v == nil then
		return "none"
	end
	if type(v) == "string" then
		if #v == 64 and string.match(v, "^%x+$") then
			return string.sub(v, 1, 12)
		end
		return v
	end
	if type(v) == "table" then
		return if isArray(v) then "[" .. #v .. " items]" else "{...}"
	end
	return tostring(v)
end

local function key(path: string, k: string): string
	if string.find(k, "[/%.%s%(]") then
		return `{path}[{k}]`
	end
	return if path == "" then k else `{path}.{k}`
end

local function walk(a: any, b: any, path: string, out: { string })
	if type(a) == "table" and type(b) == "table" then
		local keys, seen = {}, {}
		for _, k in sortedKeys(a) do
			seen[k] = true
			table.insert(keys, k)
		end
		for _, k in sortedKeys(b) do
			if not seen[k] then
				table.insert(keys, k)
			end
		end
		for _, k in keys do
			if path == "" and IGNORED[k] then
				continue
			end
			local ka: any = if a[k] ~= nil then k else tonumber(k)
			local kb: any = if b[k] ~= nil then k else tonumber(k)
			walk(a[ka or k], b[kb or k], key(path, k), out)
		end
		return
	end
	if a == b then
		return
	end
	if type(a) == "number" and type(b) == "number" and math.abs(a - b) < 1e-9 then
		return
	end
	if a == nil then
		table.insert(out, `{path}: appeared ({show(b)})`)
	elseif b == nil then
		table.insert(out, `{path}: gone (was {show(a)})`)
	else
		table.insert(out, `{path}: {show(a)} -> {show(b)}`)
	end
end

-- drift: the stored contract against the one built from the sources today, every difference by its path
function Contract.diff(stored: any, fresh: any): { string }
	local out = {}
	walk(strip(stored) or {}, strip(fresh) or {}, "", out)
	return out
end

function Contract.check(stored: any, fresh: any): { string }
	local problems = {}
	for _, p in Contract.validate(stored) do
		table.insert(problems, "contract " .. p)
	end
	for _, p in Contract.validate(fresh) do
		table.insert(problems, "sources " .. p)
	end
	for _, p in Contract.diff(stored, fresh) do
		table.insert(problems, "drift " .. p)
	end
	return problems
end

-- the anim's sword against the model's length: a warning, never a failure (a clip authored for another blade)
function Contract.warnings(raw: any): { string }
	local c = strip(raw) or {}
	local out = {}
	local pl = c.physicalLength
	if type(pl) == "table" and type(pl.studs) == "number" and type(pl.animSword) == "table" then
		for _, anim in sortedKeys(pl.animSword) do
			local s = pl.animSword[anim]
			if type(s) == "table" and type(s.length) == "number" and math.abs(s.length - pl.studs) / pl.studs > 0.1 then
				table.insert(
					out,
					`{anim} was authored for a {s.length}-stud {tostring(s.kind or "blade")}; the model is {pl.studs} studs`
				)
			end
		end
	end
	return out
end

-- JSON ----------------------------------------------------------------------------------------------------------
local ORDER = {
	"schema",
	"hero",
	"about",
	"assetId",
	"studScale",
	"studScaleSource",
	"physicalLength",
	"sockets",
	"modelSha256",
	"model",
	"animSet",
	"movesTimeline",
	"vfxSequence",
	"sfxEvents",
	"uiTrigger",
	"promptPacketSha256",
	"promptPacket",
	"whyNull",
	"sources",
	"madeWith",
}

local function quote(s: string): string
	s = string.gsub(s, '[%c"\\]', function(ch: string): string
		if ch == '"' then
			return '\\"'
		elseif ch == "\\" then
			return "\\\\"
		elseif ch == "\n" then
			return "\\n"
		elseif ch == "\r" then
			return "\\r"
		elseif ch == "\t" then
			return "\\t"
		end
		return string.format("\\u%04x", string.byte(ch))
	end)
	return '"' .. s .. '"'
end

local function num(n: number): string
	if n == math.floor(n) and math.abs(n) < 1e15 then
		return string.format("%d", n)
	end
	local s = string.format("%.15g", n)
	if tonumber(s) ~= n then
		s = string.format("%.17g", n)
	end
	return s
end

-- the lists a contract holds (an empty one is written [] - an empty Luau table could be either)
local ARRAY_KEYS = { combo = true, cues = true, events = true, sounds = true, unmade = true, notInCatalog = true }

local function enc(v: any, indent: string, top: boolean, field: string?): string
	if v == nil or v == Contract.NULL then
		return "null"
	end
	local t = type(v)
	if t == "string" then
		return quote(v)
	elseif t == "number" then
		return num(v)
	elseif t == "boolean" then
		return tostring(v)
	elseif t ~= "table" then
		return quote(tostring(v))
	end
	local inner = indent .. "  "
	if isArray(v) then
		local parts = {}
		local simple = true
		for _, x in v do
			if type(x) == "table" then
				simple = false
			end
			table.insert(parts, enc(x, inner, false, nil))
		end
		if simple then
			return "[" .. table.concat(parts, ", ") .. "]"
		end
		return "[\n" .. inner .. table.concat(parts, ",\n" .. inner) .. "\n" .. indent .. "]"
	end
	if next(v) == nil then
		return if field and ARRAY_KEYS[field] then "[]" else "{}"
	end
	local keys = {}
	if top then
		local seen = {}
		for _, k in ORDER do
			if v[k] ~= nil then
				table.insert(keys, k)
				seen[k] = true
			end
		end
		for _, k in sortedKeys(v) do
			if not seen[k] then
				table.insert(keys, k)
			end
		end
	else
		keys = sortedKeys(v)
	end
	local parts = {}
	for _, k in keys do
		table.insert(parts, quote(k) .. ": " .. enc(v[k], inner, false, k))
	end
	return "{\n" .. inner .. table.concat(parts, ",\n" .. inner) .. "\n" .. indent .. "}"
end

function Contract.encode(c: any): string
	return enc(c, "", true, nil) .. "\n"
end

Contract.at = at

return Contract
