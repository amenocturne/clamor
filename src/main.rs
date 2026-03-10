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

fn main() -> Result<()> {
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
            let state = state::FleetState::load(&config)?;
            let agent = spawn::resolve_agent(&state, &agent_ref)
                .ok_or_else(|| anyhow::anyhow!("no agent matching '{agent_ref}'"))?;
            dashboard::run(&config, Some(agent.id.clone()))?;
        }
        Some(Command::New { description, folder }) => {
            spawn::spawn_agent(description, folder, false)?;
        }
        Some(Command::Adopt { session_id, description, folder }) => {
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
        Some(Command::Hook) => {
            hook::run();
        }
        Some(Command::Stop) => {
            let mut client = client::DaemonClient::connect()?;
            client.shutdown()?;
            println!("Fleet daemon stopped");
        }
        Some(Command::Daemon) => {
            daemon::run_daemon()?;
        }
        Some(Command::MockAgent { description, duration }) => {
            mock_agent::run(&description, duration);
        }
    }

    Ok(())
}
