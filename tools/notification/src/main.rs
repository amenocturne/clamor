use notify_rust::Notification;
use serde::Deserialize;
use std::io::{self, Read};

#[derive(Deserialize, Default)]
struct HookInput {
    #[serde(default)]
    hook_event_name: String,
    #[serde(default)]
    notification_type: String,
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

    Notification::new()
        .summary("Claude Code")
        .body(message)
        .sound_name("Tink")
        .show()?;

    Ok(())
}

fn main() {
    let _ = run();
}
