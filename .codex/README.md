# YouTube editorial agent skills (repository-local)

Installed from [Jakeschincariol/chatgpt-youtube-agent-skill](https://github.com/Jakeschincariol/chatgpt-youtube-agent-skill), pinned to upstream commit `6314d3c17dfa1e596096654204e8a09e28cdfd74`. Copyright and MIT permission notice are preserved in `YOUTUBE_AGENT_LICENSE.txt`.

Installed skills: `yt-audit`, `yt-chapters`, `yt-comment`, `yt-edit`, `yt-package`, `yt-plan`, `yt-retention`, `yt-script`, `yt-seo`, `yt-shorts`, `yt-viral`.

All original `skills/` files, including six standard-library Python scripts and `hooks.json`, are copied unmodified into `.codex/skills/`.

Use `.codex/youtube/voice.md` as the FPL VORTEX voice profile. The repository-root `AGENTS.md` tells Codex agents to use that profile for editorial tasks.

Examples (from repository root):
```sh
python3 .codex/skills/yt-script/hookscore.py --hook "Five FPL picks with secure minutes for the next gameweek"
python3 .codex/skills/yt-package/title.py --title "FPL Gameweek Value Board: 5 Smart Picks" --thumb "VALUE BOARD"
```

**Production protection:** no GitHub Actions files, active publishing scripts, credentials, posting schedules or video rendering files were modified. Installing skills does not make unattended GitHub Actions run them: production automation needs a separate reviewed integration.
