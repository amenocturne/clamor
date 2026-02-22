# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "psutil"]
# ///
"""Detect running dev servers."""

import json

import click
import psutil

COMMON_DEV_PORTS = [3000, 3001, 4000, 5000, 5173, 5174, 8000, 8080, 8888]

DEV_SERVER_PATTERNS = [
    "vite",
    "next",
    "webpack",
    "node",
    "python",
    "uvicorn",
    "flask",
    "django",
    "bun",
    "deno",
]


def get_process_name(conn) -> str | None:
    """Get process name for a connection."""
    try:
        proc = psutil.Process(conn.pid)
        cmdline = " ".join(proc.cmdline()).lower()

        for pattern in DEV_SERVER_PATTERNS:
            if pattern in cmdline:
                return pattern

        return proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


@click.command()
@click.option("--ports", "-p", default=None, help="Comma-separated ports or range (e.g., 3000-3010)")
@click.option("--json-output/--text", default=True, help="Output format")
def main(ports: str | None, json_output: bool):
    """Detect running dev servers on common ports."""
    if ports:
        if "-" in ports:
            start, end = map(int, ports.split("-"))
            check_ports = list(range(start, end + 1))
        else:
            check_ports = [int(p.strip()) for p in ports.split(",")]
    else:
        check_ports = COMMON_DEV_PORTS

    servers = []

    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "LISTEN" and conn.laddr.port in check_ports:
            process_name = get_process_name(conn)
            if process_name:
                servers.append({
                    "port": conn.laddr.port,
                    "process": process_name,
                    "pid": conn.pid,
                    "address": conn.laddr.ip,
                })

    # Dedupe by port
    seen_ports = set()
    unique_servers = []
    for s in servers:
        if s["port"] not in seen_ports:
            seen_ports.add(s["port"])
            unique_servers.append(s)

    if json_output:
        click.echo(json.dumps(unique_servers, indent=2))
    else:
        if unique_servers:
            click.echo("Running dev servers:")
            for s in unique_servers:
                click.echo(f"  {s['process']:12} → localhost:{s['port']}")
        else:
            click.echo("No dev servers detected on common ports")


if __name__ == "__main__":
    main()
