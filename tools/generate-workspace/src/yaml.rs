use std::collections::BTreeMap;

/// Generate WORKSPACE.yaml content from a map of (relative_path -> tech_stack).
pub fn generate_yaml(projects: &BTreeMap<String, Vec<String>>) -> String {
    let mut lines = Vec::new();
    lines.push("version: 1".to_string());
    lines.push("projects:".to_string());

    for (key, tech) in projects {
        write_project(&mut lines, key, tech);
    }

    let mut output = lines.join("\n");
    output.push('\n');
    output
}

fn write_project(lines: &mut Vec<String>, key: &str, tech: &[String]) {
    lines.push(format!("  {}:", key));
    lines.push(format!("    path: \"./{key}\""));
    lines.push("    description: \"TODO: describe this project\"".to_string());
    lines.push(format!("    tech: {}", flow_list(tech)));
    lines.push(format!("    explore_when: {}", flow_list(&[])));
    lines.push(format!("    entry_points: {}", flow_list(&[])));
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
}
