---
name: playwright
description: E2E testing and visual regression. Use for structured test suites, CI pipelines, visual diff testing, and complex multi-step test scenarios. Triggers on "playwright", "e2e test", "visual regression", "test suite", "CI test".
author: amenocturne
---

# Playwright Testing

E2E testing framework for web applications. Use for structured test suites, CI integration, and visual regression testing.

## Modes

### Ad-hoc Mode
Quick checks, debugging, screenshots. Visible browser, minimal setup.

```bash
# Quick screenshot
uv run scripts/quick.py screenshot http://localhost:5173 --output tmp/screen.png

# Check if element exists
uv run scripts/quick.py check http://localhost:5173 --selector "button.submit"

# Fill form and submit
uv run scripts/quick.py form http://localhost:5173 --data '{"email": "test@example.com"}'
```

### Suite Mode
Organized tests, CI-ready, server lifecycle management.

```bash
# Run all tests
just test:e2e

# Run with server management
uv run scripts/with_server.py --server "just run" --port 5173 -- pytest tests/e2e/
```

## Quick Start

### 1. Detect Running Servers

Before testing, check what's already running:

```bash
uv run scripts/detect_servers.py
# Returns: [{"port": 5173, "process": "vite"}, ...]
```

### 2. Ad-hoc Testing

For quick checks, use visible browser:

```bash
# Screenshot with auto-wait
uv run scripts/quick.py screenshot http://localhost:5173 \
    --wait networkidle \
    --output tmp/homepage.png

# Multiple viewports
uv run scripts/quick.py responsive http://localhost:5173 \
    --viewports desktop,tablet,mobile \
    --output tmp/responsive/
```

### 3. Interactive Debugging

When something's wrong, use headed mode to watch:

```bash
uv run scripts/debug.py http://localhost:5173 \
    --pause-on-error \
    --record tmp/debug-recording/
```

## Scripts

> All paths relative to this skill folder.

### quick.py
Ad-hoc automation tasks.

```
quick.py <command> <url> [options]

Commands:
  screenshot    Take screenshot (--output, --wait, --selector)
  check         Verify element exists (--selector, --timeout)
  form          Fill and submit form (--data JSON, --submit-selector)
  responsive    Screenshots at multiple viewports (--viewports, --output)
  links         Find broken links (--follow, --output)
```

### with_server.py
Server lifecycle management for tests.

```
with_server.py --server CMD --port PORT -- <test_command>

Options:
  --server      Command to start server (e.g., "just run")
  --port        Port to wait for
  --timeout     Server startup timeout (default: 30s)
  --health      Health check URL (default: http://localhost:PORT)
```

### detect_servers.py
Find running dev servers.

```
detect_servers.py [--ports RANGE]

Returns JSON array of detected servers with port and process info.
```

### visual_diff.py
Visual regression testing for canvas/WebGL.

```
visual_diff.py <baseline> <current> [--threshold PERCENT] [--output PATH]

Compares screenshots pixel-by-pixel. Returns exit code 1 if difference
exceeds threshold. Generates diff image highlighting changes.
```

## Testing PixiJS / Canvas

Standard DOM selectors don't work for canvas content. Use visual regression:

### Capture Baseline

```bash
# Capture known-good state
uv run scripts/quick.py screenshot http://localhost:5173/game \
    --wait networkidle \
    --delay 1000 \  # Wait for animations
    --output tests/baselines/game-idle.png
```

### Compare Against Baseline

```bash
# After changes, compare
uv run scripts/quick.py screenshot http://localhost:5173/game \
    --output tmp/game-current.png

uv run scripts/visual_diff.py \
    tests/baselines/game-idle.png \
    tmp/game-current.png \
    --threshold 1 \  # Allow 1% pixel difference
    --output tmp/game-diff.png
```

### In Test Suite

```python
def test_game_renders_correctly():
    page.goto("/game")
    page.wait_for_load_state("networkidle")
    time.sleep(1)  # Wait for PixiJS animations

    screenshot = page.screenshot()
    assert visual_diff(screenshot, "baselines/game-idle.png", threshold=1)
```

## Testing Snabbdom/Elm Architecture

Predictable state makes testing easier:

### Test State Transitions

```python
def test_counter_increment():
    page.goto("/")

    # Initial state
    assert page.locator("[data-count]").text_content() == "0"

    # Trigger Msg
    page.click("button.increment")

    # Verify state update
    assert page.locator("[data-count]").text_content() == "1"
```

### Expose State for Testing

In dev mode, expose model for direct inspection:

```typescript
// In your app initialization (dev only)
if (import.meta.env.DEV) {
    (window as any).__APP_STATE__ = () => currentModel;
}
```

```python
def test_state_directly():
    page.goto("/")
    page.click("button.add-item")

    state = page.evaluate("window.__APP_STATE__()")
    assert len(state["items"]) == 1
```

## Best Practices

### Always Wait Properly

```python
# Bad: race condition
page.goto("/")
page.click("button")

# Good: wait for network
page.goto("/")
page.wait_for_load_state("networkidle")
page.click("button")
```

### Use Stable Selectors

Priority order:
1. `data-testid="submit-btn"` — explicit test hooks
2. `role=button[name="Submit"]` — accessibility roles
3. `text=Submit` — visible text
4. `.submit-button` — CSS classes (less stable)

### Handle Animations

```python
# For canvas/animations, add delay after networkidle
page.wait_for_load_state("networkidle")
page.wait_for_timeout(500)  # Let animations settle
```

### Screenshot on Failure

```python
@pytest.fixture
def page_with_screenshot(page):
    yield page
    if hasattr(page, "_failed"):
        page.screenshot(path=f"tmp/failure-{datetime.now().isoformat()}.png")
```

## Common Tasks

### Login Flow

```python
def test_login():
    page.goto("/login")
    page.fill("[name=email]", "test@example.com")
    page.fill("[name=password]", "password")
    page.click("button[type=submit]")

    # Wait for redirect
    page.wait_for_url("/dashboard")
    assert page.locator("h1").text_content() == "Dashboard"
```

### Responsive Testing

```python
VIEWPORTS = {
    "mobile": (375, 667),
    "tablet": (768, 1024),
    "desktop": (1440, 900),
}

@pytest.mark.parametrize("name,size", VIEWPORTS.items())
def test_responsive(page, name, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto("/")
    page.screenshot(path=f"tmp/responsive-{name}.png")
```

### Form Validation

```python
def test_form_validation():
    page.goto("/signup")
    page.click("button[type=submit]")  # Submit empty

    # Check error messages
    assert page.locator(".error").count() > 0
    assert "required" in page.locator("[name=email] + .error").text_content()
```
