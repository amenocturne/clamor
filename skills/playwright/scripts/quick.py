# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright", "click"]
# ///
"""Quick ad-hoc browser automation tasks."""

import json
import sys
from pathlib import Path

import click
from playwright.sync_api import sync_playwright

VIEWPORTS = {
    "mobile": {"width": 375, "height": 667},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1440, "height": 900},
}


@click.group()
def cli():
    """Quick browser automation tasks."""
    pass


@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="tmp/screenshot.png", help="Output path")
@click.option("--wait", default="networkidle", help="Wait strategy: load, domcontentloaded, networkidle")
@click.option("--selector", "-s", help="Wait for and screenshot specific element")
@click.option("--delay", type=int, default=0, help="Additional delay in ms after wait")
@click.option("--headless/--headed", default=True, help="Run headless or visible")
def screenshot(url: str, output: str, wait: str, selector: str | None, delay: int, headless: bool):
    """Take a screenshot of a page."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state(wait)

        if delay > 0:
            page.wait_for_timeout(delay)

        if selector:
            element = page.locator(selector)
            element.screenshot(path=str(output_path))
        else:
            page.screenshot(path=str(output_path), full_page=True)

        browser.close()

    click.echo(f"Screenshot saved to {output_path}")


@cli.command()
@click.argument("url")
@click.option("--selector", "-s", required=True, help="Selector to check")
@click.option("--timeout", type=int, default=5000, help="Timeout in ms")
@click.option("--headless/--headed", default=True)
def check(url: str, selector: str, timeout: int, headless: bool):
    """Check if an element exists on the page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")

        try:
            page.locator(selector).wait_for(timeout=timeout)
            click.echo(f"[ok] Element found: {selector}")
            browser.close()
            sys.exit(0)
        except Exception:
            click.echo(f"[err] Element not found: {selector}", err=True)
            browser.close()
            sys.exit(1)


@cli.command()
@click.argument("url")
@click.option("--data", "-d", required=True, help="JSON data for form fields")
@click.option("--submit-selector", default="button[type=submit]", help="Submit button selector")
@click.option("--headless/--headed", default=False, help="Run headless or visible")
def form(url: str, data: str, submit_selector: str, headless: bool):
    """Fill a form and submit it."""
    form_data = json.loads(data)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")

        for field, value in form_data.items():
            page.fill(f"[name={field}]", value)

        page.click(submit_selector)
        page.wait_for_load_state("networkidle")

        click.echo(f"Form submitted. Current URL: {page.url}")
        browser.close()


@cli.command()
@click.argument("url")
@click.option("--viewports", "-v", default="desktop,tablet,mobile", help="Comma-separated viewport names")
@click.option("--output", "-o", default="tmp/responsive", help="Output directory")
@click.option("--wait", default="networkidle")
@click.option("--delay", type=int, default=0, help="Additional delay in ms")
def responsive(url: str, viewports: str, output: str, wait: str, delay: int):
    """Take screenshots at multiple viewports."""
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    viewport_names = [v.strip() for v in viewports.split(",")]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for name in viewport_names:
            if name not in VIEWPORTS:
                click.echo(f"Unknown viewport: {name}", err=True)
                continue

            page = browser.new_page(viewport=VIEWPORTS[name])
            page.goto(url)
            page.wait_for_load_state(wait)

            if delay > 0:
                page.wait_for_timeout(delay)

            screenshot_path = output_dir / f"{name}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            click.echo(f"Saved {screenshot_path}")
            page.close()

        browser.close()


@cli.command()
@click.argument("url")
@click.option("--follow/--no-follow", default=False, help="Follow links and check recursively")
@click.option("--output", "-o", help="Output JSON file for results")
@click.option("--headless/--headed", default=True)
def links(url: str, follow: bool, output: str | None, headless: bool):
    """Find broken links on a page."""
    from urllib.parse import urljoin, urlparse

    broken = []
    checked = set()
    base_domain = urlparse(url).netloc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        def check_page(page_url: str):
            if page_url in checked:
                return
            checked.add(page_url)

            try:
                response = page.goto(page_url)
                if response and response.status >= 400:
                    broken.append({"url": page_url, "status": response.status})
                    return

                page.wait_for_load_state("networkidle")

                if follow and urlparse(page_url).netloc == base_domain:
                    hrefs = page.locator("a[href]").all()
                    for a in hrefs:
                        href = a.get_attribute("href")
                        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                            full_url = urljoin(page_url, href)
                            if urlparse(full_url).netloc == base_domain:
                                check_page(full_url)

            except Exception as e:
                broken.append({"url": page_url, "error": str(e)})

        check_page(url)
        browser.close()

    if broken:
        click.echo(f"Found {len(broken)} broken links:")
        for b in broken:
            click.echo(f"  [err] {b['url']} - {b.get('status', b.get('error'))}")
    else:
        click.echo("[ok] No broken links found")

    if output:
        Path(output).write_text(json.dumps(broken, indent=2))


if __name__ == "__main__":
    cli()
