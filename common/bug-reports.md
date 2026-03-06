## Bug Reports

When the user reports a bug, **do not start fixing immediately**. Follow this protocol:

### 1. Clarify First

If the report is ambiguous, ask targeted questions before touching code:
- **What do you see?** (the actual visual/behavioral result)
- **What did you expect?** (the correct behavior)
- **When does it happen?** (steps to reproduce, which states trigger it)
- **Where exactly?** (specific element, file, line, area of the screen)

### 2. Restate the Bug

Before proposing a fix, describe the bug back in your own words:
> "So the issue is: [your understanding]. Is that right?"

Only proceed after confirmation. Getting this wrong wastes significant time — a misunderstood bug leads to fixing the wrong thing, which compounds with each iteration.

### 3. Diagnose Before Fixing

- Form a hypothesis about the root cause
- Verify it with evidence (read code, check data, use tools)
- If the hypothesis doesn't hold, form a new one — don't cargo-cult fixes
- For visual bugs: use Playwright or browser tools to see exactly what the user sees

### Common Pitfalls

- **"Line numbers duplicated"** could mean: actual number duplication, content duplication, layout issues, extra columns, wrong spacing — always clarify
- **Assuming the obvious interpretation**: Technical terms mean different things in different contexts. What sounds clear often isn't.
- **Fixing symptoms**: If a fix doesn't work, re-examine the understanding of the bug itself, not just the code
