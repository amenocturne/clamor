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
    /// Only present on Notification events. Values seen: "permission_prompt", "idle_prompt".
    #[serde(default)]
    notification_type: Option<String>,
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

    let debug = debug_enabled();
    if debug {
        debug_log_raw(&input);
    }

    let agent_id = match std::env::var("CLAMOR_AGENT_ID") {
        Ok(id) => id,
        Err(_) => {
            if debug {
                debug_log("-- no CLAMOR_AGENT_ID, skipping\n");
            }
            return Ok(());
        }
    };

    let event: HookEvent = serde_json::from_str(&input)?;

    // Load config once — single file read, acceptable for hook path
    let config = ClamorConfig::load().ok();

    let update = |state: &mut crate::state::ClamorState| {
        let hooks_supported_default = config
            .as_ref()
            .map(|c| {
                state
                    .agents
                    .get(&agent_id)
                    .map(|a| should_process_hooks(c, &a.backend_id))
                    .unwrap_or(false)
            })
            .unwrap_or(false);

        let agent = match state.agents.get_mut(&agent_id) {
            Some(a) => a,
            None => {
                if debug {
                    debug_log(&format!(
                        "-- agent {agent_id} not in state, event {:?} ignored\n",
                        event.hook_event_name
                    ));
                }
                return;
            }
        };

        let state_before = format!("{:?}", agent.state);
        let token_before = agent.resume_token.clone();

        apply_event(agent, &event, hooks_supported_default);

        if debug {
            let state_after = format!("{:?}", agent.state);
            let token_after = agent.resume_token.clone();
            let notif = event
                .notification_type
                .as_deref()
                .map(|t| format!(" notif_type={t}"))
                .unwrap_or_default();
            debug_log(&format!(
                "-- agent={agent_id} event={}{notif} state: {state_before} -> {state_after} token: {:?} -> {:?}\n",
                event.hook_event_name, token_before, token_after
            ));
        }
    };

    // Always use non-blocking lock — a blocked lock + hook timeout = SIGKILL
    // (exit 137), which Claude Code reports as a hook error. For Stop events
    // this means the Done transition may be silently dropped if the lock is
    // contended, but the dashboard will detect the stopped process anyway.
    try_with_state(update)?;

    Ok(())
}

/// Apply a hook event to an agent. Pure state mutation — no I/O.
/// `hooks_supported` is pre-resolved from the backend config (hook processing
/// is skipped entirely for backends without hook support).
fn apply_event(agent: &mut crate::agent::Agent, event: &HookEvent, hooks_supported: bool) {
    // resume_token is gated to session-boundary events. Other events can
    // carry session_ids from unrelated contexts (observed: none in practice
    // on Claude Code 2.1.117, but the old "update on every event" behavior
    // was a latent footgun if a subagent session_id ever appears).
    if matches!(
        event.hook_event_name.as_str(),
        "SessionStart" | "UserPromptSubmit"
    ) {
        if let Some(ref sid) = event.session_id {
            if agent.resume_token.as_ref() != Some(sid) {
                agent.resume_token = Some(sid.clone());
            }
        }
    }

    if !hooks_supported {
        return;
    }

    match event.hook_event_name.as_str() {
        "SessionStart" => {
            agent.state = AgentState::Working;
            agent.last_activity_at = Utc::now();
        }
        "UserPromptSubmit" => {
            agent.state = AgentState::Working;
            agent.last_activity_at = Utc::now();
        }
        "Notification" => {
            // Claude Code emits two variants via `notification_type`:
            // "permission_prompt" (redundant with PermissionRequest which
            // already set Input) and "idle_prompt" (genuinely paused for
            // input). Both land on Input.
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
}

/// Debug tap: enabled when `~/.clamor/debug` exists. Writes to `~/.clamor/hook.log`.
/// Non-fatal on any error — this must never break the hook path.
fn debug_enabled() -> bool {
    let Some(home) = std::env::var_os("HOME") else {
        return false;
    };
    std::path::PathBuf::from(home)
        .join(".clamor")
        .join("debug")
        .exists()
}

fn debug_log_raw(input: &str) {
    let ts = Utc::now().to_rfc3339();
    let pid = std::process::id();
    let agent = std::env::var("CLAMOR_AGENT_ID").unwrap_or_else(|_| "-".into());
    let trimmed = input.trim();
    debug_log(&format!("\n>>> {ts} pid={pid} agent={agent}\n{trimmed}\n",));
}

fn debug_log(msg: &str) {
    use std::io::Write;
    let Some(home) = std::env::var_os("HOME") else {
        return;
    };
    let path = std::path::PathBuf::from(home)
        .join(".clamor")
        .join("hook.log");
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        let _ = f.write_all(msg.as_bytes());
    }
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
    use crate::agent::Agent;
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

    fn make_agent(state: AgentState, token: Option<&str>) -> Agent {
        let now = Utc::now();
        Agent {
            id: "test".into(),
            title: "t".into(),
            folder_id: "f".into(),
            backend_id: "claude-code".into(),
            cwd: "/tmp".into(),
            initial_prompt: None,
            state,
            started_at: now,
            last_activity_at: now,
            last_tool: None,
            resume_token: token.map(String::from),
            metadata: Default::default(),
            key: None,
            color_index: 0,
        }
    }

    fn event(name: &str, session_id: Option<&str>) -> HookEvent {
        HookEvent {
            hook_event_name: name.into(),
            session_id: session_id.map(String::from),
            tool_name: None,
            tool_input: None,
            notification_type: None,
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

    #[test]
    fn permission_approval_flips_input_to_working_via_posttooluse() {
        // Happy path from real hook.log capture:
        // PreToolUse -> PermissionRequest -> Notification -> PostToolUse
        let mut a = make_agent(AgentState::Working, Some("sess-1"));
        apply_event(&mut a, &event("PreToolUse", Some("sess-1")), true);
        assert_eq!(a.state, AgentState::Working);
        apply_event(&mut a, &event("PermissionRequest", Some("sess-1")), true);
        assert_eq!(a.state, AgentState::Input);
        apply_event(&mut a, &event("Notification", Some("sess-1")), true);
        assert_eq!(a.state, AgentState::Input);
        // User approves off-hook; PostToolUse fires when tool completes.
        apply_event(&mut a, &event("PostToolUse", Some("sess-1")), true);
        assert_eq!(a.state, AgentState::Working);
    }

    #[test]
    fn resume_token_only_updates_on_session_boundary_events() {
        // Non-boundary events must NOT overwrite resume_token. Protects
        // against foreign session_ids (subagents, etc.) bleeding into the
        // parent agent's token field.
        let mut a = make_agent(AgentState::Working, Some("original"));
        apply_event(&mut a, &event("PreToolUse", Some("foreign")), true);
        assert_eq!(a.resume_token.as_deref(), Some("original"));
        apply_event(&mut a, &event("PostToolUse", Some("foreign")), true);
        assert_eq!(a.resume_token.as_deref(), Some("original"));
        apply_event(&mut a, &event("Notification", Some("foreign")), true);
        assert_eq!(a.resume_token.as_deref(), Some("original"));
        apply_event(&mut a, &event("Stop", Some("foreign")), true);
        assert_eq!(a.resume_token.as_deref(), Some("original"));
        // UserPromptSubmit does update — that's an authoritative turn start.
        apply_event(&mut a, &event("UserPromptSubmit", Some("new-sess")), true);
        assert_eq!(a.resume_token.as_deref(), Some("new-sess"));
    }

    #[test]
    fn session_start_sets_working_and_updates_token() {
        let mut a = make_agent(AgentState::Done, None);
        apply_event(&mut a, &event("SessionStart", Some("sess-a")), true);
        assert_eq!(a.state, AgentState::Working);
        assert_eq!(a.resume_token.as_deref(), Some("sess-a"));
    }

    #[test]
    fn stop_always_lands_on_done() {
        let mut a = make_agent(AgentState::Input, Some("sess-1"));
        apply_event(&mut a, &event("Stop", Some("sess-1")), true);
        assert_eq!(a.state, AgentState::Done);
    }

    #[test]
    fn disabled_backend_skips_state_transitions() {
        let mut a = make_agent(AgentState::Working, Some("sess-1"));
        apply_event(&mut a, &event("Stop", Some("sess-1")), false);
        // No-op — state untouched because hooks aren't supported on this backend.
        assert_eq!(a.state, AgentState::Working);
    }
}
