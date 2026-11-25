-- SkyRules.luau (kit runtime, pure) — HOW A SKY OF THE KIT'S OWN IS TURNED (kit world sky; the owner's method list:
-- "Skyboxes"). The six pictures have their own sun drawn in them, at the place the sky was rendered for. The light in
-- the game comes from where Roblox's clock puts the sun. The sky is turned about the vertical so that the drawn sun
-- stands over the compass side the light comes from.
--
-- Azimuths are in degrees from -Z round toward +X (the kit's north toward east), as `kit world sky --sun` asks.
-- A positive turn about Y in Roblox carries -Z toward -X: it takes that many degrees OFF an azimuth. So the turn that
-- brings a sun drawn at `drawn` to the real sun at `real` is drawn - real. SEEN in Studio (2026-11-16, built-in
-- textures, nothing uploaded): a Sky's SkyboxOrientation of (0, 90, 0) shows its Ft picture toward -X, (0, -90, 0)
-- toward +X.
-- Pure: no game calls.
local SkyRules = {}

SkyRules.NAME = "KitSky"
SkyRules.DRAWN = "KitSunAzimuth" -- (the attribute on the Sky that keeps where its sun is drawn)

-- the compass side a direction points to (nil when it points straight up or down)
function SkyRules.azimuth(x: number, z: number): number?
	if math.abs(x) < 1e-3 and math.abs(z) < 1e-3 then
		return nil
	end
	return math.deg(math.atan2(x, -z))
end

-- WHERE A SKY'S SUN IS DRAWN, for the turn: sky = what the compile hands the game ({ faces, sun = {x, y, z}, fixed })
-- -> its azimuth; nil when the sky is not to be turned: it has no sun to go by, or it is FIXED - a sky with far
-- ridges painted in it (kit world sky --ridges) stands as it was rendered, for mountains do not wheel round the
-- horizon with the hour
function SkyRules.drawn(sky: any): number?
	if type(sky) ~= "table" or sky.fixed == true or type(sky.sun) ~= "table" then
		return nil
	end
	local x, z = sky.sun[1], sky.sun[3]
	if type(x) ~= "number" or type(z) ~= "number" then
		return nil
	end
	return SkyRules.azimuth(x, z)
end

-- THE TURN: drawn = the azimuth the sky's sun is drawn at; sunX, sunY, sunZ = the way to the real sun
-- -> degrees about Y, -180..180; nil when the real sun is under the horizon or straight overhead (the sky is left
-- as it stands: at night the pictures' day sun has nothing to stand over)
function SkyRules.turn(drawn: number, sunX: number, sunY: number, sunZ: number): number?
	if sunY < 0.02 then
		return nil
	end
	local real = SkyRules.azimuth(sunX, sunZ)
	if real == nil then
		return nil
	end
	return (drawn - real + 180) % 360 - 180
end

return SkyRules
