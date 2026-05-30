set positional-arguments

default:
    @just --list

# Build clamor binary (release mode)
build:
    cargo build --release

# Build clamor binary (debug mode)
build-debug:
    cargo build

# Install clamor from this checkout
install:
    cargo install --path .

# Run clamor dashboard
run *FLAGS:
    cargo run -- "$@"

# Run tests
test:
    cargo test
