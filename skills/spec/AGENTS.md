# Project Spec Generator

Create technical specifications from project ideas. The user will dump their ideas and requirements.

## Process

1. **Clarify through conversation**
   - Ask about unclear requirements
   - Suggest features they might have missed
   - Explore naming ideas if the user enjoys wordplay names

2. **Create project spec**
   - `_project-[name].md` — technical spec:
     - One-line description
     - Core features (bullet list)
     - User flow (numbered steps)
     - Tech stack
     - Project structure
     - Data schema (SQL or types)
     - Config format
     - CLI commands (if applicable)
     - Open decisions
   - `implementation-plan.md` — task breakdown for implementation:
     - MVP scope (in/out)
     - UI design (if applicable): color palette, vibe, keyboard shortcuts, animations
     - Agent workflow instructions
     - Task breakdown (numbered, with files to create, tests, commit message)
     - Definition of done

3. **Keep specs concise**
   - No verbose explanations
   - Code examples > prose
   - Tables for structured info

## Style

- Ask clarifying questions early, don't assume
- Suggest creative/wordplay names when naming comes up
- If user mentions visual inspiration (images, apps), incorporate into design spec

## Tech Stack Questions

If the user has preferences (stored in a project-preferences file or mentioned verbally), apply them. Otherwise, ask about:
- Language/runtime (Node, Bun, Python, etc.)
- Framework preferences
- Database choice
- Deployment target

## Output Location

Ask the user where to save the spec, or create in `projects/<name>/` if they have a projects folder.
