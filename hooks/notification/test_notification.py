"""Tests for notification hook."""

import importlib.util
import json
import runpy
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Import hook module using importlib to avoid sys.modules collisions with
# other hook.py files (e.g. save-conversation/hook.py).
# ---------------------------------------------------------------------------

HOOK_DIR = Path(__file__).resolve().parent
HOOK_FILE = str(HOOK_DIR / "hook.py")

_spec = importlib.util.spec_from_file_location("notification_hook", HOOK_FILE)
notification = importlib.util.module_from_spec(_spec)
sys.modules["notification_hook"] = notification
_spec.loader.exec_module(notification)


# ===================================================================
# notify() function tests
# ===================================================================


class TestNotify:
    """Test the notify() helper function."""

    @patch("notification_hook.subprocess.run")
    def test_notify_on_darwin(self, mock_run):
        with patch("notification_hook.sys.platform", "darwin"):
            notification.notify("hello world")
        mock_run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'display notification "hello world" with title "Claude Code" sound name "Tink"',
            ]
        )

    @patch("notification_hook.subprocess.run")
    def test_notify_on_darwin_custom_title(self, mock_run):
        with patch("notification_hook.sys.platform", "darwin"):
            notification.notify("msg", title="Custom")
        mock_run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'display notification "msg" with title "Custom" sound name "Tink"',
            ]
        )

    @patch("notification_hook.subprocess.run")
    def test_notify_on_darwin_custom_sound(self, mock_run):
        with patch("notification_hook.sys.platform", "darwin"):
            notification.notify("msg", sound="Glass")
        mock_run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'display notification "msg" with title "Claude Code" sound name "Glass"',
            ]
        )

    @patch("notification_hook.subprocess.run")
    def test_notify_on_linux(self, mock_run):
        with patch("notification_hook.sys.platform", "linux"):
            notification.notify("hello world")
        mock_run.assert_called_once_with(["notify-send", "Claude Code", "hello world"])

    @patch("notification_hook.subprocess.run")
    def test_notify_on_linux_custom_title(self, mock_run):
        with patch("notification_hook.sys.platform", "linux"):
            notification.notify("msg", title="Custom")
        mock_run.assert_called_once_with(["notify-send", "Custom", "msg"])

    @patch("notification_hook.subprocess.run")
    def test_notify_on_unsupported_platform(self, mock_run):
        with patch("notification_hook.sys.platform", "win32"):
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
