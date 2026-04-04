use chrono::Utc;
use serde::Deserialize;

use crate::agent::AgentState;
use crate::config::ClamorConfig;
use crate::state::try_with_state;

#[derive(Debug, Deserialize)]
struct HookEvent {
    hook_event_name: String,
    #[serde(default)]
    session_id: Option<String>,
    #[serde(default)]
    tool_name: Option<String>,
    #[serde(default)]
    tool_input: Option<serde_json::Value>,
}

/// Run the hook: read stdin JSON, update agent state.
/// Called as `clamor hook` subcommand.
///
/// Never fails — hooks must not block Claude Code.
/// Silently exits on any error or when CLAMOR_AGENT_ID is not set.
pub fn run() {
    let _ = run_inner();
}

fn run_inner() -> anyhow::Result<()> {
    // Always consume stdin to avoid broken pipe errors in Claude Code
    let mut input = String::new();
    std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)?;

    let agent_id = match std::env::var("CLAMOR_AGENT_ID") {
        Ok(id) => id,
        Err(_) => return Ok(()),
    };

    let event: HookEvent = serde_json::from_str(&input)?;

    // Load config once — single file read, acceptable for hook path
    let config = ClamorConfig::load().ok();

    let update = |state: &mut crate::state::ClamorState| {
        let agent = match state.agents.get_mut(&agent_id) {
            Some(a) => a,
            None => return,
        };

        // Always extract resume_token — useful regardless of backend
        if let Some(ref sid) = event.session_id {
            if agent.resume_token.as_ref() != Some(sid) {
                agent.resume_token = Some(sid.clone());
            }
        }

        // Skip state transitions if the backend doesn't support hooks
        let hooks_supported = config
            .as_ref()
            .map(|c| should_process_hooks(c, &agent.backend_id))
            .unwrap_or(false);

        if !hooks_supported {
            return;
        }

        match event.hook_event_name.as_str() {
            "UserPromptSubmit" => {
                agent.state = AgentState::Working;
                agent.last_activity_at = Utc::now();
            }
            "Notification" => {
                agent.state = AgentState::Input;
            }
            "PreToolUse" => {
                agent.state = AgentState::Working;
                agent.last_tool = Some(format_tool(&event.tool_name, &event.tool_input));
                agent.last_activity_at = Utc::now();
            }
            "PermissionRequest" => {
                agent.state = AgentState::Input;
                agent.last_tool = Some(format_tool(&event.tool_name, &event.tool_input));
            }
            "PostToolUse" => {
                agent.state = AgentState::Working;
                agent.last_activity_at = Utc::now();
            }
            "Stop" => {
                agent.state = AgentState::Done;
            }
            _ => {}
        }
    };

    // Always use non-blocking lock — a blocked lock + hook timeout = SIGKILL
    // (exit 137), which Claude Code reports as a hook error. For Stop events
    // this means the Done transition may be silently dropped if the lock is
    // contended, but the dashboard will detect the stopped process anyway.
    try_with_state(update)?;

    Ok(())
}

fn should_process_hooks(config: &ClamorConfig, backend_id: &str) -> bool {
    config
        .backends
        .get(backend_id)
        .map(|b| b.capabilities.hooks)
        .unwrap_or(false)
}

fn format_tool(tool_name: &Option<String>, tool_input: &Option<serde_json::Value>) -> String {
    let name = match tool_name {
        Some(n) => n,
        None => return "Unknown".into(),
    };

    let input = tool_input.as_ref();

    match name.as_str() {
        "Edit" | "Write" | "Read" => {
            let path = input
                .and_then(|v| v.get("file_path"))
                .and_then(|v| v.as_str())
                .unwrap_or("?");
            format!("{name} {path}")
        }
        "Bash" => {
            let cmd = input
                .and_then(|v| v.get("command"))
                .and_then(|v| v.as_str())
                .unwrap_or("?");
            let truncated: String = if cmd.chars().count() > 40 {
                format!("{}...", cmd.chars().take(40).collect::<String>())
            } else {
                cmd.to_string()
            };
            format!("Bash: {truncated}")
        }
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{BackendCapabilities, BackendConfig};
    use std::collections::HashMap;

    fn config_with_backend(id: &str, hooks: bool) -> ClamorConfig {
        let mut backends = HashMap::new();
        backends.insert(
            id.to_string(),
            BackendConfig {
                capabilities: BackendCapabilities {
                    hooks,
                    ..Default::default()
                },
                ..Default::default()
            },
        );
        ClamorConfig {
            backends,
            ..Default::default()
        }
    }

    #[test]
    fn hooks_enabled_backend_returns_true() {
        let config = config_with_backend("claude-code", true);
        assert!(should_process_hooks(&config, "claude-code"));
    }

    #[test]
    fn hooks_disabled_backend_returns_false() {
        let config = config_with_backend("open-code", false);
        assert!(!should_process_hooks(&config, "open-code"));
    }

    #[test]
    fn unknown_backend_returns_false() {
        let config = ClamorConfig::default();
        assert!(!should_process_hooks(&config, "nonexistent"));
    }
}
