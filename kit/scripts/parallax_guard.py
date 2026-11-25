"""parallax_guard.py - THE SCOPED ENFORCEMENT ENGINE (PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §2, §5.1 step 4): one file
every harness hook calls. Zero footprint when Parallax is not in use (a README edit, git status, pytest: exit 0, no
output), full enforcement the moment pipeline work starts.

    python kit/scripts/parallax_guard.py --hook pre-tool     Claude Code PreToolUse / Gemini BeforeTool (JSON on stdin)
    python kit/scripts/parallax_guard.py --hook post-tool    PostToolUse / AfterTool: track + anti-pattern scan
    python kit/scripts/parallax_guard.py --hook stop         Stop: one reminder for dirty pipeline work, never a loop
    python kit/scripts/parallax_guard.py --hook pre-commit [--maintenance "<why>"]   the git hook (staged files)
    python kit/scripts/parallax_guard.py --active '<event json>'   the predicate alone (prints true / false)

Exit codes (Claude Code's): 0 = go on; 2 = BLOCKED, stderr says why and the ONE command that unlocks it.
PARALLAX_ENFORCE (or KIT_ENFORCE) = enforce (default) | audit (say it, never block) | off (ignored by pre-commit unless
--maintenance "<why>" is given).

The 4-signal activation predicate (§2.2): A a mutating `lune run parallax|kit <cmd>` (or `python kit/<lane>/...`)
outside the bootstrap / read-only allowlist - wrappers unwrapped (env, timeout, nohup, time, xargs, PowerShell `&` and
Start-Process, pwsh / bash -c); B a call to the parallax (or roblox-kit) MCP server; C a write to a pipeline path
(assets/<kind>/, src/<kind>/, tests/playtest/, library/<kind>/ - at the root or under games/<Name>/, any case, any path
form: relative, C:/..., /c/... Git Bash, \\\\?\\ long paths, after a `cd`) or to a hard-protected one (generated models,
kit internals, the session token itself); D the session token (.verify/parallax_session.json). A shell that sets
PARALLAX_EXEMPT / *_ENFORCE is treated as tampering. Commands are split with their quoting respected and heredoc
bodies skipped (a commit message that says "lune run kit ui" is not a command).
Standard library only; the fast path (no pipeline word in the event) returns before any file is read.
"""

import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..")))

BLOCK = 2

# §2.2 the bootstrap + read-only + governance allowlist: never blocked (no bootstrap deadlock)
ALLOW = {
    "prompt", "start", "case", "kickoff", "game", "help", "--help", "-h", "status", "doctor", "verify", "selftest",
    "prove", "harness", "connect", "plan", "task", "handoff", "decide", "log", "lesson", "lessons", "verdict",
    "approve", "audit",
    "board", "review", "docs", "tools", "library", "vault", "examples", "skill", "version", "checks",
    "upgrade",
}
# the mutating commands (kit/lib/enforcer.luau MUTATING) and their lane
MUTATING = {"new": None, "asset": "3d", "make": "3d", "cad": "3d", "gen": "3d", "optimize": "3d", "vfx": "vfx",
            "anim": "anim", "world": "world", "ui": "ui", "sfx": "sfx", "move": "code", "net": "code", "upload": None}
LOOKUP = {"help", "list", "find", "catalog", "methods", "cost", "status", "--status", "--check", "--list"}
# python kit/<dir>/... : the pipeline tools (a lane) vs the kit's own plumbing (never a signal)
PY_LANE = {"blender": "3d", "tools": "3d", "gen": "3d", "vision": "3d", "vfx": "vfx", "anim": "anim", "world": "world",
           "ui": "ui", "audio": "sfx"}

PIPE_ASSETS = ("models", "effects", "animations", "worlds", "ui", "sounds", "net", "moves", "textures", "plans")
PIPE_SRC = ("models", "ui", "world", "animations", "net", "moves", "server", "client", "shared", "materials")
PIPE_LIB = ("vfx", "ui", "models", "sounds")
LANE_OF_ASSETS = {"models": "3d", "textures": "3d", "effects": "vfx", "animations": "anim", "worlds": "world",
                  "ui": "ui", "sounds": "sfx", "net": "code", "moves": "code", "plans": None}
LANE_OF_SRC = {"models": "3d", "ui": "ui", "world": "world", "animations": "anim", "net": "code", "moves": "code",
               "server": "code", "client": "code", "shared": "code", "materials": "world"}
# (matched on the lowercased path: Windows paths are case-insensitive)
GENERATED = (re.compile(r"^src/(ui|models|animations|world)/[^/]+\.model\.json$"), re.compile(r"^src/net/[^/]*net\.luau$"),
             re.compile(r"^src/moves/[^/]+\.luau$"))
KIT_INTERNAL = re.compile(r"^(kit|src/kit|parallax|src/parallax)/")
TOKEN_FILES = (".verify/parallax_session.json", ".verify/parallax_exempt.json")
NON_TRIGGER = re.compile(r"^(board|\.verify|build|_artifacts|_scratch|_downloads|\.git)/")
FAST_WORDS = ("kit", "parallax", "assets", "src", "tests", "library", "games", "roblox-kit", ".verify", "~", ".sh",
              ".ps1", ".bat", ".cmd", "eval")
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "write_file", "replace", "edit_file", "str_replace"}
SHELL_TOOLS = {"Bash", "PowerShell", "run_shell_command", "shell"}
TAMPER = re.compile(r"^(?:\$env:)?(?:PARALLAX|KIT)_(?:EXEMPT|ENFORCE)(?:=|$)", re.I)

ACTIVE, ANY = "<active>", "<any>"  # (a hit's game: the checkout's active game / no game check at all)


def env(name, default=None):
    for k in (f"PARALLAX_{name}", f"KIT_{name}"):
        v = os.environ.get(k)
        if v not in (None, ""):
            return v
    return default


def mode():
    m = env("ENFORCE", "enforce")
    return m if m in ("enforce", "audit", "off") else "enforce"


def repo_root(cwd=None):
    """the project the event is in: PARALLAX_ROOT, else the hook's own checkout"""
    return env("ROOT") or os.path.normpath(os.path.join(HERE, "..", ".."))


def _norm_abs(p):
    """C:\\x, //?/C:/x, \\\\?\\C:\\x, /c/x (Git Bash) -> 'c:/x' (lowercase drive), else the path with / separators"""
    p = str(p).replace("\\", "/")
    for pre in ("//?/", "//./"):
        if p.startswith(pre):
            p = p[len(pre):]
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)
    if m:
        p = f"{m.group(1)}:/{m.group(2)}"
    if re.match(r"^[A-Za-z]:/", p):
        p = p[0].lower() + p[1:]
    return p


def _clean_seg(seg):
    """one path segment as Windows reads it: no :stream suffix, no trailing dots or spaces"""
    if ":" in seg and not re.match(r"^[A-Za-z]:$", seg):
        seg = seg.split(":", 1)[0]
    return seg.rstrip(". ") if seg not in (".", "..") else seg


def _long(p):
    """an 8.3 short name (ASSETS~1) expanded by Windows itself (GetLongPathNameW); unchanged elsewhere / on failure"""
    if "~" not in p or os.name != "nt":
        return p
    try:
        import ctypes  # noqa: PLC0415

        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetLongPathNameW(p.replace("/", "\\"), buf, 1024)
        return buf.value if 0 < n < 1024 else p
    except (OSError, AttributeError, ValueError):
        return p


def rel_path(p, root, cwd=""):
    """a tool's path -> repo-relative with forward slashes ('' when it is outside the repo). cwd: the repo-relative
    folder a shell `cd`'d into before the path was named"""
    if not p:
        return ""
    p = _norm_abs(_long(str(p).strip().strip("\"'")))
    p = "/".join(_clean_seg(x) for x in p.split("/"))
    r = _norm_abs(root).rstrip("/")
    if re.match(r"^[a-z]:/", p) or p.startswith("/"):
        if p.lower().startswith(r.lower() + "/"):
            p = p[len(r) + 1:]
        else:
            return ""
    elif cwd:
        p = cwd.rstrip("/") + "/" + p
    parts = []
    for seg in p.split("/"):
        # (Windows: "assets." and "assets " are "assets"; "x.json::$DATA" / "x.json:s" are x.json's streams)
        if ":" in seg and not re.match(r"^[a-z]:$", seg):
            seg = seg.split(":", 1)[0]
        seg = seg.rstrip(". ") if seg not in (".", "..") else seg
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return ""
            parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def strip_game(rel):
    """games/<Name>/<path> -> (<path>, Name)"""
    m = re.match(r"^games/([^/]+)/(.*)$", rel, re.I)
    return (m.group(2), m.group(1)) if m else (rel, None)


def classify(rel):
    """a repo path -> (kind, lane): kind 'generated' | 'token' | 'kit' | 'pipeline' | None (no signal)"""
    if not rel:
        return None, None
    low = rel.lower()
    if low in TOKEN_FILES:
        return "token", None
    inner, _game = strip_game(low)
    if NON_TRIGGER.match(inner) or NON_TRIGGER.match(low):
        return None, None
    if "/" not in inner and inner.endswith(".md"):
        return None, None
    for g in GENERATED:
        if g.match(inner):
            return "generated", None
    if KIT_INTERNAL.match(inner):
        return "kit", "parallax"
    parts = inner.split("/")
    # an 8.3 short name (ASSETS~1) can name any folder: under the repo it is pipeline work until proven otherwise
    if any(re.search(r"~\d", x) for x in parts[:3]):
        return "pipeline", None
    if len(parts) >= 2:
        if parts[0] == "assets" and parts[1] in PIPE_ASSETS:
            return "pipeline", LANE_OF_ASSETS.get(parts[1])
        if parts[0] == "src" and parts[1] in PIPE_SRC:
            return "pipeline", LANE_OF_SRC.get(parts[1])
        if parts[0] == "library" and parts[1] in PIPE_LIB:
            return "pipeline", {"vfx": "vfx", "ui": "ui", "models": "3d", "sounds": "sfx"}[parts[1]]
        if parts[0] == "tests" and parts[1] == "playtest":
            return "pipeline", "qa"
    return None, None


SHELLS = ("pwsh", "powershell", "bash", "sh", "cmd", "zsh")
NESTED = "<parallax: shells / evals nested too deep>"


# the readers a heredoc body is DATA for (text, a commit message, a script in another language): anything else that
# receives one - a shell, eval, sudo, an unknown program - gets its body parsed as commands (fail closed)
DATA_READERS = ("cat", "tee", "git", "python", "python3", "py", "node", "lune", "jq", "sed", "awk", "less", "more",
                "sqlite3", "wc", "sort", "grep", "rg", "head", "tail")


def _heredoc_is_data(before):
    """the text of a line before its `<<WORD` -> True when the command that receives the body only reads it"""
    seg = re.split(r"\|\||&&|;|\|", before)[-1].strip()
    try:
        toks = shlex.split(seg.replace("\\", "/"), posix=True)
    except ValueError:
        return False
    t = _unwrap(toks)
    head = os.path.basename(t[0]).lower().removesuffix(".exe") if t else ""
    if head in DATA_READERS:
        return True
    return bool(re.match(r"^python[0-9.]*$", head))


def _strip_heredocs(cmd):
    """a shell script with its heredoc BODIES left out (their text is data, not commands)"""
    out, lines, i = [], (cmd or "").split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if m and not _heredoc_is_data(line[: m.start()]):
            m = None  # (a shell / eval / anything not known to only READ it: its body is parsed as commands)
        if m:
            end = m.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                i += 1
        i += 1
    return "\n".join(out)


def _newlines_to_semis(text):
    """unquoted newlines -> ';' (a quoted multi-line string - a commit message - stays one word)"""
    out, q = [], None
    for ch in text:
        if q:
            if ch == q:
                q = None
            out.append(ch)
        elif ch in "\"'":
            q = ch
            out.append(ch)
        elif ch == "\n":
            out.append(";")
        else:
            out.append(ch)
    return "".join(out)





def split_commands(cmd, depth=0):
    """a shell line -> its simple commands as token lists, quoting respected, heredoc bodies skipped, `pwsh -c "..."`
    / `bash -c "..."` unwrapped"""
    if depth > 8:  # (nested shells / evals past any real use: a hard block no session unlocks)
        return [[NESTED]]
    text = _newlines_to_semis(_strip_heredocs(cmd or "").replace("\\", "/"))
    try:
        lx = shlex.shlex(text, posix=True, punctuation_chars=";&|")
        lx.whitespace_split = True
        toks = list(lx)
    except ValueError:
        toks = text.replace(";", " ; ").split()
    out, cur = [], []
    for t in toks:
        if t and set(t) <= set(";&|"):
            if cur:
                out.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur:
        out.append(cur)
    flat = []
    for c in out:
        u = _unwrap(list(c))
        if c and os.path.basename(c[0]).lower() == "eval" and len(c) > 1:
            flat += split_commands(" ".join(c[1:]), depth + 1)  # (eval's words are a command line of their own)
            continue
        exe = os.path.basename(u[0]).lower().removesuffix(".exe") if u else ""
        if exe in SHELLS:
            for k in range(1, len(c) - 1):
                if c[k].lower() in ("-c", "-command", "/c"):
                    flat += split_commands(" ".join(c[k + 1:]), depth + 1)
                    break
            else:
                flat.append(c)
            continue
        flat.append(c)
    return flat


def _unwrap(t):
    """take the wrappers off a command's tokens: VAR=x, env [-u X], timeout [opts] N, time, nohup, xargs [opts],
    PowerShell `&` and Start-Process [-FilePath] X [-ArgumentList "..."]"""
    changed = True
    while changed and t:
        changed = False
        while t and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t[0]):
            t, changed = t[1:], True
        head = os.path.basename(t[0]).lower().removesuffix(".exe") if t else ""
        if head == "env":
            t, changed = t[1:], True
            while t and (t[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t[0])):
                t = t[2:] if t[0] in ("-u", "--unset", "-C", "--chdir") else t[1:]
        elif head in ("timeout", "gtimeout"):
            t, changed = t[1:], True
            while t and t[0].startswith("-"):
                t = t[2:] if t[0] in ("-k", "-s", "--signal", "--kill-after") else t[1:]
            if t and re.match(r"^\d+(\.\d+)?[smhd]?$", t[0]):
                t = t[1:]
        elif head in ("time", "nohup", "command", "exec", "sudo"):
            t, changed = t[1:], True
        elif head == "xargs":
            t, changed = t[1:], True
            while t and t[0].startswith("-"):
                t = t[2:] if t[0] in ("-I", "-n", "-P", "-d", "-L", "-s") else t[1:]
        elif head == "&":
            t, changed = t[1:], True
        elif head == "start-process":
            rest, exe, args = t[1:], None, []
            i = 0
            while i < len(rest):
                a = rest[i]
                if a.lower() in ("-filepath",) and i + 1 < len(rest):
                    exe, i = rest[i + 1], i + 2
                    continue
                if a.lower() in ("-argumentlist", "-args") and i + 1 < len(rest):
                    args += rest[i + 1].replace(",", " ").split()
                    i += 2
                    continue
                if a.startswith("-"):
                    i += 2 if i + 1 < len(rest) and not rest[i + 1].startswith("-") else 1
                    continue
                if exe is None:
                    exe = a
                else:
                    args += a.replace(",", " ").split()
                i += 1
            t, changed = ([exe] + args) if exe else [], True
    return t


def kit_command(tokens):
    """`lune run kit|parallax <cmd> args...` (wrappers unwrapped) -> (cmd, args) or None"""
    t = _unwrap(list(tokens))
    if len(t) >= 3 and os.path.basename(t[0]).lower() in ("lune", "lune.exe") and t[1] == "run":
        target = t[2].rstrip("/").removeprefix("./").lower()
        if target in ("kit", "parallax", "parallax.luau", "kit/init.luau", "kit/init"):
            return (t[3] if len(t) > 3 else "help"), t[4:]
    return None


SCRIPT_EXT = (".sh", ".bash", ".ps1", ".bat", ".cmd")


def repo_script(tokens, root, cwd=""):
    """`sh x.sh`, `bash x.sh`, `source x.sh`, `. x.sh`, `./x.sh`, `pwsh -File x.ps1` run a script whose lines the guard
    never sees: a script inside the repo is pipeline work (it needs a session) -> its path or None"""
    t = _unwrap(list(tokens))
    if not t:
        return None
    head = os.path.basename(t[0]).lower().removesuffix(".exe")
    cand = None
    if head in ("sh", "bash", "zsh", "source", ".", "pwsh", "powershell", "cmd"):
        rest = [a for a in t[1:] if not a.startswith("-") and a.lower() not in ("/c",)]
        if rest and rest[0].lower().endswith(SCRIPT_EXT):
            cand = rest[0]
    elif t[0].lower().endswith(SCRIPT_EXT):
        cand = t[0]
    if not cand:
        return None
    r = rel_path(cand, root, cwd)
    if not r:
        return None
    return r


def python_lane(tokens):
    """`python kit/<lane-dir>/x.py ...` -> its lane, None for the kit's plumbing or anything else"""
    t = _unwrap(list(tokens))
    if t and re.match(r"^(python[0-9.]*|py)(\.exe)?$", os.path.basename(t[0]).lower()):
        for a in t[1:]:
            if a.startswith("-"):
                continue
            m = re.match(r"^(?:\./)?(?:kit|parallax)/([^/]+)/", a)
            return PY_LANE.get(m.group(1)) if m else None
    return None


WRITE_VERBS = {"tee", "rm", "touch", "sed", "set-content", "add-content", "out-file", "new-item", "remove-item",
               "copy-item", "move-item", "cp", "mv", "truncate", "dd", "install", "ln", "curl", "wget", "git"}


def shell_writes(tokens, root, cwd=""):
    """the repo paths a simple command writes (redirections, tee, touch, sed -i, cp/mv targets, Set-Content, curl -o,
    git add / rm / mv / checkout --) -> [rel]"""
    out = []
    for k, tok in enumerate(tokens):
        m = re.match(r"^\d?>{1,2}(.*)$", tok)
        if m:
            if m.group(1):
                out.append(m.group(1))
            elif k + 1 < len(tokens):
                out.append(tokens[k + 1])
    t = _unwrap(list(tokens))
    verb = os.path.basename(t[0]).lower().removesuffix(".exe") if t else ""
    if verb in WRITE_VERBS:
        args = t[1:]
        plain = [a for a in args if not a.startswith("-")]
        if verb in ("mv", "move-item") and plain:
            out += plain  # (the sources disappear: a write to their paths too)
        elif verb in ("cp", "copy-item", "install", "ln") and plain:
            out.append(plain[-1])
        elif verb in ("curl", "wget"):
            for i, a in enumerate(args):
                if a in ("-o", "--output", "-O", "--output-document") and i + 1 < len(args):
                    out.append(args[i + 1])
        elif verb == "git":
            if args[:1] and args[0] in ("add", "rm", "mv", "checkout", "restore"):
                out += [a for a in args[1:] if not a.startswith("-")]
        elif verb == "sed":
            if any(a.startswith("-i") for a in args):
                out += plain[1:]
        else:
            for i, a in enumerate(args):
                if a.lower() in ("-path", "-filepath", "-literalpath", "-destination") and i + 1 < len(args):
                    out.append(args[i + 1])
            out += plain
    rels = []
    for p in out:
        r = rel_path(p, root, cwd)
        if r:
            rels.append(r)
    return rels


def path_game(kind, rel):
    """the game a path belongs to: games/<Name>/... is Name, a root path is the project root (None), the kit's own
    files belong to no game (a hook process has no --game: games/.active must not decide a kit edit)"""
    if kind in ("kit", "token"):
        return ANY
    return strip_game(rel)[1]


def arg_game(args):
    """a command's own --game <Name> (none = the project root), else the active game"""
    if "--game" in args:
        i = args.index("--game")
        g = args[i + 1] if i + 1 < len(args) else "none"
        return None if g in ("none", "") else g
    return ACTIVE


def unlock(lane, game=ACTIVE):
    g = "" if game in (ACTIVE, ANY) else f" --game {game or 'none'}"
    return f'lune run parallax start {lane or "<lane>"} --prompt "<the owner\'s request>"{g}'


def covers(s, lane):
    """does the session cover this lane? (its lane, its contracts' lanes, its PROMPT-X lanes; kit / parallax cover
    every lane; code and qa go together)"""
    if not lane or not s:
        return True
    own = {s.get("lane")} | {c.get("lane") for c in s.get("case_contracts") or []}
    for lane_name in s.get("lanes") or []:
        own |= {"code", "qa"} if lane_name == "systems" else {lane_name}
    if own & {"kit", "parallax"}:
        return True
    if lane in ("code", "qa") and own & {"code", "qa"}:
        return True
    return lane in own


def _cd_target(t):
    """`cd X` / `Set-Location X` / `pushd X` -> X"""
    if t and os.path.basename(t[0]).lower() in ("cd", "set-location", "pushd", "sl", "chdir") and len(t) > 1:
        return t[-1]
    return None


def is_parallax_active(event, root=None):
    """§2.2 -> (active, reasons, hits). hits: [(signal, kind, lane, what, game)]. Fast exit before any file is read
    when the event names no pipeline word."""
    root = root or repo_root()
    tool = event.get("tool_name") or ""
    ti = event.get("tool_input") or {}
    blob = json.dumps(ti) if isinstance(ti, dict) else str(ti)
    if tool.startswith("mcp__parallax") or tool.startswith("mcp__roblox-kit"):
        return True, ["B: the parallax MCP server"], [("B", "mcp", None, tool, ACTIVE)]
    low_blob = blob.lower()
    if not any(w in low_blob for w in FAST_WORDS):
        return False, [], []
    hits = []
    if isinstance(ti, dict):
        for key in ("file_path", "notebook_path", "path"):
            r = rel_path(ti.get(key), root) if ti.get(key) else ""
            kind, lane = classify(r)
            if kind:
                hits.append(("C", kind, lane, r, path_game(kind, r)))
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if isinstance(cmd, str) and cmd:
        cwd, shell_game = "", ACTIVE
        for toks in split_commands(cmd):
            if toks == [NESTED]:
                hits.append(("A", "nested", None, NESTED, ANY))
                continue
            # the game the line itself names: `export KIT_GAME=none`, an inline `KIT_GAME=X cmd`, `--game X`
            for x in toks[:4]:
                m = re.match(r"^(?:PARALLAX|KIT)_GAME=(.*)$", x)
                if m:
                    g = m.group(1).strip("\"'")
                    shell_game = None if g in ("", "none") else g
            if toks and toks[0] in ("export", "set") and len(toks) == 2 and re.match(r"^(PARALLAX|KIT)_GAME=", toks[1]):
                continue
            if any(TAMPER.match(x) for x in toks[:6]) or any(
                    x.lower().startswith(("$env:parallax_exempt", "$env:kit_enforce", "$env:parallax_enforce"))
                    for x in toks):
                hits.append(("A", "tamper", None, " ".join(toks[:4]), ANY))
            target = _cd_target(_unwrap(list(toks)))
            if target is not None:
                r = rel_path(target, root, cwd)
                cwd = r if (r or target in (".", "./")) else cwd
                continue
            kc = kit_command(toks)
            if kc:
                name, args = kc
                if name in ALLOW or "--maintenance" in args or (name == "asset" and args[:1] == ["all"]):
                    continue
                if name in MUTATING and not (args and args[0] in LOOKUP):
                    g = arg_game(args)
                    hits.append(("A", "cli", MUTATING[name], f"{name} {' '.join(args[:3])}".strip(),
                                 shell_game if g == ACTIVE else g))
                continue
            sc = repo_script(toks, root, cwd)
            if sc:
                hits.append(("A", "script", None, sc, shell_game))
                continue
            pl = python_lane(toks)
            if pl:
                hits.append(("A", "python", pl, " ".join(toks[:3])[:80], shell_game))
                continue
            # STAGING a generated file the kit rebuilt is how its output is committed - not a hand edit: `git add`
            # pathspecs (and only those, in a command with no redirection) are pipeline work for the lane whose
            # generator owns them; a redirect target, git rm or any other write to one stays the hard block
            un = _unwrap(list(toks))
            staged_specs = set()
            if un[:2] == ["git", "add"] and not any(re.match(r"^\d?>", x) for x in toks):
                staged_specs = {rel_path(a, root, cwd) for a in un[2:] if not a.startswith("-")}
            for r in shell_writes(toks, root, cwd):
                kind, lane = classify(r)
                if kind == "generated" and r in staged_specs:
                    kind = "pipeline"
                    lane = LANE_OF_SRC.get(strip_game(r.lower())[0].split("/")[1]) if "/" in r else None
                if kind:
                    hits.append(("C", kind, lane, r, path_game(kind, r)))
    return bool(hits), [f"{h[0]}: {h[3]}" for h in hits], hits


def _say_block(lines):
    sys.stderr.write("\n".join(lines) + "\n")
    if mode() == "audit":
        sys.stderr.write("(PARALLAX_ENFORCE=audit: not blocked)\n")
        return 0
    return BLOCK


def _problems(session, s, event, root, game):
    return session.problems(s, event.get("session_id"), root,
                            game=session.ANY if game == ANY else (session.ACTIVE if game == ACTIVE else game))


def pre_tool(event, root=None):
    root = root or repo_root()
    active, _reasons, hits = is_parallax_active(event, root)
    if not active:
        return 0
    from prompt import session  # noqa: PLC0415  (only once a signal fired: off the fast path)

    s = session.read(root)
    for signal, kind, lane, what, game in hits:
        if kind == "generated":
            return _say_block([f"[parallax] BLOCKED: {what} is GENERATED - never hand-edited.",
                               "Change its input under assets/ and rebuild it (lune run parallax ui | models | anim | world | net | moves)."])
        if kind == "nested":
            return _say_block([f"[parallax] BLOCKED: {what}: more than 8 levels of shell / eval wrapping is never "
                               "needed - run the command plainly."])
        if kind == "token":
            return _say_block([f"[parallax] BLOCKED: {what} is the Parallax session token: only PROMPT-X writes it.",
                               "Unlock the honest way: " + unlock("<lane>", None)])
        problems = _problems(session, s, event, root, game)
        if kind in ("kit", "tamper"):
            if problems or (s or {}).get("lane") not in ("parallax", "kit"):
                why = "; ".join(problems) if problems else f"the session's lane is {(s or {}).get('lane')!r}"
                body = ("is the kit's own engine (kit/, src/kit/)" if kind == "kit"
                        else "sets the Parallax gate's own switches (PARALLAX_EXEMPT / *_ENFORCE)")
                return _say_block([f"[parallax] BLOCKED: {what} {body}: only a parallax / kit lane session may ({why}).",
                                   "Unlock: " + unlock("kit", None)])
            continue
        if signal == "B":
            if problems:
                return _say_block([f"[parallax] BLOCKED: the parallax MCP server needs a session: {'; '.join(problems)}.",
                                   "Unlock (one line): " + unlock(lane, game)])
            continue
        if problems:
            return _say_block([f"[parallax] BLOCKED: {what} is pipeline work ({'signal ' + signal}) and there is no "
                               f"fresh Parallax session for it: {'; '.join(problems)}.",
                               "Unlock (one line): " + unlock(lane, game)])
        if not covers(s, lane):
            return _say_block([f"[parallax] BLOCKED: {what} is {lane} work; this session is for lane {s.get('lane')!r} "
                               f"(cases {', '.join(c.get('case_id', '?') for c in s.get('case_contracts') or []) or 'none'}).",
                               "Unlock (one line): " + unlock(lane, game)])
    return 0


def post_tool(event, root=None):
    root = root or repo_root()
    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return 0
    rel = ""
    for key in ("file_path", "notebook_path", "path"):
        rel = rel_path(ti.get(key), root) if ti.get(key) else ""
        if rel:
            break
    kind, _lane = classify(rel)
    if kind not in ("pipeline", "kit"):
        return 0
    from prompt import cases, session  # noqa: PLC0415

    s = session.read(root)
    game = path_game(kind, rel)
    if s and not _problems(session, s, event, root, game):
        session.log("touched_pipeline_files", rel, root)
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return 0
    hits = cases.scan_text(strip_game(rel)[0], text)  # (the kit's own registries, wherever the project is)
    blocks = [h for h in hits if h["severity"] == "block"]
    for h in hits:
        sys.stderr.write(f"[parallax] {h['severity'].upper()} {rel} ({h['case_id']}): {h['message']}\n")
    if blocks:
        return _say_block([f"[parallax] fix {rel} now: {len(blocks)} case anti-pattern(s) above."])
    return 0


def stop(event, root=None):
    # FIRST: a Stop hook that blocks makes Claude Code run again; on that run stop_hook_active is true - never loop
    if event.get("stop_hook_active"):
        return 0
    root = root or repo_root()
    from prompt import session  # noqa: PLC0415

    s = session.read(root)
    # (any game: the paths it touched were judged per path when they were tracked)
    if not s or session.problems(s, event.get("session_id"), root, game=session.ANY):
        return 0
    touched = s.get("touched_pipeline_files") or []
    if not touched or s.get("verify_passed_at") or s.get("handoff_written_at") or s.get("reminded_at"):
        return 0
    s["reminded_at"] = session.now_iso()
    session.write(s, root)
    reason = (f"Parallax: this session changed {len(touched)} pipeline file(s) ({', '.join(touched[:4])}"
              f"{' ...' if len(touched) > 4 else ''}) with no passing `lune run parallax verify` and no "
              f"`lune run parallax handoff`. Prove it (verify) and hand off before stopping - or say why not.")
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def staged(root):
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD", "-z"], cwd=root,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return [f for f in out.split("\0") if f]


def staged_text(rel, root):
    p = subprocess.run(["git", "show", f":{rel}"], cwd=root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.stdout if p.returncode == 0 else None


# the paths `parallax harness` writes or reads: a commit touching none of them cannot make the harness stale
HARNESS_PATHS = re.compile(r"^(kit/skills/|kit/harness/|kit/knowledge/cases/|kit/lib/harness\.luau$|AGENTS\.md$|"
                           r"CLAUDE\.md$|GEMINI\.md$|\.claude/|\.agents/|\.cursor/|\.opencode/|\.roo/|\.windsurf/|"
                           r"\.clinerules|\.gemini/|\.vscode/|\.github/copilot|opencode\.json$|\.mcp\.json$)")


def harness_check(root):
    """`parallax harness --check` -> (ok, text). A missing lune, or a check that hangs, is not a refusal."""
    import shutil  # noqa: PLC0415

    lune = shutil.which("lune") or os.path.join(os.path.expanduser("~"), ".rokit", "bin", "lune.exe")
    if not os.path.isfile(lune) and not shutil.which("lune"):
        return True, "lune not found: harness check skipped"
    e = dict(os.environ, KIT_GAME="none", PARALLAX_GAME="none")
    try:
        p = subprocess.run([lune, "run", "kit", "harness", "--check"], cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=e, timeout=120)
    except (OSError, subprocess.SubprocessError) as ex:
        return True, f"harness check skipped: {type(ex).__name__}"
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def pre_commit(argv, root=None, files=None, check_harness=True):
    root = root or repo_root()
    maint = None
    if "--maintenance" in argv:
        i = argv.index("--maintenance")
        maint = argv[i + 1] if i + 1 < len(argv) else ""
    if mode() == "off" and maint:
        return 0
    from prompt import cases  # noqa: PLC0415

    paths = staged(root) if files is None else files
    problems = []
    for rel in paths:
        kind, _lane = classify(rel)
        if kind == "pipeline":
            text = staged_text(rel, root) if files is None else _read(root, rel)
            if text is None:
                continue
            for h in cases.scan_text(strip_game(rel)[0], text):
                if h["severity"] == "block":
                    problems.append(f"{rel} ({h['case_id']}): {h['message']}")
    # (only a commit that touches what the harness writes or reads can be stale against it: a docs-only commit is
    # never refused for another session's skill edit)
    if check_harness and any(HARNESS_PATHS.match(p.replace("\\", "/")) for p in paths):
        ok, text = harness_check(root)
        if not ok:
            problems.append("the harness files are out of step with the kit (parallax harness --check): "
                            + " | ".join(text.splitlines()[-4:]) + " -> run: lune run parallax harness")
    if problems:
        print("pre-commit (parallax): refused -")
        for p in problems:
            print("  - " + p)
        return 1
    return 0


def _read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def read_event():
    try:
        data = sys.stdin.read()
        return json.loads(data) if data.strip() else {}
    except (ValueError, OSError):
        return {}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--active" in argv:
        i = argv.index("--active")
        ev = json.loads(argv[i + 1]) if i + 1 < len(argv) else read_event()
        active, reasons, _ = is_parallax_active(ev)
        print(json.dumps({"active": active, "reasons": reasons}))
        return 0
    hook = argv[argv.index("--hook") + 1] if "--hook" in argv and argv.index("--hook") + 1 < len(argv) else None
    if hook == "pre-commit":
        return pre_commit(argv)
    if mode() == "off":
        return 0
    try:
        ev = read_event()
        if hook == "pre-tool":
            return pre_tool(ev)
        if hook == "post-tool":
            return post_tool(ev)
        if hook == "stop":
            return stop(ev)
    except Exception as e:  # noqa: BLE001  (a broken guard never stops the agent's work: it says so)
        sys.stderr.write(f"[parallax] the guard crashed (not blocking): {type(e).__name__}: {e}\n")
        return 0
    sys.stderr.write("usage: parallax_guard.py --hook pre-tool|post-tool|stop|pre-commit\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
