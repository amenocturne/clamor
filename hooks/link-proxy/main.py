"""Link proxy — shared URL transformation utilities.

Deterministic URL-to-placeholder mapping used by proxy.py to mask
internal URLs in API traffic. Keeps the regex, hashing, and
persistence logic in one place.
"""

import hashlib
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DOMAINS_FILE = SCRIPT_DIR / "domains.txt"
MAPPINGS_FILE = DATA_DIR / "mappings.json"

# Matches both URL placeholders [InternalLink_prefix_hash] and secret placeholders [TypeName_hash].
# Group 1: full type/prefix (may contain underscores, e.g. "InternalLink_wiki")
# Group 2: 8-char hex hash (used as key into mappings)
PLACEHOLDER_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_]*)_([a-f0-9]{8})\]")


def load_domains() -> list[str]:
    """Load internal domains from config file."""
    if not DOMAINS_FILE.exists():
        return []
    lines = DOMAINS_FILE.read_text().strip().split("\n")
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def build_url_pattern(domains: list[str]) -> re.Pattern | None:
    """Build regex to match URLs for configured domains."""
    if not domains:
        return None

    base_domains = set()
    for domain in domains:
        parts = domain.lower().split(".")
        if len(parts) >= 2:
            base_domains.add(".".join(parts[-2:]))

    if not base_domains:
        return None

    escaped = [re.escape(d) for d in base_domains]
    domains_re = r"(?:" + "|".join(escaped) + r")(?![A-Za-z0-9-])"

    pattern = (
        r"(?<![A-Za-z0-9_-])"
        r"(?:https?://)?"
        r"(?:[A-Za-z0-9_\-]+\.)*"
        rf"{domains_re}"
        r"(?::\d+)?"
        r"(?:/[A-Za-z0-9а-яА-ЯёЁ\-/._?=&%#@:+~]*)?(?<![.,;:])"
    )
    return re.compile(pattern, re.IGNORECASE)


def url_to_placeholder(url: str) -> tuple[str, str]:
    """Convert URL to deterministic placeholder. Returns (placeholder, hash)."""
    url_clean = re.sub(r"^https?://", "", url)
    prefix = url_clean.split("/")[0].split(".")[0]
    prefix = re.sub(r"[^a-zA-Z0-9]", "", prefix).lower() or "link"
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"[InternalLink_{prefix}_{url_hash}]", url_hash


def load_mappings() -> dict[str, str]:
    """Load global URL mappings."""
    if MAPPINGS_FILE.exists():
        try:
            return json.loads(MAPPINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_mappings(mappings: dict[str, str]) -> None:
    """Save global URL mappings."""
    MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAPPINGS_FILE.write_text(json.dumps(mappings, indent=2))


def transform_text(text: str, pattern: re.Pattern) -> tuple[str, dict[str, str]]:
    """Replace URLs with placeholders. Returns (transformed, new_mappings)."""
    new_mappings = {}
    matches = list(pattern.finditer(text))

    for match in reversed(matches):
        url = match.group()
        placeholder, url_hash = url_to_placeholder(url)
        new_mappings[url_hash] = url
        text = text[: match.start()] + placeholder + text[match.end() :]

    return text, new_mappings


def restore_text(text: str, mappings: dict[str, str]) -> str:
    """Replace placeholders with original URLs."""
    for match in reversed(list(PLACEHOLDER_RE.finditer(text))):
        url_hash = match.group(2)
        if url_hash in mappings:
            text = text[: match.start()] + mappings[url_hash] + text[match.end() :]
    return text


# Re-export so proxy.py can import transform_secrets alongside other main.py symbols.
from secrets import transform_secrets as transform_secrets  # noqa: F401  # type: ignore[no-redef]
