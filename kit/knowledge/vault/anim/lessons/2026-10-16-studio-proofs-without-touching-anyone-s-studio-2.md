---
kind: lesson
area: anim
date: 2026-10-16
by: mayusi
source: "kit/lessons/anim.md"
links: ["[[anim/index]]"]
project: Parallax
---

Studio proofs without touching anyone's Studio (2026-10-16): open YOUR OWN instance on a COPY of build/place.rbxlx (RobloxStudioBeta.exe <copy>), then name it: kit anim play <Name> --rig R6 --run --studio <id> (the kit runs the 100-300 KB probe itself through StudioMCP) and kit playtest run <scenario> --studio <id>. In scenarios: never move the client-owned PLAYER character from the server (it fought back: flung 37-60 studs) - build server-owned R6 dummies (Players:CreateHumanoidModelFromDescription, root:SetNetworkOwner(nil)) on an anchored floor of their own (a spawn pad has edges: the first dummy fell); the owner's look = GetHumanoidDescriptionFromUserId(player.UserId) as R6; a Studio-registered animation loads ASYNC (Length 0 at first) - read a marker on track.TimePosition, never a stopwatch.
