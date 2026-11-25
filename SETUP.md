# Setting up Parallax

This guide takes a Windows 10 or 11 machine to a working Parallax project: the toolchain, the kit, Roblox Studio's MCP
server, a game project and your AI client. Every step has a **command**, a **check** with what you should see, and
**if it fails**. Most people hand this file to their AI agent and let it do the work - that is what it is written for.

**Contents** - [For AI agents](#for-ai-agents) · [What you need](#what-you-need) ·
[1 Base tools](#step-1--base-tools) · [2 Rokit](#step-2--rokit) · [3 Get Parallax](#step-3--get-parallax) ·
[4 Doctor](#step-4--check-the-toolchain) · [5 Hardware tier](#step-5--choose-your-hardware-tier) ·
[6 Roblox Studio](#step-6--roblox-studio-and-its-mcp-server) · [7 Your game](#step-7--make-your-game-project) ·
[8 Your AI client](#step-8--connect-your-ai-client) · [9 First run](#step-9--first-run-and-final-check) ·
[Uploads](#uploading-to-roblox) · [Updating](#updating) · [Troubleshooting](#troubleshooting) ·
[Uninstall](#uninstalling)

---

## For AI agents

If a person gave you this file to set Parallax up for them:

1. **Do the steps in order.** After each one, run its **Check** and compare what you get with what it should show.
2. **A failed check is not a next step.** Do that step's **If it fails**, then run the check again. Never skip a step
   or continue past a failed check; if you cannot fix it, stop and tell the person exactly what you saw.
3. **Stop and ask the person** when a step needs them: an installer's admin (UAC) prompt, signing in to anything,
   Roblox Studio's own settings and permission switches, a trust prompt you cannot answer, or a choice that is theirs
   (the game folder, the AI client, which optional lanes to set up).
4. **Never ask for, type or store a password, token or API key.** Parallax does not need one.
5. **Report at the end** with the final check's `summary:` lines (step 9).

Every Parallax command ends with `summary:` and `next_action:`. When a check fails, its `next_action:` is usually the
fix.

### The prompt to give your AI

Copy this into your AI client and fill in the two blanks:

```text
Set up Parallax for me. Follow SETUP.md from https://github.com/mayusi/parallax step by step.
My game folder: <C:\path\to\MyGame>.  My AI client: <Claude Code | Cursor | VS Code | Gemini CLI | Codex | ...>.
Run every check and compare it with the expected result. Stop and ask me when a step needs me
(admin prompts, sign-ins, Roblox Studio settings). Never ask me for a password or an API key.
```

---

## What you need

| | Needed for | Required |
|---|---|---|
| Windows 10 or 11 | everything (most commands also run on macOS and Linux; full support is on the roadmap) | yes |
| Git | cloning; the kit's git hooks | yes |
| Rokit → Rojo 7.7.1, Wally 0.3.2, Selene 0.32.0, StyLua 2.5.2, Lune 0.10.5, luau-lsp 1.70.1 | the kit runs on Lune; the rest build and check Luau | yes |
| Python 3.11 with numpy, scipy, Pillow, matplotlib, pytest | the kit's Python tools and tests, and its MCP server | yes |
| An MCP-capable AI client | driving the kit | yes |
| Roblox Studio (latest) with its MCP server | seeing the game, playtests, uploads | for real use |
| Node.js LTS | the VFX effect player's checks | for VFX |
| ffmpeg | sound, effect breakdowns and recordings | for sound and VFX |
| Blender 5.2 | 3D, effect bakes, animation, world and UI renders | for those lanes |
| Local AI models (vision stack, CAD, 3D generators) | references, segmentation, similarity, hard surfaces, drafts | optional, by [hardware tier](#step-5--choose-your-hardware-tier) |

---

## Step 1 — Base tools

Install Git, Python 3.11, Node.js and ffmpeg (skip any you already have). In PowerShell:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Gyan.FFmpeg -e
```

Then **open a new terminal** (installers change PATH only for new terminals) and install the Python packages:

```powershell
python -m pip install numpy scipy pillow matplotlib pytest
```

**Check**

```powershell
git --version
python --version
node --version
ffmpeg -version
python -c "import numpy, scipy, PIL, matplotlib, pytest; print('python packages ok')"
```

You should see a version line for each tool, `Python 3.11.x`, and `python packages ok`.

**If it fails** - "not recognized": open a new terminal and try again. Still failing: install that tool from its own
site (git-scm.com, python.org - tick "Add python.exe to PATH" - nodejs.org, ffmpeg.org) and open a new terminal. If
`python` opens the Microsoft Store, turn off the "App execution aliases" for python in Windows Settings.

---

## Step 2 — Rokit

[Rokit](https://github.com/rojo-rbx/rokit) installs the exact Roblox toolchain versions the kit pins in `rokit.toml`.

```powershell
Invoke-RestMethod https://raw.githubusercontent.com/rojo-rbx/rokit/main/scripts/install.ps1 | Invoke-Expression
```

Open a new terminal.

**Check** - `rokit --version` prints a version.

**If it fails** - download `rokit.exe` from the [latest release](https://github.com/rojo-rbx/rokit/releases) and
run `.\rokit.exe self-install` in the folder you saved it to, then open a new terminal.

---

## Step 3 — Get Parallax

Choose a folder for the kit (it is the kit's home: your games live in their own folders next to it).

```powershell
git clone https://github.com/mayusi/parallax.git
cd parallax
rokit install
wally install
```

`rokit install` may ask once whether you trust each tool. They are the six tools in `rokit.toml` from their official
authors - answer yes.

**Check**

```powershell
lune run parallax version
```

You should see `summary: kit 3.1.0` (or newer).

**If it fails** - `lune` not recognized: open a new terminal (Rokit adds its folder to PATH). The trust prompt cannot
be answered (an AI agent with no interactive terminal): ask the person to run `rokit install` once in their own
terminal. `wally install` fails: check your internet connection and run it again.

---

## Step 4 — Check the toolchain

```powershell
lune run parallax doctor
```

**Check** - every Tier 0 tool (Rokit's six, Python and its packages, Node.js, ffmpeg, the Wally packages) is found,
and the output ends with `machine tier: N`. Missing optional tools are listed with the lane each one blocks and how to
get it - that is fine until you use that lane (step 5).

**If it fails** - install what it names, open a new terminal, and run `doctor` again.

---

## Step 5 — Choose your hardware tier

Parallax runs on any PC and grows with your hardware; each tier includes the ones below it, and a lane on a lower tier
takes the route that tier allows instead of failing. Steps 1-4 already give you **Tier 0**. Go as far up as your machine
and your lanes need - if you are an AI agent, ask the person which tier they want (the bigger tiers are large downloads).

| Tier | Needs | Commands |
|---|---|---|
| **0 · Zero-GPU core** | any PC | steps 1-4 |
| **1 · DCC & CAD** (3D, bakes, renders, animation, worlds) | any CPU | install Blender 5.2, then the three below |
| **2 · Light vision core** (cut-outs, depth, similarity; 2.43 GB) | the CPU or a 4 GB GPU | PyTorch + transformers + safetensors (below), then `lune run parallax vision setup` |
| **3 · Local VLM & diffusion** (+44.58 GB of models) | an NVIDIA GPU with 12 GB, 16 GB RAM | `lune run parallax vision setup --tier vision` + the `diffusers` and TRELLIS.2 environments ([`kit/gen/README.md`](kit/gen/README.md)) |
| **4 · Full 3D generation** (+~24.5 GB of models + 25-70 GB of generator environments) | CUDA 13, 12-16+ GB VRAM, 32 GB RAM, MSVC 2022 | `lune run parallax vision setup --tier gen` + [`kit/gen/README.md`](kit/gen/README.md) |

**Tier 1.** Install Blender 5.2 LTS from [blender.org](https://www.blender.org/download/) into its default folder
(`C:\Program Files\Blender Foundation\`): Parallax finds the newest version there. Anywhere else, set an environment
variable `BLENDER` to the full path of `blender.exe`. Then:

```powershell
lune run parallax tools setup kit-python
lune run parallax tools setup cad
lune run parallax tools setup mitsuba
```

**Tier 2 runtime (before `vision setup`).** No `lune run parallax` command installs PyTorch. Install PyTorch for your
GPU (pytorch.org's selector) into the kit's Python 3.11, then:

```powershell
pip install transformers safetensors
```

(The kit's own CUDA environments in [`kit/gen/README.md`](kit/gen/README.md) use torch 2.10.0+cu130 from
download.pytorch.org/whl/cu130.) Then `lune run parallax vision setup`.

**Tier 3 environments.** `vision setup --tier vision` downloads weights only; two Python environments are built by hand
from [`kit/gen/README.md`](kit/gen/README.md):
- the `diffusers` environment ("Diffusion models"): SDXL, its VAE, the depth ControlNet, the two DiffusionLight LoRAs,
  DPT-Large and FLUX.2 klein (`vision light`, `vision concept`, `vision plate`);
- the TRELLIS.2 environment (`trellis2`, "Reinstall from scratch"): Depth Anything 3, MoGe-2, Marigold-IID and SAM 3
  (`vision relief`, `vision albedo`, `vision parts`).

Qwen3-VL-4B runs in the kit's Python with the Tier 2 runtime.

**Tier 4 size.** About 24.5 GB of models (Qwen-Image-Edit and its stable-diffusion.cpp runner) plus 25-70 GB of 3D
generator environments (TRELLIS.2 and Pixal3D in `trellis2`, `partcrafter`, `hunyuan3d2`).

**Tiers 2-4.** `lune run parallax vision setup --list` shows every model with its tier and size. Each download is
pinned to a commit and kept only if its size and hash match ([VETLOG.md](VETLOG.md)); an interrupted download resumes.
SAM 3 (Tier 3) is a gated model: the person requests access on Hugging Face with their own account and sets `HF_TOKEN`
in their own environment - without it the tier skips SAM 3 with a note and the free SAM 2.1 masks stand in. Each Tier 4
generator comes under its own licence, and some restrict territories or uses: read its [VETLOG.md](VETLOG.md) row before
installing it. Everything runs on your machine; nothing is sent to a cloud service.

**Check** - `lune run parallax doctor` prints `machine tier: N` and, below Tier 4, exactly what the next tier needs.

---

## Step 6 — Roblox Studio and its MCP server

Roblox Studio has a built-in MCP server. Parallax uses it to drive playtests, look at the game in the engine, and
upload assets through Open Cloud with **your own Studio login** - no API key.

1. **Install Roblox Studio** from [create.roblox.com](https://create.roblox.com/) and sign in. *(The person does this.)*
2. **Open a place from a published game.** Open Cloud permissions are saved per game, so a local, unpublished place
   cannot use them.
3. **Turn the MCP server on:** open **Assistant**, click **…** → **Manage MCP Servers**, and turn on
   **Enable Studio as MCP server**.
4. **Add the Roblox Studio MCP to your AI client.** Assistant's settings offer a quick connect for Claude Code,
   Codex CLI, Claude Desktop, Cursor, Gemini CLI and VS Code. For any other client, add this server (Windows):

   ```json
   {
     "mcpServers": {
       "Roblox_Studio": {
         "command": "cmd.exe",
         "args": ["/c", "%LOCALAPPDATA%\\Roblox\\mcp.bat"]
       }
     }
   }
   ```

   On macOS the command is `/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP`.
5. **Allow uploads** *(the person does this; an AI agent must not change these switches)*: click **MCP** in Studio's
   bottom-right corner → **MCP Permissions**. Under **Publish & manage assets**, allow `asset:read` and `asset:write`
   (and `asset-permissions:write` if audio should be granted to your experience). Approve your game project's
   `build` folder as an upload folder. Changes apply to the client's next request.

**Check** - Assistant → **…** → **Manage MCP Servers** shows a green indicator, and your AI client lists the Roblox
Studio tools (for example `list_roblox_studios`).

**If it fails** - restart Studio and the AI client; check the path and the JSON syntax of the config. Roblox's own
guides: [Connect to the Studio MCP server](https://create.roblox.com/docs/studio/mcp) and
[Use Open Cloud with the Studio MCP server](https://create.roblox.com/docs/studio/mcp-open-cloud).

---

## Step 7 — Make your game project

From the kit's folder, point `install` at your game's folder (it is created if it does not exist; an existing Rojo
project keeps its files):

```powershell
lune run parallax install ..\MyGame
cd ..\MyGame
git add -A
git commit -m "Start from Parallax (cross)"
```

`install` copies the kit (`kit/`) and its in-game runtime (`src/kit/`), the measured data its builders read, starter
content (sounds, effects, textures, models), a work board (`board/` with `BRIEF.md`) and the git hooks, then runs
`rokit install`, `wally install` and `git init`. It writes **no** AI-client files - step 8 adds the one you use.

(The word `cross` tells the lane fence - the git hook that keeps each commit to one department - that this commit
spans every department on purpose. A brand-new repository's first commit is let through anyway; an existing one's
needs the word.)

**Check**

```powershell
lune run parallax status
```

You should see the board's summary and a `next_action:`.

**If it fails** - `install` reports `rokit install` or `wally install` failed: run them in the game folder yourself,
then `lune run parallax doctor`.

---

## Step 8 — Connect your AI client

In the **game folder**:

```powershell
lune run parallax connect claude
```

Use your client's name:

| Client | Command | What it does |
|---|---|---|
| Claude Code | `lune run parallax connect claude` | writes `.mcp.json` and `.claude/settings.json` (the enforcement hooks) |
| Cursor | `lune run parallax connect cursor` | writes `.cursor/mcp.json` |
| VS Code (Copilot agent mode) | `lune run parallax connect vscode` | writes `.vscode/mcp.json` |
| Gemini CLI | `lune run parallax connect gemini` | writes `.gemini/settings.json` with the enforcement hooks |
| Roo Code | `lune run parallax connect roo` | writes `.roo/mcp.json` |
| OpenCode | `lune run parallax connect opencode` | writes `opencode.json` |
| Codex CLI | `lune run parallax connect codex` | prints a block for `~/.codex/config.toml` |
| Windsurf | `lune run parallax connect windsurf` | prints a block for `~/.codeium/windsurf/mcp_config.json` |
| Cline | `lune run parallax connect cline` | prints a block for Cline's MCP settings |
| Claude Desktop | `lune run parallax connect claude-desktop` | prints a block for `claude_desktop_config.json` |

Several at once: `lune run parallax connect claude,cursor`. For the clients that print a block, paste it into that
client's config file (it carries this project's absolute path). Then **restart the client in the game folder** and
approve the `parallax` server if it asks.

**Check** - `lune run parallax connect` lists your client as `connected` (the clients that print a block are not
tracked - check them in the client), and the client shows the tools `parallax_start`, `parallax_status`,
`parallax_skill` and the others.

**If it fails** - the client does not list the tools: make sure it was started in the game folder, that `python`
works in a new terminal, and that you approved the server. `lune run parallax connect <client> --remove` takes the
kit's entry out again.

---

## Step 9 — First run and final check

In your AI client, in the game folder:

```text
Call parallax_status and tell me what the board says.
```

Then fill in `board/BRIEF.md` (what the game is) and ask for the first piece, for example:

```text
Start the 3d lane: a mossy stone well for the village square.
```

**Final check** - in the game folder:

```powershell
lune run parallax harness --check
lune run parallax doctor
lune run parallax verify
```

`harness --check` says the git hooks and every connected client's config are in step; `doctor` shows no missing
required tool; `verify` ends with `summary: verify: all gates green`. The first `verify` takes a while.

---

## Uploading to Roblox

`lune run parallax upload` screens every new or changed file (the moderation gate: banned words, blood) and writes an
upload plan with the exact Roblox Studio MCP call for each file. The agent then, for each file:

1. calls `open_cloud_invoke` with that file's call from `build/upload_plan.json` (the `studio_id` comes from
   `list_roblox_studios`);
2. polls `GET /assets/v1/operations/<operationId>` with `open_cloud_invoke` until `done` is true;
3. records the id: `lune run parallax upload --record <file> <assetId>`.

`lune run parallax upload --pending` lists what is left; after the last one the kit recompiles the models and screens
that use the new ids. One-time setup: in the game's `kit.config.json`,
`"upload": {"creator": "user:<your user id>", "universe": <experience id>}` (your user id is the number in your
roblox.com profile URL; the universe is the experience that should play the audio). Uploads are permanent - Open Cloud
cannot delete them. New images and sounds go through Roblox moderation: `lune run parallax upload --status`.

For headless runs (CI, no Studio), an `ROBLOX_API_KEY` set in the environment makes the kit upload by itself - never
paste a key into a chat or a file.

---

## Updating

**From a GitHub release (any game):** inside the game folder -

```powershell
lune run parallax upgrade --check
lune run parallax upgrade
```

`--check` compares the installed version (`kit/UPSTREAM.json`) with the latest release and writes nothing. `upgrade`
refuses when you edited the kit's own files (`--force` overrides) or have uncommitted changes (commit first, or
`--allow-dirty`); downloads the release and checks its SHA-256 before unpacking anything; backs up the current kit; and
then updates in four zones - the kit's code is replaced (a file you added under `kit/` stays), starter content and
lessons are only added to, the knowledge vault is merged (your lessons, verdicts and rules are kept), and your game's
code and content are left alone. An error while the kit's files are replaced puts the backup back exactly. Last, the
new kit's `init` keeps its own lines in `.gitignore`, the git hooks and a connected client's config in step; if that
step fails, `upgrade` says so and names the command to finish it. Restart your AI client afterwards if it says the MCP server changed. `--tag vX.Y.Z`
picks a release; `--from <tarball>` (with its `.sha256`) installs a downloaded one.

**From a local clone of the kit:** in the kit's folder, `git pull`, then `lune run parallax update ..\MyGame`; or
inside a game, `lune run parallax sync`. A game made with 3.0.0 has no `upgrade` command yet: update it this way once,
and `upgrade` works from then on. An update never takes a game back: a game holding a later kit than the clone's (it
was upgraded to a newer release since) is refused - `git pull` the clone first, or pass `--force` to install the
clone's kit anyway.

Commit an update on its own, with the lane fence's word for a commit that spans every department:
`git add -A; git commit -m "Update Parallax (cross)"`.

After an update, `lune run parallax harness` refreshes the connected client's config and hooks. Coming from 3.0.0, it
also removes what that version wrote for every AI client - the instruction blocks, rule files, skill copies and the
kit's entry in every client's MCP config - keeping anything you wrote yourself; then connect the client you use again
with `lune run parallax connect <client>`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `lune`, `rokit` or `python` "not recognized" | open a new terminal; check the tool's install step |
| `rokit install` stops at a trust prompt | answer yes for the tools in `rokit.toml`, or let the person run it once |
| a pipeline command says `REFUSED` / exits with 6 | start the lane first: `parallax_start` (or `lune run parallax start <lane> --prompt "<the request>"`) |
| `harness --check` reports files out of step | `lune run parallax harness`, then commit what it changed if you share that client config |
| the AI client does not show the `parallax` tools | start the client in the game folder, approve the server, restart it |
| the Studio MCP refuses a file or a scope | the person allows it in Studio: **MCP** → **MCP Permissions** (and approves the `build` folder) |
| `rojo serve` cannot connect | only one project can serve on the port; stop the other one. Save a copy of a place before the first Connect - Rojo replaces what it manages |
| the AI broke something | `git restore .` (uncommitted) or `git revert` (a commit); `lune run parallax sync` restores edited kit files; `lune run parallax status` shows the last handoff and open tasks |

---

## Uninstalling

- A game: `lune run parallax connect <client> --remove` for each connected client, then delete `kit/` and `src/kit/`
  (your game's own files are untouched).
- The kit: delete its folder. Rokit's tools live in `%USERPROFILE%\.rokit`; the optional local models in
  `%USERPROFILE%\.cache\roblox-kit`.
