---
kind: reference
area: shared
date: 2026-10-16
source: kit lessons kit + code, memory bash-heredoc-backslashes, windows-python-crlf
links: ["[[kit/index]]", "[[shared/commits-and-sessions]]"]
---

# Windows traps (every lane hits these)

- Python patches: `open(p, "w")` turns LF files into CRLF (text mode); `.luau` is `eol=lf`, so stylua `--check`
  fails on EVERY line while `git diff` looks clean (autocrlf hides it). Read and write BYTES (or `newline=""`),
  check with `git ls-files --eol`.
- A Python patch script written through a bash heredoc loses a backslash level (a doubled backslash arrives
  single): write patch scripts with the editor tool; ASSERT every old text is present before replacing (the
  formatter reflows long calls; an unasserted replace silently does nothing).
- Lune's `stdio.prompt` fails with "not a terminal" in an agent's shell even with piped stdin: owner-only acts
  (`kit grade`, `kit accept --lower`) can be started by a model in the owner's terminal but finished only by the
  owner's keystrokes. Never fake them.
- A server a kit command starts (a booth, a worker) dies when the command returns: Lune runs tools inside a Windows
  job killed on exit. Start it through WMI (`Invoke-CimMethod Win32_Process Create`) with a per-launch token and
  Host / Origin checks (any web page can POST to 127.0.0.1).
- Headless Edge hands the page to a child process and exits: kill by profile dir, use timers not rAF for `?shots=1`.
- Selene's last two lines are "N warnings" and "N parse errors"; the error COUNT is the line BEFORE — grep for
  "errors", never `tail -2`.
- Never pipe a gate into `tail` / `head` when the exit code matters.
- Python modules of different lanes share names (check.py, library.py, look.py, judge.py, plan.py, trace.py ...):
  the combined test run imports whichever loaded first. Unique names, or `importlib` by path under a unique name;
  a diagnostics script named like a kit module shadows it on sys.path.
- A kit step whose tool prints a huge JSON result line (~13 KB) fails with an EMPTY summary: keep result lines small.
- `pip download --no-binary` of an sdist RUNS its setup.py: vet sdists by fetching the file by URL, checking its
  sha256 and reading setup.py / pyproject.toml (dependencies included — FlexGEMM's pyproject pulled triton-windows).
- Python's `hash()` is salted per process (Blender ignores PYTHONHASHSEED): seed noise with `zlib.crc32`, never
  `hash(name)`.
