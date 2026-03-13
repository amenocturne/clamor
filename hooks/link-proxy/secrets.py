"""PII / secret detection and placeholder substitution.

Ports regex patterns from the anon detector library. No external dependencies.

Placeholder format: [TypeName_8hexchars]  e.g. [UUID_a1b2c3d4]

Public API:
    transform_secrets(text) -> (transformed_text, {hash: original})
"""

from __future__ import annotations

import hashlib
import re

# ---------------------------------------------------------------------------
# Compiled regexes (most-specific / longest patterns first)
# ---------------------------------------------------------------------------

# Application ID: 17 digits + 3 uppercase letters + 5+ alphanumeric chars
_APPLICATIONID_RE = re.compile(r"\b\d{17}[A-Z]{3}[0-9a-z]{5,}\b", re.IGNORECASE)

# Payment account: starts with 4, total 20 digits
_PAYMENT_ACCOUNT_RE = re.compile(r"(?P<payment_account>\b4\d{19}\b)")

# Correspondent account: starts with 301, total 20 digits
_CORRESPONDENT_ACCOUNT_RE = re.compile(r"(?P<correspondent_account>\b301\d{17}\b)")

# UUID: standard 8-4-4-4-12 hex, allows optional whitespace around dashes
_UUID_RE = re.compile(
    r"[0-9a-z]{8}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{12}",
    re.IGNORECASE,
)

# Contract: "договор" or "номер" (with optional endings), optional non-digit chars,
# then 5+ digit number. Excludes matches where extra text contains card/order/policy keywords.
_CONTRACT_RE = re.compile(
    r"\b(договор|номер)(а|у|ом|е)?\b\s*(?P<extra>\D{,10})\s*(?P<number>\d{5,})",
    re.IGNORECASE,
)
_CONTRACT_EXCLUSION_RE = re.compile(
    r"(карты|заказа|полиса|сч[её]та|заявки)", re.IGNORECASE
)

# Siebel ID: digit-dash-5to9 alphanumeric chars
_SIEBELID_RE = re.compile(r"\b\d-[A-Z0-9]{5,9}\b", re.IGNORECASE)

# Client code: 3 uppercase letters + "0" + 6+ digits
_CLIENTCODE_RE = re.compile(r"\b[A-Z]{3}0\d{6,}\b", re.IGNORECASE)

# PAN: 13-19 digits, optionally separated by spaces/dashes/dots (Luhn-validated below)
_PAN_RE = re.compile(r"((\d((\s*)|[-.])){13,19})")
_PAN_STRIP_RE = re.compile(r"[-\s.]")


# ---------------------------------------------------------------------------
# Luhn checksum validation (ported from stdlib — no external deps)
# ---------------------------------------------------------------------------

def _luhn_valid(number: str) -> bool:
    """Return True if the digit string passes the Luhn checksum."""
    digits = [int(c) for c in number]
    # Double every second digit from the right (starting at index -2)
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_placeholder(type_name: str, original: str) -> tuple[str, str]:
    """Return (placeholder, hash8) for the given original string."""
    h = hashlib.sha256(original.encode()).hexdigest()[:8]
    return f"[{type_name}_{h}]", h


def _replace_matches(
    text: str,
    matches: list[tuple[int, int, str]],  # (start, end, original)
    type_name: str,
) -> tuple[str, dict[str, str]]:
    """Replace all (start, end) spans in text with placeholders.

    Processes in reverse order so indices stay valid.
    Returns (transformed_text, new_mappings).
    """
    new_mappings: dict[str, str] = {}
    for start, end, original in reversed(matches):
        placeholder, h = _make_placeholder(type_name, original)
        new_mappings[h] = original
        text = text[:start] + placeholder + text[end:]
    return text, new_mappings


# ---------------------------------------------------------------------------
# Per-type detection functions
# ---------------------------------------------------------------------------

def _find_application_ids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _APPLICATIONID_RE.finditer(text)]


def _find_payment_accounts(text: str) -> list[tuple[int, int, str]]:
    return [
        (m.start("payment_account"), m.end("payment_account"), m.group("payment_account"))
        for m in _PAYMENT_ACCOUNT_RE.finditer(text)
    ]


def _find_correspondent_accounts(text: str) -> list[tuple[int, int, str]]:
    return [
        (
            m.start("correspondent_account"),
            m.end("correspondent_account"),
            m.group("correspondent_account"),
        )
        for m in _CORRESPONDENT_ACCOUNT_RE.finditer(text)
    ]


def _find_uuids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _UUID_RE.finditer(text)]


def _find_contracts(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _CONTRACT_RE.finditer(text):
        extra = m.group("extra")
        if _CONTRACT_EXCLUSION_RE.search(extra):
            continue
        start, end = m.span("number")
        results.append((start, end, m.group("number")))
    return results


def _find_siebel_ids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _SIEBELID_RE.finditer(text)]


def _find_client_codes(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _CLIENTCODE_RE.finditer(text)]


def _find_pans(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _PAN_RE.finditer(text):
        candidate = _PAN_STRIP_RE.sub("", m.group(1))
        if _luhn_valid(candidate):
            results.append((m.start(), m.end(), m.group(1)))
    return results


# ---------------------------------------------------------------------------
# Detector pipeline
# Order: longest/most-specific patterns first to avoid partial matches.
# Application IDs (25+ chars) before payment accounts (20 digits) before
# UUIDs (32 hex + dashes) before shorter patterns.
# ---------------------------------------------------------------------------

_DETECTORS: list[tuple[str, object]] = [
    ("ApplicationID", _find_application_ids),
    ("PaymentAccount", _find_payment_accounts),
    ("CorrespondentAccount", _find_correspondent_accounts),
    ("UUID", _find_uuids),
    ("Contract", _find_contracts),
    ("SiebelID", _find_siebel_ids),
    ("ClientCode", _find_client_codes),
    ("PAN", _find_pans),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transform_secrets(text: str) -> tuple[str, dict[str, str]]:
    """Find and replace PII/secrets with deterministic placeholders.

    Runs each detector in order. Already-replaced spans (placeholders)
    are not re-processed because patterns don't match placeholder syntax.

    Returns (transformed_text, {hash8: original}) for all replacements made.
    """
    all_mappings: dict[str, str] = {}

    for type_name, find_fn in _DETECTORS:
        matches = find_fn(text)  # type: ignore[operator]
        if matches:
            text, new_mappings = _replace_matches(text, matches, type_name)
            all_mappings.update(new_mappings)

    return text, all_mappings
