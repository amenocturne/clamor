# Fleet Hook

Reports agent state changes (working, waiting for input, done) to the fleet orchestrator.

Triggered on:
- **Notification** — agent produced output
- **PreToolUse** — agent is about to use a tool (signals active work)
- **Stop** — agent finished its turn (signals idle/done state)

The hook delegates to the `fleet hook` subcommand, which updates the agent's state in fleet's tracking system. If the fleet binary isn't available, the hook exits silently.
