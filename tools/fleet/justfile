set positional-arguments

default:
    @just --list

# Build fleet binary (release mode)
build:
    cargo build --release

# Build fleet binary (debug mode)
build-debug:
    cargo build

# Run fleet dashboard
run *FLAGS:
    cargo run -- "$@"

# Run tests
test:
    cargo test
