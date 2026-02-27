# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "httpx"]
# ///
"""Server lifecycle management for tests."""

import subprocess
import sys
import time
from typing import NoReturn

import click
import httpx


def wait_for_server(url: str, timeout: int) -> bool:
    """Wait for server to respond."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code < 500:
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    return False


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.option("--server", "-s", required=True, help="Command to start server")
@click.option("--port", "-p", type=int, required=True, help="Port to wait for")
@click.option(
    "--timeout", "-t", type=int, default=30, help="Startup timeout in seconds"
)
@click.option(
    "--health", "-h", help="Health check URL (default: http://localhost:PORT)"
)
@click.pass_context
def main(
    ctx: click.Context, server: str, port: int, timeout: int, health: str | None
) -> NoReturn:
    """
    Start a server, run a command, then stop the server.

    Example:
        with_server.py --server "just run" --port 5173 -- pytest tests/e2e/
    """
    health_url = health or f"http://localhost:{port}"
    test_command = ctx.args

    if not test_command:
        click.echo("Error: No test command provided after --", err=True)
        sys.exit(1)

    # Start server
    click.echo(f"Starting server: {server}")
    server_process = subprocess.Popen(
        server,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        # Wait for server
        click.echo(f"Waiting for server at {health_url}...")
        if not wait_for_server(health_url, timeout):
            click.echo(f"Server failed to start within {timeout}s", err=True)
            server_process.terminate()
            sys.exit(1)

        click.echo("Server ready. Running tests...")

        # Run test command
        result = subprocess.run(test_command)

        sys.exit(result.returncode)

    finally:
        # Cleanup
        click.echo("Stopping server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()


if __name__ == "__main__":
    main()
