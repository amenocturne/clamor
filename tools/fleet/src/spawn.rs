use std::io::{self, Write};

use anyhow::{bail, Context};
use chrono::{DateTime, Utc};

use crate::agent::{generate_id, next_color_index, Agent, AgentState};
use crate::client::DaemonClient;
use crate::config::{resolve_path, FleetConfig};
use crate::daemon;
use crate::dashboard::keys;
use crate::picker;
use crate::state::{with_state, FleetState};

fn ensure_daemon() -> anyhow::Result<()> {
    if !daemon::is_daemon_running() {
        daemon::start_daemon_background()?;
    }
    Ok(())
}

/// Check if debug mode is active.
pub fn is_debug_mode() -> bool {
    std::env::var("FLEET_DEBUG").is_ok()
}

/// Build the command to spawn for an agent.
/// In debug mode, spawns `fleet _mock-agent` instead of `claude`.
pub fn build_agent_cmd(prompt: &str) -> Vec<String> {
    if is_debug_mode() {
        let exe = std::env::current_exe()
            .unwrap_or_else(|_| "fleet".into());
        vec![
            exe.to_string_lossy().to_string(),
            "mock-agent".to_string(),
            "--description".to_string(),
            prompt.to_string(),
        ]
    } else {
        vec!["claude".to_string(), prompt.to_string()]
    }
}

/// Build the command for adopting/resuming a session.
pub fn build_resume_cmd(session_id: &str) -> Vec<String> {
    if is_debug_mode() {
        let exe = std::env::current_exe()
            .unwrap_or_else(|_| "fleet".into());
        vec![
            exe.to_string_lossy().to_string(),
            "mock-agent".to_string(),
            "--description".to_string(),
            format!("resumed: {session_id}"),
        ]
    } else {
        vec!["claude".to_string(), "--resume".to_string(), session_id.to_string()]
    }
}

/// Interactive agent spawn flow.
/// If `force_editor` is true, open $EDITOR directly instead of showing a text prompt.
pub fn spawn_agent(description: Option<String>, folder_override: Option<String>, force_editor: bool) -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = FleetConfig::load()?;

    if config.folders.is_empty() {
        bail!("No folders configured. Run `fleet config` to add folders.");
    }

    // Resolve folder
    let (folder_name, folder_path) = match folder_override {
        Some(ref name) => {
            let path = config
                .folders
                .get(name)
                .with_context(|| format!("Unknown folder: {name}"))?;
            (name.clone(), path.clone())
        }
        None => select_folder(&config)?,
    };

    let cwd = resolve_path(&folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    // Get task description and prompt
    let (desc, prompt) = match description {
        Some(d) => (d.clone(), d),
        None if force_editor => read_task_from_editor()?,
        None => read_task_description()?,
    };

    let id = generate_id();
    let now = Utc::now();

    // Determine key and color from existing agents
    let state = FleetState::load(&config)?;
    let existing: Vec<&Agent> = state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        description: desc.clone(),
        folder: folder_name,
        cwd: cwd_str.clone(),
        initial_prompt: prompt.clone(),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        key,
        color_index,
    };

    // Save state first
    with_state(&config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    // Spawn via daemon
    let cmd = build_agent_cmd(&prompt);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];
    let mut client = DaemonClient::connect()?;
    client.spawn_agent(&id, &cwd_str, &cmd, &env)?;

    println!("Spawned agent {id}: {desc}");

    Ok(())
}

/// Adopt an external Claude Code session into fleet.
pub fn adopt_session(session_id: &str, description: Option<String>, folder_override: Option<String>) -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = FleetConfig::load()?;

    if config.folders.is_empty() {
        bail!("No folders configured. Run `fleet config` to add folders.");
    }

    let (folder_name, folder_path) = match folder_override {
        Some(ref name) => {
            let path = config
                .folders
                .get(name)
                .with_context(|| format!("Unknown folder: {name}"))?;
            (name.clone(), path.clone())
        }
        None => select_folder(&config)?,
    };

    let cwd = resolve_path(&folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let desc = match description {
        Some(d) => d,
        None => {
            print!("Description: ");
            io::stdout().flush()?;
            let input = read_line()?.trim().to_string();
            if input.is_empty() {
                bail!("Empty description, aborting.");
            }
            input
        }
    };

    let id = generate_id();
    let now = Utc::now();

    let state = FleetState::load(&config)?;
    let existing: Vec<&Agent> = state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        description: desc.clone(),
        folder: folder_name,
        cwd: cwd_str.clone(),
        initial_prompt: format!("--resume {session_id}"),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        key,
        color_index,
    };

    with_state(&config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    let cmd = build_resume_cmd(session_id);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];
    let mut client = DaemonClient::connect()?;
    client.spawn_agent(&id, &cwd_str, &cmd, &env)?;

    println!("Adopted session {session_id} as agent {id}: {desc}");

    Ok(())
}

/// Kill an agent by ID prefix.
pub fn kill_agent(agent_ref: &str) -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    let agent = resolve_agent(&state, agent_ref)
        .with_context(|| format!("No agent matching '{agent_ref}'"))?
        .clone();

    let mut client = DaemonClient::connect()?;
    // Ignore errors — agent may not exist in daemon if already dead
    let _ = client.kill_agent(&agent.id);

    with_state(&config, |state| {
        state.agents.remove(&agent.id);
    })?;

    println!("Killed agent {}: {}", agent.id, agent.description);

    Ok(())
}

/// Kill all agents: terminate PTYs and clear state.
pub fn kill_all_agents() -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    let count = state.agents.len();
    let mut client = DaemonClient::connect()?;
    for agent in state.agents.values() {
        let _ = client.kill_agent(&agent.id);
    }

    with_state(&config, |state| {
        state.agents.clear();
    })?;

    println!("Killed {count} agent(s).");

    Ok(())
}

/// Remove all done agents from state.
pub fn clean_agents() -> anyhow::Result<()> {
    let config = FleetConfig::load()?;

    let removed = with_state(&config, |state| {
        let done_ids: Vec<String> = state
            .agents
            .iter()
            .filter(|(_, a)| a.state == AgentState::Done || a.state == AgentState::Lost)
            .map(|(id, _)| id.clone())
            .collect();

        let count = done_ids.len();
        for id in &done_ids {
            state.agents.remove(id);
        }
        count
    })?;

    println!("Removed {removed} finished agent(s).");

    Ok(())
}

/// Print one-shot status table to stdout.
pub fn list_agents() -> anyhow::Result<()> {
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    if state.agents.is_empty() {
        println!("No agents.");
        return Ok(());
    }

    let mut agents: Vec<&Agent> = state.agents.values().collect();
    agents.sort_by_key(|a| a.started_at);

    let id_w = 6;
    let state_w = 6;
    let desc_w = 40;
    let folder_w = agents
        .iter()
        .map(|a| a.folder.len())
        .max()
        .unwrap_or(6)
        .max(6);

    println!(
        "{:<id_w$}  {:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>4}",
        "ID", "STATE", "DESCRIPTION", "FOLDER", "TIME",
    );

    for agent in &agents {
        let state_str = match agent.state {
            AgentState::Working => "work",
            AgentState::Input => "input",
            AgentState::Done => "done",
            AgentState::Lost => "lost",
        };
        let desc = truncate(&agent.description, desc_w);
        let time = format_duration(&agent.started_at);

        println!(
            "{:<id_w$}  {:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>4}",
            agent.id, state_str, desc, agent.folder, time,
        );
    }

    Ok(())
}

/// Resolve an agent reference by ID prefix match.
pub fn resolve_agent<'a>(state: &'a FleetState, agent_ref: &str) -> Option<&'a Agent> {
    if agent_ref.len() == 1 && agent_ref.chars().next().map_or(false, |c| c.is_alphabetic()) {
        return None;
    }

    let matches: Vec<&Agent> = state
        .agents
        .values()
        .filter(|a| a.id.starts_with(agent_ref))
        .collect();

    if matches.len() == 1 {
        Some(matches[0])
    } else {
        None
    }
}

/// Edit an agent's description.
pub fn edit_agent(agent_ref: &str, description: Option<String>) -> anyhow::Result<()> {
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    let agent_id = resolve_agent(&state, agent_ref)
        .with_context(|| format!("No agent matching '{agent_ref}'"))?
        .id
        .clone();

    let new_desc = match description {
        Some(d) => d,
        None => {
            print!("Description: ");
            io::stdout().flush()?;
            read_line()?.trim().to_string()
        }
    };

    if new_desc.is_empty() {
        bail!("Empty description, aborting.");
    }

    with_state(&config, |state| {
        if let Some(agent) = state.agents.get_mut(&agent_id) {
            agent.description = new_desc.clone();
        }
    })?;

    println!("Updated description for {agent_id}: {new_desc}");
    Ok(())
}

/// Open config in $EDITOR.
pub fn open_config() -> anyhow::Result<()> {
    let config_path = FleetConfig::config_dir().join("config.json");
    FleetConfig::ensure_dir()?;

    if !config_path.exists() {
        let _ = FleetConfig::load()?;
    }

    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".into());
    let status = std::process::Command::new(&editor)
        .arg(&config_path)
        .status()
        .with_context(|| format!("Failed to open {editor}"))?;

    if !status.success() {
        bail!("Editor exited with non-zero status");
    }

    Ok(())
}

/// Format duration since a timestamp as "Xm", "Xh", "Xd".
pub fn format_duration(since: &DateTime<Utc>) -> String {
    let delta = Utc::now() - *since;
    let mins = delta.num_minutes();

    if mins < 60 {
        format!("{}m", mins.max(0))
    } else if mins < 1440 {
        format!("{}h", mins / 60)
    } else {
        format!("{}d", mins / 1440)
    }
}

// ── Helpers ────────────────────────────────────────────────────────

/// Interactive folder picker.
fn select_folder(config: &FleetConfig) -> anyhow::Result<(String, String)> {
    let mut folders: Vec<(&String, &String)> = config.folders.iter().collect();
    folders.sort_by_key(|(name, _)| name.to_owned());

    let options: Vec<String> = folders.iter().map(|(name, _)| (*name).clone()).collect();

    let idx = picker::pick("Where?", &options)?
        .context("Aborted.")?;

    let (name, path) = &folders[idx];
    Ok(((*name).clone(), (*path).clone()))
}

/// Read task description from stdin, or open $EDITOR if empty.
/// Returns (description, prompt).
fn read_task_description() -> anyhow::Result<(String, String)> {
    print!("Task: ");
    io::stdout().flush()?;

    let input = read_line()?.trim().to_string();

    if !input.is_empty() {
        return Ok((input.clone(), input));
    }

    read_task_from_editor()
}

/// Open $EDITOR directly to compose a task prompt.
/// Returns (first_line_as_description, full_content_as_prompt).
fn read_task_from_editor() -> anyhow::Result<(String, String)> {
    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".into());
    let tmp = std::env::temp_dir().join(format!("fleet-task-{}.md", generate_id()));

    std::fs::write(&tmp, "")?;

    let status = std::process::Command::new(&editor)
        .arg(&tmp)
        .status()
        .with_context(|| format!("Failed to open {editor}"))?;

    if !status.success() {
        let _ = std::fs::remove_file(&tmp);
        bail!("Editor exited with non-zero status");
    }

    let content = std::fs::read_to_string(&tmp)?;
    let _ = std::fs::remove_file(&tmp);

    let content = content.trim().to_string();
    if content.is_empty() {
        bail!("Empty task description, aborting.");
    }

    let description = content.lines().next().unwrap_or("").to_string();

    Ok((description, content))
}

fn read_line() -> anyhow::Result<String> {
    let mut buf = String::new();
    io::stdin().read_line(&mut buf)?;
    Ok(buf)
}

fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else if max_len > 3 {
        format!("{}...", &s[..max_len - 3])
    } else {
        s[..max_len].to_string()
    }
}
