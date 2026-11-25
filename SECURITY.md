# Security

## Reporting a problem

Please report security issues privately: on GitHub, open the repository's **Security** tab and choose
**Report a vulnerability**. If that option is not available, open an issue asking for a private contact - without the
details. Please do not post an exploit publicly before it is fixed.

## How Parallax keeps a game and your machine safe

- **The server is the authority.** Every system the kit writes has clients ask through remotes; the server
  rate-limits (`RateLimit`), validates every argument (`Guard`), applies the rules and only then acts. `kit audit`
  fails on an unvalidated remote argument, an unthrottled handler, and the classic backdoors (`require(<asset id>)`,
  `loadstring`, `getfenv` / `setfenv`) in your code and in any free model or plugin you import.
- **Uploads are screened first.** Every file `kit upload` would send is screened (banned words, blood); one held file
  stops the whole upload. On the Studio route the kit writes the exact call for each screened file and your AI client
  sends it; `upload --record` refuses a file whose SHA-256 changed since it was screened. The kit cannot see what the
  client actually sends, so connect a client you trust (the API-key route sends the files itself).
- **No keys to leak.** Uploads go through the Roblox Studio MCP with your own Studio login and the Open Cloud
  permissions you grant per game. The kit never asks for, prints or stores a key; the optional headless route reads
  `ROBLOX_API_KEY` from the environment (on Windows, also from your saved user environment variables).
- **Local-first.** Every model and tool runs on your machine. Each download is checked against two independent
  sources, its licence and its install script, and recorded with its hash in [VETLOG.md](VETLOG.md).
- **Guard rails for agents.** Pipeline work is refused without a lane session (MCP server and CLI); git hooks refuse
  commits that break a case's contract; escape hatches are logged for your review.

## What you control

- Roblox Studio's **MCP Permissions** decide what any MCP client may do through Open Cloud - grant only what a task
  needs, per game.
- Connect only AI clients you trust, and read `git diff` before accepting large changes.
- Do not run an AI client with every permission check bypassed.
