-- familyrules.spec.luau — the pure rules of a family of modules that snap (src/kit/FamilyRules, 2026-11-17): the
-- snap Attachment's name, a side turned about up, which side cells meet (the family table), and where module B
-- stands so its side meets A's
local frk = require("../frk")
local test, check = frk.test, frk.check
local R = require("../../../src/kit/FamilyRules")

return function()
	test.suite("FamilyRules a family of modules that snap", function()
		local function same(p: { number }, q: { number }): boolean
			return math.abs(p[1] - q[1]) < 1e-9 and math.abs(p[2] - q[2]) < 1e-9 and math.abs(p[3] - q[3]) < 1e-9
		end

		test.case("the build's snap Attachment is named by side and cell", function()
			check.equal(R.snapName("+X", 0, 0), "SnapPX_0_0")
			check.equal(R.snapName("-Z", 1, 2), "SnapNZ_1_2")
		end)

		test.case("a quarter turn about up takes +X to -Z, as CFrame.Angles(0, pi/2, 0) does", function()
			check.truthy(same(R.turned({ 1, 0, 0 }, 1), { 0, 0, -1 }))
			check.truthy(same(R.turned({ 1, 2, 3 }, 4), { 1, 2, 3 }))
		end)

		test.case("a hall's straight end to end: B stands one cell on, unturned, its -X on A's +X", function()
			-- (a 4-stud module: its +X snap at (4, 2, 2), its -X snap at (0, 2, 2), the module's origin a corner)
			local b = R.place({ origin = { 0, 0, 0 }, turn = 0 }, "+X", { 4, 2, 2 }, "-X", { 0, 2, 2 })
			check.truthy(b ~= nil)
			check.truthy(same((b :: any).origin, { 4, 0, 0 }))
			check.equal((b :: any).turn, 0)
		end)

		test.case("a side met by another side turns the module until they face", function()
			-- B's +Z against A's +X: B must turn until its +Z looks along -X
			local b = R.place({ origin = { 0, 0, 0 }, turn = 0 }, "+X", { 4, 2, 2 }, "+Z", { 2, 2, 4 }) :: any
			check.truthy(b ~= nil)
			check.truthy(same(R.turned({ 0, 0, 1 }, b.turn), { -1, 0, 0 }))
			local snapB = R.turned({ 2, 2, 4 }, b.turn)
			check.truthy(same({ b.origin[1] + snapB[1], b.origin[2] + snapB[2], b.origin[3] + snapB[3] }, { 4, 2, 2 }))
		end)

		test.case("a top meets only a bottom, and the stack keeps A's turn", function()
			local b = R.place({ origin = { 0, 0, 0 }, turn = 1 }, "+Y", { 2, 4, 2 }, "-Y", { 2, 0, 2 }) :: any
			check.truthy(b ~= nil)
			check.equal(b.turn, 1)
			check.equal(R.place({ origin = { 0, 0, 0 }, turn = 0 }, "+Y", { 2, 4, 2 }, "+X", { 4, 2, 2 }), nil)
			check.equal(R.place({ origin = { 0, 0, 0 }, turn = 0 }, "+Y", { 2, 4, 2 }, "+Y", { 2, 4, 2 }), nil)
		end)

		test.case("every turn of A against every pair of wall sides: B faces A and the snaps are one", function()
			-- (review 2026-11-17: no case turned A, nor tried every side)
			local N = { ["+X"] = { 1, 0, 0 }, ["-X"] = { -1, 0, 0 }, ["+Z"] = { 0, 0, 1 }, ["-Z"] = { 0, 0, -1 } }
			local SNAP = { ["+X"] = { 4, 2, 2 }, ["-X"] = { 0, 2, 2 }, ["+Z"] = { 2, 2, 4 }, ["-Z"] = { 2, 2, 0 } }
			for ta = 0, 3 do
				for sa, na in N do
					for sb, nb in N do
						local a = { origin = { 8, 0, -4 }, turn = ta }
						local b = R.place(a, sa, SNAP[sa], sb, SNAP[sb]) :: any
						check.truthy(b ~= nil)
						local want = R.turned(na, ta)
						check.truthy(same(R.turned(nb, b.turn), { -want[1], -want[2], -want[3] }))
						local pa, pb = R.turned(SNAP[sa], ta), R.turned(SNAP[sb], b.turn)
						check.truthy(
							same(
								{ a.origin[1] + pa[1], a.origin[2] + pa[2], a.origin[3] + pa[3] },
								{ b.origin[1] + pb[1], b.origin[2] + pb[2], b.origin[3] + pb[3] }
							)
						)
					end
				end
			end
		end)

		test.case("a module stacked on a turned one keeps its turn, and a bottom meets a top above it", function()
			local b = R.place({ origin = { 0, 0, 0 }, turn = 3 }, "+Y", { 2, 4, 2 }, "-Y", { 2, 0, 2 }) :: any
			check.equal(b.turn, 3)
			local p = R.turned({ 2, 4, 2 }, 3)
			local q = R.turned({ 2, 0, 2 }, 3)
			check.truthy(same({ b.origin[1] + q[1], b.origin[2] + q[2], b.origin[3] + q[3] }, p))
			local c = R.place({ origin = { 0, 4, 0 }, turn = 0 }, "-Y", { 2, 0, 2 }, "+Y", { 2, 4, 2 }) :: any
			check.truthy(same(c.origin, { 0, 0, 0 }))
		end)

		test.case("which side cells meet is the family table's", function()
			local tbl = { meets = { ["Straight.+X.0.0"] = { "Straight.-X.0.0", "End.-X.0.0" } } }
			check.truthy(R.meets(tbl, "Straight.+X.0.0", "End.-X.0.0"))
			check.falsy(R.meets(tbl, "Straight.+X.0.0", "Bad.-X.0.0"))
			check.falsy(R.meets(tbl, "Nope", "End.-X.0.0"))
		end)
	end)
end
