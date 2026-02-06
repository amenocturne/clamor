"""Tests for notification hook."""

import json
import runpy
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Import hook module by manipulating sys.path
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTIFICATION_DIR = REPO_ROOT / "hooks" / "notification"
HOOK_FILE = str(NOTIFICATION_DIR / "hook.py")

sys.path.insert(0, str(NOTIFICATION_DIR))

import hook as notification  # noqa: E402


# ===================================================================
# notify() function tests
# ===================================================================


class TestNotify:
    """Test the notify() helper function."""

    @patch("hook.subprocess.run")
    def test_notify_on_darwin(self, mock_run):
        with patch("hook.sys.platform", "darwin"):
            notification.notify("hello world")
        mock_run.assert_called_once_with([
            "osascript", "-e",
            'display notification "hello world" with title "Claude Code"',
        ])

    @patch("hook.subprocess.run")
    def test_notify_on_darwin_custom_title(self, mock_run):
        with patch("hook.sys.platform", "darwin"):
            notification.notify("msg", title="Custom")
        mock_run.assert_called_once_with([
            "osascript", "-e",
            'display notification "msg" with title "Custom"',
        ])

    @patch("hook.subprocess.run")
    def test_notify_on_linux(self, mock_run):
        with patch("hook.sys.platform", "linux"):
            notification.notify("hello world")
        mock_run.assert_called_once_with(["notify-send", "Claude Code", "hello world"])

    @patch("hook.subprocess.run")
    def test_notify_on_linux_custom_title(self, mock_run):
        with patch("hook.sys.platform", "linux"):
            notification.notify("msg", title="Custom")
        mock_run.assert_called_once_with(["notify-send", "Custom", "msg"])

    @patch("hook.subprocess.run")
    def test_notify_on_unsupported_platform(self, mock_run):
        with patch("hook.sys.platform", "win32"):
            notification.notify("hello")
        mock_run.assert_not_called()


# ===================================================================
# Helper to run the hook script as __main__
# ===================================================================


def _run_hook(stdin_text: str) -> list:
    """Run hook.py as __main__ with given stdin, return subprocess.run calls."""
    with (
        patch("sys.stdin", StringIO(stdin_text)),
        patch("subprocess.run") as mock_run,
    ):
        runpy.run_path(HOOK_FILE, run_name="__main__")
        return mock_run.call_args_list


# ===================================================================
# __main__ block tests (event dispatch)
# ===================================================================


class TestMainNotificationEvent:
    """Test that Notification events send the 'needs input' message."""

    def test_notification_event(self):
        stdin_data = json.dumps({"hook_event_name": "Notification"})
        calls = _run_hook(stdin_data)
        assert len(calls) == 1
        args = calls[0][0][0]  # positional arg 0 of first call
        # On darwin: osascript call with "Claude needs your input"
        # On linux: notify-send call
        assert "Claude needs your input" in " ".join(args)


class TestMainStopEvent:
    """Test that Stop (or unknown) events send 'Session complete'."""

    def test_stop_event(self):
        stdin_data = json.dumps({"hook_event_name": "Stop"})
        calls = _run_hook(stdin_data)
        assert len(calls) == 1
        args = calls[0][0][0]
        assert "Session complete" in " ".join(args)

    def test_unknown_event(self):
        stdin_data = json.dumps({"hook_event_name": "SomethingElse"})
        calls = _run_hook(stdin_data)
        assert len(calls) == 1
        args = calls[0][0][0]
        assert "Session complete" in " ".join(args)

    def test_missing_event_key(self):
        stdin_data = json.dumps({"other_key": "value"})
        calls = _run_hook(stdin_data)
        assert len(calls) == 1
        args = calls[0][0][0]
        assert "Session complete" in " ".join(args)


class TestMainInvalidInput:
    """Test invalid/empty JSON input handling."""

    def test_invalid_json(self):
        calls = _run_hook("not valid json!!!")
        assert len(calls) == 1
        args = calls[0][0][0]
        assert "Session complete" in " ".join(args)

    def test_empty_input(self):
        calls = _run_hook("")
        assert len(calls) == 1
        args = calls[0][0][0]
        assert "Session complete" in " ".join(args)
