use std::io::{self, Write};

use anyhow::{bail, Context};
use chrono::Utc;

use crate::agent::{generate_id, next_color_index, Agent, AgentState};
use crate::client::DaemonClient;
use crate::config::{resolve_path, ClamorConfig};
use crate::daemon;
use crate::dashboard::keys;
use crate::picker;
use crate::state::{with_state, ClamorState};

fn ensure_daemon() -> anyhow::Result<()> {
    if !daemon::is_daemon_running() {
        daemon::start_daemon_background()?;
    }
    Ok(())
}

pub fn is_debug_mode() -> bool {
    std::env::var("CLAMOR_DEBUG").is_ok()
}

pub fn build_agent_cmd(prompt: Option<&str>) -> Vec<String> {
    if is_debug_mode() {
        let exe = std::env::current_exe().unwrap_or_else(|_| "clamor".into());
        let desc = prompt.unwrap_or("interactive");
        vec![
            exe.to_string_lossy().to_string(),
            "mock-agent".to_string(),
            "--description".to_string(),
            desc.to_string(),
        ]
    } else {
        match prompt {
            Some(p) if !p.is_empty() => vec!["claude".to_string(), p.to_string()],
            _ => vec!["claude".to_string()],
        }
    }
}

pub fn build_resume_cmd(session_id: &str) -> Vec<String> {
    if is_debug_mode() {
        let exe = std::env::current_exe().unwrap_or_else(|_| "clamor".into());
        vec![
            exe.to_string_lossy().to_string(),
            "mock-agent".to_string(),
            "--description".to_string(),
            format!("resumed: {session_id}"),
        ]
    } else {
        vec![
            "claude".to_string(),
            "--resume".to_string(),
            session_id.to_string(),
        ]
    }
}

pub async fn spawn_agent(
    description: Option<String>,
    folder_override: Option<String>,
    force_editor: bool,
) -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = ClamorConfig::load()?;

    if config.folders.is_empty() {
        bail!("No folders configured. Run `clamor config` to add folders.");
    }

    let (folder_name, folder_path) = match folder_override {
        Some(ref name) => {
            let path = config
                .folders
                .get(name)
                .with_context(|| format!("Unknown folder: {name}"))?;
            (name.clone(), path.clone())
        }
        None => tokio::task::block_in_place(|| select_folder(&config))?,
    };

    let cwd = resolve_path(&folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let (title, prompt) = match description {
        Some(d) => (d.clone(), Some(d)),
        None if force_editor => {
            let (t, p) = tokio::task::block_in_place(read_task_from_editor)?;
            (t, Some(p))
        }
        None => tokio::task::block_in_place(read_task_description)?,
    };

    let state = ClamorState::load()?;
    let existing_ids: std::collections::HashSet<String> = state.agents.keys().cloned().collect();
    let id = generate_id(&existing_ids);
    let now = Utc::now();

    let existing: Vec<&Agent> = state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let initial_state = if prompt.is_some() {
        AgentState::Working
    } else {
        AgentState::Input
    };

    let agent = Agent {
        id: id.clone(),
        title: title.clone(),
        folder: folder_name,
        cwd: cwd_str.clone(),
        initial_prompt: prompt.clone(),
        state: initial_state,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        session_id: None,
        key,
        color_index,
    };

    with_state(|state| {
        state.agents.insert(id.clone(), agent);
    })?;

    let cmd = build_agent_cmd(prompt.as_deref());
    let env = vec![("CLAMOR_AGENT_ID".to_string(), id.clone())];
    let (term_cols, term_rows) = crossterm::terminal::size().unwrap_or((80, 24));
    let mut client = DaemonClient::connect().await?;
    client
        .spawn_agent(&id, &cwd_str, &cmd, &env, term_rows, term_cols)
        .await?;

    println!("Spawned agent {id}: {title}");

    Ok(())
}

pub async fn adopt_session(
    session_id: &str,
    description: Option<String>,
    folder_override: Option<String>,
) -> anyhow::Result<()> {
    ensure_daemon()?;
    let config = ClamorConfig::load()?;

    if config.folders.is_empty() {
        bail!("No folders configured. Run `clamor config` to add folders.");
    }

    let (folder_name, folder_path) = match folder_override {
        Some(ref name) => {
            let path = config
                .folders
                .get(name)
                .with_context(|| format!("Unknown folder: {name}"))?;
            (name.clone(), path.clone())
        }
        None => tokio::task::block_in_place(|| select_folder(&config))?,
    };

    let cwd = resolve_path(&folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let title = match description {
        Some(d) => d,
        None => tokio::task::block_in_place(|| {
            print!("Title: ");
            io::stdout().flush()?;
            let input = read_line()?.trim().to_string();
            if input.is_empty() {
                bail!("Empty title, aborting.");
            }
            Ok(input)
        })?,
    };

    let state = ClamorState::load()?;
    let existing_ids: std::collections::HashSet<String> = state.agents.keys().cloned().collect();
    let id = generate_id(&existing_ids);
    let now = Utc::now();

    let existing: Vec<&Agent> = state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        title: title.clone(),
        folder: folder_name,
        cwd: cwd_str.clone(),
        initial_prompt: Some(format!("--resume {session_id}")),
        state: AgentState::Input,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        session_id: Some(session_id.to_string()),
        key,
        color_index,
    };

    with_state(|state| {
        state.agents.insert(id.clone(), agent);
    })?;

    let cmd = build_resume_cmd(session_id);
    let env = vec![("CLAMOR_AGENT_ID".to_string(), id.clone())];
    let (term_cols, term_rows) = crossterm::terminal::size().unwrap_or((80, 24));
    let mut client = DaemonClient::connect().await?;
    client
        .spawn_agent(&id, &cwd_str, &cmd, &env, term_rows, term_cols)
        .await?;

    println!("Adopted session {session_id} as agent {id}: {title}");

    Ok(())
}

pub async fn pre_upgrade() -> anyhow::Result<bool> {
    if !daemon::is_daemon_running() {
        return Ok(true);
    }

    let state = ClamorState::load()?;
    let total = state.agents.len();

    if total > 0 {
        let resumable: Vec<&Agent> = state
            .agents
            .values()
            .filter(|a| a.session_id.is_some())
            .collect();
        let lost: Vec<&Agent> = state
            .agents
            .values()
            .filter(|a| a.session_id.is_none())
            .collect();

        println!();
        if lost.is_empty() {
            println!("{total} session(s) — all will auto-resume after upgrade.");
        } else if resumable.is_empty() {
            println!("{total} session(s) will be lost (no claude session ID captured):");
            for a in &lost {
                println!("    {} {}", a.id, a.title);
            }
        } else {
            println!(
                "{} of {total} session(s) will auto-resume after upgrade.",
                resumable.len()
            );
            println!();
            println!(
                "{} will be lost (no claude session ID captured):",
                lost.len()
            );
            for a in &lost {
                println!("    {} {}", a.id, a.title);
            }
        }
        println!();
    }

    let confirmed = tokio::task::block_in_place(|| {
        print!("Proceed? [y/N] ");
        io::stdout().flush()?;
        let mut answer = String::new();
        io::stdin().read_line(&mut answer)?;
        Ok::<bool, anyhow::Error>(answer.trim().eq_ignore_ascii_case("y"))
    })?;

    if !confirmed {
        println!("Skipping. Rebuild and restart the daemon later.");
        return Ok(false);
    }

    let mut client = DaemonClient::connect().await?;
    client.shutdown().await?;
    println!("Daemon stopped.");

    Ok(true)
}

pub async fn resume_agents() -> anyhow::Result<()> {
    let state = ClamorState::load()?;

    let resumable: Vec<&Agent> = state
        .agents
        .values()
        .filter(|a| a.session_id.is_some())
        .collect();

    if resumable.is_empty() {
        println!("No agents to resume.");
        return Ok(());
    }

    ensure_daemon()?;

    let (term_cols, term_rows) = crossterm::terminal::size().unwrap_or((80, 24));
    let mut client = DaemonClient::connect().await?;
    let mut count = 0;

    for agent in &resumable {
        let session_id = agent.session_id.as_ref().unwrap();
        let cmd = build_resume_cmd(session_id);
        let env = vec![("CLAMOR_AGENT_ID".to_string(), agent.id.clone())];

        match client
            .spawn_agent(&agent.id, &agent.cwd, &cmd, &env, term_rows, term_cols)
            .await
        {
            Ok(()) => {
                count += 1;
                println!("  Resumed {}: {}", agent.id, agent.title);
            }
            Err(e) => {
                eprintln!("  Failed to resume {}: {e:#}", agent.id);
            }
        }
    }

    with_state(|state| {
        for agent in &resumable {
            if let Some(a) = state.agents.get_mut(&agent.id) {
                a.state = AgentState::Input;
                a.last_activity_at = chrono::Utc::now();
            }
        }
    })?;

    println!("Resumed {count}/{} agent(s).", resumable.len());

    Ok(())
}

pub async fn kill_agent(agent_ref: &str) -> anyhow::Result<()> {
    ensure_daemon()?;
    let state = ClamorState::load()?;

    let agent = resolve_agent(&state, agent_ref)?.clone();

    let mut client = DaemonClient::connect().await?;
    let _ = client.kill_agent(&agent.id).await;

    with_state(|state| {
        state.agents.remove(&agent.id);
    })?;

    println!("Killed agent {}: {}", agent.id, agent.title);

    Ok(())
}

pub async fn kill_all_agents() -> anyhow::Result<()> {
    ensure_daemon()?;
    let state = ClamorState::load()?;

    let count = state.agents.len();
    let mut client = DaemonClient::connect().await?;
    for agent in state.agents.values() {
        let _ = client.kill_agent(&agent.id).await;
    }

    with_state(|state| {
        state.agents.clear();
    })?;

    println!("Killed {count} agent(s).");

    Ok(())
}

pub fn clean_agents() -> anyhow::Result<()> {
    let removed = with_state(|state| {
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

pub fn list_agents() -> anyhow::Result<()> {
    let state = ClamorState::load()?;

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
        "{:<id_w$}  {:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>5}",
        "ID", "STATE", "TITLE", "FOLDER", "TIME",
    );

    for agent in &agents {
        let state_str = match agent.state {
            AgentState::Working => "work",
            AgentState::Input => "input",
            AgentState::Done => "done",
            AgentState::Lost => "lost",
        };
        let desc = truncate(&agent.title, desc_w);
        let time = format_duration(agent.started_at);

        println!(
            "{:<id_w$}  {:<state_w$}  {:<desc_w$}  {:<folder_w$}  {:>5}",
            agent.id, state_str, desc, agent.folder, time,
        );
    }

    Ok(())
}

pub fn resolve_agent<'a>(state: &'a ClamorState, agent_ref: &str) -> anyhow::Result<&'a Agent> {
    let matches: Vec<&Agent> = state
        .agents
        .values()
        .filter(|a| a.id.starts_with(agent_ref))
        .collect();

    match matches.len() {
        0 => bail!("no agent matching '{agent_ref}'"),
        1 => Ok(matches[0]),
        _ => {
            let ids: Vec<&str> = matches.iter().map(|a| a.id.as_str()).collect();
            bail!(
                "ambiguous prefix '{agent_ref}' — matches: {}",
                ids.join(", ")
            )
        }
    }
}

pub async fn edit_agent(agent_ref: &str, description: Option<String>) -> anyhow::Result<()> {
    let state = ClamorState::load()?;

    let agent_id = resolve_agent(&state, agent_ref)?.id.clone();

    let new_title = match description {
        Some(d) => d,
        None => tokio::task::block_in_place(|| {
            print!("Title: ");
            io::stdout().flush()?;
            Ok::<String, anyhow::Error>(read_line()?.trim().to_string())
        })?,
    };

    if new_title.is_empty() {
        bail!("Empty title, aborting.");
    }

    with_state(|state| {
        if let Some(agent) = state.agents.get_mut(&agent_id) {
            agent.title = new_title.clone();
        }
    })?;

    println!("Updated title for {agent_id}: {new_title}");
    Ok(())
}

pub fn open_config() -> anyhow::Result<()> {
    let config_path = ClamorConfig::config_dir()?.join("config.json");
    ClamorConfig::ensure_dir()?;

    if !config_path.exists() {
        let _ = ClamorConfig::load()?;
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

use crate::dashboard::render::format_duration;

// ── Helpers ────────────────────────────────────────────────────────

fn select_folder(config: &ClamorConfig) -> anyhow::Result<(String, String)> {
    let mut folders: Vec<(&String, &String)> = config.folders.iter().collect();
    folders.sort_by_key(|(name, _)| name.to_owned());

    let options: Vec<String> = folders.iter().map(|(name, _)| (*name).clone()).collect();

    let idx = picker::pick("Where?", &options)?.context("Aborted.")?;

    let (name, path) = &folders[idx];
    Ok(((*name).clone(), (*path).clone()))
}

fn read_task_description() -> anyhow::Result<(String, Option<String>)> {
    print!("Title: ");
    io::stdout().flush()?;

    let input = read_line()?.trim().to_string();

    if !input.is_empty() {
        return Ok((input.clone(), Some(input)));
    }

    let (title, prompt) = read_task_from_editor()?;
    Ok((title, Some(prompt)))
}

pub fn read_task_from_editor() -> anyhow::Result<(String, String)> {
    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".into());
    let tmp = std::env::temp_dir().join(format!(
        "clamor-task-{}.md",
        generate_id(&std::collections::HashSet::new())
    ));

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
    if max_len <= 3 {
        return s.chars().take(max_len).collect();
    }
    if s.len() <= max_len {
        s.to_string()
    } else {
        let truncated: String = s.chars().take(max_len - 3).collect();
        format!("{}...", truncated)
    }
}
