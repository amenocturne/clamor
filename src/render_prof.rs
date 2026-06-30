use std::time::{Duration, Instant};

pub const RENDER_PROF_ENV: &str = "CLAMOR_RENDER_PROF";

#[derive(Clone, Copy)]
pub enum Stage {
    Parse = 0,
    Render = 1,
    Frame = 2,
}

const STAGE_NAMES: [&str; 3] = ["parse", "render", "frame"];
const STAGE_COUNT: usize = 3;

pub struct RenderProfiler {
    window_start: Instant,
    stages: [StageStats; STAGE_COUNT],
}

struct StageStats {
    count: u32,
    total: Duration,
    max: Duration,
}

impl StageStats {
    fn new() -> Self {
        Self {
            count: 0,
            total: Duration::ZERO,
            max: Duration::ZERO,
        }
    }

    fn record(&mut self, d: Duration) {
        self.count += 1;
        self.total += d;
        if d > self.max {
            self.max = d;
        }
    }

    fn reset(&mut self) {
        *self = Self::new();
    }
}

impl RenderProfiler {
    /// Returns `Some` if `CLAMOR_RENDER_PROF` is set to a truthy value.
    pub fn from_env() -> Option<Self> {
        let val = std::env::var(RENDER_PROF_ENV).ok()?;
        if val.is_empty() || val == "0" {
            return None;
        }
        Some(Self {
            window_start: Instant::now(),
            stages: std::array::from_fn(|_| StageStats::new()),
        })
    }

    /// Record a duration for the given pipeline stage.
    pub fn record(&mut self, stage: Stage, duration: Duration) {
        self.stages[stage as usize].record(duration);
    }

    /// If the 1-second window has elapsed, log stats to stderr and reset.
    pub fn maybe_flush(&mut self) {
        if self.window_start.elapsed() < Duration::from_secs(1) {
            return;
        }

        let mut parts = Vec::new();
        for (i, name) in STAGE_NAMES.iter().enumerate() {
            let s = &self.stages[i];
            if s.count > 0 {
                let avg_ms = s.total.as_secs_f64() * 1000.0 / f64::from(s.count);
                let max_ms = s.max.as_secs_f64() * 1000.0;
                parts.push(format!(
                    "{name}: n={} avg={avg_ms:.2}ms max={max_ms:.2}ms",
                    s.count,
                ));
            }
        }

        if !parts.is_empty() {
            eprintln!("[render-prof] {}", parts.join(" | "));
        }

        self.window_start = Instant::now();
        for s in &mut self.stages {
            s.reset();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn from_env_returns_none_when_unset() {
        // CLAMOR_RENDER_PROF is not set in test environment
        std::env::remove_var(RENDER_PROF_ENV);
        assert!(RenderProfiler::from_env().is_none());
    }

    #[test]
    fn from_env_returns_none_for_zero() {
        std::env::set_var(RENDER_PROF_ENV, "0");
        assert!(RenderProfiler::from_env().is_none());
        std::env::remove_var(RENDER_PROF_ENV);
    }

    #[test]
    fn from_env_returns_none_for_empty() {
        std::env::set_var(RENDER_PROF_ENV, "");
        assert!(RenderProfiler::from_env().is_none());
        std::env::remove_var(RENDER_PROF_ENV);
    }

    #[test]
    fn from_env_returns_some_for_truthy() {
        std::env::set_var(RENDER_PROF_ENV, "1");
        assert!(RenderProfiler::from_env().is_some());
        std::env::remove_var(RENDER_PROF_ENV);
    }

    #[test]
    fn record_accumulates_stats() {
        std::env::set_var(RENDER_PROF_ENV, "1");
        let mut prof = RenderProfiler::from_env().unwrap();
        std::env::remove_var(RENDER_PROF_ENV);

        prof.record(Stage::Parse, Duration::from_micros(100));
        prof.record(Stage::Parse, Duration::from_micros(300));
        prof.record(Stage::Render, Duration::from_micros(500));

        let parse = &prof.stages[Stage::Parse as usize];
        assert_eq!(parse.count, 2);
        assert_eq!(parse.total, Duration::from_micros(400));
        assert_eq!(parse.max, Duration::from_micros(300));

        let render = &prof.stages[Stage::Render as usize];
        assert_eq!(render.count, 1);
        assert_eq!(render.total, Duration::from_micros(500));

        let frame = &prof.stages[Stage::Frame as usize];
        assert_eq!(frame.count, 0);
    }

    #[test]
    fn maybe_flush_resets_after_window() {
        std::env::set_var(RENDER_PROF_ENV, "1");
        let mut prof = RenderProfiler::from_env().unwrap();
        std::env::remove_var(RENDER_PROF_ENV);

        prof.record(Stage::Parse, Duration::from_micros(100));

        // Force window to have elapsed by backdating window_start
        prof.window_start = Instant::now() - Duration::from_secs(2);
        prof.maybe_flush();

        assert_eq!(prof.stages[Stage::Parse as usize].count, 0);
    }

    #[test]
    fn maybe_flush_does_not_reset_within_window() {
        std::env::set_var(RENDER_PROF_ENV, "1");
        let mut prof = RenderProfiler::from_env().unwrap();
        std::env::remove_var(RENDER_PROF_ENV);

        prof.record(Stage::Parse, Duration::from_micros(100));
        prof.maybe_flush();

        assert_eq!(prof.stages[Stage::Parse as usize].count, 1);
    }
}
