import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_mock_yaml = ModuleType("yaml")
_mock_yaml.safe_load = lambda text: json.loads(text) if text else None
_mock_yaml.dump = lambda data, **kwargs: json.dumps(data)
sys.modules.setdefault("yaml", _mock_yaml)

from lib.install_types import InstallContext  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CLAUDE_INSTALLER = load_module(
    "claude_code_installer", REPO_ROOT / "agents" / "claude-code" / "install.py"
)
OPEN_CODE_INSTALLER = load_module(
    "open_code_installer", REPO_ROOT / "agents" / "open-code" / "install.py"
)
PI_INSTALLER = load_module("pi_installer", REPO_ROOT / "agents" / "pi" / "install.py")


@pytest.fixture()
def isolated_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "skills" / "spec").mkdir(parents=True)
    (repo_root / "hooks" / "notification").mkdir(parents=True)
    (repo_root / "pipelines" / "workspace").mkdir(parents=True)
    (repo_root / "common").mkdir(parents=True)
    (repo_root / "agents" / "pi" / "extensions" / "nestor-provider").mkdir(parents=True)

    preset_dir = repo_root / "presets" / "test"
    preset_dir.mkdir(parents=True)
    (preset_dir / "claude.md").write_text("# Rules")
    (preset_dir / "settings.json").write_text(json.dumps({"hooks": {}}))

    target_dir = tmp_path / "project"
    target_dir.mkdir()

    return repo_root, preset_dir, target_dir


def test_claude_installer_extracts_current_layout(isolated_repo):
    repo_root, preset_dir, target_dir = isolated_repo
    ctx = InstallContext(
        target_dir=target_dir,
        project_dir=target_dir / ".claude",
        repo_root=repo_root,
        preset_name="test",
        preset_dir=preset_dir,
        skills=["spec"],
        hooks=["notification"],
        pipelines=["workspace"],
        all_agents=["claude-code", "open-code", "pi"],
        project_dirs={
            "claude-code": target_dir / ".claude",
            "open-code": target_dir / ".opencode",
            "pi": target_dir / ".pi",
        },
        install_state_path=target_dir / ".claude" / "agentic-kit.json",
    )

    CLAUDE_INSTALLER.install(ctx)

    assert (target_dir / ".claude" / "settings.json").exists()
    config = json.loads((target_dir / ".claude" / "agentic-kit.json").read_text())
    assert config["managed"]["agents"] == ["claude-code", "open-code", "pi"]
    assert (target_dir / ".claude" / "CLAUDE.md").read_text() == "# Rules"
    assert (target_dir / ".claude" / "skills" / "spec").is_symlink()
    assert (target_dir / ".claude" / "hooks" / "notification").is_symlink()
    assert (target_dir / "pipelines" / "workspace").is_symlink()


def test_open_code_installer_uses_local_layout(isolated_repo):
    repo_root, preset_dir, target_dir = isolated_repo
    ctx = InstallContext(
        target_dir=target_dir,
        project_dir=target_dir / ".opencode",
        repo_root=repo_root,
        preset_name="test",
        preset_dir=preset_dir,
        skills=["spec"],
        all_agents=["open-code"],
        project_dirs={"open-code": target_dir / ".opencode"},
        install_state_path=target_dir / ".opencode" / "agentic-kit.json",
    )

    OPEN_CODE_INSTALLER.install(ctx)

    assert (target_dir / ".opencode" / "skills" / "spec").is_symlink()
    config = json.loads((target_dir / ".opencode" / "agentic-kit.json").read_text())
    assert config["agentic_kit"] == str(repo_root)
    assert config["managed"]["project_dir"] == str((target_dir / ".opencode").resolve())
    assert not (target_dir / ".opencode" / "settings.json").exists()


def test_pi_installer_writes_defaults_and_extensions(isolated_repo):
    repo_root, preset_dir, target_dir = isolated_repo
    ctx = InstallContext(
        target_dir=target_dir,
        project_dir=target_dir / ".pi",
        repo_root=repo_root,
        preset_name="test",
        preset_dir=preset_dir,
        skills=["spec"],
        all_agents=["pi"],
        project_dirs={"pi": target_dir / ".pi"},
        install_state_path=target_dir / ".pi" / "agentic-kit.json",
    )

    PI_INSTALLER.install(ctx)

    assert (target_dir / ".pi" / "skills" / "spec").is_symlink()
    assert (target_dir / ".pi" / "extensions" / "nestor-provider").is_symlink()
    settings = json.loads((target_dir / ".pi" / "settings.json").read_text())
    assert settings == PI_INSTALLER.DEFAULT_SETTINGS
    config = json.loads((target_dir / ".pi" / "agentic-kit.json").read_text())
    assert config["managed"]["project_dir"] == str((target_dir / ".pi").resolve())


def test_pi_installer_fails_when_required_extension_is_missing(isolated_repo):
    repo_root, preset_dir, target_dir = isolated_repo
    ctx = InstallContext(
        target_dir=target_dir,
        project_dir=target_dir / ".pi",
        repo_root=repo_root,
        preset_name="test",
        preset_dir=preset_dir,
        skills=["spec"],
        all_agents=["pi"],
        project_dirs={"pi": target_dir / ".pi"},
        install_state_path=target_dir / ".pi" / "agentic-kit.json",
    )
    (repo_root / "agents" / "pi" / "extensions" / "nestor-provider").rmdir()

    with pytest.raises(FileNotFoundError, match="nestor-provider"):
        PI_INSTALLER.install(ctx)

    assert not (target_dir / ".pi" / "settings.json").exists()
