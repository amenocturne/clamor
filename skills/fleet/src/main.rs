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

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        None | Some(Command::Watch) => {
            let config = config::FleetConfig::load()?;
            let respawned = spawn::respawn_dead()?;
            if respawned > 0 {
                eprintln!("Respawned {respawned} dead agent(s).");
            }
            dashboard::run(&config)?;
        }
        Some(Command::Ls) => {
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
        Some(Command::Hook) => {
            hook::run();
        }
    }

    Ok(())
}
