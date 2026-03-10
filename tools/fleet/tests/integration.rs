use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

fn fleet_bin() -> PathBuf {
    env!("CARGO_BIN_EXE_fleet").into()
}

fn fleet_cmd() -> Command {
    let mut cmd = Command::new(fleet_bin());
    cmd.env("FLEET_DEBUG", "1");
    cmd
}

/// Create an isolated HOME directory with a minimal fleet config.
fn setup_test_env() -> PathBuf {
    let test_home = std::env::temp_dir().join(format!(
        "fleet-test-{}-{}",
        std::process::id(),
        rand_suffix()
    ));
    std::fs::create_dir_all(test_home.join(".fleet")).unwrap();

    let config = serde_json::json!({
        "folders": {
            "test": test_home.to_string_lossy()
        }
    });
    std::fs::write(
        test_home.join(".fleet/config.json"),
        serde_json::to_string_pretty(&config).unwrap(),
    )
    .unwrap();

    test_home
}

fn rand_suffix() -> u64 {
    use std::time::SystemTime;
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

/// Kill any daemon and remove the temp directory.
fn cleanup_test_env(test_home: &PathBuf) {
    let pid_file = test_home.join(".fleet/fleet.pid");
    if let Ok(pid_str) = std::fs::read_to_string(&pid_file) {
        if let Ok(pid) = pid_str.trim().parse::<i32>() {
            unsafe {
                libc::kill(pid, libc::SIGTERM);
            }
            // Brief wait for process to exit
            std::thread::sleep(Duration::from_millis(100));
        }
    }
    let _ = std::fs::remove_dir_all(test_home);
}

/// Start the daemon in the background and wait for it to be ready.
fn start_daemon(home: &PathBuf) {
    let mut child = Command::new(fleet_bin())
        .arg("daemon")
        .env("HOME", home)
        .env("FLEET_DEBUG", "1")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("failed to start daemon");

    // Wait for the socket to appear
    let sock = home.join(".fleet/fleet.sock");
    for _ in 0..50 {
        if sock.exists() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }

    // If we get here, the daemon didn't start
    let _ = child.kill();
    panic!("daemon did not start within 5s");
}

#[test]
fn test_daemon_starts_and_stops() {
    let home = setup_test_env();
    start_daemon(&home);

    assert!(home.join(".fleet/fleet.pid").exists());
    assert!(home.join(".fleet/fleet.sock").exists());

    cleanup_test_env(&home);
}

#[test]
fn test_spawn_and_list() {
    let home = setup_test_env();
    start_daemon(&home);

    // Spawn an agent
    let output = fleet_cmd()
        .args(["new", "--folder", "test", "test task"])
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "spawn failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    // List agents
    let output = fleet_cmd()
        .arg("ls")
        .env("HOME", &home)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("test task"), "agent not listed: {stdout}");
    assert!(stdout.contains("work"), "agent not in working state: {stdout}");

    cleanup_test_env(&home);
}

#[test]
fn test_spawn_and_kill() {
    let home = setup_test_env();
    start_daemon(&home);

    // Spawn
    let output = fleet_cmd()
        .args(["new", "--folder", "test", "kill me"])
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(output.status.success());

    // Extract agent ID from output ("Spawned agent XXXXXX: kill me")
    let stdout = String::from_utf8_lossy(&output.stdout);
    let id = stdout
        .split_whitespace()
        .nth(2)
        .unwrap()
        .trim_end_matches(':');

    // Kill it
    let output = fleet_cmd()
        .args(["kill", id])
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "kill failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    // Verify it's gone from list
    let output = fleet_cmd()
        .arg("ls")
        .env("HOME", &home)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        !stdout.contains("kill me") || stdout.contains("No agents"),
        "agent still listed: {stdout}"
    );

    cleanup_test_env(&home);
}

#[test]
fn test_kill_all() {
    let home = setup_test_env();
    start_daemon(&home);

    // Spawn two agents
    for desc in ["agent one", "agent two"] {
        let output = fleet_cmd()
            .args(["new", "--folder", "test", desc])
            .env("HOME", &home)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "spawn '{}' failed: {}",
            desc,
            String::from_utf8_lossy(&output.stderr)
        );
        std::thread::sleep(Duration::from_millis(100));
    }

    // Kill all
    let output = fleet_cmd()
        .args(["kill", "--all"])
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "kill --all failed: stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("2 agent(s)"));

    // List should be empty
    let output = fleet_cmd()
        .arg("ls")
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&output.stdout).contains("No agents"));

    cleanup_test_env(&home);
}

#[test]
fn test_adopt_session() {
    let home = setup_test_env();
    start_daemon(&home);

    let output = fleet_cmd()
        .args([
            "adopt",
            "fake-session-123",
            "--folder",
            "test",
            "-d",
            "adopted task",
        ])
        .env("HOME", &home)
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "adopt failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.contains("Adopted session fake-session-123"),
        "unexpected output: {stdout}"
    );

    // Should appear in list
    let output = fleet_cmd()
        .arg("ls")
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&output.stdout).contains("adopted task"));

    cleanup_test_env(&home);
}

#[test]
fn test_persistent_keys() {
    let home = setup_test_env();
    start_daemon(&home);

    // Spawn three agents
    for desc in ["first", "second", "third"] {
        let output = fleet_cmd()
            .args(["new", "--folder", "test", desc])
            .env("HOME", &home)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "spawn '{}' failed: {}",
            desc,
            String::from_utf8_lossy(&output.stderr)
        );
        std::thread::sleep(Duration::from_millis(100));
    }

    // Read state file to verify keys
    let state_path = home.join(".fleet/state.json");
    let state_str = std::fs::read_to_string(&state_path).unwrap();
    let state: serde_json::Value = serde_json::from_str(&state_str).unwrap();

    let agents = state["agents"].as_object().unwrap();
    let keys: Vec<Option<&str>> = agents.values().map(|a| a["key"].as_str()).collect();

    // All agents should have keys assigned
    assert!(
        keys.iter().all(|k| k.is_some()),
        "not all agents have keys: {keys:?}"
    );

    // Keys should be unique
    let key_set: std::collections::HashSet<&str> = keys.iter().filter_map(|k| *k).collect();
    assert_eq!(key_set.len(), 3, "keys are not unique: {keys:?}");

    // Keys should be from the pool
    let pool = ['a', 's', 'd', 'f', 'j', 'k', 'l', 'g', 'h'];
    for key in &key_set {
        assert!(
            pool.contains(&key.chars().next().unwrap()),
            "key '{key}' not in pool"
        );
    }

    cleanup_test_env(&home);
}

#[test]
fn test_color_indices_increment() {
    let home = setup_test_env();
    start_daemon(&home);

    for desc in ["a", "b", "c"] {
        let output = fleet_cmd()
            .args(["new", "--folder", "test", desc])
            .env("HOME", &home)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "spawn '{}' failed: {}",
            desc,
            String::from_utf8_lossy(&output.stderr)
        );
        std::thread::sleep(Duration::from_millis(100));
    }

    let state_str = std::fs::read_to_string(home.join(".fleet/state.json")).unwrap();
    let state: serde_json::Value = serde_json::from_str(&state_str).unwrap();

    let agents = state["agents"].as_object().unwrap();
    let mut colors: Vec<u64> = agents
        .values()
        .map(|a| a["color_index"].as_u64().unwrap())
        .collect();
    colors.sort();

    assert_eq!(colors, vec![0, 1, 2], "colors not sequential: {colors:?}");

    cleanup_test_env(&home);
}

#[test]
fn test_mock_agent_produces_output() {
    let output = Command::new(fleet_bin())
        .args(["mock-agent", "--description", "test", "--duration", "3"])
        .env("FLEET_AGENT_ID", "test123")
        .output()
        .unwrap();

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Mock Agent"), "missing banner: {stdout}");
    assert!(stdout.contains("test123"), "missing agent ID: {stdout}");
    assert!(stdout.contains("tick"), "missing tick output: {stdout}");
    assert!(stdout.contains("done"), "missing completion: {stdout}");
}

#[test]
fn test_clean_removes_done_agents() {
    let home = setup_test_env();
    start_daemon(&home);

    // Spawn an agent
    fleet_cmd()
        .args(["new", "--folder", "test", "will be done"])
        .env("HOME", &home)
        .output()
        .unwrap();

    // Manually mark as done in state file
    let state_path = home.join(".fleet/state.json");
    let state_str = std::fs::read_to_string(&state_path).unwrap();
    let mut state: serde_json::Value = serde_json::from_str(&state_str).unwrap();

    if let Some(agents) = state["agents"].as_object_mut() {
        for (_, agent) in agents.iter_mut() {
            agent["state"] = serde_json::json!("done");
        }
    }
    std::fs::write(
        &state_path,
        serde_json::to_string_pretty(&state).unwrap(),
    )
    .unwrap();

    // Clean
    let output = fleet_cmd()
        .arg("clean")
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("1 done agent(s)"));

    // Verify empty
    let output = fleet_cmd()
        .arg("ls")
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&output.stdout).contains("No agents"));

    cleanup_test_env(&home);
}
