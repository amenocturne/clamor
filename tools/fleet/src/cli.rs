use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "fleet", about = "Terminal multiplexer for Claude Code agents")]
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
        description: Option<String>,
        #[arg(long)]
        folder: Option<String>,
    },

    /// Attach to an agent's terminal
    Attach {
        #[arg(name = "ref")]
        agent_ref: String,
    },

    /// Adopt an external Claude Code session into fleet
    Adopt {
        /// Claude Code session ID
        session_id: String,
        /// Description of the task
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        folder: Option<String>,
    },

    /// Update an agent's description
    Edit {
        #[arg(name = "ref")]
        agent_ref: String,
        description: Option<String>,
    },

    /// Terminate an agent (or all with --all)
    Kill {
        #[arg(name = "ref", required_unless_present = "all")]
        agent_ref: Option<String>,
        #[arg(long)]
        all: bool,
    },

    /// Remove done agents
    Clean,

    /// Open config in $EDITOR
    Config,

    /// Internal: called by Claude Code hooks (reads stdin JSON)
    Hook,

    /// Stop the fleet daemon
    Stop,

    /// Run the fleet daemon (usually started automatically)
    Daemon,

    /// Internal: mock agent for testing (hidden)
    #[command(hide = true)]
    MockAgent {
        /// Agent description (passed by fleet)
        #[arg(long, default_value = "test agent")]
        description: String,
        /// How long to run in seconds
        #[arg(long, default_value = "30")]
        duration: u64,
    },
}
