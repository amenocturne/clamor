from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InstallContext:
    target_dir: Path
    project_dir: Path
    repo_root: Path
    preset_name: str
    preset_dir: Path
    skills: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    common: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    pipelines: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    all_agents: list[str] = field(default_factory=list)
    project_dirs: dict[str, Path] = field(default_factory=dict)
    install_state_path: Optional[Path] = None
    knowledge_base: Optional[Path] = None
