# YouTube editorial agent skills (repository-local)

Installed from [Jakeschincariol/chatgpt-youtube-agent-skill](https://github.com/Jakeschincariol/chatgpt-youtube-agent-skill), pinned to upstream commit `6314d3c17dfa1e596096654204e8a09e28cdfd74`. The license is retained in `.codex/YOUTUBE_AGENT_LICENSE.txt`.

**Use the 11 skills in `.agents/skills/` when working with Codex.** The same source files are retained in `.codex/skills/` for compatibility with the upstream installation instructions:
`yt-audit`, `yt-chapters`, `yt-comment`, `yt-edit`, `yt-package`, `yt-plan`, `yt-retention`, `yt-script`, `yt-seo`, `yt-shorts`, `yt-viral`.

Each location includes the six dependency-free Python utilities plus `yt-script/hooks.json`. The skill files are unchanged from upstream. The FPL VORTEX editorial profile is `.codex/youtube/voice.md` and repository directives are in `AGENTS.md`.

Command examples from repository root:
```sh
python3 .agents/skills/yt-script/hookscore.py --hook "Five FPL picks with secure minutes for the next gameweek"
python3 .agents/skills/yt-package/title.py --title "FPL Gameweek Value Board: 5 Smart Picks" --thumb "VALUE BOARD"
```

**Production safety:** This installation does not edit GitHub Actions, renderers, publishing code, credentials or schedules. For auto-generating scripts or titles during an Actions run, a separate reviewed integration must be made.
