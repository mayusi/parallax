-- jsonmodel.luau — compare a generated JSON file with the model that would be written now.
-- Both sides go through the SAME path (pretty encode -> decode -> compact encode): Lune's pretty printer rounds
-- floats differently from the compact one, so comparing a pretty file with a compact encoding reported every
-- model with a fraction (colours like 231/255, trig in level generators) as stale forever.
local serde = require("@lune/serde")

local JsonModel = {}

function JsonModel.same(fileText: string, model: any): boolean
	local onDisk = serde.encode("json", serde.decode("json", fileText))
	local fresh = serde.encode("json", serde.decode("json", serde.encode("json", model, true)))
	return onDisk == fresh
end

return JsonModel
