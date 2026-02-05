# Workspace Generator

Scans for git repositories and generates a `WORKSPACE.yaml` with detected tech stacks.

## Usage

```bash
uv run generate-workspace.py --root ~/projects --output WORKSPACE.yaml
```

## Options

- `--root PATH`: Directory to scan (default: current directory)
- `--output PATH`: Output file (default: WORKSPACE.yaml)

## Tech Detection

Detects tech stacks from build files:

| Build File | Tech | Tools |
|------------|------|-------|
| `build.sbt` | scala | sbt |
| `package.json` | javascript, typescript | npm |
| `Cargo.toml` | rust | cargo |
| `go.mod` | go | - |
| `pyproject.toml` | python | uv |
| `build.gradle` | kotlin, java | gradle |
| `Package.swift` | swift | spm |
| `.xcodeproj/` | swift | xcode |

## Output Format

```yaml
version: 1
projects:
  project-name:
    path: ./path/to/project
    description: "TODO: describe"
    tech: [scala, sbt]
    explore_when: []
    entry_points: []
    format_cmd: "sbt scalafmtAll"
    lint_cmd: "sbt 'scalafixAll --check'"
    test_cmd: "sbt test"
```
