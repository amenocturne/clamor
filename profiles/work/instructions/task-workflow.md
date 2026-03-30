## Working on a Task

When user asks to work on an ITAL task (e.g. "work on ITAL-1234", "implement ITAL-1234"):
1. Fetch task description using the dp-jira skill
2. Create a branch: `git checkout -b feature/ITAL-<number>`
3. Ask the user any clarifying questions needed before starting

When researching something or creating new branch, make sure to firstly switch to `master` if other instructions from user are present.
