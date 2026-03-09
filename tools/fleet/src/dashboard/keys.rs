use crate::agent::{Agent, AgentState};

/// Jump key pool in priority order: a, s, d, f, j, k, l, g, h
const KEY_POOL: &[char] = &['a', 's', 'd', 'f', 'j', 'k', 'l', 'g', 'h'];

/// Reserved keys that cannot be assigned to agents
const _RESERVED: &[char] = &['n', 'e', 'K', 'q'];

/// Assign jump keys to agents based on priority:
/// 1. Input agents get the best (earliest) keys
/// 2. Working agents next
/// 3. Done agents get remaining keys
///
/// Display order is STABLE (by folder, then start time).
/// Only the key assignments shift based on priority.
///
/// Returns: Vec<(agent_id, jump_key)>
pub fn assign_keys(agents: &[(String, &Agent)]) -> Vec<(String, char)> {
    // Sort by priority: input > working > done, then by start time within same priority
    let mut priority_sorted: Vec<&(String, &Agent)> = agents.iter().collect();
    priority_sorted.sort_by(|a, b| {
        let pri_a = state_priority(&a.1.state);
        let pri_b = state_priority(&b.1.state);
        pri_a.cmp(&pri_b).then_with(|| a.1.started_at.cmp(&b.1.started_at))
    });

    // Assign keys from pool in priority order
    priority_sorted
        .iter()
        .zip(KEY_POOL.iter())
        .map(|(entry, &key)| (entry.0.clone(), key))
        .collect()
}

/// Lower number = higher priority for key assignment.
fn state_priority(state: &AgentState) -> u8 {
    match state {
        AgentState::Input => 0,
        AgentState::Working => 1,
        AgentState::Done => 2,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    fn make_agent(state: AgentState, minutes_ago: i64) -> Agent {
        let now = Utc::now();
        Agent {
            id: String::new(),
            description: String::new(),
            folder: String::new(),
            cwd: String::new(),
            tmux_session: String::new(),
            initial_prompt: String::new(),
            state,
            started_at: now - chrono::Duration::minutes(minutes_ago),
            last_activity_at: now,
            last_tool: None,
        }
    }

    #[test]
    fn input_agents_get_best_keys() {
        let working = make_agent(AgentState::Working, 10);
        let input = make_agent(AgentState::Input, 5);
        let done = make_agent(AgentState::Done, 20);

        let agents: Vec<(String, &Agent)> = vec![
            ("w1".into(), &working),
            ("i1".into(), &input),
            ("d1".into(), &done),
        ];

        let keys = assign_keys(&agents);
        let input_key = keys.iter().find(|(id, _)| id == "i1").unwrap().1;
        let working_key = keys.iter().find(|(id, _)| id == "w1").unwrap().1;
        let done_key = keys.iter().find(|(id, _)| id == "d1").unwrap().1;

        assert_eq!(input_key, 'a');
        assert_eq!(working_key, 's');
        assert_eq!(done_key, 'd');
    }
}
