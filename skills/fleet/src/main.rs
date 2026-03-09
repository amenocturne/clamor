mod agent;
mod cli;
mod config;
mod dashboard;
mod hook;
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
            eprintln!("dashboard: not implemented");
        }
        Some(Command::Ls) => {
            spawn::list_agents()?;
        }
        Some(Command::New { description, folder }) => {
            spawn::spawn_agent(description, folder)?;
        }
        Some(Command::Attach { agent_ref }) => {
            eprintln!("attach: not implemented (ref={})", agent_ref);
        }
        Some(Command::Edit {
            agent_ref,
            description,
        }) => {
            eprintln!(
                "edit: not implemented (ref={}, description={:?})",
                agent_ref, description
            );
        }
        Some(Command::Kill { agent_ref }) => {
            spawn::kill_agent(&agent_ref)?;
        }
        Some(Command::Clean) => {
            spawn::clean_agents()?;
        }
        Some(Command::Config) => {
            eprintln!("config: not implemented");
        }
        Some(Command::Hook) => {
            if let Err(e) = hook::run() {
                eprintln!("fleet hook error: {e}");
            }
        }
    }

    Ok(())
}
