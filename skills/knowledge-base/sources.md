# Processing Source Materials

When the user shares source material (article, video transcript, podcast notes, book highlights):

## Step 1: Identify Key Concepts

Read the source material and identify concepts worth extracting as atomic notes.

## Step 2: Create Source Note

Create a source note in `sources/<type>/` (e.g., `sources/articles/`, `sources/youtube/`):

- Use `templates/source.md` format
- Include URL, title, summary
- Link to extracted concept notes

## Step 3: Create Concept Notes

Extract atomic concepts to appropriate folders:

- `knowledge/` for general facts
- `ideas/` for frameworks or theories
- `insights/` if the concept triggered personal realization

**Follow atomic note principles:**
- One concept per file
- Use domain prefixes in names
- Add wiki link tags at the bottom

## Step 4: Connect Notes

- Add backlinks from source note to concept notes
- Update related existing notes with links to new content
- Add MOC tags even if the MOC doesn't exist yet

## Source Note Format

Use the template but adapt as needed:

```markdown
---
aliases:
  - [Source Title]
source: [URL]
type: [youtube | article | book | podcast]
---

# [Source Title]

> **Source:** [URL]

## Summary

[Brief summary - key points and main thesis]

## Key Concepts

- [[concept-one]] — brief description
- [[concept-two]] — brief description

## Transcript / Highlights

[Full transcript or key highlights]

---

[[MOC-topic]] [[tag]]
```

## Important

- Connect user's personal reactions to the concepts where relevant
- Don't just summarize — extract actionable atomic notes
- Update existing notes with backlinks to new content
