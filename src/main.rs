mod agent;
mod cli;
mod client;
mod config;
mod daemon;
mod dashboard;
mod hook;
mod mock_agent;
mod pane;
mod picker;
mod protocol;
mod spawn;
mod state;
mod watcher;

use anyhow::Result;
use clap::Parser;
use cli::{Cli, Command};
use config::FleetConfig;

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        None => {
            let config = FleetConfig::load()?;
            if config.folders.is_empty() {
                eprintln!("Error: No folders configured. Run `fleet config` to add folders.");
                std::process::exit(1);
            }
            dashboard::run(&config, None)?;
        }
        Some(Command::Ls) => {
            spawn::list_agents()?;
        }
        Some(Command::Attach { agent_ref }) => {
            let config = FleetConfig::load()?;
            let state = state::FleetState::load()?;
            let agent = spawn::resolve_agent(&state, &agent_ref)?;
            dashboard::run(&config, Some(agent.id.clone()))?;
        }
        Some(Command::New {
            title,
            description,
            folder,
        }) => {
            // If title provided via CLI: title is set, description becomes prompt
            // If only title: title is both title and prompt (backward compat)
            let effective_desc = match (title, description) {
                (Some(t), Some(d)) => Some(format!("{t}\n\n{d}")),
                (Some(t), None) => Some(t),
                (None, _) => None,
            };
            spawn::spawn_agent(effective_desc, folder, false)?;
        }
        Some(Command::Adopt {
            session_id,
            description,
            folder,
        }) => {
            spawn::adopt_session(&session_id, description, folder)?;
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
        Some(Command::Kill {
            agent_ref: Some(r), ..
        }) => {
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
        Some(Command::Hook) => {
            hook::run();
        }
        Some(Command::PreUpgrade) => {
            if !spawn::pre_upgrade()? {
                std::process::exit(1);
            }
        }
        Some(Command::Resume) => {
            spawn::resume_agents()?;
        }
        Some(Command::Stop) => {
            let mut client = client::DaemonClient::connect()?;
            client.shutdown()?;
            println!("Fleet daemon stopped");
        }
        Some(Command::Daemon) => {
            daemon::run_daemon().await?;
        }
        Some(Command::MockAgent {
            description,
            duration,
        }) => {
            mock_agent::run(&description, duration);
        }
    }

    Ok(())
}
