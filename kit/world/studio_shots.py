"""studio_shots.py - a world's look stations captured in ROBLOX STUDIO, in Roblox's own light (kit world studio).

    python kit/world/studio_shots.py snippet <stations.json> <out.luau> --world <Name> [--build <key>]
    python kit/world/studio_shots.py watch   <shots_dir> --match <the scratch place's name>
                                             [--stations a,b,c] [--world <Name>] [--wait 240]
    python kit/world/studio_shots.py windows [--match <...>]                                (which Studios are open)

Blender's light is a stand-in: until 2026-11-12 no session saw a world as the owner sees it. The stations are the
ones kit/world/look_blender.py rendered (stations.json: each camera in Roblox's own axes), so Studio shoots the very
same views. The place is the kit's own SCRATCH place (kit/lib/world.luau World.scratchProject, built by rojo): the
world alone, nothing saved, nothing uploaded - so Studio shows plain parts and light, never the meshes.

  snippet  writes the Luau a session runs ONCE through the Studio tools (execute_luau, the Edit datamodel). It REFUSES
           any place but the scratch place (Workspace.KitWorldScratch must name the world) and an OLDER build of it
           still open in Studio (its Build value must be --build: a place file rebuilt on disk is not reloaded by
           Studio), applies the world's own environment with the kit's runtime (ReplicatedStorage.kit.Environment:
           light, atmosphere, terrain), stands a grey R6 figure where the Blender shot has one, and walks the
           stations: before each it covers the 3D view with a plain colour for a second, then holds the view still.
  watch    takes the pictures. The script cannot call out (measured 2026-11-12: "HttpService request denied: domain
           127.0.0.1:<port> is not in the Assistant HTTP allowlist" - every local port), so the two sides agree by
           what is ON SCREEN: this command reads the scratch place's own window (PrintWindow, also while other
           windows cover it; the ONE Studio window whose place is --match, so another session's Studio is never
           read) a few times a second. Magenta = the walk starts (and where the 3D view is in the window); one of
           six colours = a station is coming, the colour saying WHICH (its place in the list, in sixes: a signal
           nobody read can lose that station's picture, never file the next one under its name); cyan = the walk is
           over. Each view is saved once two reads agree (Roblox's light lands over a few frames) and cut to the
           station's frame: the largest 16:9 box in the middle of the 3D view that stays clear of Studio's own view
           cube and tool strip at its sides (the script gives the camera the wider field of view that makes that box
           show exactly what the Blender shot shows) -> <shots_dir>/<station>.png, capture.json.
Prints one JSON line: {status, summary, next_action, ...}.
"""

import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
# the shared Studio capture bridge (kit/tools/studio_capture.py, card 4s96): the signals, the window, the walk
from studio_capture import (  # noqa: E402,F401  (re-exported: kit/tools/studio_model.py and the tests read them here)
    END, NEXTS, START, Walk, _text, blank, differ, dpi_scale, flash_box, grab, lua_str, pick_window, place_of, signal,
    top_windows, user32, watch_walk,
)

ASPECT = 16.0 / 9.0
FLASH, HOLD, MOVE, SETTLE = 1.0, 4.0, 0.3, 1.5  # s: a signal up, a station held, the camera moving, before the walk
# px at the 3D view's sides kept OUT of the frame: Studio's own view cube sits in the top right corner (its X arrow
# reaches 107 px in from the edge, measured 2026-11-12: at 100 a sliver of it stayed) and a tool strip down the left
MARGIN = 120
RIG = (  # the R6 scale figure, as kit/world/look_blender.py add_r6_figure builds it: name, size x y z, across, up
    ("LeftLeg", (1, 2, 1), -0.5, 1.0), ("RightLeg", (1, 2, 1), 0.5, 1.0), ("Torso", (2, 2, 1), 0.0, 3.0),
    ("LeftArm", (1, 2, 1), -1.5, 3.0), ("RightArm", (1, 2, 1), 1.5, 3.0), ("Head", (1.2, 1.2, 1.2), 0.0, 4.6),
)

# ---------------------------------------------------------------- the pure parts
def frame_size(vw, vh, margin=MARGIN, aspect=ASPECT):
    """the station's frame inside a vw x vh 3D view: the largest 16:9 box in its MIDDLE that keeps `margin` px clear
    at both sides - or, where that is larger (a view much taller than wide), above and below, and half of it at the
    sides. Studio draws its own view cube in the top right corner and a tool strip down the left edge: a frame that
    reached the corners carried a sliver of the cube (GothicCourtyard, 2026-11-12). -> (width, height), not rounded"""
    narrower = min(vw - 2.0 * margin, vh * aspect)
    shorter = min(vw - float(margin), (vh - 2.0 * margin) * aspect)
    bw = max(narrower, shorter, 1.0)
    return bw, bw / aspect


def frame_box(vw, vh, margin=MARGIN, aspect=ASPECT):
    """that frame as a box to cut out of a picture of the 3D view -> (left, top, right, bottom)"""
    bw, bh = frame_size(vw, vh, margin, aspect)
    left, top = int(round((vw - bw) / 2.0)), int(round((vh - bh) / 2.0))
    return (left, top, left + int(round(bw)), top + int(round(bh)))


def fit_fov(fov, vw, vh, margin=MARGIN, aspect=ASPECT):
    """the camera's vertical field of view (degrees) that makes the frame (frame_size) show exactly what the station
    shows - `fov` tall, `aspect` wide: the 3D view is taller than the frame, so its own field of view is wider"""
    if vw <= 0 or vh <= 0:
        return fov
    _, bh = frame_size(vw, vh, margin, aspect)
    return math.degrees(2.0 * math.atan(math.tan(math.radians(fov) / 2.0) * vh / bh))


def walk_seconds(n):
    """how long the script's walk of n stations takes (what the session is told, and what the watch waits for)"""
    return SETTLE + FLASH + n * (FLASH + MOVE + HOLD) + FLASH


def _num(v):
    return ("%.3f" % float(v)).rstrip("0").rstrip(".") or "0"


def snippet(stations, world, build=None):
    """the Luau that walks the stations in the scratch place (run once through execute_luau, the Edit datamodel);
    `build`: the scratch place's own build key - the script refuses a place that carries another"""
    rows = []
    for s in stations:
        rig = s.get("rig")
        rows.append(
            "\t{ name = %s, cam = Vector3.new(%s), target = Vector3.new(%s), fov = %s%s },"
            % (lua_str(s["name"]), ", ".join(_num(v) for v in s["cam"]), ", ".join(_num(v) for v in s["target"]),
               _num(s.get("fov", 70)), (", rig = Vector3.new(%s)" % ", ".join(_num(v) for v in rig)) if rig else ""))
    rig_rows = "\n".join(
        "\t\tbox(%s, Vector3.new(%s), %s, %s)" % (lua_str(n), ", ".join(_num(v) for v in size), _num(ox), _num(oy))
        for n, size, ox, oy in RIG)

    def rgb(c):
        return "Color3.fromRGB(%d, %d, %d)" % c

    return (LUAU.replace("@WORLD@", lua_str(world)).replace("@BUILD@", lua_str(build or ""))
            .replace("@ASPECT@", repr(ASPECT)).replace("@STATIONS@", "\n".join(rows)).replace("@RIG@", rig_rows)
            .replace("@START@", rgb(START)).replace("@END@", rgb(END))
            .replace("@NEXTS@", ", ".join(rgb(c) for c in NEXTS))
            .replace("@FLASH@", _num(FLASH)).replace("@HOLD@", _num(HOLD)).replace("@MOVE@", _num(MOVE))
            .replace("@SETTLE@", _num(SETTLE)).replace("@MARGIN@", _num(MARGIN))
            .replace("@SECONDS@", str(int(math.ceil(walk_seconds(len(stations)))))))


LUAU = r'''-- kit world studio: the look stations of one world, shown one by one in THIS Studio for `kit world studio
-- <Name> --capture` to photograph. Generated by kit/world/studio_shots.py from the Blender look's stations.json - do
-- not edit. Run it ONCE through the Studio tools (execute_luau, the Edit datamodel) in the kit's SCRATCH place only:
-- it refuses every other place, and an older build of the scratch place. It calls nothing outside Studio; a plain
-- colour over the 3D view tells the capture what is coming (magenta: the walk starts; one of six colours: a
-- station, and which; cyan: over).
local WORLD, BUILD, ASPECT, MARGIN = @WORLD@, @BUILD@, @ASPECT@, @MARGIN@
local FLASH, HOLD, MOVE, SETTLE, SECONDS = @FLASH@, @HOLD@, @MOVE@, @SETTLE@, @SECONDS@
local NEXTS = { @NEXTS@ }
local STATIONS = {
@STATIONS@
}
local Workspace = game:GetService("Workspace")

local marker = Workspace:FindFirstChild("KitWorldScratch")
if not (marker and marker:IsA("StringValue") and marker.Value == WORLD) then
	return "REFUSED: this is not the kit's scratch place for " .. WORLD .. " (Workspace.KitWorldScratch is missing or names another world). Nothing was touched. Open the scratch place and pass ITS studio_id."
end
local built = marker:FindFirstChild("Build")
if BUILD ~= "" and not (built and built:IsA("StringValue") and built.Value == BUILD) then
	return "REFUSED: this Studio shows an OLDER build of " .. WORLD .. "'s scratch place (the file was rebuilt since it was opened; Studio does not reload it). Nothing was touched. Close this place, open the file again, and run the script again."
end
local started = marker:GetAttribute("Started")
if marker:GetAttribute("Status") == "running" and type(started) == "number" and os.time() - started < SECONDS + 20 then
	return "ALREADY WALKING: a walk of " .. WORLD .. " is running in this place; wait for it (about " .. SECONDS .. " s)"
end
local camera = Workspace.CurrentCamera
local view = camera.ViewportSize
marker:SetAttribute("Status", "running")
marker:SetAttribute("Started", os.time())
task.spawn(function()
	local gui, cover, rig
	local was = { cf = camera.CFrame, fov = camera.FieldOfView, focus = camera.Focus }
	local function flash(colour)
		cover.BackgroundColor3 = colour
		cover.Visible = true
		task.wait(FLASH)
	end
	local ok, err = pcall(function()
		-- the world's own environment, by the kit's runtime, as the game applies it at start (light, atmosphere, terrain)
		local okEnv, got = pcall(function()
			local kit = game:GetService("ReplicatedStorage"):WaitForChild("kit", 5)
			return (require :: any)(kit:WaitForChild("Environment", 5)).applyAll()
		end)
		marker:SetAttribute("Environment", if okEnv then "applied to " .. tostring(got) .. " world(s)" else "NOT applied: " .. tostring(got))
		pcall(function()
			game:GetService("Selection"):Set({})
		end)
		local old = Workspace:FindFirstChild("KitLookRig")
		if old then
			old:Destroy()
		end
		rig = Instance.new("Model")
		rig.Name = "KitLookRig"
		local function box(name, size, across, up)
			local p = Instance.new("Part")
			p.Name, p.Size, p.Anchored, p.CanCollide = name, size, true, false
			p.Color, p.Material = Color3.fromRGB(160, 160, 160), Enum.Material.SmoothPlastic
			p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
			p:SetAttribute("across", across)
			p:SetAttribute("up", up)
			p.Parent = rig
		end
@RIG@
		-- the signal: one plain colour over the whole 3D view (drawn above everything else there)
		gui = Instance.new("ScreenGui")
		gui.Name, gui.DisplayOrder, gui.IgnoreGuiInset = "KitWorldStudioSignal", 2147483647, true
		cover = Instance.new("Frame")
		cover.Size, cover.BorderSizePixel, cover.Visible = UDim2.fromScale(1, 1), 0, false
		cover.Parent = gui
		gui.Parent = game:GetService("CoreGui")
		task.wait(SETTLE) -- (the light just changed: let it land before the first picture)
		flash(@START@)
		for i, s in STATIONS do
			-- which station is coming is in the colour (its place in the list, in sixes); the camera moves behind it,
			-- so no half-moved view is ever read
			flash(NEXTS[(i - 1) % #NEXTS + 1])
			if s.rig then
				local flat = Vector3.new(s.cam.X, s.rig.Y, s.cam.Z)
				local stand = if (flat - s.rig).Magnitude > 0.01 then CFrame.lookAt(s.rig, flat) else CFrame.new(s.rig)
				for _, p in rig:GetChildren() do
					p.CFrame = stand * CFrame.new(p:GetAttribute("across"), p:GetAttribute("up"), 0)
				end
				rig.Parent = Workspace
			else
				rig.Parent = nil
			end
			-- the station's frame: the largest 16:9 box in the MIDDLE of the 3D view that stays MARGIN px clear of its
			-- sides (Studio's own view cube and tool strip sit there) - the capture cuts the same box out of its
			-- picture (kit/world/studio_shots.py frame_size). The view is taller than the frame: a wider field of view
			local vs = camera.ViewportSize
			local wide = math.max(math.min(vs.X - 2 * MARGIN, vs.Y * ASPECT), math.min(vs.X - MARGIN, (vs.Y - 2 * MARGIN) * ASPECT), 1)
			local fov = math.deg(2 * math.atan(math.tan(math.rad(s.fov) / 2) * vs.Y / (wide / ASPECT)))
			if fov > 120 then
				error(string.format("the 3D view (%d x %d) cannot hold the station's frame: make the Studio window wider", vs.X, vs.Y))
			end
			camera.CFrame = CFrame.lookAt(s.cam, s.target)
			camera.Focus = CFrame.new(s.target)
			camera.FieldOfView = fov
			task.wait(MOVE)
			cover.Visible = false
			task.wait(HOLD)
		end
	end)
	if cover then
		pcall(flash, @END@) -- (also after an error: the capture stops waiting, and says which stations it has)
	end
	if gui then
		gui:Destroy()
	end
	if rig then
		rig:Destroy()
	end
	camera.CFrame, camera.FieldOfView, camera.Focus = was.cf, was.fov, was.focus
	marker:SetAttribute("Status", if ok then "done" else "error: " .. tostring(err))
end)
return "kit world studio: walking " .. #STATIONS .. " station(s) of " .. WORLD .. " (about " .. SECONDS .. " s; the 3D view is " .. view.X .. " x " .. view.Y .. "). The capture command that is waiting takes the pictures and ends by itself. Afterwards: Workspace.KitWorldScratch's Status and Environment attributes say how it went."
'''


# ---------------------------------------------------------------- the watch
def watch(shots_dir, match, world, expected, wait, pause=0.2):
    os.makedirs(shots_dir, exist_ok=True)
    for f in os.listdir(shots_dir):  # (a last walk's pictures: this walk shows its own, or says not captured)
        if f.endswith(".png") or f in ("capture.json", "of.txt"):
            os.remove(os.path.join(shots_dir, f))
    shots = {}

    def keep(station, img, ok, top):
        native = img.size
        img = img.crop(frame_box(native[0], native[1], MARGIN * dpi_scale(top)))
        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in station)
        if blank(img):
            return
        img.save(os.path.join(shots_dir, safe + ".png"))
        shots[station] = {"file": safe + ".png", "native": list(img.size), "viewport": list(native),
                          "settled": bool(ok)}

    got = watch_walk(match, expected, wait, keep, pause=pause)
    walk, place, why = got["walk"], got["place"], got["why"]
    missing = [n for n in expected if n not in shots]
    if not walk.started:
        why = why or (f"no walk was seen in {int(wait)} s: the capture script was not run in the scratch place "
                      "(or its 3D view is not on screen)")
    elif not walk.over:
        why = f"the walk did not finish in {int(wait)} s ({len(shots)} of {len(expected)} station(s) seen)"
    elif missing:
        why = ("not captured: " + ", ".join(missing) + " (the walk ended without them: Workspace.KitWorldScratch's "
               "Status attribute in the scratch place says why)")
    else:
        why = None
    meta = {"world": world, "place": place, "when": datetime.datetime.now().isoformat(timespec="seconds"),
            "stations": shots,
            "shows": "plain parts and light: nothing is uploaded, so no mesh and no custom material is shown"}
    if why:
        meta["why"] = why
    with open(os.path.join(shots_dir, "capture.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    unsettled = [n for n, r in shots.items() if not r["settled"]]
    ok = bool(shots) and not missing and walk.over
    summary = f"{len(shots)} station(s) captured in Roblox Studio" + (f" ({place})" if place and shots else "")
    if unsettled:
        summary += f"; the light had not settled for {', '.join(unsettled)}"
    if why:
        summary += "; " + why
    print(json.dumps({"status": "pass" if ok else "fail", "summary": summary,
                      "next_action": f"look at {shots_dir.replace(os.sep, '/')}" if ok else
                      "open the scratch place in Roblox Studio, start this again and run the capture script there",
                      "captured": sorted(shots), "missing": missing, "why": why, "unsettled": unsettled}))
    return 0 if ok else 1


def main(argv):
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default

    cmd = argv[0] if argv else ""
    if cmd == "snippet" and len(argv) >= 3:
        with open(argv[1], encoding="utf-8") as fh:
            stations = [s for s in json.load(fh).get("stations", []) if s.get("name") and s.get("cam") and s.get("target")]
        if not stations:
            print(json.dumps({"status": "fail", "summary": f"{argv[1]} names no station with a camera",
                              "next_action": "render the look again: lune run kit world look <Name>"}))
            return 1
        with open(argv[2], "w", encoding="utf-8", newline="\n") as fh:
            fh.write(snippet(stations, opt("--world", "World"), opt("--build")))
        print(json.dumps({"status": "pass", "summary": f"the Studio capture script for {len(stations)} station(s)",
                          "next_action": f"run {argv[2].replace(os.sep, '/')} through the Studio tools (execute_luau, Edit) in the scratch place",
                          "stations": [s["name"] for s in stations],
                          "seconds": int(math.ceil(walk_seconds(len(stations))))}))
        return 0
    if cmd == "windows":
        tops = top_windows()
        studios = [t for _, t in tops if t.endswith("Roblox Studio")]
        match = opt("--match")
        hit, why = pick_window(tops, match) if match else (None, None)
        print(json.dumps({"status": "pass", "summary": f"{len(studios)} Roblox Studio window(s)", "next_action": "none",
                          "studios": studios, "open": hit is not None, "why": why}))
        return 0
    if cmd == "watch" and len(argv) >= 2 and opt("--match"):
        if user32 is None:
            print(json.dumps({"status": "fail", "summary": "the Studio capture reads a Windows window: not on this system",
                              "next_action": "run it on the PC that has Roblox Studio"}))
            return 1
        expected = [n for n in (opt("--stations") or "").split(",") if n]
        return watch(argv[1], opt("--match"), opt("--world", ""), expected, float(opt("--wait", 240)))
    print(json.dumps({"status": "fail", "summary": "usage: studio_shots.py snippet|watch|windows ... (see the file's head)",
                      "next_action": "lune run kit world studio <Name>"}))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
