--!strict
-- CraterRefs (kit) — which terrain cells a crater may give back (the V3 doc, VFX stage B: "craterRefs[cellKey]
-- reference counting").
--
-- Crater.blast with heal = N wrote back, N seconds later, the voxels IT read when it went off. Two craters that
-- overlap clobbered each other: the older one's heal filled the newer bowl in, and the newer one's heal wrote back
-- ground that still had the older bowl in it - a hole left for good after both had healed.
--
-- Now every 4-stud cell a crater touches is counted: the first crater on a cell keeps the cell as it was (the
-- untouched ground), each later one only counts; a heal counts down and gives back only the cells no crater holds
-- any more - with the untouched ground. A permanent crater (no heal) holds its cells for good, so a healing crater
-- beside it never fills it in. Pure: kit/test/spec/craterrefs.spec.luau.
local CraterRefs = {}

export type Cell = { material: any, occupancy: number }
export type Refs = { [string]: { count: number, pristine: Cell } }

function CraterRefs.new(): Refs
	return {}
end

-- the key of a cell: its integer position on the 4-stud voxel grid
function CraterRefs.key(x: number, y: number, z: number): string
	return `{x},{y},{z}`
end

-- the cells of a voxel read: its first cell's grid place (gx, gy, gz) and its size in cells -> the keys, and where
-- each sits in the read's arrays ({ ix, iy, iz }, 1-based)
function CraterRefs.grid(gx: number, gy: number, gz: number, nx: number, ny: number, nz: number)
	local keys: { string } = {}
	local at: { [string]: { number } } = {}
	for ix = 1, nx do
		for iy = 1, ny do
			for iz = 1, nz do
				local k = CraterRefs.key(gx + ix - 1, gy + iy - 1, gz + iz - 1)
				table.insert(keys, k)
				at[k] = { ix, iy, iz }
			end
		end
	end
	return keys, at
end

-- a crater takes the cells it touches: read(key) -> the cell as it is NOW (asked only for a cell no crater holds)
function CraterRefs.take(refs: Refs, keys: { string }, read: (string) -> Cell)
	for _, k in keys do
		local r = refs[k]
		if r then
			r.count += 1
		else
			refs[k] = { count = 1, pristine = read(k) }
		end
	end
end

-- a crater heals: -> { [key]: the untouched cell } for the cells no crater holds any more (the rest stay as they are)
function CraterRefs.give(refs: Refs, keys: { string }): { [string]: Cell }
	local back: { [string]: Cell } = {}
	for _, k in keys do
		local r = refs[k]
		if r then
			r.count -= 1
			if r.count <= 0 then
				back[k] = r.pristine
				refs[k] = nil
			end
		end
	end
	return back
end

-- how many cells are held now (a probe: 0 once every healing crater has healed and none is permanent)
function CraterRefs.held(refs: Refs): number
	local n = 0
	for _ in refs do
		n += 1
	end
	return n
end

return CraterRefs
