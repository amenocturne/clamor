# Processing Source Materials

When the user shares source material (article, video, podcast) with their thoughts/reactions:

## Step 1: Extract Content

Use appropriate tool to extract content to `tmp/`:

- **YouTube**: `uv run scripts/yt-subs.py <url>` → saves to `tmp/<video_id>.txt`
- **Articles**: save text content to `tmp/<slug>.txt`

Do NOT read the full content into context — it wastes tokens.

## Step 2: Create Source Note

Create source note in `sources/<type>/` using `templates/source.md`:

- Include `{{transcript}}` placeholder (do NOT paste content manually)
- Fill in metadata: URL, title, type

## Step 3: Inject Content

Run inject script to copy content from tmp to source note:

```bash
uv run scripts/inject-transcript.py sources/youtube/<note-name>.md
```

This replaces `{{transcript}}` with formatted content and deletes tmp file.

## Step 4: Create Notes Based on User's Reactions

**Only extract notes for concepts the user commented on or reacted to.**

Do NOT create notes for every idea in the source material. The user shares their thoughts for a reason — focus on what resonated with them.

- `knowledge/` — if user learned a new fact
- `insights/` — if it triggered personal realization
- `ideas/` — if user developed a new framework from it

## Step 5: Link Source to Notes

Update the source note's "Key Concepts" section to link to created notes.

## Important

- User's reactions guide what to extract — not the source content itself
- Don't paste transcripts manually — use the inject script
- Templates live in `templates/` folder
