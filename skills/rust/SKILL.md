---
name: rust
description: Rust development patterns. Use when working on Rust projects. Provides cargo workflows, error handling, and functional idioms.
author: amenocturne
---

# Rust Development

Rust with functional patterns and strict clippy.

## Stack

| Purpose | Tool |
|---------|------|
| Build | cargo |
| Formatter | rustfmt |
| Linter | clippy |
| Testing | cargo test |

## Commands

```bash
just run         # cargo run
just build       # cargo build
just test        # cargo test
just lint        # cargo clippy -- -D warnings
just fmt         # cargo fmt
just fix         # cargo clippy --fix
```

## Project Structure

```
project/
├── src/
│   ├── main.rs          # Entry point (binary)
│   ├── lib.rs           # Library root (if lib)
│   ├── types.rs         # Type definitions
│   └── core/            # Business logic
├── tests/
│   └── integration.rs   # Integration tests
├── Cargo.toml
└── justfile
```

## Functional Patterns

### Prefer Expressions

```rust
fn classify(n: i32) -> &'static str {
    match n {
        n if n < 0 => "negative",
        0 => "zero",
        _ => "positive",
    }
}

let status = if active { "on" } else { "off" };
```

### Immutability by Default

```rust
let items = vec![1, 2, 3];
let doubled: Vec<_> = items.iter().map(|x| x * 2).collect();

// When mutation needed, scope it tightly
let result = {
    let mut buffer = Vec::new();
    // ... fill buffer
    buffer
};
```

### Iterators Over Loops

```rust
// Good: iterator chains
let sum: i32 = items.iter().filter(|x| x.active).map(|x| x.value).sum();
```

### Enums for State

```rust
enum Status {
    Pending,
    Processing { started: Instant },
    Complete { result: Output },
    Failed { error: String },
}

fn describe(status: &Status) -> String {
    match status {
        Status::Pending => "waiting".into(),
        Status::Processing { started } => format!("running since {:?}", started),
        Status::Complete { result } => format!("done: {}", result),
        Status::Failed { error } => format!("error: {}", error),
    }
}
```

## Error Handling

```rust
use thiserror::Error;

#[derive(Error, Debug)]
enum AppError {
    #[error("failed to parse: {0}")]
    Parse(String),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
}

// Use ? for propagation
fn process(path: &Path) -> Result<Output, AppError> {
    let content = std::fs::read_to_string(path)?;
    let parsed = parse(&content).map_err(AppError::Parse)?;
    Ok(transform(parsed))
}

// Handle errors at boundaries
fn main() {
    if let Err(e) = run() {
        eprintln!("Error: {e}");
        std::process::exit(1);
    }
}
```

## Type Definitions

```rust
// Newtype for type safety
struct UserId(String);
struct Email(String);

// Derive what you need
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct User {
    id: UserId,
    email: Email,
    active: bool,
}

type Result<T> = std::result::Result<T, AppError>;
```

## Testing

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_negative() {
        assert_eq!(classify(-5), "negative");
    }

    #[test]
    fn classify_zero() {
        assert_eq!(classify(0), "zero");
    }
}
```

## Cargo.toml

```toml
[package]
name = "project"
version = "0.1.0"
edition = "2021"

[dependencies]
thiserror = "1"
serde = { version = "1", features = ["derive"] }

[dev-dependencies]
pretty_assertions = "1"

[lints.clippy]
pedantic = "warn"
```

## Anti-patterns

- `unwrap()` in library code (use `?` or `expect` with message)
- `clone()` to satisfy borrow checker without understanding why
- Mutable state when iterators work
- Manual loops when `map/filter/fold` suffice
- Ignoring clippy warnings
