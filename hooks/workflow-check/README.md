# workflow-check

A `Stop` hook that checks for uncommitted git changes and reminds the agent to follow The Loop workflow (verify, commit, review) before responding to the user.

## How it works

When the assistant is about to respond, this hook:

1. Checks if the active project directory is a git repository
2. Runs `git diff --stat` and `git diff --cached --stat` to detect uncommitted changes
3. If changes exist, injects a reminder into the assistant's context

If there are no changes or the directory isn't a git repo, the hook outputs nothing and has no effect.
