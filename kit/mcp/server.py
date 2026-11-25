"""server.py — Parallax (the Roblox kit) as an MCP server (stdio, JSON-RPC 2.0). Python standard library only.

Any MCP-capable harness (Claude Code, Cursor, Gemini CLI, OpenCode, Roo, VS Code/Copilot, Codex, Windsurf) gets:
  parallax_start   START HERE: load ONE lane (+ prompt: PROMPT-X compiles the request and writes the session)
  parallax_prompt  compile the owner's request with PROMPT-X (its case contracts + the session token)
  parallax_case    the CASE a request is in its lane: contract + capability menu (<= 25 lines)
  parallax_skill   the lane's full recipe (its skill page), for harnesses without a skills folder
  parallax_status  the arriving-model briefing (board, last handoff, failing gates, next step)
  parallax_help    every command
  parallax_verify  the full quality gate
  parallax         run ANY command, e.g. ["task", "claim", "ab12", "--as", "gpt-5@codex"] or ["asset", "crate"]:
                   a MUTATING pipeline command is refused (isError, with the exact next call) without a fresh
                   session from parallax_start(prompt=...) / parallax_prompt (PARALLAX spec §2.3 layer 3)
The pre-Parallax names (kit_start, kit_skill, kit_status, kit_help, kit_verify, kit) still answer (zero breakage).
Prompts start-<lane> exist for clients that show MCP prompts as slash commands.
The rules travel with the server: `initialize` returns kit/harness/AGENTS.parallax.md as the instructions every client
gets, so no client needs an instruction file. A client's config is written by `lune run parallax connect <client>`.
Run from anywhere: the project root is found from this file.
"""

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "kit", "scripts"))
PROTOCOL = "2025-06-18"
MAX_LINES = 160  # keep tool output small: the agent's context is expensive
LANES = ["3d", "vfx", "ui", "anim", "world", "sfx", "code", "qa", "kit"]
CASE_LANES = ["3d", "vfx", "anim", "world", "ui", "sfx", "code", "qa"]
VERSION = "3.1.0"  # the kit's release (kit/VERSION); PROTOCOL above is the MCP spec date, a separate thing
ALIASES = {"kit_start": "parallax_start", "kit_skill": "parallax_skill", "kit_status": "parallax_status",
           "kit_help": "parallax_help", "kit_verify": "parallax_verify", "kit": "parallax"}

TOOLS = [
    {
        "name": "parallax_start",
        "description": "START HERE. Load ONE department lane: its boot sheet, stage commands and lessons, open tasks, "
        "last handoff and vault page. With `prompt` (the owner's request) PROMPT-X compiles it, routes it to its CASE "
        "and writes the session that unlocks pipeline commands. Work only in that lane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dept": {"type": "string", "enum": LANES, "description": "the department lane to load"},
                "prompt": {"type": "string", "description": "the owner's request, word for word"},
                "stage": {"type": "string", "description": "a stage of that lane's route, default the first"},
                "game": {"type": "string", "description": "the game (games/<Name>) this session works in, when the owner named one"},
            },
            "required": ["dept"],
        },
    },
    {
        "name": "parallax_prompt",
        "description": "Compile the owner's request with PROMPT-X: lanes, the vault's graveyard + golden records, the "
        "CASE contract per lane, the capability menu, a token budget per model; writes the session token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "the owner's request, word for word"},
                "lane": {"type": "string", "enum": LANES, "description": "the lane that leads (optional)"},
                "model": {"type": "string", "description": "claude | codex | gemini | local"},
                "piece": {"type": "string", "description": "the piece it is for (optional)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "parallax_case",
        "description": "The CASE a request is in its lane: the contract's floor, forbidden routes, owner stops + the "
        "lane's capability menu and escalation ladder (<= 25 lines).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lane": {"type": "string", "enum": CASE_LANES},
                "words": {"type": "string", "description": "the request"},
            },
            "required": ["lane", "words"],
        },
    },
    {
        "name": "parallax_skill",
        "description": "The lane's FULL recipe (its skill page): every stage, its commands and its traps. Read it after "
        "parallax_start when your harness has no skills folder.",
        "inputSchema": {
            "type": "object",
            "properties": {"dept": {"type": "string", "enum": LANES, "description": "the department lane"}},
            "required": ["dept"],
        },
    },
    {
        "name": "parallax_status",
        "description": "The whole board (all lanes): project brief, tasks in progress/ready/blocked, the last handoff, "
        "failing quality gates, and the single next step.",
        "inputSchema": {
            "type": "object",
            "properties": {"as": {"type": "string", "description": 'who you are, e.g. "sonnet-4.6@claude-code"'}},
        },
    },
    {
        "name": "parallax_help",
        "description": "List every command (work board, systems, 3D, VFX, sound, UI, QA, setup).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "parallax_verify",
        "description": "Run THE quality gate: format, selene, types, tests, VFX presets, UI drift, security audit, "
        "harness drift, Rojo build. Returns summary + next_action.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "parallax",
        "description": "Run any command. args is the argument list after `lune run parallax`. Examples: "
        '["task","add","Dash ability","--area","code","--done","dash covers 12 studs"], '
        '["new","system","Dash"], ["asset","crate","--fast"], ["vfx"], ["audit"], '
        '["handoff","what I did","--next","what is next","--as","gpt-5@codex"]. A mutating pipeline command needs '
        "the session from parallax_start(prompt=...) first. Act on the final summary: and next_action: lines.",
        "inputSchema": {
            "type": "object",
            "properties": {"args": {"type": "array", "items": {"type": "string"}}},
            "required": ["args"],
        },
    },
]


def find_lune():
    found = shutil.which("lune")
    if found:
        return found
    home = os.path.expanduser("~")
    for name in ("lune.exe", "lune"):
        candidate = os.path.join(home, ".rokit", "bin", name)
        if os.path.isfile(candidate):
            return candidate
    return "lune"


RULES = os.path.join(ROOT, "kit", "harness", "AGENTS.parallax.md")
HEAD = ("Parallax is enforced, not advisory. Pipeline work (3D models, VFX, animation, worlds, UI, sound, gameplay "
        "systems, QA) is refused until you call parallax_start with the lane and the owner's request (prompt). "
        "parallax_case gives the request's contract, parallax_skill the lane's full recipe. Every command ends with "
        "summary: and next_action: - act on them. Each `lune run parallax <command> ...` below is also the `parallax` "
        "tool with args [\"<command>\", ...].")


def instructions():
    """the rules every client gets at initialize: one source, kit/harness/AGENTS.parallax.md"""
    try:
        with open(RULES, encoding="utf-8") as fh:
            return HEAD + "\n\n" + fh.read().strip()
    except OSError:
        return HEAD


def run_kit(args, max_lines=MAX_LINES):
    """`lune run kit <args>` in the project root -> (text, is_error); max_lines=None returns the whole output (a skill
    page or the command list must arrive from its first line)"""
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return "args must be a list of strings", True
    try:
        # argument list, no shell: nothing in args is ever interpreted by a shell
        proc = subprocess.run(
            [find_lune(), "run", "kit", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    except FileNotFoundError:
        return "lune not found — install the toolchain (rokit install) and restart the harness", True
    except subprocess.TimeoutExpired:
        return "kit command timed out after 15 minutes", True
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    lines = out.rstrip().splitlines()
    if max_lines is not None and len(lines) > max_lines:
        lines = [f"... ({len(lines) - max_lines} earlier lines trimmed; full verdict in .verify/)"] + lines[-max_lines:]
    return "\n".join(lines) + f"\n(exit {proc.returncode})", proc.returncode != 0


def gate(args):
    """layer 3: a mutating pipeline command without a fresh session -> the refusal text (None = go on)"""
    import parallax_guard  # noqa: PLC0415
    from prompt import session  # noqa: PLC0415

    if not args or not isinstance(args, list):
        return None
    name, rest = args[0], args[1:]
    if name in parallax_guard.ALLOW or "--maintenance" in rest or (name == "asset" and rest[:1] == ["all"]):
        return None
    if name not in parallax_guard.MUTATING or (rest and rest[0] in parallax_guard.LOOKUP):
        return None
    if parallax_guard.mode() == "off":
        return None
    s = session.read(ROOT)
    g = parallax_guard.arg_game(rest)  # (the call's own --game decides, like the CLI's)
    problems = session.problems(s, None, ROOT, game=session.ACTIVE if g == parallax_guard.ACTIVE else g)
    lane = parallax_guard.MUTATING.get(name)
    if not problems and parallax_guard.covers(s, lane):
        return None
    if not problems:
        problems = [f"the session is for lane {(s or {}).get('lane')!r}, this is {lane} work"]
    lane = lane or "<lane>"
    nxt = json.dumps({"dept": lane, "prompt": "<the owner's request, word for word>"}
                     | ({} if g == parallax_guard.ACTIVE else {"game": g or "none"}))
    return (f"REFUSED by the Parallax gate: `{' '.join(args)}` is pipeline work and there is no fresh session "
            f"({'; '.join(problems)}).\nNext call: parallax_start with {nxt} (or parallax_prompt), then this call again.")


def call_tool(name, arguments):
    arguments = arguments or {}
    name = ALIASES.get(name, name)
    if name == "parallax_start":
        dept = arguments.get("dept")
        if dept not in LANES:
            return f"dept must be one of {', '.join(LANES)}", True
        stage, game, prompt = arguments.get("stage"), arguments.get("game"), arguments.get("prompt")
        return run_kit(["start", dept] + (["--stage", stage] if isinstance(stage, str) and stage else [])
                       + (["--game", game] if isinstance(game, str) and game else [])
                       + (["--prompt", prompt] if isinstance(prompt, str) and prompt.strip() else []))
    if name == "parallax_prompt":
        prompt = arguments.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return "prompt: the owner's request is needed", True
        args = ["prompt", "compile", prompt]
        for key in ("lane", "model", "piece"):
            if isinstance(arguments.get(key), str) and arguments[key]:
                args += [f"--{key}", arguments[key]]
        return run_kit(args)
    if name == "parallax_case":
        lane, words = arguments.get("lane"), arguments.get("words")
        if lane not in CASE_LANES or not isinstance(words, str) or not words.strip():
            return f"lane must be one of {', '.join(CASE_LANES)} and words the request", True
        return run_kit(["case", lane, words])
    if name == "parallax_skill":
        dept = arguments.get("dept")
        if dept not in LANES:
            return f"dept must be one of {', '.join(LANES)}", True
        return run_kit(["skill", dept], max_lines=None)  # (the recipe whole: its stages open the page)
    if name == "parallax_status":
        args = ["status"]
        if arguments.get("as"):
            args += ["--as", str(arguments["as"])]
        return run_kit(args)
    if name == "parallax_help":
        return run_kit(["help"], max_lines=None)
    if name == "parallax_verify":
        return run_kit(["verify"])
    if name == "parallax":
        refused = gate(arguments.get("args"))
        if refused:
            return refused, True
        return run_kit(arguments.get("args"))
    return f"unknown tool {name}", True


def respond(msg_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def handle(msg):
    method = msg.get("method")
    msg_id = msg.get("id")
    if msg_id is None:
        return  # notification (e.g. notifications/initialized): no response
    if method == "initialize":
        requested = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        respond(msg_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": "parallax", "version": VERSION},
            "instructions": instructions(),
        })
    elif method == "tools/list":
        respond(msg_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params") or {}
        text, is_error = call_tool(params.get("name"), params.get("arguments"))
        respond(msg_id, {"content": [{"type": "text", "text": text}], "isError": bool(is_error)})
    elif method == "prompts/list":
        respond(msg_id, {"prompts": [
            {
                "name": f"start-{lane}",
                "description": f"Start a {lane} lane session: load it with parallax_start and work only in that lane.",
            }
            for lane in LANES
        ]})
    elif method == "prompts/get":
        name = (msg.get("params") or {}).get("name")
        lane = name[len("start-"):] if isinstance(name, str) and name.startswith("start-") else None
        if lane not in LANES:
            respond(msg_id, error={"code": -32602, "message": f"unknown prompt: {name}"})
        else:
            respond(msg_id, {
                "description": f"Start a {lane} lane session: load it with parallax_start and work only in that lane.",
                "messages": [{
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f'You are the {lane} lane of this project. Call the parallax_start tool with dept '
                        f'"{lane}" first, act on its next_action, and work only on this department; leave every '
                        f"other department's files alone.",
                    },
                }],
            })
    elif method == "ping":
        respond(msg_id, {})
    else:
        respond(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            respond(None, error={"code": -32700, "message": "parse error"})
            continue
        try:
            handle(msg)
        except Exception as exc:  # never die mid-session: report and keep serving
            if msg.get("id") is not None:
                respond(msg.get("id"), error={"code": -32603, "message": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
