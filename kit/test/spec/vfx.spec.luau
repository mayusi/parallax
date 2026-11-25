-- vfx.spec.luau (kit) — the kit's starter VFX presets pass VfxValidate, the starter texture registry matches the
-- texture generator specs, and the validator rejects a known-bad preset (so the gate can't silently rot).
-- Project presets are validated by `lune run kit vfx`, not here.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local VfxValidate = require("../../../src/kit/VfxValidate")

local PRESETS = "kit/starter/vfx"

local function readJson(path: string): any
	return serde.decode("json", fs.readFile(path))
end

local function describe(issues: { VfxValidate.Issue }): string
	local lines = {}
	for _, issue in issues do
		table.insert(lines, `{issue.path}: {issue.message}`)
	end
	return table.concat(lines, "\n")
end

return function()
	-- ---------------------------------------------------------------- VfxCompose: beats / use (parts) / variants
	local VfxCompose = require("../../../src/kit/VfxCompose")

	test.suite("VfxCompose", function()
		test.case("an overlay (kit vfx evolve's picked look) retimes, rescales, resaturates and mutes", function()
			local host = {
				version = 3,
				duration = 2,
				palette = { c = { 200, 100, 100 } },
				points = { hand = { 2, 0, 0 } },
				hitstop = { { at = 1, hold = 0.1 } },
				overlay = { time = 0.5, scale = 2, saturate = 0.5, mute = { "dust*" } },
				layers = {
					{ name = "core", kind = "sprite", at = 1, lifetime = { 0.4, 0.6 }, color = { 200, 150, 150 } },
					{ name = "dust_1", kind = "sprite", at = 0, lifetime = 1 },
				},
			}
			local out, issues = VfxCompose.expand(host)
			check.equal(#issues, 0)
			check.equal(#out.layers, 1) -- dust_* muted
			check.equal(out.duration, 1)
			check.equal(out.layers[1].at, 0.5)
			check.equal(out.layers[1].lifetime[2], 0.3)
			check.equal(out.hitstop[1].at, 0.5)
			check.equal(out.points.hand[1], 4) -- the variant machinery scales positions too
			check.equal(out.layers[1].color[2], 125) -- saturation x1.5 about the value, hue kept
			check.equal(out.palette.c[2], 50)
			check.equal(out.overlay, nil)
			check.equal(host.layers[1].at, 1) -- the host is never edited
		end)
		test.case(
			"a used part's impact frames take the use's point as their focus, its palette as their accent, and a frames map as their image",
			function()
				local part = {
					version = 3,
					part = true,
					palette = { accent = { 255, 210, 80 } },
					points = { hit = { 0, 0, 0 } },
					layers = {
						{
							name = "frame_a",
							kind = "impact",
							style = "frame",
							focus = "hit",
							accent = "accent",
							at = 0,
							life = 0.08,
						},
					},
				}
				local host = {
					version = 3,
					duration = 2,
					points = { muzzle = { 0, 4.5, -3 } },
					use = {
						{
							part = "frames",
							as = "hit1",
							at = 1,
							point = "muzzle",
							palette = { accent = { 10, 20, 30 } },
						},
					},
					layers = {},
				}
				local out, issues = VfxCompose.expand(host, {
					parts = function()
						return part
					end,
					frames = { ["hit1.frame_a"] = "frame_x_hit1_frame_a" },
				})
				check.equal(#issues, 0)
				local l = out.layers[1]
				check.equal(l.name, "hit1.frame_a")
				check.equal(l.focus, "hit1.hit")
				check.equal(out.points["hit1.hit"][2], 4.5)
				check.equal(l.accent[3], 30)
				check.equal(l.at, 1)
				check.equal(l.image, "frame_x_hit1_frame_a")
				check.equal(l.style, nil)
				local live = VfxCompose.expand(host, {
					parts = function()
						return part
					end,
				})
				check.equal(live.layers[1].style, "frame")
			end
		)
		test.case("a use hands the attack's name and font to a part's text layers", function()
			local part = {
				version = 3,
				part = true,
				points = { hit = { 0, 0, 0 } },
				layers = {
					{
						name = "call_1",
						kind = "impact",
						style = "frame",
						focus = "hit",
						text = "ATTACK",
						textFont = "Impact",
						at = 0,
						life = 0.07,
					},
				},
			}
			local out = VfxCompose.expand({
				version = 3,
				duration = 1,
				use = { { part = "attack_call", as = "call", text = "STARBLADE", textFont = "Chiller" } },
				layers = {},
			}, {
				parts = function()
					return part
				end,
			})
			check.equal(out.layers[1].text, "STARBLADE")
			check.equal(out.layers[1].textFont, "Chiller")
		end)

		test.case("a part's layers take the scene beat of their use, unless they say their own", function()
			-- (2026-11-13: the kit's method gate proves a beat's methods from the layers of that beat; a part's
			-- layers had none, so a part could never prove a method)
			local part = {
				part = true,
				layers = {
					{ kind = "sprite", name = "spark", at = 0, lifetime = 0.2 },
					{ kind = "sprite", name = "late", at = 0, lifetime = 0.2, beat = 2 },
				},
			}
			local function expand(use: any): any
				return VfxCompose.expand({ version = 3, duration = 1, use = { use }, layers = {} }, {
					parts = function()
						return part
					end,
				})
			end
			local tagged = expand({ part = "sparks", as = "hit", beat = 1 })
			check.equal(tagged.layers[1].name, "hit.spark")
			check.equal(tagged.layers[1].beat, 1)
			check.equal(tagged.layers[2].beat, 2)
			local bare = expand({ part = "sparks", as = "hit" })
			check.equal(bare.layers[1].beat, nil)
			check.equal(bare.layers[2].beat, 2)
		end)

		test.case(
			"beats resolve, a part joins prefixed / shifted / recoloured / placed / scaled, variants swap",
			function()
				local part = {
					part = true,
					palette = { core = { 255, 0, 0 }, rim = { 0, 255, 0 } },
					points = { tip = { 0, 2, 0 } },
					beats = { pop = 0.3 },
					layers = {
						{
							kind = "sprite",
							name = "spark",
							at = "pop",
							life = 0.5,
							color = "core",
							point = "tip",
							size = 2,
							speed = { { 0, 3 }, { 1, 0 } },
						},
						{
							kind = "light",
							name = "glow",
							at = 0,
							life = 0.2,
							color = { { 0, "rim" }, { 1, "gold" } },
							range = 10,
						},
					},
					hits = { "pop" },
				}
				local host = {
					version = 3,
					duration = 5,
					beats = { chop = 2.6 },
					palette = { gold = { 255, 200, 0 } },
					points = { hand = { 1, 0, 0 } },
					layers = { { kind = "sprite", name = "a", at = "chop+0.2", life = 1 } },
					hits = { "chop" },
					hitstop = { { at = "chop", hold = 0.1 } },
					use = {
						{
							part = "spark",
							at = "chop",
							as = "cut",
							point = "hand",
							scale = 2,
							palette = { core = "gold" },
						},
					},
					variants = { ice = { palette = { gold = { 0, 0, 255 } }, mute = { "cut.*" }, scale = 0.5 } },
				}
				local function parts(n: string): any?
					return if n == "spark" then part else nil
				end
				local out, issues = VfxCompose.expand(host, { parts = parts })
				check.equal(#issues, 0)
				check.is_true(math.abs(out.layers[1].at - 2.8) < 1e-9) -- "chop+0.2"
				check.equal(#out.layers, 3)
				local spark = out.layers[2]
				check.equal(spark.name, "cut.spark")
				check.is_true(math.abs(spark.at - 2.9) < 1e-9) -- the part's "pop" (0.3) after the use's "chop" (2.6)
				check.equal(spark.color, "gold") -- mapped by the use
				check.equal(spark.point, "cut.tip")
				check.equal(spark.size, 4) -- scaled
				check.equal(spark.speed[1][2], 6) -- sequences scale too
				check.equal(out.points["cut.tip"][1], 1) -- (0, 2, 0) * 2 + hand (1, 0, 0)
				check.equal(out.points["cut.tip"][2], 4)
				local glow = out.layers[3]
				check.equal(glow.range, 20)
				check.equal(glow.color[1][2], "cut.rim") -- an unmapped part colour joins the host palette prefixed
				check.equal(out.palette["cut.rim"][2], 255)
				check.equal(glow.color[2][2], "gold") -- a host colour named by the part passes through
				check.is_true(math.abs(out.hits[2] - 2.9) < 1e-9)
				check.equal(out.hitstop[1].at, 2.6)
				check.equal(out.use, nil)
				check.equal(out.variants, nil)
				-- host untouched (expand copies)
				check.equal(host.layers[1].at, "chop+0.2")
				check.equal(#host.layers, 1)
				-- the variant: palette over the host's, mutes by glob, scales the whole stack
				local ice, iceIssues = VfxCompose.expand(host, { parts = parts, variant = "ice" })
				check.equal(#iceIssues, 0)
				check.equal(#ice.layers, 1)
				check.equal(ice.palette.gold[3], 255)
				check.equal(ice.points.hand[1], 0.5)
				check.equal(VfxCompose.variants(host)[1], "ice")
				-- errors name the path
				local _, bad = VfxCompose.expand({
					version = 3,
					duration = 1,
					layers = { { kind = "sprite", name = "x", at = "nope", life = 1 } },
					use = { { part = "missing" } },
				}, { parts = parts, variant = "none" })
				check.equal(#bad, 3)
				check.equal(bad[1].path, "variants")
				check.equal(bad[2].path, "use[1].part")
				check.equal(bad[3].path, "layers[1].at")
				-- a part on its own validates as a preset
				local alone = VfxCompose.partAsPreset(part)
				check.equal(alone.version, 3)
				check.equal(alone.layers[1].at, 0.3)
				check.is_true(alone.duration >= 1.8)
			end
		)
	end)

	local textures = readJson("kit/starter/vfx/_textures.json")
	local meshes = readJson("kit/starter/vfx/_meshes.json")

	test.suite("VFX presets", function()
		local names = {}
		for _, file in fs.readDir(PRESETS) do
			if string.sub(file, 1, 1) ~= "_" and string.sub(file, -5) == ".json" then
				table.insert(names, file)
			end
		end
		table.sort(names)
		test.case("at least one preset exists", function()
			check.is_true(#names > 0)
		end)
		for _, file in names do
			local name = string.gsub(file, "%.json$", "")
			test.case(`{name} is valid`, function()
				-- an example is checked as it plays: expanded with the parts and the texture ids
				-- it carries in _deps/<name>/ — an example that forgot a dependency still fails here
				local preset = readJson(`{PRESETS}/{file}`)
				local reg = textures
				local deps = `{PRESETS}/_deps/{name}`
				local composeIssues = {}
				-- every example installs with the ids it carries (Library.installVfx merges them for plain presets too)
				if fs.isFile(`{deps}/registry.json`) then
					reg = table.clone(textures)
					for k, v in readJson(`{deps}/registry.json`) do
						reg[k] = v
					end
				end
				-- expanded like the game does (Vfx.register): every version-3 preset, so tech keys (`lit`, `echo`...) count
				if type(preset) == "table" and preset.version == 3 then
					preset, composeIssues = VfxCompose.expand(preset, {
						parts = function(p: string): any
							local path = `{deps}/parts/{p}.json`
							return if fs.isFile(path) then readJson(path) else nil
						end,
					})
				end
				local issues = VfxValidate.preset(name, preset, reg, meshes)
				for _, i in composeIssues do
					table.insert(issues, i)
				end
				local errors = VfxValidate.errors(issues)
				-- the message carries the exact fix, so a failing run is self-explanatory
				check.equal(describe(errors), "")
			end)
		end
	end)

	test.suite("VFX texture registry", function()
		for key, entry in textures do
			if type(entry) ~= "table" then
				continue
			end
			test.case(`{key} has a generator spec with the same grid`, function()
				local spec = `kit/starter/textures/{key}.json`
				check.is_true(fs.isFile(spec))
				if fs.isFile(spec) then
					check.equal(readJson(spec).grid or 1, entry.grid)
				end
			end)
			test.case(`{key} has a fallback texture`, function()
				check.is_true(type(entry.fallback) == "string" and #entry.fallback > 0)
			end)
		end
	end)

	test.suite("VfxValidate rejects bad presets", function()
		local bad = readJson("kit/selftest/vfx/_selftest_bad_preset.json")
		local errors = VfxValidate.errors(VfxValidate.preset("bad", bad, textures))
		local text = describe(errors)
		test.case("catches every planted fault", function()
			for _, needle in
				{
					"duration",
					"unknown texture",
					"rate must be",
					"lifetime must",
					"times must increase",
					"first keypoint",
					"outside 0..1",
					"fps must",
					"shake intensity",
					"to must be",
					"sound needs",
					"flash (brightness",
					"delay must",
				}
			do
				check.is_true(string.find(text, needle, 1, true) ~= nil)
			end
		end)
		test.case(
			"particles may emit up in the sky (offset) and through a volume (area); bad shapes are errors",
			function()
				local function preset(area: any): any
					return {
						mode = "burst",
						duration = 6,
						elements = {
							{
								kind = "particles",
								texture = "glow",
								burst = 4,
								lifetime = { 1, 2 },
								offset = { 0, 500, 0 },
								area = area,
							},
						},
					}
				end
				local good = VfxValidate.errors(
					VfxValidate.preset("c", preset({ shape = "Cylinder", size = { 100, 300, 100 } }), textures)
				)
				check.equal(#good, 0)
				local wrongShape = describe(
					VfxValidate.errors(
						VfxValidate.preset("c", preset({ shape = "Torus", size = { 1, 1, 1 } }), textures)
					)
				)
				check.is_true(string.find(wrongShape, "area must be", 1, true) ~= nil)
			end
		)
		test.case("an older preset's reach is studs or all, never a mistake", function()
			local function with(reach: any): number
				return #VfxValidate.errors(VfxValidate.preset("r", {
					mode = "attach",
					reach = reach,
					elements = { { kind = "trail", lifetime = 1 } },
				}, textures))
			end
			check.equal(with(nil), 0)
			check.equal(with(400), 0)
			check.equal(with("all"), 0)
			check.equal(with(0), 1)
			check.equal(with(-5), 1)
			check.equal(with("far"), 1)
			check.equal(with(true), 1)
		end)
		test.case("trail outside attach mode is an error", function()
			local issues = VfxValidate.errors(VfxValidate.preset("t", {
				mode = "burst",
				duration = 1,
				elements = { { kind = "trail", lifetime = 1 } },
			}, textures))
			check.equal(#issues, 1)
		end)
		test.case("v2 kinds: a good mesh / afterimage / grade preset passes", function()
			local reg = { dome = { id = "", fallback = "Ball", size = { 2, 1, 2 } } }
			local burst = VfxValidate.errors(VfxValidate.preset("m", {
				mode = "burst",
				duration = 2,
				elements = {
					{
						kind = "mesh",
						mesh = "dome",
						material = "ForceField",
						texture = "glow",
						time = 1.5,
						scale = { { 0, 1 }, { 1, { 60, 20, 60 } } },
						transparency = { { 0, 0 }, { 1, 1 } },
						color = { { 0, { 255, 255, 255 } }, { 1, { 255, 120, 40 } } },
						spin = { 0, 90, 0 },
					},
					{ kind = "grade", tint = { 255, 220, 200 }, contrast = 0.3, blur = 8, fov = 10, time = 0.4 },
				},
			}, textures, reg))
			check.equal(describe(burst), "")
			local attach = VfxValidate.errors(VfxValidate.preset("a", {
				mode = "attach",
				elements = {
					{
						kind = "afterimage",
						interval = 0.06,
						lifetime = 0.6,
						cycle = 1,
						color = { { 0, { 255, 0, 80 } }, { 1, { 0, 255, 200 } } },
						transparency = { { 0, 0.3 }, { 1, 1 } },
					},
					{ kind = "grade", who = "owner", tint = { 170, 255, 210 }, saturation = -0.3 },
				},
			}, textures, reg))
			check.equal(describe(attach), "")
		end)
		test.case("v2 kinds: bad fields are errors with fixes", function()
			local msgs = describe(VfxValidate.errors(VfxValidate.preset("x", {
				mode = "burst",
				duration = 1,
				elements = {
					{ kind = "mesh", mesh = "nope", material = "Lava", scale = { { 0.2, 1 } } },
					{ kind = "afterimage", interval = 0.001, lifetime = 9 },
					{ kind = "grade", blur = 99, who = "everyone", fov = 90 },
				},
			}, textures, {})))
			for _, needle in
				{
					"mesh must be",
					"material must be",
					"keypoints must start",
					"mesh needs time",
					"afterimages need an attach",
					"interval",
					"blur size",
					"who must be",
					"fov",
					"burst grades need time",
				}
			do
				check.is_true(string.find(msgs, needle, 1, true) ~= nil)
			end
		end)
		test.case("over-budget preset is an error", function()
			local issues = VfxValidate.errors(VfxValidate.preset("b", {
				mode = "burst",
				duration = 2,
				elements = {
					{ kind = "particles", texture = "glow", burst = 200, lifetime = 1 },
					{ kind = "particles", texture = "glow", burst = 200, lifetime = 1 },
					{ kind = "particles", texture = "glow", burst = 200, lifetime = 1, rate = 400 },
				},
			}, textures))
			check.is_true(string.find(describe(issues), "budget", 1, true) ~= nil)
		end)
	end)

	-- version 3: layer stacks played by VfxStage (one clock, every engine property)
	test.suite("VFX v3 layer stacks", function()
		local good = {
			version = 3,
			duration = 2,
			palette = { gold = { 255, 200, 90 } },
			points = { blade = { 0, 6, -1 } },
			layers = {
				{
					name = "flash",
					kind = "sprite",
					at = 0.1,
					point = "blade",
					texture = "glow",
					count = 1,
					lifetime = 0.3,
					size = { { 0, 4 }, { 1, 8 } },
					color = "gold",
					brightness = 12,
					lightEmission = -1,
					squash = { { 0, 2 }, { 1, 0 } },
				},
				{
					name = "line",
					kind = "beam",
					from = "blade",
					to = "target",
					width = 2,
					life = 0.5,
					texture = "glow",
				},
				{ name = "ring", kind = "mesh", shape = "ring", life = 0.5, scale = { { 0, 1 }, { 1, 20 } } },
				{ name = "punch", kind = "fov", life = 0.4, delta = { { 0, 0 }, { 0.2, 8 }, { 1, 0 } } },
				{ name = "frame", kind = "impact", at = 0.1, life = 0.06, mode = "white" },
				{ name = "plate", kind = "impact", at = 0.2, life = 0.1, image = "glow", imageTransparency = 0.1 },
			},
		}
		test.case("a well-formed v3 preset passes", function()
			check.equal(describe(VfxValidate.errors(VfxValidate.preset("good", good, textures, meshes))), "")
		end)
		test.case("a sheet that breaks up on a mesh: its window, its mode, its surface; erode is warned", function()
			-- (2026-11-13, the VFX methods audit: a mesh's erode shows in the player only, a baked dissolve sheet -
			-- kit vfx dissolve - played through a surface inside "over" is what the game shows)
			local function shell(extra: { [string]: any }): any
				local layer: { [string]: any } =
					{ name = "shell", kind = "mesh", shape = "ring", life = 0.5, texture = "smoke" }
				for k, v in extra do
					layer[k] = v
				end
				return { version = 3, duration = 1, layers = { layer } }
			end
			local function said(preset: any, severity: string): string
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, textures, meshes) do
					if issue.severity == severity then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, "\n")
			end
			local function sheet(mode: string, over: { number }): any
				return { layout = "4x4", mode = mode, over = over }
			end
			check.equal(said(shell({ surface = 1, flipbook = sheet("OneShot", { 0.6, 1 }) }), "error"), "")
			local loop = said(shell({ surface = 1, flipbook = sheet("Loop", { 0.6, 1 }) }), "error")
			check.is_true(string.find(loop, 'over needs "mode": "OneShot"', 1, true) ~= nil)
			local bare = said(shell({ flipbook = sheet("OneShot", { 0.6, 1 }) }), "error")
			check.is_true(string.find(bare, 'needs "surface": 1 on its mesh', 1, true) ~= nil)
			local back = said(shell({ surface = 1, flipbook = sheet("OneShot", { 0.9, 0.2 }) }), "error")
			check.is_true(string.find(back, "0 <= start < end <= 1", 1, true) ~= nil)
			-- erode is still a preset the player takes (no error) and now says where it does NOT show
			check.equal(said(shell({ erode = { 0.6, 1 } }), "error"), "")
			local warned = said(shell({ erode = { 0.6, 1 } }), "warn")
			check.is_true(string.find(warned, "erode shows in the browser player only", 1, true) ~= nil)
			check.is_true(string.find(warned, "kit vfx dissolve", 1, true) ~= nil)
			check.equal(said(shell({}), "warn"), "")
		end)
		test.case("a debris layer that flies a fracture plan's pieces", function()
			local function with(extra: { [string]: any }): any
				local layer: { [string]: any } = { name = "slab", kind = "debris", life = 1.2 }
				for k, v in extra do
					layer[k] = v
				end
				return { version = 3, duration = 2, layers = { layer } }
			end
			local function said(preset: any, severity: string): string
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, textures, meshes) do
					if issue.severity == severity then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			check.equal(said(with({ pieces = "slab_a", speed = 30 }), "error"), "")
			check.is_true(
				string.find(said(with({ pieces = 3 }), "error"), "pieces names a fracture plan", 1, true) ~= nil
			)
			-- the game finds a plan by its exact letters; the kit's own files do not tell Slab from slab
			check.is_true(
				string.find(said(with({ pieces = "Slab_A" }), "error"), "pieces names a fracture plan", 1, true) ~= nil
			)
			check.is_true(
				string.find(said(with({ pieces = "slab_a", speed = 0 }), "error"), "speed above 0", 1, true) ~= nil
			)
			check.is_true(
				string.find(said(with({ pieces = "slab_a", shape = "rock" }), "error"), "drop shape", 1, true) ~= nil
			)
			local range = said(with({ pieces = "slab_a", speed = { 20, 40 } }), "error")
			check.is_true(string.find(range, "speed is ONE number", 1, true) ~= nil)
			-- "rest": the pieces come to rest and lie there
			check.equal(said(with({ pieces = "slab_a", rest = true, life = 1.8 }), "error"), "")
			check.is_true(
				string.find(said(with({ pieces = "slab_a", rest = "yes" }), "error"), "rest is true", 1, true) ~= nil
			)
			check.is_true(
				string.find(
					said(with({ pieces = "slab_a", rest = true, life = 0.6 }), "warn"),
					"kit vfx settle",
					1,
					true
				) ~= nil
			)
			-- the rule's floor and flat faces are the world's level: a turned slab, no gravity, or no pieces are refused
			check.is_true(
				string.find(
					said(with({ pieces = "slab_a", rest = true, rotate = { 90, 0, 0 } }), "error"),
					"a slab that lies level",
					1,
					true
				) ~= nil
			)
			check.is_true(
				string.find(
					said(with({ pieces = "slab_a", rest = true, gravity = 0 }), "error"),
					"gravity is 1 or more",
					1,
					true
				) ~= nil
			)
			check.is_true(string.find(said(with({ rest = true }), "error"), "flies a fracture plan", 1, true) ~= nil)
			local stray = said(with({ pieces = "slab_a", count = 12, spread = 40 }), "warn")
			check.is_true(string.find(stray, "count is not read", 1, true) ~= nil)
			check.is_true(string.find(stray, "spread is not read", 1, true) ~= nil)
		end)
		test.case("a lens layer's flare", function()
			local withFlare = table.clone(textures)
			for _, key in { "lens_glow", "lens_ghost", "lens_streak" } do
				withFlare[key] = { id = "rbxassetid://1" }
			end
			local function said(flare: any, tex: any, severity: string): string
				local preset = {
					version = 3,
					duration = 2,
					layers = { { name = "sun", kind = "lens", life = 1.5, point = { 0, 30, -80 }, flare = flare } },
				}
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, tex, meshes) do
					if issue.severity == severity then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			local whole =
				{ strength = 0.8, ghosts = 5, size = 0.18, streak = 0.6, squeeze = 1.6, color = { 255, 220, 170 } }
			check.equal(said(whole, withFlare, "error"), "")
			-- its three pictures are made once a project: without them the game would draw nothing
			check.is_true(string.find(said(whole, textures, "error"), "kit/vfx/lens.py lens_glow", 1, true) ~= nil)
			check.is_true(string.find(said(true, withFlare, "error"), "flare is a block", 1, true) ~= nil)
			-- "occlude": hide it while something stands before its light - true or false, nothing else
			check.equal(said({ strength = 0.8, occlude = true }, withFlare, "error"), "")
			check.is_true(
				string.find(said({ strength = 0.8, occlude = "walls" }, withFlare, "error"), "flare.occlude", 1, true)
					~= nil
			)
			check.is_true(string.find(said({ ghosts = 5 }, withFlare, "error"), "say how strong", 1, true) ~= nil)
			check.is_true(
				string.find(said({ strength = 1, ghosts = 20 }, withFlare, "error"), "flare.ghosts", 1, true) ~= nil
			)
			check.is_true(
				string.find(said({ strength = 1, glare = 2 }, withFlare, "error"), "a flare reads strength", 1, true)
					~= nil
			)
		end)
		test.case("a swarm layer that follows an authored field", function()
			local function said(fieldBlock: any, severity: string): string
				local preset = {
					version = 3,
					duration = 2,
					layers = { { name = "motes", kind = "swarm", life = 1.5, count = 30, field = fieldBlock } },
				}
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, textures, meshes) do
					if issue.severity == severity then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			check.equal(said({ name = "whirl", follow = 6, gain = { { 0, 0 }, { 1, 1 } } }, "error"), "")
			check.is_true(string.find(said("whirl", "error"), "field is a block", 1, true) ~= nil)
			check.is_true(string.find(said({ name = "Whirl" }, "error"), "name is a field of", 1, true) ~= nil)
			check.is_true(string.find(said({ follow = 6 }, "error"), "name is a field of", 1, true) ~= nil)
			check.is_true(
				string.find(said({ name = "whirl", strength = 3 }, "error"), "reads name, follow and gain", 1, true)
					~= nil
			)
			check.is_true(string.find(said({ name = "whirl", follow = 0 }, "error"), "field.follow", 1, true) ~= nil)
		end)
		test.case("a swarm layer that gathers into a point cloud", function()
			local function said(cloudBlock: any): string
				local preset = {
					version = 3,
					duration = 2,
					layers = { { name = "motes", kind = "swarm", life = 1.5, count = 60, cloud = cloudBlock } },
				}
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, textures, meshes) do
					if issue.severity == "error" then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			check.equal(said({ name = "sigil", size = 6, pull = { { 0, 0 }, { 0.4, 10 }, { 1, 10 } } }), "")
			check.equal(said({ name = "sigil" }), "")
			check.is_true(string.find(said("sigil"), "cloud is a block", 1, true) ~= nil)
			check.is_true(string.find(said({ name = "Sigil" }), "name is a cloud of", 1, true) ~= nil)
			check.is_true(string.find(said({ size = 6 }), "name is a cloud of", 1, true) ~= nil)
			check.is_true(
				string.find(said({ name = "sigil", strength = 3 }), "reads name, size and pull", 1, true) ~= nil
			)
			check.is_true(string.find(said({ name = "sigil", size = 0 }), "cloud.size", 1, true) ~= nil)
			check.is_true(string.find(said({ name = "sigil", pull = 500 }), "cloud.pull", 1, true) ~= nil)
		end)
		test.case("a mesh layer whose size answers the camera (forced perspective)", function()
			local function said(forcedBlock: any): string
				local preset = {
					version = 3,
					duration = 2,
					layers = { { name = "moon", kind = "mesh", shape = "ring", life = 1.5, forced = forcedBlock } },
				}
				local lines = {}
				for _, issue in VfxValidate.preset("p", preset, textures, meshes) do
					if issue.severity == "error" then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			check.equal(said({ ref = 40, keep = 1, min = 0.25, max = 4 }), "")
			check.equal(said({ ref = 40 }), "")
			check.is_true(string.find(said(40), "forced is a block", 1, true) ~= nil)
			check.is_true(string.find(said({ keep = 1 }), "ref is the distance", 1, true) ~= nil)
			check.is_true(string.find(said({ ref = 40, keep = 0 }), "does nothing", 1, true) ~= nil)
			check.is_true(string.find(said({ ref = 40, keep = 0.001 }), "does nothing", 1, true) ~= nil)
			check.is_true(string.find(said({ ref = 40, min = 1, max = 1 }), "forced does nothing", 1, true) ~= nil)
			check.is_true(string.find(said({ ref = 40, keep = 3 }), "forced.keep", 1, true) ~= nil)
			check.is_true(
				string.find(said({ ref = 40, hold = 1 }), "forced reads ref, keep, min and max", 1, true) ~= nil
			)
		end)
		test.case("a swarm whose particles are meshes (Rock)", function()
			local function said(extra: { [string]: any }): string
				local layer: { [string]: any } =
					{ name = "grit", kind = "swarm", life = 1.5, shape = "Rock", count = 24 }
				for k, v in extra do
					layer[k] = v
				end
				local lines = {}
				for _, issue in
					VfxValidate.preset("p", { version = 3, duration = 2, layers = { layer } }, textures, meshes)
				do
					if issue.severity == "error" then
						table.insert(lines, `{issue.path}: {issue.message}`)
					end
				end
				return table.concat(lines, " | ")
			end
			check.equal(said({}), "")
			check.equal(said({ rock = { cuts = 9, jag = 0.5 }, tumble = { 2, 6 }, material = "Slate" }), "")
			check.is_true(string.find(said({ count = 60 }), "40 at most", 1, true) ~= nil)
			check.is_true(string.find(said({ trail = { lifetime = 0.2 } }), "has no trail", 1, true) ~= nil)
			check.is_true(
				string.find(said({ rock = { seed = 3 } }), "rock reads cuts, jag, spike and flat", 1, true) ~= nil
			)
			-- a stone's numbers are held to the debris layer's ranges
			for _, bad in { { cuts = 0 }, { cuts = 1000000 }, { jag = 2 }, { flat = 0 }, { spike = -1 } } do
				check.is_true(string.find(said({ rock = bad }), ".rock.", 1, true) ~= nil)
			end
			check.is_true(string.find(said({ tumble = { 6, 2 } }), "tumble is [slowest, fastest]", 1, true) ~= nil)
			check.is_true(
				string.find(said({ shape = "Ball", tumble = { 2, 6 } }), 'read with "shape": "Rock" only', 1, true)
					~= nil
			)
			check.is_true(string.find(said({ shape = "Stone" }), "shape: Ball | Block | Rock", 1, true) ~= nil)
		end)
		test.case("v3 mistakes are errors that say the fix", function()
			local msgs = describe(VfxValidate.errors(VfxValidate.preset("bad", {
				version = 3,
				duration = 1,
				layers = {
					{ name = "late", kind = "sprite", texture = "glow", count = 1, lifetime = 3 },
					{ name = "nope", kind = "sprite", texture = "no_such_texture", count = 1 },
					{ name = "where", kind = "light", point = "nowhere" },
					{ name = "flip", kind = "sprite", texture = "glow", count = 1, flipbook = { layout = "4x4" } },
					{
						name = "flat",
						kind = "sprite",
						texture = "glow",
						count = 1,
						orientation = "VelocityPerpendicular",
					},
					{
						name = "keys",
						kind = "beam",
						from = { 0, 0, 0 },
						to = { 0, 1, 0 },
						width = { { 0.2, 1 }, { 1, 2 } },
					},
					{ name = "long", kind = "impact", life = 0.5 },
					{ name = "plate", kind = "impact", life = 0.1, image = "no_such_plate" },
					{ name = "dup", kind = "shake" },
					{ name = "dup", kind = "shake" },
					{ name = "x", kind = "teleport" },
				},
			}, textures, meshes)))
			for _, needle in
				{
					"gets cut off",
					"unknown texture",
					".image: unknown texture",
					"unknown point",
					"single image, not a sheet",
					"VelocityPerpendicular sprite needs a speed",
					"start at 0 and end at 1",
					"impact frame lasts",
					"names must be unique",
					"kind must be",
				}
			do
				check.is_true(string.find(msgs, needle, 1, true) ~= nil)
			end
		end)
		test.case("v3 checks every field the runtime reads (beam / mesh / debris / glow / twin)", function()
			local msgs = describe(VfxValidate.errors(VfxValidate.preset("fields", {
				version = 3,
				duration = 2,
				layers = {
					{
						name = "b",
						kind = "beam",
						from = { 0, 0, 0 },
						to = { 0, 1, 0 },
						taper = 2,
						curve = { 1 },
						growEase = "bounce",
					},
					{
						name = "m",
						kind = "mesh",
						shape = "ring",
						pivot = "middle",
						params = { inner = "x" },
						rotate = 5,
					},
					{ name = "d", kind = "debris", material = "Lava", spread = 400 },
					{ name = "g", kind = "glow", target = "@blade", material = "Lava" },
					{
						name = "t",
						kind = "sprite",
						texture = "glow",
						count = 1,
						lifetime = 1,
						twin = { lifeScale = 3, count = 500 },
					},
				},
			}, textures, meshes)))
			for _, needle in
				{
					"layers[1](b).taper",
					"layers[1](b).curve",
					"growEase",
					"pivot",
					"params.inner",
					"rotate is",
					"layers[3](d).material",
					"layers[3](d).spread",
					"layers[4](g).material",
					"twin count",
					"gets cut off",
				}
			do
				check.is_true(string.find(msgs, needle, 1, true) ~= nil)
			end
		end)
		test.case("a mesh sequence may sit by its own origin, no other shape may", function()
			local function said(layer: any): string
				return describe(VfxValidate.errors(VfxValidate.preset("po", {
					version = 3,
					duration = 2,
					layers = { layer },
				}, textures, meshes)))
			end
			local seqLayer =
				{ name = "w", kind = "mesh", shape = "seq", pivot = "origin", params = { seq = "water_a", fps = 24 } }
			check.is_true(string.find(said(seqLayer), "pivot", 1, true) == nil)
			check.is_true(
				string.find(
					said({ name = "r", kind = "mesh", shape = "ring", pivot = "origin" }),
					"is for a mesh sequence",
					1,
					true
				) ~= nil
			)
			check.is_true(
				string.find(
					said({ name = "r", kind = "mesh", shape = "ring", pivot = "middle" }),
					"base (starts at its point",
					1,
					true
				) ~= nil
			)
		end)
		test.case("base on a mesh sequence is warned about: the game and the player put it in two places", function()
			local based = VfxValidate.preset("pb", {
				version = 3,
				duration = 2,
				layers = { { name = "w", kind = "mesh", shape = "seq", pivot = "base", params = { seq = "water_a" } } },
			}, textures, meshes)
			local warned = false
			for _, issue in based do
				if string.find(issue.message, "NOT the same place", 1, true) then
					warned = true
					check.equal(issue.severity, "warn")
				end
			end
			check.is_true(warned)
		end)
		test.case("v3 hit-stop and beam planes are validated", function()
			local msgs = describe(VfxValidate.errors(VfxValidate.preset("hs", {
				version = 3,
				duration = 2,
				hitstop = { { at = 5, hold = 2 } },
				layers = { { name = "b", kind = "beam", from = { 0, 0, 0 }, to = { 0, 1, 0 }, plane = "sideways" } },
			}, textures, meshes)))
			for _, needle in { "hitstop[1].at", "hitstop[1].hold", "plane: camera" } do
				check.is_true(string.find(msgs, needle, 1, true) ~= nil)
			end
			local ok = VfxValidate.errors(VfxValidate.preset("hs2", {
				version = 3,
				duration = 2,
				hitstop = { { at = 0.5, hold = 0.08 } },
				layers = { { name = "b", kind = "beam", from = { 0, 0, 0 }, to = { 0, 1, 0 }, plane = "up", life = 1 } },
			}, textures, meshes))
			check.equal(describe(ok), "")
		end)
		test.case("v3 attach mode and trails validate", function()
			local ok = VfxValidate.errors(VfxValidate.preset("aura", {
				version = 3,
				mode = "attach",
				layers = {
					{ name = "motes", kind = "sprite", rate = 30, texture = "glow", lifetime = 1 },
					{
						name = "tail",
						kind = "trail",
						target = "@part",
						span = { { 0, -1, 0 }, { 0, 1, 0 } },
						lifetime = 0.4,
					},
				},
			}, textures, meshes))
			check.equal(describe(ok), "")
			local msgs = describe(VfxValidate.errors(VfxValidate.preset("bad", {
				version = 3,
				duration = 2,
				layers = {
					{ name = "t", kind = "trail", target = "blade", span = { { 0, 1 } }, lifetime = 50 },
					{ name = "t2", kind = "trail", life = 1 },
				},
			}, textures, meshes)))
			for _, needle in { "target is", "span is two", "lifetime", "layers[2](t2).from" } do
				check.is_true(string.find(msgs, needle, 1, true) ~= nil)
			end
		end)
		test.case("v3 debris takes a plain number for speed and size", function()
			local issues = VfxValidate.errors(VfxValidate.preset("rocks", {
				version = 3,
				duration = 2,
				layers = { { name = "r", kind = "debris", life = 1, speed = 40, size = 1 } },
			}, textures, meshes))
			check.equal(describe(issues), "")
		end)
		test.case("v3 particle budget is enforced", function()
			local layers = {}
			for i = 1, 6 do
				table.insert(
					layers,
					{ name = `s{i}`, kind = "sprite", texture = "glow", rate = 400, ["for"] = 1, lifetime = 1 }
				)
			end
			local msgs = describe(
				VfxValidate.errors(
					VfxValidate.preset("big", { version = 3, duration = 3, layers = layers }, textures, meshes)
				)
			)
			check.is_true(string.find(msgs, "particles alive at the peak", 1, true) ~= nil)
		end)
	end)

	-- VfxImpact (bullet hits by surface, Sample Game R25): every material -> one of 14 kinds, never an EditableMesh
	test.suite("VfxImpact", function()
		local luau = require("@lune/luau")
		local VfxImpact = luau.load(fs.readFile("src/kit/VfxImpact.luau"), {
			debugName = "VfxImpact",
			environment = { game = {
				GetService = function()
					return {}
				end,
			} },
		})()
		test.case("every material maps to a kind, all 14 kinds are reachable, unknown = Plaster", function()
			local reached = {}
			for _, n in
				{ "Concrete", "Brick", "Plaster", "WoodPlanks", "DiamondPlate", "Glass", "SmoothPlastic", "Carpet" }
			do
				reached[VfxImpact.kindOf(n)] = true
			end
			for _, n in { "Mud", "Sand", "LeafyGrass", "Glacier", "Water", "Rubber" } do
				reached[VfxImpact.kindOf(n)] = true
			end
			for _, k in VfxImpact.KINDS do
				check.is_true(reached[k] == true)
			end
			check.equal(#VfxImpact.KINDS, 14)
			check.equal(VfxImpact.kindOf("NotAMaterial"), "Plaster")
		end)
		test.case("a layer that would build an EditableMesh is found, overrides included", function()
			local clean = {
				version = 3,
				layers = { { kind = "debris", floor = "world", onMaterial = { Water = { mute = true } } } },
			}
			check.equal(#VfxImpact.meshLayers(clean), 0)
			local meshy = {
				version = 3,
				layers = {
					{ name = "a", kind = "sprite", onMaterial = { Water = { kind = "mesh" } } },
					{ name = "b", kind = "debris", shape = "rock" },
					{ name = "c", kind = "trail", mesh = true },
					{ name = "d", kind = "sprite", onMaterial = { Water = { kind = "mesh", mute = true } } },
				},
			}
			check.equal(#VfxImpact.meshLayers(meshy), 3)
		end)
		test.case("debris floor: hit | world, anything else rejected", function()
			local function errs(floor: any): string
				return describe(VfxValidate.errors(VfxValidate.preset("chips", {
					version = 3,
					duration = 1,
					layers = { { name = "chips", kind = "debris", life = 0.8, floor = floor } },
				}, {}, {})))
			end
			check.equal(errs("world"), "")
			check.equal(errs("hit"), "")
			check.is_true(string.find(errs("ground"), "floor", 1, true) ~= nil)
		end)
	end)
end
