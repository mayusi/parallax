-- worldmeshes.spec.luau (kit) — a world's meshes at runtime (src/kit/WorldMeshes.luau and its rules,
-- WorldMeshRules.luau): what stands in for a mesh that is not there, and how a failed load is tried again.
-- The swapper itself runs here, as it is, on stand-ins for the engine's instances (the owner's limitations list,
-- W-R01 "missing meshes leave invisible, non-colliding placeholders" and W-R02 "a failure is cached for the
-- session"). What only Roblox can show - a real asset moderated, a real late load - is not claimed here.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Facade = require("../../lib/worldfacade")
local Rules = require("../../../src/kit/WorldMeshRules")
local World = require("../../lib/world")
local WorldMeshes = require("../../../src/kit/WorldMeshes")

-- an instance, as far as the swapper uses one: attributes, a parent that keeps its children, Clone, Destroy
local function inst(class: string, props: any?): any
	local raw: any = { ClassName = class, _attrs = {}, _children = {}, _parent = nil }
	for k, v in props or {} do
		raw[k] = v
	end
	local self: any = {}
	local methods: any = {}
	function methods.IsA(_, c: string): boolean
		return c == class or (c == "BasePart" and (class == "Part" or class == "MeshPart"))
	end
	function methods.GetAttribute(_, k: string): any
		return raw._attrs[k]
	end
	function methods.SetAttribute(_, k: string, v: any)
		raw._attrs[k] = v
	end
	function methods.GetAttributes(_): any
		return raw._attrs
	end
	function methods.GetChildren(_): { any }
		return table.clone(raw._children)
	end
	function methods.GetDescendants(_): { any }
		local out = {}
		local function walk(node: any)
			for _, c in node:GetChildren() do
				table.insert(out, c)
				walk(c)
			end
		end
		walk(self)
		return out
	end
	function methods.FindFirstChild(_, name: string): any
		for _, c in raw._children do
			if c.Name == name then
				return c
			end
		end
		return nil
	end
	function methods.Destroy(_)
		self.Parent = nil
		raw.destroyed = true
	end
	function methods.Clone(_): any
		local copy = inst(class, {})
		for k, v in raw do
			if k ~= "_attrs" and k ~= "_children" and k ~= "_parent" then
				(copy :: any)[k] = v
			end
		end
		for k, v in raw._attrs do
			copy:SetAttribute(k, v)
		end
		return copy
	end
	return setmetatable(self, {
		__index = function(_, k)
			if k == "Parent" then
				return raw._parent
			end
			return methods[k] or raw[k]
		end,
		__newindex = function(_, k, v)
			if k == "Parent" then
				local old = raw._parent
				if old then
					local list = old:_kids()
					local at = table.find(list, self)
					if at then
						table.remove(list, at)
					end
				end
				raw._parent = v
				if v then
					table.insert(v:_kids(), self)
				end
			else
				raw[k] = v
			end
		end,
	}),
		nil
end

-- (a parent's own list of children, for the Parent setter above)
local function withKids(node: any): any
	local kids = {}
	rawset(node, "_kids", function()
		return kids
	end)
	rawset(node, "GetChildren", function()
		return table.clone(kids)
	end)
	return node
end

local function folder(name: string, parent: any?): any
	local f = withKids((inst("Folder", { Name = name })))
	if parent then
		f.Parent = parent
	end
	return f
end

-- a placeholder as the compiler leaves it: unseen, not solid
local function placeholder(parent: any, mesh: string, attrs: any): any
	local p = withKids((inst("Part", {
		Name = "KitMesh",
		Transparency = 1,
		CanCollide = false,
		CanQuery = false,
		Size = { 4, 6, 4 },
		CFrame = `at {mesh}`,
		Material = "Slate",
		Color = "grey",
	})))
	p:SetAttribute("KitMesh", mesh)
	for k, v in attrs do
		p:SetAttribute(k, v)
	end
	p.Parent = parent
	return p
end

local function hidden(parent: any, name: string, key: string): any
	local p = withKids((inst("Part", { Name = name, Transparency = 1, CanCollide = true, CanQuery = true })))
	p:SetAttribute("KitBlockout", key)
	p.Parent = parent
	return p
end

-- the engine, stood in for: a clock the test moves, loads that fail as told, background work run by hand
local function engine(root: any, fails: { [string]: number }?)
	local e: any = { clock = 0, calls = {}, warned = {}, jobs = {}, fails = fails or {} }
	e.deps = {
		root = function()
			return e.root
		end,
		create = function(meshId: string)
			e.calls[meshId] = (e.calls[meshId] or 0) + 1
			local left = e.fails[meshId] or 0
			if left > 0 then
				e.fails[meshId] = left - 1
				error(`HTTP 429 for {meshId}`)
			end
			return withKids((inst("MeshPart", { MeshId = meshId })))
		end,
		now = function()
			return e.clock
		end,
		wait = function(seconds: number?)
			e.clock += seconds or 0.03
			-- (in the background work a wait hands the engine back, as task.wait does: one resume is one step)
			if e.inJob and coroutine.isyieldable() then
				coroutine.yield()
			end
		end,
		spawn = function(fn: () -> ())
			table.insert(
				e.jobs,
				coroutine.create(function()
					e.inJob = true
					fn()
					e.inJob = false
				end)
			)
		end,
		warn = function(text: string)
			table.insert(e.warned, text)
		end,
	}
	e.root = root
	return e
end

local function world(): (any, any)
	local workspace = folder("Workspace")
	local root = folder("KitWorld", workspace)
	return root, workspace
end

local function find(root: any, name: string): { any }
	local out = {}
	for _, d in root:GetDescendants() do
		if d.Name == name then
			table.insert(out, d)
		end
	end
	return out
end

return function()
	test.suite("World meshes: the rules of a mesh that is not there", function()
		test.case("a solid thing stands in as its box; what dresses a building shows the building's walls", function()
			local rock = Rules.standIn({ collide = true })
			check.equal(rock.show, true)
			check.equal(rock.collide, true)
			check.equal(rock.blockout, nil)
			local leaves = Rules.standIn({ collide = false })
			check.equal(leaves.show, false)
			check.equal(leaves.collide, false)
			local skin = Rules.standIn({ collide = false, dress = "build[2].building" })
			check.equal(skin.show, false)
			check.equal(skin.collide, false)
			check.equal(skin.blockout, "build[2].building")
			-- (a dress is never solid itself, even if its placeholder said so: its building's walls are)
			check.equal(Rules.standIn({ collide = true, dress = "h" }).collide, false)
			check.equal(Rules.standIn({ collide = true, dress = "" }).show, true)
			-- a building is dressed only when every one of its meshes is there
			check.equal(Rules.dressed({ "have", "have" }), true)
			check.equal(Rules.dressed({ "have", "wait" }), false)
			check.equal(Rules.dressed({ "missing" }), false)
			check.equal(Rules.dressed({}), false)
			check.equal(Rules.ready({ pending = 0 }), true)
			check.equal(Rules.ready({ pending = 2 }), false)
		end)

		test.case(
			"a failed load is tried again: 3 tries a round, a pause between rounds, 4 rounds, then given up",
			function()
				local s = Rules.new()
				check.equal(Rules.attempt(s, 0), "try")
				-- the whole session written out: when each try comes, by the rules' own numbers
				local now, tries, waits = 0, 0, {}
				while true do
					local what, left = Rules.attempt(s, now)
					if what == "try" then
						tries += 1
						Rules.failed(s, now)
					elseif what == "wait" then
						table.insert(waits, left)
						-- (a moment before the wait is over it is still a wait)
						check.equal(Rules.attempt(s, now + (left :: number) - 0.01), "wait")
						now += left :: number
					else
						check.equal(what, "given up")
						break
					end
					check.truthy(tries <= 50)
				end
				check.equal(tries, 12)
				check.equal(table.concat(waits, " "), "1 3 30 1 3 30 1 3 30 1 3")
				check.equal(Rules.attempt(s, now + 100000), "given up") -- (for good)
				-- a load that works on its second try is had, whatever came before
				local t = Rules.new()
				Rules.failed(t, 5)
				check.equal(Rules.attempt(t, 5.5), "wait")
				check.equal(Rules.attempt(t, 6), "try")
				Rules.loaded(t)
				check.equal(Rules.attempt(t, 6), "have")
				check.equal(Rules.attempt(t, 0), "have")
			end
		)
	end)

	test.suite("World meshes: the swapper, run on stand-ins for the engine", function()
		test.case("a mesh that loads takes its placeholder's place, as before", function()
			WorldMeshes._reset()
			local root = world()
			local a =
				placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = true, TextureId = "rbxassetid://9" })
			local b = placeholder(root, "oak", { MeshId = "rbxassetid://2", Collide = false, KitAudioPass = true })
			local c = placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = true })
			local e = engine(root)
			local made, notThere, missing = WorldMeshes.swapAll(e.deps)
			check.equal(made, 3)
			check.equal(notThere, 0)
			check.equal(missing, 0)
			check.equal(e.calls["rbxassetid://1"], 1) -- (one load an id, then clones)
			check.equal(#find(root, "KitMesh"), 0)
			check.truthy(a.destroyed and b.destroyed and c.destroyed)
			local rocks, oak = find(root, "rock_a"), find(root, "oak")[1]
			check.equal(#rocks, 2)
			check.equal(rocks[1].ClassName, "MeshPart")
			check.equal(rocks[1].CanCollide, true)
			check.equal(rocks[1].TextureID, "rbxassetid://9")
			check.equal(rocks[1].CFrame, "at rock_a")
			check.equal(rocks[1].Size, a.Size) -- (the placeholder's own box: a mesh comes out at ITS size)
			check.equal(rocks[1].Anchored, true)
			check.equal(rocks[2].Material, "Slate") -- (no texture: the palette's material)
			check.equal(oak.CanCollide, false)
			check.equal(oak:GetAttribute("KitAudioPass"), true)
			check.equal(root:GetAttribute("KitMeshesReady"), true)
			check.equal(root:GetAttribute("KitMeshesMade"), 3)
			check.equal(#e.jobs, 0) -- (nothing to try again: no background work)
			check.equal(WorldMeshes.ready(e.deps), true)
		end)

		test.case(
			"W-R01: a solid mesh that was never uploaded is a seen, solid box - not a hole in the world",
			function()
				WorldMeshes._reset()
				local root = world()
				local cliff = placeholder(root, "cliff", { Collide = true }) -- (no MeshId: not uploaded)
				local fern = placeholder(root, "fern", { Collide = false })
				local e = engine(root)
				local made, notThere, missing = WorldMeshes.swapAll(e.deps)
				check.equal(made, 0)
				check.equal(notThere, 2)
				check.equal(missing, 2)
				-- the cliff: its own box, seen and solid (before: Transparency 1, CanCollide false - you walked through)
				check.equal(cliff.Parent, root)
				check.equal(cliff.Transparency, 0)
				check.equal(cliff.CanCollide, true)
				check.equal(cliff.CanQuery, true)
				check.equal(cliff:GetAttribute("KitStandIn"), true)
				-- the fern was never an obstacle: unseen, as it was
				check.equal(fern.Transparency, 1)
				check.equal(fern.CanCollide, false)
				check.equal(fern.CanQuery, false) -- (a ray passes what a body passes)
				check.equal(fern:GetAttribute("KitStandIn"), nil)
				check.equal(root:GetAttribute("KitMeshesMissing"), 2)
				check.equal(root:GetAttribute("KitMeshesReady"), true) -- (nothing left to try: settled)
				check.equal(#e.jobs, 0)
			end
		)

		test.case(
			"W-R01: a house whose skin is not there shows its own walls; with its skin, they are hidden",
			function()
				WorldMeshes._reset()
				local root = world()
				local house = folder("House", root)
				local wall, roof = hidden(house, "Wall", "h1"), hidden(house, "RoofN", "h1")
				local other = hidden(house, "Wall", "h2")
				local skin = placeholder(house, "gc_house", { Collide = false, KitDress = "h1" })
				local skin2 =
					placeholder(house, "gc_house", { MeshId = "rbxassetid://5", Collide = false, KitDress = "h2" })
				local e = engine(root)
				WorldMeshes.swapAll(e.deps)
				check.equal(wall.Transparency, 0) -- (h1: no mesh - you see the walls you bump into)
				check.equal(roof.Transparency, 0)
				check.equal(wall.CanCollide, true)
				check.equal(skin.Transparency, 1) -- (the dress itself shows nothing)
				check.equal(skin.Parent, house)
				check.equal(other.Transparency, 1) -- (h2: dressed)
				check.truthy(skin2.destroyed)
				check.equal(#find(root, "gc_house"), 1)
			end
		)

		test.case(
			"W-R01: a facade is whole or the house shows its walls - one module missing is not half a house",
			function()
				WorldMeshes._reset()
				local root = world()
				local house = folder("House", root)
				local walls = { hidden(house, "Wall", "h"), hidden(house, "Sill", "h"), hidden(house, "RoofS", "h") }
				local m1 =
					placeholder(house, "tw_wall_14", { MeshId = "rbxassetid://1", Collide = false, KitDress = "h" })
				local m2 =
					placeholder(house, "tw_window_14", { MeshId = "rbxassetid://2", Collide = false, KitDress = "h" })
				local m3 = placeholder(house, "tw_roof", { MeshId = "rbxassetid://3", Collide = false, KitDress = "h" })
				local e = engine(root, { ["rbxassetid://3"] = 2 }) -- (the roof fails twice, then loads)
				local made, notThere = WorldMeshes.swapAll(e.deps)
				check.equal(made, 0)
				check.equal(notThere, 3) -- (the two that loaded wait for the third)
				for _, w in walls do
					check.equal(w.Transparency, 0)
				end
				check.truthy(m1.Parent == house and m2.Parent == house and m3.Parent == house)
				check.equal(root:GetAttribute("KitMeshesReady"), false)
				check.equal(#e.jobs, 1) -- (the background work that tries again)
				-- the background work: a pass a second; the roof loads on its third try (after 1 s and 3 s more)
				local job = e.jobs[1]
				local passes = 0
				while coroutine.status(job) ~= "dead" do
					local ok, err = coroutine.resume(job)
					check.truthy(ok, err)
					passes += 1
					check.truthy(passes < 50)
					if coroutine.status(job) ~= "dead" then
						-- between two steps of it: the house in its own walls, nothing half placed
						for _, w in walls do
							check.equal(w.Transparency, 0)
						end
						check.equal(#find(root, "tw_wall_14"), 0)
					end
				end
				check.truthy(passes >= 4 and passes <= 8) -- (a pass a second until the roof's third try, 4 s in)
				check.equal(e.calls["rbxassetid://3"], 3)
				check.equal(e.calls["rbxassetid://1"], 1) -- (what loaded is not loaded again)
				check.truthy(e.clock >= 4 and e.clock < 8)
				for _, w in walls do
					check.equal(w.Transparency, 1) -- (dressed: its walls hidden again, still solid)
					check.equal(w.CanCollide, true)
				end
				check.truthy(m1.destroyed and m2.destroyed and m3.destroyed)
				check.equal(#find(root, "tw_roof"), 1)
				check.equal(root:GetAttribute("KitMeshesReady"), true)
				check.equal(root:GetAttribute("KitMeshesMade"), 3)
				check.equal(root:GetAttribute("KitMeshesPending"), 0)
			end
		)

		test.case("a building that can never be whole is SETTLED: its walls shown, no work without end", function()
			-- one module never uploaded, the other two there (a fresh reader: the two counted as waiting for ever,
			-- so the world was never ready and the whole map was walked every second for the session)
			WorldMeshes._reset()
			local root = world()
			local house = folder("House", root)
			local wall = hidden(house, "Wall", "h")
			local m1 = placeholder(house, "tw_wall_14", { MeshId = "rbxassetid://1", Collide = false, KitDress = "h" })
			placeholder(house, "tw_chimney", { Collide = false, KitDress = "h" }) -- (no MeshId)
			local e = engine(root)
			local made, notThere, missing = WorldMeshes.swapAll(e.deps)
			check.equal(made, 0)
			check.equal(notThere, 2)
			check.equal(missing, 1)
			check.equal(wall.Transparency, 0)
			check.equal(m1.Parent, house)
			check.equal(#e.jobs, 0)
			check.equal(root:GetAttribute("KitMeshesReady"), true)
			check.equal(root:GetAttribute("KitMeshesHeld"), 1)
			check.equal(root:GetAttribute("KitMeshesPending"), 0)
			-- one module given up after its 12 tries: the background work ENDS, the house stays in its walls
			WorldMeshes._reset()
			local root2 = world()
			local house2 = folder("House", root2)
			local wall2 = hidden(house2, "Wall", "h")
			placeholder(house2, "tw_wall_14", { MeshId = "rbxassetid://1", Collide = false, KitDress = "h" })
			placeholder(house2, "tw_roof", { MeshId = "rbxassetid://3", Collide = false, KitDress = "h" })
			local e2 = engine(root2, { ["rbxassetid://3"] = 1000 })
			WorldMeshes.swapAll(e2.deps)
			check.equal(root2:GetAttribute("KitMeshesReady"), false)
			local steps = 0
			while coroutine.status(e2.jobs[1]) ~= "dead" do
				coroutine.resume(e2.jobs[1])
				steps += 1
				check.truthy(steps < 400)
			end
			check.equal(e2.calls["rbxassetid://3"], 12)
			check.equal(wall2.Transparency, 0)
			check.equal(root2:GetAttribute("KitMeshesReady"), true)
			check.equal(root2:GetAttribute("KitMeshesFailed"), 1)
			check.equal(root2:GetAttribute("KitMeshesHeld"), 1)
			check.equal(#find(root2, "tw_wall_14"), 0)
		end)

		test.case(
			"a tree's mesh not there: its trunk is seen; a world put in after another gets its own work",
			function()
				-- a mesh tree: the compiler's unseen trunk you bump into names the tree, the tree's mesh names it too
				WorldMeshes._reset()
				local root = world()
				local trunk = hidden(root, "TrunkCollider", "tree#4")
				local tree = placeholder(root, "oak", { Collide = false, KitDress = "tree#4" })
				local e = engine(root)
				WorldMeshes.swapAll(e.deps)
				check.equal(trunk.Transparency, 0) -- (a pole you can see, not one you walk into unseen)
				check.equal(tree.Transparency, 1)
				-- one mesh there at once, the other after a retry: both are counted as made
				WorldMeshes._reset()
				local rootM = world()
				placeholder(rootM, "rock", { MeshId = "rbxassetid://1", Collide = true })
				placeholder(rootM, "crag", { MeshId = "rbxassetid://2", Collide = true })
				local eM = engine(rootM, { ["rbxassetid://2"] = 1 })
				check.equal((WorldMeshes.swapAll(eM.deps)), 1)
				while coroutine.status(eM.jobs[1]) ~= "dead" do
					coroutine.resume(eM.jobs[1])
				end
				check.equal(rootM:GetAttribute("KitMeshesMade"), 2)
				-- world A still trying; A is taken down and world B put in: B's mesh is tried again and placed
				WorldMeshes._reset()
				local rootA = world()
				placeholder(rootA, "tower", { MeshId = "rbxassetid://3", Collide = true })
				local eA = engine(rootA, { ["rbxassetid://3"] = 100 })
				WorldMeshes.swapAll(eA.deps)
				check.equal(#eA.jobs, 1)
				rootA.Parent = nil
				WorldMeshes.stop()
				WorldMeshes._reset()
				local rootB = world()
				local b = placeholder(rootB, "keep", { MeshId = "rbxassetid://9", Collide = true })
				local eB = engine(rootB, { ["rbxassetid://9"] = 1 })
				WorldMeshes.swapAll(eB.deps)
				check.equal(#eB.jobs, 1) -- (it had none: the flag of A's work was still up)
				while coroutine.status(eB.jobs[1]) ~= "dead" do
					coroutine.resume(eB.jobs[1])
				end
				check.truthy(b.destroyed)
				check.equal(#find(rootB, "keep"), 1)
				check.equal(rootB:GetAttribute("KitMeshesReady"), true)
				while coroutine.status(eA.jobs[1]) ~= "dead" do
					coroutine.resume(eA.jobs[1])
				end
				check.equal(eA.calls["rbxassetid://3"], 1) -- (A's work ended without another try)
				-- swapAll called twice on one world: the first call's work ends, one mesh is made once
				WorldMeshes._reset()
				local rootC = world()
				placeholder(rootC, "gate", { MeshId = "rbxassetid://5", Collide = true })
				local eC = engine(rootC, { ["rbxassetid://5"] = 1 })
				WorldMeshes.swapAll(eC.deps)
				WorldMeshes.swapAll(eC.deps)
				check.equal(#eC.jobs, 2)
				check.equal(eC.calls["rbxassetid://5"], 1)
				-- the first call's work alone, to its end: it does nothing more (the second call's is the live one)
				while coroutine.status(eC.jobs[1]) ~= "dead" do
					coroutine.resume(eC.jobs[1])
				end
				check.equal(eC.calls["rbxassetid://5"], 1)
				check.equal(#find(rootC, "gate"), 0)
				while coroutine.status(eC.jobs[2]) ~= "dead" do
					coroutine.resume(eC.jobs[2])
				end
				check.equal(#find(rootC, "gate"), 1)
				check.equal(eC.calls["rbxassetid://5"], 2)
			end
		)

		test.case(
			"W-R02: a load that fails once is tried again, and the mesh then takes its stand-in's place",
			function()
				WorldMeshes._reset()
				local root = world()
				local a = placeholder(root, "rock", { MeshId = "rbxassetid://7", Collide = true })
				local b = placeholder(root, "rock", { MeshId = "rbxassetid://7", Collide = true })
				local e = engine(root, { ["rbxassetid://7"] = 1 })
				local made, notThere = WorldMeshes.swapAll(e.deps)
				check.equal(made, 0)
				check.equal(notThere, 2)
				check.equal(e.calls["rbxassetid://7"], 1) -- (one failed call, not one a placeholder)
				-- meanwhile: both rocks are solid boxes
				check.equal(a.CanCollide, true)
				check.equal(a.Transparency, 0)
				check.equal(#e.warned, 1)
				check.truthy(string.find(e.warned[1], "will be tried again", 1, true))
				-- (before these rules the id was cached as failed for the whole session: no job, no second call)
				check.equal(#e.jobs, 1)
				coroutine.resume(e.jobs[1])
				while coroutine.status(e.jobs[1]) ~= "dead" do
					coroutine.resume(e.jobs[1])
				end
				check.equal(e.calls["rbxassetid://7"], 2)
				check.truthy(a.destroyed and b.destroyed)
				local rocks = find(root, "rock")
				check.equal(#rocks, 2)
				check.equal(rocks[1].ClassName, "MeshPart")
				check.equal(rocks[1].CanCollide, true) -- (the mesh is solid as its stand-in was)
				check.equal(root:GetAttribute("KitMeshesReady"), true)
			end
		)

		test.case(
			"W-R02: a mesh that never loads is given up after 12 tries, its stand-in kept, the world settled",
			function()
				WorldMeshes._reset()
				local root = world()
				local a = placeholder(root, "wall", { MeshId = "rbxassetid://8", Collide = true })
				local e = engine(root, { ["rbxassetid://8"] = 1000 })
				WorldMeshes.swapAll(e.deps)
				local steps = 0
				while coroutine.status(e.jobs[1]) ~= "dead" do
					coroutine.resume(e.jobs[1])
					steps += 1
					check.truthy(steps < 400)
				end
				check.equal(e.calls["rbxassetid://8"], 12)
				check.equal(a.Parent, root)
				check.equal(a.CanCollide, true)
				check.equal(a.Transparency, 0)
				check.equal(root:GetAttribute("KitMeshesFailed"), 1)
				check.equal(root:GetAttribute("KitMeshesPending"), 0)
				check.equal(root:GetAttribute("KitMeshesReady"), true)
				check.truthy(string.find(e.warned[#e.warned], "given up for this session", 1, true))
				check.truthy(e.clock > 90 and e.clock < 140) -- (three pauses of 30 s between the four rounds)
			end
		)

		test.case("W-R02: a late load puts nothing back - a placeholder taken out, a world taken down", function()
			-- a placeholder destroyed while its mesh was still failing: when the mesh loads, only the other one is made
			WorldMeshes._reset()
			local root = world()
			local gone = placeholder(root, "crate", { MeshId = "rbxassetid://4", Collide = true })
			local kept = placeholder(root, "crate", { MeshId = "rbxassetid://4", Collide = true })
			local e = engine(root, { ["rbxassetid://4"] = 1 })
			WorldMeshes.swapAll(e.deps)
			gone:Destroy() -- (the game broke the crate)
			while coroutine.status(e.jobs[1]) ~= "dead" do
				coroutine.resume(e.jobs[1])
			end
			check.equal(#find(root, "crate"), 1)
			check.truthy(kept.destroyed)
			-- taken out DURING the load itself (the load yields): nothing is made for it
			WorldMeshes._reset()
			local root2 = world()
			local p = placeholder(root2, "barrel", { MeshId = "rbxassetid://6", Collide = true })
			local e2 = engine(root2)
			local create = e2.deps.create
			e2.deps.create = function(meshId: string)
				p:Destroy()
				return create(meshId)
			end
			local made = WorldMeshes.swapAll(e2.deps)
			check.equal(made, 0)
			check.equal(#find(root2, "barrel"), 0)
			-- one module of a house taken out during the load of the other: the house is NOT dressed with what is
			-- left (its walls stay shown, the module that loaded stays a placeholder)
			WorldMeshes._reset()
			local rootH = world()
			local wallH = hidden(rootH, "Wall", "h")
			local keptH =
				placeholder(rootH, "tw_wall_14", { MeshId = "rbxassetid://1", Collide = false, KitDress = "h" })
			local goneH = placeholder(rootH, "tw_roof", { MeshId = "rbxassetid://2", Collide = false, KitDress = "h" })
			local eH = engine(rootH)
			local createH = eH.deps.create
			eH.deps.create = function(meshId: string)
				if meshId == "rbxassetid://2" then
					goneH:Destroy()
				end
				return createH(meshId)
			end
			check.equal((WorldMeshes.swapAll(eH.deps)), 0)
			check.equal(wallH.Transparency, 0)
			check.equal(keptH.Parent, rootH)
			check.equal(#find(rootH, "tw_wall_14"), 0)
			-- the world taken down while a mesh is still being tried: the background work ends, nothing is made
			WorldMeshes._reset()
			local root3, workspace3 = world()
			placeholder(root3, "tower", { MeshId = "rbxassetid://3", Collide = true })
			local e3 = engine(root3, { ["rbxassetid://3"] = 1 })
			WorldMeshes.swapAll(e3.deps)
			root3.Parent = nil
			check.equal(workspace3:FindFirstChild("KitWorld"), nil)
			local n = 0
			while coroutine.status(e3.jobs[1]) ~= "dead" do
				coroutine.resume(e3.jobs[1])
				n += 1
				check.truthy(n < 5)
			end
			check.equal(e3.calls["rbxassetid://3"], 1)
			check.equal(#find(root3, "tower"), 0)
			-- ... and stop() ends it too
			WorldMeshes._reset()
			local root4 = world()
			placeholder(root4, "tower", { MeshId = "rbxassetid://3", Collide = true })
			local e4 = engine(root4, { ["rbxassetid://3"] = 5 })
			WorldMeshes.swapAll(e4.deps)
			WorldMeshes.stop()
			while coroutine.status(e4.jobs[1]) ~= "dead" do
				coroutine.resume(e4.jobs[1])
			end
			check.equal(e4.calls["rbxassetid://3"], 1)
		end)

		test.case("no KitWorld: nothing to do", function()
			WorldMeshes._reset()
			local e = engine(nil)
			local made, notThere, missing = WorldMeshes.swapAll(e.deps)
			check.equal(made + notThere + missing, 0)
			check.equal(WorldMeshes.ready(e.deps), false)
		end)
	end)

	test.suite("World meshes: the compiler tags what a dress hides", function()
		local PALETTE = {
			plaster = { material = "Concrete", color = { 150, 140, 124 } },
			slate = { material = "Slate", color = { 58, 60, 68 } },
		}
		local function registry(recipes: { any }): { [string]: any }
			local reg = {}
			for _, r in recipes do
				reg[r.name] = {
					kind = r.kind,
					module = r.module,
					floorHeight = r.floorHeight,
					gap = r.gap,
					size = r.size,
					min = { -r.size[1] / 2, 0, -r.size[3] / 2 },
				}
			end
			return reg
		end
		local function house(more: any): any
			local b: any = {
				name = "House",
				center = { 0, 0, 0 },
				size = { 23, 24 },
				floors = 2,
				floorHeight = 14,
				thickness = 1,
				mat = "plaster",
				roof = "gable",
				roofMat = "slate",
				door = { side = "S", width = 5, height = 8.5 },
				windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E", "N", "W" } },
			}
			for k, v in more do
				b[k] = v
			end
			return b
		end

		-- CORNER QUOINS (LIMITATIONS_FIXES_V3.md stage B.1: "corner quoins as instanced strips - never stripped"): the
		-- skin names its strip; one strip a corner a storey, all one mesh, standing on the skin's outer corners
		test.case("a skinned house wears its corner quoins: one strip at each corner of each storey", function()
			local function skinReg(quoinMade: boolean): any
				local reg: any = {
					whole = {
						kind = "gothic_house",
						size = { 25, 40, 26 },
						min = { -12.5, 0, -13 },
						footprint = { 23, 24 },
						floors = 2,
						floorHeight = 14,
						windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E", "N", "W" } },
						door = { side = "S", width = 5, height = 8.5 },
						quoins = "q",
					},
				}
				if quoinMade then
					-- (as kit world meshes records it: the strip's corner at its origin, its arms along +x and -z)
					reg.q = {
						kind = "gothic_quoin",
						size = { 3.15, 14, 3.15 },
						min = { -0.15, 0, -3 },
						quoin = { height = 14, proj = 0.15 },
					}
				end
				return reg
			end
			local _, parts, issues = World.compile({
				name = "T",
				palette = PALETTE,
				scale = "r6",
				build = { { building = house({ skin = "whole", center = { 10, 0, -6 } }) } },
			}, { meshes = skinReg(true) })
			for _, i in issues do
				check.truthy(i.severity ~= "error", i.message)
			end
			local strips, dress = {}, nil
			for _, p in parts do
				if p.mesh == "q" then
					table.insert(strips, p)
				elseif p.mesh == "whole" then
					dress = (p.attributes or {}).KitDress
				end
			end
			check.equal(#strips, 8) -- (4 corners x 2 storeys)
			-- each stands on a corner of the skin's outer faces (the building's box + World.QUOIN_OUT), at a storey's
			-- foot, its arms reaching back along the two faces; and dresses the same building as the skin
			local hx, hz = 23 / 2 + World.QUOIN_OUT, 24 / 2 + World.QUOIN_OUT
			local seen: { [string]: number } = {}
			for _, p in strips do
				check.equal((p.attributes or {}).KitDress, dress)
				local cx, cz = p.pos[1] - 10, p.pos[3] + 6
				-- the strip's middle lies 3.15 / 2 - 0.15 = 1.425 in from its corner along both faces
				local sx = if cx < 0 then -1 else 1
				local sz = if cz < 0 then -1 else 1
				check.truthy(math.abs(math.abs(cx) - (hx - 1.425)) < 1e-6, `x {cx}`)
				check.truthy(math.abs(math.abs(cz) - (hz - 1.425)) < 1e-6, `z {cz}`)
				local foot = p.pos[2] - 7
				check.truthy(math.abs(foot) < 1e-6 or math.abs(foot - 14) < 1e-6, `foot {foot}`)
				local key = `{sx},{sz}`
				seen[key] = (seen[key] or 0) + 1
			end
			check.equal(seen["-1,1"], 2)
			check.equal(seen["1,1"], 2)
			check.equal(seen["1,-1"], 2)
			check.equal(seen["-1,-1"], 2)
			-- two houses side by side, half a stud apart: the corners that face each other are butted (no free corner,
			-- no quoins wedged between), the free corners keep theirs
			local _, pair = World.compile({
				name = "T",
				palette = PALETTE,
				scale = "r6",
				build = {
					{ building = house({ skin = "whole", name = "A" }) },
					{ building = house({ skin = "whole", name = "B", center = { -23.5, 0, 0 } }) },
				},
			}, { meshes = skinReg(true) })
			local kept: { [string]: number } = {}
			local total = 0
			for _, p in pair do
				if p.mesh == "q" then
					total += 1
					local side = if p.pos[1] > -11.75 then "A" else "B"
					local inner = (side == "A" and p.pos[1] < 0) or (side == "B" and p.pos[1] > -23.5)
					local key = side .. (if inner then " inner" else " outer")
					kept[key] = (kept[key] or 0) + 1
				end
			end
			check.equal(total, 8) -- (16 placed, the 8 on the four facing corners taken out)
			check.equal(kept["A outer"], 4)
			check.equal(kept["B outer"], 4)
			check.equal(kept["A inner"], nil)
			check.equal(kept["B inner"], nil)
			-- a TURNED wall near a corner: its axis-aligned box covers the corner, the wall itself stands 9 studs off
			-- it - the corner is free and keeps its quoins (it lost them when the box was asked)
			local _, turned = World.compile({
				name = "T",
				palette = PALETTE,
				scale = "r6",
				build = {
					{ building = house({ skin = "whole", name = "A" }) },
					{
						part = {
							name = "Wall",
							size = { 20, 10, 1 },
							pos = { -18, 5, 5 },
							rot = { 0, 45, 0 },
							mat = "plaster",
						},
					},
				},
			}, { meshes = skinReg(true) })
			local sw = 0
			for _, p in turned do
				if p.mesh == "q" and p.pos[1] < 0 and p.pos[3] > 0 then
					sw += 1
				end
			end
			check.equal(sw, 2) -- (the south-west corner's two storeys)
			-- a strip that is not made is said, never quietly left off
			local _, _, unmade = World.compile({
				name = "T",
				palette = PALETTE,
				scale = "r6",
				build = { { building = house({ skin = "whole" }) } },
			}, { meshes = skinReg(false) })
			local said = false
			for _, i in unmade do
				said = said or (i.severity == "error" and string.find(i.message, "corner quoins", 1, true) ~= nil)
			end
			check.is_true(said)
		end)

		test.case("every hidden wall and roof of a dressed building names it, as each of its meshes does", function()
			local reg = registry(Facade.kit({
				prefix = "fx",
				floorHeights = { 14 },
				thickness = 1.2,
				door = { width = 5, height = 8.5 },
				window = { width = 4, height = 10.5, sill = 3.5 },
			}))
			reg.whole = {
				kind = "gothic_house",
				size = { 25, 40, 26 },
				min = { -12.5, 0, -13 },
				footprint = { 23, 24 },
				floors = 2,
				floorHeight = 14,
				windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E", "N", "W" } },
				door = { side = "S", width = 5, height = 8.5 },
			}
			for _, dress in { { facade = "fx", seed = 2 }, { skin = "whole" } } do
				local _, parts, issues = World.compile({
					name = "T",
					palette = PALETTE,
					scale = "r6",
					build = {
						{ building = house(dress) },
						{ building = house({ center = { 80, 0, 0 }, name = "Plain" }) },
					},
				}, { meshes = reg })
				for _, i in issues do
					check.truthy(i.severity ~= "error", i.message)
				end
				local keys: { [string]: { hidden: number, meshes: number } } = {}
				for _, p in parts do
					local a = p.attributes or {}
					if p.mesh then
						check.truthy(type(a.KitDress) == "string" and a.KitDress ~= "")
						keys[a.KitDress] = keys[a.KitDress] or { hidden = 0, meshes = 0 }
						keys[a.KitDress].meshes += 1
						check.equal(a.KitBlockout, nil)
					elseif p.transparency == 1 then
						-- every unseen part of the world is a dressed building's, and says whose
						check.truthy(type(a.KitBlockout) == "string")
						keys[a.KitBlockout] = keys[a.KitBlockout] or { hidden = 0, meshes = 0 }
						keys[a.KitBlockout].hidden += 1
						check.truthy(
							p.name == "Wall"
								or p.name == "Sill"
								or p.name == "Lintel"
								or p.name == "RoofN"
								or p.name == "RoofS"
						)
					else
						check.equal(a.KitBlockout, nil)
					end
				end
				-- one dressed building, one key, with walls to show and meshes to wait for; the plain one has none
				local n = 0
				for _, k in keys do
					n += 1
					check.truthy(k.hidden >= 20)
					check.truthy(k.meshes >= 1)
				end
				check.equal(n, 1)
			end
		end)
		test.case("a mesh tree's trunk, a wall of modules and a mesh tower's top each name what hides them", function()
			local reg = {
				oak = { kind = "tree", size = { 14, 30, 14 }, min = { -7, 0, -7 }, foliage = true },
				cw = { kind = "wall", size = { 12, 16, 3 }, min = { 0, 0, 0 } },
				keep = { kind = "tower", size = { 20, 30, 20 }, min = { -10, 0, -10 } },
				rock = { kind = "rock", size = { 6, 4, 6 }, min = { -3, 0, -3 } },
			}
			local _, parts, issues = World.compile({
				name = "T",
				palette = PALETTE,
				scale = "r6",
				build = {
					{ tree = { mesh = "oak", pos = { 0, 0, 0 }, height = 30, trunk = "plaster", leaves = "slate" } },
					{ tree = { mesh = "oak", pos = { 40, 0, 0 }, height = 30, trunk = "plaster", leaves = "slate" } },
					{
						forest = {
							center = { 0, 0, -200 },
							area = { 120, 120 },
							count = 3,
							seed = 4,
							meshes = { "oak" },
							trunk = "plaster",
							leaves = "slate",
						},
					},
					{
						wall = {
							from = { 0, 60 },
							to = { 48, 60 },
							height = 16,
							thickness = 3,
							mat = "plaster",
							mesh = "cw",
						},
					},
					{ tower = { center = { 100, 0, 0 }, radius = 9, height = 30, mat = "plaster", mesh = "keep" } },
					{ mesh = { mesh = "rock", pos = { 0, 0, 100 }, collide = true, mat = "plaster" } },
					{ wall = { from = { 0, 140 }, to = { 20, 140 }, height = 8, thickness = 1, mat = "plaster" } },
				},
			}, { meshes = reg })
			for _, i in issues do
				check.truthy(i.severity ~= "error", i.message)
			end
			local hides: { [string]: { string } } = {}
			local dresses: { [string]: { string } } = {}
			local rocks = 0
			for _, p in parts do
				local a = p.attributes or {}
				if p.mesh then
					if p.mesh == "rock" then
						rocks += 1
						check.equal(a.KitDress, nil) -- (a rock hides nothing: it is its own stand-in)
						check.equal(a.Collide, true)
					else
						check.truthy(type(a.KitDress) == "string")
						dresses[a.KitDress] = dresses[a.KitDress] or {}
						table.insert(dresses[a.KitDress], p.mesh)
					end
				elseif p.transparency == 1 then
					-- NOTHING unseen is left unnamed: every hidden part says which mesh's absence shows it
					check.truthy(type(a.KitBlockout) == "string", p.name)
					hides[a.KitBlockout] = hides[a.KitBlockout] or {}
					table.insert(hides[a.KitBlockout], p.name)
				else
					check.equal(a.KitBlockout, nil)
				end
			end
			check.equal(rocks, 1)
			local trees, walls, towers = 0, 0, 0
			for key, names in hides do
				check.truthy(dresses[key] ~= nil) -- (and a mesh names the same key)
				if names[1] == "TrunkCollider" then
					trees += 1
					check.equal(#names, 1)
					check.equal(#dresses[key], 1) -- (each tree its own: one missing mesh shows one trunk)
				elseif dresses[key][1] == "cw" then
					walls += 1
					check.truthy(#dresses[key] >= 3)
				elseif dresses[key][1] == "keep" then
					towers += 1
				end
			end
			check.equal(trees, 5) -- (two typed, three of the forest: each its own)
			check.equal(walls, 1)
			check.equal(towers, 1)
		end)
	end)

	-- LIMITATIONS_FIXES_V3.md stage B.2: a MeshPart's collision shape and level of detail are fixed when it is made,
	-- so they are asked for in CreateMeshPartAsync's options (taken as asked in Studio, 2026-11-17, card fbvv). Every
	-- world mesh was made with Roblox's defaults: a fern or a house's skin, which collide with nothing, carried a full
	-- decomposed collision shape.
	test.suite("World meshes: each made with its collision shape and level of detail", function()
		local function recording(root: any): (any, { any })
			local e = engine(root)
			local asked = {}
			local create = e.deps.create
			e.deps.create = function(meshId: string, fid: any?)
				table.insert(asked, { id = meshId, fid = fid })
				local m = create(meshId)
				m.MadeWith = if fid then `{fid.collision}/{fid.render}` else "defaults"
				return m
			end
			return e, asked
		end
		local function fidOf(asked: { any }, id: string): string
			for _, a in asked do
				if a.id == id then
					return if a.fid then `{a.fid.collision}/{a.fid.render}` else "defaults"
				end
			end
			return "never made"
		end

		test.case(
			"a mesh that collides asks for Roblox's Default, one that does not for a Box; both Automatic",
			function()
				WorldMeshes._reset()
				local root = world()
				placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = true })
				placeholder(root, "fern", { MeshId = "rbxassetid://2", Collide = false })
				placeholder(root, "skin", { MeshId = "rbxassetid://3", KitDress = "House" })
				hidden(root, "Wall", "House")
				local e, asked = recording(root)
				check.equal((WorldMeshes.swapAll(e.deps)), 3)
				check.equal(fidOf(asked, "rbxassetid://1"), "Default/Automatic")
				check.equal(fidOf(asked, "rbxassetid://2"), "Box/Automatic")
				check.equal(fidOf(asked, "rbxassetid://3"), "Box/Automatic") -- (a skin: its building's walls collide)
				check.equal(find(root, "rock_a")[1].MadeWith, "Default/Automatic")
				check.equal(find(root, "fern")[1].MadeWith, "Box/Automatic")
			end
		)

		test.case("one mesh solid here and a backdrop there is made twice, each copy from its own", function()
			WorldMeshes._reset()
			local root = world()
			placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = true })
			placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = false })
			placeholder(root, "rock_a", { MeshId = "rbxassetid://1", Collide = true })
			local e, asked = recording(root)
			check.equal((WorldMeshes.swapAll(e.deps)), 3)
			check.equal(#asked, 2) -- (one per pair of settings, then clones)
			local made = {}
			for _, r in find(root, "rock_a") do
				made[`{r.MadeWith}:{tostring(r.CanCollide)}`] = (made[`{r.MadeWith}:{tostring(r.CanCollide)}`] or 0) + 1
			end
			check.equal(made["Default/Automatic:true"], 2)
			check.equal(made["Box/Automatic:false"], 1)
		end)
	end)
end
