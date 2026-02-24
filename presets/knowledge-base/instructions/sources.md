# Processing Source Materials

When the user shares source material (article, video, podcast) with their thoughts/reactions:

## Step 1: Create Source Note

Create source note in `sources/<type>/` using the source template (see `.claude/templates/source.md`):

- Include `{{transcript}}` placeholder for content that will be injected later
- Fill in metadata: URL, title, type

## Step 2: Create Notes Based on User's Reactions

**Only extract notes for concepts the user commented on or reacted to.**

Do NOT create notes for every idea in the source material. The user shares their thoughts for a reason — focus on what resonated with them.

- `knowledge/` — if user learned a new fact
- `insights/` — if it triggered personal realization
- `ideas/` — if user developed a new framework from it

## Step 3: Link Source to Notes

Update the source note's "Key Concepts" section to link to created notes.

## Important

- User's reactions guide what to extract — not the source content itself
- Templates are in `.claude/templates/`

## Music Sources

For music (artists, albums, tracks), use a hierarchical structure in `sources/music/`:

### Naming Pattern

- `artist-<primary-alias>.md` — one note per person, named by most established alias
- `album-<artist-slug>-<album-slug>.md` — album notes
- `track-<artist-slug>-<track-slug>.md` — individual track notes

### Artist Notes

For artists with multiple personas/aliases (e.g., Aphex Twin/AFX, Bumble Beezy/кровь из носа):
- Use **one artist note per person**, named by primary/most-known alias
- List all aliases in frontmatter
- Document projects/eras in the body with links to albums

```yaml
---
aliases:
  - Primary Alias
  - Secondary Alias
  - Real Name (if relevant)
type: artist
---
```

### Album/Track Notes

- Link to artist note using display text for the releasing alias: `[[artist-primary|releasing-alias]]`
- Include frontmatter with artist, album, track number
- Add "About" section with key lines/themes before lyrics

### When to Create Track Notes

Create individual track notes when:
- The track has personal relevance (resonates with user's experience)
- Lyrics contain quotable/linkable content
- Track is standalone single or needs separate reference

For casual references, album notes with tracklist may suffice.

### Fetching Lyrics

Use the **lyrics** skill to fetch lyrics from Genius:
```bash
uv run .claude/skills/lyrics/scripts/fetch-lyrics.py --artist "Artist" --song "Song"
```

## Source Credibility Assessment

When citing academic sources or research in knowledge notes, proactively check and report:

- **Citation count** — use Semantic Scholar, Google Scholar, or web search
- **Journal reputation** — Science, Nature = top-tier; check if peer-reviewed
- **Known critiques or controversies**
- **Replication status** if relevant (especially for psychology/social science)
- **Whether findings are consensus or contested**

Don't wait for user to ask — include credibility assessment when creating knowledge notes with external sources.
