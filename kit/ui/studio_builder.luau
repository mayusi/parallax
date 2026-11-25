--!nocheck
-- studio_builder.luau — builds a compiled kit screen (its Rojo model JSON) as live instances in Roblox Studio,
-- so a screen can be looked at IN THE ENGINE (real fonts, real gradients, real motion) before anything uploads.
-- `lune run kit ui bundle <Screen>` writes build/ui/<Screen>.studio.luau = this file with __JSON__ and __NAME__
-- filled in; any harness runs that through the Studio MCP (execute_luau, datamodel Edit) and captures the screen.
-- It replaces StarterGui.<Screen> in the open place and does not save anything.
local HttpService = game:GetService("HttpService")
local StarterGui = game:GetService("StarterGui")

local NAME = "__NAME__"
local MODEL = HttpService:JSONDecode([==[__JSON__]==])

local ENUMS = {
	Font = Enum.Font,
	ScaleType = Enum.ScaleType,
	TextXAlignment = Enum.TextXAlignment,
	TextYAlignment = Enum.TextYAlignment,
	ApplyStrokeMode = Enum.ApplyStrokeMode,
	FillDirection = Enum.FillDirection,
	HorizontalAlignment = Enum.HorizontalAlignment,
	VerticalAlignment = Enum.VerticalAlignment,
	SortOrder = Enum.SortOrder,
	AutomaticSize = Enum.AutomaticSize,
	AutomaticCanvasSize = Enum.AutomaticSize,
	ZIndexBehavior = Enum.ZIndexBehavior,
	ScreenInsets = Enum.ScreenInsets,
}

local function value(v: any): any
	if type(v) ~= "table" then
		return v
	end
	if v.UDim2 then
		return UDim2.new(v.UDim2[1][1], v.UDim2[1][2], v.UDim2[2][1], v.UDim2[2][2])
	elseif v.UDim then
		return UDim.new(v.UDim[1], v.UDim[2])
	elseif v.Color3 then
		return Color3.new(v.Color3[1], v.Color3[2], v.Color3[3])
	elseif v.Vector2 then
		return Vector2.new(v.Vector2[1], v.Vector2[2])
	elseif v.Rect then
		return Rect.new(v.Rect[1][1], v.Rect[1][2], v.Rect[2][1], v.Rect[2][2])
	elseif v.ColorSequence then
		local kps = {}
		for _, k in v.ColorSequence.keypoints do
			table.insert(kps, ColorSequenceKeypoint.new(k.time, Color3.new(k.color[1], k.color[2], k.color[3])))
		end
		return ColorSequence.new(kps)
	elseif v.NumberSequence then
		local kps = {}
		for _, k in v.NumberSequence.keypoints do
			table.insert(kps, NumberSequenceKeypoint.new(k.time, k.value, k.envelope or 0))
		end
		return NumberSequence.new(kps)
	elseif v.Float64 ~= nil then
		return v.Float64
	elseif v.String ~= nil then
		return v.String
	elseif v.Bool ~= nil then
		return v.Bool
	end
	return nil
end

local refused = {}

local function build(node: any, parent: Instance): Instance
	local inst = Instance.new(node.ClassName)
	inst.Name = node.Name or node.ClassName
	for k, v in node.Properties or {} do
		if k == "Attributes" then
			for ak, av in v.Attributes or {} do
				inst:SetAttribute(ak, value(av))
			end
		else
			local val = value(v)
			if ENUMS[k] and type(val) == "string" then
				val = ENUMS[k][val]
			end
			local ok = pcall(function()
				(inst :: any)[k] = val
			end)
			if not ok then
				table.insert(refused, `{inst.Name}.{k}`)
			end
		end
	end
	for _, c in node.Children or {} do
		build(c, inst)
	end
	inst.Parent = parent
	return inst
end

local old = StarterGui:FindFirstChild(NAME)
if old then
	old:Destroy()
end
MODEL.Name = NAME
local gui = build(MODEL, StarterGui)
gui.Enabled = true
return `{NAME}: {#gui:GetDescendants()} instances in StarterGui`
	.. (if #refused > 0 then `; refused: {table.concat(refused, ", ")}` else "")
