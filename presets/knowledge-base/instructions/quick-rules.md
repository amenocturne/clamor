## Quick Rules

- **YouTube URLs**: Never use WebFetch. Use the **youtube** skill to fetch transcripts.
- **No subtitles?**: Download audio with `uvx yt-dlp -x --audio-format mp3 -o "tmp/%(id)s.%(ext)s" <url>` and use the **transcribe** skill.
- **No auto memory**: Do not use `~/.claude/projects/*/memory/`. Store all persistent knowledge in this vault.
- **tmp/ folder**: Scripts output to `tmp/` inside the vault root. This folder is gitignored.
- **Graph analysis**: Use the **graph** skill with `--exclude=logs,tmp,archive` to analyze the knowledge graph.
- **Project specs**: Use the **spec** skill to create technical specs. Save to `projects/software/<project-name>/`. Specs are the source of truth passed to dev-workspace for implementation.
