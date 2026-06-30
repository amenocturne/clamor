use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

const GHOSTTY_REPO: &str = "https://github.com/ghostty-org/ghostty.git";
const GHOSTTY_COMMIT: &str = "bebca84668947bfc92b9a30ed58712e1c34eee1d";

fn main() {
    if env::var("DOCS_RS").is_ok() {
        return;
    }

    println!("cargo:rerun-if-env-changed=LIBGHOSTTY_VT_SYS_OPTIMIZE");
    println!("cargo:rerun-if-env-changed=GHOSTTY_SOURCE_DIR");
    println!("cargo:rerun-if-env-changed=ZIG");
    println!("cargo:rerun-if-env-changed=TARGET");
    println!("cargo:rerun-if-env-changed=HOST");
    println!("cargo:rerun-if-changed=build.rs");

    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR must be set"));
    let target = env::var("TARGET").expect("TARGET must be set");
    let host = env::var("HOST").expect("HOST must be set");

    let ghostty_dir = match env::var("GHOSTTY_SOURCE_DIR") {
        Ok(dir) => {
            let p = PathBuf::from(dir);
            assert!(
                p.join("build.zig").exists(),
                "GHOSTTY_SOURCE_DIR does not contain build.zig: {}",
                p.display()
            );
            p
        }
        Err(_) => fetch_ghostty(&out_dir),
    };

    let install_prefix = out_dir.join("ghostty-install");
    let optimize = env::var("LIBGHOSTTY_VT_SYS_OPTIMIZE")
        .unwrap_or_else(|_| "ReleaseFast".into());

    let zig = find_zig();
    let mut build = Command::new(&zig);
    build
        .arg("build")
        .arg("-Demit-lib-vt")
        .arg(format!("-Doptimize={optimize}"))
        .arg("--prefix")
        .arg(&install_prefix)
        .current_dir(&ghostty_dir);

    if target != host {
        let zig_target = zig_target(&target);
        build.arg(format!("-Dtarget={zig_target}"));
    }

    run(build, "zig build");

    let lib_dir = install_prefix.join("lib");
    let include_dir = install_prefix.join("include");

    assert!(
        lib_dir.exists(),
        "expected lib dir at {}",
        lib_dir.display()
    );
    assert!(
        include_dir.join("ghostty").join("vt.h").exists(),
        "expected header at {}",
        include_dir.join("ghostty").join("vt.h").display()
    );

    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=dylib=ghostty-vt");
    println!("cargo:include={}", include_dir.display());
}

/// Find zig binary. Prefers ZIG env var, then brew zig@0.15 on macOS
/// (which links against system LLVM and handles macOS symbol variants),
/// then falls back to PATH.
fn find_zig() -> String {
    if let Ok(zig) = env::var("ZIG") {
        return zig;
    }

    if cfg!(target_os = "macos") {
        if let Ok(output) = Command::new("brew").arg("--prefix").arg("zig@0.15").output() {
            if output.status.success() {
                let prefix = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let brew_zig = format!("{prefix}/bin/zig");
                if Path::new(&brew_zig).exists() {
                    eprintln!("libghostty-vt-sys: using brew zig@0.15 at {brew_zig}");
                    return brew_zig;
                }
            }
        }
    }

    "zig".into()
}

fn fetch_ghostty(out_dir: &Path) -> PathBuf {
    let src_dir = out_dir.join("ghostty-src");
    let stamp = src_dir.join(".ghostty-commit");

    if stamp.exists()
        && let Ok(existing) = std::fs::read_to_string(&stamp)
            && existing.trim() == GHOSTTY_COMMIT {
                return src_dir;
            }

    if src_dir.exists() {
        std::fs::remove_dir_all(&src_dir)
            .unwrap_or_else(|e| panic!("failed to remove {}: {e}", src_dir.display()));
    }

    eprintln!("Fetching ghostty {GHOSTTY_COMMIT} ...");

    let mut clone = Command::new("git");
    clone
        .arg("clone")
        .arg("--filter=blob:none")
        .arg("--no-checkout")
        .arg(GHOSTTY_REPO)
        .arg(&src_dir);
    run(clone, "git clone ghostty");

    let mut checkout = Command::new("git");
    checkout
        .arg("checkout")
        .arg(GHOSTTY_COMMIT)
        .current_dir(&src_dir);
    run(checkout, "git checkout ghostty commit");

    std::fs::write(&stamp, GHOSTTY_COMMIT)
        .unwrap_or_else(|e| panic!("failed to write stamp: {e}"));

    src_dir
}

fn run(mut command: Command, context: &str) {
    let status = command
        .status()
        .unwrap_or_else(|error| panic!("failed to execute {context}: {error}"));
    assert!(status.success(), "{context} failed with status {status}");
}

fn zig_target(target: &str) -> String {
    let value = match target {
        "x86_64-unknown-linux-gnu" => "x86_64-linux-gnu",
        "x86_64-unknown-linux-musl" => "x86_64-linux-musl",
        "aarch64-unknown-linux-gnu" => "aarch64-linux-gnu",
        "aarch64-unknown-linux-musl" => "aarch64-linux-musl",
        "aarch64-apple-darwin" => "aarch64-macos-none",
        "x86_64-apple-darwin" => "x86_64-macos-none",
        other => panic!("unsupported Rust target for vendored build: {other}"),
    };
    value.to_owned()
}
