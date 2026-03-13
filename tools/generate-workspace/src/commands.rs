type ToolEntry = (&'static str, Option<&'static str>, Option<&'static str>, Option<&'static str>);

/// Default commands for each tool: (name, format_cmd, lint_cmd, test_cmd)
const TOOL_COMMANDS: &[ToolEntry] = &[
    (
        "sbt",
        Some("sbt scalafmtAll"),
        Some("sbt 'scalafixAll --check'"),
        Some("sbt test"),
    ),
    (
        "npm",
        Some("npm run format"),
        Some("npm run lint"),
        Some("npm test"),
    ),
    (
        "bun",
        Some("bunx biome check --write ."),
        Some("bunx biome check ."),
        Some("bun test"),
    ),
    (
        "cargo",
        Some("cargo fmt"),
        Some("cargo clippy"),
        Some("cargo test"),
    ),
    (
        "uv",
        Some("uv run ruff format ."),
        Some("uv run ruff check ."),
        Some("uv run pytest"),
    ),
    (
        "gradle",
        None,
        Some("./gradlew check"),
        Some("./gradlew test"),
    ),
    ("xcode", None, None, Some("xcodebuild test")),
    ("spm", None, None, Some("swift test")),
];

pub struct Commands {
    pub format_cmd: Option<String>,
    pub lint_cmd: Option<String>,
    pub test_cmd: Option<String>,
}

/// Get default commands for the first matching tool in the tech list.
pub fn get_commands(tech: &[String]) -> Commands {
    for &(tool, fmt, lint, test) in TOOL_COMMANDS {
        if tech.contains(&tool.to_string()) {
            return Commands {
                format_cmd: fmt.map(|s| s.to_string()),
                lint_cmd: lint.map(|s| s.to_string()),
                test_cmd: test.map(|s| s.to_string()),
            };
        }
    }
    Commands {
        format_cmd: None,
        lint_cmd: None,
        test_cmd: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cargo_commands() {
        let tech = vec!["cargo".to_string(), "rust".to_string()];
        let cmds = get_commands(&tech);
        assert_eq!(cmds.format_cmd.as_deref(), Some("cargo fmt"));
        assert_eq!(cmds.lint_cmd.as_deref(), Some("cargo clippy"));
        assert_eq!(cmds.test_cmd.as_deref(), Some("cargo test"));
    }

    #[test]
    fn no_commands_for_unknown() {
        let tech = vec!["unknown".to_string()];
        let cmds = get_commands(&tech);
        assert!(cmds.format_cmd.is_none());
        assert!(cmds.lint_cmd.is_none());
        assert!(cmds.test_cmd.is_none());
    }

    #[test]
    fn first_tool_wins() {
        // If both npm and cargo present, npm comes first in TOOL_COMMANDS
        let tech = vec!["cargo".to_string(), "npm".to_string(), "rust".to_string()];
        let cmds = get_commands(&tech);
        // npm appears before cargo in TOOL_COMMANDS
        assert_eq!(cmds.format_cmd.as_deref(), Some("npm run format"));
    }

    #[test]
    fn bun_commands() {
        let tech = vec!["bun".to_string(), "javascript".to_string()];
        let cmds = get_commands(&tech);
        assert_eq!(cmds.format_cmd.as_deref(), Some("bunx biome check --write ."));
        assert_eq!(cmds.test_cmd.as_deref(), Some("bun test"));
    }

    #[test]
    fn gradle_no_format() {
        let tech = vec!["gradle".to_string(), "java".to_string()];
        let cmds = get_commands(&tech);
        assert!(cmds.format_cmd.is_none());
        assert_eq!(cmds.lint_cmd.as_deref(), Some("./gradlew check"));
    }
}
