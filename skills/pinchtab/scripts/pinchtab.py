# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "httpx"]
# ///
"""CLI wrapper for pinchtab browser control."""

import os
import subprocess
import sys
import time
from pathlib import Path

import click
import httpx

DEFAULT_PORT = 9867
BASE_URL = f"http://localhost:{DEFAULT_PORT}"

SEARCH_ENGINES = {
    "kagi": "https://kagi.com/search?q=",
    "google": "https://www.google.com/search?q=",
    "ddg": "https://duckduckgo.com/?q=",
}


def get_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def check_server() -> bool:
    """Check if pinchtab server is running AND browser is connected."""
    try:
        with get_client() as client:
            r = client.get("/health")
            if r.status_code != 200:
                return False
            data = r.json()
            return data.get("status") == "ok"
    except (httpx.ConnectError, httpx.ReadError):
        return False


def server_is_listening() -> bool:
    """Check if something is listening on the pinchtab port (even if disconnected)."""
    try:
        with get_client() as client:
            r = client.get("/health")
            return r.status_code == 200
    except (httpx.ConnectError, httpx.ReadError):
        return False


def kill_server() -> None:
    """Kill any pinchtab process holding the port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{DEFAULT_PORT}"],
            capture_output=True,
            text=True,
        )
        for pid in result.stdout.strip().split("\n"):
            if pid:
                subprocess.run(["kill", pid], capture_output=True)
        time.sleep(1)
    except Exception:
        pass


def check_installed() -> bool:
    """Check if pinchtab binary is available."""
    import shutil

    return shutil.which("pinchtab") is not None


def ensure_server() -> None:
    """Start pinchtab server if not running, restart if browser disconnected."""
    if check_server():
        return

    if not check_installed():
        click.echo(
            "Pinchtab not installed. Install with: curl -fsSL https://pinchtab.com/install.sh | bash",
            err=True,
        )
        sys.exit(1)

    # Kill zombie server that's listening but has a dead browser
    if server_is_listening():
        click.echo("Pinchtab server has disconnected browser, restarting...", err=True)
        kill_server()

    click.echo("Starting pinchtab server...", err=True)
    subprocess.Popen(
        ["pinchtab"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(15):
        time.sleep(0.5)
        if check_server():
            return

    click.echo("Failed to start pinchtab server", err=True)
    sys.exit(1)


@click.group()
def cli():
    """Pinchtab browser control CLI."""
    pass


@cli.command()
@click.option("--headed", is_flag=True, help="Run with visible browser")
@click.option("--port", default=DEFAULT_PORT, help="Port to run on")
def start(headed: bool, port: int):
    """Start pinchtab server."""
    if check_server():
        click.echo("Pinchtab server already running")
        return

    env = dict(os.environ)
    if headed:
        env["BRIDGE_HEADLESS"] = "false"
    if port != DEFAULT_PORT:
        env["BRIDGE_PORT"] = str(port)

    if server_is_listening():
        click.echo("Killing disconnected pinchtab server...", err=True)
        kill_server()

    click.echo(
        f"Starting pinchtab server on port {port}{'(headed)' if headed else ''}..."
    )
    subprocess.Popen(
        ["pinchtab"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )

    for _ in range(15):
        time.sleep(0.5)
        if check_server():
            click.echo("Server started successfully")
            return

    click.echo("Failed to start server", err=True)
    sys.exit(1)


@cli.command()
def health():
    """Check if pinchtab server is running."""
    if check_server():
        click.echo("Pinchtab server is running")
    else:
        click.echo("Pinchtab server is not running", err=True)
        sys.exit(1)


@cli.command()
@click.argument("url")
def navigate(url: str):
    """Navigate to a URL."""
    ensure_server()
    with get_client() as client:
        r = client.post("/navigate", json={"url": url})
        if r.status_code == 200:
            click.echo(f"Navigated to {url}")
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
def text():
    """Get page text content."""
    ensure_server()
    with get_client() as client:
        r = client.get("/text")
        if r.status_code == 200:
            click.echo(r.text)
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
@click.option("--output", "-o", default="screenshot.jpg", help="Output file path")
def screenshot(output: str):
    """Take a screenshot."""
    import base64

    ensure_server()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_client() as client:
        r = client.get("/screenshot")
        if r.status_code != 200:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)

        data = r.json()
        image_bytes = base64.b64decode(data["base64"])
        output_path.write_bytes(image_bytes)
        click.echo(f"Screenshot saved to {output}")


@cli.command()
@click.option("--output", "-o", help="Output file path (optional)")
def snapshot(output: str | None):
    """Get accessibility tree with element references."""
    ensure_server()
    with get_client() as client:
        r = client.get("/snapshot")
        if r.status_code == 200:
            if output:
                Path(output).write_text(r.text)
                click.echo(f"Snapshot saved to {output}")
            else:
                click.echo(r.text)
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command("click")
@click.argument("ref")
def click_element(ref: str):
    """Click an element by reference (e0, e1, ...)."""
    ensure_server()
    with get_client() as client:
        r = client.post("/action", json={"kind": "click", "ref": ref})
        if r.status_code == 200:
            click.echo(f"Clicked {ref}")
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command("type")
@click.option("--ref", "-r", required=True, help="Element reference")
@click.option("--text", "-t", required=True, help="Text to type")
def type_text(ref: str, text: str):
    """Type text into an element."""
    ensure_server()
    with get_client() as client:
        r = client.post("/action", json={"kind": "fill", "ref": ref, "value": text})
        if r.status_code == 200:
            click.echo(f"Typed into {ref}")
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
@click.argument("expression")
def evaluate(expression: str):
    """Run JavaScript in the browser."""
    ensure_server()
    with get_client() as client:
        r = client.post("/evaluate", json={"expression": expression})
        if r.status_code == 200:
            click.echo(r.text)
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
@click.argument("query")
@click.option(
    "--engine",
    "-e",
    default="kagi",
    type=click.Choice(list(SEARCH_ENGINES.keys())),
    help="Search engine",
)
def search(query: str, engine: str):
    """Search using a search engine."""
    ensure_server()
    import urllib.parse

    url = SEARCH_ENGINES[engine] + urllib.parse.quote(query)

    with get_client() as client:
        r = client.post("/navigate", json={"url": url})
        if r.status_code == 200:
            click.echo(f"Searching '{query}' on {engine}")
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
def tabs():
    """List open tabs."""
    ensure_server()
    with get_client() as client:
        r = client.get("/tabs")
        if r.status_code == 200:
            click.echo(r.text)
        else:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)


@cli.command()
@click.option("--output", "-o", default="page.pdf", help="Output file path")
def pdf(output: str):
    """Export page as PDF."""
    import base64

    ensure_server()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_client() as client:
        r = client.get("/pdf")
        if r.status_code != 200:
            click.echo(f"Failed: {r.text}", err=True)
            sys.exit(1)

        data = r.json()
        pdf_bytes = base64.b64decode(data["base64"])
        output_path.write_bytes(pdf_bytes)
        click.echo(f"PDF saved to {output}")


if __name__ == "__main__":
    cli()
