use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "fleet", about = "CLI orchestrator for Claude Code instances via tmux")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Option<Command>,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// One-shot status table
    Ls,

    /// Spawn a new agent
    New {
        /// Description of the task
        description: Option<String>,

        /// Folder name override
        #[arg(long)]
        folder: Option<String>,
    },

    /// Switch to an agent's tmux session
    Attach {
        /// Jump key letter or hex ID prefix
        #[arg(name = "ref")]
        agent_ref: String,
    },

    /// Update an agent's description
    Edit {
        /// Jump key letter or hex ID prefix
        #[arg(name = "ref")]
        agent_ref: String,

        /// New description
        description: Option<String>,
    },

    /// Terminate an agent (or all with --all)
    Kill {
        /// Jump key letter or hex ID prefix
        #[arg(name = "ref", required_unless_present = "all")]
        agent_ref: Option<String>,

        /// Kill all agents
        #[arg(long)]
        all: bool,
    },

    /// Remove done agents
    Clean,

    /// Open config in $EDITOR
    Config,

    /// Open dashboard in a tmux popup (bind to Ctrl+F)
    Popup,

    /// Internal: called by Claude Code hooks (reads stdin JSON)
    Hook,
}
