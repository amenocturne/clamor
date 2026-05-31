set positional-arguments

default:
    @just --list

# Build clamor binary (release mode)
build:
    nix develop -c cargo build --release

# Build clamor binary (debug mode)
build-debug:
    nix develop -c cargo build

# Install clamor from this checkout
install:
    nix develop -c ./scripts/install.sh

# Run clamor dashboard
run *FLAGS:
    nix develop -c cargo run -- "$@"

# Run tests
test:
    nix develop -c cargo test
