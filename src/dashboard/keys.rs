use crate::agent::Agent;

const KEY_POOL: &[char] = &['a', 's', 'd', 'f', 'j', 'k', 'l', 'g', 'h'];

/// Find the next available key from the pool that isn't already assigned.
pub fn next_available_key(agents: &[&Agent]) -> Option<char> {
    let used: std::collections::HashSet<char> = agents
        .iter()
        .filter_map(|a| a.key)
        .collect();
    KEY_POOL.iter().copied().find(|k| !used.contains(k))
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use crate::agent::AgentState;

    fn make_agent(key: Option<char>) -> Agent {
        let now = Utc::now();
        Agent {
            id: String::new(),
            description: String::new(),
            folder: String::new(),
            cwd: String::new(),
            initial_prompt: String::new(),
            state: AgentState::Working,
            started_at: now,
            last_activity_at: now,
            last_tool: None,
            key,
            color_index: 0,
        }
    }

    #[test]
    fn first_key_is_a() {
        let agents: Vec<&Agent> = vec![];
        assert_eq!(next_available_key(&agents), Some('a'));
    }

    #[test]
    fn skips_used_keys() {
        let a1 = make_agent(Some('a'));
        let a2 = make_agent(Some('s'));
        let agents: Vec<&Agent> = vec![&a1, &a2];
        assert_eq!(next_available_key(&agents), Some('d'));
    }

    #[test]
    fn returns_none_when_pool_exhausted() {
        let all_agents: Vec<Agent> = KEY_POOL.iter().map(|&k| make_agent(Some(k))).collect();
        let refs: Vec<&Agent> = all_agents.iter().collect();
        assert_eq!(next_available_key(&refs), None);
    }
}
