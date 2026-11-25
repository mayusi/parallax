--!strict
-- FamilyRules.luau — the pure rules of A FAMILY OF MODULES THAT SNAP (no services, no instances: spec'd under lune,
-- kit/test/spec/familyrules.spec.luau). The build (a.module(grid, family=), kit/blender/rbx_family.py) gives every
-- module an Attachment "Snap<side>_<v>_<u>" at the middle of every grid cell of every gridded side (side PX, NX,
-- PY, NY, PZ, NZ), and `kit family <name>` writes the family table (which side cells MEET with no seam). Here:
--   snapName(side, v, u)      the Attachment's name for a side cell
--   meets(table, a, b)        do two side cells meet with no seam (the table's "meets"; "Mod.+X.0.0" keys)
--   place(a, sideA, snapA, sideB, snapB) -> { origin, turn } | nil
--                             where module B stands so its side cell meets A's: B turned in quarter turns about
--                             up (a module turns about its up only) until its side faces A's, then moved so the two
--                             snap points are one. A top meets only a bottom; a wall side any wall side.
local FamilyRules = {}

export type Placement = { origin: { number }, turn: number } -- turn: quarter turns about +Y (Roblox: +90 deg)

local NORMAL: { [string]: { number } } = {
	["+X"] = { 1, 0, 0 },
	["-X"] = { -1, 0, 0 },
	["+Y"] = { 0, 1, 0 },
	["-Y"] = { 0, -1, 0 },
	["+Z"] = { 0, 0, 1 },
	["-Z"] = { 0, 0, -1 },
}
local TAG = { ["+X"] = "PX", ["-X"] = "NX", ["+Y"] = "PY", ["-Y"] = "NY", ["+Z"] = "PZ", ["-Z"] = "NZ" }

function FamilyRules.snapName(side: string, v: number, u: number): string
	local tag = TAG[side]
	assert(tag, `FamilyRules.snapName: side {side} - one of +X -X +Y -Y +Z -Z`)
	return `Snap{tag}_{v}_{u}`
end

-- a point turned `turn` quarter turns about +Y (as CFrame.Angles(0, turn * pi / 2, 0): +X goes to -Z)
function FamilyRules.turned(p: { number }, turn: number): { number }
	local t = turn % 4
	local x, y, z = p[1], p[2], p[3]
	for _ = 1, t do
		x, z = z, -x
	end
	return { x, y, z }
end

function FamilyRules.meets(tbl: any, a: string, b: string): boolean
	local list = tbl and tbl.meets and tbl.meets[a]
	if not list then
		return false
	end
	for _, k in list do
		if k == b then
			return true
		end
	end
	return false
end

function FamilyRules.place(a: Placement, sideA: string, snapA: { number }, sideB: string, snapB: { number }): Placement?
	local na, nb = NORMAL[sideA], NORMAL[sideB]
	assert(na and nb, "FamilyRules.place: sides are +X -X +Y -Y +Z -Z")
	local want = FamilyRules.turned(na, a.turn)
	local turn: number? = nil
	for t = 0, 3 do
		local got = FamilyRules.turned(nb, t)
		if got[1] == -want[1] and got[2] == -want[2] and got[3] == -want[3] then
			-- (a top meets a bottom whatever the turn: keep A's, so a stack stands square)
			turn = if na[2] ~= 0 then a.turn % 4 else t
			break
		end
	end
	if turn == nil then
		return nil
	end
	local pa = FamilyRules.turned(snapA, a.turn)
	local pb = FamilyRules.turned(snapB, turn)
	return {
		origin = { a.origin[1] + pa[1] - pb[1], a.origin[2] + pa[2] - pb[2], a.origin[3] + pa[3] - pb[3] },
		turn = turn,
	}
end

return FamilyRules
