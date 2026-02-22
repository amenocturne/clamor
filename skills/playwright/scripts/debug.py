# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "click"]
# ///
"""Interactive debugging with visible browser."""

from pathlib import Path

import click
from playwright.sync_api import sync_playwright


@click.command()
@click.argument("url")
@click.option("--pause-on-error", is_flag=True, help="Pause browser on console errors")
@click.option("--record", type=click.Path(path_type=Path), help="Record video to directory")
@click.option("--timeout", type=int, default=0, help="Auto-close after N seconds (0 = manual)")
def main(url: str, pause_on_error: bool, record: Path | None, timeout: int):
    """
    Open URL in visible browser for interactive debugging.

    The browser stays open until you close it manually (or timeout).

    Example:
        debug.py http://localhost:5173 --pause-on-error --record tmp/debug/
    """
    with sync_playwright() as p:
        browser_args = {"headless": False, "slow_mo": 100}

        if record:
            record.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch(**browser_args).new_context(
                record_video_dir=str(record)
            )
            page = context.new_page()
        else:
            browser = p.chromium.launch(**browser_args)
            page = browser.new_page()

        errors = []

        if pause_on_error:

            def handle_console(msg):
                if msg.type == "error":
                    errors.append(msg.text)
                    click.echo(f"Console error: {msg.text}")

            page.on("console", handle_console)

        page.goto(url)
        page.wait_for_load_state("networkidle")

        click.echo(f"Browser open at {url}")
        click.echo("Close browser window or press Ctrl+C to exit.")

        if timeout > 0:
            click.echo(f"Auto-closing in {timeout} seconds...")
            page.wait_for_timeout(timeout * 1000)
        else:
            # Wait indefinitely until browser closes
            try:
                page.wait_for_event("close", timeout=0)
            except KeyboardInterrupt:
                pass

        if record:
            video_path = page.video.path()
            click.echo(f"Video saved to: {video_path}")
            context.close()
        else:
            browser.close()

        if errors:
            click.echo(f"\n{len(errors)} console errors captured")


if __name__ == "__main__":
    main()
