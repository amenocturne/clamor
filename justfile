set positional-arguments

default:
    @just --list

# Build clamor binary (release mode)
build:
    nix develop -c cargo build --release

# Build clamor binary (debug mode)
build-debug:
    nix develop -c cargo build

# Install clamor from this checkout using the local Rust toolchain
install:
    ./scripts/install.sh

# Install clamor from this checkout inside the Nix dev shell
install-nix:
    nix develop -c ./scripts/install.sh

# Run clamor dashboard
run *FLAGS:
    nix develop -c cargo run -- "$@"

# Run tests
test:
    nix develop -c cargo test
