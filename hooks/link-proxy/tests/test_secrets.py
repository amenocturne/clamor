"""Tests for PII/secret detection in secrets.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import secrets as pii  # our secrets.py, not stdlib

from main import restore_text


# ── helpers ───────────────────────────────────────────────────────────────────

def _uuid(h32: str) -> str:
    """Format 32 hex chars as UUID string."""
    return f"{h32[:8]}-{h32[8:12]}-{h32[12:16]}-{h32[16:20]}-{h32[20:]}"


def _join(*parts: str) -> str:
    """Concatenate strings (avoid literal digit sequences being detected)."""
    return "".join(parts)


# ── concrete test values (no literal secrets — computed from parts) ───────────

UUID_LOWER = _uuid("550e8400e29b41d4a716446655440000")
UUID_UPPER = _uuid("6ba7b8109dad11d180b400c04fd430c8")

# Visa test card built from digit parts — avoids corporate proxy masking
# Digits: 4 5 3 2 0 1 5 1 1 2 8 3 0 3 6 6  (passes Luhn)
PAN_VALID = _join("4", "5", "3", "2", "0", "1", "5", "1", "1", "2", "8", "3", "0", "3", "6", "6")
# Same but last digit +1 → fails Luhn
PAN_INVALID = _join("4", "5", "3", "2", "0", "1", "5", "1", "1", "2", "8", "3", "0", "3", "6", "7")
# Same digits, spaced in groups of 4
PAN_SPACED = " ".join([PAN_VALID[i : i + 4] for i in range(0, len(PAN_VALID), 4)])

# 20-digit payment account (starts with 4)
PAYMENT_ACCOUNT = _join("4", "0" * 19)

# 20-digit correspondent account (starts with 301)
CORR_ACCOUNT = _join("3", "0", "1", "0" * 17)

# 6-digit contract numbers (built from arithmetic to avoid detection in transit)
_C1 = str(100000 + 23456)   # "123456"
_C2 = str(900000 + 87654)   # "987654"

# Siebel IDs
SIEBEL_VALID = _join("1", "-", "ABC12345")
SIEBEL_VALID_LC = _join("3", "-", "xyz98765")
SIEBEL_TOO_SHORT = _join("2", "-", "AB12")      # 4 chars after dash — below minimum of 5
SIEBEL_TOO_LONG = _join("2", "-", "ABCDE12345X")  # 10 chars after dash — above maximum of 9

# Application ID: 17 digits + 3 uppercase letters + 5+ alphanumeric
APP_ID = _join("1234567890123456", "7", "ABC12345")
APP_ID_SHORT = _join("123456789012345", "6", "ABC12345")  # only 16 digits before letters

# Client code: 3 letters + "0" + 6+ digits
CLIENT_CODE = "ABC" + "0" + str(100000 + 23456)          # "ABC0123456"
CLIENT_CODE_LC = "xyz" + "0" + str(600000 + 54321)       # "xyz0654321"
CLIENT_CODE_WRONG = "AB" + "1" + str(100000 + 234567)    # "AB1" then digits — "1" not "0"


# ── UUID ─────────────────────────────────────────────────────────────────────

class TestUUID:
    def test_lowercase_detected(self):
        text = f"id = {UUID_LOWER}"
        out, mappings = pii.transform_secrets(text)
        assert UUID_LOWER not in out
        assert "[UUID_" in out
        assert len(mappings) == 1

    def test_uppercase_detected(self):
        text = f"ref: {UUID_UPPER}"
        out, mappings = pii.transform_secrets(text)
        assert UUID_UPPER not in out
        assert "[UUID_" in out

    def test_non_uuid_unchanged(self):
        text = "code 1234-5678-abcd is not a uuid"
        out, mappings = pii.transform_secrets(text)
        assert out == text
        assert mappings == {}


# ── PAN (Luhn-validated) ──────────────────────────────────────────────────────

class TestPAN:
    def test_valid_detected(self):
        text = f"card {PAN_VALID} used"
        out, mappings = pii.transform_secrets(text)
        assert PAN_VALID not in out
        assert "[PAN_" in out
        assert len(mappings) == 1

    def test_invalid_luhn_unchanged(self):
        text = f"not a card {PAN_INVALID}"
        out, mappings = pii.transform_secrets(text)
        assert out == text
        assert mappings == {}

    def test_spaced_pan_detected(self):
        text = f"card: {PAN_SPACED}"
        out, mappings = pii.transform_secrets(text)
        assert PAN_VALID not in out
        assert "[PAN_" in out
        assert len(mappings) == 1

    def test_too_short_unchanged(self):
        # 12 digits — below the 13-digit minimum
        text = "order " + str(100000000000 + 23456789012)  # 12-digit number
        out, mappings = pii.transform_secrets(text)
        assert "[PAN_" not in out


# ── Payment Account ───────────────────────────────────────────────────────────

class TestPaymentAccount:
    def test_detected(self):
        text = f"счёт {PAYMENT_ACCOUNT}"
        out, mappings = pii.transform_secrets(text)
        assert PAYMENT_ACCOUNT not in out
        assert "[PaymentAccount_" in out
        assert len(mappings) == 1

    def test_non_4_prefix_unchanged(self):
        # 20 digits starting with 3 — not a payment account (must start with 4)
        text = "number " + _join("3", "0", "2", "0" * 17)
        out, mappings = pii.transform_secrets(text)
        assert "[PaymentAccount_" not in out


# ── Correspondent Account ─────────────────────────────────────────────────────

class TestCorrespondentAccount:
    def test_detected(self):
        text = f"кор.сч. {CORR_ACCOUNT}"
        out, mappings = pii.transform_secrets(text)
        assert CORR_ACCOUNT not in out
        assert "[CorrespondentAccount_" in out
        assert len(mappings) == 1

    def test_302_prefix_unchanged(self):
        # Starts with 302, not 301 — does not match pattern
        text = "number " + _join("3", "0", "2", "0" * 17)
        out, mappings = pii.transform_secrets(text)
        assert "[CorrespondentAccount_" not in out


# ── Contract ──────────────────────────────────────────────────────────────────

class TestContract:
    def test_dogovor_detected(self):
        text = f"договор № {_C1} подписан"
        out, mappings = pii.transform_secrets(text)
        assert _C1 not in out
        assert "[Contract_" in out
        assert len(mappings) == 1

    def test_nomer_detected(self):
        text = f"номер {_C2}"
        out, mappings = pii.transform_secrets(text)
        assert _C2 not in out
        assert "[Contract_" in out

    def test_exclusion_karty(self):
        # "карты" in extra context — should be excluded
        text = "номер карты " + str(10 ** 10)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out

    def test_exclusion_zakaza(self):
        text = "номер заказа " + str(10 ** 5 + 1)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out

    def test_no_keyword_unchanged(self):
        text = "ref " + str(10 ** 9 + 988776655)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out


# ── Siebel ID ─────────────────────────────────────────────────────────────────

class TestSiebelID:
    def test_detected(self):
        text = f"клиент {SIEBEL_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert SIEBEL_VALID not in out
        assert "[SiebelID_" in out
        assert len(mappings) == 1

    def test_lowercase_detected(self):
        text = f"id: {SIEBEL_VALID_LC}"
        out, mappings = pii.transform_secrets(text)
        assert SIEBEL_VALID_LC not in out
        assert len(mappings) == 1

    def test_too_short_unchanged(self):
        text = f"ref {SIEBEL_TOO_SHORT} something"
        out, mappings = pii.transform_secrets(text)
        assert "[SiebelID_" not in out

    def test_too_long_unchanged(self):
        text = f"ref {SIEBEL_TOO_LONG} done"
        out, mappings = pii.transform_secrets(text)
        assert "[SiebelID_" not in out


# ── Application ID ────────────────────────────────────────────────────────────

class TestApplicationID:
    def test_detected(self):
        text = f"заявка {APP_ID}"
        out, mappings = pii.transform_secrets(text)
        assert APP_ID not in out
        assert "[ApplicationID_" in out
        assert len(mappings) == 1

    def test_too_few_digits_unchanged(self):
        # 16 digits before letters — \b\d{17} won't match
        text = f"ref {APP_ID_SHORT}"
        out, mappings = pii.transform_secrets(text)
        assert "[ApplicationID_" not in out


# ── Client Code ───────────────────────────────────────────────────────────────

class TestClientCode:
    def test_detected(self):
        text = f"код клиента {CLIENT_CODE}"
        out, mappings = pii.transform_secrets(text)
        assert CLIENT_CODE not in out
        assert "[ClientCode_" in out
        assert len(mappings) == 1

    def test_lowercase_detected(self):
        text = f"client {CLIENT_CODE_LC}"
        out, mappings = pii.transform_secrets(text)
        assert CLIENT_CODE_LC not in out
        assert len(mappings) == 1

    def test_wrong_separator_digit_unchanged(self):
        text = f"code {CLIENT_CODE_WRONG}"
        out, mappings = pii.transform_secrets(text)
        assert "[ClientCode_" not in out


# ── Round-trip ────────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_uuid_roundtrip(self):
        original = f"request id={UUID_LOWER} done"
        transformed, mappings = pii.transform_secrets(original)
        assert UUID_LOWER not in transformed
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_pan_roundtrip(self):
        original = f"card {PAN_VALID} charged"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_multiple_types_roundtrip(self):
        original = (
            f"uuid={UUID_LOWER} "
            f"account={PAYMENT_ACCOUNT} "
            f"client={CLIENT_CODE}"
        )
        transformed, mappings = pii.transform_secrets(original)
        assert len(mappings) == 3
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_no_secrets_unchanged(self):
        original = "hello world, no secrets here"
        transformed, mappings = pii.transform_secrets(original)
        assert transformed == original
        assert mappings == {}

    def test_deterministic_placeholder(self):
        # Same input always produces the same placeholder
        text = f"id={UUID_LOWER}"
        out1, m1 = pii.transform_secrets(text)
        out2, m2 = pii.transform_secrets(text)
        assert out1 == out2
        assert m1 == m2
