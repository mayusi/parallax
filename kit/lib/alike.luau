--!strict
-- alike.luau (lib) — search by LOOK, shared by `kit alike` (kit/cmd/alike.luau) and the closest-past-pieces lines
-- (kit/lib/routes.luau): the vision tool's argv, and the past pieces that look closest as printable lines
-- (kit/vision/alike.py; 2026-11-08, sprint 4).
local fs = require("@lune/fs")

local Run = require("./run")

local Alike = {}

Alike.INDEX = "build/look/index.json" -- the look index (a spec points it elsewhere)

-- the vision tool's argv for a kit alike call
function Alike.argv(args: { string }, flags: { [string]: any }): { string }
	local sub = args[1]
	local argv = { "kit/vision/run.py", "alike" }
	if sub == "index" or sub == "dupes" then
		table.insert(argv, sub)
	elseif sub == "round" then
		table.insert(argv, "round")
		table.insert(argv, args[2])
	else
		table.insert(argv, "near")
		table.insert(argv, sub)
	end
	for _, key in { "lane", "k", "min", "kind", "as", "round" } do
		if type(flags[key]) == "string" then
			table.insert(argv, "--" .. key)
			table.insert(argv, flags[key])
		end
	end
	for _, key in { "refs", "cached" } do
		if flags[key] then
			table.insert(argv, "--" .. key)
		end
	end
	return argv
end

-- the closest past pieces by look as printable lines (nil when there is no index or nothing to say; never fails the
-- caller). `cached`: only pictures already in the index - no model is loaded (kit start, kit help --stage)
-- `as`: the piece a fresh picture shows (its own older pictures stay out of the list)
function Alike.lines(target: string, lane: string?, k: number?, cached: boolean?, as: string?): { string }?
	if not fs.isFile(Alike.INDEX) then
		return nil
	end
	local flags: { [string]: any } = { k = tostring(k or 3), cached = cached, as = as }
	if lane then
		flags.lane = lane
	end
	-- cached: quiet (it prints inside kit start / kit help); a fresh picture goes to the warm vision worker if one runs
	-- (a plain if: an if-expression keeps only pcall's first value)
	local ok, step
	if cached then
		ok, step = pcall(Run.spawn, `alike {target}`, Run.tool("python"), Alike.argv({ target }, flags), true)
	else
		ok, step = pcall(Run.content, `alike {target}`, Run.tool("python"), Alike.argv({ target }, flags))
	end
	local r = if ok and type(step) == "table" then step.result else nil
	if type(r) ~= "table" or type(r.lines) ~= "table" or #r.lines == 0 then
		return nil
	end
	return r.lines
end

-- a pick round's candidates against the owner's own loved and rejected pieces of the lane, by look (kit alike round:
-- a report, never a gate) -> a step that always passes and prints the lines
function Alike.roundStep(move: string, round: string?): Run.Step
	local lines: { string } = {}
	local summary = "no look index yet (lune run kit alike index)"
	if fs.isFile(Alike.INDEX) then
		local args = { "round", move }
		local ok, step =
			pcall(Run.content, `alike round {move}`, Run.tool("python"), Alike.argv(args, { round = round }))
		local r = if ok and type(step) == "table" then step.result else nil
		if type(r) == "table" then
			lines = if type(r.lines) == "table" then r.lines else {}
			summary = tostring(r.summary or summary)
		end
	end
	for _, l in lines do
		print("    " .. l)
	end
	return Run.step("looks alike (kit alike round)", true, table.concat(lines, "\n"), { summary = summary })
end

-- what fresh previews LOOK like among the past pieces, for at most three named pieces (a whole-project rebuild would
-- embed every picture): a step that always passes and prints the lines. `dir` holds <piece>.png
-- the lane's taste model orders a pick round (kit/vision/taste.py: the owner's own scores, leave-one-out agreement
-- beside it; off until the lane has enough - a report, never a gate) -> a step that always passes
function Alike.tasteStep(lane: string, move: string, round: string?): Run.Step
	local lines: { string } = {}
	local summary = "no look index yet (lune run kit alike index)"
	if fs.isFile(Alike.INDEX) then
		local target = if round then `{move}/r{round}` else move
		local ok, step = pcall(
			Run.spawn,
			`taste order {target}`,
			Run.tool("python"),
			{ "kit/vision/run.py", "taste", "order", lane, target },
			true
		)
		local r = if ok and type(step) == "table" then step.result else nil
		if type(r) == "table" then
			lines = if type(r.lines) == "table" then r.lines else {}
			summary = tostring(r.summary or summary)
		end
	end
	for _, l in lines do
		print("    " .. l)
	end
	return Run.step("taste order (kit taste)", true, table.concat(lines, "\n"), { summary = summary })
end

function Alike.previewStep(dept: string, names: { string }?, dir: string): Run.Step
	local lines: { string } = {}
	if names and #names > 0 and #names <= 3 then
		for _, n in names do
			local pic = `{dir}/{n}.png`
			if fs.isFile(pic) then
				for _, l in Alike.lines(pic, dept, 3, false, n) or {} do
					table.insert(lines, `{n}: {l}`)
				end
			end
		end
	end
	for _, l in lines do
		print("    " .. l)
	end
	return Run.step(
		`looks alike (kit alike, {dept})`,
		true,
		table.concat(lines, "\n"),
		{ summary = if #lines > 0 then `{#lines} past piece(s) by look` else "nothing named to compare" }
	)
end

return Alike
