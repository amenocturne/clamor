use std::process::Command;

use anyhow::Context;

/// Check that we're running inside tmux. Errors if $TMUX is not set.
pub fn require_tmux() -> anyhow::Result<()> {
    std::env::var("TMUX")
        .map(|_| ())
        .map_err(|_| anyhow::anyhow!("Not running inside tmux. Start tmux first."))
}

/// Create a new tmux session running Claude Code with the given prompt.
///
/// Session name follows convention: {prefix}{id} (e.g., "fleet-a1b2c3").
/// Working directory set to `cwd`.
/// `FLEET_AGENT_ID` env var is set so hooks can identify the agent.
pub fn create_session(name: &str, cwd: &str, prompt: &str, agent_id: &str) -> anyhow::Result<()> {
    let escaped_prompt = shell_escape(prompt);
    let shell_cmd = format!("env FLEET_AGENT_ID={agent_id} claude {escaped_prompt}");

    let status = Command::new("tmux")
        .args(["new-session", "-d", "-s", name, "-c", cwd, &shell_cmd])
        .status()
        .context("Failed to execute tmux new-session")?;

    if !status.success() {
        anyhow::bail!("tmux new-session failed for '{name}' (exit {})", status);
    }

    Ok(())
}

/// Kill a tmux session by name.
/// If any clients are attached to it, switches them to another session first.
pub fn kill_session(name: &str) -> anyhow::Result<()> {
    evacuate_clients(name);

    let status = Command::new("tmux")
        .args(["kill-session", "-t", name])
        .status()
        .context("Failed to execute tmux kill-session")?;

    if !status.success() {
        anyhow::bail!("tmux kill-session failed for '{name}' (exit {})", status);
    }

    Ok(())
}

/// Move any clients attached to `session` to another available session.
fn evacuate_clients(session: &str) {
    // Find clients attached to this session
    let output = Command::new("tmux")
        .args(["list-clients", "-t", session, "-F", "#{client_name}"])
        .output();

    let clients = match output {
        Ok(o) if o.status.success() => {
            String::from_utf8(o.stdout).unwrap_or_default()
        }
        _ => return,
    };

    let client_names: Vec<&str> = clients.lines().filter(|l| !l.is_empty()).collect();
    if client_names.is_empty() {
        return;
    }

    // Find a fallback session (any session that isn't the one being killed)
    let fallback = find_fallback_session(session);

    for client in client_names {
        if let Some(ref target) = fallback {
            let _ = Command::new("tmux")
                .args(["switch-client", "-c", client, "-t", target])
                .status();
        }
    }
}

/// Find a session to switch to: prefer non-fleet sessions, fall back to any.
fn find_fallback_session(exclude: &str) -> Option<String> {
    let output = Command::new("tmux")
        .args(["list-sessions", "-F", "#{session_name}"])
        .output()
        .ok()?;

    let sessions: Vec<String> = String::from_utf8(output.stdout)
        .unwrap_or_default()
        .lines()
        .filter(|s| *s != exclude)
        .map(String::from)
        .collect();

    // Prefer non-fleet sessions (the user's editor/main session)
    sessions
        .iter()
        .find(|s| !s.starts_with("fleet-") && *s != "popup")
        .cloned()
        .or_else(|| sessions.into_iter().next())
}

/// Check if a tmux session exists.
pub fn session_exists(name: &str) -> bool {
    Command::new("tmux")
        .args(["has-session", "-t", name])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Switch the current tmux client to a different session.
pub fn switch_to(name: &str) -> anyhow::Result<()> {
    let status = Command::new("tmux")
        .args(["switch-client", "-t", name])
        .status()
        .context("Failed to execute tmux switch-client")?;

    if !status.success() {
        anyhow::bail!("tmux switch-client failed for '{name}' (exit {})", status);
    }

    Ok(())
}

/// List all tmux sessions. Returns session names.
#[allow(dead_code)]
pub fn list_sessions() -> anyhow::Result<Vec<String>> {
    let output = Command::new("tmux")
        .args(["list-sessions", "-F", "#{session_name}"])
        .output()
        .context("Failed to execute tmux list-sessions")?;

    if !output.status.success() {
        // No server running or no sessions — return empty list
        return Ok(Vec::new());
    }

    let stdout = String::from_utf8(output.stdout)
        .context("tmux list-sessions returned invalid UTF-8")?;

    Ok(stdout.lines().map(String::from).collect())
}

/// Get the name of the current tmux session.
pub fn current_session() -> anyhow::Result<String> {
    let output = Command::new("tmux")
        .args(["display-message", "-p", "#{session_name}"])
        .output()
        .context("Failed to execute tmux display-message")?;

    if !output.status.success() {
        anyhow::bail!("tmux display-message failed (exit {})", output.status);
    }

    let name = String::from_utf8(output.stdout)
        .context("tmux display-message returned invalid UTF-8")?;

    Ok(name.trim().to_string())
}

/// Set up the return keybinding: prefix + key switches back to dashboard session.
pub fn setup_return_key(key: &str, dashboard_session: &str) -> anyhow::Result<()> {
    let status = Command::new("tmux")
        .args(["bind-key", key, "switch-client", "-t", dashboard_session])
        .status()
        .context("Failed to execute tmux bind-key")?;

    if !status.success() {
        anyhow::bail!("tmux bind-key failed for key '{key}' (exit {})", status);
    }

    Ok(())
}

/// Format session name from prefix + id.
pub fn session_name(prefix: &str, id: &str) -> String {
    format!("{prefix}{id}")
}

/// Shell-escape a string for use inside double quotes in a tmux command.
///
/// Uses single-quote wrapping with the `'\''` idiom to handle embedded
/// single quotes safely.
fn shell_escape(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}
