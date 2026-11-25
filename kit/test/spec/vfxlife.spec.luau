-- vfxlife.spec.luau (kit) - two lifecycle rules of the VFX runtime (the owner's limitations file, 2026-11-15):
--   F-R01  a stage that is RELEASED stops adding samples to its mesh trails (the flat Trail beside them did; the ribbon
--          did not), and a ribbon whose tail has aged out goes back to the pool at once
--   F-R02  an impact that cannot play YET (the kit or the presets have not replicated) is not remembered as one that
--          never can; only a preset that LOADED and is refused is; and asking again is bounded
-- The rules are run from the runtime's own source; the wiring is read from its code (comments taken out).
local frk = require("../frk")
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local test, check = frk.test, frk.check

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	-- (runs of blanks made one, and none inside a bracket: a call the formatter split over lines reads as one)
	local flat = string.gsub(table.concat(out, " "), "%s+", " ")
	flat = string.gsub(flat, "%( ", "(")
	return (string.gsub(flat, ",? %)", ")"))
end

-- the text of a rule between its two marks, as a chunk that returns what `names` lists
local function rule(path: string, first: string, last: string, names: string): any
	local text = fs.readFile(path)
	local a = string.find(text, first, 1, true)
	local b = string.find(text, last, 1, true)
	assert(a and b and b > a, `{path} has no rule between "{first}" and "{last}"`)
	return luau.load(string.sub(text, a, b - 1) .. "\nreturn { " .. names .. " }", { debugName = "rule" })()
end

return function()
	test.suite("a released stage's mesh trail (F-R01)", function()
		local R = rule(
			"src/kit/VfxStage.luau",
			"local function ribbonEmits(",
			"-- (end of the ribbon's rules)",
			"emits = ribbonEmits, history = ribbonHistory, done = ribbonDone"
		)
		-- a host moving along x, a layer alive from 0 to 4 s, samples that live 0.5 s; released at 1 s
		local function run(releaseAt: number?): ({ any }, { number }, number?)
			local hist, counts, doneAt = {}, {}, nil
			local taken = 0
			for frame = 1, 240 do
				local t = frame / 60
				local released = releaseAt ~= nil and t >= releaseAt
				local emits = R.emits(t, 0, 4, true, released)
				R.history(
					hist,
					t,
					0.5,
					48,
					if emits
						then function()
							taken += 1
							return t * 10, t * 10 + 1
						end
						else nil
				)
				counts[frame] = taken
				if doneAt == nil and R.done((t - 0) / 4, released, #hist) then
					doneAt = t
				end
			end
			return hist, counts, doneAt
		end
		test.case(
			"while it lives, a moving source leaves a sample a frame, and the tail is as long as its lifetime",
			function()
				local hist, counts, doneAt = run(nil)
				check.equal(counts[60], 60)
				check.equal(counts[240], 240) -- to the end of the layer's life
				check.is_true(#hist >= 29 and #hist <= 31) -- half a second of samples at 60 a second
				check.equal(doneAt, nil) -- still drawing at the end of its life
			end
		)
		test.case("once the stage is released, no new sample is taken", function()
			local _, counts = run(1)
			check.equal(counts[59], 59)
			check.equal(counts[60], 59) -- released ON this frame: not sampled
			check.equal(counts[240], 59) -- and never again
		end)
		test.case(
			"the tail it has fades out, and the ribbon is done when the tail is gone - not at the layer's end",
			function()
				local hist, _, doneAt = run(1)
				check.equal(#hist, 0)
				check.is_true(doneAt ~= nil and doneAt > 1.45 and doneAt < 1.56) -- the last sample (0.983 s) aged 0.5 s
			end
		)
		test.case("a host that is gone, a layer not yet started or over: no sample either", function()
			check.is_false(R.emits(1, 0, 4, false, false))
			check.is_false(R.emits(0.5, 1, 4, true, false))
			check.is_false(R.emits(4.5, 0, 4, true, false))
			check.is_true(R.emits(1, 0, 4, true, false))
			check.is_true(R.done(1.2, false, 0)) -- past its life with no tail: done, as before
			check.is_false(R.done(0.5, false, 0)) -- alive, not released, no tail YET: it is waiting for its first samples
			check.is_false(R.done(0.5, true, 3)) -- released with a tail: the tail is still fading
		end)
		test.case("the history never holds more than its samples", function()
			local hist = {}
			for i = 1, 200 do
				R.history(hist, i / 1000, 10, 48, function()
					return i, i
				end)
			end
			check.equal(#hist, 48)
			check.equal(hist[48].a, 200) -- the newest are kept
		end)
		test.case("the ribbon's updater uses the rules, with the stage's release", function()
			local stage = code("src/kit/VfxStage.luau")
			check.is_true(
				string.find(stage, "ribbonEmits(t, at, life, host.Parent ~= nil, self.released)", 1, true) ~= nil
			)
			check.is_true(string.find(stage, "ribbonHistory(hist, t, lifetime, samples,", 1, true) ~= nil)
			-- ... and USES what they say (a check of the calls alone passed with the fix undone: a review)
			check.is_true(
				string.find(stage, "ribbonHistory(hist, t, lifetime, samples, if takes then function()", 1, true) ~= nil
			)
			check.is_true(
				string.find(
					stage,
					"if ribbonDone(u, self.released, #hist) then ribbon = nil r.destroy() return end",
					1,
					true
				) ~= nil
			)
			local kit = code("src/kit/Vfx.luau")
			check.is_true(
				string.find(
					kit,
					"presetFolder.ChildAdded:Connect(function(module) local ok, why = (pcall :: any)(load, module)",
					1,
					true
				) ~= nil
			)
		end)
	end)

	test.suite("an impact that cannot play yet (F-R02)", function()
		-- a made ReplicatedStorage whose children arrive later, a clock the test moves, a require that reads made modules
		local function world(beside: ((any) -> any)?)
			local w: any = { now = 100, children = {}, warned = {}, required = 0, looked = 0 }
			local storage = {
				FindFirstChild = function(_self: any, name: string)
					w.looked += 1
					return w.children[name]
				end,
			}
			local function folder(kids: { [string]: any }): any
				return {
					FindFirstChild = function(_self: any, name: string)
						return kids[name]
					end,
				}
			end
			local function module(value: any): any
				return {
					value = value,
					IsA = function(_self: any, class: string)
						return class == "ModuleScript"
					end,
				}
			end
			w.folder, w.module = folder, module
			w.impact = luau.load(fs.readFile("src/kit/VfxImpact.luau"), {
				debugName = "VfxImpact",
				environment = {
					game = {
						GetService = function(_self: any, name: string)
							return if name == "ReplicatedStorage" then storage else {}
						end,
					},
					require = function(m: any)
						w.required += 1
						if type(m) ~= "table" or m.value == nil then
							error("not a module")
						end
						if m.value == "broken" then
							error("the module threw")
						end
						return m.value
					end,
					warn = function(text: string)
						table.insert(w.warned, text)
					end,
					os = {
						clock = function()
							return w.now
						end,
					},
					script = if beside then beside(w) else nil,
				},
			})()
			return w
		end
		local function kit(has: { [string]: boolean }): any
			return {
				has = function(name: string)
					return has[name] == true
				end,
			}
		end
		local clean = { version = 3, layers = { { kind = "sprite" } } }

		test.case("nothing has replicated yet: not ready, and that is not remembered", function()
			local w = world()
			check.is_false(w.impact.ready())
			-- the kit and the presets arrive
			w.children.KitVfx = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(clean) })
			w.now += 1
			check.is_true(w.impact.ready()) -- (as committed, the first answer was kept for good: an impact never played)
			check.equal(#w.warned, 0)
		end)
		test.case("the kit is found where a kit project mounts it, and beside this module", function()
			-- (it was looked for as ReplicatedStorage.KitVfx alone: in a kit project, whose runtime is ReplicatedStorage.kit,
			-- no impact could ever play)
			local w = world()
			w.children.kit = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(clean) })
			check.is_true(w.impact.ready())
			local beside = world(function(w2: any)
				return { Parent = w2.folder({ Vfx = w2.module(kit({ impact = true })) }) }
			end)
			beside.children.VfxPresets = beside.folder({ _textures = beside.module({}), impact = beside.module(clean) })
			check.is_true(beside.impact.ready()) -- no folder of any known name: the module beside it
		end)
		test.case("the kit is not required before the presets' texture registry is there", function()
			-- (Vfx waits for it with no time limit: required too early, the shooter's own code would hang there)
			local w = world()
			local presets: { [string]: any } = { impact = w.module(clean) }
			w.children.kit = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder(presets)
			check.is_false(w.impact.ready())
			check.equal(w.required, 0)
			presets._textures = w.module({})
			w.now += 1
			check.is_true(w.impact.ready())
		end)
		test.case("a preset whose module throws is refused for what it is", function()
			local w = world()
			w.children.kit = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module("broken") })
			check.is_false(w.impact.ready())
			check.equal(#w.warned, 1)
			check.is_true(string.find(w.warned[1], "the preset's module threw", 1, true) ~= nil)
			check.is_true(string.find(w.warned[1], "EditableMesh", 1, true) == nil)
		end)
		test.case(
			"a preset the kit learns of later becomes playable (the kit takes presets that arrive late)",
			function()
				local w = world()
				local known: { [string]: boolean } = {}
				local presets: { [string]: any } = { _textures = w.module({}) }
				w.children.KitVfx = w.folder({ Vfx = w.module(kit(known)) })
				w.children.VfxPresets = w.folder(presets)
				check.is_false(w.impact.ready())
				known.impact = true
				presets.impact = w.module(clean)
				w.now += 1
				check.is_true(w.impact.ready())
			end
		)
		test.case("asking again is bounded: not more than once in a while, and not for ever", function()
			local w = world()
			check.is_false(w.impact.ready())
			w.children.KitVfx = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(clean) })
			check.is_false(w.impact.ready()) -- asked again at once: not looked for (a burst of hits does not search every time)
			check.equal(w.required, 0)
			w.now += w.impact.RETRY_EVERY + 0.01
			check.is_true(w.impact.ready())
			-- a place where it does not come: after RETRY_FOR seconds that is said, ONCE, and it is looked for more slowly
			local never = world()
			for _ = 1, 400 do
				check.is_false(never.impact.ready())
				never.now += 0.5
			end
			check.equal(#never.warned, 1)
			check.is_true(string.find(never.warned[1], "not playable after", 1, true) ~= nil)
			never.now += never.impact.RETRY_SLOW + 0.1
			check.is_false(never.impact.ready()) -- (a look, now: the next is RETRY_SLOW seconds from here)
			local looks = never.looked
			never.children.KitVfx = never.folder({ Vfx = never.module(kit({ impact = true })) })
			never.children.VfxPresets = never.folder({ _textures = never.module({}), impact = never.module(clean) })
			never.now += 1
			check.is_false(never.impact.ready()) -- a second later: not looked for (every RETRY_SLOW seconds now)
			check.equal(never.looked, looks)
			never.now += never.impact.RETRY_SLOW
			check.is_true(never.impact.ready()) -- never given up for good: a slow place still gets its impacts
			check.equal(#never.warned, 1)
		end)
		test.case("a preset that LOADED and is refused is remembered as refused, and said once", function()
			local w = world()
			local meshy = { version = 3, layers = { { kind = "mesh", name = "shell" } } }
			w.children.KitVfx = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(meshy) })
			check.is_false(w.impact.ready())
			local loads = w.required
			for _ = 1, 20 do
				w.now += 5
				check.is_false(w.impact.ready())
			end
			check.equal(w.required, loads) -- not loaded and scanned again
			check.equal(#w.warned, 1)
			check.is_true(string.find(w.warned[1], "would build EditableMeshes", 1, true) ~= nil)
		end)
		test.case("a preset that is not version 3 is refused for what it is: it is never said to be ready", function()
			local w = world()
			local old = { version = 2, layers = { { kind = "sprite" } } }
			w.children.KitVfx = w.folder({ Vfx = w.module(kit({ impact = true })) })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(old) })
			check.is_false(w.impact.ready())
			check.equal(#w.warned, 1)
			check.is_true(string.find(w.warned[1], "not a version-3 preset", 1, true) ~= nil)
		end)
		test.case("a kit module that throws is refused for good, not asked for every hit", function()
			local w = world()
			w.children.KitVfx = w.folder({ Vfx = w.module("broken") })
			w.children.VfxPresets = w.folder({ _textures = w.module({}), impact = w.module(clean) })
			check.is_false(w.impact.ready())
			local loads = w.required
			w.now += 30
			check.is_false(w.impact.ready())
			check.equal(w.required, loads)
		end)
	end)
end
