## Commit Style

- Write concise commit messages (1-2 sentences)
- Focus on "why" not "what"
- No Co-Authored-By lines
- No emoji prefixes unless project uses them

## Code Style

- Prefer functional style: pure functions, immutability, composition
- Avoid classes unless the codebase already uses them
- Early returns over nested conditionals
- Descriptive names over comments

## Comments

- Only comment non-obvious logic or important design decisions
- Explain "why" not "what" - the code shows what, comments explain reasoning
- Never leave development artifacts: "fixed because X didn't work", "TODO: clean up"
- Good: "Using mutex here because X is accessed from multiple goroutines"
- Bad: "Changed from channel to mutex because deadlock occurred"

## Communication

- Be direct, skip pleasantries
- Lead with the key insight
- Admit uncertainty explicitly
