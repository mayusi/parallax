-- fit.luau — FITTING against references (CMA-ES, kit/blender/cmaes.py) — never against the quality score:
--   kit fit <asset> [--evals 120] [--only a,b] [--write]
--        the asset's a.param() numbers fitted to its references (silhouette IoU per view + proportions) over --geo
--        builds through a persistent Blender -> --write keeps them in assets/models/<asset>.params.json
--   kit fit camera <photo> --asset <name> [--blend <file>] [--fov <deg>] [--evals 3200] [--ignore <groups>]
--        [--exclude "x0,y0,x1,y1;..."]
--        which camera took the photo: the model's silhouette matched to the photo's cut-out (yaw, pitch, roll, framing,
--        lens; the lens comes from the photo's EXIF when it has one) -> build/camfit/<name>/camera.json + overlay.png
local fs = require("@lune/fs")

local Config = require("../lib/config")
local Run = require("../lib/run")
local Worker = require("../lib/worker")

local function option(rest: { string }, flag: string): string?
	for i, a in rest do
		if a == flag then
			return rest[i + 1]
		end
	end
	return nil
end

local function camera(rest: { string }): Run.Step
	local photo = rest[1]
	local asset = option(rest, "--asset")
	local blend = option(rest, "--blend") or (if asset then `{Config.build("models")}/{asset}.blend` else nil)
	if not photo or not fs.isFile(photo) or not blend or not fs.isFile(blend) then
		return Run.step("fit camera", false, "", {
			summary = `fit camera: needs a photo and a built asset ({photo or "<photo>"}, {blend or "<asset>.blend"})`,
			next_action = "lune run kit asset <name> first (a full build saves its .blend), then: lune run kit fit camera <photo> --asset <name>",
		})
	end
	local name = asset or string.match(photo, "([^/]+)%.%w+$") or "photo"
	local out = `{Config.build("camfit")}/{name}`
	fs.writeDir(out)
	local mask = `{out}/mask.png`
	local cut = Run.content("cutout", Run.tool("python"), { "kit/vision/run.py", "cutout", photo, "-o", mask })
	if not cut.ok then
		return cut
	end
	local fov = option(rest, "--fov")
	if not fov then
		local ex = Run.content("exif lens", Run.tool("python"), { "kit/vision/exif_fov.py", photo })
		if ex.ok and ex.result and type(ex.result.fov) == "number" then
			fov = tostring(ex.result.fov)
		end
	end
	local args = {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/blender/camfit.py",
		"--",
		blend,
		mask,
		"--out",
		out,
		"--evals",
		option(rest, "--evals") or "3200",
	}
	if fov then
		table.insert(args, "--fov")
		table.insert(args, fov)
	end
	local ignore = option(rest, "--ignore") -- model groups the photo shows differently (a deployed bipod)
	if ignore then
		table.insert(args, "--ignore")
		table.insert(args, ignore)
	end
	local exclude = option(rest, "--exclude") -- photo regions that do not count ("x0,y0,x1,y1;...", photo pixels)
	if exclude then
		table.insert(args, "--exclude")
		table.insert(args, exclude)
	end
	-- the asset's anchors marked on the photo (a thin object's pose), a known rough view, more starts, another manifest
	for _, flag in { "--points", "--start", "--starts", "--manifest" } do
		local v = option(rest, flag)
		if v then
			table.insert(args, flag)
			table.insert(args, v)
		end
	end
	return Run.content("fit camera", Run.tool("blender"), args)
end

local function params(asset: string, rest: { string }): Run.Step
	-- (fitting rebuilds the piece over and over: its clock and its route hold here as in kit asset, and so does
	-- the owner's approval of its model sheet - fitting is shape rounds)
	local staged = require("../lib/lanelocks").stages(asset, nil, nil, "geo")
	if staged then
		return Run.step("fit", false, "", {
			summary = `fit: {asset} skipped a stage approval (model sheet)`,
			next_action = staged,
		})
	end
	local stop = require("./content").prebuild(asset, Config.path("models"))
	if stop then
		return Run.step("fit", false, "", { summary = stop.summary, next_action = stop.next_action })
	end
	local h, why = Worker.start(1200)
	if not h then
		return Run.step("fit", false, "", { summary = `fit: {why}`, next_action = "lune run kit doctor" })
	end
	local args = {
		"kit/blender/fit.py",
		asset,
		"--models",
		Config.path("models"),
		"--build",
		Config.path("build"),
	}
	for _, a in rest do
		table.insert(args, a)
	end
	local step = Run.content(`fit {asset}`, Run.tool("python"), args)
	Worker.stop(h :: any)
	return step
end

return function(Cli: any)
	Cli.command(
		"3d",
		"fit",
		"fit <asset> [--write] [--weights side=1,front=0.4] [--hold <view>] | fit camera <photo> --asset <name>",
		"fit against references (never the score): an asset's a.param() numbers, or the camera a photo was taken from",
		function(rawArgs)
			local sub = rawArgs[1]
			local rest = { table.unpack(rawArgs, 2) }
			local step: Run.Step
			if sub == "camera" then
				step = camera(rest)
			elseif
				sub
				and (
					fs.isFile(`{Config.path("models")}/build_{sub}.py`)
					or (
						table.find(rest, "--models")
						and fs.isFile(`{rest[(table.find(rest, "--models") :: number) + 1]}/build_{sub}.py`)
					)
				)
			then
				step = params(sub, rest)
			else
				return Run.report(
					"fit",
					{},
					Run.CODES.USAGE,
					"fit: needs an asset (its a.param() numbers) or camera",
					"lune run kit fit <asset>   |   lune run kit fit camera <photo> --asset <name>"
				)
			end
			local r = step.result or {}
			return Run.report(
				"fit",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "fit: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end
