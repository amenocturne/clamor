use std::collections::BTreeMap;

use crate::commands::{get_commands, Commands};

/// A project entry ready for YAML serialization.
struct ProjectEntry {
    path: String,
    tech: Vec<String>,
    format_cmd: Option<String>,
    lint_cmd: Option<String>,
    test_cmd: Option<String>,
}

/// Generate WORKSPACE.yaml content from a map of (relative_path -> tech_stack).
pub fn generate_yaml(projects: &BTreeMap<String, Vec<String>>) -> String {
    let mut lines = Vec::new();
    lines.push("version: 1".to_string());
    lines.push("projects:".to_string());

    for (key, tech) in projects {
        let entry = build_entry(key, tech);
        write_project(&mut lines, key, &entry);
    }

    let mut output = lines.join("\n");
    output.push('\n');
    output
}

fn build_entry(key: &str, tech: &[String]) -> ProjectEntry {
    let Commands {
        format_cmd,
        lint_cmd,
        test_cmd,
    } = get_commands(tech);

    ProjectEntry {
        path: format!("./{}", key),
        tech: tech.to_vec(),
        format_cmd,
        lint_cmd,
        test_cmd,
    }
}

fn write_project(lines: &mut Vec<String>, key: &str, entry: &ProjectEntry) {
    lines.push(format!("  {}:", key));
    lines.push(format!("    path: \"{}\"", entry.path));
    lines.push("    description: \"TODO: describe this project\"".to_string());
    lines.push(format!("    tech: {}", flow_list(&entry.tech)));
    lines.push(format!("    explore_when: {}", flow_list(&[])));
    lines.push(format!("    entry_points: {}", flow_list(&[])));

    if let Some(ref cmd) = entry.format_cmd {
        lines.push(format!("    format_cmd: {}", cmd));
    }
    if let Some(ref cmd) = entry.lint_cmd {
        lines.push(format!("    lint_cmd: {}", cmd));
    }
    if let Some(ref cmd) = entry.test_cmd {
        lines.push(format!("    test_cmd: {}", cmd));
    }
}

/// Format a list in YAML flow style: [item1, item2]
fn flow_list(items: &[String]) -> String {
    if items.is_empty() {
        return "[]".to_string();
    }
    let inner: Vec<String> = items.iter().map(|s| s.to_string()).collect();
    format!("[{}]", inner.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_valid_yaml() {
        let mut projects = BTreeMap::new();
        projects.insert(
            "personal/my-app".to_string(),
            vec!["cargo".to_string(), "rust".to_string()],
        );

        let yaml = generate_yaml(&projects);

        assert!(yaml.contains("version: 1"));
        assert!(yaml.contains("personal/my-app:"));
        assert!(yaml.contains("path: \"./personal/my-app\""));
        assert!(yaml.contains("tech: [cargo, rust]"));
        assert!(yaml.contains("explore_when: []"));
        assert!(yaml.contains("entry_points: []"));
        assert!(yaml.contains("format_cmd: cargo fmt"));
        assert!(yaml.contains("lint_cmd: cargo clippy"));
        assert!(yaml.contains("test_cmd: cargo test"));
    }

    #[test]
    fn unknown_tech_no_commands() {
        let mut projects = BTreeMap::new();
        projects.insert("misc/docs".to_string(), vec!["unknown".to_string()]);

        let yaml = generate_yaml(&projects);

        assert!(yaml.contains("tech: [unknown]"));
        assert!(!yaml.contains("format_cmd"));
        assert!(!yaml.contains("lint_cmd"));
        assert!(!yaml.contains("test_cmd"));
    }

    #[test]
    fn projects_sorted_alphabetically() {
        let mut projects = BTreeMap::new();
        projects.insert("z-project".to_string(), vec!["unknown".to_string()]);
        projects.insert("a-project".to_string(), vec!["unknown".to_string()]);

        let yaml = generate_yaml(&projects);
        let a_pos = yaml.find("a-project:").unwrap();
        let z_pos = yaml.find("z-project:").unwrap();
        assert!(a_pos < z_pos);
    }

    #[test]
    fn empty_flow_list() {
        assert_eq!(flow_list(&[]), "[]");
    }

    #[test]
    fn single_item_flow_list() {
        let items = vec!["rust".to_string()];
        assert_eq!(flow_list(&items), "[rust]");
    }

    #[test]
    fn multi_item_flow_list() {
        let items = vec!["cargo".to_string(), "rust".to_string()];
        assert_eq!(flow_list(&items), "[cargo, rust]");
    }

    #[test]
    fn sbt_commands_with_quotes() {
        let mut projects = BTreeMap::new();
        projects.insert("my-scala".to_string(), vec!["sbt".to_string(), "scala".to_string()]);

        let yaml = generate_yaml(&projects);
        assert!(yaml.contains("lint_cmd: sbt 'scalafixAll --check'"));
    }
}
