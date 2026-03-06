## Bug Reports

When the user reports a bug, **do not start fixing immediately**. Follow this protocol:

### 1. Clarify First

If anything in the report is ambiguous, ask targeted questions about what's unclear. Don't use a template — extract what you can from the user's description first, then ask only about gaps.

### 2. Restate the Bug

Before proposing a fix, describe the bug back in your own words:
> "So the issue is: [your understanding]. Is that right?"

Only proceed after confirmation. Getting this wrong wastes significant time — a misunderstood bug leads to fixing the wrong thing, which compounds with each iteration.

### 3. Diagnose Before Fixing

- Form a hypothesis about the root cause
- Verify it with evidence (read code, check data, use tools)
- If the hypothesis doesn't hold, form a new one — don't cargo-cult fixes
- For visual bugs: use Playwright or browser tools to see exactly what the user sees
- If a fix doesn't work, re-examine the understanding of the bug itself, not just the code
