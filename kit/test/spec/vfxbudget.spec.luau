-- vfxbudget.spec.luau (kit) - what the VFX runtime may spend (src/kit/VfxBudget.luau; the owner's limitations file):
--   F-R06  a detail level really drops layers and cuts emission (it only set how many impacts play and how far away)
--   F-R04  one count of meshes in use across every effect, a ceiling, a share kept for critical cues, builds a second
-- And that the runtime USES the rules: read from its code (comments taken out), and run where it can be run.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxBudget = require("../../../src/kit/VfxBudget")
local VfxValidate = require("../../../src/kit/VfxValidate")

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	local flat = string.gsub(table.concat(out, " "), "%s+", " ")
	flat = string.gsub(flat, "%( ", "(")
	return (string.gsub(flat, ",? %)", ")"))
end

local function has(text: string, needle: string): boolean
	return string.find(text, needle, 1, true) ~= nil
end

-- an impact as a studio would tier it: the flash and the core dust at every level, chips cut at the low levels, a
-- second puff and a light from Medium up, a lingering haze and a shell at High only
local IMPACT = {
	{ name = "flash", kind = "sprite", count = 1 },
	{ name = "dust", kind = "sprite", count = 12, tierCount = { Low = 0.34, Medium = 0.67 } },
	{ name = "chips", kind = "debris", count = 9, tierCount = { Low = 0.34 } },
	{ name = "puff2", kind = "sprite", count = 6, tier = "Medium" },
	{ name = "glow", kind = "light", tier = "Medium" },
	{ name = "haze", kind = "sprite", rate = 8, tier = "High" },
	{ name = "shell", kind = "mesh", tier = "High" },
}

local function total(layers: { any }): number
	local n = 0
	for _, el in layers do
		if type(el.count) == "number" then
			n += el.count
		end
	end
	return n
end

local function count(layers: { any }, kind: string): number
	local n = 0
	for _, el in layers do
		if el.kind == kind then
			n += 1
		end
	end
	return n
end

return function()
	test.suite("detail tiers (F-R06)", function()
		test.case("a level drops the layers above it and cuts the emission of the ones it keeps", function()
			local high, hd = VfxBudget.tiered(IMPACT, "High")
			local mid, md = VfxBudget.tiered(IMPACT, "Medium")
			local low, ld = VfxBudget.tiered(IMPACT, "Low")
			check.equal(#high, 7)
			check.equal(#hd, 0)
			check.equal(#mid, 5)
			check.equal(table.concat(md, ","), "haze,shell")
			check.equal(#low, 3)
			check.equal(table.concat(ld, ","), "puff2,glow,haze,shell")
			-- emission: 28 particles at High, 24 at Medium, 8 at Low
			check.equal(total(high), 28)
			check.equal(total(mid), 1 + 8 + 9 + 6)
			check.equal(total(low), 1 + 4 + 3)
			-- meshes and lights: none at Low, the light from Medium, the mesh at High only
			check.equal(count(low, "mesh") + count(low, "light"), 0)
			check.equal(count(mid, "light"), 1)
			check.equal(count(mid, "mesh"), 0)
			check.equal(count(high, "mesh"), 1)
		end)
		test.case("the core of the effect is the same at every level", function()
			for _, level in VfxBudget.LEVELS do
				local kept = VfxBudget.tiered(IMPACT, level)
				check.equal(kept[1].name, "flash") -- what makes it THIS hit is there, first, at every level
				check.equal(kept[1].count, 1)
				check.equal(kept[2].name, "dust")
			end
		end)
		test.case("with no level set, everything plays as it is written, and the preset is not changed", function()
			local kept, dropped = VfxBudget.tiered(IMPACT, nil)
			check.equal(#kept, 7)
			check.equal(#dropped, 0)
			for i, el in kept do
				check.is_true(el == IMPACT[i]) -- the very tables: nothing copied, nothing cut
			end
			local low = VfxBudget.tiered(IMPACT, "Low")
			check.is_true(low[2] ~= IMPACT[2]) -- a cut layer is a COPY
			check.equal(IMPACT[2].count, 12)
			check.is_true(low[1] == IMPACT[1]) -- an uncut one is the same table
		end)
		test.case("a cut layer keeps one particle at least, a range is cut at both ends, a curve is left", function()
			check.equal(VfxBudget.layerAt({ count = 2, tierCount = { Low = 0.1 } }, "Low").count, 1)
			check.equal(VfxBudget.layerAt({ count = 0, rate = 0, tierCount = { Low = 0.1 } }, "Low").count, 0) -- written to emit nothing: nothing
			check.equal(VfxBudget.layerAt({ count = 0, rate = 0, tierCount = { Low = 0.1 } }, "Low").rate, 0)
			local twin = VfxBudget.layerAt(
				{ count = 10, twin = { count = 20, lifeScale = 3 }, tierCount = { Low = 0.5 } },
				"Low"
			)
			check.equal(twin.twin.count, 10) -- a twin emitter's own count is cut with its layer's
			check.equal(twin.twin.lifeScale, 3)
			local r = VfxBudget.layerAt({ rate = { 10, 20 }, tierCount = { Low = 0.5 } }, "Low").rate
			check.equal(r[1], 5)
			check.equal(r[2], 10)
			local curve = { { 0, 4 }, { 1, 0 }, { 2, 0 } }
			check.is_true(VfxBudget.layerAt({ rate = curve, tierCount = { Low = 0.5 } }, "Low").rate == curve)
			check.equal(VfxBudget.factor({ Low = 0.4 }, "Medium"), 1)
			check.equal(VfxBudget.factor({ Low = 0.4 }, "Ultra"), 1)
			check.equal(VfxBudget.factor("half", "Low"), 1)
		end)
		test.case("a preset whose tiers are wrong is said in words, one nothing is left of at Low too", function()
			check.equal(#VfxBudget.problems(IMPACT), 0)
			check.equal(#VfxBudget.problems({ { kind = "sprite" } }), 0)
			local said = table.concat(
				VfxBudget.problems({
					{ name = "a", kind = "sprite", tier = "Ultra" },
					{ name = "b", kind = "sprite", tierCount = { Low = 0, Epic = 0.5, Medium = 2 } },
					{ name = "c", kind = "sprite", tierCount = 0.5 },
				}),
				" | "
			)
			check.is_true(has(said, "layers[1](a).tier"))
			check.is_true(has(said, '"Epic" is not a level'))
			check.is_true(has(said, "layers[2](b).tierCount.Low"))
			check.is_true(has(said, "layers[2](b).tierCount.Medium"))
			check.is_true(has(said, "layers[3](c).tierCount: tierCount is"))
			local none = VfxBudget.problems({ { kind = "sprite", tier = "Medium" }, { kind = "mesh", tier = "High" } })
			check.equal(#none, 1)
			check.is_true(has(none[1], "no layer plays at Low"))
		end)
		test.case("a layer that says no tier gets the kit's own; one that says its own keeps it", function()
			local layers = {
				{ name = "boom", kind = "sound" },
				{ name = "big", kind = "mesh", at = 0, life = 2, scale = 10 },
				{ name = "mid", kind = "mesh", at = 0, life = 1, scale = { 4, 1, 4 } },
				{ name = "small", kind = "mesh", at = 0.02, life = 0.5, scale = { { 0, 1 }, { 1, 2 } } },
				{
					name = "eased",
					kind = "mesh",
					at = 0,
					life = 1,
					scale = { from = { 1, 1, 1 }, to = { 3, 1, 3 }, ease = "expoOut" },
				},
				{ name = "later", kind = "mesh", at = 1, life = 0.2, scale = 0.5 },
				{ name = "mine", kind = "mesh", at = 0, life = 0.1, scale = 0.1, tier = "Low" },
				{ name = "sparks", kind = "sprite", count = 20 },
				{ name = "few", kind = "sprite", count = 4 },
				{ name = "one", kind = "sprite", count = 1 },
				{ name = "key", kind = "light", at = 0 },
				{ name = "fill", kind = "light", at = 0.04 },
				-- another THING (its own place and shape): a long faint haze round a short solid core
				{
					name = "haze",
					kind = "mesh",
					at = 0,
					point = { 5, 0, 0 },
					shape = "tube",
					life = 9,
					scale = 9,
					transparency = 0.6,
				},
				{
					name = "core",
					kind = "mesh",
					at = 0,
					point = { 5, 0, 0 },
					shape = "tube",
					life = 1,
					scale = 1,
					transparency = { { 0, 0 }, { 1, 1 } },
				},
				{
					name = "alone",
					kind = "mesh",
					at = 0,
					point = { 9, 0, 0 },
					shape = "tube",
					life = 0.1,
					scale = 0.1,
					transparency = 0.9,
				},
				{ name = "cue", kind = "mesh", at = 0, life = 0.01, scale = 0.01, critical = true },
			}
			local plan = VfxBudget.auto(layers)
			check.equal(plan[13].tier, "Medium") -- the haze: much more of it, but the core is the solid shell
			check.equal(plan[14], nil) -- the core of that thing plays at every level
			check.equal(plan[15], nil) -- a thing of one mesh is never taken away, however small and faint
			check.equal(plan[16], nil) -- a cue that must not be lost is never tiered
			check.equal(plan[1], nil) -- a sound carries the beat: never touched
			check.equal(plan[2], nil) -- the most there is of at that moment: every level
			check.equal(plan[3], nil) -- (six shells of that thing, two named: the top two stay)
			check.equal(plan[5].tier, "Medium") -- 1 x 3: the third
			check.equal(plan[4].tier, "Medium") -- 0.5 x 2: the fourth of six - to three quarters, from Medium
			check.equal(plan[6], nil) -- alone at its own moment: it stays
			check.equal(plan[7], nil) -- it says its own tier: the rule leaves it
			check.equal(plan[8].tierCount.Low, 0.4)
			check.equal(plan[9].tierCount.Low, 0.6)
			check.equal(plan[9].tierCount.Medium, nil)
			check.equal(plan[10], nil)
			check.equal(plan[11], nil) -- the first light of its moment
			check.equal(plan[12].tier, "Medium") -- the second
			local low = VfxBudget.tiered(layers, "Low", true)
			local names = {}
			for _, el in low do
				table.insert(names, el.name .. (if el.count then "=" .. el.count else ""))
			end
			check.equal(table.concat(names, " "), "boom big mid later mine sparks=8 few=2 one=1 key core alone cue")
			check.equal(#VfxBudget.tiered(layers, "Low", false), 16) -- without the kit's rule only the authored tiers count
			check.equal(#VfxBudget.tiered(layers, nil, true), 16) -- and with no level, everything
		end)
		test.case("the validator reads the tiers of a version 3 preset", function()
			local function said(layers: { any }): string
				local out = {}
				for _, issue in VfxValidate.preset("tiers", { version = 3, duration = 1, layers = layers }, {}, {}) do
					table.insert(out, issue.message)
				end
				return table.concat(out, " | ")
			end
			local bad = said({ { name = "a", kind = "light", tier = "Ultra" } })
			check.is_true(has(bad, "tier is the lowest level"))
			local gone = said({ { name = "a", kind = "light", tier = "High" } })
			check.is_true(has(gone, "no layer plays at Low"))
			local good = said({
				{ name = "a", kind = "light" },
				{ name = "b", kind = "mesh", shape = "ring", tier = "High", critical = true },
			})
			check.is_false(has(good, "tier"))
			check.is_false(has(good, "critical"))
			check.is_true(has(said({ { name = "a", kind = "light", critical = "yes" } }), "critical is true or false"))
			check.is_true(
				has(
					said({ { name = "a", kind = "light", critical = true } }),
					"critical is for a mesh layer or a mesh trail"
				)
			)
		end)
		test.case(
			"the stage drops and cuts by the level it is played at, and an impact plays at its configured level",
			function()
				local stage = code("src/kit/VfxStage.luau")
				local impact = code("src/kit/VfxImpact.luau")
				check.is_true(has(stage, "local tiers = if o.detail ~= nil then VfxBudget.auto(preset.layers) else {}"))
				check.is_true(has(stage, "VfxBudget.layerAt(withMaterial(raw), o.detail, tiers[index])"))
				check.is_true(has(impact, "config.detail = o.detail"))
				check.is_true(has(impact, "detail = config.detail"))
			end
		)
	end)

	test.suite("admission under pool pressure (F-R04)", function()
		local BUDGET = { max = 8, reserve = 2, perSecond = 6 }
		test.case(
			"with no budget set, everything is admitted (the kit does not know what a client can hold)",
			function()
				check.is_true((VfxBudget.admit(500, false, nil)))
				check.is_true((VfxBudget.mayStart({ 1, 1, 1, 1, 1, 1, 1, 1 }, 1.1, false, nil)))
			end
		)
		test.case(
			"an ordinary mesh is refused once the ordinary share is in use; a critical one has the reserve",
			function()
				check.is_true((VfxBudget.admit(0, false, BUDGET)))
				check.is_true((VfxBudget.admit(5, false, BUDGET)))
				local ok, why = VfxBudget.admit(6, false, BUDGET)
				check.is_false(ok)
				check.is_true(has(why :: string, "kept for critical cues"))
				check.is_true((VfxBudget.admit(6, true, BUDGET))) -- the cue that must not be lost still builds
				check.is_true((VfxBudget.admit(7, true, BUDGET)))
				check.is_false((VfxBudget.admit(8, true, BUDGET))) -- and the ceiling holds for everyone
			end
		)
		test.case(
			"fresh builds are bounded a second, the bound lets go, and a critical cue is not held by it",
			function()
				local recent: { number } = {}
				local started = 0
				for i = 1, 20 do
					local now = 5 + i * 0.005
					if VfxBudget.mayStart(recent, now, false, BUDGET) then
						started += 1
						recent = VfxBudget.started(recent, now)
					end
				end
				check.equal(started, 6)
				local _, why = VfxBudget.mayStart(recent, 5.2, false, BUDGET)
				check.is_true(has(why :: string, "started in the last second"))
				check.is_true((VfxBudget.mayStart(recent, 5.2, true, BUDGET)))
				check.is_true((VfxBudget.mayStart(recent, 6.2, false, BUDGET)))
				check.equal(#VfxBudget.started(recent, 6.2), 1)
			end
		)
		test.case("a budget that cannot be one is said in words", function()
			check.equal(VfxBudget.budget({ max = 8, reserve = 2, perSecond = 6 }).max, 8)
			check.equal(VfxBudget.budget({ max = 4 }).reserve, 0)
			for _, bad in
				{ "eight", { max = 0 }, { max = 2.5 }, { max = 4, reserve = 4 }, { max = 4, perSecond = 0 } } :: { any }
			do
				local got, wrong = VfxBudget.budget(bad)
				check.equal(got, nil)
				check.is_true(type(wrong) == "string" and #wrong > 10)
			end
		end)
	end)

	-- THE REAL MESH MAKER (src/kit/VfxMesh.luau itself), with the engine stood in for: what it says is in use is held
	-- to what was really handed out and not given back (a review found the count could only be read, never run)
	test.suite("the mesh maker's count (F-R04)", function()
		local luau = require("@lune/luau")
		local roblox = require("@lune/roblox")
		local function maker()
			-- the made engine. growMax: how many GROWABLE meshes may be alive at once (the real engine: 8; nil = any);
			-- copies: it can make a fixed-size copy; fixedMax: how many of those may be alive; throwAdd: AddVertex throws
			-- cap: the engine's editable memory (a growable mesh costs growCost of it, a fixed-size one fixedCost);
			-- outside: growable meshes a GAME holds (not the kit's); copyFrames: the copy yields that many frames;
			-- copyThrows: the copy throws
			local w: any = {
				now = 100,
				fail = 0,
				alive = 0,
				growing = 0,
				fixedAlive = 0,
				peakGrowing = 0,
				outside = 0,
				growCost = 125,
				fixedCost = 3,
			}
			local function room(cost: number): boolean
				return w.cap == nil or w.growing * w.growCost + w.fixedAlive * w.fixedCost + cost <= w.cap
			end
			local function mesh(fixed: boolean?)
				w.alive += 1
				if fixed then
					w.fixedAlive += 1
				else
					w.growing += 1
					w.peakGrowing = math.max(w.peakGrowing, w.growing)
				end
				local n, gone = 0, false
				return setmetatable({}, {
					__index = function(_, k)
						if k == "Destroy" then
							return function()
								if not gone then
									gone = true
									w.alive -= 1
									if fixed then
										w.fixedAlive -= 1
									else
										w.growing -= 1
									end
								end
							end
						end
						if k == "AddVertex" and w.throwAdd then
							return function()
								error("AddVertex refused (made)")
							end
						end
						if k == "SetPosition" and w.pos then -- (recorded when asked: where each point is set)
							return function(_, id: number, at: any)
								w.pos[id] = at
							end
						end
						if k == "AddTriangle" and w.tris then -- (recorded when asked: which points each triangle joins)
							return function(_, p1: number, p2: number, p3: number)
								n += 1
								table.insert(w.tris, { p1, p2, p3 })
								return n
							end
						end
						return function()
							n += 1
							return n
						end
					end,
				})
			end
			local function part()
				local props = {}
				return setmetatable({}, {
					__index = function(_, k)
						if k == "GetChildren" then
							return function()
								return {}
							end
						elseif k == "IsA" then
							return function(_s: any, c: string)
								return c == "MeshPart"
							end
						elseif k == "Destroy" then
							return function() end
						end
						return props[k]
					end,
					__newindex = function(_, k, v)
						props[k] = v
					end,
				})
			end
			local calls = {
				CreateEditableMesh = function()
					if (w.growMax and w.growing + w.outside >= w.growMax) or not room(w.growCost) then
						return nil -- (the real engine: no error, nil)
					end
					return mesh()
				end,
				CreateEditableMeshAsync = function()
					for _ = 1, w.copyFrames or 0 do
						coroutine.yield() -- (the real call yields)
					end
					if w.copyThrows then
						error("the copy threw (made)")
					end
					if (w.fixedMax and w.fixedAlive >= w.fixedMax) or not room(w.fixedCost) then
						return nil
					end
					return mesh(true)
				end,
				CreateMeshPartAsync = function()
					if w.fail > 0 then
						w.fail -= 1
						error("over the client's EditableMesh budget (made)")
					end
					return part()
				end,
			}
			-- (an engine with no fixed-size copy has no such member at all)
			local assets = setmetatable({}, {
				__index = function(_, k)
					if k == "CreateEditableMeshAsync" and not w.copies then
						return nil
					end
					return calls[k]
				end,
			})
			w.mesh = luau.load(fs.readFile("src/kit/VfxMesh.luau"), {
				debugName = "VfxMesh",
				environment = {
					game = {
						GetService = function()
							return assets
						end,
					},
					Content = {
						fromObject = function(x: any)
							return x
						end,
					},
					Vector3 = roblox.Vector3,
					Vector2 = roblox.Vector2,
					CFrame = roblox.CFrame,
					Color3 = roblox.Color3,
					os = {
						clock = function()
							return w.now
						end,
					},
					task = {
						wait = function()
							coroutine.yield()
						end,
					},
					require = function(path: string)
						if path == "./VfxBudget" then
							return VfxBudget
						end
						return require("../../../src/kit/VfxArc")
					end,
				},
			})()
			return w
		end
		-- n builds started in ONE frame, each in its own thread (as the stage starts its mesh layers), stepped a frame
		-- at a time until all are done -> (what each got, or false; the frames it took)
		local function burst(w: any, n: number, one: (number) -> any): ({ any }, number)
			local out, threads = {}, {}
			for i = 1, n do
				threads[i] = coroutine.create(function()
					out[i] = one(i) or false
				end)
			end
			local frames = 0
			while frames < 20000 do
				local live = 0
				for _, t in threads do
					if coroutine.status(t) == "suspended" then
						local ok, err = coroutine.resume(t)
						if not ok then
							error(err)
						end
						if coroutine.status(t) == "suspended" then
							live += 1
						end
					end
				end
				if live == 0 then
					break
				end
				frames += 1
				w.now += 1 / 60
			end
			return out, frames
		end
		local function builtOf(list: { any }): number
			local n = 0
			for _, b in list do
				if b then
					n += 1
				end
			end
			return n
		end
		local function rock(w: any, seed: number, critical: boolean?): any
			w.now += 0.3
			return (w.mesh.build("rock", { seed = seed }, nil, nil, critical))
		end

		test.case(
			"with no budget, an effect of twenty meshes builds all twenty, and the count comes back to nothing",
			function()
				local w = maker()
				check.equal(w.mesh.setBudget(false), nil)
				local held = {}
				for i = 1, 20 do
					held[i] = rock(w, i)
					check.is_true(held[i] ~= nil)
				end
				check.equal(w.mesh.stats().active, 20)
				check.equal(w.mesh.stats().max, 0) -- no budget is set
				for _, b in held do
					b.destroy()
				end
				check.equal(w.mesh.stats().active, 0)
				held[1].destroy() -- a second destroy of one (a layer let go at its fade, then the stage's cleanup)
				check.equal(w.mesh.stats().active, 0)
				check.equal(w.mesh.stats().refused, 0)
			end
		)
		test.case("a game's budget holds: the ordinary share, the reserve for critical layers, the ceiling", function()
			local w = maker()
			check.equal(w.mesh.setBudget({ max = 8, reserve = 2, perSecond = 100 }), nil)
			local held = {}
			for i = 1, 6 do
				table.insert(held, rock(w, i))
			end
			check.equal(#held, 6)
			check.equal(rock(w, 7), nil) -- the seventh ordinary one is turned away
			table.insert(held, rock(w, 8, true)) -- a critical one builds from the reserve
			table.insert(held, rock(w, 9, true))
			check.equal(#held, 8)
			check.equal(rock(w, 10, true), nil) -- the ceiling holds for everyone
			local st = w.mesh.stats()
			check.equal(st.active, 8)
			check.equal(st.refused, 1)
			check.equal(st.refusedCritical, 1)
			held[1].destroy()
			check.equal(rock(w, 11), nil) -- one given back: 7 in use, still in the reserve - not for an ordinary one
			held[2].destroy()
			held[3].destroy()
			check.is_true(rock(w, 11) ~= nil) -- three given back: the ordinary share has room again
			check.is_true(type(w.mesh.setBudget({ max = 0 })) == "string") -- a budget that is none is said, and changes nothing
			check.equal(w.mesh.stats().max, 8)
			w.mesh.setBudget(false)
			check.is_true(rock(w, 12) ~= nil and rock(w, 13) ~= nil) -- the budget taken off: no ceiling
		end)
		test.case("the ceiling is on by default, and a game may set its own or none", function()
			local w = maker()
			check.equal(w.mesh.stats().max, 100)
			check.equal(w.mesh.stats().reserve, 10)
			w.mesh.setBudget(false)
			check.equal(w.mesh.stats().max, 0)
			w.mesh.setBudget(nil)
			check.equal(w.mesh.stats().max, 100)
			local held = 0
			for i = 1, 130 do
				if rock(w, i) then
					held += 1
				end
			end
			check.equal(held, 90) -- the ordinary share; the last 10 are a critical cue's
			check.is_true(rock(w, 200, true) ~= nil)
		end)
		-- THE ENGINE'S OWN LIMIT (measured in a Studio play client, 2026-11-15): 8 growable meshes alive at once, the
		-- ninth create returns nil. The made engine here has that limit
		test.case(
			"a mesh is grown, settled into a fixed-size copy, and the growable one is released at once",
			function()
				local old = maker() -- an engine with no fixed-size copy: what the kit did before
				old.growMax = 8
				old.mesh.setBudget(false)
				local got, said = 0, false
				for i = 1, 40 do
					old.now += 0.3
					local b, why = old.mesh.build("rock", { seed = i })
					if b then
						got += 1
					elseif type(why) == "string" and string.find(why, "no place to grow", 1, true) then
						said = true
					end
				end
				check.equal(got, 8) -- an effect of forty mesh layers drew its first eight
				check.is_true(old.mesh.stats().engineFull > 0)
				check.is_true(said) -- said as what it is

				local w = maker()
				w.growMax, w.copies = 8, true
				w.mesh.setBudget(false)
				local held = {}
				for i = 1, 40 do
					held[i] = rock(w, i)
					check.is_true(held[i] ~= nil)
				end
				check.equal(w.growing, 0) -- no growable mesh is left alive
				check.equal(w.fixedAlive, 40)
				check.is_true(w.peakGrowing <= 6)
				check.equal(w.mesh.stats().engineFull, 0)
				local ribbon = w.mesh.ribbon(8, 12)
				check.is_true(ribbon ~= nil)
				check.equal(w.growing, 0) -- a ribbon too
				for _, b in held do
					b.destroy()
				end
				ribbon.destroy()
			end
		)
		test.case("a build that throws half way gives its growable mesh back", function()
			local w = maker()
			w.growMax, w.copies, w.throwAdd = 8, true, true
			for i = 1, 20 do
				check.equal(rock(w, i), nil)
			end
			check.equal(w.mesh.ribbon(8, 12), nil)
			check.equal(w.growing, 0) -- (each one left alive took one of the engine's eight for good)
			check.equal(w.mesh.stats().active, 0)
			w.throwAdd = false
			check.is_true(rock(w, 50) ~= nil)
		end)
		test.case("a client learns its own ceiling the first time the engine refuses a mesh", function()
			local w = maker()
			w.growMax, w.copies, w.fixedMax = 8, true, 10 -- a small device: ten fixed-size meshes, then none
			local held = {}
			for i = 1, 30 do
				local b = rock(w, i)
				if b then
					table.insert(held, b)
				end
			end
			check.equal(#held, 10)
			check.equal(w.growing, 0) -- a mesh that could not be copied is not kept growable: the places to grow in stay free
			local st = w.mesh.stats()
			check.equal(st.learned, 10)
			check.equal(st.max, 10) -- the default of 100 is cut to what this client showed
			check.equal(st.reserve, 2)
			local full = st.engineFull
			check.is_true(full >= 1)
			check.equal(rock(w, 100), nil) -- over the learned ceiling: turned away ...
			check.equal(w.mesh.stats().engineFull, full) -- ... without asking the engine again
			for i = 1, 6 do
				held[i].destroy()
			end
			check.is_true(rock(w, 101) ~= nil) -- room again under the learned ceiling
			w.mesh.setBudget({ max = 50, reserve = 5 }) -- a game that sets its own budget takes charge: what was learned is forgotten
			check.equal(w.mesh.stats().max, 50)
			check.equal(w.mesh.stats().learned, 0)
		end)
		test.case(
			"layers started in one frame wait their turn to grow: none is refused, none is created past the gate",
			function()
				local w = maker()
				w.growMax, w.copies, w.copyFrames = 8, true, 3
				w.mesh.setBudget(false)
				local out = burst(w, 60, function(i)
					return (w.mesh.build("rock", { seed = i }))
				end)
				check.equal(builtOf(out), 60)
				check.equal(w.peakGrowing, 1) -- one growing at a time
				check.equal(w.growing, 0)
				check.equal(w.mesh.stats().engineFull, 0)
				check.equal(w.mesh.stats().learned, 0)
			end
		)
		test.case("a burst builds as many as one at a time, and learns the same ceiling", function()
			-- (the first version grew six at once: on this made engine a burst built 89 where one at a time built 291; two
			-- at once, 251)
			local function made(atOnce: boolean): (number, number)
				local w = maker()
				w.growMax, w.copies, w.copyFrames, w.cap = 8, true, 2, 1000
				w.mesh.setBudget(false)
				local n = 0
				if atOnce then
					n = builtOf((burst(w, 320, function(i)
						return (w.mesh.build("rock", { seed = i }))
					end)))
				else
					for i = 1, 320 do
						n += builtOf((burst(w, 1, function()
							return (w.mesh.build("rock", { seed = i }))
						end)))
					end
				end
				return n, w.mesh.stats().learned
			end
			local one, learnedOne = made(false)
			local many, learnedMany = made(true)
			check.equal(one, 291)
			check.equal(many, 291)
			check.equal(learnedOne, 291)
			check.equal(learnedMany, 291)
		end)
		test.case("a passing refusal does not hold the client down for the session", function()
			local w = maker()
			w.growMax, w.copies = 8, true
			w.outside = 8 -- a game's own growable meshes hold every place, for a moment
			local b, why = w.mesh.build("rock", { seed = 1 })
			check.equal(b, nil)
			check.is_true(type(why) == "string" and string.find(why, "no place to grow", 1, true) ~= nil)
			w.outside = 0
			check.equal(w.mesh.stats().learned, 1) -- (all the kit can tell: it was refused with nothing standing)
			w.now += 31
			check.equal(w.mesh.stats().learned, 0) -- forgotten after half a minute
			check.equal(w.mesh.stats().max, 100)
			local n = 0
			for i = 1, 50 do
				if rock(w, 10 + i) then
					n += 1
				end
			end
			check.equal(n, 50)
		end)
		test.case("a build whose thread died while its copy yielded gives its place to grow in back", function()
			local w = maker()
			w.growMax, w.copies, w.copyFrames = 8, true, 50
			w.mesh.setBudget(false)
			for i = 1, 1 do
				local dead = coroutine.create(function()
					w.mesh.build("rock", { seed = i })
				end)
				coroutine.resume(dead) -- into its copy's yield, and never again (its script was destroyed)
			end
			check.equal(w.growing, 1) -- it holds the one turn to grow
			w.copyFrames = 1
			w.now += 6
			local out, frames = burst(w, 3, function(i)
				return (w.mesh.build("rock", { seed = 20 + i }))
			end)
			check.equal(builtOf(out), 3)
			check.is_true(frames < 30) -- (the first version: 365 frames, each build waiting out its 120)
			check.equal(w.growing, 0) -- the dead builds' growable meshes were destroyed
		end)
		test.case("an effect's build started while a prewarm yields is still held by the budget", function()
			local w = maker()
			w.growMax, w.copies, w.copyFrames = 8, true, 5
			w.mesh.setBudget({ max = 2, reserve = 0 })
			local held = burst(w, 2, function(i)
				return (w.mesh.build("rock", { seed = i }))
			end)
			check.equal(builtOf(held), 2)
			local warm = coroutine.create(function()
				w.mesh.prewarm("rock", { seed = 77 }, nil, nil, 1)
			end)
			coroutine.resume(warm) -- the prewarm is in its copy's yield
			local third = burst(w, 1, function()
				return (w.mesh.build("rock", { seed = 3 }))
			end)
			check.equal(builtOf(third), 0) -- (a flag of the module let it through as a prewarm)
			check.equal(w.mesh.stats().refused, 1)
			while coroutine.status(warm) == "suspended" do
				coroutine.resume(warm)
			end
			check.equal(w.mesh.stats().active, 2)
		end)
		test.case("a draped sheet's face and its back share no point (a shared point's normal is none)", function()
			local w = maker()
			w.growMax, w.copies = 8, true
			w.tris = {}
			local sheet = w.mesh.sheet(3, 2, 10)
			check.is_true(sheet ~= nil)
			check.equal(#w.tris, 3 * 2 * 4) -- two triangles a cell, a face and a back
			-- the points the triangles join fall in groups; one group per face, each with half the triangles
			local group, size = {}, {}
			local function find(v: number): number
				while group[v] and group[v] ~= v do
					v = group[v]
				end
				return v
			end
			for _, t in w.tris do
				for _, v in t do
					group[v] = group[v] or v
				end
				local r = find(t[1])
				for k = 2, 3 do
					local q = find(t[k])
					if q ~= r then
						group[q] = r
					end
				end
			end
			for _, t in w.tris do
				local r = find(t[1])
				size[r] = (size[r] or 0) + 1
			end
			local groups, each = 0, {}
			for _, n in size do
				groups += 1
				table.insert(each, n)
			end
			check.equal(groups, 2)
			check.equal(each[1], 12)
			check.equal(each[2], 12)
			-- laid over the ground (set): the back's points go where the face's go, and every back triangle is a face
			-- triangle the other way round (the review: the grouping alone passed a wrong winding and a back never moved)
			w.pos = {}
			local Vector3 = require("@lune/roblox").Vector3
			local pts = {}
			for j = 0, 2 do
				for i = 0, 3 do
					table.insert(pts, Vector3.new(i * 1.5, (i * 7 + j * 3) % 5 * 0.1, j * 2))
				end
			end
			sheet.set(pts, Vector3.zero)
			local function key(v: any): string
				return string.format("%.4f,%.4f,%.4f", v.X, v.Y, v.Z)
			end
			local faceTris, backTris = {}, {}
			local faceGroup = find(w.tris[1][1])
			for _, t in w.tris do
				local a, b, c = w.pos[t[1]], w.pos[t[2]], w.pos[t[3]]
				check.is_true(a ~= nil and b ~= nil and c ~= nil) -- every point of both faces was set
				if a and b and c then
					local ka, kb, kc = key(a), key(b), key(c)
					if find(t[1]) == faceGroup then
						faceTris[ka .. "|" .. kb .. "|" .. kc] = true
						faceTris[kb .. "|" .. kc .. "|" .. ka] = true
						faceTris[kc .. "|" .. ka .. "|" .. kb] = true
					else
						table.insert(backTris, ka .. "|" .. kc .. "|" .. kb) -- (read the other way round)
					end
				end
			end
			check.equal(#backTris, 12)
			for _, t in backTris do
				check.is_true(faceTris[t] == true)
			end
		end)
		test.case("the pool keeps what a warm-up asks for, and says what it holds", function()
			local w = maker()
			w.growMax, w.copies = 8, true
			-- twelve different rocks made ahead: the pool kept 8 in all, so the first four were thrown away
			for i = 1, 12 do
				w.mesh.prewarm("rock", { seed = i }, nil, nil, 1)
			end
			local held = 0
			for i = 1, 12 do
				held += w.mesh.kept("rock", { seed = i })
			end
			check.equal(held, 8)
			-- asked to keep 20, and 3 of one key: all of them stay
			w.mesh.keep(20, 3)
			for i = 1, 12 do
				w.mesh.prewarm("rock", { seed = i }, nil, nil, 1)
			end
			w.mesh.prewarm("rock", { seed = 99 }, nil, nil, 3)
			held = 0
			for i = 1, 12 do
				held += w.mesh.kept("rock", { seed = i })
			end
			check.equal(held, 12)
			check.equal(w.mesh.kept("rock", { seed = 99 }), 3)
			check.equal(w.mesh.keyOf("rock", { seed = 1 }), w.mesh.keyOf("rock", { seed = 1 }))
			check.is_true(w.mesh.keyOf("rock", { seed = 1 }) ~= w.mesh.keyOf("rock", { seed = 2 }))
			-- never more than KEEP_MOST, never lowered
			w.mesh.keep(5000, 5000)
			local inAll, perKey = w.mesh.keeps()
			check.equal(inAll, 100)
			check.equal(perKey, 100)
			w.mesh.keep(1, 1) -- (never lowered)
			inAll, perKey = w.mesh.keeps()
			check.equal(inAll, 100)
			check.equal(perKey, 100)
			check.equal(w.mesh.keptKey(w.mesh.keyOf("rock", { seed = 99 })), 3)
		end)
		test.case("a copy that throws fails the build and frees its growable mesh; it teaches no ceiling", function()
			local w = maker()
			w.growMax, w.copies, w.copyThrows = 8, true, true
			for i = 1, 12 do
				local b, why = w.mesh.build("rock", { seed = i })
				check.equal(b, nil)
				check.is_true(type(why) == "string" and string.find(why, "copy failed", 1, true) ~= nil)
			end
			check.equal(w.growing, 0)
			check.equal(w.mesh.stats().learned, 0)
			check.equal(w.mesh.stats().active, 0)
		end)
		test.case("the held budget: the set one, cut to a learned ceiling", function()
			check.equal(VfxBudget.ceiling(nil, nil), nil)
			local b = { max = 120, reserve = 12, perSecond = 1000 }
			check.equal(VfxBudget.ceiling(b, nil), b)
			check.equal(VfxBudget.ceiling(b, 200), b) -- a ceiling above the budget changes nothing
			local cut = VfxBudget.ceiling(b, 40) :: any
			check.equal(cut.max, 40)
			check.equal(cut.reserve, 10)
			check.equal(cut.perSecond, 1000)
			local alone = VfxBudget.ceiling(nil, 7) :: any
			check.equal(alone.max, 7)
			check.equal(alone.reserve, 0) -- (a reserve is a budget's: with none set, nothing is kept back)
			check.equal((VfxBudget.ceiling(b, 0) :: any).max, 1) -- never a ceiling of nothing
		end)
		test.case("a build that fails or THROWS gives its count back", function()
			local w = maker()
			w.fail = 2 -- the engine refuses the part, and the retry after freeing the kept ones too
			check.equal(rock(w, 1), nil)
			check.equal(w.mesh.stats().active, 0)
			local b, why = w.mesh.build("seq", { seq = "x", data = { frames = { { 0, 0, 0 } } } }) -- frames with no grid: the maker throws
			check.equal(b, nil)
			check.is_true(type(why) == "string")
			check.equal(w.mesh.stats().active, 0) -- (it stayed one up for good: every later effect a mesh short)
		end)
		test.case("a mesh out of the pool is not held by the rate, and prewarming is not an effect asking", function()
			local w = maker()
			w.mesh.setBudget({ max = 8, reserve = 0, perSecond = 2 })
			local a = w.mesh.build("rock", { seed = 1 })
			local b = w.mesh.build("rock", { seed = 2 })
			check.is_true(a ~= nil and b ~= nil)
			check.equal(w.mesh.build("rock", { seed = 3 }), nil) -- a third FRESH one in the same second: held
			a.destroy()
			b.destroy()
			local again = w.mesh.build("rock", { seed = 1 }) -- the same shape again, the same second: out of the pool
			check.is_true(again ~= nil)
			again.destroy()
			local turnedBefore = w.mesh.stats().refused
			w.now += 5
			w.mesh.setBudget({ max = 2, reserve = 0, perSecond = 1 })
			w.mesh.prewarm("rock", { seed = 40 }, nil, nil, 5)
			check.equal(w.mesh.stats().refused, turnedBefore) -- the prewarm was not turned away
			check.equal(w.mesh.stats().active, 0)
			local taken = 0
			for _ = 1, 2 do
				if w.mesh.build("rock", { seed = 40 }) then
					taken += 1
				end
			end
			check.equal(taken, 2) -- and what it built is there to hand out
		end)
		test.case("kept meshes that are freed for room are not counted as given back twice", function()
			local w = maker()
			local held = {}
			for i = 1, 12 do
				held[i] = rock(w, 100 + i)
			end
			for _, b in held do
				b.destroy() -- twelve go idle: the idle cap frees the oldest
			end
			check.equal(w.mesh.stats().active, 0)
			check.is_true(w.mesh.stats().idle <= 8)
			local one = rock(w, 112)
			check.equal(w.mesh.stats().active, 1)
			one.destroy()
			check.equal(w.mesh.stats().active, 0)
		end)
		test.case(
			"the stage hands the layer's critical to the maker, and a client's detail level reaches every effect",
			function()
				local stage = code("src/kit/VfxStage.luau")
				check.is_true(has(stage, "VfxMesh.build(shape, params, el.wobble, el.erode, el.critical)"))
				check.is_true(has(stage, "VfxMesh.ribbon(samples, (el.reach or 12) * scale, el.critical)"))
				local kit = code("src/kit/Vfx.luau")
				check.is_true(has(kit, "o.detail = o.detail or detailLevel"))
				check.is_true(has(kit, "detail = detailLevel,"))
			end
		)
	end)

	test.suite("meshes are made before the effect, not during it (ten cold Studio sessions, 2026-11-16)", function()
		test.case("what a preset builds is counted: every kind that asks the engine for a mesh", function()
			check.equal(VfxBudget.builds(nil), 0)
			check.equal(
				VfxBudget.builds({
					{ kind = "sprite", count = 20 },
					{ kind = "light" },
					{ kind = "trail" },
					{ kind = "decal" },
				}),
				0
			)
			check.equal(VfxBudget.builds({ { kind = "mesh" }, { kind = "mesh", shape = "ring" } }), 2)
			check.equal(VfxBudget.builds({ { kind = "debris", shape = "rock", count = 90 } }), 40) -- (the layer throws 40 at most)
			check.equal(VfxBudget.builds({ { kind = "debris", shape = "rock" } }), 6)
			check.equal(VfxBudget.builds({ { kind = "debris", count = 12 } }), 0) -- (plain blocks)
			check.equal(VfxBudget.builds({ { kind = "swarm", shape = "Rock", count = 150 } }), 40)
			check.equal(VfxBudget.builds({ { kind = "swarm", count = 150 } }), 0)
			check.equal(
				VfxBudget.builds({
					{ kind = "trail", mesh = true },
					{ kind = "decal", wrap = true },
					{ kind = "decal", wrap = 6 },
				}),
				3
			)
			check.equal(VfxBudget.builds({ { kind = "decal", wrap = false } }), 0)
		end)
		test.case("a fracture's pieces are as many as its plan cuts, none when the plan is not known", function()
			local layers = { { kind = "debris", pieces = "slab" } }
			check.equal(VfxBudget.builds(layers), 0)
			check.equal(
				VfxBudget.builds(layers, function(name: string): number?
					return if name == "slab" then 14 else nil
				end),
				14
			)
			check.equal(
				VfxBudget.builds(layers, function(): number?
					return 500
				end),
				64
			)
		end)
		test.case("every version 3 play on a client is counted when its meshes were not made ahead", function()
			local kit = code("src/kit/Vfx.luau")
			-- (Vfx.play goes through Vfx.stage; an attach has its own stage)
			check.is_true(has(kit, "noteCold(name, preset, o.detail, o.scale) return VfxStage.play(preset, cframe, o)"))
			check.is_true(
				has(kit, "noteCold(name, preset, detailLevel, scale) local stage = VfxStage.play(preset, part.CFrame")
			)
			-- warm is what the pool HOLDS now, checked at every play (a review: it was a flag set once, and the pool kept 8)
			check.is_true(
				has(
					kit,
					"if not RunService:IsClient() or #(needsOf(preset, level)) == 0 or warmNow(preset, level, scale) then return end coldCount += 1"
				)
			)
			-- the avatar is waited for before a mesh is made at spawn, and a preset is warm only once its meshes are made
			check.is_true(has(kit, "while not avatarLoaded() and os.clock() - t0 < Vfx.SPAWN_WAIT do"))
			-- a play is early until a while AFTER the avatar loaded (the engine is still slow then: seen in Studio)
			check.is_true(has(kit, "return avatarSince == nil or os.clock() - avatarSince < Vfx.SPAWN_QUIET"))
			check.is_true(has(kit, "coldCount += 1 if tooEarly() then earlyCount += 1"))
			-- a warm-up raises what the pool keeps to what every preset warmed so far needs
			-- the same preset warmed again asks once (a game that warms on every respawn), others add up
			check.is_true(has(kit, "keepAsks[name] = math.max(keepAsks[name] or 0, total)"))
			check.is_true(has(kit, "noteCold(name, preset, o.detail, o.scale)"))
			-- an early play never plays invisible: a mesh layer draws a stand-in until its mesh is built, or for its whole
			-- life when it never is (an effect played as the avatar arrived drew no mesh for its whole life: Studio)
			local stage = code("src/kit/VfxStage.luau")
			check.is_true(has(stage, "local mp: BasePart? = part or standin"))
			-- the pieces' early stop is taken only when the rule says none lie in each other (the review: a step too short to
			-- push left them in each other, unchanged, and the stop was taken)
			check.is_true(
				has(
					stage,
					"local new, _, overlapped = debrisMeet(S, shapes, H, W, A, dt, g, moving[1].floor, moving[1].turn, scale) local same = not overlapped"
				)
			)
			check.is_true(has(code("kit/vfx/player/player.js"), "const same = !met[2] && live.every("))
			-- and its clock does not jump into its life on the first step of a long frame (seen in Studio)
			check.is_true(
				has(stage, "if not catching then dt, stepClock = VfxNet.stepBy(dt, os.clock(), stepClock) end")
			)
			check.is_true(has(stage, "native = b.native if standin then standin:Destroy() standin = nil end"))
			check.is_true(
				has(stage, 'if VfxMesh.SHAPES[el.shape or "ring"] then local p = plainPart("MeshStandIn", root)')
			)
		end)
		test.case("a forced size on drawings (step) is read once a drawing, in the game and in the player", function()
			-- (a review leftover, stage 13: a layer held on twos still changed size every frame)
			local stage = code("src/kit/VfxStage.luau")
			check.is_true(has(stage, "local drawing = if el.step then math.floor((t - at) * el.step) else nil"))
			check.is_true(
				has(stage, "if cam and (drawing == nil or drawing ~= forcedDrawing or forcedHeld == nil) then")
			)
			local player = code("kit/vfx/player/player.js")
			check.is_true(has(player, "forcedScale(p.viewAt(el.step ? at + age : t).pos.distanceTo("))
		end)
	end)

	test.suite("VfxBudget: a swarm's frame (the V3 doc, VFX stage F.1)", function()
		test.case("past 0.5 ms the stride grows, well under it it shrinks, on fours at most", function()
			check.equal(VfxBudget.swarmStride(0.9, 1), 2)
			check.equal(VfxBudget.swarmStride(0.9, 4), 4)
			check.equal(VfxBudget.swarmStride(0.4, 2), 2) -- (inside the band: kept, no flicker between strides)
			check.equal(VfxBudget.swarmStride(0.1, 3), 2)
			check.equal(VfxBudget.swarmStride(0.1, 1), 1)
			check.equal(VfxBudget.swarmStride(5, 99), 4)
		end)

		test.case("on a stride of k every part moves exactly once in k frames", function()
			for _, k in { 1, 2, 3, 4 } do
				local moved = {}
				for n = 1, k do
					for i = 1, 37 do
						if VfxBudget.swarmMoves(i, n, k) then
							moved[i] = (moved[i] or 0) + 1
						end
					end
				end
				for i = 1, 37 do
					check.equal(moved[i], 1)
				end
			end
		end)

		test.case("a swarm past 300 studs is left where it is", function()
			check.is_true(VfxBudget.swarmCulled(301))
			check.is_true(not VfxBudget.swarmCulled(300))
		end)

		test.case("the stage's swarm times itself, strides and culls", function()
			local stage = code("src/kit/VfxStage.luau")
			check.is_true(
				has(
					stage,
					"VfxBudget.swarmCulled((cam.CFrame.Position - worldPoint(el.point or { 0, 0, 0 })).Magnitude)"
				)
			)
			check.is_true(has(stage, "not VfxBudget.swarmMoves(i, frameN, stride)"))
			check.is_true(has(stage, "stride = VfxBudget.swarmStride((os.clock() - spent) * 1000, stride)"))
			check.is_true(has(stage, "math.clamp(t - q.moved, 0, 0.25)")) -- a part moves by all the time since it last did
		end)
	end)
end
