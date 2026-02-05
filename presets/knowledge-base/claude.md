## Knowledge Base Mode

You are managing an Obsidian vault with atomic notes following zettelkasten principles.

### Key Conventions

- **Atomic notes**: One concept per file, brief content
- **Wiki links**: Use `[[links]]` for connections, no #tags
- **Meaningful links**: Each link needs context explaining why
- **Unique names**: Search before creating to avoid collisions

### Folder Structure

- `core/` — stable identity facts
- `ideas/` — personal theories and frameworks
- `insights/` — personal realizations
- `knowledge/` — general facts
- `projects/` — actionable plans
- `sources/` — source material with transcripts
- `logs/` — conversation summaries

### Source Materials

When user shares a YouTube video or article with their thoughts:
1. Extract content to `tmp/` using appropriate script
2. Create source note with `{{transcript}}` placeholder
3. Run inject script to copy content
4. Create notes only for concepts user reacted to

### Saving Conversations

When user says "save", "wrap up", etc.:
1. Create atomic notes first
2. Create summary in `logs/YYYY-MM-DD/_Topic.md` that links to notes
3. Hook will rename and commit on Stop
