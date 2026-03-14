use mac_notification_sys::*;
use serde::Deserialize;
use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;

const ICNS_BYTES: &[u8] = include_bytes!("../AppIcon.icns");

#[derive(Deserialize, Default)]
struct HookInput {
    #[serde(default)]
    hook_event_name: String,
    #[serde(default)]
    notification_type: String,
}

fn icns_path() -> Option<PathBuf> {
    let home = dirs::home_dir()?;
    let path = home.join(".claude/assets/claude-code.icns");

    if !path.exists() {
        fs::create_dir_all(path.parent()?).ok()?;
        fs::write(&path, ICNS_BYTES).ok()?;
    }

    Some(path)
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;

    let data: HookInput = serde_json::from_str(&input).unwrap_or_default();

    let message = match data.hook_event_name.as_str() {
        "Notification" => match data.notification_type.as_str() {
            "permission_prompt" => "Permission required",
            "idle_prompt" => "Waiting for your input",
            _ => "Claude needs your input",
        },
        "Stop" => "Session complete",
        _ => return Ok(()),
    };

    let icon = icns_path();
    let mut n = Notification::new();
    n.title("Claude Code").message(message).sound("Tink");

    if let Some(ref icon) = icon {
        n.app_icon(icon.to_str().unwrap_or_default());
    }

    n.send()?;
    Ok(())
}

fn main() {
    let _ = run();
}
