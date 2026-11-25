--!strict
-- parts.luau (lib) — the parts libraries (kit/tools/parts.py; board/plans/archive/2026-11-09-parts-libraries-plan.md, P0),
-- shared by `kit parts` (kit/cmd/parts.luau) and the verdict hook (kit/cmd/vault.luau): the owner's verdict on a piece
-- credits, BY ITSELF, the cards its parts sheet built from and the parts its words name.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Run = require("./run")
local Vault = require("./vault")

local Parts = {}

-- the lanes that keep a parts library (each its own: departments never share one)
Parts.LANES = { "3d", "anim", "vfx", "ui", "world", "sfx", "code", "qa" }

function Parts.lane(name: string?): string?
	return if name and table.find(Parts.LANES, name) then name else nil
end

-- the owner's verdict on `name` credits its parts (nil when the lane keeps no parts library yet)
function Parts.credit(dept: string?, name: string): string?
	local lane = Parts.lane(dept)
	if not lane or not fs.isFile(`{Vault.dir(lane)}/parts/kinds.json`) then
		return nil
	end
	local step =
		Run.spawn(`parts {lane} credit`, Run.tool("python"), { "kit/tools/parts.py", lane, "credit", name }, true)
	local r = step.result or {}
	if not step.ok then
		return `the {lane} parts library could not credit {name}: {tostring(
			r.summary or string.sub(step.tail or "", -120)
		)}`
	end
	return `the {lane} parts library: {tostring(r.summary)}`
end

-- today's lesson ranking for the lane's fixed questions, written to build/parts/<lane>/today.json as the baselines of
-- `kit parts <lane> label | eval`:
--   "today"     exactly what `kit start <lane> --for "<brief>"` shows a session starting the piece (kit/cmd/start.luau
--               -> Routes.lines): the route's FIRST stage, the stage words, the piece's family, then Vault.pick
--   "today-all" the same ranking over every stage's lessons (a session that reads each stage's list in turn)
-- Returns how many questions it ranked.
function Parts.writeToday(lane: string, k: number): number
	local qpath = `{Vault.dir(lane)}/parts/questions.json`
	if not fs.isFile(qpath) then
		return 0
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(qpath))
	if not ok or type(data) ~= "table" or type(data.questions) ~= "table" then
		return 0
	end
	local Families = require("./families")
	local Routes = require("./routes")
	local first = Routes.stages(lane)[1]
	local stageWords = Routes.words(lane)
	local today: { [string]: { string } } = {}
	local all: { [string]: { string } } = {}
	local n = 0
	for _, q in data.questions :: { any } do
		if type(q) == "table" and type(q.id) == "string" and type(q.brief) == "string" then
			local family = if type(q.piece) == "string" then Families.ofPiece(lane, q.piece) else nil
			local ids, idsAll = {}, {}
			local ranked = Vault.rank(lane, q.brief, { stage = first, stageWords = stageWords, family = family })
			for _, r in Vault.pick(ranked, k, true) do
				table.insert(ids, r.id)
			end
			for _, r in Vault.pick(Vault.rank(lane, q.brief, { family = family }), k, true) do
				table.insert(idsAll, r.id)
			end
			today[q.id] = ids
			all[q.id] = idsAll
			n += 1
		end
	end
	local out = { today = today, ["today-all"] = all, stage = first }
	local dir = `build/parts/{lane}`
	if not fs.isDir(dir) then
		fs.writeDir(dir)
	end
	fs.writeFile(`{dir}/today.json`, serde.encode("json", out, true))
	return n
end

return Parts
