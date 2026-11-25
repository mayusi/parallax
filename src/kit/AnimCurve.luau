--!strict
-- AnimCurve — A KIT CLIP AS A ROBLOX CURVE ANIMATION (the owner's method lists 2026-11-13: "animation curves"; the
-- last row of board/plans/archive/2026-11-13-anim-methods-audit.md that was only partly there).
--
-- The kit bakes a clip as a KeyframeSequence with a pose on EVERY frame (60 a second, linear between them). Roblox
-- also plays a CurveAnimation: one curve a channel, a key only where the motion needs one. The MOTION is the same;
-- what a curve buys is a smaller asset (the keys a straight stretch does not need are left out) and curves a person
-- can open in Roblox's Curve Editor.
--
--   local curve, report = AnimCurve.fromSequence(sequence, { rotTol = 0.25, posTol = 0.005 })
--       -> a CurveAnimation (not parented) holding the same motion to within rotTol degrees and posTol studs at
--          every frame the sequence has, named <Name>Curve, and { keys, kept, tracks, lostDeg, lostStuds }
--          (keys / kept count a joint's turn and its place once each a frame; a kept place is three numbers)
--   AnimCurve.thin(times, values, tol, lerp, dist) -> { index }   THE RULE (pure): which keys a track keeps
--   AnimCurve.lost(times, values, lerp, dist) -> number           WHAT THE ENGINE DROPS (pure): see below
--
-- WHAT ROBLOX DOES TO A CURVE ANIMATION (measured in Studio, 2026-11-15, three clips, every key kept): it plays it
-- at THIRTY samples a second. A key on that grid plays exactly (0.11 degrees); a key between two grid moments - every
-- odd frame of a 60-a-second kit clip - is replaced by the straight line between its neighbours: 5.24 degrees and
-- 0.14 studs on the loved kesa's arms at its fastest, 2.15 degrees on IronMountain; a 30-a-second walk loses
-- nothing. The SAME clips as KeyframeSequences play every frame to 0.12 degrees. So the kit's clips stay
-- KeyframeSequences; a curve animation is for a clip made at 30 a second, or one a person wants to open in the
-- Curve Editor. `lost` works out that loss before anything is uploaded (it predicted 5.241 and 2.153: measured
-- 5.242 and 2.152), the report carries it, and fromSequence WARNS when it is over the tolerance.
--
-- THE RULE: the first and the last key are kept. Walking forward, a key is dropped while every key dropped since
-- the last kept one stays within `tol` of the straight line (lerp) between the kept key and the next one; the
-- moment one would not, the key before is kept. So no dropped key is ever further than tol from the curve's own
-- line (a place: exactly; a turn: to within a hair more, a slerp is not a straight line). What the ENGINE then plays
-- of a thinned curve is within tol + the loss below of the clip. At most RUN keys in a row are left out.
-- WHAT IT REFUSES: a pose that is not eased "Linear" (a hand-keyed sequence with Cubic or Bounce eases is not a
-- sampled motion: thinning its keys would change it - bake it dense first: `kit anim <Name>` does).
-- A joint the sequence only carries along (Weight 0) gets its folder and no curve, as the sequence gets a pose and
-- no weight. Markers become MarkerCurves of the same name and value.
-- Studio only for the building (FloatCurve keys are written by script); the result is an asset like any other.

local AnimCurve = {}

export type Report = {
	keys: number,
	kept: number,
	tracks: number,
	lostDeg: number, -- the most a joint's turn is off at a key the engine's 30-a-second playback drops
	lostStuds: number, -- ... and its place
}
export type Options = { rotTol: number?, posTol: number? }

AnimCurve.ROT_TOL = 0.25 -- degrees a dropped key's turn may be from what plays
AnimCurve.POS_TOL = 0.005 -- studs a dropped key's place may be from what plays
AnimCurve.GRID = 30 -- samples a second the engine plays a curve animation at (measured)
AnimCurve.RUN = 64 -- keys in a row that may be left out (a long straight stretch is checked key against key: bounded)

-- which keys of one track are kept -> their indices, ascending. times: ascending seconds; values: one a key;
-- lerp(a, b, u) -> the value u of the way from a to b; dist(a, b) -> how far apart two values are (>= 0).
function AnimCurve.thin<T>(
	times: { number },
	values: { T },
	tol: number,
	lerp: (T, T, number) -> T,
	dist: (T, T) -> number
): { number }
	local n = #values
	if n <= 2 then
		local all = {}
		for i = 1, n do
			table.insert(all, i)
		end
		return all
	end
	local limit = if tol == tol and tol > 0 then tol else 0
	local kept = { 1 }
	local anchor = 1
	for i = 2, n - 1 do
		-- may key i be dropped? every key after the anchor up to i must sit on the line anchor -> i + 1
		local span = times[i + 1] - times[anchor]
		local fine = span > 0 and i - anchor < AnimCurve.RUN
		if fine then
			for j = anchor + 1, i do
				local u = (times[j] - times[anchor]) / span
				local d = dist(values[j], lerp(values[anchor], values[i + 1], u))
				if not (d <= limit) then -- (a distance that is not a number keeps the key)
					fine = false
					break
				end
			end
		end
		if not fine then
			table.insert(kept, i)
			anchor = i
		end
	end
	table.insert(kept, n)
	return kept
end

-- the track's value at a time (the straight line between the keys either side; held before the first, after the last)
local function at<T>(times: { number }, values: { T }, lerp: (T, T, number) -> T, t: number): T
	local n = #values
	if t <= times[1] then
		return values[1]
	end
	for i = 2, n do
		if t <= times[i] then
			local span = times[i] - times[i - 1]
			return if span > 0 then lerp(values[i - 1], values[i], (t - times[i - 1]) / span) else values[i]
		end
	end
	return values[n]
end

-- WHAT THE ENGINE'S PLAYBACK DROPS: the engine samples the track 30 times a second and plays the straight line
-- between two samples. For every key: how far it lies from what plays at its own time - the line between the
-- track's value at the grid moment before it and at the one after. 0 for a track whose keys are all on the grid.
-- (The first cut compared a key with the line between its two neighbouring KEYS: the same thing for a 60-a-second
-- clip, too little for a 120-a-second one or a key squeezed between two frames - the one review, 2026-11-15.)
function AnimCurve.lost<T>(times: { number }, values: { T }, lerp: (T, T, number) -> T, dist: (T, T) -> number): number
	local worst = 0
	for i = 1, #values do
		local g = times[i] * AnimCurve.GRID
		if math.abs(g - math.floor(g + 0.5)) > 0.01 then
			local before, after = math.floor(g) / AnimCurve.GRID, math.ceil(g) / AnimCurve.GRID
			local plays = lerp(at(times, values, lerp, before), at(times, values, lerp, after), g - math.floor(g))
			local d = dist(values[i], plays)
			if d == d and d > worst then
				worst = d
			end
		end
	end
	return worst
end

local function lerpNumber(a: number, b: number, u: number): number
	return a + (b - a) * u
end
local function distNumber(a: number, b: number): number
	return math.abs(a - b)
end
AnimCurve.lerpNumber = lerpNumber
AnimCurve.distNumber = distNumber

-- ---------------------------------------------------------------- the game side (Instances; Studio)
type Track = { times: { number }, frames: { CFrame }, moved: boolean }

local function collect(pose: Pose, path: string, t: number, tracks: { [string]: Track }, order: { string })
	local key = if path == "" then pose.Name else path .. "/" .. pose.Name
	local track = tracks[key]
	if not track then
		track = { times = {}, frames = {}, moved = false }
		tracks[key] = track
		table.insert(order, key)
	end
	if pose.Weight > 0 then
		if pose.EasingStyle ~= Enum.PoseEasingStyle.Linear then
			error(
				`[AnimCurve] the pose of {pose.Name} at {t} s is eased {pose.EasingStyle.Name}, not Linear: a keyed sequence is not a sampled motion - bake it dense first (lune run kit anim <Name>)`,
				0
			)
		end
		track.moved = true
		if #track.times > 0 and t <= track.times[#track.times] then
			track.frames[#track.frames] = pose.CFrame -- (two keyframes at one time: the later one stands, as in a curve)
		else
			table.insert(track.times, t)
			table.insert(track.frames, pose.CFrame)
		end
	end
	for _, child in pose:GetSubPoses() do
		if child:IsA("Pose") then
			collect(child, key, t, tracks, order)
		end
	end
end

local function folderFor(root: Instance, key: string): Instance
	local here = root
	for _, name in string.split(key, "/") do
		local nextFolder = here:FindFirstChild(name)
		if not nextFolder or not nextFolder:IsA("Folder") then -- (a marker named like a part is not that part's folder)
			local made = Instance.new("Folder")
			made.Name = name
			made.Parent = here
			nextFolder = made
		end
		here = nextFolder :: Instance
	end
	return here
end

function AnimCurve.fromSequence(sequence: KeyframeSequence, options: Options?): (CurveAnimation, Report)
	local rotTol = math.rad(if options and options.rotTol then options.rotTol else AnimCurve.ROT_TOL)
	local posTol = if options and options.posTol then options.posTol else AnimCurve.POS_TOL
	local keyframes: { Keyframe } = {}
	for _, k in sequence:GetKeyframes() do
		if k:IsA("Keyframe") then
			table.insert(keyframes, k)
		end
	end
	table.sort(keyframes, function(a, b)
		return a.Time < b.Time
	end)
	local tracks: { [string]: Track } = {}
	local order: { string } = {}
	local curve = Instance.new("CurveAnimation")
	curve.Name = sequence.Name .. "Curve" -- (never the sequence's own name: side by side, one would hide the other)
	curve.Loop = sequence.Loop
	curve.Priority = sequence.Priority
	local markers: { [string]: MarkerCurve } = {}
	for _, k in keyframes do
		for _, pose in k:GetPoses() do
			if pose:IsA("Pose") then
				collect(pose, "", k.Time, tracks, order)
			end
		end
		for _, m in k:GetMarkers() do
			if m:IsA("KeyframeMarker") then
				local mc: MarkerCurve = markers[m.Name] or Instance.new("MarkerCurve")
				if not markers[m.Name] then
					mc.Name = m.Name
					mc.Parent = curve
					markers[m.Name] = mc
				end
				mc:InsertMarkerAtTime(k.Time, m.Value)
			end
		end
	end
	local report: Report = { keys = 0, kept = 0, tracks = 0, lostDeg = 0, lostStuds = 0 }
	local function turnLerp(a: CFrame, b: CFrame, u: number): CFrame
		return a.Rotation:Lerp(b.Rotation, u)
	end
	local function turnDist(a: CFrame, b: CFrame): number
		local _, angle = (a.Rotation:Inverse() * b.Rotation):ToAxisAngle()
		angle = math.abs(angle) % (2 * math.pi)
		return math.min(angle, 2 * math.pi - angle) -- (the short way: a turn read as nearly a full circle is a small one)
	end
	local function placeLerp(a: CFrame, b: CFrame, u: number): CFrame
		return CFrame.new(a.Position:Lerp(b.Position, u))
	end
	local function placeDist(a: CFrame, b: CFrame): number
		return (a.Position - b.Position).Magnitude
	end
	for _, key in order do
		local track = tracks[key]
		local folder = folderFor(curve, key)
		if track.moved then
			report.tracks += 1
			report.keys += 2 * #track.frames
			-- the turn: one rotation curve, slerped between its keys
			local turns = AnimCurve.thin(track.times, track.frames, rotTol, turnLerp, turnDist)
			report.lostDeg =
				math.max(report.lostDeg, math.deg(AnimCurve.lost(track.times, track.frames, turnLerp, turnDist)))
			report.lostStuds =
				math.max(report.lostStuds, AnimCurve.lost(track.times, track.frames, placeLerp, placeDist))
			local rotation = Instance.new("RotationCurve")
			rotation.Name = "Rotation"
			for _, i in turns do
				rotation:InsertKey(
					RotationCurveKey.new(track.times[i], track.frames[i].Rotation, Enum.KeyInterpolationMode.Linear)
				)
			end
			rotation.Parent = folder
			report.kept += #turns
			-- the place: three number curves; a key is kept on all three where the place needs one
			local places = AnimCurve.thin(track.times, track.frames, posTol, placeLerp, placeDist)
			local position = Instance.new("Vector3Curve")
			position.Name = "Position"
			for axis, name in { "X", "Y", "Z" } do
				local fc = Instance.new("FloatCurve")
				fc.Name = name
				for _, i in places do
					local p = track.frames[i].Position
					local v = if axis == 1 then p.X elseif axis == 2 then p.Y else p.Z
					fc:InsertKey(FloatCurveKey.new(track.times[i], v, Enum.KeyInterpolationMode.Linear))
				end
				fc.Parent = position
			end
			position.Parent = folder
			report.kept += #places
		end
	end
	if report.lostDeg > math.deg(rotTol) or report.lostStuds > posTol then
		warn(
			string.format(
				"[AnimCurve] %s: Roblox plays a curve animation at %d samples a second - this clip's keys between them lose up to %.2f degrees and %.3f studs. Keep it a KeyframeSequence (every frame plays), or make the clip at %d a second",
				sequence.Name,
				AnimCurve.GRID,
				report.lostDeg,
				report.lostStuds,
				AnimCurve.GRID
			)
		)
	end
	return curve, report
end

return AnimCurve
