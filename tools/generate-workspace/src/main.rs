mod commands;
mod detect;
mod scan;
mod yaml;

use std::collections::BTreeMap;
use std::path::PathBuf;

fn parse_args() -> (PathBuf, PathBuf) {
    let args: Vec<String> = std::env::args().collect();
    let mut root = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut output = PathBuf::from("WORKSPACE.yaml");

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--root" => {
                i += 1;
                if i < args.len() {
                    root = PathBuf::from(&args[i]);
                } else {
                    eprintln!("Error: --root requires a path argument");
                    std::process::exit(1);
                }
            }
            "--output" => {
                i += 1;
                if i < args.len() {
                    output = PathBuf::from(&args[i]);
                } else {
                    eprintln!("Error: --output requires a path argument");
                    std::process::exit(1);
                }
            }
            "--help" | "-h" => {
                eprintln!("Usage: generate-workspace [--root PATH] [--output PATH]");
                eprintln!();
                eprintln!("Scan for git repos and generate WORKSPACE.yaml");
                eprintln!();
                eprintln!("Options:");
                eprintln!("  --root PATH    Directory to scan (default: CWD)");
                eprintln!("  --output PATH  Output file (default: WORKSPACE.yaml)");
                std::process::exit(0);
            }
            other => {
                eprintln!("Unknown argument: {}", other);
                std::process::exit(1);
            }
        }
        i += 1;
    }

    (root, output)
}

fn main() {
    let (root, output) = parse_args();

    let root = root.canonicalize().unwrap_or_else(|e| {
        eprintln!("Error: cannot resolve root path: {}", e);
        std::process::exit(1);
    });

    // Phase 1: Find repos
    eprintln!("Scanning for repos...");
    let repos = scan::find_git_repos(&root);
    eprintln!("Found {} repos", repos.len());

    // Phase 2: Detect tech stacks
    eprintln!("Detecting tech stacks...");
    let mut projects = BTreeMap::new();

    for repo in &repos {
        let rel_path = repo
            .strip_prefix(&root)
            .unwrap_or(repo)
            .to_string_lossy()
            .to_string();

        eprintln!("  {}", rel_path);
        let tech = detect::detect_tech_stack(repo);
        projects.insert(rel_path, tech);
    }

    // Phase 3: Generate YAML
    let yaml_content = yaml::generate_yaml(&projects);

    // Phase 4: Write output
    if output.to_string_lossy() == "/dev/stdout" || output.to_string_lossy() == "-" {
        print!("{}", yaml_content);
    } else {
        std::fs::write(&output, &yaml_content).unwrap_or_else(|e| {
            eprintln!("Error writing {}: {}", output.display(), e);
            std::process::exit(1);
        });
        eprintln!("Generated {}", output.display());
    }

    // Summary
    eprintln!("{} projects:", projects.len());
    for (name, tech) in &projects {
        eprintln!("  {} : {}", name, tech.join(", "));
    }
}
