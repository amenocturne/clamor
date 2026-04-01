from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InstallContext:
    target_dir: Path
    project_dir: Path
    repo_root: Path

    # v2: profile × agent sources
    profile_name: str
    profile_dir: Path
    agent_name: str
    agent_dir: Path

    # Merged component lists
    skills: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    common: list[str] = field(default_factory=list)
    system_prompt_local: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    pipelines: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    # Multi-agent state
    all_agents: list[str] = field(default_factory=list)
    project_dirs: dict[str, Path] = field(default_factory=dict)

    # Paths
    install_state_path: Optional[Path] = None
    knowledge_base: Optional[Path] = None
