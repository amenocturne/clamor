/// A keyboard shortcut for display in help popups and documentation.
pub struct Shortcut {
    pub keys: &'static str,
    pub description: &'static str,
}

pub const DASHBOARD_SHORTCUTS: &[Shortcut] = &[
    Shortcut {
        keys: "J / K / ↑↓",
        description: "navigate",
    },
    Shortcut {
        keys: "Enter",
        description: "attach",
    },
    Shortcut {
        keys: "gg / G",
        description: "first / last",
    },
    Shortcut {
        keys: "v",
        description: "toggle select",
    },
    Shortcut {
        keys: "V",
        description: "select all / none",
    },
    Shortcut {
        keys: "/",
        description: "filter",
    },
    Shortcut {
        keys: "c",
        description: "create",
    },
    Shortcut {
        keys: "C",
        description: "create ($EDITOR)",
    },
    Shortcut {
        keys: "e + key",
        description: "edit description",
    },
    Shortcut {
        keys: "x + key",
        description: "kill (batch if selected)",
    },
    Shortcut {
        keys: "R",
        description: "adopt session",
    },
    Shortcut {
        keys: "Esc",
        description: "clear selection",
    },
    Shortcut {
        keys: "q",
        description: "quit",
    },
];

pub const TERMINAL_SHORTCUTS: &[Shortcut] = &[
    Shortcut {
        keys: "^F",
        description: "detach (back to dashboard)",
    },
    Shortcut {
        keys: "^C",
        description: "send SIGINT to agent",
    },
    Shortcut {
        keys: "^J",
        description: "snap to bottom (live view)",
    },
    Shortcut {
        keys: "^S",
        description: "enter copy mode",
    },
    Shortcut {
        keys: "scroll up",
        description: "freeze + scroll",
    },
];

pub const COPY_MODE_SHORTCUTS: &[Shortcut] = &[
    Shortcut {
        keys: "h/j/k/l",
        description: "move cursor",
    },
    Shortcut {
        keys: "v",
        description: "toggle selection",
    },
    Shortcut {
        keys: "y",
        description: "yank to clipboard + exit",
    },
    Shortcut {
        keys: "0 / $",
        description: "start / end of line",
    },
    Shortcut {
        keys: "^U / ^D",
        description: "half page up / down",
    },
    Shortcut {
        keys: "gg / G",
        description: "top / bottom of scrollback",
    },
    Shortcut {
        keys: "q / Esc",
        description: "exit copy mode",
    },
];

#[allow(dead_code)] // available for future contextual help
pub const SPAWN_PROMPT_SHORTCUTS: &[Shortcut] = &[
    Shortcut {
        keys: "Tab",
        description: "toggle title / description",
    },
    Shortcut {
        keys: "↑ / ↓",
        description: "prompt history",
    },
    Shortcut {
        keys: "^W / Alt+Bksp",
        description: "delete word",
    },
    Shortcut {
        keys: "^U",
        description: "delete line",
    },
];
