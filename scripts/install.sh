#!/usr/bin/env bash
set -euo pipefail

cargo build --release

bin_dir="${CARGO_HOME:-$HOME/.cargo}/bin"
lib_dir="${XDG_DATA_HOME:-$HOME/.local/share}/clamor/lib"
bin_path="$bin_dir/clamor"

mkdir -p "$bin_dir" "$lib_dir"

install -m 0755 target/release/clamor "$bin_path"

if [[ "$(uname -s)" == "Darwin" ]]; then
  dylib_path=""
  while IFS= read -r candidate; do
    case "$candidate" in
      */ghostty-install/lib/libghostty-vt.dylib)
        dylib_path="$candidate"
        break
        ;;
    esac
  done < <(/usr/bin/find target/release/build -name 'libghostty-vt.dylib')
  if [[ -z "$dylib_path" ]]; then
    echo "libghostty-vt.dylib not found under target/release/build" >&2
    exit 1
  fi

  install -m 0644 "$dylib_path" "$lib_dir/libghostty-vt.dylib"

  if ! otool -l "$bin_path" | grep -Fq "$lib_dir"; then
    install_name_tool -add_rpath "$lib_dir" "$bin_path"
  fi
fi

echo "Installed clamor to $bin_path"

pid_file="$HOME/.clamor/clamor.pid"
if [[ -f "$pid_file" ]]; then
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "Note: clamor daemon pid $pid is still running from the previous executable." >&2
    echo "Run 'clamor pre-upgrade' and then 'clamor resume' before testing the newly installed binary." >&2
  fi
fi
