---
name: spec
description: Technical specification generator. Use when user has a project idea and wants to plan before coding, create a spec, or write an implementation plan. Triggers on "write a spec", "create specification", "plan this project", "implementation plan", "design document", "spec.md".
author: amenocturne
---

# Project Spec Generator

Create technical specifications from project ideas.

## Process

1. **Clarify requirements**
   - Ask about unclear points
   - Suggest features they might have missed
   - Explore naming ideas if relevant

2. **Determine output location**
   - Ask the user where to save the spec files

3. **Create spec files**

   **Main spec** (`spec.md`):
   - One-line description
   - Core features (bullet list)
   - User flow (numbered steps)
   - Tech stack
   - Project structure
   - Data schema (SQL or types)
   - Config format (if applicable)
   - CLI commands (if applicable)
   - Open decisions

   **Implementation plan** (`implementation-plan.md`):
   - MVP scope (in/out)
   - UI design (if applicable): color palette, vibe, shortcuts
   - Task breakdown (numbered, with files to create)
   - Definition of done

4. **Keep specs concise**
   - Code examples > prose
   - Tables for structured info
   - No verbose explanations

## Style

- Ask clarifying questions early, don't assume
- Suggest creative names when naming comes up
- If user shares visual inspiration, incorporate into design spec

## Tech Stack

If user has preferences file or mentions preferences, apply them. Otherwise ask about:
- Language/runtime
- Framework preferences
- Database choice
- Deployment target
