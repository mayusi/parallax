--!strict
-- VfxPlate (kit) — B4: an IMPACT PLATE shown over the whole screen, a drawn flipbook stepped cell by cell on the 60 fps
-- game clock (LIMITATIONS_FIXES_V4 §3.4 step 3, §13.3.4). The plates are baked by kit/vfx/plates.py (halftone burst,
-- concentration lines, a brush-written kanji) into a 1024 x 1024 sheet of 1 / 4 / 16 cells + a spec
-- (assets/effects/plates/<key>.plate.json -> ReplicatedStorage.VfxPresets.plates[<key>]).
--
--   VfxPlate.layout(spec) -> cols, rows               the sheet's grid (checked: 1x1, 2x2, 4x4 only)
--   VfxPlate.cellAt(spec, frame, mode?) -> number?     the cell (0-based) shown on the plate's frame-th 60 fps frame:
--                                                       each drawing held `rate` frames; "OneShot" (default) -> nil
--                                                       past its last drawing, "Loop" wraps, "Hold" keeps the last
--   VfxPlate.rect(spec, cell, sheetPx?) -> ox, oy, w, h   ImageRectOffset / ImageRectSize of a cell, in px
--   VfxPlate.show(spec, opts) -> handle                 (client) a ScreenGui ImageLabel over the screen:
--       opts = { image = "rbxassetid://..."? (else the spec's own "id", else textures[spec.texture]), color = Color3?,
--                transparency = 0..1?, mode = "OneShot" | "Loop" | "Hold"?, order = DisplayOrder? }
--       handle:step(frame) -> boolean (false: the plate is over) ; handle:destroy()
-- The maths is pure (no service is touched until show is called): kit/test/spec/vfxsequence.spec.luau runs it.
local VfxPlate = {}

local GRIDS: { [number]: number } = { [1] = 1, [4] = 2, [16] = 4 }

function VfxPlate.layout(spec: any): (number, number)
	local n = if type(spec) == "table" then GRIDS[spec.frames] else nil
	if not n then
		error("VfxPlate: a plate has 1, 4 or 16 frames (kit vfx plate bakes it)", 2)
	end
	return n, n
end

function VfxPlate.cellAt(spec: any, frame: number, mode: string?): number?
	local cols = VfxPlate.layout(spec)
	local count = cols * cols
	local rate = if type(spec.rate) == "number" and spec.rate >= 1 then math.floor(spec.rate) else 2
	if type(frame) ~= "number" or frame ~= frame or frame < 0 then
		return nil
	end
	local i = math.floor(frame / rate)
	local m = mode or spec.mode or "OneShot"
	if m == "Loop" then
		return i % count
	elseif m == "Hold" then
		return math.min(i, count - 1)
	end
	return if i < count then i else nil
end

function VfxPlate.rect(spec: any, cell: number, sheetPx: number?): (number, number, number, number)
	local cols = VfxPlate.layout(spec)
	local px = sheetPx or 1024
	local size = px / cols
	local r, q = cell // cols, cell % cols
	return q * size, r * size, size, size
end

local function idOf(spec: any, opts: any): string
	if type(opts.image) == "string" and opts.image ~= "" then
		return opts.image
	end
	if type(spec.id) == "string" and spec.id ~= "" then -- the plate's own (kit vfx plate writes it; the owner's upload fills it)
		return spec.id
	end
	local reg = opts.textures
	local e = if type(reg) == "table" then reg[spec.texture or ""] else nil
	if type(e) == "table" and type(e.id) == "string" and e.id ~= "" then
		return e.id
	end
	return ""
end

export type Handle = { step: (self: Handle, frame: number) -> boolean, destroy: (self: Handle) -> (), gui: any }

function VfxPlate.show(spec: any, opts: any?): Handle
	local o = opts or {}
	VfxPlate.layout(spec) -- refuses a plate that is not one before anything is made
	local Players = game:GetService("Players")
	local gui = Instance.new("ScreenGui")
	gui.Name = "KitVfxPlate"
	gui.IgnoreGuiInset = true
	gui.ResetOnSpawn = false
	gui.DisplayOrder = o.order or 1001
	local img = Instance.new("ImageLabel")
	img.Name = "Plate"
	img.BackgroundTransparency = 1
	img.Size = UDim2.fromScale(1, 1)
	img.ScaleType = Enum.ScaleType.Crop
	img.Image = idOf(spec, o)
	img.ImageColor3 = o.color or Color3.new(0, 0, 0)
	img.ImageTransparency = o.transparency or 0
	img.Visible = false
	img.Parent = gui
	local lp = Players.LocalPlayer
	gui.Parent = if lp then lp:WaitForChild("PlayerGui") else game:GetService("StarterGui")
	local handle = { gui = gui } :: any
	function handle.step(_self: any, frame: number): boolean
		local cell = VfxPlate.cellAt(spec, frame, o.mode)
		if cell == nil then
			img.Visible = false
			return false
		end
		local ox, oy, w, h = VfxPlate.rect(spec, cell)
		img.ImageRectOffset = Vector2.new(ox, oy)
		img.ImageRectSize = Vector2.new(w, h)
		img.Visible = img.Image ~= ""
		return true
	end
	function handle.destroy(_self: any)
		gui:Destroy()
	end
	return handle :: Handle
end

return VfxPlate
