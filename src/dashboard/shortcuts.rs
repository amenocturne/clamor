/// A keyboard shortcut for display in help popups and documentation.
pub struct Shortcut {
    pub keys: &'static str,
    pub description: &'static str,
}

const SECTIONS: &[(&str, &[Shortcut])] = &[
    ("Dashboard", DASHBOARD_SHORTCUTS),
    ("Spawn Prompt", SPAWN_PROMPT_SHORTCUTS),
    ("Terminal", TERMINAL_SHORTCUTS),
    ("Copy Mode", COPY_MODE_SHORTCUTS),
];

/// Whether a shortcut matches a filter query (case-insensitive).
fn matches_filter(shortcut: &Shortcut, filter: &str) -> bool {
    if filter.is_empty() {
        return true;
    }
    let f = filter.to_ascii_lowercase();
    shortcut.keys.to_ascii_lowercase().contains(&f)
        || shortcut.description.to_ascii_lowercase().contains(&f)
}

/// Count total display lines for the help popup (with optional filter).
pub fn help_line_count(filter: &str) -> usize {
    let mut count = 0;
    for (_, items) in SECTIONS.iter() {
        let filtered: Vec<_> = items.iter().filter(|s| matches_filter(s, filter)).collect();
        if filtered.is_empty() {
            continue;
        }
        if count > 0 {
            count += 1; // blank line between sections
        }
        count += 2 + filtered.len(); // header + separator + items
    }
    count
}

/// Return the sections (for use by render).
pub fn sections() -> &'static [(&'static str, &'static [Shortcut])] {
    SECTIONS
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
        keys: "V",
        description: "toggle line selection",
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

pub const SPAWN_PROMPT_SHORTCUTS: &[Shortcut] = &[
    Shortcut {
        keys: "Tab / Shift+Tab",
        description: "cycle fields (title \u{2192} description \u{2192} backend)",
    },
    Shortcut {
        keys: "\u{2190} / \u{2192}",
        description: "select backend (when backend field active)",
    },
    Shortcut {
        keys: "Shift+Enter",
        description: "new line in description",
    },
    Shortcut {
        keys: "\u{2191} / \u{2193}",
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
