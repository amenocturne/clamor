mod agent;
mod cli;
mod config;
mod dashboard;
mod hook;
mod picker;
mod spawn;
mod state;
mod tmux;

use anyhow::Result;
use clap::Parser;
use cli::{Cli, Command};
use config::FleetConfig;

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        None | Some(Command::Ls) => {
            spawn::list_agents()?;
        }
        Some(Command::New { description, folder }) => {
            spawn::spawn_agent(description, folder, false)?;
        }
        Some(Command::Attach { agent_ref }) => {
            spawn::attach_agent(&agent_ref)?;
        }
        Some(Command::Edit {
            agent_ref,
            description,
        }) => {
            spawn::edit_agent(&agent_ref, description)?;
        }
        Some(Command::Kill { all: true, .. }) => {
            spawn::kill_all_agents()?;
        }
        Some(Command::Kill { agent_ref: Some(r), .. }) => {
            spawn::kill_agent(&r)?;
        }
        Some(Command::Kill { .. }) => {
            unreachable!("clap enforces ref or --all");
        }
        Some(Command::Clean) => {
            spawn::clean_agents()?;
        }
        Some(Command::Config) => {
            spawn::open_config()?;
        }
        Some(Command::Popup) => {
            if std::env::var("FLEET_POPUP").is_ok() {
                let config = FleetConfig::load()?;
                let respawned = spawn::respawn_dead()?;
                if respawned > 0 {
                    eprintln!("Respawned {respawned} dead agent(s).");
                }
                dashboard::run(&config)?;
            } else {
                check_claude_keybindings();
                open_popup()?;
            }
        }
        Some(Command::Hook) => {
            hook::run();
        }
    }

    Ok(())
}

fn open_popup() -> Result<()> {
    tmux::require_tmux()?;
    let _ = std::fs::remove_file("/tmp/fleet-target");
    let _ = std::fs::remove_file("/tmp/fleet-open-term");

    std::process::Command::new("tmux")
        .args(["display-popup", "-E", "-w80%", "-h70%", "FLEET_POPUP=1 fleet popup"])
        .status()?;

    Ok(())
}

fn check_claude_keybindings() {
    let path = std::env::var("HOME")
        .map(|h| std::path::PathBuf::from(h).join(".claude/keybindings.json"))
        .unwrap_or_default();

    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => {
            eprintln!(
                "warning: ~/.claude/keybindings.json not found. \
                 Ctrl+F/Ctrl+T won't work from Claude Code sessions. \
                 See: fleet README for setup."
            );
            return;
        }
    };

    let missing: Vec<&str> = ["ctrl+f", "ctrl+t"]
        .into_iter()
        .filter(|key| !content.contains(key))
        .collect();

    if !missing.is_empty() {
        eprintln!(
            "warning: {} not unbound in ~/.claude/keybindings.json. \
             Set to null so tmux can intercept. See: fleet README",
            missing.join(", ")
        );
    }
}
