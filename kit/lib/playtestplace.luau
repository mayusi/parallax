-- playtestplace.luau (kit) — the PLAYTEST PLACE: the game's own Rojo project built to a scratch place file that a
-- playtest runs in, with the playtests' FIXTURES in it. Phase 0, 2026-11-17: ten of twelve stored playtests were red
-- and most were not the game - they had run on a place the project was never synced into (smoke: "sync the project
-- into Studio"), and two scenarios need fixture movesets (tests/playtest/fixtures/ProbeParrySet.json) that only a
-- hand had ever put in the place.
--   <playtests>/fixtures/*.json            -> ReplicatedStorage.KitMoves.<name>   (a moveset module: Rojo makes a
--                                             .json a ModuleScript returning its table)
--   <playtests>/fixtures/<Child>/*.json    -> ReplicatedStorage.<Child>.<name>
-- -> build/playtest/KitPlaytestScratch.rbxlx. Never a real place: nothing is saved back, nothing uploaded. Open it in
-- Studio as its own window (RobloxStudioBeta.exe "<its full path>") and run `kit playtest run <name> --studio <id>`.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")
local Run = require("./run")

local PlaytestPlace = {}

PlaytestPlace.NAME = "KitPlaytestScratch"

-- every "$path" in a Rojo tree, written from another folder (`up` = the way back to the project's own folder)
local function rebase(node: any, up: string): any
	if type(node) ~= "table" then
		return node
	end
	local out = {}
	for k, v in node do
		if k == "$path" and type(v) == "string" then
			out[k] = up .. v
		else
			out[k] = rebase(v, up)
		end
	end
	return out
end

-- the fixtures a playtest place carries -> { { into = "KitMoves", name = "ProbeParrySet", path = "tests/.../x.json" } }
function PlaytestPlace.fixtures(dir: string): { { into: string, name: string, path: string } }
	local out = {}
	if not fs.isDir(dir) then
		return out
	end
	local entries = fs.readDir(dir)
	table.sort(entries)
	for _, e in entries do
		local p = `{dir}/{e}`
		if fs.isFile(p) and string.sub(e, -5) == ".json" then
			table.insert(out, { into = "KitMoves", name = string.sub(e, 1, -6), path = p })
		elseif fs.isDir(p) then
			local inner = fs.readDir(p)
			table.sort(inner)
			for _, f in inner do
				if string.sub(f, -5) == ".json" and fs.isFile(`{p}/{f}`) then
					table.insert(out, { into = e, name = string.sub(f, 1, -6), path = `{p}/{f}` })
				end
			end
		end
	end
	return out
end

-- the scratch project (pure). gameUp: the way from the scratch folder to the game's project file's folder (its own
-- "$path"s are relative to it); rootUp: the way to the project root (the fixtures' paths are). -> the project table
function PlaytestPlace.project(
	game: any,
	fixtures: { { into: string, name: string, path: string } },
	gameUp: string,
	rootUp: string
): any
	local tree = rebase(game.tree, gameUp)
	local rs = tree.ReplicatedStorage
	if type(rs) ~= "table" then
		rs = { ["$className"] = "ReplicatedStorage" }
		tree.ReplicatedStorage = rs
	end
	for _, f in fixtures do
		local holder = rs[f.into]
		if type(holder) ~= "table" then
			holder = { ["$className"] = "Folder" }
			rs[f.into] = holder
		end
		holder[f.name] = { ["$path"] = rootUp .. f.path }
	end
	local out = table.clone(game)
	out.name = PlaytestPlace.NAME
	out.tree = tree
	return out
end

-- build it -> the step, the place file
function PlaytestPlace.build(): (Run.Step, string)
	local dir = Config.build("playtest")
	local place = `{dir}/{PlaytestPlace.NAME}.rbxlx`
	local projectPath = Config.load().rojo
	local ok, game = pcall(serde.decode, "json" :: any, fs.readFile(projectPath))
	if not ok or type(game) ~= "table" or type(game.tree) ~= "table" then
		return Run.step("playtest place", false, `{projectPath}: not a Rojo project`, {
			next_action = `fix {projectPath}`,
		}),
			place
	end
	Config.ensureDir(dir)
	-- the project file's own folder, seen from the scratch folder
	local base = string.match(projectPath, "^(.*)/[^/]*$") or ""
	local rootUp = string.rep("../", #string.split(dir, "/"))
	local gameUp = rootUp .. (if base ~= "" then base .. "/" else "")
	local fixtures = PlaytestPlace.fixtures(Config.path("playtests") .. "/fixtures")
	local scratch = PlaytestPlace.project(game, fixtures, gameUp, rootUp)
	local projectFile = `{dir}/playtest.project.json`
	fs.writeFile(projectFile, serde.encode("json", scratch, true))
	local step =
		Run.spawn("rojo build (the playtest place)", Run.tool("rojo"), { "build", projectFile, "-o", place }, true)
	if not step.ok then
		step.result = { next_action = "read the rojo output above (lune run kit doctor checks the tool)" }
		return step, place
	end
	local names = {}
	for _, f in fixtures do
		table.insert(names, `{f.into}.{f.name}`)
	end
	return Run.step("playtest place", true, place, {
		summary = `{place}: the game's project + {#fixtures} fixture(s){if #names > 0
			then " (" .. table.concat(names, ", ") .. ")"
			else ""}`,
		fixtures = names,
	}),
		place
end

return PlaytestPlace
