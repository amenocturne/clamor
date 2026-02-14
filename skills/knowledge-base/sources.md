# Processing Source Materials

When the user shares source material (article, video, podcast) with their thoughts/reactions:

## Step 1: Extract Content

Use the appropriate skill to extract content:

- **YouTube**: Use the **youtube** skill to fetch the transcript
- **Audio** (no subtitles available): Use the **transcribe** skill
- **Articles**: Save text content to `tmp/<slug>.txt`

Do NOT read the full content into context — it wastes tokens.

## Step 2: Create Source Note

Create source note in `sources/<type>/` using `templates/source.md`:

- Include `{{transcript}}` placeholder (do NOT paste content manually)
- Fill in metadata: URL, title, type

## Step 3: Inject Content

Use the **youtube** skill's inject script to copy content from tmp into the source note. This replaces `{{transcript}}` with formatted content and deletes the tmp file.

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
- Templates live in the `templates/` folder within this skill

## Source Credibility Assessment

When citing academic sources or research in knowledge notes, proactively check and report:

- **Citation count** — use Semantic Scholar, Google Scholar, or web search
- **Journal reputation** — Science, Nature = top-tier; check if peer-reviewed
- **Known critiques or controversies**
- **Replication status** if relevant (especially for psychology/social science)
- **Whether findings are consensus or contested**

Don't wait for user to ask — include credibility assessment when creating knowledge notes with external sources.
