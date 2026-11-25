-- review.luau (kit) — ONE piece's stages for ONE review page (the 3D studio-route plan, H8; wave 2 of the pipelines
-- plan the owner approved 2026-11-12). Why: the owner approved by telling a session, and what he was asked to look at
-- were files in folders. `kit review <name>` shows a piece's stages in order - a model sheet, a blockout, a beat
-- chart, a style sheet, the newest build's views, the dailies, the finished piece - each with the state it is in and
-- its pictures.
--
-- Nothing here judges, and nothing here writes. A stage's state is read from the SAME records the locks read
-- (board/locks.json through Locks.stage / Locks.waiver / Locks.approval, a chart's "approved", the vault's verdicts)
-- and by the same comparisons. A click is turned into the kit's OWN command by Review.plan (kit approve --stage, kit
-- vfx chart --approve, kit verdict, kit task rework) and run by kit/cmd/review.luau: the page can write no record a
-- typed command could not, and none of another shape.
--
-- The piece is the ACTIVE project's (the root, or the game named with --game): the page reads the folders the kit's
-- commands write to, so what a click records is about what the page showed (a review, 2026-11-12: the first build
-- looked a piece up in every game and let the command write the active one's).
--
-- A lane's later sprints add their stages here (V2 animatic, A1 design sheet, A2 blocking, W1 bible and greybox):
-- one entry in the lane's list, nothing else changes.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")
local LaneLocks = require("./lanelocks")
local Locks = require("./locks")
local Vault = require("./vault")

local Review = {}

Review.PORT = 8791
Review.LANES = { "3d", "vfx", "anim", "world" }
Review.WHO = "owner@review-page" -- who a verdict or a board card made by a click is signed by
Review.VIA = "review-page" -- what an approval made by a click says of itself (a typed one carries no "via")

export type Picture = { path: string, label: string }
export type Record = { words: string, date: string, score: string? }
export type Stage = {
	key: string,
	title: string,
	state: string, -- missing | waiting | approved | changed | waived | look | scored
	says: string, -- the state in plain words
	pictures: { Picture },
	record: Record?,
	actions: { string }, -- what a click may do here: approve, redo, verdict
	make: string?, -- the command that makes it, when there is nothing to show
	ref: string?, -- what an approval names when it is not the piece (a chart's set)
	wide: boolean?, -- its pictures are wide pairs: one a row on the page
	expect: string?, -- what the command is told was looked at (it refuses when that is no longer what is there)
	where: string?, -- the folder the page read it in, for a command that would otherwise pick its own (a chart's)
	seen: string?, -- what exactly is on the page: an approval or a verdict is taken only for this (see Review.fresh)
}

local IMAGES = { png = true, jpg = true, jpeg = true, gif = true }

local function isImage(path: string): boolean
	local ext = string.match(string.lower(path), "%.(%w+)$")
	return ext ~= nil and IMAGES[ext] == true
end

-- the build folder beside a piece's folder ("assets/effects" -> "build/", "games/X/assets/models" -> "games/X/build/")
local function buildRoot(dir: string): string
	local root = string.gsub(string.gsub(dir, "\\", "/"), "/?assets/[%w_]+/?$", "")
	return if root == "" or root == "." then "build/" else root .. "/build/"
end

local function readJson(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok and type(v) == "table" then v else nil
end

-- when a file or folder last changed ("-" when it is not there): a folder's time moves when a file is added to it
function Review.modified(path: string): string
	if not fs.isFile(path) and not fs.isDir(path) then
		return "-"
	end
	local ok, meta = pcall(fs.metadata, path)
	return if ok and meta and meta.modifiedAt then tostring(meta.modifiedAt.unixTimestampMillis) else "-"
end

-- pictures as they are now: what "seen" is for a stage with no id of its own
local function stamped(shown: { Picture }): string
	local parts = {}
	for _, p in shown do
		table.insert(parts, `{p.path}@{Review.modified(p.path)}`)
	end
	return table.concat(parts, "|")
end

local function pictures(list: { { string } }): { Picture }
	local out = {}
	for _, p in list do
		if fs.isFile(p[1]) then
			table.insert(out, { path = p[1], label = p[2] })
		end
	end
	return out
end

-- a file name's sort key: its text with every number padded, so beat10 comes after beat2
local function natural(name: string): string
	return (
		string.gsub(name, "%d+", function(d: string): string
			return string.rep("0", math.max(0, 6 - #d)) .. d
		end)
	)
end

-- a folder's pictures in name order (at most `cap`): `first` names sort to the front; `keep` chooses which count
-- (chosen BEFORE the cap: a folder's first twelve files are not its twelve pages)
local function folder(
	dir: string,
	cap: number,
	first: ((string) -> boolean)?,
	keep: ((string) -> boolean)?
): { Picture }
	local names = {}
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			if isImage(f) and (keep == nil or keep(f)) then
				table.insert(names, f)
			end
		end
	end
	table.sort(names, function(a, b)
		local fa, fb = first ~= nil and first(a), first ~= nil and first(b)
		if fa ~= fb then
			return fa
		end
		return natural(a) < natural(b)
	end)
	local out = {}
	for i = 1, math.min(cap, #names) do
		table.insert(out, { path = `{dir}/{names[i]}`, label = names[i] })
	end
	return out
end

-- the owner's newest verdict on a piece (never a model's reading of his words) -> its record, or nil
local function verdictOf(dept: string, name: string): Record?
	for _, n in Vault.verdicts(dept, name) do
		local front = n.front
		if Vault.ownersOwn(front) then
			local score = if front.score ~= nil
				then `{tostring(front.score)}/10`
				else tostring(front.direction or front.word or "")
			local words = string.match(n.body or "", "([^\r\n]+)") or ""
			return { words = words, date = tostring(front.date or ""), score = score }
		end
	end
	return nil
end

local function recordOf(rec: any): Record
	return { words = tostring(rec.words or ""), date = tostring(rec.date or "") }
end

-- an artefact the owner approves as it is now (LaneLocks.stageState's answer) + his record for it -> the stage.
-- The same comparison the lock makes: a record for another id is an approval of something he no longer sees; a
-- waiver (his own, for this step) passes the lock whatever the artefact is.
function Review.stageOf(
	key: string,
	title: string,
	st: any,
	rec: any?,
	make: string?,
	shown: { Picture },
	waiver: any?
): Stage
	-- what exactly is here now. expect: the artefact's id and, where it has one, the hash of its pictures (a style
	-- sheet drawn again from a new recording keeps its id and shows other pictures) - what the COMMAND can read again
	-- and is told. seen: that, and the picture files as they are on disk (a sheet drawn again with the same id is
	-- still another look) - what a CLICK must name
	local expect = `{key}:{tostring(st.id or "")}:{tostring(st.drawn or "")}`
	local seen = `{expect}|{stamped(shown)}`
	if waiver then
		return {
			key = key,
			title = title,
			state = "waived",
			says = `you waived this step ({tostring(waiver.date or "")}): the build lock does not ask for it`,
			pictures = shown,
			record = recordOf(waiver),
			actions = if st.ok then { "approve", "redo" } else {},
			seen = seen,
			expect = expect,
		}
	end
	if not st.ok then
		return {
			key = key,
			title = title,
			state = "missing",
			says = tostring(st.why or "not made yet"),
			pictures = shown,
			actions = {},
			make = make,
			seen = seen,
		}
	end
	if not rec then
		return {
			key = key,
			title = title,
			state = "waiting",
			says = "made, and waiting for your yes",
			pictures = shown,
			actions = { "approve", "redo" },
			seen = seen,
			expect = expect,
		}
	end
	local record = recordOf(rec)
	-- the lock's own comparison (LaneLocks.holds): the id and, where the artefact names its pictures, the ones he saw
	if not LaneLocks.holds(rec, st) then
		return {
			key = key,
			title = title,
			state = "changed",
			says = if rec.id ~= st.id
				then `it changed since you approved it ({record.date}): what you see now is not what you said yes to`
				elseif
					rec.drawn == nil
				then `your approval ({record.date}) does not say which pictures you saw: look at these, then say yes again`
				else `it was drawn again since you approved it ({record.date}): these are not the pictures you said yes to`,
			pictures = shown,
			record = record,
			actions = { "approve", "redo" },
			seen = seen,
			expect = expect,
		}
	end
	return {
		key = key,
		title = title,
		state = "approved",
		says = `approved {record.date}`,
		pictures = shown,
		record = record,
		actions = { "redo" },
		seen = seen,
	}
end

-- the finished piece: its pictures and the owner's verdict on it
local function final(dept: string, name: string, shown: { Picture }, make: string): Stage
	local v = verdictOf(dept, name)
	if v then
		return {
			key = "final",
			title = "The finished piece: your verdict",
			state = "scored",
			says = `your verdict {v.date}: {v.score or ""}`,
			pictures = shown,
			record = v,
			actions = { "verdict", "redo" },
			seen = "final:" .. stamped(shown),
		}
	end
	return {
		key = "final",
		title = "The finished piece: your verdict",
		state = if #shown > 0 then "waiting" else "missing",
		says = if #shown > 0 then "built, and waiting for your verdict" else "nothing finished to show yet",
		pictures = shown,
		actions = if #shown > 0 then { "verdict", "redo" } else {},
		make = if #shown > 0 then nil else make,
		seen = "final:" .. stamped(shown),
	}
end

-- ------------------------------------------------------------------ 3D: sheet, blockout, the newest build, final
local STAGE_TITLES = { sheet = "The model sheet", blockout = "The blockout" }

local function newestBuild(root: string): (string?, string)
	local best, at = nil, ""
	if fs.isDir(root) then
		for _, b in fs.readDir(root) do
			local meta = readJson(`{root}/{b}/meta.json`)
			local when = if meta then tostring(meta.at or "") else ""
			if fs.isDir(`{root}/{b}`) and (best == nil or when > at) then
				best, at = b, when
			end
		end
	end
	return best, at
end

local function modelsOf(opts: any?): string
	return if opts and opts.models then opts.models else Config.path("models")
end

local function stages3d(name: string, opts: any?): { Stage }
	local dir = modelsOf(opts)
	local out = {}
	for _, step in { "sheet", "blockout" } do
		local st = LaneLocks.stageState(name, step, dir)
		local shown = if st.png then pictures({ { st.png, STAGE_TITLES[step] } }) else {}
		table.insert(
			out,
			Review.stageOf(
				step,
				STAGE_TITLES[step],
				st,
				Locks.stage("3d", name, step),
				`lune run kit {step} {name}`,
				shown,
				Locks.waiver("3d", name, step)
			)
		)
	end
	local b = buildRoot(dir)
	local builds = `{b}judge/{name}/builds`
	local id, at = newestBuild(builds)
	local views = if id then folder(`{builds}/{id}`, 16) else {}
	table.insert(out, {
		key = "builds",
		title = "The newest build, beside its references",
		state = if #views > 0 then "look" else "missing",
		says = if #views > 0 then `build {id} ({at}): {#views} picture(s)` else "no build with its views yet",
		pictures = views,
		actions = if #views > 0 then { "redo" } else {},
		make = if #views > 0 then nil else `lune run kit asset {name}`,
		seen = "builds:" .. stamped(views),
	})
	table.insert(
		out,
		final(
			"3d",
			name,
			pictures({
				{ `{b}renders/{name}.png`, "the preview sheet" },
				{ `{b}renders/{name}_sheet.png`, "the look sheet" },
			}),
			`lune run kit asset {name}`
		)
	)
	return out
end

-- ------------------------------------------------------------------ VFX: the beat chart, the style sheet, dailies
-- a chart's plan as one comparable line: ONE reading for the scene gate and this page (kit/lib/chartplan.luau)
Review.chartPlan = require("./chartplan")

-- a chart + its picture -> the stage, by the scene gate's own rule (kit/cmd/content.luau sceneGate):
--   own.waiver   his waiver of the chart step for this piece: the gate asks no chart
--   own.approval his approval of the set or the piece in board/locks.json: it stands in for the chart's own "by"
--   own.before   the piece was built before a chart approval had to be his own look (kit/vfx/scene_gate.json)
-- else the chart's "approved" must be by "owner" exactly, with his words; and its plan must be the one he approved.
function Review.chartStage(set: string, chart: any?, shown: { Picture }, own: any?): Stage
	local title = `The beat chart ({set})`
	local make = `lune run kit vfx chart {set}`
	local plan = if chart then Review.chartPlan(chart) else ""
	-- own.drawnPlan: the plan the PICTURE shows (kit vfx chart writes it beside the picture). A chart edited after it
	-- was drawn has a picture of another plan, and a picture from before the kit kept this (nil) shows nobody knows
	-- which: neither is a chart he can say yes to - it is drawn again first (the drawing keeps the timing)
	local drawnPlan = if own then own.drawnPlan else nil
	local where = if own then own.where else nil
	-- the picture's file is one per set NAME: a game's set of the same name draws over the project's. A picture
	-- drawn from another folder's set is not this chart's, whatever its plan (own.drawnWhere: where it was drawn from)
	local elsewhere = own ~= nil
		and type(own.drawnWhere) == "string"
		and where ~= nil
		and string.lower(Locks.normal(own.drawnWhere)) ~= string.lower(Locks.normal(where))
	-- ... and the picture he is asked to approve holds ONE test frame of the key beat, the key beat marked, not guessed
	-- (the owner, 2026-11-11: a chart and one test frame, approved by him first; kit vfx chart says the same when it
	-- warns). own.test / own.guessed: what the drawing said of itself; unknown (nil) is not held against it
	local untested = own ~= nil and (own.test == false or own.guessed == true)
	-- (seen: the plan, the plan its picture shows, and the picture file itself - the same plan drawn again with
	-- another test frame is another look)
	local seen = `chart:{plan}:{tostring(drawnPlan or "")}|{stamped(shown)}`
	local current = #shown > 0 and drawnPlan == plan and not elsewhere and not untested
	if own and own.waiver then
		return {
			key = "chart",
			title = title,
			state = "waived",
			says = `you waived the chart for this piece ({tostring(own.waiver.date or "")}): the build lock does not ask for it`,
			pictures = shown,
			record = recordOf(own.waiver),
			actions = if chart and current then { "approve", "redo" } else {},
			ref = set,
			seen = seen,
			expect = plan,
			where = where,
		}
	end
	if not chart then
		return {
			key = "chart",
			title = title,
			state = "missing",
			says = "no beat chart yet",
			pictures = shown,
			actions = {},
			make = make,
			ref = set,
			seen = seen,
		}
	end
	-- a click may approve only what there is to look at: the chart's picture, of the chart's own plan
	local can = if current then { "approve", "redo" } else {}
	local undrawn = if #shown == 0
		then `; its picture is not drawn on this machine ({make})`
		elseif drawnPlan == nil then `; which plan its picture shows is not known: draw it again ({make})`
		elseif
			drawnPlan ~= plan
		then `; its picture is of an earlier plan - the chart was edited since it was drawn ({make})`
		elseif
			elsewhere
		then `; the picture on this machine was drawn from another folder's set of the same name ({tostring(
			own.drawnWhere
		)}): draw this one ({make})`
		elseif
			own ~= nil and own.guessed == true
		then `; its key beat was only guessed from the frames: mark it in the beat sheet or name it, then draw it again ({make} --key <beat #>)`
		elseif
			untested
		then `; its picture has no test frame of the key beat: build ONLY the key beat, record it, then draw the chart with it ({make} --test <mp4@seconds>)`
		else ""
	local a = chart.approved
	local words = type(a) == "table" and type(a.words) == "string" and a.words ~= ""
	local by = if type(a) == "table"
		then string.lower((string.gsub(tostring(a.by or ""), "^%s*(.-)%s*$", "%1")))
		else ""
	-- how the record is marked, for the line that says it is not his: "owner" written by somebody else names who
	local mark = if type(a) ~= "table"
		then ""
		elseif by == "owner" and a.who ~= nil then `"owner" by {tostring(a.who)}`
		else `"{tostring(a.by)}"`
	local standing = own and own.approval -- his record in board/locks.json
	-- the gate's rule: an owner's record (Locks.isOwner: "by" AND, when it is there, "who"), and his own look -
	-- "owner" exactly - unless he approved the piece in the locks or it was built before that rule
	local his = words
		and (standing ~= nil or (Locks.isOwner(a) and (by == "owner" or (own ~= nil and own.before == true))))
	if not his then
		return {
			key = "chart",
			title = title,
			state = if current then "waiting" else "missing",
			says = (
				if words and not (by == "owner" and Locks.isOwner(a))
					then `marked {mark}, which is not your own look at this chart: waiting for your yes`
					else "drawn, and waiting for your yes"
			) .. undrawn,
			pictures = shown,
			actions = can,
			make = if current then nil else make,
			ref = set,
			seen = seen,
			expect = plan,
			where = where,
		}
	end
	local record = recordOf(a)
	if type(a.plan) == "string" and a.plan ~= plan then
		return {
			key = "chart",
			title = title,
			state = "changed",
			says = `the chart was re-timed since you approved it ({record.date}): look again{undrawn}`,
			pictures = shown,
			record = record,
			actions = can,
			ref = set,
			seen = seen,
			expect = plan,
			where = where,
		}
	end
	local how = if by == "owner" and Locks.isOwner(a)
		then ""
		elseif standing then " (by your approval of the piece in the locks)"
		else " (an approval from before 2026-11-11, which the lock still accepts for this piece)"
	-- (an approved chart's picture is a courtesy: only a picture that is missing, or KNOWN to be of another plan, is
	-- worth a line here)
	local picture = if #shown == 0 or (drawnPlan ~= nil and drawnPlan ~= plan) or elsewhere then undrawn else ""
	return {
		key = "chart",
		title = title,
		state = "approved",
		says = `approved {record.date}{how}{picture}`,
		pictures = shown,
		record = record,
		actions = if #shown > 0 then { "redo" } else {},
		ref = set,
		seen = seen,
	}
end

-- the pieces built before a chart approval had to be the owner's own look (the scene gate reads the same list)
local function builtBefore(name: string): boolean
	local gate = readJson("kit/vfx/scene_gate.json")
	local list = if gate and type(gate.chart_owner) == "table" then gate.chart_owner.grandfathered else nil
	return type(list) == "table" and table.find(list, name) ~= nil
end

-- where an effect's set is measured: beside the effect, as the scene gate reads it (kit/cmd/content.luau: `{dir}/
-- refs_measured/`); kit vfx chart --approve writes the same file when the set is there (kit/vfx/chart.py)
local function measuredOf(dir: string): string
	return `{dir}/refs_measured`
end

-- the effects folder the page reads: the active project's, or a fixture project's (opts.effects, with a locks file
-- of its own). Its commands are told the same folder, so the page and what a click runs cannot read two
local function effectsOf(opts: any?): string
	return if opts and opts.effects then opts.effects else Config.path("vfx")
end

-- is `name` a scene SET of this effects folder (its beat sheet or its chart is there)?
function Review.isSet(name: string, dir: string): boolean
	return fs.isFile(`{measuredOf(dir)}/{name}.chart.json`) or fs.isFile(`{measuredOf(dir)}/{name}.beats.md`)
end

local function stagesVfx(name: string, opts: any?): { Stage }
	local dir = effectsOf(opts)
	local out = {}
	local preset = readJson(`{dir}/{name}.json`)
	local set = if preset
			and type(preset.scene) == "table"
			and type(preset.scene.set) == "string"
		then preset.scene.set
		else nil
	-- a scene SET with no effect built from it yet is a piece too: its chart and its timing animatic are approved
	-- before the effect's look is paid for (the page then ends there: nothing else exists)
	local setOnly = preset == nil and Review.isSet(name, dir)
	if setOnly then
		set = name
	end
	if set then
		-- what the picture on this machine shows (kit vfx chart writes it beside the picture when it draws)
		local made = readJson(`{Config.build("vfx")}/charts/{set}.drawn.json`)
		table.insert(
			out,
			Review.chartStage(
				set,
				readJson(`{measuredOf(dir)}/{set}.chart.json`),
				pictures({ { `{Config.build("vfx")}/charts/{set}.png`, "the beat chart" } }),
				{
					waiver = Locks.waiver("vfx", name, "chart"),
					approval = Locks.approval("vfx", set) or Locks.approval("vfx", name),
					before = builtBefore(name),
					drawnPlan = if made and type(made.plan) == "string" then made.plan else nil,
					drawnWhere = if made and type(made.measured) == "string" then made.measured else nil,
					test = if made then made.test == true else nil,
					guessed = if made then made.guessed == true else nil,
					where = measuredOf(dir),
				}
			)
		)
		-- the timing animatic (kit vfx animatic <set>; V2): the set's motion in flat shapes at the chart's timing,
		-- beside the scene - the video first, then each beat's page (the very files its "drawn" is the hash of)
		local ani = LaneLocks.vfxStageState(set, "animatic", dir)
		local motion: { Picture } = {}
		if ani.exists and not ani.stale then
			for _, f in ani.shown or {} do
				if fs.isFile(f) then
					local isVideo = string.sub(f, -4) == ".mp4"
					table.insert(motion, {
						path = f,
						label = if isVideo
							then "the scene | the animatic, beat after beat, then the animatic alone"
							else (string.match(f, "([^/]+)$") or f),
					})
				end
			end
			if #motion ~= #(ani.shown or {}) then
				ani = {
					ok = false,
					id = ani.id,
					why = "a file of the animatic is missing: make it again",
					exists = false,
				}
				motion = {}
			end
		end
		local animatic = Review.stageOf(
			"animatic",
			`The timing animatic ({set}): the motion in flat shapes, beside the scene`,
			ani,
			Locks.stage("vfx", set, "animatic"),
			`lune run kit vfx animatic {set}`,
			motion,
			nil
		)
		animatic.ref = set
		animatic.wide = true
		table.insert(out, animatic)
	end
	if setOnly then
		return out
	end
	-- the style sheet (kit vfx stylesheet): every beat's look, ours beside the scene's - one pair a picture. Shown
	-- only when there IS a sheet on this machine, of the preset and the recording here now (a folder a failed drawing
	-- left is not one; pictures of an older recording are not this effect's look any more). No waiver: no build lock
	-- asks for the style sheet yet, so there is no step of that name to waive
	local sheet = LaneLocks.vfxStageState(name, "style", dir)
	-- the pictures shown are the very files the sheet's "drawn" is the hash of, in order, every one of them (a
	-- review, 2026-11-12: the page showed a folder's first 40 pictures and recorded a yes for all of them)
	local pairsShown: { Picture } = {}
	if sheet.exists and not sheet.stale then
		for _, f in sheet.files or {} do
			if fs.isFile(`{Config.build("vfx")}/stylesheet/{name}/{f}`) then
				table.insert(pairsShown, { path = `{Config.build("vfx")}/stylesheet/{name}/{f}`, label = f })
			end
		end
		if #pairsShown ~= #(sheet.files or {}) then -- (a picture went missing between the check and here)
			sheet = {
				ok = false,
				id = sheet.id,
				why = "a pair picture of the sheet is missing: draw it again",
				exists = false,
			}
			pairsShown = {}
		end
	end
	local style = Review.stageOf(
		"style",
		"The style sheet: every beat's look, ours beside the scene's",
		sheet,
		Locks.stage("vfx", name, "style"),
		`lune run kit vfx stylesheet {name}`,
		pairsShown,
		nil
	)
	style.wide = true
	table.insert(out, style)
	-- the dailies (kit vfx dailies; every recorded play makes them): each beat's page, the chart's key beat first
	local look = `{Config.build("vfx")}/dailies/{name}`
	local numbers = readJson(`{look}/dailies.json`)
	local key, said = nil, ""
	if numbers and type(numbers.beats) == "table" then
		for _, b in numbers.beats do
			if type(b) == "table" and b.key == true then
				key = `beat{tostring(b.index or 0)}_page.png`
				said = if type(b.differences) == "table" and #b.differences > 0
					then table.concat(b.differences, "; ")
					else "the key beat's timing agrees with the scene within a film frame"
			end
		end
	end
	local only = folder(look, 12, function(f: string): boolean
		return f == key
	end, function(f: string): boolean
		return string.find(f, "_page%.png$") ~= nil
	end)
	table.insert(out, {
		key = "dailies",
		title = "Dailies: ours beside the scene, frame by frame",
		state = if #only > 0 then "look" else "missing",
		says = if #only > 0
			then (if said ~= "" then said else `{#only} beat page(s)`)
			else "no recorded play with dailies yet",
		pictures = only,
		actions = if #only > 0 then { "redo" } else {},
		make = if #only > 0 then nil else `lune run kit vfx play {name} --record`,
		seen = "dailies:" .. stamped(only),
	})
	table.insert(
		out,
		final(
			"vfx",
			name,
			pictures({
				{ `{Config.build("vfx")}/booth/{name}_play_all.png`, "the recording, every view" },
				{ `{Config.build("vfx")}/booth/{name}_play_hero.png`, "the recording, hero view" },
				{ `{Config.build("vfx")}/{name}.png`, "the frame strip" },
			}),
			`lune run kit vfx play {name} --record`
		)
	)
	return out
end

-- ------------------------------------------------------------------ animation, world: the look, then the verdict
local function looked(lane: string, name: string, shown: { Picture }, make: string): { Stage }
	return {
		{
			key = "look",
			title = "What was made, as it looks now",
			state = if #shown > 0 then "look" else "missing",
			says = if #shown > 0 then `{#shown} picture(s)` else "nothing to look at yet",
			pictures = shown,
			actions = if #shown > 0 then { "redo" } else {},
			make = if #shown > 0 then nil else make,
			seen = "look:" .. stamped(shown),
		},
		final(lane, name, shown, make),
	}
end

local function stagesAnim(name: string): { Stage }
	local a = `{Config.build("animations")}/{name}`
	return looked(
		"anim",
		name,
		pictures({
			{ `{a}.r6.look.png`, "the look sheet (R6)" },
			{ `{a}.look.png`, "the look sheet" },
			{ `{a}.r6.look.gif`, "in motion (R6)" },
			{ `{a}.look.gif`, "in motion" },
		}),
		`lune run kit anim look {name}`
	)
end

local function stagesWorld(name: string): { Stage }
	return looked(
		"world",
		name,
		pictures({ { `{Config.build("worlds")}/look/{name}.png`, "the look shots" } }),
		`lune run kit world look {name}`
	)
end

-- which lane a piece of the ACTIVE project is in (where its own file is), or nil. A 3D piece is one from its BRIEF
-- on - the model sheet and the blockout are approved before any build script exists
function Review.laneOf(name: string): string?
	local models, effects = Config.path("models"), Config.path("vfx")
	for _, f in { `{models}/{name}.brief.md`, `{models}/build_{name}.py`, `{models}/{name}.sheet.json` } do
		if fs.isFile(f) then
			return "3d"
		end
	end
	if fs.isFile(`{effects}/{name}.json`) or Review.isSet(name, effects) then
		return "vfx"
	end
	for _, lane in { "anim", "world" } do
		if LaneLocks.pieceDir(lane, name) then
			return lane
		end
	end
	return nil
end

-- a piece's stages in the order they are made. opts.models / opts.effects: a fixture project's folder
function Review.stages(lane: string, name: string, opts: { models: string?, effects: string? }?): { Stage }
	if lane == "3d" then
		return stages3d(name, opts)
	elseif lane == "vfx" then
		return stagesVfx(name, opts)
	elseif lane == "anim" then
		return stagesAnim(name)
	elseif lane == "world" then
		return stagesWorld(name)
	end
	return {}
end

-- a line under the page's head, when the stages alone could mislead. For 3D it is a general truth, not a reading of
-- this piece: the build lock's own answer depends on the piece's tier, its build script and lists that the lock
-- may WRITE while it reads them (a review, 2026-11-12) - and nothing on this page writes.
function Review.note(lane: string, _name: string, _stages: { Stage }, _opts: any?): string?
	if lane == "3d" then
		return "A build asks for the model sheet's and the blockout's approval only of a NEW complex, hero or aaa piece (kit asset says so when it refuses). On a prop, or a piece from before the rule, a yes here is yours to give and no build waits for it."
	end
	return nil
end

-- the files and folders whose change means the page should be read again - also the ones a stage has no picture
-- from YET (a blockout drawn, a new build, dailies made after the page was opened)
function Review.watch(lane: string, name: string, opts: { models: string?, effects: string? }?): { string }
	local watched = Review.watched(lane, name, opts)
	-- his verdicts (the finished piece's state): a new one is a new file in the lane's own folder of the vault
	table.insert(watched, `kit/knowledge/vault/{lane}/verdicts`)
	return watched
end

function Review.watched(lane: string, name: string, opts: { models: string?, effects: string? }?): { string }
	if lane == "3d" then
		local dir = modelsOf(opts)
		local b = buildRoot(dir)
		local builds = `{b}judge/{name}/builds`
		local newest = newestBuild(builds)
		return {
			dir,
			`{dir}/{name}.brief.md`,
			`{dir}/{name}.sheet.json`,
			`{dir}/{name}.blockout.json`,
			builds,
			-- (a folder's time moves when a file is added to IT, not to a folder inside it: the newest build's own
			-- folder is watched too, for views still being written into it)
			if newest then `{builds}/{newest}` else builds,
			`{b}renders`,
		}
	elseif lane == "vfx" then
		local dir = effectsOf(opts)
		local preset = readJson(`{dir}/{name}.json`)
		local set = if preset and type(preset.scene) == "table" then tostring(preset.scene.set or "") else ""
		local watched = {
			`{dir}/{name}.json`,
			measuredOf(dir),
			-- (files rewritten in place move their own time, never their folder's)
			`{measuredOf(dir)}/{set}.chart.json`,
			`{Config.build("vfx")}/charts/{set}.png`,
			`{Config.build("vfx")}/charts/{set}.drawn.json`,
			"kit/vfx/scene_gate.json", -- (the pieces whose older chart approval still counts)
			Config.build("vfx") .. "/animatic",
			`{Config.build("vfx")}/animatic/{if set == "" then name else set}.plan.json`,
			`{Config.build("vfx")}/animatic/{if set == "" then name else set}_side.mp4`,
			`{Config.build("vfx")}/dailies/{if set == "" then name else set}_animatic`,
			Config.build("vfx") .. "/stylesheet",
			`{Config.build("vfx")}/stylesheet/{name}`,
			`{Config.build("vfx")}/stylesheet/{name}.json`,
			`{Config.build("vfx")}/dailies/{name}`,
			`{Config.build("vfx")}/dailies/{name}/dailies.json`,
			Config.build("vfx") .. "/booth",
		}
		if fs.isDir(Config.build("vfx") .. "/booth") then
			for _, f in fs.readDir(Config.build("vfx") .. "/booth") do
				if string.sub(f, 1, #name + 6) == `{name}_play_` and string.sub(f, -4) == ".mp4" then
					table.insert(watched, `{Config.build("vfx")}/booth/{f}`) -- (a recording made again: the style sheet is stale)
				end
			end
		end
		return watched
	elseif lane == "anim" then
		return { Config.build("animations") }
	elseif lane == "world" then
		return { `{Config.build("worlds")}/look` }
	end
	return {}
end

-- the only files the page may fetch: the pictures the stages name right now
function Review.allowed(stages: { Stage }): { [string]: boolean }
	local set = {}
	for _, s in stages do
		for _, p in s.pictures do
			set[p.path] = true
		end
	end
	return set
end

-- is what the page showed still what is there? An approval or a verdict is for what he SAW: when the sheet was
-- redrawn or the chart re-timed while he was typing, the click is refused and the page shows the new one
function Review.fresh(stage: Stage, action: string, seen: any): boolean
	if action ~= "approve" and action ~= "verdict" then
		return true
	end
	return type(seen) == "string" and seen == stage.seen
end

-- one line a stage, for a session (kit review <name> --stages)
function Review.line(s: Stage): string
	local record = if s.record then ` - "{s.record.words}"` else ""
	local how = if s.make then ` -> {s.make}` else ""
	return `{s.key}: {string.upper(s.state)} - {s.says}{record}{how}`
end

local function clean(words: any): string
	local text = string.gsub(string.gsub(tostring(words or ""), "[\r\n\t]+", " "), "^%s+", "")
	return (string.gsub(text, "%s+$", ""))
end

-- a click -> the kit's own command: (command name, its arguments), or nil and why not. Nothing is run here.
--   approve  his yes to the stage as it is now, in HIS words (a click with no words is refused: the record is his
--            words, and the page invents none)
--   redo     what to do again, on the board (a rework card)
--   verdict  the finished piece: 0-10, keep or redo, with his words (route: what failed, needed at 3 or less)
function Review.plan(
	lane: string,
	name: string,
	stage: Stage,
	action: string,
	words: any,
	score: any?,
	opts: { models: string?, effects: string?, route: string? }?
): (string?, any)
	if not table.find(stage.actions, action) then
		return nil, `{stage.title}: nothing to {action} here ({stage.says})`
	end
	local text = clean(words)
	if string.sub(text, 1, 1) == "-" then
		return nil, "start the note with a word, not a dash"
	end
	if action == "approve" then
		if #text < 2 then
			return nil, "an approval is recorded in your words: write them in the note (a plain yes is enough)"
		end
		if stage.key == "chart" and stage.ref then
			-- the chart he LOOKED AT (its plan), in the folder the page read it in (kit vfx chart would otherwise
			-- pick a folder of its own from the environment)
			local args = { "chart", stage.ref, "--approve", text, "--by", "owner", "--via", Review.VIA }
			if stage.expect and stage.expect ~= "" then
				table.insert(args, "--expect-plan")
				table.insert(args, stage.expect)
			end
			if stage.where then
				table.insert(args, "--measured")
				table.insert(args, stage.where)
			end
			return "vfx", args
		end
		-- (a stage of a SET - the timing animatic - is recorded under the set's name, whichever piece's page showed it)
		local piece = if stage.key == "animatic" and stage.ref then stage.ref else name
		local args = { lane, piece, text, "--by", "owner", "--stage", stage.key, "--via", Review.VIA }
		if stage.expect then -- (what the page showed: the command refuses when that is no longer what is there)
			table.insert(args, "--expect")
			table.insert(args, stage.expect)
		end
		if lane == "3d" and opts and opts.models then
			table.insert(args, "--models")
			table.insert(args, opts.models)
		elseif lane == "vfx" then
			table.insert(args, "--effects")
			table.insert(args, effectsOf(opts))
		end
		return "approve", args
	elseif action == "redo" then
		if #text < 3 then
			return nil, "say what to do again: the note is what the session reads"
		end
		return "task", { "rework", `{name} - {stage.title}: {text}`, "--area", lane, "--as", Review.WHO }
	elseif action == "verdict" then
		local value = string.lower(clean(score))
		local n = if string.match(value, "^%d+%.?%d*$") then tonumber(value) else nil
		if not ((n and n >= 0 and n <= 10) or value == "keep" or value == "redo") then
			return nil, "a verdict is a number from 0 to 10, or keep, or redo"
		end
		if #text < 3 then
			return nil, "a verdict needs your words: they are what the next piece learns from"
		end
		local args = { Vault.KIND_OF_DEPT[lane] or lane, name, value, text }
		if stage.pictures[1] then
			table.insert(args, "--shown")
			table.insert(args, stage.pictures[1].path)
		end
		local route = if opts then clean(opts.route) else ""
		if route ~= "" and string.sub(route, 1, 1) ~= "-" then
			table.insert(args, "--route")
			table.insert(args, route)
		end
		table.insert(args, "--as")
		table.insert(args, Review.WHO)
		return "verdict", args
	end
	return nil, `unknown action "{action}"`
end

-- a planned command as the line a person would type (what a dry run shows, what the server logs)
function Review.typed(command: string, args: { string }): string
	local out = { "lune run kit", command }
	for _, a in args do
		local plain = (string.gsub(a, '"', "'"))
		table.insert(out, if string.find(a, '[%s"]') then `"{plain}"` else a)
	end
	return table.concat(out, " ")
end

return Review
