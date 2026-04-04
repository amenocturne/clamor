use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(
    name = "clamor",
    version,
    about = "Terminal multiplexer for Claude Code agents"
)]
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
        /// Agent title (shown in dashboard). Also used as prompt if no --description.
        title: Option<String>,
        /// Detailed prompt sent to claude (combined with title)
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        folder: Option<String>,
    },

    /// Attach to an agent's terminal
    Attach {
        #[arg(name = "ref")]
        agent_ref: String,
    },

    /// Adopt an external Claude Code session into clamor
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
    Config {
        #[command(subcommand)]
        command: Option<ConfigCommand>,
    },

    /// Print default theme as JSON
    DefaultTheme,

    /// Internal: called by Claude Code hooks (reads stdin JSON)
    Hook,

    /// Check sessions, warn user, stop daemon if confirmed (exit 1 = declined)
    PreUpgrade,

    /// Resume agents from a previous daemon session
    Resume,

    /// Stop the clamor daemon
    Stop,

    /// Run the clamor daemon (usually started automatically)
    Daemon,

    /// Internal: mock agent for testing (hidden)
    #[command(hide = true)]
    MockAgent {
        /// Agent description (passed by clamor)
        #[arg(long, default_value = "test agent")]
        description: String,
        /// How long to run in seconds
        #[arg(long, default_value = "30")]
        duration: u64,
    },
}

#[derive(Subcommand, Debug)]
pub enum ConfigCommand {
    /// Create a starter XDG config with built-in backends
    Init,

    /// Migrate legacy ~/.clamor/config.json to XDG YAML
    Migrate,

    /// Print one built-in backend template as YAML
    PrintBackend { backend_id: String },

    /// Print a full example config with built-in backends
    PrintExample,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_nested_config_commands() {
        let cli = Cli::parse_from(["clamor", "config", "print-backend", "claude-code"]);

        match cli.command {
            Some(Command::Config {
                command: Some(ConfigCommand::PrintBackend { backend_id }),
            }) => assert_eq!(backend_id, "claude-code"),
            other => panic!("unexpected command: {other:?}"),
        }
    }
}
