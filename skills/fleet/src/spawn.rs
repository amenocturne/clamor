use std::io::{self, Write};

use anyhow::{bail, Context};
use chrono::{DateTime, Utc};

use crate::agent::{generate_id, Agent, AgentState};
use crate::config::{FleetConfig, FolderConfig};
use crate::state::{with_state, FleetState};
use crate::tmux;

/// Interactive agent spawn flow.
pub fn spawn_agent(description: Option<String>, folder_override: Option<String>) -> anyhow::Result<()> {
    tmux::require_tmux()?;
    let config = FleetConfig::load()?;

    if config.folders.is_empty() {
        bail!("No folders configured. Run `fleet config` to add folders.");
    }

    // Resolve folder
    let (folder_key, folder_config) = match folder_override {
        Some(ref key) => {
            let fc = config
                .folders
                .get(key)
                .with_context(|| format!("Unknown folder: {key}"))?;
            (key.clone(), fc.clone())
        }
        None => select_folder(&config)?,
    };

    // Resolve optional subfolder
    let subfolder = if folder_config.list_subdirs {
        Some(select_subfolder(&folder_config)?)
    } else {
        None
    };

    // Build cwd
    let cwd = match &subfolder {
        Some(sub) => folder_config.resolved_path().join(sub),
        None => folder_config.resolved_path(),
    };
    let cwd_str = cwd.to_string_lossy().to_string();

    // Get task description and prompt
    let (desc, prompt) = match description {
        Some(d) => (d.clone(), d),
        None => read_task_description()?,
    };

    // Generate agent
    let id = generate_id();
    let session = tmux::session_name(&config.tmux.session_prefix, &id);
    let now = Utc::now();

    let agent = Agent {
        id: id.clone(),
        description: desc.clone(),
        folder: folder_key,
        subfolder,
        cwd: cwd_str.clone(),
        tmux_session: session.clone(),
        initial_prompt: prompt.clone(),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
    };

    // Save state
    with_state(&config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    // Create tmux session
    tmux::create_session(&session, &cwd_str, &prompt, &id)?;

    println!("Spawned agent {id}: {desc}");

    Ok(())
}

/// Kill an agent by ID prefix.
pub fn kill_agent(agent_ref: &str) -> anyhow::Result<()> {
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    let agent = resolve_agent(&state, agent_ref)
        .with_context(|| format!("No agent matching '{agent_ref}'"))?
        .clone();

    // Kill tmux session if it exists
    if tmux::session_exists(&agent.tmux_session) {
        tmux::kill_session(&agent.tmux_session)?;
    }

    // Remove from state
    with_state(&config, |state| {
        state.agents.remove(&agent.id);
    })?;

    println!("Killed agent {}: {}", agent.id, agent.description);

    Ok(())
}

/// Remove all done agents from state.
pub fn clean_agents() -> anyhow::Result<()> {
    let config = FleetConfig::load()?;

    let removed = with_state(&config, |state| {
        let done_ids: Vec<String> = state
            .agents
            .iter()
            .filter(|(_, a)| a.state == AgentState::Done)
            .map(|(id, _)| id.clone())
            .collect();

        let count = done_ids.len();
        for id in &done_ids {
            state.agents.remove(id);
        }
        count
    })?;

    println!("Removed {removed} done agent(s).");

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

    // Collect and sort by start time
    let mut agents: Vec<&Agent> = state.agents.values().collect();
    agents.sort_by_key(|a| a.started_at);

    // Column widths
    let state_w = 6;
    let desc_w = 40;
    let folder_w = agents
        .iter()
        .map(|a| display_folder(a).len())
        .max()
        .unwrap_or(6)
        .max(6);

    println!(
        "{:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>4}",
        "STATE", "DESCRIPTION", "FOLDER", "TIME",
    );

    for agent in &agents {
        let state_str = match agent.state {
            AgentState::Working => "work",
            AgentState::Input => "input",
            AgentState::Done => "done",
        };
        let desc = truncate(&agent.description, desc_w);
        let folder = display_folder(agent);
        let time = format_duration(&agent.started_at);

        println!(
            "{:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>4}",
            state_str, desc, folder, time,
        );
    }

    Ok(())
}

/// Resolve an agent reference by ID prefix match.
fn resolve_agent<'a>(state: &'a FleetState, agent_ref: &str) -> Option<&'a Agent> {
    if agent_ref.len() == 1 && agent_ref.chars().next().map_or(false, |c| c.is_alphabetic()) {
        // Single letter = future jump key, not supported yet
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

/// Format duration since a timestamp as "Xm", "Xh", "Xd".
fn format_duration(since: &DateTime<Utc>) -> String {
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

/// Attach to an agent's tmux session.
pub fn attach_agent(agent_ref: &str) -> anyhow::Result<()> {
    tmux::require_tmux()?;
    let config = FleetConfig::load()?;
    let state = FleetState::load(&config)?;

    let agent = resolve_agent(&state, agent_ref)
        .with_context(|| format!("No agent matching '{agent_ref}'"))?;

    if !tmux::session_exists(&agent.tmux_session) {
        bail!("Agent {}'s tmux session no longer exists", agent.id);
    }

    tmux::switch_to(&agent.tmux_session)
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

    // Create default config if missing
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

// ── Helpers ────────────────────────────────────────────────────────

/// Present numbered folder list, return (key, config).
fn select_folder(config: &FleetConfig) -> anyhow::Result<(String, FolderConfig)> {
    let mut folders: Vec<(&String, &FolderConfig)> = config.folders.iter().collect();
    folders.sort_by_key(|(_, fc)| &fc.name);

    println!("Where?");
    for (i, (_, fc)) in folders.iter().enumerate() {
        println!("  {}  {}", i + 1, fc.name);
    }
    print!("> ");
    io::stdout().flush()?;

    let input = read_line()?.trim().to_string();
    let idx: usize = input
        .parse::<usize>()
        .context("Invalid selection")?
        .checked_sub(1)
        .context("Selection out of range")?;

    let (key, fc) = folders
        .get(idx)
        .context("Selection out of range")?;

    Ok(((*key).clone(), (*fc).clone()))
}

/// Present numbered subdirectory list, return selected name.
fn select_subfolder(folder: &FolderConfig) -> anyhow::Result<String> {
    let subdirs = folder.subdirs()?;

    if subdirs.is_empty() {
        bail!("No subdirectories found in {}", folder.resolved_path().display());
    }

    println!("Project?");
    for (i, name) in subdirs.iter().enumerate() {
        println!("  {}  {}", i + 1, name);
    }
    print!("> ");
    io::stdout().flush()?;

    let input = read_line()?.trim().to_string();
    let idx: usize = input
        .parse::<usize>()
        .context("Invalid selection")?
        .checked_sub(1)
        .context("Selection out of range")?;

    subdirs
        .get(idx)
        .cloned()
        .context("Selection out of range")
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

    // Empty line — open $EDITOR
    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".into());
    let tmp = std::env::temp_dir().join(format!("fleet-task-{}.md", generate_id()));

    // Create empty temp file
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

    // First line = description, full content = prompt
    let description = content.lines().next().unwrap_or("").to_string();

    Ok((description, content))
}

/// Read a single line from stdin.
fn read_line() -> anyhow::Result<String> {
    let mut buf = String::new();
    io::stdin().read_line(&mut buf)?;
    Ok(buf)
}

/// Display folder name for an agent (subfolder if present, else folder key).
fn display_folder(agent: &Agent) -> String {
    agent
        .subfolder
        .as_deref()
        .unwrap_or(&agent.folder)
        .to_string()
}

/// Truncate a string to max_len, adding "..." if truncated.
fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else if max_len > 3 {
        format!("{}...", &s[..max_len - 3])
    } else {
        s[..max_len].to_string()
    }
}
